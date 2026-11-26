"""Rilevazione indicatori shell, FP search mask e autorizzazione script (re-export helper)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
_GOV_ENV_VAR_PAT = (
    r"(?:NK_ALLOW_GOVERNANCE_OVERRIDE|NK_GOVERNANCE_[A-Z0-9_]*|"
    r"NK_TENSOR_[A-Z0-9_]*|NK_COMMIT_TRAIN_[A-Z0-9_]*|NK_HOLDOUT_DIR|(?:NK_)?PROGET_ROOT|"
    r"NK_HOOKS_TEMP_DIR|ANTIGRAVITY_CONVERSATION_ID|NK_CONVERSATION_ID|"
    r"NK_LANE_ID|NK_LANE_SECRET)"
)
_GOV_ENV_TAMPER_RE = re.compile(
    rf"(?:"
    rf"(?:\$\{{?env:|(?:\bset|\bexport)\s+|(?:^|[\s;|&(])){_GOV_ENV_VAR_PAT}\}}?\s*="
    rf"|(?:Set|New|Clear|Remove)-Item\b[^\n;|&]*\bEnv:[\\/]?{_GOV_ENV_VAR_PAT}\b"
    rf"|\[(?:System\.)?Environment\]::SetEnvironmentVariable\s*\([^\n)]*{_GOV_ENV_VAR_PAT}"
    rf"|os\.environ\s*\[[^\n\]]*{_GOV_ENV_VAR_PAT}[^\n\]]*\]\s*="
    rf"|(?:del\s+os\.environ\s*\[[^\n\]]*{_GOV_ENV_VAR_PAT})"
    rf"|os\.environ\.(?:update|setdefault|pop)\s*\([^\n]*{_GOV_ENV_VAR_PAT}"
    rf"|os\.(?:putenv|unsetenv)\s*\([^\n]*{_GOV_ENV_VAR_PAT}"
    rf")",
    re.IGNORECASE,
)


def _segment_has_write_indicator(raw_cmd: str, seg: str) -> bool:
    """Valuta gli indicatori di scrittura su un singolo segmento applicando FP-mask."""
    cand_prompt = _mask_balanced_prompt_payloads(
        raw_cmd, _redact_safe_si_literals(raw_cmd, seg)
    )
    seg_clean = _strip_readonly_search_patterns(cand_prompt)
    cand_low = seg_clean.replace("\\", "/").lower()
    if any(ind in cand_low for ind in _CMD_WRITE_INDICATORS):
        return True
    if _DYN_IMPORT_REFLECT_RE.search(seg_clean):
        return True
    if _ARCHIVE_EXTRACT_RE.search(seg_clean):
        return True
    if _CMD_WORD_WRITE_RE.search(cand_low):
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


def _is_allowed_script_parent(raw_script_tok: str, project_root: Path) -> bool:
    """Verifica che il token script risieda sotto scripts/ di produzione (blocco .staging/scripts SEC-F3)."""
    if not raw_script_tok or "scratch/" in raw_script_tok.lower():
        return False
    eff_root = _resolve_effective_hub_root(project_root)
    hub_canon = _canonical_path(_HUB_ROOT)
    cand = _resolve_target_path(raw_script_tok, eff_root)
    allowed_roots = (
        eff_root / "scripts",
        hub_canon / "scripts",
    )
    return any(cand.parent == _canonical_path(ar) for ar in allowed_roots)


def _has_inline_governance_env_tampering(cmd_str: str) -> bool:
    """Blocca tentativi inline di manipolare NK_ALLOW_GOVERNANCE_OVERRIDE o KEY_PATH."""
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments

    if not cmd_str:
        return False
    for cand in (
        cmd_str,
        _deobfuscate_ps_backticks(cmd_str),
        *_unwrap_shell_subcommands(cmd_str),
    ):
        for seg in _split_shell_segments(cand) or [cand]:
            seg_clean = _strip_readonly_search_patterns(
                _mask_balanced_prompt_payloads(cmd_str, seg)
            )
            if _GOV_ENV_TAMPER_RE.search(seg_clean):
                return True
    return False


def _extract_cli_flag_value(
    tokens: List[Tuple[str, str, bool]], flag_name: str
) -> str:
    """Estrae il valore di un flag CLI (--flag val o --flag=val) dai token shell."""
    target_low = flag_name.lower()
    prefix = target_low + "="
    for idx, (_, unq, _) in enumerate(tokens):
        low = unq.lower()
        if low.startswith(prefix):
            return unq.split("=", 1)[1].strip()
        if low == target_low and (idx + 1) < len(tokens):
            return tokens[idx + 1][1].strip()
    return ""


def _resolve_override_staging_sha(
    tokens: List[Tuple[str, str, bool]], project_root: Path
) -> str:
    """Calcola lo SHA-256 dello staging/lane bersaglio per verifica token governance v2 (SEC-F4)."""
    from _internal.nk_common.lane_paths import resolve_staging_dir
    from _internal.nk_common.staging_manifest import compute_staging_manifest_sha256

    raw_root = _extract_cli_flag_value(tokens, "--repo-root") or _extract_cli_flag_value(tokens, "--root")
    eff_root = (
        _canonical_path(_resolve_target_path(raw_root, project_root))
        if raw_root
        else _resolve_effective_hub_root(project_root)
    )
    raw_lane = _extract_cli_flag_value(tokens, "--lane-id") or None
    raw_stg = _extract_cli_flag_value(tokens, "--staging-dir") or None
    if raw_lane is not None and raw_stg == ".staging":
        raw_stg = None
    eff_stg, norm_lane = resolve_staging_dir(eff_root, lane_id=raw_lane, staging_dir=raw_stg)
    excl_lanes = norm_lane is None and eff_stg.name == ".staging"
    return compute_staging_manifest_sha256(eff_stg, reject_symlinks=True, exclude_lanes=excl_lanes)


def _is_authorized_governance_override_cmd(
    cmd_str: str, project_root: Path = _WORKSPACE_ROOT
) -> bool:
    """Autorizza --allow-governance-override solo su win32_2pc_engine con HMAC valido."""
    from _internal.nk_hook_gate.shell_parser import _tokenize_shell_tokens

    if os.environ.get("NK_ALLOW_GOVERNANCE_OVERRIDE", "").strip() != "1":
        return False
    if _has_inline_governance_env_tampering(cmd_str):
        return False
    norm = cmd_str.replace("\\", "/").strip()
    if "`" in norm or any(sep in norm for sep in (";", "|", "&", "\n", "\r")):
        return False
    if not _AUTH_SCRIPT_RE.match(norm):
        return False
    m_tok = _AUTH_SCRIPT_TOKEN_RE.search(norm)
    if not m_tok:
        return False
    raw_script_tok = _strip_wrapping_quotes(m_tok.group(0)).strip()
    if os.path.basename(raw_script_tok).lower() != "win32_2pc_engine.py":
        return False
    if not _is_allowed_script_parent(raw_script_tok, project_root):
        return False
    tokens = _tokenize_shell_tokens(cmd_str)
    reason = _extract_cli_flag_value(tokens, "--override-reason")
    token = _extract_cli_flag_value(tokens, "--governance-token") or os.environ.get(
        "NK_GOVERNANCE_TOKEN", ""
    ).strip()
    if len(reason.strip()) < 8 or not token:
        return False
    try:
        from _internal.win32_2pc_engine.governance_auth import verify_governance_token

        stg_sha = _resolve_override_staging_sha(tokens, project_root)
        verify_governance_token(token, reason, staging_manifest_sha256=stg_sha)
        return True
    except (ImportError, RuntimeError, ValueError, OSError):
        return False


def _check_governance_override_denial(
    cmd_str: str, cmd_deobf: str, project_root: Path
) -> Optional[Dict[str, Any]]:
    """Valida in fail-closed flag --allow-governance-override e manipolazioni env inline."""
    if _has_inline_governance_env_tampering(cmd_str):
        return {
            "decision": "deny",
            "reason_code": "UNAUTHORIZED_GOVERNANCE_OVERRIDE",
            "reason": "Inline governance environment tampering is forbidden ([RULE-00]).",
        }
    cmd_low = cmd_deobf.replace("\\", "/").lower()
    if "--allow-governance-override" not in cmd_low:
        return None
    if _is_authorized_governance_override_cmd(cmd_str, project_root):
        return None
    return {
        "decision": "deny",
        "reason_code": "UNAUTHORIZED_GOVERNANCE_OVERRIDE",
        "reason": (
            "Flag --allow-governance-override requires NK_ALLOW_GOVERNANCE_OVERRIDE=1, "
            "--override-reason, and valid HMAC --governance-token ([RULE-00] / EXAM-06)."
        ),
    }


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
        and not _is_authorized_governance_override_cmd(cmd_str, project_root)
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
    return _is_allowed_script_parent(raw_script_tok, project_root)
