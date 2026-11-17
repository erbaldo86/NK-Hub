#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orchestratore NKSessionBootstrap ed helper pubblici di modulo."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import constants as _consts


def _run_bootstrap_impl(
    self_obj: Any, fast_stat: bool = True, prompt: Optional[str] = None
) -> Dict[str, Any]:
    """Esegue la verifica di avvio controllando prima Fast-Stat e preservando immutabilita cache."""
    start_time = time.perf_counter()
    self_obj._cached_root_mtime = None
    self_obj._cached_staging_mtime = None
    self_obj._wal_dir_exists = None
    self_obj._cached_baseline_stat = None
    self_obj._resolved_gate_tuple = None
    if prompt is not None:
        self_obj.explicit_prompt = prompt
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    cached_state = self_obj._load_fast_cache() if fast_stat else None
    can_fast = bool(fast_stat and self_obj._can_fast_pass(cached=cached_state))

    onboarding_bypass, _gate_mode = self_obj._resolve_onboarding_and_gate_mode(
        cached=cached_state if can_fast else None
    )
    staging_dirty = self_obj._is_staging_dirty(
        cached=cached_state if can_fast else None
    )
    is_standalone = (
        self_obj.explicit_transcript_path is None and not bool(self_obj.conversation_id)
    )

    report: Dict[str, Any] = {
        "status": "PASS",
        "session_id": f"NK-BOOT-{int(time.time())}",
        "conversation_id": self_obj.conversation_id,
        "context_mode": "CLI_STANDALONE" if is_standalone else "ACTIVE_SESSION",
        "model_profile": self_obj.model_profile,
        "pythonutf8": os.environ.get("PYTHONUTF8", "1"),
        "fast_stat": fast_stat,
        "onboarding_bypass": onboarding_bypass,
        "staging_dirty_warning": staging_dirty,
        "checks": {},
        "issues": [],
    }

    # 1. Verifica immediata Fast-Pass (< 15 ms) riusando la copia immutabile cached_state
    if can_fast:
        isolation_check = self_obj._check_root_hygiene(
            use_fast_cache=True, cached=cached_state
        )
        isolation_check["staging_dirty_warning"] = staging_dirty
        report["checks"]["project_isolation"] = isolation_check
        wal_check: Dict[str, Any] = {
            "passed": True,
            "stale_wals_purged": 0,
            "corrupted_wals_quarantined": 0,
            "status": "PASS",
        }
        if self_obj._has_actionable_wal_entries():
            wal_check = self_obj._purge_stale_wal_files(ttl_seconds=60.0)
        baseline_check = self_obj._verify_baseline(cached=cached_state)
        report["checks"]["quality_baseline"] = baseline_check
        if isolation_check["passed"] and baseline_check["passed"]:
            context_check = self_obj._verify_context_sentry(
                use_fast_cache=True, cached=cached_state
            )
            report["checks"]["fast_stat"] = {
                "status": "PASS",
                "details": "Fast-stat invariant verified. TTL valid (<900s).",
            }
            report["checks"]["wal_hygiene"] = wal_check
            report["checks"]["context_sentry"] = context_check
            report["checks"]["meta_prompt_gate"] = (
                self_obj._verify_meta_prompt_gate_state(cached=cached_state)
            )
            if context_check.get("warning"):
                report["issues"].append(context_check["warning"])
            duration_ms = (time.perf_counter() - start_time) * 1000
            report["duration_ms"] = round(duration_ms, 2)
            report["execution_time_ms"] = round(duration_ms, 2)
            prev_t_size = (
                int(cached_state.get("last_transcript_size", 0))
                if cached_state
                else 0
            )
            prev_t_steps = (
                int(cached_state.get("last_step_count", 0))
                if cached_state
                else 0
            )
            prev_prompt = (
                cached_state.get(
                    "latest_user_prompt",
                    cached_state.get("cached_latest_user_prompt"),
                )
                if cached_state
                else None
            )
            cur_t_size = int(context_check.get("transcript_size", 0))
            cur_t_steps = int(context_check.get("step_count", 0))
            transcript_grew = (
                cur_t_size != prev_t_size
                or cur_t_steps != prev_t_steps
                or self_obj._last_detected_user_prompt != prev_prompt
            )
            if (
                wal_check.get("stale_wals_purged", 0) > 0
                or wal_check.get("corrupted_wals_quarantined", 0) > 0
                or transcript_grew
            ):
                self_obj._last_root_mtime = self_obj._get_root_mtime()
                self_obj._save_state(report)
            else:
                ws_key = str(self_obj.workspace_root)
                lock = _consts._get_facade_attr("_BOOTSTRAP_LOCK", _consts._BOOTSTRAP_LOCK)
                with lock:
                    mem_entry = self_obj._MEMORY_CACHE.get(ws_key)
                    if isinstance(mem_entry, dict):
                        import copy

                        updated_mem = copy.deepcopy(mem_entry)
                        updated_mem["duration_ms"] = report["duration_ms"]
                        updated_mem["execution_time_ms"] = report["execution_time_ms"]
                        self_obj._MEMORY_CACHE[ws_key] = updated_mem
            return report

    # 2. Controlla l'igiene della radice con scansione diretta os.scandir
    isolation_check = self_obj._check_root_hygiene(use_fast_cache=False)
    isolation_check["staging_dirty_warning"] = staging_dirty
    report["checks"]["project_isolation"] = isolation_check
    if not isolation_check["passed"]:
        report["status"] = "FAIL"
        report["issues"].append(isolation_check["details"])

    # 3. Bonifica i file WAL orfani e isola i corrotti sotto mutex canonico 2PC
    wal_purge_check = self_obj._purge_stale_wal_files(ttl_seconds=60.0)
    report["checks"]["wal_hygiene"] = wal_purge_check
    now_orphan_ts = time.time()
    try:
        with os.scandir(self_obj.repo_root) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False) and entry.name.endswith(
                    (".tmp", ".bak")
                ):
                    try:
                        if (now_orphan_ts - entry.stat().st_mtime) > 60.0:
                            Path(entry.path).unlink(missing_ok=True)
                    except OSError:
                        pass
    except OSError:
        pass

    # 4. Verifica la coerenza di quality_baseline.json
    baseline_check = self_obj._verify_baseline(cached=None)
    report["checks"]["quality_baseline"] = baseline_check
    if not baseline_check["passed"]:
        report["status"] = "FAIL"
        report["issues"].append(baseline_check["details"])

    # 5. Esegue il controllo non bloccante del Context Sentry
    context_check = self_obj._verify_context_sentry(
        use_fast_cache=fast_stat, cached=cached_state
    )
    report["checks"]["context_sentry"] = context_check
    report["checks"]["meta_prompt_gate"] = self_obj._verify_meta_prompt_gate_state(
        cached=cached_state
    )
    if context_check.get("warning"):
        report["issues"].append(context_check["warning"])

    duration_ms = (time.perf_counter() - start_time) * 1000
    report["duration_ms"] = round(duration_ms, 2)
    report["execution_time_ms"] = round(duration_ms, 2)
    self_obj._save_state(report)
    return report
