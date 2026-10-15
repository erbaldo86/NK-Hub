# -*- coding: utf-8 -*-
"""
Renderer telemetrico Micro-HUD per Nexus Keystone v3.0.0-STE100-Unified.
Allinea HUDState con MicroUIHUDState e supporta il fallback ASCII e le metriche RSI.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Dict, List, Literal, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field

try:
    from platform_runner import reconfigure_streams
except ImportError:
    try:
        from scripts.platform_runner import reconfigure_streams
    except ImportError:
        def reconfigure_streams() -> None:
            pass

try:
    from schemas.nk_ipc_contracts import MicroUIHUDState
except ImportError:
    try:
        from scripts.schemas.nk_ipc_contracts import MicroUIHUDState
    except ImportError:
        MicroUIHUDState = None


GateStatus = Literal["PASSED", "RUNNING", "FAILED", "PENDING", "BLOCKED", "SKIPPED"]
MutexStatus = Literal["LOCKED", "UNLOCKED", "ACQUIRING", "STALE_RECOVERED"]

GATE_SYMBOLS: Dict[GateStatus, str] = {
    "PASSED": "✓",
    "RUNNING": "⟳",
    "FAILED": "✗",
    "PENDING": "⏳",
    "BLOCKED": "⏸",
    "SKIPPED": "⊘",
}

GATE_SYMBOLS_ASCII: Dict[GateStatus, str] = {
    "PASSED": "[OK]",
    "RUNNING": "[RUN]",
    "FAILED": "[FAIL]",
    "PENDING": "[WAIT]",
    "BLOCKED": "[BLOCK]",
    "SKIPPED": "[SKIP]",
}


def is_unicode_stream_supported(stream: object = None) -> bool:
    """Verifica se lo stream di output supporta i simboli Unicode del Micro-HUD."""
    target_stream = stream or sys.stdout
    encoding = getattr(target_stream, "encoding", None)
    if not encoding:
        return True
    try:
        "▓░✓⟳✗⏳⏸⊘".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError, AttributeError):
        return False


class GateEntry(BaseModel):
    """Stato di un singolo gate visualizzato nel Micro-HUD."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    status: GateStatus = "PENDING"
    description: Optional[str] = None


class HUDState(BaseModel):
    """Stato interno del renderer Micro-HUD sincronizzabile con MicroUIHUDState."""

    model_config = ConfigDict(strict=True, extra="forbid")

    version: str = "v3.0"
    progress_percent: int = Field(default=0, ge=0, le=100)
    bar_width: int = Field(default=10, ge=5, le=50)
    gates: List[GateEntry] = Field(default_factory=list)
    mutex_status: MutexStatus = "UNLOCKED"
    agent_id: Optional[str] = None
    domain: Optional[str] = None
    tier1_tokens_used: Optional[int] = Field(default=None, ge=0)
    tier1_token_cap: int = Field(default=350, ge=1)
    elapsed_seconds: Optional[float] = Field(default=None, ge=0.0)
    rsi_delta: Optional[float] = Field(default=None, ge=0.0)
    rsi_fitness_q: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class MicroHUDRenderer:
    """Genera stringhe di stato compatte per la telemetria della sessione."""

    def __init__(
        self,
        version: str = "v3.0",
        default_gates: Optional[Sequence[str]] = ("G1", "G2", "G3", "G4", "G5"),
        bar_width: int = 10,
        ascii_mode: Optional[bool] = None,
    ) -> None:
        reconfigure_streams()
        gates_list = [
            GateEntry(id=gid, status="PENDING") for gid in (default_gates or [])
        ]
        self.state = HUDState(
            version=version,
            progress_percent=0,
            bar_width=bar_width,
            gates=gates_list,
            mutex_status="UNLOCKED",
        )
        self.ascii_mode = ascii_mode

    def set_ascii_mode(self, ascii_mode: bool) -> MicroHUDRenderer:
        """Imposta forzatamente la modalita ASCII pura."""
        self.ascii_mode = ascii_mode
        return self

    def set_progress(self, percent: int) -> MicroHUDRenderer:
        """Aggiorna la percentuale di avanzamento tra 0 e 100."""
        self.state.progress_percent = max(0, min(100, int(percent)))
        return self

    def set_gate(
        self,
        gate_id: str,
        status: GateStatus,
        description: Optional[str] = None,
    ) -> MicroHUDRenderer:
        """Aggiorna o aggiunge lo stato di un gate specifico."""
        for g in self.state.gates:
            if g.id == gate_id:
                g.status = status
                if description:
                    g.description = description
                return self
        self.state.gates.append(
            GateEntry(id=gate_id, status=status, description=description)
        )
        return self

    def set_all_gates(self, statuses: Dict[str, GateStatus]) -> MicroHUDRenderer:
        """Aggiorna in blocco gli stati di una mappa di gate."""
        for gid, status in statuses.items():
            self.set_gate(gid, status)
        return self

    def set_mutex(self, status: MutexStatus) -> MicroHUDRenderer:
        """Imposta lo stato corrente del mutex Win32."""
        self.state.mutex_status = status
        return self

    def set_tier1_budget(self, used: int, cap: int = 350) -> MicroHUDRenderer:
        """Imposta il consumo corrente di token della memoria di Livello 1."""
        self.state.tier1_tokens_used = max(0, used)
        self.state.tier1_token_cap = max(1, cap)
        return self

    def set_agent_context(
        self,
        agent_id: str,
        domain: Optional[str] = None,
    ) -> MicroHUDRenderer:
        """Imposta l'identificatore dell'agente attivo e il relativo dominio."""
        self.state.agent_id = agent_id
        self.state.domain = domain
        return self

    def set_elapsed_time(self, seconds: float) -> MicroHUDRenderer:
        """Imposta il tempo trascorso in secondi."""
        self.state.elapsed_seconds = max(0.0, seconds)
        return self

    def set_rsi_metrics(self, delta_k: float, fitness_q: float) -> MicroHUDRenderer:
        """Imposta le metriche di convergenza RSI (Delta_k e Fitness Q)."""
        self.state.rsi_delta = max(0.0, float(delta_k))
        self.state.rsi_fitness_q = max(0.0, min(100.0, float(fitness_q)))
        return self

    def to_ipc_state(
        self,
        session_id: str = "nk_session",
        hud_status: Literal["IDLE", "RUNNING", "BLOCKED", "ERROR", "COMMITTED"] = "RUNNING",
        active_task: str = "active_op",
    ) -> MicroUIHUDState:
        """Esporta lo stato corrente nel contratto IPC MicroUIHUDState."""
        metrics: Dict[str, float] = {}
        if self.state.rsi_delta is not None:
            metrics["rsi_delta"] = float(self.state.rsi_delta)
        if self.state.rsi_fitness_q is not None:
            metrics["rsi_fitness_q"] = float(self.state.rsi_fitness_q)
        if self.state.tier1_tokens_used is not None:
            metrics["tier1_tokens_used"] = float(self.state.tier1_tokens_used)

        return MicroUIHUDState(
            session_id=session_id,
            hud_status=hud_status,
            active_task=active_task,
            progress_pct=float(self.state.progress_percent),
            metrics=metrics,
            updated_at=time.time(),
        )

    def _build_progress_bar(self, ascii_mode: bool = False) -> str:
        width = self.state.bar_width
        filled_count = int(round((self.state.progress_percent / 100.0) * width))
        filled_count = max(0, min(width, filled_count))
        empty_count = width - filled_count
        if ascii_mode:
            bar = "#" * filled_count + "-" * empty_count
        else:
            bar = "▓" * filled_count + "░" * empty_count
        return f"{bar} {self.state.progress_percent}%"

    def _build_gates_string(self, ascii_mode: bool = False) -> str:
        if not self.state.gates:
            return ""
        rendered_gates = []
        for g in self.state.gates:
            if ascii_mode:
                raw_sym = GATE_SYMBOLS_ASCII.get(g.status, "[WAIT]")
                sym = raw_sym.strip("[]")
                rendered_gates.append(f"[{g.id}:{sym}]")
            else:
                symbol = GATE_SYMBOLS.get(g.status, "⏳")
                rendered_gates.append(f"[{g.id}:{symbol}]")
        return "GATES: " + " ".join(rendered_gates)

    def _render_internal(
        self,
        include_extras: bool = False,
        ascii_mode: bool = False,
    ) -> str:
        bar_part = self._build_progress_bar(ascii_mode=ascii_mode)
        gates_part = self._build_gates_string(ascii_mode=ascii_mode)
        mutex_part = f"MUTEX: {self.state.mutex_status}"

        segments = [f"[NK-HUD {self.state.version}] {bar_part}"]
        if gates_part:
            segments.append(gates_part)
        segments.append(mutex_part)

        if include_extras:
            if self.state.rsi_delta is not None and self.state.rsi_fitness_q is not None:
                segments.append(
                    f"RSI: Δ={self.state.rsi_delta:.1f} Q={self.state.rsi_fitness_q:.1f}"
                )
            if self.state.tier1_tokens_used is not None:
                segments.append(
                    f"TIER1: {self.state.tier1_tokens_used}/{self.state.tier1_token_cap} tok"
                )
            if self.state.agent_id:
                dom_suffix = f" [{self.state.domain}]" if self.state.domain else ""
                segments.append(f"AGENT: {self.state.agent_id}{dom_suffix}")
            if self.state.elapsed_seconds is not None:
                segments.append(f"T: {self.state.elapsed_seconds:.2f}s")

        return " | ".join(segments)

    def render(
        self,
        include_extras: bool = False,
        ascii_mode: Optional[bool] = None,
    ) -> str:
        """Restituisce la stringa HUD con fallback automatico in ASCII."""
        use_ascii = (
            self.ascii_mode
            if self.ascii_mode is not None
            else not is_unicode_stream_supported()
        )
        if ascii_mode is not None:
            use_ascii = ascii_mode

        if not use_ascii:
            try:
                candidate = self._render_internal(
                    include_extras=include_extras,
                    ascii_mode=False,
                )
                enc = getattr(sys.stdout, "encoding", None) or "utf-8"
                candidate.encode(enc)
                return candidate
            except (UnicodeEncodeError, LookupError):
                use_ascii = True

        return self._render_internal(include_extras=include_extras, ascii_mode=True)

    def render_markdown_block(
        self,
        include_extras: bool = False,
        ascii_mode: Optional[bool] = None,
    ) -> str:
        """Restituisce il Micro-HUD racchiuso in un blocco di codice Markdown."""
        hud_line = self.render(include_extras=include_extras, ascii_mode=ascii_mode)
        return f"```text\n{hud_line}\n```"

    @classmethod
    def render_pulse(
        cls,
        step: str,
        percent: int,
        pulse_status: str = "ALIVE",
        ascii_mode: Optional[bool] = None,
    ) -> str:
        """Genera una stringa rapida di impulso con tolleranza CP1252 e UTF-8."""
        reconfigure_streams()
        bar_width = 10
        p = max(0, min(100, int(percent)))
        filled = int(round((p / 100.0) * bar_width))
        empty = bar_width - filled

        use_ascii = (
            ascii_mode
            if ascii_mode is not None
            else not is_unicode_stream_supported()
        )
        if not use_ascii:
            try:
                bar = "▓" * filled + "░" * empty
                pulse_str = f"[NK-PULSE v3.0] {bar} {p}% | STEP: {step} | STATUS: {pulse_status}"
                enc = getattr(sys.stdout, "encoding", None) or "utf-8"
                pulse_str.encode(enc)
                return pulse_str
            except (UnicodeEncodeError, LookupError):
                use_ascii = True

        bar = "#" * filled + "-" * empty
        return f"[NK-PULSE v3.0] {bar} {p}% | STEP: {step} | STATUS: {pulse_status}"


def main() -> int:
    """Interfaccia CLI per il renderer telemetrico Micro-HUD."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Real-Time Micro-HUD Stream Renderer"
    )
    parser.add_argument("--percent", type=int, default=100)
    parser.add_argument("--mutex", type=str, default="UNLOCKED")
    parser.add_argument("--agent", type=str, default="NK-Master-Hub")
    parser.add_argument("--domain", type=str, default="DEVX")
    parser.add_argument("--ascii", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    renderer = MicroHUDRenderer(ascii_mode=args.ascii if args.ascii else None)
    renderer.set_progress(args.percent)
    renderer.set_mutex(args.mutex)
    renderer.set_agent_context(args.agent, args.domain)
    for g in ("G1", "G2", "G3", "G4", "G5"):
        renderer.set_gate(g, "PASSED")

    if args.json:
        print(renderer.state.model_dump_json(indent=2))
    else:
        print(renderer.render(ascii_mode=args.ascii if args.ascii else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
