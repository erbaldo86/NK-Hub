"""Pattern regex compilati per il gate shell/PowerShell/MCP di HookGateV2."""

from __future__ import annotations

import re

_ARCHIVE_EXTRACT_RE = re.compile(
    r"\btar(?:\.exe)?\b(?:\s+x[vzfjc]*(?=\s)|[^\n;|&]*?(?:\s-[a-z]*x|\s--extract\b))"
    r"|\bexpand-archive\b"
    r"|\bunpack_archive\b"
    r"|\bunzip(?:\.exe)?\b(?![^\n;|&]*\s-[a-z]*(?:l|t)\b)"
    r"|\b7za?(?:\.exe)?\b\s+[xe]\b",
    re.IGNORECASE,
)

_DYN_IMPORT_REFLECT_RE = re.compile(
    r"(?:__import__|__getattribute__|getattr|setattr|import_module)\s*\("
    r"|importlib\s*\.\s*(?:import_module|util)\b"
    r"|shutil\s*\.\s*(?:copyfile|copyfileobj|copy|copy2|copytree|rmtree|move)\s*\(",
    re.IGNORECASE,
)

_CMD_WORD_WRITE_RE = re.compile(
    r"(?:^|[\s;|&,({])(?:(?<![>&])&(?!&)\s*)?[\"']?(?:del|rm|erase|cp|mv|ren|rename|rmdir|rd|sc|ac|ni|ri|si|copy|move)[\"']?(?=\s)"
    r"|\bcmd(?:\.exe)?\s+/c\s+[\"']?(?:copy|move|ren|rename|del|erase|mkdir|md|rmdir|rd|mklink)\b"
    r"|\btar(?:\.exe)?\b(?:\s+x[vzfjc]*(?=\s)|[^\n;|&]*?(?:\s-[a-z]*x|\s--extract\b))"
    r"|\bexpand-archive\b"
    r"|\bunpack_archive\b"
    r"|\bunzip(?:\.exe)?\b(?![^\n;|&]*\s-[a-z]*(?:l|t)\b)"
    r"|\b7za?(?:\.exe)?\b\s+[xe]\b",
    re.IGNORECASE,
)

_CERT_RE = re.compile(
    r"("
    r"\bCONVERGED_OPTIMAL\b"
    r"|\b\d+\s*/\s*\d+\s+PASS(?:ED)?\b"
    r"|\b100(?:\.0+)?%\s*(?:PASS(?:ED)?|VERIFIED)\b"
    r"|\ball\s+tests?\s+pass(?:ed|ing)?\b"
    r"|\b0\s+fail(?:ed|ures?)\b"
    r"|\bEXIT[_\s]+(?:CODE\s+)?0\b"
    r")",
    re.IGNORECASE,
)

_FENCED_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_INLINE_CODE_SPAN_RE = re.compile(r"(`{1,3})([^`\n]+?)\1")
_OPEN_TOKEN_RE = re.compile(r"(?<![a-zA-Z0-9_])open\s*\(", re.IGNORECASE)
_PATH_CTOR_TOKEN_RE = re.compile(
    r"\b(?:pathlib\.)?(?:pure)?(?:posix|windows)?path\s*\(",
    re.IGNORECASE,
)
_PATH_MUTATION_METHOD_RE = re.compile(
    r"^(?:\s*/\s*(?:['\"][^'\"]*['\"]|[a-zA-Z0-9_.-]+|\([^()]*\)))*\s*\)?\s*\.\s*"
    r"(?:write_text|write_bytes|replace|rename|unlink|mkdir|rmdir|touch|chmod|symlink_to|hardlink_to|link_to)\s*\(",
    re.IGNORECASE,
)
_CHAINED_FILE_WRITE_RE = re.compile(
    r"^\s*\.\s*(?:write|writelines|truncate)\s*\(",
    re.IGNORECASE,
)
_READONLY_OPEN_TAIL_RE = re.compile(
    r"^\s*(?:(?:mode\s*=\s*)?['\"]r[bt]?['\"]\s*)?"
    r"(?:,\s*(?:encoding|errors|newline)\s*=\s*['\"][^'\"]*['\"]\s*)*$",
    re.IGNORECASE,
)
_ENCODED_CMD_RE = re.compile(
    r"(?:^|[\s\"';|&])-(?:encodedcommand|enc|ec)\b"
    r"|\b(?:powershell|pwsh)(?:\.exe)?\b[^\n\r;|&]*?(?:^|[\s\"'])[-/]"
    r"(?:e|ec|en(?:c(?:o(?:d(?:e(?:d(?:c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?)?)?)?)?)?)?)\b",
    re.IGNORECASE,
)
_PS_COMMAND_WRAPPER_RE = re.compile(
    r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n\r;|&]*?(?:^|[\s\"'])[-/]"
    r"c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_CMD_C_WRAPPER_RE = re.compile(
    r"\bcmd(?:\.exe)?\s+/[ck]\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_DYNAMIC_PS_EXEC_RE = re.compile(
    r"(?:^|[\s;|&({])(?:invoke-expression|iex)(?:\s+|\(|[\"'])"
    r"|(?:^|[\s;|({])(?<![>&])&(?!&)\s*(?:\(|\$[a-zA-Z_{])",
    re.IGNORECASE,
)
_PS_CALL_WRITE_RE = re.compile(
    r"(?:^|[\s;|({])(?<![>&])&(?!&)\s*[\"']?"
    r"(?:set-content|add-content|out-file|set-item|remove-item|copy-item|move-item|"
    r"new-item|clear-content|rename-item|tee-object|start-process|robocopy|xcopy|mklink|"
    r"del|rm|erase|cp|mv|ren|rename|rmdir|rd|sc|ac|ni|ri|si|copy|move)[\"']?(?=$|[\s\"';|&)])",
    re.IGNORECASE,
)
_DESTRUCTIVE_GIT_RE = re.compile(
    r"\bgit\s+(?:"
    r"reset\s+[^\n;|&]*--hard\b"
    r"|clean\s+[^\n;|&]*(?:-[a-zA-Z]*f[a-zA-Z]*|--force)\b"
    r"|checkout\s+(?:--\s+|\.|-(?:f|-force)\b|(?:HEAD\s+--\s+)|(?:[^\n;|&]*\b(?:scripts|\.agents|src_app|tests|nk_tracking|nk_genome)\b))"
    r"|restore\s+(?!--staged\b)[^\n;|&]*"
    r")",
    re.IGNORECASE,
)
_PROTECTED_DIR_CMD_RE = re.compile(
    r"(?:^|[\s\"'/\\,;()\[\]=])(?:scripts|\.agents|nk_genome|schemas)(?:$|[\s\"'/\\,;()\[\]])"
    r"|(?:^|[\s\"'/\\,;()\[\]=])(?:agents|gemini)\.md(?:$|[\s\"'/\\,;()\[\]])",
    re.IGNORECASE,
)
_UNSTAGE_CODE_DIR_CMD_RE = re.compile(
    r"(?:^|[\s\"'/\\,;()\[\]=])(?:src_app|tests|app|src|core)(?:$|[\s\"'/\\,;()\[\]])"
    r"|checkpoint_|patch_notes\.md|quality_baseline\.json",
    re.IGNORECASE,
)
_FS_PATH_PREFIX_RE = re.compile(
    r"^(?:[a-zA-Z]:[/\\]|/|\\|\./|\.\\|\.\./|\.\.\\|"
    r"(?:scripts|\.agents|nk_tracking|nk_genome|tests|\.staging|src_app|app|src|core|nk_external_projects)[/\\])",
    re.IGNORECASE,
)
_SHELL_CMD_START_RE = re.compile(
    r"^(?:(?<![>&])&(?!&)\s*|[\"']?[^\s\"']*?(?:python(?:3)?|py|powershell|pwsh|cmd|robocopy|xcopy)(?:\.exe)?[\"']?(?:\s|$)|"
    r"(?:out-file|set-content|add-content|set-item|tee-object|copy-item|move-item|new-item|"
    r"remove-item|clear-content|rename-item|start-process|git|tar|unzip|expand-archive|7z|7za)\b|"
    r"(?:sc|ac|ni|ri|si|del|rm|cp|mv|ren|rmdir|rd)\s|"
    r"\[(?:system\.)?io\.(?:file|streamwriter|directory)\])",
    re.IGNORECASE,
)
_SAFE_CONV_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_PY_EXE_TOK_RE = (
    r'(?:"[^"\n\r;|&<>`]*(?:[/\\])?(?:python(?:3)?|py)(?:\.exe)?"|'
    r"'[^'\n\r;|&<>`]*(?:[/\\])?(?:python(?:3)?|py)(?:\.exe)?'|"
    r"(?:[^\s\"';|&<>`]*[/\\])?(?:python(?:3)?|py)(?:\.exe)?)"
)
_SCRIPTS_PY_TOK_RE = (
    r'(?:"(?:[^"\n\r;|&<>`]*[/\\])?scripts[/\\][a-zA-Z0-9_.-]+\.py"|'
    r"'(?:[^'\n\r;|&<>`]*[/\\])?scripts[/\\][a-zA-Z0-9_.-]+\.py'|"
    r"(?:[^\s\"';|&<>`]*[/\\])?scripts[/\\][a-zA-Z0-9_.-]+\.py)"
)
_SAFE_SI_CMD_START_RE = re.compile(
    rf"^\s*{_PY_EXE_TOK_RE}(?:\s+-[BSu]+)*\s+{_SCRIPTS_PY_TOK_RE}(?=\s|$)",
    re.IGNORECASE,
)
_SAFE_SI_QUOTED_ARG_RE = re.compile(
    r"(--(?:prompt|text|content|message|reason)\s+)(?:\"si\"|'si')(?=$|\s)",
    re.IGNORECASE,
)
_SAFE_SI_FORBIDDEN_RE = re.compile(
    r"[;&|<>\n\r`]|"
    r"\$\(|\$\{|"
    r'\\["\']|'
    r"(?:^|\s)--[a-zA-Z0-9_-]+=|"
    r"(?:^|\s)-(?:e|ec|enc|encodedcommand)\b|"
    r"\b(?:powershell|pwsh|cmd)(?:\.exe)?\b|"
    r"(?:^|\s)iex\b|\binvoke-expression\b",
    re.IGNORECASE,
)
_PROMPT_FLAG_SCAN_RE = re.compile(
    r"(--(?:prompt-text|prompt|text|content|message|reason))(\s+)([\"'])",
    re.IGNORECASE,
)
_PROMPT_SHELL_HAZARD_RE = re.compile(
    r"[\n\r`]|"
    r"\$\(|\$\{|"
    r"(?:^|\s)-(?:e|ec|enc|encodedcommand)\b|"
    r"\b(?:powershell|pwsh|cmd)(?:\.exe)?\b|"
    r"(?:^|\s)iex\b|\binvoke-expression\b",
    re.IGNORECASE,
)
_AUTH_PY_TOK_RE = (
    r'(?:"[^"\n\r;|&<>`]*?(?:python(?:3)?|py)(?:\.exe)?"|'
    r"'[^'\n\r;|&<>`]*?(?:python(?:3)?|py)(?:\.exe)?'|"
    r"(?:[^\s\"';|&<>`]*?)(?:python(?:3)?|py)(?:\.exe)?)"
)
_AUTH_SCRIPT_TOK_RE = (
    r'(?:"(?:[^"\n\r;|&<>`]*?/)?(?:\.staging/)?scripts/(?:win32_2pc_engine|nk_registry_indexer|healing_snapshot_rollback|ast_repo_mapper|ast_guard_validator|dast_sandbox_runner|nk_transcript_tools)\.py"|'
    r"'(?:[^'\n\r;|&<>`]*?/)?(?:\.staging/)?scripts/(?:win32_2pc_engine|nk_registry_indexer|healing_snapshot_rollback|ast_repo_mapper|ast_guard_validator|dast_sandbox_runner|nk_transcript_tools)\.py'|"
    r"(?:[^\s\"';|&<>`]*?/)?(?:\.staging/)?scripts/(?:win32_2pc_engine|nk_registry_indexer|healing_snapshot_rollback|ast_repo_mapper|ast_guard_validator|dast_sandbox_runner|nk_transcript_tools)\.py)"
)
_AUTH_SCRIPT_RE = re.compile(
    rf"^\s*{_AUTH_PY_TOK_RE}\s+(?:-[a-zA-Z0-9]+\s+)*{_AUTH_SCRIPT_TOK_RE}(?=$|\s)",
    re.IGNORECASE,
)
_MCP_MUTATING_TOOL_RE = re.compile(
    r"(?:^|[_-])(?:write|edit|append|create|update|delete|remove|unlink|rmdir|mkdir|"
    r"move|rename|copy|patch|replace|modify|exec|execute|shell|bash|powershell|pwsh|"
    r"cmd|command|run_command|run_script|spawn|deploy|init|login|logout|touch|chmod|chown|"
    r"put_file|save_file|write_file|edit_file)(?:$|[_-])",
    re.IGNORECASE,
)
