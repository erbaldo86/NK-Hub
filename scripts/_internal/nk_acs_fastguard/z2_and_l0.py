"""Spawn Z2 background, controllo mutex/WAL e gate L0 one-shot (pure stdlib)."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from _internal.nk_acs_fastguard.constants import (
    _ERROR_ACCESS_DENIED,
    _FILE_ATTRIBUTE_REPARSE_POINT,
    _SCRIPT_DIR,
    _SUBPROCESS_DETACHED,
    _SYNCHRONIZE,
    _WAL_ACTIVE_AGE_SEC,
    _WORKSPACE_ROOT,
    _Z2_COOLDOWN_SEC,
    _fg_attr,
    _get_k32,
    _is_safe_dir,
    _is_safe_file,
    _stat_safe_file,
    _warn_stderr,
)
from _internal.nk_acs_fastguard.state_rmw import _is_valid_conv_id
from _internal.nk_common.constants import ONBOARDING_TRIGGERS

_PURE_L0_EXEMPT: FrozenSet[str] = frozenset((
    "ok",
    "si",
    "sì",
    "procedi",
    "procedi pure",
    "procedi con il piano",
    "procedi alla creazione dell implementation plan",
    "procedi alla creazione dell'implementation plan",
    "confermo",
    "approvo",
    "vai",
    "vai pure",
    "vai avanti",
    "proceed",
    "premi proceed",
)) | frozenset(ONBOARDING_TRIGGERS)


def _is_batch_mutex_busy(roots: List[str]) -> bool:
    """Controlla OpenMutexW su Global\\ e Local\\ NK_RepoBatchLock_<hash16>."""
    ctypes_mod, k32 = _fg_attr("_get_k32", _get_k32)()
    if k32 is None or ctypes_mod is None:
        return False
    import hashlib

    seen_hashes = set()
    for root in roots:
        norm_root = os.path.realpath(root).lower().replace("/", "\\").rstrip("\\")
        h16 = hashlib.sha256(norm_root.encode("utf-8")).hexdigest()[:16]
        if h16 in seen_hashes:
            continue
        seen_hashes.add(h16)
        for prefix in ("Global", "Local"):
            name = f"{prefix}\\NK_RepoBatchLock_{h16}"
            ctypes_mod.set_last_error(0)
            handle = k32.OpenMutexW(_SYNCHRONIZE, False, name)
            err = ctypes_mod.get_last_error()
            if handle:
                k32.CloseHandle(handle)
                return True
            if err == _ERROR_ACCESS_DENIED:
                return True
    return False


def _has_active_wal(roots: List[str]) -> bool:
    """Verifica la presenza di file .wal 2PC attivi recenti via os.scandir."""
    import hashlib

    cutoff = time.time() - _WAL_ACTIVE_AGE_SEC
    base_tmp = os.environ.get("TEMP") or os.environ.get("TMP")
    if not base_tmp:
        import tempfile

        base_tmp = tempfile.gettempdir()
    temp_wal_root = os.path.join(base_tmp, "nk_2pc_wal")
    wal_dirs: List[str] = []
    for root in roots:
        wal_dirs.append(os.path.join(root, ".wal"))
        try:
            ws_hash = hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()[:12]
            wal_dirs.append(os.path.join(temp_wal_root, ws_hash))
        except OSError:
            pass
    if _is_safe_dir(temp_wal_root):
        wal_dirs.append(temp_wal_root)
    for w_dir in wal_dirs:
        if not _is_safe_dir(w_dir):
            continue
        try:
            with os.scandir(w_dir) as it:
                for entry in it:
                    if not entry.name.endswith(".wal") or entry.is_symlink():
                        continue
                    st = entry.stat(follow_symlinks=False)
                    if (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) != 0:
                        continue
                    if st.st_mtime >= cutoff:
                        return True
        except OSError:
            continue
    return False


def _read_anchor_meta(
    roots: List[str], payload: Dict[str, Any], conv_id: Optional[str] = None
) -> Tuple[str, int]:
    """Legge milestone_id e turn dall'ancora isolata di sessione con fallback canonico."""
    milestone_id = str(
        payload.get("milestoneId") or payload.get("milestone_id") or os.environ.get("NK_MILESTONE_ID") or ""
    ).strip()
    turn_val = 1
    has_isolated_conv = bool(
        isinstance(conv_id, str)
        and not conv_id.startswith("default_")
        and _is_valid_conv_id(conv_id)
    )
    for root in roots:
        candidates: List[str] = []
        if has_isolated_conv and conv_id is not None:
            candidates.append(
                os.path.join(root, "nk_tracking", "sessions", conv_id, "session_anchor.jsonl")
            )
        candidates.append(os.path.join(root, "nk_tracking", "anchor", "session_anchor.jsonl"))
        for anchor in candidates:
            size = _is_safe_file(anchor)
            if size is None:
                continue
            try:
                with open(anchor, "rb") as f:
                    if size > 4096:
                        f.seek(size - 4096)
                    tail = f.read().decode("utf-8", errors="replace").splitlines()
                for line in reversed(tail):
                    s = line.strip()
                    if not s:
                        continue
                    rec = json.loads(s)
                    if isinstance(rec, dict):
                        if not milestone_id:
                            milestone_id = str(
                                rec.get("milestone_id") or rec.get("milestone") or ""
                            ).strip()
                        raw_t = rec.get("turn")
                        if isinstance(raw_t, int) and not isinstance(raw_t, bool) and 1 <= raw_t <= 5:
                            turn_val = raw_t
                        break
                if milestone_id:
                    break
            except Exception:
                continue
        if milestone_id:
            break
    return milestone_id or "NK-ACS-AUTO", turn_val


def _maybe_spawn_z2(
    roots: List[str],
    tp_path: str,
    conv_id: str,
    payload: Dict[str, Any],
    state: Dict[str, Any],
    cooldown_s: float = _Z2_COOLDOWN_SEC,
) -> None:
    """Avvia nk_session_handoff.py detached live senza --dry-run rispettando cooldown, mutex e WAL."""
    now = time.time()
    epoch = int(state.get("compaction_epoch", 0))
    last_ts = float(state.get("z2_last_spawn_ts", 0.0))
    last_ep = int(state.get("z2_last_spawn_epoch", -1))
    if last_ep == epoch and (now - last_ts) < cooldown_s:
        return
    if _fg_attr("_is_batch_mutex_busy", _is_batch_mutex_busy)(roots) or _fg_attr("_has_active_wal", _has_active_wal)(roots):
        return
    scr_dir = str(_fg_attr("_SCRIPT_DIR", _SCRIPT_DIR))
    ws_root = str(_fg_attr("_WORKSPACE_ROOT", _WORKSPACE_ROOT))
    handoff_script = os.path.join(scr_dir, "nk_session_handoff.py")
    if not os.path.isfile(handoff_script):
        handoff_script = os.path.join(ws_root, "scripts", "nk_session_handoff.py")
    if _is_safe_file(handoff_script) is None:
        return
    import subprocess

    eff_root = roots[0]
    milestone_id, turn_val = _read_anchor_meta(roots, payload, conv_id=conv_id)
    _opt = "-" * 2
    cmd = [
        sys.executable, "-B", "-u", handoff_script,
        f"{_opt}auto-checkpoint", "--project-root", eff_root,
        "--transcript", tp_path, "--conversation-id", conv_id,
        f"{_opt}milestone-id", milestone_id, f"{_opt}turn", str(turn_val),
    ]
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                cmd, cwd=eff_root, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                creationflags=_SUBPROCESS_DETACHED,
            )
        else:
            subprocess.Popen(
                cmd, cwd=eff_root, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                start_new_session=True,
            )
        state["z2_last_spawn_ts"] = now
        state["z2_last_spawn_epoch"] = epoch
    except Exception as exc:
        _warn_stderr("z2_spawn_failed", f"conv_id={conv_id} reason={exc}")


def _strip_xml_wrapper_fast(raw_text: str) -> str:
    """Estrae <USER_REQUEST> o rimuove envelope XML Antigravity in sola stdlib."""
    import re

    cleaned = re.sub(
        r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|EPHEMERAL_MESSAGE|SYSTEM_MESSAGE)\b[^>]*>.*?</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|EPHEMERAL_MESSAGE|SYSTEM_MESSAGE)>",
        "",
        str(raw_text or ""),
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    m_req = re.search(
        r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return m_req.group(1).strip() if m_req else cleaned


def _is_l0_exempt_fast(clean_prompt: str) -> bool:
    """Filtro rapido pure-stdlib per conferme pure, avvio dashboard e capsule pass-through."""
    txt = (clean_prompt or "").strip()
    if not txt or len(txt) <= 2:
        return True
    low = txt.lower()
    if low.startswith("<env_capsule>") or ("!diretto" in low or "!raw" in low):
        return True
    if low.startswith("[") and low.endswith("]") and low[1:-1].isdigit():
        return True
    if low.isdigit() and 0 <= int(low) <= 9:
        return True
    if low in ("/compact", "procedi e quando raggiungi la saturazione di contesto esegui un /compact"):
        return True
    norm = " ".join(
        low.replace("!", "")
        .replace(".", "")
        .replace(",", "")
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )
    if len(norm.split()) <= 1 and "/" not in txt and "\\" not in txt and "." not in txt:
        return True
    return norm in _PURE_L0_EXEMPT


def _check_l0_gate_one_shot(
    tp_path: str, conv_id: str, hooks_dir: Optional[str], state: Dict[str, Any], epoch: int
) -> Optional[str]:
    """Inietta avviso L0 one-shot se l'ultimo USER_INPUT non ha gate L0 registrato per il turno."""
    if not hooks_dir or not tp_path:
        return None
    try:
        sz = os.stat(tp_path).st_size
    except OSError:
        return None
    if sz <= 0:
        return None
    try:
        with open(tp_path, "rb") as fh:
            if sz > 32768:
                fh.seek(sz - 32768)
            raw_lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None

    last_user_prompt = ""
    for line in reversed(raw_lines):
        ls = line.strip()
        if not ls or not ls.startswith("{"):
            continue
        try:
            rec = json.loads(ls)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        rtype = str(rec.get("type") or "").strip().upper()
        src = str(rec.get("source") or "").strip().upper()
        role = str(rec.get("role") or "").strip().lower()
        if rtype == "USER_INPUT" or src in ("USER", "USER_EXPLICIT") or role == "user":
            raw_c = rec.get("content") if rec.get("content") is not None else rec.get("text")
            if isinstance(raw_c, str) and raw_c.strip():
                cleaned = _strip_xml_wrapper_fast(raw_c)
                if cleaned and not cleaned.lstrip().startswith(("<CONTEXT_SUMMARY>", "# Resuming from a compaction")):
                    last_user_prompt = cleaned
                    break

    if not last_user_prompt or _is_l0_exempt_fast(last_user_prompt):
        return None
    import hashlib

    prompt_sha = hashlib.sha256(" ".join(last_user_prompt.split()).encode("utf-8")).hexdigest()
    gate_file = os.path.join(hooks_dir, f"l0_gate_{conv_id}.json")
    if _stat_safe_file(gate_file) is not None:
        try:
            with open(gate_file, "r", encoding="utf-8") as gf:
                gdata = json.load(gf)
            if isinstance(gdata, dict) and gdata.get("turn_prompt_sha256") == prompt_sha:
                return None
        except Exception:
            pass
    if str(state.get("enforced_prompt_sha256") or "") == prompt_sha and int(state.get("enforced_epoch", -1)) == epoch:
        return None
    state["enforced_prompt_sha256"] = prompt_sha
    state["enforced_epoch"] = epoch
    return (
        "[RULE-00.6-ENFORCE] Prompt o task incrementale senza gate L0 verificato: "
        "esegui vibe_sprint_router.py --meta-prompt-gate ed esponi lo Specchio Concettuale L0 visibile prima di agire."
    )
