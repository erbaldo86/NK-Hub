# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_deterministic_api_cache.py
Valida la connessione SQLite WAL persistente e la scadenza TTL.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_cache_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "deterministic_api_cache.py"
    prod_target = _workspace_root / "scripts" / "deterministic_api_cache.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("deterministic_api_cache", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deterministic_api_cache"] = mod
    spec.loader.exec_module(mod)
    return mod


cache_mod = _load_cache_module()
DeterministicApiCache = cache_mod.DeterministicApiCache


def test_api_cache_persistent_wal_connection_and_close(tmp_path: Path) -> None:
    """1. Verifica il riutilizzo della connessione WAL persistente e la chiusura pulita."""
    db_path = tmp_path / "wal_persistent.db"
    with DeterministicApiCache(db_path=db_path, ttl_seconds=3600.0) as cache:
        conn_initial = cache._conn
        assert conn_initial is not None
        cache.set("https://example.org/v1", 200, '{"ok": true}')
        hit = cache.get("https://example.org/v1")
        assert hit is not None
        assert cache._conn is conn_initial
    assert cache._conn is None


def test_api_cache_ttl_expiration_and_eviction(tmp_path: Path) -> None:
    """2. Verifica l'invalidazione per scadenza TTL e la pulizia della tabella cache."""
    db_path = tmp_path / "ttl_test.db"
    with DeterministicApiCache(db_path=db_path, ttl_seconds=0.05) as cache:
        cache.set("https://example.org/short", 200, '{"ephemeral": 1}')
        time.sleep(0.08)
        expired_hit = cache.get("https://example.org/short")
        assert expired_hit is None

        cache.set("https://example.org/short2", 200, '{"ephemeral": 2}')
        cleared = cache.clear()
        assert cleared == 1
