# -*- coding: utf-8 -*-
"""Costanti, soglie lazy e marker di compattazione per nk_context_sentry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from _internal.nk_common.constants import (
    HIGH_CAPACITY_PROFILES,
    SUPPORTED_MODEL_PROFILES,
)
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
NEON_GREEN_STEP_THRESHOLD: int = CARBON_GREEN_STEP_THRESHOLD
NEON_RED_STEP_THRESHOLD: int = CARBON_RED_STEP_THRESHOLD
NEON_GREEN_TOKEN_THRESHOLD: int = CARBON_GREEN_TOKEN_THRESHOLD
NEON_RED_TOKEN_THRESHOLD: int = CARBON_RED_TOKEN_THRESHOLD
NEON_ACTUAL_WARN_TOKENS: int = CARBON_ACTUAL_WARN_TOKENS
NEON_ACTUAL_RED_TOKENS: int = CARBON_ACTUAL_RED_TOKENS
PRO_GREEN_STEP_THRESHOLD: int = CARBON_GREEN_STEP_THRESHOLD
PRO_RED_STEP_THRESHOLD: int = CARBON_RED_STEP_THRESHOLD
PRO_GREEN_TOKEN_THRESHOLD: int = CARBON_GREEN_TOKEN_THRESHOLD
PRO_RED_TOKEN_THRESHOLD: int = CARBON_RED_TOKEN_THRESHOLD
PRO_ACTUAL_WARN_TOKENS: int = CARBON_ACTUAL_WARN_TOKENS
PRO_ACTUAL_RED_TOKENS: int = CARBON_ACTUAL_RED_TOKENS
FLASH_GREEN_STEP_THRESHOLD: int = 90
FLASH_RED_STEP_THRESHOLD: int = 140
FLASH_GREEN_TOKEN_THRESHOLD: int = 100_000
FLASH_RED_TOKEN_THRESHOLD: int = 160_000
FLASH_ACTUAL_WARN_TOKENS: int = 120_000
FLASH_ACTUAL_RED_TOKENS: int = 160_000
ARGON_ACTUAL_WARN_TOKENS: int = CARBON_ACTUAL_WARN_TOKENS
ARGON_ACTUAL_RED_TOKENS: int = CARBON_ACTUAL_RED_TOKENS
PLATFORM_COMPACTION_TOKEN_LIMIT: int = 273_000
COMPACTION_SUMMARY_MARKER: str = "<CONTEXT_SUMMARY>"
CONTEXT_BACKSCAN_CHUNK_BYTES: int = 65536
CONTEXT_MAX_SCAN_BYTES: int = 50 * 1024 * 1024

_PROFILE_ATTR_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    "_STD_CS": ("standard",),
    "_CARB_CS": ("carbon", "generation"),
    "_GEN_CS": ("generation", "carbon"),
    "_NEON_CS": ("neon", "generation", "carbon"),
    "_PRO_CS": ("pro", "generation", "carbon"),
    "_FLASH_CS": ("flash", "standard"),
}


def _get_thresholds_data(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Carica pigramente i dati di saturazione solo al primo utilizzo effettivo."""
    global _THRESHOLDS_CACHE
    if workspace_root is not None:
        return load_saturation_thresholds(workspace_root=workspace_root)
    if _THRESHOLDS_CACHE is None:
        _THRESHOLDS_CACHE = load_saturation_thresholds(workspace_root=_workspace_root)
    return _THRESHOLDS_CACHE


def _lookup_profile_ctx(candidates: Tuple[str, ...]) -> Dict[str, Any]:
    """Restituisce il blocco context_sentry per la prima chiave profilo presente."""
    profiles = get_lazy_threshold_attr("_PROFILES_DATA")
    for key in candidates:
        entry = profiles.get(key)
        if isinstance(entry, dict):
            return entry.get("context_sentry", {})
    return {}


def get_lazy_threshold_attr(name: str) -> Any:
    """Risolve i dizionari di soglia lazy richiesti dalla facciata."""
    if name == "_THRESHOLDS_DATA":
        return _get_thresholds_data()
    if name == "_PROFILES_DATA":
        data = _get_thresholds_data()
        return data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    candidates = _PROFILE_ATTR_CANDIDATES.get(name)
    if candidates is not None:
        return _lookup_profile_ctx(candidates)
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
    "FLASH_ACTUAL_RED_TOKENS",
    "FLASH_ACTUAL_WARN_TOKENS",
    "FLASH_GREEN_STEP_THRESHOLD",
    "FLASH_GREEN_TOKEN_THRESHOLD",
    "FLASH_RED_STEP_THRESHOLD",
    "FLASH_RED_TOKEN_THRESHOLD",
    "GENERATION_ACTUAL_RED_TOKENS",
    "GENERATION_ACTUAL_WARN_TOKENS",
    "GENERATION_GREEN_STEP_THRESHOLD",
    "GENERATION_GREEN_TOKEN_THRESHOLD",
    "GENERATION_RED_STEP_THRESHOLD",
    "GENERATION_RED_TOKEN_THRESHOLD",
    "HIGH_CAPACITY_PROFILES",
    "NEON_ACTUAL_RED_TOKENS",
    "NEON_ACTUAL_WARN_TOKENS",
    "NEON_GREEN_STEP_THRESHOLD",
    "NEON_GREEN_TOKEN_THRESHOLD",
    "NEON_RED_STEP_THRESHOLD",
    "NEON_RED_TOKEN_THRESHOLD",
    "PLATFORM_COMPACTION_TOKEN_LIMIT",
    "PRO_ACTUAL_RED_TOKENS",
    "PRO_ACTUAL_WARN_TOKENS",
    "PRO_GREEN_STEP_THRESHOLD",
    "PRO_GREEN_TOKEN_THRESHOLD",
    "PRO_RED_STEP_THRESHOLD",
    "PRO_RED_TOKEN_THRESHOLD",
    "STANDARD_GREEN_STEP_THRESHOLD",
    "STANDARD_GREEN_TOKEN_THRESHOLD",
    "STANDARD_RED_STEP_THRESHOLD",
    "STANDARD_RED_TOKEN_THRESHOLD",
    "SUPPORTED_MODEL_PROFILES",
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
