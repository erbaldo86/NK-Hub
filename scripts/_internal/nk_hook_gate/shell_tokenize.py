"""Tokenizzazione lessicale shell/PowerShell e bilanciamento parentesi per HookGateV2."""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from _internal.nk_hook_gate.constants import _CMD_C_WRAPPER_RE, _PS_COMMAND_WRAPPER_RE, _strip_wrapping_quotes
from _internal.nk_hook_gate.constants_patterns import extract_ps_command_payload, extract_ps_positional_payload


def _norm_cmd_verb(tok: str) -> str:
    """Normalizza il nome di un eseguibile shell eliminando &, percorso e suffisso .exe."""
    cleaned = _strip_wrapping_quotes(tok).lstrip("&").strip("\"'").replace("\\", "/")
    base = os.path.basename(cleaned).lower()
    return base[:-4] if base.endswith(".exe") else base


def _has_unquoted_ps_backtick_obfuscation(cmd_str: str) -> bool:
    """Rileva backtick di offuscamento PowerShell fuori dalle stringhe quotate."""
    if "`" not in cmd_str:
        return False
    in_single = False
    in_double = False
    idx = 0
    n = len(cmd_str)
    while idx < n:
        ch = cmd_str[idx]
        if in_single:
            if ch == "'":
                in_single = False
            idx += 1
            continue
        if in_double:
            if ch == "\\" and idx + 1 < n and cmd_str[idx + 1] in ('"', "\\"):
                idx += 2
                continue
            if ch == "`" and idx + 1 < n:
                idx += 2
                continue
            if ch == '"':
                in_double = False
            idx += 1
            continue
        if ch == "'":
            in_single = True
            idx += 1
            continue
        if ch == '"':
            in_double = True
            idx += 1
            continue
        if ch == "`" and idx + 1 < n and re.match(r"[a-zA-Z0-9_./\\:-]", cmd_str[idx + 1]):
            return True
        idx += 1
    return False


def _deobfuscate_ps_backticks(cmd_str: str) -> str:
    """Rimuove i backtick di offuscamento PowerShell fuori dalle stringhe a singolo apice."""
    if "`" not in cmd_str:
        return cmd_str
    out: List[str] = []
    in_single = False
    idx = 0
    n = len(cmd_str)
    while idx < n:
        ch = cmd_str[idx]
        if in_single:
            if ch == "'":
                in_single = False
            out.append(ch)
            idx += 1
            continue
        if ch == "'":
            in_single = True
            out.append(ch)
            idx += 1
            continue
        if ch == "`" and idx + 1 < n and re.match(r"[a-zA-Z0-9_./\\:-]", cmd_str[idx + 1]):
            idx += 1
            continue
        out.append(ch)
        idx += 1
    return "".join(out)


def _split_shell_segments(cmd_str: str) -> List[str]:
    """Divide il comando su separatori shell non quotati (| || && ; newline &) preservando 2>&1."""
    if not cmd_str:
        return []
    segments: List[str] = []
    curr: List[str] = []
    in_single = False
    in_double = False
    idx = 0
    n = len(cmd_str)
    while idx < n:
        ch = cmd_str[idx]
        if in_single:
            curr.append(ch)
            if ch == "'":
                in_single = False
            idx += 1
            continue
        if in_double:
            curr.append(ch)
            if ch == "\\" and idx + 1 < n and cmd_str[idx + 1] in ('"', "\\"):
                curr.append(cmd_str[idx + 1])
                idx += 2
                continue
            if ch == "`" and idx + 1 < n:
                curr.append(cmd_str[idx + 1])
                idx += 2
                continue
            if ch == '"':
                in_double = False
            idx += 1
            continue
        if ch == "'":
            in_single = True
            curr.append(ch)
            idx += 1
            continue
        if ch == '"':
            in_double = True
            curr.append(ch)
            idx += 1
            continue
        if ch in (";", "\n", "\r"):
            seg = "".join(curr).strip()
            if seg:
                segments.append(seg)
            curr = []
            idx += 1
            continue
        if ch == "|":
            seg = "".join(curr).strip()
            if seg:
                segments.append(seg)
            curr = []
            idx += 2 if (idx + 1 < n and cmd_str[idx + 1] == "|") else 1
            continue
        if ch == "&":
            prev_ch = cmd_str[idx - 1] if idx > 0 else ""
            if prev_ch in (">", "<"):
                curr.append(ch)
                idx += 1
                continue
            if idx + 1 < n and cmd_str[idx + 1] == "&":
                seg = "".join(curr).strip()
                if seg:
                    segments.append(seg)
                curr = []
                idx += 2
                continue
            seg = "".join(curr).strip()
            if seg:
                segments.append(seg)
            curr = ["&"]
            idx += 1
            continue
        curr.append(ch)
        idx += 1
    tail = "".join(curr).strip()
    if tail:
        segments.append(tail)
    return segments


def _tokenize_shell_tokens(seg: str) -> Optional[List[Tuple[str, str, bool]]]:
    """Tokenizza una riga shell rispettando le quote e restituendo (raw, unquoted, was_quoted) o None."""
    tokens: List[Tuple[str, str, bool]] = []
    n = len(seg)
    idx = 0
    while idx < n:
        while idx < n and seg[idx].isspace():
            idx += 1
        if idx >= n:
            break
        start = idx
        unq: List[str] = []
        was_quoted = False
        in_q = ""
        while idx < n:
            ch = seg[idx]
            if in_q:
                if (
                    in_q == '"'
                    and ch == "\\"
                    and idx + 1 < n
                    and seg[idx + 1] in ('"', "\\")
                ):
                    unq.append(seg[idx + 1])
                    idx += 2
                    continue
                if in_q == '"' and ch == "`" and idx + 1 < n:
                    unq.append(seg[idx + 1])
                    idx += 2
                    continue
                if ch == in_q:
                    in_q = ""
                    idx += 1
                    continue
                unq.append(ch)
                idx += 1
                continue
            if ch.isspace():
                break
            if ch in ("'", '"'):
                in_q = ch
                was_quoted = True
                idx += 1
                continue
            unq.append(ch)
            idx += 1
        if in_q:
            return None
        tokens.append((seg[start:idx], "".join(unq), was_quoted))
    return tokens


def _extract_leading_quoted(text: str) -> str:
    """Estrae il payload dalla prima stringa quotata se seguita da fine o operatore shell."""
    if len(text) < 2 or text[0] not in ('"', "'"):
        return ""
    q, idx, n = text[0], 1, len(text)
    while idx < n:
        ch = text[idx]
        if q == '"' and ((ch == "\\" and idx + 1 < n and text[idx + 1] in ('"', "\\")) or (ch == "`" and idx + 1 < n)):
            idx += 2
            continue
        if ch == q:
            return text[1:idx].strip() if (idx + 1 == n or text[idx + 1] in " \t&|;\n\r)") else ""
        idx += 1
    return ""


def _clean_wrapped_inner(raw: str) -> str:
    """Normalizza il payload estratto da wrapper shell rimuovendo quote esterne, escape o graffe."""
    inner = raw.strip()
    if inner.startswith(('\\"', '`"')):
        inner = inner.replace('\\"', '"').replace('`"', '"')
    inner = _extract_leading_quoted(inner) or _strip_wrapping_quotes(inner)
    if '\\"' in inner or '`"' in inner:
        inner = inner.replace('\\"', '"').replace('`"', '"')
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1].strip()
    return inner


def _append_ps_positional(chunk: str, text: str, found: List[str]) -> None:
    """Aggiunge il payload posizionale o multi-argomento PowerShell se non duplicato."""
    toks = _tokenize_shell_tokens(chunk)
    pos_raw, is_multi = extract_ps_command_payload(toks, _norm_cmd_verb) if toks else ("", False)
    pos_inner = pos_raw if is_multi else _clean_wrapped_inner(pos_raw)
    if pos_inner and pos_inner != text and pos_inner not in found:
        found.append(pos_inner)


def _unwrap_shell_once(text: str) -> List[str]:
    """Estrae un livello di comandi annidati da powershell -c, cmd /c o scriptblock & {...}."""
    found: List[str] = []
    deobf = _deobfuscate_ps_backticks(text)
    targets = [deobf, *(s for s in _split_shell_segments(deobf) if s != deobf)]
    for chunk in targets:
        for rx in (_PS_COMMAND_WRAPPER_RE, _CMD_C_WRAPPER_RE):
            m = rx.search(chunk)
            inner = _clean_wrapped_inner(m.group(1)) if m else ""
            if inner and inner != text and inner not in found:
                found.append(inner)
        _append_ps_positional(chunk, text, found)
    for m_sb in re.finditer(r"(?<![>&])&(?!&)\s*\{([^{}]*)\}", deobf):
        sb_body = m_sb.group(1).strip()
        if sb_body and sb_body not in found:
            found.append(sb_body)
    return found


def _unwrap_shell_subcommands(cmd_str: str) -> List[str]:
    """Estrae ricorsivamente (fino a 4 livelli) comandi annidati powershell -c, cmd /c e & {...}."""
    subcommands: List[str] = []
    seen = {cmd_str}
    frontier = [cmd_str]
    for _ in range(4):
        candidates = [i for cur in frontier for i in _unwrap_shell_once(cur)]
        next_frontier = [i for i in dict.fromkeys(candidates) if i not in seen]
        if not next_frontier:
            break
        seen.update(next_frontier)
        subcommands.extend(next_frontier)
        frontier = next_frontier
    return subcommands


def _extract_balanced_parens(text: str, open_paren_idx: int) -> Optional[Tuple[str, int]]:
    """Estrae il contenuto tra parentesi bilanciate rispettando apici e sequenze di escape."""
    if open_paren_idx >= len(text) or text[open_paren_idx] != "(":
        return None
    depth = 1
    in_single = False
    in_double = False
    idx = open_paren_idx + 1
    n = len(text)
    while idx < n:
        ch = text[idx]
        if in_single:
            if ch == "\\" and idx + 1 < n:
                idx += 2
                continue
            if ch == "'":
                in_single = False
            idx += 1
            continue
        if in_double:
            if ch == "\\" and idx + 1 < n:
                idx += 2
                continue
            if ch == '"':
                in_double = False
            idx += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1 : idx], idx + 1
        idx += 1
    return None


def _split_top_level_args(inner: str) -> List[str]:
    """Divide gli argomenti separati da virgola solo al livello zero di annidamento."""
    args: List[str] = []
    curr: List[str] = []
    p_depth = 0
    b_depth = 0
    c_depth = 0
    in_single = False
    in_double = False
    idx = 0
    n = len(inner)
    while idx < n:
        ch = inner[idx]
        if in_single:
            curr.append(ch)
            if ch == "\\" and idx + 1 < n:
                curr.append(inner[idx + 1])
                idx += 2
                continue
            if ch == "'":
                in_single = False
            idx += 1
            continue
        if in_double:
            curr.append(ch)
            if ch == "\\" and idx + 1 < n:
                curr.append(inner[idx + 1])
                idx += 2
                continue
            if ch == '"':
                in_double = False
            idx += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "(":
            p_depth += 1
        elif ch == ")" and p_depth > 0:
            p_depth -= 1
        elif ch == "[":
            b_depth += 1
        elif ch == "]" and b_depth > 0:
            b_depth -= 1
        elif ch == "{":
            c_depth += 1
        elif ch == "}" and c_depth > 0:
            c_depth -= 1
        elif ch == "," and p_depth == 0 and b_depth == 0 and c_depth == 0:
            args.append("".join(curr).strip())
            curr = []
            idx += 1
            continue
        curr.append(ch)
        idx += 1
    tail_arg = "".join(curr).strip()
    if tail_arg or args:
        args.append(tail_arg)
    return args
