"""Parser e dispatcher CLI per il motore di convergenza RSI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Optional, Sequence


def run_rsi_cli(
    argv: Optional[Sequence[str]] = None,
    default_root: Optional[Path] = None,
    ensure_exports_fn: Optional[Callable[[], Any]] = None,
) -> int:
    """Esegue il parser CLI del motore di convergenza RSI."""
    parser = argparse.ArgumentParser(
        description="Motore di Convergenza RSI NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Esegue la verifica completa Guardia G6 sull'ecosistema",
    )
    parser.add_argument(
        "--strict-verify",
        action="store_true",
        help="Esegue pytest reale e restituisce UNMEASURED se la suite e assente",
    )
    parser.add_argument(
        "--ab-benchmark",
        action="store_true",
        help="Esegue la suite deterministica A/B sui 12 task core e stampa il report JSON",
    )
    parser.add_argument(
        "--verify-canary",
        action="store_true",
        help="Esegue la verifica deterministica AST del Canary Holdout Impossibile (6 task)",
    )
    parser.add_argument(
        "--emit-gt14-bundle",
        action="store_true",
        help="Esegue le sonde GT-14 in-process (6 -> 1) e salva il bundle diagnostico JSON",
    )
    parser.add_argument(
        "--with-dast",
        action="store_true",
        help="Include l'esecuzione DAST overlay dentro --emit-gt14-bundle",
    )
    parser.add_argument(
        "--bundle-output",
        type=str,
        default=None,
        help="Percorso di output opzionale per il bundle JSON di --emit-gt14-bundle",
    )
    parser.add_argument(
        "--sast-report",
        type=str,
        default=None,
        help="Percorso opzionale a un report JSON SAST da integrare in Delta_k",
    )
    parser.add_argument(
        "--persist-telemetry",
        action="store_true",
        help="Salva il record di verifica in nk_tracking/rsi_telemetry.jsonl",
    )
    parser.add_argument(
        "--vibe-check",
        nargs="?",
        const=".",
        type=str,
        default=None,
        help="Esegue il micro-loop Vibe Check (<500ms) sul file o directory target",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Profilo Tensor-RSI attivo (code_rsi, vibe_sprint_micro_rsi, spec_rsi, ui_ux_rsi, ste100_rsi; default vibe_sprint_micro_rsi per --vibe-check)",
    )
    parser.add_argument(
        "--benchmark-suite",
        type=str,
        default=None,
        help="Percorso opzionale a file o cartella pytest di benchmark funzionale",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice da verificare",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )

    args = parser.parse_args(argv)
    if ensure_exports_fn is not None:
        ensure_exports_fn()
    from _internal.rsi_convergence_engine.ab_benchmark import run_ab_benchmark
    from _internal.rsi_convergence_engine.canary_holdout import evaluate_canary_holdout
    from _internal.rsi_convergence_engine.constants import _workspace_root
    from _internal.rsi_convergence_engine.engine import RSIConvergenceEngine

    base_root = default_root or _workspace_root
    root_path = Path(args.root).resolve() if args.root else base_root
    engine = RSIConvergenceEngine(workspace_root=root_path, root=root_path)

    if args.ab_benchmark:
        ab_suite = Path(args.benchmark_suite) if args.benchmark_suite else None
        ab_res = run_ab_benchmark(workspace_root=root_path, suite_path=ab_suite)
        print(json.dumps(ab_res, indent=2, ensure_ascii=False))
        return 0 if ab_res.get("passed") else 1

    if args.verify_canary:
        canary_res = evaluate_canary_holdout()
        print(json.dumps(canary_res, indent=2, ensure_ascii=False))
        return 0 if canary_res.get("passed") else 1

    if args.emit_gt14_bundle:
        bundle_res = engine.emit_gt14_bundle(
            workspace_root=root_path,
            with_dast=bool(args.with_dast),
            strict_verify=bool(args.strict_verify),
            output_path=args.bundle_output,
        )
        if args.json:
            print(json.dumps(bundle_res, indent=2, ensure_ascii=False))
        else:
            sym = "🟢" if bundle_res["passed"] else "🔴"
            print(
                f"{sym} [GT14-BUNDLE] Stato: {bundle_res['status']} | "
                f"Probes: {bundle_res['probes_executed']} | Bundle: {bundle_res['bundle_path']} "
                f"({bundle_res['elapsed_ms']} ms)"
            )
        return 0 if bundle_res.get("passed") else 1

    if args.vibe_check:
        vibe_profile = (
            args.profile if args.profile is not None else "vibe_sprint_micro_rsi"
        )
        if args.vibe_check == ".":
            stg_dir = root_path / ".staging"
            has_staged_files = stg_dir.exists() and any(
                p.is_file() and p.suffix in (".py", ".md", ".json")
                for p in stg_dir.rglob("*")
            )
            if has_staged_files:
                vibe_target = str(root_path)
            elif (root_path / ".agents").exists():
                vibe_target = str(root_path / ".agents")
            else:
                vibe_target = str(root_path)
        else:
            vibe_target = args.vibe_check
        vibe_res = engine.run_vibe_check(
            vibe_target,
            profile=vibe_profile,
            sast_report=args.sast_report,
            strict_verify=bool(args.strict_verify),
        )
        if args.json:
            print(json.dumps(vibe_res, indent=2))
        else:
            sym = "🟢" if vibe_res["passed"] else "🔴"
            print(
                f"{sym} [RSI-VIBE-CHECK] Stato: {vibe_res['status']} | Delta: {vibe_res['delta_k']} | Q: {vibe_res['fitness_q']} ({vibe_res['elapsed_ms']} ms)"
            )
            for v in vibe_res["violations"]:
                print(f"  - {v}")
        return 0 if vibe_res["passed"] else 1

    res = engine.verify_ecosystem(
        root_dir=root_path,
        run_pytest=False,
        profile=args.profile or "code_rsi",
        benchmark_suite=args.benchmark_suite,
        sast_report=args.sast_report,
        strict_verify=bool(args.strict_verify),
        persist_telemetry=bool(args.persist_telemetry),
    )
    if args.json or (not args.verify and not args.strict_verify):
        print(json.dumps(res, indent=2))
    else:
        sym = "🟢" if res["passed"] else "🔴"
        print(
            f"{sym} [RSI-VERIFY] Stato: {res['status']} | SCOPE: {root_path} | Profilo: {res['profile']} | Delta: {res['delta_k']} | Q: {res['fitness_q']}"
        )
        for v in res["violations"]:
            print(f"  - {v}")
    if res["status"] == "UNMEASURED":
        return 2
    return 0 if res["passed"] else 1
