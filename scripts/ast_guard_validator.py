#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validatore statico AST deterministico per NK Hub Generation 1.0.0-Generation.
Modulo: ast_guard_validator.py.
@domain_id: DOM-04
Verifica purezza sintattica fail-closed, conservazione completa delle firme e controlli TAS/SAST.

Funzionalita principali:
1. Verifica purezza sintattica bloccante e conservazione di firme, *args, **kwargs, classi e basi ereditarie.
2. Verifica integrita dello scope, incluso uso post-'del var' senza re-binding.
3. Traccia alias di importazione e assegnazioni dirette semplici per bloccare evasioni SAST, mock, ctypes.windll e test-gaming.
4. Scansiona scripts, src_app e tests con --target all e persiste --output-json in modo atomico (.tmp + os.replace).
5. Termina fail-closed (rc=2) quando --stage-dir o il percorso target non esistono.
"""

from __future__ import annotations

import argparse
import json
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc
    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
init_nk_facade(__file__, pkg="ast_guard_validator")

_EXPORTS_LOADED = False


def _ensure_exports_loaded() -> Dict[str, Any]:
    """Carica pigramente i sottomoduli AST Guard evitando import Pydantic su --help."""
    global _EXPORTS_LOADED
    if _EXPORTS_LOADED:
        return globals()

    from _internal.ast_guard_validator.models import (
        PROTECTED_SECURITY_ANCHORS,
        FunctionSignatureSnapshot,
        GuardViolation,
        ValidationReport,
        ViolationType,
        _PEP585_TYPE_ALIASES,
        _collect_union_parts,
        _format_canonical_union,
        _normalize_type_annotation,
        _normalize_type_ast_node,
    )
    from _internal.ast_guard_validator.reexports import (
        _collect_resolved_module,
        _iter_top_level_import_from,
        _merge_symbol_from_collector,
        _resolve_import_from_module_file,
        _resolve_local_import_exports,
        _resolve_local_import_roots,
        validate_pydantic_catalog_records,
    )
    from _internal.ast_guard_validator.sast_checker import SASTConstructChecker
    from _internal.ast_guard_validator.scope_checker import (
        MODULE_DUNDERS,
        ScopeIntegrityChecker,
    )
    from _internal.ast_guard_validator.signature_collector import SignatureCollector
    from _internal.ast_guard_validator.validator import ASTGuardValidator
    from _internal.ast_guard_validator.validator_helpers import (
        _resolve_production_counterpart,
        _write_json_atomic,
    )

    exported: Dict[str, Any] = {
        "PROTECTED_SECURITY_ANCHORS": PROTECTED_SECURITY_ANCHORS,
        "FunctionSignatureSnapshot": FunctionSignatureSnapshot,
        "GuardViolation": GuardViolation,
        "ValidationReport": ValidationReport,
        "ViolationType": ViolationType,
        "_PEP585_TYPE_ALIASES": _PEP585_TYPE_ALIASES,
        "_collect_union_parts": _collect_union_parts,
        "_format_canonical_union": _format_canonical_union,
        "_normalize_type_annotation": _normalize_type_annotation,
        "_normalize_type_ast_node": _normalize_type_ast_node,
        "_collect_resolved_module": _collect_resolved_module,
        "_iter_top_level_import_from": _iter_top_level_import_from,
        "_merge_symbol_from_collector": _merge_symbol_from_collector,
        "_resolve_import_from_module_file": _resolve_import_from_module_file,
        "_resolve_local_import_exports": _resolve_local_import_exports,
        "_resolve_local_import_roots": _resolve_local_import_roots,
        "validate_pydantic_catalog_records": validate_pydantic_catalog_records,
        "SASTConstructChecker": SASTConstructChecker,
        "MODULE_DUNDERS": MODULE_DUNDERS,
        "ScopeIntegrityChecker": ScopeIntegrityChecker,
        "SignatureCollector": SignatureCollector,
        "ASTGuardValidator": ASTGuardValidator,
        "_resolve_production_counterpart": _resolve_production_counterpart,
        "_write_json_atomic": _write_json_atomic,
    }
    globals().update(exported)
    _EXPORTS_LOADED = True
    return globals()


def __getattr__(name: str) -> Any:
    """Espone in modo trasparente la facciata AST Guard al primo accesso."""
    ns = _ensure_exports_loaded()
    if name in ns:
        return ns[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic AST Guard Validator")
    parser.add_argument(
        "target_path",
        nargs="*",
        default=None,
        help="Percorso/i del file o directory Python da scansionare, oppure 'all'",
    )
    parser.add_argument(
        "--target",
        dest="target",
        default=None,
        help="File o directory target da scansionare, oppure 'all'",
    )
    parser.add_argument(
        "--stage-dir",
        dest="stage_dir",
        default=None,
        help="Directory di staging da scansionare (fail-closed rc=2 se inesistente)",
    )
    parser.add_argument(
        "--allowed-mutations",
        type=str,
        default="",
        help="Simboli separati da virgola autorizzati a mutare firma",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il report in JSON",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Salva atomicamente il report JSON sul percorso specificato",
    )

    args = parser.parse_args()
    _ensure_exports_loaded()
    from _internal.ast_guard_validator.validator import ASTGuardValidator
    from _internal.ast_guard_validator.validator_helpers import (
        _resolve_production_counterpart,
        _write_json_atomic,
    )

    raw_targets: List[tuple[str, bool]] = []
    if args.stage_dir is not None:
        raw_targets.append((str(args.stage_dir), True))
    if args.target is not None:
        raw_targets.append((str(args.target), False))
    if args.target_path:
        if isinstance(args.target_path, list):
            raw_targets.extend(
                (str(x), False) for x in args.target_path if str(x).strip()
            )
        elif str(args.target_path).strip():
            raw_targets.append((str(args.target_path).strip(), False))

    if not raw_targets:
        raw_targets = [("all", False)]

    allowed_set = {
        s.strip() for s in args.allowed_mutations.split(",") if s.strip()
    }
    validator = ASTGuardValidator(allowed_mutations=allowed_set)

    script_dir = Path(__file__).resolve().parent
    workspace_root = (
        script_dir.parent.parent
        if script_dir.parent.name == ".staging"
        else script_dir.parent
    )

    def _fail_closed_missing(msg: str) -> int:
        err_payload = {
            "passed": False,
            "files_scanned": 0,
            "total_violations": 1,
            "sast_critical": 1,
            "error": msg,
        }
        if args.output_json:
            _write_json_atomic(Path(args.output_json), err_payload)
        if args.json:
            print(json.dumps(err_payload))
        else:
            print(f"[ERROR] {msg}")
        return 2

    cwd_resolved = Path.cwd().resolve()
    scan_root = workspace_root
    if (
        cwd_resolved != workspace_root
        and cwd_resolved != workspace_root.parent
        and any((cwd_resolved / d).is_dir() for d in ("scripts", "src_app", "tests"))
    ):
        scan_root = cwd_resolved

    targets_to_scan: List[Path] = []
    for raw_target, require_dir in raw_targets:
        if not require_dir and raw_target.lower() == "all":
            for candidate in ("scripts", "src_app", "tests"):
                cand_path = scan_root / candidate
                if cand_path.exists() and cand_path.is_dir():
                    targets_to_scan.append(cand_path)
        else:
            if not raw_target.strip():
                return _fail_closed_missing("Empty target/stage-dir path provided.")
            p = Path(raw_target)
            if not p.exists():
                return _fail_closed_missing(f"Path does not exist: {p}")
            if require_dir and not p.is_dir():
                return _fail_closed_missing(f"Stage directory is not a directory: {p}")
            targets_to_scan.append(p)

    py_files: List[Path] = []
    for t in targets_to_scan:
        if t.is_file() and t.suffix == ".py":
            py_files.append(t)
        elif t.is_dir():
            py_files.extend(
                sorted([f for f in t.rglob("*.py") if "__pycache__" not in f.parts])
            )

    py_files = sorted(list(dict.fromkeys(py_files)))

    total_violations = 0
    total_sast_violations = 0
    if not args.json:
        print("=" * 80)
        print(f"AST GUARD VALIDATOR: Scanning {len(py_files)} files across targets")
        print("=" * 80)

    for py_file in py_files:
        try:
            code = py_file.read_text(encoding="utf-8")
        except Exception as e:
            if not args.json:
                print(f"[FAIL] {py_file}: Could not read file: {e}")
            total_violations += 1
            total_sast_violations += 1
            continue

        prod_file = _resolve_production_counterpart(py_file, workspace_root)
        pre_code = code
        if prod_file is not None:
            try:
                pre_code = prod_file.read_text(encoding="utf-8")
            except Exception:
                pre_code = code

        report = validator.validate_code_edit(
            pre_code,
            code,
            allowed_mutations=validator.allowed_mutations,
            target_file=py_file.as_posix(),
        )
        total_sast_violations += int(report.metrics.get("sast_violations_count", 0))
        rel_path = py_file.as_posix()
        if not report.is_valid:
            if not args.json:
                print(f"[FAIL] {rel_path}: {len(report.violations)} AST violation(s):")
                for v in report.violations:
                    loc = (
                        f"L{v.line_number}:{v.column}"
                        if v.line_number is not None
                        else "GLOBAL"
                    )
                    print(f"       - [{v.violation_type.value}] {loc}: {v.message}")
            total_violations += len(report.violations)
        else:
            if not args.json:
                print(f"[PASS] {rel_path} (Symbols: {report.post_symbol_count})")

    json_payload = {
        "passed": total_violations == 0,
        "files_scanned": len(py_files),
        "total_violations": total_violations,
        "sast_critical": total_sast_violations,
    }
    if args.output_json:
        _write_json_atomic(Path(args.output_json), json_payload)

    if args.json:
        print(json.dumps(json_payload))
        return 0 if total_violations == 0 else 1

    print("=" * 80)
    if total_violations == 0:
        print(
            f"[RESULT] ALL {len(py_files)} FILES PASSED DETERMINISTIC AST GUARD VALIDATION."
        )
        return 0
    print(
        f"[RESULT] FAILED: {total_violations} total violations detected across {len(py_files)} files."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
