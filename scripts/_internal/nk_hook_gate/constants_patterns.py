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
    r"(?:^|[\s;|&,({])(?:(?<![>&])&(?!&)\s*)?[\"']?(?:del|rm|erase|cp|mv|ren|rename|rmdir|rd|sc|ac|ni|ri|si|cpi|mi|rni|clc|tee|mkdir|md|copy|move)[\"']?(?=\s)"
    r"|(?:^|[\s;|&,({\"'\\/:])(?:cmd(?:\.exe)?|%comspec%)[\"']?(?:\s+|(?=/))(?:/[a-z](?::[a-z0-9]+)?\s*)*/[ckr]\s*[\"']?(?:copy|move|ren|rename|del|erase|mkdir|md|rmdir|rd|mklink)\b"
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
    r"(?:^|[\s;|&,({\"'\\/:])(?:powershell|pwsh)(?:\.exe)?[\"']?[^\n\r;|&]*?(?:^|[\s\"'])[-/]"
    r"c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?(?:\s+|:\s*)(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_CMD_C_WRAPPER_RE = re.compile(
    r'(?:^|[\s;|&,({"\'\\/:])(?:cmd(?:\.exe)?|%comspec%)["\']?(?:\s+|(?=/))(?:/[a-z](?::[a-z0-9]+)?\s*)*/[ckr](?:\s+|(?=["\'(]|\\"|`"))(.+)$',
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
    r"del|rm|erase|cp|mv|ren|rename|rmdir|rd|sc|ac|ni|ri|si|cpi|mi|rni|clc|tee|mkdir|md|copy|move)[\"']?(?=$|[\s\"';|&)])",
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
    r"(?:scripts|\.agents|nk_tracking|nk_genome|tests|\.staging|src_app|app|src|core|nk_external_projects|nk\s+proget)[/\\])",
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
_AUTH_SCRIPT_NAMES = (
    r"(?:win32_2pc_engine|nk_registry_indexer|healing_snapshot_rollback|"
    r"ast_repo_mapper|ast_guard_validator|dast_sandbox_runner|"
    r"nk_transcript_tools|vibe_sprint_router|external_project_scaffolder|builder_mutation_gate|tensor_rsi)"
)
_AUTH_SCRIPT_TOK_RE = (
    rf'(?:"(?:[^"\n\r;|&<>`]*?/)?(?:\.staging/)?scripts/{_AUTH_SCRIPT_NAMES}\.py"|'
    rf"'(?:[^'\n\r;|&<>`]*?/)?(?:\.staging/)?scripts/{_AUTH_SCRIPT_NAMES}\.py'|"
    rf"(?:[^\s\"';|&<>`]*?/)?(?:\.staging/)?scripts/{_AUTH_SCRIPT_NAMES}\.py)"
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
_WIN32_2PC_CMD_RE = re.compile(r"(?:^|[/\\.])win32_2pc_engine(?:\.py)?$", re.IGNORECASE)
_PROMOTE_VALUE_FLAGS = frozenset((
    "--milestone", "--repo-root", "--staging-dir", "--override-reason", "--governance-token",
    "--sandbox-report", "--root", "--lane-id", "--parent-lane", "--base-seq",
))
_PROMOTE_VALUE_EQ = tuple(f + "=" for f in _PROMOTE_VALUE_FLAGS)
_PROMOTE_ACTION_FLAGS = frozenset(("--promote-staging", "--commit-train", "--consolidate-sublanes"))
_PROMOTE_ACTION_EQ = ("--promote-staging=", "--commit-train=", "--consolidate-sublanes=")
_PROMOTE_IGNORED_VERBS = frozenset((
    "rg", "ripgrep", "grep", "egrep", "fgrep", "select-string", "echo", "write-output", "printf",
))
_PS_VALUE_FLAGS = frozenset((
    "-executionpolicy", "-ep", "-ex", "/executionpolicy", "/ep",
    "-windowstyle", "-w", "-win", "/windowstyle", "/w",
    "-inputformat", "-if", "-inp", "-outputformat", "-of", "-out",
    "-workingdirectory", "-wd", "-configurationname", "-config",
    "-settingsfile", "-custompipename", "-psconsolefile", "-version", "-v",
))
_PS_CMD_FLAG_RE = re.compile(r"^[-/]c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?$", re.IGNORECASE)
_PS_CMD_STDIN_RE = re.compile(r"^[-/](?:c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?|f(?:i(?:l(?:e)?)?)?)[:=]-$", re.IGNORECASE)
_PS_FILE_FLAG_RE = re.compile(r"^[-/]f(?:i(?:l(?:e)?)?)?$", re.IGNORECASE)
_PS_COLON_CMD_RE = re.compile(r"^[-/]c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?:", re.IGNORECASE)
_STDIN_SHELL_VERBS = frozenset(("powershell", "pwsh", "cmd", "%comspec%"))
_CD_SHELL_VERBS = frozenset(("cd", "chdir", "pushd", "push-location", "set-location", "sl"))
_SHELL_SEP_TOKENS = frozenset(("&&", "||", "|", ";", "&"))
_PS_COLON_CMD_PREFIXES = ("-c:", "-command:", "/c:", "/command:")


def has_win32_2pc_promote_tokens(words: list[str]) -> bool:
    """Riconosce invocazioni reali di win32_2pc_engine con --promote-staging, --commit-train o --consolidate-sublanes."""
    idx = 1 if len(words) > 1 and words[0] == "&" else 0
    if idx >= len(words) or words[idx].replace("\\", "/").rsplit("/", 1)[-1].lower() in _PROMOTE_IGNORED_VERBS:
        return False
    saw_eng, saw_prom, skip_next = False, False, False
    for tok in words[idx:]:
        if skip_next:
            skip_next = False
            continue
        low = tok.replace("\\", "/").lower()
        if low in _PROMOTE_VALUE_FLAGS:
            skip_next = True
            continue
        if not low.startswith(_PROMOTE_VALUE_EQ):
            saw_eng = saw_eng or bool(_WIN32_2PC_CMD_RE.search(low))
            saw_prom = saw_prom or low in _PROMOTE_ACTION_FLAGS or low.startswith(_PROMOTE_ACTION_EQ)
    return saw_eng and saw_prom


def _shell_verb_from_tokens(tokens: list[tuple[str, str, bool]], norm_verb_fn) -> tuple[int, str]:
    """Restituisce indice e nome normalizzato del comando (gestendo &, (, {, &"cmd" e %comspec%)."""
    idx = 0
    while idx < len(tokens) and tokens[idx][1] in ("&", "(", "{", "$(", "@("):
        idx += 1
    if idx >= len(tokens):
        return -1, ""
    raw_verb = tokens[idx][1].lstrip("&({").rstrip(")}").strip("\"'")
    if raw_verb.lower() == "%comspec%":
        return idx, "%comspec%"
    return idx, norm_verb_fn(raw_verb)


def _is_explicit_ps_cmd_or_file(low_t: str) -> bool:
    """Riconosce flag espliciti powershell/pwsh -Command/-File o separatore stdin '-'."""
    if low_t == "-" or _PS_CMD_FLAG_RE.match(low_t) or _PS_CMD_STDIN_RE.match(low_t) or _PS_FILE_FLAG_RE.match(low_t):
        return True
    return any(low_t.startswith(p) for p in ("-f:", "-file:", "-f=", "-file=", "-c:", "-command:", "/c:", "/command:"))


def _collect_ps_arg_tokens(tokens: list[tuple[str, str, bool]], start_idx: int) -> list[tuple[str, str, bool]]:
    """Raccoglie i token argomento fino al primo separatore shell non quotato."""
    collected: list[tuple[str, str, bool]] = []
    for tok in tokens[start_idx:]:
        if not tok[2] and tok[1] in _SHELL_SEP_TOKENS:
            break
        collected.append(tok)
    return collected


def _format_ps_payload_tokens(arg_toks: list[tuple[str, str, bool]], prefix_arg: str = "") -> tuple[str, bool]:
    """Unisce gli argomenti multipli PowerShell o preserva il singolo token quotato."""
    if prefix_arg:
        parts = [prefix_arg, *(t[1] for t in arg_toks)]
        return (parts[0], False) if len(parts) == 1 else (" ".join(parts).strip(), True)
    if not arg_toks:
        return "", False
    if len(arg_toks) == 1:
        return arg_toks[0][0], False
    joined = " ".join(t[1] for t in arg_toks).strip()
    if joined.startswith("{") and joined.endswith("}"):
        joined = joined[1:-1].strip()
    return joined, True


def _advance_ps_payload_start(tokens: list[tuple[str, str, bool]], start_idx: int) -> tuple[int, str, bool]:
    """Avanza oltre i flag powershell/pwsh e restituisce (indice_arg, prefix_col, ok)."""
    i = start_idx
    while i < len(tokens):
        raw_t, unq_t, was_q = tokens[i]
        low_t = unq_t.rstrip(")}").lower()
        if not raw_t.startswith(('"', "'")) and _PS_COLON_CMD_RE.match(low_t):
            val = unq_t.split(":", 1)[1].strip()
            return (0, "", False) if val == "-" else (i + 1, val.strip("\"'"), True)
        if was_q or not low_t.startswith(("-", "/")):
            return i, "", True
        if low_t == "--" or _PS_CMD_FLAG_RE.match(low_t):
            return i + 1, "", True
        if _is_explicit_ps_cmd_or_file(low_t):
            return 0, "", False
        i += 2 if low_t in _PS_VALUE_FLAGS else 1
    return i, "", True


def extract_ps_command_payload(tokens: list[tuple[str, str, bool]], norm_verb_fn) -> tuple[str, bool]:
    """Estrae il payload posizionale o multi-argomento da powershell/pwsh."""
    idx, verb = _shell_verb_from_tokens(tokens, norm_verb_fn)
    if verb not in ("powershell", "pwsh"):
        return "", False
    start_i, prefix_arg, ok = _advance_ps_payload_start(tokens, idx + 1)
    if not ok:
        return "", False
    arg_toks = _collect_ps_arg_tokens(tokens, start_i)
    if not prefix_arg and arg_toks and not arg_toks[0][2] and arg_toks[0][1] == "-":
        return "", False
    return _format_ps_payload_tokens(arg_toks, prefix_arg=prefix_arg)


def extract_ps_positional_payload(tokens: list[tuple[str, str, bool]], norm_verb_fn) -> str:
    """Estrae il comando posizionale o -Command da powershell/pwsh (compatibilita)."""
    return extract_ps_command_payload(tokens, norm_verb_fn)[0]


def has_ps_stdin_flag_tokens(tokens: list[tuple[str, str, bool]], norm_verb_fn) -> bool:
    """Rileva esecuzione stdin PowerShell via -Command -, -File - o - finale."""
    idx, verb = _shell_verb_from_tokens(tokens, norm_verb_fn)
    if verb not in ("powershell", "pwsh"):
        return False
    i = idx + 1
    while i < len(tokens):
        _, unq_t, was_q = tokens[i]
        low_t = unq_t.rstrip(")}").lower()
        if (not was_q and low_t == "-") or _PS_CMD_STDIN_RE.match(low_t):
            return True
        if _PS_CMD_FLAG_RE.match(low_t) or _PS_FILE_FLAG_RE.match(low_t):
            return i + 1 < len(tokens) and tokens[i + 1][1].rstrip(")}") == "-"
        if was_q or not low_t.startswith(("-", "/")) or low_t == "--":
            return False
        i += 2 if low_t in _PS_VALUE_FLAGS else 1
    return False


def _iter_unquoted_char_positions(text: str, target_ch: str) -> list[int]:
    """Trova le posizioni non quotate di un carattere operatore (| o <) nella riga shell."""
    positions: list[int] = []
    in_q, idx, n = "", 0, len(text)
    while idx < n:
        ch = text[idx]
        if in_q == '"' and ((ch == "\\" and idx + 1 < n and text[idx + 1] in ('"', "\\")) or (ch == "`" and idx + 1 < n)):
            idx += 2
            continue
        if in_q:
            if ch == in_q:
                in_q = ""
        elif ch in ('"', "'"):
            in_q = ch
        elif ch == target_ch:
            positions.append(idx)
        idx += 1
    return positions


def _iter_unquoted_pipe_rhs(text: str) -> list[str]:
    """Estrae i lati destri delle pipe singole non quotate (ignorando ||)."""
    out: list[str] = []
    for pos in _iter_unquoted_char_positions(text, "|"):
        is_or = (pos > 0 and text[pos - 1] == "|") or (pos + 1 < len(text) and text[pos + 1] == "|")
        if not is_or:
            out.append(text[pos + 1 :].strip())
    return out


def has_stdin_shell_exec(cmd_text: str, split_fn, tokenize_fn, norm_verb_fn) -> bool:
    """Rileva pipe verso shell interattiva, redirezione stdin < o powershell -Command -."""
    for rhs in _iter_unquoted_pipe_rhs(cmd_text):
        first_seg = (split_fn(rhs) or [rhs])[0]
        toks = tokenize_fn(first_seg)
        if toks and _shell_verb_from_tokens(toks, norm_verb_fn)[1] in _STDIN_SHELL_VERBS:
            return True
    for seg in split_fn(cmd_text) or [cmd_text]:
        toks = tokenize_fn(seg)
        if not toks:
            continue
        _, verb = _shell_verb_from_tokens(toks, norm_verb_fn)
        if verb in ("powershell", "pwsh") and has_ps_stdin_flag_tokens(toks, norm_verb_fn):
            return True
        if verb in _STDIN_SHELL_VERBS and _iter_unquoted_char_positions(seg, "<"):
            return True
    return False
