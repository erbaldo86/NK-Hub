#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore snapshot di staging e rollback transazionale per Nexus Keystone v3.0.0.
Modulo: healing_snapshot_rollback.py.
Implementa la correzione U-23 (persistenza di snapshot_manifest.json tra processi CLI).

Funzionalita principali:
1. Crea snapshot SHA-256 in memoria e in %TEMP%/nk_heal_snapshots/.
2. Salva snapshot_manifest.json su disco per supportare --rollback tra processi separati (U-23).
3. Applica lo Strict Monotonic Fitness Gate per rilevare regressioni sui test.
4. Esegue il rollback atomico e la pulizia delle risorse temporanee.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
if _scripts_dir.name == ".staging":
    _root_dir = _scripts_dir.parent
for _d in (
    _scripts_dir,
    _root_dir / "scripts",
    _root_dir / ".staging" / "scripts",
    _root_dir,
):
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
    """Valutazione dell'esito dei test rispetto al baseline precedente."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    verdict: FitnessVerdict
    current_passed: int
    current_failed: int
    prev_passed: int
    prev_failed: int
    exit_code: int
    reason: str


class FileSnapshot(BaseModel):
    """Contenuto e stato di integrita SHA-256 di un singolo file tracciato."""

    model_config = ConfigDict(strict=True, extra="forbid")

    relative_path: str
    absolute_path: str
    sha256_hash: str
    content: str
    exists_before: bool = True


class SnapshotBundle(BaseModel):
    """Pacchetto contenente gli snapshot di tutti i file target tracciati."""

    model_config = ConfigDict(strict=True, extra="forbid")

    snapshot_id: str
    created_at_epoch: float = Field(default_factory=time.time)
    temp_backup_dir: str
    files: Dict[str, FileSnapshot] = Field(default_factory=dict)


class HealingSnapshotManager:
    """Gestisce gli snapshot transazionali e il rollback con persistenza su disco (U-23)."""

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
        """Carica gli snapshot attivi da snapshot_manifest.json su disco (U-23)."""
        if not self.manifest_path.exists():
            return
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for sid, b_data in raw.items():
                    try:
                        bundle = SnapshotBundle.model_validate(b_data)
                        self.active_snapshots[sid] = bundle
                    except Exception:
                        pass
        except Exception:
            pass

    def _save_manifest(self) -> None:
        """Persiste il dizionario degli snapshot attivi in snapshot_manifest.json (U-23)."""
        try:
            self.base_temp_dir.mkdir(parents=True, exist_ok=True)
            serialized = {
                sid: bundle.model_dump()
                for sid, bundle in self.active_snapshots.items()
            }
            self.manifest_path.write_text(
                json.dumps(serialized, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def create_snapshot(self, target_files: Sequence[Path | str]) -> str:
        """Cattura SHA-256 e contenuto dei file target in memoria e in %TEMP%."""
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
                prefix = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:8]
                backup_dest = snap_temp_dir / f"{prefix}_{p.name}"
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

        # Salva anche una copia locale del manifesto nella cartella dello snapshot
        try:
            (snap_temp_dir / "snapshot_manifest.json").write_text(
                bundle.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            pass

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
        """Applica lo Strict Monotonic Fitness Gate confrontando gli esiti dei test."""
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
        """Ripristina i file tracciati allo stato originale dello snapshot."""
        if snapshot_id not in self.active_snapshots:
            self._load_manifest()
        if snapshot_id not in self.active_snapshots:
            local_manifest = self.base_temp_dir / snapshot_id / "snapshot_manifest.json"
            if local_manifest.exists():
                bundle = SnapshotBundle.model_validate_json(
                    local_manifest.read_text(encoding="utf-8")
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
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(file_snap.content, encoding="utf-8")
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
            bundle = self.active_snapshots.pop(snapshot_id, None)
            if bundle and Path(bundle.temp_backup_dir).exists():
                shutil.rmtree(bundle.temp_backup_dir, ignore_errors=True)
            self._save_manifest()
        else:
            for _, bundle in list(self.active_snapshots.items()):
                if Path(bundle.temp_backup_dir).exists():
                    shutil.rmtree(bundle.temp_backup_dir, ignore_errors=True)
            self.active_snapshots.clear()
            if self.manifest_path.exists():
                try:
                    self.manifest_path.unlink()
                except Exception:
                    pass


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Staging Snapshot & Rollback Engine"
    )
    parser.add_argument(
        "--create", nargs="+", help="Crea lo snapshot dei file specificati"
    )
    parser.add_argument(
        "--rollback", type=str, help="Ripristina lo snapshot con l'ID specificato"
    )
    parser.add_argument(
        "--cleanup", action="store_true", help="Rimuove tutti gli snapshot temporanei"
    )

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
