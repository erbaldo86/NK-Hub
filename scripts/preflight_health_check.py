#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostica di manutenzione e auto-sanitizzazione per Nexus Keystone v3.5.0.
Modulo: preflight_health_check.py.
Implementa le regole [RULE-02.3.1] e [RULE-05.4], la correzione BS-01 e l'ottimizzazione OPT-10.

Funzionalita principali:
1. Verifica l'integrita di session_anchor.jsonl in nk_tracking/anchor/.
2. Unifica la scansione os.walk potando in-place .git, .venv, node_modules e .staging (OPT-10).
3. Elimina i file WAL scaduti con TTL > 60 secondi.
4. Restituisce FAIL (exit 1) se permangono errori dopo auto_fix=True (BS-01).
5. Legge dinamicamente il conteggio atteso delle skill da nk_registry_manifest.json (fallback 16).
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
from typing import Any, Dict, List, Optional, Set, Tuple

PRUNED_WALK_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".staging",
}


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
        self._cached_walk: Optional[Tuple[List[Path], List[Path], List[Path]]] = None

    def _scan_workspace_once(self) -> Tuple[List[Path], List[Path], List[Path]]:
        """Esegue un unico os.walk potato in-place per raccogliere cache e file WAL (OPT-10)."""
        if self._cached_walk is not None:
            return self._cached_walk

        cache_dirs: List[Path] = []
        wal_files: List[Path] = []
        wal_dirs: List[Path] = []

        for root, dirs, files in os.walk(self.workspace_root, topdown=True):
            root_path = Path(root)
            keep_dirs: List[str] = []
            for d in dirs:
                if d in ("__pycache__", ".pytest_cache"):
                    cache_dirs.append(root_path / d)
                elif d == ".wal":
                    wal_dirs.append(root_path / d)
                    keep_dirs.append(d)
                elif d not in PRUNED_WALK_DIRS:
                    keep_dirs.append(d)
            dirs[:] = keep_dirs

            for f in files:
                if f.endswith(".wal") or f.endswith(".wal_2pc.jsonl"):
                    wal_files.append(root_path / f)

        staging_dir = self.workspace_root / ".staging"
        if staging_dir.exists():
            for pattern in ("*.wal", "*.wal_2pc.jsonl"):
                for wf in staging_dir.glob(pattern):
                    wal_files.append(wf)

        self._cached_walk = (cache_dirs, wal_files, wal_dirs)
        return self._cached_walk

    def run_full_check(self, auto_fix: bool = True) -> Dict[str, Any]:
        """Esegue la verifica preflight completa e applica le correzioni se auto_fix=True."""
        start_time = time.time()
        self._cached_walk = None
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
            report["issues_detected"].append(
                str(staging_res.get("details", "Orphan temp dirs found"))
            )

        # 3. Pulizia cache Python e pytest tramite scansione unificata (OPT-10)
        cache_res = self._check_and_purge_caches(auto_fix)
        report["checks"]["cache_hygiene"] = cache_res

        # 4. Bonifica file WAL scaduti (TTL 60s) tramite scansione unificata (OPT-10)
        wal_res = self._check_and_purge_stale_wals(auto_fix, ttl_seconds=60.0)
        report["checks"]["wal_hygiene"] = wal_res
        if not wal_res["passed"]:
            report["issues_detected"].append(
                "Stale WAL files detected in check-only mode."
            )

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
        self._cached_walk = None
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
                details.append(
                    "Removed duplicate session_anchor.jsonl from workspace root."
                )
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
            "details": "Staging hygiene verified."
            if passed
            else f"Orphan directories: {cleaned}",
        }

    def _check_and_purge_caches(self, auto_fix: bool) -> Dict[str, Any]:
        """Rimuove le directory __pycache__ e .pytest_cache se auto_fix=True (OPT-10)."""
        purged = []
        if auto_fix:
            cache_dirs, _, _ = self._scan_workspace_once()
            for target_dir in cache_dirs:
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
        """Scansiona ed elimina i file .wal e .wal_2pc.jsonl con eta superiore al TTL (OPT-10)."""
        now = time.time()
        _, wal_candidates, stale_wal_dirs = self._scan_workspace_once()
        stale_wal_files: List[Path] = []

        for f_path in wal_candidates:
            try:
                if f_path.exists():
                    age = now - f_path.stat().st_mtime
                    if age > ttl_seconds:
                        stale_wal_files.append(f_path)
            except OSError:
                pass

        purged_count = 0
        if auto_fix:
            for wf in stale_wal_files:
                if safe_remove_file(wf):
                    purged_count += 1
            for wd in stale_wal_dirs:
                try:
                    if wd.exists() and not any(wd.iterdir()):
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
                        pruned_files.append(
                            str(old_f.relative_to(self.workspace_root))
                        )

        return {
            "passed": True,
            "max_per_target": max_per_target,
            "pruned_count": len(pruned_files),
            "pruned_files": pruned_files,
        }

    def _get_expected_skills_count(self) -> int:
        """Legge il conteggio atteso delle skill da nk_registry_manifest.json con fallback a 16."""
        candidates = (
            self.workspace_root / ".staging" / "nk_genome" / "nk_registry_manifest.json",
            self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
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
        return 16

    def _check_baseline_alignment(self) -> Dict[str, Any]:
        """Verifica che quality_baseline.json sia valido e allineato al manifesto SSOT."""
        if not self.baseline_file.exists():
            return {"passed": False, "details": "quality_baseline.json not found"}

        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return {
                    "passed": False,
                    "details": "quality_baseline.json root is not a dict",
                }

            expected_skills = self._get_expected_skills_count()
            metrics = data.get("metrics", {})
            raw_skills = metrics.get("skills_audited", 0)
            skills_audited = (
                raw_skills.get("value", 0)
                if isinstance(raw_skills, dict)
                else raw_skills
            )
            raw_crv = metrics.get("crv_macro_phases", 0)
            crv_phases = (
                raw_crv.get("value", 0) if isinstance(raw_crv, dict) else raw_crv
            )
            raw_pass = metrics.get("unit_tests_pass_pct", 100.0)
            unit_pass = (
                raw_pass.get("value", 0.0)
                if isinstance(raw_pass, dict)
                else raw_pass
            )

            passed = (
                skills_audited == expected_skills
                and crv_phases == 4
                and float(unit_pass) >= 100.0
            )
            return {
                "passed": passed,
                "version": data.get("_version", "3.0.0-STE100-Unified"),
                "skills_audited": skills_audited,
                "expected_skills": expected_skills,
                "crv_macro_phases": crv_phases,
                "details": (
                    f"Baseline perfectly aligned ({expected_skills} canonical skills, CRV 4 Macro-Phases)"
                    if passed
                    else f"Discrepancy: skills={skills_audited}/{expected_skills}, crv_phases={crv_phases}/4, pass_pct={unit_pass}"
                ),
            }
        except Exception as e:
            return {
                "passed": False,
                "details": f"Corrupted quality_baseline.json: {e}",
            }


def main() -> int:
    """Punto di ingresso CLI per il verificatore preflight di Nexus Keystone."""
    parser = argparse.ArgumentParser(
        description="Pre-Flight Health Check & Auto-Sanitizer Nexus Keystone v3.5.0"
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
