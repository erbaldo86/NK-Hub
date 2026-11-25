"""Costanti, pattern regex (via constants_patterns) e risolutori root per HookGateV2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from _internal.nk_common.constants import HALLUCINATED_SCRIPT_DENYLIST, NK_LOCK_FILENAMES
from _internal.nk_common.paths import resolve_scripts_dir
from _internal.nk_hook_gate.constants_patterns import (
    _ARCHIVE_EXTRACT_RE,
    _AUTH_PY_TOK_RE,
    _AUTH_SCRIPT_RE,
    _AUTH_SCRIPT_TOK_RE,
    _CERT_RE,
    _CHAINED_FILE_WRITE_RE,
    _CMD_C_WRAPPER_RE,
    _CMD_WORD_WRITE_RE,
    _DESTRUCTIVE_GIT_RE,
    _DYNAMIC_PS_EXEC_RE,
    _DYN_IMPORT_REFLECT_RE,
    _ENCODED_CMD_RE,
    _FENCED_CODE_BLOCK_RE,
    _FS_PATH_PREFIX_RE,
    _INLINE_CODE_SPAN_RE,
    _MCP_MUTATING_TOOL_RE,
    _OPEN_TOKEN_RE,
    _PATH_CTOR_TOKEN_RE,
    _PATH_MUTATION_METHOD_RE,
    _PROMPT_FLAG_SCAN_RE,
    _PROMPT_SHELL_HAZARD_RE,
    _PROTECTED_DIR_CMD_RE,
    _PS_CALL_WRITE_RE,
    _PS_COMMAND_WRAPPER_RE,
    _PY_EXE_TOK_RE,
    _READONLY_OPEN_TAIL_RE,
    _SAFE_CONV_ID_RE,
    _SAFE_SI_CMD_START_RE,
    _SAFE_SI_FORBIDDEN_RE,
    _SAFE_SI_QUOTED_ARG_RE,
    _SCRIPTS_PY_TOK_RE,
    _SHELL_CMD_START_RE,
    _UNSTAGE_CODE_DIR_CMD_RE,
)
from _internal.nk_hook_gate.core_env import (
    _DELEGATION_TOOLS,
    _HUB_ROOT as _CORE_HUB_ROOT,
    _IS_WIN,
    _READ_ONLY_TOOLS,
    _REPARSE_ATTR_MASK,
    _RETRY_WINERRORS,
    _SCRIPT_DIR as _CORE_SCRIPT_DIR,
    _WORKSPACE_ROOT as _CORE_WORKSPACE_ROOT,
    _is_safe_conv_id,
)


def _resolve_scripts_dir(anchor: Optional[Path] = None) -> Path:
    """Risolve la directory scripts delegando a nk_common.paths.resolve_scripts_dir."""
    return Path(resolve_scripts_dir(str(anchor or __file__)))


_SCRIPT_DIR = Path(_CORE_SCRIPT_DIR)
_HUB_ROOT = Path(_CORE_HUB_ROOT)
_WORKSPACE_ROOT = Path(_CORE_WORKSPACE_ROOT)


def pre_command_gate(cmd: str) -> Dict[str, Any]:
    """Blocca qualsiasi comando che invochi uno degli script allucinati nella denylist."""
    cmd_low = (cmd or "").replace("\\", "/").lower()
    for h_script in HALLUCINATED_SCRIPT_DENYLIST:
        if h_script.lower() in cmd_low:
            return {
                "decision": "deny",
                "reason_code": "HALLUCINATED_SCRIPT_BLOCKED",
                "reason": f"Blocked hallucinated script invocation: {h_script}",
            }
    return {}


_SAFE_DIR_COMPONENTS = ("scratch", "nk_hooks", "nk_diagnostics")
_SAFE_ROOT_FILENAMES = ("readme.md", "readme.it.md", "guida_installazione.md")
_PROTECTED_ROOT_FILENAMES = frozenset(
    (
        "pytest.ini",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "agents.md",
        "gemini.md",
        "claude.md",
        "quality_baseline.json",
        "patch_notes.md",
        "active.json",
        ".gitignore",
        ".env",
        *(name.lower() for name in NK_LOCK_FILENAMES),
    )
)
_PROTECTED_FILE_EXTS = frozenset(
    (
        ".py",
        ".ps1",
        ".json",
        ".jsonl",
        ".md",
        ".ini",
        ".toml",
        ".yaml",
        ".yml",
        ".cfg",
        ".sh",
        ".bat",
        ".cmd",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".wal",
    )
)
_OUTPUT_FLAG_NAMES = frozenset(
    (
        "--snapshot-out",
        "--output",
        "--output-json",
        "--out",
        "--bundle-output",
        "--export",
        "--outfile",
        "-outfile",
        "-out-file",
        "-destinationpath",
        "-destination",
        "-output",
    )
)
_CMD_WRITE_INDICATORS = (
    "set-content",
    "add-content",
    "out-file",
    "-outfile",
    "set-item",
    "remove-item",
    "copy-item",
    "move-item",
    "new-item",
    "clear-content",
    "rename-item",
    "tee-object",
    "start-process",
    "[system.io.file]::",
    "[io.file]::",
    "[system.io.streamwriter]",
    "[io.streamwriter]",
    "streamwriter]::new",
    "streamwriter(",
    "[system.io.binarywriter]",
    "[system.io.directory]::",
    "robocopy",
    "xcopy",
    "mklink",
    "write_text",
    "write_bytes",
    "shutil.",
    "io.fileio",
    "fileio(",
    "extractall(",
    "sqlite3.connect(",
    "b64decode(",
    "os.open(",
    "o_wronly",
    "o_creat",
    "o_rdwr",
    "os.rename(",
    "os.replace(",
    "os.replace",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.makedirs",
    "os.mkdir",
    "os.system(",
    "unlink(",
    "__import__(",
    "importlib.",
    "import_module(",
    "getattr(",
    "__getattribute__(",
    "setattr(",
    "copyfile",
    "copy2(",
    "copytree(",
    "rmtree(",
    "expand-archive",
    "unpack_archive",
)
_PROTECTED_PROJECT_SEGMENTS = (
    "scripts",
    ".agents",
    "tests",
    "nk_genome",
    "src_app",
    "src",
    "app",
    "core",
    "schemas",
)
_PROD_DIR_PREFIXES = (
    "scripts/",
    ".agents/",
    "src_app/",
    "tests/",
    "nk_tracking/",
    "nk_genome/",
    "app/",
    "src/",
    "core/",
    "schemas/",
)
_MCP_CHROME_DEVTOOLS_TOOLS = frozenset(
    (
        "click",
        "close_page",
        "drag",
        "emulate",
        "evaluate_script",
        "fill",
        "fill_form",
        "get_console_message",
        "get_css_styles",
        "get_network_request",
        "handle_dialog",
        "hover",
        "lighthouse_audit",
        "list_console_messages",
        "list_network_requests",
        "list_pages",
        "navigate_page",
        "new_page",
        "performance_analyze_insight",
        "performance_start_trace",
        "performance_stop_trace",
        "press_key",
        "resize_page",
        "screencast_start",
        "screencast_stop",
        "select_page",
        "set_logpoints",
        "take_heapsnapshot",
        "take_screenshot",
        "take_snapshot",
        "type_text",
        "upload_file",
        "wait_for",
    )
)
_MCP_PATH_KEY_SUBSTRINGS = (
    "path",
    "file",
    "target",
    "output",
    "dest",
    "dir",
    "folder",
    "cwd",
    "root",
)
_STOP_SPOOF_SOURCES = frozenset(
    ("USER", "USER_EXPLICIT", "MODEL", "ASSISTANT", "TOOL", "GENERIC")
)
_STOP_SPOOF_TYPES = frozenset(
    ("USER_INPUT", "PLANNER_RESPONSE", "TOOL_RESULT", "TOOL_OUTPUT", "GENERIC")
)
_STOP_SPOOF_ROLES = frozenset(("user", "model", "assistant", "tool"))

_PYTEST_ISOLATED_SAFE_RUNNERS = (
    "dast_sandbox_runner.py",
    "quality_baseline_manager.py",
    "rsi_convergence_engine.py",
    "sbfl_pytest_bridge.py",
    "auto_heal_pipeline.py",
)
_PYTEST_CLOUD_DRIVE_MARKERS = (
    "g:/",
    "il mio drive",
    "google drive",
)
_PYTEST_TEMP_SAFE_MARKERS = (
    "%temp%",
    "$env:temp",
    "${env:temp}",
    "/tmp/",
    "appdata/local/temp",
    "nk_pytest_iso_",
    "nk_sandbox_",
)


def _strip_markdown_code_spans(text: str) -> str:
    """Rimuove blocchi di codice fenced e span inline tra backtick prima della verifica claim."""
    cleaned = _FENCED_CODE_BLOCK_RE.sub(" ", text or "")
    return _INLINE_CODE_SPAN_RE.sub(" ", cleaned)


def _strip_wrapping_quotes(raw_str: str) -> str:
    """Rimuove un'eventuale coppia simmetrica di virgolette esterne attorno al percorso."""
    s = raw_str.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1].strip()
    return s
