"""Estrazione argomenti MCP e classificazione chiamate MCP potenzialmente mutanti."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from _internal.nk_hook_gate.constants import (
    _MCP_CHROME_DEVTOOLS_TOOLS,
    _MCP_MUTATING_TOOL_RE,
    _MCP_PATH_KEY_SUBSTRINGS,
    _WORKSPACE_ROOT,
)
from _internal.nk_hook_gate.json_io import _extract_args_dict
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _has_ancestor_reparse_escape,
    _has_ntfs_ads_stream,
    _is_valid_staging_path,
    _is_whitelisted_outside_staging,
    _resolve_effective_hub_root,
    _resolve_target_path,
)

_KNOWN_MCP_EAGER_PREFIXES = (
    "mcp_tavily-mcp_",
    "mcp_google-docs-mcp_",
    "mcp_puppeteer_",
    "mcp_chrome-devtools-mcp_",
    "mcp_firebase-mcp-server_",
)


def _extract_mcp_candidate_paths(
    obj: Any, key_hint: str = "", depth: int = 0
) -> List[str]:
    """Estrae ricorsivamente i valori stringa candidati a rappresentare path FS negli argomenti MCP."""
    if depth > 10 or obj is None:
        return []
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_extract_mcp_candidate_paths(v, str(k or ""), depth + 1))
        return out
    if isinstance(obj, (list, tuple)):
        for item in obj:
            out.extend(_extract_mcp_candidate_paths(item, key_hint, depth + 1))
        return out
    if not isinstance(obj, str):
        return []
    val = obj.strip()
    if not val:
        return []
    val_low = val.lower()
    if val_low.startswith(
        (
            "http://",
            "https://",
            "ws://",
            "wss://",
            "about:",
            "data:",
            "blob:",
            "chrome://",
            "devtools://",
        )
    ):
        return []
    if val_low.startswith("file://"):
        stripped = val[8:] if val_low.startswith("file:///") else val[7:]
        return [stripped] if stripped else []
    key_low = key_hint.lower()
    is_path_key = any(sub in key_low for sub in _MCP_PATH_KEY_SUBSTRINGS)
    if is_path_key:
        return [val]
    norm_low = val_low.replace("\\", "/")
    if re.match(r"^(?:[a-z]:/|\\\\|/|(?:\./|\.\./))", norm_low) or (
        " " not in norm_low
        and (
            norm_low.startswith(
                (
                    "nk_hub/",
                    ".staging/",
                    "scripts/",
                    ".agents/",
                    "nk_genome/",
                    "schemas/",
                    "tests/",
                    "nk_tracking/",
                )
            )
            or any(
                seg in norm_low
                for seg in (
                    "/scripts/",
                    "/.agents/",
                    "/nk_genome/",
                    "/schemas/",
                    "/tests/",
                    "/nk_hub/",
                    "oracle_lock.json",
                    "quality_baseline.json",
                )
            )
        )
    ):
        return [val]
    return []


def _resolve_eager_mcp_names(
    mcp_server: str, mcp_tool: str, fallback_tool_name: str
) -> tuple[str, str]:
    """Risolve ServerName e ToolName per chiamate MCP dirette mcp_<server>_<tool>."""
    if mcp_tool or not fallback_tool_name.lower().startswith("mcp_"):
        return mcp_server, mcp_tool
    low_fb = fallback_tool_name.lower()
    for pref in _KNOWN_MCP_EAGER_PREFIXES:
        if low_fb.startswith(pref):
            srv = pref[4:-1]
            tool = fallback_tool_name[len(pref) :]
            return mcp_server or srv, tool
    parts = fallback_tool_name.split("_", 2)
    if len(parts) == 3:
        return mcp_server or parts[1], parts[2]
    return mcp_server, fallback_tool_name


def _classify_mcp_tool_call(
    args: Dict[str, Any], project_root: Path, fallback_tool_name: str = ""
) -> Dict[str, Any]:
    """Applica il gate di sicurezza ai tool MCP bloccando mutazioni, shell e path protetti."""
    mcp_server = str(
        args.get("ServerName")
        or args.get("server_name")
        or args.get("serverName")
        or args.get("server")
        or ""
    ).strip()
    mcp_tool = str(
        args.get("ToolName")
        or args.get("tool_name")
        or args.get("mcp_tool_name")
        or args.get("mcpToolName")
        or ""
    ).strip()
    mcp_server, mcp_tool = _resolve_eager_mcp_names(
        mcp_server, mcp_tool, fallback_tool_name
    )
    if not mcp_tool:
        return {
            "decision": "deny",
            "reason": "Blocked call_mcp_tool without explicit ToolName (fail-closed).",
        }

    raw_mcp_args: Any = None
    for k_arg in ("Arguments", "arguments", "input", "params"):
        if k_arg in args and args[k_arg] is not None:
            raw_mcp_args = args[k_arg]
            break
    if isinstance(raw_mcp_args, str):
        stripped_args = raw_mcp_args.strip()
        if stripped_args.startswith("{") or stripped_args.startswith("["):
            try:
                raw_mcp_args = json.loads(stripped_args)
            except Exception:
                raw_mcp_args = {"_raw": stripped_args}
        elif stripped_args:
            raw_mcp_args = {"_raw": stripped_args}
        else:
            raw_mcp_args = {}
    elif not isinstance(raw_mcp_args, (dict, list)):
        raw_mcp_args = args if fallback_tool_name.lower().startswith("mcp_") else {}

    eff_root = _resolve_effective_hub_root(project_root)
    proj_canon = _canonical_path(project_root)
    ws_hub = _canonical_path(_WORKSPACE_ROOT / "NK_Hub")
    for cand_str in _extract_mcp_candidate_paths(raw_mcp_args):
        if _has_ntfs_ads_stream(cand_str):
            return {
                "decision": "deny",
                "reason": "Blocked call_mcp_tool with NTFS Alternate Data Stream path target.",
            }
        if _has_ancestor_reparse_escape(cand_str, project_root):
            return {
                "decision": "deny",
                "reason": "Blocked call_mcp_tool with symlink/reparse point escape path target.",
            }
        cand_path = _resolve_target_path(cand_str, project_root)
        if _is_valid_staging_path(cand_path, project_root):
            continue
        cand_parts_low = [p.lower().rstrip(". ") for p in cand_path.parts]
        cand_name_low = cand_path.name.lower().split(":", 1)[0].rstrip(". ")
        if (
            cand_name_low
            in ("oracle_lock.json", "quality_baseline.json", "patch_notes.md")
            or (
                cand_name_low.startswith("checkpoint_")
                and cand_name_low.endswith(".json")
            )
        ):
            return {
                "decision": "deny",
                "reason": f"Blocked call_mcp_tool targeting protected governance artifact outside .staging/: {cand_path.name}",
            }
        if any(
            p
            in (
                "scripts",
                ".agents",
                "nk_genome",
                "schemas",
                "tests",
                ".wal",
                "nk_external_projects",
            )
            for p in cand_parts_low
        ):
            return {
                "decision": "deny",
                "reason": "Blocked call_mcp_tool targeting protected code/governance/tests directory outside .staging/.",
            }
        if any(
            cand_path == br or br in cand_path.parents
            for br in (eff_root, proj_canon, ws_hub)
        ) and not _is_whitelisted_outside_staging(cand_path, project_root):
            return {
                "decision": "deny",
                "reason": "Blocked call_mcp_tool targeting NK_Hub path outside .staging/.",
            }

    srv_low = mcp_server.lower()
    tool_low = mcp_tool.lower()
    if _MCP_MUTATING_TOOL_RE.search(tool_low):
        return {
            "decision": "deny",
            "reason": f"Blocked mutating/shell MCP tool: {mcp_tool}",
        }

    if tool_low.startswith("tavily_") or srv_low == "tavily-mcp":
        return {}
    if tool_low == "read_google_doc":
        return {}
    if tool_low.startswith("developerknowledge_"):
        return {}
    if tool_low.startswith(("firebase_get_", "firebase_list_")) or tool_low in (
        "firebase_read_resources",
        "firebase_deploy_status",
    ):
        return {}
    if tool_low.startswith("puppeteer_") or (
        srv_low == "puppeteer" and not _MCP_MUTATING_TOOL_RE.search(tool_low)
    ):
        return {}
    if tool_low in _MCP_CHROME_DEVTOOLS_TOOLS or (
        srv_low == "chrome-devtools-mcp"
        and not _MCP_MUTATING_TOOL_RE.search(tool_low)
    ):
        return {}

    return {
        "decision": "deny",
        "reason": f"Blocked unrecognized or non-readonly MCP tool: {mcp_server or 'unknown'}:{mcp_tool}",
    }
