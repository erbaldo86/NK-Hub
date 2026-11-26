"""Gestione RMW atomica stato fastguard, risoluzione path e Named Mutex Win32."""

from __future__ import annotations

import contextvars
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_acs_fastguard.constants import (
    _CONV_ID_CHARS,
    _RETRY_WINERRORS,
    _SCRIPT_DIR,
    _WORKSPACE_ROOT,
    _fg_attr,
    _is_reparse_or_symlink,
    _is_safe_dir,
    _is_safe_file,
    _stat_safe_file,
    _warn_stderr,
)

_FASTGUARD_MUTEX_ACQUIRED: contextvars.ContextVar[bool] = contextvars.ContextVar("nk_fg_mutex_acq", default=True)


def is_fastguard_mutex_acquired() -> bool:
    """Restituisce False se l'ultimo tentativo di mutex fastguard su Win32 e fallito."""
    return bool(_FASTGUARD_MUTEX_ACQUIRED.get())


def _iter_eff_root_candidates(payload: Dict[str, Any], cli_root: Optional[str]) -> Tuple[Any, ...]:
    ws_paths = payload.get("workspacePaths")
    first_ws = ws_paths[0] if (isinstance(ws_paths, list) and ws_paths and isinstance(ws_paths[0], str)) else None
    return (cli_root, payload.get("projectRoot"), payload.get("workspacePath"), payload.get("workspace_root"), first_ws, os.environ.get("NK_PROJECT_ROOT"), payload.get("cwd"))


def _resolve_eff_root(payload: Dict[str, Any], cli_root: Optional[str]) -> str:
    for raw in _iter_eff_root_candidates(payload, cli_root):
        if isinstance(raw, str):
            cand = raw.strip()
            if cand and _is_safe_dir(cand):
                if not _is_safe_dir(os.path.join(cand, "scripts")):
                    nk_sub = os.path.join(cand, "NK_Hub")
                    if _is_safe_dir(nk_sub) and _is_safe_dir(os.path.join(nk_sub, "scripts")):
                        return os.path.realpath(nk_sub)
                return os.path.realpath(cand)
    return str(_fg_attr("_WORKSPACE_ROOT", _WORKSPACE_ROOT))


def _resolve_hub_and_project_roots(payload: Dict[str, Any], cli_root: Optional[str] = None) -> Tuple[str, str]:
    project_root = _resolve_eff_root(payload, cli_root)
    base_ws = os.path.realpath(str(_fg_attr("_WORKSPACE_ROOT", _WORKSPACE_ROOT)))
    if os.path.basename(project_root) == "NK_Hub" and _is_safe_dir(os.path.join(project_root, "scripts")):
        return project_root, project_root
    sib_hub = os.path.join(os.path.dirname(os.path.dirname(project_root)), "NK_Hub")
    if _is_safe_dir(sib_hub) and _is_safe_dir(os.path.join(sib_hub, "scripts")):
        return os.path.realpath(sib_hub), project_root
    return base_ws, project_root


def _is_valid_conv_id(raw: str) -> bool:
    return 1 <= len(raw) <= 64 and all(ch in _CONV_ID_CHARS for ch in raw)


def _resolve_explicit_conv_id(cli_id: Optional[str], payload: Dict[str, Any]) -> Optional[str]:
    for raw in (cli_id, payload.get("conversationId"), payload.get("conversation_id"), os.environ.get("NK_CONVERSATION_ID")):
        if isinstance(raw, str) and _is_valid_conv_id(raw):
            return raw
    return None


def _resolve_conv_id(cli_id: Optional[str], payload: Dict[str, Any], eff_root: str) -> str:
    valid = _fg_attr("_resolve_explicit_conv_id", _resolve_explicit_conv_id)(cli_id, payload)
    if valid is not None:
        return valid
    import hashlib

    return f"default_{hashlib.sha256(os.path.realpath(eff_root).lower().encode('utf-8')).hexdigest()[:10]}"


def _candidate_roots(eff_root: str) -> List[str]:
    roots = [eff_root]
    if os.path.basename(eff_root) == ".staging":
        parent = os.path.dirname(eff_root)
        if _is_safe_dir(parent):
            roots.append(parent)
    return roots


def _resolve_transcript_path(cli_tp: Optional[str], payload: Dict[str, Any], conv_id: Optional[str]) -> Optional[str]:
    raw = cli_tp or payload.get("transcriptPath") or payload.get("transcript_path")
    if isinstance(raw, str) and raw.strip():
        return raw.strip() if _is_safe_file(raw.strip()) is not None else None
    if conv_id and not conv_id.startswith("default_") and _is_valid_conv_id(conv_id):
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        cand = os.path.join(home, ".gemini", "antigravity", "brain", conv_id, ".system_generated", "logs", "transcript.jsonl")
        if _is_safe_file(cand) is not None:
            return cand
    return None


def _get_hooks_temp_dir() -> Optional[str]:
    reparse_fn = _fg_attr("_is_reparse_or_symlink", _is_reparse_or_symlink)
    base_root = os.environ.get("NK_HOOKS_TEMP_DIR") or os.environ.get("TEMP") or os.environ.get("TMP")
    if not base_root:
        import tempfile
        base_root = tempfile.gettempdir()
    if reparse_fn(base_root):
        return None
    norm_base = os.path.normpath(base_root)
    hooks_dir = norm_base if os.path.basename(norm_base).lower() == "nk_hooks" else os.path.join(norm_base, "nk_hooks")
    if not _is_safe_dir(hooks_dir):
        if reparse_fn(hooks_dir):
            return None
        os.makedirs(hooks_dir, exist_ok=True)
        if reparse_fn(hooks_dir):
            return None
    return hooks_dir


def _default_state() -> Dict[str, Any]:
    return {
        "version": 1, "byte_offset": 0, "steps": 0, "fallback_steps": 0,
        "last_actual_tokens": 0, "prev_actual_tokens": 0, "epoch_baseline_tokens": 0,
        "compaction_epoch": 0, "checkpoint_byte_offset": 0, "reanchor_emitted_offset": -1,
        "z1_epoch": -1, "z3_pre_epoch": -1, "z3_post_epoch": -1,
        "z2_last_spawn_ts": 0.0, "z2_last_spawn_epoch": -1,
        "enforced_prompt_sha256": "", "enforced_epoch": -1, "session_start_ns": 0,
    }


def _reset_state_on_compaction(state: Dict[str, Any], comp_offset: int, *, new_epoch: int) -> None:
    state["compaction_epoch"], state["checkpoint_byte_offset"] = new_epoch, comp_offset
    state["steps"], state["fallback_steps"] = 0, 0
    state["last_actual_tokens"], state["prev_actual_tokens"], state["epoch_baseline_tokens"] = 0, 0, 0
    state["z1_epoch"], state["z3_pre_epoch"], state["z3_post_epoch"] = -1, -1, -1
    state["z2_last_spawn_epoch"], state["z2_last_spawn_ts"] = -1, 0.0


def _load_state_with_exists(state_path: Optional[str]) -> Tuple[Dict[str, Any], bool, bool]:
    state = _default_state()
    if state_path is None or _stat_safe_file(state_path) is None:
        state["session_start_ns"] = time.time_ns()
        return state, False, False
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, default_v in state.items():
                v = data.get(k, default_v)
                if type(v) is type(default_v) or (isinstance(default_v, float) and isinstance(v, (int, float)) and not isinstance(v, bool)):
                    state[k] = float(v) if isinstance(default_v, float) else v
            cur_ns = state.get("session_start_ns")
            if not isinstance(cur_ns, int) or isinstance(cur_ns, bool) or cur_ns <= 0:
                state["session_start_ns"] = time.time_ns()
            return state, True, False
    except Exception:
        pass
    state = _default_state()
    state["session_start_ns"] = time.time_ns()
    return state, True, True


def _load_state(state_path: Optional[str]) -> Dict[str, Any]:
    return _load_state_with_exists(state_path)[0]


def _save_state_atomic(state_path: Optional[str], state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if state_path is None:
        return False, "missing_state_path"
    reparse_fn = _fg_attr("_is_reparse_or_symlink", _is_reparse_or_symlink)
    parent_dir = os.path.dirname(state_path)
    if (parent_dir and reparse_fn(parent_dir)) or reparse_fn(state_path):
        return False, "reparse_guard"
    tmp_path = f"{state_path}.{os.getpid()}.{time.time_ns()}.tmp"
    if reparse_fn(tmp_path):
        return False, "reparse_guard"
    try:
        payload_bytes = json.dumps(state, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, payload_bytes)
        finally:
            os.close(fd)
        delays = (0.01, 0.02, 0.04, 0.08, 0.16)
        last_exc: Optional[OSError] = None
        for attempt, delay in enumerate(delays):
            try:
                if reparse_fn(state_path):
                    return False, "reparse_guard"
                os.replace(tmp_path, state_path)
                return True, None
            except OSError as exc:
                last_exc = exc
                if getattr(exc, "winerror", None) in _RETRY_WINERRORS and attempt < len(delays) - 1:
                    time.sleep(delay)
                    continue
                return (False, f"winerror_exhausted:{exc}") if getattr(exc, "winerror", None) in _RETRY_WINERRORS else (False, f"io_error:{exc}")
        return False, f"winerror_exhausted:{last_exc}"
    except Exception as exc:
        return False, f"io_error:{exc}"
    finally:
        try:
            if not reparse_fn(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass


def _persist_state_or_warn(state_path: Optional[str], state: Dict[str, Any]) -> None:
    ok, err = _save_state_atomic(state_path, state)
    if not ok:
        _warn_stderr("state_save_failed", f"path={state_path} reason={err}")


def _retry_local_fastguard_mutex(conv_id: str, prev_err: str) -> Tuple[Optional[int], str]:
    from _internal.nk_common.win32_mutex import create_or_open_named_mutex

    handle2, acquired2, err2 = create_or_open_named_mutex(f"Local\\NK_FastguardState_{conv_id}", wait_ms=500)
    return (handle2, "") if (acquired2 and handle2 is not None) else (None, err2 or prev_err)


def _try_open_fastguard_mutex(conv_id: str) -> Tuple[Optional[int], str]:
    from _internal.nk_common.win32_mutex import create_or_open_named_mutex

    err = ""
    for ns in ("Global", "Local"):
        handle, acquired, err = create_or_open_named_mutex(f"{ns}\\NK_FastguardState_{conv_id}", wait_ms=2000)
        if acquired and handle is not None:
            return handle, ""
        if ns == "Global" and err and "5" not in str(err) and "access" not in str(err).lower():
            break
    return _retry_local_fastguard_mutex(conv_id, err)


def _acquire_fastguard_mutex(conv_id: str) -> Optional[int]:
    """Acquisisce Named Mutex Win32 per fastguard_<conv_id>.json tracciando stato acquisizione."""
    if sys.platform != "win32":
        _FASTGUARD_MUTEX_ACQUIRED.set(True)
        return None
    try:
        scr_dir, ws_root = str(_fg_attr("_SCRIPT_DIR", _SCRIPT_DIR)), str(_fg_attr("_WORKSPACE_ROOT", _WORKSPACE_ROOT))
        for base_d in (scr_dir, os.path.join(ws_root, "scripts")):
            if base_d and base_d not in sys.path:
                sys.path.insert(0, base_d)
        handle, err = _try_open_fastguard_mutex(conv_id)
        if handle is not None:
            _FASTGUARD_MUTEX_ACQUIRED.set(True)
            return handle
        _FASTGUARD_MUTEX_ACQUIRED.set(False)
        _warn_stderr("fastguard_mutex_busy", f"conv_id={conv_id} reason={err}")
        return None
    except Exception as exc:
        _FASTGUARD_MUTEX_ACQUIRED.set(False)
        _warn_stderr("fastguard_mutex_error", f"conv_id={conv_id} reason={exc}")
        return None


def _release_fastguard_mutex(handle: Optional[int]) -> None:
    _FASTGUARD_MUTEX_ACQUIRED.set(True)
    if handle is None:
        return
    try:
        from _internal.nk_common.win32_mutex import release_win32_mutex

        release_win32_mutex(handle)
    except Exception:
        pass
