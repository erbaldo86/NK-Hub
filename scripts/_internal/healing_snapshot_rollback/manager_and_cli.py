# -*- coding: utf-8 -*-
"""Gestore HealingSnapshotManager isolato per lane con Win32NamedMutex."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from _internal.healing_snapshot_rollback.models_and_io import (
    FileSnapshot,
    FitnessReport,
    FitnessVerdict,
    SnapshotBundle,
    _MANIFEST_LOCK,
    _atomic_write_bytes,
    _atomic_write_text,
    _check_equivalent_green,
    _check_regression_reason,
    _facade_attr,
    _restore_single_entry,
    _validate_snapshot_id,
    _verify_restored_file,  # noqa: F401
)
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex
from _internal.nk_common.paths import reconfigure_streams
from _internal.nk_common.win32_mutex import repo_path_hash12


def _manifest_file_mutex(lock_name: str) -> FailClosedNamedMutex:
    return FailClosedNamedMutex(lock_name, wait_ms=5000)


def _resolve_lane_dir_and_mutex(
    base_temp_dir: Optional[Path], lane_id: Optional[str], repo_root: Optional[Path],
) -> tuple[Optional[str], Path, str]:
    clean_lane = validate_lane_id(lane_id) if (lane_id is not None and str(lane_id).strip()) else None
    root_base = Path(base_temp_dir) if base_temp_dir else (Path(tempfile.gettempdir()) / "nk_heal_snapshots")
    eff_dir = (root_base / "lanes" / clean_lane) if clean_lane else root_base
    return clean_lane, eff_dir, f"Local\\NK_HealSnapshots_{repo_path_hash12(repo_root or eff_dir)}"


class HealingSnapshotManager:
    """Gestisce snapshot binari puri, mutex cross-processo, scoping per lane e rollback."""

    _MANIFEST_LOCK = _MANIFEST_LOCK
    verdict_enum = FitnessVerdict

    def __init__(
        self,
        base_temp_dir: Optional[Path] = None,
        *,
        lane_id: Optional[str] = None,
        repo_root: Optional[Path] = None,
    ):
        reconfigure_streams()
        self.lane_id, self.base_temp_dir, self._proc_mutex_name = _resolve_lane_dir_and_mutex(
            base_temp_dir, lane_id, repo_root,
        )
        self.base_temp_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.base_temp_dir / "snapshot_manifest.json"
        self.active_snapshots: Dict[str, SnapshotBundle] = {}
        self._load_manifest()

    def _resolve_confined_snapshot_dir(self, snapshot_id: str) -> Path:
        clean_id = _validate_snapshot_id(snapshot_id)
        base_resolved = self.base_temp_dir.resolve()
        cand = (base_resolved / clean_id).resolve()
        if cand == base_resolved or cand.parent != base_resolved or not cand.is_relative_to(base_resolved):
            raise ValueError(f"Snapshot path escapes base_temp_dir: {cand}")
        return cand

    def _assert_dir_confined(self, target_dir: Path) -> Optional[Path]:
        try:
            base_resolved = self.base_temp_dir.resolve()
            resolved = target_dir.resolve()
        except OSError:
            return None
        if resolved == base_resolved or not resolved.is_relative_to(base_resolved):
            return None
        return resolved

    def _read_disk_manifest_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if not self.manifest_path.exists():
            return {}
        try:
            raw = json.loads(self.manifest_path.read_bytes().decode("utf-8", errors="replace"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError, ValueError):
            return {}

    def _load_manifest(self) -> None:
        os_mod = _facade_attr("os", os)
        with _MANIFEST_LOCK, _manifest_file_mutex(self._proc_mutex_name):
            if not self.manifest_path.exists():
                return
            raw_bytes = self.manifest_path.read_bytes()
            try:
                raw = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                if not isinstance(raw, dict):
                    raise ValueError("Snapshot manifest root must be a JSON object.")
                for sid, b_data in raw.items():
                    self.active_snapshots[sid] = SnapshotBundle.model_validate(b_data)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                corrupt_path = self.manifest_path.with_name(f"{self.manifest_path.stem}.corrupt.{int(time.time() * 1000)}{self.manifest_path.suffix}")
                try:
                    os_mod.replace(str(self.manifest_path), str(corrupt_path))
                except OSError:
                    pass
                raise ValueError(f"Corrupt snapshot manifest quarantined to {corrupt_path}: {exc}") from exc

    def _persist_single_snapshot_entry(self, snapshot_id: str, bundle: Optional[SnapshotBundle]) -> None:
        write_txt = _facade_attr("_atomic_write_text", _atomic_write_text)
        with _MANIFEST_LOCK, _manifest_file_mutex(self._proc_mutex_name):
            self.base_temp_dir.mkdir(parents=True, exist_ok=True)
            disk_map = self._read_disk_manifest_unlocked()
            if bundle is not None:
                disk_map[snapshot_id] = bundle.model_dump()
            else:
                disk_map.pop(snapshot_id, None)
            write_txt(self.manifest_path, json.dumps(disk_map, indent=2))

    def create_snapshot(self, target_files: Sequence[Path | str]) -> str:
        write_bin = _facade_attr("_atomic_write_bytes", _atomic_write_bytes)
        write_txt = _facade_attr("_atomic_write_text", _atomic_write_text)
        snapshot_id = f"snap_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        snap_temp_dir = self._resolve_confined_snapshot_dir(snapshot_id)
        snap_temp_dir.mkdir(parents=True, exist_ok=True)
        bundle = SnapshotBundle(snapshot_id=snapshot_id, temp_backup_dir=str(snap_temp_dir), files={})

        for item in target_files:
            p = Path(item).resolve()
            if p.exists() and p.is_file():
                raw_bytes = p.read_bytes()
                file_snap = FileSnapshot(
                    relative_path=p.name, absolute_path=str(p), sha256_hash=hashlib.sha256(raw_bytes).hexdigest(),
                    content=raw_bytes.decode("utf-8", errors="replace"), content_b64=base64.b64encode(raw_bytes).decode("ascii"), exists_before=True,
                )
                prefix = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:8]
                write_bin(snap_temp_dir / f"{prefix}_{p.name}", raw_bytes)
            else:
                file_snap = FileSnapshot(relative_path=p.name, absolute_path=str(p), sha256_hash="", content="", content_b64="", exists_before=False)
            bundle.files[str(p)] = file_snap

        write_txt(snap_temp_dir / "snapshot_manifest.json", bundle.model_dump_json(indent=2))
        with _MANIFEST_LOCK:
            self.active_snapshots[snapshot_id] = bundle
        self._persist_single_snapshot_entry(snapshot_id, bundle)
        return snapshot_id

    def evaluate_fitness(
        self, current_passed: int, current_failed: int, prev_passed: int, prev_failed: int, exit_code: int,
        *, allow_equivalent_green: bool = False, delta_cc: int = 0, ast_sast_violations: int = 0,
    ) -> FitnessReport:
        reg_reason = _check_regression_reason(current_passed, current_failed, prev_passed, prev_failed, exit_code)
        if reg_reason is not None:
            return FitnessReport(verdict=FitnessVerdict.REGRESSION, current_passed=current_passed, current_failed=current_failed, prev_passed=prev_passed, prev_failed=prev_failed, exit_code=exit_code, reason=reg_reason)

        curr_total, prev_total = current_passed + current_failed, prev_passed + prev_failed
        monotonic_gain = curr_total >= prev_total and curr_total > 0 and current_passed > prev_passed
        if exit_code == 0 and current_failed == 0 and monotonic_gain:
            return FitnessReport(verdict=FitnessVerdict.PASSED, current_passed=current_passed, current_failed=current_failed, prev_passed=prev_passed, prev_failed=prev_failed, exit_code=exit_code, reason="All tests passed successfully with strict monotonic gain (0 failures).")
        if monotonic_gain and current_failed < prev_failed and exit_code in (0, 1):
            return FitnessReport(verdict=FitnessVerdict.IMPROVED, current_passed=current_passed, current_failed=current_failed, prev_passed=prev_passed, prev_failed=prev_failed, exit_code=exit_code, reason=f"Failures reduced from {prev_failed} to {current_failed} (passed: {current_passed}).")
        if _check_equivalent_green(allow_equivalent_green, exit_code, current_passed, current_failed, prev_passed, prev_failed, delta_cc, ast_sast_violations):
            return FitnessReport(verdict=FitnessVerdict.REFACTOR_EQUIVALENT, current_passed=current_passed, current_failed=current_failed, prev_passed=prev_passed, prev_failed=prev_failed, exit_code=exit_code, reason="Equivalent green refactoring accepted (0 failures, delta_cc <= 0, 0 AST/SAST violations).")
        return FitnessReport(verdict=FitnessVerdict.NEUTRAL, current_passed=current_passed, current_failed=current_failed, prev_passed=prev_passed, prev_failed=prev_failed, exit_code=exit_code, reason="Test count unchanged or no monotonic gain.")

    def _resolve_snapshot_bundle(self, snapshot_id: str, snap_dir: Path) -> SnapshotBundle:
        if snapshot_id not in self.active_snapshots:
            self._load_manifest()
        if snapshot_id not in self.active_snapshots:
            local_manifest = snap_dir / "snapshot_manifest.json"
            if not local_manifest.exists():
                raise KeyError(f"Unknown snapshot ID: {snapshot_id}")
            self.active_snapshots[snapshot_id] = SnapshotBundle.model_validate_json(local_manifest.read_bytes().decode("utf-8", errors="replace"))
        return self.active_snapshots[snapshot_id]

    def rollback(self, snapshot_id: str) -> Dict[str, bool]:
        snap_dir = self._resolve_confined_snapshot_dir(snapshot_id)
        write_bin = _facade_attr("_atomic_write_bytes", _atomic_write_bytes)
        bundle = self._resolve_snapshot_bundle(snapshot_id, snap_dir)
        confined_backup = self._assert_dir_confined(Path(bundle.temp_backup_dir))
        backup_dir_str = str(confined_backup if confined_backup is not None else snap_dir)
        return {fps: _restore_single_entry(Path(fps), fs, backup_dir_str, write_bin) for fps, fs in bundle.files.items()}

    def _cleanup_single_snapshot(self, snapshot_id: str) -> None:
        snap_dir = self._resolve_confined_snapshot_dir(snapshot_id)
        with _MANIFEST_LOCK:
            bundle = self.active_snapshots.pop(snapshot_id, None)
        self._persist_single_snapshot_entry(snapshot_id, None)
        if bundle is not None:
            confined = self._assert_dir_confined(Path(bundle.temp_backup_dir))
            if confined is not None and confined.exists():
                shutil.rmtree(confined, ignore_errors=True)
        if snap_dir.exists():
            shutil.rmtree(snap_dir, ignore_errors=True)

    def _cleanup_all_snapshots(self) -> None:
        with _MANIFEST_LOCK, _manifest_file_mutex(self._proc_mutex_name):
            bundles = list(self.active_snapshots.values())
            self.active_snapshots.clear()
            if self.manifest_path.exists():
                try:
                    self.manifest_path.unlink()
                except OSError as exc:
                    _ = str(exc)
        for bundle in bundles:
            confined = self._assert_dir_confined(Path(bundle.temp_backup_dir))
            if confined is not None and confined.exists():
                shutil.rmtree(confined, ignore_errors=True)

    def cleanup(self, snapshot_id: Optional[str] = None) -> None:
        if snapshot_id is not None:
            self._cleanup_single_snapshot(snapshot_id)
            return
        self._cleanup_all_snapshots()

    def cleanup_snapshot(self, snapshot_id: str) -> None:
        self.cleanup(snapshot_id=snapshot_id)

    rollback_to_snapshot = rollback
    delete_snapshot = cleanup


def _handle_rollback_cli(mgr: Any, snap_id: str) -> int:
    try:
        status = mgr.rollback(snap_id)
    except (KeyError, ValueError) as exc:
        print(f"🔴 [SNAPSHOT-ROLLBACK-FAILED] {exc}")
        return 1
    if not status or not all(status.values()):
        print(f"🔴 [SNAPSHOT-ROLLBACK-FAILED] ID: {snap_id} Status: {status}")
        return 1
    print(f"🔄 [SNAPSHOT-ROLLED-BACK] ID: {snap_id} Status: {status}")
    return 0


def _instantiate_snapshot_mgr_from_args(mgr_cls: Any, args: Any) -> Any:
    lane = getattr(args, "lane_id", None)
    try:
        params = inspect.signature(mgr_cls).parameters
        has_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if lane is not None and (has_kw or "lane_id" in params):
            return mgr_cls(lane_id=lane)
    except (TypeError, ValueError):
        pass
    return mgr_cls()


def _cleanup_from_args(mgr: Any, args: Any) -> int:
    mgr.cleanup(snapshot_id=getattr(args, "snapshot_id", None))
    print("🧹 [SNAPSHOT-CLEANUP] Completed.")
    return 0


def _run_cli_args(args: Any) -> int:
    reconfigure_streams()
    mgr = _instantiate_snapshot_mgr_from_args(_facade_attr("HealingSnapshotManager", HealingSnapshotManager), args)
    if args.create:
        sid = mgr.create_snapshot([Path(f) for f in args.create])
        print(f"🟢 [SNAPSHOT-CREATED] ID: {sid} (Tracked files: {len(args.create)})")
        return 0
    if args.rollback:
        return _handle_rollback_cli(mgr, args.rollback)
    if args.cleanup:
        return _cleanup_from_args(mgr, args)
    return 0
