"""Mascheramento letterali sicuri e verifica Python open()/Path() per HookGateV2."""

from __future__ import annotations

import ast
import re
from typing import Dict, List, Optional, Tuple

from _internal.nk_hook_gate.constants import (
    _CHAINED_FILE_WRITE_RE, _CMD_C_WRAPPER_RE, _ENCODED_CMD_RE, _OPEN_TOKEN_RE,
    _PATH_CTOR_TOKEN_RE, _PATH_MUTATION_METHOD_RE, _PROMPT_FLAG_SCAN_RE,
    _PROMPT_SHELL_HAZARD_RE, _PS_COMMAND_WRAPPER_RE, _READONLY_OPEN_TAIL_RE,
    _SAFE_SI_CMD_START_RE, _SAFE_SI_FORBIDDEN_RE, _SAFE_SI_QUOTED_ARG_RE,
)
from _internal.nk_hook_gate.shell_parser import _extract_balanced_parens, _split_top_level_args


def _scan_quotes_clean(text: str, allow_backslash_escape: bool) -> bool:
    """Verifica bilanciamento quote e assenza di pipe/redirezioni/catene shell fuori dalle quote."""
    in_q = ""
    idx = 0
    n = len(text)
    while idx < n:
        ch = text[idx]
        if in_q:
            # In single-quote PowerShell/POSIX il backslash resta letterale e non esegue escape.
            if allow_backslash_escape and in_q == '"' and ch == "\\" and idx + 1 < n and text[idx + 1] in ('"', "\\"):
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
        if ch in (";", "|", "&", "<", ">", "`", "\n", "\r", "(", ")", "{", "}"):
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
            if any(f in inner_low for f in ("o_wronly", "o_creat", "o_rdwr", "o_trunc", "o_append")):
                return True
            if len(top_args) >= 2 and top_args[1].strip().lower() not in ("0", "os.o_rdonly", "o_rdonly"):
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
        if _ENCODED_CMD_RE.search(text) or _CMD_C_WRAPPER_RE.search(text) or _PS_COMMAND_WRAPPER_RE.search(text):
            return cand_s
    m_raw = _SAFE_SI_CMD_START_RE.match(raw_cmd)
    m_cand = _SAFE_SI_CMD_START_RE.match(cand_s)
    if not m_raw or not m_cand:
        return cand_s
    if ".." in m_raw.group(0) or ".." in m_cand.group(0):
        return cand_s
    return _SAFE_SI_QUOTED_ARG_RE.sub(r'\1"__SAFE_SI__"', cand_s)


def _mask_balanced_prompt_payloads(raw_cmd: str, cand_s: str) -> str:
    """Maschera payload testuali quotati e bilanciati di flag prompt su scripts/*.py prima dei word-check."""
    if not raw_cmd or not cand_s:
        return cand_s
    for text in (raw_cmd, cand_s):
        if _PROMPT_SHELL_HAZARD_RE.search(text):
            return cand_s
        if _ENCODED_CMD_RE.search(text) or _CMD_C_WRAPPER_RE.search(text) or _PS_COMMAND_WRAPPER_RE.search(text):
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
                in_q == '"'
                and ch == "\\"
                and idx + 1 < n
                and cand_s[idx + 1] in ('"', "\\")
            ):
                idx += 2
                continue
            if in_q == "'" and ch == "'" and idx + 1 < n and cand_s[idx + 1] == "'":
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
                            q_char == '"'
                            and c2 == "\\"
                            and j + 1 < n
                            and cand_s[j + 1] in ('"', "\\")
                        ):
                            j += 2
                            continue
                        if c2 == q_char:
                            if q_char == "'" and j + 1 < n and cand_s[j + 1] == "'":
                                j += 2
                                continue
                            j += 1
                            closed = True
                            break
                        j += 1
                    if closed and (j == n or cand_s[j].isspace()):
                        raw_span = cand_s[q_start:j]
                        if q_char == '"' and '\\"' in raw_span and any(
                            op in raw_span
                            for op in ("(", ")", ";", "|", "&", "<", ">", "`", "$", "{", "}")
                        ):
                            return cand_s
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


def build_ast_symtab(tree: ast.AST) -> Dict[str, List[ast.AST]]:
    """Indicizza gli assegnamenti AST locali per risolvere percorsi bound a variabili."""
    symtab: Dict[str, List[ast.AST]] = {}
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Assign):
            for tgt in sub.targets:
                if isinstance(tgt, ast.Name):
                    symtab.setdefault(tgt.id, []).append(sub.value)
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and sub.value is not None:
            symtab.setdefault(sub.target.id, []).append(sub.value)
    return symtab


def _combine_ast_str_pairs(left: List[str], right: List[str], is_div: bool) -> List[str]:
    """Combina liste di prefissi/suffissi per concatenazione (+) o Path join (/)."""
    sep = "/" if is_div else ""
    out: List[str] = []
    for l_val in left[:4]:
        for r_val in right[:4]:
            item = f"{l_val.rstrip('/\\')}{sep}{r_val.lstrip('/\\')}" if is_div else f"{l_val}{r_val}"
            if item not in out:
                out.append(item)
    return out


def _resolve_ast_call_literals(node: ast.Call, symtab: Dict[str, List[ast.AST]], depth: int) -> List[str]:
    """Risolve chiamate Path(...), PurePath(...) o os.path.join(...) con argomenti locali."""
    fn_nm = node.func.attr if isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node.func, ast.Name) else "")
    if fn_nm.lower() not in ("path", "posixpath", "windowspath", "purepath", "join") or not node.args:
        return []
    acc = resolve_ast_literals(node.args[0], symtab, depth + 1)
    for arg in node.args[1:]:
        acc = _combine_ast_str_pairs(acc, resolve_ast_literals(arg, symtab, depth + 1), is_div=True)
    return acc


def _resolve_ast_joined_str(node: ast.JoinedStr, symtab: Dict[str, List[ast.AST]], depth: int) -> List[str]:
    """Risolve i segmenti di una f-string AST utilizzando il symtab locale."""
    parts: List[str] = [""]
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            sub = [v.value]
        elif isinstance(v, ast.FormattedValue):
            sub = resolve_ast_literals(v.value, symtab, depth + 1)
        else:
            sub = []
        if not sub:
            return []
        parts = _combine_ast_str_pairs(parts, sub, False)
    return parts


def _resolve_ast_name(node: ast.Name, symtab: Dict[str, List[ast.AST]], depth: int) -> List[str]:
    """Risolve i valori stringa associati a un identificatore nel symtab locale."""
    vals: List[str] = []
    for expr in symtab.get(node.id, [])[:4]:
        for item in resolve_ast_literals(expr, symtab, depth + 1):
            if item not in vals:
                vals.append(item)
    return vals


def _resolve_ast_ifexp(node: ast.IfExp, symtab: Dict[str, List[ast.AST]], depth: int) -> List[str]:
    """Raccoglie tutti i letterali dei rami if-else per controllo fail-closed."""
    vals = list(resolve_ast_literals(node.body, symtab, depth + 1))
    for item in resolve_ast_literals(node.orelse, symtab, depth + 1):
        if item not in vals:
            vals.append(item)
    return vals


def _resolve_ast_subscript(node: ast.Subscript, symtab: Dict[str, List[ast.AST]], depth: int) -> List[str]:
    """Raccoglie i letterali da tuple/liste indicizzate per impedire bypass per indice."""
    container = node.value
    if isinstance(container, ast.Name) and symtab.get(container.id):
        container = symtab[container.id][0]
    if not isinstance(container, (ast.Tuple, ast.List)):
        return []
    vals: List[str] = []
    for elt in container.elts[:8]:
        for item in resolve_ast_literals(elt, symtab, depth + 1):
            if item not in vals:
                vals.append(item)
    return vals


def _resolve_ast_compound(node: ast.AST, symtab: Dict[str, List[ast.AST]], depth: int) -> List[str]:
    """Delega la risoluzione dei nodi AST composti JoinedStr, IfExp, Subscript e Call."""
    if isinstance(node, ast.JoinedStr):
        return _resolve_ast_joined_str(node, symtab, depth)
    if isinstance(node, ast.IfExp):
        return _resolve_ast_ifexp(node, symtab, depth)
    if isinstance(node, ast.Subscript):
        return _resolve_ast_subscript(node, symtab, depth)
    return _resolve_ast_call_literals(node, symtab, depth) if isinstance(node, ast.Call) else []


def resolve_ast_literals(node: ast.AST, symtab: Dict[str, List[ast.AST]], depth: int = 0) -> List[str]:
    """Risolve letterali stringa AST attraverso variabili, Path(), +, /, f-string e contenitori."""
    if depth >= 6:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return _resolve_ast_name(node, symtab, depth)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        return _combine_ast_str_pairs(resolve_ast_literals(node.left, symtab, depth + 1), resolve_ast_literals(node.right, symtab, depth + 1), isinstance(node.op, ast.Div))
    return _resolve_ast_compound(node, symtab, depth)


def collect_resolved_ast_hints(node: ast.AST, symtab: Dict[str, List[ast.AST]], depth: int = 0) -> List[str]:
    """Raccoglie hint testuali dal sottoalbero AST espandendo i riferimenti locali in symtab."""
    if depth >= 6:
        return []
    hints: List[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            hints.append(sub.value)
        elif isinstance(sub, ast.Name):
            hints.append(sub.id)
            for bound in symtab.get(sub.id, [])[:4]:
                hints.extend(collect_resolved_ast_hints(bound, symtab, depth + 1))
        elif isinstance(sub, ast.Attribute):
            hints.append(sub.attr)
    return hints


_UNSAFE_DYN_AST_TYPES = (
    ast.Subscript, ast.IfExp, ast.Tuple, ast.List, ast.Dict, ast.Set,
    ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
)
_SAFE_DYN_CALL_NAMES = frozenset(
    ("path", "posixpath", "windowspath", "purepath", "join", "joinpath", "resolve", "expanduser", "gettempdir", "mkdtemp", "str")
)


def _is_unsafe_ast_subnode(sub: ast.AST) -> bool:
    """Rileva costrutti AST dinamici o chiamate non consentite nel target."""
    if isinstance(sub, _UNSAFE_DYN_AST_TYPES):
        return True
    if not isinstance(sub, ast.Call):
        return False
    fn = sub.func
    fn_nm = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
    return fn_nm.lower() not in _SAFE_DYN_CALL_NAMES


def has_unsafe_dynamic_ast(node: ast.AST, symtab: Optional[Dict[str, List[ast.AST]]] = None, depth: int = 0) -> bool:
    """Verifica se target o variabili legate usano indicizzazioni, rami o chiamate dinamiche."""
    if depth >= 6:
        return False
    for sub in ast.walk(node):
        if _is_unsafe_ast_subnode(sub):
            return True
        if symtab and isinstance(sub, ast.Name) and any(
            has_unsafe_dynamic_ast(b, symtab, depth + 1) for b in symtab.get(sub.id, [])[:4]
        ):
            return True
    return False
