# -*- coding: utf-8 -*-
"""Test rapidi Wave 5B per hotspot_audit, audit_mode, path hardening e CLI audit."""
from __future__ import annotations

import ast, hashlib, json, os
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, List, Tuple
import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

import _internal.builder_mutation_gate as bmg_pkg
from _internal.builder_mutation_gate import audit_mode, hotspot_audit, mutant_gen as mg_mod, runner as mut_runner

_mut_cli = load_nk_script_module("builder_mutation_gate")

_HOTSPOT_SAMPLE = (
    'def low_cc3_loc39(x: int) -> int:\n    """Docstring lunga."""\n'
    '    if x > 0:\n        x += 1\n    elif x < 0:\n        x -= 1\n'
    + "".join("    x += 1\n" for _ in range(34)) + '    return x\n\n'
    + 'def exact_loc40(v: int) -> int:\n' + "".join("    v += 1\n" for _ in range(39)) + '    return v\n\n'
    + 'def tie_alpha(a: int, b: int) -> int:\n    if a > 0 and b > 0: return a + b\n    if a < 0: return a - b\n    return 0\n\n'
    + 'def tie_beta(a: int, b: int) -> int:\n    if a > 0 and b > 0: return a + b\n    if a < 0: return a - b\n    return 0\n\n'
    + 'class Box:\n    async def deep_nested(self, items: list[int]) -> int:\n        total = 0\n'
    + '        for item in items:\n            if item > 0:\n                if item > 10: total += item\n                elif item > 5: total += 1\n'
    + '        try: assert total >= 0\n        except AssertionError: return -1\n        return [x for x in items if x > 0][0] if items else 0\n'
)


def _make_mini_ws(tmp_path: Path, files: dict[str, str]) -> Path:
    ws = tmp_path / "audit_ws"
    for d in ("scripts", "tests", ".staging/scripts"): (ws / d).mkdir(parents=True, exist_ok=True)
    (ws / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "tests" / "__init__.py").write_text("", encoding="utf-8")
    for rel, content in files.items():
        p = ws / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8")
    return ws


@pytest.mark.fast
def test_hotspot_scanner_inclusion_order_and_nesting() -> None:
    """Verifica CC>=4, LOC>=40, esclusioni, score CC*max(1,nesting) e tie-break (lineno, name)."""
    assert hotspot_audit.select_hotspot_functions("def broken(:") == []
    selected = hotspot_audit.select_hotspot_functions(_HOTSPOT_SAMPLE)
    assert ("low_cc3_loc39" in selected, selected[0], selected[-1]) == (False, "Box.deep_nested", "exact_loc40")
    assert selected.index("tie_alpha") < selected.index("tie_beta")
    assert hotspot_audit._calc_block_nesting([], 2) == 2
    assert hotspot_audit._calc_cc_and_loc(ast.parse("def outer():\n    def inner():\n        if 1: pass\n    return 1\n").body[0]) == (1, 1)
    with_src = "def fn(p):\n    with p:\n        for x in [1, 2]: pass\n        else: pass\n    while False: pass\n"
    assert hotspot_audit._calc_block_nesting(ast.parse(with_src).body[0].body, 0) == 2
    m_node = ast.parse("def m(v):\n    match v:\n        case 1: return True\n        case _: return False\n").body[0]
    assert (hotspot_audit._calc_cc_and_loc(m_node), hotspot_audit._calc_block_nesting(m_node.body, 0)) == ((3, 3), 1)
    assert hotspot_audit._calc_cc_and_loc(ast.parse("def b(x, y):\n    return x and y\n").body[0]) == (2, 1)
    assert hotspot_audit._calc_cc_and_loc(ast.parse("def c(xs):\n    return [x for x in xs if x > 0]\n").body[0]) == (3, 1)


@pytest.mark.fast
def test_hotspot_mutant_generation_caps_and_priority() -> None:
    """Verifica max_audit_mutants<=0, cap audit<=16 vs diff<=8 e priorita hotspot."""
    assert mg_mod.generate_audit_mutants("a.py", "def broken(:") == []
    assert mg_mod.generate_audit_mutants("m.py", _HOTSPOT_SAMPLE, max_audit_mutants=0) == []
    assert mg_mod.generate_audit_mutants("m.py", _HOTSPOT_SAMPLE, max_audit_mutants=-3) == []
    assert mg_mod.generate_audit_mutants("m.py", "def tiny(x): return x + 1\n") == []
    muts_16 = mg_mod.generate_audit_mutants("m.py", _HOTSPOT_SAMPLE, max_audit_mutants=50)
    muts_diff = mg_mod.generate_differential_mutants("m.py", None, _HOTSPOT_SAMPLE, max_mutants=50)
    assert (len(muts_16), len(muts_diff)) == (16, 8)
    muts_top2 = mg_mod.generate_audit_mutants("m.py", _HOTSPOT_SAMPLE, max_audit_mutants=2)
    assert (len(muts_top2), {m.function_name for m in muts_top2}) == (2, {"Box.deep_nested"})


def _assert_pyc_purge_and_restore(slot_ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target_f = slot_ws / "scripts" / "mod.py"
    orig_sha = hashlib.sha256(target_f.read_bytes()).hexdigest()
    pyc_dir = target_f.parent / "__pycache__"; pyc_dir.mkdir(exist_ok=True)
    for fn, data in (("mod.cpython-312.pyc", b"s1"), ("mod.pyc", b"s2"), ("keep.cpython-312.pyc", b"keep")): (pyc_dir / fn).write_bytes(data)
    assert (audit_mode._purge_target_pyc(target_f), (pyc_dir / "keep.cpython-312.pyc").is_file()) == (2, True)
    calls, real_awb = [], audit_mode.atomic_write_bytes

    def _flaky_awb(p: Path, d: bytes, **kw: Any) -> Tuple[bool, str | None]:
        calls.append(1)
        return (False, "tr") if len(calls) == 1 else real_awb(p, d, **kw)

    monkeypatch.setattr(audit_mode, "atomic_write_bytes", _flaky_awb)
    audit_mode._restore_slot_target(target_f, target_f.read_bytes(), orig_sha, "scripts/mod.py")
    assert len(calls) == 2
    monkeypatch.setattr(audit_mode, "atomic_write_bytes", lambda p, d, **_kw: real_awb(p, b"corrupt", fsync_data=False))
    with pytest.raises(RuntimeError, match="sha256_mismatch"): audit_mode._restore_slot_target(target_f, b"expected", orig_sha, "scripts/mod.py")
    monkeypatch.setattr(audit_mode, "atomic_write_bytes", lambda *_a, **_kw: (False, "io_blocked"))
    with pytest.raises(RuntimeError, match="io_blocked"): audit_mode._restore_slot_target(target_f, b"expected", orig_sha, "scripts/mod.py")
    monkeypatch.setattr(audit_mode, "atomic_write_bytes", lambda p, d, **kw: (False, "mut_fail") if d != target_f.read_bytes() else real_awb(p, d, **kw))


@pytest.mark.integration
def test_pool_single_copy_clamp_pyc_restore_and_cleanup(tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica 1 copia base, clamp workers 1..4, purge .pyc, restore SHA-256 e close cleanup."""
    _ = isolated_nk_env
    ws = _make_mini_ws(tmp_path, {"scripts/mod.py": _HOTSPOT_SAMPLE, "tests/test_mod.py": "def test_ok():\n    assert 1 == 1\n"})
    mirror_calls, real_mirror = [0], audit_mode.mirror_workspace_to_nvme
    monkeypatch.setattr(audit_mode, "mirror_workspace_to_nvme", lambda *a, **kw: (mirror_calls.__setitem__(0, mirror_calls[0] + 1) or real_mirror(*a, **kw)))
    with audit_mode.SharedBaseNVMeWorkerPool(ws, workers=9) as pool_hi, audit_mode.SharedBaseNVMeWorkerPool(ws, workers=0) as pool_lo:
        assert (mirror_calls[0], pool_hi.workers, len(pool_hi.slots), pool_lo.workers, len(pool_lo.slots)) == (2, 4, 4, 1, 1)
        slot0 = pool_lo.slots[0]; target_f = slot0.workspace_dir / "scripts" / "mod.py"
        orig_sha = hashlib.sha256(target_f.read_bytes()).hexdigest()
        seen_bt: List[Path] = []
        mut = mg_mod.generate_audit_mutants("scripts/mod.py", _HOTSPOT_SAMPLE, max_audit_mutants=1)[0]

        def _fake_py(sb_dir: Path, _t: Any, bt: Path, _to: float) -> Tuple[int, float]:
            seen_bt.append(bt); (sb_dir / "scripts" / "__pycache__").mkdir(exist_ok=True)
            (sb_dir / "scripts" / "__pycache__" / "mod.cpython-312.pyc").write_bytes(b"p")
            return (1, 0.02)

        out = pool_lo.run_mutant("scripts/mod.py", mut, ["tests/test_mod.py"], _fake_py, 5.0)
        assert (out.killed, out.exit_code, hashlib.sha256(target_f.read_bytes()).hexdigest() == orig_sha) == (True, 1, True)
        assert (seen_bt[0].exists(), (target_f.parent / "__pycache__" / "mod.cpython-312.pyc").exists()) == (False, False)
        _assert_pyc_purge_and_restore(slot0.workspace_dir, monkeypatch)
        with pytest.raises(OSError, match="Atomic write failed"): pool_lo.run_mutant("scripts/mod.py", mut, ["tests/test_mod.py"], _fake_py, 5.0)

    assert (pool_lo._slots_root.exists(), pool_lo._base_root.exists()) == (False, False)
    pool_lo.close()
    with pytest.raises(RuntimeError, match="closed"): pool_lo.run_baseline(["tests/test_mod.py"], lambda *_a: (0, 0.0), 1.0)
    assert pool_lo.evaluate_mutants("scripts/mod.py", [mut], ["tests/test_mod.py"], lambda *_a: (1, 0.0), 1.0, 5.0, 0.0)[2] == "SharedBaseNVMeWorkerPool is closed"


def _assert_full_module_audit_guards(ws: Path) -> None:
    assert audit_mode.run_full_module_audit(ws, "../escape.py", ["tests/test_m.py"]).passed is False
    assert audit_mode.run_full_module_audit(ws, "scripts/missing.py", ["tests/test_m.py"]).passed is False
    assert audit_mode.run_full_module_audit(ws, "scripts/bad.py", ["tests/test_m.py"]).passed is False
    assert audit_mode.run_full_module_audit(ws, "scripts/tiny.py", ["tests/test_m.py"], audit_workers=1, run_pytest_fn=lambda *_a: (0, 0.01)).passed is True
    assert audit_mode.run_full_module_audit(ws, "scripts/m1.py", ["tests/test_m.py"], audit_workers=1, run_pytest_fn=lambda *_a: (1, 0.01)).baseline_passed is False


@pytest.mark.integration
def test_multi_module_audit_and_single_pool_reuse(tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica run_full_module_audit edge cases e run_multi_module_audit con 1 pool."""
    _ = isolated_nk_env
    ws = _make_mini_ws(tmp_path, {".staging/scripts/m1.py": _HOTSPOT_SAMPLE, ".staging/scripts/m2.py": _HOTSPOT_SAMPLE, ".staging/scripts/tiny.py": "def ok(x: int) -> int:\n    return x + 1\n", ".staging/scripts/bad.py": "def broken(:\n", "tests/test_m.py": "def test_ok():\n    assert 1 == 1\n"})
    mirror_calls, real_mirror = [0], audit_mode.mirror_workspace_to_nvme
    monkeypatch.setattr(audit_mode, "mirror_workspace_to_nvme", lambda *a, **kw: (mirror_calls.__setitem__(0, mirror_calls[0] + 1) or real_mirror(*a, **kw)))
    _assert_full_module_audit_guards(ws)
    outcomes_map = {"m1.py": [1, 1, 1, 1], "m2.py": [1, 0, 1, 0]}

    def _per_mod(sb_dir: Path, _t: Any, _bt: Path, _to: float) -> Tuple[int, float]:
        for name, seq in outcomes_map.items():
            if (sb_dir / "scripts" / name).read_text(encoding="utf-8") != _HOTSPOT_SAMPLE:
                return (seq.pop(0) if seq else 1, 0.01)
        return (0, 0.01)

    mirror_calls[0] = 0
    multi = audit_mode.run_multi_module_audit(ws, [("scripts/m1.py", ["tests/test_m.py"]), {"target_file": "scripts/m2.py", "test_targets": ["tests/test_m.py"]}], audit_workers=2, max_audit_mutants=2, min_kill_rate=0.85, run_pytest_fn=_per_mod)
    assert (mirror_calls[0], multi["status"], multi["passed"], multi["modules_total"]) == (1, "FAIL", False, 2)
    assert (multi["modules_below_threshold"], len(multi["modules"][1]["survivors"])) == (["scripts/m2.py"], 1)
    assert set(multi["modules"][1]["survivors"][0]) == {"mutant_id", "operator", "function_name", "line_number"}
    assert audit_mode.run_multi_module_audit(ws, [], audit_workers=1, run_pytest_fn=lambda *_a: (0, 0.01))["passed"] is False


def _assert_budget_boundaries(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _DoneFut:
        def __init__(self, is_done: bool, res: Any = None) -> None: self._d, self._r, self.cancelled = is_done, res, False
        def done(self) -> bool: return self._d
        def cancel(self) -> bool: self.cancelled = True; return True
        def result(self, timeout: float = 0.0) -> Any: _ = timeout; return self._r

    out_ok = mut_runner.MutantOutcome(mutant_id="M1", operator="BinOpFlip", function_name="f", line_number=1, killed=True, exit_code=1, timed_out=False, duration_sec=0.01)
    d1, p1, p2 = _DoneFut(True, out_ok), _DoneFut(False, out_ok), _DoneFut(False, out_ok)
    outs_z, ex_z, _ = audit_mode._collect_audit_futures([d1, p1], 0.0, 0.0)
    assert (len(outs_z), ex_z, d1.cancelled, p1.cancelled) == (1, True, True, True)
    clock = [100.0]
    monkeypatch.setattr(audit_mode.time, "perf_counter", lambda: clock[0])
    outs_h, ex_h, _ = audit_mode._collect_audit_futures([p2], 0.5, 100.0)
    assert (len(outs_h), ex_h, p2.cancelled) == (1, False, False)

    def _adv_pytest(sb_dir: Path, _t: Any, _bt: Path, _to: float) -> Tuple[int, float]:
        if (sb_dir / "scripts" / "m1.py").read_text(encoding="utf-8") != _HOTSPOT_SAMPLE:
            clock[0] = 100.20
            return (1, 0.01)
        return (0, 0.01)

    res = audit_mode.run_multi_module_audit(ws, [("scripts/m1.py", ["tests/test_m.py"]), ("scripts/m1.py", ["tests/test_m.py"])], audit_workers=1, max_audit_mutants=1, total_budget_sec=0.10, run_pytest_fn=_adv_pytest)
    assert (res["modules"][0]["status"], res["modules"][1]["status"], res["passed"]) == ("PASS", "FAIL", False)


@pytest.mark.integration
def test_audit_budget_timeout_error_and_stub_futures(tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica budget=0.0, future timeout/error cancellation e failure esplicito run_full_module_audit."""
    _ = isolated_nk_env
    ws = _make_mini_ws(tmp_path, {".staging/scripts/m1.py": _HOTSPOT_SAMPLE, "tests/test_m.py": "def test_ok():\n    assert 1 == 1\n"})

    class _StubFut:
        def __init__(self, mode: str) -> None: self.mode, self.cancelled = mode, False
        def done(self) -> bool: return False
        def cancel(self) -> bool: self.cancelled = True; return True
        def result(self, timeout: float = 0.0) -> Any:
            _ = timeout
            if self.mode == "timeout": raise FuturesTimeoutError()
            raise RuntimeError("boom")

    f1, f2, f3 = _StubFut("timeout"), _StubFut("ok"), _StubFut("err")
    _, ex_to, _ = audit_mode._collect_audit_futures([f1, f2], 5.0, 10**9)
    _, _, err_s = audit_mode._collect_audit_futures([f3], 5.0, 10**9)
    assert (ex_to, f1.cancelled, f2.cancelled, err_s, f3.cancelled) == (True, True, True, "boom", True)
    ex_zero = audit_mode.run_full_module_audit(ws, "scripts/m1.py", ["tests/test_m.py"], audit_workers=1, total_budget_sec=0.0, run_pytest_fn=lambda *_a: (0, 0.01))
    assert (ex_zero.budget_exhausted, ex_zero.passed) == (True, False)
    calls: List[int] = []
    err_rep = audit_mode.run_full_module_audit(ws, "scripts/m1.py", ["tests/test_m.py"], audit_workers=1, max_audit_mutants=1, run_pytest_fn=lambda *_a: (0, 0.01) if (calls.append(1) or len(calls) == 1) else (_ for _ in ()).throw(RuntimeError("worker_exploded")))
    assert (err_rep.status, err_rep.passed, "worker_exploded" in err_rep.message) == ("FAIL", False, True)
    _assert_budget_boundaries(ws, monkeypatch)


def _assert_normalize_path_cases(ws: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"; outside.write_text("X = 1\n", encoding="utf-8")
    bad_paths = ["", "   ", "scripts/a\x00b.py", r"\\server\share\a.py", "//server/share/a.py", "../a.py", "scripts/../../a.py", "scripts/m.py:ads", str(outside), ".", ".staging"]
    if os.name == "nt": bad_paths.extend(["C:\\ws\\m.py:stream", "C:rel.py"])
    for bad in bad_paths:
        with pytest.raises(ValueError): mut_runner._normalize_target_rel_path(ws, bad)
    assert mut_runner._normalize_target_rel_path(ws, str(ws / ".staging" / "scripts" / "h.py")) == "scripts/h.py"
    assert mut_runner._normalize_target_rel_path(ws, ".staging/scripts/h.py") == "scripts/h.py"


@pytest.mark.integration
def test_path_hardening_runner_audit_and_cli_flags(tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica _normalize_target_rel_path, run_mutation_gate audit_full_module=True, _CLI_FLAGS e --out-map."""
    _ = isolated_nk_env
    ws = _make_mini_ws(tmp_path, {".staging/scripts/h.py": _HOTSPOT_SAMPLE, "tests/test_h.py": "def test_ok():\n    assert 1 == 1\n"})
    _assert_normalize_path_cases(ws, tmp_path)
    inv_rep = mut_runner.run_mutation_gate(ws, "../evil.py", ["tests/test_h.py"])
    assert (inv_rep.status, inv_rep.passed, inv_rep.baseline_passed) == ("FAIL", False, False)

    calls = [0]
    monkeypatch.setattr(mut_runner, "_run_pytest_fail_fast", lambda *_a: (0, 0.01) if (calls.__setitem__(0, calls[0] + 1) or calls[0] == 1) else (1, 0.01))
    rep = mut_runner.run_mutation_gate(ws, "scripts/h.py", ["tests/test_h.py"], stage_dir=ws / ".staging", audit_full_module=True, max_audit_mutants=4, audit_workers=2)
    assert (rep.passed, rep.mutants_total, rep.kill_rate) == (True, 4, 1.0)
    flags = list(_mut_cli._CLI_FLAGS)
    assert (flags == sorted(flags), {"--audit-full-module", "--audit-workers", "--max-audit-mutants", "--out-map"}.issubset(flags)) == (True, True)
    assert set(bmg_pkg.__all__).issuperset({"SharedBaseNVMeWorkerPool", "generate_audit_mutants", "run_full_module_audit", "run_multi_module_audit", "select_hotspot_functions"})

    calls[0] = 0
    out_map = tmp_path / "out" / "audit_map.json"
    rc, stdout, _ = call_script_main_captured(_mut_cli, ["--workspace-root", str(ws), "--stage-dir", str(ws / ".staging"), "--target-file", "scripts/h.py", "--test-targets", "tests/test_h.py", "--audit-full-module", "--audit-workers", "2", "--max-audit-mutants", "3", "--out-map", str(out_map), "--json"])
    assert (rc, json.loads(stdout)["mutants_total"], out_map.is_file(), json.loads(out_map.read_text(encoding="utf-8"))["kill_rate"]) == (0, 3, True, 1.0)
