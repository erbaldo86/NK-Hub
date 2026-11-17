#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentinella runtime degli step per NK Hub Generation 1.0.0-Generation.
Modulo: nk_active_runtime_sentinel.py.
@domain_id: DOM-05
Implementa la guardia GT-02 con profili standard, generation, carbon e argon e reset su <CONTEXT_SUMMARY>.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = _scripts_dir.parent.parent if _scripts_dir.parent.name == ".staging" else _scripts_dir.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if _scripts_dir.parent.name == ".staging" and (_scripts_dir / "_internal" / "nk_common").is_dir():
    _prod_scripts_dir = _workspace_root / "scripts"
    if _prod_scripts_dir.is_dir() and str(_prod_scripts_dir) not in sys.path:
        sys.path.append(str(_prod_scripts_dir))
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    for _pkg_obj, _stg_dir in (
        (_stg_int, str(_scripts_dir / "_internal")),
        (_stg_nkc, str(_scripts_dir / "_internal" / "nk_common")),
    ):
        _cur_p = list(getattr(_pkg_obj, "__path__", ()))
        _pkg_obj.__path__ = [_stg_dir] + [p for p in _cur_p if os.path.normcase(p) != os.path.normcase(_stg_dir)]

from _internal.nk_common.constants import HIGH_CAPACITY_PROFILES  # noqa: E402
from _internal.nk_common.facade_boot import _prepend_pkg_overlay  # noqa: E402
from _internal.nk_common.io import atomic_write_text  # noqa: E402
from _internal.nk_common.paths import reconfigure_streams  # noqa: E402
from _internal.nk_common.thresholds import _safe_pos_int, load_saturation_thresholds  # noqa: E402
from _internal.nk_common.transcript_guards import (  # noqa: E402
    extract_actual_tokens_from_record,
    is_verified_compaction,
    valid_token_int,
)
from _internal.nk_common.win32_mutex import (  # noqa: E402
    create_or_open_named_mutex,
    get_kernel32,
    release_win32_mutex,
)

if _scripts_dir.parent.name == ".staging" and (_scripts_dir / "_internal" / "nk_transcript_tools").is_dir():
    _prepend_pkg_overlay("_internal.nk_transcript_tools", str(_scripts_dir / "_internal" / "nk_transcript_tools"))

try:
    from nk_transcript_tools import discover_active_main_transcript
except ImportError:
    from scripts.nk_transcript_tools import discover_active_main_transcript  # type: ignore[no-redef]


def _get_step_thresholds(profile_name: str) -> Tuple[int, int, int]:
    """Restituisce (green_max_steps, caution_max_steps, critical_max_steps) dal JSON canonico."""
    norm = (profile_name or "standard").lower().strip()
    is_hc = norm in HIGH_CAPACITY_PROFILES
    defaults = (120, 180, 250) if is_hc else (60, 85, 100)
    data = load_saturation_thresholds(workspace_root=_workspace_root)
    profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    prof_entry = profiles.get(norm) if isinstance(profiles, dict) else None
    if not isinstance(prof_entry, dict) and is_hc and isinstance(profiles, dict):
        prof_entry = profiles.get("generation") or profiles.get("carbon")
    rs = (
        prof_entry.get("runtime_sentinel")
        if isinstance(prof_entry, dict) and isinstance(prof_entry.get("runtime_sentinel"), dict)
        else {}
    )
    return (
        _safe_pos_int(rs.get("green_max_steps"), defaults[0]),
        _safe_pos_int(rs.get("caution_max_steps"), defaults[1]),
        _safe_pos_int(rs.get("critical_max_steps"), defaults[2]),
    )


COMPACTION_SUMMARY_MARKER: str = "<CONTEXT_SUMMARY>"
_STATE_SEVERITY: Dict[str, int] = {"GREEN": 0, "CAUTION": 1, "CRITICAL": 2, "RED": 3}
_HIGH_CAP_TOKEN_TIERS = ((200_000, "RED"), (185_000, "CRITICAL"), (150_000, "CAUTION"))
_STD_TOKEN_TIERS = ((120_000, "RED"), (100_000, "CRITICAL"), (80_000, "CAUTION"))


def _get_kernel32_mutex_api() -> Any:
    """Restituisce l'API kernel32 WinDLL tramite nk_common.win32_mutex."""
    return get_kernel32()


class _SentinelNamedMutex:
    """Mutex Win32 fail-closed per proteggere sentinel_state.json sotto concorrenza (<50ms)."""

    def __init__(self, name: str, timeout_ms: int = 1000) -> None:
        self.name = str(name)
        self.timeout_ms = max(0, int(timeout_ms))
        self._handle: Optional[int] = None
        self._acquired_win32 = False
        self._k32: Any = _get_kernel32_mutex_api()

    def __enter__(self) -> bool:
        if self._k32 is None:
            self._handle = None
            self._acquired_win32 = False
            return False
        handle, acquired, _ = create_or_open_named_mutex(self.name, wait_ms=self.timeout_ms, k32=self._k32)
        if acquired and handle is not None:
            self._handle = handle
            self._acquired_win32 = True
            return True
        self._handle = None
        self._acquired_win32 = False
        return False

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._handle is not None:
            release_win32_mutex(self._handle, k32=self._k32)
            self._handle = None
            self._acquired_win32 = False


def _coerce_non_bool_int(value: Any) -> Optional[int]:
    """Delega la validazione intera non negativa a nk_common.transcript_guards."""
    return valid_token_int(value)


def _extract_actual_tokens_from_record(parsed: Dict[str, Any]) -> Optional[int]:
    """Delega l'estrazione token transcript a nk_common.transcript_guards."""
    return extract_actual_tokens_from_record(parsed)


def calculate_state(
    steps: int,
    profile: str = "standard",
    actual_tokens: Optional[int] = None,
) -> str:
    """Calcola lo stato runtime preservando 60/85/100 in standard e 120/180/250 in generation, carbon e argon (GT-02)."""
    norm_prof = (profile or "standard").lower().strip()
    is_high_cap = norm_prof in HIGH_CAPACITY_PROFILES
    green_max, caution_max, critical_max = _get_step_thresholds(norm_prof)
    if steps < green_max:
        step_state = "GREEN"
    elif steps < caution_max:
        step_state = "CAUTION"
    elif steps < critical_max:
        step_state = "CRITICAL"
    else:
        step_state = "RED"

    tok_val = _coerce_non_bool_int(actual_tokens)
    if tok_val is None:
        return step_state

    tiers = _HIGH_CAP_TOKEN_TIERS if is_high_cap else _STD_TOKEN_TIERS
    tok_state = next((st for lim, st in tiers if tok_val >= lim), "GREEN")
    return tok_state if _STATE_SEVERITY[tok_state] > _STATE_SEVERITY[step_state] else step_state


def _discover_active_transcript() -> Optional[str]:
    """Individua il transcript attivo dell'agente principale tramite SSOT EXT-05."""
    found = discover_active_main_transcript()
    return str(found) if found is not None else None


def _is_compaction_checkpoint(stripped: str, parsed: Dict[str, Any]) -> bool:
    """Rileva un vero record di compattazione delegando a nk_common.transcript_guards (TV-08)."""
    if not isinstance(parsed, dict):
        return False
    if "\\u003c" in stripped.lower():
        raw_c = parsed.get("content") or parsed.get("text") or ""
        if not isinstance(raw_c, str) or COMPACTION_SUMMARY_MARKER not in raw_c.lstrip():
            return False
    return is_verified_compaction(parsed)


def _scan_transcript_since_compaction(
    transcript_path: Path,
) -> Tuple[int, int, int, Optional[int]]:
    """Scansiona step, righe non vuote, caratteri e actual_tokens post-compattazione."""
    steps = 0
    non_empty = 0
    total_chars = 0
    actual_tokens: Optional[int] = None
    if not transcript_path or not transcript_path.is_file():
        return 0, 0, 0, None

    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            total_chars += len(raw_line)
            if not stripped:
                continue
            non_empty += 1
            try:
                parsed = json.loads(stripped)
            except Exception:
                continue
            if isinstance(parsed, dict):
                tok = _extract_actual_tokens_from_record(parsed)
                if _is_compaction_checkpoint(stripped, parsed):
                    steps = 1
                    total_chars = len(raw_line)
                    actual_tokens = tok
                else:
                    steps += 1
                    if tok is not None:
                        actual_tokens = tok

    return steps, non_empty, total_chars, actual_tokens


def _count_steps_since_compaction(transcript_path: Path) -> Tuple[int, int, int]:
    """Conta step JSON validi, righe non vuote e caratteri dall'ultimo checkpoint di compattazione."""
    steps, non_empty, total_chars, _ = _scan_transcript_since_compaction(transcript_path)
    return steps, non_empty, total_chars


def _write_state_atomic_win32(state_file: str, result: Dict[str, Any]) -> None:
    """Scrive sentinel_state.json in modo atomico protetto da Named Mutex fail-closed e nk_common.io."""
    abs_state = os.path.abspath(state_file)
    os.makedirs(os.path.dirname(abs_state), exist_ok=True)
    mutex_hash = hashlib.sha256(abs_state.lower().encode("utf-8")).hexdigest()[:16]
    with _SentinelNamedMutex(f"Global\\NK_SentinelState_{mutex_hash}", timeout_ms=1000) as acquired:
        if not acquired:
            return
        ok, err = atomic_write_text(abs_state, json.dumps(result), fsync_data=False)
        if not ok:
            raise OSError(err or f"Atomic state write failed for {abs_state}")


def _infer_sentinel_conv_id(transcript_path: Optional[str]) -> str:
    """Estrae un conversation_id sicuro da NK_CONVERSATION_ID o dal path brain/ per isolare sentinel_state."""
    raw_cid = os.environ.get("NK_CONVERSATION_ID", "").strip()
    if not raw_cid and transcript_path:
        parts = Path(transcript_path).resolve().parts
        for idx, pt in enumerate(parts):
            if pt == "brain" and idx + 1 < len(parts):
                raw_cid = parts[idx + 1]
                break
    safe = "".join(ch for ch in raw_cid if ch.isalnum() or ch in ("_", "-"))[:64]
    return safe or "default"


def run_sentinel(
    transcript_path: Optional[str], profile: str = "standard"
) -> Dict[str, Any]:
    """Conta gli step JSON validi post-compattazione e salva lo stato isolato per conversazione."""
    steps = 0
    total_chars = 0
    actual_tokens: Optional[int] = None

    if transcript_path and os.path.exists(transcript_path):
        steps, non_empty, total_chars, actual_tokens = _scan_transcript_since_compaction(Path(transcript_path))
        if steps == 0 and non_empty > 0:
            steps = non_empty

    tokens = max(1, total_chars // 4)
    state = calculate_state(steps, profile=profile, actual_tokens=actual_tokens)
    result: Dict[str, Any] = {"steps": steps, "tokens": tokens, "state": state, "profile": profile}
    if actual_tokens is not None:
        result["actual_tokens"] = actual_tokens

    conv_sig = _infer_sentinel_conv_id(transcript_path)
    state_file = os.path.join(tempfile.gettempdir(), "nk_diagnostics", f"sentinel_state_{conv_sig}.json")
    _write_state_atomic_win32(state_file, result)
    return result


def main() -> None:
    """Punto di ingresso CLI della sentinella runtime degli step."""
    reconfigure_streams()
    default_profile = os.environ.get("NK_MODEL_PROFILE", "generation")
    parser = argparse.ArgumentParser(description="Sentinella Runtime Step NK Hub Generation 1.0.0-Generation")
    parser.add_argument("--transcript", required=False, default=None)
    parser.add_argument("--profile", default=default_profile, help="Profilo soglie step: standard, generation, carbon o argon")
    parser.add_argument("--conversation-id", required=False, default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.conversation_id and not os.environ.get("NK_CONVERSATION_ID"):
        os.environ["NK_CONVERSATION_ID"] = str(args.conversation_id)
    target = args.transcript or _discover_active_transcript()
    result = run_sentinel(target, profile=args.profile)

    if args.json:
        print(json.dumps(result))
    if args.check and result["state"] == "RED":
        sys.exit(1)


if __name__ == "__main__":
    main()
