# -*- coding: utf-8 -*-
"""Classe PreflightHealthChecker per preflight_health_check."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.preflight_health_check.cleanup_and_wal import (
    DEFAULT_VERSION,
    canonical_wal_directories,
    check_and_purge_stale_wals,
    check_ssot_anchor,
    check_staging_and_temp,
    is_committed_wal,
    is_wal_filename,
    safe_remove_file,
    scan_workspace_once,
)
from _internal.preflight_health_check.ssot_governance import (
    check_baseline_alignment,
    check_ssot_governance,
    collect_agents_overlay,
    get_expected_skills_count,
    normalize_tombstone_rel,
    resolve_overlay_file,
)


class PreflightHealthChecker:
    """Verificatore diagnostico e sanitizzatore preflight per l'Hub."""

    def __init__(self, workspace_root: Path = None):  # type: ignore[assignment]
        if workspace_root is None:
            script_dir = Path(__file__).resolve().parent.parent.parent
            if script_dir.parent.name == ".staging":
                self.workspace_root = script_dir.parent.parent
            else:
                self.workspace_root = script_dir.parent
        else:
            self.workspace_root = Path(workspace_root).resolve()

        self.tracking_dir = self.workspace_root / "nk_tracking"
        self.anchor_file = self.tracking_dir / "anchor" / "session_anchor.jsonl"
        self.baseline_file = self.tracking_dir / "quality_baseline.json"
        self.reports_dir = self.tracking_dir / "reports_and_briefs"
        self.manifests_dir = self.tracking_dir / "manifests"
        self.stashes_dir = self.tracking_dir / "handoff" / "stashes"
        self.skills_dir = self.workspace_root / ".agents" / "skills"
        self._cached_walk: Optional[Tuple[List[Path], List[Path], List[Path]]] = None
        self._last_tombstone_error: Optional[str] = None
        self._tombstone_errors: List[str] = []

    def _canonical_wal_directories(self) -> Tuple[Path, ...]:
        return canonical_wal_directories(self.workspace_root)

    @staticmethod
    def _is_wal_filename(fname: str) -> bool:
        return is_wal_filename(fname)

    def _scan_workspace_once(self) -> Tuple[List[Path], List[Path], List[Path]]:
        return scan_workspace_once(self)

    def run_full_check(self, auto_fix: bool = True) -> Dict[str, Any]:
        """Esegue la verifica preflight completa applicando auto_fix se True."""
        start_time = time.time()
        self._cached_walk = None
        try:
            if self.tracking_dir.exists():
                (self.workspace_root / "nk_tracking" / "manifests").mkdir(
                    parents=True, exist_ok=True
                )
            if auto_fix or self.anchor_file.exists():
                (self.workspace_root / ".staging").mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        report: Dict[str, Any] = {
            "status": "PASS",
            "version": DEFAULT_VERSION,
            "auto_fix": auto_fix,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace_root": str(self.workspace_root),
            "checks": {},
            "actions_taken": [],
            "issues_detected": [],
        }

        ssot_res = self._check_ssot_anchor(auto_fix)
        report["checks"]["ssot_anchor"] = ssot_res
        if not ssot_res["passed"]:
            report["issues_detected"].extend(
                ssot_res["details"]
                if isinstance(ssot_res["details"], list)
                else [str(ssot_res["details"])]
            )

        staging_res = self._check_staging_and_temp(auto_fix)
        report["checks"]["staging_hygiene"] = staging_res
        if not staging_res["passed"]:
            report["issues_detected"].append(
                str(staging_res.get("details", "Orphan temp dirs or patch stashes found"))
            )

        wal_res = self._check_and_purge_stale_wals(auto_fix, ttl_seconds=60.0)
        report["checks"]["wal_hygiene"] = wal_res
        if not wal_res["passed"]:
            report["issues_detected"].append(
                "Stale WAL files detected in check-only mode."
            )

        retention_res = (
            self._enforce_report_retention(auto_fix)
            if auto_fix
            else self._check_report_retention(auto_fix)
        )
        report["checks"]["report_retention"] = retention_res
        if not retention_res["passed"]:
            report["issues_detected"].append(
                "Temporary prompt files detected in reports_and_briefs/."
            )

        baseline_res = self._check_baseline_alignment()
        report["checks"]["baseline_alignment"] = baseline_res
        if not baseline_res["passed"]:
            report["issues_detected"].append(baseline_res["details"])

        gov_res = self._check_ssot_governance()
        report["checks"]["ssot_governance"] = gov_res
        if not gov_res["passed"]:
            report["issues_detected"].append(
                str(gov_res.get("details", "SSOT governance parity discrepancy."))
            )

        report["status"] = "FAIL" if report["issues_detected"] else "HEALTHY_GREEN"
        report["elapsed_ms"] = round((time.time() - start_time) * 1000, 2)
        self._cached_walk = None
        return report

    def _check_ssot_anchor(self, auto_fix: bool) -> Dict[str, Any]:
        return check_ssot_anchor(self, auto_fix)

    def _check_staging_and_temp(self, auto_fix: bool) -> Dict[str, Any]:
        return check_staging_and_temp(self, auto_fix)

    @staticmethod
    def _is_committed_wal(wal_file: Path) -> bool:
        return is_committed_wal(wal_file)

    def _check_and_purge_stale_wals(
        self, auto_fix: bool, ttl_seconds: float = 60.0
    ) -> Dict[str, Any]:
        return check_and_purge_stale_wals(self, auto_fix, ttl_seconds=ttl_seconds)

    def _enforce_report_retention(
        self, auto_fix: bool, max_per_target: int = 3
    ) -> Dict[str, Any]:
        return self._check_report_retention(auto_fix=auto_fix, max_per_target=max_per_target)

    def _collect_report_files_shallow(self) -> List[Path]:
        """Raccoglie i file .md e .json in reports_and_briefs/."""
        out: List[Path] = []
        if not self.reports_dir.exists() or not self.reports_dir.is_dir():
            return out
        try:
            with os.scandir(self.reports_dir) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False):
                        if entry.name.endswith((".md", ".json")) and not entry.name.startswith("."):
                            out.append(Path(entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        try:
                            with os.scandir(entry.path) as sub_it:
                                for sub_e in sub_it:
                                    if sub_e.is_file(follow_symlinks=False) and sub_e.name.endswith((".md", ".json")) and not sub_e.name.startswith("."):
                                        out.append(Path(sub_e.path))
                        except OSError:
                            continue
        except OSError:
            pass
        return out

    def _collect_tracking_bak_files_shallow(self) -> List[Path]:
        """Individua i file .bak* nelle sottocartelle note di nk_tracking."""
        bak_files: List[Path] = []
        if not self.tracking_dir.exists() or not self.tracking_dir.is_dir():
            return bak_files
        for tdir in (self.tracking_dir, self.tracking_dir / "anchor", self.tracking_dir / "handoff", self.tracking_dir / "manifests", self.reports_dir):
            if not tdir.exists() or not tdir.is_dir():
                continue
            try:
                with os.scandir(tdir) as it:
                    for entry in it:
                        if entry.is_file(follow_symlinks=False) and ".bak" in entry.name:
                            bak_files.append(Path(entry.path))
            except OSError:
                continue
        return bak_files

    def _check_report_retention(
        self, auto_fix: bool, max_per_target: int = 3
    ) -> Dict[str, Any]:
        """Applica la finestra mobile per prefisso ed elimina i prompt temporanei."""
        if not self.reports_dir.exists():
            return {"passed": True, "reports_pruned": 0, "pruned_count": 0, "pruned_files": []}
        pruned_files: List[str] = []
        groups: Dict[str, List[Path]] = {}
        passed = True
        for p in self._collect_report_files_shallow():
            if p.name.startswith(("FORENSIC_INSPECTOR_", "PROMPT_A_", "PROMPT_B_")):
                if auto_fix:
                    if safe_remove_file(p):
                        pruned_files.append(str(p.relative_to(self.workspace_root)))
                else:
                    passed = False
                continue
            name = p.stem
            if re.match(r"^IB-\d{8}-[0-9a-zA-Z_-]+$", name, flags=re.IGNORECASE):
                prefix = "IB_Brief"
            else:
                matched = next((cp for cp in ("TAS_Report", "DAST_Report", "RCA_Report") if name.startswith(cp)), None)
                if matched is not None:
                    prefix = matched
                else:
                    prefix = re.sub(r"_\d{8}[_\d]*$", "", name)
                    prefix = re.sub(r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", "", prefix, flags=re.IGNORECASE)
            groups.setdefault(prefix, []).append(p)
        for p_list in groups.values():
            if len(p_list) > max_per_target:
                p_list.sort(key=lambda x: (x.stat().st_mtime, x.name), reverse=True)
                for old_f in p_list[max_per_target:]:
                    if auto_fix and safe_remove_file(old_f):
                        pruned_files.append(str(old_f.relative_to(self.workspace_root)))
        if auto_fix and self.tracking_dir.exists():
            for bak_f in self._collect_tracking_bak_files_shallow():
                if safe_remove_file(bak_f):
                    pruned_files.append(str(bak_f.relative_to(self.workspace_root)))
        return {"passed": passed, "max_per_target": max_per_target, "pruned_count": len(pruned_files), "pruned_files": pruned_files}

    def _get_expected_skills_count(self) -> int:
        return get_expected_skills_count(self.workspace_root)

    def _check_baseline_alignment(self) -> Dict[str, Any]:
        return check_baseline_alignment(self)

    @staticmethod
    def _normalize_tombstone_rel(raw_item: str) -> str:
        return normalize_tombstone_rel(raw_item)

    def _collect_agents_overlay(self) -> Dict[str, Path]:
        return collect_agents_overlay(self)

    def _resolve_overlay_file(self, rel_path: str) -> Optional[Path]:
        return resolve_overlay_file(self.workspace_root, rel_path)

    def _check_ssot_governance(self) -> Dict[str, Any]:
        return check_ssot_governance(self)
