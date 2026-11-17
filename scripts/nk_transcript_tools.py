#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strumenti forensi per transcript, FSM evidenze, STE100 SSOT e prompt linter di NK Hub Generation 1.0.0-Generation.
Modulo: scripts/nk_transcript_tools.py.
@domain_id: DOM-04
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS_DIR = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (str(_PROD_SCRIPTS_DIR), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS_DIR and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="nk_transcript_tools")

from _internal.nk_transcript_tools.constants import (  # noqa: E402
    classify_transcript_record, clean_tool_path, clean_tool_str, extract_command_exit_code,
    extract_tool_args, extract_tool_name, is_read_file_output, is_user_turn_record, validate_intent_brief_id,
)
from _internal.nk_transcript_tools.evidence_and_ears import check_evidence  # noqa: E402
from _internal.nk_transcript_tools.locate_and_compliance import (  # noqa: E402
    analyze_compliance, count_transcript_steps, discover_active_main_transcript,
    is_subagent_transcript_file, load_transcript_records, locate_transcript,
)
from _internal.nk_transcript_tools.oracle_and_grounding import (  # noqa: E402
    handle_oracle_lock, handle_report_conflict, verify_report_grounding,
)
from _internal.nk_transcript_tools.prompt_and_ste100 import (  # noqa: E402
    lint_ears_requirements, lint_prompt_text, verify_ste100_compliance,
)

_C = "_internal.nk_transcript_tools.constants"
_LC = "_internal.nk_transcript_tools.locate_and_compliance"
_EV = "_internal.nk_transcript_tools.evidence_and_ears"
_OG = "_internal.nk_transcript_tools.oracle_and_grounding"
_PS = "_internal.nk_transcript_tools.prompt_and_ste100"

_LAZY_EXPORT_MAP: Dict[str, tuple[str, str]] = {
    "DIRECT_TOOLS": (_C, "DIRECT_TOOLS"),
    "_DIRECT_TOOLS": (_C, "_DIRECT_TOOLS"),
    "DELEGATION_TOOLS": (_C, "DELEGATION_TOOLS"),
    "_DELEGATION_TOOLS": (_C, "_DELEGATION_TOOLS"),
    "WRITE_BURST_TOOLS": (_C, "WRITE_BURST_TOOLS"),
    "_WRITE_BURST_TOOLS": (_C, "_WRITE_BURST_TOOLS"),
    "READ_FILE_TOOLS": (_C, "READ_FILE_TOOLS"),
    "_READ_FILE_TOOLS": (_C, "_READ_FILE_TOOLS"),
    "CANONICAL_AP_TABLE": (_C, "CANONICAL_AP_TABLE"),
    "EXIT_CODE_RE": (_C, "EXIT_CODE_RE"),
    "INTENT_BRIEF_ID_RE": (_C, "INTENT_BRIEF_ID_RE"),
    "HALLUCINATED_SCRIPT_DENYLIST": (_C, "HALLUCINATED_SCRIPT_DENYLIST"),
    "_get_runtime_temp_markers": (_C, "_get_runtime_temp_markers"),
    "_strip_claim_code_spans": (_C, "_strip_claim_code_spans"),
    "_extract_call_id": (_C, "_extract_call_id"),
    "_pop_correlated_tool_call": (_C, "_pop_correlated_tool_call"),
    "_has_missing_path_error": (_C, "_has_missing_path_error"),
    "_inspect_record_blind_reads_and_bursts": (_LC, "_inspect_record_blind_reads_and_bursts"),
    "_classify_command_targets": (_EV, "_classify_command_targets"),
    "_hash_target_files": (_OG, "_hash_target_files"),
    "_sha256_eol_matches": (_OG, "_sha256_eol_matches"),
    "_is_explicitly_negated_script_mention": (_OG, "_is_explicitly_negated_script_mention"),
    "_collect_grounding_valid_scripts": (_OG, "_collect_grounding_valid_scripts"),
    "main": ("_internal.nk_transcript_tools.cli", "main"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli del pacchetto _internal/nk_transcript_tools."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is not None:
        mod = importlib.import_module(target[0])
        val = getattr(mod, target[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI delegato a _internal.nk_transcript_tools.cli."""
    return importlib.import_module("_internal.nk_transcript_tools.cli").main(argv)


if __name__ == "__main__":
    sys.exit(main())
