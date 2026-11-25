# -*- coding: utf-8 -*-
"""Analizzatore differenziale qualitativo pure-AST e guardia di perimetro file (--allowed-files)."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from _internal.ast_guard_validator.quality_diff_rules import (
    QualityDiffViolation,
    extract_function_metrics,
)
from _internal.ast_guard_validator.validator_helpers import parse_ast_cached

MAX_NEW_FUNC_CC: int = 15
MAX_NEW_FUNC_NESTING: int = 4


class QualityDiffReport(BaseModel):
    """Rapporto aggregato delle verifiche qualitative differenziali su uno o piu file."""

    model_config = ConfigDict(strict=True, frozen=True)

    passed: bool = Field(description="True se non vi sono violazioni HIGH o MEDIUM")
    files_checked: int = Field(description="Numero di file valutati")
    violations: List[QualityDiffViolation] = Field(default_factory=list)
    delta_cc_by_file: Dict[str, int] = Field(default_factory=dict)
    high_count: int = Field(default=0)
    medium_count: int = Field(default=0)
    low_count: int = Field(default=0)


def _is_test_path(target_file: str) -> bool:
    """Identifica i file test dai segmenti del percorso normalizzato."""
    norm = str(target_file or "").replace("\\", "/").lower()
    parts = [p for p in norm.split("/") if p]
    base = parts[-1] if parts else ""
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or "tests" in parts
    )


def _collect_new_silent_except_violations(
    qname: str,
    pre_lines: Sequence[int],
    post_lines: Sequence[int],
    target_file: str,
) -> List[QualityDiffViolation]:
    """Segnala ogni nuovo handler except ampio silenzioso introdotto rispetto al baseline."""
    new_count = len(post_lines) - len(pre_lines)
    if new_count <= 0:
        return []
    pre_set = set(pre_lines)
    unseen = [ln for ln in post_lines if ln not in pre_set]
    reported = (
        unseen[:new_count]
        if len(unseen) >= new_count
        else list(post_lines[-new_count:])
    )
    return [
        QualityDiffViolation(
            rule_id="QD-SILENT-EXCEPT",
            file_path=target_file,
            symbol_name=qname,
            line_number=exc_ln,
            severity="HIGH",
            message=f"New silent broad except handler introduced in '{qname}'.",
        )
        for exc_ln in reported
    ]


def _append_cc_and_nest_regressions(
    qname: str,
    pre_m: Dict[str, Any],
    post_m: Dict[str, Any],
    target_file: str,
    out: List[QualityDiffViolation],
) -> None:
    """Segnala regressioni di complessita e nesting escludendo le sole guardie difensive minime."""
    ln = int(post_m["lineno"])
    pre_cc, post_cc = int(pre_m["cc"]), int(post_m["cc"])
    pre_nest, post_nest = int(pre_m["nesting"]), int(post_m["nesting"])
    exempt_cc = post_cc <= 10 and (post_cc - pre_cc) <= 2 and post_nest <= max(pre_nest, 2)
    exempt_nest = pre_nest == 0 and post_nest == 1 and post_cc <= 10
    if post_cc > pre_cc and not exempt_cc:
        out.append(QualityDiffViolation(
            rule_id="QD-CC-REGRESSION", file_path=target_file, symbol_name=qname,
            line_number=ln, severity="MEDIUM",
            message=f"Cyclomatic complexity regressed in '{qname}' ({pre_cc} -> {post_cc}).",
        ))
    if post_nest > pre_nest and not exempt_nest:
        out.append(QualityDiffViolation(
            rule_id="QD-NESTING-REGRESSION", file_path=target_file, symbol_name=qname,
            line_number=ln, severity="MEDIUM",
            message=f"Max nesting regressed in '{qname}' ({pre_nest} -> {post_nest}).",
        ))


def _check_modified_function(
    qname: str,
    pre_m: Dict[str, Any],
    post_m: Dict[str, Any],
    target_file: str,
) -> List[QualityDiffViolation]:
    """Verifica che una funzione modificata non subisca regressioni di CC, nesting o except."""
    out: List[QualityDiffViolation] = []
    if pre_m["body_dump"] == post_m["body_dump"]:
        return out
    _append_cc_and_nest_regressions(qname, pre_m, post_m, target_file, out)
    out.extend(
        _collect_new_silent_except_violations(
            qname, pre_m["silent_except_lines"], post_m["silent_except_lines"], target_file
        )
    )
    pre_taut = len(pre_m["test_assert_issues"])
    post_taut = post_m["test_assert_issues"]
    if len(post_taut) > pre_taut:
        for rid, issue_ln, msg in post_taut[pre_taut:]:
            out.append(
                QualityDiffViolation(
                    rule_id=rid,
                    file_path=target_file,
                    symbol_name=qname,
                    line_number=issue_ln,
                    severity="HIGH",
                    message=msg,
                )
            )
    return out


def _check_added_function(
    qname: str, post_m: Dict[str, Any], target_file: str
) -> List[QualityDiffViolation]:
    """Applica i tetti di complessita, nesting, silent except e tautologia alle funzioni nuove."""
    out: List[QualityDiffViolation] = []
    ln = int(post_m["lineno"])
    if post_m["cc"] > MAX_NEW_FUNC_CC:
        out.append(
            QualityDiffViolation(
                rule_id="QD-CC-LIMIT",
                file_path=target_file,
                symbol_name=qname,
                line_number=ln,
                severity="MEDIUM",
                message=(
                    f"New function '{qname}' exceeds CC limit "
                    f"({post_m['cc']} > {MAX_NEW_FUNC_CC})."
                ),
            )
        )
    if post_m["nesting"] > MAX_NEW_FUNC_NESTING:
        out.append(
            QualityDiffViolation(
                rule_id="QD-NESTING-LIMIT",
                file_path=target_file,
                symbol_name=qname,
                line_number=ln,
                severity="MEDIUM",
                message=(
                    f"New function '{qname}' exceeds nesting limit "
                    f"({post_m['nesting']} > {MAX_NEW_FUNC_NESTING})."
                ),
            )
        )
    for exc_ln in post_m["silent_except_lines"]:
        out.append(
            QualityDiffViolation(
                rule_id="QD-SILENT-EXCEPT",
                file_path=target_file,
                symbol_name=qname,
                line_number=exc_ln,
                severity="HIGH",
                message=f"Silent broad except handler in added function '{qname}'.",
            )
        )
    for rid, issue_ln, msg in post_m["test_assert_issues"]:
        out.append(
            QualityDiffViolation(
                rule_id=rid,
                file_path=target_file,
                symbol_name=qname,
                line_number=issue_ln,
                severity="HIGH",
                message=msg,
            )
        )
    return out


def _syntax_error_violation(
    target_file: str, syn_err: Optional[SyntaxError], label: str
) -> QualityDiffViolation:
    return QualityDiffViolation(
        rule_id="QD-SYNTAX-ERROR",
        file_path=target_file,
        symbol_name=None,
        line_number=getattr(syn_err, "lineno", None),
        severity="HIGH",
        message=f"{label} in '{target_file}': {getattr(syn_err, 'msg', str(syn_err or 'invalid syntax'))}",
    )


def _parse_diff_trees_or_error(
    pre_code: str, post_code: str, target_file: str
) -> Tuple[Optional[Tuple[ast.AST, ast.AST]], List[QualityDiffViolation]]:
    """Parsa pre/post AST tramite RepoSnapshotCache fail-closed con QD-SYNTAX-ERROR."""
    post_tree, post_err = parse_ast_cached(post_code, filename=target_file)
    if post_err is not None or post_tree is None:
        return None, [_syntax_error_violation(target_file, post_err, "SyntaxError")]
    if pre_code:
        pre_tree, pre_err = parse_ast_cached(pre_code, filename=target_file)
        if pre_err is not None or pre_tree is None:
            return None, [_syntax_error_violation(target_file, pre_err, "Baseline SyntaxError")]
    else:
        pre_tree = ast.Module(body=[], type_ignores=[])
    return (pre_tree, post_tree), []


def check_python_quality_diff(
    pre_code: str, post_code: str, target_file: str = "<target>"
) -> List[QualityDiffViolation]:
    """Confronta le metriche AST pre/post in modalita fail-closed con cache condivisa."""
    if pre_code == post_code:
        return []
    trees, syn_violations = _parse_diff_trees_or_error(pre_code, post_code, target_file)
    if trees is None:
        return syn_violations
    pre_tree, post_tree = trees

    is_test = _is_test_path(target_file)
    pre_funcs = extract_function_metrics(pre_tree, is_test_file=is_test)
    post_funcs = extract_function_metrics(post_tree, is_test_file=is_test)

    violations: List[QualityDiffViolation] = []
    for qname, post_m in post_funcs.items():
        if qname in pre_funcs:
            violations.extend(
                _check_modified_function(qname, pre_funcs[qname], post_m, target_file)
            )
        else:
            violations.extend(_check_added_function(qname, post_m, target_file))
    return violations


def _parse_delta_trees(pre_code: str, post_code: str) -> Optional[Tuple[ast.AST, ast.AST]]:
    """Parsa pre/post tramite cache condivisa restituendo None su errori di sintassi."""
    pre_tree, pre_err = parse_ast_cached(pre_code, filename="<pre>")
    post_tree, post_err = parse_ast_cached(post_code, filename="<post>")
    if pre_err is not None or post_err is not None or pre_tree is None or post_tree is None:
        return None
    return pre_tree, post_tree


def compute_file_delta_cc(pre_code: str, post_code: str) -> int:
    """Restituisce la somma netta delta_cc sulle funzioni modificate rispetto al baseline."""
    if pre_code == post_code or not pre_code:
        return 0
    trees = _parse_delta_trees(pre_code, post_code)
    if trees is None:
        return 0
    pre_funcs = extract_function_metrics(trees[0])
    post_funcs = extract_function_metrics(trees[1])
    delta = 0
    for qname, post_m in post_funcs.items():
        if qname in pre_funcs and pre_funcs[qname]["body_dump"] != post_m["body_dump"]:
            delta += int(post_m["cc"]) - int(pre_funcs[qname]["cc"])
    return delta


def _compile_segment_glob(norm_pat: str) -> re.Pattern[str]:
    """Compila un glob segment-aware dove * = [^/]*, ** = .* e ? = [^/]."""
    parts: List[str] = ["^"]
    i = 0
    n = len(norm_pat)
    while i < n:
        if norm_pat.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif norm_pat.startswith("**", i):
            parts.append(".*")
            i += 2
        elif norm_pat[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif norm_pat[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(norm_pat[i]))
            i += 1
    parts.append("$")
    return re.compile("".join(parts))


def _strip_rel_prefix(raw: str) -> str:
    """Rimuove spazi e prefissi './' o '/' preservando directory puntate come '.agents/'."""
    clean = raw.strip().replace("\\", "/")
    while clean.startswith("./"):
        clean = clean[2:]
    return clean.lstrip("/")


def _single_pattern_matches(norm_rel: str, pat: str) -> bool:
    """Verifica un singolo pattern normalizzato contro norm_rel con semantica segment-aware."""
    norm_pat = _strip_rel_prefix(pat)
    if not norm_pat:
        return False
    if norm_pat.endswith("/"):
        if "*" in norm_pat or "?" in norm_pat:
            return bool(_compile_segment_glob(norm_pat + "**").match(norm_rel))
        return norm_rel.startswith(norm_pat)
    if norm_rel == norm_pat:
        return True
    return bool(_compile_segment_glob(norm_pat).match(norm_rel))


def _matches_allowed_pattern(rel_posix: str, patterns: Sequence[str]) -> bool:
    """Verifica se rel_posix corrisponde a uno dei pattern consentiti dal brief."""
    norm_rel = _strip_rel_prefix(rel_posix)
    return any(_single_pattern_matches(norm_rel, pat) for pat in patterns)


def _resolve_rel_staged_posix(fpath: Path, base: Path) -> Optional[str]:
    """Risolve il percorso relativo POSIX sotto stage_dir, restituendo None su escape."""
    try:
        return fpath.resolve().relative_to(base).as_posix()
    except (ValueError, OSError):
        return None


def check_allowed_files(
    staged_files: Sequence[Path],
    stage_dir: Path,
    allowed_patterns: Sequence[str],
) -> List[QualityDiffViolation]:
    """Segnala i file in staging fuori dal perimetro --allowed-files o fuori stage_dir."""
    clean_patterns = [p.strip() for p in allowed_patterns if p.strip()]
    if not clean_patterns:
        return []
    violations: List[QualityDiffViolation] = []
    base = stage_dir.resolve()
    for fpath in staged_files:
        if fpath.name == ".gitkeep" or "__pycache__" in fpath.parts:
            continue
        rel_posix = _resolve_rel_staged_posix(fpath, base)
        if rel_posix is None:
            violations.append(
                QualityDiffViolation(
                    rule_id="QD-SCOPE-CREEP",
                    file_path=fpath.as_posix(),
                    severity="HIGH",
                    message=(
                        f"Staged file '{fpath.as_posix()}' escapes stage directory '{base.as_posix()}'."
                    ),
                )
            )
            continue
        if not _matches_allowed_pattern(rel_posix, clean_patterns):
            violations.append(
                QualityDiffViolation(
                    rule_id="QD-SCOPE-CREEP",
                    file_path=rel_posix,
                    severity="HIGH",
                    message=(
                        f"Staged file '{rel_posix}' is outside --allowed-files perimeter."
                    ),
                )
            )
    return violations
