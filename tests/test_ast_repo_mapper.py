# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Topologia AST, PageRank, Slicer e Repo-Map (v1.0.0-Generation).
Modulo: tests/test_ast_repo_mapper.py.
Valida SymbolExtractor, PageRank, Karpathy Slicer, cache concorrente, facade_resolver, _internal e CLI.
"""

from __future__ import annotations

import ast
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import time

import pytest

try:
    from conftest import is_cov_instrumented, load_nk_script_module
except ImportError:
    from tests.conftest import is_cov_instrumented, load_nk_script_module

mapper_mod = load_nk_script_module("ast_repo_mapper")
AtomicCacheManager = mapper_mod.AtomicCacheManager
DEFAULT_EXCLUDED_DIRS = mapper_mod.DEFAULT_EXCLUDED_DIRS
GraduatedSkillAdapter = mapper_mod.GraduatedSkillAdapter
KarpathySurgicalSlicer = mapper_mod.KarpathySurgicalSlicer
PersonalizedPageRank = mapper_mod.PersonalizedPageRank
PolyglotExtractor = mapper_mod.PolyglotExtractor
RepoMapConfig = mapper_mod.RepoMapConfig
RepoMapGenerator = mapper_mod.RepoMapGenerator
ResilientParser = mapper_mod.ResilientParser
SymbolExtractor = mapper_mod.SymbolExtractor
SymbolGraph = mapper_mod.SymbolGraph
SymbolNode = mapper_mod.SymbolNode
SymbolType = mapper_mod.SymbolType
export_markdown_snapshot = mapper_mod.export_markdown_snapshot

from _internal.ast_repo_mapper import (  # noqa: E402
    facade_resolver as facade_res,
    subgraph_query as subq_mod,
)
from _internal.ast_repo_mapper.map_rendering import (  # noqa: E402
    compact_sig_for_ste100_impl,
    render_expanded_module_impl,
    render_inline_compact_module_impl,
    render_two_tier_map_impl,
)
from _internal.ast_repo_mapper.models import EdgeType, SymbolEdge  # noqa: E402

_SAMPLE_CODE = """
import math

class DataProcessor:
    def __init__(self, factor: float):
        self.factor = factor

    def process(self, value: float) -> float:
        return math.sqrt(value) * self.factor

def execute_pipeline(items: list[float]) -> float:
    dp = DataProcessor(2.0)
    total = sum(dp.process(x) for x in items)
    return total
"""


def _assert_rich_symbol_signatures_and_edges() -> None:
    rich_sym_code = (
        "class BaseItem:\n"
        "    CLASS_K = 10\n"
        "    class NestedMeta:\n"
        "        pass\n"
        "class ChildItem(BaseItem):\n"
        "    pass\n"
        "def rich_sig(pos_a: int, /, reg_b: BaseItem = ..., *args: str, kw_c: str = 'x', **kwargs: int) -> ChildItem:\n"
        "    c1 = ChildItem()\n"
        "    c2 = ChildItem()\n"
        "    return c1\n"
        "def broken_default(x=lambda: 1):\n"
        "    return x\n"
    )
    ex2 = SymbolExtractor(module_path="rich.py", source_lines=rich_sym_code.splitlines(keepends=True))
    ex2.visit(ast.parse(rich_sym_code))
    g2 = ex2.graph
    assert "rich.py:BaseItem.CLASS_K" in g2.nodes
    assert "rich.py:BaseItem.NestedMeta" in g2.nodes
    sig = g2.nodes["rich.py:rich_sig"].signature or ""
    assert "/," in sig
    assert "*args: str" in sig
    assert "kw_c: str='x'" in sig
    assert "**kwargs: int" in sig
    edge_types = {e.edge_type for e in g2.edges}
    assert {EdgeType.CONTAINMENT, EdgeType.INHERITANCE, EdgeType.TYPE_REFERENCE, EdgeType.CALL}.issubset(edge_types)
    call_edges = [e for e in g2.edges if e.source_id == "rich.py:rich_sig" and e.target_id == "rich.py:ChildItem" and e.edge_type == EdgeType.CALL]
    assert len(call_edges) == 1


@pytest.mark.fast
def test_symbol_extractor_pagerank_and_missing_branches() -> None:
    """1. Valida SymbolExtractor, PageRank, posonly/vararg/kwonly/kwarg, ereditarieta e containment."""
    lines = _SAMPLE_CODE.splitlines(keepends=True)
    extractor = SymbolExtractor(module_path="test_mod.py", source_lines=lines)
    extractor.visit(ast.parse(_SAMPLE_CODE))
    graph = extractor.graph

    assert "test_mod.py:DataProcessor" in graph.nodes
    assert "test_mod.py:DataProcessor.process" in graph.nodes
    assert "test_mod.py:execute_pipeline" in graph.nodes
    assert len(graph.edges) > 0

    pr = PersonalizedPageRank.compute(
        graph, target_symbol_ids={"test_mod.py:execute_pipeline"}, damping=0.85, max_iter=100, epsilon=1e-6
    )
    assert pr.converged is True
    assert abs(sum(pr.scores.values()) - 1.0) < 1e-5
    _assert_rich_symbol_signatures_and_edges()


def _assert_map_rendering_budgets(tmp_path: Path) -> None:
    long_sig = "def very_long_fn(alpha_one: int, beta_two: int, gamma_three: int, delta_four: int, epsilon_five: int, zeta_six: int, eta_seven: int) -> dict[str, int]:"
    assert "..." in compact_sig_for_ste100_impl(long_sig, max_words=6)
    assert len(compact_sig_for_ste100_impl("word " * 20, max_words=5).split()) <= 5

    empty_map, _ = render_two_tier_map_impl(tmp_path, SymbolGraph(), {}, set(), 500)
    assert "REPO-MAP" in empty_map

    g = SymbolGraph()
    for i in range(14):
        mod = f"scripts/mod_{i}.py" if i < 12 else f"tests/test_mod_{i}.py"
        g.add_node(SymbolNode(id=f"{mod}:Cls_{i}", name=f"Cls_{i}", symbol_type=SymbolType.CLASS, module_path=mod, line_start=1, line_end=10))
        for m in range(10):
            g.add_node(SymbolNode(id=f"{mod}:Cls_{i}._m{m}", name=f"_m{m}" if m < 8 else f"pub_{m}", symbol_type=SymbolType.METHOD, module_path=mod, parent_id=f"{mod}:Cls_{i}", line_start=2 + m, line_end=3 + m))
    const_only = [SymbolNode(id="scripts/consts.py:K", name="K", symbol_type=SymbolType.CONSTANT, module_path="scripts/consts.py", line_start=1, line_end=1)]
    assert "symbols" in render_inline_compact_module_impl("scripts/consts.py", const_only)
    assert "K" in render_expanded_module_impl("scripts/consts.py", const_only)
    assert render_two_tier_map_impl(tmp_path, g, {}, {"scripts/mod_0.py:Cls_0"}, 920)[1] <= 920
    assert render_two_tier_map_impl(tmp_path, g, {}, set(), 35)[1] <= 35


def _assert_dense_repo_compaction_and_subgraph(tmp_path: Path) -> None:
    dense_repo = tmp_path / "dense_repo"
    for d in ("scripts", ".staging/scripts", "web"):
        (dense_repo / d).mkdir(parents=True)
    for idx in range(8):
        (dense_repo / "scripts" / f"mod_{idx:02d}.py").write_text(
            f"from scripts.mod_00 import CoreService0\nclass CoreService{idx}:\n"
            f"    def m1(self, x: int) -> int:\n        return x + {idx}\n"
            f"    def m2(self) -> int:\n        return self.m1(1)\n"
            f"def helper_fn_{idx}(a: int) -> int:\n    return CoreService0().m1(a)\n",
            encoding="utf-8",
        )
    (dense_repo / ".staging" / "scripts" / "staged_extra.py").write_text("def staged_caller() -> int:\n    return helper_fn_0(5)\n", encoding="utf-8")
    (dense_repo / "web" / "ui_widget.ts").write_text("export class WidgetView { renderItem() { return formatLabel(); } }\nexport function formatLabel(): string { return 'ok'; }\n", encoding="utf-8")
    empty_r = tmp_path / "empty_r"
    empty_r.mkdir()
    assert "REPO-MAP" in RepoMapGenerator.generate(empty_r).content
    snap_md = tmp_path / "out_repo_map.md"
    assert export_markdown_snapshot(dense_repo, snap_md, max_tokens=128).token_count <= 128
    assert snap_md.exists()
    assert mapper_mod.query_symbol_subgraph("", root=dense_repo)["found"] is False
    assert mapper_mod.query_symbol_subgraph("m1", root=dense_repo)["found"] is True
    sub_warm = mapper_mod.query_symbol_subgraph("helper_fn_0", root=dense_repo)
    assert sub_warm["found"] is True
    assert len(sub_warm["callers"]) >= 1


@pytest.mark.fast
def test_karpathy_slicer_map_rendering_and_cli_gate_compaction(tmp_path: Path) -> None:
    """2. Valida slicer, rendering 2-tier e migrazione compaction <=128 tok / subgraph da cli_core_gates."""
    for max_tokens in (200, 80):
        res = KarpathySurgicalSlicer.slice_module(
            source_code=_SAMPLE_CODE, focal_symbol_names=["execute_pipeline"], module_path="test_mod.py", max_tokens=max_tokens
        )
        assert res.token_count < max_tokens
        if max_tokens >= 200:
            assert "def execute_pipeline" in res.sliced_code

    multi_code = (
        "class ServiceA:\n    def method_one(self, a: int, b: str) -> bool:\n        return True\n"
        "class ServiceB:\n    def method_two(self, x: float) -> str:\n        return 'ok'\n"
    )
    res_multi = KarpathySurgicalSlicer.slice_module(
        source_code=multi_code, focal_symbol_names=["method_one", "method_two"], module_path="svc.py", max_tokens=300
    )
    assert "method_one" in res_multi.sliced_code
    assert "method_two" in res_multi.sliced_code
    assert res_multi.token_count <= 300

    empty_pr = PersonalizedPageRank.compute(SymbolGraph())
    assert empty_pr.converged is True
    assert empty_pr.scores == {}

    rich_code = (
        'CONST_VAL = 99\nclass EmptyBox:\n    pass\n'
        'class Worker:\n    """Doc worker."""\n'
        '    def keep_me(self):\n        """Keep doc."""\n        return 1\n'
        '    def drop_me(self):\n        return 2\n'
        'async def async_job(a: int) -> int:\n    """Async doc."""\n    return a\n'
    )
    assert "# " in KarpathySurgicalSlicer.slice_module(rich_code, ["keep_me", "Worker.keep_me"], module_path="w.py", max_tokens=2).sliced_code
    assert "def keep_me" in KarpathySurgicalSlicer.slice_module(rich_code, ["keep_me"], module_path="w.py", max_tokens=160).sliced_code
    _assert_map_rendering_budgets(tmp_path)
    _assert_dense_repo_compaction_and_subgraph(tmp_path)


def _assert_graduated_skill_adapter_budgets() -> None:
    gsa = GraduatedSkillAdapter
    assert gsa.get_token_budget("NK-Scribe-Memory", "mode_a") == 0
    assert gsa.get_token_budget("NK-Agent-Instruction-Forge") == 0
    assert (gsa.get_token_budget("NK-Python-Async-Builder", "mode_c"), gsa.get_token_budget("NK-Python-Async-Builder", "mode_b"), gsa.get_token_budget("NK-Orchestrator", "mode_a")) == (256, 512, 1024)
    assert (gsa.get_token_budget("NK-Builder", "argon_mode_c"), gsa.get_token_budget("NK-Builder", "argon_mode_b"), gsa.get_token_budget("NK-Builder", "argon_mode_a")) == (512, 1500, 4000)
    assert (gsa.get_token_budget("NK-Builder-Agent", "generation_mode_c"), gsa.get_token_budget("NK-Builder-Agent", "carbon_mode_b"), gsa.get_token_budget("NK-Builder-Agent", "generation_mode_a")) == (512, 1500, 4000)
    assert (gsa.get_token_budget("NK-Builder-Agent", "vibe"), gsa.get_token_budget("NK-Builder-Agent", "fast"), gsa.get_token_budget("NK-Builder", "auto")) == (256, 512, 1024)


def _assert_synthetic_repo_and_cache_errors(tmp_path: Path) -> None:
    syn_ws = tmp_path / "syn_ws"
    syn_ws.mkdir()
    synthetic_classes = set()
    for m_idx in range(4):
        lines = []
        for c_idx in range(3):
            c_name = f"SyntheticEntity_{m_idx}_{c_idx}"
            synthetic_classes.add(c_name)
            lines.append(f"class {c_name}:\n    def op_{c_idx}(self, x: int) -> int:\n        return x * {c_idx}\n")
        (syn_ws / f"service_mod_{m_idx}.py").write_text("\n".join(lines), encoding="utf-8")
    res_syn = RepoMapGenerator.generate(root_dir=syn_ws, config=RepoMapConfig(max_tokens=1024, polyglot=False, cache_enabled=False))
    assert res_syn.token_count <= 850
    assert all(cls_name in res_syn.content for cls_name in synthetic_classes)
    snap_file = syn_ws / "repo_map.md"
    export_markdown_snapshot(root_dir=syn_ws, output_path=snap_file, max_tokens=512)
    assert snap_file.exists()

    assert AtomicCacheManager.get_default_cache_path(tmp_path).parent.name == "nk_diagnostics"
    assert AtomicCacheManager.load_safe(tmp_path / "missing_cache.json") is None
    bad_json_file = tmp_path / "corrupt_cache.json"
    bad_json_file.write_text("{corrupt", encoding="utf-8")
    assert AtomicCacheManager.load_safe(bad_json_file, max_retries=2) is None
    dir_as_cache = tmp_path / "dir_target"
    dir_as_cache.mkdir()
    assert AtomicCacheManager.save_atomic({"k": 1}, dir_as_cache, max_retries=1) is False


def _assert_concurrent_atomic_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / "test_repo_cache.json"

    def worker_write(val: int) -> bool:
        return AtomicCacheManager.save_atomic({"version": "6.0.0-Carbon", "val": val, "ts": time.time()}, cache_file)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        write_futures = [executor.submit(worker_write, i) for i in range(10)]
        read_futures = [executor.submit(AtomicCacheManager.load_safe, cache_file) for _ in range(10)]
        assert all(f.result() for f in write_futures)
        assert all(r is None or isinstance(r, dict) for r in (f.result() for f in read_futures))
    assert cache_file.exists()


def _assert_incremental_repo_cache_hit(tmp_path: Path) -> None:
    inc_ws = tmp_path / "inc_ws"
    inc_ws.mkdir()
    inc_cache = tmp_path / "inc_cache.json"
    (inc_ws / "a.py").write_text("def fn_a(): pass\n", encoding="utf-8")
    cfg = RepoMapConfig(max_tokens=512, cache_enabled=True, cache_dir=str(inc_cache))
    assert RepoMapGenerator.generate(root_dir=inc_ws, config=cfg).cached_hits == 0
    res2 = RepoMapGenerator.generate(root_dir=inc_ws, config=cfg)
    assert res2.cached_hits >= 1
    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    max_ms = 1000.0 if (is_cov_instrumented() or is_ci) else 500.0
    assert res2.elapsed_ms < max_ms


@pytest.mark.integration
def test_atomic_cache_concurrency_skill_adapter_and_errors(tmp_path: Path) -> None:
    """3. Valida cache atomica concorrente, errori AtomicCacheManager, snapshot e tetti GT-06."""
    _assert_concurrent_atomic_cache(tmp_path)
    _assert_incremental_repo_cache_hit(tmp_path)
    _assert_graduated_skill_adapter_budgets()
    _assert_synthetic_repo_and_cache_errors(tmp_path)


@pytest.mark.fast
def test_repo_mapper_includes_internal_dir_and_cli_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """4. Verifica che _internal non sia escluso e valida CLI main e __getattr__."""
    assert "_internal" not in DEFAULT_EXCLUDED_DIRS
    with pytest.raises(AttributeError):
        getattr(mapper_mod, "NON_EXISTENT_MAPPER_EXPORT")

    (tmp_path / "scripts" / "_internal").mkdir(parents=True)
    (tmp_path / "scripts" / "main_entry.py").write_text("def run_main():\n    return 1\n", encoding="utf-8")
    (tmp_path / "scripts" / "_internal" / "sub_helper.py").write_text("def internal_helper_fn():\n    return 2\n", encoding="utf-8")

    out_snap = tmp_path / "snap.md"
    monkeypatch.setattr(sys, "argv", ["ast_repo_mapper.py", "--root", str(tmp_path), "--json", "--snapshot-out", str(out_snap)])
    mapper_mod.main()
    raw_out = capsys.readouterr().out
    assert out_snap.is_file()
    parsed = json.loads(raw_out[raw_out.index("{") :])
    assert "internal_helper_fn" in parsed["content"]

    monkeypatch.setattr(sys, "argv", ["ast_repo_mapper.py", "--root", str(tmp_path), "--symbol", "internal_helper_fn"])
    mapper_mod.main()
    sym_out = json.loads(capsys.readouterr().out)
    assert sym_out["found"] is True and sym_out["symbol"] == "internal_helper_fn" and len(sym_out["definitions"]) >= 1


@pytest.mark.fast
def test_strict_symbol_models_and_json_cache_hydration(tmp_path: Path) -> None:
    """5. Verifica strict=True su SymbolNode/SymbolEdge e idratazione JSON cache in generator.py."""
    from pydantic import ValidationError

    assert SymbolNode.model_config.get("strict") is True and SymbolNode.model_config.get("frozen") is True
    assert SymbolEdge.model_config.get("strict") is True and SymbolEdge.model_config.get("frozen") is True

    n_obj = SymbolNode(id="pkg/a.py:Fn", name="Fn", symbol_type=SymbolType.FUNCTION, module_path="pkg/a.py", line_start=1, line_end=3)
    e_obj = SymbolEdge(source_id="pkg/a.py:Fn", target_id="pkg/b.py:Helper", edge_type=EdgeType.CALL, weight=1.5)
    assert SymbolNode.model_validate(json.loads(json.dumps(n_obj.model_dump()))).symbol_type is SymbolType.FUNCTION
    assert SymbolEdge.model_validate(json.loads(json.dumps(e_obj.model_dump()))).edge_type is EdgeType.CALL

    with pytest.raises(ValidationError):
        SymbolNode.model_validate({"id": "x", "name": "x", "symbol_type": "FUNCTION", "module_path": "x.py", "line_start": "1", "line_end": 2})
    with pytest.raises(ValidationError):
        SymbolEdge.model_validate({"source_id": "a", "target_id": "b", "edge_type": 123, "weight": 1.0})

    repo_dir = tmp_path / "strict_cache_repo"
    (repo_dir / "pkg").mkdir(parents=True)
    (repo_dir / "pkg" / "helper.py").write_text("def cache_target_fn() -> int:\n    return 7\n", encoding="utf-8")
    (repo_dir / "pkg" / "caller.py").write_text("from pkg.helper import cache_target_fn\ndef invoke_cached() -> int:\n    return cache_target_fn()\n", encoding="utf-8")
    cfg = RepoMapConfig(max_tokens=512, cache_enabled=True, cache_dir=str(tmp_path / "strict_repo_cache.json"))
    res1 = RepoMapGenerator.generate(root_dir=repo_dir, config=cfg)
    res2 = RepoMapGenerator.generate(root_dir=repo_dir, config=cfg)
    assert res1.cached_hits == 0 and res2.cached_hits == 2
    assert "cache_target_fn" in res2.content and "invoke_cached" in res2.content
    sub = mapper_mod.query_symbol_subgraph("cache_target_fn", root=repo_dir)
    assert sub["found"] is True and any("invoke_cached" in str(c) for c in sub["callers"])


@pytest.mark.fast
def test_facade_resolver_reexports_relative_and_init_generator(tmp_path: Path) -> None:
    """6. Esercita facade_resolver.py su re-export _internal, import relativi, _LAZY_EXPORT_MAP e __init__.py."""
    repo = tmp_path / "facade_ws"
    pkg_dir = repo / "scripts" / "_internal" / "demo_pkg"
    sub_pkg = pkg_dir / "sub"
    stg_pkg = repo / ".staging" / "scripts" / "_internal" / "demo_pkg"
    sub_pkg.mkdir(parents=True)
    stg_pkg.mkdir(parents=True)

    (pkg_dir / "__init__.py").write_text(
        "from typing import Any\nfrom .core import CoreService, core_op\nfrom .sub import *\n"
        "_LAZY_EXPORT_MAP = {'lazy_sub_fn': ('.sub.leaf', 'lazy_sub_fn')}\n",
        encoding="utf-8",
    )
    (pkg_dir / "core.py").write_text(
        "class CoreService:\n    def execute(self, val: int) -> int:\n        return val + 1\n\n"
        "def core_op(item: int) -> int:\n    return CoreService().execute(item)\n",
        encoding="utf-8",
    )
    (sub_pkg / "__init__.py").write_text("from .leaf import leaf_fn\n", encoding="utf-8")
    (sub_pkg / "leaf.py").write_text(
        "from ..core import core_op\ndef leaf_fn(x: int) -> int:\n    return core_op(x)\n"
        "def lazy_sub_fn(x: int) -> int:\n    return x * 2\n",
        encoding="utf-8",
    )
    (stg_pkg / "lazy_override.py").write_text("def staged_lazy_fn(tag: str) -> str:\n    return tag.upper()\n", encoding="utf-8")

    facade_file = repo / "scripts" / "demo_facade.py"
    facade_src = (
        "from typing import Optional\nfrom _internal.demo_pkg import CoreService, leaf_fn, lazy_sub_fn\n"
        "from _internal.demo_pkg.sub import *\n_LAZY_EXPORT_MAP = {\n"
        "    'staged_lazy_fn': ('_internal.demo_pkg.lazy_override', 'staged_lazy_fn'),\n"
        "    'missing_mod_fn': ('_internal.demo_pkg.absent_mod', 'missing_mod_fn'),\n}\n"
    )
    facade_file.write_text(facade_src, encoding="utf-8")

    nodes, edges, scope_calls, deps_meta = facade_res.extract_python_module_symbols(
        facade_file, "scripts/demo_facade.py", facade_src, root_dir=repo
    )
    assert {"CoreService", "execute", "leaf_fn", "lazy_sub_fn", "staged_lazy_fn"}.issubset({n.name for n in nodes})
    assert len(edges) >= 1 and any("core_op" in vals for vals in scope_calls.values())
    assert facade_res.internal_deps_still_valid({"internal_deps": deps_meta}) is True
    (stg_pkg / "lazy_override.py").write_text("def staged_lazy_fn(tag: str) -> str:\n    return tag.lower()\n", encoding="utf-8")
    assert facade_res.internal_deps_still_valid({"internal_deps": deps_meta}) is False

    rel_ws = tmp_path / "facade_rel_ws"
    rel_pkg = rel_ws / "scripts" / "_internal" / "rel_pkg"
    rel_sub = rel_pkg / "sub"
    rel_sub.mkdir(parents=True)
    init_only = rel_ws / "scripts" / "init_only_pkg" / "__init__.py"
    init_only.parent.mkdir(parents=True)
    init_only.write_text("from os import path\n", encoding="utf-8")
    (rel_pkg / "core.py").write_text("def c_fn() -> int:\n    return 1\n", encoding="utf-8")

    assert facade_res.internal_deps_still_valid({"internal_deps": [["bad_tuple"]]}) is False
    assert facade_res.internal_deps_still_valid({"internal_deps": [[str(rel_ws / "missing.py"), 1.0, 1]]}) is False
    assert facade_res._resolve_relative_module("_internal.a.b", "c", 0, init_only) == "c"
    assert facade_res._resolve_relative_module("_internal.a", "core", 1, rel_pkg / "__init__.py") == "_internal.a.core"
    assert facade_res._resolve_relative_module("_internal.a.b", "core", 2, rel_sub / "leaf.py") == "_internal.core"
    assert facade_res._resolve_internal_file("typing", [rel_ws / "scripts"]) is None
    assert "init" in RepoMapGenerator.generate(root_dir=rel_ws, config=RepoMapConfig(max_tokens=512, polyglot=False, cache_enabled=False)).content


def _assert_partial_repomap_recovery(tmp_path: Path) -> None:
    partial_ws = tmp_path / "partial_ws"
    partial_ws.mkdir()
    (partial_ws / "partial.py").write_text(
        "def ok_head(x: int) -> int:\n    return x\n\ndef bad_mid(a: int):\n    if a\n        return a\n\nclass CleanTail:\n    def ok_tail(self) -> int:\n        return 2\n",
        encoding="utf-8",
    )
    res_part = RepoMapGenerator.generate(root_dir=partial_ws, config=RepoMapConfig(max_tokens=512, polyglot=False, cache_enabled=False))
    assert ("ok_head" in res_part.content, "CleanTail" in res_part.content) == (True, True)


def _assert_resilient_parser_recovery(tmp_path: Path) -> None:
    empty_tree, empty_warn = ResilientParser.parse_safe("")
    assert (isinstance(empty_tree, ast.Module), empty_warn) == (True, [])
    assert isinstance(ResilientParser._recover_ast_chunks("", "<empty>", []), ast.Module)

    broken_source = (
        "# Intestazione UTF-8: caffe e accento\n@staticmethod\ndef valid_top(alpha: int) -> int:\n    return alpha + 1\n\n"
        "def broken_sync(first, second):\n    if first > 0\n        return second\n"
        "    async def broken_async(rate):\n        items = [\n    class BrokenInner(Base):\n        pass\n\n"
        "class CleanTail:\n    def ping(self) -> str:\n        return 'pong'\n"
    )
    tree, warnings = ResilientParser.parse_safe(broken_source, filename="broken_mod.py")
    assert isinstance(tree, ast.Module)
    assert len(warnings) >= 2
    recovered = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    assert {"valid_top", "broken_sync", "broken_async", "BrokenInner", "CleanTail"}.issubset({n.name for n in recovered})
    assert [a.arg for a in next(n for n in recovered if n.name == "broken_sync").args.args] == ["first", "second"]
    _assert_partial_repomap_recovery(tmp_path)


def _assert_polyglot_tsx_calls() -> None:
    js_names = [n.name for n in PolyglotExtractor.extract_symbols("app.js", "export class DashboardView extends BaseView { render() {} }\nexport async function fetchData(url) {}")]
    assert ("DashboardView" in js_names, "fetchData" in js_names) == (True, True)

    tsx_code = (
        "/* block comment */\n// comment calling ignoredCall()\nexport default async function loadUser<T>(id: string) {\n"
        "  const cfg = (\n    1\n  );\n  /* ignoredCall() */\n  helperFn(id);\n  return <UserBadge />;\n}\n"
        "export const UserBadge = (props: Props) => {\n  if (props.ready) { return helperFn(props.id); }\n  return null;\n};\n"
        "export const inlineArrow = (n: number) => n + 1;\nfunction helperFn(v: string) { return v; }\n"
    )
    tsx_nodes = PolyglotExtractor.extract_symbols("ui/UserPanel.tsx", tsx_code)
    assert {"loadUser", "UserBadge", "inlineArrow", "helperFn"}.issubset({n.name for n in tsx_nodes})
    edges, scope_calls = PolyglotExtractor.extract_call_edges("ui/UserPanel.tsx", tsx_code, tsx_nodes)
    assert any(e.source_id.endswith(":loadUser") and e.target_id.endswith(":helperFn") for e in edges)
    assert any(e.source_id.endswith(":loadUser") and e.target_id.endswith(":UserBadge") for e in edges)
    assert "ignoredCall" not in scope_calls.get("ui/UserPanel.tsx:loadUser", set())


def _assert_polyglot_tsx_css_html() -> None:
    _assert_polyglot_tsx_calls()
    assert {n.name for n in PolyglotExtractor.extract_symbols("theme.css", ".btn-main { color: blue; }\n#nav-bar { display: flex; }\n")} == {".btn-main", "#nav-bar"}
    assert {n.name for n in PolyglotExtractor.extract_symbols("index.html", '<main id="app-root"><button id="save-btn"></button></main>')} == {"#app-root", "#save-btn"}
    assert PolyglotExtractor.extract_symbols("README.md", "# Title\n") == []
    assert PolyglotExtractor.extract_call_edges("README.md", "# Title\n") == ([], {})


@pytest.mark.fast
def test_resilient_parser_empty_broken_blocks_and_polyglot(tmp_path: Path) -> None:
    """7. Esercita parser_resilient.py e PolyglotExtractor su JS/TSX/CSS/HTML/Markdown."""
    _assert_resilient_parser_recovery(tmp_path)
    _assert_polyglot_tsx_css_html()


def _assert_subgraph_cache_corrupt_hydration(tmp_path: Path) -> None:
    sub_ws = tmp_path / "sub_cache_ws"
    (sub_ws / "src").mkdir(parents=True)
    (sub_ws / "src" / "worker.py").write_text("def cached_op(x: int) -> int:\n    return x\n", encoding="utf-8")
    assert subq_mod.query_symbol_subgraph("cached_op", root_dir=sub_ws)["found"] is True
    cache_p = AtomicCacheManager.get_default_cache_path(sub_ws)
    payload = AtomicCacheManager.load_safe(cache_p)
    assert isinstance(payload, dict)
    payload["files"]["src/worker.py"]["nodes"].append({"bad": "node"})
    payload["files"]["src/worker.py"]["edges"].append({"bad": "edge"})
    AtomicCacheManager.save_atomic(payload, cache_p)
    assert subq_mod.query_symbol_subgraph("cached_op", root_dir=sub_ws)["found"] is True


@pytest.mark.integration
def test_subgraph_query_staging_polyglot_and_cache_hydration(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """8. Esercita subgraph_query.py su query vuota, staging overlay, JS/TS e corruzione cache."""
    assert isolated_nk_env.is_dir()
    empty_sub = subq_mod.query_symbol_subgraph("   ", root=tmp_path)
    assert empty_sub["found"] is False
    assert empty_sub["symbol"] == ""

    repo = tmp_path / "subgraph_ws"
    (repo / "src").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".git" / "ignored.py").write_text("def target_op(): pass\n", encoding="utf-8")
    (repo / ".staging" / "src").mkdir(parents=True)
    (repo / "src" / "worker.py").write_text(
        "def leaf_helper(x: int) -> int:\n    return x + 1\n\n"
        "def target_op(x: int) -> int:\n    external_unmapped(x)\n    return leaf_helper(x)\n",
        encoding="utf-8",
    )
    (repo / ".staging" / "src" / "caller.py").write_text(
        "from src.worker import target_op\ndef staged_caller() -> int:\n    return target_op(5)\n", encoding="utf-8"
    )
    (repo / "src" / "panel.tsx").write_text(
        "export function renderPanel() { return target_op(1); }\nexport const usePanel = () => { return renderPanel(); };\n",
        encoding="utf-8",
    )

    first = subq_mod.query_symbol_subgraph("target_op", root_dir=repo)
    assert first["found"] is True
    assert any(c["name"] == "staged_caller" for c in first["callers"])
    assert any(c["name"] == "leaf_helper" for c in first["callees"])
    assert any(c["name"] == "external_unmapped" for c in first["callees"])

    second = subq_mod.query_symbol_subgraph("renderPanel", root_dir=repo)
    assert second["found"] is True
    assert any(c["name"] == "usePanel" for c in second["callers"])
    _assert_subgraph_cache_corrupt_hydration(tmp_path)
