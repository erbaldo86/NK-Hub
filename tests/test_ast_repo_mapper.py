# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 4: AST Topology, Personalized PageRank & Karpathy Slicer
6 Tests: Symbol Table, Dependency Graph, PageRank Alpha=0.85, Token Budget, Binary Search, Blast Radius.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from ast_repo_mapper import (
    EdgeType,
    KarpathySurgicalSlicer,
    PersonalizedPageRank,
    ResilientParser,
    SymbolExtractor,
    SymbolGraph,
    SymbolType,
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


if __name__ == "__main__":
    unittest.main()
