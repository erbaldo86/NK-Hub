#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Control Plane co-esecutivo Tensor-RSI per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/tensor_rsi.py.
@domain_id: DOM-01
Gestisce FSM T0..T7, State-Ticket HMAC trsi1., PolicyCell e Gate epsilon-Pareto.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__nk_domain__: str = "DOM-01"
__nk_role__: str = "facade"
__nk_facade__: str = "tensor_rsi"


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI con i 5 flag pubblici DOM-01 prima degli import pesanti."""
    parser = argparse.ArgumentParser(
        description="Tensor-RSI Co-Execution Control Plane (DOM-01)"
    )
    parser.add_argument(
        "--step",
        required=True,
        choices=("intake", "diagnose", "propose", "evaluate", "decide", "record", "status", "abort"),
        help="Fase FSM Tensor-RSI da eseguire",
    )
    parser.add_argument(
        "--ticket",
        type=str,
        default=None,
        help="State-Ticket firmato trsi1. restituito dal turno precedente",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Percorso JSON o oggetto inline di input per lo step corrente",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Percorso alla radice del repository NK_Hub",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa l'output strutturato TensorRSIStepOutput in formato JSON",
    )
    return parser


if __name__ == "__main__" and (
    len(sys.argv) <= 1 or any(arg in ("-h", "--help") for arg in sys.argv[1:])
):
    _cli_parser = _build_cli_parser()
    _cli_parser.print_help() if len(sys.argv) <= 1 else _cli_parser.parse_args()
    raise SystemExit(0)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="tensor_rsi")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "TensorRSICoExecutor": ("_internal.tensor_rsi.co_executor", "TensorRSICoExecutor"),
}
__all__ = ["TensorRSICoExecutor", "main"]


def __getattr__(name: str) -> Any:
    """Risolve pigramente la classe pubblica TensorRSICoExecutor."""
    spec = _LAZY_EXPORT_MAP.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    val = getattr(importlib.import_module(spec[0]), spec[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per il Control Plane Tensor-RSI."""
    parser = _build_cli_parser()
    return importlib.import_module("_internal.tensor_rsi.co_executor").run_tensor_cli(
        argv=argv,
        parser=parser,
    )


if __name__ == "__main__":
    sys.exit(main())
