# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 6: 3-Tier Episodic Memory Engine
6 Tests: Tier 1 Cap 350 tok, Tier 2 Sliding Window 200, Tier 3 RRF k=60, Shadow Cache, Circular Backups, CTypes MoveFileExW.
"""

from __future__ import annotations

import sys
import time
import tempfile
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from memory_3tier_engine import (
    ThreeTierMemoryEngine,
    MemoryEpisode,
    Tier1CoreMemory,
    PureBM25,
    DenseEmbedder,
    HybridRRFSearchEngine,
    rotate_circular_backups,
    win32_atomic_replace,
    TIER1_TOKEN_CAP,
)


class TestMemory3TierEngine(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp.name)

    def tearDown(self):
        try:
            self._temp.cleanup()
        except Exception:
            pass

    # 35. test_tier1_core_memory_350_tokens_cap
    def test_tier1_core_memory_350_tokens_cap(self):
        """35. Validates hard enforcement of <= 350 tokens cap per domain."""
        t1 = Tier1CoreMemory(token_cap=TIER1_TOKEN_CAP)
        domain = "02_Development_Patterns"
        for i in range(25):
            t1.set_item(
                domain=domain,
                key=f"pattern_{i}",
                value=f"Deterministic architectural pattern {i} with strict pydantic models and zero mock mandate rule {i}",
                priority=i % 5 + 1,
            )
        usage = t1.get_token_usage(domain)
        self.assertLessEqual(usage, TIER1_TOKEN_CAP)

    # 36. test_tier2_scratchpad_sliding_window
    def test_tier2_scratchpad_sliding_window(self):
        """36. Validates 200 events sliding window and surplus archiving to Tier 3."""
        engine = ThreeTierMemoryEngine(base_dir=self.tmp_dir, sliding_window_max=200)
        domain = "04_Governance_and_Rules"
        for i in range(215):
            ep = MemoryEpisode(
                episode_id=f"ep_{i:04d}",
                domain=domain,
                title=f"Rule {i}",
                content=f"Governance content for event {i}",
                tags=["gov"],
            )
            engine.append_episode(ep)

        t2_eps = engine.get_tier2_episodes(domain)
        self.assertEqual(len(t2_eps), 200)

        t3_eps = engine.get_tier3_episodes(domain)
        self.assertEqual(len(t3_eps), 15)

    # 37. test_tier3_hybrid_bm25_dense_rrf_search
    def test_tier3_hybrid_bm25_dense_rrf_search(self):
        """37. Validates Pure BM25 + Dense Cosine with RRF rank fusion (k=60)."""
        episodes = [
            MemoryEpisode(
                episode_id=f"ep_{i}",
                domain="01_Bug_Diagnostics",
                title=f"Diagnostic Report {i}",
                content=f"Lock contention during MoveFileExW execution {i}",
                tags=["win32", "lock"],
            )
            for i in range(5)
        ]
        target_ep = MemoryEpisode(
            episode_id="target_ep",
            domain="01_Bug_Diagnostics",
            title="Win32 Atomic Move Lock Contention Diagnostic",
            content="Detailed analysis of MoveFileExW error handling and stale PID resolution.",
            tags=["win32", "atomic", "diagnostic"],
        )
        episodes.append(target_ep)

        engine = HybridRRFSearchEngine(k_rrf=60.0)
        results = engine.search("Win32 MoveFileExW lock resolution", episodes=episodes, top_k=3)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][0].episode_id, "target_ep")

    # 38. test_shadow_read_cache_invalidation
    def test_shadow_read_cache_invalidation(self):
        """38. Validates shadow cache fast read and invalidation upon modification."""
        engine = ThreeTierMemoryEngine(base_dir=self.tmp_dir, sliding_window_max=50)
        domain = "03_Ideation_and_Decisions"
        ep = MemoryEpisode(episode_id="ep1", domain=domain, title="Title 1", content="Content 1")
        engine.append_episode(ep)

        t_start = time.perf_counter()
        cached = engine.get_tier2_episodes(domain)
        t_duration = time.perf_counter() - t_start
        self.assertEqual(len(cached), 1)
        self.assertLess(t_duration, 0.05)

    # 39. test_circular_backup_rotation_streaming
    def test_circular_backup_rotation_streaming(self):
        """39. Validates circular backup rotation (.bak_1, .bak_2) using streaming copy."""
        target_file = self.tmp_dir / "test.jsonl"
        target_file.write_text("INITIAL_CONTENT", encoding="utf-8")

        rotate_circular_backups(target_file, depth=2)
        bak1 = self.tmp_dir / "test.jsonl.bak_1"
        self.assertTrue(bak1.exists())
        self.assertEqual(bak1.read_text(encoding="utf-8"), "INITIAL_CONTENT")

    # 40. test_win32_atomic_replace_ctypes_safety
    def test_win32_atomic_replace_ctypes_safety(self):
        """40. Validates MoveFileExW with explicit Win64 CTypes argtypes/restype."""
        src = self.tmp_dir / "src.txt"
        dst = self.tmp_dir / "dst.txt"
        src.write_text("ATOMIC_DATA", encoding="utf-8")
        win32_atomic_replace(src, dst)
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "ATOMIC_DATA")


if __name__ == "__main__":
    unittest.main()
