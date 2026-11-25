"""Spawn Z2 background, controllo mutex/WAL e gate L0 one-shot (pure stdlib)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_acs_fastguard.constants import (
    _ERROR_ACCESS_DENIED, _FILE_ATTRIBUTE_REPARSE_POINT, _SCRIPT_DIR, _SUBPROCESS_DETACHED, _SYNCHRONIZE,
    _WAL_ACTIVE_AGE_SEC, _WORKSPACE_ROOT, _Z2_COOLDOWN_SEC, _fg_attr, _get_k32, _is_safe_dir,
    _is_safe_file, _stat_safe_file, _warn_stderr,
)
from _internal.nk_acs_fastguard.l0_exempt_rules import (  # noqa: F401
    _DIRECTIVE_CUE_FAST_RE, _DIRETTO_CMD_RE, _META_LINE_RE, _MUTATING_ORDER_RE, _PHASE_COUNT_RE,
    _PROHIBITION_RE, _PURE_L0_EXEMPT, _SHELL_META_TOKENS, _WRITE_VERB_FAST_RE, _extract_user_from_line,
    _extract_user_raw_text, _has_direct_imperative_outside_fence, _is_l0_exempt_fast,
    _read_last_user_prompt, _strip_xml_wrapper_fast, _validate_handoff_exempt_fast,
)
from _internal.nk_acs_fastguard.state_rmw import _is_valid_conv_id
from _internal.nk_common.constants import DEFAULT_MILESTONE_ID, ONBOARDING_TRIGGERS  # noqa: F401
from _internal.nk_common.epistemic_firewall_rules import (  # noqa: F401
    HANDOFF_V2_START_ACTIVE, HANDOFF_V2_START_PASSIVE, _AGENT_DIRECTIVE_CUE_RE, _DESTRUCTIVE_SHELL_RE,
    _HANDOFF_MUTATING_ORDER_RE, _SHA256_HEX64_RE, check_passive_v2_tiered_content,
    detect_outbound_handoff_intent_fast, evaluate_epistemic_firewall_rules, extract_t12_scan_lines,
    has_unprohibited_pattern, has_unprohibited_smuggle, strip_zero_width_chars,
)

_PLACEHOLDER_MILESTONES = frozenset((DEFAULT_MILESTONE_ID, "Auto-Saved Milestone", "NK-ACS-AUTO", "2PC_PROMOTE"))


def _is_batch_mutex_busy(roots: List[str]) -> bool:
    """Controlla OpenMutexW su Global\\ e Local\\ NK_RepoBatchLock_<hash16>."""
    ctypes_mod, k32 = _fg_attr("_get_k32", _get_k32)()
    if k32 is None or ctypes_mod is None:
        return False
    seen = set()
    for root in roots:
        h16 = hashlib.sha256(os.path.realpath(root).lower().replace("/", "\\").rstrip("\\").encode("utf-8")).hexdigest()[:16]
        if h16 in seen:
            continue
        seen.add(h16)
        for prefix in ("Global", "Local"):
            ctypes_mod.set_last_error(0)
            if handle := k32.OpenMutexW(_SYNCHRONIZE, False, f"{prefix}\\NK_RepoBatchLock_{h16}"):
                k32.CloseHandle(handle)
                return True
            if ctypes_mod.get_last_error() == _ERROR_ACCESS_DENIED:
                return True
    return False


def _wal_dir_has_recent(w_dir: str, cutoff: float) -> bool:
    """Controlla in sicurezza se una directory contiene almeno un file .wal recente."""
    if not _is_safe_dir(w_dir):
        return False
    try:
        with os.scandir(w_dir) as it:
            entries = [e for e in it if e.name.endswith(".wal") and not e.is_symlink()]
        for entry in entries:
            st = entry.stat(follow_symlinks=False)
            if (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) == 0 and st.st_mtime >= cutoff:
                return True
    except OSError:
        return False
    return False


def _has_active_wal(roots: List[str]) -> bool:
    """Verifica la presenza di file .wal 2PC attivi recenti via os.scandir."""
    cutoff = time.time() - _WAL_ACTIVE_AGE_SEC
    if not (base_tmp := os.environ.get("TEMP") or os.environ.get("TMP")):
        import tempfile

        base_tmp = tempfile.gettempdir()
    temp_wal_root = os.path.join(base_tmp, "nk_2pc_wal")
    wal_dirs: List[str] = []
    for root in roots:
        wal_dirs.append(os.path.join(root, ".wal"))
        try:
            wal_dirs.append(os.path.join(temp_wal_root, hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()[:12]))
        except OSError:
            continue
    if _is_safe_dir(temp_wal_root):
        wal_dirs.append(temp_wal_root)
    return any(_wal_dir_has_recent(w_dir, cutoff) for w_dir in wal_dirs)


def _parse_anchor_iso_ts(rec: Dict[str, Any]) -> Optional[datetime]:
    for key in ("timestamp", "ts"):
        if isinstance(raw := rec.get(key), str) and raw.strip():
            try:
                dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    raw_ns = rec.get("timestamp_ns")
    return datetime.fromtimestamp(raw_ns / 1_000_000_000, tz=timezone.utc) if type(raw_ns) is int and raw_ns > 0 else None


def _allow_anchor_turn(rec: Dict[str, Any], conv_id: Optional[str], has_iso: bool, is_conv: bool, def_turn: int) -> bool:
    """Verifica se il record ancora appartiene alla conversazione per estrarre turn."""
    if def_turn != 0 or is_conv:
        return True
    rec_cid = str(rec.get("conversation_id") or "").strip()
    return (rec_cid == conv_id) if has_iso else (not rec_cid)


def _apply_anchor_rec(rec: Dict[str, Any], meta: Dict[str, Any], is_conv: bool, conv_id: Optional[str], has_iso: bool, def_turn: int, max_turn: int) -> None:
    """Aggiorna milestone_id e turn dall'ultimo record valido dell'ancora."""
    if not meta["milestone_id"] and (ms := str(rec.get("milestone_id") or rec.get("milestone") or "").strip()):
        meta["milestone_id"] = ms
        meta["ms_from_conv"] = is_conv
        meta["sess_ms_ts"] = _parse_anchor_iso_ts(rec) if is_conv else None
    if not meta["found_turn"] and type(raw_t := rec.get("turn")) is int and 1 <= raw_t <= max_turn:
        if _allow_anchor_turn(rec, conv_id, has_iso, is_conv, def_turn):
            meta["turn_val"], meta["found_turn"] = raw_t, True


def _parse_promo_rec(line: str) -> Optional[Tuple[str, Optional[datetime]]]:
    """Estrae (milestone_id, timestamp) se la riga e un record 2PC_ATOMIC_PROMOTION."""
    if not (s := line.strip()):
        return None
    try:
        rec = json.loads(s)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(rec, dict) or str(rec.get("event") or rec.get("event_type") or "").strip() != "2PC_ATOMIC_PROMOTION":
        return None
    return str(rec.get("milestone_id") or rec.get("milestone") or "").strip(), _parse_anchor_iso_ts(rec)


def _extract_latest_promo(tail: List[str]) -> Tuple[str, Optional[datetime]]:
    """Trova l'ultima promozione 2PC significativa (milestone_id, timestamp) nella coda."""
    best_ms, best_ts = "", None
    for line in reversed(tail):
        parsed = _parse_promo_rec(line)
        if parsed is None or not parsed[0] or parsed[0] in _PLACEHOLDER_MILESTONES:
            continue
        promo_ms, promo_ts = parsed
        if promo_ts is not None and (best_ts is None or promo_ts > best_ts):
            best_ms, best_ts = promo_ms, promo_ts
        elif promo_ts is None and not best_ms:
            best_ms = promo_ms
    return best_ms, best_ts


def _find_promo_ms(tail: List[str], cur_ms: str, sess_ms_ts: Optional[datetime], from_conv: bool = True) -> str:
    """Recupera l'eventuale milestone_id piu recente da 2PC_ATOMIC_PROMOTION."""
    best_ms, best_ts = _extract_latest_promo(tail)
    if not best_ms:
        return cur_ms
    if not cur_ms or cur_ms in _PLACEHOLDER_MILESTONES or not from_conv:
        return best_ms
    if best_ts is not None and (sess_ms_ts is None or best_ts > sess_ms_ts):
        return best_ms
    return cur_ms


def _read_tail_bytes(anchor: str, size: int, max_bytes: int) -> bytes:
    """Legge gli ultimi max_bytes di anchor scartando l'eventuale prima riga tronca."""
    with open(anchor, "rb") as f:
        if size <= max_bytes:
            return f.read()
        f.seek(size - max_bytes)
        raw = f.read(max_bytes)
    nl = raw.find(b"\n")
    return raw[nl + 1 :] if nl != -1 else raw


def _read_tail_8k(anchor: str, max_bytes: int = 8192) -> Optional[List[str]]:
    """Legge fino agli ultimi max_bytes da un file ancora sicuro."""
    if (size := _is_safe_file(anchor)) is None:
        return None
    try:
        return _read_tail_bytes(anchor, size, max_bytes).decode("utf-8", errors="replace").splitlines()
    except (OSError, UnicodeDecodeError):
        return None


def _scan_anchor_candidate(anchor: str, is_conv: bool, meta: Dict[str, Any], conv_id: Optional[str], has_iso: bool, explicit_ms: str, def_turn: int, max_turn: int) -> None:
    """Legge la coda di un singolo file session_anchor.jsonl aggiornando i metadati."""
    if (tail := _read_tail_8k(anchor, 8192 if is_conv else 65536)) is None:
        return
    try:
        if first_s := next((ln.strip() for ln in reversed(tail) if ln.strip()), ""):
            if isinstance(rec := json.loads(first_s), dict):
                _apply_anchor_rec(rec, meta, is_conv, conv_id, has_iso, def_turn, max_turn)
    except (json.JSONDecodeError, ValueError, TypeError):
        return
    if not (is_conv or explicit_ms):
        meta["milestone_id"] = _find_promo_ms(tail, meta["milestone_id"], meta["sess_ms_ts"], bool(meta.get("ms_from_conv", False)))


def _anchor_done(meta: Dict[str, Any], turn_ok: bool) -> bool:
    """Verifica se milestone definitivo e condizione sul turn risultano risolti."""
    return bool(meta["milestone_id"]) and meta["milestone_id"] not in _PLACEHOLDER_MILESTONES and (meta["found_turn"] or turn_ok)


def _should_stop_root_scan(is_conv: bool, explicit_ms: str, meta: Dict[str, Any]) -> bool:
    """Interrompe la scansione per-root dopo l'ancora di sessione solo con milestone esplicito e turn trovato."""
    return bool(is_conv and explicit_ms and meta["found_turn"])


def _scan_root_anchors(root: str, meta: Dict[str, Any], conv_id: Optional[str], has_iso: bool, explicit_ms: str, def_turn: int, max_turn: int) -> None:
    """Scansiona le ancore di sessione e globale per una root."""
    cands = ([(os.path.join(root, "nk_tracking", "sessions", conv_id, "session_anchor.jsonl"), True)] if has_iso and conv_id is not None else []) + [
        (os.path.join(root, "nk_tracking", "anchor", "session_anchor.jsonl"), False)
    ]
    for anchor, is_conv in cands:
        _scan_anchor_candidate(anchor, is_conv, meta, conv_id, has_iso, explicit_ms, def_turn, max_turn)
        if _should_stop_root_scan(is_conv, explicit_ms, meta):
            break


def _read_anchor_meta(roots: List[str], payload: Dict[str, Any], conv_id: Optional[str] = None, default_turn: int = 1) -> Tuple[str, int]:
    """Legge milestone_id e turn dall'ancora isolata di sessione con fallback configurabile."""
    explicit_ms = str(payload.get("milestoneId") or payload.get("milestone_id") or os.environ.get("NK_MILESTONE_ID") or "").strip()
    meta: Dict[str, Any] = {"milestone_id": explicit_ms, "sess_ms_ts": None, "ms_from_conv": False, "turn_val": int(default_turn), "found_turn": False}
    max_turn = 4 if default_turn == 0 else 5
    has_iso = bool(isinstance(conv_id, str) and not conv_id.startswith("default_") and _is_valid_conv_id(conv_id))
    for root in roots:
        _scan_root_anchors(root, meta, conv_id, has_iso, explicit_ms, default_turn, max_turn)
        if _anchor_done(meta, not has_iso):
            break
    return meta["milestone_id"] or "NK-ACS-AUTO", meta["turn_val"]


def _maybe_spawn_z2(roots: List[str], tp_path: str, conv_id: str, payload: Dict[str, Any], state: Dict[str, Any], cooldown_s: float = _Z2_COOLDOWN_SEC) -> None:
    """Avvia nk_session_handoff.py detached live senza --dry-run rispettando cooldown, mutex e WAL."""
    now, epoch = time.time(), int(state.get("compaction_epoch", 0))
    if int(state.get("z2_last_spawn_epoch", -1)) == epoch and (now - float(state.get("z2_last_spawn_ts", 0.0))) < cooldown_s:
        return
    if _fg_attr("_is_batch_mutex_busy", _is_batch_mutex_busy)(roots) or _fg_attr("_has_active_wal", _has_active_wal)(roots):
        return
    scr_dir, ws_root = str(_fg_attr("_SCRIPT_DIR", _SCRIPT_DIR)), str(_fg_attr("_WORKSPACE_ROOT", _WORKSPACE_ROOT))
    handoff_script = os.path.join(scr_dir, "nk_session_handoff.py")
    if not os.path.isfile(handoff_script):
        handoff_script = os.path.join(ws_root, "scripts", "nk_session_handoff.py")
    if _is_safe_file(handoff_script) is None:
        return
    milestone_id, turn_val = _read_anchor_meta(roots, payload, conv_id=conv_id, default_turn=0)
    _opt = "-" * 2
    cmd = [sys.executable, "-B", "-u", handoff_script, f"{_opt}auto-checkpoint", "--project-root", roots[0], "--transcript", tp_path, "--conversation-id", conv_id, f"{_opt}milestone-id", milestone_id, f"{_opt}turn", str(turn_val)]
    try:
        if sys.platform == "win32":
            subprocess.Popen(cmd, cwd=roots[0], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, creationflags=_SUBPROCESS_DETACHED)
        else:
            subprocess.Popen(cmd, cwd=roots[0], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        state["z2_last_spawn_ts"], state["z2_last_spawn_epoch"] = now, epoch
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        _warn_stderr("z2_spawn_failed", f"conv_id={conv_id} reason={exc}")


def _gate_file_matches(gate_file: str, prompt_sha: str) -> bool:
    """Verifica se l0_gate_<cid>.json registra gia prompt_sha."""
    if _stat_safe_file(gate_file) is None:
        return False
    try:
        with open(gate_file, "r", encoding="utf-8") as gf:
            gdata = json.load(gf)
        return isinstance(gdata, dict) and gdata.get("turn_prompt_sha256") == prompt_sha
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return False


def _check_l0_gate_one_shot(tp_path: str, conv_id: str, hooks_dir: Optional[str], state: Dict[str, Any], epoch: int) -> Optional[str]:
    """Inietta avviso L0 one-shot se l'ultimo USER_INPUT non ha gate L0 registrato per il turno."""
    if not hooks_dir or not tp_path or not (last_prompt := _read_last_user_prompt(tp_path)) or _is_l0_exempt_fast(last_prompt):
        return None
    prompt_sha = hashlib.sha256(" ".join(last_prompt.split()).encode("utf-8")).hexdigest()
    if _gate_file_matches(os.path.join(hooks_dir, f"l0_gate_{conv_id}.json"), prompt_sha):
        return None
    if str(state.get("enforced_prompt_sha256") or "") == prompt_sha and int(state.get("enforced_epoch", -1)) == epoch:
        return None
    state["enforced_prompt_sha256"], state["enforced_epoch"] = prompt_sha, epoch
    return "[RULE-00.6-ENFORCE] Prompt o task incrementale senza gate L0 verificato: esegui vibe_sprint_router.py --meta-prompt-gate ed esponi lo Specchio Concettuale L0 visibile prima di agire."
