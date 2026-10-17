# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per deterministic_api_cache.py di Nexus Keystone v3.3.0.
Modulo: tests/test_deterministic_api_cache.py.
Valida la connessione SQLite WAL persistente, il bypass force_refresh e la scadenza TTL.
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
    """Carica il modulo deterministic_api_cache dando priorita a .staging/scripts."""
    staging_target = (
        _workspace_root / ".staging" / "scripts" / "deterministic_api_cache.py"
    )
    prod_target = _workspace_root / "scripts" / "deterministic_api_cache.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(
        "deterministic_api_cache", str(target)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deterministic_api_cache"] = mod
    spec.loader.exec_module(mod)
    return mod


cache_mod = _load_cache_module()
DeterministicApiCache = cache_mod.DeterministicApiCache


def test_api_cache_persistent_wal_connection_and_close(tmp_path: Path) -> None:
    """1. Verifica connessione WAL persistente, force_refresh, scadenza TTL ed eviction."""
    db_path = tmp_path / "wal_persistent.db"
    with DeterministicApiCache(db_path=db_path, ttl_seconds=0.02) as cache:
        assert cache.health_check() is True
        conn_initial = cache._conn
        assert conn_initial is not None

        cache.set(
            "https://example.org/v1",
            200,
            '{"ok": true}',
            method="POST",
            params={"q": "nk"},
        )
        hit = cache.get("https://example.org/v1", method="POST", params={"q": "nk"})
        assert hit is not None
        assert hit[0] == 200
        assert cache._conn is conn_initial

        bypass = cache.get(
            "https://example.org/v1",
            method="POST",
            params={"q": "nk"},
            force_refresh=True,
        )
        assert bypass is None

        time.sleep(0.03)
        assert (
            cache.get("https://example.org/v1", method="POST", params={"q": "nk"})
            is None
        )

        cache.set("https://example.org/v2", 200, '{"ephemeral": 2}')
        assert cache.clear() == 1
    assert cache._conn is None
