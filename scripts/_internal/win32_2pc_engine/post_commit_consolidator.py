# -*- coding: utf-8 -*-
"""Consolidamento post-commit in L1: frammenti changelog.d, CAS baseline, store e closure lane."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from _internal.nk_common.commit_train_store import append_commit_train_entry
from _internal.nk_common.lane_registry import release_lane

from .constants import TwoPhaseCommitError
from .io_and_paths import _atomic_write_bytes, _extract_patch_notes_headers, _unlink_with_retry, _win_long_path
from .tensor_session_guard import close_active_tensor_session_post_commit


def _find_patch_notes_target(root: Path) -> Path:
    gen_pn = root / "nk_genome" / "PATCH_NOTES.md"
    return gen_pn if gen_pn.is_file() else (root / "PATCH_NOTES.md")


def _find_patch_notes_insert_index(lines: List[str]) -> int:
    """Trova la prima riga ## dopo eventuale frontmatter YAML --- ... --- e header #."""
    start_idx = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                start_idx = idx + 1
                break
    for idx in range(start_idx, len(lines)):
        if lines[idx].lstrip().startswith("## "):
            return idx
    insert_at = start_idx
    while insert_at < len(lines):
        stripped = lines[insert_at].strip()
        if not stripped or stripped.startswith(("# ", ">", "---")):
            insert_at += 1
            continue
        break
    return insert_at


def _collect_fragment_blocks(fragments: List[Path], existing_headers: set[str]) -> Tuple[List[str], List[str]]:
    new_blocks: List[str] = []
    consumed: List[str] = []
    for frag in fragments:
        consumed.append(frag.name)
        raw_frag = _win_long_path(frag).read_bytes().decode("utf-8-sig", errors="replace").strip()
        if not raw_frag:
            continue
        frag_headers = _extract_patch_notes_headers(raw_frag)
        if frag_headers and all(h in existing_headers for h in frag_headers):
            continue
        new_blocks.append(raw_frag)
        existing_headers.update(frag_headers)
    return new_blocks, consumed


def materialize_changelog_fragments(root: Path, *, milestone: Optional[str] = None) -> List[str]:
    """Unisce atomicamente i frammenti changelog.d/*.md in PATCH_NOTES.md senza perderne lo storico."""
    _ = milestone
    res_root = Path(root).resolve()
    fragments = sorted(
        p for fdir in (res_root / "nk_genome" / "changelog.d", res_root / "changelog.d")
        if fdir.is_dir() for p in fdir.glob("*.md") if p.is_file()
    )
    if not fragments:
        return []
    pn_path = _find_patch_notes_target(res_root)
    existing_txt = _win_long_path(pn_path).read_bytes().decode("utf-8-sig", errors="replace") if pn_path.is_file() else "# Patch Notes\n\n"
    new_blocks, consumed = _collect_fragment_blocks(fragments, set(_extract_patch_notes_headers(existing_txt)))
    if new_blocks:
        lines = existing_txt.splitlines(keepends=True)
        insert_at = _find_patch_notes_insert_index(lines)
        head_part = "".join(lines[:insert_at]).rstrip("\r\n")
        tail_part = "".join(lines[insert_at:]).lstrip("\r\n")
        merged_blocks = "\n\n".join(new_blocks)
        merged = (f"{head_part}\n\n{merged_blocks}\n\n{tail_part}" if head_part else f"{merged_blocks}\n\n{tail_part}").rstrip() + "\n"
        _atomic_write_bytes(pn_path, merged.encode("utf-8"))
    for frag in fragments:
        _unlink_with_retry(frag)
    return consumed


def _sha256_lf_file(fp: Path) -> str:
    return hashlib.sha256(fp.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _hash_tree(base_dir: Path, root: Path, suffixes: Tuple[str, ...]) -> str:
    entries: Dict[str, str] = {}
    if base_dir.is_dir():
        for fp in sorted(base_dir.rglob("*")):
            if fp.is_file() and fp.suffix.lower() in suffixes and "__pycache__" not in fp.parts and ".pytest_cache" not in fp.parts:
                entries[fp.relative_to(root).as_posix()] = _sha256_lf_file(fp)
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def compute_live_chain_anchor_sha256(root: Path) -> str:
    """Calcola chain_anchor_sha256 identico a nk_hook_gate per sincronizzazione multi-lane."""
    res_root = Path(root).resolve()
    oracle_p = res_root / "nk_tracking" / "oracle_lock.json"
    if not oracle_p.is_file():
        oracle_p = res_root / "oracle_lock.json"
    oracle_sha = _sha256_lf_file(oracle_p) if oracle_p.is_file() else hashlib.sha256(b"").hexdigest()
    tests_sha = _hash_tree(res_root / "tests", res_root, (".py", ".json"))
    scripts_sha = _hash_tree(res_root / "scripts", res_root, (".py",))
    agents_sha = _hash_tree(res_root / ".agents", res_root, (".py", ".md", ".json"))
    tel_file = res_root / "nk_tracking" / "rsi_telemetry.jsonl"
    last_tel = ""
    if tel_file.is_file():
        with open(tel_file, "rb") as tf:
            tf.seek(0, os.SEEK_END)
            tf.seek(max(0, tf.tell() - 4096), os.SEEK_SET)
            last_tel = next((ln.strip() for ln in reversed(tf.read().decode("utf-8", errors="replace").splitlines()) if ln.strip()), "")
    return hashlib.sha256(f"{oracle_sha}|{tests_sha}|{scripts_sha}|{agents_sha}|{last_tel}".encode("utf-8")).hexdigest()


def consolidate_post_commit(
    root: Path, *, batch_id: str, lane_id: Optional[str], milestone: Optional[str],
    committed_files: Sequence[str], deleted_files: Sequence[str], staging_manifest_sha256: str,
    baseline_metrics_update: Optional[Dict[str, Any]] = None, expected_baseline_sha256: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Materializza hotspot changelog/baseline, registra Commit Train e chiude la lane."""
    res_root = Path(root).resolve()
    frags = materialize_changelog_fragments(res_root, milestone=milestone)
    if baseline_metrics_update is not None:
        from _internal.quality_baseline_manager.ratchet_core import update_baseline_metrics

        upd = update_baseline_metrics(
            str(res_root / "nk_tracking" / "quality_baseline.json"),
            baseline_metrics_update, reason=milestone or "2PC_PROMOTE", expected_baseline_sha256=expected_baseline_sha256,
        )
        if upd.get("verdict") != "PASS":
            raise TwoPhaseCommitError(f"Aggiornamento CAS quality_baseline fallito: {upd.get('message') or upd}")

    anchor_sha = compute_live_chain_anchor_sha256(res_root)
    entry, _head = append_commit_train_entry(
        res_root, batch_id=batch_id, lane_id=lane_id or "legacy", milestone=milestone or "2PC_PROMOTE",
        committed_files=list(committed_files), deleted_files=list(deleted_files),
        staging_manifest_sha256=staging_manifest_sha256, chain_anchor_sha256=anchor_sha, key_path=key_path,
    )
    close_active_tensor_session_post_commit(res_root, lane_id=lane_id)
    if lane_id is not None:
        release_lane(res_root, lane_id, conv_id=None, force=True)
    return {"committed_seq": int(entry["seq"]), "record_hash": str(entry["record_hash"]), "materialized_fragments": frags, "chain_anchor_sha256": anchor_sha}
