# -*- coding: utf-8 -*-
"""
Validazione wire format HANDOFF_V2, T12 legacy e scansione fence pure stdlib.
Modulo: scripts/_internal/nk_common/epistemic_firewall_wire.py.
@domain_id: DOM-05
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.staging_manifest import canonical_json_bytes, no_dup_pairs_hook

from .epistemic_firewall_patterns import (
    HANDOFF_V2_END_ACTIVE,
    HANDOFF_V2_END_PASSIVE,
    HANDOFF_V2_START_ACTIVE,
    HANDOFF_V2_START_PASSIVE,
    T12_END,
    T12_HEADER_PREFIX,
    T12_START,
    _FENCE_OPEN_RE,
    _NEUTRAL_FENCE_LANGS,
    strip_zero_width_chars,
)

_V2_ENVELOPE_ALLOWED_KEYS = frozenset((
    "schema_version", "handoff_id", "manifest", "payload", "pii_redacted_count",
    "external_live_calls_prohibited", "canonical_bootstrap_cmd", "envelope_sha256",
    "version", "milestone", "conversation_id", "steps", "steps_tail_window",
    "tokens", "actual_tokens", "estimated_tokens", "turn", "turn_phase",
    "handoff_template", "standby_mode", "baseline_tests", "baseline_pass_rate_pct",
    "prompt_lint", "state_sha256", "staging_state_sha256", "dirty_files",
    "project_root", "project_dirty_files", "stash_patch", "unverified_claims",
    "intent_brief_path", "intent_brief_sha256", "pending_actions", "last_summary",
    "last_failed_checks",
))


_no_dup_pairs_hook = no_dup_pairs_hook


def _strict_json_loads(raw_json: str) -> Any:
    """Parsa JSON in modalita strict rifiutando chiavi duplicate e NaN/Infinity."""
    def _reject_const(val: str) -> Any:
        raise ValueError(f"Non-standard JSON constant forbidden: {val!r}")
    return json.loads(raw_json, object_pairs_hook=_no_dup_pairs_hook, parse_constant=_reject_const)


def compute_envelope_sha256_stdlib(data: Dict[str, Any]) -> str:
    """Calcola lo SHA-256 canonico di un envelope JSON escludendo envelope_sha256."""
    canonical = {k: v for k, v in data.items() if k != "envelope_sha256"}
    return hashlib.sha256(canonical_json_bytes(canonical)).hexdigest()


def scan_fences_strict(text: str) -> Tuple[List[Dict[str, Any]], bool, List[str]]:
    """Scansiona blocchi fenced chiudendo SOLO su riga pura di backtick/tilde >= fence_len."""
    clean = strip_zero_width_chars(text or "")
    blocks: List[Dict[str, Any]] = []
    outside_lines: List[str] = []
    fence_char, fence_len, fence_marker, fence_info, start_line, buf = "", 0, "", "", 0, []

    def _blk(end_ln: Optional[int], is_closed: bool) -> Dict[str, Any]:
        return {
            "fence": fence_marker, "char": fence_char, "length": fence_len, "info": fence_info,
            "lang": fence_info.split()[0].lower() if fence_info else "", "content": "\n".join(buf),
            "lines": list(buf), "start_line": start_line, "end_line": end_ln, "closed": is_closed,
        }

    for idx, line in enumerate(clean.splitlines(), start=1):
        if fence_char:
            close_pat = rf"^\s*`{{{fence_len},}}\s*$" if fence_char == "`" else rf"^\s*~{{{fence_len},}}\s*$"
            if re.match(close_pat, line):
                blocks.append(_blk(idx, True))
                fence_char, fence_len, buf = "", 0, []
            else:
                buf.append(line)
            continue
        m_open = _FENCE_OPEN_RE.match(line)
        if m_open:
            fence_marker = m_open.group(1)
            fence_char, fence_len, fence_info, start_line, buf = fence_marker[0], len(fence_marker), m_open.group(2).strip(), idx, []
        else:
            outside_lines.append(line)

    unclosed = bool(fence_char)
    if unclosed:
        blocks.append(_blk(None, False))
    return blocks, unclosed, outside_lines


def _has_nonempty_str(obj: Dict[str, Any], keys: Tuple[str, ...]) -> bool:
    return any(isinstance(obj.get(k), str) and bool(obj[k].strip()) for k in keys)


def _validate_v2_manifest_and_header(obj: Dict[str, Any]) -> bool:
    if not set(obj.keys()).issubset(_V2_ENVELOPE_ALLOWED_KEYS):
        return False
    if obj.get("schema_version") != "2.0.0" or not _has_nonempty_str(obj, ("handoff_id",)):
        return False
    manifest = obj.get("manifest")
    if not isinstance(manifest, dict) or not manifest:
        return False
    if not (_has_nonempty_str(manifest, ("timestamp", "handoff_id")) and _has_nonempty_str(manifest, ("handoff_type", "active_mode", "mode"))):
        return False
    state_sha = obj.get("state_sha256")
    return isinstance(state_sha, str) and bool(re.fullmatch(r"[0-9a-f]{64}", state_sha)) and obj.get("external_live_calls_prohibited") is True


def _validate_v2_structure(obj: Dict[str, Any], mode: str) -> bool:
    """Valida i vincoli strutturali pure-stdlib dell'envelope HANDOFF_V2."""
    if not _validate_v2_manifest_and_header(obj):
        return False
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("handoff_mode") != mode:
        return False
    repos = payload.get("ecosystem_repos")
    if not isinstance(repos, list) or not repos or not all(isinstance(r, dict) for r in repos):
        return False
    if mode == "PASSIVE_STANDBY":
        return payload.get("transcript_raw_jsonl_included") is False
    if mode == "ACTIVE_CONTINUATION":
        abid, reqs = payload.get("active_brief_id"), payload.get("requirements")
        return payload.get("failed_reasoning_included") is False and isinstance(abid, str) and bool(re.fullmatch(r"IB-\d{8}-[A-Z0-9]{6}", abid)) and isinstance(reqs, list) and bool(reqs)
    return True


def _extract_v2_wire_inner(clean: str) -> Optional[Tuple[str, str]]:
    specs = ((HANDOFF_V2_START_PASSIVE, HANDOFF_V2_END_PASSIVE, "PASSIVE_STANDBY"), (HANDOFF_V2_START_ACTIVE, HANDOFF_V2_END_ACTIVE, "ACTIVE_CONTINUATION"))
    matched = next(((s, e, m) for s, e, m in specs if clean.startswith(s)), None)
    if matched is None:
        return None
    start_tag, end_tag, mode = matched
    if not clean.endswith(end_tag) or clean.count(start_tag) != 1 or clean.count(end_tag) != 1 or clean.lower().count("[nk-anchor:") != 2:
        return None
    inner = clean[len(start_tag) : len(clean) - len(end_tag)]
    if not inner.startswith(("\n", "\r")) or not inner.endswith(("\n", "\r")):
        return None
    return inner, mode


def _parse_v2_json_payload(inner: str, mode: str) -> Optional[Dict[str, Any]]:
    blocks, unclosed, outside_lines = scan_fences_strict(inner)
    if unclosed or len(blocks) != 1 or blocks[0]["info"].lower() not in ("json", ""):
        return None
    non_empty, banner = [ln.strip() for ln in outside_lines if ln.strip()], f"# [NK-HANDOFF-V2] Mode: {mode}"
    if non_empty and (len(non_empty) != 1 or non_empty[0] != banner or inner.find(banner) > inner.find(blocks[0]["fence"])):
        return None
    try:
        obj = _strict_json_loads(blocks[0]["content"])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def parse_verified_handoff_v2_wire(text: str) -> Optional[Dict[str, Any]]:
    """Valida il wire format HANDOFF_V2 (START a idx 0, END a EOF, banner, 1 JSON, SHA-256)."""
    clean = strip_zero_width_chars(text or "").strip()
    extracted = _extract_v2_wire_inner(clean) if clean else None
    if extracted is None:
        return None
    inner, mode = extracted
    obj = _parse_v2_json_payload(inner, mode)
    env_sha = obj.get("envelope_sha256") if obj is not None else None
    if obj is None or not isinstance(env_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", env_sha):
        return None
    try:
        expected_sha = compute_envelope_sha256_stdlib(obj)
    except Exception:
        return None
    return obj if (hmac.compare_digest(env_sha, expected_sha) and _validate_v2_structure(obj, mode)) else None


def _validate_t12_prefix(prefix: str) -> Optional[str]:
    if not prefix.endswith(("\n", "\r")):
        return "INVALID_T12_PREFIX"
    plines = [ln.strip() for ln in prefix.splitlines() if ln.strip()]
    if len(plines) not in (1, 2) or plines[0] != T12_HEADER_PREFIX:
        return "INVALID_T12_HEADER"
    if len(plines) == 2 and (not plines[1].startswith(("Modalità:", "Modalita:")) or len(plines[1]) > 120 or "`" in plines[1]):
        return "INVALID_T12_MODE_LINE"
    return None


def check_legacy_t12_framing(text: str) -> Tuple[bool, str]:
    """Verifica il framing strutturale canonico del Template 12 legacy."""
    clean = strip_zero_width_chars(text or "").strip()
    if not clean or clean.count(T12_START) != 1 or clean.count(T12_END) != 1 or clean.lower().count("[nk-anchor:") != 2:
        return False, "INVALID_T12_ANCHORS"
    if not clean.endswith(T12_END):
        return False, "T12_END_NOT_AT_EOF"
    start_idx = clean.find(T12_START)
    if start_idx > 0 and (err := _validate_t12_prefix(clean[:start_idx])):
        return False, err
    inner = clean[start_idx + len(T12_START) : len(clean) - len(T12_END)]
    _, unclosed, outside_lines = scan_fences_strict(inner)
    if unclosed:
        return False, "UNCLOSED_FENCE"
    if "### 1." not in "\n".join(outside_lines):
        return False, "MISSING_SECTION_1"
    return True, ("HAS_SHA" if re.search(r"\b[0-9a-fA-F]{64}\b", inner) else "PROVENANCE_UNVERIFIED")


def _decode_json_or_jsonl(raw_json: str) -> Optional[Any]:
    """Decodifica una stringa JSON strict o sequenza JSONL di dizionari."""
    try:
        parsed = _strict_json_loads(raw_json)
        return parsed if isinstance(parsed, (dict, list)) else None
    except Exception:
        try:
            recs = [_strict_json_loads(ln.strip()) for ln in raw_json.splitlines() if ln.strip()]
            return recs if (recs and all(isinstance(r, dict) for r in recs)) else None
        except Exception:
            return None


def _parse_sealed_t12_json_capsule(text: str) -> Optional[Any]:
    """Decodifica la capsula JSON/JSONL di un T12 legacy valido, o None se non sigillata."""
    clean = strip_zero_width_chars(text or "").strip()
    t12_ok, _ = check_legacy_t12_framing(clean)
    s_idx, e_idx = clean.find(T12_START), clean.rfind(T12_END)
    if not t12_ok or s_idx == -1 or e_idx <= s_idx:
        return None
    blocks, unclosed, _ = scan_fences_strict(clean[s_idx + len(T12_START) : e_idx])
    if unclosed or len(blocks) != 1:
        return None
    if str(blocks[0].get("info", "")).strip().lower() not in ("json", ""):
        return None
    raw_json = str(blocks[0].get("content", "")).strip()
    return _decode_json_or_jsonl(raw_json) if raw_json else None


def is_sealed_t12_json_capsule(text: str) -> bool:
    """Verifica che T12 legacy sia sigillato con esattamente una capsula JSON/JSONL valida."""
    return _parse_sealed_t12_json_capsule(text) is not None


def extract_t12_scan_lines(text: str) -> Tuple[List[str], List[str]]:
    """Separa righe T12 strette e righe in fence neutri chiusi, esentando capsule JSON sigillate."""
    clean = strip_zero_width_chars(text or "").strip()
    blocks, unclosed, outside_lines = scan_fences_strict(clean)
    if is_sealed_t12_json_capsule(clean):
        return outside_lines, []
    strict_lines, neutral_lines = list(outside_lines), []
    for blk in blocks:
        dst = neutral_lines if (not unclosed and blk["closed"] and blk["lang"] in _NEUTRAL_FENCE_LANGS) else strict_lines
        dst.extend(blk["lines"])
    return strict_lines, neutral_lines
