# -*- coding: utf-8 -*-
"""Classe NKContextSentry e punto di ingresso CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.nk_context_sentry.estimator import (
    build_standalone_report_impl,
    estimate_tokens as _estimate_tokens,
    extract_actual_tokens_from_record,
    format_head_tail as _format_head_tail,
    get_traffic_light_status_impl,
    is_background_task_message as _is_bg_task_msg,
    valid_token_int,
)
from _internal.nk_context_sentry.thresholds_proxy import (
    ARGON_ACTUAL_RED_TOKENS,
    ARGON_ACTUAL_WARN_TOKENS,
    CARBON_ACTUAL_RED_TOKENS,
    CARBON_ACTUAL_WARN_TOKENS,
    CARBON_GREEN_STEP_THRESHOLD,
    CARBON_GREEN_TOKEN_THRESHOLD,
    CARBON_RED_STEP_THRESHOLD,
    CARBON_RED_TOKEN_THRESHOLD,
    GENERATION_ACTUAL_RED_TOKENS,
    GENERATION_ACTUAL_WARN_TOKENS,
    GENERATION_GREEN_STEP_THRESHOLD,
    GENERATION_GREEN_TOKEN_THRESHOLD,
    GENERATION_RED_STEP_THRESHOLD,
    GENERATION_RED_TOKEN_THRESHOLD,
    STANDARD_GREEN_STEP_THRESHOLD,
    STANDARD_GREEN_TOKEN_THRESHOLD,
    STANDARD_RED_STEP_THRESHOLD,
    STANDARD_RED_TOKEN_THRESHOLD,
    SWARM_MSG_HARD_CAP,
    SWARM_MSG_MSS_CAP,
    _get_thresholds_data,
    _workspace_root,
    has_compaction_candidate_bytes,
    reconfigure_streams,
)
from _internal.nk_context_sentry.transcript_tail import (
    _get_transcript_tools,
    analyze_transcript_impl,
    compute_tail_resilience_flags_impl,
    find_last_compaction_offset_impl,
)


class NKContextSentry:
    """Sentinella deterministica del contesto con supporto multi-profilo e Dual-Schema."""

    GREEN_STEP_THRESHOLD = STANDARD_GREEN_STEP_THRESHOLD
    RED_STEP_THRESHOLD = STANDARD_RED_STEP_THRESHOLD
    GREEN_TOKEN_THRESHOLD = STANDARD_GREEN_TOKEN_THRESHOLD
    RED_TOKEN_THRESHOLD = STANDARD_RED_TOKEN_THRESHOLD
    GENERATION_GREEN_STEP_THRESHOLD = GENERATION_GREEN_STEP_THRESHOLD
    GENERATION_RED_STEP_THRESHOLD = GENERATION_RED_STEP_THRESHOLD
    GENERATION_GREEN_TOKEN_THRESHOLD = GENERATION_GREEN_TOKEN_THRESHOLD
    GENERATION_RED_TOKEN_THRESHOLD = GENERATION_RED_TOKEN_THRESHOLD
    GENERATION_ACTUAL_WARN_TOKENS = GENERATION_ACTUAL_WARN_TOKENS
    GENERATION_ACTUAL_RED_TOKENS = GENERATION_ACTUAL_RED_TOKENS
    CARBON_GREEN_STEP_THRESHOLD = CARBON_GREEN_STEP_THRESHOLD
    CARBON_RED_STEP_THRESHOLD = CARBON_RED_STEP_THRESHOLD
    CARBON_GREEN_TOKEN_THRESHOLD = CARBON_GREEN_TOKEN_THRESHOLD
    CARBON_RED_TOKEN_THRESHOLD = CARBON_RED_TOKEN_THRESHOLD
    CARBON_ACTUAL_WARN_TOKENS = CARBON_ACTUAL_WARN_TOKENS
    CARBON_ACTUAL_RED_TOKENS = CARBON_ACTUAL_RED_TOKENS
    ARGON_GREEN_STEP_THRESHOLD = CARBON_GREEN_STEP_THRESHOLD
    ARGON_RED_STEP_THRESHOLD = CARBON_RED_STEP_THRESHOLD
    ARGON_ACTUAL_WARN_TOKENS = ARGON_ACTUAL_WARN_TOKENS
    ARGON_ACTUAL_RED_TOKENS = ARGON_ACTUAL_RED_TOKENS
    SWARM_MSG_MSS_CAP = SWARM_MSG_MSS_CAP
    SWARM_MSG_HARD_CAP = SWARM_MSG_HARD_CAP
    AP_CATALOG = _get_transcript_tools().CANONICAL_AP_TABLE

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        profile: Optional[str] = None,
    ):
        reconfigure_streams()
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )
        if profile is not None:
            self.profile = profile.lower().strip() or "standard"
        else:
            self.profile = (
                os.environ.get("NK_MODEL_PROFILE", "standard").lower().strip()
                or "standard"
            )
        self._thresholds = _get_thresholds_data(
            workspace_root=None if workspace_root is None else self.workspace_root
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Stima il numero di token con rapporto medio 4 caratteri per token."""
        return _estimate_tokens(text)

    @staticmethod
    def format_head_tail(
        traceback_text: str, head_chars: int = 400, tail_chars: int = 800
    ) -> str:
        """Comprime i traceback lunghi preservando testa e coda."""
        return _format_head_tail(traceback_text, head_chars=head_chars, tail_chars=tail_chars)

    @staticmethod
    def _valid_token_int(val: Any) -> Optional[int]:
        """Convalida un conteggio token intero non negativo."""
        return valid_token_int(val)

    @staticmethod
    def _extract_actual_tokens_from_record(data: Dict[str, Any]) -> Optional[int]:
        """Estrae actual_context_tokens da un record JSON."""
        return extract_actual_tokens_from_record(data)

    def get_traffic_light_status(
        self,
        step_count: int,
        estimated_tokens: int,
        profile: Optional[str] = None,
        actual_context_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Calcola lo stato semaforico in base a step, token e profilo."""
        return get_traffic_light_status_impl(
            self,
            step_count,
            estimated_tokens,
            profile=profile,
            actual_context_tokens=actual_context_tokens,
        )

    @staticmethod
    def is_background_task_message(data: Dict[str, Any], content: str) -> bool:
        """Verifica se il record appartiene a un task asincrono in background."""
        return _is_bg_task_msg(data, content)

    def inspect(self, transcript_path: Path) -> Dict[str, Any]:
        """Ispeziona il transcript e restituisce il rapporto completo."""
        return self.analyze_transcript(transcript_path)

    def build_standalone_report(
        self, profile: Optional[str] = None
    ) -> Dict[str, Any]:
        """Costruisce un rapporto GREEN in modalita CLI_STANDALONE."""
        return build_standalone_report_impl(self, profile=profile)

    @staticmethod
    def _has_compaction_candidate_bytes(buf: bytes) -> bool:
        """Esegue un pre-filtro binario rapido."""
        return has_compaction_candidate_bytes(buf)

    @classmethod
    def _find_last_compaction_offset(cls, transcript_path: Path) -> int:
        """Esegue il backscan 64 KB (<= 50 MB) per l'ultimo checkpoint."""
        return find_last_compaction_offset_impl(transcript_path)

    def analyze_transcript(
        self,
        transcript_path: Path,
        profile: Optional[str] = None,
        actual_context_tokens: Optional[int] = None,
        preloaded_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Analizza transcript.jsonl in Dual-Schema."""
        return analyze_transcript_impl(
            self,
            transcript_path,
            profile=profile,
            actual_context_tokens=actual_context_tokens,
            preloaded_records=preloaded_records,
        )

    @staticmethod
    def _compute_tail_resilience_flags(
        transcript_path: Path,
        estimated_tokens: int,
        actual_tokens: Optional[int],
    ) -> Dict[str, Any]:
        """Calcola kv_cache_cold_risk e rpc_stream_burst_risk."""
        return compute_tail_resilience_flags_impl(
            transcript_path, estimated_tokens, actual_tokens
        )


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per la sentinella del contesto."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="NK Hub Generation Context Sentry & Debloating Guard 1.0.0-Generation"
    )
    parser.add_argument("--transcript", type=str, required=False, default=None, help="Percorso opzionale del file transcript.jsonl")
    parser.add_argument("--conversation-id", type=str, required=False, default=None, help="ID opzionale della conversazione attiva")
    parser.add_argument("--profile", type=str, default=None, help="Profilo soglie: standard, generation, carbon o argon")
    parser.add_argument("--actual-context-tokens", type=int, default=None, help="Token di contesto reali osservati")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato in formato JSON")
    parser.add_argument("--verbose", action="store_true", help="Mostra i dettagli completi")

    args = parser.parse_args(argv)
    sentry = NKContextSentry(profile=args.profile)

    resolved_tp: Optional[Path] = None
    if args.transcript:
        resolved_tp = Path(args.transcript)
    else:
        conv_id = (args.conversation_id or os.environ.get("NK_CONVERSATION_ID", "")).strip()
        if conv_id:
            facade_mod = sys.modules.get("nk_context_sentry") or sys.modules.get("scripts.nk_context_sentry")
            loc_fn = getattr(facade_mod, "locate_transcript", None) if facade_mod else None
            if not callable(loc_fn):
                loc_fn = _get_transcript_tools().locate_transcript
            loc_res, loc_code = loc_fn(None, conv_id)
            if loc_code == 0 and loc_res.get("transcript_path"):
                cand = Path(str(loc_res["transcript_path"]))
                if cand.is_file():
                    resolved_tp = cand

    if resolved_tp is not None:
        res = sentry.analyze_transcript(
            resolved_tp,
            profile=args.profile,
            actual_context_tokens=args.actual_context_tokens,
        )
    else:
        res = sentry.build_standalone_report(profile=args.profile)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        status_sym = {"GREEN": "🟢", "YELLOW": "🟡", "WARN": "🟡", "RED": "🔴"}.get(
            res.get("status"), "⚪"
        )
        print(
            f"{status_sym} [NK-CONTEXT-SENTRY] Status: {res.get('status')} | "
            f"Steps: {res.get('step_count')} | Est Tokens: {res.get('estimated_tokens'):,}"
        )
        print(f"  - Recommendation: {res.get('recommendation')}")
        if args.verbose:
            print(f"  - Total chars: {res.get('total_chars', 0):,}")
            print(f"  - Max consecutive direct tools: {res.get('max_consecutive_direct_audit')}")
            print(f"  - Swarm hygiene violations: {res.get('swarm_hygiene_violations_count')}")

    return 0 if res.get("status") in ("GREEN", "YELLOW", "WARN") else 1
