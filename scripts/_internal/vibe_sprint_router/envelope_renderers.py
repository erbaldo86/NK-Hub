"""Parser requisiti R1..Rn, risoluzione CID e rendering testuale L0."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.vibe_sprint_router.constants_core import _CLAUSE_SPLIT_RE

_MAX_REQUIREMENT_CLAUSES: int = 64
_REQ_INLINE_SPLIT_RE = re.compile(r"\s+(?=(?:[-*+]\s+)?R\d+\s*:)")
_REQ_INLINE_DETECT_RE = re.compile(r"(?:^|\s)(?:[-*+]\s+)?R\d+\s*:")
_BULLET_NUM_SPLIT_RE = re.compile(r"\s+(?=\d+\)\s+)")
_BULLET_NUM_DETECT_RE = re.compile(r"(?:^|\s)\d+\)\s+")
_REQ_PREFIX_RE = re.compile(r"^R\d+\s*:\s*", re.IGNORECASE)
_VALID_CID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _split_single_clause_segment(seg_clean: str) -> List[str]:
    """Suddivide un segmento singolo su R1..Rn inline o elenchi numerati."""
    if len(_REQ_INLINE_DETECT_RE.findall(seg_clean)) >= 2:
        return _REQ_INLINE_SPLIT_RE.split(seg_clean)
    if len(_BULLET_NUM_DETECT_RE.findall(seg_clean)) >= 2:
        return _BULLET_NUM_SPLIT_RE.split(seg_clean)
    return [seg_clean]


def _split_requirement_clauses(cleaned_prompt: str) -> List[str]:
    """Estrae le clausole requisito sull'intero prompt conservando R7+ e coda >16KB entro 64 clausole."""
    raw_clauses: List[str] = []
    for seg in _CLAUSE_SPLIT_RE.split(cleaned_prompt):
        seg_clean = seg.strip(" .;")
        if len(seg_clean) < 3:
            continue
        for part in _split_single_clause_segment(seg_clean):
            p_clean = part.strip(" .;")
            if len(p_clean) >= 3:
                raw_clauses.append(p_clean)
    if len(raw_clauses) > _MAX_REQUIREMENT_CLAUSES:
        raw_clauses = raw_clauses[:48] + raw_clauses[-16:]
    return raw_clauses or [cleaned_prompt or "Eseguire il task richiesto"]


def _first_nonempty_str(mapping: Dict[str, Any], keys: Tuple[str, ...], default: str = "") -> str:
    """Restituisce il primo valore truthy tra le chiavi indicate come stringa stripped."""
    for key in keys:
        val = mapping.get(key)
        if val:
            return str(val).strip()
    return default


def _format_active_v2_req_item(idx: int, item: Any) -> Optional[str]:
    """Normalizza una singola voce requisito R1..Rn da dizionario o stringa."""
    if isinstance(item, dict):
        rid = _first_nonempty_str(item, ("req_id", "id"), f"R{idx}")
        rtxt = _first_nonempty_str(item, ("text", "description", "requirement"))
        return None if not rtxt else (f"{rid}: {rtxt}" if not _REQ_PREFIX_RE.match(rtxt) else rtxt)
    txt = str(item or "").strip()
    return None if not txt else (txt if _REQ_PREFIX_RE.match(txt) else f"R{idx}: {txt}")


def _active_v2_fallback_text(envelope_or_payload: Dict[str, Any], inner: Dict[str, Any], default: str) -> str:
    """Estrae il testo fallback di continuazione preservando l'ordine canonico dei campi."""
    primary = envelope_or_payload.get("last_summary") or inner.get("active_brief_id")
    return str(primary).strip() if primary else _first_nonempty_str(envelope_or_payload, ("summary", "goal"), default)


def _extract_active_v2_requirements(envelope_or_payload: Dict[str, Any]) -> List[str]:
    """Estrae i requisiti R1..Rn dal payload ACTIVE_CONTINUATION senza _split_requirement_clauses."""
    inner = envelope_or_payload.get("payload") if isinstance(envelope_or_payload.get("payload"), dict) else envelope_or_payload
    raw_reqs = inner.get("requirements") or envelope_or_payload.get("requirements") or []
    out: List[str] = []
    if isinstance(raw_reqs, list):
        for idx, item in enumerate(raw_reqs, start=1):
            formatted = _format_active_v2_req_item(idx, item)
            if formatted:
                out.append(formatted)
    return out or [f"R1: {_active_v2_fallback_text(envelope_or_payload, inner, 'Eseguire la continuazione richiesta')}"]


def _valid_cid_token(raw_val: Optional[str]) -> str:
    """Valida un token conversation_id escludendo sentinelle auto o default."""
    raw = str(raw_val or "").strip()
    low = raw.lower()
    if not raw or not _VALID_CID_RE.fullmatch(raw) or low in ("auto", "default") or low.startswith("default_"):
        return ""
    return raw


def _cid_from_hook_filename(fname: str) -> str:
    """Estrae il token conversation_id grezzo dai nomi file runtime degli hook."""
    if fname.startswith("fastguard_") and fname.endswith(".json"):
        return fname[len("fastguard_") : -len(".json")]
    if fname.startswith("probe_") and fname.endswith(".jsonl"):
        return fname[len("probe_") : -len(".jsonl")]
    return fname[: -len("_integrity.json")] if fname.endswith("_integrity.json") else ""


def _entry_cid_if_recent(entry: Any, now: float) -> Tuple[float, str]:
    """Restituisce (mtime, cid) se il file hook e valido e aggiornato entro 60 secondi."""
    try:
        if not entry.is_file(follow_symlinks=False):
            return -1.0, ""
        cid_tok = _valid_cid_token(_cid_from_hook_filename(entry.name))
        mt = entry.stat().st_mtime if cid_tok else -1.0
    except OSError:
        return -1.0, ""
    return (mt, cid_tok) if (cid_tok and (now - mt) <= 60.0) else (-1.0, "")


def _scan_hooks_dir_for_cid(hooks_dir: Path) -> str:
    """Cerca nella directory temporanea degli hook il conversation_id piu recente."""
    now, best_cid, best_mtime = time.time(), "", -1.0
    try:
        with os.scandir(hooks_dir) as it:
            entries = list(it)
    except OSError:
        return ""
    for entry in entries:
        mt, cid_tok = _entry_cid_if_recent(entry, now)
        if cid_tok and mt > best_mtime:
            best_mtime, best_cid = mt, cid_tok
    return best_cid


def _resolve_cid(conversation_id: Optional[str]) -> str:
    """Risolve un conversation_id esplicito o da env/discovery senza emettere 'auto'."""
    for cand in (conversation_id, os.environ.get("NK_CONVERSATION_ID"), os.environ.get("ANTIGRAVITY_CONVERSATION_ID")):
        valid = _valid_cid_token(cand)
        if valid:
            return valid
    hooks_env = os.environ.get("NK_HOOKS_TEMP_DIR", "").strip()
    return _scan_hooks_dir_for_cid(Path(hooks_env)) if (hooks_env and Path(hooks_env).is_dir()) else ""


def _summarize_eval_text(eval_text: str) -> str:
    """Genera il sommario mirror testuale troncato ai confini di parola oltre 240 caratteri."""
    if len(eval_text) <= 240:
        return eval_text
    head_part = eval_text[:140].rsplit(" ", 1)[0].rstrip(" ,;:") or eval_text[:140]
    tail_slice = eval_text[-90:]
    tail_part = (tail_slice.split(" ", 1)[1] if " " in tail_slice and not tail_slice.startswith(" ") else tail_slice).lstrip(" ,;:") or tail_slice
    return f"{head_part} ... {tail_part}"


def _render_full_meta_prompt(
    rec_mode: str, primary_ag: str, native_sub: str, bypassed: bool, bypass_reason: Optional[str],
    eval_text: str, requirements_r_ids: List[str], protocols_str: str,
) -> Tuple[List[str], str, str]:
    """Compone out_of_scope, conceptual_mirror e optimized_meta_prompt in profilo esteso."""
    if rec_mode == "mode_d":
        out_of_scope = ["Qualsiasi modifica ai file del repository (esecuzione 100% Read-Only)", "Esecuzione di commit transazionali 2PC"]
        nk_guidance = "Regolamento NK: opera in sola lettura (Mode D) e verifica le fonti."
    else:
        out_of_scope = ["Modifica diretta dei file di produzione fuori da .staging/", "Uso di MagicMock o stub sintetici vietati da RULE-01.2"]
        nk_guidance = "Regolamento NK: dopo la conferma L0, prepara Brief in nk_genome/ e implementation_plan.md confermato dall'utente (RequestFeedback: true) prima di delegare la scrittura codice ai Builder in .staging/, applica commit 2PC e convergenza RSI."
    if bypassed:
        out_of_scope.append("Bypass L0_GATE_ONLY: topologia 2-Tier (max 12 tool diretti) e .staging/ + 2PC restano obbligatori")
    scope_tag = " | Single-Gate: READONLY_MODE_D_BYPASS" if bypass_reason == "READONLY_MODE_D_BYPASS" else (" | BypassScope: L0_GATE_ONLY" if bypassed else "")
    header_line = f"[META-PROMPT L0 | Mode: {rec_mode}{scope_tag} | Skill: {primary_ag}]" if bypass_reason == "READONLY_MODE_D_BYPASS" else f"[META-PROMPT L0 | Mode: {rec_mode} | Skill: {primary_ag}{scope_tag}]"
    opt = f"{header_line}\nObiettivo ad alto livello: {eval_text}\nRequisiti: {'; '.join(requirements_r_ids)}\nProtocolli Intrinseci Auto-Attivati: {protocols_str}\n{nk_guidance}"
    mirror = f"Obiettivo: {_summarize_eval_text(eval_text)} (Modalita: {rec_mode}, Skill: {primary_ag}, Sub-Agente: {native_sub}, Protocolli: {protocols_str}). {nk_guidance}"
    return out_of_scope, mirror, opt


def _render_standard_envelope_texts(
    compact: bool, rec_mode: str, primary_ag: str, native_sub: str, bypassed: bool,
    bypass_reason: Optional[str], eval_text: str, requirements_r_ids: List[str], protocols_str: str,
) -> Tuple[List[str], str, str]:
    """Seleziona il rendering compatto o esteso per i testi L0 dell'envelope."""
    if compact:
        return (["Read-Only"] if rec_mode == "mode_d" else ["Solo .staging/"]), f"{eval_text[:48]} ({rec_mode}/{primary_ag}).", f"[L0:{rec_mode}:{primary_ag}] {eval_text[:64]} | {'; '.join(requirements_r_ids)}"
    return _render_full_meta_prompt(rec_mode, primary_ag, native_sub, bypassed, bypass_reason, eval_text, requirements_r_ids, protocols_str)
