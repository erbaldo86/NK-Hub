#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di routing Mode A/B/C/D e Super Meta-Prompt Gate per NK Hub Generation 1.0.0-Generation.
Modulo: vibe_sprint_router.py.
@domain_id: DOM-01
Calcola la reale profondita AST max_depth e applica la soglia <= 150 LOC per Mode C.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _build_router_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Router Mode A/B/C/D basato sul rischio AST e intento prompt per NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument("--test", action="store_true", help="Esegue l'autotest rapido del router")
    parser.add_argument("--prompt", "--task", dest="prompt", type=str, default="Vibe Sprint Change", help="Descrizione sintetica dell'intento")
    parser.add_argument("--prompt-file", dest="prompt_file", type=str, default=None, help="Legge il prompt da un file UTF-8")
    parser.add_argument("--stdin", action="store_true", help="Legge il prompt completo da stdin")
    parser.add_argument("--transcript", type=str, default=None, help="Percorso al file transcript.jsonl")
    parser.add_argument("--conversation-id", dest="conversation_id", type=str, default=None, help="ID conversazione per l'envelope L0")
    parser.add_argument("--lane-id", dest="lane_id", type=str, default=None, help="Lane di staging isolata (.staging/lanes/<id>/)")
    parser.add_argument("--classify-prompt", nargs="?", const="__USE_PROMPT__", default=None, help="Classifica l'intento del prompt")
    parser.add_argument("--meta-prompt-gate", action="store_true", help="Costruisce e valida MetaPromptGateContract")
    parser.add_argument("--no-gate", action="store_true", help="Disabilita il Meta-Prompt Gate")
    parser.add_argument("--compact", action="store_true", help="Attiva profilo compatto L0")
    parser.add_argument("--auto-bypass-readonly", action="store_true", help="Mantiene bypass automatico Mode D Read-Only")
    parser.add_argument("--force-gate", action="store_true", help="Forza AWAIT_CONFIRM su Mode D")
    parser.add_argument("--mode", type=str, default=None, help="Modalita operativa opzionale")
    parser.add_argument("--files", nargs="*", default=None, help="Elenco file sorgente per il routing")
    parser.add_argument("--changed-lines", type=int, default=None, help="Righe modificate per escalation Mode C -> B")
    parser.add_argument("--validate-generated-prompt", "--lint-prompt", dest="validate_generated_prompt", nargs="?", const="__USE_PROMPT__", type=str, default=None, help="Valida un prompt contro AP-1..AP-16")
    parser.add_argument("--discovery-check", action="store_true", help="Valuta intento Mode D Read-Only Discovery")
    parser.add_argument("--capsule", action="store_true", help="Include la capsula Tier-1")
    parser.add_argument("--json", action="store_true", help="Stampa il verdetto in JSON")
    parser.add_argument("positional_prompt", nargs="*", default=[], help="Prompt posizionale opzionale")
    return parser


if __name__ == "__main__" and any(a in ("-h", "--help") for a in sys.argv[1:]):
    _build_router_cli_parser().parse_args()
    raise SystemExit(0)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _cand in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _cand.exists():
        _cand_s = str(_cand)
        if _cand_s in sys.path:
            sys.path.remove(_cand_s)
        sys.path.insert(0, _cand_s)

if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int
    if hasattr(_stg_int, "__path__"):
        import _internal.nk_common as _stg_nkc
        _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
        _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
        _stg_nkc_dir = str(_SCRIPT_DIR / "_internal" / "nk_common")
        if isinstance(_stg_nkc.__path__, list):
            if _stg_nkc_dir in _stg_nkc.__path__:
                _stg_nkc.__path__.remove(_stg_nkc_dir)
            _stg_nkc.__path__.insert(0, _stg_nkc_dir)

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="vibe_sprint_router")

from _internal.nk_common.paths import reconfigure_streams  # noqa: E402
from _internal.vibe_sprint_router.ast_risk_and_capsule import _ASTDepthVisitor  # noqa: E402, F401
from _internal.vibe_sprint_router.constants_core import (  # noqa: E402, F401
    DOMAIN_TO_NATIVE_SUBAGENT, HANDOFF_V2_END_ACTIVE, HANDOFF_V2_END_PASSIVE,
    HANDOFF_V2_START_ACTIVE, HANDOFF_V2_START_PASSIVE, MODE_D_KEYWORDS, MODE_D_LABEL,
    T12_END, T12_START, MetaPromptGateContract, RoutingIntentContract,
    _AGENT_DIRECTIVE_CUE_RE, _AP10_PASSIVE_SLASH_RE, _AP10_PROHIBITION_CONTEXT_RE,
    _AP12_IMPERATIVE_LEAK_RE, _AP13_COGNITIVE_TUNNELING_RE, _AUDIT_FORENSIC_WORD_RE,
    _BRIEF_HEADER_PHASE_RE, _CLAUSE_SPLIT_RE, _DEFAULT_WORKSPACE_ROOT,
    _DOM04_HIGH_PRIORITY_KWS, _DOM04_TECHNICAL_AUDIT_KEYWORDS, _FORGE_OVERRIDE_KEYWORDS,
    _HANDOFF_MUTATING_ORDER_RE, _HANDOFF_START_PREFIXES, _INTRINSIC_BOOST_KEYWORDS,
    _INTRINSIC_PLAN_KEYWORDS, _LARGE_PROMPT_THRESHOLD, _LAST_NORM_CACHE, _NOMINALIZATION_SUFFIXES,
    _ORCHESTRATOR_ROLES, _OUTBOUND_CODE_EXCLUSION_RE, _OUTBOUND_HANDOFF_RE, _PROHIBITION_LINE_RE,
    _READ_ONLY_ROLES, _ROUTER_MANIFEST_CACHE, _RSI_AUDITOR_KEYWORDS, _RSI_AUDITOR_SKILLS,
    _SHA256_HEX64_RE, _STATE_HANDOFF_MARKERS, _TECH_CAMEL_ALLOWLIST, _USER_TRANSCRIPT_ROLES,
    _ZERO_WIDTH_CHARS, _ZERO_WIDTH_TRANS, _get_ipc_contracts, _normalize_explicit_mode,
    _normalize_input_text, _sanitize_tetralogia_filenames,
)
from _internal.vibe_sprint_router.constants_stt import (  # noqa: E402, F401
    DASHBOARD_NODE_MAP, _ANALYTICAL_INTERROGATIVE_PREFIXES, _ANTI_LOOP_EXEMPT_PREFIXES,
    _BP_ANY_RE, _BP_DIRETTO_RE, _BP_RAW_RE, _CAMEL_GLUED_RE, _CODE_SPAN_RE,
    _DASHBOARD_SELECTOR_RE, _DESTRUCTIVE_OR_WRITE_EXEMPT_BLOCKERS, _EXPLICIT_BYPASS_NEG_RES,
    _EXPLICIT_BYPASS_PHRASES, _FIRST_WORD_RE, _MULTI_SPACE_RE, _NODE_SELECTIONS,
    _ONBOARDING_TRIGGERS, _PLAN_CONFIRMATION_PREFIXES, _PUNCT_NORM_RE, _SALTA_GATE_RE,
    _SENT_SPLIT_RE, _SHELL_META_EXEMPT_BLOCKERS, _SHORT_CONFIRMATIONS,
    _STT_INDEPENDENT_ACTION_START_RE, _TECHNICAL_TASK_EXEMPT_BLOCKERS, _VOICE_CORRECTION_MARKERS,
    _VOICE_CORRECTION_PATTERNS, _VOICE_SELF_CORRECTION_MARKERS, _VOICE_SELF_CORRECTION_SPLIT_RE,
    _extract_primary_stt_clause, _parse_dashboard_selector,
)
from _internal.vibe_sprint_router.domain_matcher import (  # noqa: E402, F401
    _has_audit_forensic_intent, _match_granular_skills, _resolve_native_subagent, _token_matches_keyword,
)
from _internal.vibe_sprint_router.prompt_linter import (  # noqa: E402, F401
    _detect_prompt_role_conflicts, _is_anti_loop_confirmation, _make_lint_violation,
    is_passive_state_handoff, lint_nk_prompt,
)
from _internal.vibe_sprint_router.router_core import (  # noqa: E402, F401
    VibeSprintRouter, build_meta_prompt_envelope, classify_prompt_intent, evaluate_meta_prompt_gate,
    format_compact_env_capsule, format_meta_prompt_markdown, generate_env_capsule, is_gate_exempt,
    load_prewarmed_capsule, normalize_voice_stt_input, resolve_domain_from_manifest,
    resolve_intrinsic_vibe_protocols, validate_generated_prompt,
)
from _internal.vibe_sprint_router.stt_normalize import (  # noqa: E402, F401
    detect_active_continuation_handoff_impl, detect_outbound_handoff_intent_impl,
)
from _internal.vibe_sprint_router.transcript_and_cli import (  # noqa: E402, F401
    _extract_user_text_from_record, _read_latest_user_input_from_transcript,
    _resolve_effective_cli_prompt, dispatch_router_cli, run_test,
)
from _internal.vibe_sprint_router.write_intent import (  # noqa: E402, F401
    _analyze_write_intent, _clause_bounds_at, _has_destructive_shell_command,
    _has_imperative_write_keyword, _is_negated_window_12,
)
from _internal.vibe_sprint_router.write_intent_rules import (  # noqa: E402, F401
    _ADVERSATIVE_TOKENS, _ANALYTICAL_AUDIT_HEADS, _COORDINATED_IMPERATIVE_PREFIX_TOKENS,
    _DESTRUCTIVE_SHELL_CMD_RE, _DOS_DEL_AFTER_SEP_RE, _DOS_DEL_ARG_TAIL, _DOS_DEL_AT_START_RE,
    _EXPLANATORY_CLAUSE_START_RE, _FAST_NOUN_DET_SUFFIXES, _ITALIAN_NOUN_DETERMINERS,
    _LIGHT_EXEC_VERBS, _NEGATION_TOKENS, _READ_ONLY_ROLES_LOWER, _ROLE_CONFLICT_WRITE_RE,
    _SINGLE_OPERA_RE, _SUBORDINATE_WH_TOKENS, _VERB_CONJ_TAIL, _WORD_TOKEN_RE,
    _WRITE_ROOT_GROUPS, _WRITE_ROOT_PATTERNS,
)


def __getattr__(name: str) -> Any:
    """Risolve pigramente SKILL_ROUTING_RULES da routing_helpers senza import eager."""
    if name == "SKILL_ROUTING_RULES":
        val = importlib.import_module("_internal.vibe_sprint_router.routing_helpers").SKILL_ROUTING_RULES
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def detect_outbound_handoff_intent(text: str) -> Optional[str]:
    """Rileva l'intento di serializzazione handoff in uscita (PASSIVE_STANDBY o ACTIVE_CONTINUATION)."""
    return detect_outbound_handoff_intent_impl(text)


def detect_active_continuation_handoff(text: str) -> Optional[Dict[str, Any]]:
    """Rileva un handoff V2 ACTIVE_CONTINUATION verificato."""
    return detect_active_continuation_handoff_impl(text)


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il router Mode A/B/C/D di NK Hub Generation."""
    reconfigure_streams()
    args = _build_router_cli_parser().parse_args(argv)
    return dispatch_router_cli(args)


if __name__ == "__main__":
    sys.exit(main())
