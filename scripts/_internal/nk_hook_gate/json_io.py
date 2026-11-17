"""I/O stdin/JSON atomico, gestione reparse point e helper fast-path a bassa latenza."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from _internal.nk_hook_gate.core_env import (
    _DELEGATION_TOOLS,
    _IS_WIN,
    _REPARSE_ATTR_MASK,
    _RETRY_WINERRORS,
    _SAFE_READONLY_UNSAFE_ARG_KEYS,
    _STREAK_EXEMPT_TOOLS,
    _WORKSPACE_ROOT,
    _is_safe_conv_id,
)

if TYPE_CHECKING:
    from pathlib import Path
else:
    Path = Any


def _get_hooks_temp_dir_str() -> str:
    """Restituisce e crea la directory temporanea per gli hook usando solo os.path."""
    temp_base = (
        os.environ.get("NK_HOOKS_TEMP_DIR")
        or os.environ.get("TEMP")
        or os.environ.get("TMP")
        or os.environ.get("TMPDIR")
    )
    if not temp_base:
        import tempfile

        temp_base = tempfile.gettempdir()
    base = os.path.join(temp_base, "nk_hooks")
    os.makedirs(base, exist_ok=True)
    return base


def _get_hooks_temp_dir() -> Path:
    """Restituisce come oggetto Path la directory temporanea per lo stato degli hook."""
    from pathlib import Path

    return Path(_get_hooks_temp_dir_str())


def _is_win_pipe_empty(fd: int) -> bool:
    """Verifica con singolo PeekNamedPipe (max 1ms) se una pipe Win32 stdin e vuota."""
    import _winapi
    import msvcrt

    try:
        handle = msvcrt.get_osfhandle(fd)
        avail, _ = _winapi.PeekNamedPipe(handle, 0)
        if avail == 0:
            time.sleep(0.001)
            avail, _ = _winapi.PeekNamedPipe(handle, 0)
            return avail == 0
    except OSError:
        return False
    return False


def _read_stdin_payload_ex() -> Tuple[Dict[str, Any], bool]:
    """Legge JSON da stdin via buffer UTF-8 con fallback StringIO restituendo (payload, parse_error)."""
    try:
        if sys.stdin is None:
            return {}, False
        try:
            if sys.stdin.isatty():
                return {}, False
        except Exception:
            pass
        if _IS_WIN and hasattr(sys.stdin, "fileno"):
            try:
                fd = sys.stdin.fileno()
                if (os.fstat(fd).st_mode & 0xF000) == 0x1000 and _is_win_pipe_empty(fd):
                    return {}, False
            except Exception:
                pass
        buf = getattr(sys.stdin, "buffer", None)
        try:
            if buf is not None:
                raw_b = buf.read()
                raw = raw_b.decode("utf-8", errors="replace") if isinstance(raw_b, (bytes, bytearray)) else str(raw_b or "")
            else:
                raw = sys.stdin.read()
        except OSError:
            return {}, False
        cleaned = raw.lstrip("\ufeff").strip() if raw else ""
        if not cleaned:
            return {}, False
        try:
            parsed = json.loads(cleaned)
        except Exception:
            return {}, True
        return (parsed, False) if isinstance(parsed, dict) else ({}, True)
    except Exception:
        return {}, True


def _resolve_conv_id(cli_id: Optional[str], payload: Dict[str, Any]) -> str:
    """Risolve l'identificativo di conversazione validato o fallback SHA-256."""
    for raw in (
        cli_id,
        payload.get("conversationId"),
        payload.get("conversation_id"),
        os.environ.get("NK_CONVERSATION_ID"),
    ):
        if _is_safe_conv_id(raw):
            return str(raw)
    import hashlib

    norm_ws = os.path.realpath(str(_WORKSPACE_ROOT)).lower().encode("utf-8")
    return f"default_{hashlib.sha256(norm_ws).hexdigest()[:10]}"


def _is_path_reparse_str(path_str: str) -> bool:
    """Rileva symlink o Win32 junction/reparse point senza istanziare pathlib."""
    try:
        if os.path.islink(path_str):
            return True
        st = os.lstat(path_str)
        if (getattr(st, "st_file_attributes", 0) & _REPARSE_ATTR_MASK) != 0:
            return True
    except OSError:
        pass
    return False


def _is_path_reparse_point(path_obj: Path | str) -> bool:
    """Rileva symlink o Win32 junction/reparse point sul percorso indicato."""
    return _is_path_reparse_str(str(path_obj))


def _read_json_safe(path_obj: Path | str) -> Optional[Dict[str, Any]]:
    """Legge un JSON locale rifiutando symlink o reparse point."""
    path_str = str(path_obj)
    try:
        if (
            not os.path.isfile(path_str)
            or _is_path_reparse_str(os.path.dirname(path_str))
            or _is_path_reparse_str(path_str)
        ):
            return None
        with open(path_str, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json_atomic_str(path_str: str, data: Dict[str, Any]) -> None:
    """Scrive atomicamente un JSON in %TEMP%/nk_hooks con protezione symlink e retry Win32."""
    parent_dir = os.path.dirname(path_str)
    if parent_dir and _is_path_reparse_str(parent_dir):
        return
    if os.path.exists(path_str) and _is_path_reparse_str(path_str):
        return
    tmp_str = f"{path_str}.{os.getpid()}.{time.time_ns()}.tmp"
    if os.path.exists(tmp_str) and _is_path_reparse_str(tmp_str):
        return
    raw = json.dumps(data, ensure_ascii=True).encode("utf-8")
    try:
        fd = os.open(tmp_str, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        for attempt, delay in enumerate((0.01, 0.02, 0.04, 0.08, 0.16)):
            try:
                if os.path.exists(path_str) and _is_path_reparse_str(path_str):
                    return
                os.replace(tmp_str, path_str)
                return
            except OSError as exc:
                if getattr(exc, "winerror", None) in _RETRY_WINERRORS and attempt < 4:
                    time.sleep(delay)
                    continue
                return
    except Exception:
        pass
    finally:
        try:
            if os.path.exists(tmp_str) and not _is_path_reparse_str(tmp_str):
                os.unlink(tmp_str)
        except Exception:
            pass


def _write_json_atomic_safe(path_obj: Path, data: Dict[str, Any]) -> None:
    """Scrive atomicamente un JSON da Path rifiutando symlink o reparse point."""
    _write_json_atomic_str(str(path_obj), data)


def _sha256_file(path: Path) -> str:
    """Calcola l'hash SHA-256 del file indicato normalizzando i fine riga."""
    import hashlib

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _extract_first_section(text: str) -> str:
    """Estrae la prima sezione storica da PATCH_NOTES.md per il controllo prepend-only."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for idx, ln in enumerate(lines):
        if ln.startswith("## "):
            return "\n".join(lines[idx : idx + 6])
    return "\n".join(lines[:6])


def _extract_historical_headers(text: str) -> List[str]:
    """Estrae tutte le intestazioni storiche di livello ## da PATCH_NOTES.md."""
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("## ")]


def _extract_tool_identity(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Estrae (tool_call, tool_name) dal payload supportando camelCase e snake_case."""
    tc = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else (payload.get("tool_call") if isinstance(payload.get("tool_call"), dict) else {})
    tname = str(
        payload.get("toolName") or payload.get("tool_name") or payload.get("name")
        or tc.get("name") or tc.get("toolName") or tc.get("tool_name") or ""
    ).strip()
    return tc, tname


def _extract_args_dict(payload: Dict[str, Any], tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae il dizionario argomenti supportando sia chiavi camelCase sia snake_case."""
    for cand in (
        payload.get("args"), payload.get("arguments"), payload.get("tool_input"), payload.get("toolInput"), payload.get("input"),
        tool_call.get("args"), tool_call.get("arguments"), tool_call.get("tool_input"), tool_call.get("toolInput"), tool_call.get("input"),
    ):
        if isinstance(cand, dict):
            return cand
        if isinstance(cand, str) and cand.strip().startswith("{"):
            try:
                parsed_c = json.loads(cand)
                if isinstance(parsed_c, dict):
                    return parsed_c
            except Exception:
                pass
    return payload if isinstance(payload, dict) else {}


def _has_unsafe_readonly_args(args: Dict[str, Any]) -> bool:
    """Verifica che gli argomenti di un tool read-only non contengano chiavi shell/scrittura/MCP o byte nulli."""
    if not isinstance(args, dict):
        return True
    for k in _SAFE_READONLY_UNSAFE_ARG_KEYS:
        val = args.get(k)
        if isinstance(val, str):
            if val.strip():
                return True
        elif isinstance(val, list):
            if val:
                return True
        elif val is not None:
            return True
    return any(isinstance(v, str) and "\x00" in v for v in args.values())


def _write_probe_record(conv_id: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Registra in modo leggero e veloce evento e chiavi payload nella sonda jsonl."""
    probe_file = os.path.join(_get_hooks_temp_dir_str(), f"probe_{conv_id}.jsonl")
    _, tool_name = _extract_tool_identity(payload)
    record = {
        "timestamp": time.time(),
        "event": event,
        "conversation_id": conv_id,
        "payload_keys": sorted(payload.keys()),
        "tool_name": tool_name,
    }
    with open(probe_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    return {}


def _read_fasttrack_streak(conv_id: str) -> int:
    """Legge lo streak fasttrack corrente con sola libreria os/json senza reparse escape."""
    ft_file = os.path.join(_get_hooks_temp_dir_str(), f"fasttrack_{conv_id}.json")
    data = _read_json_safe(ft_file)
    if data is None:
        return 0
    try:
        return int(data.get("streak", 0))
    except Exception:
        return 0


def _update_fasttrack_streak(conv_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna atomicamente lo streak fasttrack evitando scritture parziali."""
    ft_file = os.path.join(_get_hooks_temp_dir_str(), f"fasttrack_{conv_id}.json")
    data = _read_json_safe(ft_file)
    state: Dict[str, Any] = dict(data) if data is not None else {"streak": 0}
    _, tname = _extract_tool_identity(payload)
    tname_low = tname.lower()
    if tname_low in _DELEGATION_TOOLS or payload.get("reset") is True:
        state["streak"] = 0
    elif tname_low in _STREAK_EXEMPT_TOOLS or not tname_low:
        try:
            state["streak"] = int(state.get("streak", 0))
        except Exception:
            state["streak"] = 0
    else:
        try:
            state["streak"] = int(state.get("streak", 0)) + 1
        except Exception:
            state["streak"] = 1
    _write_json_atomic_str(ft_file, state)
    if state["streak"] > 12:
        return {
            "streak": state["streak"],
            "ephemeralMessage": f"[RULE-01] Fast-Track streak ({state['streak']} > 12). Delegate work via invoke_subagent.",
        }
    return {}


def _log_shadow_decision(
    conv_id: str, subcommand: str, event: str, res: Dict[str, Any]
) -> None:
    """Registra in modalita shadow i potenziali blocchi o avvisi nel file shadow jsonl."""
    shadow_file = os.path.join(_get_hooks_temp_dir_str(), f"shadow_{conv_id}.jsonl")
    decision_val = res.get("decision") or ("warn" if res.get("ephemeralMessage") else "allow")
    record = {
        "timestamp": time.time(),
        "subcommand": subcommand,
        "event": event,
        "conversation_id": conv_id,
        "would_decide": decision_val,
        "decision": decision_val,
        "reason": res.get("reason") or res.get("ephemeralMessage") or "",
    }
    with open(shadow_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")
