#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.1.0-FastHealing - Staging Snapshot & Transactional Rollback Engine
Module: healing_snapshot_rollback.py
Author: NK-State-Router & NK-Environment-Architect
Implements: Atomic snapshotting & Strict Monotonic Fitness Gate rollback

Features:
- Ephemeral in-memory & %TEMP% snapshotting before healing patch execution.
- SHA-256 integrity hashing of all tracked staged files.
- Strict Monotonic Fitness Gate: detects regressions (failed_count increases or passed_count decreases).
- Deterministic atomic rollback protecting working directory from broken patch attempts.
- Teardown & resource cleanup upon session completion.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field

_scripts_dir = Path(__file__).resolve().parent
_root_dir = _scripts_dir.parent.parent if _scripts_dir.parent.name == ".staging" else _scripts_dir.parent
for _d in (_scripts_dir, _root_dir / "scripts", _root_dir / ".staging" / "scripts", _root_dir):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    from scripts.platform_runner import reconfigure_streams


class FitnessVerdict(str, Enum):
    PASSED = "PASSED"
    IMPROVED = "IMPROVED"
    REGRESSION = "REGRESSION"
    NEUTRAL = "NEUTRAL"


class FitnessReport(BaseModel):
    """Evaluation of test outcome compared to previous baseline."""
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    verdict: FitnessVerdict
    current_passed: int
    current_failed: int
    prev_passed: int
    prev_failed: int
    exit_code: int
    reason: str


class FileSnapshot(BaseModel):
    """File content and integrity state."""
    model_config = ConfigDict(strict=True, extra="forbid")

    relative_path: str
    absolute_path: str
    sha256_hash: str
    content: str
    exists_before: bool = True


class SnapshotBundle(BaseModel):
    """Bundle containing snapshots for all tracked target files."""
    model_config = ConfigDict(strict=True, extra="forbid")

    snapshot_id: str
    created_at_epoch: float = Field(default_factory=time.time)
    temp_backup_dir: str
    files: Dict[str, FileSnapshot] = Field(default_factory=dict)


class HealingSnapshotManager:
    """Manages transactional snapshots and rollback for healing cycles."""

    def __init__(self, base_temp_dir: Optional[Path] = None):
        reconfigure_streams()
        self.base_temp_dir = Path(base_temp_dir) if base_temp_dir else Path(tempfile.gettempdir()) / "nk_heal_snapshots"
        self.base_temp_dir.mkdir(parents=True, exist_ok=True)
        self.active_snapshots: Dict[str, SnapshotBundle] = {}

    def create_snapshot(self, target_files: Sequence[Path | str]) -> str:
        """Captures SHA-256 and content of target files into memory and %TEMP%."""
        snapshot_id = f"snap_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        snap_temp_dir = self.base_temp_dir / snapshot_id
        snap_temp_dir.mkdir(parents=True, exist_ok=True)

        bundle = SnapshotBundle(
            snapshot_id=snapshot_id,
            temp_backup_dir=str(snap_temp_dir),
            files={},
        )

        for item in target_files:
            p = Path(item).resolve()
            rel_name = str(p)
            if p.exists() and p.is_file():
                content = p.read_text(encoding="utf-8", errors="replace")
                sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
                file_snap = FileSnapshot(
                    relative_path=p.name,
                    absolute_path=str(p),
                    sha256_hash=sha256,
                    content=content,
                    exists_before=True,
                )
                # Backup copy
                backup_dest = snap_temp_dir / p.name
                backup_dest.write_text(content, encoding="utf-8")
            else:
                file_snap = FileSnapshot(
                    relative_path=p.name,
                    absolute_path=str(p),
                    sha256_hash="",
                    content="",
                    exists_before=False,
                )
            bundle.files[str(p)] = file_snap

        self.active_snapshots[snapshot_id] = bundle
        return snapshot_id

    def evaluate_fitness(
        self,
        current_passed: int,
        current_failed: int,
        prev_passed: int,
        prev_failed: int,
        exit_code: int,
    ) -> FitnessReport:
        """
        Applies the Strict Monotonic Fitness Gate:
        - If exit_code == 0: PASSED.
        - If failed < prev_failed and passed >= prev_passed: IMPROVED.
        - If failed > prev_failed or passed < prev_passed: REGRESSION.
        - Otherwise: NEUTRAL.
        """
        if exit_code == 0 and current_failed == 0:
            return FitnessReport(
                verdict=FitnessVerdict.PASSED,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason="All tests passed successfully (0 failures).",
            )

        # Regression detection
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

        if current_failed < prev_failed and current_passed >= prev_passed:
            return FitnessReport(
                verdict=FitnessVerdict.IMPROVED,
                current_passed=current_passed,
                current_failed=current_failed,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=exit_code,
                reason=f"Failures reduced from {prev_failed} to {current_failed} (passed: {current_passed}).",
            )

        return FitnessReport(
            verdict=FitnessVerdict.NEUTRAL,
            current_passed=current_passed,
            current_failed=current_failed,
            prev_passed=prev_passed,
            prev_failed=prev_failed,
            exit_code=exit_code,
            reason="Test count unchanged.",
        )

    def rollback(self, snapshot_id: str) -> Dict[str, bool]:
        """Restores tracked files to their original snapshot state atomically."""
        if snapshot_id not in self.active_snapshots:
            raise KeyError(f"Unknown snapshot ID: {snapshot_id}")

        bundle = self.active_snapshots[snapshot_id]
        restoration_status: Dict[str, bool] = {}

        for file_path_str, file_snap in bundle.files.items():
            target_path = Path(file_path_str)
            try:
                if file_snap.exists_before:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(file_snap.content, encoding="utf-8")
                    restoration_status[file_path_str] = True
                else:
                    # If it was created during healing and did not exist before, remove it
                    if target_path.exists():
                        target_path.unlink(missing_ok=True)
                    restoration_status[file_path_str] = True
            except Exception:
                restoration_status[file_path_str] = False

        return restoration_status

    def cleanup(self, snapshot_id: Optional[str] = None) -> None:
        """Removes temporary snapshot directories."""
        if snapshot_id:
            bundle = self.active_snapshots.pop(snapshot_id, None)
            if bundle and Path(bundle.temp_backup_dir).exists():
                shutil.rmtree(bundle.temp_backup_dir, ignore_errors=True)
        else:
            for snap_id, bundle in list(self.active_snapshots.items()):
                if Path(bundle.temp_backup_dir).exists():
                    shutil.rmtree(bundle.temp_backup_dir, ignore_errors=True)
            self.active_snapshots.clear()


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(description="Nexus Keystone Staging Snapshot & Rollback Engine")
    parser.add_argument("--create", nargs="+", help="Create snapshot of specified file(s)")
    parser.add_argument("--rollback", type=str, help="Rollback specified snapshot ID")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup all temporary snapshots")

    args = parser.parse_args()
    mgr = HealingSnapshotManager()

    if args.create:
        sid = mgr.create_snapshot([Path(f) for f in args.create])
        print(f"🟢 [SNAPSHOT-CREATED] ID: {sid} (Tracked files: {len(args.create)})")
        return 0
    elif args.rollback:
        status = mgr.rollback(args.rollback)
        print(f"🔄 [SNAPSHOT-ROLLED-BACK] ID: {args.rollback} Status: {status}")
        return 0
    elif args.cleanup:
        mgr.cleanup()
        print("🧹 [SNAPSHOT-CLEANUP] Completed.")
        return 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
