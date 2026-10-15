#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cache locale deterministica Tier-0 in SQLite WAL per Nexus Keystone v3.0.0-STE100-Unified.
Mantiene una connessione persistente per istanza per evitare il churn dei file WAL.
"""

from __future__ import annotations

import argparse
import atexit
from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
if _scripts_dir.name == ".staging":
    _workspace_root = _scripts_dir.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    from scripts.platform_runner import reconfigure_streams


class DeterministicApiCache:
    """Cache SQLite in modalita WAL con connessione persistente per chiamate di rete."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        ttl_seconds: float = 86400.0,
    ) -> None:
        reconfigure_streams()
        if db_path is None:
            cache_dir = Path(tempfile.gettempdir()) / "nk_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = cache_dir / "deterministic_api_cache.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open_persistent_connection()
        self._init_db()
        atexit.register(self.close)

    def _get_connection(self) -> sqlite3.Connection:
        """Restituisce la connessione SQLite WAL persistente dell'istanza."""
        return self._open_persistent_connection()

    def _open_persistent_connection(self) -> sqlite3.Connection:
        """Apre o restituisce la connessione SQLite WAL persistente dell'istanza."""
        if self._conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            self._conn = conn
        return self._conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Fornisce accesso transazionale thread-safe alla connessione persistente."""
        with self._lock:
            conn = self._open_persistent_connection()
            with conn:
                yield conn

    def close(self) -> None:
        """Chiude esplicitamente la connessione SQLite persistente."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def __enter__(self) -> "DeterministicApiCache":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _init_db(self) -> None:
        """Inizializza la tabella e l'indice della cache SQLite."""
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    request_hash TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_body TEXT NOT NULL,
                    response_headers TEXT,
                    created_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 1
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_endpoint ON api_cache(endpoint);"
            )

    @staticmethod
    def compute_hash(
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
    ) -> str:
        """Calcola la firma SHA-256 deterministica per una richiesta HTTP."""
        normalized_params = json.dumps(params or {}, sort_keys=True)
        raw_key = f"{method.upper()}|{endpoint}|{normalized_params}|{body or ''}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Tuple[int, str, Dict[str, str]]]:
        """Recupera la risposta salvata se presente e non scaduta."""
        if force_refresh or os.environ.get("NK_FORCE_NETWORK_REFRESH") == "1":
            return None

        req_hash = self.compute_hash(endpoint, method, params, body)
        now = time.time()

        with self._connection() as conn:
            cur = conn.execute(
                """
                SELECT status_code, response_body, response_headers, created_at
                FROM api_cache WHERE request_hash = ?
                """,
                (req_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None

            status_code, resp_body, headers_json, created_at = row
            if now - created_at > self.ttl_seconds:
                conn.execute(
                    "DELETE FROM api_cache WHERE request_hash = ?",
                    (req_hash,),
                )
                return None

            conn.execute(
                "UPDATE api_cache SET hit_count = hit_count + 1 WHERE request_hash = ?",
                (req_hash,),
            )
            headers = json.loads(headers_json) if headers_json else {}
            return (status_code, resp_body, headers)

    def set(
        self,
        endpoint: str,
        status_code: int,
        response_body: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Salva nella cache una risposta HTTP reale."""
        req_hash = self.compute_hash(endpoint, method, params, body)
        headers_json = json.dumps(headers or {})
        now = time.time()

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO api_cache (
                    request_hash, endpoint, method, status_code,
                    response_body, response_headers, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_hash) DO UPDATE SET
                    status_code = excluded.status_code,
                    response_body = excluded.response_body,
                    response_headers = excluded.response_headers,
                    created_at = excluded.created_at,
                    hit_count = hit_count + 1
                """,
                (
                    req_hash,
                    endpoint,
                    method.upper(),
                    status_code,
                    response_body,
                    headers_json,
                    now,
                ),
            )
        return req_hash

    def health_check(self) -> bool:
        """Verifica l'accessibilita del database e lo stato della modalita WAL."""
        try:
            with self._connection() as conn:
                cur = conn.execute("PRAGMA journal_mode;")
                mode = cur.fetchone()[0]
                return mode.lower() == "wal"
        except Exception:
            return False

    def clear(self) -> int:
        """Svuota tutte le voci presenti nella cache."""
        with self._connection() as conn:
            cur = conn.execute("DELETE FROM api_cache;")
            return cur.rowcount

    def get_stats(self) -> Dict[str, Any]:
        """Restituisce le statistiche correnti della cache SQLite WAL."""
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM api_cache;"
            )
            row = cur.fetchone()
            entries = int(row[0]) if row else 0
            total_hits = int(row[1]) if row else 0
        return {
            "entries": entries,
            "total_hits": total_hits,
            "db_path": str(self.db_path),
            "wal_healthy": self.health_check(),
        }


def main() -> int:
    """Interfaccia CLI per la cache deterministica Tier-0."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Tier-0 Deterministic Local API Cache"
    )
    parser.add_argument("--health", action="store_true", help="Verifica stato WAL")
    parser.add_argument("--clear", action="store_true", help="Svuota la cache")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Stampa le statistiche della cache in formato JSON",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Invalida la cache forzando il refresh di rete",
    )

    args = parser.parse_args()
    cache = DeterministicApiCache()
    try:
        if args.force_refresh:
            os.environ["NK_FORCE_NETWORK_REFRESH"] = "1"
            count = cache.clear()
            print(f"[API-CACHE] Refresh forzato attivo. Voci rimosse: {count}")
            return 0
        if args.stats:
            print(json.dumps(cache.get_stats(), indent=2))
            return 0
        if args.health:
            healthy = cache.health_check()
            print(f"[API-CACHE] WAL Health: {healthy}")
            return 0 if healthy else 1
        if args.clear:
            count = cache.clear()
            print(f"[API-CACHE] Voci rimosse: {count}")
            return 0
        parser.print_help()
        return 0
    finally:
        cache.close()


if __name__ == "__main__":
    sys.exit(main())
