# -*- coding: utf-8 -*-
"""Registro NVMe ownership delle lane con Claim Secret >=128-bit off-path (pure stdlib)."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex, ensure_nvme_local_dir
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import repo_path_hash12

_CID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_MAX_CLAIM_TTL_SEC = 10.0


def is_valid_owner_cid(cid: Optional[str]) -> bool:
    """Valida un conversation_id escludendo sentinelle default, default_* e auto (SEC-F1)."""
    if not isinstance(cid, str):
        return False
    clean = cid.strip()
    if not (1 <= len(clean) <= 64) or any(ch not in _CID_CHARS for ch in clean):
        return False
    low = clean.lower()
    return low not in ("auto", "default") and not low.startswith("default_")


def resolve_lane_registry_path(repo_root: Union[str, Path]) -> Path:
    """Restituisce il percorso NVMe sicuro per lane_registry.json del repository."""
    base_dir = ensure_nvme_local_dir(Path(tempfile.gettempdir()) / "nk_parallel", "nk_parallel")
    repo_dir = base_dir / repo_path_hash12(Path(repo_root).resolve())
    if is_reparse_entry(repo_dir):
        raise OSError(f"Reparse point vietato su directory lane_registry: {repo_dir}")
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir / "lane_registry.json"


def _registry_mutex(repo_root: Union[str, Path]) -> FailClosedNamedMutex:
    h12 = repo_path_hash12(Path(repo_root).resolve())
    return FailClosedNamedMutex(f"Local\\NK_LaneRegistry_{h12}", wait_ms=3000)


def _load_registry_unlocked(reg_path: Path) -> Dict[str, Any]:
    if is_reparse_entry(reg_path):
        raise OSError(f"Reparse point vietato su {reg_path}")
    if not reg_path.is_file():
        return {"version": 1, "lanes": {}}
    raw = json.loads(reg_path.read_text(encoding="utf-8"))
    return raw if (isinstance(raw, dict) and isinstance(raw.get("lanes"), dict)) else {"version": 1, "lanes": {}}


def _save_registry_unlocked(reg_path: Path, data: Dict[str, Any]) -> None:
    ok, err = atomic_write_json(
        reg_path, data, indent=2, ensure_ascii=False, ensure_parent=True,
        fsync_data=True, reparse_check=is_reparse_entry,
    )
    if not ok:
        raise OSError(f"Salvataggio atomico lane_registry fallito: {err}")


def _validate_authorized_cids(cids: Sequence[str], owner: str) -> list[str]:
    out = [owner]
    for raw in cids:
        cand = str(raw or "").strip()
        if not is_valid_owner_cid(cand):
            raise ValueError(f"authorized_cid non valido o default_* vietato: {raw!r}")
        if cand not in out:
            out.append(cand)
    return out


def register_lane(
    repo_root: Union[str, Path],
    lane_id: str,
    owner_cid: str,
    *,
    parent_cid: Optional[str] = None,
    authorized_cids: Sequence[str] = (),
    claim_ttl_sec: float = _MAX_CLAIM_TTL_SEC,
    base_repo_seq: int = 0,
    declared_write_set: Sequence[str] = (),
) -> Dict[str, Any]:
    """Registra una lane con owner_cid, parent_cid e Claim Secret >=128-bit solo hash su disco."""
    norm_lane = validate_lane_id(lane_id)
    if not is_valid_owner_cid(owner_cid):
        raise ValueError(f"owner_cid non valido o default_* vietato: {owner_cid!r}")
    owner = owner_cid.strip()
    eff_parent = owner if parent_cid is None else parent_cid.strip()
    if not is_valid_owner_cid(eff_parent):
        raise ValueError(f"parent_cid non valido o default_* vietato: {parent_cid!r}")
    ttl = float(claim_ttl_sec)
    if ttl <= 0.0 or ttl > _MAX_CLAIM_TTL_SEC:
        raise ValueError(f"claim_ttl_sec fuori range (0, 10.0]: {claim_ttl_sec!r}")

    claim_secret = secrets.token_hex(16)
    secret_sha = hashlib.sha256(claim_secret.encode("ascii")).hexdigest()
    now_ts = time.time()
    record: Dict[str, Any] = {
        "lane_id": norm_lane,
        "owner_cid": owner,
        "parent_cid": eff_parent,
        "authorized_cids": _validate_authorized_cids(authorized_cids, owner),
        "claimed_by": None,
        "claim_secret_sha256": secret_sha,
        "claim_expires_at": now_ts + ttl,
        "base_repo_seq": int(base_repo_seq),
        "declared_write_set": sorted({str(p) for p in declared_write_set if str(p).strip()}),
        "active": True,
        "created_at": now_ts,
    }
    reg_path = resolve_lane_registry_path(repo_root)
    with _registry_mutex(repo_root):
        data = _load_registry_unlocked(reg_path)
        existing = data["lanes"].get(norm_lane)
        if (
            isinstance(existing, dict)
            and existing.get("active") is True
            and existing.get("owner_cid") != owner
        ):
            raise PermissionError(
                f"Lane '{norm_lane}' gia attiva per owner diverso: {existing.get('owner_cid')}"
            )
        data["lanes"][norm_lane] = record
        _save_registry_unlocked(reg_path, data)

    return {**record, "claim_secret": claim_secret}


def _verify_claim_preconditions(
    rec: Any, norm_lane: str, parent_cid: Optional[str], claim_secret: str
) -> None:
    if not isinstance(rec, dict) or rec.get("active") is not True:
        raise PermissionError(f"Lane '{norm_lane}' non registrata o inattiva.")
    stored_parent = rec.get("parent_cid")
    if not is_valid_owner_cid(stored_parent):
        raise PermissionError(f"Record lane '{norm_lane}' privo di parent_cid valido.")
    if parent_cid is not None and parent_cid.strip() != stored_parent:
        raise PermissionError(f"parent_cid mismatch su lane '{norm_lane}'.")
    stored_hash = str(rec.get("claim_secret_sha256") or "")
    if len(stored_hash) != 64 or rec.get("claimed_by"):
        raise PermissionError(f"Claim secret gia consumato o non valido per lane '{norm_lane}'.")
    if time.time() > float(rec.get("claim_expires_at", 0.0)):
        raise TimeoutError(f"Claim TTL scaduto per lane '{norm_lane}'.")
    cand_hash = hashlib.sha256(claim_secret.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(stored_hash, cand_hash):
        raise PermissionError(f"Claim secret non valido per lane '{norm_lane}'.")


def claim_lane(
    repo_root: Union[str, Path],
    lane_id: str,
    child_cid: str,
    claim_secret: str,
    *,
    parent_cid: Optional[str] = None,
) -> Dict[str, Any]:
    """Riscatta atomicamente il possesso sub-agente bruciando il Claim Secret monouso."""
    norm_lane = validate_lane_id(lane_id)
    if not is_valid_owner_cid(child_cid):
        raise ValueError(f"child_cid non valido o default_* vietato: {child_cid!r}")
    if not isinstance(claim_secret, str) or not claim_secret.strip():
        raise ValueError("claim_secret obbligatorio per il claim sub-agente.")
    clean_child = child_cid.strip()
    reg_path = resolve_lane_registry_path(repo_root)
    with _registry_mutex(repo_root):
        data = _load_registry_unlocked(reg_path)
        rec = data["lanes"].get(norm_lane)
        _verify_claim_preconditions(rec, norm_lane, parent_cid, claim_secret.strip())
        auth_list = list(rec.get("authorized_cids") or [])
        if clean_child not in auth_list:
            auth_list.append(clean_child)
        rec["authorized_cids"] = auth_list
        rec["claimed_by"] = clean_child
        rec["claim_secret_sha256"] = ""
        rec["claimed_at"] = time.time()
        _save_registry_unlocked(reg_path, data)
        return dict(rec)


def verify_lane_access(
    repo_root: Union[str, Path], lane_id: str, conv_id: Optional[str]
) -> Tuple[bool, str]:
    """Verifica fail-closed se conv_id possiede o e autorizzato su lane_id."""
    try:
        norm_lane = validate_lane_id(lane_id)
    except ValueError:
        return False, "invalid_lane_id"
    if not is_valid_owner_cid(conv_id):
        return False, "invalid_or_default_cid"
    clean_cid = str(conv_id).strip()
    reg_path = resolve_lane_registry_path(repo_root)
    with _registry_mutex(repo_root):
        data = _load_registry_unlocked(reg_path)
        rec = data["lanes"].get(norm_lane)
        if not isinstance(rec, dict) or rec.get("active") is not True:
            return False, "lane_not_registered"
        if rec.get("owner_cid") == clean_cid:
            return True, "owner"
        if clean_cid in (rec.get("authorized_cids") or ()):
            return True, "authorized_child"
        return False, "foreign_cid_denied"


def release_lane(
    repo_root: Union[str, Path],
    lane_id: str,
    conv_id: Optional[str],
    *,
    force: bool = False,
) -> bool:
    """Chiude e rimuove il record della lane se autorizzato o force=True."""
    norm_lane = validate_lane_id(lane_id)
    reg_path = resolve_lane_registry_path(repo_root)
    with _registry_mutex(repo_root):
        data = _load_registry_unlocked(reg_path)
        rec = data["lanes"].get(norm_lane)
        if not isinstance(rec, dict):
            return False
        if not force:
            if not is_valid_owner_cid(conv_id):
                raise PermissionError("release_lane rifiutata per CID non valido o default_*.")
            clean_cid = str(conv_id).strip()
            if clean_cid not in (rec.get("owner_cid"), rec.get("parent_cid")) and clean_cid not in (rec.get("authorized_cids") or ()):
                raise PermissionError(f"CID estraneo non puo rilasciare lane '{norm_lane}'.")
        data["lanes"].pop(norm_lane, None)
        _save_registry_unlocked(reg_path, data)
        return True


def list_active_lanes(repo_root: Union[str, Path]) -> Dict[str, Dict[str, Any]]:
    """Restituisce mappa delle lane attualmente registrate ed attive."""
    reg_path = resolve_lane_registry_path(repo_root)
    with _registry_mutex(repo_root):
        data = _load_registry_unlocked(reg_path)
        return {
            k: dict(v)
            for k, v in data.get("lanes", {}).items()
            if isinstance(v, dict) and v.get("active") is True
        }
