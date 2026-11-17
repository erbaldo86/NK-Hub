# -*- coding: utf-8 -*-
"""Archivio cold gzip, indice SQLite FTS5 e caricamento raw Tier-2."""

from __future__ import annotations

import contextlib
import gzip
import json
import os
import re
import sqlite3
import zlib
from pathlib import Path
from typing import Any, List, Sequence, Tuple

from _internal.memory_3tier_engine.models import (
    MemoryEpisode,
    _facade_attr,
    _resolve_external_backup_dir,
)
from _internal.memory_3tier_engine.search_bm25_dense import _light_stem_token


def read_cold_archive_impl(cold_file: Path) -> List[MemoryEpisode]:
    """Legge l'archivio compresso recuperando i record validi prima di troncamenti."""
    if not cold_file.exists():
        return []

    episodes: List[MemoryEpisode] = []
    seen_ids: set[str] = set()
    corrupted = False
    try:
        with gzip.open(cold_file, "rt", encoding="utf-8", errors="replace") as f:
            while True:
                try:
                    line = f.readline()
                except (EOFError, zlib.error, gzip.BadGzipFile, OSError):
                    corrupted = True
                    break
                if not line:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    ep = MemoryEpisode.model_validate_json(stripped)
                    episodes.append(ep)
                    seen_ids.add(ep.episode_id)
                except Exception:
                    continue
    except (EOFError, zlib.error, gzip.BadGzipFile, OSError):
        corrupted = True

    if corrupted:
        try:
            raw_bytes = cold_file.read_bytes()
            pos = 0
            while pos < len(raw_bytes):
                idx = raw_bytes.find(b"\x1f\x8b\x08", pos)
                if idx < 0:
                    break
                next_idx = raw_bytes.find(b"\x1f\x8b\x08", idx + 3)
                member = raw_bytes[idx:next_idx] if next_idx > idx else raw_bytes[idx:]
                decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
                chunks: List[bytes] = []
                for offset in range(0, len(member), 64):
                    try:
                        chunks.append(decomp.decompress(member[offset : offset + 64]))
                    except zlib.error:
                        break
                text = b"".join(chunks).decode("utf-8", errors="replace")
                for raw_line in text.splitlines():
                    s_line = raw_line.strip()
                    if not s_line:
                        continue
                    try:
                        ep = MemoryEpisode.model_validate_json(s_line)
                        if ep.episode_id not in seen_ids:
                            episodes.append(ep)
                            seen_ids.add(ep.episode_id)
                    except Exception:
                        continue
                pos = next_idx if next_idx > idx else len(raw_bytes)
        except OSError:
            pass

    return episodes


def init_cold_fts_schema_impl(conn: sqlite3.Connection) -> None:
    """Inizializza le tabelle metadati e FTS5 per la cache cold SQLite."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cold_archive_meta ("
        "gz_path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, "
        "file_size INTEGER NOT NULL, episode_count INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cold_episodes ("
        "gz_path TEXT NOT NULL, seq_idx INTEGER NOT NULL, "
        "episode_id TEXT NOT NULL, episode_json TEXT NOT NULL, "
        "PRIMARY KEY (gz_path, seq_idx))"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS cold_episodes_fts USING fts5("
        "gz_path UNINDEXED, episode_id UNINDEXED, episode_json UNINDEXED, "
        "title, content, tags)"
    )


def sync_cold_fts5_index_impl(
    engine: Any, cold_file: Path, conn: sqlite3.Connection
) -> None:
    """Sincronizza la cache SQLite FTS5 solo quando mtime_ns o size cambiano."""
    st = cold_file.stat()
    gz_key = os.path.realpath(str(cold_file)).lower()
    engine._init_cold_fts_schema(conn)
    row = conn.execute(
        "SELECT mtime_ns, file_size FROM cold_archive_meta WHERE gz_path = ?",
        (gz_key,),
    ).fetchone()
    if row is not None and int(row[0]) == st.st_mtime_ns and int(row[1]) == st.st_size:
        return

    episodes = engine._read_cold_archive(cold_file)
    ep_rows: List[Tuple[str, int, str, str]] = []
    fts_rows: List[Tuple[str, str, str, str, str, str]] = []
    for idx, ep in enumerate(episodes):
        ep_json = ep.model_dump_json()
        ep_rows.append((gz_key, idx, ep.episode_id, ep_json))
        fts_rows.append(
            (gz_key, ep.episode_id, ep_json, ep.title, ep.content, " ".join(ep.tags))
        )

    with conn:
        conn.execute("DELETE FROM cold_episodes WHERE gz_path = ?", (gz_key,))
        conn.execute("DELETE FROM cold_episodes_fts WHERE gz_path = ?", (gz_key,))
        if ep_rows:
            conn.executemany(
                "INSERT INTO cold_episodes (gz_path, seq_idx, episode_id, episode_json) VALUES (?, ?, ?, ?)",
                ep_rows,
            )
            conn.executemany(
                "INSERT INTO cold_episodes_fts (gz_path, episode_id, episode_json, title, content, tags) VALUES (?, ?, ?, ?, ?, ?)",
                fts_rows,
            )
        conn.execute(
            "INSERT OR REPLACE INTO cold_archive_meta (gz_path, mtime_ns, file_size, episode_count) VALUES (?, ?, ?, ?)",
            (gz_key, st.st_mtime_ns, st.st_size, len(episodes)),
        )


def get_cached_cold_episodes_impl(
    engine: Any, cold_file: Path
) -> List[MemoryEpisode]:
    """Recupera gli episodi cold dalla cache SQLite senza decomprimere file invariati."""
    if not cold_file.exists():
        return []
    gz_key = os.path.realpath(str(cold_file)).lower()
    sql_mod = _facade_attr("sqlite3", sqlite3)
    try:
        with engine._lock, contextlib.closing(
            sql_mod.connect(str(engine._cold_fts_db_path), timeout=5.0)
        ) as conn:
            engine._sync_cold_fts5_index(cold_file, conn)
            rows = conn.execute(
                "SELECT episode_json FROM cold_episodes WHERE gz_path = ? ORDER BY seq_idx ASC",
                (gz_key,),
            ).fetchall()
        out: List[MemoryEpisode] = []
        for (raw_json,) in rows:
            try:
                out.append(MemoryEpisode.model_validate_json(raw_json))
            except (json.JSONDecodeError, ValueError, Exception):
                continue
        return out
    except (sqlite3.Error, OSError):
        return engine._read_cold_archive(cold_file)


def search_cold_fts5_impl(
    engine: Any, cold_file: Path, query: str, limit: int = 64
) -> List[MemoryEpisode]:
    """Interroga l'archivio cold tramite indice FTS5 evitando decompressioni ripetute."""
    if not cold_file.exists() or not query or not query.strip():
        return []
    raw_toks = re.findall(r"\b[a-z0-9_]{2,}\b", query.lower())
    if not raw_toks:
        return []
    fts_terms: List[str] = []
    for tok in raw_toks:
        fts_terms.append(tok)
        stem = _light_stem_token(tok)
        if len(stem) >= 3 and stem != tok:
            fts_terms.append(stem)
        if len(tok) >= 5:
            fts_terms.append(tok[:5])
    unique_terms = list(dict.fromkeys(fts_terms))[:24]
    fts_expr = " OR ".join(f'"{t}"*' for t in unique_terms)
    gz_key = os.path.realpath(str(cold_file)).lower()
    sql_mod = _facade_attr("sqlite3", sqlite3)
    try:
        with engine._lock, contextlib.closing(
            sql_mod.connect(str(engine._cold_fts_db_path), timeout=5.0)
        ) as conn:
            engine._sync_cold_fts5_index(cold_file, conn)
            rows = conn.execute(
                "SELECT episode_json FROM cold_episodes_fts WHERE gz_path = ? AND cold_episodes_fts MATCH ? ORDER BY rank LIMIT ?",
                (gz_key, fts_expr, max(1, int(limit))),
            ).fetchall()
        hits: List[MemoryEpisode] = []
        for (raw_json,) in rows:
            try:
                hits.append(MemoryEpisode.model_validate_json(raw_json))
            except (json.JSONDecodeError, ValueError, Exception):
                continue
        return hits
    except (sqlite3.Error, OSError):
        return engine._read_cold_archive(cold_file)


def archive_to_tier3_impl(
    base_dir: Path, domain: str, surplus: Sequence[MemoryEpisode]
) -> None:
    """Appende in formato gzip gli episodi eccedenti la finestra mobile del Livello 2."""
    if not surplus:
        return
    cold_file = base_dir / domain / "archive.cold.jsonl.gz"
    cold_file.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(ep.model_dump_json() + "\n" for ep in surplus).encode("utf-8")
    with gzip.open(cold_file, "ab") as f:
        f.write(payload)


def load_tier2_raw_impl(path: Path) -> List[MemoryEpisode]:
    """Carica episodes.jsonl recuperando dai backup circolari se il file primario e corrotto."""
    if not path.exists():
        return []
    episodes: List[MemoryEpisode] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.replace("\x00", "").strip()
                if not stripped:
                    continue
                try:
                    episodes.append(MemoryEpisode.model_validate_json(stripped))
                except (json.JSONDecodeError, ValueError, Exception):
                    continue
    except OSError:
        pass

    if not episodes:
        bak_candidates = [
            path.with_name(f"{path.name}.bak_1"),
            path.with_name(f"{path.name}.bak_2"),
        ]
        ext_bkp = _resolve_external_backup_dir(path)
        if ext_bkp is not None:
            bak_candidates.extend(
                [ext_bkp / f"{path.name}.bak_1", ext_bkp / f"{path.name}.bak_2"]
            )
        for bak_path in bak_candidates:
            if not bak_path.exists() or bak_path.stat().st_size == 0:
                continue
            try:
                with open(bak_path, "r", encoding="utf-8", errors="replace") as bf:
                    for bline in bf:
                        bstripped = bline.replace("\x00", "").strip()
                        if not bstripped:
                            continue
                        try:
                            episodes.append(MemoryEpisode.model_validate_json(bstripped))
                        except (json.JSONDecodeError, ValueError, Exception):
                            continue
            except OSError:
                continue
            if episodes:
                break
    return episodes
