"""Helper di audit Markdown, GT-14/CRIT-01, dry-run e hygiene per ecosystem_verify."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import VERSION
from _internal.rsi_convergence_engine.constants import (
    _collect_overlay_md_files,
    _scripts_dir,
    _workspace_root,
)
from _internal.rsi_convergence_engine.profiles import verify_ste100_compliance
from _internal.rsi_convergence_engine.sast_scanner import audit_markdown_doc_references


def audit_markdown_docs_impl(
    engine: Any,
    root: Path,
    canonical_profile: str,
    verified_files: List[Path],
    violations: List[str],
) -> Dict[str, Any]:
    """Audit dei documenti Markdown (STE100, link relativi e script mancanti/vietati)."""
    has_skills_hub = (root / ".agents" / "skills").is_dir() or (
        root / ".staging" / ".agents" / "skills"
    ).is_dir()
    broken_links: List[str] = []
    phantom_scripts: List[str] = []
    ste100_issues: List[str] = []
    seen_md_paths: Set[Path] = set()
    skills_verified_count = 0
    agents_verified_count = 0
    deleted_rel = engine._load_staging_deleted_set(root)

    if has_skills_hub:
        md_candidates: List[Path] = []
        md_candidates.extend(_collect_overlay_md_files(root, ".agents/skills", recursive=True))
        md_candidates.extend(_collect_overlay_md_files(root, ".agents/agents", recursive=True))
        md_candidates.extend(_collect_overlay_md_files(root, "nk_genome", recursive=True))
        for doc_md_rel in ("nk_genome/PATCH_NOTES.md", "nk_docs_and_setup/README.md"):
            rmd_cand = engine._resolve_candidate(root, doc_md_rel)
            if rmd_cand.exists() and rmd_cand.is_file():
                md_candidates.append(rmd_cand)

        for md_file in md_candidates:
            if not md_file.exists() or not md_file.is_file():
                continue
            res_md_path = md_file.resolve()
            if res_md_path in seen_md_paths:
                continue
            seen_md_paths.add(res_md_path)
            verified_files.append(res_md_path)

            raw_bytes = md_file.read_bytes()
            try:
                rel_md = md_file.relative_to(root).as_posix()
            except ValueError:
                rel_md = md_file.name
            logical_rel = (
                rel_md[len(".staging/") :] if rel_md.startswith(".staging/") else rel_md
            )
            content = raw_bytes.decode("utf-8", errors="replace")
            is_skill_doc = logical_rel.startswith(".agents/skills/")
            is_agent_doc = logical_rel.startswith(".agents/agents/")
            is_genome_doc = logical_rel.startswith("nk_genome/")
            is_patch_notes = md_file.name == "PATCH_NOTES.md"

            if is_skill_doc and md_file.name == "SKILL.md":
                skills_verified_count += 1
            if is_agent_doc and md_file.name == "agent.md":
                agents_verified_count += 1

            should_check_ste = (
                (
                    is_skill_doc
                    and (
                        "v1." in content
                        or VERSION in content
                        or "v3." in content
                        or "v4." in content
                        or "v5." in content
                        or "v6." in content
                        or "[RULE-STE100]" in content
                    )
                )
                or is_agent_doc
                or is_genome_doc
                or is_patch_notes
                or canonical_profile == "ste100_rsi"
            )
            if should_check_ste:
                ste_skill = verify_ste100_compliance(content)
                if not ste_skill["passed"]:
                    ste100_issues.extend(
                        f"{logical_rel}: {v}" for v in ste_skill["violations"][:2]
                    )

            is_active_ref_doc = (
                is_skill_doc or is_agent_doc or is_genome_doc
            ) and md_file.name not in ("PATCH_NOTES.md", "repo_map.md", "SKILL_INDEX.md")
            b_links, p_scripts = audit_markdown_doc_references(
                md_file,
                content,
                root,
                engine._resolve_candidate,
                deleted_rel=deleted_rel,
                check_scripts=is_active_ref_doc,
            )
            broken_links.extend(b_links)
            phantom_scripts.extend(p_scripts)
    else:
        seen_md_hashes: Set[str] = set()
        for md_file in _collect_overlay_md_files(root, "", recursive=True):
            res_md_path = md_file.resolve()
            verified_files.append(res_md_path)
            raw_bytes = md_file.read_bytes()
            md_sha = hashlib.sha256(raw_bytes).hexdigest()
            if md_sha in seen_md_hashes:
                continue
            seen_md_hashes.add(md_sha)
            try:
                rel_md = md_file.relative_to(root).as_posix()
            except ValueError:
                rel_md = md_file.name
            logical_rel = (
                rel_md[len(".staging/") :] if rel_md.startswith(".staging/") else rel_md
            )
            content = raw_bytes.decode("utf-8", errors="replace")
            has_nk_marker = (
                ".agents" in md_file.parts
                or md_file.name in ("SKILL.md", "PATCH_NOTES.md")
                or ".agents" in content
                or "SKILL.md" in content
                or "[RULE-STE100]" in content
            )
            if canonical_profile in ("ste100_rsi", "spec_rsi") or has_nk_marker:
                ste_md = verify_ste100_compliance(content)
                if not ste_md["passed"]:
                    ste100_issues.extend(
                        f"{logical_rel}: {v}" for v in ste_md["violations"]
                    )
            is_active_nk_doc = (
                logical_rel.startswith((".agents/", "nk_genome/"))
                and md_file.name not in ("PATCH_NOTES.md", "repo_map.md", "SKILL_INDEX.md")
            )
            b_links, p_scripts = audit_markdown_doc_references(
                md_file,
                content,
                root,
                engine._resolve_candidate,
                deleted_rel=deleted_rel,
                check_scripts=is_active_nk_doc,
            )
            broken_links.extend(b_links)
            phantom_scripts.extend(p_scripts)

    if broken_links:
        violations.append(f"Link ausiliari interrotti: {broken_links}")
    if phantom_scripts:
        violations.extend(phantom_scripts)

    return {
        "passed": len(broken_links) == 0 and len(phantom_scripts) == 0,
        "skills_verified": skills_verified_count,
        "agents_verified": agents_verified_count,
        "broken_links": broken_links,
        "phantom_scripts": phantom_scripts,
        "ste100_warnings": ste100_issues,
        "ste100_issues": [],
    }


def audit_gt14_governance_impl(
    root: Path, measured_components: List[str], violations: List[str]
) -> Tuple[List[str], Dict[str, Any]]:
    """Verifica governance GT-14 / CRIT-01 tramite NKRegistryIndexer."""
    gt14_issues: List[str] = []
    agent_overlay_mds = _collect_overlay_md_files(root, ".agents/agents", recursive=True)
    skill_overlay_mds = _collect_overlay_md_files(root, ".agents/skills", recursive=True)
    if not (agent_overlay_mds or skill_overlay_mds):
        return gt14_issues, {
            "passed": True,
            "skipped": True,
            "reason": "no_agents_or_skills_md_files",
            "agents_checked": 0,
            "skills_checked": 0,
            "issues": [],
        }
    try:
        nri_cls: Any = None
        try:
            from nk_registry_indexer import NKRegistryIndexer as _nri_cls

            if hasattr(_nri_cls, "verify_gt14_crit01_governance"):
                nri_cls = _nri_cls
        except ImportError:
            try:
                from scripts.nk_registry_indexer import NKRegistryIndexer as _nri_cls2

                if hasattr(_nri_cls2, "verify_gt14_crit01_governance"):
                    nri_cls = _nri_cls2
            except ImportError:
                nri_cls = None
        if nri_cls is None:
            for _nri_cand in (
                root / ".staging" / "scripts" / "nk_registry_indexer.py",
                root / "scripts" / "nk_registry_indexer.py",
                _scripts_dir / "nk_registry_indexer.py",
                _workspace_root / ".staging" / "scripts" / "nk_registry_indexer.py",
                _workspace_root / "scripts" / "nk_registry_indexer.py",
            ):
                if _nri_cand.is_file():
                    _nri_spec = importlib.util.spec_from_file_location(
                        "_nk_registry_indexer_gt14", str(_nri_cand)
                    )
                    if _nri_spec and _nri_spec.loader:
                        _nri_mod = importlib.util.module_from_spec(_nri_spec)
                        _nri_spec.loader.exec_module(_nri_mod)
                        _cand_cls = getattr(_nri_mod, "NKRegistryIndexer", None)
                        if _cand_cls is not None and hasattr(
                            _cand_cls, "verify_gt14_crit01_governance"
                        ):
                            nri_cls = _cand_cls
                            break
        if nri_cls is not None:
            gt14_res = nri_cls(workspace_root=root).verify_gt14_crit01_governance()
            gt14_issues = list(gt14_res.get("issues") or [])
            if not gt14_res.get("passed", False):
                if not gt14_issues:
                    gt14_issues = ["Violazione governance GT-14 / CRIT-01."]
                violations.extend(gt14_issues)
            measured_components.append("gt14_crit01_governance")
            return gt14_issues, gt14_res
        return gt14_issues, {
            "passed": True,
            "skipped": True,
            "reason": "registry_indexer_unavailable",
            "issues": [],
        }
    except Exception as exc:
        gt14_issues = [f"Errore verifica governance GT-14/CRIT-01: {exc}"]
        violations.extend(gt14_issues)
        return gt14_issues, {"passed": False, "issues": gt14_issues}


def report_is_dry_run_impl(report: Optional[Path | str | Dict[str, Any]]) -> bool:
    """Rileva se un report SAST o DAST risulta eseguito in modalita dry-run."""
    if report is None:
        return False
    payload: Any = None
    if isinstance(report, dict):
        payload = report
    elif isinstance(report, (str, Path)):
        report_path = Path(report)
        if not report_path.is_file():
            return False
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            return False
    if not isinstance(payload, dict):
        return False
    status_val = str(payload.get("status", "")).upper()
    return bool(
        payload.get("is_dry_run")
        or payload.get("dry_run")
        or "DRY_RUN" in status_val
    )
