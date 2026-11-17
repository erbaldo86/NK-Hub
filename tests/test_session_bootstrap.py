# -*- coding: utf-8 -*-
"""
Test Zero-Mock per nk_session_bootstrap (P1-BUG-10, P2-BUG-17, P1-BUG-11).
Modulo: tests/test_session_bootstrap.py.
Valida auto-discesa Antigravity -> NK_Hub, XML stripping, --hook lastUserInput e cache isolation.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

boot_mod = load_nk_script_module("nk_session_bootstrap")
w2pc_mod = load_nk_script_module("win32_2pc_engine")

pytestmark = pytest.mark.fast


def _make_clean_hub(hub_dir: Path) -> None:
    """Crea una radice NK_Hub minimale conforme ai controlli Fast-Stat."""
    for sub in ("scripts", ".agents", "nk_tracking", ".wal"):
        (hub_dir / sub).mkdir(parents=True, exist_ok=True)
    (hub_dir / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}),
        encoding="utf-8",
    )


def test_p1_bug_10_parent_cwd_autodescent_and_hook_last_user_input(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica auto-discesa da cartella padre Antigravity e --hook con lastUserInput + XML."""
    assert isolated_nk_env.is_dir()
    parent_ws = tmp_path / "Antigravity"
    hub_ws = parent_ws / "NK_Hub"
    _make_clean_hub(hub_ws)

    boot = boot_mod.NKSessionBootstrap(workspace_root=parent_ws, conversation_id="conv-desc")
    assert boot.workspace_root == hub_ws.resolve()
    assert boot.repo_root == hub_ws.resolve()

    hook_payload = json.dumps(
        {
            "conversationId": "conv-hook-xml",
            "lastUserInput": (
                "<USER_REQUEST>\navvia nk hub\n</USER_REQUEST>\n"
                "<ADDITIONAL_METADATA>meta</ADDITIONAL_METADATA>\n"
                "<USER_SETTINGS_CHANGE>cfg</USER_SETTINGS_CHANGE>"
            ),
        }
    )
    rc, out_txt, _ = call_script_main_captured(
        boot_mod, ["--hook", "--project-root", str(parent_ws)], stdin_text=hook_payload
    )
    assert rc == 0
    res = json.loads(out_txt)
    assert res["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    assert res["conversation_id"] == "conv-hook-xml"


def test_p1_bug_10_fastguard_conv_inference_and_recent_transcript_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica inferenza conv_id da fastguard_<cid>.json (>60s), scarto default_* e fallback brain."""
    hooks_dir = isolated_nk_env / "nk_hooks_env"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    default_int = hooks_dir / "default_deadbeef_integrity.json"
    default_int.write_text("{}", encoding="utf-8")
    fg_file = hooks_dir / "fastguard_conv-real-120.json"
    fg_file.write_text("{}", encoding="utf-8")
    t_90s = time.time() - 90.0
    os.utime(fg_file, (t_90s, t_90s))

    assert boot_mod.NKSessionBootstrap._infer_active_conversation_id(120.0) == "conv-real-120"

    ws = tmp_path / "hub_recent"
    _make_clean_hub(ws)
    fake_home = tmp_path / "user_home"
    conv_dir = fake_home / ".gemini" / "antigravity" / "brain" / "conv-fallback-xml" / ".system_generated" / "logs"
    conv_dir.mkdir(parents=True, exist_ok=True)
    tp_file = conv_dir / "transcript.jsonl"
    tp_file.write_text(
        json.dumps(
            {
                "type": "USER_INPUT",
                "source": "USER_EXPLICIT",
                "content": "<USER_REQUEST>\nAvvia NK Hub\n</USER_REQUEST>\n<ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    boot_fb = boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="")
    res_fb = boot_fb.run_bootstrap(fast_stat=False)
    assert res_fb["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    assert res_fb["conversation_id"] == "conv-fallback-xml"
    assert res_fb["context_mode"] == "ACTIVE_SESSION"


def test_p2_bug_17_cross_conversation_cache_isolation_and_p1_bug_11_wal(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica blocco cache hit cross-conversazione (P2-BUG-17) e pulizia WAL deep subdir (P1-BUG-11)."""
    assert isolated_nk_env.is_dir()
    ws = tmp_path / "cache_iso_ws"
    _make_clean_hub(ws)
    tp_a = tmp_path / "tp_a.jsonl"
    tp_a.write_text(
        json.dumps({"type": "USER_INPUT", "content": "<USER_REQUEST>\navvia nk hub\n</USER_REQUEST>"})
        + "\n",
        encoding="utf-8",
    )

    boot_a = boot_mod.NKSessionBootstrap(
        workspace_root=ws, conversation_id="conv-alpha", transcript_path=tp_a
    )
    res_a = boot_a.run_bootstrap(fast_stat=False)
    assert res_a["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"

    boot_b = boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="conv-beta")
    assert boot_b._can_fast_pass() is False

    boot_anon = boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="")
    assert boot_anon._can_fast_pass() is False

    deep_target = ws / "scripts" / "_internal" / "deep_pkg" / "submod.py"
    deep_target.parent.mkdir(parents=True, exist_ok=True)
    wal_mgr = w2pc_mod.WriteAheadLogManager()
    wal_path = wal_mgr.write_wal(
        tx_id="tx_deep_stale",
        target_path=deep_target,
        staging_path=ws / ".staging" / "scripts" / "_internal" / "deep_pkg" / "submod.py",
        payload_sha256="a" * 64,
        payload_crc32=123,
        state="PREPARED",
    )
    assert wal_path.is_file()
    old_ts = time.time() - 300.0
    os.utime(wal_path, (old_ts, old_ts))

    purge_res = boot_mod.enforce_wal_hygiene(workspace_root=ws, ttl_seconds=30.0)
    assert purge_res["stale_wals_purged"] >= 1
    assert not wal_path.exists()
