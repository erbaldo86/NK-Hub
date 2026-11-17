#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Facciata pure-stdlib ACS FastGuard 1.0.0-Generation (PreInvocation / PostInvocation)."""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
_SCRIPT_PARENT = os.path.dirname(_SCRIPT_DIR)
_PROD_SCRIPTS = os.path.join(os.path.dirname(_SCRIPT_PARENT), "scripts") if os.path.basename(_SCRIPT_PARENT) == ".staging" else _SCRIPT_DIR
_WORKSPACE_ROOT = os.path.dirname(_PROD_SCRIPTS)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and os.path.isdir(os.path.join(_SCRIPT_DIR, "_internal", "nk_common")):
    import _internal as _stg_int, _internal.nk_common as _stg_nkc
    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
    _stg_nkc_dir = os.path.join(_SCRIPT_DIR, "_internal", "nk_common")
    if isinstance(_stg_nkc.__path__, list):
        if _stg_nkc_dir in _stg_nkc.__path__:
            _stg_nkc.__path__.remove(_stg_nkc_dir)
        _stg_nkc.__path__.insert(0, _stg_nkc_dir)
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
init_nk_facade(__file__, pkg="nk_acs_fastguard")
importlib.import_module("_internal.nk_acs_fastguard.constants").register_facade_module(__name__)

_CLI_FLAGS = ("--conversation-id", "--event", "--help", "--native-contract", "--project-root", "--transcript")
_C = "_internal.nk_acs_fastguard.constants"
_S = "_internal.nk_acs_fastguard.state_rmw"
_M = "_internal.nk_acs_fastguard.compaction"
_E = "_internal.nk_acs_fastguard.evaluator"
_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "_ACS_PARSED_JSON_CACHE": (_C, "_ACS_PARSED_JSON_CACHE"), "_CHUNK_SIZE": (_C, "_CHUNK_SIZE"),
    "_CONV_ID_CHARS": (_C, "_CONV_ID_CHARS"), "_CTYPES_MOD": (_C, "_CTYPES_MOD"),
    "_DEFAULT_EPOCH_BASELINE_TOKENS": (_C, "_DEFAULT_EPOCH_BASELINE_TOKENS"), "_DEFAULT_FALLBACK_STEPS": (_C, "_DEFAULT_FALLBACK_STEPS"),
    "_ERROR_ACCESS_DENIED": (_C, "_ERROR_ACCESS_DENIED"), "_FILE_ATTRIBUTE_REPARSE_POINT": (_C, "_FILE_ATTRIBUTE_REPARSE_POINT"),
    "_FILE_TYPE_PIPE": (_C, "_FILE_TYPE_PIPE"), "_INVALID_FILE_ATTRIBUTES": (_C, "_INVALID_FILE_ATTRIBUTES"),
    "_K32_CACHE": (_C, "_K32_CACHE"), "_MAX_BACKSCAN_BYTES": (_C, "_MAX_BACKSCAN_BYTES"),
    "_RETRY_WINERRORS": (_C, "_RETRY_WINERRORS"), "_SMALL_FILE_THRESHOLD": (_C, "_SMALL_FILE_THRESHOLD"),
    "_SPOOF_ROLES": (_C, "_SPOOF_ROLES"), "_SPOOF_SOURCES": (_C, "_SPOOF_SOURCES"), "_SPOOF_TYPES": (_C, "_SPOOF_TYPES"),
    "_SUBPROCESS_DETACHED": (_C, "_SUBPROCESS_DETACHED"), "_SYNCHRONIZE": (_C, "_SYNCHRONIZE"),
    "_WAL_ACTIVE_AGE_SEC": (_C, "_WAL_ACTIVE_AGE_SEC"), "_Z1_STEPS": (_C, "_Z1_STEPS"), "_Z1_TOKENS": (_C, "_Z1_TOKENS"),
    "_Z2_COOLDOWN_SEC": (_C, "_Z2_COOLDOWN_SEC"), "_Z2_STEPS": (_C, "_Z2_STEPS"), "_Z2_TOKENS": (_C, "_Z2_TOKENS"),
    "_Z3_STEPS": (_C, "_Z3_STEPS"), "_Z3_TOKENS": (_C, "_Z3_TOKENS"), "_get_k32": (_C, "_get_k32"),
    "_is_reparse_or_symlink": (_C, "_is_reparse_or_symlink"), "_is_safe_dir": (_C, "_is_safe_dir"), "_is_safe_file": (_C, "_is_safe_file"),
    "_load_acs_thresholds": (_C, "_load_acs_thresholds"), "_read_stdin_safe": (_C, "_read_stdin_safe"),
    "_reconfigure_streams": (_C, "_reconfigure_streams"), "_stat_safe_file": (_C, "_stat_safe_file"),
    "_warn_stderr": (_C, "_warn_stderr"), "_win32_stdin_ready": (_C, "_win32_stdin_ready"),
    "_acquire_fastguard_mutex": (_S, "_acquire_fastguard_mutex"), "_candidate_roots": (_S, "_candidate_roots"),
    "_default_state": (_S, "_default_state"), "_get_hooks_temp_dir": (_S, "_get_hooks_temp_dir"),
    "_is_valid_conv_id": (_S, "_is_valid_conv_id"), "_load_state": (_S, "_load_state"),
    "_load_state_with_exists": (_S, "_load_state_with_exists"), "_persist_state_or_warn": (_S, "_persist_state_or_warn"),
    "_release_fastguard_mutex": (_S, "_release_fastguard_mutex"), "_reset_state_on_compaction": (_S, "_reset_state_on_compaction"),
    "_resolve_conv_id": (_S, "_resolve_conv_id"), "_resolve_eff_root": (_S, "_resolve_eff_root"),
    "_resolve_explicit_conv_id": (_S, "_resolve_explicit_conv_id"), "_resolve_transcript_path": (_S, "_resolve_transcript_path"),
    "_save_state_atomic": (_S, "_save_state_atomic"), "_advance_cursor": (_M, "_advance_cursor"),
    "_cold_backscan_64kb": (_M, "_cold_backscan_64kb"), "_extract_tokens": (_M, "_extract_tokens"),
    "_extract_tokens_from_mapping": (_M, "_extract_tokens_from_mapping"), "_is_subagent_transcript": (_M, "_is_subagent_transcript"),
    "_is_verified_compaction": (_M, "_is_verified_compaction"), "_parse_json_bytes": (_M, "_parse_json_bytes"),
    "_safe_int_val": (_M, "_safe_int_val"), "_valid_int_tok": (_M, "_valid_int_tok"),
    "_check_l0_gate_one_shot": (_E, "_check_l0_gate_one_shot"), "_format_hook_output": (_E, "_format_hook_output"),
    "_has_active_wal": (_E, "_has_active_wal"), "_is_batch_mutex_busy": (_E, "_is_batch_mutex_busy"),
    "_is_l0_exempt_fast": (_E, "_is_l0_exempt_fast"), "_maybe_spawn_z2": (_E, "_maybe_spawn_z2"),
    "_parse_fastguard_args": (_E, "_parse_fastguard_args"), "_read_anchor_meta": (_E, "_read_anchor_meta"),
    "_strip_xml_wrapper_fast": (_E, "_strip_xml_wrapper_fast"),
}


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def __getattr__(name: str) -> Any:
    spec = _LAZY_EXPORT_MAP.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(spec[0]), spec[1])


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point rapido della guardia ACS PreInvocation e PostInvocation."""
    return importlib.import_module(_E).main(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
