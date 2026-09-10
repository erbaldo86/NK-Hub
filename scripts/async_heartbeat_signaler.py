#!/usr/bin/env python3
"""
scripts/async_heartbeat_signaler.py - Nexus Keystone v1.6.0-VibeEnhanced
Anti-Freeze Telemetry Pulse & Heartbeat Watchdog Sentinel.

Implements [RULE-01.9] ANTI_FREEZE_HEARTBEAT_MANDATE:
- Liveness Pulse Cadence: 15-20 seconds.
- Maximum Inactivity Watchdog: 45.0 seconds.
- Non-blocking telemetry output stream.
- Isolated Diagnostic Dumps in %TEMP%/nk_diagnostics/ (strictly non-Google Drive).
"""

import os
import sys
import time
import json
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_CADENCE_SEC = 15.0

DEFAULT_WATCHDOG_SEC = 45.0

class AsyncHeartbeatSignaler:
    """
    Background liveness pulse emitter & watchdog sentinel.
    Ensures long-running operations do not appear frozen to IDE/users
    and captures non-destructive diagnostic dumps if a thread hangs.
    """

    def __init__(
        self,
        step_name: str = "general_task",
        cadence_sec: float = DEFAULT_CADENCE_SEC,
        watchdog_sec: float = DEFAULT_WATCHDOG_SEC,
        telemetry_file: Optional[Path] = None,
    ):
        self.step_name = step_name
        self.cadence_sec = cadence_sec
        self.watchdog_sec = watchdog_sec
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_beat_time = time.time()
        self.pulse_count = 0

        # Isolated diagnostics folder in local temp (never on G:)
        self.diag_dir = Path(tempfile.gettempdir()) / "nk_diagnostics"
        self.diag_dir.mkdir(parents=True, exist_ok=True)

        if telemetry_file:
            self.telemetry_file = Path(telemetry_file)
        else:
            self.telemetry_file = self.diag_dir / "heartbeat_stream.jsonl"

    def reset_step(self, new_step_name: str):
        """Resets the timer for a new major step to prevent false watchdog triggers."""
        self.step_name = new_step_name
        self.last_beat_time = time.time()
        self.emit_pulse(status="STEP_RESET")

    def start(self):
        """Starts the background pulse thread."""
        if self.running:
            return
        self.running = True
        self.last_beat_time = time.time()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops the heartbeat thread cleanly."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def emit_pulse(self, status: str = "ALIVE") -> Dict[str, Any]:
        """Emits a single heartbeat pulse record."""
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
        """Dumps non-destructive stack frames into %TEMP%/nk_diagnostics/."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dump_path = self.diag_dir / f"diag_dump_{timestamp}.json"
        
        frames = {}
        for thread_id, frame in sys._current_frames().items():
            frames[str(thread_id)] = {
                "trace": "".join(traceback.format_stack(frame)),
                "thread_name": getattr(threading.current_thread(), "name", "unknown"),
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

    def _run_loop(self):
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
                self.last_beat_time = now


def run_standalone_test():
    """Validates the signaler for automated test suites."""
    print("Testing AsyncHeartbeatSignaler (5s fast test)...")
    signaler = AsyncHeartbeatSignaler(step_name="unit_test_pulse", cadence_sec=1.0, watchdog_sec=3.0)
    signaler.start()
    time.sleep(3.5)
    signaler.reset_step("reset_phase")
    time.sleep(1.5)
    signaler.stop()
    
    assert signaler.pulse_count >= 3, f"Expected >= 3 pulses, got {signaler.pulse_count}"
    print(f"✅ Heartbeat Signaler test PASS: {signaler.pulse_count} pulses emitted.")
    return 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(run_standalone_test())
    else:
        signaler = AsyncHeartbeatSignaler()
        signaler.start()
        print(f"💓 Heartbeat Signaler active. Telemetry: {signaler.telemetry_file}")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            signaler.stop()
            print("Heartbeat stopped.")
