"""Ambiente leggero zero-overhead per i path fast-path di HookGateV2."""

from __future__ import annotations

import os
import sys

_IS_WIN = (os.name == "nt") or (sys.platform == "win32")


def _resolve_scripts_dir_str(anchor: str = "") -> str:
    """Risolve la directory scripts risalendo dal file corrente con solo os.path."""
    cur = os.path.realpath(anchor or __file__)
    while True:
        parent = os.path.dirname(cur)
        if os.path.basename(cur) == "scripts":
            return cur
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.realpath(anchor or __file__))


_SCRIPT_DIR = _resolve_scripts_dir_str()
_SCRIPT_PARENT = os.path.dirname(_SCRIPT_DIR)
_HUB_ROOT = (
    os.path.dirname(_SCRIPT_PARENT)
    if os.path.basename(_SCRIPT_PARENT) == ".staging"
    else _SCRIPT_PARENT
)
_WORKSPACE_ROOT = _HUB_ROOT

_RETRY_WINERRORS = frozenset((5, 32, 33))
_REPARSE_ATTR_MASK = 0x0400

_DELEGATION_TOOLS = (
    "invoke_subagent",
    "define_subagent",
    "send_message",
    "swarm",
    "post_message",
)

_READ_ONLY_TOOLS = (
    "read_file",
    "view_file",
    "view_file_outline",
    "view_code_item",
    "list_dir",
    "find_by_name",
    "grep_search",
    "list_resources",
    "read_resource",
    "search_web",
)
_READ_ONLY_TOOLS_SET = frozenset(_READ_ONLY_TOOLS)

_STREAK_EXEMPT_TOOLS = _READ_ONLY_TOOLS_SET | frozenset(
    ("read_board", "swarm_wait", "ask_question", "manage_task", "schedule")
)

_SAFE_READONLY_UNSAFE_ARG_KEYS = frozenset(
    (
        "CommandLine",
        "command_line",
        "command",
        "cmd",
        "Content",
        "content",
        "CodeContent",
        "code_content",
        "Replacement",
        "replacement",
        "ReplacementContent",
        "replacement_content",
        "ReplacementChunks",
        "replacement_chunks",
        "new_string",
        "new_str",
        "ServerName",
        "server_name",
        "serverName",
        "ToolName",
        "mcp_tool_name",
        "mcpToolName",
    )
)


def _is_safe_conv_id(cid: object) -> bool:
    """Verifica che l'ID conversazione contenga 1-64 caratteri alfanumerici ASCII, '_' o '-'."""
    if not isinstance(cid, str):
        return False
    n = len(cid)
    if n < 1 or n > 64:
        return False
    for ch in cid:
        if not (
            ("a" <= ch <= "z")
            or ("A" <= ch <= "Z")
            or ("0" <= ch <= "9")
            or ch in ("_", "-")
        ):
            return False
    return True
