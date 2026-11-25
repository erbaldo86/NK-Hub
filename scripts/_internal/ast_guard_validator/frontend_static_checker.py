# -*- coding: utf-8 -*-
"""Gate statico pure-stdlib per file Frontend (.ts, .tsx, .js, .jsx, .css)."""

from __future__ import annotations

import difflib
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from _internal.ast_guard_validator.frontend_static_rules import (
    FRONTEND_EXTENSIONS,
    _CSS_CUSTOM_PROP_RE,
    _CSS_RULES,
    _INLINE_HEX_RE,
    _JS_TS_RULES,
    _REGEX_PREFIX_KEYWORDS,
    _SKIP_DIRS,
    _TS_BYPASS_COMMENT_RE,
)
from _internal.ast_guard_validator.quality_diff_rules import QualityDiffViolation


def _consume_quoted_span(code: str, start: int, quote: str) -> Tuple[str, int]:
    """Legge una stringa quotata preservando escape e lunghezza righe."""
    chars = [code[start]]
    i = start + 1
    n = len(code)
    while i < n:
        ch = code[i]
        chars.append(ch)
        if ch == "\\" and i + 1 < n:
            chars.append(code[i + 1])
            i += 2
            continue
        i += 1
        if ch == quote:
            break
    return "".join(chars), i


def _consume_block_comment(code: str, start: int) -> Tuple[str, int]:
    """Salta un commento /* ... */ emettendo solo eventuali newline."""
    newlines: List[str] = []
    i = start + 2
    n = len(code)
    while i < n and not (code[i] == "*" and i + 1 < n and code[i + 1] == "/"):
        if code[i] == "\n":
            newlines.append("\n")
        i += 1
    return "".join(newlines), min(n, i + 2)


def _try_consume_regex_literal(code: str, start: int) -> Optional[Tuple[str, int]]:
    """Legge un literal regex /.../flags su singola riga rispettando escape e classi [...]."""
    n = len(code)
    j = start + 1
    in_class = False
    while j < n:
        ch = code[j]
        if ch in ("\n", "\r"):
            return None
        if ch == "\\":
            if j + 1 < n and code[j + 1] not in ("\n", "\r"):
                j += 2
                continue
            return None
        if ch == "[":
            in_class = True
        elif ch == "]" and in_class:
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            while j < n and code[j].isalpha():
                j += 1
            return code[start:j], j
        j += 1
    return None


def _consume_ident_or_num(code: str, start: int) -> Tuple[str, int, bool]:
    """Consuma identificatore o numero e indica se puo precedere un regex literal."""
    n = len(code)
    ch = code[start]
    j = start + 1
    if ch.isdigit():
        while j < n and (code[j].isalnum() or code[j] in (".", "_")):
            j += 1
        return code[start:j], j, False
    while j < n and (code[j].isalnum() or code[j] in ("_", "$")):
        j += 1
    word = code[start:j]
    return word, j, (word in _REGEX_PREFIX_KEYWORDS)


def _step_slash_token(
    code: str, i: int, is_css: bool, can_start_regex: bool
) -> Tuple[str, int, bool]:
    """Gestisce commenti /*...*/, // e literal regex /.../ a partire dall'indice i."""
    n = len(code)
    nxt = code[i + 1] if i + 1 < n else ""
    if nxt == "*":
        span, next_i = _consume_block_comment(code, i)
        return span, next_i, can_start_regex
    if not is_css and nxt == "/":
        nl = code.find("\n", i + 2)
        return "", (n if nl < 0 else nl), can_start_regex
    if not is_css and can_start_regex:
        matched = _try_consume_regex_literal(code, i)
        if matched is not None:
            return matched[0], matched[1], False
    return "/", i + 1, True


def _step_lexer_token(
    code: str, i: int, is_css: bool, can_start_regex: bool
) -> Tuple[str, int, bool]:
    """Avanza di un token lessicale restituendo (testo_emesso, nuovo_indice, can_start_regex)."""
    ch = code[i]
    if ch in ("'", '"', "`"):
        span, next_i = _consume_quoted_span(code, i, ch)
        return span, next_i, False
    if ch == "/":
        return _step_slash_token(code, i, is_css, can_start_regex)
    if ch.isalpha() or ch in ("_", "$") or ch.isdigit():
        return _consume_ident_or_num(code, i)
    next_ctx = can_start_regex if ch.isspace() else (ch not in (")", "]", "."))
    return ch, i + 1, next_ctx


def _strip_comments_preserve_lines(code: str, is_css: bool = False) -> str:
    """Rimuove commenti /* ... */ e // preservando stringhe, regex literal JS/TS e numeri di riga."""
    out: List[str] = []
    i = 0
    n = len(code)
    can_start_regex = True
    while i < n:
        piece, i, can_start_regex = _step_lexer_token(code, i, is_css, can_start_regex)
        if piece:
            out.append(piece)
    return "".join(out)


def _scan_js_ts_lines(
    raw_lines: List[str], clean_lines: List[str], file_path: str
) -> List[QualityDiffViolation]:
    """Applica regole sicurezza, type-bypass e design-token su file JS/TS."""
    violations: List[QualityDiffViolation] = []
    for idx, (raw_ln, clean_ln) in enumerate(zip(raw_lines, clean_lines), start=1):
        if _TS_BYPASS_COMMENT_RE.search(raw_ln):
            violations.append(
                QualityDiffViolation(
                    rule_id="FE-TS-BYPASS",
                    file_path=file_path,
                    line_number=idx,
                    severity="MEDIUM",
                    message="TypeScript suppression directive (@ts-ignore/@ts-nocheck) detected.",
                )
            )
        for rule_id, sev, pat, msg in _JS_TS_RULES:
            if pat.search(clean_ln):
                violations.append(
                    QualityDiffViolation(
                        rule_id=rule_id,
                        file_path=file_path,
                        line_number=idx,
                        severity=sev,
                        message=msg,
                    )
                )
        if _INLINE_HEX_RE.search(clean_ln) and not _CSS_CUSTOM_PROP_RE.search(clean_ln):
            violations.append(
                QualityDiffViolation(
                    rule_id="FE-INLINE-HEX",
                    file_path=file_path,
                    line_number=idx,
                    severity="LOW",
                    message="Hardcoded inline hex color detected outside CSS custom properties.",
                )
            )
    return violations


def _scan_css_lines(clean_lines: List[str], file_path: str) -> List[QualityDiffViolation]:
    """Applica regole sicurezza CSS e design-token su file .css."""
    violations: List[QualityDiffViolation] = []
    for idx, clean_ln in enumerate(clean_lines, start=1):
        for rule_id, sev, pat, msg in _CSS_RULES:
            if pat.search(clean_ln):
                violations.append(
                    QualityDiffViolation(
                        rule_id=rule_id,
                        file_path=file_path,
                        line_number=idx,
                        severity=sev,
                        message=msg,
                    )
                )
        if _INLINE_HEX_RE.search(clean_ln) and not _CSS_CUSTOM_PROP_RE.search(clean_ln):
            violations.append(
                QualityDiffViolation(
                    rule_id="FE-INLINE-HEX",
                    file_path=file_path,
                    line_number=idx,
                    severity="LOW",
                    message="Hardcoded inline hex color detected outside CSS custom properties.",
                )
            )
    return violations


def _scan_frontend_single(code: str, file_path: str, ext: str) -> List[QualityDiffViolation]:
    """Scansiona un singolo sorgente Frontend senza confronto differenziale."""
    raw_lines = code.splitlines()
    clean_lines = _strip_comments_preserve_lines(code, is_css=(ext == ".css")).splitlines()
    if len(clean_lines) < len(raw_lines):
        clean_lines.extend([""] * (len(raw_lines) - len(clean_lines)))
    if ext == ".css":
        return _scan_css_lines(clean_lines, file_path)
    return _scan_js_ts_lines(raw_lines, clean_lines, file_path)


def _group_violations_by_line(
    violations: List[QualityDiffViolation],
) -> Dict[int, List[QualityDiffViolation]]:
    """Indicizza le violazioni per numero di riga 1-indexed."""
    grouped: Dict[int, List[QualityDiffViolation]] = {}
    for viol in violations:
        ln = int(viol.line_number or 0)
        grouped.setdefault(ln, []).append(viol)
    return grouped


def _filter_equal_hunk(
    i1: int,
    i2: int,
    j1: int,
    pre_by_ln: Dict[int, List[QualityDiffViolation]],
    post_by_ln: Dict[int, List[QualityDiffViolation]],
) -> List[QualityDiffViolation]:
    """Sopprime violazioni legacy gia attive su righe identiche segnalando solo nuove esposizioni."""
    out: List[QualityDiffViolation] = []
    for offset in range(i2 - i1):
        pre_rules = Counter(v.rule_id for v in pre_by_ln.get(i1 + offset + 1, ()))
        for post_v in post_by_ln.get(j1 + offset + 1, ()):
            if pre_rules[post_v.rule_id] > 0:
                pre_rules[post_v.rule_id] -= 1
            else:
                out.append(post_v)
    return out


def _filter_replace_hunk(
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    pre_lines: List[str],
    post_lines: List[str],
    pre_by_ln: Dict[int, List[QualityDiffViolation]],
    post_by_ln: Dict[int, List[QualityDiffViolation]],
) -> List[QualityDiffViolation]:
    """Confronta le violazioni in blocchi modificati bloccando ogni nuova introduzione."""
    pre_counts: Counter[Tuple[str, str]] = Counter()
    for ln in range(i1 + 1, i2 + 1):
        txt = pre_lines[ln - 1].strip() if 1 <= ln <= len(pre_lines) else ""
        for v in pre_by_ln.get(ln, ()):
            pre_counts[(v.rule_id, txt)] += 1
    out: List[QualityDiffViolation] = []
    for ln in range(j1 + 1, j2 + 1):
        txt = post_lines[ln - 1].strip() if 1 <= ln <= len(post_lines) else ""
        for v in post_by_ln.get(ln, ()):
            key = (v.rule_id, txt)
            if pre_counts[key] > 0:
                pre_counts[key] -= 1
            else:
                out.append(v)
    return out


def _scan_frontend_differential(
    pre_code: str, post_code: str, file_path: str, ext: str
) -> List[QualityDiffViolation]:
    """Restituisce solo le nuove violazioni Frontend introdotte rispetto a pre_code."""
    if pre_code == post_code:
        return []
    if not pre_code:
        return _scan_frontend_single(post_code, file_path, ext)
    pre_by_ln = _group_violations_by_line(_scan_frontend_single(pre_code, file_path, ext))
    post_by_ln = _group_violations_by_line(_scan_frontend_single(post_code, file_path, ext))
    pre_lines = pre_code.splitlines()
    post_lines = post_code.splitlines()
    out: List[QualityDiffViolation] = []
    matcher = difflib.SequenceMatcher(None, pre_lines, post_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.extend(_filter_equal_hunk(i1, i2, j1, pre_by_ln, post_by_ln))
        elif tag == "replace":
            out.extend(
                _filter_replace_hunk(
                    i1, i2, j1, j2, pre_lines, post_lines, pre_by_ln, post_by_ln
                )
            )
        elif tag == "insert":
            for ln in range(j1 + 1, j2 + 1):
                out.extend(post_by_ln.get(ln, ()))
    return out


def scan_frontend_code(
    code: str, file_path: str, pre_code: Optional[str] = None
) -> List[QualityDiffViolation]:
    """Scansiona una sorgente Frontend (.ts, .tsx, .js, .jsx, .css) con supporto differenziale."""
    ext = Path(file_path).suffix.lower()
    if ext not in FRONTEND_EXTENSIONS:
        return []
    if pre_code is None:
        return _scan_frontend_single(code, file_path, ext)
    return _scan_frontend_differential(pre_code, code, file_path, ext)


def _resolve_frontend_pre_code(
    fpath: Path, root_dir: Path, pre_root: Optional[Path]
) -> Optional[str]:
    """Risolve il codice baseline di produzione per file Frontend in .staging/ o pre_root."""
    if pre_root is not None:
        rel = fpath.relative_to(root_dir) if root_dir.is_dir() else Path(fpath.name)
        cand = pre_root / rel
        return cand.read_text(encoding="utf-8-sig", errors="replace") if cand.is_file() else ""
    resolved = fpath.resolve()
    parts = list(resolved.parts)
    if ".staging" not in parts:
        return None
    idx = parts.index(".staging")
    rel_parts = parts[idx + 1 :]
    if not rel_parts:
        return ""
    prod_cand = Path(*parts[:idx]).joinpath(*rel_parts) if idx > 0 else Path(*rel_parts)
    if prod_cand.is_file() and prod_cand != resolved:
        return prod_cand.read_text(encoding="utf-8-sig", errors="replace")
    return ""


def scan_frontend_directory(
    root_dir: Path, pre_root: Optional[Path] = None
) -> List[QualityDiffViolation]:
    """Scansiona ricorsivamente i file Frontend sotto root_dir escludendo vendor dir."""
    if not root_dir.exists():
        return []
    violations: List[QualityDiffViolation] = []
    if root_dir.is_file():
        candidates = [root_dir]
    else:
        candidates = sorted(
            f
            for f in root_dir.rglob("*")
            if f.is_file()
            and f.suffix.lower() in FRONTEND_EXTENSIONS
            and not any(part in _SKIP_DIRS for part in f.parts)
        )
    for fpath in candidates:
        content = fpath.read_text(encoding="utf-8-sig", errors="replace")
        pre_code = _resolve_frontend_pre_code(fpath, root_dir, pre_root)
        violations.extend(scan_frontend_code(content, fpath.as_posix(), pre_code=pre_code))
    return violations
