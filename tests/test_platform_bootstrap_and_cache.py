# -*- coding: utf-8 -*-
"""Suite piattaforma DOM-01/DOM-03: Bootstrap, Cache WAL, Handoff e Wave 2 Generation."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

try:
    from conftest import CONFTEST_VERSION, WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module, load_script_by_relpath
except ImportError:
    from tests.conftest import CONFTEST_VERSION, WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module, load_script_by_relpath

boot_mod = load_nk_script_module("nk_session_bootstrap")
cache_mod = load_nk_script_module("deterministic_api_cache")
hand_mod = load_nk_script_module("nk_session_handoff")
sentry_mod = load_nk_script_module("nk_context_sentry")
DeterministicApiCache = cache_mod.DeterministicApiCache
_GEN_TRIGGERS: tuple[str, ...] = ("avvia generation", "avvia nk generation", "avvia nk hub generation", "avvia ambiente generation", "start generation", "start nk generation", "attiva generation", "attiva ambiente generation")


def _make_clean_hub(hub_dir: Path, pass_pct: float = 100.0) -> Path:
    """Crea una radice NK_Hub minimale conforme ai controlli Fast-Stat."""
    for sub in ("scripts", ".agents", "nk_tracking", ".wal"):
        (hub_dir / sub).mkdir(parents=True, exist_ok=True)
    (hub_dir / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": pass_pct, "unit_tests_total": 100}}), encoding="utf-8"
    )
    return hub_dir


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Scrive una lista di record JSONL UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows), encoding="utf-8")


def _assert_wal_hygiene_and_staging_dirty(tmp_path: Path) -> tuple[Any, Path]:
    """Verifica wal_hygiene.py e is_staging_dirty() in root_hygiene.py."""
    from _internal.nk_session_bootstrap import root_hygiene as rh, wal_hygiene as wh

    wh_ws = tmp_path / "wh_ws"
    (wh_ws / ".wal" / "quarantine").mkdir(parents=True)
    boot_wh = boot_mod.NKSessionBootstrap(workspace_root=wh_ws)
    assert wh.has_actionable_wal_entries(boot_wh) is False
    tx_wal = wh_ws / ".wal" / "tx.wal"
    tx_wal.write_text('{"state": "PREPARE"}\n{"state": "COMMITTED"}\n', encoding="utf-8")
    assert (wh.has_actionable_wal_entries(boot_wh), wh.inspect_wal_state(tx_wal)) == (True, "COMMITTED")
    for name, raw in (("empty.wal", b""), ("bin.wal", b"\xff\xfe\xfd"), ("list.wal", b"[1, 2]")):
        (wh_ws / ".wal" / name).write_bytes(raw)
        assert wh.inspect_wal_state(wh_ws / ".wal" / name) == "CORRUPTED"
    (wh_ws / ".staging" / "clean_sub").mkdir(parents=True)
    (wh_ws / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    (wh_ws / ".staging" / "clean_sub" / ".gitkeep").write_text("", encoding="utf-8")
    assert (rh.is_staging_dirty(boot_wh), rh.is_staging_dirty(boot_wh, cached={"staging_mtime": rh.get_staging_mtime(boot_wh), "staging_dirty_warning": True})) == (False, True)
    return boot_wh, wh_ws


def _assert_root_hygiene_extra_branches(boot: Any, ws_root: Path, monkeypatch: Any) -> None:
    """Copre branch aggiuntivi di root_hygiene.py: whitelist ext, scandir fallback e baseline."""
    from _internal.nk_session_bootstrap import constants as _consts, root_hygiene as rh

    for name in (".hidden", "quality_baseline.json.bak", "conftest.py", "setup.py", "README.md"):
        (ws_root / name).write_text("ok\n", encoding="utf-8")
    assert rh.has_root_file_pollution_quick(boot, is_hub_root=False) is False
    (ws_root / "rogue.py").write_text("x = 1\n", encoding="utf-8")
    assert rh.has_root_file_pollution_quick(boot, is_hub_root=False) is True
    (ws_root / "src_app").mkdir()
    rem, real_scandir = [2], os.scandir
    with monkeypatch.context() as mp:
        mp.setattr(_consts, "HUB_ROOT", ws_root.resolve())
        mp.setattr(boot_mod, "HUB_ROOT", ws_root.resolve())
        assert "src_app" not in rh.check_root_hygiene(boot, use_fast_cache=True)["violations"]
        (ws_root / "src_app" / "mod.py").write_text("a = 1\n", encoding="utf-8")
        assert "src_app" in rh.check_root_hygiene(boot, use_fast_cache=False)["violations"]
        mp.setattr(os, "scandir", lambda p=".", *_a, **_kw: (rem.__setitem__(0, rem[0] - 1) or (_ for _ in ()).throw(OSError("no_scandir"))) if (Path(p).resolve() == ws_root.resolve() and rem[0] > 0) else real_scandir(p, *_a, **_kw))
        fb_res = rh.check_root_hygiene(boot, use_fast_cache=False)
        assert (fb_res["passed"], "rogue.py" in fb_res["violations"], "src_app" in fb_res["violations"]) == (False, True, True)
    (ws_root / "nk_tracking").mkdir(exist_ok=True)
    bl_f = ws_root / "nk_tracking" / "quality_baseline.json"
    boot._cached_baseline_stat = None
    bl_f.write_text(json.dumps({"metrics": {"total_golden_tests": {"value": 12}}, "pass_rate_pct": 100.0}), encoding="utf-8")
    v_ok = rh.verify_baseline(boot)
    boot._cached_baseline_stat = None
    bl_f.write_text(json.dumps({"pass_rate": 80.0}), encoding="utf-8")
    assert (v_ok["passed"], v_ok["total_tests"], rh.verify_baseline(boot)["passed"]) == (True, 12, False)


@pytest.mark.fast
def test_bootstrap_fast_stat_pollution_wal_and_root_hygiene(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica Fast-Stat, root pollution, bonifica WAL e rami wal_hygiene/root_hygiene."""
    from _internal.nk_session_bootstrap import root_hygiene as rh

    ws_root = _make_clean_hub(tmp_path / "isolated_hub_ws")
    boot = boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-alpha")
    assert (boot.run_bootstrap(fast_stat=False)["status"], "fast_stat" in boot.run_bootstrap(fast_stat=True)["checks"]) == ("PASS", True)
    saved_mtime = boot._get_root_mtime()
    tmp_polluter = ws_root / "rogue_artifact.tmp"
    tmp_polluter.write_text("temp pollution", encoding="utf-8")
    os.utime(ws_root, (saved_mtime, saved_mtime))
    hyg = boot._check_root_hygiene(use_fast_cache=True, cached={"root_mtime": boot._get_root_mtime(), "timestamp_epoch": time.time(), "root_hygiene_violations": []})
    assert (boot._has_root_file_pollution_quick(is_hub_root=False), hyg["passed"], "rogue_artifact.tmp" in hyg["violations"], boot.run_bootstrap(fast_stat=True)["checks"]["project_isolation"]["passed"]) == (True, False, True, False)
    tmp_polluter.unlink(missing_ok=True)
    assert boot.run_bootstrap(fast_stat=False)["status"] == "PASS"
    stale_wal = ws_root / ".wal" / "expired_tx.wal"
    stale_wal.write_text('{"state": "PREPARE"}', encoding="utf-8")
    os.utime(stale_wal, (time.time() - 180.0, time.time() - 180.0))
    res_wal = boot.run_bootstrap(fast_stat=True)
    assert (res_wal["status"], stale_wal.exists(), res_wal["checks"]["wal_hygiene"]["stale_wals_purged"] >= 1) == ("PASS", False, True)
    boot_wh, wh_ws = _assert_wal_hygiene_and_staging_dirty(tmp_path)
    _assert_root_hygiene_extra_branches(boot_wh, wh_ws, monkeypatch)
    (wh_ws / ".staging" / "dirty.py").write_text("x = 1\n", encoding="utf-8")
    boot_wh._cached_staging_mtime = None
    assert rh.is_staging_dirty(boot_wh) is True


def _assert_transcript_prompt_conv_and_subagent(tmp_path: Path, monkeypatch: Any) -> Path:
    """Verifica inferenza conversation_id, subagent head e has_newer_brain_directory."""
    from _internal.nk_session_bootstrap import transcript_prompt as tp_mod

    hooks_d = tmp_path / "boot_hooks"
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_d))
    assert boot_mod.NKSessionBootstrap._infer_active_conversation_id(60.0) == ""
    (hooks_d / "nested_dir").mkdir(parents=True)
    assert boot_mod.NKSessionBootstrap._infer_active_conversation_id(60.0) == ""
    (hooks_d / "probe_default.jsonl").write_text("{}", encoding="utf-8")
    (hooks_d / "probe_cid_alpha.jsonl").write_text("{}", encoding="utf-8")
    p_beta = hooks_d / "cid_beta_integrity.json"
    p_beta.write_text("{}", encoding="utf-8")
    now = time.time()
    os.utime(hooks_d / "probe_cid_alpha.jsonl", (now - 10.0, now - 10.0))
    os.utime(p_beta, (now, now))
    assert boot_mod.NKSessionBootstrap._infer_active_conversation_id(60.0) == "cid_beta"
    for raw, exp in (
        (b"", False), (b"   \n", False), (b'{"source": "SYSTEM", "content": "init"}\n', True),
        (b'{"source": "USER", "content": "<Agent System Instructions> <subagent_reminder>"}\n', True),
        (b'{"role": "assistant", "text": "[Message] sender=a <env_capsule>"}\n', True),
        (b'{"source": "USER", "content": "procedi"}\n', False), (b'not_json <Agent System Instructions> <subagent_reminder>\n', True),
        (b'not_json "source": "USER"\n', False), (b'not_json "source": "SYSTEM"\n', True),
    ):
        assert boot_mod.NKSessionBootstrap._is_subagent_transcript_head(raw) is exp
    assert tp_mod.has_newer_brain_directory(tmp_path / "missing_brain" / "c" / "l" / "t.jsonl", 60.0) is False
    brain = tmp_path / "b_root"
    old_tp = brain / "c_old" / ".system_generated" / "logs" / "transcript.jsonl"
    old_tp.parent.mkdir(parents=True)
    old_tp.write_text("{}", encoding="utf-8")
    (brain / "stray_file.txt").write_text("x", encoding="utf-8")
    (brain / "c_older").mkdir()
    os.utime(old_tp, (now + 10.0, now + 10.0))
    os.utime(brain / "c_older", (now - 30.0, now - 30.0))
    assert boot_mod.NKSessionBootstrap._has_newer_brain_directory(old_tp, 60.0) is False
    os.utime(old_tp, (now - 10.0, now - 10.0))
    (brain / "c_new").mkdir()
    os.utime(brain / "c_new", (now, now))
    assert boot_mod.NKSessionBootstrap._has_newer_brain_directory(old_tp, 60.0) is True
    return brain


def _assert_transcript_prompt_extract_and_tail(ws_root: Path, brain: Path, tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica extract_user_prompt_from_line, chunk carry e find_recent_transcript."""
    from _internal.nk_session_bootstrap import constants as _consts, transcript_prompt as tp_mod

    assert [tp_mod.extract_user_prompt_from_line(r) for r in (b"[1, 2]\n", json.dumps({"type": "USER_INPUT", "content": [" ", {"text": "ciao"}, {"content": "nk"}]}).encode(), json.dumps({"type": "USER_INPUT", "content": ""}).encode(), json.dumps({"type": "USER_INPUT", "content": "<CONTEXT_SUMMARY> x"}).encode())] == [None, "ciao\nnk", None, None]
    tp_empty, tp_multi = tmp_path / "empty_tp.jsonl", tmp_path / "multi_tp.jsonl"
    tp_empty.write_bytes(b"")
    _write_jsonl(tp_multi, [{"type": "USER_INPUT", "content": "primo"}, {"type": "MODEL", "content": "m" * 90}])
    boot_m = boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-m", transcript_path=tp_multi)
    st_m = tp_multi.stat()
    assert boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-tp", transcript_path=tp_empty)._detect_latest_user_prompt() is None
    assert boot_m._detect_latest_user_prompt(cached={"last_transcript_path": str(tp_multi), "transcript_mtime": st_m.st_mtime, "transcript_size": st_m.st_size, "cached_latest_user_prompt": "cached_p"}) == "cached_p"
    with monkeypatch.context() as mp:
        mp.setattr(_consts, "BINARY_CHUNK_SIZE", 48)
        assert boot_m._detect_latest_user_prompt() == "primo"
    assert tp_mod.find_recent_transcript(boot_m, brain) == tp_multi.resolve()


@pytest.mark.integration
def test_bootstrap_baseline_onboarding_resilience_and_transcript_prompt(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica baseline 50% fail, onboarding bypass, tail resilience e branch transcript_prompt."""
    ws_root = _make_clean_hub(tmp_path / "onboarding_ws", pass_pct=50.0)
    res_bad = boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-base").run_bootstrap(fast_stat=True)
    assert (res_bad["status"], res_bad["checks"]["quality_baseline"]["unit_pass_pct"]) == ("FAIL", 50.0)
    tp_err, tp_ok = tmp_path / "transcript_err.jsonl", tmp_path / "transcript_ok.jsonl"
    _write_jsonl(tp_err, [{"source": "USER", "content": "Analizza il bug per cui avvia nk hub mostra un errore"}])
    _write_jsonl(tp_ok, [{"source": "USER", "content": "Avvia NK Hub!"}])
    assert boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-ob-1", transcript_path=tp_err)._resolve_onboarding_and_gate_mode() == ("NONE", "CONFIRM")
    assert boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-ob-2", transcript_path=tp_ok)._resolve_onboarding_and_gate_mode() == ("ONBOARDING_BYPASS_VERIFIED", "BYPASSED")
    (ws_root / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8")
    sim_brain = tmp_path / "brain"
    tp_red = sim_brain / "conv-old-red" / ".system_generated" / "logs" / "transcript.jsonl"
    _write_jsonl(tp_red, [{"step_index": i, "source": "USER", "content": "x" * 1200} for i in range(260)])
    assert boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-old-red", transcript_path=tp_red).run_bootstrap(fast_stat=False)["checks"]["context_sentry"]["status"] == "RED"
    boot_anon = boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="")
    os.utime(tp_red, (time.time() - 300.0, time.time() - 300.0))
    assert boot_anon._find_recent_transcript(sim_brain) is None
    os.utime(tp_red, (time.time(), time.time()))
    assert boot_anon.run_bootstrap(fast_stat=True)["checks"]["context_sentry"]["status"] != "RED"
    tp_res = tmp_path / "transcript_resilience.jsonl"
    _write_jsonl(tp_res, [
        {"step_index": 56, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-09T18:45:49Z", "input_tokens": 5582, "cache_read_tokens": 55484, "content": "Analisi."},
        {"step_index": 57, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-09T18:50:13Z", "content": "Procedi."},
        {"step_index": 84, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-09T18:50:15Z", "input_tokens": 62615, "cache_read_tokens": 0, "output_tokens": 7136, "tool_calls": [{"name": "write_file"} for _ in range(4)], "content": "Write."},
    ])
    risks = boot_mod._inspect_tail_resilience_risks(tp_res, t_size=tp_res.stat().st_size, est_tokens=15000)
    rep = sentry_mod.NKContextSentry(workspace_root=tmp_path, profile="argon").analyze_transcript(tp_res)
    assert (sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"input_tokens": 5582, "cache_read_tokens": 55484}), risks["kv_cache_cold_risk"], risks["rpc_stream_burst_risk"], risks["idle_gap_seconds"] >= 264.0, rep["kv_cache_cold_risk"]) == (61066, True, True, True, True)
    brain = _assert_transcript_prompt_conv_and_subagent(tmp_path, monkeypatch)
    _assert_transcript_prompt_extract_and_tail(ws_root, brain, tmp_path, monkeypatch)


def _assert_p13_cache_isolation(tmp_path: Path, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica cache workspace-keyed, inferenza conv_id e invalidazione tail P1-3."""
    ws_a, ws_b, ws_c = _make_clean_hub(tmp_path / "ws_alpha"), _make_clean_hub(tmp_path / "ws_beta"), _make_clean_hub(tmp_path / "ws_gamma")
    boot_a, boot_b = boot_mod.NKSessionBootstrap(workspace_root=ws_a, conversation_id="conv-a"), boot_mod.NKSessionBootstrap(workspace_root=ws_b, conversation_id="conv-b")
    assert (boot_a.fast_cache_file != boot_b.fast_cache_file, ".bootstrap_fast_cache_" in boot_a.fast_cache_file.name, boot_a.run_bootstrap(fast_stat=False)["status"], boot_b.run_bootstrap(fast_stat=False)["status"]) == (True, True, "PASS", "PASS")
    assert json.loads(boot_a.fast_cache_file.read_text(encoding="utf-8"))["workspace_root"] == str(ws_a.resolve())
    (hooks_dir / "probe_cli_conv_99.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("NK_CONVERSATION_ID", raising=False)
    assert (boot_mod.NKSessionBootstrap(workspace_root=boot_mod.HUB_ROOT, hook_mode=False).conversation_id, boot_mod.NKSessionBootstrap(workspace_root=ws_a, hook_mode=False).conversation_id) == ("cli_conv_99", "")
    (hooks_dir / "probe_cli_conv_99.jsonl").unlink(missing_ok=True)
    tp_c = tmp_path / "tp_p13.jsonl"
    _write_jsonl(tp_c, [{"step_index": 1, "source": "USER", "content": "ciao"}])
    boot_c = boot_mod.NKSessionBootstrap(workspace_root=ws_c, conversation_id="conv-c", transcript_path=tp_c)
    assert boot_c.run_bootstrap(fast_stat=False)["onboarding_bypass"] == "NONE"
    with tp_c.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"step_index": 2, "source": "MODEL", "content": "ok"}) + "\n")
    assert (boot_c._can_fast_pass(), "fast_stat" in boot_c.run_bootstrap(fast_stat=True)["checks"]) == (True, True)
    with tp_c.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"step_index": 3, "source": "USER", "type": "USER_INPUT", "content": "avvia nk hub"}) + "\n")
    assert (boot_c._can_fast_pass(), boot_c.run_bootstrap(fast_stat=True)["onboarding_bypass"]) == (False, "ONBOARDING_BYPASS_VERIFIED")
    boot_c.explicit_prompt = "analizza bug"
    assert (boot_c._can_fast_pass(), boot_c.run_bootstrap(fast_stat=True, prompt="analizza bug")["onboarding_bypass"]) == (False, "NONE")


@pytest.mark.integration
def test_bootstrap_autodescent_conv_inference_and_cross_conv_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Verifica P1-3 cache workspace-keyed, P1-BUG-10 autodescent/--hook e P2-BUG-17/P1-BUG-11 WAL."""
    hooks_dir = isolated_nk_env / "nk_hooks_env"
    _assert_p13_cache_isolation(tmp_path, hooks_dir, monkeypatch)
    parent_ws = tmp_path / "Antigravity"
    hub_ws = _make_clean_hub(parent_ws / "NK_Hub")
    hook_payload = json.dumps({"conversationId": "conv-hook-xml", "lastUserInput": "<USER_REQUEST>\navvia nk hub\n</USER_REQUEST>\n<ADDITIONAL_METADATA>meta</ADDITIONAL_METADATA>"})
    rc_hk, out_hk, _ = call_script_main_captured(boot_mod, ["--hook", "--project-root", str(parent_ws)], stdin_text=hook_payload)
    assert (boot_mod.NKSessionBootstrap(workspace_root=parent_ws, conversation_id="conv-desc").workspace_root, rc_hk, json.loads(out_hk)["onboarding_bypass"]) == (hub_ws.resolve(), 0, "ONBOARDING_BYPASS_VERIFIED")
    (hooks_dir / "default_deadbeef_integrity.json").write_text("{}", encoding="utf-8")
    fg_file = hooks_dir / "fastguard_conv-real-120.json"
    fg_file.write_text("{}", encoding="utf-8")
    os.utime(fg_file, (time.time() - 90.0, time.time() - 90.0))
    user_home = tmp_path / "user_home"
    _write_jsonl(user_home / ".gemini" / "antigravity" / "brain" / "conv-fallback-xml" / ".system_generated" / "logs" / "transcript.jsonl", [{"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "<USER_REQUEST>\nAvvia NK Hub\n</USER_REQUEST>"}])
    monkeypatch.setenv("USERPROFILE", str(user_home))
    res_fb = boot_mod.NKSessionBootstrap(workspace_root=_make_clean_hub(tmp_path / "hub_recent"), conversation_id="").run_bootstrap(fast_stat=False)
    assert (boot_mod.NKSessionBootstrap._infer_active_conversation_id(120.0), res_fb["onboarding_bypass"], res_fb["conversation_id"]) == ("conv-real-120", "ONBOARDING_BYPASS_VERIFIED", "conv-fallback-xml")
    ws_iso = _make_clean_hub(tmp_path / "cache_iso_ws")
    tp_a = tmp_path / "tp_a.jsonl"
    _write_jsonl(tp_a, [{"type": "USER_INPUT", "content": "<USER_REQUEST>\navvia nk hub\n</USER_REQUEST>"}])
    assert boot_mod.NKSessionBootstrap(workspace_root=ws_iso, conversation_id="conv-alpha", transcript_path=tp_a).run_bootstrap(fast_stat=False)["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    assert (boot_mod.NKSessionBootstrap(workspace_root=ws_iso, conversation_id="conv-beta")._can_fast_pass(), boot_mod.NKSessionBootstrap(workspace_root=ws_iso, conversation_id="")._can_fast_pass()) == (False, False)
    deep_t = ws_iso / "scripts" / "_internal" / "deep_pkg" / "submod.py"
    deep_t.parent.mkdir(parents=True)
    wal_p = load_nk_script_module("win32_2pc_engine").WriteAheadLogManager().write_wal("tx_deep_stale", deep_t, ws_iso / ".staging" / "submod.py", "a" * 64, 123, "PREPARED")
    os.utime(wal_p, (time.time() - 300.0, time.time() - 300.0))
    assert (boot_mod.enforce_wal_hygiene(workspace_root=ws_iso, ttl_seconds=30.0)["stale_wals_purged"] >= 1, wal_p.exists()) == (True, False)


def _verify_single_trigger_4_gates(trigger: str, ws: Path, tp: Path, mods: Dict[str, Any]) -> None:
    """Verifica i 4 gate Generation su un singolo trigger rappresentativo."""
    pv = f"{trigger.title()}!"
    b_res = mods["boot"].NKSessionBootstrap(workspace_root=ws, conversation_id="conv-gen-trig", prompt=pv).run_bootstrap(fast_stat=False)
    assert (b_res["onboarding_bypass"], b_res["checks"]["meta_prompt_gate"]["mode"], mods["router"].VibeSprintRouter(workspace_root=ws).evaluate_meta_prompt_gate(pv)["fsm_state"]) == ("ONBOARDING_BYPASS_VERIFIED", "BYPASSED", "BYPASSED")
    _write_jsonl(tp, [{"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": f"<USER_REQUEST>\n{pv}\n</USER_REQUEST>"}, {"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 15_000, "content": "d"}, {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 16_000, "content": "d"}])
    rc_fg, out_fg, _ = call_script_main_captured(mods["fg"], ["--event", "PreInvocation", "--native-contract"], stdin_text=json.dumps({"conversationId": "conv-fg-gen", "projectRoot": str(ws), "transcriptPath": str(tp)}))
    comp = mods["comp"].NKComplianceChecker(workspace_root=ws).audit_transcript(tp)
    assert (rc_fg, json.loads(out_fg), comp["metrics"]["meta_prompt_gate_executed"], comp["scores"]["procedural_score"]) == (0, {}, False, 100)


def _assert_wave2_runtime_subsystems(ws_rt: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica parita runtime generation su bootstrap, sentry, mapper, hook, memory e handoff."""
    hook_mod = load_nk_script_module("nk_hook_gate")
    monkeypatch.delenv("NK_MODEL_PROFILE", raising=False)
    rc_hu, out_hu, _ = call_script_main_captured(hook_mod, ["session-start", "--event", "SessionStart", "--conversation-id", "conv-hk-u", "--project-root", str(ws_rt)])
    assert (boot_mod.NKSessionBootstrap(workspace_root=ws_rt, conversation_id="conv-unset").model_profile, rc_hu, json.loads(out_hu)["profile"]) == ("generation", 0, "generation")
    monkeypatch.setenv("NK_MODEL_PROFILE", "generation")
    tp_140 = tmp_path / "tp_140.jsonl"
    _write_jsonl(tp_140, [{"step_index": i, "source": "MODEL", "input_tokens": 100_000} for i in range(140)])
    assert boot_mod.NKSessionBootstrap(workspace_root=ws_rt, conversation_id="conv-140", transcript_path=tp_140).run_bootstrap(fast_stat=False)["checks"]["context_sentry"]["status"] == "GREEN"
    assert sentry_mod.NKContextSentry(workspace_root=ws_rt).get_traffic_light_status(140, 120_000, actual_context_tokens=140_000)["status"] == "GREEN"
    map_mod, mem_mod = load_nk_script_module("ast_repo_mapper"), load_nk_script_module("memory_3tier_engine")
    rc_hkn, out_hkn, _ = call_script_main_captured(hook_mod, ["session-start", "--event", "SessionStart", "--native-contract", "--conversation-id", "conv-hkn", "--project-root", str(ws_rt)])
    assert (map_mod.CACHE_SCHEMA_VERSION, map_mod.GraduatedSkillAdapter.get_token_budget("NK-Ideator", "generation_mode_c"), rc_hkn, "Generation profile active" in out_hkn) == ("1.0.0-Generation", 512, 0, True)
    assert (mem_mod.MEMORY_SCHEMA_VERSION, mem_mod.sync_tier1_capsule(base_dir=tmp_path / "m3_gen", profile="generation")["profile"], hand_mod.HANDOFF_VERSION, hand_mod.generate_active_context_view(root=ws_rt, profile="generation", dry_run=True)["max_tokens"]) == ("1.0.0-Generation", "generation", "1.0.0-Generation", 1200)


@pytest.mark.integration
def test_wave2_generation_constants_triggers_and_runtime_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Wave 2: SSOT constants/thresholds, 8 trigger Generation sui 4 gate e parita profilo runtime."""
    assert isolated_nk_env.is_dir()
    consts, thr = load_script_by_relpath("nk_common_constants_w2", "scripts/_internal/nk_common/constants.py"), load_script_by_relpath("nk_common_thresholds_w2", "scripts/_internal/nk_common/thresholds.py")
    assert (CONFTEST_VERSION, consts.VERSION, consts.DEFAULT_MILESTONE_ID, consts.GENERATION_ONBOARDING_TRIGGERS, len(consts.ONBOARDING_TRIGGERS)) == ("1.0.0-Generation", "1.0.0-Generation", "NK-GEN-1.0.0", _GEN_TRIGGERS, 16)
    thr.clear_thresholds_cache()
    live_cfg = thr.load_saturation_thresholds(workspace_root=WORKSPACE_ROOT)
    assert live_cfg["profiles"]["generation"]["context_sentry"] == live_cfg["profiles"]["carbon"]["context_sentry"]
    for prof_k, other_k in (("carbon", "generation"), ("generation", "carbon")):
        pf = tmp_path / f"{prof_k}_only.json"
        pf.write_text(json.dumps({"profiles": {prof_k: {"tier1_token_cap": 1200}}}), encoding="utf-8")
        assert thr.load_saturation_thresholds(thresholds_path=pf)["profiles"][other_k]["tier1_token_cap"] == 1200

    mods = {"boot": boot_mod, "router": load_nk_script_module("vibe_sprint_router"), "fg": load_nk_script_module("nk_acs_fastguard"), "comp": load_nk_script_module("nk_compliance_checker")}
    ws_g = _make_clean_hub(tmp_path / "w2_gates")
    (ws_g / ".wal" / "hold.wal").write_text('{"state":"PREPARED"}', encoding="utf-8")
    rtr = mods["router"].VibeSprintRouter(workspace_root=ws_g)
    for trig in _GEN_TRIGGERS:
        assert (rtr.is_gate_exempt(f"{trig.title()}!"), mods["fg"]._is_l0_exempt_fast(f"{trig.title()}!")) == (True, True)
    _verify_single_trigger_4_gates("avvia generation", ws_g, tmp_path / "tp_g1.jsonl", mods)
    _verify_single_trigger_4_gates("start nk generation", ws_g, tmp_path / "tp_g2.jsonl", mods)
    analytical = "Analizza perche avvia generation fallisce nel log"
    assert (rtr.is_gate_exempt(analytical), mods["fg"]._is_l0_exempt_fast(analytical), boot_mod.NKSessionBootstrap(workspace_root=ws_g, conversation_id="conv-neg-gen", prompt=analytical).run_bootstrap(fast_stat=False)["onboarding_bypass"]) == (False, False, "NONE")
    _assert_wave2_runtime_subsystems(_make_clean_hub(tmp_path / "w2_runtime"), tmp_path, monkeypatch)


def _assert_handoff_cursor_and_tracking(tmp_path: Path) -> None:
    """Verifica cursor cache incrementale, resolve_session_tracking_dir e checkpoint isolation."""
    tp = tmp_path / "handoff_cursor.jsonl"
    tp.write_text(json.dumps({"step_index": 1, "source": "USER", "content": "start"}) + "\n", encoding="utf-8")
    assert (hand_mod._inspect_transcript_fast(str(tp))[0], hand_mod._inspect_transcript_fast(str(tp))[0]) == (1, 1)
    with tp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"step_index": 2, "source": "MODEL", "input_tokens": 1200, "content": "mid"}) + "\n" + json.dumps({"step_index": 3, "source": "MODEL", "content": "pending_tail"}))
    s2, _, t2, tok2 = hand_mod._inspect_transcript_fast(str(tp))
    with tp.open("a", encoding="utf-8") as fh:
        fh.write("\n" + json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT"}) + "\n" + json.dumps({"step_index": 4, "source": "MODEL", "input_tokens": 300, "content": "post_ckpt"}))
    assert (s2, tok2, "pending_tail" in t2, hand_mod._inspect_transcript_fast(str(tp))[0]) == (3, 1200, True, 2)
    ws = _make_clean_hub(tmp_path / "iso_hub")
    (ws / "scripts" / "core.py").write_text("VAL = 1\n", encoding="utf-8")
    assert hand_mod.resolve_session_tracking_dir(ws, "conv-alpha_01") == (ws / "nk_tracking" / "sessions" / "conv-alpha_01").resolve()
    assert [hand_mod.resolve_session_tracking_dir(ws, b) for b in (None, "", "default_abc123", "../escape", "nested/sub", "bad$chars!", "x" * 65)] == [None] * 7
    acs_mod = load_script_by_relpath("nk_acs_fastguard_iso", "scripts/nk_acs_fastguard.py")
    cp_a = hand_mod.record_fsm_checkpoint(2, "PASS", "MS-ALPHA", root=ws, state_sha256_override="0" * 64, conversation_id="sess_alpha")
    cp_b = hand_mod.record_fsm_checkpoint(4, "PASS", "MS-BETA", root=ws, conversation_id="sess_beta")
    assert acs_mod._resolve_conv_id(None, {}, str(ws / "repo_a")) != acs_mod._resolve_conv_id(None, {}, str(ws / "repo_b"))
    assert (Path(cp_a["session_anchor_path"]) != Path(cp_b["session_anchor_path"]), hand_mod.resume_from_anchor(root=ws, conversation_id="sess_alpha")["status"], hand_mod.resume_from_anchor(root=ws, conversation_id="sess_beta")["status"]) == (True, "DRIFT_DETECTED", "RESUMED")


def _assert_handoff_templates_and_cli(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verifica Template 11, handoff CLI e _check_git_dirty_fast."""
    tr_mod = load_nk_script_module("nk_transcript_tools")
    p_hub = hand_mod.compile_template_11_prompt(project_root=str(WORKSPACE_ROOT), milestone_id="M-LOTTO-1B", capsule='{"goal": "handoff"}')
    ext_r = tmp_path / "external_proj"
    ext_r.mkdir()
    assert ("v1.0.0-Generation" in p_hub, "oracle-lock freeze" in p_hub, tr_mod.lint_prompt_text(p_hub, mode="auto")[1], tr_mod.lint_prompt_text(hand_mod.compile_template_11_prompt(project_root=str(ext_r), milestone_id="EXT-MS-01"), mode="auto")[1]) == (True, True, 0, 0)
    ws_cli = _make_clean_hub(tmp_path / "ho_cli_ws")
    (ws_cli / "nk_tracking" / "anchor").mkdir(parents=True)
    _write_jsonl(tmp_path / "ho_tr.jsonl", [{"step_index": 0, "type": "USER_INPUT", "content": "Completa WP-7"}])
    for argv in (
        ["--root", str(ws_cli), "--checkpoint-turn", "2", "--gate-status", "PASS", "--milestone-id", "MS-CARBON"],
        ["--root", str(ws_cli), "--resume-from-anchor"],
        ["--project-root", str(ws_cli), "--transcript", str(tmp_path / "ho_tr.jsonl"), "--generate-active-context", "--profile", "argon"],
        ["--project-root", str(ws_cli), "--transcript", str(tmp_path / "ho_tr.jsonl"), "--output-dir", str(tmp_path / "ho_out"), "--compile-state-handoff"],
    ):
        assert call_script_main(hand_mod, argv, monkeypatch) == 0
    ng_repo = tmp_path / "non_git_ws"
    (ng_repo / ".staging").mkdir(parents=True)
    (ng_repo / ".staging" / "dirty.py").write_text("X = 1\n", encoding="utf-8")
    assert (bool(capsys.readouterr().out.strip()), hand_mod._check_git_dirty_fast(ng_repo, "git")) == (True, (True, None))


@pytest.mark.integration
def test_session_handoff_cursor_templates_cli_and_z2_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any, isolated_nk_env: Path) -> None:
    """Verifica cursor/tracking/CLI handoff e protezione Template 12 con turn=0 su Z2/stop-evidence."""
    assert isolated_nk_env.is_dir()
    _assert_handoff_cursor_and_tracking(tmp_path)
    _assert_handoff_templates_and_cli(tmp_path, monkeypatch, capsys)
    fg_mod = load_nk_script_module("nk_acs_fastguard")
    load_nk_script_module("nk_hook_gate")
    import _internal.nk_acs_fastguard.z2_and_l0 as z2_mod
    import _internal.nk_hook_gate.stop_evidence as se_mod

    ws = tmp_path / "turn_ws"
    for d in ("nk_tracking/anchor", "nk_tracking/sessions/conv-active", "scripts"):
        (ws / d).mkdir(parents=True)
    (ws / "scripts" / "nk_session_handoff.py").write_text("# placeholder\n", encoding="utf-8")
    tp_file = tmp_path / "transcript.jsonl"
    tp_file.write_text('{"usage": {"input_tokens": 160000}}\n', encoding="utf-8")
    (ws / "nk_tracking" / "anchor" / "session_anchor.jsonl").write_text(json.dumps({"milestone_id": "M-OLD", "turn": 1, "conversation_id": "other-conv"}) + "\n", encoding="utf-8")
    (ws / "nk_tracking" / "sessions" / "conv-active" / "session_anchor.jsonl").write_text(json.dumps({"milestone_id": "M-ACT", "turn": 2, "conversation_id": "conv-active"}) + "\n", encoding="utf-8")
    assert (z2_mod._read_anchor_meta([str(ws)], {}, conv_id="conv-clean", default_turn=0)[1], se_mod._stop_read_anchor_meta([ws], {}, conv_id="conv-clean", default_turn=0)[1], z2_mod._read_anchor_meta([str(ws)], {}, conv_id="conv-active", default_turn=0)) == (0, 0, ("M-ACT", 2))
    spawned: List[List[str]] = []
    with monkeypatch.context() as mp:
        mp.setattr(subprocess, "Popen", lambda cmd, **_kw: spawned.append(list(cmd)) or object())
        for mod in (z2_mod, fg_mod):
            mp.setattr(mod, "_is_batch_mutex_busy", lambda _r: False, raising=False)
            mp.setattr(mod, "_has_active_wal", lambda _r: False, raising=False)
            mp.setattr(mod, "_SCRIPT_DIR", str(ws / "scripts"), raising=False)
        z2_mod._maybe_spawn_z2([str(ws)], str(tp_file), "conv-clean", {}, {"compaction_epoch": 1, "z2_last_spawn_epoch": -1, "z2_last_spawn_ts": 0.0})
        hooks_tmp = ws.parent / "hooks_tmp_l1b"
        hooks_tmp.mkdir(exist_ok=True)
        mp.setattr(se_mod, "_get_hooks_temp_dir", lambda: hooks_tmp)
        mp.setattr(se_mod, "_stop_read_tokens_and_epoch", lambda _tp, _c: (160_000, 10, 1))
        mp.setattr(se_mod, "_stop_is_batch_mutex_or_wal_busy", lambda _r: False)
        mp.setattr(se_mod, "_SCRIPT_DIR", ws / "scripts")
        se_mod._maybe_spawn_stop_idle_checkpoint("conv-clean", ws, tp_file, {})
    assert len(spawned) == 2 and all(cmd[cmd.index("--turn") + 1] == "0" for cmd in spawned)
    ckpt_ws = tmp_path / "ckpt_ws"
    (ckpt_ws / "nk_tracking" / "handoff").mkdir(parents=True)
    rc_live, out_live, _ = call_script_main_captured(hand_mod, ["--auto-checkpoint", "--project-root", str(ckpt_ws), "--transcript", str(tp_file), "--conversation-id", "conv-clean", "--turn", "0"])
    assert (json.loads(call_script_main_captured(hand_mod, ["--auto-checkpoint", "--project-root", str(ckpt_ws), "--conversation-id", "conv-clean", "--turn", "0", "--dry-run"])[1])["handoff_template"], json.loads(call_script_main_captured(hand_mod, ["--auto-checkpoint", "--project-root", str(ckpt_ws), "--conversation-id", "conv-active", "--turn", "2", "--dry-run"])[1])["handoff_template"], rc_live, json.loads(out_live)["anchor_recorded"], hand_mod.resume_from_anchor(root=ckpt_ws, conversation_id="conv-clean")["gate_status"]) == ("Template 12", "Template 11", 0, True, "MISSING")


@pytest.mark.integration
def test_api_cache_wal_retry_eviction_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Verifica cache SQLite WAL persistente, retry, eviction, defaults e CLI deterministic_api_cache."""
    assert (isolated_nk_env.is_dir(), DeterministicApiCache.compute_hash("https://x", params={"b": 2, "a": 1}) == DeterministicApiCache.compute_hash("https://x", params={"a": 1, "b": 2})) == (True, True)
    with DeterministicApiCache(db_path=tmp_path / "wal_persistent.db", ttl_seconds=0.005) as cache:
        conn_init = cache._conn
        cache.set("https://example.org/v1", 200, '{"ok": true}', method="POST", params={"q": "nk"}, headers={"X-K": "1"})
        cache.set("https://example.org/v1", 201, '{"ok": 2}', method="POST", params={"q": "nk"}, headers={"X-K": "2"})
        assert (cache.health_check(), conn_init is not None, cache.get("https://example.org/v1", method="POST", params={"q": "nk"}), cache._conn is conn_init, cache.get("https://example.org/v1", method="POST", params={"q": "nk"}, force_refresh=True)) == (True, True, (201, '{"ok": 2}', {"X-K": "2"}), True, None)
        attempts = [0]

        def _flaky_op(conn: Any) -> int:
            attempts[0] += 1
            if attempts[0] == 1:
                raise cache_mod.sqlite3.OperationalError("transient busy")
            return int(conn.execute("SELECT COUNT(*) FROM api_cache;").fetchone()[0])

        assert (cache._run_with_sqlite_retry(_flaky_op), attempts[0]) == (1, 2)
        time.sleep(0.009)
        assert (cache.get("https://example.org/v1", method="POST", params={"q": "nk"}), cache.get_stats()["entries"]) == (None, 0)
        cache.set("https://example.org/v2", 200, '{"ephemeral": 2}')
        assert cache.clear() == 1
    with DeterministicApiCache(ttl_seconds=60.0) as default_cache:
        assert (cache._conn, default_cache.get("https://miss.example.org"), default_cache.get_stats()["wal_healthy"]) == (None, None, True)
    for cli_flag, exp_tok in (("--health", "WAL Health"), ("--stats", "wal_healthy"), ("--clear", "Voci rimosse")):
        rc_c, out_c, _ = call_script_main_captured(cache_mod, [cli_flag])
        assert (rc_c, exp_tok in out_c) == (0, True)
    monkeypatch.delenv("NK_FORCE_NETWORK_REFRESH", raising=False)
    try:
        rc_rf, out_rf, _ = call_script_main_captured(cache_mod, ["--force-refresh"])
        assert (call_script_main_captured(cache_mod, [])[0], rc_rf, "Refresh forzato" in out_rf, os.environ.get("NK_FORCE_NETWORK_REFRESH")) == (0, 0, True, "1")
    finally:
        os.environ.pop("NK_FORCE_NETWORK_REFRESH", None)
