#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di routing Mode A/B/C/D e Super Meta-Prompt Gate per Nexus Keystone v4.1.0.
Calcola la reale profondita AST max_depth e applica la soglia <= 150 LOC per Mode C.
Supporta Mode D, normalizzazione vocale STT e risoluzione O(1) tramite nk_registry_manifest.json.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_WORKSPACE_ROOT = (
    _SCRIPT_DIR.parent.parent
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR.parent
)

for _cand_path in (
    _DEFAULT_WORKSPACE_ROOT / ".staging" / "scripts",
    _DEFAULT_WORKSPACE_ROOT / "scripts",
    _SCRIPT_DIR,
):
    if _cand_path.exists() and str(_cand_path) not in sys.path:
        sys.path.insert(0, str(_cand_path))

try:
    from schemas.nk_ipc_contracts import MetaPromptGateContract
except Exception:
    try:
        from scripts.schemas.nk_ipc_contracts import MetaPromptGateContract
    except Exception:
        MetaPromptGateContract = None  # type: ignore[assignment]

MODE_D_KEYWORDS: Tuple[str, ...] = (
    "audit",
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
)

MODE_D_LABEL: str = (
    "Mode D (Analytical Discovery & Benchmark - 100% Read-Only + MCP/Web)"
)

DOMAIN_TO_NATIVE_SUBAGENT: Dict[str, str] = {
    "DOM-01": "NK-Specifier-Agent",
    "DOM-02": "NK-Specifier-Agent",
    "DOM-03": "NK-Builder-Agent",
    "DOM-04": "NK-Security-DAST-Auditor",
    "DOM-05": "NK-Scribe-Agent",
}

_RSI_AUDITOR_SKILLS = frozenset(
    {"NK-Oracle-Evaluator", "NK-State-Router", "NK-Plan-Aligner"}
)
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
    "strict_boundaries",
)
_WRITE_ACTION_KEYWORDS: Tuple[str, ...] = (
    "implementa",
    "sviluppa",
    "refactoring",
    "refactor",
    "modifica",
    ".staging",
    "forgia",
    "crea",
    "sincronizza",
    "allinea",
    "progetta",
)
_NOMINALIZATION_SUFFIXES: Tuple[str, ...] = (
    "zione",
    "zioni",
    "mento",
    "menti",
)
_DOM04_TECHNICAL_AUDIT_KEYWORDS: Tuple[str, ...] = (
    "sast",
    "dast",
    "e2e",
    "puppeteer",
    "chrome-devtools",
    "sbfl",
    "ochiai",
    "cold review",
    "6 gate",
    "oracolo",
)

_SHORT_CONFIRMATIONS: Set[str] = {
    "ok",
    "si",
    "sì",
    "procedi",
    "confermo",
    "vai",
    "proceed",
    "premi proceed",
}
_ONBOARDING_TRIGGERS: Set[str] = {
    "avvia ambiente nk",
    "avvia nk hub",
    "avvia nk",
    "avvia hub",
    "start nk",
    "start hub",
    "attiva nk",
    "attiva ambiente nk",
}
_NODE_SELECTIONS: Set[str] = {f"[{i}]" for i in range(15)} | {
    str(i) for i in range(15)
}
_BYPASS_AND_TOGGLE_MARKERS: Tuple[str, ...] = (
    "!diretto",
    "!raw",
    "salta gate",
    "disattiva prompt gate",
    "attiva prompt gate",
    "nk refiner",
)
_VOICE_CORRECTION_MARKERS: Tuple[str, ...] = (
    "anzi no",
    "o meglio",
    "volevo dire",
    "anzi",
    "scusa",
    "praticamente",
)

SKILL_ROUTING_RULES: Tuple[Tuple[str, str, str, str, Tuple[str, ...]], ...] = (
    (
        "NK-Plan-Aligner",
        "DOM-01",
        "GOV_AND_ROUTING",
        "NK-RSI-Auditor",
        (
            "allinea 1:1",
            "allinea",
            "1:1",
            "tetralogia",
            "concept_map.md",
            "concept_map",
            "implementation_plan.md",
            "turno 4",
            "auto-brief",
        ),
    ),
    (
        "NK-Oracle-Evaluator",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-RSI-Auditor",
        (
            "cold review",
            "6 gate",
            "oracolo",
            "oracle",
            "delta_k",
            "convergenza rsi",
        ),
    ),
    (
        "NK-State-Router",
        "DOM-01",
        "GOV_AND_ROUTING",
        "NK-RSI-Auditor",
        (
            "dag di kahn",
            "dag",
            "kahn",
            "drift sha",
        ),
    ),
    (
        "NK-Security-Auditor",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-Security-DAST-Auditor",
        (
            "sast",
            "audit di sicurezza",
            "sicurezza",
            "l1/l2/l3",
            "l1",
            "l2",
            "l3",
            "security",
            "vulnerabilita",
            "exploit",
            "cove",
        ),
    ),
    (
        "NK-Dynamic-Sandbox-StressTester",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-Security-DAST-Auditor",
        (
            "dast",
            "sandbox",
            "e2e",
            "puppeteer",
            "chrome-devtools-mcp",
            "chrome-devtools",
            "lighthouse",
            "browser",
            "stress",
        ),
    ),
    (
        "NK-Bug-Diagnostic-Engine",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-Security-DAST-Auditor",
        (
            "sbfl",
            "ochiai",
            "tarantula",
            "dstar",
            "causa radice",
            "rca",
            "falsi bug",
            "crash",
            "diagnosi",
        ),
    ),
    (
        "NK-Agent-Instruction-Forge",
        "DOM-03",
        "BUILD_AND_HEAL",
        "NK-Builder-Agent",
        (
            "forgia",
            "forge",
            "skill.md",
            "playbook",
            "metaprompt",
            "strict_boundaries",
        ),
    ),
    (
        "NK-Delta-Architect",
        "DOM-03",
        "BUILD_AND_HEAL",
        "NK-Builder-Agent",
        (
            "react",
            "typescript",
            "tailwind",
            "nextjs",
            "next.js",
            "html",
            "css",
            "fullstack",
            "full-stack",
            "refactoring chirurgico",
            "chirurgico",
            "multi-file",
            "multifile",
            "delta",
        ),
    ),
    (
        "NK-Python-Async-Builder",
        "DOM-03",
        "BUILD_AND_HEAL",
        "NK-Builder-Agent",
        (
            "fastapi",
            "pydantic",
            "asincrono",
            "async",
            "asyncio",
            "sqlite",
            "endpoint",
        ),
    ),
    (
        "NK-App-UX-Architect",
        "DOM-02",
        "IDEATION_AND_ARCH",
        "NK-Specifier-Agent",
        (
            "ux/ui",
            "ux",
            "ui",
            "8px",
            "hsl",
            "palette",
            "generative_ui",
            "design system",
            "bounded context",
            "user journey",
            "canvas architetturale",
        ),
    ),
    (
        "NK-Backend-Architect",
        "DOM-02",
        "IDEATION_AND_ARCH",
        "NK-Specifier-Agent",
        (
            "openapi",
            "architettura backend",
            "contratti dati",
        ),
    ),
    (
        "NK-Scribe",
        "DOM-05",
        "MEMORY_TELEMETRY_AND_DOCS",
        "NK-Scribe-Agent",
        (
            "sincronizza",
            "patch_notes.md",
            "patch_notes",
            "quality_baseline.json",
            "quality_baseline",
            "changelog",
            "scribe",
            "readme",
        ),
    ),
    (
        "NK-Episodic-Memory-Engine",
        "DOM-05",
        "MEMORY_TELEMETRY_AND_DOCS",
        "NK-Scribe-Agent",
        (
            "memoria 3-tier",
            "memoria episodica",
            "memoria",
            "memory",
            "3-tier",
            "bm25",
            "rrf",
            "recall",
        ),
    ),
    (
        "NK-Ideator",
        "DOM-02",
        "IDEATION_AND_ARCH",
        "NK-Specifier-Agent",
        (
            "ricerca competitor",
            "tavily",
            "benchmark analitico",
            "stato dell'arte",
            "ricerca web",
            "ideazione",
            "scamper",
            "quanti bandi",
            "copertura bandi",
        ),
    ),
)

_ROUTER_MANIFEST_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def _sanitize_tetralogia_filenames(text_low: str) -> str:
    """Protegge i nomi file della Tetralogia da falsi positivi di sottostringa."""
    sanitized = text_low
    for fname in (
        "implementation_plan.md",
        "concept_map.md",
        "structural_tree.md",
        "repo_map.md",
    ):
        sanitized = sanitized.replace(fname, " ")
    return sanitized


def _has_imperative_write_keyword(clean_text: str) -> bool:
    """Verifica la presenza di verbi imperativi di scrittura escludendo nominalizzazioni astratte."""
    text_low = (clean_text or "").strip().lower()
    if not text_low:
        return False
    if ".staging" in text_low:
        return True
    tokens = re.findall(r"[a-z0-9_àèéìòù]+", text_low)
    for tok in tokens:
        if tok.endswith(_NOMINALIZATION_SUFFIXES):
            continue
        for wkw in _WRITE_ACTION_KEYWORDS:
            if wkw == ".staging":
                continue
            if tok == wkw or re.fullmatch(
                rf"{re.escape(wkw)}(?:re|lo|la|li|le)?", tok
            ):
                return True
    return False


def _token_matches_keyword(
    kw: str,
    text_low: str,
    tokens: Set[str],
    min_sub_len: int = 4,
) -> bool:
    """Verifica il matching tra keyword e testo escludendo falsi positivi da nominalizzazioni."""
    kw_low = kw.lower()
    if " " in kw_low or "." in kw_low or "/" in kw_low or "-" in kw_low:
        return kw_low in text_low
    if kw_low in tokens:
        return True
    if len(kw_low) >= min_sub_len and kw_low in text_low:
        kw_is_nominal = kw_low.endswith(_NOMINALIZATION_SUFFIXES)
        for tok in tokens:
            if not kw_is_nominal and tok.endswith(_NOMINALIZATION_SUFFIXES):
                continue
            if kw_low in tok:
                return True
    return False


def _match_granular_skills(text_low: str) -> List[Tuple[str, str, str, str, List[str]]]:
    """Valuta le regole granulari di skill restituendo le corrispondenze ordinate per punteggio."""
    tokens = set(re.findall(r"[a-z0-9_àèéìòù]+", text_low))
    matches: List[Tuple[int, int, str, str, str, str, List[str]]] = []

    for idx, (sk_name, dom_id, dom_name, subagent, kws) in enumerate(
        SKILL_ROUTING_RULES
    ):
        hits: List[str] = []
        for kw in kws:
            if _token_matches_keyword(kw, text_low, tokens, min_sub_len=5):
                hits.append(kw)
        if hits:
            matches.append(
                (len(hits), -idx, sk_name, dom_id, dom_name, subagent, hits)
            )

    matches.sort(reverse=True)
    return [
        (sk_name, dom_id, dom_name, subagent, hits)
        for _, _, sk_name, dom_id, dom_name, subagent, hits in matches
    ]


def _resolve_native_subagent(
    domain_id: str,
    matched_skill: Optional[str] = None,
    text: str = "",
) -> str:
    """Risolve il Sub-Agente Nativo instradando query RSI e Oracolo su NK-RSI-Auditor."""
    text_low = (text or "").strip().lower()
    if matched_skill == "NK-Agent-Instruction-Forge" or any(
        fk in text_low for fk in _FORGE_OVERRIDE_KEYWORDS
    ):
        return "NK-Builder-Agent"
    if matched_skill and matched_skill in _RSI_AUDITOR_SKILLS:
        return "NK-RSI-Auditor"
    if text_low:
        tokens = set(
            "".join(ch if ch.isalnum() or ch == "_" else " " for ch in text_low).split()
        )
        for kw in _RSI_AUDITOR_KEYWORDS:
            if (" " in kw and kw in text_low) or kw in tokens:
                return "NK-RSI-Auditor"
    return DOMAIN_TO_NATIVE_SUBAGENT.get(domain_id, "NK-Builder-Agent")


class _ASTDepthVisitor(ast.NodeVisitor):
    """Calcola la profondita massima di annidamento del flusso di controllo AST."""

    _CONTROL_NODES = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
    )

    def __init__(self) -> None:
        self.current_depth: int = 0
        self.max_depth: int = 0

    def generic_visit(self, node: ast.AST) -> None:
        is_branch = isinstance(node, self._CONTROL_NODES)
        if is_branch:
            self.current_depth += 1
            if self.current_depth > self.max_depth:
                self.max_depth = self.current_depth
        super().generic_visit(node)
        if is_branch:
            self.current_depth -= 1


class VibeSprintRouter:
    """Valuta il rischio strutturale AST e seleziona la modalita operativa (Mode A, B, C o D)."""

    MODE_C_MAX_LOC: int = 150
    DISCOVERY_KEYWORDS: Tuple[str, ...] = MODE_D_KEYWORDS

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        if workspace_root is None:
            self.workspace_root = _DEFAULT_WORKSPACE_ROOT
        else:
            self.workspace_root = Path(workspace_root).resolve()
        self.staging_dir = self.workspace_root / ".staging"

    def _load_registry_manifest(self) -> Dict[str, Any]:
        """Carica nk_registry_manifest.json da staging o root con cache statica O(1)."""
        candidates = (
            self.staging_dir / "nk_genome" / "nk_registry_manifest.json",
            self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
            _DEFAULT_WORKSPACE_ROOT
            / ".staging"
            / "nk_genome"
            / "nk_registry_manifest.json",
            _DEFAULT_WORKSPACE_ROOT / "nk_genome" / "nk_registry_manifest.json",
        )
        for cand in candidates:
            if cand.exists() and cand.is_file():
                try:
                    st = cand.stat()
                    key = str(cand)
                    cached = _ROUTER_MANIFEST_CACHE.get(key)
                    if (
                        cached is not None
                        and cached[0] == st.st_mtime_ns
                        and cached[1] == st.st_size
                    ):
                        return cached[2]
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        _ROUTER_MANIFEST_CACHE[key] = (
                            st.st_mtime_ns,
                            st.st_size,
                            data,
                        )
                        return data
                except Exception:
                    pass
        return {}

    def normalize_voice_stt_input(self, raw_prompt: str) -> Dict[str, Any]:
        """Normalizza il testo dettato a voce separando CamelCase fusi ed estraendo correzioni."""
        text = (raw_prompt or "").strip()
        if not text:
            return {
                "raw_prompt": raw_prompt or "",
                "cleaned_prompt": "",
                "voice_corrections_applied": [],
                "camelcase_splits": [],
                "bypass_requested": False,
            }

        code_spans: List[str] = []

        def _stash_code(match: re.Match[str]) -> str:
            idx = len(code_spans)
            code_spans.append(match.group(0))
            return f"__NK_CODE_{idx}__"

        masked = re.sub(r"(`{1,3}[\s\S]*?`{1,3})", _stash_code, text)
        voice_corrections: List[str] = []
        camelcase_splits: List[str] = []
        bypass_requested = False

        for bp_marker in ("!diretto", "!raw", "salta gate"):
            pat = re.compile(rf"(?i)(?:^|\s){re.escape(bp_marker)}(?=\s|$|[.,;!?])")
            if pat.search(masked):
                bypass_requested = True
                masked = pat.sub(" ", masked).strip()

        camel_pat = re.compile(r"([a-zàèéìòù]{2,})([A-Z][a-zàèéìòù]+)")

        def _split_camel(match: re.Match[str]) -> str:
            orig = match.group(0)
            rep = f"{match.group(1)} {match.group(2)}"
            camelcase_splits.append(f"{orig} -> {rep}")
            voice_corrections.append(f"{orig} -> {rep}")
            return rep

        masked = camel_pat.sub(_split_camel, masked)

        for marker in _VOICE_CORRECTION_MARKERS:
            m_pat = re.compile(rf"(?i)\b{re.escape(marker)}\b")
            if m_pat.search(masked):
                if marker in ("anzi no", "o meglio", "volevo dire"):
                    parts = m_pat.split(masked, maxsplit=1)
                    if len(parts) == 2:
                        before_part = parts[0].strip(" ,;:-")
                        after_part = parts[1].strip(" ,;:-")
                        if after_part:
                            voice_corrections.append(
                                f"{before_part or marker} -> {after_part}"
                            )
                            if len(after_part.split()) >= 2:
                                masked = after_part
                            else:
                                masked = f"{before_part} {after_part}".strip()
                else:
                    voice_corrections.append(f"{marker} -> (rimosso filler vocale)")
                    masked = m_pat.sub(" ", masked)

        masked = re.sub(r"\s+", " ", masked).strip()
        for idx, span in enumerate(code_spans):
            masked = masked.replace(f"__NK_CODE_{idx}__", span)

        return {
            "raw_prompt": raw_prompt,
            "cleaned_prompt": masked,
            "voice_corrections_applied": voice_corrections,
            "camelcase_splits": camelcase_splits,
            "bypass_requested": bypass_requested,
        }

    def is_gate_exempt(self, raw_prompt: str) -> bool:
        """Verifica le 5 esenzioni anti-loop per il Super Meta-Prompt Gate (RULE-00.6)."""
        text = (raw_prompt or "").strip()
        if not text:
            return True
        text_low = text.lower()
        if "<env_capsule>" in text_low:
            return True
        for marker in _BYPASS_AND_TOGGLE_MARKERS:
            if marker in text_low:
                return True
        norm = text_low.strip(" .!?;:\"'")
        if norm in _SHORT_CONFIRMATIONS:
            return True
        if norm in _ONBOARDING_TRIGGERS:
            return True
        if norm in _NODE_SELECTIONS:
            return True
        return False

    def build_meta_prompt_envelope(
        self,
        prompt: str,
        gate_enabled: bool = True,
        gate_mode: str = "CONFIRM",
        files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Costruisce e valida il contratto MetaPromptGateContract di Livello 0."""
        stt_info = self.normalize_voice_stt_input(prompt)
        exempt = self.is_gate_exempt(prompt) or bool(stt_info.get("bypass_requested"))
        cleaned_prompt = stt_info["cleaned_prompt"] or (prompt or "").strip()
        intent = self.classify_prompt_intent(cleaned_prompt, files=files)

        effective_mode = (gate_mode or "CONFIRM").strip().upper()
        if effective_mode not in ("CONFIRM", "ECHO", "OFF"):
            effective_mode = "CONFIRM"

        bypassed = bool(exempt or (not gate_enabled) or effective_mode == "OFF")
        if bypassed:
            fsm_state = "BYPASSED"
        elif effective_mode == "ECHO":
            fsm_state = "CONFIRMED"
        else:
            fsm_state = "AWAIT_CONFIRM"

        raw_clauses = [
            c.strip(" .;")
            for c in re.split(r"(?:[.;\n]+|\b(?:inoltre|poi)\b)", cleaned_prompt)
            if c and len(c.strip(" .;")) >= 3
        ]
        if not raw_clauses:
            raw_clauses = [cleaned_prompt or "Eseguire il task richiesto"]

        requirements_r_ids = [
            f"R{idx}: {clause}" for idx, clause in enumerate(raw_clauses[:6], start=1)
        ]

        rec_mode = str(intent.get("recommended_mode", "mode_c"))
        primary_ag = str(intent.get("primary_agent", "NK-Python-Async-Builder"))
        native_sub = str(intent.get("native_subagent", "NK-Builder-Agent"))

        if rec_mode == "mode_d":
            out_of_scope = [
                "Qualsiasi modifica ai file del repository (esecuzione 100% Read-Only)",
                "Esecuzione di commit transazionali 2PC",
            ]
        else:
            out_of_scope = [
                "Modifica diretta dei file di produzione fuori da .staging/",
                "Uso di MagicMock o stub sintetici vietati da RULE-01.2",
            ]

        conceptual_mirror = (
            f"Obiettivo: {cleaned_prompt[:140]} "
            f"(Modalita: {rec_mode}, Skill: {primary_ag}, Sub-Agente: {native_sub})."
        )
        optimized_meta_prompt = (
            f"[META-PROMPT L0 | Mode: {rec_mode} | Skill: {primary_ag}]\n"
            f"Obiettivo strutturato: {cleaned_prompt}\n"
            f"Requisiti: {'; '.join(requirements_r_ids)}"
        )

        hash_input = f"{optimized_meta_prompt}|{'|'.join(requirements_r_ids)}"
        intent_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        brief_id = f"IB-{time.strftime('%Y%m%d')}-{intent_hash[:6].upper()}"

        payload: Dict[str, Any] = {
            "brief_id": brief_id,
            "fsm_state": fsm_state,
            "gate_mode": effective_mode,
            "enabled": bool(gate_enabled and effective_mode != "OFF"),
            "bypassed": bypassed,
            "conceptual_mirror": conceptual_mirror,
            "optimized_meta_prompt": optimized_meta_prompt,
            "requirements_r_ids": requirements_r_ids,
            "voice_corrections_applied": list(
                stt_info.get("voice_corrections_applied", [])
            ),
            "out_of_scope": out_of_scope,
            "ambiguities": [],
            "recommended_mode": rec_mode,
            "primary_agent": primary_ag,
            "native_subagent": native_sub,
            "intent_hash_sha256": intent_hash,
            "ttl_seconds": 1800,
        }

        if MetaPromptGateContract is not None:
            validated = MetaPromptGateContract(**payload)
            return validated.model_dump()
        return payload

    def resolve_domain_from_manifest(self, prompt: str) -> Dict[str, Any]:
        """Risolve in O(1) il dominio funzionale DOM-01..DOM-05 e le skill interrogando il manifesto SSOT."""
        text_lower = (prompt or "").strip().lower()
        manifest = self._load_registry_manifest()
        domains = manifest.get("domains", {})
        skills_index = manifest.get("skills_index", {})
        scripts_index = manifest.get("scripts_index", {})
        dispatch_table = manifest.get("intent_dispatch_table", {})

        # 1. Riferimento esplicito a ID dominio nel prompt (es. DOM-04)
        for dom_id, dom_meta in domains.items():
            if (
                dom_id.lower() in text_lower
                or dom_meta.get("name", "").lower() in text_lower
            ):
                primary_sk = dom_meta.get("primary_skill", "NK-Master-Hub")
                return {
                    "domain_id": dom_id,
                    "domain_name": dom_meta.get("name", ""),
                    "primary_skill": primary_sk,
                    "matched_skills": [primary_sk],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [dom_id],
                }

        # 2. Riferimento esplicito a una skill nel prompt
        for sk_name, sk_meta in skills_index.items():
            if sk_name.lower() in text_lower:
                dom_id = sk_meta.get("domain_id", "DOM-01")
                return {
                    "domain_id": dom_id,
                    "domain_name": sk_meta.get("domain_name", "GOV_AND_ROUTING"),
                    "primary_skill": sk_name,
                    "matched_skills": [sk_name],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=sk_name, text=text_lower
                    ),
                    "matched_triggers": [sk_name],
                }

        # 3. Regole granulari multi-skill per intenti composti o specialistici
        skill_matches = _match_granular_skills(text_lower)
        if skill_matches:
            primary_sk, dom_id, dom_name, subagent, triggers = skill_matches[0]
            matched_skills = [m[0] for m in skill_matches]
            all_triggers: List[str] = []
            for m in skill_matches:
                for t in m[4]:
                    if t not in all_triggers:
                        all_triggers.append(t)
            return {
                "domain_id": dom_id,
                "domain_name": dom_name,
                "primary_skill": primary_sk,
                "matched_skills": matched_skills,
                "native_subagent": subagent,
                "matched_triggers": all_triggers or triggers,
            }

        # 4. Riferimento esplicito a uno script Python nel prompt
        for sc_name, sc_meta in scripts_index.items():
            if sc_name.lower() in text_lower:
                dom_id = sc_meta.get("domain_id", "DOM-03")
                dom_meta = domains.get(dom_id, {})
                primary_sk = dom_meta.get("primary_skill", "NK-Python-Async-Builder")
                return {
                    "domain_id": dom_id,
                    "domain_name": sc_meta.get("domain_name", "BUILD_AND_HEAL"),
                    "primary_skill": primary_sk,
                    "matched_skills": [primary_sk],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [sc_name],
                }

        # 5. Punteggio keyword tramite domains e intent_dispatch_table (con protezione Tetralogia e nominalizzazioni)
        clean_text = _sanitize_tetralogia_filenames(text_lower)
        tokens = set(
            "".join(
                ch if ch.isalnum() or ch == "_" else " " for ch in clean_text
            ).split()
        )
        best_dom_id = ""
        best_score = 0
        best_triggers: List[str] = []

        for dom_id, dom_meta in domains.items():
            kws = dom_meta.get("keywords", [])
            hits = [
                kw
                for kw in kws
                if _token_matches_keyword(kw, clean_text, tokens, min_sub_len=4)
            ]
            if len(hits) > best_score:
                best_score = len(hits)
                best_dom_id = dom_id
                best_triggers = hits

        if best_dom_id and best_score > 0:
            dom_meta = domains[best_dom_id]
            primary_sk = dom_meta.get("primary_skill", "NK-Master-Hub")
            return {
                "domain_id": best_dom_id,
                "domain_name": dom_meta.get("name", ""),
                "primary_skill": primary_sk,
                "matched_skills": [primary_sk],
                "native_subagent": _resolve_native_subagent(
                    best_dom_id, matched_skill=primary_sk, text=clean_text
                ),
                "matched_triggers": best_triggers,
            }

        for kw, entry in dispatch_table.items():
            if _token_matches_keyword(kw, clean_text, tokens, min_sub_len=4):
                dom_id = entry.get("domain_id", "DOM-03")
                primary_sk = entry.get("primary_agent", "NK-Python-Async-Builder")
                return {
                    "domain_id": dom_id,
                    "domain_name": entry.get("domain_name", "BUILD_AND_HEAL"),
                    "primary_skill": primary_sk,
                    "matched_skills": [primary_sk],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=clean_text
                    ),
                    "matched_triggers": [kw],
                }

        is_disc = any(kw in clean_text for kw in self.DISCOVERY_KEYWORDS)
        if is_disc:
            return {
                "domain_id": "DOM-02",
                "domain_name": "IDEATION_AND_ARCH",
                "primary_skill": "NK-Ideator",
                "matched_skills": ["NK-Ideator"],
                "native_subagent": "NK-Specifier-Agent",
                "matched_triggers": [],
            }
        return {
            "domain_id": "DOM-03",
            "domain_name": "BUILD_AND_HEAL",
            "primary_skill": "NK-Python-Async-Builder",
            "matched_skills": ["NK-Python-Async-Builder"],
            "native_subagent": _resolve_native_subagent(
                "DOM-03", matched_skill="NK-Python-Async-Builder", text=clean_text
            ),
            "matched_triggers": [],
        }

    def classify_prompt_intent(
        self,
        prompt: str,
        files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Classifica il prompt, attiva Mode D su discovery pura e risolve skill e sub-agente."""
        text_lower = (prompt or "").strip().lower()
        clean_text = _sanitize_tetralogia_filenames(text_lower)
        has_code_files = bool(files and len(files) > 0)
        matched = [kw for kw in self.DISCOVERY_KEYWORDS if kw in text_lower]
        domain_info = self.resolve_domain_from_manifest(prompt)

        has_write_intent = _has_imperative_write_keyword(
            clean_text
        ) or _has_imperative_write_keyword(text_lower)

        is_dom04_tech_audit = domain_info["domain_id"] == "DOM-04" and any(
            tkw in text_lower for tkw in _DOM04_TECHNICAL_AUDIT_KEYWORDS
        )

        if matched and not has_code_files and not has_write_intent:
            if is_dom04_tech_audit:
                primary_ag = domain_info.get("primary_skill", "NK-Security-Auditor")
                native_sub = domain_info.get(
                    "native_subagent", "NK-Security-DAST-Auditor"
                )
                matched_sk = domain_info.get("matched_skills", [primary_ag])
                dom_id = domain_info["domain_id"]
                dom_name = domain_info["domain_name"]
            else:
                primary_ag = "NK-Ideator"
                native_sub = "NK-Specifier-Agent"
                matched_sk = ["NK-Ideator"]
                dom_id = (
                    "DOM-02"
                    if domain_info["domain_id"] == "DOM-03"
                    else domain_info["domain_id"]
                )
                dom_name = (
                    "IDEATION_AND_ARCH"
                    if dom_id == "DOM-02"
                    else domain_info["domain_name"]
                )

            return {
                "recommended_mode": "mode_d",
                "mode": MODE_D_LABEL,
                "mode_label": MODE_D_LABEL,
                "is_discovery": True,
                "read_only": True,
                "matched_keywords": matched,
                "primary_agent": primary_ag,
                "matched_skills": matched_sk,
                "native_subagent": native_sub,
                "fast_bypass_eligible": False,
                "domain_id": dom_id,
                "domain_name": dom_name,
                "tools_allowed": [
                    "view_file",
                    "search_web",
                    "read_url_content",
                    "call_mcp_tool",
                    "list_resources",
                    "read_resource",
                ],
                "prompt": prompt,
                "reason": (
                    f"Analytical discovery intent detected via keywords: {matched}"
                ),
            }

        primary_ag = domain_info.get("primary_skill", "NK-Python-Async-Builder")
        matched_sk = domain_info.get("matched_skills", [primary_ag])
        native_sub = domain_info.get(
            "native_subagent",
            _resolve_native_subagent(
                domain_info["domain_id"],
                matched_skill=primary_ag,
                text=text_lower,
            ),
        )

        if any(
            k in text_lower
            for k in (
                "allinea 1:1",
                "turno 4",
                "auto-brief",
                "cold review",
                "6 gate",
                "oracolo",
                "multi-file",
                "multifile",
            )
        ):
            rec_mode = "mode_a"
        elif any(
            k in text_lower
            for k in ("sbfl", "ochiai", "causa radice", "rca", "falsi bug")
        ):
            rec_mode = "mode_b"
        else:
            rec_mode = "mode_c"

        return {
            "recommended_mode": rec_mode,
            "mode": "Mode A/B/C (Code & Specification Routing)",
            "mode_label": "Mode A/B/C (Code & Specification Routing)",
            "is_discovery": False,
            "read_only": False,
            "matched_keywords": matched,
            "primary_agent": primary_ag,
            "matched_skills": matched_sk,
            "native_subagent": native_sub,
            "fast_bypass_eligible": rec_mode == "mode_c",
            "domain_id": domain_info["domain_id"],
            "domain_name": domain_info["domain_name"],
            "tools_allowed": [],
            "prompt": prompt,
            "reason": "Standard implementation or file modification routing.",
        }

    def compute_ast_risk_score(
        self,
        source_code: str,
        filename: str = "snippet.py",
    ) -> Dict[str, Any]:
        """Calcola il punteggio di rischio AST (0.0 - 1.0) e la profondita max_depth."""
        if not filename.endswith(".py"):
            lines = [
                line.strip() for line in source_code.splitlines() if line.strip()
            ]
            loc = len(lines)
            risk = min(1.0, round(loc / 300.0, 2))
            eligible = risk <= 0.5 and loc <= self.MODE_C_MAX_LOC
            recommended_mode = (
                "mode_c" if eligible else ("mode_b" if loc <= 300 else "mode_a")
            )
            return {
                "risk_score": risk,
                "mode_eligible": eligible,
                "fast_bypass_eligible": eligible,
                "native_subagent": "NK-Builder-Agent",
                "recommended_mode": recommended_mode,
                "max_depth": 0,
                "reason": f"Non-Python asset ({loc} LOC). Mode C eligible: {eligible}",
                "loc": loc,
            }

        try:
            tree = ast.parse(source_code, filename=filename)
        except SyntaxError as exc:
            return {
                "risk_score": 1.0,
                "mode_eligible": False,
                "fast_bypass_eligible": False,
                "native_subagent": "NK-Builder-Agent",
                "recommended_mode": "mode_a",
                "max_depth": 0,
                "reason": f"SyntaxError in code: {exc}",
                "loc": len(source_code.splitlines()),
            }

        class_count = 0
        func_count = 0
        import_count = 0
        loc = len(source_code.splitlines())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_count += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_count += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_count += 1

        depth_visitor = _ASTDepthVisitor()
        depth_visitor.visit(tree)
        max_depth = depth_visitor.max_depth

        depth_penalty = min(0.25, max(0, max_depth - 2) * 0.05)
        risk = (
            min(0.35, (loc / 250.0) * 0.35)
            + min(0.25, class_count * 0.12)
            + min(0.15, import_count * 0.04)
            + min(0.10, func_count * 0.02)
            + depth_penalty
        )
        risk = round(min(1.0, risk), 2)
        eligible = risk <= 0.5 and loc <= self.MODE_C_MAX_LOC and max_depth <= 6

        if eligible:
            recommended_mode = "mode_c"
        elif risk <= 0.75 and loc <= 350:
            recommended_mode = "mode_b"
        else:
            recommended_mode = "mode_a"

        return {
            "risk_score": risk,
            "mode_eligible": eligible,
            "fast_bypass_eligible": eligible,
            "native_subagent": "NK-Builder-Agent",
            "recommended_mode": recommended_mode,
            "loc": loc,
            "classes": class_count,
            "functions": func_count,
            "imports": import_count,
            "max_depth": max_depth,
            "reason": (
                "Safe for Mode C Vibe-Sprint"
                if eligible
                else "Exceeds Mode C risk threshold (requires Mode A/B)"
            ),
        }

    def generate_inline_micro_spec(
        self,
        target_file: str,
        change_intent: str,
        risk_info: Dict[str, Any],
    ) -> str:
        """Sintetizza una micro-specifica inline inferiore a 150 token."""
        capsule = self.load_prewarmed_capsule()
        capsule_summary = str(capsule.get("capsule_text", "")).strip()
        if not capsule_summary and isinstance(capsule.get("lessons"), list):
            capsule_summary = " | ".join(
                str(item.get("lesson", ""))
                for item in capsule["lessons"][:3]
                if isinstance(item, dict) and item.get("lesson")
            ).strip()
        spec = [
            f"[NK-VIBE-SPRINT-SPEC | Target: {target_file}]",
            f"Intent: {change_intent.strip()}",
            f"Risk Score: {risk_info.get('risk_score', 0.0)} | LOC: {risk_info.get('loc', 0)} | Max Depth: {risk_info.get('max_depth', 0)}",
            "Mode: Mode C (Fast Staging -> AST Guard -> Zero-Mock Verification -> 2PC Commit)",
            "Safety Invariant: Zero-Mock / Real fixture adherence.",
        ]
        if capsule_summary:
            spec.append(f"Tier-1 Capsule: {capsule_summary[:240]}")
        return "\n".join(spec)

    def load_prewarmed_capsule(self) -> Dict[str, Any]:
        """Carica la capsula di memoria Tier-1 pre-riscaldata con fallback a memory_3tier."""
        candidates = (
            self.staging_dir / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.workspace_root / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.staging_dir
            / "nk_tracking"
            / "memory_3tier"
            / "tier1_active_capsule.json",
            self.workspace_root
            / "nk_tracking"
            / "memory_3tier"
            / "tier1_active_capsule.json",
        )
        for cand in candidates:
            if cand.exists():
                try:
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {
            "status": "EMPTY",
            "capsule_text": "",
            "token_count": 0,
            "token_cap": 350,
            "entries": [],
        }


def resolve_domain_from_manifest(
    prompt: str,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per risolvere il dominio O(1) dal manifesto SSOT."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.resolve_domain_from_manifest(prompt=prompt)


def classify_prompt_intent(
    prompt: str,
    files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per classificare l'intento del prompt (Mode D vs A/B/C)."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.classify_prompt_intent(prompt=prompt, files=files)


def normalize_voice_stt_input(
    raw_prompt: str,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per normalizzare l'input vocale STT."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.normalize_voice_stt_input(raw_prompt=raw_prompt)


def is_gate_exempt(
    raw_prompt: str,
    workspace_root: Optional[Path] = None,
) -> bool:
    """Funzione helper di modulo per verificare le 5 esenzioni anti-loop."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.is_gate_exempt(raw_prompt=raw_prompt)


def build_meta_prompt_envelope(
    prompt: str,
    gate_enabled: bool = True,
    gate_mode: str = "CONFIRM",
    files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per costruire il contratto MetaPromptGateContract."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.build_meta_prompt_envelope(
        prompt=prompt,
        gate_enabled=gate_enabled,
        gate_mode=gate_mode,
        files=files,
    )


def load_prewarmed_capsule(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Funzione helper di modulo per caricare la capsula Tier-1 pre-riscaldata."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.load_prewarmed_capsule()


def run_test() -> int:
    """Esegue l'autotest rapido del router Mode C, Mode D e Meta-Prompt Gate."""
    router = VibeSprintRouter()
    code_sample = '''
def calculate_vat(amount: float, rate: float = 0.22) -> float:
    """Calcola l'IVA per una transazione."""
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    return round(amount * rate, 2)
'''
    res = router.compute_ast_risk_score(code_sample, "tax_calculator.py")
    assert res["mode_eligible"] is True
    assert res["max_depth"] >= 2
    spec = router.generate_inline_micro_spec(
        "src_app/utils/tax.py",
        "Add VAT calculation",
        res,
    )
    assert "NK-VIBE-SPRINT-SPEC" in spec
    disc = router.classify_prompt_intent("Esegui audit e benchmark copertura bandi")
    assert disc["recommended_mode"] == "mode_d"
    assert "domain_id" in disc
    env = router.build_meta_prompt_envelope(
        "Analizza primaLa struttura e l'implementazione attuale"
    )
    assert env["fsm_state"] == "AWAIT_CONFIRM"
    assert len(env["intent_hash_sha256"]) == 64
    print(
        f"VibeSprintRouter test PASS: Risk {res['risk_score']} | Depth {res['max_depth']}"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il router Mode A/B/C/D di Nexus Keystone."""
    parser = argparse.ArgumentParser(
        description="Router Mode A/B/C/D basato sul rischio AST e intento prompt per Nexus Keystone"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Esegue l'autotest rapido del router",
    )
    parser.add_argument(
        "--prompt",
        "--task",
        dest="prompt",
        type=str,
        default="Vibe Sprint Change",
        help="Descrizione sintetica dell'intento di modifica o discovery",
    )
    parser.add_argument(
        "--classify-prompt",
        nargs="?",
        const="__USE_PROMPT__",
        default=None,
        help="Classifica l'intento del prompt e restituisce modalita, dominio e sub-agente",
    )
    parser.add_argument(
        "--meta-prompt-gate",
        action="store_true",
        help="Costruisce e valida il contratto MetaPromptGateContract per il prompt fornito",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Disabilita o bypassa il Meta-Prompt Gate per l'invocazione corrente",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Modalita operativa opzionale",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Elenco dei file sorgente da valutare per il routing",
    )
    parser.add_argument(
        "--discovery-check",
        action="store_true",
        help="Valuta l'intento del prompt per attivare Mode D Read-Only Discovery",
    )
    parser.add_argument(
        "--capsule",
        action="store_true",
        help="Include e stampa la capsula di memoria Tier-1 pre-riscaldata",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il verdetto di routing in formato JSON",
    )
    args = parser.parse_args(argv)

    if args.test:
        return run_test()

    effective_prompt = args.prompt
    if (
        args.classify_prompt is not None
        and args.classify_prompt != "__USE_PROMPT__"
        and args.prompt == "Vibe Sprint Change"
    ):
        effective_prompt = str(args.classify_prompt)

    router = VibeSprintRouter()

    if args.meta_prompt_gate or args.no_gate:
        envelope = router.build_meta_prompt_envelope(
            effective_prompt,
            gate_enabled=not args.no_gate,
            gate_mode="OFF" if args.no_gate else "CONFIRM",
            files=args.files,
        )
        if args.json:
            print(json.dumps(envelope, indent=2, ensure_ascii=False))
        else:
            print(
                f"[META-PROMPT-GATE] Brief: {envelope['brief_id']} | "
                f"State: {envelope['fsm_state']} | Mode: {envelope['recommended_mode']} | "
                f"Agent: {envelope['primary_agent']} | SHA256: {envelope['intent_hash_sha256'][:12]}"
            )
        return 0

    if args.files:
        results: List[Dict[str, Any]] = []
        for file_arg in args.files:
            p = Path(file_arg)
            if not p.is_absolute():
                p = (router.workspace_root / p).resolve()
            if p.exists() and p.is_file():
                code = p.read_text(encoding="utf-8", errors="replace")
                info = router.compute_ast_risk_score(code, p.name)
            else:
                info = router.compute_ast_risk_score("", p.name)
            info["file"] = str(file_arg)
            info["micro_spec"] = router.generate_inline_micro_spec(
                str(file_arg),
                effective_prompt,
                info,
            )
            results.append(info)
        payload: Dict[str, Any] = {"files": results}
        if args.capsule:
            payload["tier1_capsule"] = router.load_prewarmed_capsule()
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for item in results:
                print(item["micro_spec"])
        return 0

    intent = router.classify_prompt_intent(effective_prompt, files=args.files)
    prompt_explicit = (
        args.classify_prompt is not None
        or args.discovery_check
        or effective_prompt != "Vibe Sprint Change"
    )
    if prompt_explicit or intent["is_discovery"]:
        if args.capsule:
            intent["tier1_capsule"] = router.load_prewarmed_capsule()
        if args.json:
            print(json.dumps(intent, indent=2, ensure_ascii=False))
        else:
            print(
                f"[{intent['mode_label']}] | Mode: {intent['recommended_mode']} | "
                f"Agent: {intent['primary_agent']} | Subagent: {intent['native_subagent']} | "
                f"Domain: {intent['domain_id']}"
            )
        return 0

    if args.capsule:
        cap = router.load_prewarmed_capsule()
        print(json.dumps(cap, indent=2, ensure_ascii=False))
        return 0

    print("VibeSprintRouter CLI ready. Use --test to validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
