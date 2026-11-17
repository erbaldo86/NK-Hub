# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Topologia AST, PageRank, Slicer e Repo-Map (v6.4.0-Carbon).
Modulo: tests/test_ast_repo_mapper.py.
Valida SymbolExtractor, PageRank, Karpathy Slicer, cache concorrente, _internal e CLI.
"""

from __future__ import annotations

import ast
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

import pytest

try:
    from conftest import is_cov_instrumented, load_nk_script_module
except ImportError:
    from tests.conftest import is_cov_instrumented, load_nk_script_module

pytestmark = pytest.mark.fast

mapper_mod = load_nk_script_module("ast_repo_mapper")
AtomicCacheManager = mapper_mod.AtomicCacheManager
DEFAULT_EXCLUDED_DIRS = mapper_mod.DEFAULT_EXCLUDED_DIRS
GraduatedSkillAdapter = mapper_mod.GraduatedSkillAdapter
KarpathySurgicalSlicer = mapper_mod.KarpathySurgicalSlicer
PersonalizedPageRank = mapper_mod.PersonalizedPageRank
PolyglotExtractor = mapper_mod.PolyglotExtractor
RepoMapConfig = mapper_mod.RepoMapConfig
RepoMapGenerator = mapper_mod.RepoMapGenerator
SymbolExtractor = mapper_mod.SymbolExtractor
SymbolGraph = mapper_mod.SymbolGraph
SymbolNode = mapper_mod.SymbolNode
SymbolType = mapper_mod.SymbolType
export_markdown_snapshot = mapper_mod.export_markdown_snapshot

from _internal.ast_repo_mapper.map_rendering import (  # noqa: E402
    compact_sig_for_ste100_impl,
    render_expanded_module_impl,
    render_inline_compact_module_impl,
    render_two_tier_map_impl,
)


class TestASTRepoMapper(unittest.TestCase):
    def setUp(self):
        self.code = """
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
        self.lines = self.code.splitlines(keepends=True)

    def test_symbol_table_extraction(self):
        """1. Valida estrazione tabella simboli, archi del grafo e convergenza PageRank."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph

        self.assertIn("test_mod.py:DataProcessor", graph.nodes)
        self.assertIn("test_mod.py:DataProcessor.process", graph.nodes)
        self.assertIn("test_mod.py:execute_pipeline", graph.nodes)
        self.assertGreater(len(graph.edges), 0)

        pr = PersonalizedPageRank.compute(
            graph,
            target_symbol_ids={"test_mod.py:execute_pipeline"},
            damping=0.85,
            max_iter=100,
            epsilon=1e-6,
        )
        self.assertTrue(pr.converged)
        self.assertAlmostEqual(sum(pr.scores.values()), 1.0, places=5)

    def test_karpathy_slicer_token_budgets(self):
        """2. Valida lo slicer chirurgico Karpathy singolo e multi-focale sotto budget."""
        for max_tokens in [200, 80]:
            res = KarpathySurgicalSlicer.slice_module(
                source_code=self.code,
                focal_symbol_names=["execute_pipeline"],
                module_path="test_mod.py",
                max_tokens=max_tokens,
            )
            self.assertLess(res.token_count, max_tokens)
            if max_tokens >= 200:
                self.assertIn("def execute_pipeline", res.sliced_code)

        multi_code = (
            "class ServiceA:\n    def method_one(self, a: int, b: str) -> bool:\n        return True\n"
            "class ServiceB:\n    def method_two(self, x: float) -> str:\n        return 'ok'\n"
        )
        res_multi = KarpathySurgicalSlicer.slice_module(
            source_code=multi_code,
            focal_symbol_names=["method_one", "method_two"],
            module_path="svc.py",
            max_tokens=300,
        )
        self.assertIn("method_one", res_multi.sliced_code)
        self.assertIn("method_two", res_multi.sliced_code)
        self.assertLessEqual(res_multi.token_count, 300)

    def test_atomic_cache_manager_concurrency(self):
        """3. Valida salvataggi concorrenti thread-safe e cache hit incrementale."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_file = tmp_path / "test_repo_cache.json"

            def worker_write(val: int):
                return AtomicCacheManager.save_atomic(
                    {"version": "6.0.0-Carbon", "val": val, "ts": time.time()}, cache_file
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                write_futures = [executor.submit(worker_write, i) for i in range(10)]
                read_futures = [
                    executor.submit(AtomicCacheManager.load_safe, cache_file)
                    for _ in range(10)
                ]
                write_results = [f.result() for f in write_futures]
                read_results = [f.result() for f in read_futures]

            self.assertTrue(all(write_results))
            self.assertTrue(all(r is None or isinstance(r, dict) for r in read_results))
            self.assertTrue(cache_file.exists())

            inc_cache = tmp_path / "inc_cache.json"
            (tmp_path / "a.py").write_text("def fn_a(): pass\n", encoding="utf-8")
            cfg = RepoMapConfig(
                max_tokens=512, cache_enabled=True, cache_dir=str(inc_cache)
            )
            res1 = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg)
            self.assertEqual(res1.cached_hits, 0)
            res2 = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg)
            self.assertGreaterEqual(res2.cached_hits, 1)
            is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
            max_ms = (450.0 if is_cov_instrumented() else 250.0) if is_ci else (300.0 if is_cov_instrumented() else 150.0)
            self.assertLess(res2.elapsed_ms, max_ms)

    def test_graduated_skill_adapter_and_snapshot(self):
        """4. Valida tetti GT-06 standard e argon_mode_*, estrazione poliglotta e compattazione."""
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Scribe-Memory"), 0)
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "mode_c"), 256
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "mode_b"), 512
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Orchestrator", "mode_a"), 1024
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "argon_mode_c"),
            512,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "argon_mode_b"),
            1500,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Orchestrator", "argon_mode_a"),
            4000,
        )

        js_code = "export class DashboardView extends BaseView { render() {} }\nexport async function fetchData(url) {}"
        names = [n.name for n in PolyglotExtractor.extract_symbols("app.js", js_code)]
        self.assertIn("DashboardView", names)
        self.assertIn("fetchData", names)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            synthetic_classes = set()
            for m_idx in range(4):
                lines = []
                for c_idx in range(3):
                    c_name = f"SyntheticEntity_{m_idx}_{c_idx}"
                    synthetic_classes.add(c_name)
                    lines.append(
                        f"class {c_name}:\n    def op_{c_idx}(self, x: int) -> int:\n        return x * {c_idx}\n"
                    )
                (tmp_path / f"service_mod_{m_idx}.py").write_text(
                    "\n".join(lines), encoding="utf-8"
                )

            cfg_syn = RepoMapConfig(max_tokens=1024, polyglot=False, cache_enabled=False)
            res_syn = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg_syn)
            self.assertLessEqual(res_syn.token_count, 850)
            for cls_name in synthetic_classes:
                self.assertIn(cls_name, res_syn.content)

            snap_file = tmp_path / "repo_map.md"
            export_markdown_snapshot(
                root_dir=tmp_path, output_path=snap_file, max_tokens=512
            )
            self.assertTrue(snap_file.exists())


def test_repo_mapper_includes_internal_dir_and_cli_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """5. Verifica che _internal non sia escluso e valida CLI main e __getattr__."""
    assert "_internal" not in DEFAULT_EXCLUDED_DIRS
    with pytest.raises(AttributeError):
        getattr(mapper_mod, "NON_EXISTENT_MAPPER_EXPORT")

    (tmp_path / "scripts" / "_internal").mkdir(parents=True)
    (tmp_path / "scripts" / "main_entry.py").write_text("def run_main():\n    return 1\n", encoding="utf-8")
    (tmp_path / "scripts" / "_internal" / "sub_helper.py").write_text(
        "def internal_helper_fn():\n    return 2\n", encoding="utf-8"
    )

    out_snap = tmp_path / "snap.md"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ast_repo_mapper.py", "--root", str(tmp_path), "--json", "--snapshot-out", str(out_snap)],
    )
    mapper_mod.main()
    raw_out = capsys.readouterr().out
    assert out_snap.is_file()
    json_start = raw_out.index("{")
    parsed = json.loads(raw_out[json_start:])
    assert "internal_helper_fn" in parsed["content"]

    monkeypatch.setattr(
        sys,
        "argv",
        ["ast_repo_mapper.py", "--root", str(tmp_path), "--symbol", "internal_helper_fn"],
    )
    mapper_mod.main()
    sym_out = json.loads(capsys.readouterr().out)
    assert sym_out["found"] is True and sym_out["symbol"] == "internal_helper_fn"
    assert len(sym_out["definitions"]) >= 1


def test_ranking_slicing_and_map_rendering_edge_branches(tmp_path: Path) -> None:
    """6. Verifica PageRank su grafo vuoto, compressione multi-focale e rendering 2-tier."""
    empty_pr = PersonalizedPageRank.compute(SymbolGraph())
    assert empty_pr.converged is True and empty_pr.scores == {}

    rich_code = (
        'CONST_VAL = 99\n'
        'class EmptyBox:\n    pass\n'
        'class Worker:\n    """Doc worker."""\n'
        '    def keep_me(self):\n        """Keep doc."""\n        return 1\n'
        '    def drop_me(self):\n        return 2\n'
        'async def async_job(a: int) -> int:\n    """Async doc."""\n    return a\n'
    )
    sliced_tight = KarpathySurgicalSlicer.slice_module(
        rich_code, ["keep_me", "Worker.keep_me"], module_path="w.py", max_tokens=2
    )
    assert "# " in sliced_tight.sliced_code
    sliced_mid = KarpathySurgicalSlicer.slice_module(
        rich_code, ["keep_me"], module_path="w.py", max_tokens=160
    )
    assert "def keep_me" in sliced_mid.sliced_code

    long_sig = (
        "def very_long_fn(alpha_one: int, beta_two: int, gamma_three: int, "
        "delta_four: int, epsilon_five: int, zeta_six: int, eta_seven: int) -> dict[str, int]:"
    )
    assert "..." in compact_sig_for_ste100_impl(long_sig, max_words=6)
    assert len(compact_sig_for_ste100_impl("word " * 20, max_words=5).split()) <= 5

    empty_map, _ = render_two_tier_map_impl(tmp_path, SymbolGraph(), {}, set(), 500)
    assert "REPO-MAP" in empty_map

    g = SymbolGraph()
    for i in range(14):
        mod = f"scripts/mod_{i}.py" if i < 12 else f"tests/test_mod_{i}.py"
        g.add_node(
            SymbolNode(
                id=f"{mod}:Cls_{i}",
                name=f"Cls_{i}",
                symbol_type=SymbolType.CLASS,
                module_path=mod,
                line_start=1,
                line_end=10,
            )
        )
        for m in range(10):
            g.add_node(
                SymbolNode(
                    id=f"{mod}:Cls_{i}._m{m}",
                    name=f"_m{m}" if m < 8 else f"pub_{m}",
                    symbol_type=SymbolType.METHOD,
                    module_path=mod,
                    parent_id=f"{mod}:Cls_{i}",
                    line_start=2 + m,
                    line_end=3 + m,
                )
            )
    const_only = [
        SymbolNode(
            id="scripts/consts.py:K",
            name="K",
            symbol_type=SymbolType.CONSTANT,
            module_path="scripts/consts.py",
            line_start=1,
            line_end=1,
        )
    ]
    assert "symbols" in render_inline_compact_module_impl("scripts/consts.py", const_only)
    assert "K" in render_expanded_module_impl("scripts/consts.py", const_only)

    content, tok = render_two_tier_map_impl(tmp_path, g, {}, {"scripts/mod_0.py:Cls_0"}, 920)
    assert tok <= 920 and "REPO-MAP" in content
    tiny_content, tiny_tok = render_two_tier_map_impl(tmp_path, g, {}, set(), 35)
    assert tiny_tok <= 35 and "REPO-MAP" in tiny_content


@pytest.mark.fast
def test_strict_symbol_models_and_json_cache_hydration(tmp_path: Path) -> None:
    """Verifica strict=True su SymbolNode/SymbolEdge e idratazione JSON cache in generator.py."""
    from pydantic import ValidationError
    from _internal.ast_repo_mapper.models import EdgeType, SymbolEdge

    assert SymbolNode.model_config.get("strict") is True and SymbolNode.model_config.get("frozen") is True
    assert SymbolEdge.model_config.get("strict") is True and SymbolEdge.model_config.get("frozen") is True

    n_obj = SymbolNode(
        id="pkg/a.py:Fn", name="Fn", symbol_type=SymbolType.FUNCTION,
        module_path="pkg/a.py", line_start=1, line_end=3,
    )
    e_obj = SymbolEdge(
        source_id="pkg/a.py:Fn", target_id="pkg/b.py:Helper",
        edge_type=EdgeType.CALL, weight=1.5,
    )
    n_hyd = SymbolNode.model_validate(json.loads(json.dumps(n_obj.model_dump())))
    e_hyd = SymbolEdge.model_validate(json.loads(json.dumps(e_obj.model_dump())))
    assert n_hyd.symbol_type is SymbolType.FUNCTION and e_hyd.edge_type is EdgeType.CALL

    with pytest.raises(ValidationError):
        SymbolNode.model_validate({"id": "x", "name": "x", "symbol_type": "FUNCTION", "module_path": "x.py", "line_start": "1", "line_end": 2})
    with pytest.raises(ValidationError):
        SymbolEdge.model_validate({"source_id": "a", "target_id": "b", "edge_type": 123, "weight": 1.0})

    repo_dir = tmp_path / "strict_cache_repo"
    (repo_dir / "pkg").mkdir(parents=True)
    (repo_dir / "pkg" / "helper.py").write_text("def cache_target_fn() -> int:\n    return 7\n", encoding="utf-8")
    (repo_dir / "pkg" / "caller.py").write_text("from pkg.helper import cache_target_fn\ndef invoke_cached() -> int:\n    return cache_target_fn()\n", encoding="utf-8")
    cache_file = tmp_path / "strict_repo_cache.json"
    cfg = RepoMapConfig(max_tokens=512, cache_enabled=True, cache_dir=str(cache_file))
    res1 = RepoMapGenerator.generate(root_dir=repo_dir, config=cfg)
    res2 = RepoMapGenerator.generate(root_dir=repo_dir, config=cfg)
    assert res1.cached_hits == 0 and res2.cached_hits == 2
    assert "cache_target_fn" in res2.content and "invoke_cached" in res2.content
    sub = mapper_mod.query_symbol_subgraph("cache_target_fn", root=repo_dir)
    assert sub["found"] is True and any("invoke_cached" in str(c) for c in sub["callers"])
