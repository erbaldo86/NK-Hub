"""Ancora di sicurezza primaria _handle_write_gate per PreToolUse."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

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
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
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


def _handle_write_gate(
    payload: Dict[str, Any],
    project_root: Path,
    strict_external: bool,
    cli_target: str,
    cli_cmd: str,
    cli_content: str,
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

    target = str(
        cli_target
        or args.get("TargetFile")
        or args.get("target_file")
        or args.get("Path")
        or args.get("path")
        or args.get("file_path")
        or args.get("filePath")
        or args.get("AbsolutePath")
        or args.get("absolute_path")
        or args.get("NotebookPath")
        or args.get("notebook_path")
        or args.get("file")
        or args.get("target")
        or ""
    )
    cmd = str(
        cli_cmd
        or args.get("CommandLine")
        or args.get("command_line")
        or args.get("command")
        or args.get("cmd")
        or ""
    )
    chunks = (
        args.get("ReplacementChunks")
        if isinstance(args.get("ReplacementChunks"), list)
        else (
            args.get("replacement_chunks")
            if isinstance(args.get("replacement_chunks"), list)
            else []
        )
    )
    new_content = str(
        cli_content
        or args.get("Content")
        or args.get("content")
        or args.get("CodeContent")
        or args.get("code_content")
        or args.get("Replacement")
        or args.get("replacement")
        or args.get("ReplacementContent")
        or args.get("replacement_content")
        or args.get("new_string")
        or args.get("new_str")
        or ""
    )
    if not new_content and chunks:
        new_content = "\n".join(
            str(
                c.get("ReplacementContent")
                or c.get("Replacement")
                or c.get("new_string")
                or c.get("new_str")
                or ""
            )
            for c in chunks
            if isinstance(c, dict)
        )

    cmd_stripped = cmd.strip()
    if cmd_stripped:
        from _internal.nk_hook_gate.shell_parser import _deobfuscate_ps_backticks

        cmd_deobf = _deobfuscate_ps_backticks(cmd)
        cmd_low = cmd_deobf.replace("\\", "/").lower()
        hallucinated_res = pre_command_gate(cmd_deobf)
        if hallucinated_res:
            return hallucinated_res
    else:
        cmd_low = ""

    protected_res = _classify_protected_target(
        target, cmd, project_root, strict_external=strict_external
    )
    if protected_res:
        return protected_res

    if target.strip():
        cand = _resolve_target_path(target, project_root)
        cand_parts_low = [p.lower().rstrip(". ") for p in cand.parts]
        cand_name_low = cand.name.lower().split(":", 1)[0].rstrip(". ")

        if _is_valid_staging_path(cand, project_root):
            return {}

        if cand_name_low == "patch_notes.md":
            if cand.exists():
                old_txt = cand.read_text(encoding="utf-8", errors="replace").strip()
                anchor = _extract_first_section(old_txt)
                old_headers = _extract_historical_headers(old_txt)
                if old_txt and (anchor or old_headers):
                    if chunks:
                        sim_txt = old_txt
                        for c in chunks:
                            if isinstance(c, dict):
                                t_c = (
                                    str(
                                        c.get("TargetContent")
                                        or c.get("Target")
                                        or c.get("old_string")
                                        or c.get("old_str")
                                        or ""
                                    )
                                    .replace("\r\n", "\n")
                                    .strip()
                                )
                                r_c = str(
                                    c.get("ReplacementContent")
                                    or c.get("Replacement")
                                    or c.get("new_string")
                                    or c.get("new_str")
                                    or ""
                                )
                                if t_c and t_c in sim_txt:
                                    sim_txt = sim_txt.replace(t_c, r_c)
                                elif not t_c:
                                    sim_txt = r_c
                    elif (
                        args.get("Target")
                        or args.get("TargetContent")
                        or args.get("old_string")
                        or args.get("old_str")
                    ):
                        tgt_s = str(
                            args.get("Target")
                            or args.get("TargetContent")
                            or args.get("old_string")
                            or args.get("old_str")
                            or ""
                        )
                        rep_raw = (
                            args.get("Replacement")
                            if "Replacement" in args
                            else (
                                args.get("ReplacementContent")
                                if "ReplacementContent" in args
                                else (
                                    args.get("new_string")
                                    if "new_string" in args
                                    else (
                                        args.get("new_str")
                                        if "new_str" in args
                                        else new_content
                                    )
                                )
                            )
                        )
                        rep_s = str(rep_raw if rep_raw is not None else "")
                        sim_txt = (
                            old_txt.replace(tgt_s, rep_s)
                            if (tgt_s and tgt_s in old_txt)
                            else rep_s
                        )
                    else:
                        sim_txt = new_content

                    norm_sim = "\n".join(
                        ln.strip()
                        for ln in str(sim_txt or "").splitlines()
                        if ln.strip()
                    )
                    sim_headers_set = set(
                        _extract_historical_headers(str(sim_txt or ""))
                    )
                    if (
                        not sim_txt
                        or (
                            anchor
                            and anchor not in sim_txt
                            and anchor not in norm_sim
                        )
                        or any(h not in sim_headers_set for h in old_headers)
                    ):
                        return {
                            "decision": "deny",
                            "reason": "PATCH_NOTES.md is prepend-only: preserve previous history.",
                        }
            return {}

        if _is_whitelisted_outside_staging(cand, project_root):
            return {}

        if any(
            p in ("nk_external_projects", *_PROTECTED_PROJECT_SEGMENTS)
            for p in cand_parts_low
        ):
            return {
                "decision": "deny",
                "reason": "Direct write outside .staging/ to protected code or test directories is blocked; stage and promote via win32_2pc_engine.py.",
            }

        eff_root = _resolve_effective_hub_root(project_root)
        proj_canon = _canonical_path(project_root)
        ws_root = _canonical_path(_WORKSPACE_ROOT)
        if any(
            cand == base_r or base_r in cand.parents
            for base_r in (eff_root, proj_canon, ws_root)
        ):
            return {
                "decision": "deny",
                "reason": "Default-deny: direct write inside project root outside .staging/ is forbidden ([RULE-00]).",
            }

    if cmd_low:
        from _internal.nk_hook_gate.shell_write_detector import (
            _has_cmd_write_indicator,
            _has_unstaged_temp_script_targeting_protected,
            _is_authorized_script_invocation,
        )

        is_temp_writer = _has_unstaged_temp_script_targeting_protected(
            cmd, project_root
        )
        sanitized_cmd = _sanitize_staged_tokens_in_cmd(cmd_low)
        has_write_ind = is_temp_writer or _has_cmd_write_indicator(cmd, project_root)
        is_pure_pytest = ("pytest" in cmd_low) and not has_write_ind
        is_auth_script = _is_authorized_script_invocation(cmd, project_root)
        ext_cmd_unstage = (
            "nk_external_projects/" in sanitized_cmd
            and not is_auth_script
            and not is_pure_pytest
            and (
                has_write_ind
                or bool(_UNSTAGE_CODE_DIR_CMD_RE.search(sanitized_cmd))
            )
        )
        local_cmd_unstage = (
            not is_auth_script
            and bool(_UNSTAGE_CODE_DIR_CMD_RE.search(sanitized_cmd))
            and has_write_ind
        )
        if ext_cmd_unstage or local_cmd_unstage or (is_temp_writer and not is_auth_script):
            return {
                "decision": "deny",
                "reason": "Direct write to src_app/, app/, or tests/ outside .staging/ is blocked; stage and promote via win32_2pc_engine.py.",
            }

    return {}
