#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica live V2/T12 per nk_session_bootstrap con Fast-Stat NVMe (<60ms warm)."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.paths import resolve_nk_proget_roots
from _internal.nk_session_bootstrap.handoff_verify_io import (  # noqa: F401
    _DEFAULT_SKIP_DIRS, _DEFAULT_SKIP_FILES, _FASTSTAT_TTL_SEC, _SAFE_CID_RE, _V2_HINT_RE,
    _ensure_handoff_staging_overlay, _find_fallback_prompt_file, _get_state_exclusions,
    _inspect_anchor_tail, _is_repo_root_in_scope, _is_valid_cid, _read_anchor_tail_cid,
    _resolve_live_state_sha256, _sanitize_cid, _scan_tracked_metadata, atomic_write_text,
)


def _staging_sigs(entries: Sequence[Any]) -> Tuple[List[Tuple[str, str]], bool]:
    sigs: List[Tuple[str, str]] = []
    has_sha = False
    for item in entries:
        if isinstance(item, dict):
            sh = str(item.get("sha256") or "")
            has_sha = has_sha or bool(sh)
            sigs.append((str(item.get("rel_path") or item.get("path") or "").replace("\\", "/"), sh))
        else:
            sigs.append((str(item).replace("\\", "/"), ""))
    return sorted(sigs), has_sha


def _has_staging_drift(live_entries: Sequence[Any], snap: Dict[str, Any]) -> bool:
    """Verifica discrepanze tra stato .staging/ live e snapshot atteso."""
    if (len(live_entries) > 0) != bool(snap.get("staging_dirty", False)):
        return True
    snap_sigs, snap_has_sha = _staging_sigs(snap.get("staging_entries") or [])
    live_sigs, _ = _staging_sigs(live_entries)
    if not snap_sigs and not live_sigs:
        return False
    return (live_sigs if snap_has_sha else [(p, "") for p, _ in live_sigs]) != snap_sigs


def _check_staging_and_conc_drifts(repo_root: Path, snap: Dict[str, Any], current_cid: str, target_repo_ids: Sequence[str], session_start_ns: int, walk_fn: Any, exempt_cids: Sequence[str], drifts: List[str]) -> Tuple[bool, int, List[str]]:
    """Esegue la scansione live di .staging/ e registra drift di staging, anchor o scrittori."""
    import inspect

    try:
        walk_kw = {"exempt_cids": exempt_cids} if "exempt_cids" in inspect.signature(walk_fn).parameters else {}
    except (TypeError, ValueError):
        walk_kw = {}
    live_entries, conc_det, conc_cids, anc_warn = walk_fn(repo_root, current_cid, target_repo_ids, session_start_ns, **walk_kw)
    if _has_staging_drift(live_entries, snap):
        drifts.append("STAGING_DRIFT")
    if conc_det or conc_cids:
        drifts.append("CONCURRENT_SESSION_WRITE")
    if anc_warn:
        drifts.append("ANCHOR_CORRUPTED" if anc_warn == "CORRUPT_ANCHOR_TAIL" else "CONCURRENT_SESSION_WRITE")
    return len(live_entries) > 0, len(live_entries), list(conc_cids or [])


def _check_patch_notes_drift(repo_root: Path, snap: Dict[str, Any], pn_fn: Any, drifts: List[str]) -> str:
    """Verifica coerenza SHA-256 di PATCH_NOTES rispetto allo snapshot."""
    live_pn_res = pn_fn(repo_root)
    raw_head = live_pn_res.get("patch_notes_head")
    live_pn_sha = str((raw_head if isinstance(raw_head, dict) else live_pn_res).get("patch_notes_sha256") or "")
    snap_pn = snap.get("patch_notes_head") if isinstance(snap.get("patch_notes_head"), dict) else {}
    expected_pn = str(snap_pn.get("patch_notes_sha256") or snap.get("patch_notes_sha256") or "").strip()
    if expected_pn and live_pn_sha != expected_pn:
        drifts.append("SHA256_MISMATCH")
    return live_pn_sha


def _check_anchor_cid_drift(repo_root: Path, snap: Dict[str, Any], current_cid: str, exempt_cids: Sequence[str], drifts: List[str]) -> None:
    """Verifica integrita tail session_anchor.jsonl e assenza di scrittori concorrenti."""
    live_cid, anchor_corrupt = _inspect_anchor_tail(repo_root, current_cid)
    if anchor_corrupt:
        drifts.append("ANCHOR_CORRUPTED")
    expected_cid = str(snap.get("tracking_last_conversation_id") or "").strip()
    allowed = ({expected_cid} if expected_cid else set()) | set(exempt_cids)
    if expected_cid and live_cid and live_cid not in allowed:
        drifts.append("CONCURRENT_SESSION_WRITE")


def _build_allowed_repo_roots(hub_res: Path, proj_res: Path) -> Tuple[Path, ...]:
    """Costruisce la tupla di root consentite includendo NK Proget/Locale quando esistente."""
    roots: List[Path] = [hub_res, proj_res, (hub_res.parent / "NK_External_Projects").resolve()]
    locale_root, _ = resolve_nk_proget_roots(hub_res)
    if locale_root is not None and locale_root.exists():
        roots.append(locale_root.resolve())
    return tuple(roots)


def _verify_single_repo(repo_id: str, repo_root: Path, snap: Dict[str, Any], current_cid: str, target_repo_ids: Sequence[str], session_start_ns: int, deps: Tuple[Any, Any, Any], exempt_cids: Sequence[str] = (), allowed_roots: Optional[Sequence[Path]] = None) -> Tuple[str, Dict[str, Any]]:
    """Verifica contenimento scope, SHA-256, .staging/ non cachato, PATCH_NOTES e anchor."""
    if allowed_roots is not None and not _is_repo_root_in_scope(repo_root, allowed_roots):
        return repo_id, {"repo_id": repo_id, "repo_root": str(repo_root), "status": "DRIFT", "cache_mode": "OUT_OF_SCOPE", "drifts": ["REPO_OUT_OF_SCOPE"]}
    walk_fn, pn_fn, compute_sha_fn = deps
    if not repo_root.is_dir():
        return repo_id, {"repo_id": repo_id, "repo_root": str(repo_root), "status": "DRIFT", "cache_mode": "MISSING", "drifts": ["REPO_MISSING", "SHA256_MISMATCH"]}
    drifts: List[str] = []
    live_dirty, stg_cnt, conc_list = _check_staging_and_conc_drifts(repo_root, snap, current_cid, target_repo_ids, session_start_ns, walk_fn, exempt_cids, drifts)
    live_state_sha, cache_mode = _resolve_live_state_sha256(repo_root, compute_sha_fn)
    expected_sha = str(snap.get("state_sha256") or "").strip()
    if expected_sha and live_state_sha != expected_sha:
        drifts.append("SHA256_MISMATCH")
    live_pn_sha = _check_patch_notes_drift(repo_root, snap, pn_fn, drifts)
    _check_anchor_cid_drift(repo_root, snap, current_cid, exempt_cids, drifts)
    u_drifts = list(dict.fromkeys(drifts))
    return repo_id, {"repo_id": repo_id, "repo_root": str(repo_root), "status": "DRIFT" if u_drifts else "OK", "cache_mode": cache_mode, "live_state_sha256": live_state_sha, "expected_state_sha256": expected_sha, "staging_dirty": live_dirty, "staging_count": stg_cnt, "patch_notes_sha256": live_pn_sha, "concurrent_writer_cids": conc_list, "drifts": u_drifts}


def _read_transcript_handoff(transcript_path: Optional[Path], has_fb: bool) -> Optional[str]:
    """Legge l'ultimo input utente dal transcript se rilevante come handoff."""
    if transcript_path is None or not Path(transcript_path).is_file():
        return None
    from _internal.nk_common.transcript_io import extract_last_user_input

    if not (last_u := extract_last_user_input(transcript_path, max_bytes=262144)) or not last_u.strip():
        return None
    last_up = last_u.upper()
    has_hint = bool(_V2_HINT_RE.search(last_u) or "PASSIVE_SESSION_STATE_HANDOFF" in last_up or "[NK-ANCHOR:" in last_up)
    return last_u if (has_hint or not has_fb) else None


def _read_handoff_input(project_root: Path, prompt_text: Optional[str], handoff_file: Optional[Path], transcript_path: Optional[Path], hub_root: Optional[Path] = None) -> Tuple[Optional[str], str]:
    if handoff_file is not None:
        hf = Path(handoff_file)
        return (hf.read_text(encoding="utf-8", errors="replace"), "handoff_file") if hf.is_file() else (None, "HANDOFF_FILE_NOT_FOUND")
    if prompt_text is not None:
        return (prompt_text, "prompt_text") if prompt_text.strip() else (None, "EMPTY_PROMPT_TEXT")
    fb_existing = _find_fallback_prompt_file(project_root, hub_root)
    if (tr_u := _read_transcript_handoff(transcript_path, fb_existing is not None)) is not None:
        return tr_u, "transcript"
    if fb_existing is not None:
        return fb_existing.read_text(encoding="utf-8", errors="replace"), "next_session_prompt"
    return None, "EMPTY_OR_MISSING_HANDOFF"


def _spoof_res(t0: float, provenance: str, reason: str, source: str = "", violations: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "HANDOFF_SPOOF_OR_INVALID", "passed": False, "provenance": provenance, "reason": reason, "repos": {}, "duration_ms": round((time.perf_counter() - t0) * 1000, 2)}
    return {**out, **({"source": source} if source else {}), **({"violations": violations} if violations else {})}


def _verify_legacy_t12(t0: float, clean: str, source_kind: str, check_t12_fn: Any, eval_fw_fn: Any) -> Dict[str, Any]:
    """Verifica un handoff legacy T12 rispetto a framing, SHA-256, firewall e AP rules."""
    if _V2_HINT_RE.search(clean):
        return _spoof_res(t0, "INVALID_SIGNATURE", "INVALID_OR_SPOOFED_V2_ENVELOPE", source=source_kind)
    t12_ok, t12_reason = check_t12_fn(clean)
    low = clean.lower()
    bad_sha = ("sha-256" in low or "sha256" in low) and not re.search(r"\b[0-9a-fA-F]{64}\b", clean)
    if not t12_ok or bad_sha:
        return _spoof_res(t0, "INVALID_FRAMING", t12_reason if not t12_ok else "MALFORMED_SHA256", source=source_kind)
    if fw_viols := eval_fw_fn(clean, mode="state-handoff", is_state_handoff=True)[0]:
        return _spoof_res(t0, "FIREWALL_REJECTED", "FIREWALL_VIOLATION", source=source_kind, violations=fw_viols)
    from _internal.nk_common.prompt_linter_core import evaluate_ap_rules
    from _internal.vibe_sprint_router.prompt_linter import is_passive_state_handoff

    ap_res = evaluate_ap_rules(clean, mode="state-handoff")
    if not ap_res.get("passed", False) or not is_passive_state_handoff(clean):
        return _spoof_res(t0, "FIREWALL_REJECTED", "T12_IMPERATIVE_OR_AP_VIOLATION", source=source_kind, violations=ap_res.get("violations"))
    return {"status": "HANDOFF_VERIFY_OK", "passed": True, "handoff_format": "LEGACY_T12", "provenance": "PROVENANCE_UNVERIFIED", "mode": "PASSIVE_STANDBY", "source": source_kind, "repos": {}, "duration_ms": round((time.perf_counter() - t0) * 1000, 2)}


def _build_v2_repo_specs(project_root: Path, v2_obj: Dict[str, Any], v2_pl: Dict[str, Any], discovered: Dict[str, Path]) -> List[Tuple[str, Path, Dict[str, Any]]]:
    """Costruisce la lista (repo_id, repo_root, snapshot) dai metadati V2."""
    raw_repos = list(v2_pl.get("ecosystem_repos") or []) or [{"repo_id": project_root.name, "repo_root": str(project_root), "state_sha256": v2_obj.get("state_sha256", "")}]
    specs: List[Tuple[str, Path, Dict[str, Any]]] = []
    for s in raw_repos:
        if not isinstance(s, dict):
            continue
        rid = str(s.get("repo_id") or s.get("id") or project_root.name)
        raw_root = str(s.get("repo_root") or "").strip()
        specs.append((rid, Path(raw_root) if raw_root else discovered.get(rid, project_root), s))
    return specs


def _run_repo_pool(repo_specs: List[Tuple[str, Path, Dict[str, Any]]], cid_for_start: str, target_repo_ids: Sequence[str], session_start_ns: int, deps: Tuple[Any, Any, Any], exempt_cids: Tuple[str, ...], allowed_roots: Sequence[Path]) -> Dict[str, Dict[str, Any]]:
    """Esegue la verifica live parallela sui repository e segnala ID duplicati."""
    from concurrent.futures import ThreadPoolExecutor

    per_repo: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(repo_specs)))) as pool:
        for fut in [pool.submit(_verify_single_repo, rid, rroot, snap, cid_for_start, target_repo_ids, session_start_ns, deps, exempt_cids, allowed_roots) for rid, rroot, snap in repo_specs]:
            rid, rres = fut.result()
            if rid not in per_repo:
                per_repo[rid] = rres
                continue
            prev = per_repo[rid]
            prev["drifts"] = list(dict.fromkeys(list(prev.get("drifts") or []) + list(rres.get("drifts") or []) + ["DUPLICATE_REPO_ID"]))
            prev["status"] = "DRIFT"
            if rres.get("cache_mode") != "FAST_STAT_HIT":
                prev["cache_mode"] = rres.get("cache_mode", prev.get("cache_mode"))
    return per_repo


def _resolve_session_start(hub_root: Path, recv_clean: str, sender_cid: str, cid_for_start: str, transcript_path: Optional[Path], v2_man: Dict[str, Any], ss_mod: Any, parse_ts_fn: Any, res_start_fn: Any) -> int:
    """Ricava il timestamp nanosecondi di inizio sessione da fastguard o ancora."""
    for cid_cand in (recv_clean, sender_cid):
        if cid_cand and (ns := ss_mod._read_fastguard_session_start_ns(hub_root, cid_cand)) > 0:
            return ns
    return parse_ts_fn(v2_man.get("timestamp")) or res_start_fn(hub_root, cid_for_start, transcript_path)


def _check_v2_firewall(t0: float, clean: str, v2_mode: str, source_kind: str, eval_fw_fn: Any, check_tier_fn: Any) -> Optional[Dict[str, Any]]:
    """Valida il payload V2 contro il firewall epistemico e le regole tiered passive."""
    fw_viols, fw_meta = eval_fw_fn(clean, mode="handoff-v2", is_state_handoff=(v2_mode == "PASSIVE_STANDBY"))
    if fw_viols:
        return _spoof_res(t0, "FIREWALL_REJECTED", "FIREWALL_VIOLATION", source=source_kind, violations=fw_viols)
    if fw_meta.get("v2_verified") and str(fw_meta.get("v2_mode") or "").upper() in ("PASSIVE_STANDBY", "ACTIVE_CONTINUATION"):
        if tiered_viols := check_tier_fn(fw_meta):
            return _spoof_res(t0, "FIREWALL_REJECTED", "V2_PASSIVE_CONTENT_VIOLATION", source=source_kind, violations=tiered_viols)
    return None


def _extract_v2_ids(v2_obj: Dict[str, Any], v2_man: Dict[str, Any], receiver_cid: Optional[str]) -> Tuple[Tuple[str, ...], str, str, str]:
    """Estrae tuple CID esenti e identificativi sender/receiver dal payload V2."""
    sender_cid = _sanitize_cid(str(v2_obj.get("conversation_id") or v2_man.get("source_conversation_id") or ""))
    recv_clean = _sanitize_cid(str(receiver_cid or ""))
    return tuple(dict.fromkeys(c for c in (sender_cid, recv_clean) if c)), (recv_clean or sender_cid), recv_clean, sender_cid


def _summarize_v2_res(t0: float, v2_mode: str, per_repo: Dict[str, Dict[str, Any]], source_kind: str) -> Dict[str, Any]:
    """Compila il report finale aggregando drift e stato cache dei repository V2."""
    all_drifts = list(dict.fromkeys(d for r in per_repo.values() for d in r.get("drifts", [])))
    all_fast = bool(per_repo) and all(r.get("cache_mode") == "FAST_STAT_HIT" for r in per_repo.values())
    return {"status": "HANDOFF_DRIFT_DETECTED" if all_drifts else "HANDOFF_VERIFY_OK", "passed": True, "handoff_format": "HANDOFF_V2", "provenance": "VERIFIED_V2_SHA256", "mode": v2_mode, "cache_mode": "FAST_STAT_HIT" if all_fast else "COLD_DEEP_HASH", "drift_reasons": all_drifts, "repos": per_repo, "source": source_kind, "duration_ms": round((time.perf_counter() - t0) * 1000, 2)}


def _verify_v2_envelope(t0: float, clean: str, v2_obj: Dict[str, Any], hub_root: Path, project_root: Path, transcript_path: Optional[Path], receiver_cid: Optional[str], source_kind: str, eval_fw_fn: Any, check_tier_fn: Any) -> Dict[str, Any]:
    """Esegue verifica firewall e scansione live multi-repo per un envelope HANDOFF_V2."""
    v2_pl = v2_obj.get("payload") if isinstance(v2_obj.get("payload"), dict) else {}
    v2_mode = str(v2_pl.get("handoff_mode") or "PASSIVE_STANDBY").upper()
    if fw_err := _check_v2_firewall(t0, clean, v2_mode, source_kind, eval_fw_fn, check_tier_fn):
        return fw_err
    _ensure_handoff_staging_overlay()
    from _internal.nk_session_handoff import session_state as ss_mod
    from _internal.nk_session_handoff.ecosystem_scanner import _parse_ts_ns, discover_ecosystem_repos, extract_patch_notes_head, resolve_session_start_ns, walk_staging_entries_recursive

    v2_man = v2_obj.get("manifest") if isinstance(v2_obj.get("manifest"), dict) else {}
    exempt_cids, cid_start, recv_clean, sender_cid = _extract_v2_ids(v2_obj, v2_man, receiver_cid)
    sess_ns = _resolve_session_start(hub_root, recv_clean, sender_cid, cid_start, transcript_path, v2_man, ss_mod, _parse_ts_ns, resolve_session_start_ns)
    hub_res, proj_res = Path(hub_root).resolve(), Path(project_root).resolve()
    allowed_roots = _build_allowed_repo_roots(hub_res, proj_res)
    target_ids = [str(x) for x in (v2_pl.get("target_repo_ids") or []) if str(x).strip()]
    discovered = {p.name: p for p in discover_ecosystem_repos(hub_root, project_root, True)}
    deps = (walk_staging_entries_recursive, extract_patch_notes_head, ss_mod._compute_workspace_state_sha256)
    per_repo = _run_repo_pool(_build_v2_repo_specs(project_root, v2_obj, v2_pl, discovered), cid_start, target_ids, sess_ns, deps, exempt_cids, allowed_roots)
    return _summarize_v2_res(t0, v2_mode, per_repo, source_kind)


def verify_handoff_envelope_live(hub_root: Path, project_root: Path, prompt_text: Optional[str] = None, handoff_file: Optional[Path] = None, transcript_path: Optional[Path] = None, receiver_cid: Optional[str] = None) -> Dict[str, Any]:
    """Verifica live integrita, firewall, staging non cachato e SHA-256 dell'handoff."""
    t0 = time.perf_counter()
    from _internal.nk_common.epistemic_firewall_rules import check_legacy_t12_framing, check_passive_v2_tiered_content, evaluate_epistemic_firewall_rules, parse_verified_handoff_v2_wire, strip_zero_width_chars

    raw_text, source_kind = _read_handoff_input(project_root, prompt_text, handoff_file, transcript_path, hub_root=hub_root)
    if not raw_text or not raw_text.strip():
        return _spoof_res(t0, "INVALID_OR_MISSING", source_kind)
    clean = strip_zero_width_chars(raw_text).strip()
    if (v2_obj := parse_verified_handoff_v2_wire(clean)) is None:
        return _verify_legacy_t12(t0, clean, source_kind, check_legacy_t12_framing, evaluate_epistemic_firewall_rules)
    return _verify_v2_envelope(t0, clean, v2_obj, hub_root, project_root, transcript_path, receiver_cid, source_kind, evaluate_epistemic_firewall_rules, check_passive_v2_tiered_content)
