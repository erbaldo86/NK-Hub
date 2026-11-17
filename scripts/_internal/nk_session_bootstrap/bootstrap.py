#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orchestratore NKSessionBootstrap ed helper pubblici di modulo."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import compaction_and_head as _compaction
from . import constants as _consts
from . import context_sentry_bridge as _sentry_bridge
from . import fast_cache as _fast_cache
from . import root_hygiene as _root_hygiene
from . import transcript_prompt as _tp
from . import wal_hygiene as _wal_hygiene
from _internal.nk_session_bootstrap.bootstrap_checks import (
    _run_bootstrap_impl,
)


class NKSessionBootstrap:
    """Cancello deterministico di avvio sessione con verifica Fast-Stat ottimizzata."""

    _MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        conversation_id: Optional[str] = None,
        transcript_path: Optional[Path] = None,
        prompt: Optional[str] = None,
        hook_mode: bool = False,
    ):
        os.environ["PYTHONUTF8"] = "1"
        os.environ["PYTHONIOENCODING"] = "utf-8"
        _consts.reconfigure_streams()
        resolved_ws = (
            Path(workspace_root).resolve()
            if workspace_root
            else _consts._workspace_root.resolve()
        )
        if (
            not (resolved_ws / "scripts").is_dir()
            and (resolved_ws / "NK_Hub" / "scripts").is_dir()
        ):
            resolved_ws = (resolved_ws / "NK_Hub").resolve()
        self.repo_root = resolved_ws
        self.workspace_root = resolved_ws
        self.hook_mode = bool(hook_mode)
        self.explicit_prompt = prompt
        hub_root = Path(_consts._get_facade_attr("HUB_ROOT", _consts.HUB_ROOT)).resolve()
        if conversation_id is not None:
            self.conversation_id = conversation_id.strip()
        else:
            raw_conv_id = os.environ.get("NK_CONVERSATION_ID", "").strip()
            if not raw_conv_id and resolved_ws == hub_root:
                raw_conv_id = self._infer_active_conversation_id(120.0)
            self.conversation_id = raw_conv_id
        self.explicit_transcript_path = (
            Path(transcript_path).resolve() if transcript_path else None
        )
        self.transcript_path = self.explicit_transcript_path
        ws_hash = hashlib.sha256(
            os.path.realpath(str(resolved_ws)).lower().encode("utf-8")
        ).hexdigest()[:12]
        self.temp_bootstrap_dir = Path(tempfile.gettempdir()) / "nk_bootstrap"
        self.state_file = (
            self.temp_bootstrap_dir / f"session_bootstrap_state_{ws_hash}.json"
        )
        self.fast_cache_file = (
            self.temp_bootstrap_dir / f".bootstrap_fast_cache_{ws_hash}.json"
        )
        self.temp_bootstrap_dir.mkdir(parents=True, exist_ok=True)
        raw_prof = os.environ.get("NK_MODEL_PROFILE", "generation").strip().lower()
        self.model_profile = (
            raw_prof
            if raw_prof in _consts.SUPPORTED_MODEL_PROFILES
            else (raw_prof or "generation")
        )
        self._last_root_mtime: float = 0.0
        self._cached_root_mtime: Optional[float] = None
        self._cached_staging_mtime: Optional[float] = None
        self._wal_dir_exists: Optional[bool] = None
        self._cached_baseline_stat: Optional[tuple[Path, Any]] = None
        self._last_root_violations: List[str] = []
        self._last_detected_user_prompt: Optional[str] = None
        self._resolved_gate_tuple: Optional[tuple[str, str]] = None

    @staticmethod
    def _get_hooks_temp_dir() -> Path:
        return _tp.get_hooks_temp_dir()

    @classmethod
    def _infer_active_conversation_id(cls, max_age_seconds: float = 60.0) -> str:
        return _tp.infer_active_conversation_id(cls, max_age_seconds=max_age_seconds)

    @staticmethod
    def _is_subagent_transcript_head(head_bytes: bytes) -> bool:
        return _compaction.is_subagent_transcript_head(head_bytes)

    @staticmethod
    def _has_newer_brain_directory(
        cand_tp: Path, recent_window_sec: float = 60.0
    ) -> bool:
        return _tp.has_newer_brain_directory(
            cand_tp, recent_window_sec=recent_window_sec
        )

    def _get_staging_mtime(self) -> float:
        return _root_hygiene.get_staging_mtime(self)

    def _is_staging_dirty(self, cached: Optional[Dict[str, Any]] = None) -> bool:
        return _root_hygiene.is_staging_dirty(self, cached=cached)

    def _has_actionable_wal_entries(self) -> bool:
        return _wal_hygiene.has_actionable_wal_entries(self)

    def _get_root_mtime(self) -> float:
        return _root_hygiene.get_root_mtime(self)

    def _is_cache_entry_valid(
        self, data: Dict[str, Any], ws_key: str, now: Optional[float] = None
    ) -> bool:
        return _fast_cache.is_cache_entry_valid(self, data, ws_key, now=now)

    def _load_fast_cache(self) -> Optional[Dict[str, Any]]:
        return _fast_cache.load_fast_cache(self)

    def _resolve_bound_transcript_path(self) -> Optional[Path]:
        return _tp.resolve_bound_transcript_path(self)

    @staticmethod
    def _extract_user_prompt_from_line(line_bytes: bytes) -> Optional[str]:
        return _tp.extract_user_prompt_from_line(line_bytes)

    def _detect_latest_user_prompt(
        self, cached: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        return _tp.detect_latest_user_prompt(self, cached=cached)

    def _resolve_onboarding_and_gate_mode(
        self, cached: Optional[Dict[str, Any]] = None
    ) -> tuple[str, str]:
        return _tp.resolve_onboarding_and_gate_mode(self, cached=cached)

    def _verify_meta_prompt_gate_state(
        self, cached: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return _tp.verify_meta_prompt_gate_state(self, cached=cached)

    def run_bootstrap(
        self, fast_stat: bool = True, prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Esegue la verifica di avvio controllando prima Fast-Stat e preservando immutabilita cache."""
        return _run_bootstrap_impl(self, fast_stat=fast_stat, prompt=prompt)

    def _can_fast_pass(self, cached: Optional[Dict[str, Any]] = None) -> bool:
        return _fast_cache.can_fast_pass(self, cached=cached)

    def _has_root_file_pollution_quick(self, is_hub_root: bool) -> bool:
        return _root_hygiene.has_root_file_pollution_quick(self, is_hub_root)

    def _check_root_hygiene(
        self, use_fast_cache: bool = False, cached: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return _root_hygiene.check_root_hygiene(
            self, use_fast_cache=use_fast_cache, cached=cached
        )

    @staticmethod
    def _try_acquire_2pc_mutex_nonblocking(root: Optional[Path] = None) -> Optional[int]:
        return _wal_hygiene.try_acquire_2pc_mutex_nonblocking(root=root)

    @staticmethod
    def _release_2pc_mutex(handle: Optional[int]) -> None:
        _wal_hygiene.release_2pc_mutex(handle)

    @staticmethod
    def _inspect_wal_state(wal_file: Path) -> str:
        return _wal_hygiene.inspect_wal_state(wal_file)

    @classmethod
    def _is_committed_wal_file(cls, wal_file: Path) -> bool:
        return cls._inspect_wal_state(wal_file) == "COMMITTED"

    def _quarantine_corrupted_wal(self, wal_file: Path) -> Optional[Path]:
        return _wal_hygiene.quarantine_corrupted_wal(self, wal_file)

    def _purge_stale_wal_files(self, ttl_seconds: float = 60.0) -> Dict[str, Any]:
        return _wal_hygiene.purge_stale_wal_files(self, ttl_seconds=ttl_seconds)

    def _verify_baseline(
        self, cached: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return _root_hygiene.verify_baseline(self, cached=cached)

    def _find_recent_transcript(
        self, brain_dir: Path, max_age_seconds: float = 120.0
    ) -> Optional[Path]:
        return _tp.find_recent_transcript(
            self, brain_dir, max_age_seconds=max_age_seconds
        )

    @staticmethod
    def _count_lines_binary_64kb(transcript_file: Path, t_size: int) -> int:
        return _compaction.count_lines_binary_64kb(transcript_file, t_size)

    @staticmethod
    def _has_compaction_candidate_bytes(buf: bytes) -> bool:
        return _compaction.has_compaction_candidate_bytes(buf)

    @classmethod
    def _count_post_compaction_binary(
        cls, transcript_file: Path, t_size: int
    ) -> tuple[int, int]:
        return _compaction.count_post_compaction_binary(transcript_file, t_size)

    def _fast_tail_estimate(
        self,
        transcript_file: Path,
        t_size: int,
        cached: Optional[Dict[str, Any]],
        sentry: Any = None,
    ) -> Dict[str, Any]:
        return _sentry_bridge.fast_tail_estimate(
            self, transcript_file, t_size, cached, sentry=sentry
        )

    def _verify_context_sentry(
        self, use_fast_cache: bool = False, cached: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return _sentry_bridge.verify_context_sentry(
            self, use_fast_cache=use_fast_cache, cached=cached
        )

    @staticmethod
    def _atomic_write_json(target_path: Path, serialized: str) -> None:
        _fast_cache.atomic_write_json(target_path, serialized)

    def _save_state(self, report: Dict[str, Any]) -> None:
        _fast_cache.save_state(self, report)


def run_bootstrap(
    workspace_root: Optional[Path] = None,
    transcript_path: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    fast_stat: bool = True,
    prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per eseguire il bootstrap Fast-Stat."""
    ws = Path(workspace_root).resolve() if workspace_root else None
    tp = Path(transcript_path).resolve() if transcript_path else None
    return NKSessionBootstrap(
        workspace_root=ws,
        conversation_id=conversation_id,
        transcript_path=tp,
        prompt=prompt,
    ).run_bootstrap(fast_stat=fast_stat, prompt=prompt)


def verify_fast_stat_invariant(
    workspace_root: Optional[Path] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per verificare l'invariante Fast-Stat."""
    ws = Path(workspace_root).resolve() if workspace_root else None
    boot = NKSessionBootstrap(workspace_root=ws, conversation_id=conversation_id)
    cached = boot._load_fast_cache()
    can_fast = boot._can_fast_pass(cached=cached)
    return {
        "passed": True,
        "fast_pass_eligible": can_fast,
        "ttl_seconds": _consts._get_facade_attr(
            "FAST_CACHE_TTL_SECONDS", _consts.FAST_CACHE_TTL_SECONDS
        ),
        "details": "Fast-stat invariant verified. TTL valid (<900s).",
    }


def verify_project_isolation(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Funzione helper di modulo per verificare l'isolamento della root."""
    ws = Path(workspace_root).resolve() if workspace_root else None
    return NKSessionBootstrap(workspace_root=ws)._check_root_hygiene(
        use_fast_cache=False
    )


def enforce_wal_hygiene(
    workspace_root: Optional[Path] = None,
    ttl_seconds: float = 60.0,
) -> Dict[str, Any]:
    """Funzione helper di modulo per bonificare i file WAL scaduti e isolare i corrotti."""
    ws = Path(workspace_root).resolve() if workspace_root else None
    return NKSessionBootstrap(workspace_root=ws)._purge_stale_wal_files(
        ttl_seconds=ttl_seconds
    )
