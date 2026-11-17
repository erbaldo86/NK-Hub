#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stima delta tail post-compattazione e ponte Context Sentry."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import compaction_and_head as _compaction
from . import constants as _consts
from . import resilience_tail as _resilience_tail


def fast_tail_estimate(
    self_obj: Any,
    transcript_file: Path,
    t_size: int,
    cached: Optional[Dict[str, Any]],
    sentry: Any = None,
) -> Dict[str, Any]:
    """Calcola step e token post-compattazione sul transcript attivo con stima delta o a ritroso."""
    chunk_size = int(
        _consts._get_facade_attr("BINARY_CHUNK_SIZE", _consts.BINARY_CHUNK_SIZE)
    )
    prev_size = int(cached.get("last_transcript_size", 0)) if cached else 0
    prev_steps = int(cached.get("last_step_count", 0)) if cached else 0
    prev_cs = (
        cached.get("checks", {}).get("context_sentry", {}) if cached else {}
    )
    prev_tokens = int(prev_cs.get("estimated_tokens", 0))

    if (
        cached is not None
        and prev_size > 0
        and prev_steps > 0
        and 0 <= (t_size - prev_size) <= chunk_size
        and cached.get("last_transcript_path") == str(transcript_file)
    ):
        delta_bytes = t_size - prev_size
        if delta_bytes > 0:
            with open(transcript_file, "rb") as bf:
                bf.seek(prev_size)
                tail_chunk = bf.read(delta_bytes)
            if self_obj._has_compaction_candidate_bytes(tail_chunk):
                step_count, post_bytes = self_obj._count_post_compaction_binary(
                    transcript_file, t_size
                )
                est_tokens = max(1, post_bytes // 4)
            else:
                delta_steps = tail_chunk.count(b"\n")
                step_count = prev_steps + delta_steps
                est_tokens = prev_tokens + max(1, delta_bytes // 4)
        else:
            step_count = prev_steps
            est_tokens = prev_tokens
    else:
        step_count, post_bytes = self_obj._count_post_compaction_binary(
            transcript_file, t_size
        )
        est_tokens = max(1, post_bytes // 4) if post_bytes > 0 else 0

    inspect_fn = _consts._get_facade_attr(
        "_inspect_tail_resilience_risks", _resilience_tail._inspect_tail_resilience_risks
    )
    tail_risks = inspect_fn(
        transcript_file, t_size=t_size, est_tokens=est_tokens
    )
    eff_ctx = int(tail_risks.get("effective_context_tokens", 0))
    if sentry is not None:
        traffic = sentry.get_traffic_light_status(
            step_count,
            est_tokens,
            profile=self_obj.model_profile,
            actual_context_tokens=eff_ctx if eff_ctx > 0 else None,
        )
        traffic["profile"] = self_obj.model_profile
    else:
        light_fn = _consts._get_facade_attr(
            "_compute_fast_traffic_light", _compaction._compute_fast_traffic_light
        )
        traffic = light_fn(
            step_count,
            est_tokens,
            profile=self_obj.model_profile,
            actual_context_tokens=eff_ctx if eff_ctx > 0 else None,
        )
    traffic.update(tail_risks)
    return traffic


def verify_context_sentry(
    self_obj: Any,
    use_fast_cache: bool = False,
    cached: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Controlla il transcript vincolato o imposta CLI_STANDALONE / GREEN senza falsi positivi (BOOT-01)."""
    if self_obj.explicit_transcript_path is None and not self_obj.conversation_id:
        return {
            "passed": True,
            "status": "GREEN",
            "mode": "CLI_STANDALONE",
            "context_mode": "CLI_STANDALONE",
            "health_status": "PASS",
            "step_count": 0,
            "estimated_tokens": 0,
            "last_transcript_path": "",
            "transcript_mtime": 0.0,
            "transcript_size": 0,
            "active_profile": self_obj.model_profile,
            "kv_cache_cold_risk": False,
            "rpc_stream_burst_risk": False,
            "idle_gap_seconds": 0.0,
            "warning": None,
            "details": "CLI_STANDALONE: no active transcript bound; context status GREEN.",
        }

    tp_max_age = float(
        _consts._get_facade_attr(
            "TRANSCRIPT_MAX_AGE_SECONDS", _consts.TRANSCRIPT_MAX_AGE_SECONDS
        )
    )
    if cached is None and use_fast_cache:
        cached = self_obj._load_fast_cache()
    transcript_file: Optional[Path] = None

    if (
        self_obj.explicit_transcript_path
        and self_obj.explicit_transcript_path.exists()
    ):
        transcript_file = self_obj.explicit_transcript_path
    elif (
        use_fast_cache
        and cached
        and str(cached.get("conversation_id", "")).strip() == self_obj.conversation_id
    ):
        cached_tp = cached.get("last_transcript_path", "")
        if cached_tp:
            cand_tp = Path(cached_tp)
            try:
                if (
                    cand_tp.exists()
                    and (time.time() - cand_tp.stat().st_mtime) <= tp_max_age
                ):
                    transcript_file = cand_tp
            except Exception:
                transcript_file = None

    if transcript_file is None:
        brain_dir = (
            Path(os.environ.get("USERPROFILE", ""))
            / ".gemini"
            / "antigravity"
            / "brain"
        )
        transcript_file = self_obj._find_recent_transcript(brain_dir)

    if not transcript_file or not transcript_file.exists():
        return {
            "passed": True,
            "status": "GREEN",
            "mode": "ACTIVE_SESSION",
            "step_count": 0,
            "estimated_tokens": 0,
            "last_transcript_path": "",
            "transcript_mtime": 0.0,
            "transcript_size": 0,
            "active_profile": self_obj.model_profile,
            "details": "No active transcript found. Fresh session assumed.",
        }

    try:
        t_stat = transcript_file.stat()
        t_mtime = t_stat.st_mtime
        t_size = t_stat.st_size

        if (
            cached is not None
            and str(cached.get("conversation_id", "")).strip()
            == self_obj.conversation_id
        ):
            prev_t_size = int(cached.get("transcript_size", 0) or 0)
            if (
                cached.get("last_transcript_path") == str(transcript_file)
                and cached.get("active_profile") == self_obj.model_profile
            ):
                cached_cs = cached.get("checks", {}).get("context_sentry")
                if isinstance(cached_cs, dict) and cached_cs.get("passed"):
                    if (
                        cached.get("transcript_mtime") == t_mtime
                        and prev_t_size == t_size
                    ):
                        import copy

                        return copy.deepcopy(cached_cs)

        sentry_cls = _consts._get_facade_attr(
            "NKContextSentry", _consts.NKContextSentry
        )
        injected_sentry = (
            sentry_cls(
                workspace_root=self_obj.workspace_root,
                profile=self_obj.model_profile,
            )
            if sentry_cls is not None
            else None
        )
        res = self_obj._fast_tail_estimate(
            transcript_file, t_size, cached, sentry=injected_sentry
        )

        status = res.get("status", "GREEN")
        step_count = int(res.get("step_count", 0))
        est_tokens = int(res.get("estimated_tokens", 0))
        warn_fn = _consts._get_facade_attr(
            "_build_context_warning", _resilience_tail._build_context_warning
        )
        warning = warn_fn(status, step_count, est_tokens, res)

        return {
            "passed": True,
            "status": status,
            "mode": "ACTIVE_SESSION",
            "health_status": "WARN" if status in ("RED", "WARN") else "PASS",
            "step_count": step_count,
            "estimated_tokens": est_tokens,
            "last_transcript_path": str(transcript_file),
            "transcript_mtime": t_mtime,
            "transcript_size": t_size,
            "active_profile": self_obj.model_profile,
            "kv_cache_cold_risk": bool(res.get("kv_cache_cold_risk", False)),
            "rpc_stream_burst_risk": bool(res.get("rpc_stream_burst_risk", False)),
            "idle_gap_seconds": float(res.get("idle_gap_seconds", 0.0)),
            "warning": warning,
            "details": f"Context status {status} ({step_count} steps).",
        }
    except Exception as exc:
        return {
            "passed": True,
            "status": "GREEN",
            "details": f"Context Sentry check error: {exc}",
        }
