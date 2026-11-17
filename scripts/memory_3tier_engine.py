#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di memoria episodica a 3 livelli per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/memory_3tier_engine.py.
@domain_id: DOM-05
Supporta cap 350 token standard (GT-05), 1200 token Generation/Carbon/Argon e alias di dominio.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

__nk_domain__: str = "DOM-05"
__nk_role__: str = "facade"
__nk_facade__: str = "memory_3tier_engine"

_CLI_FLAGS: Tuple[str, ...] = (
    "--append", "--base-dir", "--consolidate", "--content", "--domain", "--json", "--output",
    "--profile", "--query", "--recall", "--tags", "--threshold", "--tier1-sync", "--title",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc
    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
init_nk_facade(__file__, pkg="memory_3tier_engine")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "_scripts_dir": ("_internal.memory_3tier_engine.models", "_scripts_dir"),
    "_workspace_root": ("_internal.memory_3tier_engine.models", "_workspace_root"),
    "_MEMORY_THREAD_LOCK": ("_internal.memory_3tier_engine.models", "_MEMORY_THREAD_LOCK"),
    "_UNSET": ("_internal.memory_3tier_engine.models", "_UNSET"),
    "_Win32NamedMutex": ("_internal.memory_3tier_engine.models", "_Win32NamedMutex"),
    "_win32_2pc_atomic_replace": ("_internal.memory_3tier_engine.models", "_win32_2pc_atomic_replace"),
    "_kernel32": ("_internal.memory_3tier_engine.models", "_kernel32"),
    "NK_DOMAINS": ("_internal.memory_3tier_engine.models", "NK_DOMAINS"),
    "DOMAIN_ALIAS_MAP": ("_internal.memory_3tier_engine.models", "DOMAIN_ALIAS_MAP"),
    "MEMORY_SCHEMA_VERSION": ("_internal.memory_3tier_engine.models", "MEMORY_SCHEMA_VERSION"),
    "TIER1_TOKEN_CAP": ("_internal.memory_3tier_engine.models", "TIER1_TOKEN_CAP"),
    "TIER1_TOKEN_CAP_ARGON": ("_internal.memory_3tier_engine.models", "TIER1_TOKEN_CAP_ARGON"),
    "TIER1_TOKEN_CAP_CARBON": ("_internal.memory_3tier_engine.models", "TIER1_TOKEN_CAP_CARBON"),
    "TIER1_TOKEN_CAP_GENERATION": ("_internal.memory_3tier_engine.models", "TIER1_TOKEN_CAP_GENERATION"),
    "TIER2_SLIDING_WINDOW_MAX": ("_internal.memory_3tier_engine.models", "TIER2_SLIDING_WINDOW_MAX"),
    "RRF_K_CONSTANT": ("_internal.memory_3tier_engine.models", "RRF_K_CONSTANT"),
    "BACKUP_DEPTH": ("_internal.memory_3tier_engine.models", "BACKUP_DEPTH"),
    "MAX_BACKUP_DEPTH": ("_internal.memory_3tier_engine.models", "MAX_BACKUP_DEPTH"),
    "MOVEFILE_REPLACE_EXISTING": ("_internal.memory_3tier_engine.models", "MOVEFILE_REPLACE_EXISTING"),
    "MOVEFILE_WRITE_THROUGH": ("_internal.memory_3tier_engine.models", "MOVEFILE_WRITE_THROUGH"),
    "MOVEFILE_COPY_ALLOWED": ("_internal.memory_3tier_engine.models", "MOVEFILE_COPY_ALLOWED"),
    "ERROR_ACCESS_DENIED": ("_internal.memory_3tier_engine.models", "ERROR_ACCESS_DENIED"),
    "ERROR_SHARING_VIOLATION": ("_internal.memory_3tier_engine.models", "ERROR_SHARING_VIOLATION"),
    "ERROR_LOCK_VIOLATION": ("_internal.memory_3tier_engine.models", "ERROR_LOCK_VIOLATION"),
    "_ensure_win32_2pc_loaded": ("_internal.memory_3tier_engine.models", "_ensure_win32_2pc_loaded"),
    "_acquire_memory_file_mutex": ("_internal.memory_3tier_engine.models", "_acquire_memory_file_mutex"),
    "_get_kernel32": ("_internal.memory_3tier_engine.models", "_get_kernel32"),
    "resolve_domain": ("_internal.memory_3tier_engine.models", "resolve_domain"),
    "win32_atomic_replace": ("_internal.memory_3tier_engine.models", "win32_atomic_replace"),
    "_resolve_external_backup_dir": ("_internal.memory_3tier_engine.models", "_resolve_external_backup_dir"),
    "rotate_circular_backups": ("_internal.memory_3tier_engine.models", "rotate_circular_backups"),
    "estimate_tokens": ("_internal.memory_3tier_engine.models", "estimate_tokens"),
    "MemoryEpisode": ("_internal.memory_3tier_engine.models", "MemoryEpisode"),
    "Tier1Item": ("_internal.memory_3tier_engine.models", "Tier1Item"),
    "Tier1DomainState": ("_internal.memory_3tier_engine.models", "Tier1DomainState"),
    "PureBM25": ("_internal.memory_3tier_engine.search_bm25_dense", "PureBM25"),
    "_LEXICAL_STOPWORDS": ("_internal.memory_3tier_engine.search_bm25_dense", "_LEXICAL_STOPWORDS"),
    "_POLARITY_AFFIRMATIVE_TOKENS": ("_internal.memory_3tier_engine.search_bm25_dense", "_POLARITY_AFFIRMATIVE_TOKENS"),
    "_POLARITY_NEGATIVE_TOKENS": ("_internal.memory_3tier_engine.search_bm25_dense", "_POLARITY_NEGATIVE_TOKENS"),
    "_light_stem_token": ("_internal.memory_3tier_engine.search_bm25_dense", "_light_stem_token"),
    "_extract_significant_terms": ("_internal.memory_3tier_engine.search_bm25_dense", "_extract_significant_terms"),
    "_has_significant_overlap": ("_internal.memory_3tier_engine.search_bm25_dense", "_has_significant_overlap"),
    "_has_opposite_polarity": ("_internal.memory_3tier_engine.search_bm25_dense", "_has_opposite_polarity"),
    "DenseEmbedder": ("_internal.memory_3tier_engine.search_bm25_dense", "DenseEmbedder"),
    "HybridRRFSearchEngine": ("_internal.memory_3tier_engine.search_bm25_dense", "HybridRRFSearchEngine"),
    "Tier1CoreMemory": ("_internal.memory_3tier_engine.tier1_capsule", "Tier1CoreMemory"),
    "ThreeTierMemoryEngine": ("_internal.memory_3tier_engine.engine_core", "ThreeTierMemoryEngine"),
    "sync_tier1_capsule": ("_internal.memory_3tier_engine.engine_core", "sync_tier1_capsule"),
    "consolidate_similar_episodes": ("_internal.memory_3tier_engine.engine_core", "consolidate_similar_episodes"),
    "_build_cli_parser": ("_internal.memory_3tier_engine.cli", "_build_cli_parser"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.memory_3tier_engine."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        mod = importlib.import_module(target[0])
    except ModuleNotFoundError:
        init_nk_facade(__file__, pkg="memory_3tier_engine")
        mod = importlib.import_module(target[0])
    val = getattr(mod, target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main() -> int:
    init_nk_facade(__file__, pkg="memory_3tier_engine")
    return importlib.import_module("_internal.memory_3tier_engine.cli").main()


if __name__ == "__main__":
    sys.exit(main())
