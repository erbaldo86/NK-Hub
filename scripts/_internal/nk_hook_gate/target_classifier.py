"""Classificazione principale dei target protetti, guardie Online e comandi shell."""

from __future__ import annotations

import os, re, tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import NK_LOCK_FILENAMES
from _internal.nk_hook_gate.classifier_redirections import (
    _check_inline_python_ast_blocks, _classify_non_redirection_write_targets, _classify_redirection_target_violation, _extract_candidate_write_targets, _looks_like_write_path_candidate,
)
from _internal.nk_hook_gate.constants import (
    _DESTRUCTIVE_GIT_RE, _DYNAMIC_PS_EXEC_RE, _ENCODED_CMD_RE, _FS_PATH_PREFIX_RE, _PROTECTED_DIR_CMD_RE, _PS_COMMAND_WRAPPER_RE,
    _PYTEST_CLOUD_DRIVE_MARKERS, _PYTEST_ISOLATED_SAFE_RUNNERS, _PYTEST_TEMP_SAFE_MARKERS, _SHELL_CMD_START_RE, _WORKSPACE_ROOT, _strip_wrapping_quotes, extract_cd_target,
)
from _internal.nk_hook_gate.constants_patterns import _CD_SHELL_VERBS, has_stdin_shell_exec
from _internal.nk_hook_gate.path_safety import (
    _canonical_path, _cmd_mentions_nk_proget_online, _deny_online_readonly, _has_ancestor_reparse_escape, _has_ntfs_ads_stream,
    _is_nk_proget_online_target, _is_safe_redirection_target, _is_valid_staging_path, _is_whitelisted_outside_staging,
    _resolve_effective_hub_root, _resolve_target_path, _sanitize_staged_tokens_in_cmd,
)

_PYTEST_DIRECT_CMD_RE = re.compile(
    r"(?:^|[;&|(\n\r]\s*|&&\s*|\|\|\s*)(?:[\"']?[^\s\"';|&]*[/\\])?pytest(?:\.exe)?(?=$|\s)"
    r"|(?:^|\s)-m\s+pytest(?=$|\s)",
    re.IGNORECASE,
)
_PLATFORM_CMD_PYTEST_RE = re.compile(r"--cmd(?:=|\s+)[\"']?[^\n\"']*?\bpytest(?:\.exe)?(?=$|\s)", re.IGNORECASE)
_ONLINE_MUTATING_SCRIPT_RE = re.compile(r"\b(?:win32_2pc_engine|external_project_scaffolder)(?:\.py)?\b", re.IGNORECASE)
_ONLINE_GIT_WRITE_RE = re.compile(r"\bgit(?:\.exe)?\b[^\n;|&]*\b(?:add|commit|rm|mv|checkout|restore|reset|clean|merge|rebase|apply|stash|cherry-pick|push|pull|fetch)\b", re.IGNORECASE)
_ONLINE_ORACLE_WRITE_RE = re.compile(r"\boracle-lock\b[^\n;|&]*\b(?:freeze|create)\b", re.IGNORECASE)
_LOCK_NAMES = tuple(name.lower() for name in NK_LOCK_FILENAMES)
_CD_SKIP_FLAGS = frozenset(("/d", "-path", "-literalpath", "-lp", "-p"))
_CD_INLINE_PREFIXES = ("-path:", "-literalpath:", "-lp:", "-path=", "-literalpath=", "-lp=")


def _find_seg_python_script(seg: str) -> Optional[tuple[List[tuple[str, str, bool]], int, str]]:
    """Individua token, indice e path normalizzato dello script Python invocato nel segmento."""
    from _internal.nk_hook_gate.shell_ast_paths import _find_invoked_script_index
    from _internal.nk_hook_gate.shell_parser import _norm_cmd_verb, _tokenize_shell_tokens

    tokens = _tokenize_shell_tokens(seg)
    if not tokens:
        return None
    words = [u for _, u, _ in tokens]
    first_idx = 1 if len(words) > 1 and words[0] == "&" else 0
    v0 = _norm_cmd_verb(words[first_idx]) if first_idx < len(words) else ""
    if v0 not in ("python", "python3", "py"):
        return None
    s_idx = _find_invoked_script_index(words, first_idx, v0)
    if s_idx is None or s_idx >= len(tokens):
        return None
    sc_norm = _strip_wrapping_quotes(words[s_idx]).replace("\\", "/").lower()
    return tokens, s_idx, sc_norm


def _invoked_safe_runner_basename(seg: str) -> str:
    """Restituisce il basename esatto dello script sicuro invocato, escludendo argomenti o path Temp."""
    hit = _find_seg_python_script(seg)
    if hit is None:
        return ""
    _, _, sc_norm = hit
    if not sc_norm.endswith(".py") or any(bad in sc_norm for bad in ("..", "scratch/", "%temp%", "$env:temp", "/tmp/", "appdata/local/temp", "nk_sandbox_")):
        return ""
    if "/" in sc_norm and not (sc_norm.startswith("scripts/") or "/scripts/" in sc_norm):
        return ""
    return os.path.basename(sc_norm)


def _strip_invoked_python_script_path(cmd_text: str) -> str:
    """Esclude il path dello script Python invocato sotto scripts/ prima del controllo dir protette."""
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments

    segs = _split_shell_segments(cmd_text)
    if not segs:
        return cmd_text
    cleaned_segs: List[str] = []
    for seg in segs:
        hit = _find_seg_python_script(seg)
        if hit is not None:
            tokens, s_idx, sc_norm = hit
            if sc_norm.endswith(".py") and ".." not in sc_norm and "scratch/" not in sc_norm and (sc_norm.startswith("scripts/") or "/scripts/" in sc_norm):
                raw_toks = [raw for raw, _, _ in tokens]
                raw_toks[s_idx] = "__invoked_py_script__"
                cleaned_segs.append(" ".join(raw_toks))
                continue
        cleaned_segs.append(seg)
    return " ; ".join(cleaned_segs)


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


def _classify_isolated_pytest_violation(cmd_str: str, cmd_deobf: str, project_root: Path) -> Optional[Dict[str, Any]]:
    """Blocca pytest diretto su Drive FS o Hub fuori %TEMP% ([RULE-WIN32-ISOLATED-PYTEST])."""
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments, _unwrap_shell_subcommands
    from _internal.nk_hook_gate.shell_write_detector import _mask_balanced_prompt_payloads, _strip_readonly_search_patterns

    proj_canon, eff_root = _canonical_path(project_root), _resolve_effective_hub_root(project_root)
    proj_is_temp = _is_temp_root_path(proj_canon) and _is_temp_root_path(eff_root)
    proj_markers = {proj_canon.as_posix().lower(), eff_root.as_posix().lower(), str(project_root).replace("\\", "/").lower()} - {"", "/"}
    temp_sys = _canonical_path(tempfile.gettempdir()).as_posix().lower()

    candidates = [cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str)]
    for cand in candidates:
        for seg in _split_shell_segments(cand) or [cand]:
            seg_clean = _strip_readonly_search_patterns(_mask_balanced_prompt_payloads(cmd_str, seg))
            seg_low = seg_clean.replace("\\", "/").lower()
            is_pr_cmd = "platform_runner.py" in seg_low and "--pytest-isolated" not in seg_low and bool(_PLATFORM_CMD_PYTEST_RE.search(seg_low))
            if not (_PYTEST_DIRECT_CMD_RE.search(seg_low) or is_pr_cmd):
                continue
            invoked_runner = _invoked_safe_runner_basename(seg_clean)
            if invoked_runner == "platform_runner.py" and "--pytest-isolated" in seg_low.split():
                continue
            if invoked_runner in _PYTEST_ISOLATED_SAFE_RUNNERS:
                continue

            has_cloud = any(m in seg_low for m in _PYTEST_CLOUD_DRIVE_MARKERS)
            has_proj = (not proj_is_temp) and any(pm in seg_low for pm in proj_markers)
            temp_scoped = _segment_targets_temp_isolated(seg_low, temp_sys)
            if has_cloud or has_proj or ((not proj_is_temp) and not temp_scoped):
                return {"decision": "deny", "reason": "[RULE-WIN32-ISOLATED-PYTEST] Direct pytest execution on Drive FS / Hub outside %TEMP% is blocked; use python -B -u scripts/platform_runner.py --pytest-isolated --targets ..."}
    return None


def _extract_cd_dir_arg(tokens: List[Tuple[str, str, bool]]) -> str:
    """Estrae l'argomento directory da un segmento cd/chdir/pushd/Set-Location."""
    idx = 1 if len(tokens) > 1 and tokens[0][1] == "&" else 0
    for _, unq, was_q in tokens[idx + 1 :]:
        low = unq.lower()
        if was_q or (low not in _CD_SKIP_FLAGS and not low.startswith("-")):
            if low.startswith("/d") and not was_q and len(unq) > 2:
                return _strip_wrapping_quotes(unq[2:])
            return _strip_wrapping_quotes(unq)
        for pfx in _CD_INLINE_PREFIXES:
            if low.startswith(pfx):
                return _strip_wrapping_quotes(unq[len(pfx) :])
    return ""


def _segments_cd_into_online(cand: str, project_root: Path) -> bool:
    """Traccia cd/cd/d/Set-Location nei segmenti per rilevare ingressi relativi in NK Proget/Online/."""
    from _internal.nk_hook_gate.shell_parser import _norm_cmd_verb, _split_shell_segments, _tokenize_shell_tokens
    cwd = project_root
    for seg in _split_shell_segments(cand) or [cand]:
        toks = _tokenize_shell_tokens(seg)
        if not toks:
            continue
        if cd_arg := extract_cd_target(toks, _norm_cmd_verb, _CD_SHELL_VERBS, _CD_SKIP_FLAGS, _CD_INLINE_PREFIXES):
            cwd = _resolve_target_path(cd_arg, cwd)
            if _is_nk_proget_online_target(cwd):
                return True
    return False


def _has_online_mut_trigger(cand_clean: str, has_mut: bool) -> bool:
    """Verifica trigger di scrittura su Online per segmento gia ripulito."""
    return has_mut or bool(_ONLINE_MUTATING_SCRIPT_RE.search(cand_clean) or _ONLINE_GIT_WRITE_RE.search(cand_clean) or _ONLINE_ORACLE_WRITE_RE.search(cand_clean))


def _check_cmd_online_mutation(cmd_str: str, cmd_deobf: str, project_root: Path) -> Optional[Dict[str, Any]]:
    """Blocca mutazioni shell, redirezioni, 2PC, scaffolder, git write o oracle-lock freeze verso Online/."""
    from _internal.nk_hook_gate.shell_parser import _extract_archive_targets, _extract_output_flag_targets, _extract_redirection_targets, _norm_cmd_verb, _split_shell_segments, _tokenize_shell_tokens, _unwrap_shell_subcommands
    from _internal.nk_hook_gate.shell_search_mask import _strip_readonly_search_patterns
    from _internal.nk_hook_gate.shell_write_detector import _has_non_redirection_write_indicator, _mask_balanced_prompt_payloads
    cands = (cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str))
    all_rt: List[str] = []
    for cand in cands:
        all_rt.extend(_extract_redirection_targets(cand) + _extract_output_flag_targets(cand) + _extract_archive_targets(cand))
    for rt in all_rt:
        if _cmd_mentions_nk_proget_online(rt) or _is_nk_proget_online_target(_resolve_target_path(rt, project_root)):
            return _deny_online_readonly()
    has_non_null_redir = any(_strip_wrapping_quotes(rt).replace("\\", "/").lower() not in ("nul", "/dev/null", "$null") for rt in all_rt)
    has_mut = _has_non_redirection_write_indicator(cmd_str) or has_non_null_redir or any(has_stdin_shell_exec(c, _split_shell_segments, _tokenize_shell_tokens, _norm_cmd_verb) for c in cands)
    for cand in cands:
        cand_clean = _strip_readonly_search_patterns(_mask_balanced_prompt_payloads(cmd_str, cand))
        if (_cmd_mentions_nk_proget_online(cand_clean) or _segments_cd_into_online(cand, project_root)) and _has_online_mut_trigger(cand_clean, has_mut):
            return _deny_online_readonly()
    return None


def _check_cmd_early_blocks(cmd_str: str, cmd_deobf: str, project_root: Path, conv_id: str = "") -> Tuple[Optional[Dict[str, Any]], bool]:
    """Esegue i controlli prioritari Online lock, stdin shell, AST inline e pytest isolato su cmd_str."""
    from _internal.nk_hook_gate.shell_parser import _norm_cmd_verb, _split_shell_segments, _tokenize_shell_tokens, _unwrap_shell_subcommands
    online_denial = _check_cmd_online_mutation(cmd_str, cmd_deobf, project_root)
    if online_denial is not None:
        return online_denial, False
    if any(has_stdin_shell_exec(c, _split_shell_segments, _tokenize_shell_tokens, _norm_cmd_verb) for c in (cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str))):
        return {"decision": "deny", "reason": "Piped or stdin shell execution (| powershell / | pwsh / | cmd / -Command -) is forbidden in run_command."}, False
    inline_py_denial, saw_python_c = _check_inline_python_ast_blocks(cmd_str, cmd_deobf, project_root, conv_id=conv_id)
    if inline_py_denial is not None:
        return inline_py_denial, saw_python_c
    return _classify_isolated_pytest_violation(cmd_str, cmd_deobf, project_root), saw_python_c


def _classify_gov_target_artifact(cand: Path, cand_parts_low: List[str], cand_name_low: str) -> Optional[Dict[str, Any]]:
    """Blocca scritture dirette fuori .staging/ verso lock, tensor_sessions, commit_train, baseline e checkpoint."""
    if cand_name_low in _LOCK_NAMES:
        return {"decision": "deny", "reason": f"Direct write to {cand.name} outside .staging/ is forbidden ([RULE-ORACLE-LOCK])."}
    if "nk_tracking" in cand_parts_low and ("tensor_sessions" in cand_parts_low or cand_name_low == "active.json"):
        return {"decision": "deny", "reason": "Direct write to nk_tracking/tensor_sessions/ or ACTIVE.json outside .staging/ is forbidden."}
    if "nk_tracking" in cand_parts_low and "commit_train" in cand_parts_low:
        return {"decision": "deny", "reason": "Direct write to nk_tracking/commit_train/ outside .staging/ is forbidden."}
    if cand_name_low == "quality_baseline.json":
        return {"decision": "deny", "reason": "Direct write to quality_baseline.json outside .staging/ is forbidden."}
    if cand_name_low.startswith("checkpoint_") and cand_name_low.endswith(".json"):
        return {"decision": "deny", "reason": "Direct write or creation of checkpoint_*.json outside .staging/ is forbidden (D-02)."}
    return None


def _classify_resolved_file_target(cand: Path, project_root: Path) -> Optional[Dict[str, Any]]:
    """Classifica un percorso risolto rispetto a Online lock, .wal, staging, lock e dir protette."""
    if _is_nk_proget_online_target(cand):
        return _deny_online_readonly()
    cand_parts_low = [p.lower().rstrip(". ") for p in cand.parts]
    cand_name_low = cand.name.lower().split(":", 1)[0].rstrip(". ")

    if ".wal" in cand_parts_low:
        return {"decision": "deny", "reason": "Direct write to .wal/ transaction logs is forbidden."}
    if _is_valid_staging_path(cand, project_root):
        return {}
    if gov_res := _classify_gov_target_artifact(cand, cand_parts_low, cand_name_low):
        return gov_res
    if cand_name_low == "patch_notes.md" or _is_whitelisted_outside_staging(cand, project_root):
        return {}
    if any(p in ("scripts", ".agents", "nk_genome", "schemas", "tests", "oracle_holdout", "benchmark_suite") for p in cand_parts_low):
        return {"decision": "deny", "reason": "Direct write to protected governance/code directories outside .staging/ is blocked; stage in .staging/ and promote via win32_2pc_engine.py."}
    return None


def _classify_oracle_lock_cli_cmd(cmd_low: str, has_write_ind: bool) -> Optional[Dict[str, Any]]:
    """Gestisce il gate CLI nk_transcript_tools.py oracle-lock (verify/freeze/create)."""
    if "nk_transcript_tools.py" not in cmd_low or "oracle-lock" not in cmd_low:
        return None
    if "verify" in cmd_low and not has_write_ind:
        return {}
    if "freeze" in cmd_low or "create" in cmd_low:
        return {"decision": "ask", "reason": "Re-freezing oracle_lock.json requires explicit user approval ([RULE-ORACLE-LOCK])."}
    return {} if not has_write_ind else None


def _classify_shell_gov_artifact_write(sanitized_cmd: str) -> Optional[Dict[str, Any]]:
    """Blocca scritture shell dirette su lock, tensor_sessions, commit_train, quality_baseline e PATCH_NOTES."""
    if any(lf in sanitized_cmd for lf in _LOCK_NAMES):
        return {"decision": "deny", "reason": "Direct write to oracle_lock.json outside .staging/ is forbidden ([RULE-ORACLE-LOCK])."}
    if "tensor_sessions" in sanitized_cmd or ("nk_tracking" in sanitized_cmd and "active.json" in sanitized_cmd):
        return {"decision": "deny", "reason": "Direct write to nk_tracking/tensor_sessions/ or ACTIVE.json outside .staging/ is forbidden."}
    if "commit_train" in sanitized_cmd:
        return {"decision": "deny", "reason": "Direct write to nk_tracking/commit_train/ outside .staging/ is forbidden."}
    if "quality_baseline.json" in sanitized_cmd:
        return {"decision": "deny", "reason": "Direct shell write to quality_baseline.json outside .staging/ is forbidden."}
    if "patch_notes.md" in sanitized_cmd:
        return {"decision": "deny", "reason": "Destructive shell write to PATCH_NOTES.md is forbidden; use prepend-only edit_file."}
    return None


def _classify_cmd_lock_and_gov_write(
    cmd_low: str, sanitized_cmd: str, has_write_ind: bool, saw_python_c: bool
) -> Optional[Dict[str, Any]]:
    """Valuta comandi shell relativi a oracle-lock CLI e scritture su artifact di governance."""
    if (cli_res := _classify_oracle_lock_cli_cmd(cmd_low, has_write_ind)) is not None:
        return cli_res
    if not has_write_ind or saw_python_c:
        return None
    return _classify_shell_gov_artifact_write(sanitized_cmd)


def _classify_protected_target(target: str, cmd: str = "", project_root: Path = _WORKSPACE_ROOT, strict_external: bool = False, conv_id: str = "") -> Dict[str, Any]:
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
            or (not _FS_PATH_PREFIX_RE.match(_strip_wrapping_quotes(target_str)) and bool(_SHELL_CMD_START_RE.match(target_deobf)))
        ):
            cmd, target = target, ""

    cmd_str = str(cmd or "")
    if cmd_str:
        from _internal.nk_hook_gate.shell_parser import _deobfuscate_ps_backticks, _extract_archive_targets, _extract_output_flag_targets, _extract_redirection_targets, _has_unquoted_ps_backtick_obfuscation, _unwrap_shell_subcommands
        from _internal.nk_hook_gate.shell_write_detector import _check_governance_override_denial, _has_cmd_write_indicator, _has_unstaged_temp_script_targeting_protected, _is_authorized_script_invocation

        cmd_deobf = _deobfuscate_ps_backticks(cmd_str)
        cmd_low = cmd_deobf.replace("\\", "/").lower()

        gov_denial = _check_governance_override_denial(cmd_str, cmd_deobf, project_root)
        if gov_denial is not None:
            return gov_denial

        if ("\n" in cmd_str or "\r" in cmd_str) and re.search(r"\b(?:python(?:3)?|py)(?:\.exe)?\b[^\n\r]*\s-c\b", cmd_deobf, re.IGNORECASE):
            return {"decision": "deny", "reason": "Multi-line python -c one-liner is forbidden ([RULE-01]); write a script in scratch/ or %TEMP%\\nk_diagnostics\\."}

        if _has_unquoted_ps_backtick_obfuscation(cmd_str):
            return {"decision": "deny", "reason": "Obfuscated PowerShell backtick command execution is forbidden in run_command."}

        for candidate_cmd in (cmd_str, cmd_deobf, *_unwrap_shell_subcommands(cmd_str)):
            if _ENCODED_CMD_RE.search(candidate_cmd) or _DYNAMIC_PS_EXEC_RE.search(candidate_cmd):
                return {"decision": "deny", "reason": "Obfuscated PowerShell -EncodedCommand / Invoke-Expression (iex) / dynamic & call is forbidden in run_command."}
            if _DESTRUCTIVE_GIT_RE.search(candidate_cmd):
                return {"decision": "deny", "reason": "Destructive git command (checkout/restore/reset --hard/clean -f) is forbidden."}

        early_denial, saw_python_c = _check_cmd_early_blocks(cmd_str, cmd_deobf, project_root, conv_id=conv_id)
        if early_denial is not None:
            return early_denial
    else:
        cmd_low, saw_python_c = "", False

    if target and target.strip():
        if _has_ntfs_ads_stream(target):
            return {"decision": "deny", "reason": "NTFS Alternate Data Streams (:) are forbidden in file targets."}
        if _has_ancestor_reparse_escape(target, project_root):
            return {"decision": "deny", "reason": "Symlink or reparse point escape on target or ancestor path is forbidden (anti-TOCTOU)."}
        cand = _resolve_target_path(target, project_root)
        target_res = _classify_resolved_file_target(cand, project_root)
        if target_res is not None:
            return target_res

    if cmd_low:
        all_redir_and_out = _extract_redirection_targets(cmd_str) + _extract_output_flag_targets(cmd_str) + _extract_archive_targets(cmd_str)
        for rt in all_redir_and_out:
            if not _is_safe_redirection_target(rt, project_root):
                viol = _classify_redirection_target_violation(rt, project_root)
                if viol is not None:
                    return viol

        if _has_unstaged_temp_script_targeting_protected(cmd_str, project_root):
            return {"decision": "deny", "reason": "Execution of unstaged Temp/scratch script targeting protected paths outside .staging/ is blocked."}

        has_write_ind = _has_cmd_write_indicator(cmd_str, project_root)
        sanitized_cmd = _sanitize_staged_tokens_in_cmd(cmd_low)
        cmd_gov_res = _classify_cmd_lock_and_gov_write(cmd_low, sanitized_cmd, has_write_ind, saw_python_c)
        if cmd_gov_res is not None:
            return cmd_gov_res

        is_auth = _is_authorized_script_invocation(cmd_str, project_root)
        if not is_auth and has_write_ind:
            protected_scan_cmd = _strip_invoked_python_script_path(sanitized_cmd)
            if not saw_python_c and _PROTECTED_DIR_CMD_RE.search(protected_scan_cmd):
                return {"decision": "deny", "reason": "Direct shell write to scripts/, .agents/, or nk_genome/ outside .staging/ is blocked; stage in .staging/ and promote via win32_2pc_engine.py."}
            b1_viol = _classify_non_redirection_write_targets(cmd_str, project_root)
            if b1_viol is not None:
                return b1_viol

    return {}


__all__ = [
    "_check_inline_python_ast_blocks", "_classify_isolated_pytest_violation", "_classify_non_redirection_write_targets",
    "_classify_protected_target", "_classify_redirection_target_violation", "_extract_candidate_write_targets", "_looks_like_write_path_candidate",
]
