#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generatore della capsula di handoff e compilatore Template 11 e Template 12 per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/nk_session_handoff.py.
@domain_id: DOM-05
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS_DIR = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (str(_PROD_SCRIPTS_DIR), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS_DIR and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="nk_session_handoff")

from _internal.nk_session_handoff.constants import resolve_session_tracking_dir  # noqa: E402
from _internal.nk_session_handoff.context_view import generate_active_context_view  # noqa: E402
from _internal.nk_session_handoff.handoff_engine import record_fsm_checkpoint, resume_from_anchor  # noqa: E402
from _internal.nk_session_handoff.session_state import select_auto_checkpoint_template  # noqa: E402
from _internal.nk_session_handoff.templates_compiler import (  # noqa: E402
    compile_template_11_prompt,
    compile_template_12_state_handoff,
    persist_intent_brief,
)

_C = "_internal.nk_session_handoff.constants"
_SS = "_internal.nk_session_handoff.session_state"
_TC = "_internal.nk_session_handoff.transcript_cursor"
_TM = "_internal.nk_session_handoff.templates_compiler"
_HE = "_internal.nk_session_handoff.handoff_engine"
_CV = "_internal.nk_session_handoff.context_view"

_LAZY_EXPORT_MAP: Dict[str, tuple[str, str]] = {
    "HANDOFF_SCHEMA_VERSION": (_C, "HANDOFF_SCHEMA_VERSION"),
    "HANDOFF_VERSION": (_C, "HANDOFF_VERSION"),
    "VERSION": (_C, "VERSION"),
    "DEFAULT_MILESTONE_ID": (_C, "DEFAULT_MILESTONE_ID"),
    "_workspace_root": (_C, "_workspace_root"),
    "_FILE_HASH_MEMO": (_C, "_FILE_HASH_MEMO"),
    "_BASELINE_MEMO": (_C, "_BASELINE_MEMO"),
    "_TRANSCRIPT_CURSOR_CACHE": (_C, "_TRANSCRIPT_CURSOR_CACHE"),
    "_dynamic_code_fence": (_C, "_dynamic_code_fence"),
    "_resolve_git_executable": (_C, "_resolve_git_executable"),
    "_discover_default_transcript": (_C, "_discover_default_transcript"),
    "_read_baseline_data": (_SS, "_read_baseline_data"),
    "_read_baseline_tests_count": (_SS, "_read_baseline_tests_count"),
    "_read_baseline_pass_rate": (_SS, "_read_baseline_pass_rate"),
    "_state_memo_cache_path": (_SS, "_state_memo_cache_path"),
    "_prune_handoff_memo_cache": (_SS, "_prune_handoff_memo_cache"),
    "_compute_workspace_state_sha256": (_SS, "_compute_workspace_state_sha256"),
    "_sanitize_ste100_inline": (_SS, "_sanitize_ste100_inline"),
    "_hash_file_cached": (_SS, "_hash_file_cached"),
    "_compute_staging_state_sha256": (_SS, "_compute_staging_state_sha256"),
    "_atomic_commit_bytes": (_SS, "_atomic_commit_bytes"),
    "_parse_optional_turn": (_SS, "_parse_optional_turn"),
    "_has_dirty_staging_inprocess": (_SS, "_has_dirty_staging_inprocess"),
    "_check_git_dirty_fast": (_SS, "_check_git_dirty_fast"),
    "Win32NamedMutex": (_SS, "Win32NamedMutex"),
    "Win32LockTimeoutError": ("_internal.nk_session_handoff.cli", "Win32LockTimeoutError"),
    "Win32LockError": ("_internal.nk_session_handoff.cli", "Win32LockError"),
    "_format_safe_capsule_lines": (_TC, "_format_safe_capsule_lines"),
    "_coerce_non_bool_int": (_TC, "_coerce_non_bool_int"),
    "_extract_actual_tokens_from_record": (_TC, "_extract_actual_tokens_from_record"),
    "_is_compaction_checkpoint_record": (_TC, "_is_compaction_checkpoint_record"),
    "_eval_transcript_line": (_TC, "_eval_transcript_line"),
    "_inspect_transcript_fast": (_TC, "_inspect_transcript_fast"),
    "_read_transcript_summary_fast": (_TC, "_read_transcript_summary_fast"),
    "_collect_staging_relative_files": (_CV, "_collect_staging_relative_files"),
    "_read_latest_handoff_state": (_CV, "_read_latest_handoff_state"),
    "_format_handoff_list_field": (_CV, "_format_handoff_list_field"),
    "_build_active_context_delta_lines": (_CV, "_build_active_context_delta_lines"),
    "subprocess": (_SS, "subprocess"),
    "locate_transcript": ("_internal.nk_session_handoff.cli", "locate_transcript"),
    "lint_prompt_text": ("_internal.nk_session_handoff.cli", "lint_prompt_text"),
    "main": ("_internal.nk_session_handoff.cli", "main"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli del pacchetto _internal/nk_session_handoff."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is not None:
        mod = importlib.import_module(target[0])
        val = getattr(mod, target[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI delegato a _internal.nk_session_handoff.cli."""
    return importlib.import_module("_internal.nk_session_handoff.cli").main(argv)


if __name__ == "__main__":
    sys.exit(main())
