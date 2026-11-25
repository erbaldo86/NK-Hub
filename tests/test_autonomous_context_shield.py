# -*- coding: utf-8 -*-
"""
Suite di test end-to-end Zero-Mock per Autonomous Context Shield 1.0.0-Generation.
Modulo: tests/test_autonomous_context_shield.py.
Copre R1..R12 e Wave 3 su nk_acs_fastguard.py, nk_session_handoff.py, win32_2pc_engine.py e bootstrap.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

try:
    from conftest import (
        STAGING_SCRIPTS_DIR,
        WORKSPACE_ROOT,
        load_nk_script_module,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        STAGING_SCRIPTS_DIR,
        WORKSPACE_ROOT,
        load_nk_script_module,
        load_script_by_relpath,
    )


def _resolve_script(script_name: str) -> Path:
    """Restituisce il percorso dello script dando priorita a .staging/scripts/."""
    staged = STAGING_SCRIPTS_DIR / script_name
    if staged.is_file():
        return staged
    return WORKSPACE_ROOT / "scripts" / script_name


def _write_jsonl(path: Path, records: List[Dict[str, Any]], eol: str = "\n") -> None:
    """Scrive una lista di record dict come JSONL UTF-8 con terminatore indicato."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = eol.join(json.dumps(r, ensure_ascii=True) for r in records) + eol
    path.write_bytes(raw.encode("utf-8"))


def _isolate_tmp_dirs(base_dir: Path, mp: pytest.MonkeyPatch) -> Path:
    """Isola NK_HOOKS_TEMP_DIR, TEMP, TMP e tempfile.tempdir tramite MonkeyPatch."""
    hooks_tmp = base_dir / "hooks_tmp"
    sys_tmp = base_dir / "sys_tmp"
    hooks_tmp.mkdir(parents=True, exist_ok=True)
    sys_tmp.mkdir(parents=True, exist_ok=True)
    mp.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))
    mp.setenv("TEMP", str(sys_tmp))
    mp.setenv("TMP", str(sys_tmp))
    mp.setattr(tempfile, "tempdir", str(sys_tmp))
    return hooks_tmp


def _run_fastguard_inproc(
    event: str,
    payload: Dict[str, Any],
    mp: pytest.MonkeyPatch,
    extra_args: Optional[List[str]] = None,
    native_contract: bool = True,
) -> Tuple[int, Dict[str, Any], str]:
    """Esegue nk_acs_fastguard.main() in-process sotto isolamento MonkeyPatch."""
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    cli_args = ["--event", event] + (["--native-contract"] if native_contract else []) + (extra_args or [])
    buf_out = io.StringIO()
    with mp.context() as local_mp:
        local_mp.setattr(sys, "stdin", io.StringIO(json.dumps(payload, ensure_ascii=True)))
        local_mp.setattr(sys, "stdout", buf_out)
        try:
            rc = int(fastguard_mod.main(cli_args) or 0)
        except SystemExit as exc:
            rc = int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    stdout_text = buf_out.getvalue()
    out_line = stdout_text.strip().splitlines()[-1] if stdout_text.strip() else "{}"
    return rc, json.loads(out_line), stdout_text


def _run_fastguard_subproc(
    event: str,
    payload: Dict[str, Any],
    env: Dict[str, str],
    extra_args: Optional[List[str]] = None,
    native_contract: bool = True,
) -> Tuple[int, Dict[str, Any], str]:
    """Esegue nk_acs_fastguard.py in subprocess -S -B -u isolato."""
    cli_args = ["--event", event] + (["--native-contract"] if native_contract else []) + (extra_args or [])
    cmd = [sys.executable, "-S", "-B", "-u", str(_resolve_script("nk_acs_fastguard.py")), *cli_args]
    proc = subprocess.run(
        cmd, input=json.dumps(payload, ensure_ascii=True), text=True, encoding="utf-8",
        errors="replace", capture_output=True, env=env, timeout=15, shell=False,
    )
    out_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
    return proc.returncode, json.loads(out_line), proc.stdout


def _run_handoff_inproc(
    handoff_mod: Any, cli_args: List[str], mp: pytest.MonkeyPatch, in_thread: bool = False
) -> Tuple[int, str]:
    """Esegue nk_session_handoff.main(cli_args) in-process catturando stdout."""
    buf_out = io.StringIO()
    result_box: Dict[str, int] = {"rc": 0}

    def _invoke() -> None:
        try:
            result_box["rc"] = int(handoff_mod.main(cli_args) or 0)
        except SystemExit as exc:
            result_box["rc"] = int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 1)

    with mp.context() as local_mp:
        local_mp.setattr(sys, "stdout", buf_out)
        local_mp.setattr(sys, "stderr", io.StringIO())
        if in_thread:
            worker = threading.Thread(target=_invoke)
            worker.start()
            worker.join(timeout=15.0)
        else:
            _invoke()
    return result_box["rc"], buf_out.getvalue()


def _precreate_wal_hold(proj_dir: Path) -> None:
    """Pre-crea un .wal attivo locale per prevenire subprocess.Popen duplicati."""
    wal_dir = proj_dir / ".wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    (wal_dir / "hold.wal").write_text('{"state":"PREPARED"}', encoding="utf-8")


def _native_sys_msg(out: Dict[str, Any]) -> str:
    """Estrae systemMessage dal contratto nativo injectSteps."""
    steps = out.get("injectSteps")
    if not isinstance(steps, list) or not steps:
        return ""
    return str(steps[0].get("systemMessage", {}).get("systemMessage", ""))


def _native_post_msg(out: Dict[str, Any]) -> Tuple[str, str]:
    """Estrae (systemMessage, user_markdown) dal contratto nativo PostInvocation."""
    steps = out.get("injectSteps")
    assert isinstance(steps, list) and len(steps) == 1
    sm_obj = steps[0].get("systemMessage", {})
    return str(sm_obj.get("systemMessage", "MISSING")), str(sm_obj.get("metadata", {}).get("user_markdown", ""))


def _wait_for_paths(paths: List[Path], timeout_s: float = 8.0) -> bool:
    """Attende che tutti i file spawnati in background esistano con dimensione > 0."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if all(p.is_file() and p.stat().st_size > 0 for p in paths):
            return True
        time.sleep(0.002)
    return all(p.is_file() and p.stat().st_size > 0 for p in paths)


def _repo_hash16(root: Path) -> str:
    """Calcola l'hash16 canonico condiviso da NK_RepoBatchLock e NK_HandoffWorker."""
    norm = os.path.realpath(str(root)).lower().replace("/", "\\").rstrip("\\")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _acquire_kernel_mutex(mutex_name: str) -> Tuple[Any, int]:
    """Acquisisce un mutex kernel Win32 reale tramite ctypes.WinDLL."""
    if sys.platform != "win32":
        return None, 0
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k32.WaitForSingleObject.restype = ctypes.c_uint32
    k32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    k32.ReleaseMutex.restype = ctypes.c_int
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = ctypes.c_int
    ctypes.set_last_error(0)
    handle = k32.CreateMutexW(None, False, mutex_name)
    if not handle and mutex_name.startswith("Global\\"):
        ctypes.set_last_error(0)
        handle = k32.CreateMutexW(None, False, "Local\\" + mutex_name.split("\\", 1)[1])
    assert handle
    assert k32.WaitForSingleObject(ctypes.c_void_p(handle), 2000) in (0, 0x80)
    return k32, int(handle)


def _release_kernel_mutex(k32: Any, handle: int) -> None:
    """Rilascia e chiude l'handle mutex Win32 acquisito."""
    if k32 is None or not handle:
        return
    try:
        k32.ReleaseMutex(ctypes.c_void_p(handle))
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))


def _assert_acs_z0_z1_and_z2_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, handoff_mod: Any
) -> None:
    proj_z1 = tmp_path / "proj_z1"
    proj_z1.mkdir(parents=True)
    tp_z0 = tmp_path / "tp_z0.jsonl"
    _write_jsonl(tp_z0, [{"step_index": 1, "source": "MODEL", "input_tokens": 155_000}])
    rc, out_z0, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z0-silent", "projectRoot": str(proj_z1), "transcriptPath": str(tp_z0)}, monkeypatch)
    assert (rc, out_z0) == (0, {})

    tp_z1 = tmp_path / "tp_z1.jsonl"
    _write_jsonl(tp_z1, [{"step_index": 1, "source": "MODEL", "input_tokens": 130_000, "cache_read_tokens": 30_000}])
    pl_z1 = {"conversationId": "conv-z1-tok", "projectRoot": str(proj_z1), "transcriptPath": str(tp_z1)}
    rc, out_post_z1, raw_post_z1 = _run_fastguard_inproc("PostInvocation", pl_z1, monkeypatch)
    assert (rc, out_post_z1) == (0, {})
    assert "/compact" not in raw_post_z1
    rc, out_pre_z1, raw_pre_z1 = _run_fastguard_inproc("PreInvocation", pl_z1, monkeypatch)
    assert rc == 0
    assert "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_pre_z1)
    assert "/compact" not in raw_pre_z1
    rc, out_pre_z1_dup, _ = _run_fastguard_inproc("PreInvocation", pl_z1, monkeypatch)
    assert (rc, out_pre_z1_dup) == (0, {})

    tp_z1_steps = tmp_path / "tp_z1_steps.jsonl"
    _write_jsonl(tp_z1_steps, [{"step_index": i, "source": "MODEL", "content": "ok"} for i in range(120)])
    rc, out_z1_steps, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z1-steps", "projectRoot": str(proj_z1), "transcriptPath": str(tp_z1_steps)}, monkeypatch)
    assert rc == 0
    assert "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_z1_steps)

    proj_z2_s = tmp_path / "proj_z2_steps"
    _precreate_wal_hold(proj_z2_s)
    tp_z2_s = tmp_path / "tp_z2_steps.jsonl"
    _write_jsonl(tp_z2_s, [{"step_index": i, "source": "MODEL", "content": "s"} for i in range(150)])
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z2-steps", "projectRoot": str(proj_z2_s), "transcriptPath": str(tp_z2_s)}, monkeypatch)[0] == 0
    _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_z2_s), "--transcript", str(tp_z2_s), "--conversation-id", "conv-z2-steps", "--turn", "1"], monkeypatch)
    assert (proj_z2_s / "nk_tracking" / "handoff" / "session_handoff_latest.json").is_file()


def _assert_acs_z3_pre_post_native_and_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj_z3 = tmp_path / "proj_z3"
    _precreate_wal_hold(proj_z3)
    tp_z3 = tmp_path / "tp_z3.jsonl"
    _write_jsonl(tp_z3, [{"step_index": 1, "source": "MODEL", "input_tokens": 205_000}])
    pl_z3 = {"conversationId": "conv-z3-tok", "projectRoot": str(proj_z3), "transcriptPath": str(tp_z3)}
    rc, out_pre, raw_pre = _run_fastguard_inproc("PreInvocation", pl_z3, monkeypatch)
    assert rc == 0
    assert "[ACS-Z3 CRITICO]" in _native_sys_msg(out_pre)
    assert "/compact" not in raw_pre
    assert _run_fastguard_inproc("PreInvocation", pl_z3, monkeypatch)[1] == {}

    rc, out_post, raw_post = _run_fastguard_inproc("PostInvocation", pl_z3, monkeypatch)
    assert rc == 0
    assert _native_post_msg(out_post)[0] == ""
    assert "[ACS-Z3]" in _native_post_msg(out_post)[1]
    assert "/compact" not in raw_post
    assert _run_fastguard_inproc("PostInvocation", pl_z3, monkeypatch)[1] == {}

    pl_leg = {"conversationId": "conv-z3-legacy", "projectRoot": str(proj_z3), "transcriptPath": str(tp_z3)}
    _, out_leg_pre, _ = _run_fastguard_inproc("PreInvocation", pl_leg, monkeypatch, native_contract=False)
    assert "injectSteps" not in out_leg_pre
    assert "[ACS-Z3 CRITICO]" in out_leg_pre.get("systemMessage", "")
    _, out_leg_post, _ = _run_fastguard_inproc("PostInvocation", pl_leg, monkeypatch, native_contract=False)
    assert "injectSteps" not in out_leg_post
    assert "[ACS-Z3]" in out_leg_post.get("metadata", {}).get("user_markdown", "")


def _assert_acs_velocity_jump_and_z3_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj_vel = tmp_path / "proj_vel"
    _precreate_wal_hold(proj_vel)
    tp_vel = tmp_path / "tp_vel.jsonl"
    _write_jsonl(tp_vel, [{"step_index": 1, "source": "MODEL", "input_tokens": 110_000}])
    pl_vel = {"conversationId": "conv-vel-185", "projectRoot": str(proj_vel), "transcriptPath": str(tp_vel)}
    assert _run_fastguard_inproc("PreInvocation", pl_vel, monkeypatch)[1] == {}
    with open(tp_vel, "ab") as f:
        f.write((json.dumps({"step_index": 2, "source": "MODEL", "input_tokens": 185_000}) + "\n").encode("utf-8"))
    assert "[ACS-Z3 CRITICO]" in _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_vel, monkeypatch)[1])

    proj_z3_s = tmp_path / "proj_z3_steps"
    _precreate_wal_hold(proj_z3_s)
    tp_z3_s = tmp_path / "tp_z3_steps.jsonl"
    _write_jsonl(tp_z3_s, [{"step_index": i, "source": "MODEL", "content": "x"} for i in range(180)])
    _, out_z3_s, _ = _run_fastguard_inproc("PostInvocation", {"conversationId": "conv-z3-steps", "projectRoot": str(proj_z3_s), "transcriptPath": str(tp_z3_s)}, monkeypatch)
    assert "[ACS-Z3]" in _native_post_msg(out_z3_s)[1]


@pytest.mark.integration
def test_acs_z1_z2_z3_zones_velocity_and_legacy_contract(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica Z0, Z1 one-shot, Z2 150 step, Z3 Pre/Post (nativo/legacy), 180 step e velocity jump."""
    isolated_nk_ws_factory("z1_z3_vel", apply_inproc=True)
    handoff_mod = load_nk_script_module("nk_session_handoff")
    _assert_acs_z0_z1_and_z2_steps(tmp_path, monkeypatch, handoff_mod)
    _assert_acs_z3_pre_post_native_and_legacy(tmp_path, monkeypatch)
    _assert_acs_velocity_jump_and_z3_steps(tmp_path, monkeypatch)


@pytest.mark.integration
def test_acs_z2_live_spawn_cooldown_mutex_and_wal_guards(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica Z2 spawn live isolato, cooldown 60s, guard mutex Win32 e blocco .wal."""
    env, hooks_tmp, _ = isolated_nk_ws_factory("z2_live", apply_inproc=True)
    proj_z2 = tmp_path / "proj_z2_live"
    proj_z2.mkdir(parents=True)
    tp_z2 = tmp_path / "tp_z2.jsonl"
    _write_jsonl(tp_z2, [{"step_index": 1, "source": "MODEL", "input_tokens": 150_000, "cache_read_tokens": 35_000}])
    pl_z2 = {"conversationId": "conv-z2-live", "projectRoot": str(proj_z2), "transcriptPath": str(tp_z2)}
    rc, out_z2, _ = _run_fastguard_subproc("PreInvocation", pl_z2, env)
    assert rc == 0 and out_z2 == {}

    expected_files = [
        proj_z2 / "nk_tracking" / "handoff" / "session_handoff_latest.json",
        proj_z2 / "nk_tracking" / "handoff" / "next_session_prompt.md",
        proj_z2 / "nk_tracking" / "active_context.md",
        proj_z2 / "nk_tracking" / "anchor" / "session_anchor.jsonl",
    ]
    assert _wait_for_paths(expected_files, timeout_s=8.0)
    handoff_meta = json.loads(expected_files[0].read_text(encoding="utf-8"))
    assert Path(handoff_meta["project_root"]).resolve() == proj_z2.resolve() and handoff_meta.get("conversation_id") == "conv-z2-live"

    expected_files[0].unlink()
    with open(tp_z2, "ab") as f:
        f.write((json.dumps({"step_index": 2, "source": "MODEL", "input_tokens": 190_000}) + "\n").encode("utf-8"))
    rc, out_cool, _ = _run_fastguard_inproc("PostInvocation", pl_z2, monkeypatch)
    assert rc == 0 and out_cool == {} and not expected_files[0].exists()

    proj_mtx = tmp_path / "proj_z2_mutex"
    proj_mtx.mkdir(parents=True)
    tp_mtx = tmp_path / "tp_mtx.jsonl"
    _write_jsonl(tp_mtx, [{"step_index": 1, "source": "MODEL", "input_tokens": 190_000}])
    expected_local_mtx = f"Local\\NK_RepoBatchLock_{_repo_hash16(proj_mtx)}"
    if sys.platform == "win32":
        k32, mtx_handle = _acquire_kernel_mutex(expected_local_mtx)
        try:
            rc, out_mtx, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z2-mtx", "projectRoot": str(proj_mtx), "transcriptPath": str(tp_mtx)}, monkeypatch)
            assert rc == 0 and out_mtx == {}
        finally:
            _release_kernel_mutex(k32, mtx_handle)
    else:
        fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
        fake_ctypes = SimpleNamespace(set_last_error=lambda _e: None, get_last_error=lambda: 0)
        fake_k32 = SimpleNamespace(
            OpenMutexW=lambda _acc, _inh, name: 8888 if name == expected_local_mtx else 0,
            CloseHandle=lambda _h: 1,
        )
        with monkeypatch.context() as mp_mtx:
            mp_mtx.setattr(fastguard_mod, "_get_k32", lambda: (fake_ctypes, fake_k32), raising=False)
            rc, out_mtx, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z2-mtx", "projectRoot": str(proj_mtx), "transcriptPath": str(tp_mtx)}, mp_mtx)
            assert rc == 0 and out_mtx == {}
    assert json.loads((hooks_tmp / "nk_hooks" / "fastguard_conv-z2-mtx.json").read_text(encoding="utf-8"))["z2_last_spawn_ts"] == 0.0

    proj_wal = tmp_path / "proj_z2_wal"
    _precreate_wal_hold(proj_wal)
    tp_wal = tmp_path / "tp_wal.jsonl"
    _write_jsonl(tp_wal, [{"step_index": 1, "source": "MODEL", "input_tokens": 195_000}])
    rc, out_wal, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z2-wal", "projectRoot": str(proj_wal), "transcriptPath": str(tp_wal)}, monkeypatch)
    assert rc == 0 and out_wal == {}
    assert json.loads((hooks_tmp / "nk_hooks" / "fastguard_conv-z2-wal.json").read_text(encoding="utf-8"))["z2_last_spawn_ts"] == 0.0


def _assert_tv03_subagent_and_spoof(
    tmp_path: Path, hooks_tmp: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tp_sub = tmp_path / "tp_subagent.jsonl"
    _write_jsonl(tp_sub, [
        {"step_index": 0, "source": "SYSTEM_SDK", "type": "SESSION_START", "content": "start"},
        {"step_index": 1, "source": "SYSTEM", "content": "<SYSTEM_MESSAGE> sender=parent </SYSTEM_MESSAGE>"},
        {"step_index": 2, "source": "MODEL", "input_tokens": 210_000},
    ])
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-sub-a44", "projectRoot": str(proj), "transcriptPath": str(tp_sub)}, monkeypatch)[1] == {}
    assert not (hooks_tmp / "nk_hooks" / "fastguard_conv-sub-a44.json").exists()

    tp_spoof = tmp_path / "tp_spoof_sub.jsonl"
    _write_jsonl(tp_spoof, [
        {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "<SYSTEM_MESSAGE> sender=fake </SYSTEM_MESSAGE>"},
        {"step_index": 1, "source": "MODEL", "input_tokens": 205_000},
    ])
    out_spoof = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-spoof-sub", "projectRoot": str(proj), "transcriptPath": str(tp_spoof)}, monkeypatch)[1]
    assert "[ACS-Z3 CRITICO]" in _native_sys_msg(out_spoof)

    tp_sub5 = tmp_path / "tp_sub5.jsonl"
    _write_jsonl(tp_sub5, [
        {"step_index": 0, "source": "SYSTEM_SDK", "content": "s0"},
        {"step_index": 1, "source": "SYSTEM_SDK", "content": "s1"},
        {"step_index": 1, "source": "SYSTEM_SDK", "content": "s2"},
        {"step_index": 2, "source": "SYSTEM_SDK", "content": "s3"},
        {"step_index": 2, "source": "SYSTEM", "content": "<subagent_reminder>foglia</subagent_reminder>"},
    ])
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-sub5", "projectRoot": str(proj), "transcriptPath": str(tp_sub5)}, monkeypatch)[1] == {}
    assert not (hooks_tmp / "nk_hooks" / "fastguard_conv-sub5.json").exists()


def _assert_tv01_crlf_550kb_partial_and_shrink(
    tmp_path: Path, hooks_tmp: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tp_big = tmp_path / "tp_big_crlf.jsonl"
    filler = [{"step_index": i, "source": "MODEL", "content": "B" * 4000} for i in range(115)]
    big_row = {"step_index": 116, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 125_000, "cache_read_tokens": 35_000, "content": "L" * 140_800}
    _write_jsonl(tp_big, [*filler, big_row], eol="\r\n")
    assert tp_big.stat().st_size > 550 * 1024

    pl_big = {"conversationId": "conv-tv01", "projectRoot": str(proj), "transcriptPath": str(tp_big)}
    rc, out_big, _ = _run_fastguard_inproc("PreInvocation", pl_big, monkeypatch)
    assert rc == 0
    assert "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_big)
    st_file = hooks_tmp / "nk_hooks" / "fastguard_conv-tv01.json"
    st_big = json.loads(st_file.read_text(encoding="utf-8"))
    assert (st_big["byte_offset"], st_big["last_actual_tokens"]) == (tp_big.stat().st_size, 160_000)

    with open(tp_big, "ab") as f:
        f.write(b'{"step_index":117,"source":"MODEL","input_tokens":205000')
    rc, out_part, _ = _run_fastguard_inproc("PreInvocation", pl_big, monkeypatch)
    assert (rc, out_part) == (0, {})
    assert json.loads(st_file.read_text(encoding="utf-8"))["byte_offset"] == st_big["byte_offset"]

    with open(tp_big, "ab") as f:
        f.write(b"}\r\n")
    assert "[ACS-Z3 CRITICO]" in _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_big, monkeypatch)[1])

    _write_jsonl(tp_big, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "reset"}, {"step_index": 2, "source": "MODEL", "input_tokens": 10_000, "content": "ok"}])
    assert _run_fastguard_inproc("PreInvocation", pl_big, monkeypatch)[1] == {}
    st_shrink = json.loads(st_file.read_text(encoding="utf-8"))
    assert (st_shrink["byte_offset"], st_shrink["steps"], st_shrink["last_actual_tokens"]) == (tp_big.stat().st_size, 2, 10_000)


def _assert_tv02_bool_tv08_rehydrate_and_traversal(
    tmp_path: Path, hooks_tmp: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tp_bool = tmp_path / "tp_bool.jsonl"
    _write_jsonl(tp_bool, [
        {"step_index": 1, "source": "MODEL", "input_tokens": True, "cache_read_tokens": False},
        {"step_index": 2, "source": "MODEL", "actual_context_tokens": True},
        {"step_index": 3, "source": "MODEL", "usage": {"input_tokens": True, "cache_read_tokens": 190_000}},
    ])
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-bool", "projectRoot": str(proj), "transcriptPath": str(tp_bool)}, monkeypatch)[1] == {}
    assert json.loads((hooks_tmp / "nk_hooks" / "fastguard_conv-bool.json").read_text(encoding="utf-8"))["last_actual_tokens"] == 0

    tp_re = tmp_path / "tp_rehydrate.jsonl"
    _write_jsonl(tp_re, [
        {"step_index": 1, "source": "USER", "type": "CHECKPOINT", "compacted": True, "content": "<CONTEXT_SUMMARY>"},
        {"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "compacted": True, "content": "# Resuming"},
        {"step_index": 5, "source": "SYSTEM", "content": "[Message] sender=subagent <CONTEXT_SUMMARY>"},
        {"step_index": 6, "source": "MODEL", "input_tokens": 160_000},
    ])
    pl_re = {"conversationId": "conv-tv08", "projectRoot": str(proj), "transcriptPath": str(tp_re)}
    msg1 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_re, monkeypatch)[1])
    assert "[ACS-Z1 SOFT-FOLDING]" in msg1
    assert "[RULE-REHYDRATE]" not in msg1

    with open(tp_re, "ab") as f:
        f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint"}) + "\n").encode("utf-8"))
    msg2 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_re, monkeypatch)[1])
    assert "[RULE-REHYDRATE]" in msg2
    assert "nk_tracking/active_context.md" in msg2
    assert _run_fastguard_inproc("PreInvocation", pl_re, monkeypatch)[1] == {}

    proj_trav = tmp_path / "proj_trav"
    proj_trav.mkdir()
    tp_trav = tmp_path / "tp_trav.jsonl"
    _write_jsonl(tp_trav, [{"step_index": 1, "source": "MODEL", "input_tokens": 1000}])
    expected_default_id = f"default_{hashlib.sha256(os.path.realpath(str(proj_trav)).lower().encode('utf-8')).hexdigest()[:10]}"
    for bad_conv in ("../escape", "..\\..\\evil", "a/b", ".", ".."):
        rc_t, out_trav, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": bad_conv, "projectRoot": str(proj_trav), "transcriptPath": str(tp_trav)}, monkeypatch)
        assert (rc_t, out_trav) == (0, {})
    assert (hooks_tmp / "nk_hooks" / f"fastguard_{expected_default_id}.json").is_file()


@pytest.mark.integration
def test_acs_tv01_tv02_tv03_tv08_subagent_spoof_and_traversal(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica TV-01 (>550KB CRLF), TV-02 bool, TV-03 subagent/spoof, TV-04/08 [RULE-REHYDRATE] e path traversal."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("tv_all", apply_inproc=True)
    proj = tmp_path / "proj_tv_all"
    _precreate_wal_hold(proj)
    _assert_tv03_subagent_and_spoof(tmp_path, hooks_tmp, proj, monkeypatch)
    _assert_tv01_crlf_550kb_partial_and_shrink(tmp_path, hooks_tmp, proj, monkeypatch)
    _assert_tv02_bool_tv08_rehydrate_and_traversal(tmp_path, hooks_tmp, proj, monkeypatch)


def _make_global_deny_k32_class(real_k32: Any, seen_names: List[str]) -> type[Any]:
    class _GlobalDenyKernel32:
        def __getattr__(self, item: str) -> Any:
            return getattr(real_k32, item)

        def CreateMutexW(self, sec: Any, initial: Any, name: str) -> Any:
            seen_names.append(name)
            if name.startswith("Global\\"):
                ctypes.set_last_error(5)
                return None
            return real_k32.CreateMutexW(sec, initial, name)

    return _GlobalDenyKernel32


def _assert_handoff_dry_run_and_fsm_checkpoints(
    tmp_path: Path, tp: Path, monkeypatch: pytest.MonkeyPatch, handoff_mod: Any
) -> None:
    proj_dry = tmp_path / "proj_dry"
    proj_dry.mkdir()
    rc_auto, out_auto = _run_handoff_inproc(
        handoff_mod, ["--auto-checkpoint", "--dry-run", "--project-root", str(proj_dry), "--transcript", str(tp), "--conversation-id", "conv-dry", "--milestone-id", "MS-DRY", "--turn", "2"], monkeypatch
    )
    dry_json = json.loads(out_auto)
    assert (rc_auto, dry_json["status"], dry_json["handoff_template"]) == (0, "DRY_RUN", "Template 11")
    assert not (proj_dry / "nk_tracking").exists()

    rc_cp, out_cp = _run_handoff_inproc(handoff_mod, ["--project-root", str(proj_dry), "--checkpoint-turn", "2", "--dry-run"], monkeypatch)
    assert (rc_cp, json.loads(out_cp)["status"]) == (0, "DRY_RUN")
    assert not (proj_dry / "nk_tracking").exists()

    proj_eff = tmp_path / "proj_eff_l1022"
    (proj_eff / ".staging" / "scripts").mkdir(parents=True)
    (proj_eff / ".staging" / "scripts" / "demo.py").write_text("x = 1\n", encoding="utf-8")
    rc_eff, _ = _run_handoff_inproc(
        handoff_mod, ["--project-root", str(proj_eff), "--transcript", str(tp), "--checkpoint-turn", "2", "--persist-brief-id", "IB-L1022", "--prompt-text", "Test L1022.", "--generate-prompt"], monkeypatch
    )
    assert rc_eff == 0
    eff_latest = json.loads((proj_eff / "nk_tracking" / "handoff" / "session_handoff_latest.json").read_text(encoding="utf-8"))
    assert (Path(eff_latest["project_root"]).resolve(), eff_latest["dirty_files"]) == (proj_eff.resolve(), True)
    assert (proj_eff / "nk_tracking" / "reports_and_briefs" / "IB-L1022.md").is_file()

    cp_rec = handoff_mod.record_fsm_checkpoint(turn=2, gate_status="PASS", milestone_id="MS-CP", root=proj_eff, conversation_id="conv-fsm-2")
    assert (cp_rec["passed"], len(cp_rec["staging_state_sha256"])) == (True, 64)
    for bad_turn in (True, False, 0, 6):
        with pytest.raises(ValueError):
            handoff_mod.record_fsm_checkpoint(turn=bad_turn, gate_status="PASS", root=proj_eff)
    with pytest.raises(ValueError):
        handoff_mod.select_auto_checkpoint_template(False, True)
    assert handoff_mod.select_auto_checkpoint_template(False, 0) == "Template 12"


def _assert_handoff_t11_t12_lint_and_mutex_busy(
    tmp_path: Path, tp: Path, monkeypatch: pytest.MonkeyPatch, handoff_mod: Any, win32_mod: Any, tt_mod: Any
) -> Path:
    proj_clean = tmp_path / "proj_clean_t12"
    proj_clean.mkdir()
    for turn, exp_tpl, exp_mode, exp_sb in (("5", "Template 12", "state-handoff", True), ("2", "Template 11", "auto", False)):
        rc, out = _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_clean), "--transcript", str(tp), "--turn", turn], monkeypatch)
        res = json.loads(out)
        assert (rc, res["handoff_template"], res["metadata"]["standby_mode"]) == (0, exp_tpl, exp_sb)
        lint_r, lint_c = tt_mod.lint_prompt_text(Path(res["prompt_path"]).read_text(encoding="utf-8"), mode=exp_mode)
        assert (lint_c, lint_r["passed"]) == (0, True)

    proj_busy = tmp_path / "proj_busy"
    proj_busy.mkdir()
    with win32_mod.Win32NamedMutex(f"Global\\NK_HandoffWorker_{_repo_hash16(proj_busy)}", timeout_ms=1000, is_path=False):
        rc_w, out_w = _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_busy), "--transcript", str(tp), "--turn", "2"], monkeypatch, in_thread=True)
        assert (rc_w, json.loads(out_w)["status"]) == (0, "SKIPPED_LOCK_BUSY")

    batch_name = win32_mod.get_repo_batch_mutex_name(proj_busy.resolve())
    orig_mtx = handoff_mod.Win32NamedMutex
    with monkeypatch.context() as mp_mtx:
        mp_mtx.setattr(handoff_mod, "Win32NamedMutex", lambda name, timeout_ms=1000, is_path=True: orig_mtx(name, timeout_ms=min(int(timeout_ms), 20), is_path=is_path))
        with orig_mtx(batch_name, timeout_ms=1000, is_path=False):
            rc_b, out_b = _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_busy), "--transcript", str(tp), "--turn", "2"], monkeypatch, in_thread=True)
    assert (rc_b, json.loads(out_b)["status"]) == (0, "SKIPPED_LOCK_BUSY")
    return proj_busy


def _assert_win32_global_fallback_and_replace_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, win32_mod: Any
) -> None:
    if sys.platform == "win32" and win32_mod._kernel32 is not None:
        real_k32 = win32_mod._kernel32
        seen_names: List[str] = []
        deny_cls = _make_global_deny_k32_class(real_k32, seen_names)
        with monkeypatch.context() as mp_k:
            mp_k.setattr(win32_mod, "_kernel32", deny_cls())
            probe_name, local_name = f"Global\\NK_FallbackTest_{os.getpid()}", f"Local\\NK_FallbackTest_{os.getpid()}"
            with win32_mod.Win32NamedMutex(probe_name, timeout_ms=1000, is_path=False) as mtx:
                assert (mtx.acquired, seen_names) == (True, [probe_name, local_name])
                check_h = real_k32.OpenMutexW(0x00100000, False, local_name)
                assert check_h
                real_k32.CloseHandle(ctypes.c_void_p(check_h))

    orig_replace = os.replace
    for winerr_code in (5, 32, 33):
        src, dst = tmp_path / f"src_{winerr_code}.tmp", tmp_path / f"dst_{winerr_code}.txt"
        src.write_text(f"payload_{winerr_code}", encoding="utf-8")
        dst.write_text("old", encoding="utf-8")
        attempts = {"n": 0}

        def _transient_replace(s: Any, d: Any, _code: int = winerr_code) -> None:
            attempts["n"] += 1
            if attempts["n"] <= 2:
                err = OSError("transient win32 sharing error")
                err.winerror = _code
                raise err
            orig_replace(s, d)

        with monkeypatch.context() as mp_rep:
            mp_rep.setattr(os, "replace", _transient_replace)
            win32_mod._replace_with_retry(src, dst, retries=4, delay_sec=0.005)
        assert (attempts["n"], dst.read_text(encoding="utf-8")) == (3, f"payload_{winerr_code}")


@pytest.mark.integration
def test_handoff_templates_dry_run_and_win32_mutex_retry(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica --dry-run, Template 11/12 lintati, mutex Win32 Global/Local e retry WinError (5, 32, 33)."""
    isolated_nk_ws_factory("ho_tpl", apply_inproc=True)
    handoff_mod = load_script_by_relpath("nk_session_handoff_acs", "scripts/nk_session_handoff.py")
    win32_mod = load_script_by_relpath("win32_2pc_engine_acs", "scripts/win32_2pc_engine.py")
    tt_mod = load_script_by_relpath("nk_transcript_tools_acs", "scripts/nk_transcript_tools.py")

    tp = tmp_path / "tp_dry.jsonl"
    _write_jsonl(tp, [{"step_index": 1, "source": "USER", "content": "dry test"}])
    _assert_handoff_dry_run_and_fsm_checkpoints(tmp_path, tp, monkeypatch, handoff_mod)
    _assert_handoff_t11_t12_lint_and_mutex_busy(tmp_path, tp, monkeypatch, handoff_mod, win32_mod, tt_mod)
    _assert_win32_global_fallback_and_replace_retry(tmp_path, monkeypatch, win32_mod)


def _assert_bootstrap_sentry_green_and_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boot_mod: Any
) -> None:
    proj_boot = tmp_path / "proj_boot"
    (proj_boot / "nk_tracking").mkdir(parents=True)
    (proj_boot / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": {"value": 100.0}, "unit_tests_total": {"value": 183}}}), encoding="utf-8"
    )
    tp_boot = tmp_path / "tp_boot.jsonl"
    _write_jsonl(tp_boot, [{"step_index": i, "source": "MODEL", "input_tokens": 10_000, "content": "ok"} for i in range(5)])

    boot_args = ["--project-root", str(proj_boot), "--transcript", str(tp_boot), "--conversation-id", "conv-boot-warn", "--json"]
    buf_b1 = io.StringIO()
    with monkeypatch.context() as mp1:
        boot_mod.NKSessionBootstrap._MEMORY_CACHE.pop(str(proj_boot.resolve()), None)
        mp1.setattr(sys, "stdout", buf_b1)
        mp1.setattr(sys, "stderr", io.StringIO())
        assert int(boot_mod.main(boot_args) or 0) == 0
    r1 = json.loads(buf_b1.getvalue())
    assert (r1["status"], r1["checks"]["context_sentry"]["status"], r1["checks"]["context_sentry"]["step_count"]) == ("PASS", "GREEN", 5)

    with open(tp_boot, "ab") as f:
        f.write((json.dumps({"step_index": 5, "source": "MODEL", "input_tokens": 160_000, "content": "warn"}) + "\n").encode("utf-8"))
    buf_b2 = io.StringIO()
    with monkeypatch.context() as mp2:
        boot_mod.NKSessionBootstrap._MEMORY_CACHE.pop(str(proj_boot.resolve()), None)
        mp2.setattr(sys, "stdout", buf_b2)
        mp2.setattr(sys, "stderr", io.StringIO())
        assert int(boot_mod.main(boot_args) or 0) == 0
    r2 = json.loads(buf_b2.getvalue())
    assert (r2["status"], r2["checks"]["context_sentry"]["status"], r2["checks"]["context_sentry"]["step_count"]) == ("PASS", "WARN", 6)


def _assert_compliance_penalties_and_ghost_cove(tmp_path: Path) -> None:
    comp_mod = load_script_by_relpath("nk_compliance_checker_acs", "scripts/nk_compliance_checker.py")
    rsi_mod = load_script_by_relpath("rsi_convergence_acs", "scripts/rsi_convergence_engine.py")
    checker = comp_mod.NKComplianceChecker(workspace_root=tmp_path)

    tp_warn = tmp_path / "tp_comp_warn.jsonl"
    _write_jsonl(tp_warn, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Audit"}, {"step_index": 2, "source": "MODEL", "input_tokens": 160_000, "content": "ok"}])
    res_cw = checker.audit_transcript(tp_warn)
    assert (res_cw["warn_advisory"], res_cw["metrics"]["context_sentry_status"], res_cw["scores"]["procedural_score"], res_cw["penalties"]) == (True, "WARN", 100, [])

    tp_yel = tmp_path / "tp_comp_yellow.jsonl"
    _write_jsonl(tp_yel, [{"step_index": i, "source": "MODEL", "input_tokens": 120_000, "content": "y"} for i in range(160)])
    res_cy = checker.audit_transcript(tp_yel)
    assert (res_cy["warn_advisory"], res_cy["metrics"]["context_sentry_status"], res_cy["scores"]["procedural_score"]) == (False, "YELLOW", 85)

    tp_red = tmp_path / "tp_comp_red.jsonl"
    _write_jsonl(tp_red, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Audit"}, {"step_index": 2, "source": "MODEL", "input_tokens": 210_000, "content": "red"}])
    res_cr = checker.audit_transcript(tp_red)
    assert (res_cr["warn_advisory"], res_cr["metrics"]["context_sentry_status"], res_cr["scores"]["procedural_score"]) == (False, "RED", 65)

    cove_proj = tmp_path / "proj_cove"
    (cove_proj / ".agents" / "skills" / "GhostSkill").mkdir(parents=True)
    (cove_proj / ".agents" / "skills" / "GhostSkill" / "SKILL.md").write_text("# Ghost\nEsegui `python scripts/missing_ghost_script.py --ghost-flag`.\n", encoding="utf-8")
    cove_res = rsi_mod.RSIConvergenceEngine(workspace_root=cove_proj).verify_cli_flags_cove(cove_proj)
    assert cove_res["passed"] is False
    assert any("missing_ghost_script.py" in inv for inv in cove_res["invalid_flags"])


@pytest.mark.integration
def test_bootstrap_compliance_warn_penalties_and_rsi_cove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica bootstrap WARN delta, penalita compliance WARN/YELLOW/RED e CoVe script mancante."""
    boot_mod = load_script_by_relpath("nk_session_bootstrap_acs", "scripts/nk_session_bootstrap.py")
    _isolate_tmp_dirs(tmp_path, monkeypatch)
    monkeypatch.setenv("NK_MODEL_PROFILE", "carbon")
    _assert_bootstrap_sentry_green_and_warn(tmp_path, monkeypatch, boot_mod)
    _assert_compliance_penalties_and_ghost_cove(tmp_path)


def _assert_fastguard_inproc_io_cases(
    blocked_file: Path, proj: Path, tp_low: Path, tmp_path: Path
) -> None:
    """Verifica in-process warn su NK_HOOKS_TEMP_DIR invalido e EOF/None stdin."""
    fg_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    pl_dir = json.dumps({"conversationId": "conv-cli-bad-dir", "projectRoot": str(proj), "transcriptPath": str(tp_low)}, ensure_ascii=True)
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(blocked_file))
        mp.setattr(sys, "stdin", io.StringIO(pl_dir))
        mp.setattr(sys, "stdout", buf_out)
        mp.setattr(sys, "stderr", buf_err)
        rc_dir = int(fg_mod.main(["--event", "PreInvocation"]) or 0)
    assert rc_dir == 0 and json.loads(buf_out.getvalue().strip()) == {} and "[ACS-FASTGUARD WARN]" in buf_err.getvalue()

    hooks_ok = tmp_path / "hooks_ok_inproc"
    hooks_ok.mkdir(parents=True, exist_ok=True)
    for stdin_obj in (io.StringIO(""), None):
        b_out, b_err = io.StringIO(), io.StringIO()
        with pytest.MonkeyPatch.context() as mp2:
            mp2.setenv("NK_HOOKS_TEMP_DIR", str(hooks_ok))
            mp2.setattr(sys, "stdin", stdin_obj)
            mp2.setattr(sys, "stdout", b_out)
            mp2.setattr(sys, "stderr", b_err)
            rc_empty = int(fg_mod.main(["--event", "PreInvocation", "--project-root", str(proj)]) or 0)
        assert rc_empty == 0 and json.loads(b_out.getvalue().strip()) == {}


def _assert_save_state_atomic_and_root_resolution(
    tmp_path: Path, fastguard_mod: Any, srmw: Any
) -> Path:
    assert Path(fastguard_mod.__file__).resolve() == _resolve_script("nk_acs_fastguard.py").resolve()
    assert fastguard_mod._save_state_atomic(None, {"version": 1}) == (False, "missing_state_path")
    ok_miss, reason_miss = fastguard_mod._save_state_atomic(str(tmp_path / "missing_parent" / "fastguard_state.json"), {"version": 1})
    assert (ok_miss, isinstance(reason_miss, str), str(reason_miss).startswith("io_error:")) == (False, True, True)

    blocked_parent = tmp_path / "blocked_parent_file"
    blocked_parent.write_text("not_a_dir", encoding="utf-8")
    ok_blk, reason_blk = fastguard_mod._save_state_atomic(str(blocked_parent / "state.json"), {"version": 1})
    assert (ok_blk, isinstance(reason_blk, str), str(reason_blk).startswith("io_error:")) == (False, True, True)

    good_target = tmp_path / "good_dir" / "fastguard_state.json"
    good_target.parent.mkdir(parents=True)
    assert fastguard_mod._save_state_atomic(str(good_target), {"version": 1, "steps": 3}) == (True, None)
    assert json.loads(good_target.read_text(encoding="utf-8")) == {"version": 1, "steps": 3}

    ws_wrap = tmp_path / "ws_wrap"
    hub_dir = ws_wrap / "NK_Hub"
    (hub_dir / "scripts").mkdir(parents=True)
    assert srmw._resolve_eff_root({}, None) == str(srmw._fg_attr("_WORKSPACE_ROOT", srmw._WORKSPACE_ROOT))
    assert Path(srmw._resolve_eff_root({"projectRoot": str(ws_wrap)}, None)) == hub_dir.resolve()

    ext_app = ws_wrap / "NK_External_Projects" / "AppDemo"
    ext_app.mkdir(parents=True)
    assert srmw._resolve_hub_and_project_roots({}, str(hub_dir)) == (str(hub_dir.resolve()), str(hub_dir.resolve()))
    assert srmw._resolve_hub_and_project_roots({}, str(ext_app)) == (str(hub_dir.resolve()), str(ext_app.resolve()))
    solo_dir = tmp_path / "solo_proj"
    solo_dir.mkdir()
    assert srmw._resolve_hub_and_project_roots({}, str(solo_dir))[1] == str(solo_dir.resolve())

    stg_sub = tmp_path / "repo_stg" / ".staging"
    stg_sub.mkdir(parents=True)
    assert len(srmw._candidate_roots(str(stg_sub))) == 2
    return good_target


def _assert_state_rmw_transcript_reparse_typed_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fastguard_mod: Any, srmw: Any, good_target: Path
) -> None:
    user_tp = tmp_path / "u_home" / ".gemini" / "antigravity" / "brain" / "cid_home_1" / ".system_generated" / "logs" / "transcript.jsonl"
    _write_jsonl(user_tp, [{"step_index": 1}])
    with monkeypatch.context() as mp_rmw:
        mp_rmw.setenv("USERPROFILE", str(tmp_path / "u_home"))
        assert srmw._resolve_transcript_path(None, {}, "cid_home_1") == str(user_tp)
        mp_rmw.delenv("NK_HOOKS_TEMP_DIR", raising=False)
        mp_rmw.delenv("TEMP", raising=False)
        mp_rmw.delenv("TMP", raising=False)
        assert srmw._get_hooks_temp_dir() is not None
        mp_rmw.setattr(srmw, "_is_reparse_or_symlink", lambda _p: True)
        mp_rmw.setattr(fastguard_mod, "_is_reparse_or_symlink", lambda _p: True, raising=False)
        assert srmw._get_hooks_temp_dir() is None
        assert srmw._save_state_atomic(str(good_target), {"version": 1}) == (False, "reparse_guard")

    list_state = tmp_path / "good_dir" / "list_state.json"
    list_state.write_text("[1, 2]", encoding="utf-8")
    assert srmw._load_state_with_exists(str(list_state))[1:] == (True, True)
    typed_state = tmp_path / "good_dir" / "typed_state.json"
    typed_state.write_text(json.dumps({"steps": "bad", "z2_last_spawn_ts": 5, "session_start_ns": 0}), encoding="utf-8")
    loaded_t, ex_t, rec_t = srmw._load_state_with_exists(str(typed_state))
    assert (ex_t, rec_t, loaded_t["steps"], loaded_t["z2_last_spawn_ts"]) == (True, False, 0, 5.0)
    assert loaded_t["session_start_ns"] > 0

    def _win32_busy_replace(_s: Any, _d: Any) -> None:
        err = OSError("sharing violation")
        err.winerror = 32
        raise err

    with monkeypatch.context() as mp_w32:
        mp_w32.setattr(os, "replace", _win32_busy_replace)
        mp_w32.setattr(srmw.time, "sleep", lambda _sec: None)
        ok_w32, err_w32 = srmw._save_state_atomic(str(good_target), {"version": 1})
    assert (ok_w32, isinstance(err_w32, str), str(err_w32).startswith("winerror_exhausted:")) == (False, True, True)


@pytest.mark.fast
def test_fastguard_save_state_atomic_errors_and_state_rmw_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica _save_state_atomic ed esercita i branch mancanti di nk_acs_fastguard/state_rmw.py."""
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    from _internal.nk_acs_fastguard import state_rmw as srmw

    good_target = _assert_save_state_atomic_and_root_resolution(tmp_path, fastguard_mod, srmw)
    _assert_state_rmw_transcript_reparse_typed_and_retry(tmp_path, monkeypatch, fastguard_mod, srmw, good_target)


@pytest.mark.integration
def test_fastguard_cli_stderr_and_nonblocking_stdin(
    tmp_path: Path, isolated_nk_ws_factory: Any
) -> None:
    """Verifica diagnostica stderr CLI su errori I/O e stdin PIPE non bloccante (2 sottoprocessi mirati)."""
    fg_script = _resolve_script("nk_acs_fastguard.py").resolve()
    proj = tmp_path / "proj_cli_err"
    proj.mkdir()
    tp_low = tmp_path / "tp_cli_low.jsonl"
    _write_jsonl(tp_low, [{"step_index": 1, "source": "MODEL", "input_tokens": 1000}])

    blocked_file = tmp_path / "blocked_dir"
    blocked_file.write_text("x", encoding="utf-8")
    _assert_fastguard_inproc_io_cases(blocked_file, proj, tp_low, tmp_path)

    cmd_cli = [sys.executable, "-S", "-B", "-u", str(fg_script), "--event", "PreInvocation"]
    env_save_err, hooks_err, _ = isolated_nk_ws_factory("cli_save_err")
    (hooks_err / "nk_hooks" / "fastguard_conv-cli-save-err.json").mkdir(parents=True)
    pl_save = json.dumps({"conversationId": "conv-cli-save-err", "projectRoot": str(proj), "transcriptPath": str(tp_low)}, ensure_ascii=True)
    proc_save = subprocess.run(cmd_cli, input=pl_save, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env_save_err, timeout=15, shell=False)
    assert proc_save.returncode == 0 and json.loads(proc_save.stdout.strip()) == {} and "[ACS-FASTGUARD WARN] state_save_failed" in proc_save.stderr

    cmd_no_stdin = [*cmd_cli, "--project-root", str(proj)]
    proc_pipe = subprocess.Popen(cmd_no_stdin, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env_save_err, shell=False)
    try:
        rc_pipe = proc_pipe.wait(timeout=3)
        out_pipe = proc_pipe.stdout.read() if proc_pipe.stdout is not None else ""
        assert rc_pipe == 0 and json.loads(out_pipe.strip()) == {}
    finally:
        for stream in (proc_pipe.stdin, proc_pipe.stdout, proc_pipe.stderr):
            if stream is not None:
                stream.close()


def _assert_cold_backscan_case_a_and_b(
    tmp_path: Path, fastguard_mod: Any, filler: List[Dict[str, Any]]
) -> None:
    tp_stale = tmp_path / "tp_cold_comp.jsonl"
    _write_jsonl(tp_stale, [*filler, {"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction"}])
    cp1_end = tp_stale.stat().st_size
    with open(tp_stale, "ab") as f:
        f.write((json.dumps({"step_index": 136, "source": "MODEL", "input_tokens": 175_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}) + "\n").encode("utf-8"))
    cp2_end = tp_stale.stat().st_size

    stale_base = {"version": 1, "byte_offset": 0, "steps": 140, "fallback_steps": 99, "last_actual_tokens": 175_000, "prev_actual_tokens": 175_000, "epoch_baseline_tokens": 120_000, "compaction_epoch": 1, "checkpoint_byte_offset": cp1_end, "reanchor_emitted_offset": cp1_end, "z1_epoch": 1, "z3_pre_epoch": 1, "z3_post_epoch": 1, "z2_last_spawn_ts": time.time(), "z2_last_spawn_epoch": 1}
    stale_a = dict(stale_base)
    fastguard_mod._cold_backscan_64kb(str(tp_stale), cp2_end, stale_a)
    assert (stale_a["compaction_epoch"], stale_a["checkpoint_byte_offset"], stale_a["steps"], stale_a["last_actual_tokens"], stale_a["z1_epoch"], stale_a["reanchor_emitted_offset"]) == (2, cp2_end, 0, 0, -1, cp1_end)

    with open(tp_stale, "ab") as f:
        f.write((json.dumps({"step_index": 137, "source": "MODEL", "input_tokens": 18_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 138, "source": "MODEL", "input_tokens": 162_000}) + "\n").encode("utf-8"))
    stale_b = dict(stale_base)
    fastguard_mod._cold_backscan_64kb(str(tp_stale), tp_stale.stat().st_size, stale_b)
    assert (stale_b["compaction_epoch"], stale_b["steps"], stale_b["last_actual_tokens"], stale_b["epoch_baseline_tokens"], stale_b["z3_post_epoch"]) == (2, 2, 162_000, 18_000, -1)


def _assert_cold_rehydrate_idempotency(
    tmp_path: Path, hooks_tmp: Path, monkeypatch: pytest.MonkeyPatch, filler: List[Dict[str, Any]]
) -> None:
    proj = tmp_path / "proj_cold_idem"
    _precreate_wal_hold(proj)
    tp_big = tmp_path / "tp_cold_idem.jsonl"
    _write_jsonl(tp_big, [*filler, {"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}])
    cp_end = tp_big.stat().st_size
    with open(tp_big, "ab") as f:
        f.write((json.dumps({"step_index": 137, "source": "MODEL", "input_tokens": 18_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 138, "source": "MODEL", "input_tokens": 162_000}) + "\n").encode("utf-8"))

    pl = {"conversationId": "conv-cold-idem", "projectRoot": str(proj), "transcriptPath": str(tp_big)}
    rc1, out1, _ = _run_fastguard_inproc("PreInvocation", pl, monkeypatch)
    assert rc1 == 0
    assert "[RULE-REHYDRATE]" in _native_sys_msg(out1)
    assert "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out1)

    st_path = hooks_tmp / "nk_hooks" / "fastguard_conv-cold-idem.json"
    persisted = json.loads(st_path.read_text(encoding="utf-8"))
    assert (persisted["checkpoint_byte_offset"], persisted["reanchor_emitted_offset"]) == (cp_end, cp_end)
    persisted.update({"byte_offset": 0, "z3_pre_epoch": 1, "z3_post_epoch": 1, "z2_last_spawn_epoch": 1})
    st_path.write_text(json.dumps(persisted, ensure_ascii=True), encoding="utf-8")

    rc2, out2, _ = _run_fastguard_inproc("PreInvocation", pl, monkeypatch)
    persisted_after = json.loads(st_path.read_text(encoding="utf-8"))
    assert (rc2, out2, persisted_after["compaction_epoch"], persisted_after["z3_pre_epoch"]) == (0, {}, 1, 1)


def _assert_b2b_compactions_and_epoch3_reset(
    tmp_path: Path, hooks_tmp: Path, monkeypatch: pytest.MonkeyPatch, fastguard_mod: Any
) -> None:
    proj_b2b = tmp_path / "proj_b2b"
    _precreate_wal_hold(proj_b2b)
    tp_b2b = tmp_path / "tp_b2b.jsonl"
    _write_jsonl(tp_b2b, [{"step_index": 1, "source": "MODEL", "input_tokens": 205_000}])
    pl_b2b = {"conversationId": "conv-b2b-gates", "projectRoot": str(proj_b2b), "transcriptPath": str(tp_b2b)}

    assert "[ACS-Z3 CRITICO]" in _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_b2b, monkeypatch)[1])
    assert "[ACS-Z3]" in _native_post_msg(_run_fastguard_inproc("PostInvocation", pl_b2b, monkeypatch)[1])[1]
    with open(tp_b2b, "ab") as f:
        f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 2, "source": "MODEL", "input_tokens": 205_000}) + "\n").encode("utf-8"))

    msg_p1 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_b2b, monkeypatch)[1])
    assert "[RULE-REHYDRATE]" in msg_p1
    assert "[ACS-Z3 CRITICO]" in msg_p1
    assert "[ACS-Z3]" in _native_post_msg(_run_fastguard_inproc("PostInvocation", pl_b2b, monkeypatch)[1])[1]

    st1 = json.loads((hooks_tmp / "nk_hooks" / "fastguard_conv-b2b-gates.json").read_text(encoding="utf-8"))
    assert (st1["compaction_epoch"], st1["z1_epoch"], st1["z3_pre_epoch"], st1["z3_post_epoch"]) == (1, 1, 1, 1)
    st1["fallback_steps"] = 55
    st1["z2_last_spawn_epoch"] = 1
    with open(tp_b2b, "ab") as f:
        f.write((json.dumps({"source": "SYSTEM", "compacted": True}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 3, "source": "MODEL", "input_tokens": 45_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT"}) + "\n").encode("utf-8"))
    fastguard_mod._advance_cursor(str(tp_b2b), st1)
    assert (st1["compaction_epoch"], st1["steps"], st1["fallback_steps"], st1["last_actual_tokens"], st1["z1_epoch"], st1["z2_last_spawn_ts"]) == (3, 0, 0, 0, -1, 0.0)


@pytest.mark.fast
def test_cold_backscan_rehydrate_idempotency_and_b2b_compactions(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica cold backscan Caso A/B/C idempotenza [RULE-REHYDRATE] e back-to-back compactions."""
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    _, hooks_tmp, _ = isolated_nk_ws_factory("cold_b2b", apply_inproc=True)
    filler = [{"step_index": i, "source": "MODEL", "content": "F" * 4000} for i in range(135)]
    _assert_cold_backscan_case_a_and_b(tmp_path, fastguard_mod, filler)
    _assert_cold_rehydrate_idempotency(tmp_path, hooks_tmp, monkeypatch, filler)
    _assert_b2b_compactions_and_epoch3_reset(tmp_path, hooks_tmp, monkeypatch, fastguard_mod)


def _assert_fg_args_corrupt_and_fallback_steps(
    tmp_path: Path, hooks_tmp: Path, monkeypatch: pytest.MonkeyPatch, fg: Any
) -> None:
    with pytest.raises(SystemExit) as help_exc:
        fg._parse_fastguard_args(["--help"])
    assert help_exc.value.code == 0
    with pytest.raises(SystemExit) as bad_ev:
        fg._parse_fastguard_args(["--event=InvalidEvent"])
    assert bad_ev.value.code == 2

    assert fg._extract_tokens({"usage": {"prompt_tokens": 42_000}}) == 42_000
    assert fg._candidate_roots(str(tmp_path / ".staging"))[0].endswith(".staging")

    bad_st = hooks_tmp / "nk_hooks" / "corrupt_state.json"
    bad_st.parent.mkdir(parents=True, exist_ok=True)
    bad_st.write_text("{broken", encoding="utf-8")
    _, exists_b, rec_b = fg._load_state_with_exists(str(bad_st))
    assert (exists_b, rec_b) == (True, True)

    proj_fb = tmp_path / "proj_fb"
    _precreate_wal_hold(proj_fb)
    fb_state_p = hooks_tmp / "nk_hooks" / "fastguard_conv-fb-only.json"
    fb_seed = fg._default_state()
    fb_seed["fallback_steps"] = fg._Z1_STEPS - 1
    fb_state_p.write_text(json.dumps(fb_seed), encoding="utf-8")
    rc_fb, out_fb, _ = _run_fastguard_inproc(
        "PreInvocation", {"conversationId": "conv-fb-only", "projectRoot": str(proj_fb)}, monkeypatch,
        extra_args=["--conversation-id=conv-fb-only", f"--project-root={proj_fb}"],
    )
    assert rc_fb == 0
    assert "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_fb)

    with monkeypatch.context() as mp_bad:
        mp_bad.setattr(sys, "stdin", io.StringIO("{bad_stdin_json"))
        mp_bad.setattr(sys, "stdout", io.StringIO())
        mp_bad.setattr(sys, "stderr", io.StringIO())
        assert fg.main(["--event", "PreInvocation"]) == 0


def _assert_s2b_rule006_rehydrate_and_rmw_threads(
    tmp_path: Path, hooks_tmp: Path, monkeypatch: pytest.MonkeyPatch, fg: Any
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    proj_s2b = tmp_path / "proj_s2b"
    _precreate_wal_hold(proj_s2b)
    tp = tmp_path / "tp_s2b.jsonl"
    _write_jsonl(tp, [
        {"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "<USER_REQUEST>Implementa feature X</USER_REQUEST>"},
        {"step_index": 2, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "Nota su <CONTEXT_SUMMARY> nel mezzo della frase"},
        {"step_index": 3, "source": "MODEL", "input_tokens": 20_000},
    ])
    in_payload = json.dumps({"hookEventName": "PreInvocation", "conversationId": "conv-s2b", "projectRoot": str(proj_s2b), "transcriptPath": str(tp)})
    buf_out = io.StringIO()
    with monkeypatch.context() as mp_cc:
        mp_cc.setattr(sys, "stdin", io.StringIO(in_payload))
        mp_cc.setattr(sys, "stdout", buf_out)
        mp_cc.setattr(sys, "stderr", io.StringIO())
        assert fg.main(["--native-contract"]) == 0
    out1 = json.loads(buf_out.getvalue())
    assert "terminationBehavior" not in out1
    assert "[RULE-00.6-ENFORCE]" in _native_sys_msg(out1)
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-s2b", "projectRoot": str(proj_s2b), "transcriptPath": str(tp)}, monkeypatch)[1] == {}

    st_file = hooks_tmp / "nk_hooks" / "fastguard_conv-s2b.json"
    assert json.loads(st_file.read_text(encoding="utf-8"))["compaction_epoch"] == 0
    prompt_sha = hashlib.sha256(b"Implementa feature Y").hexdigest()
    (hooks_tmp / "nk_hooks" / "l0_gate_conv-s2b.json").write_text(json.dumps({"turn_prompt_sha256": prompt_sha}), encoding="utf-8")
    with open(tp, "ab") as f:
        f.write((json.dumps({"step_index": 4, "source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>\nRiassunto"}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 5, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Implementa feature Y"}) + "\n").encode("utf-8"))
    msg3 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", {"conversationId": "conv-s2b", "projectRoot": str(proj_s2b), "transcriptPath": str(tp)}, monkeypatch)[1])
    assert "[RULE-REHYDRATE]" in msg3
    assert "[RULE-00.6-ENFORCE]" not in msg3
    assert json.loads(st_file.read_text(encoding="utf-8"))["compaction_epoch"] == 1

    tp_sub = tmp_path / "tp_sub_s2b.jsonl"
    _write_jsonl(tp_sub, [
        {"step_index": 0, "source": "SYSTEM", "content": "<subagent_reminder>leaf</subagent_reminder>"},
        {"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Implementa Z"},
    ])
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-sub-s2b", "projectRoot": str(proj_s2b), "transcriptPath": str(tp_sub)}, monkeypatch)[1] == {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda idx: fg._persist_state_or_warn(str(st_file), {"steps": idx, "compaction_epoch": 1}), range(8)))
    assert isinstance(json.loads(st_file.read_text(encoding="utf-8"))["steps"], int)


def _assert_posix_fifo_stdin_branches(monkeypatch: pytest.MonkeyPatch, fg: Any) -> None:
    import select as _sel
    import stat as _st

    const_fg = sys.modules[fg._read_stdin_safe.__module__]
    with monkeypatch.context() as mp_lx_fg:
        mp_lx_fg.setattr(const_fg.sys, "platform", "linux")
        mp_lx_fg.setattr(const_fg.sys, "stdin", io.StringIO('{"ok": true}'))
        assert fg._read_stdin_safe() == '{"ok": true}'

        fake_fifo_stdin = SimpleNamespace(isatty=lambda: False, fileno=lambda: 77, read=lambda: "pipe_payload")
        mp_lx_fg.setattr(const_fg.sys, "stdin", fake_fifo_stdin)
        mp_lx_fg.setattr(const_fg.os, "fstat", lambda _fd: SimpleNamespace(st_mode=0o100644))
        assert fg._read_stdin_safe() == "pipe_payload"
        mp_lx_fg.setattr(const_fg.os, "fstat", lambda _fd: SimpleNamespace(st_mode=_st.S_IFIFO | 0o600))
        mp_lx_fg.setattr(_sel, "select", lambda *_a: ([], [], []))
        assert fg._read_stdin_safe() == ""
        mp_lx_fg.setattr(_sel, "select", lambda *_a: ([77], [], []))
        assert fg._read_stdin_safe() == "pipe_payload"
        mp_lx_fg.setattr(const_fg.os, "fstat", lambda _fd: (_ for _ in ()).throw(OSError("fstat fail")))
        assert fg._read_stdin_safe() == "pipe_payload"


@pytest.mark.fast
def test_fastguard_fallback_steps_args_s2b_rmw_and_fifo(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica fallback steps, CLI args, JSON corrotto, camelCase, RMW mutex, [RULE-00.6-ENFORCE] e POSIX FIFO."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("fg_s2b", apply_inproc=True)
    fg = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    _assert_fg_args_corrupt_and_fallback_steps(tmp_path, hooks_tmp, monkeypatch, fg)
    _assert_s2b_rule006_rehydrate_and_rmw_threads(tmp_path, hooks_tmp, monkeypatch, fg)
    _assert_posix_fifo_stdin_branches(monkeypatch, fg)


def _assert_wave3_idle_dedup_and_rotation(tmp_path: Path, handoff_mod: Any, he_mod: Any) -> None:
    proj = tmp_path / "proj_w3_dedup"
    proj.mkdir(parents=True)
    r1 = handoff_mod.record_idle_checkpoint_anchor(gate_status="PASS", milestone_id="MS-W3", root=proj, state_sha256_override="sha_v1", staging_state_sha256="stg_v1", conversation_id="conv-w3-dedup", handoff_template="Template 12")
    assert (r1["status"], r1["deduplicated"]) == ("RECORDED", False)
    r2 = handoff_mod.record_idle_checkpoint_anchor(gate_status="PASS", milestone_id="MS-W3", root=proj, state_sha256_override="sha_v1", staging_state_sha256="stg_v1", conversation_id="conv-w3-dedup", handoff_template="Template 12")
    assert (r2["status"], r2["deduplicated"]) == ("DEDUP_SKIPPED", True)
    assert len((proj / "nk_tracking" / "anchor" / "session_anchor.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert len((proj / "nk_tracking" / "sessions" / "conv-w3-dedup" / "session_anchor.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    r3 = handoff_mod.record_idle_checkpoint_anchor(gate_status="PASS", milestone_id="MS-W3", root=proj, state_sha256_override="sha_v2", staging_state_sha256="stg_v1", conversation_id="conv-w3-dedup", handoff_template="Template 12")
    assert (r3["status"], r3["deduplicated"]) == ("RECORDED", False)
    assert len((proj / "nk_tracking" / "anchor" / "session_anchor.jsonl").read_text(encoding="utf-8").splitlines()) == 2

    assert he_mod.ANCHOR_MAX_LINES == 200
    proj_rot = tmp_path / "proj_w3_rot"
    global_anchor = proj_rot / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    global_anchor.parent.mkdir(parents=True, exist_ok=True)
    seed_lines = [json.dumps({"event": "fsm_checkpoint", "turn": 1, "idx": idx, "state_sha256": f"s_{idx}"}) for idx in range(200)]
    global_anchor.write_text("\n".join(seed_lines) + "\n", encoding="utf-8")
    r_rot = handoff_mod.record_idle_checkpoint_anchor(gate_status="PASS", milestone_id="MS-W3", root=proj_rot, state_sha256_override="sha_rot_final", staging_state_sha256="stg_rot", conversation_id="conv-w3-rot")
    assert r_rot["status"] == "RECORDED"
    rotated = [json.loads(ln) for ln in global_anchor.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert (len(rotated), rotated[0]["idx"], rotated[-1]["state_sha256"]) == (200, 1, "sha_rot_final")


def _assert_wave3_session_retention_limit(tmp_path: Path, ss_mod: Any) -> None:
    assert ss_mod.SESSION_RETENTION_LIMIT == 5
    proj_ret = tmp_path / "proj_w3_ret"
    sessions_root = proj_ret / "nk_tracking" / "sessions"
    base_t = time.time() - 1000.0
    for idx in range(7):
        sdir = sessions_root / f"sess-{idx}"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "session_anchor.jsonl").write_text('{"event":"auto_checkpoint_idle"}\n', encoding="utf-8")
        ts = base_t + idx * 50.0
        os.utime(sdir, (ts, ts))
    removed = ss_mod.prune_session_tracking_dirs(proj_ret, active_conversation_id="sess-0", max_sessions=5)
    remaining = sorted(p.name for p in sessions_root.iterdir() if p.is_dir())
    assert (len(remaining), "sess-0" in remaining, set(removed)) == (5, True, {"sess-1", "sess-2"})


@pytest.mark.fast
def test_wave3_idle_anchor_dedup_rotation_cap_and_session_retention(tmp_path: Path) -> None:
    """Wave 3: deduplica auto_checkpoint_idle, rotazione <=200 righe e retention 5 sessioni."""
    handoff_mod = load_nk_script_module("nk_session_handoff")
    from _internal.nk_session_handoff import handoff_engine as he_mod, session_state as ss_mod

    _assert_wave3_idle_dedup_and_rotation(tmp_path, handoff_mod, he_mod)
    _assert_wave3_session_retention_limit(tmp_path, ss_mod)


def _assert_z2_imperatives_and_anchor_meta(tmp_path: Path, z2: Any) -> Path:
    assert z2._has_direct_imperative_outside_fence("Non modificare il file scripts/x.py") is False
    assert z2._has_direct_imperative_outside_fence("```json\n{\"status\": \"ok\"}\n```\n- **Stato**: scrivi report") is False
    assert z2._has_direct_imperative_outside_fence("```bash\nrm -rf /\n```") is True
    assert z2._has_direct_imperative_outside_fence("Modifica subito il file scripts/x.py") is True

    assert z2._parse_anchor_iso_ts({"timestamp": "2026-11-22T01:00:00Z"}) is not None
    assert z2._parse_anchor_iso_ts({"timestamp": "bad-iso", "timestamp_ns": True}) is None
    assert z2._parse_anchor_iso_ts({"timestamp_ns": 1_700_000_000_000_000_000}) is not None

    proj = tmp_path / "proj_z2_b"
    anc = proj / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    anc.parent.mkdir(parents=True)
    pad_lines = [json.dumps({"event": "x", "pad": "a" * 120}) for _ in range(80)]
    pad_lines.append(json.dumps({"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "M-2PC", "timestamp": "2026-11-22T02:00:00Z"}))
    anc.write_text("\n".join(pad_lines) + "\n", encoding="utf-8")
    assert z2._read_anchor_meta([str(proj)], {}, conv_id="c1", default_turn=0)[0] == "M-2PC"

    sess_anc = proj / "nk_tracking" / "sessions" / "c_iso" / "session_anchor.jsonl"
    sess_anc.parent.mkdir(parents=True)
    sess_anc.write_text(json.dumps({"milestone_id": z2.DEFAULT_MILESTONE_ID, "timestamp": "2026-11-22T01:00:00Z"}) + "\n", encoding="utf-8")
    anc.write_text("\n{bad\n[1]\n" + json.dumps({"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "M-PROMO", "timestamp": "2026-11-22T03:00:00Z"}) + "\n" + json.dumps({"turn": 2, "conversation_id": "c_iso"}) + "\n", encoding="utf-8")
    assert z2._read_anchor_meta([str(proj)], {}, conv_id="c_iso", default_turn=0) == ("M-PROMO", 2)
    return proj


def _assert_z2_wal_mutex_and_env(proj: Path, monkeypatch: pytest.MonkeyPatch, z2: Any) -> None:
    wal_dir = proj / ".wal"
    wal_dir.mkdir(parents=True)
    (wal_dir / "ignore.txt").write_text("skip", encoding="utf-8")
    wal_f = wal_dir / "tx.wal"
    wal_f.write_text("{}", encoding="utf-8")
    assert z2._has_active_wal([str(proj)]) is True
    old_t = time.time() - 300.0
    os.utime(wal_f, (old_t, old_t))
    with monkeypatch.context() as mp_w:
        mp_w.delenv("TEMP", raising=False)
        mp_w.delenv("TMP", raising=False)
        assert z2._has_active_wal([str(proj)]) is False
        mp_w.setattr(z2, "_get_k32", lambda: (None, None))
        assert z2._is_batch_mutex_busy([str(proj)]) is False
        fake_ctypes = SimpleNamespace(set_last_error=lambda _e: None, get_last_error=lambda: z2._ERROR_ACCESS_DENIED)
        fake_k32 = SimpleNamespace(OpenMutexW=lambda _a, _i, _n: 0, CloseHandle=lambda _h: 1)
        mp_w.setattr(z2, "_get_k32", lambda: (fake_ctypes, fake_k32))
        assert z2._is_batch_mutex_busy([str(proj), str(proj)]) is True

    with monkeypatch.context() as mp_env:
        mp_env.setenv("NK_MILESTONE_ID", "M-ENV")
        assert z2._read_anchor_meta([str(proj)], {}, conv_id="c1")[0] == "M-ENV"


def _assert_z2_l0_exempt_and_large_oneshot(tmp_path: Path, z2: Any) -> None:
    for ok_p in ("ok", "status", "[3]", "7", "/compact", "<env_capsule>read</env_capsule>", "<env_capsule>short"):
        assert z2._is_l0_exempt_fast(ok_p) is True
    for no_p in ("scripts/x.py", "<env_capsule>rm -rf /</env_capsule>", "<env_capsule>" + ("x" * 140)):
        assert z2._is_l0_exempt_fast(no_p) is False

    hooks_d = tmp_path / "hooks_l0"
    hooks_d.mkdir()
    assert z2._check_l0_gate_one_shot("", "c1", str(hooks_d), {}, 0) is None
    tp_big = tmp_path / "tp_140k.jsonl"
    rows = [json.dumps({"type": "MODEL", "content": "pad_" + ("b" * 350)}) for _ in range(420)]
    rows.append(json.dumps({"type": "USER_INPUT", "content": "Implementa endpoint nuovo"}))
    tp_big.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (hooks_d / "l0_gate_c1.json").write_text("{bad", encoding="utf-8")
    st: Dict[str, Any] = {}
    assert "[RULE-00.6-ENFORCE]" in (z2._check_l0_gate_one_shot(str(tp_big), "c1", str(hooks_d), st, 0) or "")
    assert z2._check_l0_gate_one_shot(str(tp_big), "c1", str(hooks_d), st, 0) is None


@pytest.mark.fast
def test_acs_z2_l0_imperative_anchor_wal_and_missing_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Esercita nk_acs_fastguard/z2_and_l0.py su imperativi, anchor, WAL, L0 e branch mancanti."""
    load_nk_script_module("nk_acs_fastguard")
    from _internal.nk_acs_fastguard import z2_and_l0 as z2

    proj = _assert_z2_imperatives_and_anchor_meta(tmp_path, z2)
    _assert_z2_wal_mutex_and_env(proj, monkeypatch, z2)
    _assert_z2_l0_exempt_and_large_oneshot(tmp_path, z2)


def _assert_acs_consts_cache_and_bad_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], fg_mod: Any, fg_consts: Any
) -> Tuple[Path, Path, Path]:
    hooks_tmp = _isolate_tmp_dirs(tmp_path / "iso_fg_c", monkeypatch)
    proj = tmp_path / "proj_fg_c"
    cfg_p = proj / ".staging" / "nk_genome" / "configs" / "saturation_thresholds.json"
    cfg_p.parent.mkdir(parents=True)
    cfg_p.write_text(
        json.dumps({"autonomous_context_shield": {"z1_tokens": 100, "z2_tokens": 150, "z3_tokens": 200, "velocity_jump": 50, "velocity_floor": 100, "cooldown_s": 0.0}}),
        encoding="utf-8",
    )
    loaded = fg_consts._load_acs_thresholds([str(proj)])
    assert (loaded["z1_tokens"], loaded["fallback_steps"]["z1"]) == (100, 120)
    assert fg_consts._load_acs_thresholds([str(proj)])["z1_tokens"] == 100
    assert fg_consts._safe_int_val(True, 99) == 99
    fg_consts._warn_stderr("tag_x", "line1\nline2")
    assert "tag_x line1 line2" in capsys.readouterr().err

    assert "_Z1_TOKENS" in dir(fg_mod)
    assert fg_mod._Z1_TOKENS > 0
    with pytest.raises(AttributeError):
        getattr(fg_mod, "nonexistent_fg_sym_xyz")
    for bad_cli in (["--help"], ["--event=InvalidEvt"]):
        with pytest.raises(SystemExit):
            fg_mod.main(bad_cli)
    capsys.readouterr()

    fg_consts.register_facade_module("custom_fg_probe")
    fg_consts.register_facade_module("custom_fg_probe")
    with monkeypatch.context() as mp_c:
        mp_c.setattr(fg_consts.sys, "platform", "linux")
        assert fg_consts._get_k32() == (None, None)
        assert fg_consts._is_reparse_or_symlink(str(tmp_path / "missing_x")) is False
    return hooks_tmp, proj, cfg_p


def _assert_acs_win32_stdin_and_reparse_branches(
    monkeypatch: pytest.MonkeyPatch, cfg_p: Path, proj: Path, fg_consts: Any
) -> None:
    if sys.platform != "win32":
        return
    import msvcrt

    class _FakeUint32:
        def __init__(self, v: int) -> None:
            self.value = v

    with monkeypatch.context() as mp_w:
        mp_w.setattr(msvcrt, "get_osfhandle", lambda _fd: -1)
        assert fg_consts._win32_stdin_ready(0) is False
        mp_w.setattr(msvcrt, "get_osfhandle", lambda _fd: 123)
        mp_w.setattr(fg_consts, "_get_k32", lambda: (None, None))
        assert fg_consts._win32_stdin_ready(0) is True

        state_pipe = {"err": 5, "ft": 0, "ok": 0, "avail": 0}
        fake_c = SimpleNamespace(
            set_last_error=lambda _e: None, get_last_error=lambda: state_pipe["err"],
            c_void_p=lambda h: h, c_uint32=lambda v: _FakeUint32(v), byref=lambda obj: obj,
        )
        fake_k = SimpleNamespace(
            GetFileType=lambda _h: state_pipe["ft"],
            PeekNamedPipe=lambda _h, _a, _b, _c, av, _d: (setattr(av, "value", state_pipe["avail"]), state_pipe["ok"])[1],
            GetFileAttributesW=lambda _p: fg_consts._FILE_ATTRIBUTE_REPARSE_POINT,
        )
        mp_w.setattr(fg_consts, "_get_k32", lambda: (fake_c, fake_k))
        assert fg_consts._win32_stdin_ready(0) is False
        state_pipe.update({"err": 0, "ft": 1})
        assert fg_consts._win32_stdin_ready(0) is True
        state_pipe.update({"ft": fg_consts._FILE_TYPE_PIPE, "ok": 0})
        assert fg_consts._win32_stdin_ready(0) is False
        state_pipe.update({"ok": 1, "avail": 4})
        assert fg_consts._win32_stdin_ready(0) is True
        state_pipe.update({"avail": 0})
        mp_w.setattr(fg_consts.time, "sleep", lambda _s: None)
        assert fg_consts._win32_stdin_ready(0) is False

        mp_w.setattr(fg_consts.os, "lstat", lambda _p: (_ for _ in ()).throw(OSError("perm")))
        assert fg_consts._is_reparse_or_symlink(str(cfg_p)) is True
        assert fg_consts._is_safe_dir(str(proj)) is False
        assert fg_consts._stat_safe_file(str(cfg_p)) is None


def _assert_acs_cli_fallback_steps_and_cold_550k(
    tmp_path: Path, hooks_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    cfg_p: Path, proj: Path, fg_mod: Any, fg_consts: Any, fg_comp: Any,
) -> None:
    cfg_p.write_text(json.dumps({"autonomous_context_shield": {"z1_tokens": 100, "z2_tokens": 150, "z3_tokens": 200, "fallback_steps": {"z1": 1, "z2": 2, "z3": 2}}}), encoding="utf-8")
    fg_consts._ACS_PARSED_JSON_CACHE.clear()
    with monkeypatch.context() as mp_cli:
        mp_cli.setattr(sys, "stdin", io.StringIO("{corrupt"))
        assert fg_mod.main(["--event=PreInvocation"]) == 0
        assert capsys.readouterr().out.strip() == "{}"
        mp_cli.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "cid_fb_z", "projectRoot": str(proj)})))
        assert fg_mod.main(["--event=PreInvocation", "--native-contract"]) == 0
        assert "[ACS-Z1 SOFT-FOLDING]" in capsys.readouterr().out
        mp_cli.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "cid_fb_z", "projectRoot": str(proj)})))
        assert fg_mod.main(["--event=PreInvocation", "--native-contract"]) == 0
        assert "[ACS-Z3 CRITICO]" in capsys.readouterr().out

    tp_cold = tmp_path / "tp_cold_550k.jsonl"
    cold_rows = [json.dumps({"type": "CHECKPOINT", "source": "SYSTEM", "content": "<CONTEXT_SUMMARY> cp"})]
    cold_rows.extend(json.dumps({"type": "PLANNER_RESPONSE", "source": "MODEL", "input_tokens": 250, "content": "p_" + ("c" * 350)}) for _ in range(1500))
    tp_cold.write_text("\n".join(cold_rows) + "\n", encoding="utf-8")
    st_cold = fg_mod._default_state()
    fg_comp._advance_cursor(str(tp_cold), st_cold)
    assert (st_cold["compaction_epoch"] >= 1, st_cold["last_actual_tokens"]) == (True, 250)
    tp_cold.write_text('{"type": "MODEL", "input_tokens": 10}\n', encoding="utf-8")
    fg_comp._advance_cursor(str(tp_cold), st_cold)
    assert st_cold["steps"] == 1
    assert (hooks_tmp / "nk_hooks" / "fastguard_cid_fb_z.json").is_file()


@pytest.mark.fast
def test_acs_constants_thresholds_stdin_reparse_and_cli_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Esercita nk_acs_fastguard/constants.py, stdin Win32, reparse fallback e fallback CLI."""
    fg_mod = load_nk_script_module("nk_acs_fastguard")
    from _internal.nk_acs_fastguard import compaction as fg_comp, constants as fg_consts

    hooks_tmp, proj, cfg_p = _assert_acs_consts_cache_and_bad_cli(tmp_path, monkeypatch, capsys, fg_mod, fg_consts)
    _assert_acs_win32_stdin_and_reparse_branches(monkeypatch, cfg_p, proj, fg_consts)
    _assert_acs_cli_fallback_steps_and_cold_550k(tmp_path, hooks_tmp, monkeypatch, capsys, cfg_p, proj, fg_mod, fg_consts, fg_comp)


def _assert_sentry_lazy_thresholds_and_swarm(tmp_path: Path, cs_mod: Any) -> Path:
    assert "_GEN_CS" in dir(cs_mod)
    assert (isinstance(cs_mod._THRESHOLDS_DATA, dict), isinstance(cs_mod._PROFILES_DATA, dict)) == (True, True)
    assert (isinstance(cs_mod._STD_CS, dict), isinstance(cs_mod._GEN_CS, dict)) == (True, True)
    with pytest.raises(AttributeError):
        getattr(cs_mod, "nonexistent_sentry_attr_xyz")

    sentry = cs_mod.NKContextSentry(workspace_root=tmp_path, profile="generation")
    assert sentry.estimate_tokens("") == 0
    assert "TRUNCATED" in sentry.format_head_tail("A" * 2000, head_chars=50, tail_chars=50)
    assert sentry._extract_actual_tokens_from_record({"usage": {"input_tokens": 40, "cache_read_tokens": 10}}) == 50
    assert sentry.is_background_task_message({"sender": "task-7"}, "ok") is True

    assert (
        sentry.get_traffic_light_status(10, 1000, profile="standard")["status"],
        sentry.get_traffic_light_status(80, 1000, profile="standard")["status"],
        sentry.get_traffic_light_status(110, 1000, profile="standard")["status"],
        sentry.get_traffic_light_status(10, 1000, profile="generation", actual_context_tokens=210_000)["status"],
    ) == ("GREEN", "YELLOW", "RED", "RED")

    assert sentry.analyze_transcript(tmp_path / "missing_tp.jsonl")["status"] == "ERROR"
    corrupt_tp = tmp_path / "corrupt_tp.jsonl"
    corrupt_tp.write_text("{bad\n", encoding="utf-8")
    assert sentry.analyze_transcript(corrupt_tp)["status"] == "ERROR"

    swarm_tp = tmp_path / "swarm_tp.jsonl"
    swarm_tp.write_text(
        json.dumps({"step_index": 1, "source": "SYSTEM", "content": "<SYSTEM_MESSAGE>[Message] sender=sub content=" + ("w" * 2100) + "</SYSTEM_MESSAGE>"}) + "\n",
        encoding="utf-8",
    )
    sw_rep = sentry.analyze_transcript(swarm_tp)
    assert sw_rep["swarm_mss_warnings_count"] >= 1
    assert sw_rep["swarm_hygiene_violations_count"] >= 1
    return swarm_tp


def _assert_sentry_backscan_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], cs_mod: Any, tt_mod: Any, swarm_tp: Path
) -> None:
    big_cs_tp = tmp_path / "cs_70k.jsonl"
    cs_rows = [json.dumps({"type": "CHECKPOINT", "source": "SYSTEM", "content": "<CONTEXT_SUMMARY> cp"})]
    cs_rows.extend(json.dumps({"step_index": i + 1, "source": "MODEL", "content": "z" * 350}) for i in range(210))
    big_cs_tp.write_text("\n".join(cs_rows) + "\n", encoding="utf-8")
    assert tt_mod.find_last_compaction_offset_impl(big_cs_tp) == 0

    capsys.readouterr()
    assert cs_mod.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "CLI_STANDALONE"
    assert cs_mod.main(["--transcript", str(swarm_tp), "--verbose"]) == 0
    assert "NK-CONTEXT-SENTRY" in capsys.readouterr().out


@pytest.mark.fast
def test_context_sentry_lazy_thresholds_swarm_cap_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Esercita nk_context_sentry.py su lazy thresholds, traffic light, swarm cap, backscan e CLI."""
    cs_mod = load_nk_script_module("nk_context_sentry")
    from _internal.nk_context_sentry import transcript_tail as tt_mod

    swarm_tp = _assert_sentry_lazy_thresholds_and_swarm(tmp_path, cs_mod)
    _assert_sentry_backscan_and_cli(tmp_path, capsys, cs_mod, tt_mod, swarm_tp)
