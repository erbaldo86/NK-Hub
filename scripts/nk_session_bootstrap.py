#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Bootstrap Gate Fast-Stat per Nexus Keystone v3.0.0.
Modulo: nk_session_bootstrap.py.
Implementa le regole [RULE-00.4] e [RULE-PROJECT-ISOLATION].

Funzionalita principali:
1. Verifica invarianti Fast-Stat in meno di 50 millisecondi.
2. Controlla l'igiene della radice (src/, src_app/, app/, file .py estranei) anche su cache hit.
3. Elimina i file .wal e .wal_2pc.jsonl scaduti (TTL > 60 secondi).
4. Attiva il profilo modello argon per la sessione corrente.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

_scripts_dir = Path(__file__).resolve().parent
if _scripts_dir.parent.name == ".staging":
    _workspace_root = _scripts_dir.parent.parent
else:
    _workspace_root = _scripts_dir.parent

if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

try:
    from scripts.platform_runner import reconfigure_streams
except ImportError:
    try:
        from platform_runner import reconfigure_streams
    except ImportError:
        def reconfigure_streams() -> None:
            pass

try:
    from nk_context_sentry import NKContextSentry
except ImportError:
    try:
        from scripts.nk_context_sentry import NKContextSentry
    except ImportError:
        NKContextSentry = None  # type: ignore[assignment]


class NKSessionBootstrap:
    """Cancello deterministico di avvio sessione con verifica Fast-Stat."""

    def __init__(self, workspace_root: Optional[Path] = None):
        reconfigure_streams()
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )
        self.temp_bootstrap_dir = Path(tempfile.gettempdir()) / "nk_bootstrap"
        self.state_file = self.temp_bootstrap_dir / "session_bootstrap_state.json"
        self.temp_bootstrap_dir.mkdir(parents=True, exist_ok=True)
        self.model_profile = os.environ.get("NK_MODEL_PROFILE", "argon")
        if "PYTEST_CURRENT_TEST" not in os.environ:
            os.environ.setdefault("NK_MODEL_PROFILE", "argon")

    def run_bootstrap(self, fast_stat: bool = True) -> Dict[str, Any]:
        """Esegue la verifica di avvio e restituisce il rapporto diagnostico."""
        start_time = time.perf_counter()
        if "PYTEST_CURRENT_TEST" not in os.environ:
            os.environ.setdefault("NK_MODEL_PROFILE", "argon")

        report: Dict[str, Any] = {
            "status": "PASS",
            "session_id": f"NK-BOOT-{int(time.time())}",
            "model_profile": self.model_profile,
            "fast_stat": fast_stat,
            "checks": {},
            "issues": [],
        }

        # 1. Controlla sempre l'igiene della radice anche su cache hit (< 50 ms)
        isolation_check = self._check_root_hygiene()
        report["checks"]["project_isolation"] = isolation_check
        if not isolation_check["passed"]:
            report["status"] = "FAIL"
            report["issues"].append(isolation_check["details"])

        # 2. Verifica la cache Fast-Stat se l'isolamento radice e valido
        if fast_stat and isolation_check["passed"] and self._can_fast_pass():
            context_check = self._verify_context_sentry()
            report["checks"]["fast_stat"] = {
                "status": "PASS",
                "details": "Fast-stat invariant verified. TTL valid (<15m).",
            }
            report["checks"]["context_sentry"] = context_check
            if context_check.get("warning"):
                report["issues"].append(context_check["warning"])
            duration_ms = (time.perf_counter() - start_time) * 1000
            report["duration_ms"] = round(duration_ms, 2)
            self._save_state(report)
            return report

        # 3. Bonifica i file WAL orfani con TTL > 60 secondi
        wal_purge_check = self._purge_stale_wal_files(ttl_seconds=60.0)
        report["checks"]["wal_hygiene"] = wal_purge_check

        # 4. Verifica la coerenza di quality_baseline.json
        baseline_check = self._verify_baseline()
        report["checks"]["quality_baseline"] = baseline_check
        if not baseline_check["passed"]:
            report["status"] = "FAIL"
            report["issues"].append(baseline_check["details"])

        # 5. Esegue il controllo non bloccante del Context Sentry
        context_check = self._verify_context_sentry()
        report["checks"]["context_sentry"] = context_check
        if context_check.get("warning"):
            report["issues"].append(context_check["warning"])

        duration_ms = (time.perf_counter() - start_time) * 1000
        report["duration_ms"] = round(duration_ms, 2)
        self._save_state(report)
        return report

    def _can_fast_pass(self) -> bool:
        """Verifica se lo stato in cache e valido e non scaduto."""
        if not self.state_file.exists():
            return False
        try:
            cached = json.loads(self.state_file.read_text(encoding="utf-8"))
            cached_time = cached.get("timestamp_epoch", 0)
            if time.time() - cached_time > 900:
                return False

            agents_md = self.workspace_root / ".agents" / "AGENTS.md"
            if agents_md.exists() and agents_md.stat().st_mtime > cached_time:
                return False

            return cached.get("status") == "PASS"
        except Exception:
            return False

    def _check_root_hygiene(self) -> Dict[str, Any]:
        """Verifica l'assenza di cartelle applicative o file Python estranei nella radice."""
        forbidden_dirs = ["src_app", "app", "src"]
        detected = []
        for fdir in forbidden_dirs:
            target = self.workspace_root / fdir
            if target.exists() and (any(target.rglob("*.py")) or any(target.iterdir())):
                detected.append(fdir)

        for root_py in self.workspace_root.glob("*.py"):
            detected.append(root_py.name)

        passed = len(detected) == 0
        return {
            "passed": passed,
            "details": "Workspace root isolated."
            if passed
            else f"Pollution detected in: {detected}",
        }

    def _verify_project_isolation(self) -> Dict[str, Any]:
        """Alias compatibile per il controllo di isolamento della radice."""
        return self._check_root_hygiene()

    def _purge_stale_wal_files(self, ttl_seconds: float = 60.0) -> Dict[str, Any]:
        """Elimina i file .wal_2pc.jsonl e .wal piu vecchi della soglia TTL."""
        purged = 0
        now = time.time()
        candidate_dirs = [
            self.workspace_root,
            self.workspace_root / ".staging",
            self.workspace_root / ".wal",
            self.workspace_root / "nk_tracking",
        ]
        for cdir in candidate_dirs:
            if cdir.exists():
                try:
                    for pattern in ("*.wal_2pc.jsonl", "*.wal"):
                        for wal_file in cdir.glob(pattern):
                            if now - wal_file.stat().st_mtime > ttl_seconds:
                                wal_file.unlink(missing_ok=True)
                                purged += 1
                except Exception:
                    pass
        return {"passed": True, "stale_wals_purged": purged}

    def _verify_baseline(self) -> Dict[str, Any]:
        """Verifica che quality_baseline.json esista e abbia pass rate pari a 100%."""
        staging_baseline = (
            self.workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json"
        )
        baseline_path = (
            staging_baseline
            if staging_baseline.exists()
            else self.workspace_root / "nk_tracking" / "quality_baseline.json"
        )
        if not baseline_path.exists():
            return {"passed": False, "details": "quality_baseline.json missing."}
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8"))
            unit_pass = (
                data.get("metrics", {}).get("unit_tests_pass_pct", {}).get("value", 0)
            )
            passed = unit_pass >= 100.0
            return {
                "passed": passed,
                "unit_pass_pct": unit_pass,
                "details": f"Baseline pass rate: {unit_pass}%",
            }
        except Exception as exc:
            return {"passed": False, "details": str(exc)}

    def _verify_context_sentry(self) -> Dict[str, Any]:
        """Esegue il controllo rapido sul transcript della conversazione attiva."""
        if NKContextSentry is None:
            return {"passed": True, "details": "NKContextSentry module unavailable, skipped."}

        brain_dir = (
            Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "brain"
        )
        transcript_file: Optional[Path] = None
        if brain_dir.exists():
            candidates = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))
            if candidates:
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                transcript_file = candidates[0]

        if not transcript_file or not transcript_file.exists():
            return {
                "passed": True,
                "status": "GREEN",
                "details": "No active transcript found. Fresh session assumed.",
            }

        try:
            t_stat = transcript_file.stat()
            t_mtime = t_stat.st_mtime
            t_size = t_stat.st_size

            if self.state_file.exists():
                try:
                    cached = json.loads(self.state_file.read_text(encoding="utf-8"))
                    if (
                        cached.get("transcript_mtime") == t_mtime
                        and cached.get("transcript_size") == t_size
                        and cached.get("active_profile") == self.model_profile
                    ):
                        cached_cs = cached.get("checks", {}).get("context_sentry")
                        if isinstance(cached_cs, dict) and cached_cs.get("passed"):
                            return cached_cs
                except Exception:
                    pass

            sentry = NKContextSentry(
                workspace_root=self.workspace_root, profile=self.model_profile
            )
            res = sentry.analyze_transcript(transcript_file)
            status = res.get("status", "GREEN")
            warning = None
            if status == "YELLOW":
                warning = (
                    f"Context warning: session at {res.get('step_count', 0)} steps "
                    f"(~{res.get('estimated_tokens', 0):,} tokens)."
                )
            elif status == "RED":
                warning = (
                    f"CRITICAL context saturation: session at {res.get('step_count', 0)} steps. "
                    "Execute /compact or nk_session_handoff.py."
                )

            return {
                "passed": True,
                "status": status,
                "step_count": res.get("step_count", 0),
                "estimated_tokens": res.get("estimated_tokens", 0),
                "transcript_mtime": t_mtime,
                "transcript_size": t_size,
                "active_profile": self.model_profile,
                "warning": warning,
                "details": f"Context status {status} ({res.get('step_count', 0)} steps).",
            }
        except Exception as exc:
            return {"passed": True, "details": f"Context Sentry check error: {exc}"}

    def _save_state(self, report: Dict[str, Any]) -> None:
        """Salva lo stato del bootstrap nella directory temporanea locale."""
        try:
            report_to_save = dict(report)
            report_to_save["timestamp_epoch"] = time.time()
            report_to_save["active_profile"] = self.model_profile
            cs_info = report.get("checks", {}).get("context_sentry", {})
            if isinstance(cs_info, dict):
                if "transcript_mtime" in cs_info:
                    report_to_save["transcript_mtime"] = cs_info["transcript_mtime"]
                if "transcript_size" in cs_info:
                    report_to_save["transcript_size"] = cs_info["transcript_size"]
            self.state_file.write_text(
                json.dumps(report_to_save, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def main() -> int:
    reconfigure_streams()
    os.environ.setdefault("NK_MODEL_PROFILE", "argon")
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Fast-Stat Session Bootstrap Gate"
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Ignora la cache Fast-Stat ed esegue la scansione completa",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )

    args = parser.parse_args()
    bootstrap = NKSessionBootstrap()
    res = bootstrap.run_bootstrap(fast_stat=not args.force_full)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        status_symbol = "🟢" if res["status"] == "PASS" else "🔴"
        print(
            f"{status_symbol} [NK-BOOTSTRAP] Status: {res['status']} | Duration: {res.get('duration_ms', 0)} ms"
        )
        for check_name, check_data in res.get("checks", {}).items():
            print(f"  - {check_name}: {check_data.get('details', check_data)}")
        for issue in res.get("issues", []):
            print(f"  ⚠️ [ALERT] {issue}")

    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
