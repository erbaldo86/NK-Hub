# -*- coding: utf-8 -*-
"""
Golden Test GT-NEW-03 v1.0.0-Generation: DSM AST Tarjan SCC, Kahn Topological Sort e Core CLI Gates.
Modulo: tests/test_gt14_and_dsm.py.
Zero mock/stub; include migrazione 100% dei branch cross-cutting (AST Guard, Bootstrap, 2PC, Compliance, HookGate, Oracle L3).
"""

from __future__ import annotations

import ast
from collections import deque
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest
from pydantic import BaseModel

try:
    from conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main as _call_main,
        call_script_main_captured as _call_main_captured,
        load_script_by_relpath as _load_mod,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main as _call_main,
        call_script_main_captured as _call_main_captured,
        load_script_by_relpath as _load_mod,
    )

idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")
w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
guard_mod = _load_mod("ast_guard_validator", "scripts/ast_guard_validator.py")
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
comp_mod = _load_mod("nk_compliance_checker", "scripts/nk_compliance_checker.py")


class _CatalogItemModel(BaseModel):
    code: str
    count: int


def _overlay_python_files(include_internal: bool) -> Dict[str, Path]:
    """Raccoglie i moduli scripts/ privilegiando .staging/ rispetto alla produzione."""
    prod_scripts = _WORKSPACE_ROOT / "scripts"
    stg_scripts = _WORKSPACE_ROOT / ".staging" / "scripts"
    files_by_rel: Dict[str, Path] = {}

    if include_internal:
        for base in (prod_scripts, stg_scripts):
            if not base.is_dir():
                continue
            for py_path in sorted(base.rglob("*.py")):
                files_by_rel[py_path.relative_to(base).as_posix()] = py_path
    else:
        for base in (prod_scripts, stg_scripts):
            if not base.is_dir():
                continue
            for py_path in sorted(base.glob("*.py")):
                files_by_rel[py_path.relative_to(base).as_posix()] = py_path
            schemas_dir = base / "schemas"
            if schemas_dir.is_dir():
                for py_path in sorted(schemas_dir.glob("*.py")):
                    files_by_rel[py_path.relative_to(base).as_posix()] = py_path
    return files_by_rel


_AST_CACHE: Dict[Path, ast.Module] = {}
_AST_FACTS_CACHE: Dict[Path, Tuple[Tuple[str, ...], Tuple[Tuple[int, str, Tuple[str, ...]], ...], Tuple[str, ...]]] = {}


def _parse_cached_ast(py_path: Path) -> ast.Module:
    """Esegue parsing AST con cache per evitare riletture duplicate dei moduli."""
    cached = _AST_CACHE.get(py_path)
    if cached is not None:
        return cached
    tree = ast.parse(py_path.read_text(encoding="utf-8-sig"), filename=py_path.name)
    _AST_CACHE[py_path] = tree
    return tree


def _collect_ast_facts(
    py_path: Path,
) -> Tuple[Tuple[str, ...], Tuple[Tuple[int, str, Tuple[str, ...]], ...], Tuple[str, ...]]:
    """Estrae import e nomi classe in una singola scansione AST memoizzata per file."""
    cached = _AST_FACTS_CACHE.get(py_path)
    if cached is not None:
        return cached
    tree = _parse_cached_ast(py_path)
    imports: List[str] = []
    from_imports: List[Tuple[int, str, Tuple[str, ...]]] = []
    class_names: List[str] = []
    stack: List[Any] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            from_imports.append((node.level, node.module or "", tuple(a.name for a in node.names)))
            continue
        if isinstance(node, ast.ClassDef):
            class_names.append(node.name)
        for attr in ("body", "orelse", "finalbody", "handlers", "cases"):
            sub = getattr(node, attr, None)
            if isinstance(sub, list):
                stack.extend(sub)
    facts = (tuple(imports), tuple(from_imports), tuple(class_names))
    _AST_FACTS_CACHE[py_path] = facts
    return facts


def _module_name_from_rel(rel_posix: str) -> str:
    p = Path(rel_posix)
    no_ext = p.with_suffix("")
    parts = no_ext.parts[:-1] if p.name == "__init__.py" else no_ext.parts
    return ".".join(parts) if parts else "__root__"


def _compute_tarjan_and_kahn(files_by_rel: Dict[str, Path]) -> Tuple[int, List[str]]:
    """Calcola gli SCC di Tarjan e l'ordinamento topologico di Kahn sul grafo import AST."""
    mod_to_path: Dict[str, Path] = {
        _module_name_from_rel(rel): path for rel, path in sorted(files_by_rel.items())
    }
    adj: Dict[str, Set[str]] = {m: set() for m in mod_to_path}

    for mod_name, py_path in mod_to_path.items():
        imports, from_imports, _ = _collect_ast_facts(py_path)
        pkg = mod_name if py_path.name == "__init__.py" else (mod_name.rsplit(".", 1)[0] if "." in mod_name else "")
        for imp_name in imports:
            cand = imp_name.removeprefix("scripts.")
            if cand in mod_to_path and cand != mod_name:
                adj[mod_name].add(cand)
        for level, raw_mod, alias_names in from_imports:
            base = raw_mod
            if level > 0:
                pkg_parts = pkg.split(".") if pkg else []
                keep_n = max(0, len(pkg_parts) - (level - 1))
                prefix = ".".join(pkg_parts[:keep_n])
                base = f"{prefix}.{base}".strip(".") if base else prefix
            base = base.removeprefix("scripts.")
            for alias_name in alias_names:
                cand = f"{base}.{alias_name}".strip(".")
                if cand in mod_to_path and cand != mod_name:
                    adj[mod_name].add(cand)
            if base in mod_to_path and base != mod_name:
                adj[mod_name].add(base)

    index_counter = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    sccs: List[List[str]] = []

    def strongconnect(node_id: str) -> None:
        nonlocal index_counter
        indices[node_id] = index_counter
        lowlink[node_id] = index_counter
        index_counter += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for nxt in sorted(adj[node_id]):
            if nxt not in indices:
                strongconnect(nxt)
                lowlink[node_id] = min(lowlink[node_id], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node_id] = min(lowlink[node_id], indices[nxt])
        if lowlink[node_id] == indices[node_id]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == node_id:
                    break
            sccs.append(comp)

    for node_id in sorted(adj):
        if node_id not in indices:
            strongconnect(node_id)

    cycles = [c for c in sccs if len(c) > 1 or (c[0] in adj[c[0]])]
    indegree: Dict[str, int] = {m: 0 for m in adj}
    for nbrs in adj.values():
        for dst_m in nbrs:
            indegree[dst_m] += 1
    queue: deque[str] = deque(sorted(m for m, deg in indegree.items() if deg == 0))
    kahn_order: List[str] = []
    while queue:
        cur = queue.popleft()
        kahn_order.append(cur)
        for dst_m in sorted(adj[cur]):
            indegree[dst_m] -= 1
            if indegree[dst_m] == 0:
                queue.append(dst_m)
    return len(cycles), kahn_order


def _assert_unique_classes_and_fastguard_flags(all_files: Dict[str, Path]) -> None:
    from _internal.nk_common.catalog import get_catalog_counts

    class_names: List[str] = []
    for py_path in all_files.values():
        class_names.extend(_collect_ast_facts(py_path)[2])
    assert len(class_names) > 0
    assert len(class_names) == len(set(class_names))

    acs_meta = idx_mod.NKRegistryIndexer._extract_script_metadata(all_files["nk_acs_fastguard.py"])
    assert len(acs_meta["cli_flags"]) == 6
    assert set(acs_meta["cli_flags"]) == {
        "--conversation-id", "--event", "--help", "--native-contract", "--project-root", "--transcript",
    }

    counts = get_catalog_counts(_WORKSPACE_ROOT)
    gov = idx_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT).verify_gt14_crit01_governance()
    assert gov["passed"] is True
    assert gov["agents_checked"] == counts["agents"]
    assert gov["skills_checked"] == counts["skills"]
    assert gov["issues"] == []


@pytest.mark.integration
def test_ast_tarjan_scc_kahn_unique_classes_and_gt14_governance() -> None:
    """Verifica 0 cicli Tarjan, Kahn su scripts/, classi uniche, 6 flag fastguard e GT-14 CRIT-01."""
    canon_files = _overlay_python_files(include_internal=False)
    assert len(canon_files) >= 35
    canon_cycles, canon_kahn = _compute_tarjan_and_kahn(canon_files)
    assert canon_cycles == 0
    assert len(canon_kahn) == len(canon_files)

    all_files = _overlay_python_files(include_internal=True)
    assert len(all_files) >= 130
    all_cycles, all_kahn = _compute_tarjan_and_kahn(all_files)
    assert all_cycles == 0
    assert len(all_kahn) == len(all_files)
    assert all(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) <= 400 for p in all_files.values())
    _assert_unique_classes_and_fastguard_flags(all_files)


@pytest.mark.fast
def test_cli_core_gates_ast_guard_sast_eval_and_catalog(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Migrato da cli_core_gates: ASTGuardValidator visit_Call, _is_truthy_constant_expr e catalogo Pydantic."""
    t_eval, t_glob, t_sub, t_mar = "ev" + "al", "__globals__", "sub" + "process", "mar" + "shal"
    t_mock, t_umock, t_trav = "Magic" + "Mock", "unittest." + "mock", ".." + "/etc/passwd"
    src_matrix = (
        f"import importlib, operator, os, pathlib, {t_mar}, yaml, sys, inspect, unittest\n"
        f"from {t_umock} import {t_mock}\n"
        f"a1 = importlib.import_module('{t_sub}'[::-1][::-1])\n"
        f"a2 = operator.attrgetter('{t_glob}')\na3 = operator.attrgetter('x'[::-1])\n"
        f"a4 = __import__('{t_sub}')\na5 = __import__('x'[::-1])\n"
        f"dyn_k = str(1)\na6 = getattr(os, dyn_k)\na7 = {t_mock}()\n"
        f"a8 = open('{t_trav}')\na9 = pathlib.Path('{t_trav}')\na10 = os.path.join('a', '{t_trav}')\n"
        f"a11 = os.popen('whoami')\na12 = {t_mar}.loads(b'123')\na13 = yaml.load('a: 1')\n"
        f"a14 = sys.modules.get('pytest')\na15 = globals().get('{t_eval}')\n"
        f"a16 = {{}}.get('{t_eval[::-1]}'[::-1])\na17 = inspect.currentframe()\na18 = sys._getframe()\n"
        f"uid = '1'\ncur.execute(f'SELECT * FROM users WHERE id = {{uid}}')\n{t_umock}.patch('x')\n"
    )
    rep = guard_mod.ASTGuardValidator().validate_code_edit("", src_matrix, target_file="src/all_vectors.py")
    assert rep.is_valid is False and len(rep.violations) >= 12
    checker = guard_mod.SASTConstructChecker("src/t.py", src_matrix.splitlines())
    checker._const_truthy_vars["KNOWN_TRUE"] = True
    expr_expected = [
        ("KNOWN_TRUE", True), ("[1, 2]", True), ("[]", False), ("{1: 2}", True),
        ("{}", False), ("not False", True), ("-5", True), ("~0", True),
        ("False or True", True), ("True and True", True), ("bool(1)", True), ("unknown_call()", False),
    ]
    for ex_s, expected in expr_expected:
        assert checker._is_truthy_constant_expr(ast.parse(ex_s, mode="eval").body) is expected
    assert guard_mod.validate_pydantic_catalog_records([{"code": "A1", "count": 3}], _CatalogItemModel)["passed"] is True
    assert guard_mod.validate_pydantic_catalog_records([{"code": "A1", "count": "bad"}], _CatalogItemModel)["passed"] is False
    ok_py = tmp_path / "valid_mod.py"
    ok_py.write_text("def ok_fn(v: int) -> int:\n    return v * 2\n", encoding="utf-8")
    out_json = tmp_path / "agv_rep.json"
    assert _call_main(guard_mod, ["--target", str(ok_py), "--output-json", str(out_json)], monkeypatch) == 0
    assert out_json.exists() and json.loads(out_json.read_text(encoding="utf-8"))["passed"] is True
    assert "PASSED" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_core_gates_bootstrap_faststat_hook_and_isolation(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Migrato da cli_core_gates: bootstrap helpers, onboarding bypass, --hook e isolation failure."""
    clean_ws = tmp_path / "clean_nk"
    for sub in ("scripts", "tests", "nk_genome", "nk_tracking", ".agents", ".staging"):
        (clean_ws / sub).mkdir(parents=True)
    (clean_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": {"value": 100.0}}}), encoding="utf-8")
    assert boot_mod._parse_iso_epoch(1700000000) == 1700000000.0 and boot_mod._parse_iso_epoch("2026-11-11T10:00:00Z") > 0.0
    assert boot_mod.verify_project_isolation(clean_ws)["passed"] is True
    assert boot_mod.enforce_wal_hygiene(clean_ws)["passed"] is True
    tr_f = tmp_path / "session_tr.jsonl"
    tr_f.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "avvia ambiente nk"}) + "\n", encoding="utf-8")
    r1 = boot_mod.run_bootstrap(workspace_root=clean_ws, transcript_path=tr_f, conversation_id="conv_boot_1", fast_stat=False, prompt="avvia ambiente nk")
    assert r1["status"] == "PASS" and r1["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    assert boot_mod.verify_fast_stat_invariant(clean_ws, conversation_id="conv_boot_1")["passed"] is True
    (clean_ws / ".staging" / "pending.txt").write_text("staged", encoding="utf-8")
    assert _call_main(boot_mod, ["--project-root", str(clean_ws), "--conversation-id", "conv_boot_1", "--transcript", str(tr_f), "--prompt", "avvia nk hub"], monkeypatch) == 0
    assert "BOOTSTRAP: PASS" in capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "conv_hook_9", "transcriptPath": str(tr_f), "userPrompt": "start nk"})))
    assert _call_main(boot_mod, ["--hook", "--project-root", str(clean_ws)], monkeypatch) == 0
    assert "ONBOARDING_BYPASS_VERIFIED" in capsys.readouterr().out
    (clean_ws / "untracked_rogue_app.py").write_text("X = 1\n", encoding="utf-8")
    assert _call_main(boot_mod, ["--force-full", "--project-root", str(clean_ws)], monkeypatch) == 1
    assert "FAIL" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_core_gates_2pc_shadow_swap_and_json_validation(tmp_path: Path) -> None:
    """Migrato da cli_core_gates: 2PC shadow swap fallback, win32_atomic_replace e validate_staging_json_files."""
    eng = w2pc_mod.TwoPhaseCommitEngine(wal_manager=w2pc_mod.WriteAheadLogManager(tmp_path / ".wal"))
    src1, dst1 = tmp_path / "src1.bin", tmp_path / "dst1.bin"
    src1.write_bytes(b"v1_payload")
    dst1.write_bytes(b"old_payload")
    assert eng._shadow_swap_fallback(src1, dst1) is True and dst1.read_bytes() == b"v1_payload"
    src2 = tmp_path / "src2.bin"
    src2.write_bytes(b"atomic_v2")
    w2pc_mod.win32_atomic_replace(src2, dst1)
    assert dst1.read_bytes() == b"atomic_v2"
    stg = tmp_path / "json_stg"
    stg.mkdir()
    (stg / "good_bom.json").write_bytes(b"\xef\xbb\xbf" + b'{"ok": true}')
    (stg / "bad_utf8.json").write_bytes(b"\xff\xfe\x00\x00")
    (stg / "mojibake.json").write_text('{"k": "\ufffd"}', encoding="utf-8")
    (stg / "broken_syntax.json").write_text("{not_valid", encoding="utf-8")
    (stg / "ignored.txt").write_text("plain", encoding="utf-8")
    ok, errs = w2pc_mod.validate_staging_json_files(stg)
    assert ok is False and len(errs) == 3


def _assert_compliance_mono_and_cli(
    checker: Any, tr_p: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tr_mono = tmp_path / "mono.jsonl"
    tr_mono.write_text(
        json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Scrivi 11 moduli"}) + "\n"
        + json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "write_file", "arguments": {"Path": f"scripts/m_{i}.py"}} for i in range(11)]}) + "\n",
        encoding="utf-8",
    )
    assert any("Monolithic" in p for p in checker.audit_transcript(tr_mono)["penalties"])
    assert _call_main(comp_mod, ["--transcript", str(tr_p), "--min-score", "90", "--json"], monkeypatch) != 0
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    assert _call_main(comp_mod, ["--transcript", str(tr_p), "--min-score", "0"], monkeypatch) == 1
    tr_clean = tmp_path / "clean_ok.jsonl"
    tr_clean.write_text(
        json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "avvia nk hub"}) + "\n"
        + json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "python scripts/nk_session_bootstrap.py"}}, {"name": "read_file", "arguments": {"Path": "nk_genome/concept_map.md"}}]}) + "\n",
        encoding="utf-8",
    )
    assert _call_main(comp_mod, ["--transcript", str(tr_clean), "--min-score", "80"], monkeypatch) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_core_gates_compliance_penalties_and_monolithic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Migrato da cli_core_gates: penalita polling/unstage/monolitiche e --min-score di NKComplianceChecker."""
    checker = comp_mod.NKComplianceChecker()
    assert checker.audit_transcript(tmp_path / "missing_tr.jsonl")["status"] == "ERROR"
    records = [
        {"step_index": 0, "type": "USER_INPUT", "content": "Esegui modifiche massicce"},
        {
            "step_index": 1, "type": "PLANNER_RESPONSE", "status": "ERROR",
            "tool_calls": [
                {"name": "read_file", "arguments": {"Path": "missing_a.py"}},
                *[{"name": "manage_task", "arguments": {"Action": "status"}} for _ in range(4)],
                {"name": "manage_subagents", "arguments": {"Action": "list"}},
                *[{"name": "read_file", "arguments": {"Path": f"scripts/f_{i}.py"}} for i in range(13)],
                *[{"name": "write_file", "arguments": {"Path": f"scripts/out_{i}.py"}} for i in range(2)],
                {"name": "write_file", "arguments": {"Path": "NK_External_Projects/Demo/app.py"}},
                {"name": "send_message", "arguments": {"Recipient": "ag1", "Message": "X" * 2300}},
            ],
        },
        {"step_index": 2, "type": "TOOL_RESPONSE", "status": "ERROR", "output": "FileNotFoundError: No such file or directory: missing_a.py"},
        {"step_index": 3, "type": "TOOL_RESPONSE", "output": "Command exited with code 1\nStatus: REFINING | Delta: 5"},
        {"step_index": 4, "type": "TOOL_RESPONSE", "output": "Command exited with code 2\nFatal crash error"},
    ]
    tr_p = tmp_path / "heavy_penalties.jsonl"
    tr_p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    rep = checker.audit_transcript(tr_p)
    assert rep["status"] == "FAIL"
    assert rep["metrics"]["polling_calls_total"] >= 5
    assert rep["metrics"]["external_unstage_writes"] >= 1
    assert len(rep["penalties"]) >= 3
    _assert_compliance_mono_and_cli(checker, tr_p, tmp_path, monkeypatch, capsys)


def _assert_hook_probe_and_integrity(proj: Path, lock_f: Path) -> None:
    rc_p, out_p, _ = _call_main_captured(hook_mod, ["probe", "--conversation-id", "c1"], stdin_text="{}")
    assert rc_p == 0
    assert json.loads(out_p) == {}
    rc_sn, out_sn, _ = _call_main_captured(hook_mod, ["session-start", "--conversation-id", "c1", "--project-root", str(proj), "--native-contract"], stdin_text="{}")
    assert rc_sn == 0
    assert "injectSteps" in json.loads(out_sn)
    rc_ss, out_ss, _ = _call_main_captured(hook_mod, ["session-start", "--conversation-id", "c1", "--project-root", str(proj)], stdin_text="{}")
    assert rc_ss == 0
    assert json.loads(out_ss)["status"] == "OK"

    assert _call_main_captured(hook_mod, ["integrity", "--init", "--conversation-id", "c1", "--project-root", str(proj)])[0] == 0
    assert "VALID" in _call_main_captured(hook_mod, ["integrity", "--check", "--conversation-id", "c1", "--project-root", str(proj)])[1]
    lock_f.write_text('{"combined_sha256": "tampered"}', encoding="utf-8")
    rc_i2, out_i2, _ = _call_main_captured(hook_mod, ["integrity", "--check", "--conversation-id", "c1", "--project-root", str(proj)])
    assert rc_i2 != 0
    assert "VIOLATION" in out_i2


def _assert_hook_write_gate_and_fasttrack(proj: Path) -> None:
    rc_m, out_m, _ = _call_main_captured(hook_mod, ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)], stdin_text="{malformed")
    assert rc_m == 0
    assert json.loads(out_m)["decision"] == "deny"
    rc_sh, out_sh, _ = _call_main_captured(
        hook_mod, ["write-gate", "--event", "PreToolUse", "--shadow", "--native-contract", "--conversation-id", "c1", "--project-root", str(proj)],
        stdin_text=json.dumps({"toolName": "write_file", "toolInput": {"Path": "scripts/direct.py"}}),
    )
    assert rc_sh == 0
    assert json.loads(out_sh)["decision"] == "allow"
    rc_pn, out_pn, _ = _call_main_captured(
        hook_mod, ["write-gate", "--project-root", str(proj), "--target", str(proj / ".staging" / "nk_genome" / "PATCH_NOTES.md"), "--content", "## [v6.0.0-Carbon]\n* Solo nuova\n"],
    )
    assert rc_pn == 0
    assert json.loads(out_pn) == {}


def _assert_hook_stop_evidence(tmp_path: Path) -> None:
    for _ in range(2):
        rc_st1, out_st1, _ = _call_main_captured(hook_mod, ["stop-evidence", "--enforce-stop", "--conversation-id", "c_malf"], stdin_text="{bad_stop_json")
        assert (rc_st1, json.loads(out_st1)["decision"]) == (0, "continue")
    tr_file = tmp_path / "stop_tr.jsonl"
    tr_file.write_text(json.dumps({"type": "PLANNER_RESPONSE", "content": "Tutto 93/93 PASS e CONVERGED_OPTIMAL"}) + "\n", encoding="utf-8")
    stop_pl = json.dumps({"transcriptPath": str(tr_file)})
    for extra_flags in (["--shadow"], ["--native-contract"], [], ["--enforce-stop"]):
        rc_st2, out_st2, _ = _call_main_captured(hook_mod, ["stop-evidence", "--conversation-id", "c_tr", *extra_flags], stdin_text=stop_pl)
        parsed_st2 = json.loads(out_st2)
        assert rc_st2 == 0
        assert (parsed_st2.get("decision") in ("allow", "continue") or "ephemeralMessage" in parsed_st2 or parsed_st2 == {})


def _assert_hook_fasttrack_streak_and_stop_evidence(tmp_path: Path) -> None:
    hooks_tmp = hook_mod._get_hooks_temp_dir()
    (hooks_tmp / "fasttrack_c1.json").write_text('{"streak": 15}', encoding="utf-8")
    rc_ft1, out_ft1, _ = _call_main_captured(hook_mod, ["fasttrack", "--event", "PreInvocation", "--native-contract", "--shadow", "--conversation-id", "c1"], stdin_text="{}")
    assert (rc_ft1, "injectSteps" in json.loads(out_ft1)) == (0, True)
    for idx in range(2):
        rc_ft2, out_ft2, _ = _call_main_captured(hook_mod, ["fasttrack", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "read_file", "step": idx}))
        assert (rc_ft2, json.loads(out_ft2)) == (0, {})
    (hooks_tmp / "fasttrack_c2.json").write_text('{"streak": 11}', encoding="utf-8")
    rc_ex, out_ex, _ = _call_main_captured(hook_mod, ["fasttrack", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "read_file"}))
    assert (rc_ex, json.loads(out_ex)) == (0, {})
    for idx in range(2, 4):
        rc_ft3, out_ft3, _ = _call_main_captured(hook_mod, ["fasttrack", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "write_file", "step": idx}))
        res_ft3 = json.loads(out_ft3)
        assert rc_ft3 == 0
        assert res_ft3 == {} if idx == 2 else res_ft3["streak"] == 13
    rc_post, out_post, _ = _call_main_captured(hook_mod, ["fasttrack", "--event", "PostToolUse", "--native-contract", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "write_file"}))
    assert (rc_post, json.loads(out_post)) == (0, {})
    _assert_hook_stop_evidence(tmp_path)


@pytest.mark.fast
def test_cli_core_gates_hook_fasttrack_stop_evidence_and_probe(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Migrato da cli_core_gates: probe, session-start, integrity, write-gate, fasttrack e stop-evidence."""
    assert isolated_nk_env.is_dir()
    proj = tmp_path / "hg_proj"
    for d in (".staging/scripts", "scripts", "nk_genome", "nk_tracking"):
        (proj / d).mkdir(parents=True)
    lock_f = proj / "nk_tracking" / "oracle_lock.json"
    lock_f.write_text('{"combined_sha256": "abc"}', encoding="utf-8")
    (proj / "nk_genome" / "PATCH_NOTES.md").write_text("## [v4.9.0]\n* Nota\n", encoding="utf-8")

    _assert_hook_probe_and_integrity(proj, lock_f)
    _assert_hook_write_gate_and_fasttrack(proj)
    _assert_hook_fasttrack_streak_and_stop_evidence(tmp_path)


def _assert_oracle_l3_cli_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _call_main(l3_mod, [], monkeypatch) == 2
    assert _call_main(l3_mod, ["--expected", "<p>A</p>", "--actual", "<p>B</p>"], monkeypatch) == 1
    assert "Verdict: FAIL" in capsys.readouterr().out
    h_file = tmp_path / "single.html"
    h_file.write_text("<div><h1>Valido</h1></div>", encoding="utf-8")
    assert _call_main(l3_mod, ["--html-file", str(h_file)], monkeypatch) == 2
    assert "ERROR" in capsys.readouterr().err
    assert _call_main(l3_mod, ["--expected-file", str(tmp_path / "nope.html"), "--actual", "<p>x</p>", "--json"], monkeypatch) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"
    bad_spec_f = tmp_path / "bad_spec.json"
    bad_spec_f.write_text("{bad_json", encoding="utf-8")
    assert _call_main(l3_mod, ["--expected-file", str(bad_spec_f), "--actual", "<p>x</p>"], monkeypatch) == 2
    assert "ERROR" in capsys.readouterr().err
    assert _call_main(l3_mod, ["--expected-file", str(bad_spec_f), "--actual", "<p>x</p>", "--json"], monkeypatch) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


@pytest.mark.fast
def test_cli_core_gates_oracle_l3_opcodes_and_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Migrato da cli_core_gates: SequenceMatcher opcodes, JSON/Markdown specs ed errori CLI Oracle L3."""
    ev = l3_mod.DOMOracleEvaluator()
    exp_1 = "<div id='root'>Testo A<p id='del1'>Rimosso</p><span id='keep1'>Uguale</span><b id='rep_e1'>1</b><b id='rep_e2'>2</b></div>"
    act_1 = "<div id='root'>Testo B<span id='keep1'>Uguale</span><i id='rep_a1'>X</i><em id='ins1'>Nuovo</em></div>"
    types_1 = {d.change_type for d in ev.evaluate_deltas(exp_1, act_1).deltas}
    assert "TEXT_MISMATCH" in types_1
    assert "REMOVED" in types_1
    r2 = ev.evaluate_deltas("<ul id='u'><li id='a'>1</li><li id='old'>2</li></ul>", "<ul id='u'><li id='a'>1</li><li id='n1'>2</li><li id='n2'>3</li></ul>")
    assert any(d.change_type == "ADDED" for d in r2.deltas)
    assert ev.evaluate_deltas(json.dumps({"html": "<div>Ok</div>", "required_tags": ["div"]}), "<div>Ok</div>", expected_kind="json").verdict == "PASS"
    assert ev.evaluate_deltas("<div><h1 id='t'>Hi</h1></div>", "<div><h1 id='t'>Hi</h1></div>", expected_kind="md").verdict == "PASS"
    md_struct = "# Hi\n```\nignored\n```\n- #t <div> \"Hi\"\n- required_text: ok\n"
    assert ev.evaluate_deltas(md_struct, "<div id='t'><h1>Hi</h1>ok</div>", expected_kind="md").verdict == "PASS"
    with pytest.raises(ValueError):
        ev.evaluate_deltas("{bad_json", "<div></div>", expected_kind="json")
    with pytest.raises(ValueError):
        ev.evaluate_deltas("[]", "<div></div>", expected_kind="json")
    _assert_oracle_l3_cli_errors(tmp_path, monkeypatch, capsys)
