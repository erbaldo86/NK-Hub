# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per 3-Tier Episodic Memory Engine (v6.4.0-Carbon).
Modulo: tests/test_memory_3tier.py.
Valida GT-05 (350/1200 token), Tier-2/3, RRF, FTS5, polarita, backup e CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

import pytest

try:
    from conftest import (
        call_script_main_captured,
        is_cov_instrumented,
        load_nk_script_module,
    )
except ImportError:
    from tests.conftest import (
        call_script_main_captured,
        is_cov_instrumented,
        load_nk_script_module,
    )

pytestmark = pytest.mark.fast

_mem_mod = load_nk_script_module("memory_3tier_engine")
DenseEmbedder = _mem_mod.DenseEmbedder
HybridRRFSearchEngine = _mem_mod.HybridRRFSearchEngine
MemoryEpisode = _mem_mod.MemoryEpisode
TIER1_TOKEN_CAP = _mem_mod.TIER1_TOKEN_CAP
TIER1_TOKEN_CAP_ARGON = getattr(_mem_mod, "TIER1_TOKEN_CAP_ARGON", 1200)
ThreeTierMemoryEngine = _mem_mod.ThreeTierMemoryEngine
Tier1CoreMemory = _mem_mod.Tier1CoreMemory
consolidate_similar_episodes = _mem_mod.consolidate_similar_episodes
resolve_domain = _mem_mod.resolve_domain
rotate_circular_backups = _mem_mod.rotate_circular_backups
sync_tier1_capsule = _mem_mod.sync_tier1_capsule
win32_atomic_replace = _mem_mod.win32_atomic_replace


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
        engine = ThreeTierMemoryEngine(base_dir=self.tmp_dir, sliding_window_max=5)
        domain = "04_Governance_and_Rules"
        for i in range(7):
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
        self.assertEqual(len(t2_eps), 5)
        self.assertLess(t_duration, 0.15 if is_cov_instrumented() else 0.05)

        t3_eps = engine.get_tier3_episodes(domain)
        self.assertEqual(len(t3_eps), 2)

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

    def test_cold_archive_o1_append_and_corruption_recovery(self):
        """5. Valida append O(1) su archive.cold.jsonl.gz, isolamento cache SHA-256 e auto-recovery JSONL."""
        proj_a = self.tmp_dir / "proj_a"
        proj_b = self.tmp_dir / "proj_b"
        eng_a = ThreeTierMemoryEngine(base_dir=proj_a, sliding_window_max=2)
        eng_b = ThreeTierMemoryEngine(base_dir=proj_b, sliding_window_max=2)
        self.assertNotEqual(eng_a._project_cache_id, eng_b._project_cache_id)
        self.assertEqual(len(eng_a._project_cache_id), 12)
        self.assertNotEqual(eng_a.cache_dir, eng_b.cache_dir)

        domain = "01_Bug_Diagnostics"
        for idx in range(5):
            eng_a.append_episode(
                MemoryEpisode(
                    episode_id=f"ep_cold_{idx}",
                    domain=domain,
                    title=f"Cold Archive Item {idx}",
                    content=f"Detailed cold archive payload for item {idx}",
                    tags=["cold", "gzip"],
                )
            )

        cold_file = proj_a / domain / "archive.cold.jsonl.gz"
        self.assertTrue(cold_file.exists())
        self.assertEqual(len(eng_a.get_tier3_episodes(domain)), 3)

        raw_gz = cold_file.read_bytes()
        cold_file.write_bytes(raw_gz[:-6])
        recovered_cold = eng_a.get_tier3_episodes(domain)
        self.assertGreaterEqual(len(recovered_cold), 2)
        self.assertTrue(cold_file.exists())

        t2_file = proj_a / domain / "episodes.jsonl"
        with open(t2_file, "a", encoding="utf-8") as fh:
            fh.write("{corrupted_json_line_not_valid\n")
        self.assertEqual(len(eng_a._load_tier2_raw(t2_file)), 2)

        t2_file.write_text("{corrupted_only_line\n", encoding="utf-8")
        recovered_t2 = eng_a._load_tier2_raw(t2_file)
        self.assertGreaterEqual(len(recovered_t2), 1)

        unrelated_hits = eng_a.recall_hybrid(
            domain, "zzzz_nonexistent_quantum_banana_999"
        )
        self.assertEqual(unrelated_hits, [])
        self.assertEqual(
            eng_a.search_engine.search(
                "!!!", [MemoryEpisode(episode_id="ep_m18", domain=domain, title="t", content="c")]
            ),
            [],
        )
        eng_a.tier1.token_cap = 500
        eng_a.tier1.set_item(domain, "k1", "piccolo testo dieci token", priority=1)
        self.assertGreaterEqual(len(eng_a.tier1._domains[domain].items), 1)
        corrupt_head_gz = proj_a / "corrupt_head.jsonl.gz"
        corrupt_head_gz.write_bytes(b"BAD!" + raw_gz)
        self.assertGreaterEqual(len(eng_a._read_cold_archive(corrupt_head_gz)), 2)


def test_memory_domain_embedder_polarity_and_backups(tmp_path: Path) -> None:
    """6. Verifica resolve_domain, vettori densi, polarita opposta e rotazione backup."""
    assert resolve_domain("ops") == "01_Bug_Diagnostics"
    assert resolve_domain("ARCH") == "02_Development_Patterns"
    with pytest.raises(ValueError, match="unknown domain"):
        resolve_domain("INVALID_DOM")

    assert DenseEmbedder.vector_from_text("", dim=0) == []
    assert all(x == 0.0 for x in DenseEmbedder.vector_from_text("", dim=8))
    assert DenseEmbedder.cosine_similarity([], [1.0]) == 0.0
    assert DenseEmbedder.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    t1 = Tier1CoreMemory(profile="carbon")
    assert t1.token_cap == 1200
    assert t1.get_token_usage("BAD") == 0
    assert t1.get_context_string("BAD") == ""
    t1.set_item("DEVX", "k1", "valore uno", priority=2)
    assert "[k1] valore uno" in t1.get_context_string("DEVX")

    assert _mem_mod._has_opposite_polarity("always enable cache", "never enable cache") is True
    assert _mem_mod._has_opposite_polarity("enable cache", "allow cache") is False

    empty_file = tmp_path / "empty.jsonl"
    empty_file.touch()
    rotate_circular_backups(empty_file, depth=2)
    assert not (tmp_path / "empty.jsonl.bak_1").exists()

    trk_file = tmp_path / "nk_tracking" / "memory_3tier" / "ep.jsonl"
    trk_file.parent.mkdir(parents=True)
    trk_file.write_text("v1\n", encoding="utf-8")
    bkp_dir = tmp_path / "custom_bkp"
    rotate_circular_backups(trk_file, depth=2, backup_dir=bkp_dir)
    trk_file.write_text("v2\n", encoding="utf-8")
    rotate_circular_backups(trk_file, depth=2, backup_dir=bkp_dir)
    assert (bkp_dir / "ep.jsonl.bak_1").read_text(encoding="utf-8") == "v2\n"
    assert (bkp_dir / "ep.jsonl.bak_2").read_text(encoding="utf-8") == "v1\n"


def test_memory_fts5_cache_adaptive_recall_and_consolidation(tmp_path: Path) -> None:
    """7. Verifica FTS5 cache hit/miss, recall adattivo, consolidazione e guardie polarita."""
    eng = ThreeTierMemoryEngine(base_dir=tmp_path, sliding_window_max=1, profile="carbon")
    assert eng.recall_hybrid("OPS", "") == []
    assert eng.recall_hybrid("OPS", "!!") == []

    eps = [
        MemoryEpisode(
            episode_id="c1",
            domain="01_Bug_Diagnostics",
            title="Always enable SQLite WAL",
            content="Always enable SQLite WAL mode for concurrent reads and atomic durability.",
            tags=["sqlite", "wal", "durability"],
            metadata={"source_url": "https://example.org/wal"},
        ),
        MemoryEpisode(
            episode_id="c2",
            domain="01_Bug_Diagnostics",
            title="Always enable SQLite WAL",
            content="Always enable SQLite WAL mode for concurrent reads and atomic durability.",
            tags=["extra_tag"],
            metadata={"evidence_quote": "WAL durability confirmed"},
        ),
        MemoryEpisode(
            episode_id="c3",
            domain="01_Bug_Diagnostics",
            title="Never enable SQLite WAL",
            content="Never enable SQLite WAL mode on read-only NFS mounts.",
            tags=["sqlite", "nfs"],
        ),
    ]
    for ep in eps:
        eng.append_episode(ep)

    cold_gz = tmp_path / "01_Bug_Diagnostics" / "archive.cold.jsonl.gz"
    assert len(eng._search_cold_fts5(cold_gz, "sqlite wal", limit=10)) >= 1
    assert len(eng._search_cold_fts5(cold_gz, "sqlite wal", limit=10)) >= 1
    assert eng._search_cold_fts5(cold_gz, "!", limit=5) == []

    hits = eng.recall_hybrid("OPS", "sqlite nfs nonexistent_extra_kw1 nonexistent_extra_kw2", adaptive=True)
    assert len(hits) >= 1

    with pytest.raises(ValueError):
        consolidate_similar_episodes(base_dir=tmp_path, threshold=True)
    with pytest.raises(ValueError):
        consolidate_similar_episodes(base_dir=tmp_path, threshold=1.5)

    eng_cons = ThreeTierMemoryEngine(base_dir=tmp_path / "cons", sliding_window_max=10)
    for ep in eps:
        eng_cons.append_episode(ep)
    cons_res = consolidate_similar_episodes(root=tmp_path / "cons", domain="OPS", threshold=0.90)
    assert cons_res["merged_count"] == 1
    assert cons_res["remaining_count"] == 2

    eng_cons._cold_fts_db_path = tmp_path / "missing_dir_parent" / "bad_fts.db"
    (tmp_path / "missing_dir_parent").write_text("file_blocks_dir", encoding="utf-8")
    assert len(eng._get_cached_cold_episodes(cold_gz)) >= 2


def test_memory_3tier_cli_entrypoints_and_sync_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8. Verifica helper sync_tier1_capsule e tutti i sottocomandi CLI di memory_3tier_engine."""
    out_cap = tmp_path / "custom_capsule.json"
    cap = sync_tier1_capsule(base_dir=tmp_path, output_path=out_cap, profile="standard")
    assert out_cap.is_file() and cap["token_cap"] == 350

    base = tmp_path / "cli_mem"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "memory_3tier_engine.py",
            "--base-dir",
            str(base),
            "--append",
            "--domain",
            "ARCH",
            "--title",
            "Pattern Async",
            "--content",
            "Usa asyncio per I/O non bloccante",
            "--tags",
            "async,io",
            "--json",
        ],
    )
    rc_app, out_app, _ = call_script_main_captured(_mem_mod, sys.argv[1:])
    assert rc_app == 0 and json.loads(out_app)["status"] == "APPENDED"

    for extra_args, marker in (
        (["--base-dir", str(base), "--tier1-sync", "--json"], "domains"),
        (["--base-dir", str(base), "--consolidate", "--domain", "ARCH", "--json"], "CONSOLIDATED"),
        (["--base-dir", str(base), "--recall", "--domain", "ARCH", "--query", "asyncio", "--json"], "Pattern Async"),
        (["--base-dir", str(base)], "Ready."),
    ):
        monkeypatch.setattr(sys, "argv", ["memory_3tier_engine.py", *extra_args])
        rc, out, _ = call_script_main_captured(_mem_mod, extra_args)
        assert rc == 0 and marker in out
