#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demone di battito asincrono e watchdog anti-blocco per Nexus Keystone v3.0.0-STE100-Unified.
Emette impulsi ogni 15s e salva dump diagnostici in %TEMP%/nk_diagnostics/ se lo step supera 45s.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_CADENCE_SEC = 15.0
DEFAULT_WATCHDOG_SEC = 45.0


class AsyncHeartbeatSignaler:
    """Emette impulsi di vitalita in background e controlla il timeout di inattivita."""

    def __init__(
        self,
        step_name: str = "general_task",
        cadence_sec: float = DEFAULT_CADENCE_SEC,
        watchdog_sec: float = DEFAULT_WATCHDOG_SEC,
        telemetry_file: Optional[Path] = None,
    ) -> None:
        self.step_name = step_name
        self.cadence_sec = cadence_sec
        self.watchdog_sec = watchdog_sec
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_beat_time = time.time()
        self.pulse_count = 0

        self.diag_dir = Path(tempfile.gettempdir()) / "nk_diagnostics"
        self.diag_dir.mkdir(parents=True, exist_ok=True)

        if telemetry_file:
            self.telemetry_file = Path(telemetry_file)
        else:
            self.telemetry_file = self.diag_dir / "heartbeat_stream.jsonl"

    def reset_step(self, new_step_name: str) -> None:
        """Azzera il timer di inattivita all'inizio di un nuovo step operativo."""
        self.step_name = new_step_name
        self.last_beat_time = time.time()
        self.emit_pulse(status="STEP_RESET")

    def start(self) -> None:
        """Avvia il thread demone di monitoraggio in background."""
        if self.running:
            return
        self.running = True
        self.last_beat_time = time.time()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Arresta il thread di heartbeat in modo pulito."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def emit_pulse(self, status: str = "ALIVE") -> Dict[str, Any]:
        """Registra un singolo impulso telemetrico sul file JSONL locale."""
        now = time.time()
        self.pulse_count += 1
        elapsed = round(now - self.last_beat_time, 2)
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "step": self.step_name,
            "status": status,
            "pulse_index": self.pulse_count,
            "elapsed_since_last_pulse_sec": elapsed,
            "pid": os.getpid(),
        }

        try:
            with open(self.telemetry_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass

        return payload

    def dump_diagnostics(self) -> Path:
        """Salva lo stack trace di tutti i thread attivi in %TEMP%/nk_diagnostics/."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dump_path = self.diag_dir / f"diag_dump_{timestamp}.json"

        thread_names = {
            t.ident: t.name for t in threading.enumerate() if t.ident is not None
        }
        frames: Dict[str, Any] = {}
        for thread_id, frame in sys._current_frames().items():
            frames[str(thread_id)] = {
                "trace": "".join(traceback.format_stack(frame)),
                "thread_name": thread_names.get(thread_id, f"Thread-{thread_id}"),
            }

        data = {
            "event": "WATCHDOG_45S_DEADLOCK_TRIGGER",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "step": self.step_name,
            "pid": os.getpid(),
            "threads": frames,
        }

        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return dump_path

    def _run_loop(self) -> None:
        """Esegue il ciclo periodico e attiva il dump se lo step supera watchdog_sec."""
        while self.running:
            time.sleep(self.cadence_sec)
            if not self.running:
                break

            now = time.time()
            inactivity = now - self.last_beat_time
            if inactivity >= self.watchdog_sec:
                dump_file = self.dump_diagnostics()
                self.emit_pulse(status=f"WATCHDOG_ALERT_DUMP:{dump_file.name}")
                self.last_beat_time = now
            else:
                self.emit_pulse(status="PULSE_OK")


def run_standalone_test() -> int:
    """Valida il funzionamento del segnalatore e del watchdog."""
    signaler = AsyncHeartbeatSignaler(
        step_name="unit_test_pulse",
        cadence_sec=0.5,
        watchdog_sec=1.2,
    )
    signaler.start()
    time.sleep(1.6)
    signaler.reset_step("reset_phase")
    time.sleep(0.7)
    signaler.stop()

    assert signaler.pulse_count >= 3, f"Expected >= 3 pulses, got {signaler.pulse_count}"
    print(f"Heartbeat Signaler test PASS: {signaler.pulse_count} pulses emitted.")
    return 0


def main() -> int:
    """Interfaccia CLI per il demone di battito asincrono e watchdog."""
    parser = argparse.ArgumentParser(
        description="Demone di battito asincrono e watchdog per Nexus Keystone"
    )
    parser.add_argument(
        "--task-id",
        "--step-name",
        dest="task_id",
        type=str,
        default="general_task",
        help="Identificativo del task o step attivo",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_CADENCE_SEC,
        help="Intervallo tra gli impulsi in secondi",
    )
    parser.add_argument(
        "--max-beats",
        type=int,
        default=None,
        help="Numero massimo di impulsi prima di terminare",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Emette un singolo impulso immediato e termina con codice 0",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Esegue l'autotest rapido del segnalatore",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa l'impulso in formato JSON",
    )
    args = parser.parse_args()

    if args.test:
        return run_standalone_test()

    signaler = AsyncHeartbeatSignaler(
        step_name=args.task_id,
        cadence_sec=args.interval,
    )

    if args.once or (args.max_beats is not None and args.max_beats <= 1):
        pulse = signaler.emit_pulse(status="ALIVE")
        if args.json:
            print(json.dumps(pulse, indent=2))
        else:
            print(
                f"Heartbeat Signaler active. Pulse #{pulse['pulse_index']} emitted for '{args.task_id}'."
            )
        return 0

    if args.max_beats is not None and args.max_beats > 1:
        for idx in range(args.max_beats):
            pulse = signaler.emit_pulse(status="ALIVE")
            if args.json:
                print(json.dumps(pulse))
            if idx < args.max_beats - 1:
                time.sleep(max(0.01, args.interval))
        return 0

    signaler.start()
    print(f"Heartbeat Signaler active. Telemetry: {signaler.telemetry_file}")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        signaler.stop()
        print("Heartbeat stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
