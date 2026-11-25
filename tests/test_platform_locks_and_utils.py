# -*- coding: utf-8 -*-
"""
Suite piattaforma DOM-02/DOM-03/DOM-04: nk_common, Catalog, Scaffolder, Transcript, Hook, RSI e 2PC.
Modulo: tests/test_platform_locks_and_utils.py.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module, load_script_by_relpath
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module, load_script_by_relpath

probe_mod = load_nk_script_module("env_capability_probe")
scaf_mod = load_nk_script_module("external_project_scaffolder")
tr_mod = load_nk_script_module("nk_transcript_tools")
hook_mod = load_nk_script_module("nk_hook_gate")
guard_mod = load_nk_script_module("ast_guard_validator")
rsi_mod = load_nk_script_module("rsi_convergence_engine")
dast_mod = load_nk_script_module("dast_sandbox_runner")
w2pc_mod = load_nk_script_module("win32_2pc_engine")
runner_mod = load_nk_script_module("platform_runner")


def _assert_nk_common_io_guards(tmp_path: Path) -> None:
    """Verifica win_long_path, retryable errors, unlink_with_retry e atomic_write guards."""
    from _internal.nk_common import io as nc_io

    short_p = tmp_path / "short.txt"
    assert (nc_io.win_long_path(short_p), nc_io.win_long_path(Path("\\\\?\\" + str(short_p)))) == (short_p, Path("\\\\?\\" + str(short_p)))
    assert str(nc_io.win_long_path(tmp_path / ("d_" * 120) / "deep.txt")).startswith("\\\\?\\") is (os.name == "nt")
    win32_e, win2_e = OSError("sharing"), OSError("missing")
    win32_e.winerror, win2_e.winerror = 32, 2  # type: ignore[attr-defined]
    assert [nc_io._is_retryable_os_error(e) for e in (win32_e, win2_e, PermissionError("d"), OSError(13, "e"))] == [True, False, True, True]
    assert nc_io.unlink_with_retry(tmp_path / "never_existed.txt") is True

    non_empty = tmp_path / "dir_keep"
    non_empty.mkdir()
    (non_empty / "inner.txt").write_text("x", encoding="utf-8")
    assert nc_io.unlink_with_retry(non_empty, delays=(0.001,), raise_on_error=False) is False
    with pytest.raises(OSError):
        nc_io.unlink_with_retry(non_empty, delays=(0.0,), raise_on_error=True)

    file_p = tmp_path / "file_parent"
    file_p.write_text("x", encoding="utf-8")
    compact_j = tmp_path / "compact.json"
    assert (nc_io.atomic_write_text(tmp_path / "blk.txt", "x", reparse_check=lambda p: p.name == "blk.txt"), nc_io.atomic_write_text(tmp_path / "blk_dir" / "f.txt", "x", reparse_check=lambda p: p.name == "blk_dir")) == ((False, "reparse_guard"), (False, "reparse_guard"))
    assert (nc_io.atomic_write_bytes(tmp_path / "no_parent" / "f.bin", b"1", ensure_parent=False)[1].startswith("open_tmp_error:"), nc_io.atomic_write_text(file_p / "child.txt", "y")[1].startswith("mkdir_error:"), nc_io.atomic_write_bytes(non_empty, b"z", delays=(0.0,))[0]) == (True, True, False)
    assert (nc_io.atomic_write_json(compact_j, {"b": 2, "a": 1}, indent=None, sort_keys=True, separators=(",", ":"), fsync_data=False), compact_j.read_text(encoding="utf-8")) == ((True, None), '{"a":1,"b":2}')


@pytest.mark.integration
def test_nk_common_primitives_io_guards_and_long_path(tmp_path: Path) -> None:
    """Verifica primitive _internal.nk_common: paths, io, long_path, atomic_write, mutex, guards e linter."""
    from _internal.nk_common import constants as nc_consts, io as nc_io, paths as nc_paths, prompt_linter_core as nc_lint, transcript_guards as nc_guards, win32_mutex as nc_mutex

    assert len(nc_consts.HALLUCINATED_SCRIPT_DENYLIST) == 32
    assert (Path(nc_paths.resolve_scripts_dir(str(WORKSPACE_ROOT / ".staging" / "scripts" / "_internal" / "nk_common" / "paths.py"))).name, Path(nc_paths.resolve_workspace_root(str(WORKSPACE_ROOT / ".staging" / "scripts" / "nk_session_bootstrap.py"))), Path(nc_paths.resolve_workspace_root(str(WORKSPACE_ROOT / "scripts" / "_internal" / "nk_common" / "paths.py")))) == ("scripts", WORKSPACE_ROOT.resolve(), WORKSPACE_ROOT.resolve())

    io_target = tmp_path / "nc_io_test.json"
    ok_w, err_w = nc_io.atomic_write_json(io_target, {"status": "OK", "count": 2})
    assert (ok_w, err_w, json.loads(io_target.read_text(encoding="utf-8")), nc_io.unlink_with_retry(io_target), io_target.exists()) == (True, None, {"status": "OK", "count": 2}, True, False)
    assert [nc_mutex.is_win32_handle_valid(v) for v in (None, -1, 42)] == [sys.platform != "win32", sys.platform != "win32", True]
    sub_tp = tmp_path / "nc_sub.jsonl"
    sub_tp.write_text(json.dumps({"step_index": 0, "source": "SYSTEM", "content": "<subagent_reminder>ok"}) + "\n", encoding="utf-8")
    assert (nc_guards.has_compaction_candidate_bytes(b'{"type": "CHECKPOINT"}'), nc_guards.is_verified_compaction({"source": "SYSTEM", "type": "CHECKPOINT"}), nc_guards.is_verified_compaction({"source": "MODEL", "type": "CHECKPOINT"}), nc_guards.is_subagent_transcript_head(sub_tp, max_non_empty=5)) == (True, True, False, True)
    lint_out = nc_lint.evaluate_ap_rules("!diretto\nFase 1: modifica src_app/x.py\nFase 2: continua\n")
    assert (lint_out["passed"], lint_out["violation_count"] == len(lint_out["violations"]), all({"code", "id", "severity", "message", "msg"}.issubset(v.keys()) for v in lint_out["violations"])) == (False, True, True)
    _assert_nk_common_io_guards(tmp_path)


def _assert_facade_boot_and_init(tmp_path: Path) -> None:
    """Verifica facade_boot.py su _prepend_pkg_overlay, resolve_facade_attr e init_nk_facade."""
    from _internal.nk_common import facade_boot as fb

    pkg_root = tmp_path / "pkg_root"
    prod_pkg, stg_pkg = pkg_root / "prod_ov" / "demo_ov_pkg", pkg_root / "stg_ov" / "demo_ov_pkg"
    prod_pkg.mkdir(parents=True)
    stg_pkg.mkdir(parents=True)
    (prod_pkg / "__init__.py").write_text("TAG = 'prod'\n", encoding="utf-8")
    (stg_pkg / "__init__.py").write_text("TAG = 'stg'\n", encoding="utf-8")
    orig_path = list(sys.path)
    try:
        fb._prepend_pkg_overlay("demo_ov_pkg", str(tmp_path / "missing_dir"))
        fb._prepend_pkg_overlay("missing_pkg_xyz_999", str(stg_pkg))
        sys.path.insert(0, str(pkg_root / "prod_ov"))
        ov_mod = importlib.import_module("demo_ov_pkg")
        fb._prepend_pkg_overlay("demo_ov_pkg", str(stg_pkg), str(prod_pkg))
        ov_mod.__path__.reverse()
        fb._prepend_pkg_overlay("demo_ov_pkg", str(stg_pkg), str(prod_pkg))
        sys.modules["_nk_int_obj"] = "plain_str"  # type: ignore[assignment]
        assert (ov_mod.__path__[0], fb.resolve_facade_attr(["missing_mod_x", "_nk_int_obj", "json"], "loads"), fb.resolve_facade_attr(["json"], "nonexistent_attr_z", "fb_val")) == (str(stg_pkg), json.loads, "fb_val")
    finally:
        sys.path[:] = orig_path
        sys.modules.pop("demo_ov_pkg", None)
        sys.modules.pop("_nk_int_obj", None)

    base = tmp_path / "mini_ws"
    stg_s, prod_s = base / ".staging" / "scripts", base / "scripts"
    for r_s in (stg_s, prod_s):
        for sub in ("_internal", "_internal/nk_common", "_internal/demo_pkg"):
            (r_s / sub).mkdir(parents=True)
            (r_s / sub / "__init__.py").write_text("", encoding="utf-8")
    stg_cli, prod_cli = stg_s / "demo_cli.py", prod_s / "demo_cli.py"
    stg_cli.write_text("VAL = 'stg'\n", encoding="utf-8")
    prod_cli.write_text("VAL = 'prod'\n", encoding="utf-8")
    orig_path, saved = list(sys.path), {k: sys.modules.get(k) for k in list(sys.modules) if k == "_internal" or k.startswith("_internal.")}
    try:
        sys.modules["_internal"] = importlib.import_module("_internal")
        assert (Path(fb.init_nk_facade(str(stg_cli), pkg="demo_pkg")), sys.path[0], fb.init_nk_facade(str(prod_cli), pkg="demo_pkg")) == (prod_s, str(stg_s), str(prod_s))
    finally:
        sys.path[:] = orig_path
        sys.modules.update({k: v for k, v in saved.items() if v is not None})
        for k in [k for k in list(sys.modules) if (k == "_internal" or k.startswith("_internal.")) and k not in saved]:
            sys.modules.pop(k, None)


def _assert_ast_exports_branches(tmp_path: Path) -> None:
    """Verifica ast_exports.py su lazy map, path e collect_exported_class_names."""
    from _internal.nk_common import ast_exports as ae

    tree = ast.parse("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    _LAZY_EXPORT_MAP = {'IgnoredTC': 'x.y:Z'}\ntry:\n    with open('x') as _f:\n        pass\nexcept Exception:\n    _LAZY_EXPORT_MAP: dict[str, object] = {'Alpha': 'pkg.a:OrigAlpha', 'Beta': ('pkg.a', 'Beta'), 'Gamma': 'pkg.b', 'Empty': '', 'Bad': 123}\n")
    assert ae.extract_lazy_export_specs(tree) == {"Alpha": ("pkg.a", "OrigAlpha"), "Beta": ("pkg.a", "Beta"), "Gamma": ("pkg.b", "Gamma")}
    assert (ae.extract_lazy_export_map(tree)["Alpha"], ae.group_lazy_exports_by_module(tree)["pkg.a"], ae.group_lazy_export_pairs_by_module(tree)["pkg.a"]) == ("pkg.a", {"OrigAlpha", "Beta"}, [("OrigAlpha", "Alpha"), ("Beta", "Beta")])

    ws = tmp_path / "ast_ws"
    stg_pkg, prod_pkg, sch_dir = ws / ".staging" / "scripts" / "_internal" / "demo_pkg", ws / "scripts" / "_internal" / "demo_pkg", ws / "scripts" / "schemas"
    for d in (stg_pkg, prod_pkg, sch_dir):
        d.mkdir(parents=True)
    (stg_pkg / "__init__.py").write_text("", encoding="utf-8")
    (stg_pkg / "staged_cls.py").write_text("class StagedCls:\n    pass\n", encoding="utf-8")
    (prod_pkg / "prod_cls.py").write_text("class ProdCls:\n    pass\nclass _Hidden:\n    pass\n", encoding="utf-8")
    (sch_dir / "schema_cls.py").write_text("class SchemaCls:\n    pass\n", encoding="utf-8")
    facade_f = ws / ".staging" / "scripts" / "demo_facade.py"
    facade_src = "from _internal.demo_pkg.staged_cls import StagedCls as RenamedStaged\nfrom _internal.demo_pkg.prod_cls import *\nfrom scripts.schemas.schema_cls import SchemaCls\nclass DirectCls:\n    pass\n_LAZY_EXPORT_MAP = {'LazySchema': 'schemas.schema_cls:SchemaCls'}\n"
    facade_f.write_text(facade_src, encoding="utf-8")
    roots = ae.resolve_scripts_search_roots(facade_f)
    assert (roots, ae.resolve_dotted_module_file(".staged_cls", roots, cur_dir=stg_pkg), ae.resolve_dotted_module_file("scripts._internal.demo_pkg", roots), set(ae.collect_exported_class_names(ast.parse(facade_src), facade_f))) == ([ws / ".staging" / "scripts", ws / "scripts"], (stg_pkg / "staged_cls.py").resolve(), (stg_pkg / "__init__.py").resolve(), {"DirectCls", "RenamedStaged", "ProdCls", "SchemaCls", "LazySchema"})


@pytest.mark.fast
def test_nk_common_facade_boot_ast_exports_and_ledger_lock(tmp_path: Path) -> None:
    """Verifica facade_boot, ast_exports (lazy map/classi) e ledger_lock_io recovery/timeout."""
    from _internal.nk_common.ledger_lock_io import PIDFileLock

    _assert_facade_boot_and_init(tmp_path)
    _assert_ast_exports_branches(tmp_path)
    assert (PIDFileLock._is_pid_alive(0), PIDFileLock._is_pid_alive(os.getpid())) == (False, True)
    dead_l, stale_l, corrupt_l = tmp_path / "dead.lock", tmp_path / "stale.lock", tmp_path / "corrupt.lock"
    dead_l.write_text(json.dumps({"pid": 9999999, "nonce": "n1", "timestamp": time.time()}), encoding="utf-8")
    lk_d = PIDFileLock(dead_l, stale_timeout_sec=30.0)
    assert lk_d.acquire(timeout_sec=0.5) is True
    lk_d.release()
    stale_l.write_text(json.dumps({"pid": os.getpid(), "nonce": "old", "timestamp": time.time() - 120.0}), encoding="utf-8")
    with PIDFileLock(stale_l, stale_timeout_sec=0.5, acquire_timeout_sec=0.5) as held:
        assert held.acquired is True
    corrupt_l.write_text("{bad_json", encoding="utf-8")
    os.utime(corrupt_l, (time.time() - 10.0, time.time() - 10.0))
    lk_c = PIDFileLock(corrupt_l, stale_timeout_sec=2.0)
    assert lk_c.acquire(timeout_sec=0.5) is True
    corrupt_l.write_text(json.dumps({"pid": os.getpid(), "nonce": "foreign", "timestamp": time.time()}), encoding="utf-8")
    lk_c.release()
    assert (dead_l.exists(), corrupt_l.exists()) == (False, True)
    with pytest.raises(TimeoutError):
        with PIDFileLock(corrupt_l, stale_timeout_sec=30.0, acquire_timeout_sec=0.05):
            assert corrupt_l.exists()


@pytest.mark.fast
def test_nk_common_catalog_loader_branches(tmp_path: Path) -> None:
    """Copre branch di catalog_loader.py: cache, shard staging/prod, rehydrate e fallback."""
    from _internal.nk_common import catalog_loader as cl

    cl.clear_catalog_cache()
    assert (cl._resolve_base_root(None).is_dir(), cl.load_domain_shard("", tmp_path), cl.load_registry_manifest(tmp_path / "missing_ws")) == (True, {}, {})
    ws = tmp_path / "cat_ws"
    stg_sh, prod_sh = ws / ".staging" / "nk_genome" / "shards", ws / "nk_genome" / "shards"
    stg_sh.mkdir(parents=True)
    prod_sh.mkdir(parents=True)
    (prod_sh / "DOM-00.json").write_text(json.dumps({"global_hygiene_profile": {"strict": True}, "docs_and_setup_index": {"a": 1}, "milestone_anchor_id": "M-GEN"}), encoding="utf-8")
    (prod_sh / "DOM-01.json").write_text(json.dumps({"domain": {"domain_id": "DOM-01", "name": "PROD"}}), encoding="utf-8")
    (stg_sh / "DOM-01.json").write_text(json.dumps({"domain": {"domain_id": "DOM-01", "name": "GOV", "primary_skill": "NK-Orch", "keywords": ["gov"]}, "intent_dispatch_table": {"_routes": [["NK-Orch", "mode_b", ["kw1"]]], "kw2": "mode_a", "kw3": {"domain_id": "DOM-01", "recommended_mode": "mode_c"}}, "skills_index": {"NK-Orch": {"sector": "GOV"}}, "scripts_index": {"s.py": {}}, "native_agents_index": {"NK-Spec": {}}}), encoding="utf-8")
    (stg_sh / "DOM-02.json").write_text(json.dumps({"skills_index": {"NK-B": {}}, "intent_dispatch_table": {"kw_s": "mode_d"}}), encoding="utf-8")
    (stg_sh / "DOM-03.json").write_text("[1, 2]", encoding="utf-8")
    (stg_sh / "DOM-04.json").write_text("{corrupt", encoding="utf-8")
    (stg_sh / "DOM-06.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

    assert (cl.load_domain_shard("DOM-01.json", ws)["domain"]["name"], cl.load_domain_shard("DOM-03", ws), cl.load_domain_shard("DOM-04", ws), set(cl.load_all_domain_shards(ws).keys())) == ("GOV", {}, {}, {"DOM-00", "DOM-01", "DOM-02", "DOM-06"})
    slim = {"domains": {"DOM-02": {"name": "FALLBACK_NAME"}}, "shards": {"DOM-00": "shards/DOM-00.json", "DOM-01": "shards/DOM-01.json", "DOM-02": "shards/DOM-02.json", "DOM-05": "shards/missing.json", "DOM-06": "shards/DOM-06.json"}}
    (ws / ".staging" / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps(slim), encoding="utf-8")
    rehyd = cl.load_registry_manifest(ws, rehydrate=True)
    assert ("skills_index" in cl.load_registry_manifest(ws, rehydrate=False), rehyd["milestone_anchor_id"], rehyd["release_meta"]["version"], rehyd["skills_index"]["NK-B"]["domain_name"], rehyd["intent_dispatch_table"]["kw1"]["primary_agent"], rehyd["intent_dispatch_table"]["kw2"]["recommended_mode"], cl._rehydrate_from_shards({"plain": True}, ws)) == (False, "M-GEN", "1.0.0", "FALLBACK_NAME", "NK-Orch", "mode_a", {"plain": True})


@pytest.mark.integration
def test_env_probe_and_external_scaffolder(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verifica sonda env GT-09, scaffolder isolation/Pentad, PATCH_NOTES, dry_run e retrofit."""
    exp_f = tmp_path / "probe_exp.json"
    assert (call_script_main_captured(probe_mod, ["--export", str(exp_f)])[0], exp_f.is_file()) == (0, True)
    data = json.loads(exp_f.read_text(encoding="utf-8"))
    exp_tot = len(probe_mod.STANDARD_MODULES_TO_PROBE) + len(probe_mod.THIRD_PARTY_MODULES_TO_PROBE)
    assert (data["python"]["version_major"], data["standard_modules"]["sqlite3"]["available"], len(probe_mod.format_human_readable(data)) > 40, probe_mod.check_module_availability("fictitious_xyz_98")["available"], data["summary"]["total_probed"], exp_tot, data["summary"]["all_core_hub_available"], data["summary"]["status"]) == (3, True, True, False, 15, 15, True, "PASS")
    assert (call_script_main(probe_mod, ["--check-module", "json", "--json"], monkeypatch), json.loads(capsys.readouterr().out)["available"]) == (0, True)

    forbidden_t = WORKSPACE_ROOT / f"forbidden_internal_app_{uuid.uuid4().hex[:6]}"
    with pytest.raises(ValueError) as exc_i:
        scaf_mod.ExternalProjectScaffolder(project_name="ForbiddenApp", target_dir=forbidden_t)
    assert ("RULE-PROJECT-ISOLATION" in str(exc_i.value), forbidden_t.exists()) == (True, False)
    with pytest.raises(ValueError):
        scaf_mod.ExternalProjectScaffolder("../bad", tmp_path / "NK_External_Projects" / "Bad")

    ext_dir = tmp_path / "ExternalCleanProject"
    assert scaf_mod.ExternalProjectScaffolder(project_name="ExternalCleanProject", target_dir=ext_dir).scaffold()["status"] == "SUCCESS"
    baseline = json.loads((ext_dir / "nk_tracking" / "quality_baseline.json").read_text(encoding="utf-8"))
    assert (all((ext_dir / rel).exists() for rel in ("nk_genome/concept_map.md", "nk_genome/structural_tree.md", "nk_genome/implementation_plan.md", "nk_genome/repo_map.md", "nk_genome/PATCH_NOTES.md", "src/core/__init__.py", "tests/test_ast_purity.py")), (ext_dir / "nk_genome" / "changelog.md").exists(), baseline["metrics"]["unit_tests_total"]["value"], baseline["metrics"]["unit_tests_total"]["direction"]) == (True, False, 1, "higher_is_better")

    ext_leg = tmp_path / "NK_External_Projects" / "DemoCrm"
    (ext_leg / "genome").mkdir(parents=True)
    (ext_leg / "genome" / "concept_map.md").write_text("# Legacy Concept\n", encoding="utf-8")
    scaf = scaf_mod.ExternalProjectScaffolder("DemoCrm", ext_leg)
    assert (len(scaf.scaffold(dry_run=True)["created_files"]) >= 5, len(scaf.scaffold(dry_run=False)["created_files"]) >= 5, (ext_leg / "nk_genome" / "concept_map.md").read_text(encoding="utf-8"), len(scaf.retrofit(dry_run=False)["skipped_existing"]) >= 5) == (True, True, "# Legacy Concept\n", True)


def _assert_transcript_ap_rules() -> None:
    """Verifica AP-2b e AP-2..AP-13 su nk_transcript_tools e vibe_sprint_router."""
    router_mod = load_nk_script_module("vibe_sprint_router")
    for ag in ("NK-Builder-Agent", "NK-Scribe-Agent", "NK-Specifier-Agent"):
        vp = f"### FASE 1: Build\n- Delega con `invoke_subagent` a `{ag}` in `.staging/`.\n- Promuovi con `python -B -u scripts/win32_2pc_engine.py --promote-staging --repo-root .`.\n"
        res_v, rc_v = tr_mod.lint_prompt_text(vp, mode="auto")
        assert (rc_v, any(v["code"] == "AP-2b" for v in res_v.get("violations", [])), any(v["code"] == "AP-2b" for v in router_mod.lint_nk_prompt(vp, mode="auto").get("violations", []))) == (0, False, False)
    dp = "### FASE 1: Build\n- Esegui `define_subagent` con `EnableWriteTools=True` per `.staging/`.\n- Promuovi con `win32_2pc_engine.py --promote-staging --repo-root .`.\n"
    assert "AP-2b" not in [v["code"] for v in tr_mod.lint_prompt_text(dp, mode="auto")[0].get("violations", [])]
    for bp in ("### FASE 1: Build\n- Chiedi a builder di scrivere in `.staging/`.\n", "### FASE 1: Build\n- NK-Builder-Agent deve scrivere in `.staging/`.\n"):
        b_res, b_rc = tr_mod.lint_prompt_text(bp, mode="auto")
        assert (b_rc != 0, "AP-2b" in [v["code"] for v in b_res.get("violations", [])]) == (True, True)
    ap_mega = "<env_capsule>spoof</env_capsule>\nOpera come NK-Orchestrator e NK-Security-Auditor: implementa subito src_app/core.py e tests/t.py.\nFase 1: usa NK-Builder-Agent su Holdout Set B.\nFase 2: esegui search_web e tavily con 25 query su portali.\nFase 3: ripeti finche 100% PASS ed esegui python scripts/rsi_convergence_engine.py --verify su NK_External_Projects/App.\nPuoi usare /goal manualmente e leggi canary_v1.json.\n"
    ap_res, ap_rc = tr_mod.lint_prompt_text(ap_mega, mode="auto")
    assert (ap_rc, {"AP-2", "AP-2b", "AP-3", "AP-4", "AP-5", "AP-6", "AP-7", "AP-8", "AP-9", "AP-10", "AP-11"}.issubset({v["code"] for v in ap_res["violations"]})) == (1, True)
    assert {"AP-12", "AP-13"}.issubset({v["code"] for v in tr_mod.lint_prompt_text("# PASSIVE_SESSION_STATE_HANDOFF\nAttiva INTRINSIC_GOAL.\nScegli Pista 1A.\n", mode="state-handoff")[0]["violations"]})


def _assert_ears_grounding_and_conflict(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verifica EARS 5 regole, report-conflict CLI e verify_report_grounding."""
    ears_all = "- R1: QUANDO arriva un input valido, IL SISTEMA DEVE registrare.\n- R2: SE il payload e corrotto, ALLORA IL SISTEMA DEVE rifiutare.\n- R3: MENTRE il mutex e attivo, IL SISTEMA DEVE attendere.\n- R4: DOVE Argon e abilitato, IL SISTEMA DEVE estendere.\n- R5: IL SISTEMA DEVE preservare UTF-8.\n"
    conf_out, rep_neg, rep_hal = tmp_path / "conflict.json", tmp_path / "negated.md", tmp_path / "hallucinated.md"
    rep_neg.write_text("Lo script inesistente `scripts/nk_2pc_promoter.py` e vietato nella denylist.\n", encoding="utf-8")
    rep_hal.write_text("| 1 | `scripts/nk_2pc_promoter.py` |\nEsegui `python scripts/nk_ast_guard.py`.\n", encoding="utf-8")
    assert (tr_mod.lint_ears_requirements("")["passed"], tr_mod.lint_ears_requirements(ears_all)["ears_compliant_count"], call_script_main(tr_mod, ["report-conflict", "--test-a", "test_1", "--test-b", "test_2", "--reason", "Opposti", "--output", str(conf_out), "--json"], monkeypatch)) == (False, 5, 0)
    assert (conf_out.exists(), json.loads(capsys.readouterr().out)["status"], [tr_mod.verify_report_grounding(p)["passed"] for p in (tmp_path / "missing_rep.md", rep_neg, rep_hal)]) == (True, "HALT_EPISTEMIC_CONFLICT", [False, True, False])


@pytest.mark.integration
def test_transcript_tools_ap2b_ste100_ears_grounding_and_lock(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica AP-2b, AP-2..AP-13, EARS, grounding, oracle_lock, brain discovery e CLI transcript_tools."""
    _assert_transcript_ap_rules()
    _assert_ears_grounding_and_conflict(tmp_path, monkeypatch, capsys)
    t_dir, ol_f = tmp_path / "ol_tests", tmp_path / "oracle_lock.json"
    t_dir.mkdir()
    (t_dir / "test_one.py").write_text("def test_1(): assert True\n", encoding="utf-8")
    (t_dir / "test_two.py").write_text("def test_2(): assert True\n", encoding="utf-8")
    tr_mod.handle_oracle_lock("freeze", t_dir, ol_f)
    (t_dir / "test_one.py").write_text("def test_1(): assert False\n", encoding="utf-8")
    (t_dir / "test_two.py").unlink()
    (t_dir / "test_three.py").write_text("def test_3(): assert True\n", encoding="utf-8")
    ol_res, ol_rc = tr_mod.handle_oracle_lock("verify", t_dir, ol_f)
    assert (ol_rc, len(ol_res["mismatches"])) == (1, 3)

    brain = tmp_path / "fake_brain"
    brain.mkdir()
    assert (tr_mod.discover_active_main_transcript(brain_dir=tmp_path / "missing_b"), tr_mod.discover_active_main_transcript(brain_dir=brain)) == (None, None)
    for i in range(26):
        cdir = brain / f"conv_sub_{i:02d}" / ".system_generated" / "logs"
        cdir.mkdir(parents=True)
        if i == 25:
            (cdir / "transcript.jsonl").write_text(json.dumps({"source": "SYSTEM", "content": "<Agent System Instructions> <subagent_reminder>"}) + "\n", encoding="utf-8")
    main_tp = brain / "conv_main_active" / ".system_generated" / "logs" / "transcript.jsonl"
    main_tp.parent.mkdir(parents=True)
    main_tp.write_text(json.dumps({"source": "USER", "step_index": 0, "content": "avvia nk hub"}) + "\n" + json.dumps({"source": "MODEL", "step_index": 1, "content": "OK"}) + "\n", encoding="utf-8")
    rc_comp, out_comp, _ = call_script_main_captured(tr_mod, ["compliance", "--conversation-id", "conv_main_active", "--brain-dir", str(brain)])
    rc_ev, out_ev, _ = call_script_main_captured(tr_mod, ["evidence", "--conversation-id", "conv_main_active", "--brain-dir", str(brain)])
    assert (tr_mod.discover_active_main_transcript(brain_dir=brain, max_age_seconds=300.0).resolve(), tr_mod.count_transcript_steps(main_tp)[:2], tr_mod.count_transcript_steps(tmp_path / "no_tr.jsonl"), tr_mod.verify_ste100_compliance("---\ntitle: Spec\nversion: 6.0.0-Carbon\n---\n# H\n| C | V |\n| --- | --- |\n| S | A |\n\n* Voce `span`.\nFrase.\n")["passed"]) == (main_tp.resolve(), (2, 2), (0, 0, 0), True)
    assert (call_script_main_captured(tr_mod, ["compliance", "--conversation-id", "nope", "--brain-dir", str(brain)])[0] != 0, call_script_main_captured(tr_mod, ["evidence", "--conversation-id", "nope", "--brain-dir", str(brain)])[0] != 0, rc_comp in (0, 1), "max_consecutive_direct_tools" in json.loads(out_comp), rc_ev, bool(out_ev.strip())) == (True, True, True, True, 0, True)


@pytest.mark.integration
def test_hook_gate_write_integrity_and_sast_const_expr(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Verifica _handle_integrity tamper, CLI write-gate e _eval_const_str_expr in SASTConstructChecker."""
    assert isolated_nk_env.is_dir()
    root = tmp_path / "int_hub"
    for d in ("nk_tracking", "nk_genome", "tests"):
        (root / d).mkdir(parents=True)
    cp_f, pn_f, ol_f, tf_f = root / "nk_tracking" / "checkpoint_01.json", root / "nk_genome" / "PATCH_NOTES.md", root / "nk_tracking" / "oracle_lock.json", root / "tests" / "test_a.py"
    cp_f.write_text('{"step": 1}', encoding="utf-8")
    pn_f.write_text("## [v4.9.0]\n* Storico immutabile\n", encoding="utf-8")
    ol_f.write_text('{"lock": 1}', encoding="utf-8")
    tf_f.write_text("def test_a(): assert True\n", encoding="utf-8")
    assert hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)[0]["status"] == "UNINITIALIZED"
    (hook_mod._get_hooks_temp_dir() / "c_int_integrity.json").write_text("{corrupt", encoding="utf-8")
    assert (hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)[0]["status"], hook_mod._handle_integrity("c_int", root, init_mode=True, check_mode=False)[1], hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)[1]) == ("CORRUPTED_SNAPSHOT", 0, 0)
    cp_f.write_text('{"step": 999}', encoding="utf-8")
    pn_f.write_text("## [v9.9.9]\n* Sovrascritto\n", encoding="utf-8")
    ol_f.write_text('{"lock": 2}', encoding="utf-8")
    tf_f.write_text("def test_a(): assert False\n", encoding="utf-8")
    r_viol, rc_v = hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)
    assert (rc_v, len(r_viol["violations"])) == (1, 4)

    proj = tmp_path / "hg_cli_proj"
    for d in (".staging/scripts", "scripts", "nk_tracking"):
        (proj / d).mkdir(parents=True)
    rc_wg1, out_wg1, _ = call_script_main_captured(hook_mod, ["write-gate", "--project-root", str(proj)], stdin_text=json.dumps({"tool_input": {"Path": str(proj / ".staging" / "scripts" / "a.py")}}))
    rc_bad, out_bad, _ = call_script_main_captured(hook_mod, ["write-gate", "--project-root", str(proj)], stdin_text=json.dumps({"tool_input": {"Path": str(proj / "scripts" / "prod.py")}}))
    rc_wg2, out_wg2, _ = call_script_main_captured(hook_mod, ["write-gate", "--project-root", str(proj)], stdin_text=json.dumps({"tool_input": {"Path": str(tmp_path / "brain" / "conv1" / "scratch" / "note.py")}}))
    assert (rc_wg1, json.loads(out_wg1), rc_bad != 0 or json.loads(out_bad)["decision"] == "deny", rc_wg2, json.loads(out_wg2)) == (0, {}, True, 0, {})

    checker = guard_mod.SASTConstructChecker("src/expr.py", [])
    checker._const_str_vars["PART"] = "ev"
    for ce, exp_str in (("PART + 'al'", "eval"), ("''.join(['e', 'v', 'a', 'l'])", "eval"), ("''.join(reversed('lave'))", "eval"), ("f'{PART}al'", "eval"), ("'%sal' % ('ev',)", None), ("'xxal'.replace('xx', 'ev')", None), ("'lave'[::-1]", "eval"), ("chr(101) + 'val'", "eval")):
        assert checker._eval_const_str_expr(ast.parse(ce, mode="eval").body) == exp_str


def _assert_2pc_promotion_guards(tmp_path: Path) -> None:
    """Verifica guardie fail-closed e promozione atomica win32_2pc_engine."""
    repo = tmp_path / "prom_repo"
    repo.mkdir()
    with pytest.raises(FileNotFoundError):
        w2pc_mod.promote_staging_to_production(repo_root=repo)
    stg = repo / ".staging"
    stg.mkdir()
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=repo, verify_baseline=True)
    (stg / ".deleted_files.json").write_text("123", encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=repo)
    (repo / "nk_tracking").mkdir()
    (repo / "nk_tracking" / "oracle_lock.json").write_text("{}", encoding="utf-8")
    (stg / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["nk_tracking/oracle_lock.json"]}), encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=repo)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "same.py").write_text("SAME = 1\n", encoding="utf-8")
    (repo / "scripts" / "to_del.py").write_text("DEL = 1\n", encoding="utf-8")
    (stg / "scripts").mkdir()
    (stg / "scripts" / "same.py").write_text("SAME = 1\n", encoding="utf-8")
    (stg / "scripts" / "brand_new.py").write_text("NEW = 2\n", encoding="utf-8")
    (stg / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["scripts/to_del.py"]}), encoding="utf-8")
    res = w2pc_mod.promote_staging_to_production(repo_root=repo, milestone="MS-PROM-TEST", git_sync=False, cleanup_staging=True)
    assert (res["status"], len(res["unchanged_files"]), (repo / "scripts" / "to_del.py").exists(), (repo / "scripts" / "brand_new.py").exists()) == ("SUCCESS", 1, False, True)


@pytest.mark.integration
def test_rsi_gt14_sast_scanner_dast_and_2pc_guards(tmp_path: Path) -> None:
    """Verifica GT-14 strict/non-strict, sast_scanner, RSI fallback, DAST RSS/report e guardie 2PC."""
    import _internal.rsi_convergence_engine.gt14_probes as gp_mod

    ws = tmp_path / "gt14_ws"
    (ws / ".agents").mkdir(parents=True)
    (ws / "nk_tracking").mkdir()
    (ws / ".agents" / "guide.md").write_text("# Guida\nModulo conforme.\n", encoding="utf-8")
    (ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"_version": "1.0.0-Generation", "metrics": {"rsi_convergence_score": {"value": 100.0, "direction": "higher_is_better"}, "rsi_residual_delta": {"value": 0, "direction": "lower_is_better"}}}), encoding="utf-8")
    qb = rsi_mod.RSIConvergenceEngine(workspace_root=ws).emit_gt14_bundle(workspace_root=ws, with_dast=False, strict_verify=False, output_path=tmp_path / "gt14_out.json")["probes"]["quality_baseline"]
    strict_qb = gp_mod._run_quality_baseline_probe(root=ws, stg_dir=ws / ".staging", probes={"ast_guard": {"skipped": True}, "rsi_verify": {"delta_k": 0, "fitness_q": 40.0, "checks": {}}}, dast_test_report=None, load_probe_fn=lambda _r, n: load_nk_script_module(n), strict_verify=True)
    assert (qb["live_tests_measured"], qb["status"], qb["regressions"], strict_qb["passed"], strict_qb["regressions"][0]["metric"]) == (False, "UNMEASURED", [], False, "rsi_convergence_score")

    ss_mod = load_script_by_relpath("sast_scanner", "scripts/_internal/rsi_convergence_engine/sast_scanner.py")
    ext_repo = tmp_path / "NK_External_Projects" / "ClientPortal"
    (ext_repo / "nk_docs_and_setup").mkdir(parents=True)
    doc_p = ext_repo / "nk_docs_and_setup" / "playbook.md"
    doc_txt = "# Playbook\nEsegui `python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir .staging`.\nOppure `G:\\Workspace\\NK_Hub\\scripts\\win32_2pc_engine.py`.\nEsegui `python -B -u NK_Hub/scripts/phantom.py`.\n"
    doc_p.write_text(doc_txt, encoding="utf-8")
    broken, phantoms = ss_mod.audit_markdown_doc_references(doc_p, doc_txt, ext_repo, lambda r, rel: r / rel, deleted_rel={"scripts/ast_guard_validator.py"}, check_scripts=True)
    assert (broken, any("ast_guard_validator.py" in p for p in phantoms), any("scripts/phantom.py" in p for p in phantoms)) == ([], False, True)

    fb_bad = rsi_mod._fallback_verify_ste100_compliance("Frase — trattino.\n" + " ".join(f"p{i}" for i in range(25)) + ".\n")
    b_ws = tmp_path / "bench_ws"
    (b_ws / "tests").mkdir(parents=True)
    (b_ws / ".staging" / "tests").mkdir(parents=True)
    assert (rsi_mod._fallback_verify_ste100_compliance("---\nname: T\n---\n# T\n```python\nx = 1 — 2\n```\n| C1 | C2 |\n| --- | --- |\n| V | Ok |\n- Voce.\nFrase breve.\n")["passed"], fb_bad["passed"], len(fb_bad["violations"]) >= 2, rsi_mod.RSIConvergenceEngine(workspace_root=b_ws, root=b_ws).run_benchmark_suite(b_ws / "nonexistent", root_dir=b_ws)["executed"]) == (True, False, True, False)

    cur_pid = os.getpid()
    rss1 = dast_mod._get_process_memory_rss(cur_pid, p_process=None)
    rep_dir = tmp_path / "dast_rep"
    rep_dir.mkdir()
    assert (rss1 >= 0, dast_mod._get_process_memory_rss(cur_pid, p_process=None) >= 0, dast_mod._terminate_process_tree_fallback(0), dast_mod.resolve_dast_report_path(rep_dir, explicit_output=rep_dir).parent, dast_mod.write_atomic_dast_report({"ok": True}, rep_dir).exists()) == (True, True, 0, rep_dir, True)
    _assert_2pc_promotion_guards(tmp_path)


@pytest.mark.integration
def test_platform_runner_unbuffered_tree_kill_and_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica stream UTF-8, pytest.ini, tree-kill timeout, missing binary e --no-capture reali."""
    runner_mod.reconfigure_streams()
    ini_text = (WORKSPACE_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert ("[pytest]" in ini_text, "testpaths" in ini_text, ".staging" in ini_text) == (True, True, True)
    rc_ok, out_ok, err_ok = runner_mod.safe_subprocess_run([sys.executable, "-c", "import sys; sys.stdout.write('NK_UTF8_🚀_€\\n')"])
    rc_nf, out_nf, err_nf = runner_mod.safe_subprocess_run(["nonexistent_binary_nk_987654321"])
    rc_to, _, err_to = runner_mod.safe_subprocess_run([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    rc_ctl, _, err_ctl = runner_mod.safe_subprocess_run("echo hi\necho bye", use_shell=True)
    assert (rc_ok, "🚀" in out_ok, "€" in out_ok, err_ok) == (0, True, True, "")
    assert (rc_nf, out_nf, "FILE_NOT_FOUND" in err_nf, rc_to, "timed out" in err_to.lower(), rc_ctl, "EXECUTION_ERROR" in err_ctl) == (127, "", True, -1, True, 1, True)
    assert (call_script_main(runner_mod, ["--cmd", "nonexistent_cmd_999"], monkeypatch), call_script_main(runner_mod, ["--cmd", f'"{sys.executable}" -B -c "print(42)"', "--no-capture"], monkeypatch)) == (127, 0)
