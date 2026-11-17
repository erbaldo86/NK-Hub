"""Rilevazione indicatori shell, FP search mask e autorizzazione script (re-export helper)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from _internal.nk_hook_gate.constants import (
    _ARCHIVE_EXTRACT_RE,
    _AUTH_SCRIPT_RE,
    _AUTH_SCRIPT_TOK_RE,
    _CMD_WORD_WRITE_RE,
    _CMD_WRITE_INDICATORS,
    _DYN_IMPORT_REFLECT_RE,
    _HUB_ROOT,
    _PS_CALL_WRITE_RE,
    _WORKSPACE_ROOT,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _is_safe_redirection_target,
    _resolve_effective_hub_root,
    _resolve_target_path,
)
from _internal.nk_hook_gate.shell_ast_paths import (
    _arg_targets_protected_outside_staging,
    _find_invoked_script_index,
    _has_unstaged_temp_script_targeting_protected,
    _is_temp_or_scratch_script_token,
)
from _internal.nk_hook_gate.shell_parser import (
    _deobfuscate_ps_backticks,
    _extract_archive_targets,
    _extract_output_flag_targets,
    _extract_redirection_targets,
    _unwrap_shell_subcommands,
)
from _internal.nk_hook_gate.shell_redaction import (
    _has_balanced_path_mutation,
    _has_non_readonly_open,
    _mask_balanced_prompt_payloads,
    _redact_safe_si_literals,
    _scan_quotes_clean,
)
from _internal.nk_hook_gate.shell_search_mask import _strip_readonly_search_patterns

_AUTH_SCRIPT_TOKEN_RE = re.compile(_AUTH_SCRIPT_TOK_RE, re.IGNORECASE)


def _segment_has_write_indicator(raw_cmd: str, seg: str) -> bool:
    """Valuta gli indicatori di scrittura su un singolo segmento applicando FP-mask."""
    cand_eval = _redact_safe_si_literals(raw_cmd, seg)
    seg_clean = _strip_readonly_search_patterns(cand_eval)
    cand_low = seg_clean.replace("\\", "/").lower()
    if any(ind in cand_low for ind in _CMD_WRITE_INDICATORS):
        return True
    if _DYN_IMPORT_REFLECT_RE.search(seg_clean):
        return True
    if _ARCHIVE_EXTRACT_RE.search(seg_clean):
        return True
    cand_word_eval = _mask_balanced_prompt_payloads(raw_cmd, seg_clean)
    if _CMD_WORD_WRITE_RE.search(cand_word_eval.replace("\\", "/").lower()):
        return True
    if _PS_CALL_WRITE_RE.search(cand_low):
        return True
    if _has_non_readonly_open(seg_clean):
        return True
    if _has_balanced_path_mutation(seg_clean):
        return True
    return False


def _has_non_redirection_write_indicator(cmd_str: str) -> bool:
    """Verifica indicatori di scrittura escludendo le redirezioni analizzate separatamente."""
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments

    if not cmd_str:
        return False
    for cand_s in (
        cmd_str,
        _deobfuscate_ps_backticks(cmd_str),
        *_unwrap_shell_subcommands(cmd_str),
    ):
        for seg in _split_shell_segments(cand_s) or [cand_s]:
            if _segment_has_write_indicator(cmd_str, seg):
                return True
    return False


def _has_cmd_write_indicator(
    cmd_str: str, project_root: Path = _WORKSPACE_ROOT
) -> bool:
    """Rileva scritture shell consentendo redirezioni verso destinazioni temporanee/staged sicure."""
    if not cmd_str:
        return False
    if _has_non_redirection_write_indicator(cmd_str):
        return True
    if _has_unstaged_temp_script_targeting_protected(cmd_str, project_root):
        return True
    all_targets = (
        _extract_redirection_targets(cmd_str)
        + _extract_output_flag_targets(cmd_str)
        + _extract_archive_targets(cmd_str)
    )
    if not all_targets:
        return False
    return any(not _is_safe_redirection_target(rt, project_root) for rt in all_targets)


def _is_authorized_script_invocation(
    cmd_str: str, project_root: Path = _WORKSPACE_ROOT
) -> bool:
    """Verifica che il comando invochi realmente uno script ancorato a HUB_ROOT senza concatenazioni."""
    norm = cmd_str.replace("\\", "/").strip()
    norm_low = norm.lower()
    if "`" in norm or any(sep in norm_low for sep in (";", "|", "&", "\n", "\r")):
        return False
    if (
        "--allow-governance-override" in norm_low
        and os.environ.get("NK_ALLOW_GOVERNANCE_OVERRIDE", "").strip() != "1"
    ):
        return False
    if _has_cmd_write_indicator(norm, project_root):
        return False
    if not _AUTH_SCRIPT_RE.match(norm):
        return False

    m_tok = _AUTH_SCRIPT_TOKEN_RE.search(norm)
    if not m_tok:
        return False
    raw_script_tok = _strip_wrapping_quotes(m_tok.group(0)).strip()
    if not raw_script_tok or "scratch/" in raw_script_tok.lower():
        return False
    eff_root = _resolve_effective_hub_root(project_root)
    hub_canon = _canonical_path(_HUB_ROOT)
    cand = _resolve_target_path(raw_script_tok, eff_root)
    allowed_roots = (
        eff_root / "scripts",
        eff_root / ".staging" / "scripts",
        hub_canon / "scripts",
        hub_canon / ".staging" / "scripts",
    )
    return any(cand.parent == _canonical_path(ar) for ar in allowed_roots)
