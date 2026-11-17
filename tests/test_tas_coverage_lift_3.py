#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test unitari TAS Wave 3 per copertura reale su ast_exports, lazy_bridge, facade_resolver e PIDFileLock."""

from __future__ import annotations

import ast
import json
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict

import pytest

_BASE_DIR = Path(__file__).resolve().parent.parent
_HUB_ROOT = _BASE_DIR.parent if _BASE_DIR.name == ".staging" else _BASE_DIR
_PROD_SCRIPTS = _HUB_ROOT / "scripts"
_STG_SCRIPTS = _HUB_ROOT / ".staging" / "scripts"
for _cand in (_PROD_SCRIPTS, _STG_SCRIPTS):
    if _cand.is_dir() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))


@pytest.mark.fast
def test_pid_file_lock_winerror_retries_and_adaptive_default_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica retry PermissionError su acquire/release e timeout adattivo PIDFileLock."""
    import _internal.nk_common.ledger_lock_io as lio

    lock_path = tmp_path / "winretry.lock"
    lk = lio.PIDFileLock(lock_path, stale_timeout_sec=30.0)
    assert lk.acquire(timeout_sec=0.1) is True

    calls = {"unlink": 0}
    orig_unlink = Path.unlink

    def _flaky_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path and calls["unlink"] == 0:
            calls["unlink"] += 1
            raise PermissionError("WinError 32 simulated lock contention")
        orig_unlink(self, missing_ok=missing_ok)

    with monkeypatch.context() as mp:
        mp.setattr(Path, "unlink", _flaky_unlink)
        mp.setattr(lio.time, "sleep", lambda _s: None)
        lk.release()
    assert calls["unlink"] == 1 and not lock_path.exists()

    lock_path.write_text(
        json.dumps({"pid": 1, "nonce": "n", "timestamp": time.time()}),
        encoding="utf-8",
    )
    reads = {"n": 0}
    orig_read_text = Path.read_text

    def _flaky_read(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == lock_path and reads["n"] == 0:
            reads["n"] += 1
            raise PermissionError("WinError 32 simulated read contention")
        return orig_read_text(self, *args, **kwargs)

    with monkeypatch.context() as mp:
        mp.setattr(Path, "read_text", _flaky_read)
        mp.setattr(lio.PIDFileLock, "_is_pid_alive", staticmethod(lambda _p: True))
        mp.setattr(lio.time, "sleep", lambda _s: None)
        assert lk.acquire(timeout_sec=0.05) is False
    assert reads["n"] == 1


@pytest.mark.fast
def test_ast_exports_full_resolution_and_class_collection(tmp_path: Path) -> None:
    """Copre ast_exports: statement modulo, _LAZY_EXPORT_MAP, moduli relativi e collect classi."""
    import _internal.nk_common.ast_exports as ae

    sample_src = """
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    class OnlyTypeChecking: pass
if True:
    _LAZY_EXPORT_MAP: dict = {
        "Alpha": ("_internal.pkg.alpha", "AlphaCls"),
        "Beta": "_internal.pkg.beta:BetaCls",
        "Gamma": "_internal.pkg.gamma",
        "": "ignored",
        "Empty": "   ",
        "BadColon": ":Sym",
        "BadVal": 123,
    }
else:
    _ALT = 0
try:
    with dummy():
        _UNUSED = 1
except Exception:
    pass
class DirectFacade: pass
"""
    tree = ast.parse(sample_src)
    exp_map = ae.extract_lazy_export_map(tree)
    assert exp_map == {
        "Alpha": "_internal.pkg.alpha",
        "Beta": "_internal.pkg.beta",
        "Gamma": "_internal.pkg.gamma",
    }
    assert ae.group_lazy_exports_by_module(tree)["_internal.pkg.beta"] == {"BetaCls"}
    pairs = ae.group_lazy_export_pairs_by_module(tree)
    assert ("Gamma", "Gamma") in pairs["_internal.pkg.gamma"]

    stg_scripts = tmp_path / ".staging" / "scripts"
    pkg_dir = stg_scripts / "_internal" / "pkg"
    sub_dir = pkg_dir / "nested"
    sub_dir.mkdir(parents=True)
    (pkg_dir / "alpha.py").write_text("class AlphaCls: pass\n", encoding="utf-8")
    (pkg_dir / "beta.py").write_text("class BetaCls: pass\n", encoding="utf-8")
    (pkg_dir / "gamma.py").write_text("class Gamma: pass\nclass _Hidden: pass\n", encoding="utf-8")
    (sub_dir / "__init__.py").write_text(
        "from ..gamma import *\nfrom . import deep\n", encoding="utf-8"
    )
    (sub_dir / "deep.py").write_text("class DeepCls: pass\n", encoding="utf-8")
    facade_file = stg_scripts / "facade_demo.py"
    facade_file.write_text(
        "from . import _internal\n"
        "from scripts._internal.pkg.nested import DeepCls as PublicDeep\n"
        "from _internal.pkg.beta import BetaCls\n"
        "import os\n"
        "from external_pkg import Ext\n"
        "class OwnClass: pass\n"
        "_LAZY_EXPORT_MAP = {\n"
        '    "AlphaAlias": ("scripts._internal.pkg.alpha", "AlphaCls"),\n'
        '    "SkipExt": "ext.mod:Foo",\n'
        '    "MissingMod": "_internal.pkg.nope:NoCls",\n'
        "}\n",
        encoding="utf-8",
    )

    roots = ae.resolve_scripts_search_roots(facade_file)
    assert stg_scripts.resolve() == roots[0].resolve()
    assert ae.resolve_dotted_module_file("..beta", roots, cur_dir=sub_dir) is not None
    assert ae.resolve_dotted_module_file("..alpha", roots, cur_dir=None) is None
    assert ae.resolve_dotted_module_file("....", roots, cur_dir=pkg_dir) is None
    assert ae.resolve_dotted_module_file("", roots, cur_dir=pkg_dir) is None
    assert ae.resolve_dotted_module_file("scripts._internal.pkg.nested", roots) is not None
    assert ae.resolve_dotted_module_file("", roots, cur_dir=pkg_dir, level=1, alias_name="gamma") is not None
    assert ae.resolve_dotted_module_file("", [tmp_path / "other"], cur_dir=pkg_dir, level=1, alias_name="gamma") is None

    other_file = tmp_path / "misc" / "standalone.py"
    other_file.parent.mkdir(parents=True)
    other_file.write_text("x=1\n", encoding="utf-8")
    assert ae.resolve_scripts_search_roots(other_file) == [other_file.parent]

    ftree = ast.parse(facade_file.read_text(encoding="utf-8"))
    memo: Dict[Path, set] = {}
    classes = ae.collect_exported_class_names(ftree, facade_file, roots, _memo=memo)
    assert {"OwnClass", "BetaCls", "AlphaAlias"} <= set(classes)
    classes_cached = ae.collect_exported_class_names(ftree, facade_file, roots, _memo=memo)
    assert sorted(classes_cached) == sorted(classes)


@pytest.mark.fast
def test_rsi_lazy_bridge_fallback_and_facade_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre lazy_bridge: fallback_reconfigure, fallback_load_ntt, facade_* e hook registry."""
    import _internal.rsi_convergence_engine.lazy_bridge as lb

    stg_s = tmp_path / ".staging" / "scripts"
    prod_s = tmp_path / "scripts"
    stg_s.mkdir(parents=True)
    prod_s.mkdir(parents=True)
    (stg_s / "ast_guard_validator.py").write_text(
        "class ASTGuardValidator:\n    @staticmethod\n    def check_sast_constructs(*_a): return []\n",
        encoding="utf-8",
    )
    (stg_s / "nk_transcript_tools.py").write_text(
        "def verify_ste100_compliance(*_a, **_kw): return {'passed': True}\n"
        "def verify_report_grounding(*_a, **_kw): return {'passed': True}\n",
        encoding="utf-8",
    )

    orig_hooks = dict(lb._HOOKS)
    orig_fb = dict(lb._FALLBACK_STATE)
    try:
        lb._HOOKS.clear()
        lb._FALLBACK_STATE.update(
            {
                "streams_reconfigured": False,
                "hsm_cls": None,
                "hsm_loaded": False,
                "agv_cls": None,
                "agv_loaded": False,
                "ste100_fn": None,
                "grounding_fn": None,
            }
        )
        lb.fallback_reconfigure_streams()
        lb.fallback_reconfigure_streams()

        ns_stream: Dict[str, Any] = {}
        lb.facade_reconfigure_streams(ns_stream)
        lb.facade_reconfigure_streams(ns_stream)
        assert ns_stream["_STREAMS_RECONFIGURED"] is True

        ntt_mod = lb.fallback_load_ntt_module(scripts_dir=stg_s, workspace_root=tmp_path)
        assert hasattr(ntt_mod, "verify_ste100_compliance")
        assert lb.fallback_load_ntt_module(scripts_dir=tmp_path / "none1", workspace_root=tmp_path / "none2") is None

        ns: Dict[str, Any] = {
            "_SCRIPT_DIR": stg_s,
            "_PROD_SCRIPTS": prod_s,
            "_workspace_root": tmp_path,
        }
        with monkeypatch.context() as mp:
            for k in ("ast_guard_validator", "nk_transcript_tools"):
                mp.delitem(sys.modules, k, raising=False)
            agv_cls = lb.facade_get_ast_guard_validator(ns)
            assert agv_cls is not None and lb.facade_get_ast_guard_validator(ns) is agv_cls
            ste_fn = lb.facade_get_ste100_validator(ns, lambda: ntt_mod)
            assert callable(ste_fn) and lb.facade_get_ste100_validator(ns, lambda: ntt_mod) is ste_fn
            grd_fn = lb.facade_get_report_grounding_validator(ns, lambda: ntt_mod)
            assert callable(grd_fn) and lb.facade_get_report_grounding_validator(ns, lambda: ntt_mod) is grd_fn

        ns_err = {"_SCRIPT_DIR": tmp_path / "x", "_PROD_SCRIPTS": tmp_path / "x"}
        with monkeypatch.context() as mp:
            mp.setitem(sys.modules, "nk_transcript_tools", types.SimpleNamespace())
            mp.setitem(sys.modules, "scripts.nk_transcript_tools", types.SimpleNamespace())
            with pytest.raises((ImportError, RuntimeError)):
                lb.facade_get_ste100_validator(ns_err, lambda: None)
            assert lb.facade_get_report_grounding_validator(ns_err, lambda: None) is None

        hsm_cls = lb.get_healing_snapshot_manager_cls()
        assert lb.get_healing_snapshot_manager_cls() is hsm_cls
        assert lb.get_ast_guard_validator() is not None
        assert lb.get_ast_guard_validator() is lb._FALLBACK_STATE["agv_cls"]
        assert callable(lb.get_ste100_validator())
        assert callable(lb.get_ste100_validator())
        assert lb.get_report_grounding_validator() is not None
        assert lb.get_report_grounding_validator() is lb._FALLBACK_STATE["grounding_fn"]
        lb.get_reconfigure_streams()

        ensured: Dict[str, Any] = {}
        lb.facade_ensure_exports_loaded(
            ensured,
            {"PathCls": ("pathlib", "Path")},
            reconfigure_fn=lambda: None,
            hsm_fn=lambda: "HSM",
            agv_fn=lambda: "AGV",
            ste100_fn=lambda: "STE",
            grounding_fn=lambda: "GRD",
        )
        assert ensured["PathCls"] is Path
        assert lb.get_healing_snapshot_manager_cls() == "HSM"
        assert lb.get_ast_guard_validator() == "AGV"
        assert lb.get_ste100_validator() == "STE"
        assert lb.get_report_grounding_validator() == "GRD"
        lb.get_reconfigure_streams()
    finally:
        lb._HOOKS.clear()
        lb._HOOKS.update(orig_hooks)
        lb._FALLBACK_STATE.clear()
        lb._FALLBACK_STATE.update(orig_fb)


@pytest.mark.fast
def test_facade_resolver_internal_deps_and_lazy_edges(tmp_path: Path) -> None:
    """Copre facade_resolver: estrazione simboli _internal, import relativi e cache deps."""
    import _internal.ast_repo_mapper.facade_resolver as fr

    ws = tmp_path / "ws"
    s_root = ws / "scripts"
    int_pkg = s_root / "_internal" / "demo"
    int_pkg.mkdir(parents=True)
    (s_root / "_internal" / "__init__.py").write_text("", encoding="utf-8")
    (int_pkg / "__init__.py").write_text("", encoding="utf-8")
    (int_pkg / "leaf.py").write_text(
        "class LeafBox:\n    def run(self) -> int:\n        return 1\ndef helper(): return 2\n",
        encoding="utf-8",
    )
    (int_pkg / "mid.py").write_text(
        "from .leaf import LeafBox\n"
        "_LAZY_EXPORT_MAP = {'hlp': ('_internal.demo.leaf', 'helper'), 'ext': 'json:loads'}\n"
        "def mid_fn(): return LeafBox().run()\n",
        encoding="utf-8",
    )
    facade_p = s_root / "demo_facade.py"
    facade_src = (
        "from _internal.demo.mid import mid_fn\n"
        "from _internal.demo.leaf import *\n"
        "from json import dumps\n"
        "_LAZY_EXPORT_MAP = {\n"
        "    'LeafBox': ('_internal.demo.leaf', 'LeafBox'),\n"
        "    'hlp': ('_internal.demo.mid', 'hlp'),\n"
        "    'skip': 'pathlib:Path',\n"
        "}\n"
        "def facade_api(): return mid_fn()\n"
    )
    facade_p.write_text(facade_src, encoding="utf-8")

    nodes, edges, calls, deps = fr.extract_python_module_symbols(
        facade_p, "scripts/demo_facade.py", facade_src, root_dir=ws
    )
    names = {n.name for n in nodes}
    assert {"facade_api", "mid_fn", "LeafBox", "helper"} <= names
    assert isinstance(edges, list) and isinstance(calls, dict)
    assert len(deps) >= 2
    assert fr.internal_deps_still_valid({"internal_deps": deps}) is True
    assert fr.internal_deps_still_valid({"internal_deps": [["bad_len"]]}) is False
    assert fr.internal_deps_still_valid({"internal_deps": [[str(ws / "missing.py"), 1.0, 1]]}) is False
    changed_deps = [[deps[0][0], deps[0][1] + 99.0, deps[0][2]]]
    assert fr.internal_deps_still_valid({"internal_deps": changed_deps}) is False


@pytest.mark.fast
def test_handoff_explicit_conversation_id_never_discovers_foreign_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Impedisce che --conversation-id assente erediti trascritti di altre sessioni."""
    import _internal.nk_session_handoff.cli as handoff_cli
    import nk_session_handoff as hm

    ws = tmp_path / "isolated_conv"
    (ws / "scripts").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 10}}),
        encoding="utf-8",
    )
    called = {"discover": 0}

    def _boom_discover() -> str:
        called["discover"] += 1
        raise AssertionError("_discover_default_transcript non deve essere chiamato")

    with monkeypatch.context() as mp:
        mp.setattr(hm, "locate_transcript", lambda **_kw: ({"transcript_path": ""}, 0))
        mp.setattr(handoff_cli, "_discover_default_transcript", _boom_discover)
        rc = hm.main(["--root", str(ws), "--conversation-id", "missing_conv_99", "--turn", "2", "--auto-checkpoint"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and called["discover"] == 0 and out["status"] == "CHECKPOINT_SAVED"
