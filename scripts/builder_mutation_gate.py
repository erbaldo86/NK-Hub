#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gate di Mutation Testing Differenziale AST per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/builder_mutation_gate.py.
@domain_id: DOM-03
Genera e verifica fino a K=8 mutanti AST sulle sole funzioni aggiunte o modificate in ShadowSandbox NVMe.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__nk_domain__: str = "DOM-03"
__nk_role__: str = "facade"
__nk_facade__: str = "builder_mutation_gate"

_CLI_FLAGS: Tuple[str, ...] = (
    "--audit-full-module",
    "--audit-workers",
    "--json",
    "--max-audit-mutants",
    "--max-mutants",
    "--min-kill-rate",
    "--out-map",
    "--stage-dir",
    "--target-file",
    "--test-targets",
    "--workspace-root",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
from _internal.nk_common.io import atomic_write_json  # noqa: E402
from _internal.nk_common.paths import reconfigure_streams  # noqa: E402

init_nk_facade(__file__, pkg="builder_mutation_gate")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "MutantOutcome": ("_internal.builder_mutation_gate.runner", "MutantOutcome"),
    "MutantSpec": ("_internal.builder_mutation_gate.mutant_gen", "MutantSpec"),
    "MutationGateReport": ("_internal.builder_mutation_gate.runner", "MutationGateReport"),
    "SharedBaseNVMeWorkerPool": ("_internal.builder_mutation_gate.audit_mode", "SharedBaseNVMeWorkerPool"),
    "find_touched_functions": ("_internal.builder_mutation_gate.mutant_gen", "find_touched_functions"),
    "generate_audit_mutants": ("_internal.builder_mutation_gate.mutant_gen", "generate_audit_mutants"),
    "generate_differential_mutants": ("_internal.builder_mutation_gate.mutant_gen", "generate_differential_mutants"),
    "run_full_module_audit": ("_internal.builder_mutation_gate.audit_mode", "run_full_module_audit"),
    "run_multi_module_audit": ("_internal.builder_mutation_gate.audit_mode", "run_multi_module_audit"),
    "run_mutation_gate": ("_internal.builder_mutation_gate.runner", "run_mutation_gate"),
    "select_hotspot_functions": ("_internal.builder_mutation_gate.hotspot_audit", "select_hotspot_functions"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.builder_mutation_gate."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="builder_mutation_gate")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI in ordine alfabetico senza importare Pydantic su --help."""
    parser = argparse.ArgumentParser(description="NK Hub Generation Differential AST Mutation Gate CLI")
    parser.add_argument("--audit-full-module", action="store_true", help="Esegue audit mutazione su hotspot dell'intero modulo")
    parser.add_argument("--audit-workers", type=int, default=4, help="Numero slot worker NVMe per audit full-module (1..4)")
    parser.add_argument("--json", action="store_true", help="Stampa il rapporto MutationGateReport in formato JSON")
    parser.add_argument("--max-audit-mutants", type=int, default=16, help="Numero massimo mutanti AST in modalita audit (default: 16)")
    parser.add_argument("--max-mutants", type=int, default=8, help="Numero massimo K di mutanti AST differenziali (default: 8)")
    parser.add_argument("--min-kill-rate", type=float, default=0.80, help="Soglia minima di kill rate [0.0..1.0] (default: 0.80)")
    parser.add_argument("--out-map", type=str, default=None, help="Percorso JSON opzionale su cui salvare atomicamente il rapporto")
    parser.add_argument("--stage-dir", type=str, default=None, help="Cartella staging opzionale (default: <workspace-root>/.staging)")
    parser.add_argument("--target-file", type=str, required=True, help="Percorso relativo del file sorgente Python da mutare")
    parser.add_argument("--test-targets", nargs="+", required=True, help="Uno o piu file test pytest da eseguire sui mutanti")
    parser.add_argument("--workspace-root", type=str, default="NK_Hub", help="Root del repository target (default: NK_Hub)")
    return parser


def _expand_test_targets(raw_targets: Sequence[str]) -> List[str]:
    """Espande target pytest separati da spazio o virgola."""
    expanded: List[str] = []
    for item in raw_targets:
        for piece in str(item).split(","):
            clean = piece.strip()
            if clean:
                expanded.append(clean)
    return expanded


def _run_gate_from_args(runner_mod: Any, args: argparse.Namespace, targets: List[str]) -> Any:
    """Esegue run_mutation_gate in modalita differenziale oppure --audit-full-module."""
    common_kw: Dict[str, Any] = {
        "workspace_root": Path(args.workspace_root),
        "target_rel_path": args.target_file,
        "test_targets": targets,
        "stage_dir": Path(args.stage_dir) if args.stage_dir else None,
        "min_kill_rate": args.min_kill_rate,
    }
    if getattr(args, "audit_full_module", False):
        return runner_mod.run_mutation_gate(
            **common_kw,
            audit_full_module=True,
            max_audit_mutants=args.max_audit_mutants,
            audit_workers=args.audit_workers,
        )
    return runner_mod.run_mutation_gate(**common_kw, max_mutants=args.max_mutants)


def _write_out_map(out_map: Optional[str], report: Any) -> None:
    """Scrive atomicamente il report JSON sul percorso --out-map se specificato."""
    if not out_map or not str(out_map).strip():
        return
    payload = json.loads(report.model_dump_json())
    ok, err = atomic_write_json(Path(out_map), payload, indent=2, ensure_ascii=False, ensure_parent=True)
    if not ok:
        raise OSError(err or f"Atomic JSON write failed for {out_map}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per il Mutation Gate differenziale e audit."""
    reconfigure_streams()
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    init_nk_facade(__file__, pkg="builder_mutation_gate")
    runner_mod = importlib.import_module("_internal.builder_mutation_gate.runner")

    targets = _expand_test_targets(args.test_targets)
    report = _run_gate_from_args(runner_mod, args, targets)
    _write_out_map(getattr(args, "out_map", None), report)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        icon = "[PASS]" if report.passed else "[FAIL]"
        print(f"{icon} {report.message} (elapsed={report.elapsed_sec}s)")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
