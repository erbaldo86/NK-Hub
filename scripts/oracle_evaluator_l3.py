#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Valutatore DOM L3 e Oracolo E2E per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/oracle_evaluator_l3.py.
@domain_id: DOM-04
Gestisce i void tag HTML5 e la chiusura implicita dei tag opzionali ripetuti.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

__nk_domain__: str = "DOM-04"
__nk_role__: str = "facade"
__nk_facade__: str = "oracle_evaluator_l3"

_CLI_FLAGS: Tuple[str, ...] = (
    "--actual",
    "--actual-file",
    "--expected",
    "--expected-file",
    "--html-file",
    "--json",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="oracle_evaluator_l3")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "_scripts_dir": ("_internal.oracle_evaluator_l3.models_and_dom", "_scripts_dir"),
    "_root_dir": ("_internal.oracle_evaluator_l3.models_and_dom", "_root_dir"),
    "HTML5_VOID_TAGS": ("_internal.oracle_evaluator_l3.models_and_dom", "HTML5_VOID_TAGS"),
    "ALLOWED_HTML_EXTENSIONS": ("_internal.oracle_evaluator_l3.models_and_dom", "ALLOWED_HTML_EXTENSIONS"),
    "ALLOWED_EXPECTED_EXTENSIONS": ("_internal.oracle_evaluator_l3.models_and_dom", "ALLOWED_EXPECTED_EXTENSIONS"),
    "_HTML5_CLOSES_OPEN_P": ("_internal.oracle_evaluator_l3.models_and_dom", "_HTML5_CLOSES_OPEN_P"),
    "_NON_HTML_EXT_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_NON_HTML_EXT_RE"),
    "_FENCED_HTML_BLOCK_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_FENCED_HTML_BLOCK_RE"),
    "_MD_HEADING_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_MD_HEADING_RE"),
    "_MD_PAIRED_HTML_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_MD_PAIRED_HTML_RE"),
    "_MD_ID_TOKEN_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_MD_ID_TOKEN_RE"),
    "_MD_TAG_TOKEN_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_MD_TAG_TOKEN_RE"),
    "_MD_QUOTED_TEXT_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_MD_QUOTED_TEXT_RE"),
    "_MD_BULLET_PREFIX_RE": ("_internal.oracle_evaluator_l3.models_and_dom", "_MD_BULLET_PREFIX_RE"),
    "DOMNode": ("_internal.oracle_evaluator_l3.models_and_dom", "DOMNode"),
    "DOMDeltaItem": ("_internal.oracle_evaluator_l3.models_and_dom", "DOMDeltaItem"),
    "DOMEvaluationReport": ("_internal.oracle_evaluator_l3.models_and_dom", "DOMEvaluationReport"),
    "_DOMBuilderParser": ("_internal.oracle_evaluator_l3.models_and_dom", "_DOMBuilderParser"),
    "_collect_dom_index": ("_internal.oracle_evaluator_l3.models_and_dom", "_collect_dom_index"),
    "_extract_candidate_file_str": ("_internal.oracle_evaluator_l3.gate_validators", "_extract_candidate_file_str"),
    "_has_traversal_segment": ("_internal.oracle_evaluator_l3.gate_validators", "_has_traversal_segment"),
    "_looks_like_disallowed_file_reference": ("_internal.oracle_evaluator_l3.gate_validators", "_looks_like_disallowed_file_reference"),
    "_expected_kind_from_path": ("_internal.oracle_evaluator_l3.gate_validators", "_expected_kind_from_path"),
    "_read_validated_html_file": ("_internal.oracle_evaluator_l3.gate_validators", "_read_validated_html_file"),
    "_read_validated_expected_file": ("_internal.oracle_evaluator_l3.gate_validators", "_read_validated_expected_file"),
    "resolve_html_source": ("_internal.oracle_evaluator_l3.gate_validators", "resolve_html_source"),
    "resolve_expected_source": ("_internal.oracle_evaluator_l3.gate_validators", "resolve_expected_source"),
    "_extract_markdown_expectations": ("_internal.oracle_evaluator_l3.gate_validators", "_extract_markdown_expectations"),
    "DOMOracleEvaluator": ("_internal.oracle_evaluator_l3.evaluator_core", "DOMOracleEvaluator"),
    "_build_cli_parser": ("_internal.oracle_evaluator_l3.cli", "_build_cli_parser"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.oracle_evaluator_l3."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="oracle_evaluator_l3")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main() -> int:
    """Punto di ingresso CLI per il valutatore DOM L3."""
    init_nk_facade(__file__, pkg="oracle_evaluator_l3")
    return importlib.import_module("_internal.oracle_evaluator_l3.cli").main()


if __name__ == "__main__":
    sys.exit(main())
