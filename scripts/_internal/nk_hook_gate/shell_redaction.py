"""Mascheramento letterali sicuri e verifica Python open()/Path() per HookGateV2."""

from __future__ import annotations

import re
from typing import List, Tuple

from _internal.nk_hook_gate.constants import (
    _CHAINED_FILE_WRITE_RE,
    _CMD_C_WRAPPER_RE,
    _ENCODED_CMD_RE,
    _OPEN_TOKEN_RE,
    _PATH_CTOR_TOKEN_RE,
    _PATH_MUTATION_METHOD_RE,
    _PROMPT_FLAG_SCAN_RE,
    _PROMPT_SHELL_HAZARD_RE,
    _PS_COMMAND_WRAPPER_RE,
    _READONLY_OPEN_TAIL_RE,
    _SAFE_SI_CMD_START_RE,
    _SAFE_SI_FORBIDDEN_RE,
    _SAFE_SI_QUOTED_ARG_RE,
)
from _internal.nk_hook_gate.shell_parser import (
    _extract_balanced_parens,
    _split_top_level_args,
)


def _scan_quotes_clean(text: str, allow_backslash_escape: bool) -> bool:
    """Verifica bilanciamento quote e assenza di pipe/redirezioni/catene shell fuori dalle quote."""
    in_q = ""
    idx = 0
    n = len(text)
    while idx < n:
        ch = text[idx]
        if in_q:
            if (
                allow_backslash_escape
                and ch == "\\"
                and idx + 1 < n
                and text[idx + 1] in (in_q, "\\")
            ):
                idx += 2
                continue
            if ch == in_q:
                in_q = ""
            idx += 1
            continue
        if ch in ("'", '"'):
            in_q = ch
            idx += 1
            continue
        if ch in (";", "|", "&", "<", ">", "`", "\n", "\r"):
            return False
        if ch == "$" and idx + 1 < n and text[idx + 1] in ("(", "{"):
            return False
        idx += 1
    return in_q == ""


def _has_non_readonly_open(cmd_str: str) -> bool:
    """Rileva chiamate open(...) con argomenti di scrittura o dinamici usando parentesi bilanciate."""
    if "open" not in cmd_str.lower():
        return False
    for match in _OPEN_TOKEN_RE.finditer(cmd_str):
        paren_idx = match.end() - 1
        bal = _extract_balanced_parens(cmd_str, paren_idx)
        if bal is None:
            return True
        inner, after_idx = bal
        if _CHAINED_FILE_WRITE_RE.match(cmd_str[after_idx:]):
            return True

        prefix = cmd_str[: match.start()].rstrip()
        has_dot = prefix.endswith(".")
        prev_ident = ""
        if has_dot:
            m_prev = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\.$", prefix)
            if m_prev:
                prev_ident = m_prev.group(1).lower()

        top_args = _split_top_level_args(inner.strip()) if inner.strip() else []

        if has_dot and prev_ident == "os":
            inner_low = inner.lower()
            if any(
                f in inner_low
                for f in ("o_wronly", "o_creat", "o_rdwr", "o_trunc", "o_append")
            ):
                return True
            if (
                len(top_args) >= 2
                and top_args[1].strip().lower() not in ("0", "os.o_rdonly", "o_rdonly")
            ):
                return True
            continue

        if has_dot and prev_ident not in ("io", "_io", "builtins", "codecs"):
            if top_args:
                tail = ", ".join(top_args)
                if not _READONLY_OPEN_TAIL_RE.match(tail):
                    return True
            continue

        if len(top_args) >= 2:
            tail = ", ".join(top_args[1:])
            if not _READONLY_OPEN_TAIL_RE.match(tail):
                return True
        elif len(top_args) == 1 and re.match(
            r"^mode\s*=", top_args[0], re.IGNORECASE
        ):
            if not _READONLY_OPEN_TAIL_RE.match(top_args[0]):
                return True
    return False


def _has_balanced_path_mutation(cmd_str: str) -> bool:
    """Rileva mutazioni su oggetti Path(...) con argomenti annidati tramite parentesi bilanciate."""
    if "path" not in cmd_str.lower():
        return False
    for match in _PATH_CTOR_TOKEN_RE.finditer(cmd_str):
        paren_idx = match.end() - 1
        bal = _extract_balanced_parens(cmd_str, paren_idx)
        if bal is None:
            return True
        _, after_idx = bal
        if _PATH_MUTATION_METHOD_RE.match(cmd_str[after_idx:]):
            return True
    return False


def _redact_safe_si_literals(raw_cmd: str, cand_s: str) -> str:
    """Esenta il solo 'si' quotato in --prompt/--text/--content/--message/--reason su scripts/ dopo fail-closed."""
    if not raw_cmd or not cand_s:
        return cand_s
    for text in (raw_cmd, cand_s):
        if _SAFE_SI_FORBIDDEN_RE.search(text):
            return cand_s
        if (
            _ENCODED_CMD_RE.search(text)
            or _CMD_C_WRAPPER_RE.search(text)
            or _PS_COMMAND_WRAPPER_RE.search(text)
        ):
            return cand_s
    m_raw = _SAFE_SI_CMD_START_RE.match(raw_cmd)
    m_cand = _SAFE_SI_CMD_START_RE.match(cand_s)
    if not m_raw or not m_cand:
        return cand_s
    if ".." in m_raw.group(0) or ".." in m_cand.group(0):
        return cand_s
    return _SAFE_SI_QUOTED_ARG_RE.sub(r'\1"__SAFE_SI__"', cand_s)


def _mask_balanced_prompt_payloads(raw_cmd: str, cand_s: str) -> str:
    """Maschera payload testuali quotati e bilanciati di flag prompt su scripts/*.py prima del solo word-check."""
    if not raw_cmd or not cand_s:
        return cand_s
    for text in (raw_cmd, cand_s):
        if _PROMPT_SHELL_HAZARD_RE.search(text):
            return cand_s
        if (
            _ENCODED_CMD_RE.search(text)
            or _CMD_C_WRAPPER_RE.search(text)
            or _PS_COMMAND_WRAPPER_RE.search(text)
        ):
            return cand_s
        if not _scan_quotes_clean(text, allow_backslash_escape=True):
            return cand_s
        if not _scan_quotes_clean(text, allow_backslash_escape=False):
            return cand_s
    m_raw = _SAFE_SI_CMD_START_RE.match(raw_cmd)
    m_cand = _SAFE_SI_CMD_START_RE.match(cand_s)
    if not m_raw or not m_cand:
        return cand_s
    if ".." in m_raw.group(0) or ".." in m_cand.group(0):
        return cand_s

    spans: List[Tuple[int, int]] = []
    in_q = ""
    idx = 0
    n = len(cand_s)
    while idx < n:
        ch = cand_s[idx]
        if in_q:
            if (
                ch == "\\"
                and idx + 1 < n
                and cand_s[idx + 1] in (in_q, "\\")
            ):
                idx += 2
                continue
            if ch == in_q:
                in_q = ""
            idx += 1
            continue
        if cand_s[idx] == "-":
            can_start_flag = idx == 0 or cand_s[idx - 1].isspace()
            if can_start_flag:
                m_flag = _PROMPT_FLAG_SCAN_RE.match(cand_s, idx)
                if m_flag:
                    q_start = idx + len(m_flag.group(1)) + len(m_flag.group(2))
                    q_char = m_flag.group(3)
                    j = q_start + 1
                    closed = False
                    while j < n:
                        c2 = cand_s[j]
                        if (
                            c2 == "\\"
                            and j + 1 < n
                            and cand_s[j + 1] in (q_char, "\\")
                        ):
                            j += 2
                            continue
                        if c2 == q_char:
                            j += 1
                            closed = True
                            break
                        j += 1
                    if closed and (j == n or cand_s[j].isspace()):
                        spans.append((q_start, j))
                        idx = j
                        continue
        if ch in ("'", '"'):
            in_q = ch
        idx += 1

    if not spans:
        return cand_s
    out_parts: List[str] = []
    prev = 0
    for s_idx, e_idx in spans:
        out_parts.append(cand_s[prev:s_idx])
        out_parts.append('"__SAFE_PROMPT__"')
        prev = e_idx
    out_parts.append(cand_s[prev:])
    return "".join(out_parts)
