"""Logica SBFLPytestBridge per esecuzione pytest isolata su NVMe e localizzazione SBFL."""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


from _internal.sbfl_pytest_bridge import _ensure_staging_pkg

_ensure_staging_pkg(Path(__file__).resolve().parent)

from _internal.nk_common.isolated_test_runner import (
    is_temp_workspace,
    mirror_workspace_to_nvme,
    safe_rmtree,
)
from _internal.nk_common.paths import reconfigure_streams
from _internal.sbfl_pytest_bridge.frame_extractor import (
    _TRACEBACK_FILE_RE,
    _classify_pytest_line,
    _lookup_frame_code,
    _lookup_passed_line_count,
    _matches_target_hint,
    _parse_traceback_diagnostics,
    _read_source_line,
)
from _internal.sbfl_pytest_bridge.matrix_engine import rank_bridge_coverage
from _internal.sbfl_pytest_bridge.models import (
    CoverageRecord,
    OchiaiBridgeLocation,
    PytestRunSummary,
    SBFLScore,
    SpectrumCounts,
    calculate_ochiai,
    compute_ochiai,
    is_monitoring_conflict_active,
)
from _internal.sbfl_pytest_bridge.pass_tracer import (
    _collect_passed_lines_trace_fallback,
    collect_coverage_records_batched,
    collect_passed_lines_batched,
)
from _internal.sbfl_pytest_bridge.runner_and_cli import (
    _append_pytest_iso_flags,
    _is_pytest_command,
    _normalize_mirror_output,
    _rewrite_cmd_for_mirror,
    _strip_quiet_and_add_verbose,
)
from _internal.sbfl_pytest_bridge.scoring_helpers import (
    build_fallback_coverage_records,
    split_stmt,
)

try:
    from platform_runner import safe_subprocess_run
except ImportError:
    from scripts.platform_runner import safe_subprocess_run


def _resolve_bridge_facade_attr(attr_name: str, default_val: Any) -> Any:
    """Risolve eventuali monkeypatch applicati sulla facciata o alias sbfl_pytest_bridge."""
    mod_a = sys.modules.get("sbfl_pytest_bridge")
    mod_b = sys.modules.get("scripts.sbfl_pytest_bridge")
    for mod in (mod_a, mod_b, *reversed(list(sys.modules.values()))):
        if mod is None:
            continue
        mod_file = getattr(mod, "__file__", "") or ""
        if mod is mod_a or mod is mod_b or mod_file.endswith(("sbfl_pytest_bridge.py", "sbfl_pytest_bridge.pyc")):
            try:
                mod_vars = vars(mod)
            except TypeError:
                continue
            if attr_name in mod_vars:
                val = getattr(mod, attr_name)
                if val is not None and val is not default_val:
                    return val
    return default_val


def _resolve_safe_subprocess_run() -> Any:
    return _resolve_bridge_facade_attr("safe_subprocess_run", safe_subprocess_run)


def _resolve_monitoring_conflict() -> bool:
    """Verifica eventuali conflitti sys.monitoring rispettando monkeypatch sulla facciata."""
    conflict_fn = _resolve_bridge_facade_attr(
        "is_monitoring_conflict_active", is_monitoring_conflict_active
    )
    return bool(conflict_fn())


def _create_nvme_mirror(ws_root: Path) -> Tuple[Path, Path]:
    """Crea un mirror NVMe temporaneo in TEMP e prepara la directory basetemp."""
    apply_ov = (ws_root / ".staging").is_dir()
    mirror_dir = mirror_workspace_to_nvme(ws_root, prefix="nk_sbfl_iso_", apply_overlay=apply_ov)
    if ws_root.is_dir():
        for entry in ws_root.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".py":
                dst = mirror_dir / entry.name
                if not dst.exists():
                    shutil.copy2(entry, dst)
    basetemp = mirror_dir.parent / "basetemp"
    basetemp.mkdir(parents=True, exist_ok=True)
    return mirror_dir, basetemp


class SBFLPytestBridge:
    """Ponte che coordina esecuzione pytest su NVMe, CoverageMatrix e SBFLEngine."""

    compute_ochiai = staticmethod(compute_ochiai)
    TRACEBACK_FILE_RE = _TRACEBACK_FILE_RE

    def __init__(self, cwd: Optional[Path] = None):
        reconfigure_streams()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()
        self._active_mirror_dir: Optional[Path] = None
        self.last_ranked_scores: List[SBFLScore] = []
        self.last_diagnostic_payload: Optional[Any] = None

    def parse_pytest_output(
        self, stdout: str, stderr: str, exit_code: int, duration_sec: float = 0.0
    ) -> PytestRunSummary:
        """Analizza stdout e stderr di pytest per estrarre le statistiche di esito."""
        passed_tests: List[str] = []
        failed_tests: List[str] = []
        for line in stdout.splitlines():
            _classify_pytest_line(line.strip(), passed_tests, failed_tests)
        failed_cnt, passed_cnt = len(failed_tests), len(passed_tests)
        if failed_cnt == 0 and passed_cnt == 0:
            p_match = re.search(r"(\d+)\s+passed", stdout)
            f_match = re.search(r"(\d+)\s+failed", stdout)
            if p_match:
                passed_cnt = int(p_match.group(1))
            if f_match:
                failed_cnt = int(f_match.group(1))
        return PytestRunSummary(
            total_tests=failed_cnt + passed_cnt,
            passed_count=passed_cnt,
            failed_count=failed_cnt,
            error_count=1 if exit_code != 0 and failed_cnt == 0 else 0,
            exit_code=exit_code,
            duration_sec=duration_sec,
            failed_test_names=failed_tests,
            passed_test_names=passed_tests,
            raw_stdout=stdout,
            raw_stderr=stderr,
        )

    def collect_passed_line_counts(
        self,
        passed_test_names: Sequence[str],
        target_file_hint: Optional[str] = None,
        timeout_sec: float = 30.0,
    ) -> Dict[Tuple[str, int], int]:
        """Raccoglie i conteggi n_ep dei test passati in mirror NVMe senza pytest-cov."""
        if not passed_test_names or _resolve_monitoring_conflict():
            return {}

        run_fn = _resolve_safe_subprocess_run()
        exec_root = self._active_mirror_dir or self.cwd
        own_mirror_root: Optional[Path] = None
        if self._active_mirror_dir is None and run_fn is safe_subprocess_run and not is_temp_workspace(exec_root):
            exec_root, _ = _create_nvme_mirror(self.cwd)
            own_mirror_root = exec_root.parent

        norm_hint = Path(target_file_hint).stem if target_file_hint else None
        try:
            if run_fn is safe_subprocess_run:
                batched = collect_passed_lines_batched(
                    passed_test_names,
                    exec_root,
                    run_fn,
                    target_file_hint=target_file_hint,
                    timeout_sec=timeout_sec,
                )
                if batched is not None:
                    return batched
            return _collect_passed_lines_trace_fallback(
                passed_test_names, exec_root, self.cwd, run_fn, norm_hint, timeout_sec
            )
        finally:
            if own_mirror_root is not None:
                safe_rmtree(own_mirror_root)

    def _collect_run_coverage(
        self,
        exec_cwd: Path,
        run_fn: Any,
        summary: PytestRunSummary,
        target_file_hint: Optional[str],
        timeout_sec: float,
    ) -> Tuple[Optional[Dict[Tuple[str, int], int]], Optional[List[CoverageRecord]]]:
        """Raccoglie CoverageRecord pass/fail o conteggi fallback per la diagnosi."""
        all_tests = list(summary.passed_test_names) + list(summary.failed_test_names)
        if run_fn is safe_subprocess_run and all_tests:
            return collect_coverage_records_batched(
                all_tests,
                exec_cwd,
                run_fn,
                target_file_hint=target_file_hint,
                timeout_sec=timeout_sec,
            )
        if summary.passed_test_names:
            counts = self.collect_passed_line_counts(
                summary.passed_test_names,
                target_file_hint=target_file_hint,
                timeout_sec=min(timeout_sec, 30.0),
            )
            return counts, None
        return None, None

    def extract_failure_location(
        self,
        summary: PytestRunSummary,
        target_file_hint: Optional[str] = None,
        passed_line_counts: Optional[Dict[Tuple[str, int], int]] = None,
        coverage_records: Optional[Sequence[CoverageRecord]] = None,
    ) -> Optional[OchiaiBridgeLocation]:
        """Estrae il guasto tramite CoverageMatrix + SBFLEngine e codice frame-specific."""
        if summary.exit_code == 0:
            return None
        lines = (summary.raw_stdout + "\n" + summary.raw_stderr).splitlines()
        norm_hint = Path(target_file_hint).name if target_file_hint else None
        error_type, error_msg, ordered_locs, frame_counts, frame_code_map = (
            _parse_traceback_diagnostics(lines, norm_hint)
        )

        top_score: Optional[SBFLScore] = None
        if coverage_records:
            best, ranked, payload = rank_bridge_coverage(
                coverage_records, norm_hint=norm_hint, preferred_locations=ordered_locs
            )
            if best is not None and best.spectrum.n_ef > 0:
                top_score = best
                self.last_ranked_scores = ranked
                self.last_diagnostic_payload = payload

        if top_score is not None:
            target_file, target_line = split_stmt(top_score.statement)
        else:
            target_file, target_line = (
                ordered_locs[0]
                if ordered_locs
                else (str(target_file_hint) if target_file_hint else "unknown.py", 1)
            )
            total_failed = max(1, summary.failed_count)
            cnt = frame_counts.get((target_file, target_line), 0)
            n_ef = total_failed if cnt == 0 else min(total_failed, cnt)
            n_ep = (
                _lookup_passed_line_count(passed_line_counts, target_file, target_line)
                if passed_line_counts is not None
                else 0
            )
            fb_recs = build_fallback_coverage_records(
                f"{target_file}:{target_line}", total_failed, n_ef, summary.passed_count, n_ep
            )
            top_score, ranked, payload = rank_bridge_coverage(
                fb_recs, norm_hint=Path(target_file).name
            )
            self.last_ranked_scores = ranked
            self.last_diagnostic_payload = payload

        failing_code = _lookup_frame_code(frame_code_map, target_file, target_line)
        if not failing_code:
            failing_code = _read_source_line(self._active_mirror_dir, self.cwd, target_file, target_line)

        spec = top_score.spectrum  # type: ignore[union-attr]
        return OchiaiBridgeLocation(
            file_path=target_file,
            line_number=target_line,
            suspiciousness=min(1.0, top_score.ochiai),  # type: ignore[union-attr]
            error_type=error_type,
            error_message=error_msg,
            failing_line_content=failing_code,
            total_failed_tests=spec.total_failed,
            n_ef=spec.n_ef,
            n_ep=spec.n_ep,
            n_nf=spec.n_nf,
            n_np=spec.n_np,
            tarantula=top_score.tarantula,  # type: ignore[union-attr]
            dstar=top_score.dstar,  # type: ignore[union-attr]
        )

    def run_and_diagnose(
        self,
        test_cmd: Sequence[str] | str,
        target_file_hint: Optional[str] = None,
        timeout_sec: float = 60.0,
        passed_line_counts: Optional[Dict[Tuple[str, int], int]] = None,
        collect_pass_coverage: bool = True,
    ) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        """Esegue pytest su mirror NVMe e calcola localizzazione SBFL reale (CoverageMatrix)."""
        cmd_str = test_cmd if isinstance(test_cmd, str) else " ".join(str(part) for part in test_cmd)
        has_cov_flag = "--cov" in cmd_str
        is_pytest = _is_pytest_command(cmd_str)
        effective_cmd: Sequence[str] | str = (
            _strip_quiet_and_add_verbose(test_cmd)
            if (collect_pass_coverage and is_pytest)
            else test_cmd
        )

        run_fn = _resolve_safe_subprocess_run()
        mirror_dir: Optional[Path] = None
        mirror_root: Optional[Path] = None
        temp_bt: Optional[tempfile.TemporaryDirectory[str]] = None

        try:
            if is_pytest and run_fn is safe_subprocess_run and not is_temp_workspace(self.cwd):
                mirror_dir, bt_dir = _create_nvme_mirror(self.cwd)
                mirror_root = mirror_dir.parent
                exec_cwd = mirror_dir
                effective_cmd = _append_pytest_iso_flags(_rewrite_cmd_for_mirror(effective_cmd, self.cwd, mirror_dir), bt_dir)
                run_env = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(mirror_dir)}
                self._active_mirror_dir = mirror_dir
            else:
                exec_cwd = self.cwd
                run_env = {"PYTHONDONTWRITEBYTECODE": "1"}
                if is_pytest:
                    temp_bt = tempfile.TemporaryDirectory(prefix="nk_sbfl_bt_")
                    effective_cmd = _append_pytest_iso_flags(effective_cmd, Path(temp_bt.name))

            t0 = time.perf_counter()
            rc, stdout, stderr = run_fn(cmd=effective_cmd, cwd=str(exec_cwd), timeout=timeout_sec, env=run_env)
            duration = time.perf_counter() - t0
            if mirror_dir is not None:
                stdout = _normalize_mirror_output(stdout, mirror_dir)
                stderr = _normalize_mirror_output(stderr, mirror_dir)

            summary = self.parse_pytest_output(stdout, stderr, rc, duration)
            eff_passed_counts = passed_line_counts
            eff_records: Optional[List[CoverageRecord]] = None
            if (
                eff_passed_counts is None
                and collect_pass_coverage
                and not has_cov_flag
                and not _resolve_monitoring_conflict()
                and summary.exit_code != 0
            ):
                eff_passed_counts, eff_records = self._collect_run_coverage(
                    exec_cwd, run_fn, summary, target_file_hint, timeout_sec
                )

            loc = self.extract_failure_location(
                summary,
                target_file_hint=target_file_hint,
                passed_line_counts=eff_passed_counts,
                coverage_records=eff_records,
            )
            return summary, loc
        finally:
            self._active_mirror_dir = None
            if temp_bt is not None:
                temp_bt.cleanup()
            if mirror_root is not None:
                safe_rmtree(mirror_root)
