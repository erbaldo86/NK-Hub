"""Probe diagnostico, integrity anchor Pentad, fast-track e lettura transcript."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    """Verifica formato esadecimale esatto a 64 caratteri per digest SHA-256."""
    return len(val) == 64 and all(c in _HEX_CHARS for c in val)


def _is_contained_path(cand: Path, base: Path) -> bool:
    """Verifica che cand risieda esattamente sotto base senza path escape."""
    return cand == base or base in cand.parents


def _handle_probe(conv_id: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Salva l'evento e le chiavi del payload stdin nel log jsonl della sonda."""
    return _write_probe_record(conv_id, event, payload)


def _verify_oracle_lock_files(root: Path, oracle_lock_file: Path) -> List[str]:
    """Verifica contenimento root, formato SHA-256 valido e hash dei file in oracle_lock.json."""
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

    root_canon = root.resolve()
    tests_base = (root_canon / "tests").resolve()
    cur_effective: Dict[str, str] = {}
    had_entry_error = False

    for rel_key, expected_sha in raw_files.items():
        rel_str = str(rel_key)
        cand_tests = (tests_base / rel_str).resolve()
        cand_root = (root_canon / rel_str).resolve()
        in_tests_root = _is_contained_path(cand_tests, root_canon)
        in_root = _is_contained_path(cand_root, root_canon)

        target: Path | None = None
        if in_tests_root and cand_tests.is_file() and not _is_path_reparse_point(cand_tests):
            target = cand_tests
        elif in_root and cand_root.is_file() and not _is_path_reparse_point(cand_root):
            target = cand_root
        elif (not in_tests_root and not in_root) or (
            not in_root and (cand_root.exists() or os.path.isabs(rel_str))
        ):
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

        raw_bytes = target.read_bytes()
        lf_bytes = raw_bytes.replace(b"\r\n", b"\n")
        lf_sha = hashlib.sha256(lf_bytes).hexdigest()
        crlf_sha = hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest()
        if exp_str not in (lf_sha, crlf_sha):
            violations.append(f"oracle_lock SHA-256 mismatch: {rel_str}")
            had_entry_error = True
        else:
            cur_effective[rel_str] = str(expected_sha)

    saved_combined = str(lock_data.get("combined_sha256", "")).lower()
    if (
        not had_entry_error
        and len(cur_effective) == len(raw_files)
        and _is_valid_sha256_hex(saved_combined)
    ):
        comp_combined = hashlib.sha256(
            json.dumps(cur_effective, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if comp_combined != saved_combined:
            violations.append("oracle_lock combined_sha256 mismatch")
    return violations


def _hash_tree_manifest(
    base_dir: Path, root: Path, suffixes: Tuple[str, ...]
) -> str:
    """Calcola il digest SHA-256 deterministico dei file sotto base_dir escludendo cache."""
    entries: Dict[str, str] = {}
    if base_dir.is_dir():
        for fp in sorted(base_dir.rglob("*")):
            if (
                fp.is_file()
                and fp.suffix.lower() in suffixes
                and "__pycache__" not in fp.parts
                and ".pytest_cache" not in fp.parts
            ):
                rel_fp = fp.relative_to(root).as_posix()
                entries[rel_fp] = _sha256_file(fp)
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _handle_integrity(
    conv_id: str, project_root: Path, init_mode: bool, check_mode: bool
) -> Tuple[Dict[str, Any], int]:
    """Salva con --init o verifica gli hash SHA-256 di checkpoint, test, scripts, .agents e PATCH_NOTES.md."""
    state_file = _get_hooks_temp_dir() / f"{conv_id}_integrity.json"
    root = _resolve_effective_hub_root(project_root)
    tracking_dir = root / "nk_tracking"

    checkpoints: Dict[str, str] = {}
    if tracking_dir.exists():
        for cp in sorted(tracking_dir.rglob("checkpoint_*.json")):
            if cp.is_file():
                rel = cp.relative_to(root).as_posix()
                checkpoints[rel] = _sha256_file(cp)

    patch_candidates = [
        root / "PATCH_NOTES.md",
        root / "nk_genome" / "PATCH_NOTES.md",
    ]
    patch_info: Dict[str, Dict[str, Any]] = {}
    for pc in patch_candidates:
        if pc.is_file():
            rel_p = pc.relative_to(root).as_posix()
            txt = pc.read_text(encoding="utf-8", errors="replace")
            patch_info[rel_p] = {
                "sha256": _sha256_file(pc),
                "first_section": _extract_first_section(txt),
                "historical_headers": _extract_historical_headers(txt),
            }

    oracle_lock_file = tracking_dir / "oracle_lock.json"
    if not oracle_lock_file.is_file() and (root / "oracle_lock.json").is_file():
        oracle_lock_file = root / "oracle_lock.json"
    oracle_lock_sha256 = (
        _sha256_file(oracle_lock_file)
        if oracle_lock_file.is_file()
        else hashlib.sha256(b"").hexdigest()
    )

    tests_manifest_sha256 = _hash_tree_manifest(
        root / "tests", root, (".py", ".json")
    )
    scripts_manifest_sha256 = _hash_tree_manifest(root / "scripts", root, (".py",))
    agents_manifest_sha256 = _hash_tree_manifest(
        root / ".agents", root, (".py", ".md", ".json")
    )

    telemetry_file = tracking_dir / "rsi_telemetry.jsonl"
    last_telemetry_line = ""
    if telemetry_file.is_file():
        try:
            with open(telemetry_file, "rb") as tf_bin:
                tf_bin.seek(0, os.SEEK_END)
                fsize = tf_bin.tell()
                tf_bin.seek(max(0, fsize - 4096), os.SEEK_SET)
                tail_txt = tf_bin.read().decode("utf-8", errors="replace")
            for ln in reversed(tail_txt.splitlines()):
                if ln.strip():
                    last_telemetry_line = ln.strip()
                    break
        except Exception:
            pass

    chain_anchor_sha256 = hashlib.sha256(
        (
            f"{oracle_lock_sha256}|{tests_manifest_sha256}|"
            f"{scripts_manifest_sha256}|{agents_manifest_sha256}|{last_telemetry_line}"
        ).encode("utf-8")
    ).hexdigest()

    if init_mode and not check_mode:
        snap = {
            "root": root.as_posix(),
            "checkpoints": checkpoints,
            "patch_notes": patch_info,
            "oracle_lock_sha256": oracle_lock_sha256,
            "tests_manifest_sha256": tests_manifest_sha256,
            "scripts_manifest_sha256": scripts_manifest_sha256,
            "agents_manifest_sha256": agents_manifest_sha256,
            "chain_anchor_sha256": chain_anchor_sha256,
        }
        _write_json_atomic_safe(state_file, snap)
        return {
            "status": "INITIALIZED",
            "passed": True,
            "checkpoints_count": len(checkpoints),
            "oracle_lock_sha256": oracle_lock_sha256,
            "tests_manifest_sha256": tests_manifest_sha256,
            "scripts_manifest_sha256": scripts_manifest_sha256,
            "agents_manifest_sha256": agents_manifest_sha256,
            "chain_anchor_sha256": chain_anchor_sha256,
        }, 0

    if not state_file.exists():
        return {
            "status": "UNINITIALIZED",
            "passed": False,
            "violations": ["Missing integrity snapshot"],
        }, 1

    try:
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return {
                "status": "CORRUPTED_SNAPSHOT",
                "passed": False,
                "violations": ["Corrupted integrity snapshot"],
            }, 1
    except Exception:
        return {
            "status": "CORRUPTED_SNAPSHOT",
            "passed": False,
            "violations": ["Corrupted integrity snapshot"],
        }, 1

    violations: List[str] = []
    for rel_cp, old_sha in saved.get("checkpoints", {}).items():
        cur_sha = checkpoints.get(rel_cp)
        if cur_sha is None:
            violations.append(f"Deleted historical checkpoint: {rel_cp}")
        elif cur_sha != old_sha:
            violations.append(f"Tampered historical checkpoint: {rel_cp}")

    for rel_pn, old_meta in saved.get("patch_notes", {}).items():
        pn_file = root / rel_pn
        if not pn_file.is_file():
            violations.append(f"Deleted PATCH_NOTES file: {rel_pn}")
            continue
        cur_txt = pn_file.read_text(encoding="utf-8", errors="replace")
        norm_cur = "\n".join(ln.strip() for ln in cur_txt.splitlines() if ln.strip())
        req_sec = old_meta.get("first_section", "")
        saved_headers = old_meta.get("historical_headers", [])
        cur_headers_set = set(_extract_historical_headers(cur_txt))
        missing_hdrs = [h for h in saved_headers if h not in cur_headers_set]
        if (
            req_sec and req_sec not in cur_txt and req_sec not in norm_cur
        ) or missing_hdrs:
            violations.append(f"Destructive overwrite of history in {rel_pn}")

    oracle_tampered = False
    if "oracle_lock_sha256" not in saved or oracle_lock_sha256 != saved.get("oracle_lock_sha256"):
        violations.append("Tampered or deleted oracle_lock.json")
        oracle_tampered = True

    tests_tampered = False
    if "tests_manifest_sha256" not in saved or tests_manifest_sha256 != saved.get("tests_manifest_sha256"):
        violations.append("Tampered tests/ manifest SHA-256")
        tests_tampered = True

    scripts_tampered = False
    if "scripts_manifest_sha256" not in saved or scripts_manifest_sha256 != saved.get("scripts_manifest_sha256"):
        violations.append("Tampered scripts/ manifest SHA-256")
        scripts_tampered = True

    agents_tampered = False
    if "agents_manifest_sha256" not in saved or agents_manifest_sha256 != saved.get("agents_manifest_sha256"):
        violations.append("Tampered .agents/ manifest SHA-256")
        agents_tampered = True

    violations.extend(_verify_oracle_lock_files(root, oracle_lock_file))

    anchor_input_flagged = (
        oracle_tampered or tests_tampered or scripts_tampered or agents_tampered
    )
    saved_anchor = saved.get("chain_anchor_sha256")
    if (
        not isinstance(saved_anchor, str)
        or not saved_anchor
        or saved_anchor != chain_anchor_sha256
    ):
        if not anchor_input_flagged:
            violations.append("Tampered chain_anchor_sha256 or telemetry anchor")

    passed = len(violations) == 0
    return {
        "status": "VALID" if passed else "VIOLATION",
        "passed": passed,
        "violations": violations,
        "oracle_lock_sha256": oracle_lock_sha256,
        "tests_manifest_sha256": tests_manifest_sha256,
        "scripts_manifest_sha256": scripts_manifest_sha256,
        "agents_manifest_sha256": agents_manifest_sha256,
        "chain_anchor_sha256": chain_anchor_sha256,
    }, (0 if passed else 1)


def _handle_fasttrack(conv_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Traccia le chiamate dirette consecutive e avvisa oltre la soglia di 12."""
    return _update_fasttrack_streak(conv_id, payload)


def _extract_last_planner_message(transcript_path: Path) -> str:
    """Estrae l'ultimo messaggio PLANNER_RESPONSE dal file transcript indicato."""
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
        content = str(
            rec.get("content") or rec.get("message") or rec.get("response") or ""
        )
        if src in ("PLANNER_RESPONSE", "ASSISTANT", "MODEL") and content.strip():
            last_msg = content
    return last_msg
