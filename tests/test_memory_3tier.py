# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per 3-Tier Episodic Memory Engine (v3.3.0).
Modulo: tests/test_memory_3tier.py.
Valida GT-05 (TIER1_TOKEN_CAP=350 e ARGON=1200), Tier-2/3, RRF, backup e MoveFileExW.
"""

from __future__ import annotations

import importlib.util
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


def _load_staging_memory_module():
    """Carica il modulo memory_3tier_engine dando priorita a .staging/scripts."""
    stg = STAGING_SCRIPTS_DIR / "memory_3tier_engine.py"
    target = stg if stg.exists() else (SCRIPTS_DIR / "memory_3tier_engine.py")
    spec = importlib.util.spec_from_file_location("memory_3tier_engine", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["memory_3tier_engine"] = mod
    spec.loader.exec_module(mod)
    return mod


_mem_mod = _load_staging_memory_module()
ThreeTierMemoryEngine = _mem_mod.ThreeTierMemoryEngine
MemoryEpisode = _mem_mod.MemoryEpisode
Tier1CoreMemory = _mem_mod.Tier1CoreMemory
HybridRRFSearchEngine = _mem_mod.HybridRRFSearchEngine
rotate_circular_backups = _mem_mod.rotate_circular_backups
win32_atomic_replace = _mem_mod.win32_atomic_replace
TIER1_TOKEN_CAP = _mem_mod.TIER1_TOKEN_CAP
TIER1_TOKEN_CAP_ARGON = getattr(_mem_mod, "TIER1_TOKEN_CAP_ARGON", 1200)


class TestMemory3TierEngine(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp.name)

    def tearDown(self):
        try:
            self._temp.cleanup()
        except Exception:
            pass

    def test_tier1_core_memory_350_tokens_cap(self):
        """1. Valida i limiti GT-05 (350 standard e 1200 argon) e tier1_active_capsule.json."""
        self.assertEqual(TIER1_TOKEN_CAP, 350)
        self.assertEqual(TIER1_TOKEN_CAP_ARGON, 1200)

        t1 = Tier1CoreMemory(token_cap=TIER1_TOKEN_CAP)
        domain = "02_Development_Patterns"
        for i in range(25):
            t1.set_item(
                domain=domain,
                key=f"pattern_{i}",
                value=f"Deterministic architectural pattern {i} with strict pydantic models and zero mock rule {i}",
                priority=i % 5 + 1,
            )
        self.assertLessEqual(t1.get_token_usage(domain), TIER1_TOKEN_CAP)

        engine = ThreeTierMemoryEngine(base_dir=self.tmp_dir, sliding_window_max=10)
        engine.append_episode(
            MemoryEpisode(
                episode_id="ep_cap_01",
                domain="02_Development_Patterns",
                title="Pattern Atomico Tier-1",
                content="Regola deterministica per il pre-warming della capsula Mode C.",
                tags=["tier1", "capsule"],
            )
        )
        capsule = engine.sync_tier1_capsule()
        self.assertTrue((self.tmp_dir / "tier1_active_capsule.json").exists())
        self.assertEqual(capsule["token_cap"], TIER1_TOKEN_CAP)
        for dom_info in capsule["domains"].values():
            self.assertLessEqual(dom_info["total_tokens"], TIER1_TOKEN_CAP)

    def test_tier2_scratchpad_sliding_window(self):
        """2. Valida la finestra scorrevole verso Tier-3 e la shadow read cache rapida."""
        engine = ThreeTierMemoryEngine(base_dir=self.tmp_dir, sliding_window_max=10)
        domain = "04_Governance_and_Rules"
        for i in range(15):
            engine.append_episode(
                MemoryEpisode(
                    episode_id=f"ep_{i:04d}",
                    domain=domain,
                    title=f"Rule {i}",
                    content=f"Governance content for event {i}",
                    tags=["gov"],
                )
            )

        t_start = time.perf_counter()
        t2_eps = engine.get_tier2_episodes(domain)
        t_duration = time.perf_counter() - t_start
        self.assertEqual(len(t2_eps), 10)
        self.assertLess(t_duration, 0.05)

        t3_eps = engine.get_tier3_episodes(domain)
        self.assertEqual(len(t3_eps), 5)

    def test_tier3_hybrid_bm25_dense_rrf_search(self):
        """3. Valida la ricerca ibrida BM25 e Dense Cosine con RRF k=60."""
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
        results = engine.search(
            "Win32 MoveFileExW lock resolution", episodes=episodes, top_k=3
        )
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][0].episode_id, "target_ep")

    def test_circular_backup_rotation_streaming(self):
        """4. Valida la rotazione circolare dei backup e la sostituzione atomica MoveFileExW."""
        target_file = self.tmp_dir / "test.jsonl"
        target_file.write_text("INITIAL_CONTENT", encoding="utf-8")

        rotate_circular_backups(target_file, depth=2)
        bak1 = self.tmp_dir / "test.jsonl.bak_1"
        self.assertTrue(bak1.exists())
        self.assertEqual(bak1.read_text(encoding="utf-8"), "INITIAL_CONTENT")

        src = self.tmp_dir / "src.txt"
        dst = self.tmp_dir / "dst.txt"
        src.write_text("ATOMIC_DATA", encoding="utf-8")
        win32_atomic_replace(src, dst)
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "ATOMIC_DATA")


if __name__ == "__main__":
    unittest.main()
