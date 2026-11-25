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
    _check_equivalent_green,
    _check_regression_reason,
    _facade_attr,
    _restore_single_entry,
    _validate_snapshot_id,
    _verify_restored_file,
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

    def _resolve_confined_snapshot_dir(self, snapshot_id: str) -> Path:
        """Valida snapshot_id e garantisce il confinamento stretto sotto base_temp_dir."""
        clean_id = _validate_snapshot_id(snapshot_id)
        base_resolved = self.base_temp_dir.resolve()
        cand = (base_resolved / clean_id).resolve()
        if cand == base_resolved or cand.parent != base_resolved or not cand.is_relative_to(base_resolved):
            raise ValueError(f"Snapshot path escapes base_temp_dir: {cand}")
        return cand

    def _assert_dir_confined(self, target_dir: Path) -> Optional[Path]:
        """Restituisce target_dir risolto se strettamente dentro base_temp_dir, altrimenti None."""
        try:
            base_resolved = self.base_temp_dir.resolve()
            resolved = target_dir.resolve()
        except OSError:
            return None
        if resolved == base_resolved or not resolved.is_relative_to(base_resolved):
            return None
        return resolved

    def _read_disk_manifest_unlocked(self) -> Dict[str, Dict[str, Any]]:
        """Legge il dizionario manifesto su disco senza alterare gli snapshot altrui."""
        if not self.manifest_path.exists():
            return {}
        try:
            raw = json.loads(
                self.manifest_path.read_bytes().decode("utf-8", errors="replace")
            )
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError, ValueError):
            return {}

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

    def _persist_single_snapshot_entry(
        self, snapshot_id: str, bundle: Optional[SnapshotBundle]
    ) -> None:
        """Aggiorna o rimuove una sola voce nel manifesto preservando le sessioni concorrenti."""
        write_txt = _facade_attr("_atomic_write_text", _atomic_write_text)
        with _MANIFEST_LOCK:
            self.base_temp_dir.mkdir(parents=True, exist_ok=True)
            disk_map = self._read_disk_manifest_unlocked()
            if bundle is not None:
                disk_map[snapshot_id] = bundle.model_dump()
            else:
                disk_map.pop(snapshot_id, None)
            write_txt(self.manifest_path, json.dumps(disk_map, indent=2))

    def create_snapshot(self, target_files: Sequence[Path | str]) -> str:
        """Cattura SHA-256 e byte grezzi dei file target senza alterare i contenuti."""
        write_bin = _facade_attr("_atomic_write_bytes", _atomic_write_bytes)
        write_txt = _facade_attr("_atomic_write_text", _atomic_write_text)
        snapshot_id = f"snap_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        snap_temp_dir = self._resolve_confined_snapshot_dir(snapshot_id)
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
        self._persist_single_snapshot_entry(snapshot_id, bundle)
        return snapshot_id

    def evaluate_fitness(
        self,
        current_passed: int,
        current_failed: int,
        prev_passed: int,
        prev_failed: int,
        exit_code: int,
        *,
        allow_equivalent_green: bool = False,
        delta_cc: int = 0,
        ast_sast_violations: int = 0,
    ) -> FitnessReport:
        """Applica lo Strict Monotonic Fitness Gate H2* supportando refactoring equivalente verde."""
        reg_reason = _check_regression_reason(
            current_passed, current_failed, prev_passed, prev_failed, exit_code
        )
        if reg_reason is not None:
            return FitnessReport(
                verdict=FitnessVerdict.REGRESSION,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=reg_reason,
            )

        curr_total = current_passed + current_failed
        prev_total = prev_passed + prev_failed
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

        if monotonic_gain and current_failed < prev_failed and exit_code in (0, 1):
            return FitnessReport(
                verdict=FitnessVerdict.IMPROVED,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Failures reduced from {prev_failed} to {current_failed} (passed: {current_passed}).",
            )

        if _check_equivalent_green(
            allow_equivalent_green,
            exit_code,
            current_passed,
            current_failed,
            prev_passed,
            prev_failed,
            delta_cc,
            ast_sast_violations,
        ):
            return FitnessReport(
                verdict=FitnessVerdict.REFACTOR_EQUIVALENT,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason="Equivalent green refactoring accepted (0 failures, delta_cc <= 0, 0 AST/SAST violations).",
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

    def _resolve_snapshot_bundle(self, snapshot_id: str, snap_dir: Path) -> SnapshotBundle:
        """Recupera lo SnapshotBundle validato in memoria o sotto la directory confinata."""
        if snapshot_id not in self.active_snapshots:
            self._load_manifest()
        if snapshot_id not in self.active_snapshots:
            local_manifest = snap_dir / "snapshot_manifest.json"
            if not local_manifest.exists():
                raise KeyError(f"Unknown snapshot ID: {snapshot_id}")
            bundle = SnapshotBundle.model_validate_json(
                local_manifest.read_bytes().decode("utf-8", errors="replace")
            )
            self.active_snapshots[snapshot_id] = bundle
        return self.active_snapshots[snapshot_id]

    def rollback(self, snapshot_id: str) -> Dict[str, bool]:
        """Ripristina i byte esatti dei file tracciati verificando l'integrita SHA-256 post scrittura."""
        snap_dir = self._resolve_confined_snapshot_dir(snapshot_id)
        write_bin = _facade_attr("_atomic_write_bytes", _atomic_write_bytes)
        bundle = self._resolve_snapshot_bundle(snapshot_id, snap_dir)
        confined_backup = self._assert_dir_confined(Path(bundle.temp_backup_dir))
        backup_dir_str = str(confined_backup if confined_backup is not None else snap_dir)

        restoration_status: Dict[str, bool] = {}
        for file_path_str, file_snap in bundle.files.items():
            restoration_status[file_path_str] = _restore_single_entry(
                Path(file_path_str), file_snap, backup_dir_str, write_bin
            )

        return restoration_status

    def _cleanup_single_snapshot(self, snapshot_id: str) -> None:
        """Elimina solo lo snapshot indicato preservando tutti gli altri snapshot attivi."""
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
        """Rimuove tutti gli snapshot tracciati dall'istanza corrente."""
        with _MANIFEST_LOCK:
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
        """Rimuove lo snapshot specificato oppure tutti gli snapshot se snapshot_id e None."""
        if snapshot_id is not None:
            self._cleanup_single_snapshot(snapshot_id)
            return
        self._cleanup_all_snapshots()

    def cleanup_snapshot(self, snapshot_id: str) -> None:
        """Elimina selettivamente un singolo snapshot validato e confinato."""
        self.cleanup(snapshot_id=snapshot_id)

    rollback_to_snapshot = rollback
    delete_snapshot = cleanup


def _handle_rollback_cli(mgr: Any, snap_id: str) -> int:
    """Esegue il rollback CLI con uscita fail-closed su ID ignoto/invalido o file non verificati."""
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
        return _handle_rollback_cli(mgr, args.rollback)
    if args.cleanup:
        mgr.cleanup()
        print("🧹 [SNAPSHOT-CLEANUP] Completed.")
        return 0
    return 0
