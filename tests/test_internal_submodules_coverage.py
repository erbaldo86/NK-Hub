#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test in-process zero-dipendenze esterne per copertura rami interni NK_Hub."""

from __future__ import annotations

import ast
import concurrent.futures
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
from typing import Any, Dict, List

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main_captured as _call_main_captured,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main_captured as _call_main_captured,
        load_script_by_relpath,
    )


class _PlainCatalogRow:
    """Modello dati minimale privo di model_validate per test fallback Pydantic."""

    def __init__(self, name: str = "", score: int = 0) -> None:
        if not name or not isinstance(score, int) or score < 0:
            raise ValueError("record non valido")
        self.name = name
        self.score = score


class _DeterministicFcntl:
    """Wrapper deterministico compatibile con fcntl.flock su stato locale."""

    LOCK_EX = 2
    LOCK_NB = 4
    LOCK_UN = 8

    def __init__(self, fail_once_blocking: bool = False) -> None:
        self.held_fds: set[int] = set()
        self.unlock_calls: int = 0
        self.fail_once_blocking = fail_once_blocking
        self._failed_once = False

    def flock(self, fd: int, flags: int) -> None:
        if flags & self.LOCK_UN:
            self.held_fds.discard(fd)
            self.unlock_calls += 1
            return
        if self.fail_once_blocking and not self._failed_once:
            self._failed_once = True
            raise BlockingIOError("contenuto bloccato")
        if self.fail_once_blocking and (flags & self.LOCK_EX):
            raise BlockingIOError("contenuto bloccato permanente")
        self.held_fds.add(fd)


class _AsciiDummyStream(io.StringIO):
    """Stream in memoria con encoding ASCII per test riconfigurazione flussi."""

    encoding = "ascii"


class _DummyStdin:
    """Flusso stdin minimale deterministico senza attributo buffer."""

    def __init__(self, text: str = "", *, tty: bool = False, fail_read: bool = False) -> None:
        self._text = text
        self._tty = tty
        self._fail_read = fail_read

    def isatty(self) -> bool:
        return self._tty

    def read(self) -> str:
        if self._fail_read:
            raise OSError("stdin unreadable")
        return self._text


def _build_demo_pkg_tree(mini_repo: Path) -> tuple[Path, Path, Path]:
    """Crea un albero pacchetti minimale per i test reexports e facade_resolver."""
    prod_int = mini_repo / "scripts" / "_internal" / "demo_pkg"
    prod_sib = mini_repo / "scripts" / "_internal" / "other_pkg"
    stg_scripts = mini_repo / ".staging" / "scripts"
    for p_dir in (prod_int, prod_sib, stg_scripts / "_internal" / "stg_pkg", mini_repo / ".staging" / "misc"):
        p_dir.mkdir(parents=True)
    (prod_sib / "__init__.py").write_text("", encoding="utf-8")
    (prod_sib / "sib.py").write_text("class SibCls:\n    def ping(self) -> int:\n        return 1\n", encoding="utf-8")
    (prod_int / "sub_a.py").write_text(
        "class SubSvc:\n    class InnerCfg:\n        pass\n    def work(self) -> int:\n        return 2\n"
        "def sub_fn(x: int) -> int:\n    return x\nCONST_X = 7\n",
        encoding="utf-8",
    )
    (prod_int / "star_mod.py").write_text("def star_fn() -> str:\n    return 's'\n", encoding="utf-8")
    (prod_int / "cyc_a.py").write_text("from .cyc_b import cb_fn\ndef ca_fn() -> int:\n    return 1\n", encoding="utf-8")
    (prod_int / "cyc_b.py").write_text("from .cyc_a import *\ndef cb_fn() -> int:\n    return 2\n", encoding="utf-8")
    (prod_int / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (prod_int / "__init__.py").write_text(
        "from .sub_a import SubSvc, sub_fn as sub_alias\nfrom .star_mod import *\n"
        "from . import cyc_a\nfrom ..other_pkg.sib import SibCls\nfrom .broken import bad_sym\nfrom .nonexistent import miss_sym\n",
        encoding="utf-8",
    )
    (mini_repo / "scripts" / "top_util.py").write_text("def top_fn() -> int:\n    return 9\n", encoding="utf-8")
    return prod_int, stg_scripts, mini_repo


@pytest.mark.fast
def test_submodules_fastguard_ast_reexports_and_facade_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre argomenti CLI, fallback_steps, anchor >4KB e subagent di nk_acs_fastguard."""
    fg_mod = load_script_by_relpath("nk_acs_fastguard_cov", "scripts/nk_acs_fastguard.py")
    with pytest.raises(SystemExit) as help_ex:
        fg_mod._parse_fastguard_args(["--help"])
    assert help_ex.value.code == 0
    ev_eq, nat_eq, cid_eq, tp_eq, root_eq = fg_mod._parse_fastguard_args(
        ["--event=PreInvocation", "--conversation-id=conv_eq_1", "--transcript=t.jsonl", "--project-root=proj_dir", "--ignored-flag"]
    )
    assert nat_eq is False and ev_eq == "PreInvocation" and cid_eq == "conv_eq_1" and tp_eq == "t.jsonl" and root_eq == "proj_dir"
    ev_sp, nat_sp, cid_sp, tp_sp, root_sp = fg_mod._parse_fastguard_args(
        ["--event", "PostInvocation", "--native-contract", "--conversation-id", "conv_sp_2", "--transcript", "t2.jsonl", "--project-root", "proj_dir_2"]
    )
    assert nat_sp is True and ev_sp == "PostInvocation" and cid_sp == "conv_sp_2" and tp_sp == "t2.jsonl" and root_sp == "proj_dir_2"
    for bad_argv in (["--event=EventoInvalido"], ["--event", "EventoInvalido"]):
        with pytest.raises(SystemExit) as sys_ex:
            fg_mod._parse_fastguard_args(bad_argv)
        assert sys_ex.value.code == 2
    rc_help, out_help, _ = _call_main_captured(fg_mod, ["--help"])
    assert rc_help == 0 and "usage:" in out_help
    proj_ws = tmp_path / "fg_proj"
    res_dir = proj_ws / "nk_genome" / "configs"
    res_dir.mkdir(parents=True)
    thr_file = res_dir / "saturation_thresholds.json"
    thr_file.write_text("{corrupt", encoding="utf-8")
    assert fg_mod._load_acs_thresholds([proj_ws])["z1_steps"] >= 1
    thr_file.write_text(json.dumps({"autonomous_context_shield": {"z1_steps": 3, "fallback_steps": "not_a_dict"}}), encoding="utf-8")
    loaded_no_fb = fg_mod._load_acs_thresholds([proj_ws])
    assert loaded_no_fb["fallback_steps"]["z1"] >= 1
    conv_id = f"conv_fg_cov_{os.getpid()}"
    sess_anchor = proj_ws / "nk_tracking" / "sessions" / conv_id / "session_anchor.jsonl"
    sess_anchor.parent.mkdir(parents=True)
    sess_anchor.write_text((json.dumps({"note": "p" * 300}) + "\n") * 16 + "{corrupt\n\n" + json.dumps({"milestone": "MS-ANCHOR", "turn": 3}) + "\n", encoding="utf-8")
    assert fg_mod._read_anchor_meta([proj_ws], {}, conv_id=conv_id) == ("MS-ANCHOR", 3)
    sess_anchor.write_text(json.dumps({"turn": True}) + "\n", encoding="utf-8")
    assert fg_mod._read_anchor_meta([proj_ws], {}, conv_id=conv_id)[1] == 1


@pytest.mark.fast
def test_sub_fastguard_wal_subagent_and_z1_z3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_ws_factory: Any
) -> None:
    """Copre _has_active_wal, _is_subagent_transcript, fallback steps e Z1/Z3."""
    fg_mod = load_script_by_relpath("nk_acs_fastguard_cov", "scripts/nk_acs_fastguard.py")
    isolated_nk_ws_factory("fg_ws", apply_inproc=True)
    proj_ws = tmp_path / "fg_proj2"
    res_dir = proj_ws / "nk_genome" / "configs"
    res_dir.mkdir(parents=True)
    (res_dir / "saturation_thresholds.json").write_text(
        json.dumps({"autonomous_context_shield": {"z1_steps": 2, "z1_tokens": 400, "z2_steps": 4, "z2_tokens": 800, "z3_steps": 6, "z3_tokens": 1200, "epoch_baseline_tokens": 50, "fallback_steps": {"z1": 2, "z2": 4, "z3": 5}, "velocity_floor": 100, "velocity_step_floor": 1, "velocity_jump": 50, "cooldown_s": 0}}),
        encoding="utf-8",
    )
    wal_root = Path(tempfile.gettempdir()) / "nk_2pc_wal"
    wal_ws_dir = wal_root / hashlib.sha256(os.path.realpath(str(proj_ws)).encode("utf-8")).hexdigest()[:12]
    wal_ws_dir.mkdir(parents=True)
    old_wal = wal_root / "stale.wal"
    old_wal.write_text("old", encoding="utf-8")
    os.utime(old_wal, (time.time() - 600.0, time.time() - 600.0))
    assert fg_mod._has_active_wal([str(proj_ws)]) is False
    fresh_wal = wal_ws_dir / "active.wal"
    fresh_wal.write_text("active", encoding="utf-8")
    assert fg_mod._has_active_wal([str(proj_ws)]) is True
    assert fg_mod._is_reparse_or_symlink(tmp_path / "missing_sym") is False
    tp_sub = tmp_path / "sub_agent.jsonl"
    tp_sub.write_text("\n{bad\n[]\n" + json.dumps({"source": "SYSTEM", "content": "<subagent_reminder>"}) + "\n", encoding="utf-8")
    assert fg_mod._is_subagent_transcript(str(tp_sub)) is True
    assert _call_main_captured(fg_mod, ["--event", "PreInvocation", "--project-root", str(proj_ws)], stdin_text="{bad")[1].strip() == "{}"
    assert _call_main_captured(fg_mod, ["--project-root", str(proj_ws)], stdin_text=json.dumps({"hookEventName": "Unknown"}))[1].strip() == "{}"
    conv_id = f"conv_fg2_{os.getpid()}"
    for idx_fb in range(6):
        _, out_fb, _ = _call_main_captured(fg_mod, ["--event", "PreInvocation", "--conversation-id", conv_id, "--project-root", str(proj_ws)], stdin_text=json.dumps({"conversationId": conv_id}))
        if idx_fb == 4:
            assert "ACS-Z3" in out_fb
    home_dir = tmp_path / "fake_home"
    conv_tp = f"conv_tp2_{os.getpid()}"
    brain_tp = home_dir / ".gemini" / "antigravity" / "brain" / conv_tp / ".system_generated" / "logs" / "transcript.jsonl"
    brain_tp.parent.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    filler = json.dumps({"source": "MODEL", "content": "x" * 1600, "usage": {"input_tokens": 150}}) + "\n"
    brain_tp.write_text((filler * 48) + json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction"}) + "\n" + json.dumps({"source": "MODEL", "content": "ok", "usage": {"input_tokens": 200, "cache_read_tokens": 300}}) + "\n", encoding="utf-8")
    _, out_z1, _ = _call_main_captured(fg_mod, ["--event", "PreInvocation", "--project-root", str(proj_ws)], stdin_text=json.dumps({"conversationId": conv_tp, "toolName": "read_file"}))
    assert "ACS-Z1" in out_z1 and "RULE-REHYDRATE" in out_z1
    _, out_same, _ = _call_main_captured(fg_mod, ["--event", "PostInvocation", "--conversation-id", conv_tp, "--project-root", str(proj_ws)], stdin_text="{}")
    assert json.loads(out_same) == {}
    with open(brain_tp, "a", encoding="utf-8") as af:
        af.write(json.dumps({"source": "MODEL", "content": "delta", "usage": {"input_tokens": 1400}}) + "\n")
    _, out_z3, _ = _call_main_captured(fg_mod, ["--event", "PreInvocation", "--native-contract", "--conversation-id", conv_tp, "--project-root", str(proj_ws)], stdin_text=json.dumps({"prompt": "continua"}))
    assert "ACS-Z3" in out_z3 and "injectSteps" in out_z3
    _, out_z3p, _ = _call_main_captured(fg_mod, ["--event", "PostInvocation", "--native-contract", "--conversation-id", conv_tp, "--project-root", str(proj_ws)], stdin_text=json.dumps({"toolName": "read_file"}))
    assert "ACS-Z3" in out_z3p and "user_markdown" in out_z3p


@pytest.mark.fast
def test_sub_ast_reexports_and_facade_resolver(tmp_path: Path) -> None:
    """Copre validate_pydantic_catalog_records, reexports.py e facade_resolver.py."""
    agv_mod = load_script_by_relpath("ast_guard_validator_cov", "scripts/ast_guard_validator.py")
    map_mod = load_script_by_relpath("ast_repo_mapper_cov", "scripts/ast_repo_mapper.py")
    from _internal.ast_guard_validator import reexports as rx
    from _internal.ast_repo_mapper import facade_resolver as fr
    from pydantic import BaseModel

    class _PydRow(BaseModel):
        name: str
        count: int

    assert rx.validate_pydantic_catalog_records([{"name": "ok", "score": 5}], _PlainCatalogRow)["passed"] is True
    bad_plain = rx.validate_pydantic_catalog_records([{"name": "", "score": -1}], _PlainCatalogRow)
    assert bad_plain["passed"] is False and bad_plain["invalid_records"] == 1
    assert rx.validate_pydantic_catalog_records([{"name": "a", "count": 1}], _PydRow)["passed"] is True
    bad_pyd = rx.validate_pydantic_catalog_records([{"name": "a", "count": "bad"}], _PydRow)
    assert bad_pyd["passed"] is False and bad_pyd["invalid_records"] == 1
    assert rx._resolve_local_import_roots("") == ([], None)
    assert rx._resolve_local_import_roots("<stdin>") == ([], None)
    prod_int, stg_scripts, mini_repo = _build_demo_pkg_tree(tmp_path / "mini_repo")
    facade_src = (
        "from _internal.demo_pkg import SubSvc, SubSvc as SubAlias, sub_alias, star_fn, SibCls\n"
        "from _internal.demo_pkg.star_mod import *\nfrom scripts.top_util import top_fn\n"
        "if True:\n    from _internal.demo_pkg.cyc_a import ca_fn\nelse:\n    from _internal.demo_pkg.cyc_b import cb_fn\n"
    )
    staged_facade = stg_scripts / "my_facade.py"
    staged_facade.write_text(facade_src, encoding="utf-8")
    roots, cur_dir = rx._resolve_local_import_roots(str(staged_facade))
    assert any(r.name == "scripts" for r in roots) and cur_dir == staged_facade.parent
    roots_rel, _ = rx._resolve_local_import_roots("scripts/rel_only.py")
    assert len(roots_rel) >= 1 and any(r.name == "scripts" for r in roots_rel)
    assert len(list(rx._iter_top_level_import_from(ast.parse(facade_src)))) >= 3
    rel_too_high = ast.ImportFrom(module="up", names=[ast.alias(name="X")], level=8)
    assert rx._resolve_import_from_module_file(rel_too_high, roots, prod_int) is None
    cache: Dict[Path, Any] = {}
    col_once = rx._collect_resolved_module(staged_facade, roots, True, set(), cache)
    assert col_once.signatures and rx._collect_resolved_module(staged_facade, roots, True, set(), cache) is col_once
    assert not rx._collect_resolved_module(staged_facade, roots, True, {staged_facade.resolve()}, {}).signatures
    assert agv_mod.ASTGuardValidator.validate_code_edit(facade_src, facade_src, target_file=str(staged_facade)).is_valid is True
    prod_facade = mini_repo / "scripts" / "prod_facade.py"
    prod_facade.write_text(facade_src, encoding="utf-8")
    nodes_list, edges_list, calls_map, deps_meta = fr.extract_python_module_symbols(prod_facade, "scripts/prod_facade.py", facade_src, root_dir=mini_repo)
    assert "SubSvc" in {n.name for n in nodes_list} and isinstance(edges_list, list) and isinstance(calls_map, dict)
    assert fr.internal_deps_still_valid({"internal_deps": deps_meta}) is True
    assert fr.internal_deps_still_valid({"internal_deps": ["bad_entry"]}) is False
    dep_file = prod_int / "sub_a.py"
    assert fr.internal_deps_still_valid({"internal_deps": [(str(dep_file), dep_file.stat().st_mtime_ns, dep_file.stat().st_size + 1)]}) is False
    assert hasattr(map_mod, "RepoMapGenerator")


@pytest.mark.fast
def test_submodules_lazy_bridge_mutex_and_stop_evidence_sbfl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre lazy_bridge e fallback di rsi_convergence_engine."""
    from _internal.rsi_convergence_engine import lazy_bridge as lb

    orig_hooks = dict(lb._HOOKS)
    orig_fallback = dict(lb._FALLBACK_STATE)
    rsi_mod = load_script_by_relpath("rsi_convergence_engine_cov", "scripts/rsi_convergence_engine.py")
    try:
        with monkeypatch.context() as mp:
            mp.setattr(sys, "stdout", _AsciiDummyStream())
            mp.setattr(sys, "stderr", _AsciiDummyStream())
            for k in ("streams_reconfigured", "hsm_loaded", "agv_loaded"):
                mp.setitem(lb._FALLBACK_STATE, k, False)
            for k in ("hsm_cls", "agv_cls", "ste100_fn", "grounding_fn"):
                mp.setitem(lb._FALLBACK_STATE, k, None)
            assert lb.get_reconfigure_streams() is None
            assert lb.get_healing_snapshot_manager_cls().__name__ == "HealingSnapshotManager"
            assert lb.get_ast_guard_validator().__name__ == "ASTGuardValidator"
            assert callable(lb.get_ste100_validator()) and callable(lb.get_report_grounding_validator())
            mp.setattr(lb, "_HOOKS", {})
            for k in ("streams_reconfigured", "hsm_loaded", "agv_loaded"):
                mp.setitem(lb._FALLBACK_STATE, k, False)
            for k in ("ste100_fn", "grounding_fn"):
                mp.setitem(lb._FALLBACK_STATE, k, None)
            lb.fallback_reconfigure_streams()
            assert lb._FALLBACK_STATE["streams_reconfigured"] is True
            assert hasattr(lb.fallback_load_ntt_module(), "verify_ste100_compliance")
            assert lb.get_healing_snapshot_manager_cls().__name__ == "HealingSnapshotManager"
            assert lb.get_ast_guard_validator().__name__ == "ASTGuardValidator"
            mp.setitem(lb._FALLBACK_STATE, "agv_loaded", False)
            mp.setitem(lb._FALLBACK_STATE, "ste100_fn", None)
            mp.setitem(lb._FALLBACK_STATE, "grounding_fn", None)
            mp.setitem(sys.modules, "ast_guard_validator", None)
            mp.setitem(sys.modules, "scripts.ast_guard_validator", None)
            assert lb.get_ast_guard_validator() is None
            mp.setitem(sys.modules, "nk_transcript_tools", None)
            mp.setitem(sys.modules, "scripts.nk_transcript_tools", None)
            mp.setattr(lb, "_scripts_dir", tmp_path / "empty_scripts")
            mp.setattr(lb, "_workspace_root", tmp_path / "empty_ws")
            assert lb.fallback_load_ntt_module() is None and lb.get_report_grounding_validator() is None
            with pytest.raises(RuntimeError):
                lb.get_ste100_validator()
            mp.setitem(sys.modules, "healing_snapshot_rollback", None)
            mp.setitem(sys.modules, "scripts.healing_snapshot_rollback", None)
            mp.setattr(rsi_mod, "_LAZY_HEALING_SNAPSHOT_LOADED", False)
            mp.setattr(rsi_mod, "_LAZY_HEALING_SNAPSHOT_CLS", None)
            assert rsi_mod._get_healing_snapshot_manager_cls() is None
    finally:
        lb._HOOKS.clear()
        lb._HOOKS.update(orig_hooks)
        lb._FALLBACK_STATE.clear()
        lb._FALLBACK_STATE.update(orig_fallback)


@pytest.mark.fast
def test_sub_rsi_gt14_bundle_cli_and_vibe_check(tmp_path: Path) -> None:
    """Copre i 5 percorsi CLI di rsi_convergence_engine (--emit-gt14-bundle, --vibe-check, --strict-verify)."""
    rsi_mod = load_script_by_relpath("rsi_convergence_engine_cov", "scripts/rsi_convergence_engine.py")
    rc_can, out_can, _ = _call_main_captured(rsi_mod, ["--verify-canary"])
    assert rc_can in (0, 1) and "passed" in out_can
    gt_ws = tmp_path / "gt14_cli_ws"
    (gt_ws / ".agents" / "skills" / "S1").mkdir(parents=True)
    (gt_ws / ".agents" / "skills" / "S1" / "SKILL.md").write_text("---\nname: S1\ndesc: d\n---\nOk.\n", encoding="utf-8")
    (gt_ws / "nk_genome").mkdir(parents=True)
    (gt_ws / "scripts").mkdir(parents=True)
    (gt_ws / ".staging" / "scripts").mkdir(parents=True)
    (gt_ws / ".staging" / "scripts" / "s.py").write_text("X = 1\n", encoding="utf-8")
    b_out = tmp_path / "bundle_cli.json"
    rc_b1, out_b1, _ = _call_main_captured(rsi_mod, ["--root", str(gt_ws), "--emit-gt14-bundle", "--bundle-output", str(b_out)])
    assert rc_b1 in (0, 1) and "GT14-BUNDLE" in out_b1 and b_out.is_file()
    rc_b2, out_b2, _ = _call_main_captured(rsi_mod, ["--root", str(gt_ws), "--emit-gt14-bundle", "--bundle-output", str(b_out), "--json"])
    b_data = json.loads(out_b2)
    assert rc_b2 in (0, 1) and b_data["probes_executed"] == 5 and "bundle_path" in b_data
    rc_v1, out_v1, _ = _call_main_captured(rsi_mod, ["--root", str(gt_ws), "--vibe-check", "."])
    assert rc_v1 in (0, 1) and "RSI-VIBE-CHECK" in out_v1
    rc_v2, out_v2, _ = _call_main_captured(rsi_mod, ["--root", str(gt_ws), "--vibe-check", str(gt_ws), "--json"])
    assert rc_v2 in (0, 1) and "passed" in json.loads(out_v2)
    rc_sv, out_sv, _ = _call_main_captured(rsi_mod, ["--root", str(gt_ws), "--strict-verify"])
    assert rc_sv == 2 and "RSI" in out_sv


@pytest.mark.integration
def test_sub_win32_mutex_reentrant_and_posix_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre Win32NamedMutex reentrant, POSIX flock e errore rilascio da thread diverso."""
    w2pc_mod = load_script_by_relpath("win32_2pc_cov", "scripts/win32_2pc_engine.py")
    from _internal.win32_2pc_engine import constants as w2pc_consts

    lock_target = tmp_path / "mx_target.txt"
    lock_target.write_text("data", encoding="utf-8")
    mx_re = w2pc_mod.Win32NamedMutex(lock_target, timeout_ms=50)
    mx_re.release()
    mx_re.acquire()
    assert mx_re.acquired is True
    mx_re.acquire()
    mx_re.release()
    mx_re.release()
    with monkeypatch.context() as mp_p:
        mp_p.setattr(w2pc_consts, "_FACADE_MODULES", [w2pc_mod])
        mp_p.setattr(w2pc_consts, "_kernel32", None)
        mp_p.setattr(w2pc_mod, "_kernel32", None, raising=False)
        mp_p.setattr(w2pc_consts, "_fcntl", None)
        with pytest.raises(w2pc_consts.Win32LockError):
            w2pc_mod.Win32NamedMutex(lock_target, timeout_ms=20).acquire()
        fake_fcntl = _DeterministicFcntl()
        mp_p.setattr(w2pc_consts, "_fcntl", fake_fcntl)
        mx_px = w2pc_mod.Win32NamedMutex(lock_target, timeout_ms=40)
        mx_px.acquire()
        mx_px.acquire()
        wrong_rel_err: List[str] = []

        def _wrong_thread_release() -> None:
            try:
                mx_px.release()
            except w2pc_consts.Win32LockError:
                wrong_rel_err.append("wrong_tid")

        t_px = threading.Thread(target=_wrong_thread_release)
        t_px.start()
        t_px.join(timeout=2.0)
        assert wrong_rel_err == ["wrong_tid"]
        mx_px.release()
        mx_px.release()
        assert fake_fcntl.unlock_calls >= 1
        mp_p.setattr(w2pc_consts, "_fcntl", _DeterministicFcntl(fail_once_blocking=True))
        with pytest.raises(w2pc_consts.Win32LockTimeoutError):
            w2pc_mod.Win32NamedMutex(tmp_path / "mx_busy.txt", timeout_ms=15).acquire()


@pytest.mark.fast
def test_sub_stop_evidence_and_gt14_bundle_internals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_ws_factory: Any
) -> None:
    """Copre stop_evidence, gt14_bundle, active_runtime_sentinel, context_sentry e sbfl_engine."""
    load_script_by_relpath("nk_hook_gate_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import stop_evidence as se
    from _internal.rsi_convergence_engine import gt14_bundle as gb, lazy_bridge as lb_se

    assert se._stop_is_verified_compaction({"source": "USER", "content": "<CONTEXT_SUMMARY>"}) is False
    assert se._stop_is_verified_compaction({"source": "SYSTEM_SDK", "content": "<CONTEXT_SUMMARY>"}) is False
    assert se._stop_is_verified_compaction({"source": "SYSTEM", "type": "CHECKPOINT"}) is True
    assert se._stop_is_verified_compaction({"content": "# Resuming from a compaction"}) is True
    assert se._stop_extract_tokens({"input_tokens": True, "cache_read_tokens": 10}) is None
    assert se._stop_extract_tokens({"usage": {"actual_context_tokens": 420}}) == 420
    assert se._stop_extract_tokens({"context_tokens": 333}) == 333
    _, hooks_dir, _ = isolated_nk_ws_factory("stop_ev", apply_inproc=True)
    assert se._stop_read_tokens_and_epoch(tmp_path / "missing.jsonl", "c_miss") == (0, 0, 0)
    tp_se = tmp_path / "se_tp.jsonl"
    pad_se = json.dumps({"source": "MODEL", "content": "z" * 1200, "usage": {"input_tokens": 100}}) + "\n"
    tp_se.write_text((pad_se * 480) + json.dumps({"source": "MODEL", "usage": {"input_tokens": 500}}) + "\n", encoding="utf-8")
    assert se._stop_read_tokens_and_epoch(tp_se, "c_big")[0] == 500
    nk_hooks_sub = hooks_dir / "nk_hooks"
    nk_hooks_sub.mkdir(parents=True, exist_ok=True)
    fg_state_p = nk_hooks_sub / "fastguard_c_big.json"
    prev_sz = tp_se.stat().st_size
    with open(tp_se, "a", encoding="utf-8") as af_se:
        af_se.write("{bad\n[]\n" + json.dumps({"source": "SYSTEM", "type": "CHECKPOINT"}) + "\n" + json.dumps({"source": "MODEL", "usage": {"input_tokens": 160000}}) + "\n")
    fg_state_p.write_text(json.dumps({"byte_offset": prev_sz, "last_actual_tokens": 777, "steps": 9, "compaction_epoch": 2}), encoding="utf-8")
    assert se._stop_read_tokens_and_epoch(tp_se, "c_big") == (160000, 1, 3)
    se_ws = tmp_path / "se_ws"
    (se_ws / ".wal").mkdir(parents=True)
    assert se._stop_is_batch_mutex_or_wal_busy([se_ws]) is False
    (se_ws / ".wal" / "busy.wal").write_text("b", encoding="utf-8")
    assert se._stop_is_batch_mutex_or_wal_busy([se_ws]) is True
    (nk_hooks_sub / "stop_ckpt_cid_stop.json").write_text(json.dumps({"epoch": 3}), encoding="utf-8")
    se._maybe_spawn_stop_idle_checkpoint("cid_stop", se_ws, tp_se, {})
    se._maybe_spawn_stop_idle_checkpoint("default_x", se_ws, None, {})
    orig_hooks_se = dict(lb_se._HOOKS)
    rsi_mod = load_script_by_relpath("rsi_convergence_engine_cov", "scripts/rsi_convergence_engine.py")
    try:
        gt_ws = tmp_path / "gt_bundle_ws"
        (gt_ws / ".staging" / "scripts").mkdir(parents=True)
        (gt_ws / ".staging" / "scripts" / "bad_s.py").write_text("X = eval('1 + 1')\n", encoding="utf-8")
        with pytest.raises(ModuleNotFoundError):
            gb._load_probe_module(gt_ws, "mod_assente_xyz")
        b_res = gb.emit_gt14_bundle_impl(rsi_mod.RSIConvergenceEngine(workspace_root=gt_ws), workspace_root=gt_ws, with_dast=True, strict_verify=False, output_path=tmp_path / "gt_out.json")
        assert (tmp_path / "gt_out.json").is_file() and b_res["probes_executed"] == 6
    finally:
        lb_se._HOOKS.clear()
        lb_se._HOOKS.update(orig_hooks_se)


@pytest.mark.fast
def test_sub_sentinel_sentry_and_sbfl_unit_edges(
    tmp_path: Path, isolated_nk_ws_factory: Any
) -> None:
    """Copre active_runtime_sentinel YAML/tokens, context_sentry e sbfl_engine."""
    isolated_nk_ws_factory("sent_ev", apply_inproc=True)
    ars_mod = load_script_by_relpath("nk_active_runtime_sentinel_cov", "scripts/nk_active_runtime_sentinel.py")
    assert ars_mod._safe_pos_int("ok", 7) == 7 and ars_mod._safe_pos_int(12, 7) == 12
    json_cfg = tmp_path / "sat_thresh.json"
    json_cfg.write_text('{"profiles": {"carbon": {}}}', encoding="utf-8")
    assert "carbon" in ars_mod.load_saturation_thresholds(thresholds_path=json_cfg)["profiles"]
    assert ars_mod._safe_pos_int(True, 7) == 7 and ars_mod._get_step_thresholds("argon")[0] >= 100
    assert ars_mod._extract_actual_tokens_from_record({"usage": {"prompt_tokens": 55, "usage": {"promptTokenCount": 9}}}) == 55
    red_tp = tmp_path / "red_tp.jsonl"
    red_tp.write_text("\n".join(json.dumps({"step": i, "content": "x"}) for i in range(110)) + "\n", encoding="utf-8")
    rc_ars, out_ars, _ = _call_main_captured(ars_mod, ["--transcript", str(red_tp), "--profile", "standard", "--check", "--json"])
    assert rc_ars == 1 and json.loads(out_ars)["state"] == "RED"
    cs_mod = load_script_by_relpath("nk_context_sentry_cov", "scripts/nk_context_sentry.py")
    assert cs_mod._contains_compaction_marker("\\u003cCONTEXT_SUMMARY>", {"source": "SYSTEM", "content": "<CONTEXT_SUMMARY>"}) is True
    assert cs_mod._contains_compaction_marker("x", {"source": "SYSTEM", "content": "[Message] sender=a"}) is False
    assert cs_mod.NKContextSentry.is_background_task_message({"sender": "task-1"}, "ok") is True
    assert cs_mod.NKContextSentry.is_background_task_message({}, "Job finished with result") is True
    assert cs_mod.NKContextSentry(workspace_root=tmp_path).inspect(tmp_path / "no_tp.jsonl")["status"] == "ERROR"
    assert _call_main_captured(cs_mod, ["--transcript", str(tmp_path / "no_tp.jsonl"), "--verbose"])[0] == 1
    sbfl_mod = load_script_by_relpath("sbfl_engine_cov", "scripts/sbfl_engine.py")
    assert sbfl_mod.estimate_token_count("") == 0 and sbfl_mod.estimate_token_count("def f(): return 1") >= 4
    conflict_active = sbfl_mod.is_monitoring_conflict_active()
    ok_mon, lines_mon = sbfl_mod.collect_statements_with_monitoring(lambda: 1 + 1)
    assert ok_mon is (not conflict_active) and (not ok_mon or len(lines_mon) >= 0)


@pytest.mark.fast
def test_submodules_sast_json_io_and_handoff_cursor_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre sast_scanner (hub/non-hub/TAS audit) e nk_hook_gate.json_io in-process."""
    from _internal.rsi_convergence_engine import sast_scanner as ss
    from _internal.nk_hook_gate import json_io as jio

    stub_engine = SimpleNamespace(_load_staging_deleted_set=lambda _r: {"deleted_root.py", "scripts/deleted_mod.py", "nk_tracking/reports_and_briefs/tas_certification_report_del.md"})
    hub_root = tmp_path / "fake_hub"
    for d in ("scripts", ".staging/scripts", ".staging/nk_tracking/reports_and_briefs", "nk_tracking/reports_and_briefs"):
        (hub_root / d).mkdir(parents=True)
    (hub_root / "root_note.md").write_text("ok \ufffd mojibake", encoding="utf-8")
    (hub_root / "deleted_root.py").write_text("X = 1\n", encoding="utf-8")
    (hub_root / "scripts" / "deleted_mod.py").write_text("X = 2\n", encoding="utf-8")
    (hub_root / "scripts" / "bad.json").write_text("{broken_json", encoding="utf-8")
    (hub_root / ".staging" / "scripts" / "unsafe.py").write_text("import subprocess\nsubprocess.Popen('dir', shell=True)\n", encoding="utf-8")
    (hub_root / "nk_tracking" / "reports_and_briefs" / "tas_certification_report_live.md").write_text("# Report\nVedi `scripts/nonexistent_fake_xyz.py`.\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(ss, "_workspace_root", hub_root)
        res_hub = ss.scan_sast_and_mojibake_impl(stub_engine, hub_root)
        assert res_hub["passed"] is False and res_hub["sast_critical"] >= 1 and res_hub["mojibake_count"] >= 1
        h_cnt, tas_res = ss.audit_tas_reports_impl(stub_engine, hub_root, [], [])
        assert h_cnt >= 1 and tas_res["passed"] is False
    with monkeypatch.context() as mp_j:
        mp_j.setattr(sys, "stdin", None)
        assert jio._read_stdin_payload_ex() == ({}, False)
        mp_j.setattr(sys, "stdin", _DummyStdin("{}", tty=True))
        assert jio._read_stdin_payload_ex() == ({}, False)
        mp_j.setattr(sys, "stdin", _DummyStdin("", fail_read=True))
        assert jio._read_stdin_payload_ex() == ({}, False)
        mp_j.setattr(sys, "stdin", _DummyStdin("{invalid"))
        assert jio._read_stdin_payload_ex() == ({}, True)
        mp_j.setattr(sys, "stdin", _DummyStdin("[]"))
        assert jio._read_stdin_payload_ex() == ({}, True)
        mp_j.setattr(sys, "stdin", _DummyStdin('\ufeff{"a": 1}'))
        assert jio._read_stdin_payload_ex() == ({"a": 1}, False)
        mp_j.setenv("NK_CONVERSATION_ID", "conv_env_99")
        assert jio._resolve_conv_id("../bad", {}) == "conv_env_99"
        mp_j.delenv("NK_CONVERSATION_ID", raising=False)
        assert jio._resolve_conv_id("bad\x00id", {"conversationId": "bad id!"}).startswith("default_")
    j_target = tmp_path / "jio_state.json"
    jio._write_json_atomic_safe(j_target, {"step": 7})
    assert jio._read_json_safe(j_target) == {"step": 7} and len(jio._sha256_file(j_target)) == 64


@pytest.mark.fast
def test_sub_handoff_cursor_and_fastguard_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre cursor incrementali/cold-backscan e CLI dry-run su nk_session_handoff e fastguard."""
    sh_mod = load_script_by_relpath("nk_session_handoff_cov", "scripts/nk_session_handoff.py")
    fg_mod = load_script_by_relpath("nk_acs_fastguard_cov2", "scripts/nk_acs_fastguard.py")
    for bad_turn in (True, "abc", 9, -1, []):
        with pytest.raises(ValueError):
            sh_mod._parse_optional_turn(bad_turn)
    assert sh_mod._parse_optional_turn("   ") is None and sh_mod._dynamic_code_fence("````ok```") == "`````"
    sh_ws = tmp_path / "sh_cov_ws"
    (sh_ws / "nk_tracking" / "handoff").mkdir(parents=True)
    (sh_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"total_tests": 207, "pass_rate_pct": 100.0}), encoding="utf-8")
    assert sh_mod._read_baseline_tests_count(sh_ws) == 207 and sh_mod._read_baseline_pass_rate(sh_ws) == 100.0
    orig_cache = dict(sh_mod._TRANSCRIPT_CURSOR_CACHE)
    try:
        sh_mod._TRANSCRIPT_CURSOR_CACHE.clear()
        tp_inc = tmp_path / "sh_inc.jsonl"
        tp_inc.write_text('{"source":"MODEL","content":"partial_no_nl","usage":{"input_tokens":50}}', encoding="utf-8")
        assert sh_mod._inspect_transcript_fast(str(tp_inc))[0] == 1
        with open(tp_inc, "a", encoding="utf-8") as af_s:
            af_s.write("\n" + json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "<CONTEXT_SUMMARY>"}) + "\n" + '{"source":"MODEL","content":"tail","usage":{"input_tokens":222}}')
        st_i, _, _, tok_i = sh_mod._inspect_transcript_fast(str(tp_inc))
        assert st_i >= 1 and tok_i == 222
        out_dir = tmp_path / "sh_out"
        rc_d, out_d, _ = _call_main_captured(sh_mod, ["--auto-checkpoint", "--dry-run", "--generate-active-context", "--checkpoint-turn", "2", "--conversation-id", "cid_dry_cov", "--project-root", str(sh_ws), "--transcript", str(tp_inc), "--output-dir", str(out_dir)])
        assert rc_d == 0 and "DRY_RUN" in out_d
        assert _call_main_captured(sh_mod, ["--checkpoint-turn", "2", "--dry-run", "--project-root", str(sh_ws)])[0] == 0
        assert _call_main_captured(sh_mod, ["--output-dir", str(out_dir), "--project-root", str(sh_ws), "--git-stash"])[0] == 0
        (sh_ws / ".git").mkdir()
        assert sh_mod._check_git_dirty_fast(sh_ws, "nonexistent_git_bin_xyz")[0] is False
    finally:
        sh_mod._TRANSCRIPT_CURSOR_CACHE.clear()
        sh_mod._TRANSCRIPT_CURSOR_CACHE.update(orig_cache)
    tp_fg = tmp_path / "fg_big_cur.jsonl"
    fg_pad = json.dumps({"source": "MODEL", "content": "f" * 1600, "usage": {"input_tokens": 90}}) + "\n"
    tp_fg.write_text((fg_pad * 48) + "{bad_json\n[]\n" + json.dumps({"source": "SYSTEM", "type": "CHECKPOINT"}) + "\n" + json.dumps({"source": "MODEL", "usage": {"input_tokens": 120}}) + "\n", encoding="utf-8")
    fg_state = fg_mod._default_state()
    fg_mod._advance_cursor(str(tp_fg), fg_state)
    assert fg_state["compaction_epoch"] >= 1 and fg_state["last_actual_tokens"] == 120
    with monkeypatch.context() as mp_fg:
        mp_fg.setattr(sys, "stdin", _DummyStdin("", tty=True))
        assert _call_main_captured(fg_mod, ["--event", "PreInvocation", "--project-root", str(sh_ws)])[1].strip() == "{}"


@pytest.mark.fast
def test_submodules_auto_heal_cleanup_discovery_and_mutex_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre auto_heal_pipeline: classify_failure, normalize_test_command, KarpathySlicer e main."""
    ah_mod = load_script_by_relpath("auto_heal_pipeline_cov2", "scripts/auto_heal_pipeline.py")
    assert ah_mod.classify_failure("TimeoutExpired") == "TIMEOUT_ERROR"
    assert ah_mod.classify_failure("SyntaxError: invalid") == "SYNTAX_ERROR"
    assert ah_mod.classify_failure("ImportError: no mod") == "IMPORT_ERROR"
    assert ah_mod.classify_failure("AssertionError: bad") == "ASSERTION_ERROR"
    assert ah_mod.classify_failure("boom", exit_code=1) == "RUNTIME_ERROR"
    assert ah_mod.classify_failure("ok", exit_code=0) == "NONE"
    assert "-m pytest" in str(ah_mod.normalize_test_command("pytest"))
    assert ah_mod.normalize_test_command("python -V") == "python -V"
    assert ah_mod.normalize_test_command(["pytest", "-q"])[1:3] == ["-m", "pytest"]
    assert ah_mod.KarpathySlicer.slice_source("", 1).content == ""
    assert ah_mod.KarpathySlicer.slice_source("def bad(:\n", 1).function_name is None
    short_src = "def fn_short():\n    x = 1\n    return x\n"
    assert ah_mod.KarpathySlicer.slice_source(short_src, 2).function_name == "fn_short"
    assert ah_mod.KarpathySlicer.slice_source("def fn_long():\n" + ("    x = 1\n" * 35) + "    return x\n", 10).function_name == "fn_long"
    assert ah_mod.KarpathySlicer.slice_file(tmp_path / "missing_slice.py", 1).content == "<file not found>"
    sample_py = tmp_path / "heal_target.py"
    sample_py.write_text(short_src, encoding="utf-8")
    assert ah_mod.KarpathySlicer.slice_file(sample_py, 2).function_name == "fn_short"
    ah_mod.DSPyTelemetryHook(tmp_path / "dspy_tel.jsonl").record_run(
        ah_mod.DSPyTelemetryRecord(run_id="r1", task_name="t1", cycles_total=1, final_status="PASS", cycles_telemetry=[{"ok": True}])
    )
    assert (tmp_path / "dspy_tel.jsonl").is_file()
    dk, qk = ah_mod._compute_rsi_metrics(passed=10, failed=0, target_path=sample_py, pre_code=short_src)
    assert dk == 0 and qk > 0.0
    with monkeypatch.context() as mp_ah:
        mp_ah.setattr(ah_mod, "RSIDefectVector", None)
        mp_ah.setattr(ah_mod, "compute_delta", None)
        assert ah_mod._compute_rsi_metrics(passed=8, failed=2)[0] == 20


@pytest.mark.fast
def test_sub_safe_cleanup_psutil_and_netstat_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre safe_cleanup_dev_servers: psutil, external project, netstat fallback e error paths."""
    clean_mod = load_script_by_relpath("safe_cleanup_cov2", "scripts/safe_cleanup_dev_servers.py")
    ws_c = tmp_path / "clean_ws_c"
    (ws_c / "NK_External_Projects").mkdir(parents=True)
    assert clean_mod.parse_ports_arg("8000, bad, 70000, 8018") == [8000, 8018]
    assert clean_mod.kill_pid_tree(0) is False and clean_mod.kill_pid_tree(os.getpid()) is False
    with monkeypatch.context() as mp_c:
        mp_c.setattr(clean_mod, "_HAS_PSUTIL", False)
        mp_c.setattr(clean_mod, "psutil", None)
        assert clean_mod.scan_listening_port_range(workspace_root=ws_c) == set()
        assert clean_mod.get_pids_listening_on_ports(workspace_root=ws_c) == set()

        class _FakeProc:
            def __init__(self, pname: str, cmd: list[str], cwd_val: str, raise_cwd: bool = False) -> None:
                self._pname, self._cmd, self._cwd, self._raise_cwd = pname, cmd, cwd_val, raise_cwd
            def name(self) -> str: return self._pname
            def cmdline(self) -> list[str]: return self._cmd
            def cwd(self) -> str:
                if self._raise_cwd:
                    raise RuntimeError("cwd denied")
                return self._cwd

        proc_state: dict[str, Any] = {"proc": _FakeProc("python.exe", ["python", "-m", "http.server"], str(ws_c)), "raise_net": False}

        class _FakePsutil:
            CONN_LISTEN = "LISTEN"
            @staticmethod
            def net_connections(kind: str = "inet") -> list[Any]:
                if proc_state["raise_net"]:
                    raise RuntimeError("psutil denied")
                return [SimpleNamespace(status="LISTEN", laddr=SimpleNamespace(port=8000), pid=424242)]
            @staticmethod
            def Process(_pid: int) -> _FakeProc: return proc_state["proc"]

        mp_c.setattr(clean_mod, "_HAS_PSUTIL", True)
        mp_c.setattr(clean_mod, "psutil", _FakePsutil)
        mp_c.setattr(clean_mod, "_workspace_root", ws_c)
        assert 424242 in clean_mod.scan_listening_port_range(3000, 9999, workspace_root=ws_c)
        assert clean_mod.get_pids_listening_on_ports([8000], workspace_root=ws_c) == {424242}
        proc_state["proc"] = _FakeProc("bash.exe", ["bash"], str(ws_c))
        assert clean_mod.is_target_workspace_process(424242, ws_c) is False
        proc_state["proc"] = _FakeProc("node.exe", ["node", str(ws_c / "NK_External_Projects" / "app.js")], str(ws_c), raise_cwd=True)
        assert clean_mod.is_target_workspace_process(424242, None) is True
        proc_state["raise_net"] = True
        mp_c.setattr(clean_mod.subprocess, "check_output", lambda *_a, **_k: "TCP 127.0.0.1:8000 0.0.0.0:0 LISTENING 424242\n")
        assert clean_mod.get_pids_listening_on_ports([8000], workspace_root=None) == {424242}
        mp_c.setattr(clean_mod.subprocess, "check_output", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sub err")))
        assert clean_mod.get_pids_listening_on_ports([8000], workspace_root=ws_c) == set()
        mp_c.setattr(clean_mod.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sub err")))
        assert clean_mod.kill_pid_tree(424242) is False


@pytest.mark.fast
def test_sub_handoff_discovery_context_sentry_yaml_and_compliance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre nk_session_handoff discovery, nk_context_sentry YAML e compliance UNMEASURED."""
    sh_mod = load_script_by_relpath("nk_session_handoff_cov2", "scripts/nk_session_handoff.py")
    ws_h = tmp_path / "handoff_ws_c"
    ws_h.mkdir()
    assert sh_mod.resolve_session_tracking_dir(ws_h, "default_abc") is None
    assert sh_mod.resolve_session_tracking_dir(ws_h, "bad/id") is None
    fake_home = tmp_path / "fake_home_h"
    sub_logs = fake_home / ".gemini" / "antigravity" / "brain" / "conv_sub" / ".system_generated" / "logs"
    main_logs = fake_home / ".gemini" / "antigravity" / "brain" / "conv_main" / ".system_generated" / "logs"
    sub_logs.mkdir(parents=True)
    main_logs.mkdir(parents=True)
    (sub_logs / "transcript.jsonl").write_text('{"content": "<SYSTEM_MESSAGE> sender=parent"}\n', encoding="utf-8")
    (main_logs / "transcript.jsonl").write_text('{"step_index": 0, "content": "main"}\n', encoding="utf-8")
    with monkeypatch.context() as mp_h:
        mp_h.setenv("USERPROFILE", str(fake_home))
        mp_h.setenv("HOME", str(fake_home))
        assert "conv_main" in (sh_mod._discover_default_transcript() or "")
    sh_mod.record_fsm_checkpoint(turn=2, gate_status="PASS", milestone_id="m_cov", root=ws_h, conversation_id="conv_m")
    assert _call_main_captured(sh_mod, ["--project-root", str(ws_h), "--conversation-id", "conv_m", "--resume-from-anchor"])[0] == 0
    cs_mod = load_script_by_relpath("nk_context_sentry_cov2", "scripts/nk_context_sentry.py")
    json_cfg = tmp_path / "sat_thresh.json"
    json_cfg.write_text(json.dumps({"profiles": {"carbon": {"green_step_threshold": 150}}}), encoding="utf-8")
    assert cs_mod.load_saturation_thresholds(thresholds_path=json_cfg)["profiles"]["carbon"]["green_step_threshold"] == 150
    cc_mod = load_script_by_relpath("nk_compliance_checker_cov2", "scripts/nk_compliance_checker.py")
    ws_cc = tmp_path / "ws_cc_global"
    tp_prose = ws_cc / "brain" / "sess_prose_only" / "transcript.jsonl"
    tp_prose.parent.mkdir(parents=True)
    tp_prose.write_text(json.dumps({"step_index": 0, "source": "USER", "content": "Modifica file"}) + "\n", encoding="utf-8")
    checker = cc_mod.NKComplianceChecker(workspace_root=ws_cc)
    with monkeypatch.context() as mp_unm:
        mp_unm.setattr(cc_mod, "NKContextSentry", None)
        res_unm = checker.audit_transcript(tp_prose)
        assert res_unm["metrics"]["context_sentry_status"] == "UNMEASURED" and res_unm["status"] == "FAIL"


@pytest.mark.fast
def test_sub_win32_mutex_abandoned_and_posix_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre WAIT_ABANDONED_0, WAIT_FAILED e _FailingUnFcntl in win32_2pc_engine/mutex.py."""
    import threading as _thr

    w2pc_mod = load_script_by_relpath("w2pc_cov2", "scripts/win32_2pc_engine.py")
    mutex_mod = sys.modules[w2pc_mod.Win32NamedMutex.__module__]
    consts_mod = mutex_mod._consts
    wait_seq: list[int] = [consts_mod.WAIT_ABANDONED_0, 0xFFFFFFFF]

    class _FakeK32Abandon:
        @staticmethod
        def OpenMutexW(_a: int, _i: bool, _n: str) -> Any: return None
        @staticmethod
        def CreateMutexW(_s: Any, _i: bool, _n: str) -> int: return 7771
        @staticmethod
        def WaitForSingleObject(_h: Any, _ms: int) -> int: return wait_seq.pop(0)
        @staticmethod
        def GetCurrentThreadId() -> int: return _thr.get_ident()
        @staticmethod
        def ReleaseMutex(_h: Any) -> int: return 1
        @staticmethod
        def CloseHandle(_h: Any) -> int: return 1
        @staticmethod
        def GetLastError() -> int: return 2

    with monkeypatch.context() as mp_mx:
        if sys.platform != "win32":
            last_err_mx = {"val": 0}
            mp_mx.setattr(
                ctypes,
                "set_last_error",
                lambda v: last_err_mx.__setitem__("val", int(v)),
                raising=False,
            )
            mp_mx.setattr(
                ctypes,
                "get_last_error",
                lambda: int(last_err_mx["val"]),
                raising=False,
            )
        mp_mx.setattr(consts_mod, "_get_active_kernel32", lambda: _FakeK32Abandon)
        mtx_ab = w2pc_mod.Win32NamedMutex("Global\\NK_AbandonCov", timeout_ms=10, is_path=False)
        mtx_ab.acquire()
        assert mtx_ab.abandoned is True and mtx_ab.abandoned_recovered is True
        mtx_ab.release()
        with pytest.raises(w2pc_mod.Win32LockError):
            w2pc_mod.Win32NamedMutex("Global\\NK_FailCov", timeout_ms=10, is_path=False).acquire()

        class _FailingUnFcntl:
            LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8
            @staticmethod
            def flock(_fd: int, op: int) -> None:
                if op == 8:
                    raise OSError("unlock err")

        mp_mx.setattr(consts_mod, "_get_active_kernel32", lambda: None)
        mp_mx.setattr(consts_mod, "_fcntl", _FailingUnFcntl)
        lock_file = tmp_path / "posix_reenter.lock"
        m_p1 = w2pc_mod.Win32NamedMutex(str(lock_file), timeout_ms=20, is_path=True)
        m_p2 = w2pc_mod.Win32NamedMutex(str(lock_file), timeout_ms=20, is_path=True)
        m_p1.acquire()
        m_p2.acquire()
        m_p2.release()
        m_p1.release()
        m_unacq = w2pc_mod.Win32NamedMutex(str(lock_file), timeout_ms=20, is_path=True)
        m_unacq.handle = 999999
        m_unacq.acquired = False
        m_unacq.release()
        assert m_unacq.handle is None


@pytest.mark.integration
def test_sub_lazy_cli_cold_help_no_pydantic() -> None:
    """Verifica avvio --help senza pydantic sui moduli lazy e cold start fastguard."""
    lazy_targets = (
        "scripts/rsi_convergence_engine.py", "scripts/dast_sandbox_runner.py",
        "scripts/ast_repo_mapper.py", "scripts/ast_guard_validator.py",
        "scripts/auto_heal_pipeline.py", "scripts/memory_3tier_engine.py",
        "scripts/micro_hud_renderer.py", "scripts/oracle_evaluator_l3.py",
        "scripts/sbfl_engine.py", "scripts/sbfl_pytest_bridge.py",
        "scripts/healing_snapshot_rollback.py", "scripts/nk_context_sentry.py",
        "scripts/win32_2pc_engine.py",
    )
    py_roots = [str(_WORKSPACE_ROOT / ".staging" / "scripts"), str(_WORKSPACE_ROOT / ".staging"), str(_WORKSPACE_ROOT / "scripts"), str(_WORKSPACE_ROOT)]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(py_roots)

    def _run_probe(spec: tuple[str, list[str], str, float, bool]) -> tuple[str, int, str]:
        label, flags, probe_src, timeout_s, use_env = spec
        proc = subprocess.run([sys.executable, *flags, "-c", probe_src], cwd=str(_WORKSPACE_ROOT), env=(env if use_env else None), capture_output=True, text=True, timeout=timeout_s, shell=False)
        return label, proc.returncode, proc.stderr

    specs: list[tuple[str, list[str], str, float, bool]] = []
    for rel_s in lazy_targets:
        stg_p = _WORKSPACE_ROOT / ".staging" / rel_s
        target_p = stg_p if stg_p.is_file() else (_WORKSPACE_ROOT / rel_s)
        probe_src = (
            f"import runpy, sys\nsys.argv = [{str(target_p)!r}, '--help']\n"
            "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\n"
            "except SystemExit as exc:\n    assert exc.code in (0, None)\n"
            "assert 'pydantic' not in sys.modules\n"
        )
        specs.append((f"{rel_s} --help", ["-B"], probe_src, 20.0, True))

    fg_p = _WORKSPACE_ROOT / ".staging" / "scripts" / "nk_acs_fastguard.py"
    if not fg_p.is_file():
        fg_p = _WORKSPACE_ROOT / "scripts" / "nk_acs_fastguard.py"
    fg_src = f"import runpy, sys\nsys.argv = [{str(fg_p)!r}, '--help']\ntry:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit:\n    pass\nassert 'pathlib' not in sys.modules\n"
    specs.append(("fastguard cold start", ["-S", "-B"], fg_src, 15.0, False))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for label, rc, stderr in pool.map(_run_probe, specs):
            assert rc == 0, f"{label} failed: {stderr}"


@pytest.mark.fast
def test_sub_nk_common_io_and_paths_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre rami non coperti di nk_common.io e nk_common.paths."""
    from _internal.nk_common import io as nk_io, paths as nk_paths

    long_p = tmp_path / ("a" * 245) / "f.txt"
    if os.name != "nt":
        assert nk_io.win_long_path(long_p) == long_p
    with monkeypatch.context() as mp_lp:
        if os.name != "nt":
            mp_lp.setattr(nk_io.os, "name", "nt")
        assert str(nk_io.win_long_path(long_p)).startswith("\\\\?\\")
        assert nk_io.win_long_path("\\\\?\\C:\\x.txt") == Path("\\\\?\\C:\\x.txt")
    assert nk_io._is_retryable_os_error(PermissionError("deny")) is True
    err_win = OSError("non_retry")
    err_win.winerror = 9999  # type: ignore[attr-defined]
    assert nk_io._is_retryable_os_error(err_win) is False
    target_u = tmp_path / "u.txt"
    target_u.write_text("hi", encoding="utf-8")
    assert nk_io.unlink_with_retry(target_u, delays=(0.0,)) is True and not target_u.exists()
    assert nk_io.unlink_with_retry(tmp_path / "nonexistent_u.txt") is True
    assert nk_io.atomic_write_bytes(tmp_path / "rep.txt", b"x", reparse_check=lambda _p: True) == (False, "reparse_guard")
    assert nk_io.atomic_write_bytes(tmp_path / "ok.txt", b"payload", delays=(0.0,)) == (True, None)
    bad_parent = tmp_path / "file_not_dir"
    bad_parent.write_text("x", encoding="utf-8")
    ok_mk, err_mk = nk_io.atomic_write_bytes(bad_parent / "sub" / "f.txt", b"1")
    assert ok_mk is False and "mkdir_error:" in (err_mk or "")
    real_replace = nk_io.os.replace
    attempts = {"n": 0}
    def _flaky_replace(s: str, d: str) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise PermissionError("busy")
        real_replace(s, d)
    monkeypatch.setattr(nk_io.os, "replace", _flaky_replace)
    assert nk_io.atomic_write_json(tmp_path / "j.json", {"ok": True}, delays=(0.0,)) == (True, None)
    monkeypatch.setattr(nk_io.os, "replace", lambda *_a: (_ for _ in ()).throw(PermissionError("perm_fail")))
    ok_ex, err_ex = nk_io.atomic_write_bytes(tmp_path / "ex.txt", b"1", delays=(0.0,))
    assert ok_ex is False and "io_error:" in (err_ex or "")
    stg_anchor = tmp_path / "hub" / ".staging" / "scripts" / "x.py"
    stg_anchor.parent.mkdir(parents=True)
    assert Path(nk_paths.resolve_scripts_dir(str(stg_anchor))).name == "scripts"
    assert Path(nk_paths.resolve_workspace_root(str(stg_anchor))).name == "hub"
    assert Path(nk_paths.resolve_workspace_root(str(tmp_path / "hub" / ".staging" / "f.txt"))).name == "hub"
    nk_paths.reconfigure_streams(include_stdin=True)


@pytest.mark.fast
def test_sub_nk_common_win32_mutex_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre tutti i rami di nk_common.win32_mutex (Global->Local fallback, timeout, cleanup)."""
    from _internal.nk_common import win32_mutex as wm

    assert wm.is_win32_handle_valid(None) is False and wm.is_win32_handle_valid(True) is False
    assert wm.is_win32_handle_valid("bad") is False and wm.is_win32_handle_valid(42) is True  # type: ignore[arg-type]
    if sys.platform != "win32":
        assert wm.create_or_open_named_mutex("Global\\NK_NonWin32") == (None, False, "non_win32")
        assert wm.try_acquire_mutex_nonblocking("Global\\NK_NonWin32") == -1
        wm.release_win32_mutex(1234)
    calls: List[str] = []

    class _FakeK32:
        @staticmethod
        def CreateMutexW(_sa: Any, _init: bool, name: str) -> int:
            calls.append(name)
            if name.startswith("Global\\"):
                ctypes.set_last_error(wm.ERROR_ACCESS_DENIED)
                return 0
            return 1234
        @staticmethod
        def WaitForSingleObject(_h: Any, _ms: int) -> int: return wm.WAIT_OBJECT_0
        @staticmethod
        def ReleaseMutex(_h: Any) -> int: return 1
        @staticmethod
        def CloseHandle(_h: Any) -> int: return 1

    with monkeypatch.context() as mp_wm:
        if sys.platform != "win32":
            last_err_wm = {"val": 0}
            mp_wm.setattr(wm.sys, "platform", "win32")
            mp_wm.setattr(
                ctypes,
                "set_last_error",
                lambda v: last_err_wm.__setitem__("val", int(v)),
                raising=False,
            )
            mp_wm.setattr(
                ctypes,
                "get_last_error",
                lambda: int(last_err_wm["val"]),
                raising=False,
            )

        h, acq, err = wm.create_or_open_named_mutex("Global\\NK_TestFallback", wait_ms=0, k32=_FakeK32)
        assert acq is True and h == 1234 and err is None and calls == ["Global\\NK_TestFallback", "Local\\NK_TestFallback"]
        wm.release_win32_mutex(h, k32=_FakeK32)
        wm.release_win32_mutex(None, k32=_FakeK32)
        wm.release_win32_mutex(0, k32=_FakeK32)
        mp_wm.setattr(_FakeK32, "WaitForSingleObject", staticmethod(lambda _h, _ms: wm.WAIT_TIMEOUT))
        assert wm.create_or_open_named_mutex("Local\\NK_TO", wait_ms=0, k32=_FakeK32) == (None, False, "timeout")
        assert wm.try_acquire_mutex_nonblocking("Local\\NK_TO", k32=_FakeK32) is None
        mp_wm.setattr(_FakeK32, "WaitForSingleObject", staticmethod(lambda _h, _ms: 0xFFFFFFFF))
        assert wm.try_acquire_mutex_nonblocking("Local\\NK_Fail", k32=_FakeK32) == -1
        mp_wm.setattr(_FakeK32, "CreateMutexW", staticmethod(lambda *_a: 0))
        assert wm.create_or_open_named_mutex("Local\\NK_Zero", k32=_FakeK32)[1] is False


@pytest.mark.fast
def test_sub_hook_gate_integrity_oracle_lock_tampering(
    tmp_path: Path, isolated_nk_ws_factory: Any
) -> None:
    """Copre rami _verify_oracle_lock_files e _handle_integrity in integrity_and_fasttrack.py."""
    load_script_by_relpath("nk_hook_gate_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import integrity_and_fasttrack as itf

    isolated_nk_ws_factory("itf_env", apply_inproc=True)
    ws = tmp_path / "itf_ws"
    for d in ("nk_tracking", "tests", "scripts", ".agents"):
        (ws / d).mkdir(parents=True)
    (ws / "PATCH_NOTES.md").write_text("## [1.0.0]\n- Init.\n", encoding="utf-8")
    (ws / "nk_tracking" / "checkpoint_1.json").write_text('{"ok": true}', encoding="utf-8")
    t_py = ws / "tests" / "t1.py"
    t_py.write_text("assert True\n", encoding="utf-8")
    good_sha = hashlib.sha256(b"assert True\n").hexdigest()
    lock_p = ws / "nk_tracking" / "oracle_lock.json"
    lock_p.write_text("{bad", encoding="utf-8")
    assert "Invalid JSON" in itf._verify_oracle_lock_files(ws, lock_p)[0]
    lock_p.write_text("[]", encoding="utf-8")
    assert "Invalid root" in itf._verify_oracle_lock_files(ws, lock_p)[0]
    lock_p.write_text(json.dumps({"files": {"../escape.py": good_sha, "missing.py": good_sha, "t1.py": "not_hex"}}), encoding="utf-8")
    v_list = itf._verify_oracle_lock_files(ws, lock_p)
    assert any("escape" in v for v in v_list) and any("missing" in v for v in v_list) and any("invalid SHA-256" in v for v in v_list)
    lock_p.write_text(json.dumps({"files": {"t1.py": good_sha}, "combined_sha256": "0" * 64}), encoding="utf-8")
    assert "combined_sha256 mismatch" in itf._verify_oracle_lock_files(ws, lock_p)[0]
    comb = hashlib.sha256(json.dumps({"t1.py": good_sha}, sort_keys=True).encode("utf-8")).hexdigest()
    lock_p.write_text(json.dumps({"files": {"t1.py": good_sha}, "combined_sha256": comb}), encoding="utf-8")
    assert itf._handle_integrity("cid_itf", ws, init_mode=False, check_mode=True)[1] == 1
    assert itf._handle_integrity("cid_itf", ws, init_mode=True, check_mode=False)[1] == 0
    assert itf._handle_integrity("cid_itf", ws, init_mode=False, check_mode=True)[1] == 0
    (ws / "nk_tracking" / "checkpoint_1.json").unlink()
    (ws / "PATCH_NOTES.md").unlink()
    assert itf._handle_integrity("cid_itf", ws, init_mode=False, check_mode=True)[1] == 1


@pytest.mark.fast
def test_sub_hook_gate_mcp_classifier_branches(tmp_path: Path) -> None:
    """Copre rami mcp_classifier.py (eager MCP, JSON arguments, path protections, allowlist)."""
    load_script_by_relpath("nk_hook_gate_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import mcp_classifier as mc

    ws = tmp_path / "mcp_ws"
    (ws / "scripts").mkdir(parents=True)
    assert mc._extract_mcp_candidate_paths({"a": [{"file_path": "file:///C:/x.py"}, {"url": "https://a.test"}]}, depth=0) == ["C:/x.py"]
    assert mc._extract_mcp_candidate_paths({"p": "a"}, depth=11) == []
    assert mc._resolve_eager_mcp_names("", "", "mcp_tavily-mcp_tavily_search") == ("tavily-mcp", "tavily_search")
    assert mc._resolve_eager_mcp_names("", "", "mcp_custom_read_item") == ("custom", "read_item")
    assert mc._classify_mcp_tool_call({}, ws)["decision"] == "deny"
    assert mc._classify_mcp_tool_call({"ServerName": "s", "ToolName": "write_file_mcp"}, ws)["decision"] == "deny"
    assert mc._classify_mcp_tool_call({"ServerName": "s", "ToolName": "read_doc", "Arguments": json.dumps({"path": "scripts/x.py"})}, ws)["decision"] == "deny"
    assert mc._classify_mcp_tool_call({"ServerName": "s", "ToolName": "read_doc", "Arguments": json.dumps({"path": "nk_tracking/oracle_lock.json"})}, ws)["decision"] == "deny"
    assert mc._classify_mcp_tool_call({"ServerName": "s", "ToolName": "read_doc", "Arguments": json.dumps({"path": "C:/dir/a.txt:ads"})}, ws)["decision"] == "deny"
    assert mc._classify_mcp_tool_call({"ServerName": "tavily-mcp", "ToolName": "tavily_search", "Arguments": '{"query": "ok"}'}, ws) == {}
    assert mc._classify_mcp_tool_call({"ToolName": "read_google_doc", "Arguments": "plain_id"}, ws) == {}
    assert mc._classify_mcp_tool_call({"ToolName": "developerknowledge_search_documents"}, ws) == {}
    assert mc._classify_mcp_tool_call({"ToolName": "firebase_get_project"}, ws) == {}
    assert mc._classify_mcp_tool_call({"ServerName": "puppeteer", "ToolName": "puppeteer_screenshot"}, ws) == {}
    assert mc._classify_mcp_tool_call({"ServerName": "chrome-devtools-mcp", "ToolName": "take_screenshot"}, ws) == {}
    assert mc._classify_mcp_tool_call({"ServerName": "unknown", "ToolName": "unknown_op"}, ws)["decision"] == "deny"


@pytest.mark.fast
def test_sub_hook_gate_path_safety_and_target_classifier(tmp_path: Path) -> None:
    """Copre rami path_safety.py e target_classifier.py (whitelist, ADS, B1, oracle-lock)."""
    load_script_by_relpath("nk_hook_gate_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import path_safety as ps, target_classifier as tc

    ws = tmp_path / "ps_ws"
    (ws / "NK_Hub" / "scripts").mkdir(parents=True)
    (ws / "NK_Hub" / ".staging" / "scripts").mkdir(parents=True)
    hub = ws / "NK_Hub"
    assert ps._is_safe_temp_marker_path("%temp%/nk_diagnostics/out.json") is True
    assert ps._is_safe_temp_marker_path("scripts/%temp%/bad") is False
    assert ps._is_valid_staging_path(ws / ".staging" / ".agents" / "AGENTS.md", hub) is True
    assert ps._is_valid_staging_path(ws / "NK_External_Projects" / "App" / ".staging" / "a.py", hub) is True
    assert ps._is_safe_redirection_target("nul", hub) is True
    assert ps._is_safe_redirection_target("nk_diagnostics/rep.json", hub) is True
    assert ps._is_safe_redirection_target("%USERPROFILE%/x.txt", hub) is False
    assert "__staged_safe__" in ps._sanitize_staged_tokens_in_cmd("echo hi > .staging/a.py")
    assert ps._is_whitelisted_outside_staging(hub / "nk_tracking" / "reports_and_briefs" / "r.md", hub) is True
    assert ps._is_whitelisted_outside_staging(hub / "README.md", hub) is True
    assert ps._is_whitelisted_outside_staging(hub / "nk_docs_and_setup" / "README.md", hub) is True
    assert tc._looks_like_write_path_candidate("https://example.com") is False
    assert tc._looks_like_write_path_candidate("scripts/a.py") is True
    assert tc._classify_redirection_target_violation("__empty_redirect__", hub)["decision"] == "deny"
    assert tc._classify_redirection_target_violation("PATCH_NOTES.md", hub)["decision"] == "deny"
    assert tc._classify_redirection_target_violation("quality_baseline.json", hub)["decision"] == "deny"
    assert tc._classify_redirection_target_violation("checkpoint_1.json", hub)["decision"] == "deny"
    assert tc._classify_redirection_target_violation("custom_file.txt", hub)["decision"] == "deny"
    assert tc._classify_protected_target("", "python -c \"a=1\nb=2\"", hub)["decision"] == "deny"
    assert tc._classify_protected_target("", "git reset --hard HEAD", hub)["decision"] == "deny"
    assert tc._classify_protected_target("", "python scripts/nk_transcript_tools.py oracle-lock verify", hub) == {}
    assert tc._classify_protected_target("", "python scripts/nk_transcript_tools.py oracle-lock freeze", hub, strict_external=True)["decision"] == "ask"
    assert tc._classify_protected_target("NK_Hub/.wal/tx.wal", "", hub)["decision"] == "deny"


@pytest.mark.fast
def test_sub_hook_gate_write_gate_and_cli_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_ws_factory: Any
) -> None:
    """Copre write_gate.py (PATCH_NOTES chunks, external project) e scripts/nk_hook_gate.py CLI."""
    hook_mod = load_script_by_relpath("nk_hook_gate_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import write_gate as wg

    isolated_nk_ws_factory("wg_env", apply_inproc=True)
    ws = tmp_path / "wg_ws"
    for d in (".staging/scripts", "scripts", "NK_External_Projects/App"):
        (ws / d).mkdir(parents=True)
    pn = ws / "PATCH_NOTES.md"
    pn.write_text("## [1.0.0]\n- Init.\n", encoding="utf-8")
    assert wg._handle_write_gate(
        {"toolName": "edit_file", "toolInput": {"TargetFile": str(pn), "TargetContent": "## [1.0.0]", "ReplacementContent": "## [1.1.0]\n- Upd.\n\n## [1.0.0]"}},
        ws, False, "", "", "",
    ) == {}
    assert wg._handle_write_gate(
        {"toolName": "edit_file", "toolInput": {"TargetFile": str(pn), "ReplacementChunks": [{"TargetContent": "## [1.0.0]", "ReplacementContent": "# Wiped"}]}},
        ws, False, "", "", "",
    )["decision"] == "deny"
    assert wg._handle_write_gate({"toolName": "write_file", "toolInput": {"Path": str(ws / "custom_unlisted.txt")}}, ws, False, "", "", "")["decision"] == "deny"
    assert wg._handle_write_gate({"toolName": "run_command", "toolInput": {"CommandLine": "python -c \"open('NK_External_Projects/App/x.py','w')\""}}, ws, False, "", "", "")["decision"] == "deny"
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert _call_main_captured(hook_mod, ["probe", "--event=PreToolUse", "--project-root", str(ws)])[0] == 0
    assert _call_main_captured(hook_mod, ["fasttrack", "--conversation-id", "c_ft", "--project-root", str(ws)])[0] == 0
    assert _call_main_captured(hook_mod, ["integrity", "--init", "--conversation-id", "c_ft", "--project-root", str(ws)])[0] == 0
    assert _call_main_captured(hook_mod, ["integrity", "--check", "--conversation-id", "c_ft", "--project-root", str(ws)])[0] == 0


@pytest.mark.fast
def test_sub_hook_gate_shell_parser_and_write_detector(tmp_path: Path) -> None:
    """Copre shell_parser.py e shell_write_detector.py (output flags, archive, search, temp scripts)."""
    load_script_by_relpath("nk_hook_gate_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import shell_parser as sp, shell_write_detector as swd

    ws = tmp_path / "sh_ws"
    (ws / "scripts").mkdir(parents=True)
    assert sp._looks_like_path_token("scripts/a.py") is True and sp._looks_like_path_token("plain word") is False
    assert sp._extract_output_flag_targets_segment("tool -o out.txt --output=res.json") == ["out.txt", "res.json"]
    assert sp._extract_output_flag_targets_segment("pytest -o log_file=scripts/a.log") == ["scripts/a.log"]
    assert sp._extract_output_flag_targets_segment("7z x archive.zip -oout_dir") == ["out_dir"]
    assert sp._extract_output_flag_targets_segment("tool --output") == ["__empty_redirect__"]
    assert sp._extract_archive_targets_segment("tar -xf a.tar -C scripts") == ["scripts"]
    assert sp._extract_archive_targets_segment("unzip a.zip -dscripts") == ["scripts"]
    assert sp._extract_archive_targets_segment("7z x a.7z -oscripts") == ["scripts"]
    assert sp._extract_archive_targets_segment("Expand-Archive a.zip scripts") == ["scripts"]
    assert sp._extract_archive_targets_segment("python -c \"shutil.unpack_archive('a.zip', extract_dir='scripts')\"") == ["scripts"]
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns("rg -e 'write_file' -- scripts/a.py")
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns("findstr /c:Set-Content scripts/a.py")
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns("git grep -e Set-Content")
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns("git log --grep=write_file -S foo")
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns("powershell -Command rg Set-Content scripts/")
    assert swd._strip_readonly_search_patterns("git -c core.fsmonitor=evil status") == "git -c core.fsmonitor=evil status"
    assert swd._is_temp_or_scratch_script_token("scratch/gen.py") is True
    assert swd._arg_targets_protected_outside_staging("scripts/x.py", ws) is True
    assert swd._find_invoked_script_index(["python", "-W", "ignore", "-B", "scratch/a.py"], 0, "python") == 4
    assert swd._find_invoked_script_index(["powershell", "-ep", "Bypass", "-File", "scratch/a.ps1"], 0, "powershell") == 4
    assert swd._find_invoked_script_index(["cmd", "/d", "/c", "scratch\\a.bat"], 0, "cmd") == 3
    assert swd._has_unstaged_temp_script_targeting_protected("python scratch/gen.py --out scripts/x.py", ws) is True


@pytest.mark.fast
def test_sub_gt14_bundle_strict_verify_and_probe_branches(tmp_path: Path) -> None:
    """Copre rami strict_verify e probe branches di rsi_convergence_engine/gt14_bundle.py."""
    rsi_mod = load_script_by_relpath("rsi_convergence_engine_cov", "scripts/rsi_convergence_engine.py")
    from _internal.rsi_convergence_engine import gt14_bundle as gb

    ws = tmp_path / "gt_empty_ws"
    ws.mkdir()
    res = gb.emit_gt14_bundle_impl(
        rsi_mod.RSIConvergenceEngine(workspace_root=ws),
        workspace_root=ws,
        with_dast=False,
        strict_verify=True,
        output_path=tmp_path / "strict_out.json",
    )
    assert res["probes_executed"] == 5 and res["passed"] is False and (tmp_path / "strict_out.json").is_file()


@pytest.mark.fast
def test_sub_shell_write_detector_search_and_git_branches(tmp_path: Path) -> None:
    """Copre _strip_readonly_search_patterns, _has_non_readonly_open, _mask_balanced_prompt_payloads e script Temp."""
    load_script_by_relpath("nk_hook_gate_swd_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import shell_write_detector as swd

    assert swd._scan_quotes_clean("echo $(id)", True) is False
    assert swd._scan_quotes_clean('echo "ok\\"x"', True) is True
    for raw_unchanged in (
        "", "rg $(id) a.py", '""', "$cmd a", "rg --pre cat a.py", "rg -e",
        "git -c x=1 log", "git --exec-path=/tmp log", "git checkout main", "cmd /c", "pwsh foo", "pwsh -c echo",
    ):
        assert swd._strip_readonly_search_patterns(raw_unchanged) == raw_unchanged
    assert swd._strip_readonly_search_patterns("pwsh -c 'rg a b | grep c'") == "pwsh -c 'rg a b | grep c'"
    for masked_in in (
        "rg -- foo.py bar.py", "rg --regexp=secret f.py", "findstr /c pat f.txt",
        "findstr /i pat f.txt", "git --git-dir /g -C r --work-tree=/w -v grep -- -e pat1",
        "git log -- -S foo", "git diff --grep pat", "git show -Gpat", "cmd /nologo /c rg pat f.py",
    ):
        assert swd._strip_readonly_search_patterns(masked_in) != ""
    assert swd._has_non_readonly_open('os.open("x", os.O_CREAT)') is True
    assert swd._has_non_readonly_open('os.open("x", 0); open(x') is True
    assert swd._has_non_readonly_open('f.open("w"); open("a", mode="w")') is True
    assert swd._has_balanced_path_mutation("Path(") is True
    assert swd._has_balanced_path_mutation('Path("a").write_text("x")') is True
    assert swd._redact_safe_si_literals("", "") == ""
    assert swd._redact_safe_si_literals("python ../a.py", "python ../a.py") == "python ../a.py"
    p_ok = 'python scripts/run.py --prompt "Set-Content foo \\"si\\""'
    assert '"__SAFE_PROMPT__"' in swd._mask_balanced_prompt_payloads(p_ok, p_ok)
    assert swd._mask_balanced_prompt_payloads("python $(id)", "python $(id)") == "python $(id)"
    assert swd._mask_balanced_prompt_payloads("", "") == ""


@pytest.mark.fast
def test_sub_shell_parser_token_quote_and_segments_branches() -> None:
    """Copre rami shell_parser: verb .exe, backtick, quote unclosed, & {}, parens, top-level args e -o pytest."""
    load_script_by_relpath("nk_hook_gate_sp_cov", "scripts/nk_hook_gate.py")
    from _internal.nk_hook_gate import shell_parser as sp

    assert sp._norm_cmd_verb('"C:\\Bin\\RG.EXE"') == "rg"
    assert sp._has_unquoted_ps_backtick_obfuscation("'a`b'") is False
    assert sp._has_unquoted_ps_backtick_obfuscation('"a\\"`b"') is False
    assert sp._has_unquoted_ps_backtick_obfuscation("ec`ho hi") is True
    assert sp._deobfuscate_ps_backticks("'a`b' c`d") == "'a`b' cd"
    assert sp._split_shell_segments("") == []
    segs = sp._split_shell_segments('echo "a\\"b`c" 2>&1; cat x | sort || true && echo ok & rm y\n')
    assert len(segs) >= 5 and "2>&1" in segs[0]
    assert sp._tokenize_shell_tokens('"a\\"b`c" \'unclosed') is None
    assert sp._unwrap_shell_subcommands("powershell -c { Get-Item }") == ["Get-Item"]
    assert sp._unwrap_shell_subcommands("echo ok; & { echo 1 }") == ["echo 1"]
    assert sp._extract_balanced_parens("fn", 1) is None
    assert sp._extract_balanced_parens("fn('a\\'b', \"c\\\"d\", (1))", 2) == ("'a\\'b', \"c\\\"d\", (1)", 23)
    args = sp._split_top_level_args("'a\\'', \"b\\\"\", {1:2}, [3,4], (5,6), ")
    assert len(args) == 6 and args[-1] == ""
    assert sp._looks_like_path_token(".staging") is True
    assert sp._looks_like_path_token("C:/with space.py") is True
    assert sp._extract_output_flag_targets_segment("rg -o pat file.py") == []
    assert sp._extract_output_flag_targets_segment("pytest -o") == []
    assert sp._extract_output_flag_targets_segment("tool -o") == ["__empty_redirect__"]


@pytest.mark.fast
def test_sub_staging_guards_json_dual_baseline_and_scan_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre validate_staging_json_files, _verify_quality_baseline_ratchet e _scan_staging_canonical."""
    load_script_by_relpath("quality_baseline_manager", "scripts/quality_baseline_manager.py")
    w2pc_mod = load_script_by_relpath("w2pc_sg_cov", "scripts/win32_2pc_engine.py")
    sg = sys.modules[w2pc_mod.TwoPhaseCommitEngine.__module__.replace(".engine", ".staging_guards")]
    stg = tmp_path / ".staging"
    stg.mkdir()
    bad_utf = stg / "bad_utf.json"
    bad_utf.write_bytes(b"\xff\xfe{")
    fffd_j = stg / "fffd.json"
    fffd_j.write_bytes(b'"\xef\xbf\xbd"')
    bad_syn = stg / "bad_syn.json"
    bad_syn.write_text("{oops", encoding="utf-8")
    ok_st, errs = sg.validate_staging_json_files(stg, [stg / "skip.txt", bad_utf, fffd_j, bad_syn])
    assert ok_st is False and len(errs) == 3

    for bad_bl in ({"total_tests": 1}, {"pass_rate_pct": 90.0, "total_tests": 2}):
        with pytest.raises(sg.TwoPhaseCommitError):
            sg._verify_quality_baseline_ratchet(bad_bl)
    dst_bl, stg_bl = tmp_path / "dst_bl.json", tmp_path / "stg_bl.json"
    dst_bl.write_text('{"pass_rate": 100.0, "golden_tests_count": 5, "failed_tests": 0}', encoding="utf-8")
    stg_bl.write_text('{"other": 1}', encoding="utf-8")
    with pytest.raises(sg.TwoPhaseCommitError):
        sg._verify_quality_baseline_ratchet(dst_bl, stg_bl)
    stg_bl.write_text('{"pass_rate": 95.0, "total_tests": 5}', encoding="utf-8")
    with pytest.raises(sg.TwoPhaseCommitError):
        sg._verify_quality_baseline_ratchet(dst_bl, stg_bl)
    stg_bl.write_text('{"pass_rate": 100.0, "total_tests": 5}', encoding="utf-8")
    assert sg._verify_quality_baseline_ratchet(dst_bl, stg_bl)["verdict"] == "PASS"

    class _FakeDirEntry:
        def __init__(self, n: str) -> None:
            self.name = n
            self._is_dir = False

        def is_symlink(self) -> bool:
            return False

        def stat(self, follow_symlinks: bool = False) -> Any:
            return SimpleNamespace(st_file_attributes=0)

        def is_dir(self, follow_symlinks: bool = False) -> bool:
            return False

        def is_file(self, follow_symlinks: bool = False) -> bool:
            return True

    for bad_entry_name in ("file:ads.py", "trailing_dot."):
        with monkeypatch.context() as mp_sc:
            mp_sc.setattr(sg.os, "scandir", lambda _p, _n=bad_entry_name: type("_Ctx", (), {"__enter__": lambda s: [_FakeDirEntry(_n)], "__exit__": lambda *a: None})())
            with pytest.raises(sg.TwoPhaseCommitError):
                sg._scan_staging_canonical(stg, tmp_path)


@pytest.mark.fast
def test_sub_context_sentry_and_qbm_helper_branches(tmp_path: Path) -> None:
    """Copre __getattr__, fallback YAML->JSON, token helpers in nk_context_sentry e QBM helpers."""
    cs_mod = load_script_by_relpath("nk_context_sentry_bcov", "scripts/nk_context_sentry.py")
    qbm_mod = load_script_by_relpath("qbm_bcov", "scripts/quality_baseline_manager.py")

    assert isinstance(cs_mod._THRESHOLDS_DATA, dict)
    assert isinstance(cs_mod._STD_CS, dict) and isinstance(cs_mod._CARB_CS, dict)
    with pytest.raises(AttributeError):
        getattr(cs_mod, "no_such_lazy_attr_xyz")

    ws_th = tmp_path / "th_ws"
    cfg_dir = ws_th / "nk_genome" / "configs"
    cfg_dir.mkdir(parents=True)
    j_f = cfg_dir / "saturation_thresholds.json"
    j_f.write_text('{"profiles": {"standard": {"context_sentry": {"green_step_threshold": 55}}}}', encoding="utf-8")
    assert cs_mod.load_saturation_thresholds(thresholds_path=j_f)["profiles"]["standard"]["context_sentry"]["green_step_threshold"] == 55
    assert cs_mod.load_saturation_thresholds(workspace_root=ws_th)["profiles"]["standard"]["context_sentry"]["green_step_threshold"] == 55
    j_f.write_text("{corrupt", encoding="utf-8")
    assert cs_mod.load_saturation_thresholds(workspace_root=ws_th) == {}
    j_f.unlink()
    assert cs_mod.load_saturation_thresholds(workspace_root=ws_th) == {}
    assert cs_mod._safe_pos_int(True, 9) == 9 and cs_mod._safe_pos_int(12, 9) == 12
    assert cs_mod.NKContextSentry.estimate_tokens("") == 0
    assert cs_mod.NKContextSentry.format_head_tail("", 10, 10) == ""
    assert cs_mod.NKContextSentry.format_head_tail("short", 10, 10) == "short"
    assert "TRUNCATED" in cs_mod.NKContextSentry.format_head_tail("A" * 120, 10, 10)
    assert cs_mod.NKContextSentry._extract_actual_tokens_from_record([]) is None  # type: ignore[arg-type]
    assert cs_mod.NKContextSentry._extract_actual_tokens_from_record({"input_tokens": 0}) is None
    assert cs_mod.NKContextSentry._extract_actual_tokens_from_record({"actual_context_tokens": 777}) == 777
    assert cs_mod.NKContextSentry._extract_actual_tokens_from_record({"usage": {"input_tokens": 300, "cache_read_tokens": 200}}) == 500

    assert qbm_mod._extract_numeric_metric({"a": True, "b": {"value": 42}}, "x", "a", "b") == 42.0
    assert qbm_mod._extract_numeric_metric({}, "missing") is None
    assert qbm_mod._is_valid_gt68_recalibration({}) is False
    ws_q = tmp_path / "qbm_ws"
    for rel_s in (".agents/skills/S1", ".agents/skills/S2", ".staging/.agents/skills/S3"):
        (ws_q / rel_s).mkdir(parents=True)
        (ws_q / rel_s / "SKILL.md").write_text("# S\n", encoding="utf-8")
    (ws_q / ".staging" / ".deleted_files.json").write_text("{bad_json", encoding="utf-8")
    m_q = qbm_mod.measure_live_pytest_metrics(ws_q)
    assert m_q["unit_tests_total"] == 0 and m_q["skills_audited"] == 3
    (ws_q / ".staging" / ".deleted_files.json").write_text('{"deleted_files": [".agents/skills/S1/SKILL.md"]}', encoding="utf-8")
    assert qbm_mod.measure_live_pytest_metrics(ws_q)["skills_audited"] == 2
