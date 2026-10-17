# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Topologia AST, PageRank, Slicer e Repo-Map (v3.3.0).
Modulo: tests/test_ast_repo_mapper.py.
Valida SymbolExtractor, PageRank, Karpathy Slicer, cache concorrente e la guardia GT-06.
"""

from __future__ import annotations

import ast
import concurrent.futures
from pathlib import Path
import sys
import tempfile
import time
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
STAGING_SCRIPTS_DIR = WORKSPACE_ROOT / ".staging" / "scripts"

for _cand in (STAGING_SCRIPTS_DIR, SCRIPTS_DIR, WORKSPACE_ROOT):
    if _cand.exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

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
        """3. Valida salvataggi concorrenti thread-safe e cache hit incrementale < 150ms."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_file = tmp_path / "test_repo_cache.json"

            def worker_write(val: int):
                return AtomicCacheManager.save_atomic(
                    {"version": "3.3.0", "val": val, "ts": time.time()}, cache_file
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                write_futures = [executor.submit(worker_write, i) for i in range(10)]
                read_futures = [
                    executor.submit(AtomicCacheManager.load_safe, cache_file)
                    for _ in range(10)
                ]
                write_results = [f.result() for f in write_futures]
                _ = [f.result() for f in read_futures]

            self.assertTrue(all(write_results))
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
            self.assertLess(res2.elapsed_ms, 150.0)

    def test_graduated_skill_adapter_and_snapshot(self):
        """4. Valida tetti GT-06 standard e argon_mode_*, estrazione poliglotta e compattazione."""
        self.assertEqual(GraduatedSkillAdapter.get_token_budget("NK-Scribe"), 0)
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Episodic-Memory-Engine"), 0
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "mode_c"),
            256,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Python-Async-Builder", "mode_b"),
            512,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget("NK-Session-Controller", "mode_a"),
            1024,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget(
                "NK-Python-Async-Builder", "argon_mode_c"
            ),
            512,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget(
                "NK-Python-Async-Builder", "argon_mode_b"
            ),
            1500,
        )
        self.assertEqual(
            GraduatedSkillAdapter.get_token_budget(
                "NK-Session-Controller", "argon_mode_a"
            ),
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


if __name__ == "__main__":
    unittest.main()
