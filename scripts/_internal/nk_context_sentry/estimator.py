# -*- coding: utf-8 -*-
"""Stima token, semaforo di saturazione e report standalone per nk_context_sentry."""

from __future__ import annotations

from typing import Any, Dict, Optional

from _internal.nk_common.transcript_guards import valid_token_int
from _internal.nk_context_sentry.thresholds_proxy import (
    FLASH_ACTUAL_RED_TOKENS,
    FLASH_ACTUAL_WARN_TOKENS,
    FLASH_GREEN_STEP_THRESHOLD,
    FLASH_GREEN_TOKEN_THRESHOLD,
    FLASH_RED_STEP_THRESHOLD,
    FLASH_RED_TOKEN_THRESHOLD,
    HIGH_CAPACITY_PROFILES,
    _safe_pos_int,
)


def estimate_tokens(text: str) -> int:
    """Stima il numero di token con rapporto medio di quattro caratteri."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def format_head_tail(
    traceback_text: str, head_chars: int = 400, tail_chars: int = 800
) -> str:
    """Comprime i traceback lunghi preservando testa e coda."""
    if not traceback_text:
        return ""
    if len(traceback_text) <= (head_chars + tail_chars + 50):
        return traceback_text
    head = traceback_text[:head_chars].strip()
    tail = traceback_text[-tail_chars:].strip()
    return (
        f"{head}\n\n[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]\n\n"
        f"{tail}"
    )


def extract_actual_tokens_from_record(data: Dict[str, Any]) -> Optional[int]:
    """Estrae actual_context_tokens sommando input_tokens e cache_read_tokens."""
    if not isinstance(data, dict):
        return None
    in_tok = valid_token_int(data.get("input_tokens"))
    cache_tok = valid_token_int(data.get("cache_read_tokens"))
    if in_tok is not None or cache_tok is not None:
        total_in = (in_tok or 0) + (cache_tok or 0)
        if total_in > 0:
            return total_in
    for key in ("actual_context_tokens", "context_tokens", "prompt_tokens"):
        val = valid_token_int(data.get(key))
        if val is not None and val > 0:
            return val
    for sub_key in ("metadata", "usage", "token_usage", "context_window"):
        sub = data.get(sub_key)
        if isinstance(sub, dict):
            sub_in = valid_token_int(sub.get("input_tokens"))
            sub_cache = valid_token_int(sub.get("cache_read_tokens"))
            if sub_in is not None or sub_cache is not None:
                total_sub = (sub_in or 0) + (sub_cache or 0)
                if total_sub > 0:
                    return total_sub
            for key in (
                "actual_context_tokens",
                "context_tokens",
                "prompt_tokens",
                "total_tokens",
            ):
                val = valid_token_int(sub.get(key))
                if val is not None and val > 0:
                    return val
    return None


def is_background_task_message(data: Dict[str, Any], content: str) -> bool:
    """Verifica se il record appartiene a un task asincrono in background."""
    sender = str(data.get("sender") or data.get("sender_id") or "").lower()
    if "task-" in sender or "task_id" in sender:
        return True
    if "task" in data and isinstance(data.get("task"), (dict, str)):
        return True
    content_lower = content.lower()
    if "finished with result" in content_lower:
        return True
    if "sender=" in content_lower and (
        "task-" in content_lower or "task_id" in content_lower
    ):
        return True
    if 'task id "' in content_lower or "task id '" in content_lower:
        return True
    return False


def _resolve_profile_thresholds(sentry: Any, active_profile: str, prof_cfg: Dict[str, Any]) -> tuple[int, int, int, int]:
    if active_profile in HIGH_CAPACITY_PROFILES:
        return (
            _safe_pos_int(prof_cfg.get("green_step_threshold"), sentry.CARBON_GREEN_STEP_THRESHOLD),
            _safe_pos_int(prof_cfg.get("red_step_threshold"), sentry.CARBON_RED_STEP_THRESHOLD),
            _safe_pos_int(prof_cfg.get("green_token_threshold"), sentry.CARBON_GREEN_TOKEN_THRESHOLD),
            _safe_pos_int(prof_cfg.get("red_token_threshold"), sentry.CARBON_RED_TOKEN_THRESHOLD),
        )
    if active_profile == "flash":
        return (
            _safe_pos_int(prof_cfg.get("green_step_threshold"), getattr(sentry, "FLASH_GREEN_STEP_THRESHOLD", FLASH_GREEN_STEP_THRESHOLD)),
            _safe_pos_int(prof_cfg.get("red_step_threshold"), getattr(sentry, "FLASH_RED_STEP_THRESHOLD", FLASH_RED_STEP_THRESHOLD)),
            _safe_pos_int(prof_cfg.get("green_token_threshold"), getattr(sentry, "FLASH_GREEN_TOKEN_THRESHOLD", FLASH_GREEN_TOKEN_THRESHOLD)),
            _safe_pos_int(prof_cfg.get("red_token_threshold"), getattr(sentry, "FLASH_RED_TOKEN_THRESHOLD", FLASH_RED_TOKEN_THRESHOLD)),
        )
    return (
        _safe_pos_int(prof_cfg.get("green_step_threshold"), sentry.GREEN_STEP_THRESHOLD),
        _safe_pos_int(prof_cfg.get("red_step_threshold"), sentry.RED_STEP_THRESHOLD),
        _safe_pos_int(prof_cfg.get("green_token_threshold"), sentry.GREEN_TOKEN_THRESHOLD),
        _safe_pos_int(prof_cfg.get("red_token_threshold"), sentry.RED_TOKEN_THRESHOLD),
    )


def _apply_actual_token_caps(
    sentry: Any, active_profile: str, actual_context_tokens: Optional[int], status: str, recommendation: str,
) -> tuple[str, str]:
    if active_profile not in HIGH_CAPACITY_PROFILES and active_profile != "flash":
        return status, recommendation
    if actual_context_tokens is None or actual_context_tokens <= 0:
        return status, recommendation
    act_red = (
        sentry.CARBON_ACTUAL_RED_TOKENS
        if active_profile in HIGH_CAPACITY_PROFILES
        else getattr(sentry, "FLASH_ACTUAL_RED_TOKENS", FLASH_ACTUAL_RED_TOKENS)
    )
    act_warn = (
        sentry.CARBON_ACTUAL_WARN_TOKENS
        if active_profile in HIGH_CAPACITY_PROFILES
        else getattr(sentry, "FLASH_ACTUAL_WARN_TOKENS", FLASH_ACTUAL_WARN_TOKENS)
    )
    if actual_context_tokens >= act_red:
        return "RED", "Critical saturation (503 risk): Execute /compact or nk_session_handoff.py."
    if actual_context_tokens >= act_warn and status != "RED":
        return "WARN", "Warning: Context saturation nearing threshold. Delegate heavy tasks to subagents."
    return status, recommendation


def get_traffic_light_status_impl(
    sentry: Any,
    step_count: int,
    estimated_tokens: int,
    profile: Optional[str] = None,
    actual_context_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Calcola lo stato semaforico in base a step, token e profilo."""
    active_profile = (profile or sentry.profile or "standard").lower().strip()
    if isinstance(step_count, bool) or not isinstance(step_count, int):
        step_count = 0
    if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int):
        estimated_tokens = 0
    if isinstance(actual_context_tokens, bool) or not isinstance(
        actual_context_tokens, int
    ):
        actual_context_tokens = None
    elif actual_context_tokens < 0:
        actual_context_tokens = 0

    prof_cfg: Dict[str, Any] = {}
    profiles_map = (
        sentry._thresholds.get("profiles")
        if isinstance(getattr(sentry, "_thresholds", None), dict)
        else None
    )
    if isinstance(profiles_map, dict):
        raw_prof = profiles_map.get(active_profile)
        if not isinstance(raw_prof, dict) and active_profile in HIGH_CAPACITY_PROFILES:
            raw_prof = profiles_map.get("generation") or profiles_map.get("carbon")
        if isinstance(raw_prof, dict) and isinstance(
            raw_prof.get("context_sentry"), dict
        ):
            prof_cfg = raw_prof["context_sentry"]

    green_steps, red_steps, green_tokens, red_tokens = _resolve_profile_thresholds(
        sentry, active_profile, prof_cfg
    )

    effective_tokens = (
        actual_context_tokens
        if (actual_context_tokens is not None and actual_context_tokens > 0)
        else estimated_tokens
    )

    if step_count < green_steps and effective_tokens < green_tokens:
        status = "GREEN"
        recommendation = "Nominal execution. Context is lean and responsive."
    elif step_count < red_steps and effective_tokens < red_tokens:
        status = "YELLOW"
        recommendation = (
            "Warning: Context saturation nearing threshold. Delegate heavy tasks to subagents."
        )
    else:
        status = "RED"
        recommendation = (
            "Critical saturation (503 risk): Execute /compact or nk_session_handoff.py."
        )

    status, recommendation = _apply_actual_token_caps(
        sentry, active_profile, actual_context_tokens, status, recommendation
    )

    result: Dict[str, Any] = {
        "status": status,
        "step_count": step_count,
        "estimated_tokens": estimated_tokens,
        "profile": active_profile,
        "recommendation": recommendation,
    }
    if actual_context_tokens is not None:
        result["actual_context_tokens"] = actual_context_tokens
    return result


def build_standalone_report_impl(
    sentry: Any, profile: Optional[str] = None
) -> Dict[str, Any]:
    """Costruisce un rapporto GREEN in modalita CLI_STANDALONE."""
    active_profile = (profile or sentry.profile or "standard").lower().strip()
    return {
        "status": "GREEN",
        "mode": "CLI_STANDALONE",
        "profile": active_profile,
        "step_count": 0,
        "total_chars": 0,
        "estimated_tokens": 0,
        "actual_context_tokens": None,
        "recommendation": "CLI_STANDALONE: no active transcript detected. Nominal context state.",
        "chars_by_source": {},
        "tool_counts": {},
        "max_consecutive_direct_audit": 0,
        "blind_read_errors": 0,
        "write_burst_steps": 0,
        "swarm_mss_cap": sentry.SWARM_MSG_MSS_CAP,
        "swarm_mss_warnings_count": 0,
        "swarm_mss_warnings": [],
        "swarm_hygiene_violations_count": 0,
        "swarm_hygiene_violations": [],
        "kv_cache_cold_risk": False,
        "rpc_stream_burst_risk": False,
        "idle_gap_seconds": 0.0,
    }
