# -*- coding: utf-8 -*-
"""Costanti, soglie lazy e marker di compattazione per nk_context_sentry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from _internal.nk_common.constants import HIGH_CAPACITY_PROFILES
from _internal.nk_common.paths import reconfigure_streams
from _internal.nk_common.thresholds import _safe_pos_int, load_saturation_thresholds
from _internal.nk_common.transcript_guards import (
    SPOOF_SOURCES as _UNTRUSTED_COMPACTION_SOURCES,
    SPOOF_TYPES as _UNTRUSTED_COMPACTION_TYPES,
    has_compaction_candidate_bytes,
    is_verified_compaction,
)

_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent.parent
_workspace_root = (
    _SCRIPTS_DIR.parent.parent
    if _SCRIPTS_DIR.parent.name == ".staging"
    else _SCRIPTS_DIR.parent
)

_THRESHOLDS_CACHE: Optional[Dict[str, Any]] = None

SWARM_MSG_MSS_CAP: int = 1800
SWARM_MSG_HARD_CAP: int = 2000
STANDARD_GREEN_STEP_THRESHOLD: int = 70
STANDARD_RED_STEP_THRESHOLD: int = 100
STANDARD_GREEN_TOKEN_THRESHOLD: int = 80_000
STANDARD_RED_TOKEN_THRESHOLD: int = 120_000
CARBON_GREEN_STEP_THRESHOLD: int = 150
CARBON_RED_STEP_THRESHOLD: int = 250
CARBON_GREEN_TOKEN_THRESHOLD: int = 250_000
CARBON_RED_TOKEN_THRESHOLD: int = 500_000
CARBON_ACTUAL_WARN_TOKENS: int = 150_000
CARBON_ACTUAL_RED_TOKENS: int = 200_000
GENERATION_GREEN_STEP_THRESHOLD: int = CARBON_GREEN_STEP_THRESHOLD
GENERATION_RED_STEP_THRESHOLD: int = CARBON_RED_STEP_THRESHOLD
GENERATION_GREEN_TOKEN_THRESHOLD: int = CARBON_GREEN_TOKEN_THRESHOLD
GENERATION_RED_TOKEN_THRESHOLD: int = CARBON_RED_TOKEN_THRESHOLD
GENERATION_ACTUAL_WARN_TOKENS: int = CARBON_ACTUAL_WARN_TOKENS
GENERATION_ACTUAL_RED_TOKENS: int = CARBON_ACTUAL_RED_TOKENS
ARGON_ACTUAL_WARN_TOKENS: int = CARBON_ACTUAL_WARN_TOKENS
ARGON_ACTUAL_RED_TOKENS: int = CARBON_ACTUAL_RED_TOKENS
PLATFORM_COMPACTION_TOKEN_LIMIT: int = 273_000
COMPACTION_SUMMARY_MARKER: str = "<CONTEXT_SUMMARY>"
CONTEXT_BACKSCAN_CHUNK_BYTES: int = 65536
CONTEXT_MAX_SCAN_BYTES: int = 50 * 1024 * 1024


def _get_thresholds_data(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Carica pigramente i dati di saturazione solo al primo utilizzo effettivo."""
    global _THRESHOLDS_CACHE
    if workspace_root is not None:
        return load_saturation_thresholds(workspace_root=workspace_root)
    if _THRESHOLDS_CACHE is None:
        _THRESHOLDS_CACHE = load_saturation_thresholds(workspace_root=_workspace_root)
    return _THRESHOLDS_CACHE


def get_lazy_threshold_attr(name: str) -> Any:
    """Risolve i dizionari di soglia lazy richiesti dalla facciata."""
    if name == "_THRESHOLDS_DATA":
        return _get_thresholds_data()
    if name == "_PROFILES_DATA":
        data = _get_thresholds_data()
        return data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    if name == "_STD_CS":
        profiles = get_lazy_threshold_attr("_PROFILES_DATA")
        return (
            profiles.get("standard", {}).get("context_sentry", {})
            if isinstance(profiles.get("standard"), dict)
            else {}
        )
    if name in ("_CARB_CS", "_GEN_CS"):
        profiles = get_lazy_threshold_attr("_PROFILES_DATA")
        entry = (
            profiles.get("generation")
            if name == "_GEN_CS" and isinstance(profiles.get("generation"), dict)
            else profiles.get("carbon")
            if isinstance(profiles.get("carbon"), dict)
            else profiles.get("generation")
        )
        return entry.get("context_sentry", {}) if isinstance(entry, dict) else {}
    raise AttributeError(name)


def _contains_compaction_marker(raw_line: str, data: Dict[str, Any]) -> bool:
    """Rileva un vero checkpoint di compattazione delegando a nk_common."""
    return is_verified_compaction(data)


__all__ = [
    "ARGON_ACTUAL_RED_TOKENS",
    "ARGON_ACTUAL_WARN_TOKENS",
    "CARBON_ACTUAL_RED_TOKENS",
    "CARBON_ACTUAL_WARN_TOKENS",
    "CARBON_GREEN_STEP_THRESHOLD",
    "CARBON_GREEN_TOKEN_THRESHOLD",
    "CARBON_RED_STEP_THRESHOLD",
    "CARBON_RED_TOKEN_THRESHOLD",
    "COMPACTION_SUMMARY_MARKER",
    "CONTEXT_BACKSCAN_CHUNK_BYTES",
    "CONTEXT_MAX_SCAN_BYTES",
    "GENERATION_ACTUAL_RED_TOKENS",
    "GENERATION_ACTUAL_WARN_TOKENS",
    "GENERATION_GREEN_STEP_THRESHOLD",
    "GENERATION_GREEN_TOKEN_THRESHOLD",
    "GENERATION_RED_STEP_THRESHOLD",
    "GENERATION_RED_TOKEN_THRESHOLD",
    "HIGH_CAPACITY_PROFILES",
    "PLATFORM_COMPACTION_TOKEN_LIMIT",
    "STANDARD_GREEN_STEP_THRESHOLD",
    "STANDARD_GREEN_TOKEN_THRESHOLD",
    "STANDARD_RED_STEP_THRESHOLD",
    "STANDARD_RED_TOKEN_THRESHOLD",
    "SWARM_MSG_HARD_CAP",
    "SWARM_MSG_MSS_CAP",
    "_UNTRUSTED_COMPACTION_SOURCES",
    "_UNTRUSTED_COMPACTION_TYPES",
    "_contains_compaction_marker",
    "_get_thresholds_data",
    "_safe_pos_int",
    "_workspace_root",
    "get_lazy_threshold_attr",
    "has_compaction_candidate_bytes",
    "load_saturation_thresholds",
    "reconfigure_streams",
]
