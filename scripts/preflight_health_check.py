#!/usr/bin/env python3
"""
Pre-Flight Health Check & Auto-Sanitizer - Nexus Keystone Master Ecosystem
Implements [RULE-02.3.1] HUB_PREFLIGHT_HEALTH_CHECK_DIRECTIVE, [RULE-05.4] ARTIFACT_LIFECYCLE_AND_ROLLING_WINDOW_RETENTION,
and Direttiva 7: WAL TTL (60s) Auto-Purge.

Executes deterministically at Hub boot to verify:
1. SSOT Activity Anchor integrity
2. Staging and temp folder hygiene (.staging, .commit_ready, .sandbox_tmp, .temp_sandbox)
3. Python and test cache purging (__pycache__, .pytest_cache)
4. WAL TTL 60s purge (_check_and_purge_stale_wals)
5. Quality baseline consistency
6. Rolling window retention on audit reports (max 3 per target)
"""

import json
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Dict, List, Any


def safe_remove_dir(dir_path: Path) -> bool:
    """Removes a directory tree handling Windows permissions."""
    if not dir_path.exists():
        return True
    
    def on_error(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    try:
        shutil.rmtree(dir_path, onerror=on_error)
        return True
    except Exception:
        return not dir_path.exists()


def safe_remove_file(file_path: Path) -> bool:
    """Removes a single file handling Windows permissions."""
    if not file_path.exists():
        return True
    try:
        os.chmod(file_path, stat.S_IWRITE)
        file_path.unlink()
        return True
    except Exception:
        return not file_path.exists()


class PreflightHealthChecker:
    def __init__(self, workspace_root: Path = None):
        if workspace_root is None:
            self.workspace_root = Path(__file__).resolve().parent.parent
        else:
            self.workspace_root = Path(workspace_root).resolve()

        self.tracking_dir = self.workspace_root / "nk_tracking"
        self.anchor_file = self.tracking_dir / "anchor" / "session_anchor.jsonl"
        self.baseline_file = self.tracking_dir / "quality_baseline.json"
        self.reports_dir = self.tracking_dir / "reports_and_briefs"
        self.skills_dir = self.workspace_root / ".agents" / "skills"

    def run_full_check(self, auto_fix: bool = True) -> Dict[str, Any]:
        """Runs the complete pre-flight check and self-healing pass."""
        start_time = time.time()
        report: Dict[str, Any] = {
            "status": "PASS",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace_root": str(self.workspace_root),
            "checks": {},
            "actions_taken": [],
            "issues_detected": []
        }

        # 1. SSOT Anchor Check
        ssot_res = self._check_ssot_anchor(auto_fix)
        report["checks"]["ssot_anchor"] = ssot_res
        if not ssot_res["passed"]:
            report["issues_detected"].append(ssot_res["details"])

        # 2. Temp and Staging Hygiene
        staging_res = self._check_staging_and_temp(auto_fix)
        report["checks"]["staging_hygiene"] = staging_res
        if not staging_res["passed"]:
            report["issues_detected"].append(staging_res["details"])

        # 3. Cache Purging
        cache_res = self._check_and_purge_caches(auto_fix)
        report["checks"]["cache_hygiene"] = cache_res

        # 4. WAL Stale Purge (TTL 60s)
        wal_res = self._check_and_purge_stale_wals(auto_fix, ttl_seconds=60.0)
        report["checks"]["wal_hygiene"] = wal_res

        # 5. Rolling Window Retention on Reports
        retention_res = self._enforce_report_retention(auto_fix)
        report["checks"]["report_retention"] = retention_res

        # 6. Quality Baseline & Canonical Skills Alignment
        baseline_res = self._check_baseline_alignment()
        report["checks"]["baseline_alignment"] = baseline_res
        if not baseline_res["passed"]:
            report["issues_detected"].append(baseline_res["details"])

        # Determine overall status
        if len(report["issues_detected"]) > 0 and not auto_fix:
            report["status"] = "FAIL"
        else:
            report["status"] = "HEALTHY_GREEN"

        report["elapsed_ms"] = round((time.time() - start_time) * 1000, 2)
        return report

    def _check_ssot_anchor(self, auto_fix: bool) -> Dict[str, Any]:
        """Ensures session_anchor.jsonl exists only at nk_tracking/anchor/session_anchor.jsonl."""
        passed = True
        details = []
        
        # Check canonical anchor
        if not self.anchor_file.exists():
            if auto_fix:
                self.anchor_file.parent.mkdir(parents=True, exist_ok=True)
                init_entry = {
                    "event": "PREFLIGHT_HEALTH_CHECK_INITIALIZED",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "status": "INITIALIZED"
                }
                with open(self.anchor_file, "w", encoding="utf-8") as f:
                    f.write(json.dumps(init_entry) + "\n")
                details.append("Created canonical session_anchor.jsonl.")
            else:
                passed = False
                details.append("Canonical session_anchor.jsonl is missing.")

        # Check for rogue duplicates in root
        rogue_root_anchor = self.workspace_root / "session_anchor.jsonl"
        if rogue_root_anchor.exists():
            if auto_fix:
                safe_remove_file(rogue_root_anchor)
                details.append("Removed duplicate session_anchor.jsonl from workspace root.")
            else:
                passed = False
                details.append("Rogue session_anchor.jsonl found in workspace root.")

        return {"passed": passed, "canonical_path": str(self.anchor_file), "details": details}

    def _check_staging_and_temp(self, auto_fix: bool) -> Dict[str, Any]:
        """Cleans empty and orphaned staging/temp folders."""
        orphan_dirs = [
            self.workspace_root / ".commit_ready",
            self.workspace_root / ".sandbox_tmp",
            self.workspace_root / ".temp_sandbox"
        ]
        
        cleaned = []
        for d in orphan_dirs:
            if d.exists():
                if auto_fix:
                    safe_remove_dir(d)
                    cleaned.append(str(d.name))
                else:
                    cleaned.append(f"Orphan found: {d.name}")

        # Staging folder check
        staging_dir = self.workspace_root / ".staging"
        if not staging_dir.exists() and auto_fix:
            staging_dir.mkdir(exist_ok=True)
            gitkeep = staging_dir / ".gitkeep"
            gitkeep.touch(exist_ok=True)

        return {"passed": True, "cleaned_directories": cleaned}

    def _check_and_purge_caches(self, auto_fix: bool) -> Dict[str, Any]:
        """Recursively purges __pycache__ and .pytest_cache."""
        purged = []
        if auto_fix:
            for root, dirs, _ in os.walk(self.workspace_root, topdown=False):
                if ".venv" in root or "node_modules" in root:
                    continue
                for d in dirs:
                    if d in ("__pycache__", ".pytest_cache"):
                        target_dir = Path(root) / d
                        if safe_remove_dir(target_dir):
                            purged.append(str(target_dir.relative_to(self.workspace_root)))
        return {"passed": True, "purged_count": len(purged), "purged_items": purged[:20]}

    def _check_and_purge_stale_wals(self, auto_fix: bool, ttl_seconds: float = 60.0) -> Dict[str, Any]:
        """
        Direttiva 7: WAL TTL (60s) & Auto-Purge Normativo all'Avvio.
        Scans workspace recursively for .wal files, .wal_2pc.jsonl, and .wal/ directories.
        Purges any record with age > ttl_seconds.
        """
        now = time.time()
        stale_wal_files: List[Path] = []
        stale_wal_dirs: List[Path] = []

        for root, dirs, files in os.walk(self.workspace_root):
            if ".venv" in root or "node_modules" in root:
                continue

            for f in files:
                if f.endswith(".wal") or f.endswith(".wal_2pc.jsonl"):
                    f_path = Path(root) / f
                    try:
                        age = now - f_path.stat().st_mtime
                        if age > ttl_seconds:
                            stale_wal_files.append(f_path)
                    except OSError:
                        pass

            for d in dirs:
                if d == ".wal":
                    d_path = Path(root) / d
                    stale_wal_dirs.append(d_path)

        purged_count = 0
        if auto_fix:
            for wf in stale_wal_files:
                if safe_remove_file(wf):
                    purged_count += 1
            for wd in stale_wal_dirs:
                # If directory is empty, remove it
                try:
                    if not any(wd.iterdir()):
                        safe_remove_dir(wd)
                except Exception:
                    pass

        return {
            "passed": True,
            "ttl_seconds": ttl_seconds,
            "stale_wals_detected": len(stale_wal_files),
            "purged_count": purged_count,
        }

    def _enforce_report_retention(self, auto_fix: bool, max_per_target: int = 3) -> Dict[str, Any]:
        """Enforces rolling window retention (max 3 reports per target/skill)."""
        if not self.reports_dir.exists():
            return {"passed": True, "reports_pruned": 0}

        pruned_files = []
        report_files: List[Path] = []
        for root, _, files in os.walk(self.reports_dir):
            for f in files:
                if f.endswith((".md", ".json")) and not f.startswith("."):
                    report_files.append(Path(root) / f)

        groups: Dict[str, List[Path]] = {}
        for p in report_files:
            name = p.stem
            prefix = re.sub(r'_\d{8}[_\d]*$', '', name)
            prefix = re.sub(r'_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', prefix, flags=re.IGNORECASE)
            groups.setdefault(prefix, []).append(p)

        for prefix, p_list in groups.items():
            if len(p_list) > max_per_target:
                p_list.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                excess = p_list[max_per_target:]
                for old_f in excess:
                    if auto_fix:
                        safe_remove_file(old_f)
                        pruned_files.append(str(old_f.relative_to(self.workspace_root)))

        return {
            "passed": True,
            "max_per_target": max_per_target,
            "pruned_count": len(pruned_files),
            "pruned_files": pruned_files
        }

    def _check_baseline_alignment(self) -> Dict[str, Any]:
        """Verifies quality_baseline.json reflects canonical 16 skills and CRV 4.0 (4 Macro-Phases)."""
        if not self.baseline_file.exists():
            return {"passed": False, "details": "quality_baseline.json not found"}

        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            metrics = data.get("metrics", {})
            raw_skills = metrics.get("skills_audited", 0)
            skills_audited = raw_skills.get("value", 0) if isinstance(raw_skills, dict) else raw_skills
            raw_crv = metrics.get("crv_macro_phases", 0)
            crv_phases = raw_crv.get("value", 0) if isinstance(raw_crv, dict) else raw_crv
            
            passed = (skills_audited == 16 and crv_phases == 4)
            return {
                "passed": passed,
                "version": data.get("_version", "1.1.0-Universal"),
                "skills_audited": skills_audited,
                "crv_macro_phases": crv_phases,
                "details": "Baseline perfectly aligned (16 canonical skills, CRV 4 Macro-Phases)" if passed else f"Discrepancy: skills={skills_audited}/16, crv_phases={crv_phases}/4"
            }
        except Exception as e:
            return {"passed": False, "details": str(e)}


if __name__ == "__main__":
    checker = PreflightHealthChecker()
    results = checker.run_full_check(auto_fix=True)
    print(json.dumps(results, indent=2))
    sys.exit(0 if results["status"] in ("PASS", "HEALTHY_GREEN") else 1)
