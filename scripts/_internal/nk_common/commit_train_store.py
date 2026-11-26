# -*- coding: utf-8 -*-
"""Store pure-stdlib hash-chained e HMAC per Commit Train (zero pydantic, zero win32_2pc_engine)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from _internal.nk_common.io import atomic_write_json, win_long_path
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex, resolve_local_appdata_dir
from _internal.nk_common.staging_manifest import canonical_json_bytes, is_reparse_entry, is_valid_sha256_hex
from _internal.nk_common.win32_mutex import repo_path_hash12

GENESIS_HASH: str = "0" * 64
COMMIT_TRAIN_DIR_REL: Tuple[str, str] = ("nk_tracking", "commit_train")


def casefold_win32_rel(path_str: str) -> str:
    """Normalizza un percorso relativo in formato POSIX case-folded Win32."""
    raw = str(path_str or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.lstrip("/").lower()


def resolve_commit_train_hmac_key_path(key_path: Optional[Union[str, Path]] = None) -> Path:
    """Risolve la chiave HMAC esterna Commit Train tramite SHGetFolderPathW/LOCALAPPDATA."""
    if key_path is not None and str(key_path).strip():
        cand = Path(str(key_path).strip()).expanduser()
    elif (env_p := os.environ.get("NK_COMMIT_TRAIN_HMAC_KEY_PATH", "").strip()):
        cand = Path(env_p).expanduser()
    else:
        cand = resolve_local_appdata_dir() / "nk_hub" / "commit_train_hmac.key"
    if is_reparse_entry(cand) or is_reparse_entry(cand.parent):
        raise OSError(f"Reparse point vietato su chiave HMAC Commit Train: {cand}")
    return cand.resolve()


def _read_key_bytes(resolved: Path) -> bytes:
    if is_reparse_entry(resolved) or not resolved.is_file():
        raise ValueError(f"Chiave HMAC Commit Train assente o non valida: {resolved}")
    raw = resolved.read_bytes().strip()
    if not raw:
        raise ValueError(f"Chiave HMAC Commit Train vuota: {resolved}")
    return raw


def ensure_commit_train_hmac_key(key_path: Optional[Union[str, Path]] = None) -> Path:
    """Crea la chiave HMAC Commit Train su NVMe se assente, verificando non-reparse."""
    resolved = resolve_commit_train_hmac_key_path(key_path)
    if resolved.exists():
        _read_key_bytes(resolved)
        return resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if is_reparse_entry(resolved.parent):
        raise OSError(f"Reparse point vietato su directory chiave Commit Train: {resolved.parent}")
    resolved.write_bytes(secrets.token_hex(32).encode("ascii"))
    return resolved


def sign_commit_train_payload(payload: Dict[str, Any], key_bytes: bytes) -> str:
    """Calcola firma HMAC-SHA256 canonica escludendo il campo hmac_sha256."""
    unsigned = {k: v for k, v in payload.items() if k != "hmac_sha256"}
    return hmac.new(key_bytes, canonical_json_bytes(unsigned), hashlib.sha256).hexdigest()


def verify_commit_train_signature(payload: Dict[str, Any], key_bytes: bytes) -> bool:
    """Verifica firma HMAC-SHA256 in tempo costante."""
    sig = payload.get("hmac_sha256")
    return is_valid_sha256_hex(sig) and hmac.compare_digest(sign_commit_train_payload(payload, key_bytes), str(sig).lower())


def compute_entry_record_hash(entry: Dict[str, Any]) -> str:
    """Calcola record_hash SHA-256 della entry escludendo record_hash e hmac_sha256."""
    body = {k: v for k, v in entry.items() if k not in ("record_hash", "hmac_sha256")}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def resolve_commit_train_paths(root: Union[str, Path]) -> Tuple[Path, Path, Path]:
    """Restituisce (train_dir, head_path, history_path) controllando reparse point."""
    train_dir = Path(root).resolve().joinpath(*COMMIT_TRAIN_DIR_REL)
    head_path, history_path = train_dir / "head.json", train_dir / "history.jsonl"
    for cand in (train_dir, head_path, history_path):
        if is_reparse_entry(cand):
            raise OSError(f"Reparse point vietato in commit_train store: {cand}")
    return train_dir, head_path, history_path


def _genesis_head_dict(root: Union[str, Path]) -> Dict[str, Any]:
    return {
        "schema_version": "CommitTrainHeadV1", "repo_hash12": repo_path_hash12(Path(root).resolve()),
        "seq": 0, "last_batch_id": "", "last_lane_id": "", "last_record_hash": GENESIS_HASH, "updated_at": 0.0, "hmac_sha256": "",
    }


def read_commit_train_head(
    root: Union[str, Path], *, verify_hmac: bool = True, key_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Legge head.json verificandone HMAC o restituisce il record genesis se assente."""
    _train_dir, head_path, _hist_path = resolve_commit_train_paths(root)
    if not head_path.exists():
        return _genesis_head_dict(root)
    data = json.loads(win_long_path(head_path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or isinstance(data.get("seq"), bool) or not isinstance(data.get("seq"), int) or int(data["seq"]) < 0:
        raise ValueError(f"head.json malformato in {head_path}")
    if str(data.get("repo_hash12") or "") != repo_path_hash12(Path(root).resolve()):
        raise ValueError(f"repo_hash12 mismatch in {head_path}")
    if verify_hmac and not verify_commit_train_signature(data, _read_key_bytes(resolve_commit_train_hmac_key_path(key_path))):
        raise ValueError(f"Firma HMAC non valida in {head_path}")
    return data


def _load_history_entries_unlocked(history_path: Path) -> List[Dict[str, Any]]:
    if not history_path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for idx, line in enumerate(win_long_path(history_path).read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not (clean := line.strip()):
            continue
        obj = json.loads(clean)
        if not isinstance(obj, dict):
            raise ValueError(f"Riga non oggetto JSON in {history_path}:{idx}")
        entries.append(obj)
    return entries


def _validate_chain_entries(entries: List[Dict[str, Any]], key_bytes: bytes, expected_repo_hash12: Optional[str] = None) -> List[str]:
    errors: List[str] = []
    expected_prev = GENESIS_HASH
    for idx, item in enumerate(entries, start=1):
        if expected_repo_hash12 and str(item.get("repo_hash12") or "") != expected_repo_hash12:
            errors.append(f"repo_hash12 mismatch a seq={idx}")
        if item.get("seq") != idx:
            errors.append(f"seq non monotonico a riga {idx}: {item.get('seq')!r}")
        if item.get("prev_hash") != expected_prev:
            errors.append(f"prev_hash interrotto a seq={idx}")
        if item.get("record_hash") != compute_entry_record_hash(item):
            errors.append(f"record_hash manomesso a seq={idx}")
        if not verify_commit_train_signature(item, key_bytes):
            errors.append(f"hmac_sha256 non valido a seq={idx}")
        expected_prev = str(item.get("record_hash") or "")
    return errors


def verify_commit_train_chain(
    root: Union[str, Path], *, key_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    """Verifica crittograficamente history.jsonl e head.json in fail-closed."""
    _train_dir, head_path, history_path = resolve_commit_train_paths(root)
    if not history_path.exists() and not head_path.exists():
        return True, [], []
    errors: List[str] = []
    try:
        key_bytes = _read_key_bytes(resolve_commit_train_hmac_key_path(key_path))
        entries = _load_history_entries_unlocked(history_path)
    except Exception as exc:
        return False, [], [f"Errore lettura catena Commit Train: {exc}"]
    errors.extend(_validate_chain_entries(entries, key_bytes, expected_repo_hash12=repo_path_hash12(Path(root).resolve())))
    try:
        head = read_commit_train_head(root, verify_hmac=True, key_path=key_path)
    except Exception as exc:
        return False, entries, errors + [f"Verifica head.json fallita: {exc}"]
    if entries:
        last = entries[-1]
        if int(head.get("seq", -1)) != int(last.get("seq", -2)) or str(head.get("last_record_hash") or "") != str(last.get("record_hash") or ""):
            errors.append("head mismatch rispetto all'ultima entry di history.jsonl")
    elif int(head.get("seq", 0)) != 0:
        errors.append("history.jsonl assente con head.seq > 0")
    return not errors, entries, errors


def append_commit_train_entry(
    root: Union[str, Path], *, batch_id: str, lane_id: str, milestone: str,
    committed_files: Sequence[str], deleted_files: Sequence[str], staging_manifest_sha256: str,
    chain_anchor_sha256: str = "", key_path: Optional[Union[str, Path]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Appende in modo idempotente un commit in history.jsonl e aggiorna head.json."""
    resolved_root = Path(root).resolve()
    h12, key_p = repo_path_hash12(resolved_root), ensure_commit_train_hmac_key(key_path)
    key_bytes = _read_key_bytes(key_p)
    train_dir, head_path, history_path = resolve_commit_train_paths(resolved_root)

    with FailClosedNamedMutex(f"Local\\NK_CommitTrainStore_{h12}", wait_ms=5000):
        ok, entries, errs = verify_commit_train_chain(resolved_root, key_path=key_p)
        if not ok:
            raise ValueError(f"Catena Commit Train corrotta prima di append: {errs}")
        for existing in entries:
            if existing.get("batch_id") == batch_id:
                return existing, read_commit_train_head(resolved_root, verify_hmac=True, key_path=key_p)
        now_ts = time.time()
        entry: Dict[str, Any] = {
            "seq": (int(entries[-1]["seq"]) if entries else 0) + 1, "repo_hash12": h12,
            "batch_id": str(batch_id), "lane_id": str(lane_id or "legacy"), "milestone": str(milestone or "2PC_PROMOTE"),
            "timestamp_utc": now_ts,
            "committed_files": [str(f).replace("\\", "/") for f in committed_files],
            "deleted_files": [str(f).replace("\\", "/") for f in deleted_files],
            "staging_manifest_sha256": str(staging_manifest_sha256).lower(),
            "chain_anchor_sha256": str(chain_anchor_sha256).lower(),
            "prev_hash": str(entries[-1]["record_hash"]) if entries else GENESIS_HASH,
        }
        entry["record_hash"] = compute_entry_record_hash(entry)
        entry["hmac_sha256"] = sign_commit_train_payload(entry, key_bytes)
        train_dir.mkdir(parents=True, exist_ok=True)
        with open(win_long_path(history_path), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(canonical_json_bytes(entry).decode("utf-8") + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        head: Dict[str, Any] = {
            "schema_version": "CommitTrainHeadV1", "repo_hash12": h12, "seq": entry["seq"],
            "last_batch_id": entry["batch_id"], "last_lane_id": entry["lane_id"],
            "last_record_hash": entry["record_hash"], "updated_at": now_ts,
        }
        head["hmac_sha256"] = sign_commit_train_payload(head, key_bytes)
        ok_w, err_w = atomic_write_json(head_path, head, indent=2, ensure_ascii=False, ensure_parent=True, fsync_data=True, reparse_check=is_reparse_entry)
        if not ok_w:
            raise OSError(f"Scrittura atomica head.json fallita: {err_w}")
        return entry, head


def compute_changed_files_range(
    root: Union[str, Path], from_seq: int, to_seq: Optional[int] = None, *, key_path: Optional[Union[str, Path]] = None,
) -> Tuple[Set[str], Dict[str, str]]:
    """Restituisce file toccati in (from_seq, to_seq] con confronto case-folded Win32."""
    ok, entries, errs = verify_commit_train_chain(root, key_path=key_path)
    if not ok:
        raise ValueError(f"Catena Commit Train non valida per OCC range: {errs}")
    eff_to = int(to_seq) if to_seq is not None else (int(entries[-1]["seq"]) if entries else 0)
    changed_cf, cf_to_canon = set(), {}
    for entry in entries:
        if int(from_seq) < int(entry.get("seq", 0)) <= eff_to:
            for raw_rel in list(entry.get("committed_files", ())) + list(entry.get("deleted_files", ())):
                if (cf := casefold_win32_rel(raw_rel)):
                    changed_cf.add(cf)
                    cf_to_canon[cf] = str(raw_rel).replace("\\", "/").lstrip("/")
    return changed_cf, cf_to_canon
