"""Costanti principali, risoluzione root, normalizzazione testo e contratti IPC lazy."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from _internal.nk_common.paths import resolve_scripts_dir, resolve_workspace_root

_SCRIPT_DIR = Path(resolve_scripts_dir(__file__))
_DEFAULT_WORKSPACE_ROOT = Path(resolve_workspace_root(__file__))

for _cand_path in (
    _DEFAULT_WORKSPACE_ROOT,
    _SCRIPT_DIR,
):
    if _cand_path.exists():
        _cand_str = str(_cand_path)
        if _cand_str in sys.path:
            sys.path.remove(_cand_str)
        sys.path.insert(0, _cand_str)

MetaPromptGateContract: Any = None
RoutingIntentContract: Any = None


def _get_ipc_contracts() -> Tuple[Any, Any]:
    """Carica in modo lazy i contratti Pydantic per ridurre la latenza CLI sotto 140 ms."""
    global MetaPromptGateContract, RoutingIntentContract
    if MetaPromptGateContract is None or RoutingIntentContract is None:
        try:
            from schemas.nk_ipc_contracts import (
                MetaPromptGateContract as _MPGC,
                RoutingIntentContract as _RIC,
            )

            MetaPromptGateContract = _MPGC
            RoutingIntentContract = _RIC
        except Exception:
            try:
                from scripts.schemas.nk_ipc_contracts import (
                    MetaPromptGateContract as _MPGC,
                    RoutingIntentContract as _RIC,
                )

                MetaPromptGateContract = _MPGC
                RoutingIntentContract = _RIC
            except Exception:
                pass
        for _mod_name in ("vibe_sprint_router", "scripts.vibe_sprint_router"):
            _fmod = sys.modules.get(_mod_name)
            if _fmod is not None:
                setattr(_fmod, "MetaPromptGateContract", MetaPromptGateContract)
                setattr(_fmod, "RoutingIntentContract", RoutingIntentContract)
    return MetaPromptGateContract, RoutingIntentContract


_LARGE_PROMPT_THRESHOLD: int = 16384
_ZERO_WIDTH_TRANS = str.maketrans("", "", "\u200b\u200c\u200d\ufeff\u2060")
_ZERO_WIDTH_CHARS: Tuple[str, ...] = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060")
_LAST_NORM_CACHE: Tuple[Optional[str], str] = (None, "")


def _normalize_input_text(raw_text: Optional[str]) -> str:
    """Applica normalizzazione Unicode NFKC e rimuove i caratteri zero-width invisibili."""
    global _LAST_NORM_CACHE
    if not raw_text:
        return ""
    if raw_text.isascii():
        return raw_text
    if _LAST_NORM_CACHE[0] is raw_text:
        return _LAST_NORM_CACHE[1]
    s = (
        raw_text
        if unicodedata.is_normalized("NFKC", raw_text)
        else unicodedata.normalize("NFKC", raw_text)
    )
    if any(zw in s for zw in _ZERO_WIDTH_CHARS):
        s = s.translate(_ZERO_WIDTH_TRANS)
    _LAST_NORM_CACHE = (raw_text, s)
    return s


def _normalize_explicit_mode(mode: Optional[str]) -> Optional[str]:
    """Normalizza il valore esplicito di --mode nei letterali canonici mode_a..mode_d o verify."""
    if not mode:
        return None
    norm_m = mode.strip().lower().replace("-", "_")
    if norm_m in ("mode_a", "mode_b", "mode_c", "mode_d", "verify"):
        return norm_m
    if norm_m in ("a", "b", "c", "d"):
        return f"mode_{norm_m}"
    return None


MODE_D_KEYWORDS: Tuple[str, ...] = (
    "audit",
    "controllo tas",
    "audit tas",
    "incongruenze",
    "incongruenza",
    "benchmark",
    "discovery",
    "ricerca",
    "analizza",
    "analisi",
    "quanti bandi",
    "copertura",
    "censimento",
    "mappatura",
    "esplora",
    "read-only",
    "readonly",
    "report analitico",
    "stato dell'arte",
    "spiega",
    "perché",
    "perche",
    "cosa fa",
    "come funziona",
    "review",
    "elenca",
    "dove",
    "quali",
    "quanti",
)

MODE_D_LABEL: str = (
    "Mode D (Analytical Discovery & Benchmark - 100% Read-Only + MCP/Web)"
)

DOMAIN_TO_NATIVE_SUBAGENT: Dict[str, str] = {
    "DOM-01": "Orchestrator-Direct",
    "DOM-02": "NK-Specifier-Agent",
    "DOM-03": "NK-Builder-Agent",
    "DOM-04": "NK-Security-DAST-Auditor",
    "DOM-05": "NK-Scribe-Agent",
}

_READ_ONLY_ROLES: Tuple[str, ...] = (
    "NK-Oracle-Evaluator",
    "NK-Bug-Diagnostic-Engine",
    "NK-Ideator",
    "NK-Security-DAST-Auditor",
    "NK-Security-Auditor",
    "NK-RSI-Auditor",
    "NK-Arch-Specifier",
)
_ORCHESTRATOR_ROLES: Tuple[str, ...] = (
    "NK-Orchestrator",
)

_RSI_AUDITOR_SKILLS = frozenset({"NK-Oracle-Evaluator"})
_RSI_AUDITOR_KEYWORDS: Tuple[str, ...] = (
    "rsi",
    "oracolo",
    "oracle",
    "cold review",
    "tetralogia",
)
_FORGE_OVERRIDE_KEYWORDS: Tuple[str, ...] = (
    "forgia",
    "forge",
    "playbook",
    "skill.md",
    "agent.md",
    "strict_boundaries",
)
_NOMINALIZATION_SUFFIXES: Tuple[str, ...] = (
    "zione",
    "zioni",
    "mento",
    "menti",
)
from _internal.vibe_sprint_router.keywords_core import *  # noqa: F401,F403

def _sanitize_tetralogia_filenames(text_low: str) -> str:
    """Protegge i nomi file della Pentad da falsi positivi di sottostringa."""
    if ".md" not in text_low:
        return text_low
    sanitized = text_low
    for fname in (
        "implementation_plan.md",
        "concept_map.md",
        "structural_tree.md",
        "repo_map.md",
    ):
        sanitized = sanitized.replace(fname, " ")
    return sanitized


_DOM03_HIGH_PRIORITY_KWS = frozenset(
    {
        "refactoring",
        "refactor",
        "surgical refactor",
        "refactoring chirurgico",
        "estrai modulo",
        "fastapi",
        "asyncio",
        "pydantic",
        "playwright",
        "react",
        "typescript",
        "tailwind",
        "nextjs",
        "next.js",
        "sqlite",
    }
)
_DOM04_HIGH_PRIORITY_KWS = frozenset(
    {
        "stress test",
        "sast",
        "dast",
        "rca",
        "red team",
        "red-team",
        "sbfl",
        "ochiai",
        "controllo tas",
        "audit tas",
        "audit forense",
        "audit architetturale",
        "audit multilivello",
        "audit multi-livello",
        "analizza refactoring",
        "analisi refactoring",
        "analizza il refactoring",
        "analisi del refactoring",
        "incongruenze",
        "incongruenza",
    }
)
_AUDIT_FORENSIC_WORD_RE = re.compile(
    r"\b(?:audit|tas|incongruenz\w*|forens\w*)\b"
    r"|(?:analizz\w*|analisi|verific\w*|controll\w*)\s+(?:il\s+|la\s+|del\s+|della\s+|sul\s+|sulla\s+)?refactor\w*",
    re.IGNORECASE,
)


_USER_TRANSCRIPT_ROLES: Set[str] = {
    "user",
    "user_input",
    "user_explicit",
    "human",
}
