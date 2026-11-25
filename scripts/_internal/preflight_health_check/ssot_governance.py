# -*- coding: utf-8 -*-
"""Controllo allineamento baseline e governance SSOT per preflight_health_check."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.catalog import get_catalog_counts
from _internal.nk_common.paths import normalize_rel_path
from _internal.nk_common.thresholds import load_deleted_files
from _internal.preflight_health_check.cleanup_and_wal import DEFAULT_VERSION, VERSION

_SKILL_VERSION_RE = re.compile(r'(?m)^version:\s*["\']?([^"\'\s]+)["\']?')
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+")
_RULE_DEF_RE = re.compile(r"\[(RULE-[A-Z0-9._-]+)\]")
_RULE_REF_RE = re.compile(r"\[(RULE-[A-Z0-9._*-]+)\]")
_ROOT_BRIDGE_VERSION_RE = re.compile(
    rf"(?<![A-Za-z0-9_])`?v?`?{re.escape(VERSION)}`?(?![A-Za-z0-9_.-])"
)


def get_expected_skills_count(workspace_root: Path) -> int:
    """Legge il conteggio atteso delle skill da nk_registry_manifest.json."""
    candidates = (
        workspace_root / ".staging" / "nk_genome" / "nk_registry_manifest.json",
        workspace_root / "nk_genome" / "nk_registry_manifest.json",
    )
    for cand in candidates:
        if cand.exists() and cand.is_file():
            try:
                manifest = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    skills_idx = manifest.get("skills_index")
                    if isinstance(skills_idx, dict) and len(skills_idx) > 0:
                        return len(skills_idx)
                    summary = manifest.get("summary")
                    if isinstance(summary, dict) and int(summary.get("total_skills", 0)) > 0:
                        return int(summary["total_skills"])
            except Exception:
                pass
    return 11


def _pick_metric_num(data: Dict[str, Any], metrics: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
    """Estrae il primo valore numerico valido dalle chiavi candidate in metrics o root."""
    for k in keys:
        for src in (metrics, data):
            raw = src.get(k)
            val = raw.get("value") if isinstance(raw, dict) else raw
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return float(val)
    return None


def _eval_external_baseline(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida quality_baseline.json di un repo app esterno supportando schema metrics e flat."""
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    total_v = _pick_metric_num(data, metrics, ("unit_tests_total", "total_tests", "tests_total", "total_golden_tests", "golden_tests_count"))
    failed_v = _pick_metric_num(data, metrics, ("failed_tests",))
    pass_v = _pick_metric_num(data, metrics, ("unit_tests_pass_pct", "pass_rate_pct", "pass_rate"))
    tests_total = int(total_v) if total_v is not None else 0
    failed_tests = int(failed_v) if failed_v is not None else 0
    pass_pct = float(pass_v) if pass_v is not None else 0.0
    passed = tests_total > 0 and failed_tests == 0 and pass_pct >= 100.0
    return {
        "passed": passed,
        "version": data.get("_version", data.get("version", DEFAULT_VERSION)),
        "tests_total": tests_total,
        "failed_tests": failed_tests,
        "pass_pct": pass_pct,
        "external_app": True,
        "details": (
            f"External app baseline aligned ({tests_total} tests, pass_pct={pass_pct}%)"
            if passed
            else f"External app baseline discrepancy: total={tests_total}, failed={failed_tests}, pass_pct={pass_pct}"
        ),
    }


def _is_external_app_workspace(ws: Path) -> bool:
    """True per repo app esterne con src_app/ prive di .agents/skills."""
    return (
        (ws / "src_app").is_dir()
        and not (ws / ".agents" / "skills").is_dir()
        and not (ws / ".staging" / ".agents" / "skills").is_dir()
    )


def _eval_hub_baseline(checker: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida quality_baseline.json standard dell'ecosistema NK_Hub."""
    expected_skills = checker._get_expected_skills_count()
    metrics = data.get("metrics", {})
    raw_skills = metrics.get("skills_audited", 0)
    skills_audited = raw_skills.get("value", 0) if isinstance(raw_skills, dict) else raw_skills
    raw_crv = metrics.get("crv_macro_phases", 0)
    crv_phases = raw_crv.get("value", 0) if isinstance(raw_crv, dict) else raw_crv
    raw_pass = metrics.get("unit_tests_pass_pct", 100.0)
    unit_pass = raw_pass.get("value", 0.0) if isinstance(raw_pass, dict) else raw_pass

    passed = skills_audited == expected_skills and crv_phases == 4 and float(unit_pass) >= 100.0
    return {
        "passed": passed,
        "version": data.get("_version", DEFAULT_VERSION),
        "skills_audited": skills_audited,
        "expected_skills": expected_skills,
        "crv_macro_phases": crv_phases,
        "details": (
            f"Baseline perfectly aligned ({expected_skills} canonical skills, CRV 4 Macro-Phases)"
            if passed
            else f"Discrepancy: skills={skills_audited}/{expected_skills}, crv_phases={crv_phases}/4, pass_pct={unit_pass}"
        ),
    }


def check_baseline_alignment(checker: Any) -> Dict[str, Any]:
    """Verifica che quality_baseline.json sia valido e allineato al manifesto."""
    ws = Path(checker.workspace_root)
    staged_baseline = ws / ".staging" / "nk_tracking" / "quality_baseline.json"
    target_baseline = staged_baseline if staged_baseline.exists() else checker.baseline_file
    if not target_baseline.exists():
        return {"passed": False, "details": "quality_baseline.json not found"}

    try:
        with open(target_baseline, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"passed": False, "details": "quality_baseline.json root is not a dict"}

        return _eval_external_baseline(data) if _is_external_app_workspace(ws) else _eval_hub_baseline(checker, data)
    except Exception as e:
        return {"passed": False, "details": f"Corrupted quality_baseline.json: {e}"}


def normalize_tombstone_rel(raw_item: str) -> str:
    """Normalizza un percorso relativo di tombstone tramite nk_common.paths."""
    return normalize_rel_path(raw_item)


def collect_agents_overlay(checker: Any) -> Dict[str, Path]:
    """Costruisce la mappa virtuale overlay (.staging/ > prod) sotto .agents/."""
    checker._last_tombstone_error = None
    checker._tombstone_errors = []
    deleted_rel: Set[str] = set()
    tombstone_file = checker.workspace_root / ".staging" / ".deleted_files.json"
    if tombstone_file.exists() and tombstone_file.is_file():
        try:
            raw_deleted = json.loads(tombstone_file.read_text(encoding="utf-8-sig"))
            if not isinstance(raw_deleted, (list, dict)) or (
                isinstance(raw_deleted, dict) and not isinstance(raw_deleted.get("deleted_files"), list)
            ):
                err_msg = (
                    f"Invalid .deleted_files.json schema in {tombstone_file}: "
                    "expected list or {'deleted_files': [...]}"
                )
                checker._last_tombstone_error = err_msg
                checker._tombstone_errors.append(err_msg)
            else:
                raw_items = raw_deleted if isinstance(raw_deleted, list) else raw_deleted["deleted_files"]
                for item in raw_items:
                    if not isinstance(item, str):
                        err_msg = (
                            f"Invalid non-string tombstone entry in {tombstone_file}: "
                            f"{type(item).__name__}"
                        )
                        checker._last_tombstone_error = err_msg
                        checker._tombstone_errors.append(err_msg)
                deleted_rel = load_deleted_files(deleted_manifest=tombstone_file)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            err_msg = f"Corrupt .deleted_files.json in {tombstone_file}: {exc}"
            checker._last_tombstone_error = err_msg
            checker._tombstone_errors.append(err_msg)

    overlay: Dict[str, Path] = {}
    ignored_parts = {"__pycache__", ".pytest_cache", ".wal"}

    prod_agents = checker.workspace_root / ".agents"
    if prod_agents.is_dir():
        for p in prod_agents.rglob("*"):
            if not p.is_file() or any(part in ignored_parts for part in p.parts):
                continue
            rel = p.relative_to(prod_agents).as_posix()
            if f".agents/{rel}" not in deleted_rel:
                overlay[rel] = p

    staged_agents = checker.workspace_root / ".staging" / ".agents"
    if staged_agents.is_dir():
        for p in staged_agents.rglob("*"):
            if not p.is_file() or any(part in ignored_parts for part in p.parts):
                continue
            rel = p.relative_to(staged_agents).as_posix()
            overlay[rel] = p

    return overlay


def resolve_overlay_file(workspace_root: Path, rel_path: str) -> Optional[Path]:
    """Restituisce il percorso effettivo con priorita .staging/."""
    staged = workspace_root / ".staging" / rel_path
    if staged.exists() and staged.is_file():
        return staged
    prod = workspace_root / rel_path
    if prod.exists() and prod.is_file():
        return prod
    return None


def check_ssot_governance(checker: Any) -> Dict[str, Any]:
    """Verifica parita versioni SSOT, Root Bridge padre e integrita [RULE-*]."""
    agents_overlay = checker._collect_agents_overlay()
    tombstone_err = checker._last_tombstone_error
    if "AGENTS.md" not in agents_overlay:
        if tombstone_err:
            return {"passed": False, "skipped": False, "tombstone_error": tombstone_err, "details": tombstone_err}
        return {"passed": True, "skipped": True, "details": "Synthetic workspace without .agents constitution."}

    agents_text = agents_overlay["AGENTS.md"].read_text(encoding="utf-8", errors="replace")
    has_skills_or_agents = any(
        k.endswith(("/SKILL.md", "/agent.md")) or k in ("SKILL.md", "agent.md")
        for k in agents_overlay
    )
    has_constitution_markers = any(
        tok in agents_text
        for tok in ("RULE-", "Generation", "NK Hub Generation", "Carbon", "Nexus Keystone", "Regolamento", "Versione")
    )
    if not has_constitution_markers and not has_skills_or_agents:
        if tombstone_err:
            return {"passed": False, "skipped": False, "tombstone_error": tombstone_err, "details": tombstone_err}
        return {"passed": True, "skipped": True, "details": "Synthetic workspace without .agents constitution."}

    version_mismatches: List[str] = []
    if VERSION not in agents_text:
        version_mismatches.append(f".agents/AGENTS.md: missing {VERSION}")

    for rel_k in sorted(agents_overlay):
        if not (rel_k.endswith(("/SKILL.md", "/agent.md")) or rel_k in ("SKILL.md", "agent.md")):
            continue
        txt = agents_overlay[rel_k].read_text(encoding="utf-8", errors="replace")
        m_ver = _SKILL_VERSION_RE.search(txt)
        if m_ver:
            if m_ver.group(1) != VERSION:
                version_mismatches.append(f".agents/{rel_k}: {m_ver.group(1)} != {VERSION}")
        elif VERSION not in txt:
            version_mismatches.append(f".agents/{rel_k}: missing {VERSION}")

    qb_path = checker._resolve_overlay_file("nk_tracking/quality_baseline.json")
    if qb_path is not None:
        try:
            qb_ver = json.loads(qb_path.read_text(encoding="utf-8")).get("_version")
            if qb_ver != VERSION:
                version_mismatches.append(f"nk_tracking/quality_baseline.json:_version={qb_ver}")
        except Exception as exc:
            version_mismatches.append(f"nk_tracking/quality_baseline.json:invalid({exc})")
    else:
        version_mismatches.append("nk_tracking/quality_baseline.json:MISSING")

    mn_path = checker._resolve_overlay_file("nk_genome/nk_registry_manifest.json")
    if mn_path is not None:
        try:
            mn_ver = json.loads(mn_path.read_text(encoding="utf-8")).get("version")
            if mn_ver != VERSION:
                version_mismatches.append(f"nk_genome/nk_registry_manifest.json:version={mn_ver}")
        except Exception as exc:
            version_mismatches.append(f"nk_genome/nk_registry_manifest.json:invalid({exc})")
    else:
        version_mismatches.append("nk_genome/nk_registry_manifest.json:MISSING")

    rb_path: Optional[Path] = None
    root_bridge_missing: List[str] = []
    if checker.workspace_root.name == "NK_Hub" and (checker.workspace_root.parent / ".agents").is_dir():
        staged_rb = checker.workspace_root.parent / ".staging" / ".agents" / "AGENTS.md"
        prod_rb = checker.workspace_root.parent / ".agents" / "AGENTS.md"
        rb_path = staged_rb if staged_rb.exists() else (prod_rb if prod_rb.exists() else None)
        if rb_path is not None:
            counts = get_catalog_counts(checker.workspace_root)
            rb_txt = rb_path.read_text(encoding="utf-8", errors="replace")
            bridge_checks = (
                (VERSION, _ROOT_BRIDGE_VERSION_RE),
                (f"{counts['skills']} skill", re.compile(rf"(?<!\w)`?{counts['skills']}`?\s+`?skill`?(?!\w)")),
                (f"{counts['agents']} sub-agenti", re.compile(rf"(?<!\w)`?{counts['agents']}`?\s+`?sub-agenti`?(?!\w)")),
                (f"{counts['dashboard_nodes']} nodi", re.compile(rf"(?<!\w)`?{counts['dashboard_nodes']}`?\s+`?nodi`?(?!\w)")),
            )
            for req_tok, req_pat in bridge_checks:
                if not req_pat.search(rb_txt):
                    root_bridge_missing.append(req_tok)

    defined_seq: List[str] = []
    for line in agents_text.splitlines():
        if _MD_HEADING_RE.match(line):
            defined_seq.extend(_RULE_DEF_RE.findall(line))

    seen_rules: Set[str] = set()
    duplicate_rule_ids: List[str] = []
    for rid in defined_seq:
        if rid in seen_rules and rid not in duplicate_rule_ids:
            duplicate_rule_ids.append(rid)
        seen_rules.add(rid)

    orphan_rule_refs: Dict[str, List[str]] = {}
    for rel_k, fpath in sorted(agents_overlay.items()):
        if fpath.suffix.lower() not in {".md", ".json", ".py", ".yml", ".yaml", ".txt"}:
            continue
        txt = fpath.read_text(encoding="utf-8", errors="ignore")
        for m_ref in _RULE_REF_RE.finditer(txt):
            rid = m_ref.group(1)
            if "*" in rid or rid in ("RULE-XX", "RULE-X", "RULE-NN"):
                continue
            if rid not in seen_rules:
                locs = orphan_rule_refs.setdefault(rid, [])
                if rel_k not in locs:
                    locs.append(rel_k)

    errors: List[str] = []
    if tombstone_err:
        errors.append(tombstone_err)
    if version_mismatches:
        errors.append(f"Version parity mismatch: {version_mismatches}")
    if duplicate_rule_ids:
        errors.append(f"Duplicate AGENTS.md rule IDs: {duplicate_rule_ids}")
    if orphan_rule_refs:
        errors.append(f"Orphan [RULE-*] references: {sorted(orphan_rule_refs)}")

    root_bridge_advisory = (
        f"External parent Root Bridge pending manual sync: missing {root_bridge_missing}"
        if root_bridge_missing
        else None
    )
    if root_bridge_advisory:
        errors.append(root_bridge_advisory)
    passed = len(errors) == 0
    return {
        "passed": passed,
        "skipped": False,
        "expected_version": VERSION,
        "version_mismatches": version_mismatches,
        "tombstone_error": tombstone_err,
        "root_bridge_checked": rb_path is not None,
        "root_bridge_path": str(rb_path) if rb_path is not None else None,
        "root_bridge_synced": len(root_bridge_missing) == 0,
        "root_bridge_missing": root_bridge_missing,
        "root_bridge_advisory": root_bridge_advisory,
        "defined_rules_count": len(seen_rules),
        "duplicate_rule_ids": duplicate_rule_ids,
        "orphan_rule_refs": orphan_rule_refs,
        "details": "SSOT governance parity verified." if passed else "; ".join(errors),
    }
