# -*- coding: utf-8 -*-
"""Regole pure stdlib dell'Epistemic Firewall (AP-14, AP-15, AP-16, AP-12/13, strip L3, intent)."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Tuple

from .epistemic_firewall_patterns import (  # noqa: F401
    HANDOFF_V2_END_ACTIVE, HANDOFF_V2_END_PASSIVE, HANDOFF_V2_START_ACTIVE, HANDOFF_V2_START_PASSIVE,
    T12_END, T12_HEADER_PREFIX, T12_START, _AGENT_DIRECTIVE_CUE_RE, _AP12_IMPERATIVE_LEAK_RE,
    _AP13_COGNITIVE_TUNNELING_RE, _AP14_COMMON_CONTAM_RE, _AP14_V2_TRANSCRIPT_RE, _AP15_BRIEF_ID_RE,
    _AP15_REGISTERED_BLOCK_RE, _BEARER_RE, _CLAUSE_BREAK_RE, _DESTRUCTIVE_SHELL_RE, _DSN_ANY_RE,
    _DSN_PASS_RE, _EMAIL_RE, _FENCE_OPEN_RE, _HANDOFF_MUTATING_ORDER_RE, _HTTP_CRED_RE, _HTTP_URL_RE,
    _ISO_DATE_RE, _KV_SECRET_RE, _LIVE_URL_HINT_RE, _NEUTRAL_FENCE_LANGS, _OUTBOUND_ACTIVE_CUE_RE,
    _OUTBOUND_CODE_EXCLUSION_RE, _OUTBOUND_HANDOFF_RE, _OUTBOUND_SHELL_RE, _PEM_KEY_RE, _PHONE_CTX_RE,
    _PROHIBITION_LINE_RE, _SAFE_DOMAINS, _SECRET_PREFIX_RE, _SHA256_HEX64_RE,
    _T12_ALWAYS_BLOCKED_SMUGGLE_RE, _T12_STANDALONE_SMUGGLE_RE, _ZERO_WIDTH_TRANS,
    _has_unguarded_live_endpoint, _is_safe_host, _make_violation, redact_pii_deterministic,
    strip_zero_width_chars,
)
from .epistemic_firewall_wire import (  # noqa: F401
    _V2_ENVELOPE_ALLOWED_KEYS, _no_dup_pairs_hook, _parse_sealed_t12_json_capsule, _strict_json_loads,
    _validate_v2_structure, check_legacy_t12_framing, compute_envelope_sha256_stdlib,
    extract_t12_scan_lines, is_sealed_t12_json_capsule, parse_verified_handoff_v2_wire, scan_fences_strict,
)

_PN_CH_PATHS = frozenset((
    ("payload", "ecosystem_repos", "*", "patch_notes_head", "first_section_title"),
    ("payload", "ecosystem_repos", "*", "patch_notes_head", "first_section_excerpt"),
))
_L3_STRIP_KEYS = frozenset((
    "last_summary", "historical_scores", "score_history", "history_scores",
    "prior_scores", "previous_scores", "l3_narrative", "persuasive_narrative",
    "narrative", "justification", "rationale", "reasoning", "thinking",
    "chain_of_thought", "commentary", "self_assessment", "confidence_claim", "unverified_claims",
))
_L3_PERSUASIVE_LINE_RE = re.compile(
    r"(?i)(?:^\s*(?:last_summary|l3_narrative|persuasive_narrative|historical_scores?)\s*:|"
    r"\b(?:fidati|garantit[oa]\s+al\s+100%|trust\s+me|obviously\s+correct|clearly\s+safe|"
    r"no\s+need\s+to\s+(?:test|verify)|skip\s+(?:the\s+)?oracle)\b)"
)


def detect_outbound_handoff_intent_fast(text: str) -> str | None:
    """Classifica richieste utente dirette di serializzazione handoff in uscita."""
    clean = strip_zero_width_chars(text or "").strip()
    if not clean or len(clean) > 500 or len(clean.splitlines()) > 2:
        return None
    low = clean.lower()
    if any(m in low for m in ("[nk-anchor:", "[handoff stato sessione", "passive_session_state_handoff", "# [nk-handoff-v2]")):
        return None
    if _OUTBOUND_SHELL_RE.search(clean) or _AGENT_DIRECTIVE_CUE_RE.search(clean) or _OUTBOUND_CODE_EXCLUSION_RE.search(clean):
        return None
    if not _OUTBOUND_HANDOFF_RE.search(clean):
        return None
    return "ACTIVE_CONTINUATION" if _OUTBOUND_ACTIVE_CUE_RE.search(clean) else "PASSIVE_STANDBY"


def _walk_decoded_strings(obj: Any) -> List[str]:
    out, stack = [], [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str) and (val := strip_zero_width_chars(cur)):
            out.append(val)
        elif isinstance(cur, dict):
            stack.extend(cur.keys())
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
    return out


def _extract_passive_v2_tiered_texts(v2_obj: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Estrae blocchi testuali operativi e changelog da un envelope V2 (Passive o Active)."""
    op_texts: List[str] = []
    ch_texts: List[str] = []

    def _add_str(raw: Any, dst: List[str]) -> None:
        if isinstance(raw, str) and (val := strip_zero_width_chars(raw)).strip():
            dst.append(val)

    def _walk(node: Any, path: Tuple[str, ...] = ()) -> None:
        if "staging_diffs" in path:
            return
        if isinstance(node, str):
            _add_str(node, ch_texts if path in _PN_CH_PATHS else op_texts)
        elif isinstance(node, dict):
            _walk_dict(node, path)
        elif isinstance(node, (list, tuple)):
            next_p = path + ("*",) if path == ("payload", "ecosystem_repos") else path
            for it in node:
                _walk(it, next_p)

    def _walk_dict(mapping: Dict[str, Any], path: Tuple[str, ...]) -> None:
        for k, v in mapping.items():
            ks = str(k)
            if ks != "staging_diffs":
                _add_str(k, op_texts)
                _walk(v, path + (ks,))

    _walk(v2_obj)
    return op_texts, ch_texts


def has_unprohibited_smuggle(line_s: str, prohibition_re: re.Pattern[str] = _PROHIBITION_LINE_RE) -> bool:
    """Verifica smuggle T12/V2 permettendo i soli divieti canonici su token intrinseci."""
    if _T12_ALWAYS_BLOCKED_SMUGGLE_RE.search(line_s):
        return True
    if not _T12_STANDALONE_SMUGGLE_RE.search(line_s):
        return False
    return any(c_s and _T12_STANDALONE_SMUGGLE_RE.search(c_s) and not prohibition_re.search(c_s) for c_s in (cl.strip() for cl in _CLAUSE_BREAK_RE.split(line_s)))


def has_unprohibited_pattern(line_s: str, pat: re.Pattern[str], prohibition_re: re.Pattern[str] = _PROHIBITION_LINE_RE) -> bool:
    """Verifica un pattern su sub-clausole prive di verbo proibitivo."""
    if not pat.search(line_s):
        return False
    return any(c_s and pat.search(c_s) and not prohibition_re.search(c_s) for c_s in (cl.strip() for cl in _CLAUSE_BREAK_RE.split(line_s)))


def _check_v2_line_ap12_ap13(
    ln: str, is_op: bool, is_active: bool, has_ap12: bool, has_ap13: bool,
) -> Tuple[List[Dict[str, str]], bool, bool]:
    """Valuta una singola riga di un blocco V2 restituendo eventuali violazioni AP-12/13."""
    out: List[Dict[str, str]] = []
    if not has_ap12:
        mut_hit = is_op and has_unprohibited_pattern(ln, _HANDOFF_MUTATING_ORDER_RE)
        smug_hit = bool(_DESTRUCTIVE_SHELL_RE.search(ln) or mut_hit or has_unprohibited_smuggle(ln))
        if smug_hit or (is_op and has_unprohibited_pattern(ln, _AP12_IMPERATIVE_LEAK_RE)):
            out.append(_make_violation("AP-12", "CRITICA", "STATE_HANDOFF_IMPERATIVE_LEAK: Imperative directive or mutation detected inside V2 Handoff.", "STATE_HANDOFF_IMPERATIVE_LEAK"))
            has_ap12 = True
    if not has_ap13 and (is_op or not is_active) and has_unprohibited_pattern(ln, _AP13_COGNITIVE_TUNNELING_RE):
        out.append(_make_violation("AP-13", "CRITICA", "STATE_HANDOFF_COGNITIVE_TUNNELING: Prescriptive track or option menu detected inside V2 Handoff.", "STATE_HANDOFF_COGNITIVE_TUNNELING"))
        has_ap13 = True
    return out, has_ap12, has_ap13


def check_passive_v2_tiered_content(meta: Dict[str, Any]) -> List[Dict[str, str]]:
    """Applica l'ispezione AP-12/13 a 2 livelli su PASSIVE_STANDBY e ACTIVE_CONTINUATION."""
    viols: List[Dict[str, str]] = []
    is_active = str(meta.get("v2_mode") or "PASSIVE_STANDBY").strip().upper() == "ACTIVE_CONTINUATION"
    has_ap12, has_ap13 = False, False
    blocks = [(t, True) for t in meta.get("v2_operational_texts") or ()] + [(t, False) for t in meta.get("v2_changelog_texts") or ()]
    for raw_block, is_op in blocks:
        for ln in (raw.strip() for raw in raw_block.splitlines()):
            if not ln:
                continue
            found, has_ap12, has_ap13 = _check_v2_line_ap12_ap13(ln, is_op, is_active, has_ap12, has_ap13)
            viols.extend(found)
    return viols


def strip_l3_persuasive_narrative(bundle: Any) -> Any:
    """Rimuove last_summary, score storici e narrative persuasive L3 verso DOM-04 senza mutare l'input."""
    if isinstance(bundle, dict):
        cleaned: Dict[Any, Any] = {}
        for k, v in bundle.items():
            if isinstance(k, str) and k.strip().lower() in _L3_STRIP_KEYS:
                continue
            cleaned[k] = strip_l3_persuasive_narrative(v)
        return cleaned
    if isinstance(bundle, list):
        return [strip_l3_persuasive_narrative(item) for item in bundle]
    if isinstance(bundle, tuple):
        return tuple(strip_l3_persuasive_narrative(item) for item in bundle)
    if isinstance(bundle, str):
        kept = [ln for ln in bundle.splitlines() if not _L3_PERSUASIVE_LINE_RE.search(ln)]
        return "\n".join(kept).strip()
    return copy.deepcopy(bundle)


def evaluate_epistemic_firewall_rules(
    text: str, mode: str = "auto", is_state_handoff: bool = False, is_brief_scope: bool = False
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Valuta AP-14, AP-15 e AP-16 restituendo violazioni normalizzate e metadati firewall."""
    raw_text = text or ""
    clean = strip_zero_width_chars(raw_text)
    clean_low, norm_mode = clean.lower(), (mode or "auto").strip().lower()
    blocks, unclosed_fence, outside_lines = scan_fences_strict(clean)
    v2_markers = (HANDOFF_V2_START_PASSIVE, HANDOFF_V2_END_PASSIVE, HANDOFF_V2_START_ACTIVE, HANDOFF_V2_END_ACTIVE, "# [NK-HANDOFF-V2]")
    has_v2_marker = any(mk.lower() in clean_low for mk in v2_markers) or "[nk-anchor:start:handoff_v2" in clean_low or "[nk-anchor:end:handoff_v2" in clean_low or norm_mode in ("handoff-v2", "handoff_v2")
    v2_parsed = parse_verified_handoff_v2_wire(clean) if has_v2_marker else None
    v2_mode = v2_parsed["payload"]["handoff_mode"] if (v2_parsed and isinstance(v2_parsed.get("payload"), dict)) else None
    has_t12_marker = any(mk in clean for mk in (T12_START, T12_END, T12_HEADER_PREFIX)) or "[handoff stato sessione nk-hub]" in clean_low or "passive_session_state_handoff" in clean_low
    t12_ok, t12_prov = check_legacy_t12_framing(clean) if has_t12_marker else (False, "")
    is_any_handoff = bool(is_state_handoff or has_v2_marker or has_t12_marker or norm_mode == "state-handoff")
    violations: List[Dict[str, str]] = []
    if unclosed_fence or (has_v2_marker and v2_parsed is None):
        violations.append(_make_violation("AP-16", "CRITICA", "UNCLOSED_FENCE_SPOOF: Fence non chiuso o envelope HANDOFF_V2 non conforme.", "UNCLOSED_FENCE_SPOOF"))
    decoded_obj = v2_parsed if v2_parsed is not None else (_parse_sealed_t12_json_capsule(clean) if t12_ok else None)
    decoded_strs = (_walk_decoded_strings(decoded_obj) + [strip_zero_width_chars(json.dumps(decoded_obj, ensure_ascii=False))]) if decoded_obj is not None else []
    if is_any_handoff and (_AP14_COMMON_CONTAM_RE.search(clean) or (has_v2_marker and _AP14_V2_TRANSCRIPT_RE.search(clean)) or any(_AP14_COMMON_CONTAM_RE.search(ds) or (has_v2_marker and _AP14_V2_TRANSCRIPT_RE.search(ds)) for ds in decoded_strs)):
        violations.append(_make_violation("AP-14", "CRITICA", "TRANSIENT_TASK_AND_TRANSCRIPT_CONTAMINATION: Contaminazione da transcript grezzo o stato effimero rilevata nell'handoff.", "TRANSIENT_TASK_AND_TRANSCRIPT_CONTAMINATION"))
    has_reg_block = bool(_AP15_REGISTERED_BLOCK_RE.search(clean))
    ap15_scope = bool(is_any_handoff or is_brief_scope or _AP15_BRIEF_ID_RE.search(clean) or has_reg_block or norm_mode in ("brief", "intent-brief", "intent_brief"))
    pii_count = 0
    if ap15_scope:
        _, pii_count = redact_pii_deterministic(clean)
        ap15_hit = pii_count > 0 or _has_unguarded_live_endpoint(clean, strict_registered=has_reg_block)
        for ds in (() if ap15_hit else decoded_strs):
            _, d_cnt = redact_pii_deterministic(ds)
            if d_cnt > 0 or _has_unguarded_live_endpoint(ds, strict_registered=bool(_AP15_REGISTERED_BLOCK_RE.search(ds))):
                pii_count += d_cnt
                ap15_hit = True
                break
        if ap15_hit:
            violations.append(_make_violation("AP-15", "CRITICA", "UNGUARDED_PII_AND_LIVE_ENDPOINT_EXPOSURE: PII, secret, DSN o endpoint live non oscurati in handoff/brief.", "UNGUARDED_PII_AND_LIVE_ENDPOINT_EXPOSURE"))
    v2_op_texts, v2_ch_texts = _extract_passive_v2_tiered_texts(v2_parsed) if (v2_parsed is not None and v2_mode in ("PASSIVE_STANDBY", "ACTIVE_CONTINUATION")) else ([], [])
    meta: Dict[str, Any] = {
        "is_v2_handoff": has_v2_marker, "is_t12_handoff": has_t12_marker, "v2_mode": v2_mode, "v2_verified": v2_parsed is not None,
        "v2_envelope": v2_parsed, "v2_operational_texts": v2_op_texts, "v2_changelog_texts": v2_ch_texts,
        "t12_framing_valid": t12_ok, "t12_provenance": t12_prov, "unclosed_fence": unclosed_fence,
        "zero_width_found": raw_text != clean, "fence_blocks": blocks, "outside_lines": outside_lines,
        "pii_count": pii_count, "ap15_scope_active": ap15_scope, "firewall_codes": [v["code"] for v in violations],
    }
    return violations, meta
