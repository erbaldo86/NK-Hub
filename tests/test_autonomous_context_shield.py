# -*- coding: utf-8 -*-
"""
Suite di test end-to-end Zero-Mock per Autonomous Context Shield 1.0.0-Generation.
Modulo: tests/test_autonomous_context_shield.py.
Copre R1..R12 su nk_acs_fastguard.py, nk_session_handoff.py, win32_2pc_engine.py e bootstrap.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import statistics
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
        is_cov_instrumented,
        load_nk_script_module,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        STAGING_SCRIPTS_DIR,
        WORKSPACE_ROOT,
        is_cov_instrumented,
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


@pytest.mark.fast
def test_acs_z1_z2_z3_zones_velocity_and_live_spawn(tmp_path: Path) -> None:
    """Verifica Z0 silenzioso e Z1 one-shot su token (160k) e step (120) in Pre/Post."""
    with pytest.MonkeyPatch.context() as mp:
        _isolate_tmp_dirs(tmp_path, mp)
        proj_z1 = tmp_path / "proj_z1"
        proj_z1.mkdir(parents=True)
        tp_z0 = tmp_path / "tp_z0.jsonl"
        _write_jsonl(tp_z0, [{"step_index": 1, "source": "MODEL", "input_tokens": 155_000}])
        rc, out_z0, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z0-silent", "projectRoot": str(proj_z1), "transcriptPath": str(tp_z0)}, mp)
        assert rc == 0 and out_z0 == {}

        tp_z1 = tmp_path / "tp_z1.jsonl"
        _write_jsonl(tp_z1, [{"step_index": 1, "source": "MODEL", "input_tokens": 130_000, "cache_read_tokens": 30_000}])
        pl_z1 = {"conversationId": "conv-z1-tok", "projectRoot": str(proj_z1), "transcriptPath": str(tp_z1)}
        rc, out_post_z1, raw_post_z1 = _run_fastguard_inproc("PostInvocation", pl_z1, mp)
        assert rc == 0 and out_post_z1 == {} and "/compact" not in raw_post_z1

        rc, out_pre_z1, raw_pre_z1 = _run_fastguard_inproc("PreInvocation", pl_z1, mp)
        assert rc == 0 and "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_pre_z1) and "/compact" not in raw_pre_z1
        rc, out_pre_z1_dup, _ = _run_fastguard_inproc("PreInvocation", pl_z1, mp)
        assert rc == 0 and out_pre_z1_dup == {}

        tp_z1_steps = tmp_path / "tp_z1_steps.jsonl"
        _write_jsonl(tp_z1_steps, [{"step_index": i, "source": "MODEL", "content": "ok"} for i in range(120)])
        rc, out_z1_steps, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z1-steps", "projectRoot": str(proj_z1), "transcriptPath": str(tp_z1_steps)}, mp)
        assert rc == 0 and "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_z1_steps)


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


@pytest.mark.fast
def test_acs_z3_velocity_jump_and_legacy_contract(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica Z2 150 step, Z3 Pre/Post (nativo/legacy), 180 step e velocity jump."""
    isolated_nk_ws_factory("z3_vel", apply_inproc=True)
    handoff_mod = load_nk_script_module("nk_session_handoff")

    proj_z2_s = tmp_path / "proj_z2_steps"
    _precreate_wal_hold(proj_z2_s)
    tp_z2_s = tmp_path / "tp_z2_steps.jsonl"
    _write_jsonl(tp_z2_s, [{"step_index": i, "source": "MODEL", "content": "s"} for i in range(150)])
    rc, _, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-z2-steps", "projectRoot": str(proj_z2_s), "transcriptPath": str(tp_z2_s)}, monkeypatch)
    assert rc == 0
    _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_z2_s), "--transcript", str(tp_z2_s), "--conversation-id", "conv-z2-steps", "--turn", "1"], monkeypatch)
    assert (proj_z2_s / "nk_tracking" / "handoff" / "session_handoff_latest.json").is_file()

    proj_z3 = tmp_path / "proj_z3"
    _precreate_wal_hold(proj_z3)
    tp_z3 = tmp_path / "tp_z3.jsonl"
    _write_jsonl(tp_z3, [{"step_index": 1, "source": "MODEL", "input_tokens": 205_000}])
    pl_z3 = {"conversationId": "conv-z3-tok", "projectRoot": str(proj_z3), "transcriptPath": str(tp_z3)}
    rc, out_pre, raw_pre = _run_fastguard_inproc("PreInvocation", pl_z3, monkeypatch)
    assert rc == 0 and "[ACS-Z3 CRITICO]" in _native_sys_msg(out_pre) and "/compact" not in raw_pre
    assert _run_fastguard_inproc("PreInvocation", pl_z3, monkeypatch)[1] == {}

    rc, out_post, raw_post = _run_fastguard_inproc("PostInvocation", pl_z3, monkeypatch)
    assert rc == 0 and _native_post_msg(out_post)[0] == "" and "[ACS-Z3]" in _native_post_msg(out_post)[1] and "/compact" not in raw_post
    assert _run_fastguard_inproc("PostInvocation", pl_z3, monkeypatch)[1] == {}

    pl_leg = {"conversationId": "conv-z3-legacy", "projectRoot": str(proj_z3), "transcriptPath": str(tp_z3)}
    _, out_leg_pre, _ = _run_fastguard_inproc("PreInvocation", pl_leg, monkeypatch, native_contract=False)
    assert "injectSteps" not in out_leg_pre and "[ACS-Z3 CRITICO]" in out_leg_pre.get("systemMessage", "")
    _, out_leg_post, _ = _run_fastguard_inproc("PostInvocation", pl_leg, monkeypatch, native_contract=False)
    assert "injectSteps" not in out_leg_post and "[ACS-Z3]" in out_leg_post.get("metadata", {}).get("user_markdown", "")

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


@pytest.mark.fast
def test_acs_tv03_session_start_and_spoof_subagent(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica TV-03: SessionStart step 0 ignorato e spoof USER_EXPLICIT bloccato."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("tv03_spoof", apply_inproc=True)
    proj = tmp_path / "proj_tv03_spoof"
    _precreate_wal_hold(proj)

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


@pytest.mark.fast
def test_acs_tv01_tv02_tv03_tv04_tv08_and_path_traversal(tmp_path: Path) -> None:
    """Verifica TV-01: file >550KB con riga >140KB CRLF, riga incompleta e shrink reset."""
    with pytest.MonkeyPatch.context() as mp:
        hooks_tmp = _isolate_tmp_dirs(tmp_path, mp)
        proj = tmp_path / "proj_tv"
        _precreate_wal_hold(proj)

        tp_big = tmp_path / "tp_big_crlf.jsonl"
        filler = [{"step_index": i, "source": "MODEL", "content": "B" * 4000} for i in range(115)]
        big_row = {"step_index": 116, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 125_000, "cache_read_tokens": 35_000, "content": "L" * 140_800}
        _write_jsonl(tp_big, [*filler, big_row], eol="\r\n")
        assert tp_big.stat().st_size > 550 * 1024

        pl_big = {"conversationId": "conv-tv01", "projectRoot": str(proj), "transcriptPath": str(tp_big)}
        rc, out_big, _ = _run_fastguard_inproc("PreInvocation", pl_big, mp)
        assert rc == 0 and "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_big)
        st_file = hooks_tmp / "nk_hooks" / "fastguard_conv-tv01.json"
        st_big = json.loads(st_file.read_text(encoding="utf-8"))
        assert st_big["byte_offset"] == tp_big.stat().st_size and st_big["last_actual_tokens"] == 160_000

        with open(tp_big, "ab") as f:
            f.write(b'{"step_index":117,"source":"MODEL","input_tokens":205000')
        rc, out_part, _ = _run_fastguard_inproc("PreInvocation", pl_big, mp)
        assert rc == 0 and out_part == {} and json.loads(st_file.read_text(encoding="utf-8"))["byte_offset"] == st_big["byte_offset"]

        with open(tp_big, "ab") as f:
            f.write(b"}\r\n")
        assert "[ACS-Z3 CRITICO]" in _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_big, mp)[1])

        _write_jsonl(tp_big, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "reset"}, {"step_index": 2, "source": "MODEL", "input_tokens": 10_000, "content": "ok"}])
        assert _run_fastguard_inproc("PreInvocation", pl_big, mp)[1] == {}
        st_shrink = json.loads(st_file.read_text(encoding="utf-8"))
        assert st_shrink["byte_offset"] == tp_big.stat().st_size and st_shrink["steps"] == 2 and st_shrink["last_actual_tokens"] == 10_000


@pytest.mark.fast
def test_acs_tv02_bool_tv03_subagent_and_tv08_rehydrate(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica TV-02 bool rejection, TV-03 subagent 5 righe/spoof e TV-04/TV-08 [RULE-REHYDRATE]."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("tv238", apply_inproc=True)
    proj = tmp_path / "proj_tv238"
    _precreate_wal_hold(proj)

    tp_bool = tmp_path / "tp_bool.jsonl"
    _write_jsonl(tp_bool, [
        {"step_index": 1, "source": "MODEL", "input_tokens": True, "cache_read_tokens": False},
        {"step_index": 2, "source": "MODEL", "actual_context_tokens": True},
        {"step_index": 3, "source": "MODEL", "usage": {"input_tokens": True, "cache_read_tokens": 190_000}},
    ])
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-bool", "projectRoot": str(proj), "transcriptPath": str(tp_bool)}, monkeypatch)[1] == {}
    assert json.loads((hooks_tmp / "nk_hooks" / "fastguard_conv-bool.json").read_text(encoding="utf-8"))["last_actual_tokens"] == 0

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

    tp_re = tmp_path / "tp_rehydrate.jsonl"
    _write_jsonl(tp_re, [
        {"step_index": 1, "source": "USER", "type": "CHECKPOINT", "compacted": True, "content": "<CONTEXT_SUMMARY>"},
        {"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "compacted": True, "content": "# Resuming"},
        {"step_index": 5, "source": "SYSTEM", "content": "[Message] sender=subagent <CONTEXT_SUMMARY>"},
        {"step_index": 6, "source": "MODEL", "input_tokens": 160_000},
    ])
    pl_re = {"conversationId": "conv-tv08", "projectRoot": str(proj), "transcriptPath": str(tp_re)}
    msg1 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_re, monkeypatch)[1])
    assert "[ACS-Z1 SOFT-FOLDING]" in msg1 and "[RULE-REHYDRATE]" not in msg1

    with open(tp_re, "ab") as f:
        f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint"}) + "\n").encode("utf-8"))
    msg2 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl_re, monkeypatch)[1])
    assert "[RULE-REHYDRATE]" in msg2 and "nk_tracking/active_context.md" in msg2
    assert _run_fastguard_inproc("PreInvocation", pl_re, monkeypatch)[1] == {}


@pytest.mark.fast
def test_acs_path_traversal_and_latency_benchmark(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica fallback path traversal e latenza mediana (< 50 ms senza cov, < 150 ms con cov)."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("trav_bench", apply_inproc=True)
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    proj = tmp_path / "proj_trav"
    proj.mkdir()
    tp_trav = tmp_path / "tp_trav.jsonl"
    _write_jsonl(tp_trav, [{"step_index": 1, "source": "MODEL", "input_tokens": 1000}])

    expected_default_id = f"default_{hashlib.sha256(os.path.realpath(str(proj)).lower().encode('utf-8')).hexdigest()[:10]}"
    for bad_conv in ("../escape", "..\\..\\evil", "a/b", ".", ".."):
        rc, out_trav, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": bad_conv, "projectRoot": str(proj), "transcriptPath": str(tp_trav)}, monkeypatch)
        assert rc == 0 and out_trav == {}
    assert (hooks_tmp / "nk_hooks" / f"fastguard_{expected_default_id}.json").is_file()

    latencies_ms: List[float] = []
    for _ in range(3):
        t0 = time.perf_counter()
        rc, _, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-bench", "projectRoot": str(proj), "transcriptPath": str(tp_trav)}, monkeypatch, native_contract=False)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert rc == 0
    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    max_ms = 600.0 if is_ci else (150.0 if is_cov_instrumented() else 50.0)
    assert fastguard_mod is not None and statistics.median(latencies_ms) < max_ms


@pytest.mark.fast
def test_handoff_dry_run_locks_checkpoint_l1022_and_templates(tmp_path: Path) -> None:
    """Verifica --dry-run, L1022 effective_root e record_fsm_checkpoint con rigetto bool."""
    handoff_mod = load_script_by_relpath("nk_session_handoff_acs", "scripts/nk_session_handoff.py")
    with pytest.MonkeyPatch.context() as mp:
        _isolate_tmp_dirs(tmp_path, mp)
        proj_dry = tmp_path / "proj_dry"
        proj_dry.mkdir()
        tp = tmp_path / "tp_dry.jsonl"
        _write_jsonl(tp, [{"step_index": 1, "source": "USER", "content": "dry test"}])

        rc_auto, out_auto = _run_handoff_inproc(
            handoff_mod, ["--auto-checkpoint", "--dry-run", "--project-root", str(proj_dry), "--transcript", str(tp), "--conversation-id", "conv-dry", "--milestone-id", "MS-DRY", "--turn", "2"], mp
        )
        dry_json = json.loads(out_auto)
        assert rc_auto == 0 and dry_json["status"] == "DRY_RUN" and dry_json["handoff_template"] == "Template 11" and not (proj_dry / "nk_tracking").exists()

        rc_cp, out_cp = _run_handoff_inproc(handoff_mod, ["--project-root", str(proj_dry), "--checkpoint-turn", "2", "--dry-run"], mp)
        assert rc_cp == 0 and json.loads(out_cp)["status"] == "DRY_RUN" and not (proj_dry / "nk_tracking").exists()

        proj_eff = tmp_path / "proj_eff_l1022"
        (proj_eff / ".staging" / "scripts").mkdir(parents=True)
        (proj_eff / ".staging" / "scripts" / "demo.py").write_text("x = 1\n", encoding="utf-8")
        rc_eff, _ = _run_handoff_inproc(
            handoff_mod, ["--project-root", str(proj_eff), "--transcript", str(tp), "--checkpoint-turn", "2", "--persist-brief-id", "IB-L1022", "--prompt-text", "Test L1022.", "--generate-prompt"], mp
        )
        assert rc_eff == 0
        eff_latest = json.loads((proj_eff / "nk_tracking" / "handoff" / "session_handoff_latest.json").read_text(encoding="utf-8"))
        assert Path(eff_latest["project_root"]).resolve() == proj_eff.resolve() and eff_latest["dirty_files"] is True
        assert (proj_eff / "nk_tracking" / "reports_and_briefs" / "IB-L1022.md").is_file()

        cp_rec = handoff_mod.record_fsm_checkpoint(turn=2, gate_status="PASS", milestone_id="MS-CP", root=proj_eff, conversation_id="conv-fsm-2")
        assert cp_rec["passed"] is True and len(cp_rec["staging_state_sha256"]) == 64
        for bad_turn in (True, False, 0, 6):
            with pytest.raises(ValueError):
                handoff_mod.record_fsm_checkpoint(turn=bad_turn, gate_status="PASS", root=proj_eff)
        with pytest.raises(ValueError):
            handoff_mod.select_auto_checkpoint_template(False, True)
        assert handoff_mod.select_auto_checkpoint_template(False, 0) == "Template 12"


@pytest.mark.fast
def test_handoff_templates_11_12_and_win32_mutex_busy(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica Template 11/12 lintato su --auto-checkpoint e SKIPPED_LOCK_BUSY su mutex Win32."""
    isolated_nk_ws_factory("ho_tpl", apply_inproc=True)
    handoff_mod = load_script_by_relpath("nk_session_handoff_acs", "scripts/nk_session_handoff.py")
    win32_mod = load_script_by_relpath("win32_2pc_engine_acs", "scripts/win32_2pc_engine.py")
    tt_mod = load_script_by_relpath("nk_transcript_tools_acs", "scripts/nk_transcript_tools.py")

    tp = tmp_path / "tp_tpl.jsonl"
    _write_jsonl(tp, [{"step_index": 1, "source": "USER", "content": "tpl test"}])
    proj_clean = tmp_path / "proj_clean_t12"
    proj_clean.mkdir()

    for turn, exp_tpl, exp_mode, exp_sb in (("5", "Template 12", "state-handoff", True), ("2", "Template 11", "auto", False)):
        rc, out = _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_clean), "--transcript", str(tp), "--turn", turn], monkeypatch)
        res = json.loads(out)
        assert rc == 0 and res["handoff_template"] == exp_tpl and res["metadata"]["standby_mode"] is exp_sb
        lint_r, lint_c = tt_mod.lint_prompt_text(Path(res["prompt_path"]).read_text(encoding="utf-8"), mode=exp_mode)
        assert lint_c == 0 and lint_r["passed"] is True

    proj_busy = tmp_path / "proj_busy"
    proj_busy.mkdir()
    with win32_mod.Win32NamedMutex(f"Global\\NK_HandoffWorker_{_repo_hash16(proj_busy)}", timeout_ms=1000, is_path=False):
        rc_w, out_w = _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_busy), "--transcript", str(tp), "--turn", "2"], monkeypatch, in_thread=True)
        assert rc_w == 0 and json.loads(out_w)["status"] == "SKIPPED_LOCK_BUSY"

    batch_name = win32_mod.get_repo_batch_mutex_name(proj_busy.resolve())
    orig_mtx = handoff_mod.Win32NamedMutex
    monkeypatch.setattr(handoff_mod, "Win32NamedMutex", lambda name, timeout_ms=1000, is_path=True: orig_mtx(name, timeout_ms=min(int(timeout_ms), 20), is_path=is_path))
    with orig_mtx(batch_name, timeout_ms=1000, is_path=False):
        rc_b, out_b = _run_handoff_inproc(handoff_mod, ["--auto-checkpoint", "--project-root", str(proj_busy), "--transcript", str(tp), "--turn", "2"], monkeypatch, in_thread=True)
    assert rc_b == 0 and json.loads(out_b)["status"] == "SKIPPED_LOCK_BUSY"


@pytest.mark.fast
def test_win32_2pc_global_local_fallback_and_replace_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica fallback Global\\ -> Local\\ su ERROR_ACCESS_DENIED e _replace_with_retry su WinError (5,32,33)."""
    win32_mod = load_script_by_relpath("win32_2pc_engine_acs", "scripts/win32_2pc_engine.py")
    if sys.platform == "win32" and win32_mod._kernel32 is not None:
        real_k32 = win32_mod._kernel32
        seen_names: List[str] = []

        class _GlobalDenyKernel32:
            def __getattr__(self, item: str) -> Any:
                return getattr(real_k32, item)

            def CreateMutexW(self, sec: Any, initial: Any, name: str) -> Any:
                seen_names.append(name)
                if name.startswith("Global\\"):
                    ctypes.set_last_error(5)
                    return None
                return real_k32.CreateMutexW(sec, initial, name)

        monkeypatch.setattr(win32_mod, "_kernel32", _GlobalDenyKernel32())
        probe_name, local_name = f"Global\\NK_FallbackTest_{os.getpid()}", f"Local\\NK_FallbackTest_{os.getpid()}"
        with win32_mod.Win32NamedMutex(probe_name, timeout_ms=1000, is_path=False) as mtx:
            assert mtx.acquired is True and seen_names == [probe_name, local_name]
            check_h = real_k32.OpenMutexW(0x00100000, False, local_name)
            assert check_h
            real_k32.CloseHandle(ctypes.c_void_p(check_h))

    orig_replace = os.replace
    for winerr_code in (5, 32, 33):
        src, dst = tmp_path / f"src_{winerr_code}.tmp", tmp_path / f"dst_{winerr_code}.txt"
        src.write_text(f"payload_{winerr_code}", encoding="utf-8")
        dst.write_text("old", encoding="utf-8")
        attempts = {"n": 0}

        def _transient_replace(s: Any, d: Any) -> None:
            attempts["n"] += 1
            if attempts["n"] <= 2:
                err = OSError("transient win32 sharing error")
                err.winerror = winerr_code
                raise err
            orig_replace(s, d)

        monkeypatch.setattr(os, "replace", _transient_replace)
        win32_mod._replace_with_retry(src, dst, retries=4, delay_sec=0.005)
        assert attempts["n"] == 3 and dst.read_text(encoding="utf-8") == f"payload_{winerr_code}"
        monkeypatch.undo()


@pytest.mark.fast
def test_bootstrap_warn_delta_compliance_warn_and_rsi_cove_missing_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica bootstrap WARN con byte_delta > 0 sotto 40 step senza cache stale."""
    boot_mod = load_script_by_relpath("nk_session_bootstrap_acs", "scripts/nk_session_bootstrap.py")
    _isolate_tmp_dirs(tmp_path, monkeypatch)
    monkeypatch.setenv("NK_MODEL_PROFILE", "carbon")

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
    assert r1["status"] == "PASS" and r1["checks"]["context_sentry"]["status"] == "GREEN" and r1["checks"]["context_sentry"]["step_count"] == 5

    with open(tp_boot, "ab") as f:
        f.write((json.dumps({"step_index": 5, "source": "MODEL", "input_tokens": 160_000, "content": "warn"}) + "\n").encode("utf-8"))
    buf_b2 = io.StringIO()
    with monkeypatch.context() as mp2:
        boot_mod.NKSessionBootstrap._MEMORY_CACHE.pop(str(proj_boot.resolve()), None)
        mp2.setattr(sys, "stdout", buf_b2)
        mp2.setattr(sys, "stderr", io.StringIO())
        assert int(boot_mod.main(boot_args) or 0) == 0
    r2 = json.loads(buf_b2.getvalue())
    assert r2["status"] == "PASS" and r2["checks"]["context_sentry"]["status"] == "WARN" and r2["checks"]["context_sentry"]["step_count"] == 6


@pytest.mark.fast
def test_compliance_warn_penalties_and_rsi_cove_missing_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica penalita compliance WARN/YELLOW/RED e verify_cli_flags_cove script mancante."""
    comp_mod = load_script_by_relpath("nk_compliance_checker_acs", "scripts/nk_compliance_checker.py")
    rsi_mod = load_script_by_relpath("rsi_convergence_acs", "scripts/rsi_convergence_engine.py")
    monkeypatch.setenv("NK_MODEL_PROFILE", "carbon")
    checker = comp_mod.NKComplianceChecker(workspace_root=tmp_path)

    tp_warn = tmp_path / "tp_comp_warn.jsonl"
    _write_jsonl(tp_warn, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Audit"}, {"step_index": 2, "source": "MODEL", "input_tokens": 160_000, "content": "ok"}])
    res_cw = checker.audit_transcript(tp_warn)
    assert res_cw["warn_advisory"] is True and res_cw["metrics"]["context_sentry_status"] == "WARN" and res_cw["scores"]["procedural_score"] == 100 and res_cw["penalties"] == []

    tp_yel = tmp_path / "tp_comp_yellow.jsonl"
    _write_jsonl(tp_yel, [{"step_index": i, "source": "MODEL", "input_tokens": 120_000, "content": "y"} for i in range(160)])
    res_cy = checker.audit_transcript(tp_yel)
    assert res_cy["warn_advisory"] is False and res_cy["metrics"]["context_sentry_status"] == "YELLOW" and res_cy["scores"]["procedural_score"] == 85

    tp_red = tmp_path / "tp_comp_red.jsonl"
    _write_jsonl(tp_red, [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Audit"}, {"step_index": 2, "source": "MODEL", "input_tokens": 210_000, "content": "red"}])
    res_cr = checker.audit_transcript(tp_red)
    assert res_cr["warn_advisory"] is False and res_cr["metrics"]["context_sentry_status"] == "RED" and res_cr["scores"]["procedural_score"] == 65

    cove_proj = tmp_path / "proj_cove"
    (cove_proj / ".agents" / "skills" / "GhostSkill").mkdir(parents=True)
    (cove_proj / ".agents" / "skills" / "GhostSkill" / "SKILL.md").write_text("# Ghost\nEsegui `python scripts/missing_ghost_script.py --ghost-flag`.\n", encoding="utf-8")
    cove_res = rsi_mod.RSIConvergenceEngine(workspace_root=cove_proj).verify_cli_flags_cove(cove_proj)
    assert cove_res["passed"] is False and any("missing_ghost_script.py" in inv for inv in cove_res["invalid_flags"])


@pytest.mark.fast
def test_fastguard_save_state_atomic_errors_and_cli_stderr_contract(tmp_path: Path) -> None:
    """Verifica _save_state_atomic (False, reason) su parent invalido e scrittura atomica."""
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    assert Path(fastguard_mod.__file__).resolve() == _resolve_script("nk_acs_fastguard.py").resolve()

    assert fastguard_mod._save_state_atomic(None, {"version": 1}) == (False, "missing_state_path")
    ok_miss, reason_miss = fastguard_mod._save_state_atomic(str(tmp_path / "missing_parent" / "fastguard_state.json"), {"version": 1})
    assert ok_miss is False and isinstance(reason_miss, str) and reason_miss.startswith("io_error:")

    blocked_parent = tmp_path / "blocked_parent_file"
    blocked_parent.write_text("not_a_dir", encoding="utf-8")
    ok_blk, reason_blk = fastguard_mod._save_state_atomic(str(blocked_parent / "state.json"), {"version": 1})
    assert ok_blk is False and isinstance(reason_blk, str) and reason_blk.startswith("io_error:")

    good_target = tmp_path / "good_dir" / "fastguard_state.json"
    good_target.parent.mkdir(parents=True)
    assert fastguard_mod._save_state_atomic(str(good_target), {"version": 1, "steps": 3}) == (True, None)
    assert json.loads(good_target.read_text(encoding="utf-8")) == {"version": 1, "steps": 3}


@pytest.mark.integration
def test_fastguard_cli_stderr_and_nonblocking_stdin(
    tmp_path: Path, isolated_nk_ws_factory: Any
) -> None:
    """Verifica diagnostica stderr CLI su errori I/O e stdin non bloccante (EOF, DEVNULL, PIPE)."""
    fg_script = _resolve_script("nk_acs_fastguard.py").resolve()
    proj = tmp_path / "proj_cli_err"
    proj.mkdir()
    tp_low = tmp_path / "tp_cli_low.jsonl"
    _write_jsonl(tp_low, [{"step_index": 1, "source": "MODEL", "input_tokens": 1000}])

    blocked_file = tmp_path / "blocked_dir"
    blocked_file.write_text("x", encoding="utf-8")
    env_bad_dir, _, _ = isolated_nk_ws_factory("cli_bad_dir", extra={"NK_HOOKS_TEMP_DIR": str(blocked_file)})
    cmd_cli = [sys.executable, "-S", "-B", "-u", str(fg_script), "--event", "PreInvocation"]
    pl_dir = json.dumps({"conversationId": "conv-cli-bad-dir", "projectRoot": str(proj), "transcriptPath": str(tp_low)}, ensure_ascii=True)
    proc_dir = subprocess.run(cmd_cli, input=pl_dir, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env_bad_dir, timeout=15, shell=False)
    assert proc_dir.returncode == 0 and json.loads(proc_dir.stdout.strip()) == {} and "[ACS-FASTGUARD WARN]" in proc_dir.stderr

    env_save_err, hooks_err, _ = isolated_nk_ws_factory("cli_save_err")
    (hooks_err / "nk_hooks" / "fastguard_conv-cli-save-err.json").mkdir(parents=True)
    pl_save = json.dumps({"conversationId": "conv-cli-save-err", "projectRoot": str(proj), "transcriptPath": str(tp_low)}, ensure_ascii=True)
    proc_save = subprocess.run(cmd_cli, input=pl_save, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env_save_err, timeout=15, shell=False)
    assert proc_save.returncode == 0 and json.loads(proc_save.stdout.strip()) == {} and "[ACS-FASTGUARD WARN] state_save_failed" in proc_save.stderr

    cmd_no_stdin = [*cmd_cli, "--project-root", str(proj)]
    proc_eof = subprocess.run(cmd_no_stdin, input="", text=True, encoding="utf-8", capture_output=True, env=env_save_err, timeout=5, shell=False)
    proc_null = subprocess.run(cmd_no_stdin, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", capture_output=True, env=env_save_err, timeout=5, shell=False)
    assert proc_eof.returncode == 0 and json.loads(proc_eof.stdout.strip()) == {}
    assert proc_null.returncode == 0 and json.loads(proc_null.stdout.strip()) == {}

    proc_pipe = subprocess.Popen(cmd_no_stdin, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env_save_err, shell=False)
    try:
        rc_pipe = proc_pipe.wait(timeout=3)
        out_pipe = proc_pipe.stdout.read() if proc_pipe.stdout is not None else ""
        assert rc_pipe == 0 and json.loads(out_pipe.strip()) == {}
    finally:
        for stream in (proc_pipe.stdin, proc_pipe.stdout, proc_pipe.stderr):
            if stream is not None:
                stream.close()


@pytest.mark.fast
def test_cold_backscan_compaction_resets_stale_state_and_preserves_rehydrate_idempotency(
    tmp_path: Path,
) -> None:
    """Verifica reset stato stantio in _cold_backscan_64kb su Caso A (tail) e Caso B (post-compaction)."""
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    tp_big = tmp_path / "tp_cold_comp.jsonl"
    filler = [{"step_index": i, "source": "MODEL", "content": "F" * 4000} for i in range(135)]
    _write_jsonl(tp_big, [*filler, {"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction"}])
    cp1_end = tp_big.stat().st_size
    with open(tp_big, "ab") as f:
        f.write((json.dumps({"step_index": 136, "source": "MODEL", "input_tokens": 175_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}) + "\n").encode("utf-8"))
    cp2_end = tp_big.stat().st_size

    stale_base = {"version": 1, "byte_offset": 0, "steps": 140, "fallback_steps": 99, "last_actual_tokens": 175_000, "prev_actual_tokens": 175_000, "epoch_baseline_tokens": 120_000, "compaction_epoch": 1, "checkpoint_byte_offset": cp1_end, "reanchor_emitted_offset": cp1_end, "z1_epoch": 1, "z3_pre_epoch": 1, "z3_post_epoch": 1, "z2_last_spawn_ts": time.time(), "z2_last_spawn_epoch": 1}
    stale_a = dict(stale_base)
    fastguard_mod._cold_backscan_64kb(str(tp_big), cp2_end, stale_a)
    assert stale_a["compaction_epoch"] == 2 and stale_a["checkpoint_byte_offset"] == cp2_end and stale_a["steps"] == 0 and stale_a["last_actual_tokens"] == 0 and stale_a["z1_epoch"] == -1 and stale_a["reanchor_emitted_offset"] == cp1_end

    with open(tp_big, "ab") as f:
        f.write((json.dumps({"step_index": 137, "source": "MODEL", "input_tokens": 18_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 138, "source": "MODEL", "input_tokens": 162_000}) + "\n").encode("utf-8"))
    stale_b = dict(stale_base)
    fastguard_mod._cold_backscan_64kb(str(tp_big), tp_big.stat().st_size, stale_b)
    assert stale_b["compaction_epoch"] == 2 and stale_b["steps"] == 2 and stale_b["last_actual_tokens"] == 162_000 and stale_b["epoch_baseline_tokens"] == 18_000 and stale_b["z3_post_epoch"] == -1


@pytest.mark.fast
def test_cold_backscan_rehydrate_idempotency_preinvocation(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica Caso C: idempotenza [RULE-REHYDRATE] e gate quando comp_offset == prev_cp."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("cold_idem", apply_inproc=True)
    proj = tmp_path / "proj_cold_idem"
    _precreate_wal_hold(proj)
    tp_big = tmp_path / "tp_cold_idem.jsonl"
    filler = [{"step_index": i, "source": "MODEL", "content": "F" * 4000} for i in range(135)]
    _write_jsonl(tp_big, [*filler, {"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}])
    cp_end = tp_big.stat().st_size
    with open(tp_big, "ab") as f:
        f.write((json.dumps({"step_index": 137, "source": "MODEL", "input_tokens": 18_000}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 138, "source": "MODEL", "input_tokens": 162_000}) + "\n").encode("utf-8"))

    pl = {"conversationId": "conv-cold-idem", "projectRoot": str(proj), "transcriptPath": str(tp_big)}
    rc1, out1, _ = _run_fastguard_inproc("PreInvocation", pl, monkeypatch)
    assert rc1 == 0 and "[RULE-REHYDRATE]" in _native_sys_msg(out1) and "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out1)

    st_path = hooks_tmp / "nk_hooks" / "fastguard_conv-cold-idem.json"
    persisted = json.loads(st_path.read_text(encoding="utf-8"))
    assert persisted["checkpoint_byte_offset"] == cp_end and persisted["reanchor_emitted_offset"] == cp_end
    persisted.update({"byte_offset": 0, "z3_pre_epoch": 1, "z3_post_epoch": 1, "z2_last_spawn_epoch": 1})
    st_path.write_text(json.dumps(persisted, ensure_ascii=True), encoding="utf-8")

    rc2, out2, _ = _run_fastguard_inproc("PreInvocation", pl, monkeypatch)
    persisted_after = json.loads(st_path.read_text(encoding="utf-8"))
    assert rc2 == 0 and out2 == {} and persisted_after["compaction_epoch"] == 1 and persisted_after["z3_pre_epoch"] == 1


@pytest.mark.fast
def test_advance_cursor_back_to_back_compactions_reset_epoch_gates(tmp_path: Path) -> None:
    """Verifica reset gate epoch e contatori in _advance_cursor attraverso compaction consecutive."""
    fastguard_mod = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")
    with pytest.MonkeyPatch.context() as mp:
        hooks_tmp = _isolate_tmp_dirs(tmp_path, mp)
        proj = tmp_path / "proj_b2b"
        _precreate_wal_hold(proj)
        tp = tmp_path / "tp_b2b.jsonl"
        _write_jsonl(tp, [{"step_index": 1, "source": "MODEL", "input_tokens": 205_000}])
        pl = {"conversationId": "conv-b2b-gates", "projectRoot": str(proj), "transcriptPath": str(tp)}

        assert "[ACS-Z3 CRITICO]" in _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl, mp)[1])
        assert "[ACS-Z3]" in _native_post_msg(_run_fastguard_inproc("PostInvocation", pl, mp)[1])[1]

        with open(tp, "ab") as f:
            f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}) + "\n").encode("utf-8"))
            f.write((json.dumps({"step_index": 2, "source": "MODEL", "input_tokens": 205_000}) + "\n").encode("utf-8"))

        msg_p1 = _native_sys_msg(_run_fastguard_inproc("PreInvocation", pl, mp)[1])
        assert "[RULE-REHYDRATE]" in msg_p1 and "[ACS-Z3 CRITICO]" in msg_p1
        assert "[ACS-Z3]" in _native_post_msg(_run_fastguard_inproc("PostInvocation", pl, mp)[1])[1]

        st1 = json.loads((hooks_tmp / "nk_hooks" / "fastguard_conv-b2b-gates.json").read_text(encoding="utf-8"))
        assert st1["compaction_epoch"] == 1 and st1["z1_epoch"] == 1 and st1["z3_pre_epoch"] == 1 and st1["z3_post_epoch"] == 1

        st1["fallback_steps"] = 55
        st1["z2_last_spawn_epoch"] = 1
        with open(tp, "ab") as f:
            f.write((json.dumps({"source": "SYSTEM", "compacted": True}) + "\n").encode("utf-8"))
            f.write((json.dumps({"step_index": 3, "source": "MODEL", "input_tokens": 45_000}) + "\n").encode("utf-8"))
            f.write((json.dumps({"source": "SYSTEM", "type": "CHECKPOINT"}) + "\n").encode("utf-8"))
        fastguard_mod._advance_cursor(str(tp), st1)
        assert st1["compaction_epoch"] == 3 and st1["steps"] == 0 and st1["fallback_steps"] == 0 and st1["last_actual_tokens"] == 0 and st1["z1_epoch"] == -1 and st1["z2_last_spawn_ts"] == 0.0


@pytest.mark.fast
def test_fastguard_fallback_steps_args_corrupt_state_and_usage_keys(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chiude i branch di nk_acs_fastguard su CLI args, JSON corrotto, usage.prompt_tokens e fallback steps."""
    _, hooks_tmp, _ = isolated_nk_ws_factory("fg_extra", apply_inproc=True)
    fg = load_script_by_relpath("nk_acs_fastguard_acs", "scripts/nk_acs_fastguard.py")

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
    assert exists_b is True and rec_b is True

    proj = tmp_path / "proj_fb"
    _precreate_wal_hold(proj)
    # Fallback senza transcript fino a soglia Z1 step
    fb_state_p = hooks_tmp / "nk_hooks" / "fastguard_conv-fb-only.json"
    fb_seed = fg._default_state()
    fb_seed["fallback_steps"] = fg._Z1_STEPS - 1
    fb_state_p.write_text(json.dumps(fb_seed), encoding="utf-8")
    rc_fb, out_fb, _ = _run_fastguard_inproc(
        "PreInvocation", {"conversationId": "conv-fb-only", "projectRoot": str(proj)}, monkeypatch,
        extra_args=[f"--conversation-id=conv-fb-only", f"--project-root={proj}"],
    )
    assert rc_fb == 0 and "[ACS-Z1 SOFT-FOLDING]" in _native_sys_msg(out_fb)

    with monkeypatch.context() as mp_bad:
        mp_bad.setattr(sys, "stdin", io.StringIO("{bad_stdin_json"))
        mp_bad.setattr(sys, "stdout", io.StringIO())
        mp_bad.setattr(sys, "stderr", io.StringIO())
        assert fg.main(["--event", "PreInvocation"]) == 0


@pytest.mark.fast
def test_s2b_camelcase_rmw_anchored_compaction_l0_enforce_and_sentinel_state(
    tmp_path: Path, isolated_nk_ws_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica S2-B: hookEventName camelCase, RMW mutex, <CONTEXT_SUMMARY> ancorato, [RULE-00.6-ENFORCE] e sentinel_state_<cid>."""
    from concurrent.futures import ThreadPoolExecutor

    _, hooks_tmp, _ = isolated_nk_ws_factory("s2b_fg", apply_inproc=True)
    fg = load_script_by_relpath("nk_acs_fastguard_s2b", "scripts/nk_acs_fastguard.py")
    sent_mod = load_script_by_relpath("nk_active_runtime_sentinel_s2b", "scripts/nk_active_runtime_sentinel.py")

    proj = tmp_path / "proj_s2b"
    _precreate_wal_hold(proj)
    tp = tmp_path / "tp_s2b.jsonl"
    _write_jsonl(
        tp,
        [
            {"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "<USER_REQUEST>Implementa feature X</USER_REQUEST>"},
            {"step_index": 2, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "Nota su <CONTEXT_SUMMARY> nel mezzo della frase"},
            {"step_index": 3, "source": "MODEL", "input_tokens": 20_000},
        ],
    )

    # 1. hookEventName camelCase fallback + [RULE-00.6-ENFORCE] one-shot + no terminationBehavior
    in_payload = json.dumps({"hookEventName": "PreInvocation", "conversationId": "conv-s2b", "projectRoot": str(proj), "transcriptPath": str(tp)})
    buf_out = io.StringIO()
    with monkeypatch.context() as mp_cc:
        mp_cc.setattr(sys, "stdin", io.StringIO(in_payload))
        mp_cc.setattr(sys, "stdout", buf_out)
        mp_cc.setattr(sys, "stderr", io.StringIO())
        assert fg.main(["--native-contract"]) == 0
    out1 = json.loads(buf_out.getvalue())
    assert "terminationBehavior" not in out1
    assert "[RULE-00.6-ENFORCE]" in _native_sys_msg(out1)

    # One-shot per (prompt_sha, epoch): seconda chiamata stesso turno -> silenzioso
    _, out2, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-s2b", "projectRoot": str(proj), "transcriptPath": str(tp)}, monkeypatch)
    assert out2 == {}

    # Stato compaction: mid-line <CONTEXT_SUMMARY> non deve aver incrementato compaction_epoch
    st_file = hooks_tmp / "nk_hooks" / "fastguard_conv-s2b.json"
    assert json.loads(st_file.read_text(encoding="utf-8"))["compaction_epoch"] == 0

    # 2. Compaction ancorata a inizio riga + l0_gate_<cid>.json sopprime enforce
    prompt_sha = hashlib.sha256(b"Implementa feature Y").hexdigest()
    (hooks_tmp / "nk_hooks" / "l0_gate_conv-s2b.json").write_text(json.dumps({"turn_prompt_sha256": prompt_sha}), encoding="utf-8")
    with open(tp, "ab") as f:
        f.write((json.dumps({"step_index": 4, "source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>\nRiassunto"}) + "\n").encode("utf-8"))
        f.write((json.dumps({"step_index": 5, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Implementa feature Y"}) + "\n").encode("utf-8"))
    _, out3, _ = _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-s2b", "projectRoot": str(proj), "transcriptPath": str(tp)}, monkeypatch)
    msg3 = _native_sys_msg(out3)
    assert "[RULE-REHYDRATE]" in msg3 and "[RULE-00.6-ENFORCE]" not in msg3
    assert json.loads(st_file.read_text(encoding="utf-8"))["compaction_epoch"] == 1

    # 3. Subagent silent su L0 enforce
    tp_sub = tmp_path / "tp_sub_s2b.jsonl"
    _write_jsonl(
        tp_sub,
        [
            {"step_index": 0, "source": "SYSTEM", "content": "<subagent_reminder>leaf</subagent_reminder>"},
            {"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Implementa Z"},
        ],
    )
    assert _run_fastguard_inproc("PreInvocation", {"conversationId": "conv-sub-s2b", "projectRoot": str(proj), "transcriptPath": str(tp_sub)}, monkeypatch)[1] == {}

    # 4. Concurrent RMW fastguard_<cid>.json sotto mutex senza corruzione JSON
    def _rmw_worker(idx: int) -> int:
        return fg._persist_state_or_warn(str(st_file), {"steps": idx, "compaction_epoch": 1})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_rmw_worker, range(8)))
    assert isinstance(json.loads(st_file.read_text(encoding="utf-8"))["steps"], int)

    # 5. sentinel_state_<cid>.json + default "generation" in nk_active_runtime_sentinel
    import tempfile as _tf
    monkeypatch.setenv("NK_CONVERSATION_ID", "conv-sent-s2b")
    sent_out = io.StringIO()
    with monkeypatch.context() as mp_sent:
        mp_sent.setattr(sys, "argv", ["nk_active_runtime_sentinel.py", "--transcript", str(tp), "--conversation-id", "conv-sent-s2b", "--json"])
        mp_sent.setattr(sys, "stdout", sent_out)
        sent_mod.main()
    res_sent = json.loads(sent_out.getvalue())
    assert res_sent["profile"] == "generation"
    assert (Path(_tf.gettempdir()) / "nk_diagnostics" / "sentinel_state_conv-sent-s2b.json").is_file()
