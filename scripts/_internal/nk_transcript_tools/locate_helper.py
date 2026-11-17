# -*- coding: utf-8 -*-
"""Helper discovery, lettura, conteggio e idratazione transcript per nk_transcript_tools."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.transcript_guards import is_subagent_transcript_head
from _internal.nk_transcript_tools.constants import classify_transcript_record


def is_subagent_transcript_file(transcript_path: Path) -> bool:
    """Verifica se un file transcript.jsonl appartiene a un sub-agente."""
    return is_subagent_transcript_head(transcript_path)


def discover_active_main_transcript(
    brain_dir: Optional[Path] = None,
    max_age_seconds: Optional[float] = None,
) -> Optional[Path]:
    """Individua il transcript attivo dell'agente principale escludendo i sub-agenti."""
    base = (
        Path(brain_dir).resolve()
        if brain_dir
        else Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "brain"
    )
    if not base.exists():
        return None
    now = time.time()
    candidates: List[Tuple[float, Path]] = []
    try:
        entries = [e for e in os.scandir(base) if e.is_dir(follow_symlinks=False)]
        dir_cutoff = (
            (now - max(float(max_age_seconds) * 48.0, 86400.0))
            if (max_age_seconds is not None and len(entries) > 25)
            else 0.0
        )
        for entry in entries:
            if dir_cutoff > 0.0:
                try:
                    dst = entry.stat(follow_symlinks=False)
                    if max(getattr(dst, "st_ctime", 0.0), dst.st_mtime) < dir_cutoff:
                        continue
                except OSError:
                    pass
            cand_str = os.path.join(entry.path, ".system_generated", "logs", "transcript.jsonl")
            try:
                mtime = os.stat(cand_str).st_mtime
                if max_age_seconds is None or (now - mtime) <= max_age_seconds:
                    candidates.append((mtime, Path(cand_str)))
            except OSError:
                continue
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, cand in candidates:
        if not is_subagent_transcript_file(cand):
            return cand
    return candidates[0][1]


def count_transcript_steps(transcript_path: Path) -> Tuple[int, int, int]:
    """Conta (valid_json_steps, non_empty_lines, total_raw_chars)."""
    steps = non_empty = total_chars = 0
    if not transcript_path or not transcript_path.is_file():
        return 0, 0, 0
    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            total_chars += len(raw_line)
            stripped = raw_line.strip()
            if not stripped:
                continue
            non_empty += 1
            try:
                if isinstance(json.loads(stripped), dict):
                    steps += 1
            except Exception:
                continue
    return steps, non_empty, total_chars


def load_transcript_records(
    transcript_path: Path,
    only_after_last_turn: bool = False,
    hydrate_truncated: bool = True,
) -> List[Dict[str, Any]]:
    """Carica transcript.jsonl idratando le righe con truncated_fields."""
    if not transcript_path or not transcript_path.is_file():
        return []

    indexed_records: List[Tuple[int, Dict[str, Any]]] = []
    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        for file_line_no, raw in enumerate(f):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
                if isinstance(rec, dict):
                    indexed_records.append((file_line_no, rec))
            except Exception:
                continue

    if not indexed_records:
        return []

    target_slice = indexed_records
    if only_after_last_turn:
        last_boundary = -1
        for idx, (_, rec) in enumerate(indexed_records):
            if classify_transcript_record(rec) in ("USER", "SYSTEM"):
                last_boundary = idx
        if last_boundary >= 0:
            target_slice = indexed_records[last_boundary + 1 :]

    if hydrate_truncated and transcript_path.name == "transcript.jsonl":
        needed_by_line: Dict[int, int] = {}
        needed_by_step: Dict[Any, int] = {}
        for slice_pos, (file_line_no, rec) in enumerate(target_slice):
            trunc = rec.get("truncated_fields")
            if isinstance(trunc, list) and len(trunc) > 0:
                needed_by_line[file_line_no] = slice_pos
                if "step_index" in rec:
                    needed_by_step[rec["step_index"]] = slice_pos

        if needed_by_line:
            full_cand = transcript_path.parent / "transcript_full.jsonl"
            if full_cand.is_file():
                max_needed_line = max(needed_by_line.keys())
                hydrated_positions: Set[int] = set()
                try:
                    with open(full_cand, "r", encoding="utf-8", errors="replace") as ff:
                        for full_line_no, full_raw in enumerate(ff):
                            if full_line_no in needed_by_line:
                                s_pos = needed_by_line[full_line_no]
                                try:
                                    full_rec = json.loads(full_raw)
                                    if isinstance(full_rec, dict):
                                        orig_step = target_slice[s_pos][1].get("step_index")
                                        if orig_step is None or full_rec.get("step_index") == orig_step:
                                            target_slice[s_pos] = (full_line_no, full_rec)
                                            hydrated_positions.add(s_pos)
                                except Exception:
                                    pass
                                if len(hydrated_positions) >= len(needed_by_line) and full_line_no >= max_needed_line:
                                    break
                            elif len(hydrated_positions) < len(needed_by_line) and needed_by_step and '"step_index"' in full_raw:
                                try:
                                    full_rec = json.loads(full_raw)
                                    if isinstance(full_rec, dict):
                                        st_idx = full_rec.get("step_index")
                                        if st_idx in needed_by_step and needed_by_step[st_idx] not in hydrated_positions:
                                            pos_s = needed_by_step[st_idx]
                                            target_slice[pos_s] = (full_line_no, full_rec)
                                            hydrated_positions.add(pos_s)
                                except Exception:
                                    pass
                except OSError:
                    pass

    return [rec for _, rec in target_slice]


def locate_transcript(
    transcript_arg: Optional[str] = None,
    conversation_id: Optional[str] = None,
    brain_dir: Optional[Path] = None,
) -> Tuple[Dict[str, Any], int]:
    """Risolve il percorso del transcript privilegiando transcript.jsonl."""
    if transcript_arg:
        p = Path(transcript_arg).resolve()
        if p.is_file():
            return {"status": "LOCATED", "passed": True, "transcript_path": p.as_posix()}, 0
        return {"status": "UNMEASURED", "passed": False, "error": f"Transcript not found: {p}"}, 2

    if conversation_id:
        base = (
            Path(brain_dir).resolve()
            if brain_dir
            else Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "brain"
        )
        for rel in (
            f"{conversation_id}/.system_generated/logs/transcript.jsonl",
            f"{conversation_id}/.system_generated/logs/transcript_full.jsonl",
            f"{conversation_id}/transcript.jsonl",
            f"{conversation_id}/transcript_full.jsonl",
        ):
            cand = base / rel
            if cand.is_file():
                return {"status": "LOCATED", "passed": True, "transcript_path": cand.resolve().as_posix()}, 0
        return {"status": "UNMEASURED", "passed": False, "error": f"No transcript for conversation_id={conversation_id}"}, 2

    return {"status": "UNMEASURED", "passed": False, "error": "Explicit --transcript or --conversation-id required (no st_mtime fallback)."}, 2
