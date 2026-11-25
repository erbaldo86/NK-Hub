# -*- coding: utf-8 -*-
"""Test unitari @pytest.mark.fast W1 per overlay_helpers, gt14_envelope, sast_expr_eval, quality_diff_rules e scope_branch_helpers."""

from __future__ import annotations

import ast
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

_agv_mod = load_nk_script_module("ast_guard_validator")
ASTGuardValidator = _agv_mod.ASTGuardValidator

from _internal.nk_common import gt14_envelope as gt14, tas_ssot_io as ssot  # noqa: E402
from _internal.ast_guard_validator import (  # noqa: E402
    overlay_helpers as ov_mod,
    quality_diff_checker as qd_chk,
    quality_diff_rules as qd_rules,
    sast_checker as sast_mod,
    sast_expr_eval as expr_mod,
)

pytestmark = pytest.mark.fast


def _make_overlay_ws(root: Path) -> Path:
    ws = root / "WsHub"
    for d in ("scripts", "src_app/node_modules", "tests", ".staging/scripts/sub", ".staging/src_app", ".staging/tests"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    (ws / "scripts" / "keep.py").write_text("def k(x: int) -> int:\n    return x\n", encoding="utf-8")
    (ws / "scripts" / "drop.py").write_text("DROP = 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "keep.py").write_text("def k(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "stg_only.py").write_text("def s() -> int:\n    return 1\n", encoding="utf-8")
    (ws / "src_app" / "App.tsx").write_text("export const A = 1;\n", encoding="utf-8")
    (ws / "src_app" / "Old.tsx").write_text("export const O = 1;\n", encoding="utf-8")
    (ws / "src_app" / "node_modules" / "Ign.tsx").write_text("export const I = 1;\n", encoding="utf-8")
    (ws / ".staging" / "src_app" / "New.tsx").write_text("export const N = 1;\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["scripts/drop.py", "src_app/Old.tsx", "tests/old_dir"]), encoding="utf-8")
    return ws


def _new_sast_checker() -> sast_mod.SASTConstructChecker:
    chk = sast_mod.SASTConstructChecker(target_file="src_app/sample.py")
    chk._const_str_vars["p_var"] = ".."
    chk._const_truthy_vars["t_flag"] = True
    chk._const_falsy_vars.add("f_flag")
    return chk


def test_overlay_norm_deleted_manifest_and_roots(tmp_path: Path) -> None:
    """Verifica _norm_rel, deleted manifest, resolve_overlay_roots e resolve_overlay_scan_files."""
    assert ov_mod._norm_rel("./.staging/scripts/a.py") == ".staging/scripts/a.py"
    assert ov_mod._norm_rel(".\\scripts\\a.py") == "scripts/a.py"
    assert (ov_mod.is_deleted_rel_path("tests/old_dir/x.py", {"tests/old_dir"}), ov_mod.is_deleted_rel_path("", {"a"})) == (True, False)

    ws = _make_overlay_ws(tmp_path)
    assert "scripts/drop.py" in ov_mod.load_deleted_manifest_set(ws / ".staging")
    bad_stg = tmp_path / "BadStg"
    bad_stg.mkdir()
    (bad_stg / ".deleted_files.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError):
        ov_mod.load_deleted_manifest_set(bad_stg)

    (ws / ".staging" / "scripts" / "drop.py").write_text("DROP = 2\n", encoding="utf-8")
    args = SimpleNamespace(stage_dir=str(ws / ".staging"))
    assert ov_mod.resolve_overlay_roots(args, ws, []) == (ws.resolve(), (ws / ".staging").resolve())
    assert ov_mod.resolve_overlay_roots(SimpleNamespace(stage_dir=None), ws, []) == (ws.resolve(), (ws / ".staging").resolve())
    assert ov_mod.resolve_overlay_roots(SimpleNamespace(stage_dir=None), tmp_path, [("all", False), (str(ws / "scripts/keep.py"), False)]) == (ws.resolve(), (ws / ".staging").resolve())
    assert ov_mod.resolve_overlay_roots(SimpleNamespace(stage_dir=None), tmp_path, [(str(ws / ".staging/scripts/sub"), False)]) == (tmp_path.resolve(), (tmp_path / ".staging").resolve())

    py_all, _, _, _, _, err = ov_mod.resolve_overlay_scan_files([("all", False), (str(ws / ".staging"), False)], SimpleNamespace(stage_dir=None), ws)
    py_sub, _, _, _, _, err_sub = ov_mod.resolve_overlay_scan_files([(str(ws / "scripts"), False), (str(ws / ".staging" / "scripts"), False)], args, ws)
    names = {p.name for p in py_all}
    assert (err is None, err_sub is None, "stg_only.py" in names, "drop.py" not in names, bool(py_sub)) == (True, True, True, True, True)

    py_one, _, _, _, _, e1 = ov_mod.resolve_overlay_scan_files([(str(ws / "scripts" / "stg_only.py"), False)], args, ws)
    py_stg, _, _, _, _, e2 = ov_mod.resolve_overlay_scan_files([(str(ws / ".staging" / "scripts" / "keep.py"), False)], args, ws)
    ext_py = tmp_path / "external.py"
    ext_py.write_text("X = 1\n", encoding="utf-8")
    py_ext, _, _, _, _, e3 = ov_mod.resolve_overlay_scan_files([(str(ext_py), False)], SimpleNamespace(stage_dir=None), ws)
    assert (e1, [p.name for p in py_one], e2, [p.name for p in py_stg], e3, ext_py in py_ext) == (None, ["stg_only.py"], None, ["keep.py"], None, True)


def test_overlay_errors_frontend_and_cli(tmp_path: Path) -> None:
    """Verifica rami errore resolve_overlay_scan_files, collect_overlay_frontend_files e CLI --overlay-staging."""
    ws = _make_overlay_ws(tmp_path)
    (ws / ".staging" / "src_app" / "Old.tsx").write_text("export const O = 2;\n", encoding="utf-8")
    args = SimpleNamespace(stage_dir=str(ws / ".staging"))
    assert ov_mod.resolve_overlay_roots(SimpleNamespace(stage_dir=str(tmp_path / "custom_stg")), ws, []) == (ws.resolve(), (tmp_path / "custom_stg").resolve())
    errs = (
        ov_mod.resolve_overlay_scan_files([("", False)], args, ws)[5],
        ov_mod.resolve_overlay_scan_files([(str(ws / "none.py"), False)], args, ws)[5],
        ov_mod.resolve_overlay_scan_files([(str(ws / "scripts/keep.py"), True)], args, ws)[5],
        ov_mod.resolve_overlay_scan_files([(str(ws / "no_dir"), True)], args, ws)[5],
    )
    assert None not in errs and ov_mod._iter_py_entries(None) == [] and ov_mod._iter_py_entries(ws / "no_dir") == []

    fe = ov_mod.collect_overlay_frontend_files([ws, ws / "src_app", ws / ".staging" / "src_app", tmp_path / "missing_fe", ws / "src_app" / "App.tsx"], ws.resolve(), (ws / ".staging").resolve(), {"src_app/old.tsx"}, (".tsx",), ("node_modules",))
    rc_ok, out_ok, _ = call_script_main_captured(_agv_mod, ["--stage-dir", str(ws / ".staging"), "--overlay-staging", "--quality-diff", "--json"])
    rc_bad, out_bad, _ = call_script_main_captured(_agv_mod, ["--overlay-staging", "--target", str(ws / "missing.py"), "--json"])
    (ws / ".staging" / ".deleted_files.json").write_text("{corrupt", encoding="utf-8")
    err_del = ov_mod.resolve_overlay_scan_files([(str(ws / ".staging"), True)], args, ws)[5]
    assert ({p.name for p in fe}, rc_ok, json.loads(out_ok)["passed"], rc_bad, json.loads(out_bad)["passed"], err_del is not None) == ({"App.tsx", "New.tsx"}, 0, True, 2, False, True)


def test_gt14_exec_digest_and_budget(tmp_path: Path) -> None:
    """Verifica build_compact_diagnostic_verdict, certification_tier e taglio budget <= 300 token."""
    uri = gt14.default_gt14_pointer_uri("pack_a.json", diag_dir=tmp_path / "nk_diagnostics")
    v_ok = ssot.build_compact_diagnostic_verdict("PASS", 1, {"cc": 0}, ["f1", "f2", "f3", "f4"], uri)
    assert (gt14.default_gt14_diagnostics_dir().name, "nk_diagnostics/pack_a.json" in uri) == ("nk_diagnostics", True)
    assert (v_ok["envelope_tier"], v_ok["certification_tier"], v_ok["findings_truncated"]) == ("gt14_exec_digest", "CERTIFIED_PASS", 1)
    assert (gt14.estimate_compact_tokens(v_ok) <= 300, gt14.build_gt14_exec_digest("STATIC_PASS", 0, {}, [], uri)["certification_tier"], gt14.build_gt14_exec_digest("FAIL", 0, {}, [], uri)["certification_tier"]) == (True, "STATIC_PASS", "FAIL")

    mid_m = {"msg": "z" * 120, "arr": [1, 2], "a": 1}
    v_mid = gt14.build_gt14_exec_digest("PASS", 1, mid_m, ["x"], uri, max_tokens=105)
    big_metrics = {"msg": "z" * 120, "arr": [1] * 80, "sub": {"k": "v" * 200}, "long_scalar_key_alpha": 1, "long_scalar_key_beta": 2}
    v_trim = gt14.build_gt14_exec_digest("CONVERGED_OPTIMAL", 1, big_metrics, ["X" * 115, "Y" * 115, "Z" * 115, "W"], uri, max_tokens=110, certification_tier="gold")
    assert (v_mid["certification_tier"], v_trim["certification_tier"], v_trim.get("metrics_truncated"), gt14.estimate_compact_tokens(v_trim) <= 110) == ("CERTIFIED_PASS", "GOLD", True, True)


def test_gt14_evidence_pack_and_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica gt14_evidence_pack <= 4 KB, max 3 slice SBFL, pointer_uri TEMP/nk_diagnostics e write atomico."""
    small_pack = gt14.build_gt14_evidence_pack([{"file": "a.py", "code": None}], ["t1"], {"ok": True}, extra_evidence={"x": 1})
    windows = [{"file": f"f{i}.py", "line": i, "snippet": "S" * 1200} for i in range(5)]
    taints = [{"file": "t.py", "msg": "M" * 450} for _ in range(12)]
    pack = gt14.build_gt14_evidence_pack(windows, taints, {"mismatches": [f"m{i}" for i in range(15)]}, extra_evidence={"big": "E" * 900})
    tight = gt14.build_gt14_evidence_pack(windows, [], {"mismatches": ["x" * 120] * 10}, max_bytes=450)
    pack_bytes = len(json.dumps(pack, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    assert (small_pack.get("truncated"), small_pack["extra_evidence"], pack["truncated"], len(tight["oracle_lock_state"]["mismatches"]) <= 5, pack_bytes <= 4096) == (None, {"x": 1}, True, True, True)

    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    env = gt14.write_gt14_two_tier_envelope("PASS", 1, {"ok": 1}, ["clean"], sbfl_windows=["raw"], sast_taint_diff=["t"], run_id="r1")
    assert ("nk_diagnostics" in env["pointer_uri"], env["evidence_pack_bytes"] <= 4096, Path(env["evidence_pack_path"]).is_file(), Path(env["exec_digest_path"]).is_file()) == (True, True, True, True)

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    bad_dir = tmp_path / "diag_err"
    (bad_dir / "gt14_evidence_pack.json").mkdir(parents=True)
    with pytest.raises(OSError):
        gt14.write_gt14_two_tier_envelope("PASS", 0, {}, [], diag_dir=bad_dir)


def test_sast_expr_eval_constants_compare_and_env() -> None:
    """Copre eval_int_or_none, eval_const_mult_str, collapse_partial_str_chunks, compare, truthy e falsy."""
    chk = _new_sast_checker()
    m1 = expr_mod.eval_const_mult_str(chk, ast.parse("'.' * 2", mode="eval").body)
    m2 = expr_mod.eval_const_mult_str(chk, ast.parse("'x' * 0", mode="eval").body)
    m3 = expr_mod.eval_const_mult_str(chk, ast.parse("'x' * 5000", mode="eval").body)
    m4 = expr_mod.eval_const_mult_str(chk, ast.parse("1 + 2", mode="eval").body)
    assert (expr_mod.eval_int_or_none(ast.Name("x")), expr_mod.eval_int_or_none(ast.parse("-4", mode="eval").body), m1, m2, m3, m4) == ((False, None), (True, -4), "..", "", None, None)

    c_str = "".join(expr_mod.collapse_partial_str_chunks(chk, ast.parse("f'{dyn}abc{dyn2}'", mode="eval").body))
    p_str = "".join(expr_mod.collapse_partial_str_chunks(chk, ast.parse("'a/' + dyn + '/../b'", mode="eval").body))
    t_part = expr_mod.has_traversal_in_node(chk, ast.parse("'a/' + dyn + '/../b'", mode="eval").body)
    env_expr = f"f'{chr(37)}TEMP{chr(37)}/{{dyn}}'"
    assert (expr_mod.has_traversal_in_node(chk, ast.parse("f'pre/{dyn}/..'", mode="eval").body), t_part, c_str, ".." in p_str) == (True, True, "abc", True)
    assert expr_mod.find_literal_env_token_in_node(chk, ast.parse(env_expr, mode="eval").body) == f"{chr(37)}TEMP{chr(37)}"

    cmps = (
        expr_mod.eval_const_compare(chk, ast.parse("1 + 1 == 2 < 3 != 4", mode="eval").body),
        expr_mod.eval_const_compare(chk, ast.parse("2 - 1 * 1 <= 1 >= 1 > 0", mode="eval").body),
        expr_mod.eval_const_compare(chk, ast.parse("t_flag is True and True", mode="eval").body.values[0]),
        expr_mod.eval_const_compare(chk, ast.parse("{1, 2} in 5", mode="eval").body),
        expr_mod.eval_const_compare(chk, ast.parse("1 // 2 == 0", mode="eval").body),
        expr_mod.eval_const_compare(chk, ast.parse("dyn == f_flag", mode="eval").body),
    )
    assert cmps == ((True, True), (True, True), (True, True), (False, False), (False, False), (False, False))

    t1 = expr_mod.is_truthy_constant_expr(chk, ast.parse("not {} and (t_flag or False) and bool(1) and (1 if True else 0)", mode="eval").body)
    t2 = expr_mod.is_truthy_constant_expr(chk, ast.parse("not (1 == 2) and ~0 == -1 and -1 and +2 and (1, 2) and {'a': 1}", mode="eval").body)
    f1 = expr_mod.is_falsy_constant_expr(chk, ast.parse("(f_flag or {}) and (0 if True else 1) and bool([]) and (1 == 2)", mode="eval").body)
    f2 = expr_mod.is_falsy_constant_expr(chk, ast.parse("not True or (False and t_flag)", mode="eval").body)
    assert (t1, t2, f1, f2) == (True, True, True, True)


def test_sast_wave1_detections_and_zero_fp() -> None:
    """Verifica SQL 1-hop taint, alias yaml.load, shell=var, open('.'*2) e non-FP eval/platform_runner."""
    v_sql = ASTGuardValidator.check_sast_constructs("import sqlite3\ndef f(c, u):\n    q = f'SELECT * FROM t WHERE id={u}'\n    c.execute(q)\n", "src_app/d.py")
    v_yml = ASTGuardValidator.check_sast_constructs("import yaml as y\ndef f(s):\n    return y.load(s)\n", "src_app/y.py")
    v_sh = ASTGuardValidator.check_sast_constructs("import subprocess\ndef f(c, sh):\n    subprocess.run(c, shell=sh)\n", "src_app/s.py")
    v_op = ASTGuardValidator.check_sast_constructs("def f():\n    return open('.' * 2)\n", "src_app/o.py")
    assert all((v_sql, v_yml, v_sh, v_op))
    assert not ASTGuardValidator.check_sast_constructs("def wrap(eval: int) -> int:\n    return eval + 1\n", "src_app/ok.py")
    assert not ASTGuardValidator.check_sast_constructs("import subprocess\ndef f(c, effective_shell):\n    subprocess.Popen(c, shell=effective_shell)\n", "NK_Hub/scripts/platform_runner.py")


def test_quality_diff_rules_metrics_tautology_and_deep_branches() -> None:
    """Copre quality_diff_rules: Try/TryStar/Match/For/While/With/BoolOp, silent except, tautologie, getter/deleter, raises e pure_const."""
    sample = (
        "async def complex_fn(xs, flag):\n"
        "    ok = (len(xs) > 0 and xs[0] or 0)\n"
        "    ys = [z for z in xs if z]\n"
        "    while flag:\n"
        "        break\n"
        "    else: pass\n"
        "    for z in ys:\n"
        "        with ctx():\n"
        "            try:\n"
        "                match z:\n"
        "                    case 1: pass\n"
        "                    case y: pass\n"
        "                    case _: pass\n"
        "            except (Exception, ValueError):\n"
        "                pass\n"
        "            else: pass\n"
        "            finally: pass\n"
        "            try: pass\n"
        "            except* ValueError: x = 1\n"
        "    else: pass\n"
        "    return ok\n"
        "class Prop:\n"
        "    @property\n"
        "    def v(self): return 1\n"
        "    @v.deleter\n"
        "    def v(self): pass\n"
        "def test_taut(x): assert 2 * 3 // 2 % 4 - 1 == 2\n"
        "def test_self(x): assert x <= x\n"
        "def test_empty(): x = 1\n"
        "def test_ok(): verify_result([1, 2] == [1, 2])\n"
    )
    m = qd_rules.extract_function_metrics(ast.parse(sample), is_test_file=True)
    pure_vals = (
        qd_rules._eval_pure_const_node(ast.parse("-(+1) < 0 and (True or not False)", mode="eval").body),
        qd_rules._eval_pure_const_node(ast.parse("1 // 0", mode="eval").body),
        qd_rules._eval_pure_const_node(ast.parse("[1, (2, 3)] == [1, (2, 3)]", mode="eval").body),
        qd_rules._eval_pure_const_node(ast.parse("1 < 'a'", mode="eval").body),
    )
    assert (m["complex_fn"]["cc"] >= 11, m["complex_fn"]["nesting"] >= 4, len(m["complex_fn"]["silent_except_lines"]), pure_vals) == (True, True, 1, ((True, True), (False, None), (True, True), (False, None)))
    assert ("Prop.v" in m, "Prop.v[deleter]" in m, m["test_ok"]["test_assert_issues"], m["test_self"]["test_assert_issues"][0][0]) == (True, True, [], "QD-TAUTOLOGICAL-ASSERT")
    assert (m["test_taut"]["test_assert_issues"][0][0], m["test_empty"]["test_assert_issues"][0][0], qd_chk.check_python_quality_diff("def f():\n    pass\n", "def f(:\n", "src_app/bad.py")[0].rule_id) == ("QD-TAUTOLOGICAL-ASSERT", "QD-ZERO-ASSERT-TEST", "QD-SYNTAX-ERROR")

    src = (
        "def branch_tree(a, b, c):\n"
        "    if a: x = 1\n"
        "    elif b: x = 2 if c else 3\n"
        "    else: x = 4\n"
        "    try:\n"
        "        return x\n"
        "    except:\n"
        "        \"\"\"noop doc\"\"\"\n"
        "class Box:\n"
        "    @property\n"
        "    def item(self): return 1\n"
        "    @item.getter\n"
        "    def item(self): return 2\n"
        "def helper(): return 1\n"
        "def test_raises_fn():\n"
        "    with pytest.raises(ValueError):\n"
        "        helper()\n"
    )
    m2 = qd_rules.extract_function_metrics(ast.parse(src), is_test_file=True)
    p1 = qd_rules._eval_pure_const_node(ast.parse("+2 - 1 == 1 and ('a' in ('a', 'b'))", mode="eval").body)
    p2 = qd_rules._eval_pure_const_node(ast.parse("+(True) if False else (1 + 'x')", mode="eval").body)
    p3 = qd_rules._eval_pure_const_node(ast.parse("not True", mode="eval").body)
    p4 = qd_rules._eval_pure_const_node(ast.parse("+ 'bad'", mode="eval").body)
    assert (len(m2["branch_tree"]["silent_except_lines"]), "Box.item[getter]" in m2, m2["test_raises_fn"]["test_assert_issues"]) == (1, True, [])
    assert (p1, p2, p3, p4) == ((True, True), (False, None), (True, False), (False, None))


def test_scope_branch_helpers_if_match_comp_and_globals() -> None:
    """Copre scope_branch_helpers: if/elif/del merge, stmts_terminate, Try, match, comprehension, walrus e global/nonlocal."""
    code = (
        "import sys as s\nG_VAL = 1\nY_G = 0\nif s.platform:\n    G_VAL = 2\ntype ListAlias[T] = list[T]\n"
        "def setter[T](arg: T, *va: int, **kw: str) -> T:\n"
        "    global G_VAL\n"
        "    from math import sin\n"
        "    def inner_fn(): pass\n"
        "    ann_v: int = 1\n"
        "    with arg as fh:\n"
        "        for k in [1]: G_VAL = ann_v + k\n"
        "    return arg\n"
        "def outer(flag: int, items: list[int]) -> int:\n"
        "    global Y_G\n    x = 1\n    class SkipCls:\n        x = 9\n"
        "    def inner():\n        nonlocal x\n        x = 2\n"
        "    if flag == 0: return 0\n    elif flag == 1:\n        del x\n        raise ValueError()\n    else: y = 3\n"
        "    try:\n        match flag:\n            case [a, b] if a > 0: y = a + b\n    except ValueError as err: return -1\n    finally: z = 1\n"
        "    res = [Y_G := a + b for a in items for b in items if b > 0]\n"
        "    return x + y + z + len(res) + G_VAL + Y_G\n"
    )
    rep = ASTGuardValidator.validate_code_edit(code, code, target_file="src_app/scope_ok.py")
    del_code = "def bad(flag: bool) -> int:\n    x = 1\n    if flag: return 1\n    else: del x\n    return x\n"
    rep_del = ASTGuardValidator.validate_code_edit(del_code, del_code, target_file="src_app/scope_bad.py")
    assert (rep.is_valid, rep.violations, any(v.symbol_name == "x" for v in rep_del.violations)) == (True, [], True)


def test_scope_and_expr_eval_edge_branches() -> None:
    """Copre rami residui di scope_branch_helpers (future annotations, Import, Try terminate, else_term) ed expr_eval."""
    fut_code = (
        "from __future__ import annotations\n"
        "G2 = 0\n"
        "def mod_imp():\n"
        "    global G2\n"
        "    import os.path as osp\n"
        "    G2 = 1\n"
        "def fn_fut(x: ForwardRefType) -> int:\n"
        "    return 1\n"
        "def try_term():\n"
        "    try: return 1\n"
        "    except ValueError: return 2\n"
        "def branch_else_term(flag: bool) -> int:\n"
        "    x = 1\n"
        "    if flag: del x\n"
        "    else: return 0\n"
        "    return x\n"
    )
    rep_fut = ASTGuardValidator.validate_code_edit(fut_code, fut_code, target_file="src_app/fut.py")
    chk = _new_sast_checker()
    assert any(v.symbol_name == "x" for v in rep_fut.violations)
    assert expr_mod.eval_const_compare(chk, ast.parse("{[1]} == 1", mode="eval").body) == (False, False)
    assert expr_mod.is_truthy_constant_expr(chk, ast.parse("int(1) and ('a' if flag else 'b') or (1 < 2)", mode="eval").body) is True
    assert expr_mod.eval_int_or_none(ast.parse("42", mode="eval").body) == (True, 42)
