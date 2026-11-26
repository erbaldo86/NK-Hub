"""Ancora di sicurezza primaria _handle_write_gate per PreToolUse."""

from __future__ import annotations

from pathlib import Path as _RuntimePath
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from _internal.nk_hook_gate.constants import (
    _PROTECTED_PROJECT_SEGMENTS,
    _UNSTAGE_CODE_DIR_CMD_RE,
    _WORKSPACE_ROOT,
    pre_command_gate,
)
from _internal.nk_hook_gate.core_env import _READ_ONLY_TOOLS_SET
from _internal.nk_hook_gate.json_io import (
    _extract_args_dict,
    _extract_first_section,
    _extract_historical_headers,
    _extract_tool_identity,
    _has_unsafe_readonly_args,
)
from _internal.nk_hook_gate.lane_write_guard import (
    check_lane_plan_write_authorization,
    check_lane_write_authorization,
    check_shell_lane_write_authorization,
    verify_promote_targets_with_lanes,
)
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _cmd_mentions_external_project,
    _deny_online_readonly,
    _is_nk_proget_locale_target,
    _is_nk_proget_online_target,
    _is_valid_staging_path,
    _is_whitelisted_outside_staging,
    _resolve_effective_hub_root,
    _resolve_target_path,
    _sanitize_staged_tokens_in_cmd,
)
from _internal.nk_hook_gate.target_classifier import _classify_protected_target

if TYPE_CHECKING:
    from pathlib import Path
else:
    Path = Any

_TARGET_KEYS = (
    "TargetFile", "target_file", "Path", "path", "file_path", "filePath",
    "AbsolutePath", "absolute_path", "NotebookPath", "notebook_path", "file", "target",
)
_CMD_KEYS = ("CommandLine", "command_line", "command", "cmd")
_CONTENT_KEYS = (
    "Content", "content", "CodeContent", "code_content", "Replacement",
    "replacement", "ReplacementContent", "replacement_content", "new_string", "new_str",
)
_CHUNK_TARGET_KEYS = ("TargetContent", "Target", "old_string", "old_str")
_CHUNK_REP_KEYS = ("ReplacementContent", "Replacement", "new_string", "new_str")
_SINGLE_REP_KEYS = ("Replacement", "ReplacementContent", "new_string", "new_str")


def _first_nonempty_str(args: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    """Estrae la prima stringa non vuota associata alle chiavi fornite."""
    for key in keys:
        val = args.get(key)
        if val:
            return str(val)
    return ""


def _first_present_arg(args: Dict[str, Any], keys: Tuple[str, ...], fallback: Any = "") -> Any:
    """Restituisce il primo argomento presente per chiave, oppure il fallback."""
    for key in keys:
        if key in args:
            val = args.get(key)
            return "" if val is None else val
    return fallback


_PROMOTE_VALUE_FLAGS = (
    "--milestone",
    "--staging-dir",
    "--override-reason",
    "--governance-token",
    "--sandbox-report",
    "--lane-id",
    "--parent-lane",
    "--base-seq",
)


def _extract_promote_root_candidates(words: List[str], project_root: Path) -> List[_RuntimePath]:
    """Estrae le root candidate da CLI --root/--repo-root evitando spoofing di valori di flag."""
    explicit_roots: List[_RuntimePath] = []
    idx = 0
    while idx < len(words):
        clean_tok = words[idx]
        if clean_tok in _PROMOTE_VALUE_FLAGS:
            idx += 2
            continue
        if clean_tok in ("--root", "--repo-root") and idx + 1 < len(words):
            explicit_roots.append(_canonical_path(_resolve_target_path(words[idx + 1], project_root)))
            idx += 2
            continue
        if clean_tok.startswith(("--root=", "--repo-root=")):
            explicit_roots.append(_canonical_path(_resolve_target_path(clean_tok.split("=", 1)[1], project_root)))
        idx += 1
    if explicit_roots:
        return list(dict.fromkeys(explicit_roots))
    return list(dict.fromkeys([_resolve_effective_hub_root(project_root), _canonical_path(project_root)]))


def _verify_promote_roots(roots: List[_RuntimePath]) -> Dict[str, Any]:
    """Verifica verify_active_tensor_session su tutte le root candidate e blocca fail-closed."""
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.tensor_session_guard import verify_active_tensor_session

    for root_cand in roots:
        try:
            verify_active_tensor_session(root_cand, root_cand / ".staging")
        except TwoPhaseCommitError as exc:
            return {
                "decision": "deny",
                "reason_code": "ACTIVE_TENSOR_SESSION_UNAPPROVED",
                "reason": f"Promozione staging bloccata: {exc}",
            }
    return {}


def _collect_promote_segment_roots(
    cmd_deobf: str, project_root: Path, has_inline: bool
) -> List[_RuntimePath]:
    """Estrae le root candidate per ogni segmento shell di --promote-staging."""
    from _internal.nk_hook_gate.constants_patterns import has_win32_2pc_promote_tokens
    from _internal.nk_hook_gate.shell_parser import (
        _split_shell_segments,
        _tokenize_shell_tokens,
        _unwrap_shell_subcommands,
    )

    seen_roots: Dict[_RuntimePath, None] = {}
    for cand in (cmd_deobf, *_unwrap_shell_subcommands(cmd_deobf)):
        for seg in _split_shell_segments(cand) or [cand]:
            words = [u for _, u, _ in _tokenize_shell_tokens(seg)]
            if has_win32_2pc_promote_tokens(words):
                for rc in _extract_promote_root_candidates(words, project_root):
                    seen_roots[rc] = None
    if has_inline:
        for rc in _extract_promote_root_candidates([], project_root):
            seen_roots[rc] = None
    return list(seen_roots.keys())


def _check_tensor_session_promote_gate(cmd_deobf: str, cmd_low: str, project_root: Path) -> Dict[str, Any]:
    """Blocca --promote-staging, --commit-train, --consolidate-sublanes o promote inline valutando ogni segmento."""
    from _internal.nk_hook_gate.shell_redaction import _mask_balanced_prompt_payloads

    masked_low = _mask_balanced_prompt_payloads(cmd_deobf, cmd_deobf).replace("\\", "/").lower()
    has_cli = "win32_2pc_engine" in cmd_low and any(
        fl in cmd_low for fl in ("--promote-staging", "--commit-train", "--consolidate-sublanes")
    )
    has_inline = any(
        fn in masked_low
        for fn in (
            "promote_staging_to_production", "run_commit_train_promote", "consolidate_sublanes_and_promote",
            "append_commit_train_entry", "consolidate_post_commit", "close_active_tensor_session_post_commit",
            "materialize_changelog_fragments", "release_lane", "update_baseline_metrics",
        )
    )
    if not has_cli and not has_inline:
        return {}
    return verify_promote_targets_with_lanes(
        cmd_deobf, project_root, has_inline, _extract_promote_root_candidates
    )


def _evaluate_pre_command_gates(cmd_deobf: str, cmd_low: str, project_root: Path) -> Dict[str, Any]:
    """Esegue pre_command_gate e la precondizione Tensor-RSI su --promote-staging."""
    hallucinated_res = pre_command_gate(cmd_deobf)
    if hallucinated_res:
        return hallucinated_res
    return _check_tensor_session_promote_gate(cmd_deobf, cmd_low, project_root)


def _is_protected_unstaged_direct_target(cand: Path, cand_parts_low: List[str]) -> bool:
    """Identifica target protetti o percorsi NK Proget/Locale/ scritti fuori da .staging/."""
    return _is_nk_proget_locale_target(cand) or any(
        p in ("nk_external_projects", *_PROTECTED_PROJECT_SEGMENTS)
        for p in cand_parts_low
    )


def _simulate_patch_notes_chunks(old_txt: str, chunks: List[Any]) -> str:
    """Applica la simulazione di ReplacementChunks sul testo esistente di PATCH_NOTES.md."""
    sim_txt = old_txt
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        t_c = _first_nonempty_str(chunk, _CHUNK_TARGET_KEYS).replace("\r\n", "\n").strip()
        r_c = str(_first_present_arg(chunk, _CHUNK_REP_KEYS, ""))
        if t_c and t_c in sim_txt:
            sim_txt = sim_txt.replace(t_c, r_c)
        elif not t_c:
            sim_txt = r_c
    return sim_txt


def _simulate_patch_notes_edit(
    old_txt: str, args: Dict[str, Any], chunks: List[Any], new_content: str
) -> str:
    """Calcola il testo risultante per PATCH_NOTES.md da chunks, edit singolo o write."""
    if chunks:
        return _simulate_patch_notes_chunks(old_txt, chunks)
    if any(args.get(k) for k in _CHUNK_TARGET_KEYS):
        tgt_s = _first_nonempty_str(args, _CHUNK_TARGET_KEYS)
        rep_s = str(_first_present_arg(args, _SINGLE_REP_KEYS, new_content))
        return old_txt.replace(tgt_s, rep_s) if (tgt_s and tgt_s in old_txt) else rep_s
    return new_content


def _check_patch_notes_prepend(
    cand: Path, args: Dict[str, Any], chunks: List[Any], new_content: str
) -> Dict[str, Any]:
    """Verifica che le modifiche a PATCH_NOTES.md preservino anchor e header storici (prepend-only)."""
    if not cand.exists():
        return {}
    old_txt = cand.read_text(encoding="utf-8", errors="replace").strip()
    anchor = _extract_first_section(old_txt)
    old_headers = _extract_historical_headers(old_txt)
    if not old_txt or not (anchor or old_headers):
        return {}

    sim_txt = _simulate_patch_notes_edit(old_txt, args, chunks, new_content)
    norm_sim = "\n".join(ln.strip() for ln in str(sim_txt or "").splitlines() if ln.strip())
    sim_headers_set = set(_extract_historical_headers(str(sim_txt or "")))
    if (
        not sim_txt
        or (anchor and anchor not in sim_txt and anchor not in norm_sim)
        or any(h not in sim_headers_set for h in old_headers)
    ):
        return {"decision": "deny", "reason": "PATCH_NOTES.md is prepend-only: preserve previous history."}
    return {}


def _extract_write_inputs(
    args: Dict[str, Any], cli_target: str, cli_cmd: str, cli_content: str
) -> Tuple[str, str, List[Any], str]:
    """Normalizza target, comando, chunks e contenuto dai parametri hook/CLI."""
    target = str(cli_target or _first_nonempty_str(args, _TARGET_KEYS))
    cmd = str(cli_cmd or _first_nonempty_str(args, _CMD_KEYS))
    raw_chunks = args.get("ReplacementChunks") if isinstance(args.get("ReplacementChunks"), list) else args.get("replacement_chunks")
    chunks = raw_chunks if isinstance(raw_chunks, list) else []
    new_content = str(cli_content or _first_nonempty_str(args, _CONTENT_KEYS))
    if not new_content and chunks:
        new_content = "\n".join(
            _first_nonempty_str(c, _CHUNK_REP_KEYS) for c in chunks if isinstance(c, dict)
        )
    return target, cmd, chunks, new_content


def _has_unauthorized_shell_write(cmd: str, project_root: Path) -> bool:
    """Valuta ogni segmento shell isolatamente per bloccare concatenazioni post-script."""
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments
    from _internal.nk_hook_gate.shell_write_detector import (
        _has_cmd_write_indicator,
        _has_unstaged_temp_script_targeting_protected,
        _is_authorized_script_invocation,
    )

    for seg in _split_shell_segments(cmd) or [cmd]:
        seg_low = seg.replace("\\", "/").lower()
        is_temp_writer = _has_unstaged_temp_script_targeting_protected(seg, project_root)
        sanitized_seg = _sanitize_staged_tokens_in_cmd(seg_low)
        has_write_ind = is_temp_writer or _has_cmd_write_indicator(seg, project_root)
        is_pure_pytest = ("pytest" in seg_low) and not has_write_ind
        is_auth_script = _is_authorized_script_invocation(seg, project_root)
        ext_cmd_unstage = (
            _cmd_mentions_external_project(sanitized_seg)
            and not is_auth_script
            and not is_pure_pytest
            and (has_write_ind or bool(_UNSTAGE_CODE_DIR_CMD_RE.search(sanitized_seg)))
        )
        local_cmd_unstage = not is_auth_script and bool(_UNSTAGE_CODE_DIR_CMD_RE.search(sanitized_seg)) and has_write_ind
        if ext_cmd_unstage or local_cmd_unstage or (is_temp_writer and not is_auth_script):
            return True
    return False


def _check_shell_write_and_lane_gate(
    cmd: str, project_root: Path, conv_id: str, cmd_deobf: str = ""
) -> Dict[str, Any]:
    """Verifica scritture shell non autorizzate e isolamento cross-lane verso .staging/lanes/."""
    if _has_unauthorized_shell_write(cmd, project_root):
        return {
            "decision": "deny",
            "reason": "Direct write to src_app/, app/, or tests/ outside .staging/ is blocked; stage and promote via win32_2pc_engine.py.",
        }
    return check_shell_lane_write_authorization(cmd_deobf or cmd, project_root, conv_id)


def _handle_write_gate(
    payload: Dict[str, Any],
    project_root: Path,
    strict_external: bool,
    cli_target: str,
    cli_cmd: str,
    cli_content: str,
    conv_id: str = "",
) -> Dict[str, Any]:
    """Valuta la sicurezza delle scritture su file o dei comandi prima dell'esecuzione."""
    tool_call, tool_name = _extract_tool_identity(payload)
    tool_low = tool_name.lower()
    args = _extract_args_dict(payload, tool_call)
    if (
        tool_low in _READ_ONLY_TOOLS_SET
        and not cli_target
        and not cli_cmd
        and not cli_content
        and not _has_unsafe_readonly_args(args)
    ):
        return {}

    has_mcp_payload = (
        tool_low == "call_mcp_tool"
        or tool_low.startswith("mcp_")
        or (
            not cli_cmd
            and not cli_target
            and any(k in args for k in ("ServerName", "server_name", "serverName", "mcp_tool_name", "mcpToolName"))
        )
    )
    if has_mcp_payload:
        from _internal.nk_hook_gate.mcp_classifier import _classify_mcp_tool_call

        return _classify_mcp_tool_call(args, project_root, fallback_tool_name=tool_name)

    target, cmd, chunks, new_content = _extract_write_inputs(args, cli_target, cli_cmd, cli_content)
    if cmd.strip():
        from _internal.nk_hook_gate.shell_parser import _deobfuscate_ps_backticks

        cmd_deobf = _deobfuscate_ps_backticks(cmd)
        cmd_low = cmd_deobf.replace("\\", "/").lower()
        pre_res = _evaluate_pre_command_gates(cmd_deobf, cmd_low, project_root)
        if pre_res:
            return pre_res
    else:
        cmd_deobf, cmd_low = "", ""

    protected_res = _classify_protected_target(target, cmd, project_root, strict_external=strict_external, conv_id=conv_id)
    if protected_res:
        return protected_res

    if target.strip():
        cand = _resolve_target_path(target, project_root)
        cand_parts_low = [p.lower().rstrip(". ") for p in cand.parts]
        cand_name_low = cand.name.lower().split(":", 1)[0].rstrip(". ")

        if _is_nk_proget_online_target(cand):
            return _deny_online_readonly()
        if _is_valid_staging_path(cand, project_root):
            return check_lane_write_authorization(cand, project_root, conv_id)
        if cand_name_low == "patch_notes.md":
            return _check_patch_notes_prepend(cand, args, chunks, new_content)
        if _is_whitelisted_outside_staging(cand, project_root):
            return check_lane_plan_write_authorization(cand, project_root, conv_id)
        if _is_protected_unstaged_direct_target(cand, cand_parts_low):
            return {
                "decision": "deny",
                "reason": "Direct write outside .staging/ to protected code or test directories is blocked; stage and promote via win32_2pc_engine.py.",
            }
        base_roots = (_resolve_effective_hub_root(project_root), _canonical_path(project_root), _canonical_path(_WORKSPACE_ROOT))
        if any(cand == base_r or base_r in cand.parents for base_r in base_roots):
            return {"decision": "deny", "reason": "Default-deny: direct write inside project root outside .staging/ is forbidden ([RULE-00])."}

    if cmd_low:
        return _check_shell_write_and_lane_gate(cmd, project_root, conv_id, cmd_deobf=cmd_deobf)

    return {}
