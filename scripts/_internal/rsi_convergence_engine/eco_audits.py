# -*- coding: utf-8 -*-
"""Audit Markdown, GT-14/CRIT-01, twin parity, quality-diff AST, frontend e dry-run."""

from __future__ import annotations

import hashlib, importlib, importlib.util, json, pkgutil, sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from _internal.nk_common.constants import VERSION
from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir, strip_staging_rel_parts  # noqa: F401
from _internal.rsi_convergence_engine.constants import (
    _collect_overlay_md_files, _scripts_dir, _workspace_root, load_staging_deleted_set_impl, resolve_effective_staging,
)
from _internal.rsi_convergence_engine.profiles import verify_ste100_compliance
from _internal.rsi_convergence_engine.sast_scanner import audit_markdown_doc_references

FRONTEND_SUFFIXES: Tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx", ".css")
_SKIP_STG_PARTS: Set[str] = {"__pycache__", ".pytest_cache", "node_modules", ".git", ".venv", "venv"}
_SKIP_PROD_FE_PARTS: Set[str] = _SKIP_STG_PARTS | {".staging", ".mypy_cache", ".wal", "htmlcov"}
_VERSION_MARKERS: Tuple[str, ...] = ("v1.", VERSION, "v3.", "v4.", "v5.", "v6.", "[RULE-STE100]")


def _read_unique_md_bytes(md_file: Path, has_skills_hub: bool, state: Dict[str, Any]) -> Optional[bytes]:
    raw_bytes = md_file.read_bytes()
    if has_skills_hub:
        return raw_bytes
    md_sha = hashlib.sha256(raw_bytes).hexdigest()
    if md_sha in state["seen_hashes"]:
        return None
    state["seen_hashes"].add(md_sha)
    return raw_bytes


def _logical_md_rel(md_file: Path, root: Path) -> str:
    try:
        rel_md = md_file.relative_to(root).as_posix()
    except ValueError:
        return md_file.name
    stg_idx, rel_after, _lane = strip_staging_rel_parts(Path(rel_md).parts)
    return "/".join(rel_after) if stg_idx == 0 else rel_md


def _should_check_ste100(
    md_file: Path, content: str, logical_rel: str, canonical_profile: str, has_skills_hub: bool
) -> bool:
    if has_skills_hub:
        if canonical_profile == "ste100_rsi" or md_file.name == "PATCH_NOTES.md":
            return True
        if logical_rel.startswith((".agents/agents/", "nk_genome/")):
            return True
        return logical_rel.startswith(".agents/skills/") and any(m in content for m in _VERSION_MARKERS)
    if canonical_profile in ("ste100_rsi", "spec_rsi"):
        return True
    if ".agents" in md_file.parts or md_file.name in ("SKILL.md", "PATCH_NOTES.md"):
        return True
    return any(m in content for m in (".agents", "SKILL.md", "[RULE-STE100]"))


def _is_active_audit_doc(
    md_name: str, logical_rel: str, is_skill: bool, is_agent: bool, has_skills_hub: bool
) -> bool:
    if md_name in ("PATCH_NOTES.md", "repo_map.md", "SKILL_INDEX.md"):
        return False
    if has_skills_hub:
        return is_skill or is_agent or logical_rel.startswith("nk_genome/")
    return logical_rel.startswith((".agents/", "nk_genome/"))


def _audit_single_markdown_file(
    md_file: Path, root: Path, engine: Any, canonical_profile: str, deleted_rel: Set[str],
    has_skills_hub: bool, state: Dict[str, Any],
) -> None:
    """Ispeziona un singolo file Markdown per STE100, link relativi e script citati."""
    raw_bytes = _read_unique_md_bytes(md_file, has_skills_hub, state)
    if raw_bytes is None:
        return
    logical_rel = _logical_md_rel(md_file, root)
    content = raw_bytes.decode("utf-8", errors="replace")
    is_skill = logical_rel.startswith(".agents/skills/")
    is_agent = logical_rel.startswith(".agents/agents/")
    if is_skill and md_file.name == "SKILL.md":
        state["skills"] += 1
    if is_agent and md_file.name == "agent.md":
        state["agents"] += 1
    if _should_check_ste100(md_file, content, logical_rel, canonical_profile, has_skills_hub):
        ste_res = verify_ste100_compliance(content)
        if not ste_res["passed"]:
            viols = ste_res["violations"][:2] if has_skills_hub else ste_res["violations"]
            state["ste100"].extend(f"{logical_rel}: {v}" for v in viols)
    active_doc = _is_active_audit_doc(md_file.name, logical_rel, is_skill, is_agent, has_skills_hub)
    b_links, p_scripts = audit_markdown_doc_references(
        md_file, content, root, engine._resolve_candidate, deleted_rel=deleted_rel, check_scripts=active_doc
    )
    state["broken"].extend(b_links)
    state["phantom"].extend(p_scripts)


def audit_markdown_docs_impl(
    engine: Any, root: Path, canonical_profile: str, verified_files: List[Path], violations: List[str]
) -> Dict[str, Any]:
    """Audit dei documenti Markdown (STE100, link relativi e script mancanti/vietati)."""
    has_skills_hub = (root / ".agents" / "skills").is_dir() or (root / ".staging" / ".agents" / "skills").is_dir()
    deleted_rel = engine._load_staging_deleted_set(root)
    if has_skills_hub:
        md_candidates: List[Path] = []
        for sub in (".agents/skills", ".agents/agents", "nk_genome"):
            md_candidates.extend(_collect_overlay_md_files(root, sub, recursive=True))
        for doc_rel in ("nk_genome/PATCH_NOTES.md", "nk_docs_and_setup/README.md"):
            cand = engine._resolve_candidate(root, doc_rel)
            if cand.is_file():
                md_candidates.append(cand)
    else:
        md_candidates = _collect_overlay_md_files(root, "", recursive=True)
    seen_paths: Set[Path] = set()
    state: Dict[str, Any] = {"skills": 0, "agents": 0, "broken": [], "phantom": [], "ste100": [], "seen_hashes": set()}
    for md_file in md_candidates:
        if not md_file.is_file():
            continue
        res_p = md_file.resolve()
        if res_p in seen_paths:
            continue
        seen_paths.add(res_p)
        verified_files.append(res_p)
        _audit_single_markdown_file(md_file, root, engine, canonical_profile, deleted_rel, has_skills_hub, state)
    if state["broken"]:
        violations.append(f"Link ausiliari interrotti: {state['broken']}")
    if state["phantom"]:
        violations.extend(state["phantom"])
    return {
        "passed": not state["broken"] and not state["phantom"],
        "skills_verified": state["skills"], "agents_verified": state["agents"],
        "broken_links": state["broken"], "phantom_scripts": state["phantom"],
        "ste100_warnings": state["ste100"], "ste100_issues": [],
    }


def _load_nk_registry_indexer_cls(root: Path) -> Optional[Any]:
    """Carica la classe canonica NKRegistryIndexer da _internal/scripts o file locale."""
    for mod_name in ("nk_registry_indexer", "scripts.nk_registry_indexer"):
        try:
            cand = getattr(__import__(mod_name, fromlist=["NKRegistryIndexer"]), "NKRegistryIndexer", None)
            if cand is not None and hasattr(cand, "verify_gt14_crit01_governance"):
                return cand
        except ImportError:
            continue
    cands = (
        root / ".staging" / "scripts" / "nk_registry_indexer.py", root / "scripts" / "nk_registry_indexer.py",
        _scripts_dir / "nk_registry_indexer.py", _workspace_root / ".staging" / "scripts" / "nk_registry_indexer.py",
        _workspace_root / "scripts" / "nk_registry_indexer.py",
    )
    for cand_path in cands:
        if not cand_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("_nk_registry_indexer_shared", str(cand_path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cls = getattr(mod, "NKRegistryIndexer", None)
            if cls is not None and hasattr(cls, "verify_gt14_crit01_governance"):
                return cls
    return None


def audit_gt14_governance_impl(
    root: Path, measured_components: List[str], violations: List[str]
) -> Tuple[List[str], Dict[str, Any]]:
    """Verifica governance GT-14 / CRIT-01 tramite NKRegistryIndexer."""
    if not (_collect_overlay_md_files(root, ".agents/agents", True) or _collect_overlay_md_files(root, ".agents/skills", True)):
        return [], {"passed": True, "skipped": True, "reason": "no_agents_or_skills_md_files", "agents_checked": 0, "skills_checked": 0, "issues": []}
    try:
        nri_cls = _load_nk_registry_indexer_cls(root)
        if nri_cls is None:
            return [], {"passed": True, "skipped": True, "reason": "registry_indexer_unavailable", "issues": []}
        gt14_res = nri_cls(workspace_root=root).verify_gt14_crit01_governance()
        gt14_issues = list(gt14_res.get("issues") or [])
        if not gt14_res.get("passed", False):
            gt14_issues = gt14_issues or ["Violazione governance GT-14 / CRIT-01."]
            violations.extend(gt14_issues)
        measured_components.append("gt14_crit01_governance")
        return gt14_issues, gt14_res
    except Exception as exc:
        gt14_issues = [f"Errore verifica governance GT-14/CRIT-01: {exc}"]
        violations.extend(gt14_issues)
        return gt14_issues, {"passed": False, "issues": gt14_issues}


def _fallback_twin_parity(indexer: Any) -> Dict[str, Any]:
    agent_map = indexer._collect_priority_native_agents()
    deleted_rel = indexer._load_staging_deleted_paths()
    mismatches: List[str] = []
    local_viols: List[str] = []
    for agent_name in sorted(agent_map.keys()):
        src_p, _ = agent_map[agent_name]
        rel_twin = f".agents/plugins/nk-gate/agents/{agent_name}.md"
        stg_twin = indexer.stage_dir / rel_twin
        twin_p = stg_twin if stg_twin.is_file() else (indexer.workspace_root / rel_twin)
        if rel_twin in deleted_rel or not twin_p.is_file():
            mismatches.append(agent_name)
            local_viols.append(f"Manifesto gemello mancante o eliminato: {rel_twin}")
        elif not indexer._sha256_matches_eol_normalized(twin_p, indexer._compute_sha256(twin_p), indexer._compute_sha256(src_p)):
            mismatches.append(agent_name)
            local_viols.append(f"Drift manifesto gemello per {agent_name}: eseguire nk_registry_indexer.py --sync")
    return {"passed": not mismatches, "skipped": False, "checked_agents": len(agent_map), "mismatches": mismatches, "violations": local_viols}


def audit_twin_manifest_parity_impl(root: Path) -> Dict[str, Any]:
    """Delega a NKRegistryIndexer la verifica di parita tra agent.md e plugin nk-gate."""
    agents_ok = any(d.is_dir() for d in (root / ".staging" / ".agents" / "agents", root / ".agents" / "agents"))
    twins_ok = any(d.is_dir() for d in (root / ".staging" / ".agents" / "plugins" / "nk-gate" / "agents", root / ".agents" / "plugins" / "nk-gate" / "agents"))
    if not agents_ok or not twins_ok:
        return {"passed": True, "skipped": True, "checked_agents": 0, "mismatches": [], "violations": []}
    nri_cls = _load_nk_registry_indexer_cls(root)
    if nri_cls is None:
        return {"passed": False, "skipped": False, "checked_agents": 0, "mismatches": ["registry_indexer_unavailable"], "violations": ["Impossibile caricare nk_registry_indexer per audit twin parity."]}
    indexer = nri_cls(workspace_root=root)
    if hasattr(indexer, "audit_twin_manifest_parity"):
        return dict(indexer.audit_twin_manifest_parity())
    return _fallback_twin_parity(indexer)


def report_is_dry_run_impl(report: Optional[Path | str | Dict[str, Any]]) -> bool:
    """Rileva se un report SAST o DAST risulta eseguito in modalita dry-run."""
    if report is None:
        return False
    payload: Any = report if isinstance(report, dict) else None
    if isinstance(report, (str, Path)):
        rp = Path(report)
        if not rp.is_file():
            return False
        try:
            payload = json.loads(rp.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
    if not isinstance(payload, dict):
        return False
    status_val = str(payload.get("status", "")).upper()
    return bool(payload.get("is_dry_run") or payload.get("dry_run") or "DRY_RUN" in status_val)


def _load_agv_symbol(ws_root: Path, mod_name: str, attr_name: str) -> Optional[Any]:
    """Carica pigramente un simbolo da _internal.ast_guard_validator."""
    stg_scripts = ws_root / ".staging" / "scripts"
    if stg_scripts.is_dir():
        stg_str = str(stg_scripts)
        if stg_str not in sys.path:
            sys.path.insert(0, stg_str)
        internal_pkg = sys.modules.get("_internal")
        if internal_pkg is not None and hasattr(internal_pkg, "__path__"):
            internal_pkg.__path__ = pkgutil.extend_path(internal_pkg.__path__, "_internal")
        agv_pkg = sys.modules.get("_internal.ast_guard_validator")
        cand_dir = str(stg_scripts / "_internal" / "ast_guard_validator")
        if agv_pkg is not None and hasattr(agv_pkg, "__path__") and Path(cand_dir).is_dir():
            cur = list(agv_pkg.__path__)
            if cand_dir not in cur:
                agv_pkg.__path__ = [cand_dir, *cur]
    try:
        return getattr(importlib.import_module(f"_internal.ast_guard_validator.{mod_name}"), attr_name, None)
    except ImportError:
        return None


def _make_import_fail_violation(rule_id: str, rel_label: str, symbol_name: str) -> Any:
    return SimpleNamespace(rule_id=rule_id, severity="HIGH", file_path=rel_label, line_number=0, message=f"Impossibile caricare '{symbol_name}' (fail-closed HIGH).")


def classify_quality_violations(violations: Sequence[Any]) -> Dict[str, Any]:
    """Classifica le violazioni Quality-Diff e Frontend senza doppio conteggio."""
    semantic_drift, high_cnt, med_cnt, low_cnt = 0, 0, 0, 0
    messages: List[str] = []
    for item in violations:
        rid, sev = str(getattr(item, "rule_id", "QD-UNKNOWN")), str(getattr(item, "severity", "MEDIUM")).upper()
        fpath, lineno = str(getattr(item, "file_path", "<target>")), int(getattr(item, "line_number", 0) or 0)
        if rid == "QD-SCOPE-CREEP":
            semantic_drift += 1
        elif sev == "HIGH":
            high_cnt += 1
        elif sev == "MEDIUM":
            med_cnt += 1
        else:
            low_cnt += 1
        messages.append(f"[{rid}] {f'{fpath}:{lineno}' if lineno > 0 else fpath}: {getattr(item, 'message', '')}")
    return {"semantic_drift_findings": semantic_drift, "high_findings": high_cnt, "medium_findings": med_cnt, "low_findings": low_cnt, "messages": messages}


def inspect_python_quality_staged(fpath: Path, baseline_text: str, current_text: str, rel_label: str, ws_root: Path) -> List[Any]:
    """Applica check_python_quality_diff ai file in .staging/ evitando falsi positivi legacy."""
    if strip_staging_rel_parts(fpath.parts)[0] < 0:
        return []
    fn = _load_agv_symbol(ws_root, "quality_diff_checker", "check_python_quality_diff")
    return list(fn(baseline_text, current_text, target_file=rel_label)) if fn else [_make_import_fail_violation("QD-IMPORT-FAIL", rel_label, "quality_diff_checker.check_python_quality_diff")]


def inspect_frontend_file(fpath: Path, content: str, rel_label: str, ws_root: Path) -> List[Any]:
    """Applica scan_frontend_code stdlib ai file frontend (.ts, .tsx, .js, .jsx, .css)."""
    if fpath.suffix.lower() not in FRONTEND_SUFFIXES:
        return []
    fn = _load_agv_symbol(ws_root, "frontend_static_checker", "scan_frontend_code")
    return list(fn(content, rel_label)) if fn else [_make_import_fail_violation("FE-IMPORT-FAIL", rel_label, "frontend_static_checker.scan_frontend_code")]


def _scan_staged_entry(root: Path, stg_root: Path, fpath: Path, viols: List[Any]) -> int:
    rel_p = fpath.relative_to(stg_root)
    rel_posix, ext = rel_p.as_posix(), fpath.suffix.lower()
    if ext == ".py":
        post = fpath.read_text(encoding="utf-8", errors="replace")
        prod_c = root / rel_p
        pre = prod_c.read_text(encoding="utf-8", errors="replace") if prod_c.is_file() else ""
        viols.extend(inspect_python_quality_staged(fpath, pre, post, rel_posix, root))
        return 1
    if ext in FRONTEND_SUFFIXES:
        viols.extend(inspect_frontend_file(fpath, fpath.read_text(encoding="utf-8", errors="replace"), rel_posix, root))
        return 1
    return 0


def _collect_staged_entry_if_active(
    fpath: Path, stg_root: Path, root: Path, viols: List[Any], exclude_lanes: Optional[bool] = None
) -> Optional[Tuple[int, str, Optional[Path]]]:
    """Restituisce (files_checked_delta, rel_posix, scope_file) se il file staging e attivo."""
    if not fpath.is_file():
        return None
    rel_parts = fpath.relative_to(stg_root).parts
    is_base_stg = (stg_root.name == ".staging") if exclude_lanes is None else bool(exclude_lanes)
    if (is_base_stg and rel_parts and is_lane_container_entry(rel_parts)) or any(part in _SKIP_STG_PARTS for part in rel_parts):
        return None
    rel_posix = fpath.relative_to(stg_root).as_posix()
    scope_fp = fpath if fpath.name != ".gitkeep" else None
    return _scan_staged_entry(root, stg_root, fpath, viols), rel_posix, scope_fp


def _collect_staged_quality_violations(
    root: Path, stg_root: Path, exclude_lanes: Optional[bool] = None
) -> Tuple[int, Set[str], List[Path], List[Any]]:
    viols: List[Any] = []
    files_checked, staged_rels, scope_files = 0, set(), []
    if not stg_root.is_dir():
        return files_checked, staged_rels, scope_files, viols
    for fpath in sorted(stg_root.rglob("*")):
        res = _collect_staged_entry_if_active(fpath, stg_root, root, viols, exclude_lanes=exclude_lanes)
        if res is None:
            continue
        checked_d, rel_posix, scope_fp = res
        files_checked += checked_d
        staged_rels.add(rel_posix)
        if scope_fp is not None:
            scope_files.append(scope_fp)
    return files_checked, staged_rels, scope_files, viols

def _scan_prod_frontend(root: Path, staged_rels: Set[str], deleted_rels: Set[str], viols: List[Any]) -> int:
    checked = 0
    if not root.is_dir():
        return 0
    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file() or fpath.suffix.lower() not in FRONTEND_SUFFIXES:
            continue
        rel_p = fpath.relative_to(root)
        if any(part in _SKIP_PROD_FE_PARTS or part.startswith("tmp_pytest") for part in rel_p.parts):
            continue
        rel_posix = rel_p.as_posix()
        if rel_posix not in staged_rels and rel_posix not in deleted_rels:
            checked += 1
            viols.extend(inspect_frontend_file(fpath, fpath.read_text(encoding="utf-8", errors="replace"), rel_posix, root))
    return checked

def _normalize_allowed_patterns(allowed_files: Optional[Union[str, Sequence[str]]]) -> List[str]:
    if isinstance(allowed_files, str):
        return [p.strip() for p in allowed_files.split(",") if p.strip()]
    return [str(p).strip() for p in (allowed_files or []) if str(p).strip()]

def _resolve_stg_and_deleted(root: Path, lane_id: Optional[str], staging_dir: Optional[Path]) -> Tuple[Path, bool, Set[str]]:
    stg_root = resolve_effective_staging(root, lane_id=lane_id, staging_dir=staging_dir)
    excl_lanes = lane_id is None and staging_dir is None and stg_root.name == ".staging"
    deleted_rels = load_staging_deleted_set_impl(root, lane_id=lane_id, staging_dir=staging_dir) if stg_root.is_dir() else set()
    return stg_root, excl_lanes, deleted_rels


def audit_quality_and_frontend_impl(
    root: Path, allowed_files: Optional[Union[str, Sequence[str]]] = None, scan_prod_frontend: bool = False,
    lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Scansiona .staging/ (e prod frontend se richiesto) con Quality-Diff AST e --allowed-files."""
    stg_root, excl_lanes, deleted_rels = _resolve_stg_and_deleted(root, lane_id, staging_dir)
    patterns = _normalize_allowed_patterns(allowed_files)
    if not stg_root.is_dir() and not scan_prod_frontend and not patterns:
        return {"passed": True, "skipped": True, "files_checked": 0, "semantic_drift_findings": 0, "high_findings": 0, "medium_findings": 0, "low_findings": 0, "violations": []}
    files_checked, staged_rels, scope_files, viols = _collect_staged_quality_violations(root, stg_root, exclude_lanes=excl_lanes)
    if scan_prod_frontend:
        files_checked += _scan_prod_frontend(root, staged_rels, deleted_rels, viols)
    if patterns:
        allowed_fn = _load_agv_symbol(root, "quality_diff_checker", "check_allowed_files")
        if allowed_fn is None:
            viols.append(_make_import_fail_violation("QD-IMPORT-FAIL", ".staging", "quality_diff_checker.check_allowed_files"))
        elif stg_root.is_dir():
            viols.extend(list(allowed_fn(scope_files, stg_root, patterns)))
    b = classify_quality_violations(viols)
    return {"passed": not b["messages"], "skipped": False, "files_checked": files_checked, "semantic_drift_findings": b["semantic_drift_findings"], "high_findings": b["high_findings"], "medium_findings": b["medium_findings"], "low_findings": b["low_findings"], "violations": b["messages"]}
