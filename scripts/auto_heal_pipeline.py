#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline universale di auto-riparazione per Nexus Keystone v3.0.0.
Modulo: auto_heal_pipeline.py.
Implementa l'integrazione tra SBFL Ochiai, Rollback SHA-256 e Motore RSI.

Funzionalita principali:
1. Normalizza il comando pytest per l'esecuzione affidabile su Windows.
2. Esce immediatamente a ciclo 0 se tutti i test passano alla prima verifica.
3. Esegue fino a max_cycles tentativi con rollback transazionale su regressione.
4. Evita snapshot inutili dopo l'ultimo tentativo fallito e calcola le metriche RSI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict

_scripts_dir = Path(__file__).resolve().parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
for _d in (
    _root_dir,
    _root_dir / "scripts",
    _root_dir / ".staging" / "scripts",
    _scripts_dir,
):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
if str(_scripts_dir) in sys.path:
    sys.path.remove(str(_scripts_dir))
sys.path.insert(0, str(_scripts_dir))

try:
    from platform_runner import reconfigure_streams
    from sbfl_pytest_bridge import SBFLPytestBridge, OchiaiBridgeLocation
    from healing_snapshot_rollback import HealingSnapshotManager, FitnessVerdict
except ImportError:
    from scripts.platform_runner import reconfigure_streams
    from scripts.sbfl_pytest_bridge import SBFLPytestBridge, OchiaiBridgeLocation
    from scripts.healing_snapshot_rollback import HealingSnapshotManager, FitnessVerdict

try:
    from rsi_convergence_engine import (
        RSIConvergenceEngine,
        RSIDefectVector,
        RSIIterationRecord,
        compute_delta,
        compute_fitness,
    )
except ImportError:
    try:
        from scripts.rsi_convergence_engine import (
            RSIConvergenceEngine,
            RSIDefectVector,
            RSIIterationRecord,
            compute_delta,
            compute_fitness,
        )
    except ImportError:
        RSIConvergenceEngine = None  # type: ignore[assignment]
        RSIDefectVector = None  # type: ignore[assignment]
        RSIIterationRecord = None  # type: ignore[assignment]
        compute_delta = None  # type: ignore[assignment]
        compute_fitness = None  # type: ignore[assignment]

try:
    from ast_guard_validator import ASTGuardValidator
except ImportError:
    try:
        from scripts.ast_guard_validator import ASTGuardValidator
    except ImportError:
        ASTGuardValidator = None  # type: ignore[assignment]


def normalize_test_command(cmd: Union[str, Sequence[str]]) -> Union[str, List[str]]:
    """Normalizza il comando pytest premettendo sys.executable -m pytest su Windows."""
    if isinstance(cmd, str):
        clean = cmd.strip()
        if clean == "pytest":
            return f'"{sys.executable}" -m pytest'
        elif clean.startswith("pytest "):
            rest = clean[7:].strip()
            return f'"{sys.executable}" -m pytest {rest}'
        return cmd
    elif isinstance(cmd, (list, tuple)):
        cmd_list = list(cmd)
        if len(cmd_list) > 0 and str(cmd_list[0]).lower() == "pytest":
            return [sys.executable, "-m", "pytest"] + cmd_list[1:]
        return cmd_list
    return cmd


def _build_defect_vector(
    target_path: Optional[Path],
    pre_code: str,
    passed: int,
    failed: int,
) -> Any:
    """Costruisce RSIDefectVector combinando risultati Pytest e controlli AST/SAST."""
    if RSIDefectVector is None:
        return None
    sast_crit = 0
    contract_viol = 0
    if target_path is not None and target_path.exists() and ASTGuardValidator is not None:
        try:
            post_code = target_path.read_text(encoding="utf-8", errors="replace")
            rep = ASTGuardValidator.validate_code_edit(
                pre_code or post_code, post_code, target_file=target_path.name
            )
            if not rep.is_valid:
                contract_viol = len(rep.violations)
            sast_crit = len(ASTGuardValidator.check_sast_constructs(post_code))
        except Exception:
            pass
    return RSIDefectVector(
        sast_critical=sast_crit,
        tests_passed=max(0, passed),
        tests_failed=max(0, failed),
        tests_total=max(1, passed + failed),
        contract_violations=contract_viol,
    )


def _compute_rsi_metrics(
    passed: int,
    failed: int,
    target_path: Optional[Path] = None,
    pre_code: str = "",
) -> tuple[int, float]:
    """Calcola Delta_k e Q(S_k) usando il motore RSI."""
    if RSIDefectVector is not None and compute_delta is not None and compute_fitness is not None:
        vec = _build_defect_vector(target_path, pre_code, passed, failed)
        d_k = compute_delta(vec)
        q_k = compute_fitness(vec, delta_k=d_k)
        return d_k, q_k
    d_k = 10 * max(0, failed)
    total = max(1, passed + failed)
    q_k = round(60.0 * (passed / total) + (40.0 / (1.0 + d_k / 25.0)), 4)
    return d_k, q_k


class AutoHealSessionReport(BaseModel):
    """Rapporto strutturato di una sessione di auto-riparazione con metriche RSI."""

    model_config = ConfigDict(strict=True, extra="forbid")

    success: bool
    cycles_used: int
    max_cycles: int
    initial_failed: int
    final_failed: int
    fault_location: Optional[str] = None
    error_type: Optional[str] = None
    ochiai_score: Optional[float] = None
    patch_note_line: Optional[str] = None
    rolled_back: bool = False
    rsi_delta: int = 0
    rsi_fitness_q: float = 100.0
    message: str


class AutoHealPipeline:
    """Orchestratore end-to-end del ciclo di auto-riparazione."""

    def __init__(self, cwd: Optional[Path] = None, max_cycles: int = 3):
        reconfigure_streams()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()
        self.max_cycles = max_cycles
        self.bridge = SBFLPytestBridge(cwd=self.cwd)
        self.snapshot_mgr = HealingSnapshotManager()
        telemetry_target = (
            self.cwd / ".staging" / "nk_tracking" / "rsi_telemetry.jsonl"
            if (self.cwd / ".staging" / "nk_tracking").exists()
            else self.cwd / "nk_tracking" / "rsi_telemetry.jsonl"
        )
        self.rsi_engine = (
            RSIConvergenceEngine(
                workspace_root=self.cwd,
                telemetry_path=telemetry_target,
            )
            if RSIConvergenceEngine is not None
            else None
        )

    def normalize_test_cmd(
        self, test_cmd: Union[str, Sequence[str]]
    ) -> Union[str, List[str]]:
        """Metodo di istanza per la normalizzazione del comando pytest."""
        return normalize_test_command(test_cmd)

    def _record_rsi_iteration(
        self,
        session_id: str,
        iteration: int,
        target_path: Path,
        pre_code: str,
        passed: int,
        failed: int,
        verdict: str,
        rolled_back: bool = False,
    ) -> tuple[int, float]:
        """Registra un'iterazione in rsi_telemetry.jsonl tramite RSIConvergenceEngine."""
        d_k, q_k = _compute_rsi_metrics(passed, failed, target_path, pre_code)
        if self.rsi_engine is not None and RSIIterationRecord is not None:
            try:
                vec = _build_defect_vector(target_path, pre_code, passed, failed)
                s_hash = self.rsi_engine.compute_files_state_hash([target_path])
                self.rsi_engine.append_telemetry_record(
                    RSIIterationRecord(
                        session_id=session_id,
                        iteration=iteration,
                        mode="mode_b",
                        defects=vec,
                        delta_k=d_k,
                        fitness_q=q_k,
                        state_hash=s_hash,
                        verdict=verdict,
                        rolled_back=rolled_back,
                    )
                )
            except Exception:
                pass
        return d_k, q_k

    def run_pipeline(
        self,
        test_cmd: Sequence[str] | str,
        target_file: Path | str,
        repair_callback: Optional[Callable[[OchiaiBridgeLocation, int], bool]] = None,
    ) -> AutoHealSessionReport:
        """Esegue il ciclo di auto-riparazione sul file target guidato da test_cmd."""
        norm_test_cmd = normalize_test_command(test_cmd)
        target_path = (
            Path(self.cwd / target_file)
            if not Path(target_file).is_absolute()
            else Path(target_file)
        )
        pre_code = (
            target_path.read_text(encoding="utf-8", errors="replace")
            if target_path.exists()
            else ""
        )
        session_id = f"HEAL-{target_path.stem}"

        # Valutazione iniziale prima di creare snapshot di ciclo
        summary, loc = self.bridge.run_and_diagnose(
            test_cmd=norm_test_cmd, target_file_hint=str(target_file)
        )

        if summary.exit_code == 0 and summary.failed_count == 0:
            self._record_rsi_iteration(
                session_id=session_id,
                iteration=0,
                target_path=target_path,
                pre_code=pre_code,
                passed=summary.passed_count,
                failed=0,
                verdict="CONVERGED_OPTIMAL",
                rolled_back=False,
            )
            return AutoHealSessionReport(
                success=True,
                cycles_used=0,
                max_cycles=self.max_cycles,
                initial_failed=0,
                final_failed=0,
                rsi_delta=0,
                rsi_fitness_q=100.0,
                message="Clean build: All tests passing on initial evaluation.",
            )

        self._record_rsi_iteration(
            session_id=session_id,
            iteration=0,
            target_path=target_path,
            pre_code=pre_code,
            passed=summary.passed_count,
            failed=summary.failed_count,
            verdict="REFINING",
            rolled_back=False,
        )

        init_snap_id = self.snapshot_mgr.create_snapshot([target_path])
        initial_failed = summary.failed_count
        prev_failed = summary.failed_count
        prev_passed = summary.passed_count
        latest_loc = loc

        for cycle in range(1, self.max_cycles + 1):
            cycle_snap_id = (
                None
                if cycle >= self.max_cycles
                else (
                    init_snap_id
                    if cycle == 1
                    else self.snapshot_mgr.create_snapshot([target_path])
                )
            )

            if repair_callback and latest_loc:
                try:
                    repair_callback(latest_loc, cycle)
                except Exception:
                    pass

            new_summary, new_loc = self.bridge.run_and_diagnose(
                test_cmd=norm_test_cmd, target_file_hint=str(target_file)
            )

            fitness = self.snapshot_mgr.evaluate_fitness(
                current_passed=new_summary.passed_count,
                current_failed=new_summary.failed_count,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=new_summary.exit_code,
            )

            if fitness.verdict == FitnessVerdict.PASSED:
                self._record_rsi_iteration(
                    session_id=session_id,
                    iteration=cycle,
                    target_path=target_path,
                    pre_code=pre_code,
                    passed=new_summary.passed_count,
                    failed=0,
                    verdict="CONVERGED_OPTIMAL",
                    rolled_back=False,
                )
                self.snapshot_mgr.cleanup()
                patch_note = ""
                if latest_loc:
                    patch_note = (
                        f"- **[AUTO-HEALED]** `{latest_loc.error_type}` in "
                        f"`{Path(latest_loc.file_path).name}:{latest_loc.line_number}` "
                        f"(Cycles: {cycle}, Ochiai: {round(latest_loc.suspiciousness, 3)})"
                    )
                return AutoHealSessionReport(
                    success=True,
                    cycles_used=cycle,
                    max_cycles=self.max_cycles,
                    initial_failed=initial_failed,
                    final_failed=0,
                    fault_location=(
                        f"{latest_loc.file_path}:{latest_loc.line_number}"
                        if latest_loc
                        else None
                    ),
                    error_type=latest_loc.error_type if latest_loc else None,
                    ochiai_score=latest_loc.suspiciousness if latest_loc else None,
                    patch_note_line=patch_note,
                    rolled_back=False,
                    rsi_delta=0,
                    rsi_fitness_q=100.0,
                    message=f"Healed successfully on cycle {cycle} via strict fitness gate.",
                )

            elif fitness.verdict == FitnessVerdict.REGRESSION:
                if cycle_snap_id is not None:
                    self.snapshot_mgr.rollback(cycle_snap_id)
                    if cycle_snap_id != init_snap_id:
                        self.snapshot_mgr.cleanup(cycle_snap_id)
                self._record_rsi_iteration(
                    session_id=session_id,
                    iteration=cycle,
                    target_path=target_path,
                    pre_code=pre_code,
                    passed=new_summary.passed_count,
                    failed=new_summary.failed_count,
                    verdict="ROLLED_BACK_HARD_GATE",
                    rolled_back=True,
                )
            else:
                prev_failed = new_summary.failed_count
                prev_passed = new_summary.passed_count
                latest_loc = new_loc
                if cycle_snap_id is not None and cycle_snap_id != init_snap_id:
                    self.snapshot_mgr.cleanup(cycle_snap_id)
                self._record_rsi_iteration(
                    session_id=session_id,
                    iteration=cycle,
                    target_path=target_path,
                    pre_code=pre_code,
                    passed=prev_passed,
                    failed=prev_failed,
                    verdict="REFINING",
                    rolled_back=False,
                )

        # Ripristina lo stato iniziale se i tentativi sono esauriti senza successo
        self.snapshot_mgr.rollback(init_snap_id)
        self.snapshot_mgr.cleanup()

        rsi_d, rsi_q = _compute_rsi_metrics(prev_passed, prev_failed, target_path, pre_code)
        return AutoHealSessionReport(
            success=False,
            cycles_used=self.max_cycles,
            max_cycles=self.max_cycles,
            initial_failed=initial_failed,
            final_failed=prev_failed,
            fault_location=(
                f"{latest_loc.file_path}:{latest_loc.line_number}"
                if latest_loc
                else None
            ),
            error_type=latest_loc.error_type if latest_loc else None,
            ochiai_score=latest_loc.suspiciousness if latest_loc else None,
            rolled_back=True,
            rsi_delta=rsi_d,
            rsi_fitness_q=rsi_q,
            message="Exhausted maximum healing cycles. Rollback to original state completed.",
        )


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Universal CLI Auto-Healer Pipeline"
    )
    parser.add_argument(
        "--test-cmd",
        type=str,
        default="pytest -q",
        required=False,
        help="Comando pytest da eseguire",
    )
    parser.add_argument(
        "--target-file",
        type=str,
        default="",
        required=False,
        help="File sorgente target da riparare",
    )
    parser.add_argument(
        "--cwd", type=str, default=None, help="Directory di lavoro"
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=3,
        help="Numero massimo di cicli di riparazione (default: 3)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Stampa il rapporto di sessione in JSON"
    )

    args = parser.parse_args()
    cwd_path = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    target_file_str = args.target_file.strip() if args.target_file else ""
    if not target_file_str:
        stg_dir = cwd_path / ".staging"
        stg_py = (
            sorted(f for f in stg_dir.rglob("*.py") if "__pycache__" not in f.parts)
            if stg_dir.exists()
            else []
        )
        if stg_py:
            target_file_str = str(stg_py[0])
        else:
            report = AutoHealSessionReport(
                success=True,
                cycles_used=0,
                max_cycles=args.max_cycles,
                initial_failed=0,
                final_failed=0,
                message="Clean staging: no target file required healing.",
            )
            if args.json:
                print(report.model_dump_json(indent=2))
            else:
                print(f"🟢 [AUTO-HEAL] {report.message}")
            return 0

    pipeline = AutoHealPipeline(
        cwd=Path(args.cwd) if args.cwd else None, max_cycles=args.max_cycles
    )
    norm_cmd = normalize_test_command(args.test_cmd)
    report = pipeline.run_pipeline(test_cmd=norm_cmd, target_file=target_file_str)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        if report.success:
            print(f"🟢 [AUTO-HEAL] {report.message}")
            if report.patch_note_line:
                print(f"📝 [PATCH-NOTE] {report.patch_note_line}")
        else:
            print(f"🔴 [AUTO-HEAL] {report.message}")
            if report.fault_location:
                print(
                    f"   Last detected fault: {report.fault_location} ({report.error_type})"
                )

    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())
