"""Modelli Pydantic e calcolo Ochiai per SBFL Pytest Bridge."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field

def compute_ochiai(
    n_ef: int, n_ep: int, total_failed: int, total_passed: int = 0
) -> float:
    """Calcola il coefficiente Ochiai limitando n_ef a total_failed."""
    _ = total_passed
    if total_failed <= 0:
        return 0.0
    n_ef = min(max(0, n_ef), total_failed)
    n_ep = max(0, n_ep)
    denom = math.sqrt(total_failed * (n_ef + n_ep))
    return round(n_ef / denom, 6) if denom > 0.0 else 0.0


class PytestRunSummary(BaseModel):
    """Riepilogo strutturato di un'esecuzione pytest."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    total_tests: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    exit_code: int
    duration_sec: float = Field(ge=0.0)
    failed_test_names: List[str] = Field(default_factory=list)
    passed_test_names: List[str] = Field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""


class OchiaiBridgeLocation(BaseModel):
    """Record di localizzazione del guasto calcolato tramite SBFL Ochiai."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file_path: str
    line_number: int = Field(ge=1)
    suspiciousness: float = Field(ge=0.0, le=1.0)
    error_type: str
    error_message: str
    failing_line_content: str = ""
    total_failed_tests: int = Field(ge=0, default=1)
    n_ef: int = Field(ge=0, default=1)
    n_ep: int = Field(ge=0, default=0)

    def to_compact_payload(self) -> Dict[str, Any]:
        """Genera un dizionario compatto garantito sotto 80 token (< 320 caratteri)."""
        short_file = (
            Path(self.file_path).name if len(self.file_path) > 30 else self.file_path
        )
        short_msg = (
            (self.error_message[:40] + "...")
            if len(self.error_message) > 40
            else self.error_message
        )
        short_ctx = self.failing_line_content.strip()[:35]

        return {
            "loc": f"{short_file}:{self.line_number}",
            "err": f"{self.error_type}: {short_msg}",
            "score": round(self.suspiciousness, 3),
            "ctx": short_ctx,
        }

    def render_payload_json(self) -> str:
        """Serializza il dizionario compatto in stringa JSON minimale (< 320 caratteri, GT-07)."""
        payload = self.to_compact_payload()
        rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if len(rendered) >= 320:
            payload["ctx"] = payload["ctx"][:15]
            payload["err"] = payload["err"][:25]
            rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return rendered
