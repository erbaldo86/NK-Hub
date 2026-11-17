"""Logica SBFLPytestBridge per esecuzione pytest e localizzazione Ochiai."""

from __future__ import annotations

import json
import math
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.paths import reconfigure_streams
from _internal.sbfl_pytest_bridge.models import (
    OchiaiBridgeLocation,
    PytestRunSummary,
    compute_ochiai,
)
try:
    from platform_runner import safe_subprocess_run
except ImportError:
    from scripts.platform_runner import safe_subprocess_run
try:
    from sbfl_engine import SpectrumCounts, calculate_ochiai, is_monitoring_conflict_active
except ImportError:
    from scripts.sbfl_engine import SpectrumCounts, calculate_ochiai
    def is_monitoring_conflict_active() -> bool:
        return sys.gettrace() is not None or "pytest_cov" in sys.modules


def _resolve_bridge_facade_attr(attr_name: str, default_val: Any) -> Any:
    """Risolve eventuali monkeypatch applicati sulla facciata o alias sbfl_pytest_bridge."""
    mod_a = sys.modules.get("sbfl_pytest_bridge")
    mod_b = sys.modules.get("scripts.sbfl_pytest_bridge")
    for mod in (mod_a, mod_b, *reversed(list(sys.modules.values()))):
        if mod is None:
            continue
        mod_file = getattr(mod, "__file__", "") or ""
        if (
            mod is mod_a
            or mod is mod_b
            or mod_file.endswith(("sbfl_pytest_bridge.py", "sbfl_pytest_bridge.pyc"))
        ):
            try:
                mod_vars = vars(mod)
            except TypeError:
                continue
            if attr_name in mod_vars:
                val = getattr(mod, attr_name)
                if val is not None and val is not default_val:
                    return val
    return default_val


def _resolve_safe_subprocess_run():
    return _resolve_bridge_facade_attr("safe_subprocess_run", safe_subprocess_run)

class SBFLPytestBridge:
    """Ponte che coordina l'esecuzione pytest, il parsing dei traceback e il calcolo Ochiai."""

    compute_ochiai = staticmethod(compute_ochiai)
    TRACEBACK_FILE_RE = re.compile(
        r"((?:[A-Za-z]:[\\/])?[A-Za-z0-9_\-\./\\ ]+\.py):(\d+):"
    )

    def __init__(self, cwd: Optional[Path] = None):
        reconfigure_streams()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    def parse_pytest_output(
        self, stdout: str, stderr: str, exit_code: int, duration_sec: float = 0.0
    ) -> PytestRunSummary:
        """Analizza stdout e stderr di pytest per estrarre le statistiche di esito."""
        passed_tests: List[str] = []
        failed_tests: List[str] = []

        for line in stdout.splitlines():
            clean_line = line.strip()
            if " PASSED" in clean_line:
                tname = clean_line.split(" PASSED")[0].strip()
                if tname and tname not in passed_tests:
                    passed_tests.append(tname)
            elif " FAILED" in clean_line:
                tname = clean_line.split(" FAILED")[0].strip()
                if tname and tname not in failed_tests:
                    failed_tests.append(tname)

        failed_cnt = len(failed_tests)
        passed_cnt = len(passed_tests)

        if failed_cnt == 0 and passed_cnt == 0:
            p_match = re.search(r"(\d+)\s+passed", stdout)
            f_match = re.search(r"(\d+)\s+failed", stdout)
            if p_match:
                passed_cnt = int(p_match.group(1))
            if f_match:
                failed_cnt = int(f_match.group(1))

        total_cnt = failed_cnt + passed_cnt

        return PytestRunSummary(
            total_tests=total_cnt,
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
        """Raccoglie i conteggi n_ep dei test passati disattivandosi se pytest-cov o trace sono attivi."""
        counts: Dict[Tuple[str, int], int] = {}
        conflict_fn = _resolve_bridge_facade_attr(
            "is_monitoring_conflict_active", is_monitoring_conflict_active
        )
        if not passed_test_names or conflict_fn():
            return counts

        norm_hint = Path(target_file_hint).stem if target_file_hint else None
        for node_id in list(passed_test_names)[:15]:
            with tempfile.TemporaryDirectory(prefix="nk_sbfl_cov_") as cov_dir:
                cmd = [
                    sys.executable,
                    "-B",
                    "-m",
                    "trace",
                    "--count",
                    "-C",
                    cov_dir,
                    "-m",
                    "pytest",
                    node_id,
                    "-q",
                    "--no-header",
                ]
                rc, _, _ = _resolve_safe_subprocess_run()(
                    cmd=cmd,
                    cwd=str(self.cwd),
                    timeout=min(timeout_sec, 15.0),
                    env={"PYTHONDONTWRITEBYTECODE": "1"},
                )
                if rc != 0:
                    continue
                for cover_file in Path(cov_dir).glob("*.cover"):
                    stem = cover_file.stem.split(".")[-1]
                    if norm_hint and stem != norm_hint:
                        continue
                    fname_key = f"{stem}.py"
                    try:
                        cov_lines = cover_file.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                    except OSError:
                        continue
                    for idx, raw_ln in enumerate(cov_lines, start=1):
                        m_cnt = re.match(r"^\s*(\d+):", raw_ln)
                        if m_cnt and int(m_cnt.group(1)) > 0:
                            counts[(fname_key, idx)] = (
                                counts.get((fname_key, idx), 0) + 1
                            )
        return counts

    def extract_failure_location(
        self,
        summary: PytestRunSummary,
        target_file_hint: Optional[str] = None,
        passed_line_counts: Optional[Dict[Tuple[str, int], int]] = None,
    ) -> Optional[OchiaiBridgeLocation]:
        """Estrae la posizione della riga responsabile del fallimento e calcola lo score Ochiai."""
        if summary.exit_code == 0:
            return None

        combined_text = summary.raw_stdout + "\n" + summary.raw_stderr
        lines = combined_text.splitlines()

        target_file: Optional[str] = None
        target_line: int = 1
        error_type: str = "TestFailure"
        error_msg: str = "Test failed"
        failing_code: str = ""

        for line in reversed(lines):
            line_str = line.strip()
            if line_str.startswith("E   ") or line_str.startswith("E:  "):
                err_content = line_str[4:].strip()
                if ":" in err_content:
                    parts = err_content.split(":", 1)
                    error_type = parts[0].strip()
                    error_msg = parts[1].strip()
                else:
                    error_type = "AssertionError"
                    error_msg = err_content
                break

        norm_hint = Path(target_file_hint).name if target_file_hint else None
        location_counts: Dict[Tuple[str, int], int] = {}

        for i, line in enumerate(lines):
            line_str = line.strip()
            if line_str.startswith(">") and i > 0:
                failing_code = line_str.lstrip("> ").strip()

            match = self.TRACEBACK_FILE_RE.search(line_str)
            if match:
                fpath = match.group(1).strip().replace("\\", "/")
                lno = int(match.group(2))
                if norm_hint:
                    if norm_hint in fpath:
                        target_file = fpath
                        target_line = lno
                        location_counts[(fpath, lno)] = (
                            location_counts.get((fpath, lno), 0) + 1
                        )
                elif "test_" not in Path(fpath).name.lower():
                    target_file = fpath
                    target_line = lno
                    location_counts[(fpath, lno)] = (
                        location_counts.get((fpath, lno), 0) + 1
                    )

        if location_counts:
            target_file, target_line = max(
                location_counts.items(), key=lambda kv: kv[1]
            )[0]

        if not target_file and target_file_hint:
            target_file = str(target_file_hint)
        elif not target_file:
            target_file = "unknown.py"

        if not failing_code and target_file:
            try:
                candidate_path = Path(self.cwd / target_file)
                if not candidate_path.exists():
                    candidate_path = Path(target_file)
                if candidate_path.exists():
                    flines = candidate_path.read_text(encoding="utf-8").splitlines()
                    if 1 <= target_line <= len(flines):
                        failing_code = flines[target_line - 1].strip()
            except OSError:
                failing_code = ""

        total_failed = max(1, summary.failed_count)
        count = location_counts.get((target_file, target_line), 0)
        if count == 0:
            n_ef = total_failed
        else:
            n_ef = min(total_failed, count)

        if passed_line_counts is not None:
            n_ep = passed_line_counts.get(
                (target_file, target_line),
                passed_line_counts.get((Path(target_file).name, target_line), 0),
            )
            ochiai_score = calculate_ochiai(
                SpectrumCounts(
                    n_ef=n_ef,
                    n_ep=n_ep,
                    n_nf=max(0, total_failed - n_ef),
                    n_np=max(0, summary.passed_count - n_ep),
                )
            )
        else:
            n_ep = 0
            denominator = math.sqrt(total_failed * (n_ef + n_ep))
            ochiai_score = (n_ef / denominator) if denominator > 0 else 1.0

        return OchiaiBridgeLocation(
            file_path=target_file,
            line_number=target_line,
            suspiciousness=min(1.0, ochiai_score),
            error_type=error_type,
            error_message=error_msg,
            failing_line_content=failing_code,
            total_failed_tests=total_failed,
            n_ef=n_ef,
            n_ep=n_ep,
        )

    def run_and_diagnose(
        self,
        test_cmd: Sequence[str] | str,
        target_file_hint: Optional[str] = None,
        timeout_sec: float = 60.0,
        passed_line_counts: Optional[Dict[Tuple[str, int], int]] = None,
        collect_pass_coverage: bool = False,
    ) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        """Esegue pytest e restituisce riepilogo e localizzazione Ochiai."""
        cmd_str = (
            test_cmd
            if isinstance(test_cmd, str)
            else " ".join(str(part) for part in test_cmd)
        )
        has_cov_flag = "--cov" in cmd_str
        effective_cmd: Sequence[str] | str = test_cmd
        if collect_pass_coverage and isinstance(test_cmd, str) and "-v" not in test_cmd:
            effective_cmd = f"{test_cmd} -v"
        elif (
            collect_pass_coverage
            and isinstance(test_cmd, (list, tuple))
            and "-v" not in test_cmd
        ):
            effective_cmd = list(test_cmd) + ["-v"]

        t0 = time.perf_counter()
        rc, stdout, stderr = _resolve_safe_subprocess_run()(
            cmd=effective_cmd,
            cwd=str(self.cwd),
            timeout=timeout_sec,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )
        duration = time.perf_counter() - t0
        summary = self.parse_pytest_output(stdout, stderr, rc, duration)

        eff_passed_counts = passed_line_counts
        if (
            eff_passed_counts is None
            and collect_pass_coverage
            and not has_cov_flag
            and not is_monitoring_conflict_active()
            and summary.exit_code != 0
            and summary.passed_test_names
        ):
            eff_passed_counts = self.collect_passed_line_counts(
                summary.passed_test_names,
                target_file_hint=target_file_hint,
                timeout_sec=min(timeout_sec, 30.0),
            )

        loc = self.extract_failure_location(
            summary,
            target_file_hint=target_file_hint,
            passed_line_counts=eff_passed_counts,
        )
        return summary, loc
