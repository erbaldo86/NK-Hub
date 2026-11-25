"""Parser pure-stdlib dei traceback pytest e slice AST compatte per Hybrid-FL."""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.transcript_guards import estimate_tokens

_TRACEBACK_FILE_RE = re.compile(
    r"((?:[A-Za-z]:[\\/])?[A-Za-z0-9_\-\./\\ ]+\.py):(\d+):"
)


def _lookup_passed_line_count(
    passed_line_counts: Dict[Tuple[str, int], int],
    target_file: str,
    target_line: int,
) -> int:
    """Cerca il conteggio n_ep normalizzando il case su Windows per file e basename."""
    exact = passed_line_counts.get((target_file, target_line))
    if exact is not None:
        return exact
    base_name = Path(target_file).name
    by_base = passed_line_counts.get((base_name, target_line))
    if by_base is not None:
        return by_base
    norm_full = os.path.normcase(target_file.replace("\\", "/"))
    norm_base = os.path.normcase(base_name)
    base_match = 0
    for (k_path, k_line), cnt in passed_line_counts.items():
        if k_line != target_line:
            continue
        k_norm = os.path.normcase(k_path.replace("\\", "/"))
        if k_norm == norm_full:
            return cnt
        if os.path.normcase(Path(k_norm).name) == norm_base:
            base_match = max(base_match, cnt)
    return base_match


def _matches_target_hint(fpath: str, norm_hint: Optional[str]) -> bool:
    """Confronta il filename del traceback con norm_hint in modo case-safe su Windows."""
    fname = Path(fpath).name
    if norm_hint:
        return os.path.normcase(fname) == os.path.normcase(norm_hint)
    low = fname.lower()
    return low != "conftest.py" and "test_" not in low and not low.endswith("_test.py")


def _classify_pytest_line(
    clean_line: str, passed_tests: List[str], failed_tests: List[str]
) -> None:
    """Classifica una riga verbose di pytest in test passati o falliti/error."""
    if " PASSED" in clean_line:
        tname = clean_line.split(" PASSED", 1)[0].strip()
        if tname and tname not in passed_tests:
            passed_tests.append(tname)
    elif " FAILED" in clean_line:
        tname = clean_line.split(" FAILED", 1)[0].strip()
        if tname and tname not in failed_tests:
            failed_tests.append(tname)
    elif " ERROR" in clean_line and "::" in clean_line.split(" ERROR", 1)[0]:
        tname = clean_line.split(" ERROR", 1)[0].strip()
        if tname and tname not in failed_tests:
            failed_tests.append(tname)


def _extract_error_header(lines: Sequence[str]) -> Tuple[str, str]:
    """Estrae tipo e messaggio dell'ultima riga 'E   ' del traceback pytest."""
    for line in reversed(lines):
        line_str = line.strip()
        if line_str.startswith(("E   ", "E:  ")):
            err_content = line_str[4:].strip()
            if ":" in err_content:
                parts = err_content.split(":", 1)
                return parts[0].strip(), parts[1].strip()
            return "AssertionError", err_content
    return "TestFailure", "Test failed"


def _is_frame_boundary(line_str: str) -> bool:
    """Riconosce separatori di sezione o righe esito test pytest."""
    return line_str.startswith(("___", "_ _ _", "===")) or line_str.endswith(
        (" PASSED", " FAILED", " ERROR")
    )


def _parse_traceback_diagnostics(
    lines: Sequence[str], norm_hint: Optional[str]
) -> Tuple[
    str,
    str,
    List[Tuple[str, int]],
    Dict[Tuple[str, int], int],
    Dict[Tuple[str, int], str],
]:
    """Estrae errore, frequenza frame e codice '>' associato per singolo frame."""
    error_type, error_msg = _extract_error_header(lines)
    frame_counts: Dict[Tuple[str, int], int] = {}
    last_seen: Dict[Tuple[str, int], int] = {}
    frame_code_map: Dict[Tuple[str, int], str] = {}
    pending_code = ""
    last_frame: Optional[Tuple[str, int]] = None

    for idx, raw_line in enumerate(lines):
        line_str = raw_line.strip()
        if _is_frame_boundary(line_str):
            pending_code = ""
            last_frame = None
            continue
        if line_str.startswith(">"):
            code_txt = line_str.lstrip("> ").strip()
            if last_frame is not None and last_frame not in frame_code_map:
                frame_code_map[last_frame] = code_txt
            else:
                pending_code = code_txt
            continue
        match = _TRACEBACK_FILE_RE.search(line_str)
        if not match:
            continue
        fkey = (match.group(1).strip().replace("\\", "/"), int(match.group(2)))
        if pending_code and fkey not in frame_code_map:
            frame_code_map[fkey] = pending_code
        pending_code = ""
        last_frame = fkey
        if _matches_target_hint(fkey[0], norm_hint):
            frame_counts[fkey] = frame_counts.get(fkey, 0) + 1
            last_seen[fkey] = idx

    ordered = sorted(
        frame_counts.keys(), key=lambda k: (frame_counts[k], last_seen[k]), reverse=True
    )
    return error_type, error_msg, ordered, frame_counts, frame_code_map


def _lookup_frame_code(
    frame_code_map: Dict[Tuple[str, int], str], target_file: str, target_line: int
) -> str:
    """Cerca il sorgente '>' estratto per il frame specifico normalizzando su Windows."""
    exact = frame_code_map.get((target_file, target_line))
    if exact:
        return exact
    norm_t = os.path.normcase(target_file.replace("\\", "/"))
    norm_base = os.path.normcase(Path(norm_t).name)
    for (fpath, lno), code_txt in frame_code_map.items():
        if lno != target_line or not code_txt:
            continue
        norm_f = os.path.normcase(fpath.replace("\\", "/"))
        if norm_f == norm_t or os.path.normcase(Path(norm_f).name) == norm_base:
            return code_txt
    return ""


def _read_source_line(
    mirror_dir: Optional[Path], cwd: Path, target_file: str, target_line: int
) -> str:
    """Legge la riga target da disco come fallback quando assente nel frame '>'."""
    base_dir = mirror_dir or cwd
    for cand in (base_dir / target_file, cwd / target_file, Path(target_file)):
        try:
            if cand.exists() and cand.is_file():
                flines = cand.read_text(encoding="utf-8").splitlines()
                if 1 <= target_line <= len(flines):
                    return flines[target_line - 1].strip()
        except OSError:
            continue
    return ""


def _resolve_slice_source_text(
    target_file: str, search_roots: Sequence[Optional[Path]]
) -> str:
    """Legge il contenuto sorgente cercando nelle root valide fornite."""
    for base in (*search_roots, None):
        cand = (base / target_file) if base is not None else Path(target_file)
        try:
            if cand.is_file():
                return cand.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return ""


def _find_enclosing_ast_span(src_text: str, line_number: int, total_lines: int) -> Tuple[int, int]:
    """Individua l'intervallo righe del blocco funzione o classe che racchiude line_number."""
    lo = max(1, line_number - 2)
    hi = min(total_lines, line_number + 2)
    try:
        tree = ast.parse(src_text)
    except SyntaxError:
        return lo, hi
    best_span: Optional[Tuple[int, int]] = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            s_ln = int(getattr(node, "lineno", 0) or 0)
            e_ln = int(getattr(node, "end_lineno", s_ln) or s_ln)
            if s_ln <= line_number <= e_ln:
                if best_span is None or (e_ln - s_ln) < (best_span[1] - best_span[0]):
                    best_span = (s_ln, e_ln)
    if best_span is None:
        return lo, hi
    return max(best_span[0], line_number - 3), min(best_span[1], line_number + 2)


def _fit_slice_to_token_budget(
    loc_label: str, score: float, raw_lines: List[str], max_tokens: int
) -> Dict[str, Any]:
    """Compatta lo snippet garantendo estimate_tokens(slice) e JSON dell'item <= max_tokens."""
    kept = list(raw_lines)
    snippet = "\n".join(kept).strip()
    item: Dict[str, Any] = {
        "loc": loc_label,
        "score": round(score, 4),
        "tokens": estimate_tokens(snippet),
        "slice": snippet,
    }
    while len(kept) > 1 and estimate_tokens(json.dumps(item, separators=(",", ":"))) > max_tokens:
        kept.pop()
        snippet = "\n".join(kept).strip()
        item["slice"] = snippet
        item["tokens"] = estimate_tokens(snippet)
    while item["slice"] and (
        estimate_tokens(item["slice"]) > max_tokens
        or estimate_tokens(json.dumps(item, separators=(",", ":"))) > max_tokens
    ):
        item["slice"] = item["slice"][:-16].rstrip()
        item["tokens"] = estimate_tokens(item["slice"])
    return item


def build_hybrid_fl_slices(
    candidates: Sequence[Tuple[str, int, float]],
    search_roots: Sequence[Optional[Path]],
    *,
    max_blocks: int = 3,
    max_tokens: int = 80,
) -> List[Dict[str, Any]]:
    """Costruisce fino a 3 slice AST/sorgente compatte (<= 80 token/slice) per --hybrid-fl."""
    slices: List[Dict[str, Any]] = []
    seen_locs: set[Tuple[str, int]] = set()
    for target_file, raw_lno, score in candidates:
        if len(slices) >= max(1, min(max_blocks, 3)):
            break
        lno = max(1, int(raw_lno))
        key = (target_file, lno)
        if key in seen_locs:
            continue
        seen_locs.add(key)
        src_text = _resolve_slice_source_text(target_file, search_roots)
        if src_text:
            all_lines = src_text.splitlines()
            start_ln, end_ln = _find_enclosing_ast_span(src_text, lno, len(all_lines))
            raw_slice = [
                f"{ln}: {all_lines[ln - 1].rstrip()}"
                for ln in range(start_ln, min(end_ln, len(all_lines)) + 1)
            ]
        else:
            raw_slice = [f"{target_file}:{lno}"]
        loc_label = f"{Path(target_file).name if len(target_file) > 36 else target_file}:{lno}"
        slices.append(_fit_slice_to_token_budget(loc_label, float(score), raw_slice, min(max_tokens, 80)))
    return slices
