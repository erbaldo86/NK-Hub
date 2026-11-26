# -*- coding: utf-8 -*-
"""Classe canonica RSIConvergenceEngine, emit_gt14_bundle e parser/dispatcher CLI."""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from _internal.rsi_convergence_engine.benchmark_and_vibe import run_benchmark_suite_impl, run_vibe_check_impl
from _internal.rsi_convergence_engine.canary_holdout import evaluate_canary_holdout
from _internal.rsi_convergence_engine.constants import (
    MODE_ITERATION_CAPS, _TELEMETRY_LOCK, RSIDefectVector, RSIIterationRecord, RSISessionReport,
    VIBE_SCAN_SUFFIXES, _collect_overlay_md_files, _workspace_root, get_healing_snapshot_manager_cls,
    get_reconfigure_streams, load_staging_deleted_set_impl, resolve_candidate_impl,
)
from _internal.rsi_convergence_engine.ecosystem_verify import verify_ecosystem_impl
from _internal.rsi_convergence_engine.gt14_probes import emit_gt14_bundle_impl
from _internal.rsi_convergence_engine.loop_and_cove import (
    append_telemetry_record_impl, check_hard_gate_regression_impl, compute_files_state_hash_impl,
    compute_record_hash_impl, extract_script_supported_flags_impl, get_last_telemetry_hash_impl,
    run_convergence_loop_impl, verify_cli_flags_cove_impl, verify_telemetry_chain_impl,
)
from _internal.rsi_convergence_engine.profiles import compute_delta, compute_fitness, compute_fitness_v2
from _internal.rsi_convergence_engine.sast_scanner import scan_sast_and_mojibake_impl

_CLI_BOOL_FLAGS: Tuple[Tuple[str, str], ...] = (
    ("--verify", "Verifica Guardia G6"), ("--strict-verify", "Pytest reale fail-closed"),
    ("--run-pytest", "Esegue suite pytest"), ("--ab-benchmark", "Legacy dismessa"),
    ("--verify-canary", "Canary Holdout read-only"), ("--emit-gt14-bundle", "Sonde GT-14 in-process"),
    ("--with-dast", "DAST overlay GT-14"), ("--scan-prod-frontend", "Audit frontend produzione"),
    ("--persist-telemetry", "Salva telemetria JSONL"), ("--strict-profile", "Rifiuta profili sconosciuti"),
    ("--diff-aware", "Attiva segnale diff Python solo su staging/allowed"), ("--json", "Output JSON"),
)
_CLI_STR_FLAGS: Tuple[Tuple[str, str], ...] = (
    ("--bundle-output", "Output JSON GT-14"), ("--sast-report", "Path report JSON SAST"),
    ("--mutation-report", "Path report JSON mutation"), ("--dast-report", "Path report JSON DAST"),
    ("--test-report", "Path report JSON test suite"), ("--coverage-report", "Path report JSON coverage"),
    ("--allowed-files", "CSV file consentiti in .staging/"), ("--profile", "Profilo Tensor-RSI (P1..P6)"),
    ("--lane-id", "ID lane di staging isolata"), ("--root", "Directory radice"),
)


def run_ab_benchmark(workspace_root: Path = _workspace_root, suite_path: Optional[Path] = None, repetitions: int = 3) -> Dict[str, Any]:
    """Wrapper fail-closed: la suite sintetica A/B JSON e stata dismessa in Generation v2."""
    _ = workspace_root, repetitions
    return {
        "status": "RETIRED", "passed": False, "suite_path": str(suite_path) if suite_path else "",
        "tasks_total": 0, "tasks_passed": 0, "tasks_failed": 0,
        "details": "Suite A/B JSON sintetica dismessa: utilizzare pytest reale (run-pytest / strict-verify).",
    }


class RSIConvergenceEngine:
    """Motore deterministico di convergenza RSI con guardie G1..G6 e Q_v2(S_k)."""

    _TELEMETRY_LOCK = _TELEMETRY_LOCK

    def __init__(self, workspace_root: Optional[Path] = None, telemetry_path: Optional[Path] = None, root: Optional[Path] = None) -> None:
        get_reconfigure_streams()
        effective_root = root if root is not None else workspace_root
        self.workspace_root = Path(effective_root).resolve() if effective_root else _workspace_root
        self.root = self.workspace_root
        self.telemetry_path = Path(telemetry_path).resolve() if telemetry_path else self.workspace_root / "nk_tracking" / "rsi_telemetry.jsonl"
        self._snapshot_mgr_loaded, self._snapshot_mgr = False, None

    @property
    def snapshot_mgr(self) -> Any:
        """Istanzia in modo lazy HealingSnapshotManager."""
        if not self._snapshot_mgr_loaded:
            self._snapshot_mgr_loaded = True
            cls_mgr = get_healing_snapshot_manager_cls()
            self._snapshot_mgr = cls_mgr() if cls_mgr is not None else None
        return self._snapshot_mgr

    @snapshot_mgr.setter
    def snapshot_mgr(self, value: Any) -> None:
        self._snapshot_mgr_loaded, self._snapshot_mgr = True, value

    @staticmethod
    def get_max_iterations(mode: str = "mode_a") -> int: return MODE_ITERATION_CAPS.get(mode.lower().strip(), 4)
    @staticmethod
    def evaluate_canary_holdout(holdout_path: Optional[Path] = None, simulated_outcomes: Optional[Dict[str, str]] = None, require_sha256: bool = False) -> Dict[str, Any]:
        return evaluate_canary_holdout(holdout_path=holdout_path, simulated_outcomes=simulated_outcomes, require_sha256=require_sha256)
    @staticmethod
    def compute_delta(defects: RSIDefectVector, profile: str = "code_rsi") -> int: return compute_delta(defects, profile=profile)
    @staticmethod
    def compute_fitness(defects: RSIDefectVector, delta_k: Optional[int] = None, profile: str = "code_rsi") -> float:
        return compute_fitness(defects, delta_k=delta_k, profile=profile)
    @staticmethod
    def compute_fitness_v2(defects: RSIDefectVector, **kwargs: Any) -> Dict[str, Any]: return compute_fitness_v2(defects, **kwargs)
    @staticmethod
    def is_converged(defects: RSIDefectVector, profile: str = "code_rsi") -> bool:
        d_k = compute_delta(defects, profile=profile)
        return d_k == 0 and compute_fitness(defects, delta_k=d_k, profile=profile) >= 100.0
    @staticmethod
    def check_hard_gate_regression(prev_defects: RSIDefectVector, curr_defects: RSIDefectVector, strict_monotonic: bool = False) -> Tuple[bool, str]:
        return check_hard_gate_regression_impl(prev_defects, curr_defects, strict_monotonic=strict_monotonic)
    @staticmethod
    def compute_files_state_hash(target_files: Sequence[Path | str]) -> str: return compute_files_state_hash_impl(target_files)
    @staticmethod
    def _compute_record_hash(record_dict: Dict[str, Any]) -> str: return compute_record_hash_impl(record_dict)
    def _get_last_telemetry_hash(self) -> str: return get_last_telemetry_hash_impl(self)
    def append_telemetry_record(self, record: RSIIterationRecord) -> RSIIterationRecord: return append_telemetry_record_impl(self, record)
    def verify_telemetry_chain(self, telemetry_path: Optional[Path] = None) -> Tuple[bool, int, str]:
        return verify_telemetry_chain_impl(self, telemetry_path=telemetry_path)
    def run_convergence_loop(
        self, evaluate_fn: Callable[[int], RSIDefectVector], refine_fn: Optional[Callable[[int, RSIDefectVector], bool]] = None,
        target_files: Optional[Sequence[Path | str]] = None, mode: str = "mode_a", session_id: Optional[str] = None, profile: str = "code_rsi",
    ) -> RSISessionReport:
        return run_convergence_loop_impl(self, evaluate_fn, refine_fn=refine_fn, target_files=target_files, mode=mode, session_id=session_id, profile=profile)
    def _resolve_candidate(self, root: Path, rel_path: str) -> Path: return resolve_candidate_impl(root, rel_path)
    @staticmethod
    def _collect_overlay_md_files(root: Path, rel_subdir: str, recursive: bool = True) -> List[Path]:
        return _collect_overlay_md_files(root=root, rel_subdir=rel_subdir, recursive=recursive)
    def _extract_script_supported_flags(self, script_path: Path) -> Set[str]: return extract_script_supported_flags_impl(script_path)
    def verify_cli_flags_cove(self, root_dir: Optional[Path] = None) -> Dict[str, Any]: return verify_cli_flags_cove_impl(self, root_dir=root_dir)
    def run_vibe_check(
        self, target_path: Path | str, profile: str = "vibe_sprint_micro_rsi",
        sast_report: Optional[Path | str] = None, strict_verify: bool = False, strict_profile: bool = False,
    ) -> Dict[str, Any]:
        return run_vibe_check_impl(self, target_path, profile=profile, sast_report=sast_report, strict_verify=strict_verify, strict_profile=strict_profile)
    def run_ab_benchmark(self, suite_path: Optional[Path] = None, repetitions: int = 3) -> Dict[str, Any]:
        """Wrapper fail-closed dismesso: utilizzare run_benchmark_suite con pytest reale."""
        return run_ab_benchmark(workspace_root=self.workspace_root, suite_path=suite_path, repetitions=repetitions)
    def run_benchmark_suite(
        self, benchmark_suite: Path | str, root_dir: Optional[Path] = None,
        lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        return run_benchmark_suite_impl(self, benchmark_suite, root_dir=root_dir, lane_id=lane_id, staging_dir=staging_dir)
    @staticmethod
    def _load_staging_deleted_set(root: Path) -> Set[str]: return load_staging_deleted_set_impl(root)
    def _scan_sast_and_mojibake(
        self, root: Path, sast_report: Optional[Path | str] = None,
        lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        return scan_sast_and_mojibake_impl(self, root, sast_report=sast_report, lane_id=lane_id, staging_dir=staging_dir)
    def verify_convergence(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: return self.verify_ecosystem(*args, **kwargs)

    def verify_ecosystem(
        self, root_dir: Optional[Path] = None, run_pytest: bool = False, profile: str = "code_rsi",
        benchmark_suite: Optional[str] = None, sast_report: Optional[Path | str] = None, strict_verify: bool = False,
        persist_telemetry: bool = False, test_report: Optional[Dict[str, Any]] = None, dast_report: Optional[Path | str] = None,
        mutation_report: Optional[Any] = None, allowed_files: Optional[Union[str, Sequence[str]]] = None, scan_prod_frontend: bool = False,
        coverage_report: Optional[Path | str] = None, strict_profile: bool = False, diff_aware: bool = False, allow_injected_test_report: bool = True,
        strict_unmeasured_gate: bool = False, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        return verify_ecosystem_impl(
            self, root_dir=root_dir, run_pytest=run_pytest, profile=profile, benchmark_suite=benchmark_suite,
            sast_report=sast_report, strict_verify=strict_verify, persist_telemetry=persist_telemetry,
            test_report=test_report, dast_report=dast_report, mutation_report=mutation_report,
            allowed_files=allowed_files, scan_prod_frontend=scan_prod_frontend, coverage_report=coverage_report,
            strict_profile=strict_profile, diff_aware=diff_aware, allow_injected_test_report=allow_injected_test_report,
            strict_unmeasured_gate=strict_unmeasured_gate, lane_id=lane_id, staging_dir=staging_dir,
        )

    def emit_gt14_bundle(
        self, workspace_root: Optional[Union[str, Path]] = None, with_dast: bool = False, strict_verify: bool = False,
        output_path: Optional[Union[str, Path]] = None, mutation_report: Optional[Any] = None, dast_report: Optional[Union[str, Path]] = None,
        allowed_files: Optional[Union[str, Sequence[str]]] = None, scan_prod_frontend: bool = False,
        diff_aware: bool = False, profile: Optional[str] = None, lane_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return emit_gt14_bundle_impl(
            self, workspace_root=workspace_root, with_dast=with_dast, strict_verify=strict_verify, output_path=output_path,
            mutation_report=mutation_report, dast_report=dast_report, allowed_files=allowed_files, scan_prod_frontend=scan_prod_frontend,
            diff_aware=diff_aware, profile=profile, lane_id=lane_id,
        )


def emit_gt14_bundle(
    workspace_root: Optional[Union[str, Path]] = None, with_dast: bool = False, strict_verify: bool = False,
    output_path: Optional[Union[str, Path]] = None, mutation_report: Optional[Any] = None, dast_report: Optional[Union[str, Path]] = None,
    allowed_files: Optional[Union[str, Sequence[str]]] = None, scan_prod_frontend: bool = False,
    diff_aware: bool = False, profile: Optional[str] = None, lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione di modulo per eseguire emit_gt14_bundle in-process."""
    root = Path(workspace_root).resolve() if workspace_root else _workspace_root
    return RSIConvergenceEngine(workspace_root=root, root=root).emit_gt14_bundle(
        workspace_root=root, with_dast=with_dast, strict_verify=strict_verify, output_path=output_path,
        mutation_report=mutation_report, dast_report=dast_report, allowed_files=allowed_files, scan_prod_frontend=scan_prod_frontend,
        diff_aware=diff_aware, profile=profile, lane_id=lane_id,
    )


def _resolve_vibe_target(root_path: Path, vibe_arg: str) -> str:
    if vibe_arg != ".":
        return vibe_arg
    stg_dir = root_path / ".staging"
    if stg_dir.exists() and any(p.is_file() and p.suffix.lower() in VIBE_SCAN_SUFFIXES for p in stg_dir.rglob("*")):
        return str(root_path)
    return str(root_path / ".agents") if (root_path / ".agents").exists() else str(root_path)


def _build_rsi_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Motore di Convergenza RSI NK Hub Generation")
    for flag, hlp in _CLI_BOOL_FLAGS:
        parser.add_argument(flag, action="store_true", help=hlp)
    for flag, hlp in _CLI_STR_FLAGS:
        parser.add_argument(flag, type=str, default=None, help=hlp)
    parser.add_argument("--vibe-check", nargs="?", const=".", type=str, default=None, help="Micro-loop Vibe Check")
    parser.add_argument("--benchmark-suite", "--suite", dest="benchmark_suite", type=str, default=None, help="Target suite pytest")
    return parser


def _print_vibe_result(vibe_res: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(vibe_res, indent=2))
    else:
        sym = "🟢" if vibe_res["passed"] else "🔴"
        print(f"{sym} [RSI-VIBE-CHECK] Stato: {vibe_res['status']} | Delta: {vibe_res['delta_k']} | Q: {vibe_res['fitness_q']} ({vibe_res['elapsed_ms']} ms)")
        for v in vibe_res["violations"]:
            print(f"  - {v}")
    return 0 if vibe_res["passed"] else 1


def _print_verify_result(res: Dict[str, Any], root_path: Path, as_json: bool) -> int:
    if as_json:
        print(json.dumps(res, indent=2))
    else:
        sym = "🟢" if res["passed"] else "🔴"
        print(f"{sym} [RSI-VERIFY] Stato: {res['status']} | SCOPE: {root_path} | Profilo: {res['profile']} | Delta: {res['delta_k']} | Q: {res['fitness_q']}")
        for v in res["violations"]:
            print(f"  - {v}")
    return 2 if res["status"] == "UNMEASURED" else (0 if res["passed"] else 1)


def _dispatch_with_opt(fn: Callable[..., Dict[str, Any]], fallback_fn: Callable[..., Dict[str, Any]], base_kw: Dict[str, Any], opt_kw: Dict[str, Any]) -> Dict[str, Any]:
    if not opt_kw:
        return fn(**base_kw)
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()) or all(k in params for k in opt_kw):
        return fn(**base_kw, **opt_kw)
    return fallback_fn(**base_kw, **opt_kw)


def _collect_opt_kwargs(pairs: Tuple[Tuple[str, Any], ...]) -> Dict[str, Any]:
    return {k: v for k, v in pairs if v is not None}


def _load_cli_test_report(path_str: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path_str:
        return None
    rep_p = Path(path_str)
    if not rep_p.is_file():
        raise ValueError(f"test_report non trovato: {rep_p}")
    try:
        payload = json.loads(rep_p.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"test_report JSON invalido: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("test_report non valido: atteso dizionario JSON.")
    return payload


def _run_cli_bundle_cmd(engine: RSIConvergenceEngine, root_path: Path, args: Any) -> int:
    b_base = {"workspace_root": root_path, "with_dast": bool(args.with_dast), "strict_verify": bool(args.strict_verify), "output_path": args.bundle_output}
    b_opt = _collect_opt_kwargs((
        ("mutation_report", args.mutation_report),
        ("dast_report", args.dast_report),
        ("allowed_files", args.allowed_files),
        ("scan_prod_frontend", True if args.scan_prod_frontend else None),
        ("diff_aware", True if args.diff_aware else None),
        ("profile", args.profile),
        ("lane_id", getattr(args, "lane_id", None)),
    ))
    bundle_res = _dispatch_with_opt(engine.emit_gt14_bundle, lambda **kw: emit_gt14_bundle_impl(engine, **kw), b_base, b_opt)
    if args.json:
        print(json.dumps(bundle_res, indent=2, ensure_ascii=False))
    else:
        sym = "🟢" if bundle_res["passed"] else "🔴"
        print(f"{sym} [GT14-BUNDLE] Stato: {bundle_res['status']} | Probes: {bundle_res['probes_executed']} | Bundle: {bundle_res['bundle_path']} ({bundle_res['elapsed_ms']} ms)")
    return 0 if bundle_res.get("passed") else 1


def _build_verify_opt_kwargs(args: Any) -> Dict[str, Any]:
    test_rep_dict = _load_cli_test_report(args.test_report)
    return _collect_opt_kwargs((
        ("test_report", test_rep_dict), ("dast_report", args.dast_report), ("mutation_report", args.mutation_report),
        ("coverage_report", args.coverage_report), ("allowed_files", args.allowed_files),
        ("scan_prod_frontend", True if args.scan_prod_frontend else None),
        ("strict_profile", True if args.strict_profile else None),
        ("diff_aware", True if args.diff_aware else None),
        ("allow_injected_test_report", False if args.strict_verify else None),
        ("lane_id", getattr(args, "lane_id", None)),
    ))


def _run_cli_verify_cmd(engine: RSIConvergenceEngine, root_path: Path, args: Any) -> int:
    v_base = {"root_dir": root_path, "run_pytest": bool(args.run_pytest), "profile": args.profile or "code_rsi", "benchmark_suite": args.benchmark_suite, "sast_report": args.sast_report, "strict_verify": bool(args.strict_verify), "persist_telemetry": bool(args.persist_telemetry)}
    v_opt = _build_verify_opt_kwargs(args)
    res = _dispatch_with_opt(engine.verify_ecosystem, lambda **kw: verify_ecosystem_impl(engine, **kw), v_base, v_opt)
    return _print_verify_result(res, root_path, bool(args.json) or (not args.verify and not args.strict_verify))


def _dispatch_rsi_cli_action(args: Any, engine: RSIConvergenceEngine, root_path: Path) -> int:
    try:
        if args.ab_benchmark:
            ab_res = engine.run_ab_benchmark(suite_path=Path(args.benchmark_suite) if args.benchmark_suite else None)
            print(json.dumps(ab_res, indent=2, ensure_ascii=False))
            return 0 if ab_res.get("passed") else 1
        if args.verify_canary:
            canary_res = evaluate_canary_holdout(require_sha256=True)
            print(json.dumps(canary_res, indent=2, ensure_ascii=False))
            return 0 if canary_res.get("passed") else 1
        if args.emit_gt14_bundle:
            return _run_cli_bundle_cmd(engine, root_path, args)
        if args.vibe_check:
            vibe_res = _dispatch_with_opt(engine.run_vibe_check, lambda **kw: run_vibe_check_impl(engine, **kw), {"target_path": _resolve_vibe_target(root_path, args.vibe_check), "profile": args.profile or "vibe_sprint_micro_rsi", "sast_report": args.sast_report, "strict_verify": bool(args.strict_verify)}, _collect_opt_kwargs((("strict_profile", True if args.strict_profile else None),)))
            return _print_vibe_result(vibe_res, bool(args.json))
        return _run_cli_verify_cmd(engine, root_path, args)
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "passed": False, "violations": [str(exc)]}, indent=2) if args.json else f"🔴 [RSI-CLI] {exc}")
        return 1


def run_rsi_cli(argv: Optional[Sequence[str]] = None, default_root: Optional[Path] = None, ensure_exports_fn: Optional[Callable[[], Any]] = None) -> int:
    """Esegue il parser CLI consolidato del motore di convergenza RSI."""
    args = _build_rsi_parser().parse_args(argv)
    if ensure_exports_fn is not None:
        ensure_exports_fn()
    root_path = Path(args.root).resolve() if args.root else (default_root or _workspace_root)
    return _dispatch_rsi_cli_action(args, RSIConvergenceEngine(workspace_root=root_path, root=root_path), root_path)
