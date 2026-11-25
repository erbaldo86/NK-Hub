# -*- coding: utf-8 -*-
"""Helper puri estratti da tensor_rsi/* per mantenere CC<=baseline, Nest<=2 e LOC<=256."""
from __future__ import annotations
import hashlib, hmac, os, time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

def pareto_add_node(
    entries: List[Dict[str, Any]], entry: Dict[str, Any], max_size: int,
    niche_fn: Callable[[int, int], Tuple[int, int]], sec_fn: Callable[[Any], Tuple[float, ...]],
    dom_fn: Callable[[Tuple[float, ...], Tuple[float, ...]], bool], safe_float_fn: Callable[[Any, float], float],
) -> Optional[List[Dict[str, Any]]]:
    if int(entry.get("g_hard", 0)) != 1:
        return None
    fc, dcc = int(entry.get("file_count", 1)), int(entry.get("delta_cc", 0))
    q_val, sec_t = safe_float_fn(entry.get("q_v2"), 0.0), sec_fn(entry.get("secondary"))
    fp_key, obj_vec = (fc, dcc), (q_val, *sec_t)
    node = {**entry, "niche": niche_fn(fc, dcc), "fp_key": fp_key, "obj_vec": obj_vec, "score": (q_val, sum(sec_t))}
    kept = [e for e in entries if e.get("state_hash") != node.get("state_hash")]
    if any(e.get("fp_key") == fp_key and dom_fn(tuple(e["obj_vec"]), obj_vec) for e in kept):
        return None
    out = [e for e in kept if not (e.get("fp_key") == fp_key and dom_fn(obj_vec, tuple(e["obj_vec"])))] + [node]
    return out[:max_size + 1]

def beta_quantile_bisect(betainc_fn: Callable[[float, float, float], float], successes: float, trials: float, safe_float_fn: Any, q: float = 0.10) -> float:
    s, n = safe_float_fn(successes, -1.0), safe_float_fn(trials, -1.0)
    if n <= 0.0 or s < 0.0:
        return 0.0
    a, b, lo, hi = max(0.5, 0.5 + min(s, n)), max(0.5, 0.5 + max(0.0, n - s)), 0.0, 1.0
    for _ in range(52):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if betainc_fn(a, b, mid) < q else (lo, mid)
    return round(max(0.0, min(1.0, 0.5 * (lo + hi))), 6)

def write_new_key_exclusive(resolved: Path, secret_bytes: bytes, atomic_fn: Any, exc_cls: Any) -> bytes:
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(resolved), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, secret_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
        return secret_bytes
    except FileExistsError:
        raw = resolved.read_bytes().strip()
        if not raw:
            raise exc_cls(f"Chiave HMAC Tensor-RSI vuota: {resolved}")
        return raw
    except OSError as exc:
        ok, err = atomic_fn(resolved, secret_bytes, ensure_parent=True, fsync_data=True)
        if not ok:
            raise exc_cls(f"Impossibile creare chiave HMAC esterna ({resolved}): {err or exc}") from exc
        return secret_bytes

def check_state_cas(state_path: Path, step_seq: int, sid: str, expected_sha: Optional[str], strict_loads: Any, exc_cls: Any) -> None:
    if expected_sha is not None:
        if not state_path.is_file():
            raise exc_cls(f"TICKET_CAS_CONFLICT: stato assente per {sid}.")
        cur = strict_loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(cur, dict) or not hmac.compare_digest(str(cur.get("active_ticket_sha256", "")), str(expected_sha)):
            raise exc_cls("TICKET_CAS_CONFLICT: stato sessione modificato concorrentemente.")
    elif step_seq == 1 and state_path.is_file():
        cur = strict_loads(state_path.read_text(encoding="utf-8"))
        if isinstance(cur, dict) and not cur.get("closed"):
            raise exc_cls(f"ACTIVE_SESSION_CONFLICT: sessione {sid!r} gia attiva.")

def validate_session_record(state_path: Path, ticket: Any, raw_sha: str, allow_closed: bool, allow_exp_closed: bool, eff_now: int, strict_loads: Any, exc_cls: Any) -> Dict[str, Any]:
    if not state_path.is_file():
        raise exc_cls(f"Stato sessione assente per {ticket.session_id}.")
    state = strict_loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or (state.get("closed") and not allow_closed):
        raise exc_cls("Sessione Tensor-RSI chiusa o stato corrotto.")
    if allow_exp_closed and (eff_now - ticket.issued_at > ticket.ttl_seconds) and not state.get("closed"):
        raise exc_cls("State-Ticket fuori finestra temporale (TTL).")
    if int(state.get("active_step_seq", -1)) != ticket.step_seq or not hmac.compare_digest(str(state.get("active_ticket_sha256", "")), raw_sha):
        raise exc_cls("TICKET_REPLAY_DETECTED: step_seq o ticket_sha256 non attivo.")
    if state.get("baseline_state_sha256") != ticket.baseline_state_sha256 or state.get("policy_cell_hash") != ticket.policy_cell_hash:
        raise exc_cls("Baseline SHA-256 o PolicyCell alterati tra i turni.")
    return state

def parse_verified_active_file(active_path: Path, key_path: Any, allow_expired: bool, verify_fn: Any, unlink_fn: Any, strict_loads: Any, exc_cls: Any) -> Optional[Dict[str, Any]]:
    try:
        payload = strict_loads(active_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise exc_cls(f"ACTIVE_SESSION_CONFLICT: ACTIVE.json illeggibile o corrotto ({exc}).") from exc
    if not isinstance(payload, dict):
        raise exc_cls("ACTIVE_SESSION_CONFLICT: ACTIVE.json deve contenere un oggetto JSON.")
    verify_fn(payload, key_path)
    if not allow_expired and int(time.time()) > int(payload["expires_at"]) and payload.get("accepted") is False:
        unlink_fn(active_path, raise_on_error=False)
        return None
    return payload

def next_ledger_prev_hash(ledger_p: Path, read_last_fn: Any, exc_cls: Any) -> str:
    if not (ledger_p.is_file() and ledger_p.stat().st_size > 0):
        return "0" * 64
    last = read_last_fn(ledger_p)
    if not isinstance(last, dict) or not str(last.get("record_hash", "")).strip():
        raise exc_cls("LEDGER_CHAIN_CORRUPT: coda tensor_rsi_ledger.jsonl invalida.")
    return str(last["record_hash"])

def validate_segment_id(session_id: str, candidate_id: str, id_re: Any) -> Tuple[str, str]:
    c_sid, c_cid = str(session_id or "").strip(), str(candidate_id or "").strip()
    for seg in (c_sid, c_cid):
        if seg in ("", ".", "..") or seg.endswith(".") or ".." in seg or not id_re.fullmatch(seg):
            raise ValueError(f"Identificativo session/candidate non valido: {session_id!r}/{candidate_id!r}")
    return c_sid, c_cid

def scan_cand_tree(cand_dir: Path, ignored_suffixes: Tuple[str, ...], reparse_fn: Any, val_rel_fn: Any) -> Dict[str, bytes]:
    payloads: Dict[str, bytes] = {}
    for dp, dns, fns in os.walk(cand_dir, followlinks=False):
        dp_p = Path(dp)
        if "__pycache__" in dp_p.parts:
            dns[:] = []
            continue
        dns[:] = [dn for dn in sorted(dns) if _ensure_safe_subdir(dp_p / dn, dn, reparse_fn)]
        for fn in sorted(fns):
            fp = dp_p / fn
            if reparse_fn(fp):
                raise ValueError(f"File candidato symlink/reparse vietato: {fp}")
            if fp.suffix.lower() not in ignored_suffixes:
                payloads[val_rel_fn(fp.relative_to(cand_dir).as_posix())] = fp.read_bytes()
    return payloads

def _ensure_safe_subdir(sub: Path, dn: str, reparse_fn: Any) -> bool:
    if reparse_fn(sub):
        raise ValueError(f"Sottodirectory candidato symlink/reparse vietata: {sub}")
    return dn != "__pycache__"

def acs_spike_match(cur_tok: int, prev_tok: int, steps: int, acs: Dict[str, Any], fg_data: Dict[str, Any]) -> bool:
    epoch, z3_pre, z3_post = int(fg_data.get("compaction_epoch", 0)), int(fg_data.get("z3_pre_epoch", -1)), int(fg_data.get("z3_post_epoch", -1))
    if (z3_pre >= 0 and z3_pre == epoch) or (z3_post >= 0 and z3_post == epoch):
        return True
    last_vel, direct_vel, jump = max(0, int(fg_data.get("last_velocity_delta", 0))), (max(0, cur_tok - prev_tok) if prev_tok > 0 else 0), int(acs["velocity_jump"])
    return last_vel >= jump or (direct_vel >= jump and (cur_tok >= int(acs["velocity_floor"]) or steps >= int(acs["velocity_step_floor"])))

def resolve_fg_numbers(tok_ov: Optional[int], stp_ov: Optional[int], fg_data: Dict[str, Any]) -> Tuple[int, int, int]:
    cur_tok = max(0, int(tok_ov if tok_ov is not None else fg_data.get("last_actual_tokens", 0)))
    prev_tok = int(fg_data.get("prev_actual_tokens", 0)) if tok_ov is None else 0
    steps = max(0, int(stp_ov if stp_ov is not None else (fg_data.get("steps") or fg_data.get("fallback_steps", 0))))
    return cur_tok, prev_tok, steps

def select_cell_ops(zone: str, intent: str, track: str, file_count: int, track_ops: Tuple[str, ...]) -> Tuple[str, ...]:
    if zone == "Z3" or intent == "AUDIT_RO":
        return ()
    if track == "DOC_TRACK":
        return ("OP_DOC_ALIGN",) if (not track_ops or "OP_DOC_ALIGN" in track_ops) else ()
    if zone in ("Z1", "Z2") or file_count >= 3:
        preferred = ("ISOLATED_SUBAGENT_SLICE", "SURGICAL_LOCAL_PATCH", "TEST_ORACLE_HARDENING")
        return tuple(o for o in preferred if not track_ops or o in track_ops)
    return track_ops or ("SURGICAL_LOCAL_PATCH", "DECOMPOSITION_HELPER_EXTRACT", "TEST_ORACLE_HARDENING", "ISOLATED_SUBAGENT_SLICE")

def evaluate_tier1_pairs(base_pairs: Tuple[Tuple[str, float], ...], curr_pairs: Tuple[Tuple[str, float], ...]) -> Tuple[List[str], bool]:
    import math as _math
    regressions: List[str] = []
    improved = False
    for (name, b_val), (_, c_val) in zip(base_pairs, curr_pairs):
        if not (_math.isfinite(b_val) and _math.isfinite(c_val)):
            regressions.append(f"{name}:non_finite")
        elif c_val + 1e-12 < b_val:
            regressions.append(f"{name}:{b_val:.4f}->{c_val:.4f}")
        elif c_val > b_val + 1e-12:
            improved = True
    return regressions, improved
