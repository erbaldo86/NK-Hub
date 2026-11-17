"""Classificazione principale dei target protetti e dei comandi shell (re-export redirezioni)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from _internal.nk_hook_gate.classifier_redirections import (
    _check_inline_python_ast_blocks,
    _classify_non_redirection_write_targets,
    _classify_redirection_target_violation,
    _extract_candidate_write_targets,
    _looks_like_write_path_candidate,
)
from _internal.nk_hook_gate.constants import (
    _DESTRUCTIVE_GIT_RE,
    _DYNAMIC_PS_EXEC_RE,
    _ENCODED_CMD_RE,
    _FS_PATH_PREFIX_RE,
    _PROTECTED_DIR_CMD_RE,
    _PS_COMMAND_WRAPPER_RE,
    _PYTEST_CLOUD_DRIVE_MARKERS,
    _PYTEST_ISOLATED_SAFE_RUNNERS,
    _PYTEST_TEMP_SAFE_MARKERS,
    _SHELL_CMD_START_RE,
    _WORKSPACE_ROOT,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _has_ancestor_reparse_escape,
    _has_ntfs_ads_stream,
    _is_safe_redirection_target,
    _is_valid_staging_path,
    _is_whitelisted_outside_staging,
    _resolve_effective_hub_root,
    _resolve_target_path,
    _sanitize_staged_tokens_in_cmd,
)

_PYTEST_DIRECT_CMD_RE = re.compile(
    r"(?:^|[;&|(\n\r]\s*|&&\s*|\|\|\s*)(?:[\"']?[^\s\"';|&]*[/\\])?pytest(?:\.exe)?(?=$|\s)"
    r"|(?:^|\s)-m\s+pytest(?=$|\s)",
    re.IGNORECASE,
)
_PLATFORM_CMD_PYTEST_RE = re.compile(
    r"--cmd(?:=|\s+)[\"']?[^\n\"']*?\bpytest(?:\.exe)?(?=$|\s)",
    re.IGNORECASE,
)


def _is_temp_root_path(path: Path) -> bool:
    """Verifica se il percorso risiede sotto TEMP locale o directory pytest-of-*."""
    canon_str = _canonical_path(path).as_posix().lower().rstrip("/") + "/"
    if any(m in canon_str for m in ("/appdata/local/temp/", "/tmp/", "/pytest-of-")):
        return True
    temp_cands = [tempfile.gettempdir()]
    for k in ("TEMP", "TMP", "TMPDIR"):
        if val := os.environ.get(k, "").strip():
            temp_cands.append(val)
    if la := os.environ.get("LOCALAPPDATA", "").strip():
        temp_cands.append(os.path.join(la, "Temp"))
    p_canon = _canonical_path(path)
    for tc in temp_cands:
        t_canon = _canonical_path(tc)
        if p_canon == t_canon or t_canon in p_canon.parents:
            return True
    return False


def _segment_targets_temp_isolated(seg_low: str, temp_sys: str) -> bool:
    """Verifica che tutti i target di pytest nel segmento siano confinati in TEMP/sandbox."""
    raw_tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', seg_low)
    tokens = [tok.strip("\"'()[]{}") for tok in raw_tokens if tok.strip("\"'()[]{}")]
    markers = _PYTEST_TEMP_SAFE_MARKERS + ((temp_sys,) if len(temp_sys) > 3 else ())
    has_temp_target = False
    for idx, tok in enumerate(tokens):
        if tok.startswith("--rootdir="):
            val = tok.split("=", 1)[1].strip("\"'")
            if not any(m in val for m in markers):
                return False
            has_temp_target = True
            continue
        if tok.startswith("-") or tok in ("pytest", "pytest.exe", "python", "python.exe", "python3", "py"):
            continue
        if idx > 0 and tokens[idx - 1] in ("-m", "-p", "-o", "-k", "--basetemp", "--cov", "--cov-report"):
            continue
        if tok.startswith("basetemp="):
            continue
        if "tests" in tok or tok.endswith(".py") or ".py::" in tok or "/" in tok:
            if any(m in tok for m in markers):
                has_temp_target = True
            else:
                return False
    return has_temp_target


def _classify_isolated_pytest_violation(
    cmd_str: str,
    cmd_deobf: str,
    project_root: Path,
) -> Optional[Dict[str, Any]]:
    """Blocca pytest diretto su Drive FS o Hub fuori %TEMP% ([RULE-WIN32-ISOLATED-PYTEST])."""
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments, _unwrap_shell_subcommands
    from _internal.nk_hook_gate.shell_write_detector import (
        _mask_balanced_prompt_payloads,
        _strip_readonly_search_patterns,
    )

    proj_canon = _canonical_path(project_root)
    eff_root = _resolve_effective_hub_root(project_root)
    proj_is_temp = _is_temp_root_path(proj_canon) and _is_temp_root_path(eff_root)
    proj_markers = {
        proj_canon.as_posix().lower(),
        eff_root.as_posix().lower(),
        str(project_root).replace("\\", "/").lower(),
    } - {"", "/"}
    temp_sys = _canonical_path(tempfile.gettempdir()).as_posix().lower()

    candidates = [cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str)]
    for cand in candidates:
        for seg in _split_shell_segments(cand) or [cand]:
            seg_clean = _strip_readonly_search_patterns(_mask_balanced_prompt_payloads(cmd_str, seg))
            seg_low = seg_clean.replace("\\", "/").lower()
            is_pr_cmd = "platform_runner.py" in seg_low and "--pytest-isolated" not in seg_low and bool(_PLATFORM_CMD_PYTEST_RE.search(seg_low))
            if not (_PYTEST_DIRECT_CMD_RE.search(seg_low) or is_pr_cmd):
                continue
            if "platform_runner.py" in seg_low and "--pytest-isolated" in seg_low:
                continue
            if any(runner in seg_low for runner in _PYTEST_ISOLATED_SAFE_RUNNERS):
                continue

            has_cloud = any(m in seg_low for m in _PYTEST_CLOUD_DRIVE_MARKERS)
            has_proj = (not proj_is_temp) and any(pm in seg_low for pm in proj_markers)
            temp_scoped = _segment_targets_temp_isolated(seg_low, temp_sys)
            if has_cloud or has_proj or ((not proj_is_temp) and not temp_scoped):
                return {
                    "decision": "deny",
                    "reason": (
                        "[RULE-WIN32-ISOLATED-PYTEST] Direct pytest execution on Drive FS / Hub outside %TEMP% is blocked; "
                        "use python -B -u scripts/platform_runner.py --pytest-isolated --targets ..."
                    ),
                }
    return None


def _classify_protected_target(
    target: str,
    cmd: str = "",
    project_root: Path = _WORKSPACE_ROOT,
    strict_external: bool = False,
) -> Dict[str, Any]:
    """Classifica i target protetti, i flag di override e i comandi shell malevoli."""
    target_str = str(target or "").strip()
    if not cmd and target_str:
        from _internal.nk_hook_gate.shell_parser import _deobfuscate_ps_backticks

        target_deobf = _deobfuscate_ps_backticks(target_str)
        target_low = target_deobf.lower()
        if (
            "-encodedcommand" in target_low
            or bool(_ENCODED_CMD_RE.search(target_deobf))
            or bool(_PS_COMMAND_WRAPPER_RE.search(target_deobf))
            or (
                not _FS_PATH_PREFIX_RE.match(_strip_wrapping_quotes(target_str))
                and bool(_SHELL_CMD_START_RE.match(target_deobf))
            )
        ):
            cmd = target
            target = ""

    cmd_str = str(cmd or "")
    if cmd_str:
        from _internal.nk_hook_gate.shell_parser import (
            _deobfuscate_ps_backticks,
            _extract_archive_targets,
            _extract_output_flag_targets,
            _extract_redirection_targets,
            _has_unquoted_ps_backtick_obfuscation,
            _unwrap_shell_subcommands,
        )
        from _internal.nk_hook_gate.shell_write_detector import (
            _has_cmd_write_indicator,
            _has_unstaged_temp_script_targeting_protected,
            _is_authorized_script_invocation,
        )

        cmd_deobf = _deobfuscate_ps_backticks(cmd_str)
        cmd_low = cmd_deobf.replace("\\", "/").lower()

        if (
            "--allow-governance-override" in cmd_low
            and os.environ.get("NK_ALLOW_GOVERNANCE_OVERRIDE", "").strip() != "1"
        ):
            return {
                "decision": "deny",
                "reason_code": "UNAUTHORIZED_GOVERNANCE_OVERRIDE",
                "reason": "Flag --allow-governance-override requires NK_ALLOW_GOVERNANCE_OVERRIDE=1 ([RULE-00] / EXAM-06).",
            }

        if ("\n" in cmd_str or "\r" in cmd_str) and re.search(
            r"\b(?:python(?:3)?|py)(?:\.exe)?\b[^\n\r]*\s-c\b", cmd_deobf, re.IGNORECASE
        ):
            return {
                "decision": "deny",
                "reason": "Multi-line python -c one-liner is forbidden ([RULE-01]); write a script in scratch/ or %TEMP%\\nk_diagnostics\\.",
            }

        if _has_unquoted_ps_backtick_obfuscation(cmd_str):
            return {
                "decision": "deny",
                "reason": "Obfuscated PowerShell backtick command execution is forbidden in run_command.",
            }

        for candidate_cmd in (cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str)):
            if _ENCODED_CMD_RE.search(candidate_cmd) or _DYNAMIC_PS_EXEC_RE.search(
                candidate_cmd
            ):
                return {
                    "decision": "deny",
                    "reason": "Obfuscated PowerShell -EncodedCommand / Invoke-Expression (iex) / dynamic & call is forbidden in run_command.",
                }
            if _DESTRUCTIVE_GIT_RE.search(candidate_cmd):
                return {
                    "decision": "deny",
                    "reason": "Destructive git command (checkout/restore/reset --hard/clean -f) is forbidden.",
                }

        inline_py_denial, saw_python_c = _check_inline_python_ast_blocks(
            cmd_str, cmd_deobf, project_root
        )
        if inline_py_denial is not None:
            return inline_py_denial

        iso_pytest_denial = _classify_isolated_pytest_violation(
            cmd_str, cmd_deobf, project_root
        )
        if iso_pytest_denial is not None:
            return iso_pytest_denial
    else:
        cmd_low = ""
        saw_python_c = False

    if target and target.strip():
        if _has_ntfs_ads_stream(target):
            return {
                "decision": "deny",
                "reason": "NTFS Alternate Data Streams (:) are forbidden in file targets.",
            }
        if _has_ancestor_reparse_escape(target, project_root):
            return {
                "decision": "deny",
                "reason": "Symlink or reparse point escape on target or ancestor path is forbidden (anti-TOCTOU).",
            }
        cand = _resolve_target_path(target, project_root)
        cand_parts_low = [p.lower().rstrip(". ") for p in cand.parts]
        cand_name_low = cand.name.lower().split(":", 1)[0].rstrip(". ")

        if ".wal" in cand_parts_low:
            return {
                "decision": "deny",
                "reason": "Direct write to .wal/ transaction logs is forbidden.",
            }
        if _is_valid_staging_path(cand, project_root):
            return {}
        if cand_name_low == "oracle_lock.json":
            return {
                "decision": "deny",
                "reason": "Direct write to oracle_lock.json outside .staging/ is forbidden ([RULE-ORACLE-LOCK]).",
            }
        if cand_name_low == "quality_baseline.json":
            return {
                "decision": "deny",
                "reason": "Direct write to quality_baseline.json outside .staging/ is forbidden.",
            }
        if cand_name_low.startswith("checkpoint_") and cand_name_low.endswith(".json"):
            return {
                "decision": "deny",
                "reason": "Direct write or creation of checkpoint_*.json outside .staging/ is forbidden (D-02).",
            }
        if cand_name_low == "patch_notes.md":
            return {}
        if _is_whitelisted_outside_staging(cand, project_root):
            return {}
        if any(p in ("scripts", ".agents", "nk_genome", "schemas") for p in cand_parts_low):
            return {
                "decision": "deny",
                "reason": "Direct write to protected governance/code directories outside .staging/ is blocked; stage in .staging/ and promote via win32_2pc_engine.py.",
            }

    if cmd_low:
        all_redir_and_out = (
            _extract_redirection_targets(cmd_str)
            + _extract_output_flag_targets(cmd_str)
            + _extract_archive_targets(cmd_str)
        )
        for rt in all_redir_and_out:
            if not _is_safe_redirection_target(rt, project_root):
                viol = _classify_redirection_target_violation(rt, project_root)
                if viol is not None:
                    return viol

        if _has_unstaged_temp_script_targeting_protected(cmd_str, project_root):
            return {
                "decision": "deny",
                "reason": "Execution of unstaged Temp/scratch script targeting protected paths outside .staging/ is blocked.",
            }

        has_write_ind = _has_cmd_write_indicator(cmd_str, project_root)

        if "nk_transcript_tools.py" in cmd_low and "oracle-lock" in cmd_low:
            if "verify" in cmd_low and not has_write_ind:
                return {}
            if ("freeze" in cmd_low or "create" in cmd_low) and strict_external:
                return {
                    "decision": "ask",
                    "reason": "Re-freezing oracle_lock.json requires explicit user approval ([RULE-ORACLE-LOCK]).",
                }
            if not has_write_ind:
                return {}

        sanitized_cmd = _sanitize_staged_tokens_in_cmd(cmd_low)

        if "oracle_lock.json" in sanitized_cmd and has_write_ind and not saw_python_c:
            return {
                "decision": "deny",
                "reason": "Direct write to oracle_lock.json outside .staging/ is forbidden ([RULE-ORACLE-LOCK]).",
            }
        if "quality_baseline.json" in sanitized_cmd and has_write_ind and not saw_python_c:
            return {
                "decision": "deny",
                "reason": "Direct shell write to quality_baseline.json outside .staging/ is forbidden.",
            }
        if "patch_notes.md" in sanitized_cmd and has_write_ind and not saw_python_c:
            return {
                "decision": "deny",
                "reason": "Destructive shell write to PATCH_NOTES.md is forbidden; use prepend-only edit_file.",
            }

        is_auth = _is_authorized_script_invocation(cmd_str, project_root)
        if not is_auth and has_write_ind:
            if not saw_python_c and _PROTECTED_DIR_CMD_RE.search(sanitized_cmd):
                return {
                    "decision": "deny",
                    "reason": "Direct shell write to scripts/, .agents/, or nk_genome/ outside .staging/ is blocked; stage in .staging/ and promote via win32_2pc_engine.py.",
                }
            b1_viol = _classify_non_redirection_write_targets(cmd_str, project_root)
            if b1_viol is not None:
                return b1_viol

    return {}


__all__ = [
    "_check_inline_python_ast_blocks",
    "_classify_isolated_pytest_violation",
    "_classify_non_redirection_write_targets",
    "_classify_protected_target",
    "_classify_redirection_target_violation",
    "_extract_candidate_write_targets",
    "_looks_like_write_path_candidate",
]
