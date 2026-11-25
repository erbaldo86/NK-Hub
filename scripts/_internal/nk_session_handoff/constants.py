# -*- coding: utf-8 -*-
"""Costanti e helper base di sessione per nk_session_handoff."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from _internal.nk_common.constants import (
    DEFAULT_MILESTONE_ID as _COMMON_MILESTONE_ID,
    VERSION as _COMMON_VERSION,
)
from _internal.nk_common.epistemic_firewall_rules import (
    HANDOFF_V2_END_ACTIVE,
    HANDOFF_V2_END_PASSIVE,
    HANDOFF_V2_START_ACTIVE,
    HANDOFF_V2_START_PASSIVE,
)
from _internal.nk_common.transcript_guards import is_subagent_transcript_head

HANDOFF_SCHEMA_VERSION = _COMMON_VERSION
HANDOFF_VERSION = HANDOFF_SCHEMA_VERSION
VERSION = HANDOFF_SCHEMA_VERSION
DEFAULT_MILESTONE_ID = _COMMON_MILESTONE_ID

_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent.parent
_workspace_root = (
    _SCRIPTS_DIR.parent.parent
    if _SCRIPTS_DIR.parent.name == ".staging"
    else _SCRIPTS_DIR.parent
)

_BACKTICK_RUN_RE = re.compile(r"`+")
_SAFE_SESSION_CONV_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_FILE_HASH_MEMO: Dict[str, Tuple[int, int, str]] = {}
_BASELINE_MEMO: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_TRANSCRIPT_CURSOR_CACHE: Dict[str, Dict[str, Any]] = {}
_FILE_HASH_LOCK = threading.Lock()
_BASELINE_LOCK = threading.Lock()
_CURSOR_LOCK = threading.Lock()
_TRANSCRIPT_BACKSCAN_CHUNK_BYTES = 65536
_TRANSCRIPT_BACKSCAN_MAX_BYTES = 50 * 1024 * 1024

_NK_REPO_MARKERS: Tuple[str, ...] = (
    "nk_tracking", "nk_genome", ".staging", ".agents", "scripts",
    "src", "src_app", "backend", "frontend", "tests", ".git",
)
_EXCLUDED_STATE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".staging", ".wal",
}
_EXCLUDED_STATE_FILENAMES = {
    "rsi_telemetry.jsonl", "fast_bootstrap_cache.json", "bootstrap_state.json",
}
_SKIP_STATE_REL_DIRS: Tuple[str, ...] = (
    "nk_tracking/anchor", "nk_tracking/handoff", "nk_tracking/sessions", "handoff",
)
_SKIP_STATE_REL_FILES: Tuple[str, ...] = (
    "nk_tracking/active_context.md", "nk_tracking/anchor/session_anchor.jsonl",
)
_PLACEHOLDER_MILESTONES = frozenset((DEFAULT_MILESTONE_ID, "Auto-Saved Milestone", "NK-ACS-AUTO", "2PC_PROMOTE"))


def _parse_ts_ns_value(raw_val: Any) -> int:
    """Converte un timestamp numerico o ISO-8601 UTC in nanosecondi epoch."""
    if raw_val is None or isinstance(raw_val, bool):
        return 0
    if isinstance(raw_val, (int, float)):
        val = float(raw_val)
        return 0 if val <= 0 else (int(val) if val >= 1e15 else (int(val * 1e6) if val >= 1e12 else int(val * 1e9)))
    if isinstance(raw_val, str) and (clean_s := raw_val.strip()):
        try:
            if re.fullmatch(r"\d+(?:\.\d+)?", clean_s):
                return _parse_ts_ns_value(float(clean_s))
            dt = datetime.fromisoformat(clean_s.replace("Z", "+00:00"))
            return max(0, int((dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp() * 1_000_000_000))
        except Exception:
            return 0
    return 0


def _sanitize_ste100_inline(value: str, fallback: str) -> str:
    """Sanitizza un token inline per active_context.md."""
    cleaned = str(value or "").replace("\r", " ").replace("\n", " ").replace("`", "")
    cleaned = cleaned.replace(" \u2014 ", "_").replace("\u2014", "_").replace("\u2013", "_").replace(" - ", "_")
    cleaned = " ".join(cleaned.split()).strip()[:80]
    return cleaned if cleaned else fallback


def _parse_optional_turn(raw_turn: Any) -> Optional[int]:
    """Valida il turno opzionale (0..5) rifiutando booleani."""
    if raw_turn is None:
        return None
    if isinstance(raw_turn, bool):
        raise ValueError(f"Il turno non puo essere booleano: {raw_turn}")
    if isinstance(raw_turn, str):
        clean_s = raw_turn.strip()
        if not clean_s:
            return None
        if not re.fullmatch(r"-?\d+", clean_s):
            raise ValueError(f"Il turno deve essere un intero valido (0..5): {raw_turn!r}")
        turn_val = int(clean_s)
    elif isinstance(raw_turn, int):
        turn_val = raw_turn
    else:
        raise ValueError(f"Tipo turno non valido (0..5): {raw_turn!r}")
    if not (0 <= turn_val <= 5):
        raise ValueError(f"Il turno deve essere compreso tra 0 e 5: {turn_val}")
    return turn_val


def _is_meaningful_milestone(raw_ms: Any) -> bool:
    s = str(raw_ms or "").strip()
    return bool(s) and s not in _PLACEHOLDER_MILESTONES


def _extract_patch_notes_milestone(pn_head: Mapping[str, Any]) -> str:
    title = str(pn_head.get("first_section_title") or "").strip()
    if not title:
        return ""
    cand = m.group(1).strip() if (m := re.search(r"\[([A-Za-z0-9._-]+)\]", title)) else re.sub(r"\s*\(\d{4}-\d{2}-\d{2}[^)]*\)\s*$", "", title).strip("`[] ")
    return cand if _is_meaningful_milestone(cand) else ""


def _iter_anchor_lines_reversed(anchor_file: Path, chunk_bytes: int = 65536) -> Iterator[str]:
    """Itera le righe non vuote di session_anchor.jsonl dalla fine in blocchi 64KB."""
    sz = anchor_file.stat().st_size
    if sz <= 0:
        return
    pos, carry = sz, b""
    with open(anchor_file, "rb") as fh:
        while pos > 0:
            read_sz = min(chunk_bytes, pos)
            pos -= read_sz
            fh.seek(pos)
            parts = (fh.read(read_sz) + carry).split(b"\n")
            carry = parts[0]
            for raw_ln in reversed(parts[1:]):
                if (ln := raw_ln.decode("utf-8", errors="replace").strip()):
                    yield ln
        if carry and (ln := carry.decode("utf-8", errors="replace").strip()):
            yield ln


def resolve_session_tracking_dir(root: Path, conv_id: Optional[str]) -> Optional[Path]:
    """Valida conv_id e restituisce root/nk_tracking/sessions/<conv_id>."""
    if not isinstance(conv_id, str):
        return None
    clean_id = conv_id.strip()
    if not clean_id or clean_id.lower() == "auto" or clean_id.startswith("default_"):
        return None
    if not _SAFE_SESSION_CONV_ID_RE.fullmatch(clean_id):
        return None
    base_root = Path(root).resolve()
    sessions_base = (base_root / "nk_tracking" / "sessions").resolve()
    sess_dir = (sessions_base / clean_id).resolve()
    if not sess_dir.is_relative_to(sessions_base):
        return None
    return sess_dir


def _dynamic_code_fence(body: str, min_len: int = 3) -> str:
    """Restituisce un code-fence dinamico piu lungo di ogni backtick interno."""
    runs = [len(m.group(0)) for m in _BACKTICK_RUN_RE.finditer(body or "")]
    needed = max(min_len, (max(runs) + 1) if runs else min_len)
    return "`" * needed


def _resolve_git_executable() -> str:
    """Risolve il percorso dell'eseguibile git."""
    found = shutil.which("git")
    if found:
        return found
    for candidate in (
        str(Path.home() / "AppData" / "Local" / "Programs" / "Git" / "cmd" / "git.exe"),
        "C:/Program Files/Git/cmd/git.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return "git"


def _is_subagent_transcript_tv03(cpath: str) -> bool:
    """Verifica guardia strutturale TV-03 verificando assenza di record utente reali."""
    try:
        with open(cpath, "rb") as bf:
            head_bytes = bf.read(32768)
    except OSError:
        return False
    if not head_bytes:
        return False
    raw_lines: List[str] = []
    for raw_ln in head_bytes.splitlines()[:40]:
        ln = raw_ln.decode("utf-8", errors="replace").strip()
        if not ln:
            continue
        raw_lines.append(ln)
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if isinstance(rec, dict):
            src = str(rec.get("source") or "").strip().upper()
            typ = str(rec.get("type") or "").strip().upper()
            role = str(rec.get("role") or "").strip().lower()
            if src in ("USER", "USER_EXPLICIT") or typ == "USER_INPUT" or role == "user":
                return False
    if is_subagent_transcript_head(cpath):
        return True
    for ln in raw_lines[:5]:
        if ("<SYSTEM_MESSAGE>" in ln and "sender=" in ln) or "<subagent_reminder>" in ln:
            return True
    return False


def _discover_default_transcript() -> str:
    """Individua rapidamente il trascritto attivo in brain."""
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if not brain_dir.exists():
        return ""
    now = time.time()
    candidates: List[Tuple[float, str]] = []
    try:
        dir_items: List[Tuple[float, str]] = []
        with os.scandir(brain_dir) as it:
            for entry in it:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                try:
                    dst = entry.stat(follow_symlinks=False)
                    dir_items.append(
                        (max(getattr(dst, "st_ctime", 0.0), dst.st_mtime), entry.path)
                    )
                except OSError:
                    continue
        dir_items.sort(key=lambda x: x[0], reverse=True)
        for _, dpath in dir_items[:12]:
            cand_str = os.path.join(dpath, ".system_generated", "logs", "transcript.jsonl")
            try:
                mtime = os.stat(cand_str).st_mtime
                if (now - mtime) <= 1800.0:
                    candidates.append((mtime, cand_str))
            except OSError:
                continue
    except OSError:
        return ""
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, cpath in candidates[:6]:
        if _is_subagent_transcript_tv03(cpath):
            continue
        return cpath
    return candidates[0][1]


def _state_memo_cache_path(resolved_root: Path) -> Path:
    """Restituisce il percorso in TEMP per la cache stat->sha256 del workspace."""
    norm = str(resolved_root).lower().replace("/", "\\").rstrip("\\")
    key = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "nk_cache" / "handoff_memo" / f"nk_handoff_sha_memo_{key}.json"


def _prune_handoff_memo_cache(cache_dir: Path, max_files: int = 32) -> None:
    """Mantiene al massimo max_files memo SHA piu' recenti nella directory cache."""
    entries: List[Tuple[int, str, Path]] = []
    try:
        for entry in cache_dir.glob("*.json"):
            try:
                entries.append((entry.stat().st_mtime_ns, entry.name, entry))
            except OSError:
                continue
    except OSError:
        return
    if len(entries) > max_files:
        for _, _, stale in sorted(entries, key=lambda item: (item[0], item[1]), reverse=True)[max_files:]:
            try:
                stale.unlink()
            except OSError:
                pass


def _entry_mtime_ns(item: os.DirEntry[str], default_ns: int = 0) -> int:
    """Restituisce st_mtime_ns di una DirEntry gestendo errori OS in modo piatto."""
    try:
        return item.stat(follow_symlinks=False).st_mtime_ns
    except OSError:
        return default_ns


def _dir_latest_activity_ns(dir_path: Path, base_mtime_ns: int) -> int:
    """Calcola il timestamp piu' recente tra la directory e i suoi artefatti diretti."""
    best_ns = base_mtime_ns
    try:
        with os.scandir(dir_path) as it:
            items = list(it)
    except OSError:
        return best_ns
    for item in items:
        best_ns = max(best_ns, _entry_mtime_ns(item, best_ns))
    return best_ns


def _scan_session_dir_candidate(entry: os.DirEntry[str], sessions_dir: Path) -> Optional[Tuple[int, str, Path]]:
    """Valuta una singola directory in nk_tracking/sessions/ restituendo (mtime_ns, name, path)."""
    try:
        if not entry.is_dir(follow_symlinks=False):
            return None
        entry_res = Path(entry.path).resolve()
        if not entry_res.is_relative_to(sessions_dir):
            return None
        act_ns = _dir_latest_activity_ns(entry_res, entry.stat(follow_symlinks=False).st_mtime_ns)
        return (act_ns, entry.name, entry_res)
    except OSError:
        return None


def _select_retained_session_names(
    candidates: List[Tuple[int, str, Path]],
    active_conversation_id: Optional[str],
    max_sessions: int,
) -> Set[str]:
    """Seleziona fino a max_sessions nomi sessione da preservare inclusa quella attiva."""
    keep_names: Set[str] = set()
    active_clean = str(active_conversation_id or "").strip()
    if active_clean and any(row[1] == active_clean for row in candidates):
        keep_names.add(active_clean)
    for _, name, _ in candidates:
        if len(keep_names) >= max_sessions:
            break
        keep_names.add(name)
    return keep_names


def _idle_anchor_state_key(rec: Mapping[str, Any]) -> Tuple[str, str, str, str, str, str]:
    """Estrae la firma canonica di stato per deduplicare eventi auto_checkpoint_idle consecutivi."""
    return (
        str(rec.get("state_sha256") or "").strip(), str(rec.get("staging_state_sha256") or "").strip(),
        str(rec.get("milestone_id") or rec.get("milestone") or "").strip(), str(rec.get("gate_status") or "").strip(),
        str(rec.get("template") or "").strip(), str(rec.get("conversation_id") or "").strip(),
    )


def _drift_response(turn: int = 0, gate_status: str = "MISSING", milestone_id: str = "") -> Dict[str, Any]:
    return {"status": "DRIFT_DETECTED", "passed": False, "verified": False, "state_drift": True, "turn": turn, "turn_phase": "IDLE_CHECKPOINT", "gate_status": gate_status, "milestone_id": milestone_id, "state_sha256": ""}


def _is_fsm_checkpoint_rec(parsed: Dict[str, Any]) -> bool:
    return parsed.get("event_type") == "fsm_checkpoint" or parsed.get("event") == "fsm_checkpoint" or parsed.get("type") == "fsm_checkpoint" or ("turn" in parsed and "state_sha256" in parsed)

