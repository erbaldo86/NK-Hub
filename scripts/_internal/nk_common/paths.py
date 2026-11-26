# -*- coding: utf-8 -*-
"""Risoluzione deterministica di scripts/, workspace root, NK Proget e UTF-8."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_NK_PROGET_ONLINE_CMD_RE = re.compile(
    r"(?:^|[\s\"'=/\\(])nk\s+proget[/\\]+online(?:$|[\s\"'/\\,;)\]])",
    re.IGNORECASE,
)
_NK_PROGET_LOCALE_CMD_RE = re.compile(
    r"(?:^|[\s\"'=/\\(])nk\s+proget[/\\]+locale(?:$|[\s\"'/\\,;)\]])",
    re.IGNORECASE,
)
_EXTERNAL_PROJECTS_CMD_RE = re.compile(
    r"(?:^|[\s\"'=/\\(])(?:nk_external_projects|nk\s+proget[/\\]+locale)(?:$|[\s\"'/\\,;)\]])",
    re.IGNORECASE,
)
_NK_PROGET_SLICE_RE = re.compile(
    r"nk\s+proget[/\\][^\"';|&\n\r,)]+",
    re.IGNORECASE,
)


def resolve_scripts_dir(anchor_file: str) -> str:
    """Risolve il percorso della directory scripts/ a partire dal file ancora."""
    cur = Path(anchor_file or __file__).resolve()
    if cur.name == "scripts" and (cur.is_dir() or not cur.suffix):
        return str(cur)
    for anc in cur.parents:
        if anc.name == "scripts":
            return str(anc)
    return str(cur.parent if cur.suffix or cur.is_file() else cur)


def resolve_workspace_root(anchor_file: str) -> str:
    """Risolve la radice del workspace gestendo scripts/, _internal/ e .staging/scripts/."""
    cur = Path(anchor_file or __file__).resolve()
    for cand in (cur, *cur.parents):
        if cand.name == "scripts":
            parent = cand.parent
            if parent.name == ".staging":
                return str(parent.parent)
            return str(parent)
        if cand.name == ".staging":
            return str(cand.parent)
    return str(cur.parent.parent if cur.parent != cur else cur)


def reconfigure_streams(include_stdin: bool = False) -> None:
    """Riconfigura gli stream standard in UTF-8 senza dipendenze esterne."""
    streams = (sys.stdout, sys.stderr, sys.stdin) if include_stdin else (sys.stdout, sys.stderr)
    for stream in streams:
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def normalize_rel_path(raw: str) -> str:
    """Normalizza un percorso relativo rimuovendo spazi, virgolette, ./ e / iniziali."""
    norm = str(raw or "").strip().strip("\"'").strip().replace("\\", "/")
    while norm.startswith(("./", "/")):
        norm = norm[2:] if norm.startswith("./") else norm.lstrip("/")
    return norm


def get_hooks_temp_dir_common(create: bool = True) -> Path:
    """Restituisce la directory temporanea per gli hook creandola se richiesto."""
    env_dir = os.environ.get("NK_HOOKS_TEMP_DIR", "").strip()
    hooks_dir = Path(env_dir) if env_dir else (Path(tempfile.gettempdir()) / "nk_hooks")
    if create:
        hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir


def _append_unique_dir_cand(
    out: List[Path], seen: set[str], raw: Optional[Path | str]
) -> None:
    """Aggiunge un candidato directory normalizzato evitando duplicati case-insensitive."""
    raw_s = str(raw or "").strip()
    if not raw_s:
        return
    try:
        cand = Path(raw_s).expanduser().resolve()
    except OSError:
        cand = Path(raw_s)
    key = os.path.normcase(str(cand))
    if key not in seen:
        seen.add(key)
        out.append(cand)


def iter_hooks_temp_dir_candidates(
    primary_dir: Optional[Path | str] = None,
) -> Tuple[Path, ...]:
    """Restituisce in ordine deterministico le directory candidate per gli stati L0/hook."""
    out: List[Path] = []
    seen: set[str] = set()
    _append_unique_dir_cand(out, seen, primary_dir)
    _append_unique_dir_cand(out, seen, os.environ.get("NK_HOOKS_TEMP_DIR", "").strip())
    _append_unique_dir_cand(out, seen, Path(tempfile.gettempdir()) / "nk_hooks")
    try:
        from _internal.nk_common.nvme_storage_guards import resolve_local_appdata_dir

        _append_unique_dir_cand(out, seen, resolve_local_appdata_dir() / "nk_hub" / "hooks")
    except (ImportError, OSError):
        pass
    return tuple(out)


def _strip_win32_device_prefix(raw: str) -> str:
    """Rimuove virgolette esterne e prefissi Win32 UNC/device da un percorso grezzo."""
    s = raw.strip().strip("\"'").strip()
    if s.startswith(("\\\\?\\UNC\\", "//?/UNC/")):
        return "\\\\" + s[8:]
    if s.startswith(("\\\\?\\", "//?/", "\\\\.\\", "//./")):
        return s[4:]
    return s


def _normalized_path_parts_low(path_or_str: Path | str) -> List[str]:
    """Restituisce i segmenti normalizzati in minuscolo di un percorso FS."""
    s = _strip_win32_device_prefix(str(path_or_str or ""))
    if not s:
        return []
    norm_s = os.path.normpath(s.replace("/", os.sep).replace("\\", os.sep))
    return [p.lower().rstrip(". ") for p in Path(norm_s).parts]


def _find_consecutive_pair(parts_low: Sequence[str], first: str, second: str) -> int:
    """Restituisce l'indice iniziale della coppia consecutiva (first, second) o -1."""
    limit = len(parts_low) - 1
    for idx in range(limit):
        if parts_low[idx] == first and parts_low[idx + 1] == second:
            return idx
    return -1


def is_nk_proget_online_path(path_or_str: Path | str) -> bool:
    """Verifica se il percorso ricade sotto il mirror read-only NK Proget/Online/."""
    parts = _normalized_path_parts_low(path_or_str)
    return _find_consecutive_pair(parts, "nk proget", "online") >= 0


def is_nk_proget_locale_path(path_or_str: Path | str) -> bool:
    """Verifica se il percorso ricade sotto NK Proget/Locale/ (mai Online/)."""
    parts = _normalized_path_parts_low(path_or_str)
    if _find_consecutive_pair(parts, "nk proget", "online") >= 0:
        return False
    return _find_consecutive_pair(parts, "nk proget", "locale") >= 0


def is_external_projects_staging_path(path_or_str: Path | str) -> bool:
    """Verifica se il path appartiene a .staging/ di un progetto in Locale o NK_External_Projects."""
    parts = _normalized_path_parts_low(path_or_str)
    if _find_consecutive_pair(parts, "nk proget", "online") >= 0:
        return False
    loc_idx = _find_consecutive_pair(parts, "nk proget", "locale")
    if loc_idx >= 0:
        return (
            len(parts) > loc_idx + 3
            and parts[loc_idx + 2] != ".staging"
            and parts[loc_idx + 3] == ".staging"
        )
    if "nk_external_projects" in parts:
        idx = parts.index("nk_external_projects")
        return (
            len(parts) > idx + 2
            and parts[idx + 1] != ".staging"
            and parts[idx + 2] == ".staging"
        )
    return False


def cmd_mentions_nk_proget_online(text: str) -> bool:
    """Rileva riferimenti testuali o CLI verso NK Proget/Online, normalizzando ./ e ../."""
    norm = str(text or "").replace("\\", "/")
    if _NK_PROGET_ONLINE_CMD_RE.search(norm):
        return True
    return any(is_nk_proget_online_path(m.group(0)) for m in _NK_PROGET_SLICE_RE.finditer(norm))


def cmd_mentions_nk_proget_locale(text: str) -> bool:
    """Rileva riferimenti testuali o CLI verso NK Proget/Locale."""
    return bool(_NK_PROGET_LOCALE_CMD_RE.search(str(text or "").replace("\\", "/")))


def cmd_mentions_external_project(text: str) -> bool:
    """Rileva riferimenti testuali o CLI verso NK_External_Projects/ o NK Proget/Locale/."""
    return bool(_EXTERNAL_PROJECTS_CMD_RE.search(str(text or "").replace("\\", "/")))


def resolve_nk_proget_roots(anchor_root: Path | str) -> Tuple[Optional[Path], Optional[Path]]:
    """Risolve (locale_root, online_root) da NK_PROGET_ROOT o entro due livelli padre."""
    env_proget = os.environ.get("NK_PROGET_ROOT", "").strip()
    if env_proget:
        base = Path(env_proget).resolve()
        return (base / "Locale").resolve(), (base / "Online").resolve()
    cur = Path(anchor_root).resolve()
    for anc in (cur, cur.parent, cur.parent.parent):
        cand = anc if anc.name == "NK Proget" else (anc / "NK Proget")
        if cand.is_dir():
            return (cand / "Locale").resolve(), (cand / "Online").resolve()
    return None, None
