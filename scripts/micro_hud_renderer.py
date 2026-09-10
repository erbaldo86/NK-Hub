"""
Nexus Keystone v1.1.0-Universal: Real-Time Micro-HUD Stream Renderer.
Compliant with:
- Micro-UI HUD Markdown Stream:
  `[NK-HUD v1.1] ▓▓▓▓▓▓▓▓░░ 80% | GATES: [G1:✓] [G2:✓] [G3:✓] [G4:✓] [G5:⟳] | MUTEX: LOCKED`
- Configurable Gates (G1..G5 or custom named gates) with deterministic symbols:
  ✓ (Passed), ⟳ (Running), ✗ (Failed), ⏳ (Pending), ⏸ (Blocked), ⊘ (Skipped)
- Mutex lock status tracking (LOCKED, UNLOCKED, ACQUIRING, STALE_RECOVERED)
- In-Context Tier 1 Token Budget gauge (e.g., TIER1: 280/350 tok)
- Pydantic v2 in Strict Mode.
"""

from __future__ import annotations

import math
from typing import Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator


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


class GateEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    status: GateStatus = "PENDING"
    description: Optional[str] = None


class HUDState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: str = "v1.1"
    progress_percent: int = Field(default=0, ge=0, le=100)
    bar_width: int = Field(default=10, ge=5, le=50)
    gates: List[GateEntry] = Field(default_factory=list)
    mutex_status: MutexStatus = "UNLOCKED"
    agent_id: Optional[str] = None
    domain: Optional[str] = None
    tier1_tokens_used: Optional[int] = Field(default=None, ge=0)
    tier1_token_cap: int = Field(default=350, ge=1)
    elapsed_seconds: Optional[float] = Field(default=None, ge=0.0)


class MicroHUDRenderer:
    """
    Renders high-density deterministic markdown HUD widgets for user chat and log streaming.
    """

    def __init__(
        self,
        version: str = "v1.1",
        default_gates: Optional[Sequence[str]] = ("G1", "G2", "G3", "G4", "G5"),
        bar_width: int = 10,
    ) -> None:
        gates_list = [GateEntry(id=gid, status="PENDING") for gid in (default_gates or [])]
        self.state = HUDState(
            version=version,
            progress_percent=0,
            bar_width=bar_width,
            gates=gates_list,
            mutex_status="UNLOCKED",
        )

    # ------------------------------------------------------------------
    # STATE MUTATORS
    # ------------------------------------------------------------------
    def set_progress(self, percent: int) -> MicroHUDRenderer:
        self.state.progress_percent = max(0, min(100, int(percent)))
        return self

    def set_gate(self, gate_id: str, status: GateStatus, description: Optional[str] = None) -> MicroHUDRenderer:
        for g in self.state.gates:
            if g.id == gate_id:
                g.status = status
                if description:
                    g.description = description
                return self
        self.state.gates.append(GateEntry(id=gate_id, status=status, description=description))
        return self

    def set_all_gates(self, statuses: Dict[str, GateStatus]) -> MicroHUDRenderer:
        for gid, status in statuses.items():
            self.set_gate(gid, status)
        return self

    def set_mutex(self, status: MutexStatus) -> MicroHUDRenderer:
        self.state.mutex_status = status
        return self

    def set_tier1_budget(self, used: int, cap: int = 350) -> MicroHUDRenderer:
        self.state.tier1_tokens_used = max(0, used)
        self.state.tier1_token_cap = max(1, cap)
        return self

    def set_agent_context(self, agent_id: str, domain: Optional[str] = None) -> MicroHUDRenderer:
        self.state.agent_id = agent_id
        self.state.domain = domain
        return self

    def set_elapsed_time(self, seconds: float) -> MicroHUDRenderer:
        self.state.elapsed_seconds = max(0.0, seconds)
        return self

    # ------------------------------------------------------------------
    # PROGRESS BAR BUILDER
    # ------------------------------------------------------------------
    def _build_progress_bar(self) -> str:
        width = self.state.bar_width
        filled_count = int(round((self.state.progress_percent / 100.0) * width))
        filled_count = max(0, min(width, filled_count))
        empty_count = width - filled_count
        bar = "▓" * filled_count + "░" * empty_count
        return f"{bar} {self.state.progress_percent}%"

    # ------------------------------------------------------------------
    # GATES RENDERER
    # ------------------------------------------------------------------
    def _build_gates_string(self) -> str:
        if not self.state.gates:
            return ""
        rendered_gates = []
        for g in self.state.gates:
            symbol = GATE_SYMBOLS.get(g.status, "⏳")
            rendered_gates.append(f"[{g.id}:{symbol}]")
        return "GATES: " + " ".join(rendered_gates)

    # ------------------------------------------------------------------
    # RENDER METHODS
    # ------------------------------------------------------------------
    def render(self, include_extras: bool = False) -> str:
        """
        Renders standard HUD string:
        [NK-HUD v1.1] ▓▓▓▓▓▓▓▓░░ 80% | GATES: [G1:✓] [G2:✓] [G3:✓] [G4:✓] [G5:⟳] | MUTEX: LOCKED
        """
        bar_part = self._build_progress_bar()
        gates_part = self._build_gates_string()
        mutex_part = f"MUTEX: {self.state.mutex_status}"

        segments = [f"[NK-HUD {self.state.version}] {bar_part}"]
        if gates_part:
            segments.append(gates_part)
        segments.append(mutex_part)

        if include_extras:
            if self.state.tier1_tokens_used is not None:
                segments.append(f"TIER1: {self.state.tier1_tokens_used}/{self.state.tier1_token_cap} tok")
            if self.state.agent_id:
                dom_suffix = f" [{self.state.domain}]" if self.state.domain else ""
                segments.append(f"AGENT: {self.state.agent_id}{dom_suffix}")
            if self.state.elapsed_seconds is not None:
                segments.append(f"T: {self.state.elapsed_seconds:.2f}s")

        return " | ".join(segments)

    def render_markdown_block(self, include_extras: bool = False) -> str:
        """Renders HUD enclosed in a clean markdown code/status container."""
        hud_line = self.render(include_extras=include_extras)
        return f"```text\n{hud_line}\n```"

    @classmethod
    def render_pulse(cls, step: str, percent: int, pulse_status: str = "ALIVE") -> str:
        """Renders a fast inline pulse string: [NK-PULSE v1.6] ▓▓▓▓▓░░░░░ 50% | STEP: build | STATUS: ALIVE"""
        bar_width = 10
        p = max(0, min(100, int(percent)))
        filled = int(round((p / 100.0) * bar_width))
        empty = bar_width - filled
        bar = "▓" * filled + "░" * empty
        return f"[NK-PULSE v1.6] {bar} {p}% | STEP: {step} | STATUS: {pulse_status}"

