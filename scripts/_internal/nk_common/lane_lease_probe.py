# -*- coding: utf-8 -*-
"""Sonda lease-aware pure-stdlib per _scan_dirty_orphans e isolamento epistemic conflicts."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Optional, Set

from _internal.nk_common.lane_leases import is_pid_lease_alive, list_active_leases
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.lane_registry import list_active_lanes

_ACTIVE_2PC_DOT_TMP_RE = re.compile(
    r"^(?:\.staging_(?P<stg>.+?)\.tx_[a-zA-Z0-9_]+|\.(?:shadow|old)_(?P<shd>.+?)_[a-fA-F0-9]{6,12})\.tmp$"
)


def _casefold_rel(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.lstrip("/").lower()


def _extract_2pc_dot_tmp_target_name(filename: str) -> Optional[str]:
    """Estrae il nome file target solo per pattern dot-tmp 2PC (mai *.bak o foo.tmp)."""
    match = _ACTIVE_2PC_DOT_TMP_RE.fullmatch(str(filename or ""))
    if not match:
        return None
    return match.group("stg") or match.group("shd")


def _active_leased_write_sets(root: Path, registry_path: Optional[Path]) -> Set[str]:
    """Raccoglie il write-set normalizzato delle lane che hanno sia lease vivo sia registrazione."""
    leases = list_active_leases(root, prune_dead=True, registry_path=registry_path)
    live_lanes = {
        str(rec.get("lane_id") or "").strip()
        for rec in leases
        if isinstance(rec, dict)
        and is_pid_lease_alive(int(rec.get("pid", 0) or 0), rec.get("process_create_time_epoch"))
    }
    if not live_lanes:
        return set()
    allowed_paths: Set[str] = set()
    active_lanes = list_active_lanes(root)
    for lid in live_lanes:
        lane_rec = active_lanes.get(lid)
        if not isinstance(lane_rec, dict):
            continue
        for item in lane_rec.get("declared_write_set", ()) or ():
            cf = _casefold_rel(item)
            if cf:
                allowed_paths.add(cf)
    return allowed_paths


def is_active_2pc_dot_tmp(
    fpath: Path,
    root: Path,
    *,
    now_ts: Optional[float] = None,
    max_age_sec: float = 15.0,
    registry_path: Optional[Path] = None,
) -> bool:
    """Esenta solo dot-tmp 2PC < 15s di una lane con PID vivo e target nel write-set."""
    target_name = _extract_2pc_dot_tmp_target_name(fpath.name)
    if not target_name:
        return False
    try:
        st = os.lstat(str(fpath))
    except OSError:
        return False
    eff_now = time.time() if now_ts is None else float(now_ts)
    age_s = eff_now - float(st.st_mtime)
    if age_s < 0.0 or age_s >= float(max_age_sec):
        return False
    try:
        rel_target = (fpath.parent / target_name).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return False
    target_cf = _casefold_rel(rel_target)
    if not target_cf:
        return False
    return target_cf in _active_leased_write_sets(Path(root).resolve(), registry_path)


def resolve_epistemic_conflict_paths(root: Path, lane_id: Optional[str] = None) -> List[Path]:
    """Restituisce i percorsi di epistemic conflict isolati per lane o legacy."""
    base = Path(root)
    if lane_id is not None and str(lane_id).strip():
        norm = validate_lane_id(lane_id)
        fname = f"lane_{norm}.json"
        return [
            base / ".staging" / "lanes" / norm / "nk_tracking" / "epistemic_conflicts" / fname,
            base / "nk_tracking" / "epistemic_conflicts" / fname,
        ]
    return [
        base / ".staging" / "nk_tracking" / "epistemic_conflict_report.json",
        base / "nk_tracking" / "epistemic_conflict_report.json",
    ]
