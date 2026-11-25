# -*- coding: utf-8 -*-
"""Builder Two-Tier GT-14 Envelope: Tier A exec digest <= 300 tok e Tier B evidence pack <= 4 KB."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from _internal.nk_common.io import atomic_write_json

DEFAULT_GT14_MAX_TOKENS: int = 300
DEFAULT_GT14_PACK_MAX_BYTES: int = 4096
_SNIPPET_CHAR_CAP: int = 256
_PASS_STATUSES = ("PASS", "CONVERGED_OPTIMAL", "CERTIFIED_PASS", "STATIC_PASS")


def estimate_compact_tokens(payload: Dict[str, Any]) -> int:
    """Stima in modo deterministico i token del JSON compatto (1 token ~ 3.2 byte)."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return math.ceil(len(raw) / 3.2)


def default_gt14_diagnostics_dir() -> Path:
    """Restituisce la directory canonica %TEMP%/nk_diagnostics per i pack GT-14."""
    return Path(tempfile.gettempdir()) / "nk_diagnostics"


def default_gt14_pointer_uri(
    filename: str = "gt14_evidence_pack.json",
    diag_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Genera un pointer_uri canonico dentro %TEMP%/nk_diagnostics."""
    base = (
        Path(diag_dir).resolve()
        if diag_dir is not None
        else default_gt14_diagnostics_dir().resolve()
    )
    safe_name = Path(str(filename or "gt14_evidence_pack.json")).name or "gt14_evidence_pack.json"
    return (base / safe_name).as_uri()


def _derive_certification_tier(
    norm_status: str,
    hard_gate: int,
    explicit_tier: Optional[str],
) -> str:
    if explicit_tier and str(explicit_tier).strip():
        return str(explicit_tier).strip().upper()
    if norm_status in ("CERTIFIED_PASS", "STATIC_PASS", "UNMEASURED"):
        return norm_status
    if norm_status in ("PASS", "CONVERGED_OPTIMAL") and int(hard_gate) == 1:
        return "CERTIFIED_PASS"
    return "FAIL"


def _trim_metrics_to_budget(payload: Dict[str, Any], max_tokens: int) -> None:
    """Riduce in modo controllato metrics mantenendo pointer_uri e chiavi essenziali."""
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return
    for k in list(metrics.keys()):
        if estimate_compact_tokens(payload) <= max_tokens:
            return
        val = metrics[k]
        if isinstance(val, str) and len(val) > 48:
            metrics[k] = val[:45] + "..."
        elif isinstance(val, (list, dict)):
            metrics.pop(k, None)
            payload["metrics_truncated"] = True
    for k in list(metrics.keys()):
        if estimate_compact_tokens(payload) <= max_tokens:
            return
        metrics.pop(k, None)
        payload["metrics_truncated"] = True


def build_gt14_exec_digest(
    status: str,
    hard_gate: int,
    metrics: Dict[str, Any],
    top_findings: Sequence[str],
    pointer_uri: str = "",
    max_tokens: int = DEFAULT_GT14_MAX_TOKENS,
    certification_tier: Optional[str] = None,
) -> Dict[str, Any]:
    """Costruisce il Tier A gt14_exec_digest garantito <= max_tokens con pointer_uri."""
    norm_status = str(status or "FAIL").strip().upper()
    eff_uri = str(pointer_uri or "").strip() or default_gt14_pointer_uri()
    clean_all = [str(item).strip() for item in top_findings if str(item).strip()]
    findings = [item[:120] for item in clean_all[:3]]
    tier = _derive_certification_tier(norm_status, int(hard_gate), certification_tier)

    payload: Dict[str, Any] = {
        "envelope_tier": "gt14_exec_digest",
        "status": norm_status,
        "passed": norm_status in _PASS_STATUSES,
        "hard_gate": int(hard_gate),
        "certification_tier": tier,
        "metrics": dict(metrics or {}),
        "top_findings": findings,
        "pointer_uri": eff_uri,
    }
    if len(clean_all) > 3:
        payload["findings_truncated"] = len(clean_all) - 3
    if estimate_compact_tokens(payload) <= max_tokens:
        return payload

    payload["top_findings"] = [f[:70] for f in findings]
    while estimate_compact_tokens(payload) > max_tokens and payload["top_findings"]:
        payload["top_findings"].pop()
        payload["findings_truncated"] = max(0, len(clean_all) - len(payload["top_findings"]))
    if estimate_compact_tokens(payload) > max_tokens:
        _trim_metrics_to_budget(payload, max_tokens)
    return payload


def _compact_sbfl_window(win: Any, char_cap: int) -> Dict[str, Any]:
    if not isinstance(win, dict):
        return {"snippet": str(win)[:char_cap]}
    out: Dict[str, Any] = {}
    for key in ("file", "line", "symbol", "score", "suspiciousness"):
        if key in win:
            out[key] = win[key]
    raw_code = win.get("snippet", win.get("code", ""))
    if raw_code is not None and str(raw_code):
        out["snippet"] = str(raw_code)[:char_cap]
    return out


def _compact_taint_item(item: Any, char_cap: int = 200) -> Any:
    if isinstance(item, dict):
        return {
            str(k): (v[:char_cap] if isinstance(v, str) else v)
            for k, v in list(item.items())[:8]
        }
    return str(item)[:char_cap]


def _pack_utf8_len(pack: Dict[str, Any]) -> int:
    return len(json.dumps(pack, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _shrink_gt14_evidence_pack(pack: Dict[str, Any], max_bytes: int) -> None:
    """Riduce progressivamente i campi non critici finche il pack rientra in max_bytes."""
    pack["truncated"] = True
    pack.pop("extra_evidence", None)
    for win in pack["sbfl_windows"]:
        if isinstance(win, dict) and isinstance(win.get("snippet"), str):
            win["snippet"] = win["snippet"][:120]
    while _pack_utf8_len(pack) > max_bytes and pack["sast_taint_diff"]:
        pack["sast_taint_diff"].pop()
    while _pack_utf8_len(pack) > max_bytes and pack["sbfl_windows"]:
        pack["sbfl_windows"].pop()
    if _pack_utf8_len(pack) > max_bytes:
        lock = pack.get("oracle_lock_state", {})
        if isinstance(lock, dict) and isinstance(lock.get("mismatches"), list):
            lock["mismatches"] = lock["mismatches"][:5]


def build_gt14_evidence_pack(
    sbfl_windows: Sequence[Any] = (),
    sast_taint_diff: Sequence[Any] = (),
    oracle_lock_state: Optional[Dict[str, Any]] = None,
    extra_evidence: Optional[Dict[str, Any]] = None,
    max_bytes: int = DEFAULT_GT14_PACK_MAX_BYTES,
) -> Dict[str, Any]:
    """Costruisce il Tier B gt14_evidence_pack.json garantito <= 4 KB (4096 byte)."""
    pack: Dict[str, Any] = {
        "envelope_tier": "gt14_evidence_pack",
        "sbfl_windows": [_compact_sbfl_window(w, _SNIPPET_CHAR_CAP) for w in list(sbfl_windows)[:3]],
        "sast_taint_diff": [_compact_taint_item(it) for it in list(sast_taint_diff)[:10]],
        "oracle_lock_state": dict(oracle_lock_state or {}),
    }
    if extra_evidence:
        pack["extra_evidence"] = dict(extra_evidence)
    if _pack_utf8_len(pack) <= max_bytes:
        return pack
    _shrink_gt14_evidence_pack(pack, max_bytes)
    return pack


def write_gt14_two_tier_envelope(
    status: str,
    hard_gate: int,
    metrics: Dict[str, Any],
    top_findings: Sequence[str],
    *,
    sbfl_windows: Sequence[Any] = (),
    sast_taint_diff: Sequence[Any] = (),
    oracle_lock_state: Optional[Dict[str, Any]] = None,
    extra_evidence: Optional[Dict[str, Any]] = None,
    diag_dir: Optional[Union[str, Path]] = None,
    run_id: str = "",
    certification_tier: Optional[str] = None,
    max_digest_tokens: int = DEFAULT_GT14_MAX_TOKENS,
    max_pack_bytes: int = DEFAULT_GT14_PACK_MAX_BYTES,
) -> Dict[str, Any]:
    """Scrive atomicamente Tier B e Tier A in %TEMP%/nk_diagnostics e restituisce l'envelope."""
    out_dir = (
        Path(diag_dir).resolve()
        if diag_dir is not None
        else default_gt14_diagnostics_dir().resolve()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_id = "".join(ch for ch in str(run_id or "") if ch.isalnum() or ch in ("_", "-"))[:24]
    prefix = f"gt14_{clean_id}_" if clean_id else "gt14_"
    pack_path = out_dir / f"{prefix}evidence_pack.json"
    digest_path = out_dir / f"{prefix}exec_digest.json"

    pack = build_gt14_evidence_pack(
        sbfl_windows=sbfl_windows,
        sast_taint_diff=sast_taint_diff,
        oracle_lock_state=oracle_lock_state,
        extra_evidence=extra_evidence,
        max_bytes=max_pack_bytes,
    )
    ok_pack, err_pack = atomic_write_json(
        pack_path, pack, indent=None, separators=(",", ":"), ensure_ascii=False
    )
    if not ok_pack:
        raise OSError(err_pack or f"Impossibile scrivere {pack_path}")

    pointer_uri = pack_path.as_uri()
    digest = build_gt14_exec_digest(
        status=status,
        hard_gate=hard_gate,
        metrics=metrics,
        top_findings=top_findings,
        pointer_uri=pointer_uri,
        max_tokens=max_digest_tokens,
        certification_tier=certification_tier,
    )
    ok_dig, err_dig = atomic_write_json(
        digest_path, digest, indent=None, separators=(",", ":"), ensure_ascii=False
    )
    if not ok_dig:
        raise OSError(err_dig or f"Impossibile scrivere {digest_path}")

    return {
        "gt14_exec_digest": digest,
        "gt14_evidence_pack": pack,
        "pointer_uri": pointer_uri,
        "evidence_pack_path": str(pack_path),
        "exec_digest_path": str(digest_path),
        "evidence_pack_bytes": _pack_utf8_len(pack),
    }
