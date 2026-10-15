#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostica di manutenzione e auto-sanitizzazione per Nexus Keystone v3.0.0.
Modulo: preflight_health_check.py.
Implementa le regole [RULE-02.3.1] e [RULE-05.4] e la correzione BS-01.

Funzionalita principali:
1. Verifica l'integrita di session_anchor.jsonl in nk_tracking/anchor/.
2. Pulisce le directory temporanee orfane e le cache Python.
3. Elimina i file WAL scaduti con TTL > 60 secondi.
4. Restituisce FAIL (exit 1) se permangono errori dopo auto_fix=True (BS-01).
5. Supporta la modalita di sola ispezione tramite il flag --check-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def safe_remove_dir(dir_path: Path) -> bool:
    """Rimuove un albero di directory gestendo i permessi di sola lettura su Windows."""
    if not dir_path.exists():
        return True

    def on_error(func: Any, p: str, exc_info: Any) -> None:
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
    """Rimuove un singolo file gestendo i permessi di sola lettura su Windows."""
    if not file_path.exists():
        return True
    try:
        os.chmod(file_path, stat.S_IWRITE)
        file_path.unlink()
        return True
    except Exception:
        return not file_path.exists()


class PreflightHealthChecker:
    """Verificatore diagnostico e sanitizzatore preflight per l'Hub."""

    def __init__(self, workspace_root: Path = None):  # type: ignore[assignment]
        if workspace_root is None:
            script_dir = Path(__file__).resolve().parent
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
        self.skills_dir = self.workspace_root / ".agents" / "skills"

    def run_full_check(self, auto_fix: bool = True) -> Dict[str, Any]:
        """Esegue la verifica preflight completa e applica le correzioni se auto_fix=True."""
        start_time = time.time()
        report: Dict[str, Any] = {
            "status": "PASS",
            "auto_fix": auto_fix,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace_root": str(self.workspace_root),
            "checks": {},
            "actions_taken": [],
            "issues_detected": [],
        }

        # 1. Verifica SSOT Activity Anchor
        ssot_res = self._check_ssot_anchor(auto_fix)
        report["checks"]["ssot_anchor"] = ssot_res
        if not ssot_res["passed"]:
            report["issues_detected"].extend(
                ssot_res["details"]
                if isinstance(ssot_res["details"], list)
                else [str(ssot_res["details"])]
            )

        # 2. Verifica igiene cartelle temporanee e staging
        staging_res = self._check_staging_and_temp(auto_fix)
        report["checks"]["staging_hygiene"] = staging_res
        if not staging_res["passed"]:
            report["issues_detected"].append(str(staging_res.get("details", "Orphan temp dirs found")))

        # 3. Pulizia cache Python e pytest
        cache_res = self._check_and_purge_caches(auto_fix)
        report["checks"]["cache_hygiene"] = cache_res

        # 4. Bonifica file WAL scaduti (TTL 60s)
        wal_res = self._check_and_purge_stale_wals(auto_fix, ttl_seconds=60.0)
        report["checks"]["wal_hygiene"] = wal_res
        if not wal_res["passed"]:
            report["issues_detected"].append("Stale WAL files detected in check-only mode.")

        # 5. Finestra mobile sui report di audit
        retention_res = self._enforce_report_retention(auto_fix)
        report["checks"]["report_retention"] = retention_res

        # 6. Allineamento Quality Baseline (non auto-riparabile se corrotto: BS-01)
        baseline_res = self._check_baseline_alignment()
        report["checks"]["baseline_alignment"] = baseline_res
        if not baseline_res["passed"]:
            report["issues_detected"].append(baseline_res["details"])

        # BS-01: Se restano errori irrisolti (anche con auto_fix=True), lo stato DEVE essere FAIL
        if len(report["issues_detected"]) > 0:
            report["status"] = "FAIL"
        else:
            report["status"] = "HEALTHY_GREEN"

        report["elapsed_ms"] = round((time.time() - start_time) * 1000, 2)
        return report

    def _check_ssot_anchor(self, auto_fix: bool) -> Dict[str, Any]:
        """Verifica l'esistenza e la validita JSONL di session_anchor.jsonl."""
        passed = True
        details: List[str] = []

        if not self.anchor_file.exists():
            if auto_fix:
                self.anchor_file.parent.mkdir(parents=True, exist_ok=True)
                init_entry = {
                    "event": "PREFLIGHT_HEALTH_CHECK_INITIALIZED",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "status": "INITIALIZED",
                }
                with open(self.anchor_file, "w", encoding="utf-8") as f:
                    f.write(json.dumps(init_entry) + "\n")
                details.append("Created canonical session_anchor.jsonl.")
            else:
                passed = False
                details.append("Canonical session_anchor.jsonl is missing.")
        else:
            # Verifica righe JSONL valide e deduplicazione
            try:
                raw_lines = self.anchor_file.read_text(encoding="utf-8").splitlines()
                valid_lines: List[str] = []
                seen_lines = set()
                had_invalid = False
                for line in raw_lines:
                    stripped = line.strip()
                    if not stripped:
                        had_invalid = True
                        continue
                    try:
                        json.loads(stripped)
                        if stripped not in seen_lines:
                            seen_lines.add(stripped)
                            valid_lines.append(stripped)
                        else:
                            had_invalid = True
                    except json.JSONDecodeError:
                        had_invalid = True

                if had_invalid:
                    if auto_fix and valid_lines:
                        self.anchor_file.write_text(
                            "\n".join(valid_lines) + "\n", encoding="utf-8"
                        )
                        details.append("Sanitized session_anchor.jsonl.")
                    elif not valid_lines:
                        passed = False
                        details.append("session_anchor.jsonl contains corrupted JSONL.")
            except Exception as exc:
                passed = False
                details.append(f"Error reading session_anchor.jsonl: {exc}")

        rogue_root_anchor = self.workspace_root / "session_anchor.jsonl"
        if rogue_root_anchor.exists():
            if auto_fix:
                safe_remove_file(rogue_root_anchor)
                details.append("Removed duplicate session_anchor.jsonl from workspace root.")
            else:
                passed = False
                details.append("Rogue session_anchor.jsonl found in workspace root.")

        return {
            "passed": passed,
            "canonical_path": str(self.anchor_file),
            "details": details,
        }

    def _check_staging_and_temp(self, auto_fix: bool) -> Dict[str, Any]:
        """Pulisce le cartelle temporanee orfane."""
        orphan_dirs = [
            self.workspace_root / ".commit_ready",
            self.workspace_root / ".sandbox_tmp",
            self.workspace_root / ".temp_sandbox",
        ]

        cleaned = []
        passed = True
        for d in orphan_dirs:
            if d.exists():
                if auto_fix:
                    safe_remove_dir(d)
                    cleaned.append(str(d.name))
                else:
                    passed = False
                    cleaned.append(f"Orphan found: {d.name}")

        staging_dir = self.workspace_root / ".staging"
        if not staging_dir.exists() and auto_fix:
            staging_dir.mkdir(exist_ok=True)
            gitkeep = staging_dir / ".gitkeep"
            gitkeep.touch(exist_ok=True)

        return {
            "passed": passed,
            "cleaned_directories": cleaned,
            "details": "Staging hygiene verified." if passed else f"Orphan directories: {cleaned}",
        }

    def _check_and_purge_caches(self, auto_fix: bool) -> Dict[str, Any]:
        """Rimuove le directory __pycache__ e .pytest_cache se auto_fix=True."""
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
        return {
            "passed": True,
            "purged_count": len(purged),
            "purged_items": purged[:20],
        }

    def _check_and_purge_stale_wals(
        self, auto_fix: bool, ttl_seconds: float = 60.0
    ) -> Dict[str, Any]:
        """Scansiona ed elimina i file .wal e .wal_2pc.jsonl con eta superiore al TTL."""
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
                    stale_wal_dirs.append(Path(root) / d)

        purged_count = 0
        if auto_fix:
            for wf in stale_wal_files:
                if safe_remove_file(wf):
                    purged_count += 1
            for wd in stale_wal_dirs:
                try:
                    if not any(wd.iterdir()):
                        safe_remove_dir(wd)
                except Exception:
                    pass

        passed = True if auto_fix else (len(stale_wal_files) == 0)
        return {
            "passed": passed,
            "ttl_seconds": ttl_seconds,
            "stale_wals_detected": len(stale_wal_files),
            "purged_count": purged_count,
        }

    def _enforce_report_retention(
        self, auto_fix: bool, max_per_target: int = 3
    ) -> Dict[str, Any]:
        """Applica la finestra mobile (massimo 3 report per prefisso) in reports_and_briefs/."""
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
            prefix = re.sub(r"_\d{8}[_\d]*$", "", name)
            prefix = re.sub(
                r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                "",
                prefix,
                flags=re.IGNORECASE,
            )
            groups.setdefault(prefix, []).append(p)

        for _, p_list in groups.items():
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
            "pruned_files": pruned_files,
        }

    def _check_baseline_alignment(self) -> Dict[str, Any]:
        """Verifica che quality_baseline.json sia valido e rifletta le 16 skill e le 4 fasi CRV."""
        if not self.baseline_file.exists():
            return {"passed": False, "details": "quality_baseline.json not found"}

        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return {"passed": False, "details": "quality_baseline.json root is not a dict"}

            metrics = data.get("metrics", {})
            raw_skills = metrics.get("skills_audited", 0)
            skills_audited = (
                raw_skills.get("value", 0) if isinstance(raw_skills, dict) else raw_skills
            )
            raw_crv = metrics.get("crv_macro_phases", 0)
            crv_phases = (
                raw_crv.get("value", 0) if isinstance(raw_crv, dict) else raw_crv
            )
            raw_pass = metrics.get("unit_tests_pass_pct", 100.0)
            unit_pass = (
                raw_pass.get("value", 0.0) if isinstance(raw_pass, dict) else raw_pass
            )

            passed = (
                skills_audited == 16 and crv_phases == 4 and float(unit_pass) >= 100.0
            )
            return {
                "passed": passed,
                "version": data.get("_version", "3.0.0-STE100-Unified"),
                "skills_audited": skills_audited,
                "crv_macro_phases": crv_phases,
                "details": (
                    "Baseline perfectly aligned (16 canonical skills, CRV 4 Macro-Phases)"
                    if passed
                    else f"Discrepancy: skills={skills_audited}/16, crv_phases={crv_phases}/4, pass_pct={unit_pass}"
                ),
            }
        except Exception as e:
            return {"passed": False, "details": f"Corrupted quality_baseline.json: {e}"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-Flight Health Check & Auto-Sanitizer Nexus Keystone v3.0.0"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Esegue la verifica in sola lettura senza modificare o cancellare file",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice del workspace da controllare",
    )
    args = parser.parse_args()

    root_path = Path(args.root).resolve() if args.root else None
    checker = PreflightHealthChecker(workspace_root=root_path)
    results = checker.run_full_check(auto_fix=not args.check_only)
    print(json.dumps(results, indent=2))
    return 0 if results["status"] in ("PASS", "HEALTHY_GREEN") else 1


if __name__ == "__main__":
    sys.exit(main())
