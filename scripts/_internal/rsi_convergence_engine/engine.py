"""Classe canonica RSIConvergenceEngine e entrypoint di modulo emit_gt14_bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from _internal.rsi_convergence_engine.ab_benchmark import run_ab_benchmark
from _internal.rsi_convergence_engine.benchmark_and_vibe import (
    run_benchmark_suite_impl,
    run_vibe_check_impl,
)
from _internal.rsi_convergence_engine.canary_holdout import evaluate_canary_holdout
from _internal.rsi_convergence_engine.constants import (
    MODE_ITERATION_CAPS,
    _TELEMETRY_LOCK,
    RSIDefectVector,
    RSIIterationRecord,
    RSISessionReport,
    _collect_overlay_md_files,
    _workspace_root,
    load_staging_deleted_set_impl,
    resolve_candidate_impl,
)
from _internal.rsi_convergence_engine.ecosystem_verify import verify_ecosystem_impl
from _internal.rsi_convergence_engine.gt14_bundle import emit_gt14_bundle_impl
from _internal.rsi_convergence_engine.lazy_bridge import (
    get_healing_snapshot_manager_cls,
    get_reconfigure_streams,
)
from _internal.rsi_convergence_engine.loop_and_cove import (
    append_telemetry_record_impl,
    check_hard_gate_regression_impl,
    compute_files_state_hash_impl,
    compute_record_hash_impl,
    extract_script_supported_flags_impl,
    get_last_telemetry_hash_impl,
    run_convergence_loop_impl,
    verify_cli_flags_cove_impl,
    verify_telemetry_chain_impl,
)
from _internal.rsi_convergence_engine.profiles import compute_delta, compute_fitness
from _internal.rsi_convergence_engine.sast_scanner import scan_sast_and_mojibake_impl


class RSIConvergenceEngine:
    """Motore deterministico di convergenza RSI con guardie G1..G6."""

    _TELEMETRY_LOCK = _TELEMETRY_LOCK

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        telemetry_path: Optional[Path] = None,
        root: Optional[Path] = None,
    ) -> None:
        get_reconfigure_streams()
        effective_root = root if root is not None else workspace_root
        self.workspace_root = (
            Path(effective_root).resolve() if effective_root else _workspace_root
        )
        self.root = self.workspace_root
        self.telemetry_path = (
            Path(telemetry_path).resolve()
            if telemetry_path
            else self.workspace_root / "nk_tracking" / "rsi_telemetry.jsonl"
        )
        self._snapshot_mgr_loaded = False
        self._snapshot_mgr: Any = None

    @property
    def snapshot_mgr(self) -> Any:
        """Istanzia in modo lazy HealingSnapshotManager evitando overhead nei percorsi CLI rapidi."""
        if not self._snapshot_mgr_loaded:
            self._snapshot_mgr_loaded = True
            cls_mgr = get_healing_snapshot_manager_cls()
            self._snapshot_mgr = cls_mgr() if cls_mgr is not None else None
        return self._snapshot_mgr

    @snapshot_mgr.setter
    def snapshot_mgr(self, value: Any) -> None:
        self._snapshot_mgr_loaded = True
        self._snapshot_mgr = value

    @staticmethod
    def get_max_iterations(mode: str = "mode_a") -> int:
        """Restituisce il cap di iterazioni per la modalita specificata (Guardia G5)."""
        return MODE_ITERATION_CAPS.get(mode.lower().strip(), 4)

    @staticmethod
    def evaluate_canary_holdout(
        holdout_path: Optional[Path] = None,
        simulated_outcomes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Valuta i task del Canary Holdout Impossibile penalizzando ogni forzatura PASS."""
        return evaluate_canary_holdout(
            holdout_path=holdout_path, simulated_outcomes=simulated_outcomes
        )

    @staticmethod
    def compute_delta(defects: RSIDefectVector, profile: str = "code_rsi") -> int:
        """Calcola la metrica lineare Delta_k."""
        return compute_delta(defects, profile=profile)

    @staticmethod
    def compute_fitness(
        defects: RSIDefectVector,
        delta_k: Optional[int] = None,
        profile: str = "code_rsi",
    ) -> float:
        """Calcola la fitness Q(S_k)."""
        return compute_fitness(defects, delta_k=delta_k, profile=profile)

    @staticmethod
    def is_converged(defects: RSIDefectVector, profile: str = "code_rsi") -> bool:
        """Verifica la condizione di stop Guardia G1 (Delta_k == 0 e Q(S_k) >= 100.0)."""
        d_k = compute_delta(defects, profile=profile)
        q_k = compute_fitness(defects, delta_k=d_k, profile=profile)
        return d_k == 0 and q_k >= 100.0

    @staticmethod
    def check_hard_gate_regression(
        prev_defects: RSIDefectVector,
        curr_defects: RSIDefectVector,
        strict_monotonic: bool = False,
    ) -> Tuple[bool, str]:
        """Verifica se gli Hard Invariants sono peggiorati rispetto allo stato precedente (Guardia G2)."""
        return check_hard_gate_regression_impl(
            prev_defects, curr_defects, strict_monotonic=strict_monotonic
        )

    @staticmethod
    def compute_files_state_hash(target_files: Sequence[Path | str]) -> str:
        """Calcola l'hash SHA-256 cumulativo reale dei contenuti dei file target per Guardia G3/G6."""
        return compute_files_state_hash_impl(target_files)

    @staticmethod
    def _compute_record_hash(record_dict: Dict[str, Any]) -> str:
        """Calcola l'hash SHA-256 canonico di un record telemetrico."""
        return compute_record_hash_impl(record_dict)

    def _get_last_telemetry_hash(self) -> str:
        """Legge l'ultimo record_hash dal file rsi_telemetry.jsonl."""
        return get_last_telemetry_hash_impl(self)

    def append_telemetry_record(self, record: RSIIterationRecord) -> RSIIterationRecord:
        """Aggiunge in modo thread-safe un record alla catena SHA-256 (Guardia G4)."""
        return append_telemetry_record_impl(self, record)

    def verify_telemetry_chain(
        self, telemetry_path: Optional[Path] = None
    ) -> Tuple[bool, int, str]:
        """Verifica l'integrita crittografica della catena SHA-256 in rsi_telemetry.jsonl."""
        return verify_telemetry_chain_impl(self, telemetry_path=telemetry_path)

    def run_convergence_loop(
        self,
        evaluate_fn: Callable[[int], RSIDefectVector],
        refine_fn: Optional[Callable[[int, RSIDefectVector], bool]] = None,
        target_files: Optional[Sequence[Path | str]] = None,
        mode: str = "mode_a",
        session_id: Optional[str] = None,
        profile: str = "code_rsi",
    ) -> RSISessionReport:
        """Esegue il ciclo deterministico RSI applicando le guardie G1..G5."""
        return run_convergence_loop_impl(
            self,
            evaluate_fn,
            refine_fn=refine_fn,
            target_files=target_files,
            mode=mode,
            session_id=session_id,
            profile=profile,
        )

    def _resolve_candidate(self, root: Path, rel_path: str) -> Path:
        """Risolve un singolo file dando priorita a .staging/ se presente."""
        return resolve_candidate_impl(root, rel_path)

    @staticmethod
    def _collect_overlay_md_files(
        root: Path, rel_subdir: str, recursive: bool = True
    ) -> List[Path]:
        """Raccoglie tutti i file Markdown unendo produzione e override puntuali in .staging/."""
        return _collect_overlay_md_files(
            root=root, rel_subdir=rel_subdir, recursive=recursive
        )

    def _extract_script_supported_flags(self, script_path: Path) -> Set[str]:
        """Estrae i flag CLI --flag supportati nell'AST senza mai accettare wildcard."""
        return extract_script_supported_flags_impl(script_path)

    def verify_cli_flags_cove(self, root_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Verifica con rigore AST i flag CLI su skill, agent e workflow inclusi moduli schemas/*.py."""
        return verify_cli_flags_cove_impl(self, root_dir=root_dir)

    def run_vibe_check(
        self,
        target_path: Path | str,
        profile: str = "vibe_sprint_micro_rsi",
        sast_report: Optional[Path | str] = None,
        strict_verify: bool = False,
    ) -> Dict[str, Any]:
        """Esegue il micro-loop Vibe Check in-memory in meno di 500 ms."""
        return run_vibe_check_impl(
            self,
            target_path,
            profile=profile,
            sast_report=sast_report,
            strict_verify=strict_verify,
        )

    def run_ab_benchmark(
        self,
        suite_path: Optional[Path] = None,
        repetitions: int = 3,
    ) -> Dict[str, Any]:
        """Esegue il benchmark deterministico A/B sui dodici task core di NK Hub Generation."""
        return run_ab_benchmark(
            workspace_root=self.workspace_root,
            suite_path=suite_path,
            repetitions=repetitions,
        )

    def run_benchmark_suite(
        self, benchmark_suite: Path | str, root_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Esegue una suite A/B JSON o Pytest reale (-B, .staging in PYTHONPATH) restituendo metriche reali."""
        return run_benchmark_suite_impl(self, benchmark_suite, root_dir=root_dir)

    @staticmethod
    def _load_staging_deleted_set(root: Path) -> Set[str]:
        """Carica i percorsi relativi destinati a cancellazione da .staging/.deleted_files.json."""
        return load_staging_deleted_set_impl(root)

    def _scan_sast_and_mojibake(
        self,
        root: Path,
        sast_report: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Scansiona .staging/scripts, .staging/tests, root/scripts, root/tests e doc per SAST e U+FFFD."""
        return scan_sast_and_mojibake_impl(self, root, sast_report=sast_report)

    def verify_convergence(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Alias di verify_ecosystem con verifica rigorosa di Delta_k == 0 e Q(S_k) >= 100.0."""
        return self.verify_ecosystem(*args, **kwargs)

    def verify_ecosystem(
        self,
        root_dir: Optional[Path] = None,
        run_pytest: bool = False,
        profile: str = "code_rsi",
        benchmark_suite: Optional[str] = None,
        sast_report: Optional[Path | str] = None,
        strict_verify: bool = False,
        persist_telemetry: bool = False,
        test_report: Optional[Dict[str, Any]] = None,
        dast_report: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Esegue la verifica completa Guardia G6 sull'ecosistema con Overlay Union e metriche reali."""
        return verify_ecosystem_impl(
            self,
            root_dir=root_dir,
            run_pytest=run_pytest,
            profile=profile,
            benchmark_suite=benchmark_suite,
            sast_report=sast_report,
            strict_verify=strict_verify,
            persist_telemetry=persist_telemetry,
            test_report=test_report,
            dast_report=dast_report,
        )

    def emit_gt14_bundle(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        with_dast: bool = False,
        strict_verify: bool = False,
        output_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Esegue in-process le sonde GT-14 (6 -> 1) e salva atomicamente il bundle JSON."""
        return emit_gt14_bundle_impl(
            self,
            workspace_root=workspace_root,
            with_dast=with_dast,
            strict_verify=strict_verify,
            output_path=output_path,
        )


def emit_gt14_bundle(
    workspace_root: Optional[Union[str, Path]] = None,
    with_dast: bool = False,
    strict_verify: bool = False,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Funzione di modulo per eseguire emit_gt14_bundle in-process."""
    root = Path(workspace_root).resolve() if workspace_root else _workspace_root
    return RSIConvergenceEngine(workspace_root=root, root=root).emit_gt14_bundle(
        workspace_root=root,
        with_dast=with_dast,
        strict_verify=strict_verify,
        output_path=output_path,
    )
