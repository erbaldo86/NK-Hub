# -*- coding: utf-8 -*-
"""Helper CLI pure-stdlib per opzioni quality-diff, allowed-files, overlay e parser di ast_guard_validator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.lane_paths import (
    is_lane_container_entry,
    resolve_staging_dir,
    strip_staging_rel_parts,
)


def _scan_overlay_frontend(
    targets_to_scan: List[Path],
    overlay_ctx: Tuple[Path, Path, Set[str]],
) -> List[Any]:
    """Scansiona i file Frontend overlaid in modalita differenziale."""
    from _internal.ast_guard_validator.frontend_static_checker import (
        _resolve_frontend_pre_code,
        scan_frontend_code,
    )
    from _internal.ast_guard_validator.frontend_static_rules import (
        FRONTEND_EXTENSIONS,
        _SKIP_DIRS,
    )
    from _internal.ast_guard_validator.overlay_helpers import (
        collect_overlay_frontend_files,
    )

    prod_root, stage_root, deleted_norm = overlay_ctx
    fe_files = collect_overlay_frontend_files(
        targets_to_scan,
        prod_root,
        stage_root,
        deleted_norm,
        sorted(FRONTEND_EXTENSIONS),
        sorted(_SKIP_DIRS),
    )
    violations: List[Any] = []
    for fpath in fe_files:
        content = fpath.read_text(encoding="utf-8-sig", errors="replace")
        f_res = fpath.resolve()
        pre_code = (
            _resolve_frontend_pre_code(fpath, stage_root, prod_root)
            if stage_root.is_dir() and f_res.is_relative_to(stage_root)
            else None
        )
        violations.extend(scan_frontend_code(content, fpath.as_posix(), pre_code=pre_code))
    return violations


def _collect_frontend_diff_violations(
    targets_to_scan: List[Path],
    overlay_ctx: Optional[Tuple[Path, Path, Set[str]]] = None,
) -> List[Any]:
    """Esegue lo scanner statico frontend su overlay o target diretti."""
    if overlay_ctx is not None:
        return _scan_overlay_frontend(targets_to_scan, overlay_ctx)
    from _internal.ast_guard_validator.frontend_static_checker import (
        scan_frontend_directory,
    )

    violations: List[Any] = []
    for target_root in targets_to_scan:
        violations.extend(scan_frontend_directory(target_root))
    return violations


def _collect_quality_diff_violations(
    args: Any,
    py_items: List[Tuple[Path, str, str]],
    targets_to_scan: List[Path],
    overlay_ctx: Optional[Tuple[Path, Path, Set[str]]] = None,
) -> List[Any]:
    """Esegue il ratchet differenziale Python e lo scanner statico frontend."""
    if not getattr(args, "quality_diff", False):
        return []
    from _internal.ast_guard_validator.quality_diff_checker import (
        check_python_quality_diff,
    )

    violations: List[Any] = []
    for py_file, qd_pre, code in py_items:
        violations.extend(
            check_python_quality_diff(qd_pre, code, py_file.as_posix())
        )
    violations.extend(_collect_frontend_diff_violations(targets_to_scan, overlay_ctx))
    return violations


def _is_active_staged_file(f: Path, stage_base: Path, excl_lanes: bool) -> bool:
    """True se il file e regolare e non appartiene a lanes/ in modalita legacy."""
    return f.is_file() and not (excl_lanes and is_lane_container_entry(f.relative_to(stage_base).parts))


def _collect_allowed_file_violations(
    args: Any, workspace_root: Path
) -> List[Any]:
    """Verifica che i file nello staging attivo rispettino --allowed-files."""
    raw_allowed = getattr(args, "allowed_files", "") or ""
    allowed_patterns = [p.strip() for p in raw_allowed.split(",") if p.strip()]
    if not allowed_patterns:
        return []
    from _internal.ast_guard_validator.quality_diff_checker import (
        check_allowed_files,
    )

    stage_base, norm_lane = resolve_staging_dir(
        workspace_root,
        lane_id=getattr(args, "lane_id", None),
        staging_dir=getattr(args, "stage_dir", None),
    )
    if not stage_base.is_dir():
        return []
    excl_lanes = norm_lane is None and stage_base.name == ".staging"
    staged_files = sorted(
        f for f in stage_base.rglob("*") if _is_active_staged_file(f, stage_base, excl_lanes)
    )
    return check_allowed_files(staged_files, stage_base, allowed_patterns)


def _run_quality_and_scope_checks(
    args: Any,
    py_items: List[Tuple[Path, str, str]],
    targets_to_scan: List[Path],
    workspace_root: Path,
    overlay_ctx: Optional[Tuple[Path, Path, Set[str]]] = None,
) -> Tuple[List[Any], int]:
    """Esegue --quality-diff e --allowed-files restituendo violazioni e bloccanti."""
    qd_violations: List[Any] = []
    qd_violations.extend(
        _collect_quality_diff_violations(
            args, py_items, targets_to_scan, overlay_ctx=overlay_ctx
        )
    )
    qd_violations.extend(_collect_allowed_file_violations(args, workspace_root))
    blocking_count = sum(1 for v in qd_violations if v.severity in ("HIGH", "MEDIUM", "CRITICAL"))
    if not args.json:
        for v in qd_violations:
            loc = f"L{v.line_number}" if v.line_number is not None else "GLOBAL"
            print(f"[QUALITY-DIFF:{v.severity}] {v.file_path}:{loc} [{v.rule_id}] {v.message}")
    return qd_violations, blocking_count


def _resolve_pre_codes(
    py_file: Path,
    code: str,
    workspace_root: Path,
    resolve_prod_fn: Any,
) -> Tuple[str, str]:
    """Risolve pre_code di produzione e baseline pre_code per il ratchet quality-diff."""
    prod_file = resolve_prod_fn(py_file, workspace_root)
    pre_code = code
    if prod_file is not None:
        try:
            pre_code = prod_file.read_text(encoding="utf-8")
        except OSError:
            pre_code = code
    in_staging = strip_staging_rel_parts(py_file.resolve().parts)[0] >= 0
    qd_pre = pre_code if (prod_file is not None or not in_staging) else ""
    return pre_code, qd_pre


def _append_quality_payload(
    json_payload: Dict[str, Any],
    args: Any,
    qd_blocking: int,
    qd_violations: List[Any],
) -> None:
    """Popola il payload JSON finale con i dettagli del ratchet differenziale."""
    if args.quality_diff or args.allowed_files:
        json_payload["quality_diff_violations"] = qd_blocking
        json_payload["quality_diff_details"] = [v.model_dump() for v in qd_violations]


def format_compact_violation(
    file_path: str,
    line: Optional[int],
    rule: str,
    symbol: Optional[str],
    severity: str,
    msg: str,
) -> Dict[str, Any]:
    """Formatta una violazione compatta {file, line, rule, symbol, severity, msg[:180]}."""
    return {
        "file": file_path,
        "line": line,
        "rule": rule,
        "symbol": symbol,
        "severity": severity,
        "msg": (msg or "")[:180],
    }


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI di AST Guard Validator."""
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
        "--lane-id",
        dest="lane_id",
        default=None,
        help="Lane ID opzionale per staging isolato (.staging/lanes/<id>)",
    )
    parser.add_argument(
        "--overlay-staging",
        action="store_true",
        help="Sovrappone i file in .staging/ sulla produzione escludendo i path in .deleted_files.json",
    )
    parser.add_argument(
        "--allowed-mutations",
        type=str,
        default="",
        help="Simboli separati da virgola autorizzati a mutare firma",
    )
    parser.add_argument(
        "--quality-diff",
        action="store_true",
        help="Abilita controlli differenziali di complessita, nesting, except, test e frontend",
    )
    parser.add_argument(
        "--allowed-files",
        type=str,
        default="",
        help="Elenco separato da virgola di pattern consentiti in .staging/",
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
    return parser
