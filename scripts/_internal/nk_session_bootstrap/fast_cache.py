#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cache Fast-Stat su memoria e disco con scrittura atomica e invalidazione granulare."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..nk_common import io as _nk_io
from . import compaction_and_head as _compaction
from . import constants as _consts
from . import transcript_prompt as _tp


def atomic_write_json(target_path: Path, serialized: str) -> None:
    """Scrive un file JSON in modo atomico delegando a nk_common.io.atomic_write_text."""
    _nk_io.atomic_write_text(target_path, serialized, fsync_data=False)


def is_cache_entry_valid(
    self_obj: Any,
    data: Dict[str, Any],
    ws_key: str,
    now: Optional[float] = None,
) -> bool:
    """Verifica workspace, TTL 900s, root_mtime e staging_mtime senza mutare il record."""
    fast_ttl = float(
        _consts._get_facade_attr("FAST_CACHE_TTL_SECONDS", _consts.FAST_CACHE_TTL_SECONDS)
    )
    cached_ws = data.get("workspace_root")
    if cached_ws is not None and cached_ws != ws_key:
        return False
    now_ts = time.time() if now is None else now
    cached_time = float(data.get("timestamp_epoch", 0.0))
    if cached_time <= 0.0 or (now_ts - cached_time) > fast_ttl:
        return False
    cached_root_mtime = data.get("root_mtime")
    if cached_root_mtime is not None:
        curr_root_mtime = self_obj._get_root_mtime()
        if curr_root_mtime != float(cached_root_mtime):
            return False
    cached_stg_mtime = data.get("staging_mtime")
    if cached_stg_mtime is not None:
        curr_stg_mtime = self_obj._get_staging_mtime()
        if curr_stg_mtime != float(cached_stg_mtime):
            return False
    return True


def load_fast_cache(self_obj: Any) -> Optional[Dict[str, Any]]:
    """Carica la cache veloce isolata per conversazione da _MEMORY_CACHE o disco."""
    ws_key = str(self_obj.workspace_root)
    mem_key = getattr(self_obj, "_cache_mem_key", ws_key)
    now_ts = time.time()
    lock = _consts._get_facade_attr("_BOOTSTRAP_LOCK", _consts._BOOTSTRAP_LOCK)
    with lock:
        mem_entry = self_obj._MEMORY_CACHE.get(mem_key)
        if isinstance(mem_entry, dict):
            disk_newer = False
            try:
                disk_mt = os.stat(self_obj.fast_cache_file).st_mtime
                if disk_mt > float(mem_entry.get("timestamp_epoch", 0.0)) + 0.05:
                    disk_newer = True
            except OSError:
                pass
            if not disk_newer and self_obj._is_cache_entry_valid(
                mem_entry, ws_key, now=now_ts
            ):
                import copy

                return copy.deepcopy(mem_entry)

        for candidate in (self_obj.fast_cache_file, self_obj.state_file):
            try:
                raw = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and self_obj._is_cache_entry_valid(
                    data, ws_key, now=now_ts
                ):
                    import copy

                    self_obj._MEMORY_CACHE[mem_key] = copy.deepcopy(data)
                    return copy.deepcopy(data)
            except Exception:
                continue
        return None


def can_fast_pass(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> bool:
    """Verifica validita di TTL, root_mtime, staging_mtime, prompt esplicito e delta transcript."""
    if cached is None:
        cached = self_obj._load_fast_cache()
    if not cached:
        return False
    try:
        fast_ttl = float(
            _consts._get_facade_attr(
                "FAST_CACHE_TTL_SECONDS", _consts.FAST_CACHE_TTL_SECONDS
            )
        )
        state_ttl = float(
            _consts._get_facade_attr(
                "STATE_CACHE_TTL_SECONDS", _consts.STATE_CACHE_TTL_SECONDS
            )
        )
        tp_max_age = float(
            _consts._get_facade_attr(
                "TRANSCRIPT_MAX_AGE_SECONDS", _consts.TRANSCRIPT_MAX_AGE_SECONDS
            )
        )
        tail_limit = int(
            _consts._get_facade_attr(
                "TAIL_READ_BYTES_LIMIT", _consts.TAIL_READ_BYTES_LIMIT
            )
        )

        now = time.time()
        cached_time = float(cached.get("timestamp_epoch", 0.0))
        if (
            cached_time <= 0.0
            or (now - cached_time) > fast_ttl
            or (now - cached_time) > state_ttl
        ):
            return False

        if cached.get("status") != "PASS":
            return False

        if cached.get("root_hygiene_violations"):
            return False

        if self_obj.explicit_prompt is not None:
            norm_explicit = (
                _tp.strip_antigravity_envelope(str(self_obj.explicit_prompt)).strip()
                or None
            )
            raw_cached_p = cached.get(
                "latest_user_prompt", cached.get("cached_latest_user_prompt")
            )
            norm_cached_p = (
                str(raw_cached_p).strip()
                if isinstance(raw_cached_p, str) and raw_cached_p.strip()
                else None
            )
            if norm_explicit != norm_cached_p:
                return False
        elif bool(cached.get("explicit_prompt_used")):
            return False

        curr_root_mtime = self_obj._get_root_mtime()
        self_obj._last_root_mtime = curr_root_mtime
        cached_root_mtime = cached.get("root_mtime")
        if cached_root_mtime is None or curr_root_mtime != float(cached_root_mtime):
            return False

        cached_stg_mtime = cached.get("staging_mtime")
        if cached_stg_mtime is not None:
            if self_obj._get_staging_mtime() != float(cached_stg_mtime):
                return False

        cached_conv = str(cached.get("conversation_id", "")).strip()
        same_conv = bool(self_obj.conversation_id) and (
            cached_conv == self_obj.conversation_id
        )
        if (
            not same_conv
            and self_obj.explicit_transcript_path is None
            and (self_obj.conversation_id or cached_conv)
        ):
            return False
        last_tp = str(cached.get("last_transcript_path", ""))
        if self_obj.explicit_transcript_path is not None and last_tp != str(
            self_obj.explicit_transcript_path
        ):
            return False

        tp: Optional[Path] = None
        if self_obj.explicit_transcript_path is not None:
            tp = self_obj.explicit_transcript_path
        elif same_conv and last_tp:
            tp = Path(last_tp)

        if tp is not None and tp.exists():
            t_stat = tp.stat()
            if (now - t_stat.st_mtime) > tp_max_age:
                return False
            t_size = t_stat.st_size
            prev_size = int(cached.get("last_transcript_size", 0))
            if t_size < prev_size or (t_size - prev_size) > tail_limit:
                return False
            if t_size > prev_size:
                delta = t_size - prev_size
                with open(tp, "rb") as bf:
                    bf.seek(prev_size)
                    appended = bf.read(delta)
                if _compaction.has_compaction_candidate_bytes(appended):
                    return False
                triggers = _consts._get_facade_attr(
                    "ONBOARDING_TRIGGERS", _consts.ONBOARDING_TRIGGERS
                )
                low_app = appended.lower()
                if any(trig.encode("utf-8") in low_app for trig in triggers):
                    return False
                for raw_ln in appended.splitlines():
                    if _tp.extract_user_prompt_from_line(raw_ln) is not None:
                        return False

        return True
    except Exception:
        return False


def save_state(self_obj: Any, report: Dict[str, Any]) -> None:
    """Salva atomicamente una copia immutabile dello stato del bootstrap e della cache rapida."""
    try:
        import copy

        report_to_save = copy.deepcopy(report)
        report_to_save["timestamp_epoch"] = time.time()
        report_to_save["workspace_root"] = str(self_obj.workspace_root)
        report_to_save["conversation_id"] = self_obj.conversation_id
        report_to_save["active_profile"] = self_obj.model_profile
        self_obj._last_root_mtime = self_obj._get_root_mtime()
        report_to_save["root_mtime"] = self_obj._last_root_mtime
        report_to_save["staging_mtime"] = self_obj._get_staging_mtime()
        report_to_save["root_hygiene_violations"] = list(
            self_obj._last_root_violations
        )
        report_to_save["root_hygiene"] = copy.deepcopy(
            report.get("checks", {}).get("project_isolation", {})
        )
        report_to_save["cached_latest_user_prompt"] = (
            self_obj._last_detected_user_prompt
        )
        report_to_save["latest_user_prompt"] = self_obj._last_detected_user_prompt
        report_to_save["explicit_prompt_used"] = self_obj.explicit_prompt is not None

        staging_baseline = (
            self_obj.workspace_root
            / ".staging"
            / "nk_tracking"
            / "quality_baseline.json"
        )
        prod_baseline = (
            self_obj.workspace_root / "nk_tracking" / "quality_baseline.json"
        )
        for b_cand in (staging_baseline, prod_baseline):
            try:
                bst = os.stat(b_cand)
                report_to_save["baseline_stat"] = [
                    str(b_cand),
                    bst.st_mtime_ns,
                    bst.st_size,
                ]
                break
            except OSError:
                continue

        cs_info = report.get("checks", {}).get("context_sentry", {})
        if isinstance(cs_info, dict):
            t_path = str(cs_info.get("last_transcript_path", ""))
            t_mtime = float(cs_info.get("transcript_mtime", 0.0))
            t_size = int(cs_info.get("transcript_size", 0))
            t_steps = int(cs_info.get("step_count", 0))
            report_to_save["last_transcript_path"] = t_path
            report_to_save["last_transcript_mtime"] = t_mtime
            report_to_save["last_transcript_size"] = t_size
            report_to_save["last_step_count"] = t_steps
            report_to_save["transcript_mtime"] = t_mtime
            report_to_save["transcript_size"] = t_size

        serialized = json.dumps(report_to_save, indent=2)
        lock = _consts._get_facade_attr("_BOOTSTRAP_LOCK", _consts._BOOTSTRAP_LOCK)
        mem_key = getattr(self_obj, "_cache_mem_key", str(self_obj.workspace_root))
        with lock:
            self_obj._MEMORY_CACHE[mem_key] = copy.deepcopy(
                report_to_save
            )
            self_obj._atomic_write_json(self_obj.fast_cache_file, serialized)
            self_obj._atomic_write_json(self_obj.state_file, serialized)
    except Exception:
        pass
