# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per 3-Tier Episodic Memory Engine (v1.0.0-Generation).
Modulo: tests/test_memory_3tier.py.
Valida GT-05 (350/1200 token), Tier-2/3, RRF, FTS5, polarita, backup, models.py e CLI.
"""

from __future__ import annotations

import gzip
import json
import os as _real_os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

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


@pytest.mark.integration
def test_tier1_core_memory_350_1200_caps_and_sliding_window(tmp_path: Path) -> None:
    """1. Valida limiti GT-05 (350/1200), tier1_active_capsule.json e finestra scorrevole Tier-2/3."""
    assert TIER1_TOKEN_CAP == 350 and TIER1_TOKEN_CAP_ARGON == 1200

    t1 = Tier1CoreMemory(token_cap=TIER1_TOKEN_CAP)
    domain_dev = "02_Development_Patterns"
    for i in range(25):
        t1.set_item(
            domain=domain_dev,
            key=f"pattern_{i}",
            value=f"Deterministic architectural pattern {i} with strict pydantic models and zero mock rule {i}",
            priority=i % 5 + 1,
        )
    assert t1.get_token_usage(domain_dev) <= TIER1_TOKEN_CAP

    engine = ThreeTierMemoryEngine(base_dir=tmp_path / "t1_ws", sliding_window_max=10)
    engine.append_episode(
        MemoryEpisode(
            episode_id="ep_cap_01",
            domain=domain_dev,
            title="Pattern Atomico Tier-1",
            content="Regola deterministica per il pre-warming della capsula Mode C.",
            tags=["tier1", "capsule"],
        )
    )
    capsule = engine.sync_tier1_capsule()
    assert (tmp_path / "t1_ws" / "tier1_active_capsule.json").exists()
    assert capsule["token_cap"] == TIER1_TOKEN_CAP
    for dom_info in capsule["domains"].values():
        assert dom_info["total_tokens"] <= TIER1_TOKEN_CAP

    eng_win = ThreeTierMemoryEngine(base_dir=tmp_path / "t2_win", sliding_window_max=5)
    domain_gov = "04_Governance_and_Rules"
    for i in range(7):
        eng_win.append_episode(
            MemoryEpisode(
                episode_id=f"ep_{i:04d}",
                domain=domain_gov,
                title=f"Rule {i}",
                content=f"Governance content for event {i}",
                tags=["gov"],
            )
        )
    t_start = time.perf_counter()
    t2_eps = eng_win.get_tier2_episodes(domain_gov)
    t_duration = time.perf_counter() - t_start
    assert len(t2_eps) == 5
    assert t_duration < (0.15 if is_cov_instrumented() else 0.05)
    assert len(eng_win.get_tier3_episodes(domain_gov)) == 2


def _assert_cold_corrupt_tail_and_gz(eng_a: Any, proj_a: Path, domain: str, raw_gz: bytes) -> None:
    t2_file = proj_a / domain / "episodes.jsonl"
    with open(t2_file, "a", encoding="utf-8") as fh:
        fh.write("{corrupted_json_line_not_valid\n")
    assert len(eng_a._load_tier2_raw(t2_file)) == 2

    t2_file.write_text("{corrupted_only_line\n", encoding="utf-8")
    assert len(eng_a._load_tier2_raw(t2_file)) >= 1

    assert eng_a.recall_hybrid(domain, "zzzz_nonexistent_quantum_banana_999") == []
    assert eng_a.search_engine.search("!!!", [MemoryEpisode(episode_id="ep_m18", domain=domain, title="t", content="c")]) == []
    eng_a.tier1.token_cap = 500
    eng_a.tier1.set_item(domain, "k1", "piccolo testo dieci token", priority=1)
    assert len(eng_a.tier1._domains[domain].items) >= 1
    corrupt_head_gz = proj_a / "corrupt_head.jsonl.gz"
    corrupt_head_gz.write_bytes(b"BAD!" + raw_gz)
    assert len(eng_a._read_cold_archive(corrupt_head_gz)) >= 2


@pytest.mark.integration
def test_cold_archive_o1_append_and_corruption_recovery(tmp_path: Path) -> None:
    """2. Valida append O(1) su archive.cold.jsonl.gz, isolamento cache SHA-256 e auto-recovery JSONL."""
    proj_a = tmp_path / "proj_a"
    proj_b = tmp_path / "proj_b"
    eng_a = ThreeTierMemoryEngine(base_dir=proj_a, sliding_window_max=2)
    eng_b = ThreeTierMemoryEngine(base_dir=proj_b, sliding_window_max=2)
    assert eng_a._project_cache_id != eng_b._project_cache_id
    assert len(eng_a._project_cache_id) == 12
    assert eng_a.cache_dir != eng_b.cache_dir

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
    assert cold_file.exists()
    assert len(eng_a.get_tier3_episodes(domain)) == 3

    raw_gz = cold_file.read_bytes()
    cold_file.write_bytes(raw_gz[:-6])
    assert len(eng_a.get_tier3_episodes(domain)) >= 2
    assert cold_file.exists()
    _assert_cold_corrupt_tail_and_gz(eng_a, proj_a, domain, raw_gz)


def _assert_rrf_and_embedder() -> None:
    assert resolve_domain("ops") == "01_Bug_Diagnostics"
    assert resolve_domain("ARCH") == "02_Development_Patterns"
    with pytest.raises(ValueError, match="unknown domain"):
        resolve_domain("INVALID_DOM")

    episodes = [
        MemoryEpisode(
            episode_id=f"ep_{i}", domain="01_Bug_Diagnostics", title=f"Diagnostic Report {i}",
            content=f"Lock contention during MoveFileExW execution {i}", tags=["win32", "lock"],
        )
        for i in range(5)
    ] + [
        MemoryEpisode(
            episode_id="target_ep", domain="01_Bug_Diagnostics",
            title="Win32 Atomic Move Lock Contention Diagnostic",
            content="Detailed analysis of MoveFileExW error handling and stale PID resolution.",
            tags=["win32", "atomic", "diagnostic"],
        )
    ]
    rrf_res = HybridRRFSearchEngine(k_rrf=60.0).search("Win32 MoveFileExW lock resolution", episodes=episodes, top_k=3)
    assert len(rrf_res) == 3
    assert rrf_res[0][0].episode_id == "target_ep"

    assert DenseEmbedder.vector_from_text("", dim=0) == []
    assert all(x == 0.0 for x in DenseEmbedder.vector_from_text("", dim=8))
    assert DenseEmbedder.cosine_similarity([], [1.0]) == 0.0
    assert DenseEmbedder.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def _assert_polarity_and_backups(tmp_path: Path) -> None:
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
    bkp_dir = tmp_path / "custom_bkp"
    for step in ("v1\n", "v2\n"):
        trk_file.write_text(step, encoding="utf-8")
        rotate_circular_backups(trk_file, depth=2, backup_dir=bkp_dir)
    assert (bkp_dir / "ep.jsonl.bak_1").read_text(encoding="utf-8") == "v2\n"
    assert (bkp_dir / "ep.jsonl.bak_2").read_text(encoding="utf-8") == "v1\n"

    src, dst = tmp_path / "src.txt", tmp_path / "dst.txt"
    src.write_text("ATOMIC_DATA", encoding="utf-8")
    win32_atomic_replace(src, dst)
    assert dst.read_text(encoding="utf-8") == "ATOMIC_DATA"


@pytest.mark.fast
def test_memory_domain_embedder_rrf_polarity_and_backups(tmp_path: Path) -> None:
    """3. Verifica resolve_domain, RRF k=60, vettori densi, polarita opposta e rotazione backup."""
    _assert_rrf_and_embedder()
    _assert_polarity_and_backups(tmp_path)


def _assert_adaptive_recall_and_empty_cons(tmp_path: Path) -> None:
    empty_eng = ThreeTierMemoryEngine(base_dir=tmp_path / "empty_m", sliding_window_max=5)
    assert empty_eng.recall_hybrid("OPS", "sqlite wal") == []
    assert ThreeTierMemoryEngine._char_trigram_cosine("", "abc") == 0.0
    assert ThreeTierMemoryEngine._char_trigram_cosine("alpha beta", "alpha beta gamma") > 0.5

    eng_adp = ThreeTierMemoryEngine(base_dir=tmp_path / "adp_m", sliding_window_max=5)
    eng_adp.append_episode(
        MemoryEpisode(
            episode_id="ep_adp_1", domain="01_Bug_Diagnostics", title="Alpha Fix",
            content="Alpha pattern resolves lock error", tags=["beta_tag", "gamma_tag"],
        )
    )
    assert len(eng_adp.recall_hybrid("OPS", "alpha nonexistent_kw1 nonexistent_kw2", adaptive=False)) == 1
    assert len(eng_adp.recall_hybrid("OPS", "alpha nonexistent_kw1 nonexistent_kw2", adaptive=True)) == 1

    hub_root = tmp_path / "hub_cons_root"
    (hub_root / "nk_tracking" / "memory_3tier").mkdir(parents=True)
    assert consolidate_similar_episodes(root=hub_root)["passed"] is True
    plain_root = tmp_path / "plain_cons_root"
    plain_root.mkdir()
    assert consolidate_similar_episodes(root=plain_root)["passed"] is True


@pytest.mark.integration
def test_memory_fts5_cache_adaptive_recall_and_consolidation(tmp_path: Path) -> None:
    """4. Verifica FTS5 cache hit/miss, recall adattivo, trigram cosine e consolidazione."""
    eng = ThreeTierMemoryEngine(base_dir=tmp_path, sliding_window_max=1, profile="carbon")
    assert eng.recall_hybrid("OPS", "") == []
    assert eng.recall_hybrid("OPS", "!!") == []

    eps = [
        MemoryEpisode(
            episode_id="c1", domain="01_Bug_Diagnostics", title="Always enable SQLite WAL",
            content="Always enable SQLite WAL mode for concurrent reads and atomic durability.",
            tags=["sqlite", "wal", "durability"], metadata={"source_url": "https://example.org/wal"},
        ),
        MemoryEpisode(
            episode_id="c2", domain="01_Bug_Diagnostics", title="Always enable SQLite WAL",
            content="Always enable SQLite WAL mode for concurrent reads and atomic durability.",
            tags=["extra_tag"], metadata={"evidence_quote": "WAL durability confirmed"},
        ),
        MemoryEpisode(
            episode_id="c3", domain="01_Bug_Diagnostics", title="Never enable SQLite WAL",
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
    assert len(eng.recall_hybrid("OPS", "sqlite nfs nonexistent_extra_kw1 nonexistent_extra_kw2", adaptive=True)) >= 1

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
    _assert_adaptive_recall_and_empty_cons(tmp_path)


@pytest.mark.integration
def test_memory_3tier_cli_entrypoints_and_sqlite_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Verifica sync_tier1_capsule, sqlite_store.py (multi-member gzip/bak) e CLI JSON/testo."""
    from _internal.memory_3tier_engine import sqlite_store as ss

    out_cap = tmp_path / "custom_capsule.json"
    cap = sync_tier1_capsule(base_dir=tmp_path, output_path=out_cap, profile="standard")
    assert out_cap.is_file() and cap["token_cap"] == 350

    base = tmp_path / "cli_mem"
    for cli_args, marker in (
        (["--base-dir", str(base), "--append", "--domain", "ARCH", "--title", "Pattern Async", "--content", "Usa asyncio per I/O non bloccante", "--tags", "async,io", "--json"], "APPENDED"),
        (["--base-dir", str(base), "--tier1-sync", "--json"], "domains"),
        (["--base-dir", str(base), "--consolidate", "--domain", "ARCH", "--json"], "CONSOLIDATED"),
        (["--base-dir", str(base), "--recall", "--domain", "ARCH", "--query", "asyncio", "--json"], "Pattern Async"),
        (["--base-dir", str(base)], "Ready."),
    ):
        monkeypatch.setattr(sys, "argv", ["memory_3tier_engine.py", *cli_args])
        rc, out, _ = call_script_main_captured(_mem_mod, cli_args)
        assert rc == 0 and marker in out

    assert ss.read_cold_archive_impl(tmp_path / "absent.gz") == []
    assert ss.load_tier2_raw_impl(tmp_path / "absent.jsonl") == []
    ss.archive_to_tier3_impl(tmp_path, "01_Bug_Diagnostics", [])

    eng = ThreeTierMemoryEngine(base_dir=tmp_path / "ss_ws", sliding_window_max=5)
    cold_gz = tmp_path / "ss_ws" / "01_Bug_Diagnostics" / "archive.cold.jsonl.gz"
    ep1 = MemoryEpisode(episode_id="g1", domain="01_Bug_Diagnostics", title="Consolidazione", content="Consolidazione indice SQLite", tags=["sqlite"])
    ep2 = MemoryEpisode(episode_id="g2", domain="01_Bug_Diagnostics", title="Secondo", content="Secondo record valido", tags=["wal"])
    m1 = gzip.compress((ep1.model_dump_json() + "\n{bad_line\n").encode("utf-8"))
    m2 = gzip.compress((ep2.model_dump_json() + "\n").encode("utf-8"))
    cold_gz.write_bytes(m1 + m2[:-4])
    recovered_gz = ss.read_cold_archive_impl(cold_gz)
    assert len(recovered_gz) >= 1 and recovered_gz[0].episode_id == "g1"
    assert len(ss.search_cold_fts5_impl(eng, cold_gz, "consolidazione", limit=5)) >= 1

    t2_ep = tmp_path / "ss_ws" / "01_Bug_Diagnostics" / "episodes.jsonl"
    t2_ep.write_text("", encoding="utf-8")
    t2_ep.with_name("episodes.jsonl.bak_1").write_text("{bad_bak\n", encoding="utf-8")
    t2_ep.with_name("episodes.jsonl.bak_2").write_text(ep2.model_dump_json() + "\n", encoding="utf-8")
    assert ss.load_tier2_raw_impl(t2_ep)[0].episode_id == "g2"

    cli_base = tmp_path / "cli_text_ws"
    for cli_args, exp_sub in (
        (["--base-dir", str(cli_base), "--append", "--domain", "ARCH", "--title", "TxtPat", "--content", "Contenuto test"], "Episodio salvato"),
        (["--base-dir", str(cli_base), "--tier1-sync"], "sincronizzato"),
        (["--base-dir", str(cli_base), "--consolidate", "--domain", "ARCH"], "Consolidamento completato"),
        (["--base-dir", str(cli_base), "--recall", "--domain", "ARCH", "--query", "TxtPat"], "TxtPat"),
        (["--base-dir", str(cli_base), "--json"], '"domains"'),
    ):
        monkeypatch.setattr(sys, "argv", ["memory_3tier_engine.py", *cli_args])
        rc, out, _ = call_script_main_captured(_mem_mod, cli_args)
        assert rc == 0 and exp_sub in out


def _assert_mem_models_posix_and_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mem_models: Any
) -> None:
    src_f, dst_f = tmp_path / "local_src.txt", tmp_path / "local_dst.txt"
    src_f.write_text("PAYLOAD_LOCAL_MOVE", encoding="utf-8")
    mem_models.win32_atomic_replace(src_f, dst_f)
    assert dst_f.read_text(encoding="utf-8") == "PAYLOAD_LOCAL_MOVE"

    with monkeypatch.context() as mp_px:
        posix_os = SimpleNamespace(name="posix", replace=_real_os.replace, getpid=_real_os.getpid)
        mp_px.setattr(mem_models, "os", posix_os)
        mp_px.setattr(_mem_mod, "os", posix_os, raising=False)
        mp_px.setattr(mem_models, "_kernel32", mem_models._UNSET)
        mp_px.setattr(_mem_mod, "_kernel32", mem_models._UNSET, raising=False)
        assert mem_models._get_kernel32() is None
        src_p, dst_p = tmp_path / "posix_src.txt", tmp_path / "posix_dst.txt"
        src_p.write_text("POSIX_REPLACE", encoding="utf-8")
        mem_models.win32_atomic_replace(src_p, dst_p)
        assert dst_p.read_text(encoding="utf-8") == "POSIX_REPLACE"

    bkp_env = tmp_path / "env_backups"
    monkeypatch.setenv("NK_MEMORY_BACKUP_DIR", str(bkp_env))
    trk_ep = tmp_path / "nk_tracking" / "memory_3tier" / "episodes.jsonl"
    trk_ep.parent.mkdir(parents=True)
    for step in ("s1\n", "s2\n", "s3\n"):
        trk_ep.write_text(step, encoding="utf-8")
        mem_models.rotate_circular_backups(trk_ep, depth=2)
    resolved_bkp = bkp_env / "memory_3tier"
    assert (resolved_bkp / "episodes.jsonl.bak_1").read_text(encoding="utf-8") == "s3\n"
    assert (resolved_bkp / "episodes.jsonl.bak_2").read_text(encoding="utf-8") == "s2\n"

    monkeypatch.delenv("NK_MEMORY_BACKUP_DIR", raising=False)
    ext_auto = mem_models._resolve_external_backup_dir(trk_ep)
    assert ext_auto is not None
    assert "memory_3tier" in str(ext_auto)


@pytest.mark.fast
def test_memory_models_atomic_replace_backups_and_facade_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6. Esercita models.py: facade sync, lazy 2PC load, fallback posix/nt, mutex e backup esterni."""
    from _internal.memory_3tier_engine import models as mem_models

    fake_fac = SimpleNamespace(__nk_facade__="memory_3tier_engine", _Win32NamedMutex=mem_models._UNSET)
    monkeypatch.setitem(sys.modules, "_fake_mem_fac", fake_fac)
    assert any(getattr(f, "__nk_facade__", None) == "memory_3tier_engine" for f in mem_models._iter_facades())
    mem_models._sync_facade_attr("_Win32NamedMutex", "synced_marker")
    assert fake_fac._Win32NamedMutex == "synced_marker"

    monkeypatch.setattr(mem_models, "_Win32NamedMutex", mem_models._UNSET)
    monkeypatch.setattr(mem_models, "_win32_2pc_atomic_replace", mem_models._UNSET)
    monkeypatch.setattr(_mem_mod, "_Win32NamedMutex", mem_models._UNSET, raising=False)
    monkeypatch.setattr(_mem_mod, "_win32_2pc_atomic_replace", mem_models._UNSET, raising=False)
    monkeypatch.setattr(fake_fac, "_Win32NamedMutex", mem_models._UNSET)
    mem_models._ensure_win32_2pc_loaded()
    assert mem_models._Win32NamedMutex is not mem_models._UNSET
    mem_models._ensure_win32_2pc_loaded()

    monkeypatch.setattr(mem_models, "_win32_2pc_atomic_replace", None)
    monkeypatch.setattr(_mem_mod, "_win32_2pc_atomic_replace", None, raising=False)
    monkeypatch.setattr(mem_models, "_Win32NamedMutex", None)
    monkeypatch.setattr(_mem_mod, "_Win32NamedMutex", None, raising=False)
    monkeypatch.setattr(mem_models, "_kernel32", mem_models._UNSET)
    monkeypatch.setattr(_mem_mod, "_kernel32", mem_models._UNSET, raising=False)
    with mem_models._acquire_memory_file_mutex(tmp_path / "x.jsonl") as ctx_res:
        assert ctx_res is None
    _assert_mem_models_posix_and_backups(tmp_path, monkeypatch, mem_models)
