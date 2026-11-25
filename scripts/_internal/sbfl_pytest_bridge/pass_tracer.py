"""Collector batched via sys.monitoring e hook sys.settrace per copertura pass/fail SBFL."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


from _internal.sbfl_pytest_bridge import _ensure_staging_pkg

_ensure_staging_pkg(Path(__file__).resolve().parent)

from _internal.sbfl_pytest_bridge.plugin_template import _build_pass_cov_plugin_source
from _internal.sbfl_pytest_bridge.scoring_helpers import CoverageRecord


def _parse_pass_counts_json(out_json: Path) -> Optional[Dict[Tuple[str, int], int]]:
    """Converte il JSON prodotto dal plugin in dizionario {(path_o_basename, line): count}."""
    if not out_json.exists():
        return None
    try:
        raw = json.loads(out_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    counts: Dict[Tuple[str, int], int] = {}
    for raw_key, raw_val in raw.items():
        if not isinstance(raw_key, str) or "::" not in raw_key:
            continue
        rel_part, lno_part = raw_key.rsplit("::", 1)
        try:
            lineno = int(lno_part)
            cnt = int(raw_val)
        except (TypeError, ValueError):
            continue
        if cnt <= 0 or lineno <= 0:
            continue
        rel_posix = rel_part.replace("\\", "/")
        counts[(rel_posix, lineno)] = cnt
        bname = Path(rel_posix).name
        if bname and bname != rel_posix:
            prev_base = counts.get((bname, lineno), 0)
            counts[(bname, lineno)] = max(prev_base, cnt)
    return counts


def _parse_coverage_records_json(records_json: Path) -> Optional[List[CoverageRecord]]:
    """Converte il JSON dei record per-test in lista di CoverageRecord strict."""
    if not records_json.exists():
        return None
    try:
        raw = json.loads(records_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, list):
        return None
    records: List[CoverageRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        test_id = item.get("test_id")
        passed = item.get("passed")
        stmts = item.get("executed_statements")
        if not isinstance(test_id, str) or not isinstance(passed, bool) or not isinstance(stmts, list):
            continue
        clean_stmts = [str(s) for s in stmts if isinstance(s, str)]
        records.append(CoverageRecord(test_id=test_id, passed=passed, executed_statements=clean_stmts))
    return records


def _select_pytest_cli_targets(selected: Sequence[str]) -> Tuple[List[str], Optional[Sequence[str]]]:
    """Restituisce i target CLI compatti evitando il limite CreateProcess su suite grandi."""
    total_chars = sum(len(item) + 1 for item in selected)
    if total_chars < 8000:
        return list(selected), None
    unique_files = list(dict.fromkeys(item.split("::", 1)[0] for item in selected))
    return unique_files, selected


def _run_plugin_pass_fail_cov(
    selected: Sequence[str],
    exec_root: Path,
    run_fn: Any,
    norm_hint_name: Optional[str],
    timeout_sec: float,
    *,
    prefer_settrace: bool = False,
) -> Tuple[Optional[Dict[Tuple[str, int], int]], Optional[List[CoverageRecord]]]:
    """Esegue pytest con il plugin temporaneo raccogliendo conteggi n_ep e CoverageRecord."""
    cli_targets, nodeid_filter = _select_pytest_cli_targets(selected)
    with tempfile.TemporaryDirectory(prefix="nk_sbfl_mon_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        bt_dir = tmp_path / "bt"
        out_json = tmp_path / "pass_line_counts.json"
        rec_json = tmp_path / "coverage_records.json"
        plugin_path = tmp_path / "nk_pass_cov_plugin.py"
        plugin_src = _build_pass_cov_plugin_source(
            exec_root.resolve().as_posix(),
            norm_hint_name,
            out_json.resolve().as_posix(),
            prefer_settrace=prefer_settrace,
            records_json_posix=rec_json.resolve().as_posix(),
            selected_nodeids=nodeid_filter,
        )
        plugin_path.write_text(plugin_src, encoding="utf-8")

        cmd = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            *cli_targets,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-p",
            "nk_pass_cov_plugin",
            f"--basetemp={bt_dir.as_posix()}",
        ]
        sub_env = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{tmp_path}{os.pathsep}{exec_root}",
        }
        run_fn(
            cmd=cmd,
            cwd=str(exec_root),
            timeout=max(5.0, float(timeout_sec)),
            env=sub_env,
        )
        return _parse_pass_counts_json(out_json), _parse_coverage_records_json(rec_json)


def _run_plugin_pass_cov(
    selected: Sequence[str],
    exec_root: Path,
    run_fn: Any,
    norm_hint_name: Optional[str],
    timeout_sec: float,
    *,
    prefer_settrace: bool = False,
) -> Optional[Dict[Tuple[str, int], int]]:
    """Esegue pytest con il plugin temporaneo sys.monitoring / sys.settrace."""
    counts, _ = _run_plugin_pass_fail_cov(
        selected,
        exec_root,
        run_fn,
        norm_hint_name,
        timeout_sec,
        prefer_settrace=prefer_settrace,
    )
    return counts


def _format_hint_filename(norm_hint: Optional[str]) -> Optional[str]:
    """Normalizza norm_hint aggiungendo .py se privo di suffisso."""
    if not norm_hint:
        return None
    return norm_hint if norm_hint.endswith(".py") else f"{norm_hint}.py"


def _collect_passed_lines_trace_fallback(
    passed_test_names: Sequence[str],
    exec_root: Path,
    self_cwd: Path,
    run_fn: Any,
    norm_hint: Optional[str],
    timeout_sec: float,
) -> Dict[Tuple[str, int], int]:
    """Fallback pulito via temp pytest plugin sys.settrace/sys.monitoring senza trace CLI."""
    _ = self_cwd
    selected = [t for t in passed_test_names if t and t.strip()]
    if not selected:
        return {}
    parsed = _run_plugin_pass_cov(
        selected,
        exec_root,
        run_fn,
        _format_hint_filename(norm_hint),
        timeout_sec,
        prefer_settrace=True,
    )
    return parsed or {}


def _limit_selected_tests(
    selected: List[str], max_tests: int = 0
) -> List[str]:
    """Applica un eventuale tetto esplicito richiesto dal chiamante."""
    if max_tests > 0:
        return selected[:max_tests]
    return selected


def collect_passed_lines_batched(
    passed_test_names: Sequence[str],
    exec_root: Path,
    run_fn: Any,
    *,
    target_file_hint: Optional[str] = None,
    timeout_sec: float = 30.0,
    max_tests: int = 0,
) -> Optional[Dict[Tuple[str, int], int]]:
    """Esegue un solo processo pytest batched con sys.monitoring per calcolare n_ep."""
    selected = _limit_selected_tests(
        [t for t in passed_test_names if isinstance(t, str) and t.strip()], max_tests
    )
    if not selected:
        return {}
    norm_hint_name = Path(target_file_hint).name if target_file_hint else None
    return _run_plugin_pass_cov(
        selected,
        exec_root,
        run_fn,
        norm_hint_name,
        timeout_sec,
        prefer_settrace=False,
    )


def collect_coverage_records_batched(
    test_names: Sequence[str],
    exec_root: Path,
    run_fn: Any,
    *,
    target_file_hint: Optional[str] = None,
    timeout_sec: float = 30.0,
    prefer_settrace: bool = False,
) -> Tuple[Optional[Dict[Tuple[str, int], int]], Optional[List[CoverageRecord]]]:
    """Raccoglie copertura pass/fail batched su tutti i test senza troncamenti."""
    selected = [t for t in test_names if isinstance(t, str) and t.strip()]
    if not selected:
        return {}, []
    norm_hint_name = Path(target_file_hint).name if target_file_hint else None
    return _run_plugin_pass_fail_cov(
        selected,
        exec_root,
        run_fn,
        norm_hint_name,
        timeout_sec,
        prefer_settrace=prefer_settrace,
    )
