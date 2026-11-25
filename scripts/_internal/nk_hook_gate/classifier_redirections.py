"""Classificatori per target di redirezione, B1 non-redirection e payload python -c."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import NK_LOCK_FILENAMES
from _internal.nk_hook_gate.constants import (
    _PROTECTED_FILE_EXTS,
    _PROTECTED_PROJECT_SEGMENTS,
    _PROTECTED_ROOT_FILENAMES,
    _WORKSPACE_ROOT,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _deny_online_readonly,
    _has_ancestor_reparse_escape,
    _has_ntfs_ads_stream,
    _is_nk_proget_locale_target,
    _is_nk_proget_online_target,
    _is_safe_redirection_target,
    _is_valid_staging_path,
    _is_whitelisted_outside_staging,
    _resolve_effective_hub_root,
    _resolve_target_path,
)

_CALL_PATH_TOKEN_RE = re.compile(
    r"(?:\b(?:open|fileio|streamwriter|writealltext|writeallbytes|appendalltext|"
    r"copyfile|copyfileobj|copy2|copytree|copy|move|rmtree|unpack_archive|extractall|"
    r"unlink|remove|rmdir|makedirs|mkdir|rename|replace|connect|join)|"
    r"\b(?:pure)?(?:posix|windows)?path)\s*\(",
    re.IGNORECASE,
)
_QUOTED_NOSPACE_LITERAL_RE = re.compile(r"""(['"])([^'"\n\r]{1,300})\1""")
_ASSIGNED_LITERAL_RE = re.compile(r"""=\s*(['"])([^'"\n\r]{1,300})\1""")
_VALUE_NEXT_FLAGS = frozenset(
    ("-value", "--value", "--content", "--message", "--reason", "--prompt", "--prompt-text", "-pattern")
)
_PATH_PREFIX_FLAGS = ("-path:", "-path=", "--path=", "-literalpath:", "-literalpath=", "-filepath:", "-filepath=")
_BARE_PROTECTED_NAMES = frozenset(
    ("scripts", ".agents", "tests", "nk_genome", "nk_tracking", "schemas", ".wal", "src_app", "src", "app", "core")
)
_LOCK_NAMES_LOW = frozenset(name.lower() for name in NK_LOCK_FILENAMES)


def _looks_like_write_path_candidate(tok: str) -> bool:
    """Determina se un token rappresenta un path o nome file rilevante per controllo B1."""
    cleaned = _strip_wrapping_quotes(tok).strip()
    if not cleaned or cleaned in (
        "__staged_safe__",
        "__temp_safe__",
        "__safe_si__",
        "__safe_prompt__",
        "__safe_search_pat__",
    ):
        return False
    norm = cleaned.replace("\\", "/")
    low = norm.lower()
    if low.startswith(("http://", "https://", "[", "system.")) or "::" in low:
        return False
    if "/" in norm:
        return True
    base = low.rstrip("/")
    if base in _PROTECTED_ROOT_FILENAMES or base in _BARE_PROTECTED_NAMES:
        return True
    _, ext = os.path.splitext(base)
    return ext in _PROTECTED_FILE_EXTS


def _extract_candidate_write_targets(cmd_str: str) -> List[str]:
    """Estrae i token candidati di path dai segmenti mutanti isolando i payload python -c."""
    from _internal.nk_hook_gate.ast_inline_guard import extract_python_inline_c_payloads
    from _internal.nk_hook_gate.shell_parser import (
        _deobfuscate_ps_backticks,
        _extract_archive_targets_segment,
        _extract_balanced_parens,
        _extract_output_flag_targets_segment,
        _extract_redirection_targets_single,
        _split_shell_segments,
        _split_top_level_args,
        _tokenize_shell_tokens,
        _unwrap_shell_subcommands,
    )
    from _internal.nk_hook_gate.shell_write_detector import _segment_has_write_indicator

    out: List[str] = []
    seen: set[str] = set()

    def _add(val: str) -> None:
        v = _strip_wrapping_quotes(val).strip()
        if v and v not in seen and _looks_like_write_path_candidate(v):
            seen.add(v)
            out.append(v)

    for raw_sub in (cmd_str, _deobfuscate_ps_backticks(cmd_str), *_unwrap_shell_subcommands(cmd_str)):
        for seg in (_split_shell_segments(raw_sub) or [raw_sub]):
            has_seg_write = (
                _segment_has_write_indicator(cmd_str, seg)
                or bool(_extract_redirection_targets_single(seg))
                or bool(_extract_output_flag_targets_segment(seg))
                or bool(_extract_archive_targets_segment(seg))
            )
            if not has_seg_write:
                continue

            tokens = _tokenize_shell_tokens(seg)
            c_payloads, skip_c_indices = (
                extract_python_inline_c_payloads(tokens) if tokens else ([], set())
            )

            if not c_payloads:
                for m_call in _CALL_PATH_TOKEN_RE.finditer(seg):
                    bal = _extract_balanced_parens(seg, m_call.end() - 1)
                    if bal is None:
                        continue
                    inner = bal[0]
                    for arg in _split_top_level_args(inner):
                        rhs = arg.split("=", 1)[1].strip() if "=" in arg else arg
                        _add(rhs)
                    for m_lit in _QUOTED_NOSPACE_LITERAL_RE.finditer(inner):
                        _add(m_lit.group(2))

                for m_ass in _ASSIGNED_LITERAL_RE.finditer(seg):
                    _add(m_ass.group(2))

            if tokens:
                skip_next = False
                for idx_t, (_, unq_t, was_q) in enumerate(tokens):
                    if idx_t in skip_c_indices:
                        skip_next = False
                        continue
                    if idx_t == 0 and not unq_t.startswith("-") and "/" not in unq_t and "\\" not in unq_t:
                        continue
                    if skip_next:
                        skip_next = False
                        continue
                    low_t = unq_t.lower()
                    if low_t in _VALUE_NEXT_FLAGS:
                        skip_next = True
                        continue
                    matched_pref = False
                    for pref in _PATH_PREFIX_FLAGS:
                        if low_t.startswith(pref):
                            _add(unq_t[len(pref) :])
                            matched_pref = True
                            break
                    if matched_pref:
                        continue
                    if unq_t.startswith("-") and not was_q:
                        continue
                    _add(unq_t)
    return out


def _is_protected_redir_path(cand: Path, cand_parts_low: List[str]) -> bool:
    """Verifica se una redirezione colpisce directory protette o percorsi NK Proget/Locale/."""
    return _is_nk_proget_locale_target(cand) or any(
        p in ("nk_external_projects", *_PROTECTED_PROJECT_SEGMENTS)
        for p in cand_parts_low
    )


def _classify_gov_redir_artifact(cand: Path, cand_parts_low: List[str], cand_name_low: str) -> Optional[Dict[str, Any]]:
    """Blocca redirezioni shell dirette verso file lock, tensor_sessions, baseline o checkpoint."""
    if cand_name_low in _LOCK_NAMES_LOW:
        return {"decision": "deny", "reason": f"Direct write to {cand.name} outside .staging/ is forbidden ([RULE-ORACLE-LOCK])."}
    if "nk_tracking" in cand_parts_low and ("tensor_sessions" in cand_parts_low or cand_name_low == "active.json"):
        return {"decision": "deny", "reason": "Direct shell redirection to nk_tracking/tensor_sessions/ or ACTIVE.json outside .staging/ is forbidden."}
    if cand_name_low == "quality_baseline.json":
        return {"decision": "deny", "reason": "Direct shell write to quality_baseline.json outside .staging/ is forbidden."}
    if cand_name_low.startswith("checkpoint_") and cand_name_low.endswith(".json"):
        return {"decision": "deny", "reason": "Direct shell redirection to checkpoint_*.json outside .staging/ is forbidden."}
    return None


def _classify_redirection_target_violation(
    redir_target: str, project_root: Path
) -> Optional[Dict[str, Any]]:
    """Blocca redirezioni o target di scrittura diretti verso file o cartelle protette fuori da .staging/."""
    if redir_target == "__empty_redirect__":
        return {
            "decision": "deny",
            "reason": "Malformed or empty shell redirection target is forbidden.",
        }
    if _has_ntfs_ads_stream(redir_target):
        return {
            "decision": "deny",
            "reason": "NTFS Alternate Data Streams (:) are forbidden in redirection targets.",
        }
    tc_mod = sys.modules.get("_internal.nk_hook_gate.target_classifier")
    reparse_fn = (
        getattr(tc_mod, "_has_ancestor_reparse_escape", _has_ancestor_reparse_escape)
        if tc_mod is not None
        else _has_ancestor_reparse_escape
    )
    if reparse_fn(redir_target, project_root):
        return {
            "decision": "deny",
            "reason": "Symlink or reparse point escape on redirection target is forbidden (anti-TOCTOU).",
        }
    cand = _resolve_target_path(redir_target, project_root)
    if _is_nk_proget_online_target(cand):
        return _deny_online_readonly()
    if _is_valid_staging_path(cand, project_root):
        return None
    cand_parts_low = [p.lower().rstrip(". ") for p in cand.parts]
    cand_name_low = cand.name.lower().split(":", 1)[0].rstrip(". ")
    if cand_name_low == "patch_notes.md":
        return {
            "decision": "deny",
            "reason": "Destructive shell write to PATCH_NOTES.md is forbidden; use prepend-only edit_file.",
        }
    if gov_res := _classify_gov_redir_artifact(cand, cand_parts_low, cand_name_low):
        return gov_res
    if _is_whitelisted_outside_staging(cand, project_root):
        return None
    if _is_protected_redir_path(cand, cand_parts_low):
        return {
            "decision": "deny",
            "reason": "Shell redirection to protected directories outside .staging/ is blocked; use win32_2pc_engine.py.",
        }
    eff_root = _resolve_effective_hub_root(project_root)
    proj_canon = _canonical_path(project_root)
    ws_root = _canonical_path(_WORKSPACE_ROOT)
    if any(cand == br or br in cand.parents for br in (eff_root, proj_canon, ws_root)):
        return {
            "decision": "deny",
            "reason": "Default-deny: shell redirection inside project root outside .staging/ is forbidden ([RULE-00]).",
        }
    return None


def _classify_non_redirection_write_targets(
    cmd_str: str, project_root: Path
) -> Optional[Dict[str, Any]]:
    """Valida tutti i target di scrittura non-redirezione contro staging e whitelist (B1)."""
    for cand_tok in _extract_candidate_write_targets(cmd_str):
        if _is_safe_redirection_target(cand_tok, project_root):
            continue
        viol = _classify_redirection_target_violation(cand_tok, project_root)
        if viol is not None:
            return viol
    return None


def _check_inline_python_ast_blocks(
    cmd_str: str, cmd_deobf: str, project_root: Path
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Verifica con ast.parse gli inline python -c; restituisce (denial, saw_python_c)."""
    from _internal.nk_hook_gate.ast_inline_guard import (
        extract_python_inline_c_payloads,
        inspect_python_source_mutations,
    )
    from _internal.nk_hook_gate.shell_parser import (
        _split_shell_segments,
        _tokenize_shell_tokens,
        _unwrap_shell_subcommands,
    )

    saw_python_c = False
    for raw_sub in (cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str)):
        for seg in (_split_shell_segments(raw_sub) or [raw_sub]):
            tokens = _tokenize_shell_tokens(seg)
            if not tokens:
                continue
            payloads, _ = extract_python_inline_c_payloads(tokens)
            if not payloads:
                continue
            saw_python_c = True
            for code_str in payloads:
                denial = inspect_python_source_mutations(code_str, project_root)
                if denial is not None:
                    return denial, True
    return None, saw_python_c
