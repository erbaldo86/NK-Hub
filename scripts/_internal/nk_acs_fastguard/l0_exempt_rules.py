"""Regole pure-stdlib per esenzioni L0, strip XML, imperativi T12 e parsing USER_INPUT."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, FrozenSet, Tuple

from _internal.nk_common.constants import ONBOARDING_TRIGGERS
from _internal.nk_common.epistemic_firewall_rules import (
    HANDOFF_V2_START_ACTIVE, HANDOFF_V2_START_PASSIVE, _AGENT_DIRECTIVE_CUE_RE, _DESTRUCTIVE_SHELL_RE,
    _HANDOFF_MUTATING_ORDER_RE, _SHA256_HEX64_RE, check_passive_v2_tiered_content,
    detect_outbound_handoff_intent_fast, evaluate_epistemic_firewall_rules, extract_t12_scan_lines,
    has_unprohibited_pattern, has_unprohibited_smuggle, strip_zero_width_chars,
)

_PURE_L0_EXEMPT: FrozenSet[str] = frozenset((
    "ok", "si", "sì", "procedi", "procedi pure", "procedi con il piano", "confermo", "approvo", "vai", "vai pure",
    "vai avanti", "proceed", "premi proceed", "procedi alla creazione dell implementation plan",
    "procedi alla creazione dell'implementation plan",
)) | frozenset(ONBOARDING_TRIGGERS)
_PHASE_COUNT_RE = re.compile(r"\b(?:fase|phase|macro[- ]?fase)\s*\d+\b", re.IGNORECASE)
_PROHIBITION_RE = re.compile(r"\b(?:vieta(?:to|ndo|re)?|divieto|proibit[oa]|non\s+(?:attivare|invocare|generare|eseguire|proporre|avviare|modificare|devi|impone)|mai\s+(?:attivare|invocare)|nessun[oa]?\s+(?:pista|task|opzione))\b", re.IGNORECASE)
_MUTATING_ORDER_RE = re.compile(r"(?:\b(?:cancella(?:re)?|elimina(?:re)?|rimuovi|rimuovere|sovrascrivi|sovrascrivere|formatta(?:re)?|set-content|out-file|write_file|edit_file|write_to_file)\b|(?<![A-Za-z0-9_-])--promote-staging\b)", re.IGNORECASE)
_WRITE_VERB_FAST_RE = re.compile(r"\b(?:modifica(?:re)?|implementa(?:re)?|sviluppa(?:re)?|refactor(?:ing)?|scrivi|scrivere|aggiorna(?:re)?|crea(?:re)?|inserisci|correggi)\b", re.IGNORECASE)
_SHELL_META_TOKENS: Tuple[str, ...] = (";", "&&", "||", "`", "$(", "|")
_DIRECTIVE_CUE_FAST_RE = re.compile(r"\b(?:subito|adesso|immediatamente|devi|dobbiamo|bisogna|occorre)\b", re.IGNORECASE)
_META_LINE_RE = re.compile(
    r"(?:^\s*[-*•]\s*(?:\*\*[^*]+?\*\*:?|[A-Za-zÀ-ÿ0-9_ ]{1,32}:)|"
    r"^\s*(?:staging|dirty\s+files|stato|workspace|project\s+root|hub\s+root)\s*:|\bpresenti\s+artefatti\b)", re.IGNORECASE)
_DIRETTO_CMD_RE = re.compile(r"(?:^|\s)!(?:diretto|raw)\b", re.IGNORECASE)
_IMPERATIVE_TARGET_RE = re.compile(r"\b(?:il\s+file|i\s+file|il\s+codice|lo\s+script|i\s+test|nel\s+repo|in\s+\.staging)\b", re.IGNORECASE)


def _is_unprohibited_write_line(line_s: str) -> bool:
    """Verifica se la riga contiene verbi di scrittura diretti non protetti da divieto."""
    if _PROHIBITION_RE.search(line_s) and not has_unprohibited_pattern(line_s, _WRITE_VERB_FAST_RE, _PROHIBITION_RE):
        return False
    if not _WRITE_VERB_FAST_RE.search(line_s):
        return False
    if _AGENT_DIRECTIVE_CUE_RE.search(line_s) or _DIRECTIVE_CUE_FAST_RE.search(line_s):
        return True
    return not _META_LINE_RE.search(line_s) and bool(_IMPERATIVE_TARGET_RE.search(line_s))


def _is_imperative_line(line_s: str, is_neutral: bool) -> bool:
    """Valuta una singola riga T12 fuori fence eseguibile per ordini mutanti."""
    if not is_neutral and _DESTRUCTIVE_SHELL_RE.search(line_s):
        return True
    if _MUTATING_ORDER_RE.search(line_s) or _HANDOFF_MUTATING_ORDER_RE.search(line_s):
        return True
    return True if has_unprohibited_smuggle(line_s, _PROHIBITION_RE) else _is_unprohibited_write_line(line_s)


def _has_direct_imperative_outside_fence(clean: str) -> bool:
    """Rileva ordini imperativi/mutanti nei T12 legacy proteggendo i fence eseguibili e direttive."""
    strict_lines, neutral_lines = extract_t12_scan_lines(clean)
    tagged = [(ln, False) for ln in strict_lines] + [(ln, True) for ln in neutral_lines]
    return any(_is_imperative_line(s, is_n) for raw, is_n in tagged if (s := raw.strip()))


def _strip_xml_wrapper_fast(raw_text: str) -> str:
    """Estrae <USER_REQUEST> o rimuove envelope XML Antigravity in sola stdlib."""
    cleaned = re.sub(
        r"<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|EPHEMERAL_MESSAGE|SYSTEM_MESSAGE)\b[^>]*>.*?</\1>",
        "", str(raw_text or ""), flags=re.DOTALL | re.IGNORECASE).strip()
    low = cleaned.lower()
    if low.count("<user_request>") == 1 and low.count("</user_request>") == 1:
        if m_req := re.fullmatch(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", cleaned, flags=re.DOTALL | re.IGNORECASE):
            return m_req.group(1).strip()
    return cleaned


def _validate_t12_handoff_tail(clean: str, low: str, fw_meta: Dict[str, Any]) -> bool:
    """Completa i controlli V2 spoof, framing T12, SHA-256 e imperativi per handoff legacy."""
    v2_markers = (HANDOFF_V2_START_PASSIVE.lower(), HANDOFF_V2_START_ACTIVE.lower(), "handoff_v2:")
    if fw_meta.get("is_v2_handoff") or any(m in low for m in v2_markers) or not fw_meta.get("t12_framing_valid"):
        return False
    if ("sha-256" in low or "sha256" in low) and not _SHA256_HEX64_RE.search(clean):
        return False
    return not _has_direct_imperative_outside_fence(clean)


def _validate_handoff_exempt_fast(clean: str, low: str) -> bool:
    """Valida handoff V2 o legacy T12 prima di !diretto; blocca spoof, AP-14/15/16 e ACTIVE."""
    viols, fw_meta = evaluate_epistemic_firewall_rules(clean, mode="state-handoff", is_state_handoff=True)
    if fw_meta.get("unclosed_fence") or viols:
        return False
    if fw_meta.get("v2_verified"):
        return str(fw_meta.get("v2_mode") or "").upper() == "PASSIVE_STANDBY" and not check_passive_v2_tiered_content(fw_meta)
    return _validate_t12_handoff_tail(clean, low, fw_meta)


def _is_env_capsule_exempt(clean: str, low: str) -> bool:
    """Verifica esenzione rapida di capsule <env_capsule> prive di comandi mutanti."""
    if any(p.search(clean) for p in (_DESTRUCTIVE_SHELL_RE, _MUTATING_ORDER_RE, _HANDOFF_MUTATING_ORDER_RE)):
        return False
    open_cnt, close_cnt = low.count("<env_capsule>"), low.count("</env_capsule>")
    if open_cnt == 1 and close_cnt == 1 and low.endswith("</env_capsule>"):
        return True
    return close_cnt == 0 and open_cnt == 1 and len(low) <= 128 and not _WRITE_VERB_FAST_RE.search(low)


def _is_diretto_exempt(clean: str, low: str) -> bool:
    """Verifica se il comando !diretto/!raw rispetta lunghezza, meta-token e assenza mutazioni."""
    if len(clean) > 1500 or len(_PHASE_COUNT_RE.findall(low)) > 1 or any(m in clean for m in _SHELL_META_TOKENS):
        return False
    return not any(p.search(low) for p in (_DESTRUCTIVE_SHELL_RE, _MUTATING_ORDER_RE, _HANDOFF_MUTATING_ORDER_RE, _WRITE_VERB_FAST_RE))


def _is_menu_or_pure_exempt(clean: str, low: str) -> bool:
    """Riconosce selezioni dashboard, token singoli non-path e conferme pure."""
    if (low.isdigit() and 0 <= int(low) <= 9) or (low.startswith("[") and low.endswith("]") and low[1:-1].isdigit()):
        return True
    norm = " ".join(low.replace("!", "").replace(".", "").replace(",", "").replace("-", " ").replace("_", " ").split())
    if len(norm.split()) <= 1 and "/" not in clean and "\\" not in clean and "." not in clean:
        return True
    return norm in _PURE_L0_EXEMPT


def _is_l0_exempt_fast(clean_prompt: str) -> bool:
    """Filtro rapido pure-stdlib per conferme pure, handoff verificati, dashboard e capsule."""
    clean = strip_zero_width_chars(clean_prompt or "").strip()
    if not clean or len(clean) <= 2:
        return True
    low = clean.lower()
    if "[nk-anchor:" in low:
        return _validate_handoff_exempt_fast(clean, low)
    if low.startswith("<env_capsule>"):
        return _is_env_capsule_exempt(clean, low)
    if _DIRETTO_CMD_RE.search(low):
        return _is_diretto_exempt(clean, low)
    if detect_outbound_handoff_intent_fast(clean) is not None or low in ("/compact", "procedi e quando raggiungi la saturazione di contesto esegui un /compact"):
        return True
    return _is_menu_or_pure_exempt(clean, low)


def _extract_user_raw_text(rec: Dict[str, Any]) -> str:
    """Estrae contenuto grezzo se il record JSONL rappresenta un input utente."""
    is_u = str(rec.get("type") or "").strip().upper() == "USER_INPUT" or str(rec.get("source") or "").strip().upper() in ("USER", "USER_EXPLICIT") or str(rec.get("role") or "").strip().lower() == "user"
    raw_c = rec.get("content") if rec.get("content") is not None else rec.get("text")
    return raw_c if is_u and isinstance(raw_c, str) and raw_c.strip() else ""


def _extract_user_from_line(line: str) -> str:
    """Estrae prompt utente valido da una riga JSONL di transcript."""
    if not (ls := line.strip()).startswith("{"):
        return ""
    try:
        rec = json.loads(ls)
    except (json.JSONDecodeError, ValueError, TypeError):
        return ""
    if not isinstance(rec, dict) or not (raw_c := _extract_user_raw_text(rec)):
        return ""
    cleaned = _strip_xml_wrapper_fast(raw_c)
    return "" if not cleaned or cleaned.lstrip().startswith(("<CONTEXT_SUMMARY>", "# Resuming from a compaction")) else cleaned


def _read_last_user_prompt(tp_path: str) -> str:
    """Legge l'ultimo prompt USER_INPUT valido dagli ultimi 128KB del transcript."""
    try:
        if (sz := os.stat(tp_path).st_size) <= 0:
            return ""
        with open(tp_path, "rb") as fh:
            fh.seek(max(0, sz - 131072))
            raw_lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    return next((p for ln in reversed(raw_lines) if (p := _extract_user_from_line(ln))), "")
