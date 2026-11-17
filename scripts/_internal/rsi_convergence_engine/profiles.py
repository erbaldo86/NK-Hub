"""Profili Tensor-RSI 2D, formule matematiche Delta_k / Q(S_k) e validatore STE100."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from _internal.rsi_convergence_engine.constants import RSIDefectVector
from _internal.rsi_convergence_engine.lazy_bridge import get_ste100_validator


class RSIProfileConfig(BaseModel):
    """Configurazione dei pesi e della formula di fitness per un profilo Tensor-RSI."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    profile_id: str = Field(description="Identificativo breve P1..P5")
    name: str = Field(description="Nome canonico del profilo RSI")
    weights: Tuple[int, int, int, int, int, int, int] = Field(
        description="Pesi (sast, tests_failed, contract, high, medium, low, doc_drift)"
    )
    test_weight: float = Field(description="Peso percentuale della componente test")
    delta_weight: float = Field(description="Peso percentuale della componente Delta_k")
    delta_scale: float = Field(description="Fattore di scala iperbolico di Delta_k")
    target_latency_ms: int = Field(description="Latenza target massima in millisecondi")


class RSIProfileRegistry:
    """Registro deterministico dei 5 profili di dominio Tensor-RSI 2D."""

    PROFILES: Dict[str, RSIProfileConfig] = {
        "vibe_sprint_micro_rsi": RSIProfileConfig(
            profile_id="P1",
            name="vibe_sprint_micro_rsi",
            weights=(15, 10, 10, 5, 1, 0, 1),
            test_weight=60.0,
            delta_weight=40.0,
            delta_scale=25.0,
            target_latency_ms=500,
        ),
        "code_rsi": RSIProfileConfig(
            profile_id="P2",
            name="code_rsi",
            weights=(15, 10, 10, 5, 2, 1, 1),
            test_weight=60.0,
            delta_weight=40.0,
            delta_scale=25.0,
            target_latency_ms=4000,
        ),
        "spec_rsi": RSIProfileConfig(
            profile_id="P3",
            name="spec_rsi",
            weights=(0, 0, 15, 8, 4, 1, 5),
            test_weight=0.0,
            delta_weight=100.0,
            delta_scale=15.0,
            target_latency_ms=40,
        ),
        "ui_ux_rsi": RSIProfileConfig(
            profile_id="P4",
            name="ui_ux_rsi",
            weights=(10, 5, 12, 6, 3, 1, 2),
            test_weight=50.0,
            delta_weight=50.0,
            delta_scale=20.0,
            target_latency_ms=60,
        ),
        "ste100_rsi": RSIProfileConfig(
            profile_id="P5",
            name="ste100_rsi",
            weights=(0, 0, 10, 5, 2, 1, 10),
            test_weight=0.0,
            delta_weight=100.0,
            delta_scale=10.0,
            target_latency_ms=30,
        ),
    }

    _ALIASES: Dict[str, str] = {
        "p1": "vibe_sprint_micro_rsi",
        "vibe_sprint_micro_rsi": "vibe_sprint_micro_rsi",
        "vibe": "vibe_sprint_micro_rsi",
        "p2": "code_rsi",
        "code_rsi": "code_rsi",
        "code": "code_rsi",
        "p3": "spec_rsi",
        "spec_rsi": "spec_rsi",
        "spec": "spec_rsi",
        "p4": "ui_ux_rsi",
        "ui_ux_rsi": "ui_ux_rsi",
        "ui_ux": "ui_ux_rsi",
        "p5": "ste100_rsi",
        "ste100_rsi": "ste100_rsi",
        "ste100": "ste100_rsi",
    }

    @classmethod
    def get(cls, profile: str = "code_rsi") -> RSIProfileConfig:
        """Restituisce la configurazione del profilo richiesto o code_rsi come fallback."""
        key = cls._ALIASES.get(profile.lower().strip(), "code_rsi")
        return cls.PROFILES[key]

    @classmethod
    def list_profiles(cls) -> List[str]:
        """Restituisce la lista ordinata dei 5 nomi profilo registrati."""
        return list(cls.PROFILES.keys())


def compute_delta(defects: RSIDefectVector, profile: str = "code_rsi") -> int:
    """Calcola la metrica lineare pesata Delta_k secondo il profilo specificato."""
    cfg = RSIProfileRegistry.get(profile)
    w_sast, w_tfail, w_c, w_h, w_m, w_l, w_g = cfg.weights
    raw_delta = (
        w_sast * defects.sast_critical
        + w_tfail * defects.tests_failed
        + w_c * defects.contract_violations
        + w_h * defects.high_findings
        + w_m * defects.medium_findings
        + w_l * defects.low_findings
        + w_g * defects.doc_drift
        + 20 * defects.poc_confirmed_exploits
        + 12 * defects.semantic_drift_findings
        + 100 * defects.deception_gaming_count
    )
    if w_tfail == 0 and defects.tests_failed > 0:
        raw_delta += 10 * defects.tests_failed
    if defects.hallucinated_refs > 0:
        raw_delta += 25 * defects.hallucinated_refs
    return raw_delta


def compute_fitness(
    defects: RSIDefectVector,
    delta_k: Optional[int] = None,
    profile: str = "code_rsi",
) -> float:
    """Calcola il punteggio di fitness iperbolico Q(S_k) nell'intervallo [0, 100]."""
    if defects.deception_gaming_count > 0:
        return 0.0
    cfg = RSIProfileRegistry.get(profile)
    d_val = compute_delta(defects, profile=profile) if delta_k is None else delta_k
    if cfg.test_weight <= 0.0:
        if d_val == 0 and defects.tests_failed > 0:
            d_val += 10 * defects.tests_failed
        q_val = cfg.delta_weight / (1.0 + (float(d_val) / cfg.delta_scale))
        return round(q_val, 4)

    passed, total = defects.effective_totals()
    pass_ratio = (float(passed) / float(total)) if total > 0 else 0.0
    pass_ratio = max(0.0, min(1.0, pass_ratio))
    q_val = (cfg.test_weight * pass_ratio) + (
        cfg.delta_weight / (1.0 + (float(d_val) / cfg.delta_scale))
    )
    if total > 0 and defects.unmeasured_components:
        q_val = min(q_val, 85.0)
    return round(q_val, 4)


def verify_ste100_compliance(
    text: str, max_sentence_words: int = 20
) -> Dict[str, Any]:
    """Verifica la conformita ASD-STE100 delegando al modulo SSOT nk_transcript_tools."""
    validator = get_ste100_validator()
    return validator(text, max_sentence_words=max_sentence_words)


_fallback_verify_ste100_compliance = verify_ste100_compliance
