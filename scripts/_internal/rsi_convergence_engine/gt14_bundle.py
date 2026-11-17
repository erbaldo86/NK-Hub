"""Sonde GT-14 in-process (6 -> 1) e salvataggio atomico del bundle diagnostico."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from _internal.nk_common.io import atomic_write_text
from _internal.rsi_convergence_engine.constants import _scripts_dir, _workspace_root
from _internal.rsi_convergence_engine.gt14_probes import (
    _collect_ast_guard_targets,  # noqa: F401
    _count_live_overlay_skills,  # noqa: F401
    _run_ast_guard_probe,
    _run_dast_probe,
    _run_quality_baseline_probe,
)


def _load_probe_module(root: Path, mod_name: str) -> Any:
    """Carica un modulo sonda privilegiando .staging/ rispetto alla produzione."""
    cand_dirs = [
        root / ".staging" / "scripts",
        root / "scripts",
        _scripts_dir,
        _workspace_root / ".staging" / "scripts",
        _workspace_root / "scripts",
    ]
    for d in cand_dirs:
        fpath = d / f"{mod_name}.py"
        if fpath.is_file():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            existing = sys.modules.get(mod_name)
            if existing is not None and getattr(existing, "__file__", None):
                try:
                    if Path(str(existing.__file__)).resolve() == fpath.resolve():
                        return existing
                except OSError:
                    pass
            spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                return mod
    return importlib.import_module(mod_name)


def emit_gt14_bundle_impl(
    engine: Any,
    workspace_root: Optional[Union[str, Path]] = None,
    with_dast: bool = False,
    strict_verify: bool = False,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Esegue in-process le sonde GT-14 (6 -> 1) e salva atomicamente il bundle JSON."""
    t0 = time.perf_counter()
    root = Path(workspace_root).resolve() if workspace_root else engine.workspace_root
    stg_dir = root / ".staging"
    probes: Dict[str, Any] = {}

    try:
        nri_mod = _load_probe_module(root, "nk_registry_indexer")
        probes["registry_verify"] = nri_mod.NKRegistryIndexer(workspace_root=root).verify()
    except Exception as exc:
        probes["registry_verify"] = {
            "passed": False,
            "status": "ERROR",
            "issues": [f"registry_verify error: {exc}"],
        }

    try:
        phc_mod = _load_probe_module(root, "preflight_health_check")
        pf_res = phc_mod.PreflightHealthChecker(workspace_root=root).run_full_check(
            auto_fix=False
        )
        pf_passed = (
            pf_res.get("status") not in ("CRITICAL_FAIL", "FAIL")
            and len(pf_res.get("issues_detected", [])) == 0
        )
        pf_out = dict(pf_res)
        pf_out["passed"] = bool(pf_passed)
        probes["preflight_check"] = pf_out
    except Exception as exc:
        probes["preflight_check"] = {
            "passed": False,
            "status": "ERROR",
            "issues_detected": [f"preflight_check error: {exc}"],
        }

    probes["ast_guard"] = _run_ast_guard_probe(root, stg_dir, _load_probe_module)
    dast_res, dast_test_report = _run_dast_probe(
        root, stg_dir, bool(with_dast), _load_probe_module
    )
    probes["dast_overlay"] = dast_res

    try:
        probes["rsi_verify"] = engine.verify_ecosystem(
            root_dir=root,
            run_pytest=bool(strict_verify and dast_test_report is None),
            strict_verify=bool(strict_verify),
            test_report=dast_test_report,
        )
    except Exception as exc:
        probes["rsi_verify"] = {
            "passed": False,
            "status": "ERROR",
            "violations": [f"rsi_verify error: {exc}"],
        }

    probes["quality_baseline"] = _run_quality_baseline_probe(
        root, stg_dir, probes, dast_test_report, _load_probe_module
    )

    target_out = (
        Path(output_path).resolve()
        if output_path is not None
        else (Path(tempfile.gettempdir()) / "nk_diagnostics" / "gt14_audit_bundle.json")
    )
    all_passed = all(
        bool(probes[k].get("passed", False))
        for k in (
            "registry_verify",
            "preflight_check",
            "ast_guard",
            "rsi_verify",
            "quality_baseline",
            "dast_overlay",
        )
    )
    bundle_payload: Dict[str, Any] = {
        "passed": all_passed,
        "status": "PASS" if all_passed else "FAIL",
        "workspace_root": str(root),
        "with_dast": bool(with_dast),
        "strict_verify": bool(strict_verify),
        "probes_executed": 6 if with_dast else 5,
        "bundle_path": str(target_out),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "probes": probes,
    }

    ok_w, err_w = atomic_write_text(
        target_out,
        json.dumps(bundle_payload, indent=2, ensure_ascii=False),
    )
    if not ok_w:
        raise OSError(f"Impossibile scrivere il bundle GT-14 {target_out}: {err_w}")
    return bundle_payload
