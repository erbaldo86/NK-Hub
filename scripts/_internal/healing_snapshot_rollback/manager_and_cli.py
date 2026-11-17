# -*- coding: utf-8 -*-
"""Gestore HealingSnapshotManager e azioni CLI per healing_snapshot_rollback."""

from __future__ import annotations

import base64
import hashlib
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
    _facade_attr,
)
from _internal.nk_common.paths import reconfigure_streams


class HealingSnapshotManager:
    """Gestisce snapshot binari puri e rollback transazionale atomico."""

    _MANIFEST_LOCK = _MANIFEST_LOCK
    verdict_enum = FitnessVerdict

    def __init__(self, base_temp_dir: Optional[Path] = None):
        reconfigure_streams()
        self.base_temp_dir = (
            Path(base_temp_dir)
            if base_temp_dir
            else Path(tempfile.gettempdir()) / "nk_heal_snapshots"
        )
        self.base_temp_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.base_temp_dir / "snapshot_manifest.json"
        self.active_snapshots: Dict[str, SnapshotBundle] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Carica gli snapshot attivi mettendo in quarantena i manifesti corrotti."""
        os_mod = _facade_attr("os", os)
        with _MANIFEST_LOCK:
            if not self.manifest_path.exists():
                return
            raw_bytes = self.manifest_path.read_bytes()
            try:
                raw = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                if not isinstance(raw, dict):
                    raise ValueError("Snapshot manifest root must be a JSON object.")
                for sid, b_data in raw.items():
                    bundle = SnapshotBundle.model_validate(b_data)
                    self.active_snapshots[sid] = bundle
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                corrupt_path = self.manifest_path.with_name(
                    f"{self.manifest_path.stem}.corrupt.{int(time.time() * 1000)}{self.manifest_path.suffix}"
                )
                try:
                    os_mod.replace(str(self.manifest_path), str(corrupt_path))
                except OSError:
                    pass
                raise ValueError(
                    f"Corrupt snapshot manifest quarantined to {corrupt_path}: {exc}"
                ) from exc

    def _save_manifest(self) -> None:
        """Persiste atomicamente il dizionario degli snapshot in snapshot_manifest.json."""
        write_txt = _facade_attr("_atomic_write_text", _atomic_write_text)
        with _MANIFEST_LOCK:
            self.base_temp_dir.mkdir(parents=True, exist_ok=True)
            serialized = {
                sid: bundle.model_dump()
                for sid, bundle in self.active_snapshots.items()
            }
            write_txt(self.manifest_path, json.dumps(serialized, indent=2))

    def create_snapshot(self, target_files: Sequence[Path | str]) -> str:
        """Cattura SHA-256 e byte grezzi dei file target senza alterare i contenuti."""
        write_bin = _facade_attr("_atomic_write_bytes", _atomic_write_bytes)
        write_txt = _facade_attr("_atomic_write_text", _atomic_write_text)
        snapshot_id = f"snap_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        snap_temp_dir = self.base_temp_dir / snapshot_id
        snap_temp_dir.mkdir(parents=True, exist_ok=True)

        bundle = SnapshotBundle(
            snapshot_id=snapshot_id,
            temp_backup_dir=str(snap_temp_dir),
            files={},
        )

        for item in target_files:
            p = Path(item).resolve()
            if p.exists() and p.is_file():
                raw_bytes = p.read_bytes()
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                b64_str = base64.b64encode(raw_bytes).decode("ascii")
                text_preview = raw_bytes.decode("utf-8", errors="replace")
                file_snap = FileSnapshot(
                    relative_path=p.name,
                    absolute_path=str(p),
                    sha256_hash=sha256,
                    content=text_preview,
                    content_b64=b64_str,
                    exists_before=True,
                )
                prefix = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:8]
                backup_dest = snap_temp_dir / f"{prefix}_{p.name}"
                write_bin(backup_dest, raw_bytes)
            else:
                file_snap = FileSnapshot(
                    relative_path=p.name,
                    absolute_path=str(p),
                    sha256_hash="",
                    content="",
                    content_b64="",
                    exists_before=False,
                )
            bundle.files[str(p)] = file_snap

        write_txt(
            snap_temp_dir / "snapshot_manifest.json",
            bundle.model_dump_json(indent=2),
        )

        with _MANIFEST_LOCK:
            self.active_snapshots[snapshot_id] = bundle
        self._save_manifest()
        return snapshot_id

    def evaluate_fitness(
        self,
        current_passed: int,
        current_failed: int,
        prev_passed: int,
        prev_failed: int,
        exit_code: int,
    ) -> FitnessReport:
        """Applica lo Strict Monotonic Fitness Gate rifiutando suite vuote o contratte."""
        curr_total = current_passed + current_failed
        prev_total = prev_passed + prev_failed

        if curr_total <= 0:
            return FitnessReport(
                verdict=FitnessVerdict.REGRESSION,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason="Zero tests executed (0/0 test run rejected).",
            )

        if curr_total < prev_total:
            return FitnessReport(
                verdict=FitnessVerdict.REGRESSION,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Total test count decreased from {prev_total} to {curr_total}.",
            )

        if current_passed < prev_passed:
            return FitnessReport(
                verdict=FitnessVerdict.REGRESSION,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Passed tests decreased from {prev_passed} to {current_passed}.",
            )

        if current_failed > prev_failed:
            return FitnessReport(
                verdict=FitnessVerdict.REGRESSION,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Failed tests increased from {prev_failed} to {current_failed}.",
            )

        monotonic_gain = (
            curr_total >= prev_total
            and curr_total > 0
            and current_passed > prev_passed
        )

        if exit_code == 0 and current_failed == 0 and monotonic_gain:
            return FitnessReport(
                verdict=FitnessVerdict.PASSED,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason="All tests passed successfully with strict monotonic gain (0 failures).",
            )

        if monotonic_gain and current_failed < prev_failed:
            return FitnessReport(
                verdict=FitnessVerdict.IMPROVED,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Failures reduced from {prev_failed} to {current_failed} (passed: {current_passed}).",
            )

        if exit_code != 0 and current_failed == 0 and prev_failed == 0:
            return FitnessReport(
                verdict=FitnessVerdict.REGRESSION,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Non-zero exit code ({exit_code}) without test improvement.",
            )

        return FitnessReport(
            verdict=FitnessVerdict.NEUTRAL,
            current_passed=current_passed,
            current_failed=current_failed,
            prev_passed=prev_passed,
            prev_failed=prev_failed,
            exit_code=exit_code,
            reason="Test count unchanged or no monotonic gain.",
        )

    def rollback(self, snapshot_id: str) -> Dict[str, bool]:
        """Ripristina i byte esatti dei file tracciati allo stato originale dello snapshot."""
        write_bin = _facade_attr("_atomic_write_bytes", _atomic_write_bytes)
        if snapshot_id not in self.active_snapshots:
            self._load_manifest()
        if snapshot_id not in self.active_snapshots:
            local_manifest = (
                self.base_temp_dir / snapshot_id / "snapshot_manifest.json"
            )
            if local_manifest.exists():
                bundle = SnapshotBundle.model_validate_json(
                    local_manifest.read_bytes().decode("utf-8", errors="replace")
                )
                self.active_snapshots[snapshot_id] = bundle
            else:
                raise KeyError(f"Unknown snapshot ID: {snapshot_id}")

        bundle = self.active_snapshots[snapshot_id]
        restoration_status: Dict[str, bool] = {}

        for file_path_str, file_snap in bundle.files.items():
            target_path = Path(file_path_str)
            try:
                if file_snap.exists_before:
                    prefix = hashlib.sha256(
                        str(target_path).encode("utf-8")
                    ).hexdigest()[:8]
                    backup_src = (
                        Path(bundle.temp_backup_dir)
                        / f"{prefix}_{file_snap.relative_path}"
                    )
                    if file_snap.content_b64:
                        raw_bytes = base64.b64decode(
                            file_snap.content_b64.encode("ascii")
                        )
                    elif backup_src.exists() and backup_src.is_file():
                        raw_bytes = backup_src.read_bytes()
                    else:
                        raw_bytes = file_snap.content.encode("utf-8")
                    write_bin(target_path, raw_bytes)
                    restoration_status[file_path_str] = True
                else:
                    if target_path.exists():
                        target_path.unlink(missing_ok=True)
                    restoration_status[file_path_str] = True
            except Exception:
                restoration_status[file_path_str] = False

        return restoration_status

    def cleanup(self, snapshot_id: Optional[str] = None) -> None:
        """Rimuove le directory temporanee degli snapshot e aggiorna il manifesto."""
        if snapshot_id:
            with _MANIFEST_LOCK:
                bundle = self.active_snapshots.pop(snapshot_id, None)
            if bundle and Path(bundle.temp_backup_dir).exists():
                shutil.rmtree(bundle.temp_backup_dir, ignore_errors=True)
            self._save_manifest()
        else:
            with _MANIFEST_LOCK:
                bundles = list(self.active_snapshots.values())
                self.active_snapshots.clear()
                if self.manifest_path.exists():
                    try:
                        self.manifest_path.unlink()
                    except Exception:
                        pass
            for bundle in bundles:
                if Path(bundle.temp_backup_dir).exists():
                    shutil.rmtree(bundle.temp_backup_dir, ignore_errors=True)

    rollback_to_snapshot = rollback
    delete_snapshot = cleanup


def _run_cli_args(args: Any) -> int:
    """Esegue il comando CLI usando gli argomenti gia validati da argparse."""
    reconfigure_streams()
    mgr_cls = _facade_attr("HealingSnapshotManager", HealingSnapshotManager)
    mgr = mgr_cls()

    if args.create:
        sid = mgr.create_snapshot([Path(f) for f in args.create])
        print(f"🟢 [SNAPSHOT-CREATED] ID: {sid} (Tracked files: {len(args.create)})")
        return 0
    if args.rollback:
        status = mgr.rollback(args.rollback)
        print(f"🔄 [SNAPSHOT-ROLLED-BACK] ID: {args.rollback} Status: {status}")
        return 0
    if args.cleanup:
        mgr.cleanup()
        print("🧹 [SNAPSHOT-CLEANUP] Completed.")
        return 0
    return 0
