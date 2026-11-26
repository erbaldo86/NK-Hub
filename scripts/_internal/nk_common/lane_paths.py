# -*- coding: utf-8 -*-
"""SSOT pure-stdlib per percorsi .staging/lanes/<lane_id>/ e protezione reparse."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from _internal.nk_common.staging_manifest import (
    LANE_CONTAINER_DIRNAME,
    LANE_REGISTRY_FILENAME,
    is_lane_container_entry,
    is_reparse_entry,
)

LANE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

_WIN32_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
RESERVED_LANE_IDS = frozenset(
    {"lanes", "legacy", "active", "default", "index", "all"}
    | _WIN32_DEVICE_NAMES
)


def validate_lane_id(raw: Optional[str]) -> str:
    """Valida e normalizza un lane_id rifiutando nomi riservati e device Win32."""
    if not isinstance(raw, str):
        raise ValueError(f"lane_id non valido: atteso str, ricevuto {type(raw).__name__}")
    clean = raw.strip()
    if not clean or "/" in clean or "\\" in clean or ".." in clean or "\x00" in clean:
        raise ValueError(f"lane_id non valido: {raw!r}")
    low = clean.lower()
    if not LANE_ID_RE.fullmatch(low) or low in RESERVED_LANE_IDS:
        raise ValueError(f"lane_id non conforme o riservato: {raw!r}")
    return low


def extract_lane_plan_id_from_rel_parts(rel_parts: Sequence[str]) -> Optional[str]:
    """Restituisce il lane_id se rel_parts punta a nk_genome/plans/<lane_id>.md valido."""
    if len(rel_parts) != 3:
        return None
    p0, p1, p2 = str(rel_parts[0]).lower(), str(rel_parts[1]).lower(), str(rel_parts[2])
    if p0 != "nk_genome" or p1 != "plans" or not p2.lower().endswith(".md"):
        return None
    try:
        return validate_lane_id(Path(p2).stem)
    except ValueError:
        return None


def is_valid_lane_plan_rel_parts(rel_parts: Sequence[str]) -> bool:
    """True se rel_parts indica un piano di lane nk_genome/plans/<lane_id>.md valido."""
    return extract_lane_plan_id_from_rel_parts(rel_parts) is not None


def strip_staging_rel_parts(
    parts: Sequence[str],
) -> Tuple[int, Tuple[str, ...], Optional[str]]:
    """Estrae (idx_staging, rel_parts_puliti, lane_id_opzionale) da un percorso scomposto."""
    for idx, part in enumerate(parts):
        if str(part).lower() == ".staging":
            tail = tuple(str(p) for p in parts[idx + 1 :])
            if len(tail) >= 2 and tail[0].lower() == LANE_CONTAINER_DIRNAME:
                return idx, tail[2:], tail[1]
            return idx, tail, None
    return -1, tuple(str(p) for p in parts), None


def extract_lane_id_from_path(path: Union[str, Path]) -> Optional[str]:
    """Restituisce il lane_id se path risiede sotto .staging/lanes/<id>/..., altrimenti None."""
    try:
        parts = Path(path).parts
    except Exception:
        return None
    idx, _rel, raw_lane = strip_staging_rel_parts(parts)
    if idx < 0 or raw_lane is None:
        return None
    return raw_lane.strip() or None


def assert_safe_staging_ancestors(
    legacy_stg: Path, target_stg: Path, *, uses_lane: bool
) -> None:
    """Rifiuta symlink, junction o reparse point sulla gerarchia di staging."""
    if is_reparse_entry(legacy_stg):
        raise OSError(f"Reparse point vietato su .staging: {legacy_stg}")
    if uses_lane:
        lanes_dir = legacy_stg / LANE_CONTAINER_DIRNAME
        if is_reparse_entry(lanes_dir):
            raise OSError(f"Reparse point vietato su .staging/lanes: {lanes_dir}")
    if target_stg != legacy_stg and is_reparse_entry(target_stg):
        raise OSError(f"Reparse point vietato sulla directory lane: {target_stg}")


def _resolve_explicit_staging_candidate(
    root: Path, raw_legacy: Path, staging_dir: Union[str, Path]
) -> Tuple[Path, Optional[str]]:
    raw_stg = Path(staging_dir)
    lex_stg = Path(os.path.normpath(str(raw_stg if raw_stg.is_absolute() else (root / raw_stg))))
    if is_reparse_entry(raw_legacy) or is_reparse_entry(lex_stg) or is_reparse_entry(lex_stg.parent):
        raise OSError(f"Reparse point vietato su staging_dir: {lex_stg}")
    if lex_stg.is_relative_to(root) and _has_reparse_in_chain(root, lex_stg):
        raise OSError(f"Reparse point vietato nella gerarchia staging_dir: {lex_stg}")
    raw_lanes = raw_legacy / LANE_CONTAINER_DIRNAME
    if is_reparse_entry(raw_lanes):
        raise OSError(f"Reparse point vietato su .staging/lanes: {raw_lanes}")
    stg_res, lanes_root = lex_stg.resolve(), raw_lanes.resolve()
    if stg_res == lanes_root:
        raise ValueError("Directory contenitore .staging/lanes non utilizzabile direttamente.")
    if stg_res.is_relative_to(lanes_root):
        rel = stg_res.relative_to(lanes_root)
        if len(rel.parts) != 1:
            raise ValueError(f"Percorso lane non valido in staging_dir: {stg_res}")
        return stg_res, validate_lane_id(rel.parts[0])
    return stg_res, None


def resolve_staging_dir(
    repo_root: Union[str, Path],
    *,
    lane_id: Optional[str] = None,
    staging_dir: Optional[Union[str, Path]] = None,
) -> Tuple[Path, Optional[str]]:
    """Risolve (resolved_staging_dir, normalized_lane_id) rifiutando conflitti e reparse."""
    root = Path(repo_root).resolve()
    raw_legacy = root / ".staging"
    if is_reparse_entry(raw_legacy):
        raise OSError(f"Reparse point vietato su .staging: {raw_legacy}")
    norm_lane = validate_lane_id(lane_id) if lane_id is not None else None
    has_stg_arg = staging_dir is not None and bool(str(staging_dir).strip())

    if has_stg_arg:
        stg_res, detected_lane = _resolve_explicit_staging_candidate(
            root, raw_legacy, staging_dir  # type: ignore[arg-type]
        )
        legacy_stg = raw_legacy.resolve()
        if norm_lane is not None:
            raw_lane_dir = raw_legacy / LANE_CONTAINER_DIRNAME / norm_lane
            assert_safe_staging_ancestors(raw_legacy, raw_lane_dir, uses_lane=True)
            if stg_res != raw_lane_dir.resolve():
                raise ValueError(
                    f"Conflitto tra --lane-id ({norm_lane!r}) e --staging-dir ({stg_res})"
                )
        else:
            norm_lane = detected_lane
        target_stg = stg_res
    elif norm_lane is not None:
        raw_lane_dir = raw_legacy / LANE_CONTAINER_DIRNAME / norm_lane
        assert_safe_staging_ancestors(raw_legacy, raw_lane_dir, uses_lane=True)
        legacy_stg, target_stg = raw_legacy.resolve(), raw_lane_dir.resolve()
    else:
        legacy_stg = target_stg = raw_legacy.resolve()

    assert_safe_staging_ancestors(
        legacy_stg, target_stg, uses_lane=(norm_lane is not None)
    )
    return target_stg, norm_lane


def is_skipped_lane_root_entry(base_dir: Path, rel_parts: Sequence[str]) -> bool:
    """True se rel_parts punta a lanes/ sotto .staging/ root."""
    return base_dir.name == ".staging" and bool(rel_parts) and is_lane_container_entry(rel_parts)


def _has_reparse_in_chain(root_dir: Path, target_dir: Path) -> bool:
    """True se target_dir o un antenato fino a root_dir contiene un reparse point."""
    cur = target_dir
    while True:
        if is_reparse_entry(cur):
            return True
        if cur == root_dir or cur.parent == cur:
            break
        cur = cur.parent
    return False


def is_valid_lane_subpath_no_reparse(cand_res: Path, staging_root: Path) -> bool:
    """Valida path dentro .staging/ rifiutando lanes/registry.json, bare lanes/ e reparse."""
    if is_reparse_entry(staging_root):
        return False
    if cand_res == staging_root:
        return True
    try:
        rel_parts = cand_res.relative_to(staging_root).parts
    except ValueError:
        return False
    if rel_parts and rel_parts[0].lower() == LANE_CONTAINER_DIRNAME:
        if len(rel_parts) < 3 or rel_parts[1].lower() == LANE_REGISTRY_FILENAME:
            return False
        try:
            validate_lane_id(rel_parts[1])
        except ValueError:
            return False
    return not _has_reparse_in_chain(staging_root, cand_res)


def is_unsafe_lane_staged_token(tok: str) -> bool:
    """Rileva token .staging/lanes/ malformati, registry.json o senza file figlio."""
    norm = str(tok or "").strip().strip("\"'").replace("\\", "/").lower()
    if ".staging/" not in norm:
        return False
    parts = [p for p in norm.split(".staging/", 1)[1].strip("/").split("/") if p]
    if not parts or parts[0] != LANE_CONTAINER_DIRNAME:
        return False
    if len(parts) < 3 or parts[1] == LANE_REGISTRY_FILENAME:
        return True
    try:
        validate_lane_id(parts[1])
    except ValueError:
        return True
    return False
