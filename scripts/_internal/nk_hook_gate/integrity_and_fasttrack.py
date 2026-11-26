"""Probe diagnostico, integrity anchor Pentad, fast-track e lettura transcript."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from _internal.nk_hook_gate.integrity_anchor_sync import (
    attach_commit_train_anchor_fields,
    compute_or_load_session_start_snapshot,
    verify_valid_advanced_anchor,
)
from _internal.nk_hook_gate.json_io import (
    _extract_first_section,
    _extract_historical_headers,
    _get_hooks_temp_dir,
    _is_path_reparse_point,
    _sha256_file,
    _update_fasttrack_streak,
    _write_json_atomic_safe,
    _write_probe_record,
)
from _internal.nk_hook_gate.path_safety import _resolve_effective_hub_root

_HEX_CHARS = frozenset("0123456789abcdef")


def _is_valid_sha256_hex(val: str) -> bool:
    return len(val) == 64 and all(c in _HEX_CHARS for c in val)


def _is_contained_path(cand: Path, base: Path) -> bool:
    return cand == base or base in cand.parents


def _handle_probe(conv_id: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _write_probe_record(conv_id, event, payload)


def _verify_oracle_lock_files(root: Path, oracle_lock_file: Path) -> List[str]:
    violations: List[str] = []
    if not oracle_lock_file.is_file():
        return violations
    try:
        lock_data = json.loads(oracle_lock_file.read_text(encoding="utf-8"))
    except Exception:
        return ["Invalid JSON in oracle_lock.json"]
    if not isinstance(lock_data, dict):
        return ["Invalid root object in oracle_lock.json"]
    raw_files = lock_data.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        return violations

    root_canon, tests_base = root.resolve(), (root.resolve() / "tests").resolve()
    cur_effective: Dict[str, str] = {}
    had_entry_error = False
    for rel_key, expected_sha in raw_files.items():
        rel_str = str(rel_key)
        cand_tests, cand_root = (tests_base / rel_str).resolve(), (root_canon / rel_str).resolve()
        in_tests_root, in_root = _is_contained_path(cand_tests, root_canon), _is_contained_path(cand_root, root_canon)
        target: Path | None = None
        if in_tests_root and cand_tests.is_file() and not _is_path_reparse_point(cand_tests):
            target = cand_tests
        elif in_root and cand_root.is_file() and not _is_path_reparse_point(cand_root):
            target = cand_root
        elif (not in_tests_root and not in_root) or (not in_root and (cand_root.exists() or os.path.isabs(rel_str))):
            violations.append(f"oracle_lock path escape blocked: {rel_str}")
            had_entry_error = True
            continue
        if target is None:
            violations.append(f"oracle_lock missing target: {rel_str}")
            had_entry_error = True
            continue
        exp_str = str(expected_sha).lower()
        if not _is_valid_sha256_hex(exp_str):
            violations.append(f"oracle_lock invalid SHA-256 entry: {rel_str}")
            had_entry_error = True
            continue
        lf_bytes = target.read_bytes().replace(b"\r\n", b"\n")
        if exp_str not in (hashlib.sha256(lf_bytes).hexdigest(), hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest()):
            violations.append(f"oracle_lock SHA-256 mismatch: {rel_str}")
            had_entry_error = True
        else:
            cur_effective[rel_str] = str(expected_sha)

    saved_combined = str(lock_data.get("combined_sha256", "")).lower()
    if not had_entry_error and len(cur_effective) == len(raw_files) and _is_valid_sha256_hex(saved_combined):
        if hashlib.sha256(json.dumps(cur_effective, sort_keys=True).encode("utf-8")).hexdigest() != saved_combined:
            violations.append("oracle_lock combined_sha256 mismatch")
    return violations


def _hash_tree_manifest(base_dir: Path, root: Path, suffixes: Tuple[str, ...]) -> str:
    entries: Dict[str, str] = {}
    if base_dir.is_dir():
        for fp in sorted(base_dir.rglob("*")):
            if fp.is_file() and fp.suffix.lower() in suffixes and "__pycache__" not in fp.parts and ".pytest_cache" not in fp.parts:
                entries[fp.relative_to(root).as_posix()] = _sha256_file(fp)
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _read_last_telemetry_line(telemetry_file: Path) -> str:
    if not telemetry_file.is_file():
        return ""
    try:
        with open(telemetry_file, "rb") as tf_bin:
            tf_bin.seek(0, os.SEEK_END)
            tf_bin.seek(max(0, tf_bin.tell() - 4096), os.SEEK_SET)
            tail_lines = tf_bin.read().decode("utf-8", errors="replace").splitlines()
    except OSError as exc:
        _ = str(exc)
        return ""
    return next((ln.strip() for ln in reversed(tail_lines) if ln.strip()), "")


def _collect_live_integrity_state(root: Path) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]], Path, str, str, str, str, str]:
    tracking_dir = root / "nk_tracking"
    checkpoints: Dict[str, str] = {}
    if tracking_dir.exists():
        for cp in sorted(tracking_dir.rglob("checkpoint_*.json")):
            if cp.is_file():
                checkpoints[cp.relative_to(root).as_posix()] = _sha256_file(cp)
    patch_info: Dict[str, Dict[str, Any]] = {}
    for pc in (root / "PATCH_NOTES.md", root / "nk_genome" / "PATCH_NOTES.md"):
        if pc.is_file():
            txt = pc.read_text(encoding="utf-8", errors="replace")
            patch_info[pc.relative_to(root).as_posix()] = {"sha256": _sha256_file(pc), "first_section": _extract_first_section(txt), "historical_headers": _extract_historical_headers(txt)}
    oracle_lock_file = tracking_dir / "oracle_lock.json"
    if not oracle_lock_file.is_file() and (root / "oracle_lock.json").is_file():
        oracle_lock_file = root / "oracle_lock.json"
    oracle_sha = _sha256_file(oracle_lock_file) if oracle_lock_file.is_file() else hashlib.sha256(b"").hexdigest()
    tests_sha = _hash_tree_manifest(root / "tests", root, (".py", ".json"))
    scripts_sha = _hash_tree_manifest(root / "scripts", root, (".py",))
    agents_sha = _hash_tree_manifest(root / ".agents", root, (".py", ".md", ".json"))
    last_tel = _read_last_telemetry_line(tracking_dir / "rsi_telemetry.jsonl")
    chain_anchor = hashlib.sha256(f"{oracle_sha}|{tests_sha}|{scripts_sha}|{agents_sha}|{last_tel}".encode("utf-8")).hexdigest()
    return checkpoints, patch_info, oracle_lock_file, oracle_sha, tests_sha, scripts_sha, agents_sha, chain_anchor


def _handle_integrity(
    conv_id: str, project_root: Path, init_mode: bool, check_mode: bool, *, use_start_cache: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Salva con --init o verifica SHA-256 supportando VALID_ADVANCED e cache SessionStart HMAC."""
    state_file = _get_hooks_temp_dir() / f"{conv_id}_integrity.json"
    root = _resolve_effective_hub_root(project_root)

    def _build_snap() -> Dict[str, Any]:
        cps, pinfo, _ol_p, ol_s, ts_s, sc_s, ag_s, anc_s = _collect_live_integrity_state(root)
        return attach_commit_train_anchor_fields(root, {
            "root": root.as_posix(), "checkpoints": cps, "patch_notes": pinfo,
            "oracle_lock_sha256": ol_s, "tests_manifest_sha256": ts_s,
            "scripts_manifest_sha256": sc_s, "agents_manifest_sha256": ag_s, "chain_anchor_sha256": anc_s,
        })

    if init_mode and not check_mode:
        snap, _hit = compute_or_load_session_start_snapshot(root, _build_snap) if use_start_cache else (_build_snap(), False)
        _write_json_atomic_safe(state_file, snap)
        return {
            "status": "INITIALIZED", "passed": True, "checkpoints_count": len(snap["checkpoints"]),
            "oracle_lock_sha256": snap["oracle_lock_sha256"], "tests_manifest_sha256": snap["tests_manifest_sha256"],
            "scripts_manifest_sha256": snap["scripts_manifest_sha256"], "agents_manifest_sha256": snap["agents_manifest_sha256"],
            "chain_anchor_sha256": snap["chain_anchor_sha256"],
        }, 0

    if not state_file.exists():
        return {"status": "UNINITIALIZED", "passed": False, "violations": ["Missing integrity snapshot"]}, 1
    try:
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return {"status": "CORRUPTED_SNAPSHOT", "passed": False, "violations": ["Corrupted integrity snapshot"]}, 1
    except Exception:
        return {"status": "CORRUPTED_SNAPSHOT", "passed": False, "violations": ["Corrupted integrity snapshot"]}, 1

    cps, pinfo, ol_file, ol_s, ts_s, sc_s, ag_s, anc_s = _collect_live_integrity_state(root)
    cur_snap = attach_commit_train_anchor_fields(root, {
        "root": root.as_posix(), "checkpoints": cps, "patch_notes": pinfo, "oracle_lock_sha256": ol_s,
        "tests_manifest_sha256": ts_s, "scripts_manifest_sha256": sc_s,
        "agents_manifest_sha256": ag_s, "chain_anchor_sha256": anc_s,
    })
    history_violations: List[str] = []
    for rel_cp, old_sha in saved.get("checkpoints", {}).items():
        if (cur_sha := cps.get(rel_cp)) is None:
            history_violations.append(f"Deleted historical checkpoint: {rel_cp}")
        elif cur_sha != old_sha:
            history_violations.append(f"Tampered historical checkpoint: {rel_cp}")
    for rel_pn, old_meta in saved.get("patch_notes", {}).items():
        pn_file = root / rel_pn
        if not pn_file.is_file():
            history_violations.append(f"Deleted PATCH_NOTES file: {rel_pn}")
            continue
        cur_txt = pn_file.read_text(encoding="utf-8", errors="replace")
        norm_cur = "\n".join(ln.strip() for ln in cur_txt.splitlines() if ln.strip())
        req_sec = old_meta.get("first_section", "")
        cur_headers = set(_extract_historical_headers(cur_txt))
        if (req_sec and req_sec not in cur_txt and req_sec not in norm_cur) or any(h not in cur_headers for h in old_meta.get("historical_headers", [])):
            history_violations.append(f"Destructive overwrite of history in {rel_pn}")

    violations, drift_detected = list(history_violations), False
    for key, label in (("oracle_lock_sha256", "Tampered or deleted oracle_lock.json"), ("tests_manifest_sha256", "Tampered tests/ manifest SHA-256"), ("scripts_manifest_sha256", "Tampered scripts/ manifest SHA-256"), ("agents_manifest_sha256", "Tampered .agents/ manifest SHA-256")):
        if key not in saved or cur_snap[key] != saved.get(key):
            violations.append(label)
            drift_detected = True
    ol_lock_viols = _verify_oracle_lock_files(root, ol_file)
    violations.extend(ol_lock_viols)
    saved_anchor = saved.get("chain_anchor_sha256")
    if (not isinstance(saved_anchor, str) or not saved_anchor or saved_anchor != anc_s) and not drift_detected:
        violations.append("Tampered chain_anchor_sha256 or telemetry anchor")

    if violations:
        adv_ok, adv_status, adv_meta = verify_valid_advanced_anchor(root, saved, cur_snap, oracle_lock_violations=ol_lock_viols, history_violations=history_violations)
        if adv_ok:
            _write_json_atomic_safe(state_file, cur_snap)
            return {"status": adv_status, "passed": True, "violations": [], **adv_meta, "oracle_lock_sha256": ol_s, "tests_manifest_sha256": ts_s, "scripts_manifest_sha256": sc_s, "agents_manifest_sha256": ag_s, "chain_anchor_sha256": anc_s}, 0

    passed = len(violations) == 0
    return {"status": "VALID" if passed else "VIOLATION", "passed": passed, "violations": violations, "oracle_lock_sha256": ol_s, "tests_manifest_sha256": ts_s, "scripts_manifest_sha256": sc_s, "agents_manifest_sha256": ag_s, "chain_anchor_sha256": anc_s}, (0 if passed else 1)


def _handle_fasttrack(conv_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _update_fasttrack_streak(conv_id, payload)


def _extract_last_planner_message(transcript_path: Path) -> str:
    last_msg = ""
    if not transcript_path.is_file():
        return last_msg
    for raw in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        rec_type = str(rec.get("type") or "").upper()
        src = str(rec.get("source") or rec_type or rec.get("role") or "").upper()
        if rec_type == "GENERIC" and src == "MODEL":
            continue
        content = str(rec.get("content") or rec.get("message") or rec.get("response") or "")
        if src in ("PLANNER_RESPONSE", "ASSISTANT", "MODEL") and content.strip():
            last_msg = content
    return last_msg
