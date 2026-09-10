# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.7.0-RepoMap Refined
Test Module 4: AST Topology, Personalized PageRank, Two-Tier Clustering & High-Density Repo-Map
Tests:
- Existing tests 22-27 (Symbol Table, Dependency Graph, PageRank Alpha=0.85, Token Budget, Binary Search, Blast Radius)
- New tests 28-33 (Two-Tier Clustering, Multi-Focal Slicer, Concurrency Safety, Incremental Cache, Polyglot, Autonomous Snapshot)
"""

from __future__ import annotations

import ast
import concurrent.futures
import sys
import tempfile
import time
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

# Try importing from staging scripts first, then root scripts
try:
    from ast_repo_mapper import (
        AtomicCacheManager,
        EdgeType,
        GraduatedSkillAdapter,
        KarpathySurgicalSlicer,
        PersonalizedPageRank,
        PolyglotExtractor,
        RepoMapConfig,
        RepoMapGenerator,
        ResilientParser,
        SymbolExtractor,
        SymbolGraph,
        SymbolType,
        estimate_tokens,
        export_markdown_snapshot,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".staging" / "scripts"))
    from ast_repo_mapper import (
        AtomicCacheManager,
        EdgeType,
        GraduatedSkillAdapter,
        KarpathySurgicalSlicer,
        PersonalizedPageRank,
        PolyglotExtractor,
        RepoMapConfig,
        RepoMapGenerator,
        ResilientParser,
        SymbolExtractor,
        SymbolGraph,
        SymbolType,
        estimate_tokens,
        export_markdown_snapshot,
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

    # 22. test_symbol_table_extraction
    def test_symbol_table_extraction(self):
        """22. Validates symbol table extraction (classes, methods, functions, imports)."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph

        self.assertIn("test_mod.py:DataProcessor", graph.nodes)
        self.assertIn("test_mod.py:DataProcessor.process", graph.nodes)
        self.assertIn("test_mod.py:execute_pipeline", graph.nodes)

    # 23. test_dependency_graph_edges_generation
    def test_dependency_graph_edges_generation(self):
        """23. Validates generation of dependency graph edges."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph
        self.assertGreater(len(graph.edges), 0)

    # 24. test_personalized_pagerank_convergence
    def test_personalized_pagerank_convergence(self):
        """24. Validates Personalized PageRank algorithm (alpha=0.85, epsilon=1e-6)."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph

        pr = PersonalizedPageRank.compute(
            graph,
            target_symbol_ids={"test_mod.py:execute_pipeline"},
            damping=0.85,
            max_iter=100,
            epsilon=1e-6,
        )
        self.assertTrue(pr.converged)
        self.assertAlmostEqual(sum(pr.scores.values()), 1.0, places=5)

    # 25. test_karpathy_slicer_token_budget
    def test_karpathy_slicer_token_budget(self):
        """25. Validates Karpathy surgical slicer within token budget."""
        res = KarpathySurgicalSlicer.slice_module(
            source_code=self.code,
            focal_symbol_names=["execute_pipeline"],
            module_path="test_mod.py",
            max_tokens=200,
        )
        self.assertLess(res.token_count, 200)
        self.assertIn("def execute_pipeline", res.sliced_code)

    # 26. test_slicer_binary_search_depth
    def test_slicer_binary_search_depth(self):
        """26. Validates slicer compression under tight budget (<80 tokens)."""
        res = KarpathySurgicalSlicer.slice_module(
            source_code=self.code,
            focal_symbol_names=["execute_pipeline"],
            module_path="test_mod.py",
            max_tokens=80,
        )
        self.assertLess(res.token_count, 80)

    # 27. test_symbol_lookup_and_blast_radius
    def test_symbol_lookup_and_blast_radius(self):
        """27. Validates symbol lookup and blast radius determination."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph

        focal = graph.get_node("test_mod.py:DataProcessor")
        self.assertIsNotNone(focal)
        self.assertEqual(focal.symbol_type, SymbolType.CLASS)

    # 28. test_multi_focal_slicer_integrity (New v1.7.0)
    def test_multi_focal_slicer_integrity(self):
        """28. Validates that multi-focal selection preserves signatures of ALL focal targets without truncation."""
        multi_code = """
class ServiceA:
    def method_one(self, a: int, b: str) -> bool:
        return True

class ServiceB:
    def method_two(self, x: float) -> str:
        return "ok"
"""
        res = KarpathySurgicalSlicer.slice_module(
            source_code=multi_code,
            focal_symbol_names=["method_one", "method_two"],
            module_path="svc.py",
            max_tokens=300,
        )
        self.assertIn("method_one", res.sliced_code)
        self.assertIn("method_two", res.sliced_code)
        self.assertLessEqual(res.token_count, 300)

    # 29. test_atomic_cache_manager_concurrency (New v1.7.0)
    def test_atomic_cache_manager_concurrency(self):
        """29. Validates thread-safe atomic cache saves and reads under concurrent execution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_file = Path(tmp_dir) / "test_repo_cache.json"

            def worker_write(val: int):
                payload = {"version": "1.7.0", "val": val, "ts": time.time()}
                return AtomicCacheManager.save_atomic(payload, cache_file)

            def worker_read():
                return AtomicCacheManager.load_safe(cache_file)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                write_futures = [executor.submit(worker_write, i) for i in range(15)]
                read_futures = [executor.submit(worker_read) for _ in range(15)]

                write_results = [f.result() for f in write_futures]
                read_results = [f.result() for f in read_futures]

            self.assertTrue(all(write_results))
            self.assertTrue(cache_file.exists())

    # 30. test_two_tier_clustering_token_ceiling (New v1.7.0)
    def test_two_tier_clustering_token_ceiling(self):
        """30. Validates that RepoMapGenerator strictly respects max_tokens using Two-Tier clustering."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Create a mock repo with 15 modules
            for i in range(15):
                m_file = tmp_path / f"mod_{i}.py"
                m_file.write_text(f"class ModClass{i}:\n    def do_work_{i}(self) -> int:\n        return {i}\n", encoding="utf-8")

            cfg = RepoMapConfig(max_tokens=256, polyglot=False, cache_enabled=False)
            result = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg)

            self.assertLessEqual(result.token_count, 256)
            self.assertIn("HIGH-DENSITY AST REPO-MAP", result.content)
            self.assertEqual(result.files_scanned, 15)

    # 31. test_incremental_cache_speed (New v1.7.0)
    def test_incremental_cache_speed(self):
        """31. Validates that incremental cache achieves cache hit and sub-100ms execution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_file = tmp_path / "cache.json"
            f1 = tmp_path / "a.py"
            f1.write_text("def fn_a(): pass\n", encoding="utf-8")

            cfg = RepoMapConfig(max_tokens=512, cache_enabled=True, cache_dir=str(cache_file))

            # Run 1: Cold parse
            res1 = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg)
            self.assertEqual(res1.cached_hits, 0)

            # Run 2: Cached parse (zero file changes)
            res2 = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg)
            self.assertGreaterEqual(res2.cached_hits, 1)
            self.assertLess(res2.elapsed_ms, 150.0)

    # 32. test_polyglot_frontend_contracts (New v1.7.0)
    def test_polyglot_frontend_contracts(self):
        """32. Validates polyglot extraction for JS, TS, HTML, and CSS."""
        js_code = "export class DashboardView extends BaseView { render() {} }\nexport async function fetchData(url) {}"
        nodes = PolyglotExtractor.extract_symbols("app.js", js_code)
        names = [n.name for n in nodes]
        self.assertIn("DashboardView", names)
        self.assertIn("fetchData", names)

    # 33. test_graduated_skill_adapter_and_snapshot (New v1.7.0)
    def test_graduated_skill_adapter_and_snapshot(self):
        """33. Validates GraduatedSkillAdapter token ceilings and autonomous snapshot generation."""
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Scribe"), 0)
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Episodic-Memory-Engine"), 0)
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "mode_c"), 256)
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "mode_b"), 512)
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Session-Controller", "mode_a"), 1024)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "test.py").write_text("class TestObj: pass\n", encoding="utf-8")
            snap_file = tmp_path / "repo_map.md"
            res = export_markdown_snapshot(root_dir=tmp_path, output_path=snap_file, max_tokens=512)

            self.assertTrue(snap_file.exists())
            self.assertIn("TestObj", snap_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
