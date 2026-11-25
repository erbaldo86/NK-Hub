# -*- coding: utf-8 -*-
"""Valutazione regole, telemetria RSI e scorecard per nk_compliance_checker."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_compliance_checker.transcript_scan import (
    NKContextSentry,
    SESSION_TELEMETRY_MAX_SKEW_SECONDS,
    _is_subagent_transcript,
    _parse_record_epoch,
)


def _resolve_context_sentry_cls() -> Any:
    """Risolve NKContextSentry tenendo conto di eventuali monkeypatch sulla facciata."""
    for mod in list(sys.modules.values()):
        mfile = getattr(mod, "__file__", "") or ""
        if mfile.endswith(("nk_compliance_checker.py", "nk_compliance_checker.pyc")) and "NKContextSentry" in vars(mod):
            return getattr(mod, "NKContextSentry", None)
    return NKContextSentry


def extract_session_identifier(transcript_file: Optional[Path]) -> str:
    """Estrae l'identificatore conversazione dal percorso del transcript."""
    if transcript_file is None:
        return ""
    resolved = Path(transcript_file).resolve()
    parts = list(resolved.parts)
    for idx in range(len(parts) - 2, -1, -1):
        if parts[idx].lower() == "brain" and parts[idx + 1] and parts[idx + 1] != resolved.name:
            return parts[idx + 1]
    if len(parts) >= 2 and resolved.name in ("transcript.jsonl", "transcript_full.jsonl") and parts[-2] and parts[-2] != resolved.anchor:
        return parts[-2]
    return ""


def valid_numeric_score(val: Any) -> Optional[float]:
    """Convalida un valore numerico finito escludendo i booleani."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    num = float(val)
    return num if math.isfinite(num) else None


def score_from_rsi_record(rec: Dict[str, Any]) -> int | float:
    """Converte un record rsi_telemetry.jsonl nel punteggio RSI fail-closed."""
    if not isinstance(rec, dict):
        return 0
    raw_fq_field = rec.get("fitness_q")
    raw_fq = valid_numeric_score(raw_fq_field)
    raw_dk = valid_numeric_score(rec.get("delta_k"))
    if raw_fq_field is not None and raw_fq is None:
        return 0
    if raw_fq is not None:
        return round(max(0.0, min(100.0, raw_fq)), 1)
    if raw_dk is None:
        return 0
    verdict = str(rec.get("verdict") or "").strip().upper()
    return 100 if (raw_dk == 0 and verdict not in ("FAIL", "ERROR", "UNMEASURED")) else 0


def read_jsonl_dicts_reversed(cand: Path) -> List[Dict[str, Any]]:
    """Legge i record JSON dizionario in ordine inverso dal file."""
    out: List[Dict[str, Any]] = []
    for raw_ln in reversed(cand.read_text(encoding="utf-8", errors="replace").splitlines()):
        stripped = raw_ln.strip()
        if not stripped:
            continue
        try:
            rec = json.loads(stripped)
            if isinstance(rec, dict):
                out.append(rec)
        except Exception:
            continue
    return out


def _rec_session_id(rec: Dict[str, Any]) -> str:
    """Estrae l'identificatore sessione da un record telemetrico."""
    return str(rec.get("session_id") or rec.get("conversation_id") or "").strip()


def lookup_rsi_telemetry_score(
    workspace_root: Path, transcript_file: Optional[Path] = None
) -> Tuple[bool, int | float]:
    """Cerca il punteggio RSI valido per la sessione corrente."""
    local_candidates: List[Path] = []
    transcript_mtime: Optional[float] = None
    session_id = extract_session_identifier(transcript_file)

    if transcript_file is not None:
        local_candidates.extend((transcript_file.parent / "rsi_telemetry.jsonl", transcript_file.parent / "nk_tracking" / "rsi_telemetry.jsonl"))
        try:
            if transcript_file.exists():
                transcript_mtime = transcript_file.stat().st_mtime
        except OSError:
            transcript_mtime = None

    for cand in local_candidates:
        if not cand.is_file():
            continue
        try:
            for rec in read_jsonl_dicts_reversed(cand):
                rec_session = _rec_session_id(rec)
                if session_id and rec_session and rec_session != session_id:
                    continue
                return True, score_from_rsi_record(rec)
        except Exception:
            continue

    for cand in (workspace_root / ".staging" / "nk_tracking" / "rsi_telemetry.jsonl", workspace_root / "nk_tracking" / "rsi_telemetry.jsonl"):
        if not cand.is_file():
            continue
        try:
            if transcript_mtime is not None and abs(transcript_mtime - cand.stat().st_mtime) > SESSION_TELEMETRY_MAX_SKEW_SECONDS:
                continue
            recs = read_jsonl_dicts_reversed(cand)
            if session_id:
                for rec in recs:
                    if _rec_session_id(rec) == session_id:
                        return True, score_from_rsi_record(rec)
            for rec in recs:
                if _rec_session_id(rec):
                    continue
                rec_ts = _parse_record_epoch(rec.get("timestamp") or rec.get("created_at"))
                if transcript_mtime is not None and rec_ts is not None and abs(transcript_mtime - rec_ts) > SESSION_TELEMETRY_MAX_SKEW_SECONDS:
                    continue
                return True, score_from_rsi_record(rec)
        except Exception:
            continue
    return False, 0


def _apply_holdout_and_external_penalties(
    c: Dict[str, Any],
    penalties: List[str],
    win32_2pc_executed: bool,
    procedural_score: int,
    operational_score: int,
) -> Tuple[int, int, bool, Dict[str, int]]:
    """Applica penalita holdout, same-turn test edit, Online write e Locale unstaged."""
    holdout_reads = int(c.get("holdout_read_calls", 0))
    test_edits = int(c.get("test_edit_calls", 0))
    same_turn_edits = int(c.get("same_turn_test_edits", 0))
    holdout_anoms = int(c.get("holdout_or_same_turn_test_anomalies", 0))
    online_writes = int(c.get("online_write_calls", 0))

    if holdout_reads > 0:
        hr_pen = min(50, holdout_reads * 25)
        procedural_score -= hr_pen
        penalties.append(f"Holdout read violation: {holdout_reads} forbidden oracle_holdout/nk_holdout read(s) [-{hr_pen}]")
    if same_turn_edits > 0 or holdout_anoms > holdout_reads:
        extra_anoms = max(same_turn_edits, holdout_anoms - holdout_reads)
        st_pen = min(40, extra_anoms * 20)
        procedural_score -= st_pen
        penalties.append(f"Same-turn test edit anomaly: {extra_anoms} concurrent test/prod mutation(s) [-{st_pen}]")

    procedural_score = max(0, procedural_score)
    if online_writes > 0:
        on_pen = min(50, online_writes * 20)
        operational_score = max(0, operational_score - on_pen)
        procedural_score = max(0, procedural_score - on_pen)
        penalties.append(f"Read-only NK Proget/Online mutation: {online_writes} forbidden write(s) [-{on_pen}]")
    locale_unstage = max(0, int(c["external_unstage_writes"]) - online_writes)
    if locale_unstage > 0 and not win32_2pc_executed:
        ext_penalty = min(40, locale_unstage * 10)
        operational_score = max(0, operational_score - ext_penalty)
        penalties.append(f"External project unstaged writes: {locale_unstage} direct write(s) to NK_External_Projects/Locale outside .staging/ [-{ext_penalty}]")

    hard_violation = holdout_reads > 0 or holdout_anoms > 0 or online_writes > 0
    extra_metrics = {
        "online_write_calls": online_writes,
        "holdout_read_calls": holdout_reads,
        "test_edit_calls": test_edits,
        "same_turn_test_edits": same_turn_edits,
        "holdout_or_same_turn_test_anomalies": holdout_anoms,
    }
    return procedural_score, operational_score, hard_violation, extra_metrics


def evaluate_compliance_scores(
    checker: Any,
    transcript_file: Path,
    records: List[Dict[str, Any]],
    c: Dict[str, Any],
) -> Dict[str, Any]:
    """Calcola la scorecard composita a partire dalle metriche scansionate."""
    is_subagent = _is_subagent_transcript(transcript_file)
    total_steps, total_tool_calls = c["total_steps"], c["total_tool_calls"]
    polling_calls, subagents_invoked, subagents_polled = c["polling_calls"], c["subagents_invoked"], c["subagents_polled"]
    code_write_calls, external_unstage_writes = c["code_write_calls"], c["external_unstage_writes"]
    error_steps, win32_2pc_executed = c["error_steps"], c["win32_2pc_executed"]

    sentry_cls = _resolve_context_sentry_cls()
    if sentry_cls is not None:
        inferred_profile = os.environ.get("NK_MODEL_PROFILE") or "generation"
        sentry = sentry_cls(workspace_root=checker.workspace_root, profile=inferred_profile)
        sentry_res = sentry.analyze_transcript(transcript_file, profile=inferred_profile, preloaded_records=records if records else None)
    else:
        sentry_res = {
            "status": "UNMEASURED", "step_count": total_steps, "estimated_tokens": 0,
            "max_consecutive_direct_audit": 0, "swarm_hygiene_violations_count": 0,
        }

    polling_ratio = (polling_calls + subagents_polled) / total_tool_calls if total_tool_calls > 0 else 0.0
    procedural_score = 100
    penalties: List[str] = []

    if polling_ratio > 0.15:
        penalty = min(35, int(polling_ratio * 70))
        procedural_score -= penalty
        penalties.append(f"Excessive busy polling: {polling_calls + subagents_polled} calls ({round(polling_ratio * 100, 1)}% of tools) [-{penalty}]")

    sentry_status = sentry_res.get("status", "UNMEASURED")
    warn_advisory = False
    advisories: List[str] = []
    if sentry_status == "UNMEASURED":
        procedural_score -= 25
        penalties.append("Context telemetry unavailable (UNMEASURED status) [-25]")
    elif sentry_status == "WARN":
        warn_advisory = True
        adv_tokens = sentry_res.get("actual_context_tokens") or sentry_res.get("effective_context_tokens") or sentry_res.get("estimated_tokens", 0)
        advisories.append(f"Context saturation advisory (WARN status): {sentry_res.get('step_count', 0)} steps, ~{adv_tokens:,} tokens [0]")
    elif sentry_status == "YELLOW":
        procedural_score -= 15
        penalties.append(f"Context saturation warning (YELLOW status): {sentry_res.get('step_count', 0)} steps, ~{sentry_res.get('estimated_tokens', 0):,} tokens [-15]")
    elif sentry_status == "RED":
        procedural_score -= 35
        penalties.append(f"Critical context saturation (RED status): {sentry_res.get('step_count', 0)} steps, ~{sentry_res.get('estimated_tokens', 0):,} tokens [-35]")

    swarm_violations = sentry_res.get("swarm_hygiene_violations_count", 0)
    if swarm_violations > 0:
        swarm_penalty = swarm_violations * 15
        procedural_score -= swarm_penalty
        penalties.append(f"Swarm hygiene violation: {swarm_violations} oversized inter-agent message(s) (>2000 chars) [-{swarm_penalty}]")

    max_consecutive_direct = max(int(sentry_res.get("max_consecutive_direct_audit", 0)), c["max_direct_tool_calls_streak"])
    if not is_subagent:
        if max_consecutive_direct > checker.DDI_DIRECT_STREAK_LIMIT:
            procedural_score -= 20
            penalties.append(f"Objective DDI violation: {max_consecutive_direct} consecutive direct tools without delegation (>{checker.DDI_DIRECT_STREAK_LIMIT}) [-20]")
        elif code_write_calls > 10 and subagents_invoked == 0:
            procedural_score -= 25
            penalties.append("Monolithic write pattern: >10 writes without subagent delegation (DDI violation) [-25]")

    if not is_subagent and c["has_non_exempt_user_turn"] and not c["meta_prompt_gate_executed"] and (code_write_calls > 0 or total_steps > 3):
        procedural_score -= 20
        penalties.append("Meta-Prompt Gate L0 omitted [-20]")

    if code_write_calls > 0 and not win32_2pc_executed:
        procedural_score -= 20
        penalties.append("Staging bypass: writes performed without 2PC atomic commit [-20]")

    exempt_delegated_writes = code_write_calls == 0 and (subagents_invoked > 0 or win32_2pc_executed or is_subagent)
    if code_write_calls > 0 and not c["ast_guard_executed"] and not exempt_delegated_writes:
        procedural_score -= 10
        penalties.append("AST Guard omitted [-10]")

    operational_score = max(0, 100 - (error_steps * 10)) if error_steps > 0 else 100
    procedural_score, operational_score, hard_violation, extra_m = _apply_holdout_and_external_penalties(
        c, penalties, win32_2pc_executed, procedural_score, operational_score
    )

    rsi_telemetry_found, rsi_convergence_score = checker._lookup_rsi_telemetry_score(transcript_file)
    if not rsi_telemetry_found and code_write_calls == 0:
        composite_score = round(((operational_score * 0.40) + (procedural_score * 0.35)) / 0.75, 1)
    else:
        composite_score = round((operational_score * 0.40) + (procedural_score * 0.35) + (rsi_convergence_score * 0.25), 1)

    status = "PASS" if (not hard_violation and procedural_score >= 80 and composite_score >= 80 and sentry_status != "UNMEASURED") else "FAIL"
    return {
        "status": status, "total_steps": total_steps, "total_tool_calls": total_tool_calls,
        "metrics": {
            "polling_calls_total": polling_calls + subagents_polled, "polling_ratio_pct": round(polling_ratio * 100, 2),
            "subagents_invoked": subagents_invoked, "write_calls": c["write_calls"], "code_write_calls": code_write_calls,
            "external_unstage_writes": external_unstage_writes, **extra_m,
            "ast_guard_executed": c["ast_guard_executed"],
            "healing_loop_executed": c["healing_loop_executed"], "win32_2pc_executed": win32_2pc_executed,
            "bootstrap_executed": c["bootstrap_executed"], "meta_prompt_gate_executed": c["meta_prompt_gate_executed"],
            "max_consecutive_direct_audit": max_consecutive_direct, "direct_tool_calls_streak": c["max_direct_tool_calls_streak"],
            "blind_read_errors": c["blind_read_errors"], "write_burst_steps": c["write_burst_steps"],
            "command_error_steps": c["command_error_steps"], "error_steps": error_steps,
            "swarm_hygiene_violations_count": swarm_violations, "context_sentry_status": sentry_status,
            "warn_advisory": warn_advisory, "rsi_telemetry_measured": rsi_telemetry_found,
        },
        "warn_advisory": warn_advisory, "advisories": advisories, "context_sentry": sentry_res,
        "scores": {
            "operational_score": operational_score, "procedural_score": procedural_score,
            "rsi_convergence_score": rsi_convergence_score, "composite_score": composite_score,
        },
        "penalties": penalties,
    }
