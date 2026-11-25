# -*- coding: utf-8 -*-
"""Cache AST thread-safe condivisa in memoria per passata Single-Pass TAS (SHA-256 64-char)."""

from __future__ import annotations

import ast
import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class RepoSnapshotCache:
    """Memorizza lettura testo e ast.parse() evitando passate duplicate sui medesimi sorgenti."""

    def __init__(self, max_entries: int = 4096) -> None:
        self._max_entries = max(64, int(max_entries))
        self._lock = threading.Lock()
        self._file_cache: OrderedDict[
            Tuple[str, int, int],
            Tuple[str, Optional[ast.AST], Optional[SyntaxError]],
        ] = OrderedDict()
        self._source_cache: OrderedDict[
            Tuple[str, int],
            Tuple[Optional[ast.AST], Optional[SyntaxError]],
        ] = OrderedDict()
        self._stats: Dict[str, int] = {
            "file_hits": 0,
            "file_misses": 0,
            "source_hits": 0,
            "source_misses": 0,
            "total_parses": 0,
        }

    def _evict_if_full(self, store: OrderedDict[Any, Any], incoming_key: Any = None) -> None:
        if incoming_key is not None and incoming_key in store:
            return
        while len(store) >= self._max_entries:
            store.popitem(last=False)

    @staticmethod
    def _full_sha256(code: str) -> str:
        """Calcola il digest SHA-256 completo a 64 caratteri esadecimali."""
        return hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()

    def _compile_ast(
        self, code: str, filename: str
    ) -> Tuple[Optional[ast.AST], Optional[SyntaxError]]:
        try:
            tree = ast.parse(code, filename=filename, type_comments=True)
            return tree, None
        except (SyntaxError, ValueError) as exc:
            syn_err = exc if isinstance(exc, SyntaxError) else SyntaxError(str(exc))
            return None, syn_err

    def get_text_and_ast(
        self, file_path: Path
    ) -> Tuple[str, Optional[ast.AST], Optional[SyntaxError]]:
        """Restituisce (text, ast_tree, syntax_error) da cache mtime_ns+size o disco."""
        resolved = Path(file_path).resolve()
        st = resolved.stat()
        key = (resolved.as_posix(), int(st.st_mtime_ns), int(st.st_size))
        with self._lock:
            cached = self._file_cache.get(key)
            if cached is not None:
                self._file_cache.move_to_end(key)
                self._stats["file_hits"] += 1
                return cached

        text = resolved.read_text(encoding="utf-8-sig", errors="replace")
        tree: Optional[ast.AST] = None
        syn_err: Optional[SyntaxError] = None
        parsed_count = 0
        if resolved.suffix.lower() == ".py":
            tree, syn_err = self._compile_ast(text, str(resolved))
            parsed_count = 1
            src_key = (self._full_sha256(text), len(text))
            with self._lock:
                self._evict_if_full(self._source_cache, src_key)
                self._source_cache[src_key] = (tree, syn_err)

        entry = (text, tree, syn_err)
        with self._lock:
            self._evict_if_full(self._file_cache, key)
            self._file_cache[key] = entry
            self._stats["file_misses"] += 1
            self._stats["total_parses"] += parsed_count
        return entry

    def get_text(self, file_path: Path) -> str:
        """Restituisce il testo del file sfruttando la cache condivisa."""
        text, _, _ = self.get_text_and_ast(file_path)
        return text

    def parse_source_cached(
        self, code: str, filename: str = "<string>"
    ) -> Tuple[Optional[ast.AST], Optional[SyntaxError]]:
        """Esegue ast.parse() su sorgente in memoria con cache per SHA-256 64-char/lunghezza."""
        key = (self._full_sha256(code), len(code))
        with self._lock:
            cached = self._source_cache.get(key)
            if cached is not None:
                self._source_cache.move_to_end(key)
                self._stats["source_hits"] += 1
                return cached

        tree, syn_err = self._compile_ast(code, filename)
        with self._lock:
            self._evict_if_full(self._source_cache, key)
            self._source_cache[key] = (tree, syn_err)
            self._stats["source_misses"] += 1
            self._stats["total_parses"] += 1
        return tree, syn_err

    def stats(self) -> Dict[str, int]:
        """Restituisce copia thread-safe delle statistiche hit/miss della cache."""
        with self._lock:
            out = dict(self._stats)
            out["file_entries"] = len(self._file_cache)
            out["source_entries"] = len(self._source_cache)
            return out

    def clear(self) -> None:
        """Svuota in modo thread-safe le cache AST/file e azzera i contatori telemetrici."""
        with self._lock:
            self._file_cache.clear()
            self._source_cache.clear()
            for key in self._stats:
                self._stats[key] = 0

    def reset_stats(self) -> None:
        """Azzera i contatori telemetrici mantenendo le voci valide in cache."""
        with self._lock:
            for key in self._stats:
                self._stats[key] = 0


_GLOBAL_REPO_SNAPSHOT_CACHE = RepoSnapshotCache()


def get_repo_snapshot_cache() -> RepoSnapshotCache:
    """Restituisce l'istanza singleton condivisa di RepoSnapshotCache."""
    return _GLOBAL_REPO_SNAPSHOT_CACHE
