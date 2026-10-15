# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo di test 4: Topologia AST, Personalized PageRank, Clustering e Repo-Map.
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
STAGING_SCRIPTS_DIR = STAGING_DIR / ".staging" / "scripts"

if STAGING_SCRIPTS_DIR.exists() and (STAGING_SCRIPTS_DIR / "ast_repo_mapper.py").exists():
    if str(STAGING_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(STAGING_SCRIPTS_DIR))
elif str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

try:
    from ast_repo_mapper import (
        AtomicCacheManager,
        GraduatedSkillAdapter,
        KarpathySurgicalSlicer,
        PersonalizedPageRank,
        PolyglotExtractor,
        RepoMapConfig,
        RepoMapGenerator,
        SymbolExtractor,
        export_markdown_snapshot,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".staging" / "scripts"))
    from ast_repo_mapper import (
        AtomicCacheManager,
        GraduatedSkillAdapter,
        KarpathySurgicalSlicer,
        PersonalizedPageRank,
        PolyglotExtractor,
        RepoMapConfig,
        RepoMapGenerator,
        SymbolExtractor,
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
        """22. Valida l'estrazione della tabella simboli da codice Python."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph

        self.assertIn("test_mod.py:DataProcessor", graph.nodes)
        self.assertIn("test_mod.py:DataProcessor.process", graph.nodes)
        self.assertIn("test_mod.py:execute_pipeline", graph.nodes)

    # 23. test_dependency_graph_edges_generation
    def test_dependency_graph_edges_generation(self):
        """23. Valida la generazione degli archi del grafo delle dipendenze."""
        tree = ast.parse(self.code)
        extractor = SymbolExtractor(module_path="test_mod.py", source_lines=self.lines)
        extractor.visit(tree)
        graph = extractor.graph
        self.assertGreater(len(graph.edges), 0)

    # 24. test_personalized_pagerank_convergence
    def test_personalized_pagerank_convergence(self):
        """24. Valida l'algoritmo Personalized PageRank con alpha=0.85."""
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

    # 25. test_karpathy_slicer_token_budgets
    def test_karpathy_slicer_token_budgets(self):
        """25. Valida lo slicer chirurgico Karpathy sotto budget di 200 e 80 token."""
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

    # 28. test_multi_focal_slicer_integrity (New v1.7.0)
    def test_multi_focal_slicer_integrity(self):
        """28. Valida che la selezione multi-focale preservi tutte le firme target."""
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
        """29. Valida salvataggi e letture atomiche thread-safe in concorrenza."""
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

    # 31. test_incremental_cache_speed (New v1.7.0)
    def test_incremental_cache_speed(self):
        """31. Valida che la cache incrementale ottenga cache hit sotto i 150ms."""
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
        """32. Valida l'estrazione poliglotta per JS, TS, HTML e CSS."""
        js_code = "export class DashboardView extends BaseView { render() {} }\nexport async function fetchData(url) {}"
        nodes = PolyglotExtractor.extract_symbols("app.js", js_code)
        names = [n.name for n in nodes]
        self.assertIn("DashboardView", names)
        self.assertIn("fetchData", names)

    # 33. test_graduated_skill_adapter_and_snapshot (New v1.7.0)
    def test_graduated_skill_adapter_and_snapshot(self):
        """33. Valida i tetti token di GraduatedSkillAdapter e lo snapshot autonomo."""
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

    # 34. test_tier3_elastic_compaction_headroom (New CRV 4.0 Tier-3 Elastic Compactor)
    def test_tier3_elastic_compaction_headroom(self):
        """34. Valida il compattatore elastico Tier-3 con headroom garantito e zero omissioni."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            synthetic_classes = set()
            for m_idx in range(7):
                lines = []
                for c_idx in range(5):
                    c_name = f"SyntheticEntity_{m_idx}_{c_idx}"
                    synthetic_classes.add(c_name)
                    lines.append(f"class {c_name}:\n    def op_{c_idx}(self, x: int) -> int:\n        return x * {c_idx}\n")
                (tmp_path / f"service_mod_{m_idx}.py").write_text("\n".join(lines), encoding="utf-8")

            cfg_syn = RepoMapConfig(max_tokens=1024, polyglot=False, cache_enabled=False)
            res_syn = RepoMapGenerator.generate(root_dir=tmp_path, config=cfg_syn)

            self.assertLessEqual(res_syn.token_count, 850)
            self.assertGreaterEqual(1024 - res_syn.token_count, 170)
            self.assertNotIn("omessi per budget", res_syn.content)

            for cls_name in synthetic_classes:
                self.assertIn(cls_name, res_syn.content, f"Synthetic class '{cls_name}' missing from repo map")


if __name__ == "__main__":
    unittest.main()
