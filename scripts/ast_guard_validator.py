#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validatore statico AST deterministico per NK Hub Generation 1.0.0-Generation.
Modulo: ast_guard_validator.py.
@domain_id: DOM-04
Verifica purezza sintattica fail-closed, conservazione completa delle firme e controlli TAS/SAST.

Funzionalita principali:
1. Verifica purezza sintattica bloccante e conservazione di firme, *args, **kwargs, classi e basi ereditarie.
2. Verifica integrita dello scope, incluso uso post-'del var' senza re-binding e rami if.
3. Traccia alias di importazione, scope lessicale, taint SQL 1-hop e test-gaming.
4. Scansiona scripts, src_app e tests con --target all, --overlay-staging e --output-json atomico.
5. Supporta --quality-diff (ratchet CC/nesting/except/test/frontend) e --allowed-files scope guard.
"""

from __future__ import annotations

import json
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

from _internal.ast_guard_validator.cli_helpers import (  # noqa: E402
    _append_quality_payload,
    _build_cli_parser,
    _resolve_pre_codes,
    _run_quality_and_scope_checks,
    format_compact_violation,
)

_EXPORTS_LOADED = False


def _ensure_exports_loaded() -> Dict[str, Any]:
    """Carica pigramente i sottomoduli AST Guard evitando import Pydantic su --help."""
    global _EXPORTS_LOADED
    if _EXPORTS_LOADED:
        return globals()

    from _internal.ast_guard_validator.frontend_static_checker import (
        scan_frontend_code,
        scan_frontend_directory,
    )
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
    from _internal.ast_guard_validator.quality_diff_checker import (
        QualityDiffReport,
        check_allowed_files,
        check_python_quality_diff,
        compute_file_delta_cc,
    )
    from _internal.ast_guard_validator.quality_diff_rules import QualityDiffViolation
    from _internal.ast_guard_validator.reexports import (
        _collect_resolved_module,
        _iter_top_level_import_from,
        _merge_symbol_from_collector,
        _resolve_import_from_module_file,
        _resolve_local_import_exports,
        _resolve_local_import_roots,
        _resolve_prod_import_roots,
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
        "QualityDiffViolation": QualityDiffViolation,
        "QualityDiffReport": QualityDiffReport,
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
        "_resolve_prod_import_roots": _resolve_prod_import_roots,
        "validate_pydantic_catalog_records": validate_pydantic_catalog_records,
        "check_python_quality_diff": check_python_quality_diff,
        "compute_file_delta_cc": compute_file_delta_cc,
        "check_allowed_files": check_allowed_files,
        "scan_frontend_code": scan_frontend_code,
        "scan_frontend_directory": scan_frontend_directory,
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


def _expand_py_files_from_targets(targets_to_scan: List[Path]) -> List[Path]:
    py_files: List[Path] = []
    for t in targets_to_scan:
        if t.is_file() and t.suffix == ".py":
            py_files.append(t)
        elif t.is_dir():
            py_files.extend(
                sorted([f for f in t.rglob("*.py") if "__pycache__" not in f.parts])
            )
    return sorted(list(dict.fromkeys(py_files)))


def _collect_direct_targets_and_files(
    raw_targets: List[Tuple[str, bool]],
    scan_root: Path,
) -> Tuple[List[Path], List[Path], Optional[str]]:
    targets_to_scan: List[Path] = []
    for raw_target, require_dir in raw_targets:
        if not require_dir and raw_target.lower() == "all":
            for candidate in ("scripts", "src_app", "tests"):
                cand_path = scan_root / candidate
                if cand_path.exists() and cand_path.is_dir():
                    targets_to_scan.append(cand_path)
            continue
        if not raw_target.strip():
            return [], [], "Empty target/stage-dir path provided."
        p = Path(raw_target)
        if not p.exists():
            return [], [], f"Path does not exist: {p}"
        if require_dir and not p.is_dir():
            return [], [], f"Stage directory is not a directory: {p}"
        targets_to_scan.append(p)
    return _expand_py_files_from_targets(targets_to_scan), targets_to_scan, None


def main() -> int:
    parser = _build_cli_parser()
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
            "violations": [
                format_compact_violation("", None, "CLI_ERROR", None, "CRITICAL", msg)
            ],
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

    overlay_ctx: Optional[Tuple[Path, Path, Set[str]]] = None
    effective_ws = workspace_root
    if getattr(args, "overlay_staging", False):
        from _internal.ast_guard_validator.overlay_helpers import (
            resolve_overlay_scan_files,
        )

        (
            py_files,
            targets_to_scan,
            prod_root,
            stage_root,
            deleted_norm,
            err_msg,
        ) = resolve_overlay_scan_files(raw_targets, args, scan_root)
        if err_msg:
            return _fail_closed_missing(err_msg)
        overlay_ctx = (prod_root, stage_root, deleted_norm)
        effective_ws = prod_root
    else:
        py_files, targets_to_scan, err_msg = _collect_direct_targets_and_files(
            raw_targets, scan_root
        )
        if err_msg:
            return _fail_closed_missing(err_msg)

    total_violations = 0
    total_sast_violations = 0
    compact_violations: List[Dict[str, Any]] = []
    qd_py_items: List[Tuple[Path, str, str]] = []
    if not args.json:
        print("=" * 80)
        print(f"AST GUARD VALIDATOR: Scanning {len(py_files)} files across targets")
        print("=" * 80)

    for py_file in py_files:
        rel_path = py_file.as_posix()
        try:
            code = py_file.read_text(encoding="utf-8-sig")
        except Exception as e:
            if not args.json:
                print(f"[FAIL] {py_file}: Could not read file: {e}")
            total_violations += 1
            total_sast_violations += 1
            compact_violations.append(
                format_compact_violation(
                    rel_path, None, "IO_ERROR", None, "CRITICAL", f"Could not read file: {e}"
                )
            )
            continue

        pre_code, qd_pre = _resolve_pre_codes(
            py_file, code, effective_ws, _resolve_production_counterpart
        )
        qd_py_items.append((py_file, qd_pre, code))

        report = validator.validate_code_edit(
            pre_code,
            code,
            allowed_mutations=validator.allowed_mutations,
            target_file=rel_path,
        )
        total_sast_violations += int(report.metrics.get("sast_violations_count", 0))
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
            for v in report.violations:
                compact_violations.append(
                    format_compact_violation(
                        rel_path,
                        v.line_number,
                        v.violation_type.value,
                        v.symbol_name,
                        v.severity,
                        v.message,
                    )
                )
            total_violations += len(report.violations)
        else:
            if not args.json:
                print(f"[PASS] {rel_path} (Symbols: {report.post_symbol_count})")

    qd_violations, qd_blocking = _run_quality_and_scope_checks(
        args, qd_py_items, targets_to_scan, effective_ws, overlay_ctx=overlay_ctx
    )
    for qv in qd_violations:
        if qv.severity in ("HIGH", "MEDIUM", "CRITICAL"):
            compact_violations.append(
                format_compact_violation(
                    qv.file_path,
                    qv.line_number,
                    qv.rule_id,
                    qv.symbol_name,
                    qv.severity,
                    qv.message,
                )
            )
    total_violations += qd_blocking

    json_payload: Dict[str, Any] = {
        "passed": total_violations == 0,
        "files_scanned": len(py_files),
        "total_violations": total_violations,
        "sast_critical": total_sast_violations,
        "violations": compact_violations,
    }
    _append_quality_payload(json_payload, args, qd_blocking, qd_violations)

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
