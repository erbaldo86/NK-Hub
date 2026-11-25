# -*- coding: utf-8 -*-
"""Test rapidi Wave 6 per hotspot_audit, target_prep, runner e mutant_gen."""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path
from typing import Any, List, Set, Tuple

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

_mut_mod = load_nk_script_module("builder_mutation_gate")

from _internal.builder_mutation_gate import hotspot_audit, mutant_gen, runner, target_prep  # noqa: E402

pytestmark = pytest.mark.fast


def _dummy_mutant() -> mutant_gen.MutantSpec:
    """Restituisce un MutantSpec minimo valido per i test unitari del runner."""
    return mutant_gen.MutantSpec(
        mutant_id="MUT-01-BinOpFlip",
        operator="BinOpFlip",
        rel_path="scripts/a.py",
        function_name="f",
        line_number=1,
        original_snippet="x + 1",
        mutated_snippet="x - 1",
        mutated_source="def f(x): return x - 1\n",
    )


class _PendingFuture:
    """Future fittizia non completata che vieta result() a budget esaurito."""

    def done(self) -> bool:
        return False

    def result(self, timeout: float = 0.0) -> Any:
        raise AssertionError("must not call")


class _StubFuture:
    """Future fittizia cancellabile per testare shutdown del pool parallelo."""

    def cancel(self) -> bool:
        return True


class _StubExecutor:
    """Stub ThreadPoolExecutor che registra le chiamate a shutdown()."""

    def __init__(self, shutdown_calls: List[Tuple[bool, bool]]) -> None:
        self._shutdown_calls = shutdown_calls

    def submit(self, *_args: Any, **_kwargs: Any) -> _StubFuture:
        return _StubFuture()

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        self._shutdown_calls.append((wait, cancel_futures))


class _StubSandboxDir:
    """Stub minimale con attributo sandbox_dir."""

    def __init__(self, sandbox_dir: Path) -> None:
        self.sandbox_dir = sandbox_dir


class _StubSandboxCtx:
    """Context manager stub per ShadowSandbox senza I/O reale."""

    def __init__(self, sandbox_dir: Path) -> None:
        self.sandbox_dir = sandbox_dir

    def __enter__(self) -> "_StubSandboxCtx":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


@pytest.mark.fast
def test_unique_func_qname_property_and_duplicates() -> None:
    """Verifica disambiguazione @property ripetute e omonimi top-level."""
    cls_tree = ast.parse(
        "class C:\n    @property\n    def x(self): return 1\n    @property\n    def x(self): return 2\n"
    )
    cls_node = cls_tree.body[0]
    assert isinstance(cls_node, ast.ClassDef)
    seen_cls: Set[str] = set()
    cls_q = [hotspot_audit._unique_func_qname(fn, "C", seen_cls) for fn in cls_node.body]  # type: ignore[arg-type]
    assert cls_q == ["C.x", "C.x[property]"]

    top_tree = ast.parse("def dup(): pass\ndef dup(): pass\ndef dup(): pass\n")
    seen_top: Set[str] = set()
    top_q = [hotspot_audit._unique_func_qname(fn, "", seen_top) for fn in top_tree.body]  # type: ignore[arg-type]
    assert top_q == ["dup", "dup#2", "dup#3"]


@pytest.mark.fast
def test_target_prep_strip_prefixes_and_ads_drive() -> None:
    """Verifica rimozione prefissi NK_Hub e blocco drive-relative su Windows."""
    other_ws = Path("C:/tmp/other_ws")
    assert target_prep._strip_workspace_prefixes("NK_Hub/.staging/scripts/a.py", other_ws) == "scripts/a.py"
    assert target_prep._strip_workspace_prefixes("NK_Hub/scripts/a.py", other_ws) == "scripts/a.py"
    target_prep._check_ads_and_drive("a", "a")
    if os.name == "nt":
        with pytest.raises(ValueError):
            target_prep._check_ads_and_drive("C:", "C:")


@pytest.mark.fast
def test_is_explicit_staged_target_paths(tmp_path: Path) -> None:
    """Verifica rilevamento target espliciti in .staging/ per path assoluti e relativi."""
    ws_root = tmp_path / "ws"
    stg_dir = ws_root / ".staging"
    assert target_prep._is_explicit_staged_target(ws_root, stg_dir, str(tmp_path / "ext" / ".staging" / "x.py")) is True
    assert target_prep._is_explicit_staged_target(ws_root, stg_dir, str(tmp_path / "ext" / "x.py")) is False
    assert target_prep._is_explicit_staged_target(ws_root, stg_dir, ".staging/scripts/a.py") is True
    assert target_prep._is_explicit_staged_target(ws_root, stg_dir, "scripts/a.py") is False


@pytest.mark.fast
def test_collect_parallel_futures_budget_exhausted() -> None:
    """Verifica ritorno immediato con budget scaduto senza invocare fut.result()."""
    futs: List[Any] = [_PendingFuture()]
    outcomes, exhausted = runner._collect_parallel_futures(futs, 0.0, time.perf_counter() - 10.0)
    assert outcomes == [] and exhausted is True


@pytest.mark.fast
def test_evaluate_mutants_parallel_shutdown_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica shutdown(wait=not budget_exhausted, cancel_futures=True) nei due esiti."""
    shutdown_calls: List[Tuple[bool, bool]] = []
    collect_ret: List[Tuple[List[Any], bool]] = [([], True)]
    monkeypatch.setattr(runner, "ThreadPoolExecutor", lambda max_workers=1: _StubExecutor(shutdown_calls))
    monkeypatch.setattr(runner, "_collect_parallel_futures", lambda *_a, **_kw: collect_ret[0])

    sb = _StubSandboxDir(tmp_path)
    muts = [_dummy_mutant()]
    _, ex_true = runner._evaluate_mutants_parallel(sb, "scripts/a.py", muts, ["t.py"], time.perf_counter(), 5.0, 10.0)  # type: ignore[arg-type]
    collect_ret[0] = ([], False)
    _, ex_false = runner._evaluate_mutants_parallel(sb, "scripts/a.py", muts, ["t.py"], time.perf_counter(), 5.0, 10.0)  # type: ignore[arg-type]

    assert ex_true is True and ex_false is False
    assert shutdown_calls == [(False, True), (True, True)]


@pytest.mark.fast
def test_run_sandbox_session_skips_evaluator_when_inactive(
    tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica skip dell'evaluator quando baseline fallisce o lista mutanti e vuota."""
    _ = isolated_nk_env
    rc_box = [1]
    monkeypatch.setattr(runner, "ShadowSandbox", lambda: _StubSandboxCtx(tmp_path / "sb"))
    monkeypatch.setattr(runner, "prepare_staging_overlay", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "_run_pytest_fail_fast", lambda *_a, **_kw: (rc_box[0], 0.01))
    monkeypatch.setattr(
        runner,
        "_evaluate_mutants_in_sandbox",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("unexpected call")),
    )

    res_fail = runner._run_sandbox_session(tmp_path, tmp_path / ".staging", "a.py", "x = 1\n", [_dummy_mutant()], ["t.py"], 5.0, 10.0)
    rc_box[0] = 0
    res_empty = runner._run_sandbox_session(tmp_path, tmp_path / ".staging", "a.py", "x = 1\n", [], ["t.py"], 5.0, 10.0)
    assert res_fail == (False, [], False)
    assert res_empty == (True, [], False)


@pytest.mark.fast
def test_generate_differential_mutants_limits_and_invalid_ast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica cap max_mutants, ID MUT-01/MUT-02 e lista vuota su AST invalido."""
    pre = "def f(x):\n    return x\n"
    post = "def f(x):\n    return x + 1 if x > 0 else x - 1\n"
    assert mutant_gen.generate_differential_mutants("a.py", pre, post, max_mutants=0) == []
    one = mutant_gen.generate_differential_mutants("a.py", pre, post, max_mutants=1)
    two = mutant_gen.generate_differential_mutants("a.py", pre, post, max_mutants=2)
    assert len(one) == 1 and len(two) == 2
    assert [two[0].mutant_id.startswith("MUT-01-"), two[1].mutant_id.startswith("MUT-02-")] == [True, True]

    monkeypatch.setattr(mutant_gen, "find_touched_functions", lambda *_a, **_kw: {"f"})
    bad = mutant_gen.generate_differential_mutants("a.py", pre, "def broken(:", max_mutants=2)
    assert isinstance(bad, list) and bad == []
