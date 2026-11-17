#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gate runtime leggero HookGateV2 per gli hook del ciclo di vita di NK Hub Generation 1.0.0-Generation.
Modulo: scripts/nk_hook_gate.py.
@domain_id: DOM-01
Usa solo la libreria standard Python con lazy loading per avvio veloce e zero crash cp1252.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict, Optional, Sequence

_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
_PARENT_DIR = os.path.dirname(_SCRIPT_DIR)
_PROD_SCRIPTS_DIR = (
    os.path.join(os.path.dirname(_PARENT_DIR), "scripts")
    if os.path.basename(_PARENT_DIR) == ".staging"
    else _SCRIPT_DIR
)
for _cand_dir in (_PROD_SCRIPTS_DIR, _SCRIPT_DIR):
    if _cand_dir and os.path.isdir(_cand_dir) and _cand_dir not in sys.path:
        sys.path.insert(0, _cand_dir)
_STG_INT_DIR = os.path.join(_SCRIPT_DIR, "_internal")
_STG_NKC_DIR = os.path.join(_STG_INT_DIR, "nk_common")
if _SCRIPT_DIR != _PROD_SCRIPTS_DIR and os.path.isdir(_STG_NKC_DIR):
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    for _pkg_obj, _stg_dir in ((_stg_int, _STG_INT_DIR), (_stg_nkc, _STG_NKC_DIR)):
        _cur_p = list(getattr(_pkg_obj, "__path__", ()))
        _pkg_obj.__path__ = [_stg_dir] + [p for p in _cur_p if os.path.normcase(p) != os.path.normcase(_stg_dir)]

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="nk_hook_gate")

_LAZY_EXPORT_MAP: Dict[str, str] = {
    "dispatch_hook_cli": "_internal.nk_hook_gate.cli_dispatch",
    "HALLUCINATED_SCRIPT_DENYLIST": "_internal.nk_hook_gate.constants",
    "_AUTH_PY_TOK_RE": "_internal.nk_hook_gate.constants",
    "_AUTH_SCRIPT_RE": "_internal.nk_hook_gate.constants",
    "_AUTH_SCRIPT_TOK_RE": "_internal.nk_hook_gate.constants",
    "_CERT_RE": "_internal.nk_hook_gate.constants",
    "_CHAINED_FILE_WRITE_RE": "_internal.nk_hook_gate.constants",
    "_CMD_C_WRAPPER_RE": "_internal.nk_hook_gate.constants",
    "_CMD_WORD_WRITE_RE": "_internal.nk_hook_gate.constants",
    "_CMD_WRITE_INDICATORS": "_internal.nk_hook_gate.constants",
    "_DELEGATION_TOOLS": "_internal.nk_hook_gate.constants",
    "_DESTRUCTIVE_GIT_RE": "_internal.nk_hook_gate.constants",
    "_DYNAMIC_PS_EXEC_RE": "_internal.nk_hook_gate.constants",
    "_ENCODED_CMD_RE": "_internal.nk_hook_gate.constants",
    "_FENCED_CODE_BLOCK_RE": "_internal.nk_hook_gate.constants",
    "_FS_PATH_PREFIX_RE": "_internal.nk_hook_gate.constants",
    "_INLINE_CODE_SPAN_RE": "_internal.nk_hook_gate.constants",
    "_MCP_CHROME_DEVTOOLS_TOOLS": "_internal.nk_hook_gate.constants",
    "_MCP_MUTATING_TOOL_RE": "_internal.nk_hook_gate.constants",
    "_MCP_PATH_KEY_SUBSTRINGS": "_internal.nk_hook_gate.constants",
    "_OPEN_TOKEN_RE": "_internal.nk_hook_gate.constants",
    "_PATH_CTOR_TOKEN_RE": "_internal.nk_hook_gate.constants",
    "_PATH_MUTATION_METHOD_RE": "_internal.nk_hook_gate.constants",
    "_PROD_DIR_PREFIXES": "_internal.nk_hook_gate.constants",
    "_PROMPT_FLAG_SCAN_RE": "_internal.nk_hook_gate.constants",
    "_PROMPT_SHELL_HAZARD_RE": "_internal.nk_hook_gate.constants",
    "_PROTECTED_DIR_CMD_RE": "_internal.nk_hook_gate.constants",
    "_PROTECTED_PROJECT_SEGMENTS": "_internal.nk_hook_gate.constants",
    "_PS_CALL_WRITE_RE": "_internal.nk_hook_gate.constants",
    "_PS_COMMAND_WRAPPER_RE": "_internal.nk_hook_gate.constants",
    "_PY_EXE_TOK_RE": "_internal.nk_hook_gate.constants",
    "_READONLY_OPEN_TAIL_RE": "_internal.nk_hook_gate.constants",
    "_READ_ONLY_TOOLS": "_internal.nk_hook_gate.constants",
    "_REPARSE_ATTR_MASK": "_internal.nk_hook_gate.constants",
    "_RETRY_WINERRORS": "_internal.nk_hook_gate.constants",
    "_SAFE_CONV_ID_RE": "_internal.nk_hook_gate.constants",
    "_SAFE_DIR_COMPONENTS": "_internal.nk_hook_gate.constants",
    "_SAFE_ROOT_FILENAMES": "_internal.nk_hook_gate.constants",
    "_SAFE_SI_CMD_START_RE": "_internal.nk_hook_gate.constants",
    "_SAFE_SI_FORBIDDEN_RE": "_internal.nk_hook_gate.constants",
    "_SAFE_SI_QUOTED_ARG_RE": "_internal.nk_hook_gate.constants",
    "_SCRIPTS_PY_TOK_RE": "_internal.nk_hook_gate.constants",
    "_SHELL_CMD_START_RE": "_internal.nk_hook_gate.constants",
    "_STOP_SPOOF_ROLES": "_internal.nk_hook_gate.constants",
    "_STOP_SPOOF_SOURCES": "_internal.nk_hook_gate.constants",
    "_STOP_SPOOF_TYPES": "_internal.nk_hook_gate.constants",
    "_UNSTAGE_CODE_DIR_CMD_RE": "_internal.nk_hook_gate.constants",
    "_WORKSPACE_ROOT": "_internal.nk_hook_gate.constants",
    "_strip_markdown_code_spans": "_internal.nk_hook_gate.constants",
    "_strip_wrapping_quotes": "_internal.nk_hook_gate.constants",
    "pre_command_gate": "_internal.nk_hook_gate.constants",
    "_extract_last_planner_message": "_internal.nk_hook_gate.integrity_and_fasttrack",
    "_handle_fasttrack": "_internal.nk_hook_gate.integrity_and_fasttrack",
    "_handle_integrity": "_internal.nk_hook_gate.integrity_and_fasttrack",
    "_handle_probe": "_internal.nk_hook_gate.integrity_and_fasttrack",
    "_extract_first_section": "_internal.nk_hook_gate.json_io",
    "_extract_historical_headers": "_internal.nk_hook_gate.json_io",
    "_get_hooks_temp_dir": "_internal.nk_hook_gate.json_io",
    "_is_path_reparse_point": "_internal.nk_hook_gate.json_io",
    "_log_shadow_decision": "_internal.nk_hook_gate.json_io",
    "_read_json_safe": "_internal.nk_hook_gate.json_io",
    "_read_stdin_payload_ex": "_internal.nk_hook_gate.json_io",
    "_resolve_conv_id": "_internal.nk_hook_gate.json_io",
    "_sha256_file": "_internal.nk_hook_gate.json_io",
    "_write_json_atomic_safe": "_internal.nk_hook_gate.json_io",
    "_classify_mcp_tool_call": "_internal.nk_hook_gate.mcp_classifier",
    "_extract_args_dict": "_internal.nk_hook_gate.mcp_classifier",
    "_extract_mcp_candidate_paths": "_internal.nk_hook_gate.mcp_classifier",
    "_canonical_path": "_internal.nk_hook_gate.path_safety",
    "_has_ancestor_reparse_escape": "_internal.nk_hook_gate.path_safety",
    "_has_ntfs_ads_stream": "_internal.nk_hook_gate.path_safety",
    "_is_safe_redirection_target": "_internal.nk_hook_gate.path_safety",
    "_is_valid_staging_path": "_internal.nk_hook_gate.path_safety",
    "_is_whitelisted_outside_staging": "_internal.nk_hook_gate.path_safety",
    "_resolve_effective_hub_root": "_internal.nk_hook_gate.path_safety",
    "_resolve_target_path": "_internal.nk_hook_gate.path_safety",
    "_sanitize_staged_tokens_in_cmd": "_internal.nk_hook_gate.path_safety",
    "_deobfuscate_ps_backticks": "_internal.nk_hook_gate.shell_parser",
    "_extract_balanced_parens": "_internal.nk_hook_gate.shell_parser",
    "_extract_redirection_targets": "_internal.nk_hook_gate.shell_parser",
    "_extract_redirection_targets_single": "_internal.nk_hook_gate.shell_parser",
    "_has_unquoted_ps_backtick_obfuscation": "_internal.nk_hook_gate.shell_parser",
    "_split_top_level_args": "_internal.nk_hook_gate.shell_parser",
    "_unwrap_shell_subcommands": "_internal.nk_hook_gate.shell_parser",
    "_has_balanced_path_mutation": "_internal.nk_hook_gate.shell_write_detector",
    "_has_cmd_write_indicator": "_internal.nk_hook_gate.shell_write_detector",
    "_has_non_readonly_open": "_internal.nk_hook_gate.shell_write_detector",
    "_has_non_redirection_write_indicator": "_internal.nk_hook_gate.shell_write_detector",
    "_is_authorized_script_invocation": "_internal.nk_hook_gate.shell_write_detector",
    "_mask_balanced_prompt_payloads": "_internal.nk_hook_gate.shell_write_detector",
    "_redact_safe_si_literals": "_internal.nk_hook_gate.shell_write_detector",
    "_scan_quotes_clean": "_internal.nk_hook_gate.shell_write_detector",
    "_maybe_spawn_stop_idle_checkpoint": "_internal.nk_hook_gate.stop_evidence",
    "_stop_extract_tokens": "_internal.nk_hook_gate.stop_evidence",
    "_stop_is_batch_mutex_or_wal_busy": "_internal.nk_hook_gate.stop_evidence",
    "_stop_is_verified_compaction": "_internal.nk_hook_gate.stop_evidence",
    "_stop_read_anchor_meta": "_internal.nk_hook_gate.stop_evidence",
    "_stop_read_tokens_and_epoch": "_internal.nk_hook_gate.stop_evidence",
    "_classify_protected_target": "_internal.nk_hook_gate.target_classifier",
    "_classify_redirection_target_violation": "_internal.nk_hook_gate.target_classifier",
    "_classify_non_redirection_write_targets": "_internal.nk_hook_gate.target_classifier",
    "_handle_write_gate": "_internal.nk_hook_gate.write_gate",
    "_IS_WIN": "_internal.nk_hook_gate.core_env",
    "_HUB_ROOT": "_internal.nk_hook_gate.core_env",
    "_is_safe_conv_id": "_internal.nk_hook_gate.core_env",
    "_READ_ONLY_TOOLS_SET": "_internal.nk_hook_gate.core_env",
    "_ARCHIVE_EXTRACT_RE": "_internal.nk_hook_gate.constants",
    "_DYN_IMPORT_REFLECT_RE": "_internal.nk_hook_gate.constants",
    "_verify_oracle_lock_files": "_internal.nk_hook_gate.integrity_and_fasttrack",
    "_strip_readonly_search_patterns": "_internal.nk_hook_gate.shell_write_detector",
    "_extract_output_flag_targets": "_internal.nk_hook_gate.shell_parser",
    "_extract_archive_targets": "_internal.nk_hook_gate.shell_parser",
    "extract_python_inline_c_payloads": "_internal.nk_hook_gate.ast_inline_guard",
    "inspect_python_source_mutations": "_internal.nk_hook_gate.ast_inline_guard",
    "inspect_script_file_ast": "_internal.nk_hook_gate.ast_inline_guard",
}


def __dir__() -> list[str]:
    """Espone i simboli pubblici lazy della facciata HookGateV2."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def __getattr__(name: str) -> Any:
    mod_name = _LAZY_EXPORT_MAP.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod = importlib.import_module(mod_name)
    val = getattr(mod, name)
    globals()[name] = val
    return val


_VALID_SUBCOMMANDS = frozenset(
    ("probe", "session-start", "write-gate", "fasttrack", "integrity", "stop-evidence")
)
_BOOL_FLAGS = {
    "--shadow": "shadow",
    "--enforce-stop": "enforce_stop",
    "--native-contract": "native_contract",
    "--strict-external": "strict_external",
    "--init": "init",
    "--check": "check",
}
_VAL_FLAGS = {
    "--event": "event",
    "--conversation-id": "conversation_id",
    "--project-root": "project_root",
    "--target": "target",
    "--command": "command",
    "--content": "content",
}


def _argparse_fallback_help(argv: Optional[Sequence[str]]) -> Any:
    """Carica argparse solo per -h/--help o errori CLI preservando l'output standard."""
    import argparse

    parser = argparse.ArgumentParser(description="NK Hub Generation Fast Stdlib Hook Gate V2")
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="probe",
        choices=(
            "probe",
            "session-start",
            "write-gate",
            "fasttrack",
            "stop-evidence",
            "integrity",
        ),
    )
    parser.add_argument("--event", type=str, default="Unknown")
    parser.add_argument("--conversation-id", type=str, default=None)
    parser.add_argument("--project-root", type=str, default=None)
    parser.add_argument("--target", type=str, default="")
    parser.add_argument("--command", type=str, default="")
    parser.add_argument("--content", type=str, default="")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--strict-external", action="store_true")
    parser.add_argument("--native-contract", action="store_true")
    parser.add_argument("--shadow", action="store_true")
    parser.add_argument("--enforce-stop", action="store_true")
    return parser.parse_args(argv)


def _parse_hook_cli_args(argv: Optional[Sequence[str]]) -> Any:
    """Analizza gli argomenti CLI senza importare argparse nei percorsi caldi su Python 3.14."""
    from types import SimpleNamespace

    tokens = list(sys.argv[1:] if argv is None else argv)
    if "-h" in tokens or "--help" in tokens:
        return _argparse_fallback_help(tokens)

    parsed = SimpleNamespace(
        subcommand="probe",
        event="Unknown",
        conversation_id=None,
        project_root=None,
        shadow=False,
        enforce_stop=False,
        native_contract=False,
        strict_external=False,
        target="",
        command="",
        content="",
        init=False,
        check=False,
    )
    seen_pos = False
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in _BOOL_FLAGS:
            setattr(parsed, _BOOL_FLAGS[tok], True)
            i += 1
            continue
        key, eq, val = tok.partition("=")
        attr = _VAL_FLAGS.get(key)
        if attr is not None:
            if eq:
                setattr(parsed, attr, val)
                i += 1
            elif i + 1 < n:
                setattr(parsed, attr, tokens[i + 1])
                i += 2
            else:
                return _argparse_fallback_help(tokens)
            continue
        if tok.startswith("-") or seen_pos or tok not in _VALID_SUBCOMMANDS:
            return _argparse_fallback_help(tokens)
        parsed.subcommand = tok
        seen_pos = True
        i += 1
    return parsed


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per il gate degli hook HookGateV2 di NK Hub Generation 1.0.0-Generation."""
    args = _parse_hook_cli_args(argv)

    from _internal.nk_hook_gate.cli_dispatch import dispatch_hook_cli

    return dispatch_hook_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
