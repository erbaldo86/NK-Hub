#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di convergenza RSI per Nexus Keystone v3.2.0.
Modulo: scripts/rsi_convergence_engine.py.
Implementa le regole [RULE-RSI] e [RULE-STE100] con ottimizzazioni OPT-2 e OPT-9.

Funzionalita principali:
1. Calcola la metrica lineare di difetto Delta_k e la fitness Q(S_k).
2. Applica le sei guardie invarianti G1, G2, G3, G4, G5 e G6.
3. Sincronizza con threading.Lock la catena SHA-256 in nk_tracking/rsi_telemetry.jsonl (OPT-9).
4. Esegue la verifica di conformita dell'ecosistema con filtro directory escluse (OPT-9).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
for _p in (_workspace_root, _workspace_root / "scripts", _scripts_dir):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(_scripts_dir) in sys.path:
    sys.path.remove(str(_scripts_dir))
sys.path.insert(0, str(_scripts_dir))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    try:
        from scripts.platform_runner import reconfigure_streams
    except ImportError:
        def reconfigure_streams() -> None:
            pass

try:
    from healing_snapshot_rollback import HealingSnapshotManager
except ImportError:
    try:
        from scripts.healing_snapshot_rollback import HealingSnapshotManager
    except ImportError:
        HealingSnapshotManager = None  # type: ignore[assignment]

try:
    from ast_guard_validator import ASTGuardValidator
    if not hasattr(ASTGuardValidator, "check_sast_constructs"):
        _agv_path = _scripts_dir / "ast_guard_validator.py"
        if _agv_path.exists():
            _agv_spec = importlib.util.spec_from_file_location(
                "ast_guard_validator", str(_agv_path)
            )
            if _agv_spec and _agv_spec.loader:
                _agv_mod = importlib.util.module_from_spec(_agv_spec)
                sys.modules["ast_guard_validator"] = _agv_mod
                _agv_spec.loader.exec_module(_agv_mod)
                ASTGuardValidator = _agv_mod.ASTGuardValidator
except ImportError:
    try:
        from scripts.ast_guard_validator import ASTGuardValidator
    except ImportError:
        ASTGuardValidator = None  # type: ignore[assignment]


MODE_ITERATION_CAPS: Dict[str, int] = {
    "mode_c": 2,
    "c": 2,
    "vibe": 2,
    "mode_b": 3,
    "b": 3,
    "fast": 3,
    "mode_a": 4,
    "a": 4,
    "sovereign": 4,
}

EXCLUDED_SCAN_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".staging",
    ".pytest_cache",
}

_TELEMETRY_LOCK = threading.Lock()


class RSIDefectVector(BaseModel):
    """Vettore dei difetti rilevati in una singola iterazione RSI."""

    model_config = ConfigDict(strict=True, extra="forbid")

    sast_critical: int = Field(default=0, ge=0, description="Violazioni SAST critiche")
    tests_failed: int = Field(default=0, ge=0, description="Test falliti nella suite")
    tests_passed: int = Field(default=100, ge=0, description="Test superati nella suite")
    tests_total: int = Field(default=0, ge=0, description="Totale test eseguiti")
    contract_violations: int = Field(
        default=0, ge=0, description="Violazioni contratti IPC o 2PC"
    )
    high_findings: int = Field(default=0, ge=0, description="Finding ad alta gravita")
    medium_findings: int = Field(
        default=0, ge=0, description="Finding a media gravita"
    )
    low_findings: int = Field(default=0, ge=0, description="Finding a bassa gravita")
    doc_drift: int = Field(
        default=0, ge=0, description="Disallineamenti documentali o STE100"
    )
    poc_confirmed_exploits: int = Field(
        default=0,
        ge=0,
        description="Exploit o bug logici confermati da Referee PoC",
    )
    semantic_drift_findings: int = Field(
        default=0,
        ge=0,
        description="Drift contrattuali o topologici L2/L3 confermati",
    )

    def effective_totals(self) -> Tuple[int, int]:
        """Restituisce la coppia (tests_passed, tests_total) normalizzata."""
        if self.tests_total > 0:
            return self.tests_passed, self.tests_total
        computed_total = self.tests_passed + self.tests_failed
        if computed_total > 0:
            return self.tests_passed, computed_total
        return 100, 100


class RSIIterationRecord(BaseModel):
    """Record immutabile di una singola iterazione del ciclo RSI."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str = Field(description="Identificativo univoco della sessione RSI")
    iteration: int = Field(ge=0, description="Indice progressivo dell'iterazione")
    mode: str = Field(default="mode_a", description="Modalita operativa Mode A, B, C o D")
    defects: RSIDefectVector = Field(description="Vettore analitico dei difetti")
    delta_k: int = Field(ge=0, description="Distanza lineare pesata dallo stato ottimale")
    fitness_q: float = Field(
        ge=0.0, le=100.0, description="Punteggio di fitness iperbolica"
    )
    state_hash: str = Field(description="Hash SHA-256 dello stato dei file target")
    verdict: str = Field(description="Esito deterministico dell'iterazione")
    rolled_back: bool = Field(default=False, description="Indica se e avvenuto un rollback")
    prev_hash: str = Field(
        default="0" * 64, description="Hash del record precedente nella catena"
    )
    record_hash: str = Field(default="", description="Hash SHA-256 del record corrente")
    timestamp: float = Field(default_factory=time.time, description="Timestamp epoch UTC")


class RSISessionReport(BaseModel):
    """Rapporto finale di una sessione di convergenza RSI."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str = Field(description="Identificativo della sessione RSI")
    mode: str = Field(default="mode_a", description="Modalita di esecuzione")
    max_iterations: int = Field(
        ge=1, description="Limite massimo di iterazioni per la modalita"
    )
    iterations_used: int = Field(
        ge=0, description="Numero di iterazioni effettivamente eseguite"
    )
    converged: bool = Field(description="True se Delta_k == 0 e Q(S_k) == 100.0")
    final_status: str = Field(description="Stato finale del motore RSI")
    initial_delta: int = Field(ge=0, description="Valore iniziale di Delta_k")
    final_delta: int = Field(ge=0, description="Valore finale di Delta_k")
    initial_fitness_q: float = Field(
        ge=0.0, le=100.0, description="Fitness iniziale Q(S_0)"
    )
    final_fitness_q: float = Field(
        ge=0.0, le=100.0, description="Fitness finale Q(S_k)"
    )
    rollbacks_count: int = Field(
        default=0, ge=0, description="Totale rollback eseguiti per Guardia G2"
    )
    cycle_detected: bool = Field(
        default=False, description="True se Guardia G3 ha rilevato un ciclo"
    )
    visited_hashes: List[str] = Field(
        default_factory=list, description="Lista hash SHA-256 visitati"
    )
    history: List[RSIIterationRecord] = Field(
        default_factory=list, description="Cronologia iterazioni"
    )


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
    )
    if w_tfail == 0 and defects.tests_failed > 0:
        raw_delta += 10 * defects.tests_failed
    return raw_delta


def compute_fitness(
    defects: RSIDefectVector,
    delta_k: Optional[int] = None,
    profile: str = "code_rsi",
) -> float:
    """Calcola il punteggio di fitness iperbolico Q(S_k) nell'intervallo [0, 100]."""
    cfg = RSIProfileRegistry.get(profile)
    d_val = compute_delta(defects, profile=profile) if delta_k is None else delta_k
    if cfg.test_weight <= 0.0:
        if d_val == 0 and defects.tests_failed > 0:
            d_val += 10 * defects.tests_failed
        q_val = cfg.delta_weight / (1.0 + (float(d_val) / cfg.delta_scale))
        return round(q_val, 4)

    passed, total = defects.effective_totals()
    pass_ratio = (float(passed) / float(total)) if total > 0 else 1.0
    pass_ratio = max(0.0, min(1.0, pass_ratio))
    q_val = (cfg.test_weight * pass_ratio) + (
        cfg.delta_weight / (1.0 + (float(d_val) / cfg.delta_scale))
    )
    return round(q_val, 4)


def verify_ste100_compliance(text: str, max_sentence_words: int = 20) -> Dict[str, Any]:
    """Verifica la conformita di un testo allo standard tecnico ASD-STE100."""
    violations: List[str] = []
    in_code_block = False
    in_yaml_frontmatter = False
    in_yaml_card = False
    seen_first_content = False

    for line_idx, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not seen_first_content and not stripped:
            continue
        if not seen_first_content:
            seen_first_content = True
            if stripped == "---":
                in_yaml_frontmatter = True
                continue
        elif in_yaml_frontmatter:
            if stripped == "---":
                in_yaml_frontmatter = False
            continue

        if stripped.startswith("<yaml_metadata_card>"):
            if "</yaml_metadata_card>" not in stripped:
                in_yaml_card = True
            continue
        if in_yaml_card:
            if "</yaml_metadata_card>" in stripped:
                in_yaml_card = False
            continue

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped:
            continue
        if stripped.startswith("|") or stripped.startswith("http"):
            continue

        # Regola 5: Divieto di incisi con trattini lunghi o medi spaziati
        if " \u2014 " in raw_line or " \u2013 " in raw_line:
            violations.append(
                f"Riga {line_idx}: Rilevato inciso con trattino lungo o medio vietato da [RULE-STE100]."
            )

        # Pulizia link markdown e codice inline prima del conteggio parole
        clean_line = re.sub(r"`[^`]*`", "TOKEN", stripped)
        clean_line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean_line)
        clean_line = re.sub(r"^[\*\-\+\d\.\>\s#]+", "", clean_line)
        clean_line = re.sub(r"(?<=\w)\.(?=\w)", "_", clean_line)

        sentences = [s.strip() for s in re.split(r"[\.!\?]+", clean_line) if s.strip()]
        for sent in sentences:
            words = [w for w in sent.split() if any(ch.isalpha() for ch in w)]
            if len(words) > max_sentence_words:
                violations.append(
                    f"Riga {line_idx}: Frase troppo lunga ({len(words)} parole > {max_sentence_words})."
                )

    return {
        "passed": len(violations) == 0,
        "violations_count": len(violations),
        "violations": violations,
    }


def _is_excluded_rel_path(path: Path, base_root: Path) -> bool:
    """Verifica se il percorso relativo a base_root attraversa directory escluse (OPT-9)."""
    try:
        rel_parts = path.relative_to(base_root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in EXCLUDED_SCAN_DIRS for part in rel_parts)


class RSIConvergenceEngine:
    """Motore deterministico di convergenza RSI con guardie G1..G6."""

    _TELEMETRY_LOCK = _TELEMETRY_LOCK

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        telemetry_path: Optional[Path] = None,
        root: Optional[Path] = None,
    ) -> None:
        reconfigure_streams()
        effective_root = root if root is not None else workspace_root
        self.workspace_root = (
            Path(effective_root).resolve() if effective_root else _workspace_root
        )
        self.root = self.workspace_root
        self.telemetry_path = (
            Path(telemetry_path).resolve()
            if telemetry_path
            else self.workspace_root / "nk_tracking" / "rsi_telemetry.jsonl"
        )
        self.snapshot_mgr = (
            HealingSnapshotManager() if HealingSnapshotManager is not None else None
        )

    @staticmethod
    def get_max_iterations(mode: str = "mode_a") -> int:
        """Restituisce il cap di iterazioni per la modalita specificata (Guardia G5)."""
        return MODE_ITERATION_CAPS.get(mode.lower().strip(), 4)

    @staticmethod
    def compute_delta(defects: RSIDefectVector, profile: str = "code_rsi") -> int:
        """Calcola la metrica lineare Delta_k."""
        return compute_delta(defects, profile=profile)

    @staticmethod
    def compute_fitness(
        defects: RSIDefectVector,
        delta_k: Optional[int] = None,
        profile: str = "code_rsi",
    ) -> float:
        """Calcola la fitness Q(S_k)."""
        return compute_fitness(defects, delta_k=delta_k, profile=profile)

    @staticmethod
    def is_converged(defects: RSIDefectVector, profile: str = "code_rsi") -> bool:
        """Verifica la condizione di stop Guardia G1 (Delta_k == 0 e Q(S_k) == 100.0)."""
        d_k = compute_delta(defects, profile=profile)
        q_k = compute_fitness(defects, delta_k=d_k, profile=profile)
        return d_k == 0 and q_k == 100.0

    @staticmethod
    def check_hard_gate_regression(
        prev_defects: RSIDefectVector,
        curr_defects: RSIDefectVector,
        strict_monotonic: bool = False,
    ) -> Tuple[bool, str]:
        """Verifica se gli Hard Invariants sono peggiorati rispetto allo stato precedente (Guardia G2)."""
        if curr_defects.tests_passed < prev_defects.tests_passed:
            return (
                True,
                f"Test passati scesi da {prev_defects.tests_passed} a {curr_defects.tests_passed}.",
            )
        if curr_defects.tests_failed > prev_defects.tests_failed:
            return (
                True,
                f"Test falliti saliti da {prev_defects.tests_failed} a {curr_defects.tests_failed}.",
            )
        if curr_defects.sast_critical > prev_defects.sast_critical:
            return (
                True,
                f"SAST critici saliti da {prev_defects.sast_critical} a {curr_defects.sast_critical}.",
            )
        if curr_defects.contract_violations > prev_defects.contract_violations:
            return (
                True,
                f"Violazioni contratti salite da {prev_defects.contract_violations} a {curr_defects.contract_violations}.",
            )
        if curr_defects.high_findings > prev_defects.high_findings:
            return (
                True,
                f"Finding High saliti da {prev_defects.high_findings} a {curr_defects.high_findings}.",
            )
        if curr_defects.poc_confirmed_exploits > prev_defects.poc_confirmed_exploits:
            return (
                True,
                f"Exploit PoC confermati saliti da {prev_defects.poc_confirmed_exploits} a {curr_defects.poc_confirmed_exploits}.",
            )
        if curr_defects.semantic_drift_findings > prev_defects.semantic_drift_findings:
            return (
                True,
                f"Semantic drift saliti da {prev_defects.semantic_drift_findings} a {curr_defects.semantic_drift_findings}.",
            )
        if strict_monotonic:
            prev_d = compute_delta(prev_defects)
            curr_d = compute_delta(curr_defects)
            if curr_d > prev_d or (prev_d > 0 and curr_d >= prev_d):
                return (
                    True,
                    f"Delta_k non migliorato in modalita strict_monotonic da {prev_d} a {curr_d}.",
                )
        return False, "Nessuna regressione rilevata sugli invarianti hard."

    @staticmethod
    def compute_files_state_hash(target_files: Sequence[Path | str]) -> str:
        """Calcola l'hash SHA-256 cumulativo dei file target per la Guardia G3."""
        hasher = hashlib.sha256()
        if not target_files:
            hasher.update(b"EMPTY_TARGET_SET")
            return hasher.hexdigest()

        resolved = sorted(Path(p).resolve() for p in target_files)
        for p in resolved:
            hasher.update(str(p).encode("utf-8"))
            if p.exists() and p.is_file():
                hasher.update(p.read_bytes())
            else:
                hasher.update(b"<MISSING>")
        return hasher.hexdigest()

    @staticmethod
    def _compute_record_hash(record_dict: Dict[str, Any]) -> str:
        """Calcola l'hash SHA-256 canonico di un record telemetrico."""
        payload = {k: v for k, v in record_dict.items() if k != "record_hash"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _get_last_telemetry_hash(self) -> str:
        """Legge l'ultimo record_hash dal file rsi_telemetry.jsonl."""
        if not self.telemetry_path.exists():
            return "0" * 64
        last_hash = "0" * 64
        try:
            with open(self.telemetry_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    last_hash = data.get("record_hash", last_hash)
        except Exception:
            pass
        return last_hash

    def append_telemetry_record(self, record: RSIIterationRecord) -> RSIIterationRecord:
        """Aggiunge in modo thread-safe un record alla catena SHA-256 (Guardia G4, OPT-9)."""
        with _TELEMETRY_LOCK:
            self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            prev_hash = self._get_last_telemetry_hash()
            rec_dict = record.model_dump()
            rec_dict["prev_hash"] = prev_hash
            rec_hash = self._compute_record_hash(rec_dict)
            rec_dict["record_hash"] = rec_hash

            signed_record = RSIIterationRecord.model_validate(rec_dict)
            with open(self.telemetry_path, "a", encoding="utf-8") as f:
                f.write(signed_record.model_dump_json() + "\n")
                f.flush()
            return signed_record

    def verify_telemetry_chain(
        self, telemetry_path: Optional[Path] = None
    ) -> Tuple[bool, int, str]:
        """Verifica l'integrita crittografica della catena SHA-256 in rsi_telemetry.jsonl."""
        target = Path(telemetry_path) if telemetry_path else self.telemetry_path
        if not target.exists():
            return True, 0, "Nessun file telemetrico presente."

        expected_prev = "0" * 64
        count = 0
        try:
            with open(target, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    actual_prev = data.get("prev_hash", "")
                    if actual_prev != expected_prev:
                        return (
                            False,
                            count,
                            f"Violazione catena alla riga {idx}: prev_hash non corrisponde.",
                        )
                    computed = self._compute_record_hash(data)
                    if data.get("record_hash", "") != computed:
                        return (
                            False,
                            count,
                            f"Violazione integrita alla riga {idx}: record_hash alterato.",
                        )
                    expected_prev = computed
                    count += 1
        except Exception as exc:
            return False, count, f"Errore lettura catena telemetrica: {exc}"

        return True, count, f"Catena SHA-256 integra ({count} record verificati)."

    def run_convergence_loop(
        self,
        evaluate_fn: Callable[[int], RSIDefectVector],
        refine_fn: Optional[Callable[[int, RSIDefectVector], bool]] = None,
        target_files: Optional[Sequence[Path | str]] = None,
        mode: str = "mode_a",
        session_id: Optional[str] = None,
        profile: str = "code_rsi",
    ) -> RSISessionReport:
        """Esegue il ciclo deterministico RSI applicando le guardie G1..G5."""
        sid = session_id or f"RSI-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        max_iter = self.get_max_iterations(mode)
        tracked_files = [Path(p).resolve() for p in (target_files or [])]

        history: List[RSIIterationRecord] = []
        visited_hashes: List[str] = []
        seen_hashes: Set[str] = set()
        rollbacks_count = 0
        cycle_detected = False

        # Valutazione iniziale (k = 0)
        init_defects = evaluate_fn(0)
        init_delta = self.compute_delta(init_defects, profile=profile)
        init_q = self.compute_fitness(init_defects, delta_k=init_delta, profile=profile)
        init_hash = self.compute_files_state_hash(tracked_files)
        visited_hashes.append(init_hash)
        seen_hashes.add(init_hash)

        init_verdict = (
            "CONVERGED_OPTIMAL"
            if (init_delta == 0 and init_q == 100.0)
            else "REFINING"
        )
        rec0 = self.append_telemetry_record(
            RSIIterationRecord(
                session_id=sid,
                iteration=0,
                mode=mode,
                defects=init_defects,
                delta_k=init_delta,
                fitness_q=init_q,
                state_hash=init_hash,
                verdict=init_verdict,
                rolled_back=False,
            )
        )
        history.append(rec0)

        # Guardia G1: stop immediato se gia convergente
        if init_delta == 0 and init_q == 100.0:
            return RSISessionReport(
                session_id=sid,
                mode=mode,
                max_iterations=max_iter,
                iterations_used=0,
                converged=True,
                final_status="CONVERGED_OPTIMAL",
                initial_delta=init_delta,
                final_delta=0,
                initial_fitness_q=init_q,
                final_fitness_q=100.0,
                rollbacks_count=0,
                cycle_detected=False,
                visited_hashes=visited_hashes,
                history=history,
            )

        best_defects = init_defects
        best_delta = init_delta
        best_q = init_q
        iterations_used = 0
        final_status = "MAX_ITERATIONS_REACHED"
        converged = False

        for k in range(1, max_iter + 1):
            iterations_used = k
            snap_id: Optional[str] = None
            if self.snapshot_mgr is not None and tracked_files:
                snap_id = self.snapshot_mgr.create_snapshot(tracked_files)

            if refine_fn is not None:
                refine_fn(k, best_defects)

            curr_hash = self.compute_files_state_hash(tracked_files)

            # Guardia G3: Anti-Oscillation Guard su cicli di stato SHA-256
            if tracked_files and curr_hash in seen_hashes:
                cycle_detected = True
                if snap_id and self.snapshot_mgr is not None:
                    self.snapshot_mgr.rollback(snap_id)
                    self.snapshot_mgr.cleanup(snap_id)
                rec_cycle = self.append_telemetry_record(
                    RSIIterationRecord(
                        session_id=sid,
                        iteration=k,
                        mode=mode,
                        defects=best_defects,
                        delta_k=best_delta,
                        fitness_q=best_q,
                        state_hash=curr_hash,
                        verdict="HALTED_CYCLE_DETECTED",
                        rolled_back=True,
                    )
                )
                history.append(rec_cycle)
                final_status = "HALTED_CYCLE_DETECTED"
                break

            visited_hashes.append(curr_hash)
            seen_hashes.add(curr_hash)

            curr_defects = evaluate_fn(k)
            curr_delta = self.compute_delta(curr_defects, profile=profile)
            curr_q = self.compute_fitness(
                curr_defects, delta_k=curr_delta, profile=profile
            )

            # Guardia G2: Strict Monotonic Hard Gate
            regressed, _ = self.check_hard_gate_regression(best_defects, curr_defects)
            if regressed:
                rollbacks_count += 1
                if snap_id and self.snapshot_mgr is not None:
                    self.snapshot_mgr.rollback(snap_id)
                    self.snapshot_mgr.cleanup(snap_id)
                rec_rb = self.append_telemetry_record(
                    RSIIterationRecord(
                        session_id=sid,
                        iteration=k,
                        mode=mode,
                        defects=curr_defects,
                        delta_k=curr_delta,
                        fitness_q=curr_q,
                        state_hash=curr_hash,
                        verdict="ROLLED_BACK_HARD_GATE",
                        rolled_back=True,
                    )
                )
                history.append(rec_rb)
                final_status = "ROLLED_BACK_HARD_GATE"
                continue

            if snap_id and self.snapshot_mgr is not None:
                self.snapshot_mgr.cleanup(snap_id)

            best_defects = curr_defects
            best_delta = curr_delta
            best_q = curr_q

            if curr_delta == 0 and curr_q == 100.0:
                verdict = "CONVERGED_OPTIMAL"
                converged = True
                final_status = "CONVERGED_OPTIMAL"
            else:
                verdict = "REFINING"

            rec_k = self.append_telemetry_record(
                RSIIterationRecord(
                    session_id=sid,
                    iteration=k,
                    mode=mode,
                    defects=curr_defects,
                    delta_k=curr_delta,
                    fitness_q=curr_q,
                    state_hash=curr_hash,
                    verdict=verdict,
                    rolled_back=False,
                )
            )
            history.append(rec_k)

            if converged:
                break

        return RSISessionReport(
            session_id=sid,
            mode=mode,
            max_iterations=max_iter,
            iterations_used=iterations_used,
            converged=converged,
            final_status=final_status,
            initial_delta=init_delta,
            final_delta=best_delta,
            initial_fitness_q=init_q,
            final_fitness_q=best_q,
            rollbacks_count=rollbacks_count,
            cycle_detected=cycle_detected,
            visited_hashes=visited_hashes,
            history=history,
        )

    def _resolve_candidate(self, root: Path, rel_path: str) -> Path:
        """Risolve un file dando priorita a .staging/ se presente."""
        staging_cand = root / ".staging" / rel_path
        if staging_cand.exists():
            return staging_cand
        direct_cand = root / rel_path
        if direct_cand.exists():
            return direct_cand
        if root.name == ".staging":
            parent_cand = root.parent / rel_path
            if parent_cand.exists():
                return parent_cand
        return direct_cand

    def _extract_script_supported_flags(self, script_path: Path) -> Set[str]:
        """Estrae i flag CLI --flag supportati nell'AST di uno script Python."""
        ignored_external = {"--porcelain", "--tb=short", "--version"}
        flags: Set[str] = {"--help"}
        if not script_path.exists():
            return flags
        try:
            source = script_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    val = node.value.strip()
                    if (
                        val.startswith("--")
                        and val not in ignored_external
                        and re.match(r"^--[a-zA-Z0-9][a-zA-Z0-9_-]*$", val)
                    ):
                        flags.add(val)
        except Exception:
            pass
        return flags

    def verify_cli_flags_cove(self, root_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Verifica che i flag CLI citati nei file Markdown siano definiti negli script Python (EXT-07)."""
        root = Path(root_dir).resolve() if root_dir else self.workspace_root
        invalid_flags: List[str] = []
        checked_invocations = 0

        agents_dir = self._resolve_candidate(root, ".agents")
        md_files: List[Path] = []
        if agents_dir.exists() and agents_dir.is_dir():
            md_files.extend(sorted(agents_dir.rglob("*.md")))
            stg_agents = root / ".staging" / ".agents"
            if stg_agents.exists() and stg_agents != agents_dir:
                stg_map = {
                    p.relative_to(stg_agents).as_posix(): p
                    for p in stg_agents.rglob("*.md")
                }
                merged: List[Path] = []
                for p in md_files:
                    rel = p.relative_to(agents_dir).as_posix()
                    merged.append(stg_map.pop(rel, p))
                merged.extend(stg_map.values())
                md_files = sorted(merged)
        else:
            md_files.extend(
                sorted(
                    p
                    for p in root.rglob("*.md")
                    if not _is_excluded_rel_path(p, root)
                )
            )

        flag_cache: Dict[str, Set[str]] = {}
        pattern = re.compile(r"scripts/([a-zA-Z0-9_]+\.py)\s+([^\r\n`'\"]*)")

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for match in pattern.finditer(content):
                script_name = match.group(1)
                args_tail = match.group(2)
                cited_flags = re.findall(
                    r"(?<!\w)(--[a-zA-Z0-9][a-zA-Z0-9_-]*)", args_tail
                )
                if not cited_flags:
                    continue

                if script_name not in flag_cache:
                    cand_script = self._resolve_candidate(root, f"scripts/{script_name}")
                    if not cand_script.exists():
                        cand_script = self._resolve_candidate(
                            self.workspace_root, f"scripts/{script_name}"
                        )
                    flag_cache[script_name] = self._extract_script_supported_flags(
                        cand_script
                    )

                supported = flag_cache[script_name]
                if len(supported) <= 1:
                    continue

                for fl in cited_flags:
                    checked_invocations += 1
                    if fl not in supported:
                        invalid_flags.append(f"{md_file.name}: {script_name} {fl}")

        return {
            "passed": len(invalid_flags) == 0,
            "checked_flags_count": checked_invocations,
            "invalid_flags": invalid_flags,
        }

    def run_vibe_check(
        self,
        target_path: Path | str,
        profile: str = "vibe_sprint_micro_rsi",
    ) -> Dict[str, Any]:
        """Esegue il micro-loop Vibe Check in-memory in meno di 500 ms (EXT-05)."""
        t0 = time.perf_counter()
        target = Path(target_path).resolve()
        active_profile = RSIProfileRegistry.get(profile).name
        violations: List[str] = []
        sast_count = 0
        contract_count = 0
        drift_count = 0

        if not target.exists():
            return {
                "status": "REFINING",
                "passed": False,
                "profile": active_profile,
                "target": str(target),
                "delta_k": 10,
                "fitness_q": 71.4286,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "violations": [f"Target non trovato: {target}"],
            }

        vibe_excluded = EXCLUDED_SCAN_DIRS - {".staging"}
        if target.is_file():
            files_to_check: List[Path] = [target]
        elif (target == self.root or target == _workspace_root) and (
            (target / ".agents").exists() or (target / ".staging").exists()
        ):
            roots_to_scan: List[Path] = []
            if (target / ".agents").exists():
                roots_to_scan.append(target / ".agents")
            if (target / ".staging").exists():
                roots_to_scan.append(target / ".staging")
            collected: List[Path] = []
            for s_root in roots_to_scan:
                collected.extend(
                    p
                    for p in s_root.rglob("*")
                    if p.is_file()
                    and p.suffix in (".py", ".md")
                    and not any(
                        part in vibe_excluded for part in p.relative_to(s_root).parts
                    )
                )
            files_to_check = sorted(list(dict.fromkeys(collected)))
        else:
            files_to_check = sorted(
                [
                    p
                    for p in target.rglob("*")
                    if p.is_file()
                    and p.suffix in (".py", ".md")
                    and not any(
                        part in vibe_excluded for part in p.relative_to(target).parts
                    )
                ]
            )

        for fpath in files_to_check:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                contract_count += 1
                violations.append(f"{fpath.name}: Errore lettura file ({exc})")
                continue

            if fpath.suffix == ".py":
                if ASTGuardValidator is not None:
                    rep = ASTGuardValidator.validate_code_edit(
                        text, text, target_file=fpath.name
                    )
                    if not rep.is_valid:
                        sast_in_rep = int(rep.metrics.get("sast_violations_count", 0))
                        sast_count += sast_in_rep
                        contract_count += max(0, len(rep.violations) - sast_in_rep)
                        for v in rep.violations:
                            violations.append(f"{fpath.name}: {v.message}")
                else:
                    try:
                        ast.parse(text)
                    except SyntaxError as se:
                        contract_count += 1
                        violations.append(f"{fpath.name}: SyntaxError ({se.msg})")
            elif fpath.suffix == ".md":
                ste = verify_ste100_compliance(text, max_sentence_words=20)
                if not ste["passed"]:
                    drift_count += ste["violations_count"]
                    for sv in ste["violations"][:3]:
                        violations.append(f"{fpath.name}: {sv}")

        defects = RSIDefectVector(
            sast_critical=sast_count,
            tests_failed=0,
            tests_passed=100,
            tests_total=100,
            contract_violations=contract_count,
            doc_drift=drift_count,
        )
        d_k = compute_delta(defects, profile=active_profile)
        q_k = compute_fitness(defects, delta_k=d_k, profile=active_profile)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        passed = d_k == 0 and len(violations) == 0

        return {
            "status": "CONVERGED_OPTIMAL" if passed else "REFINING",
            "passed": passed,
            "profile": active_profile,
            "target": str(target),
            "delta_0": d_k,
            "delta_k": d_k,
            "fitness_q": q_k,
            "elapsed_ms": elapsed_ms,
            "violations": violations,
        }

    def run_benchmark_suite(
        self, benchmark_suite: Path | str, root_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Esegue una suite Pytest di benchmark funzionale e restituisce i conteggi."""
        base_root = Path(root_dir).resolve() if root_dir else self.workspace_root
        suite_path = Path(benchmark_suite)
        if not suite_path.is_absolute():
            cand = base_root / suite_path
            suite_path = (
                cand.resolve()
                if cand.exists()
                else (self.workspace_root / suite_path).resolve()
            )

        if not suite_path.exists():
            return {
                "passed": False,
                "tests_failed": 1,
                "tests_passed": 0,
                "tests_total": 1,
                "suite_path": str(suite_path),
                "details": f"Benchmark suite non trovata: {suite_path}",
            }

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite_path), "-q", "--tb=short"],
                cwd=str(base_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            combined = f"{proc.stdout}\n{proc.stderr}"
            m_fail = re.search(r"(\d+)\s+failed", combined)
            m_err = re.search(r"(\d+)\s+error", combined)
            m_pass = re.search(r"(\d+)\s+passed", combined)

            t_fail = (int(m_fail.group(1)) if m_fail else 0) + (
                int(m_err.group(1)) if m_err else 0
            )
            t_pass = int(m_pass.group(1)) if m_pass else 0
            if proc.returncode != 0 and t_fail == 0:
                t_fail = 1
            if proc.returncode == 0 and t_pass == 0:
                t_pass = 1
            t_total = max(1, t_pass + t_fail)

            return {
                "passed": t_fail == 0 and proc.returncode == 0,
                "tests_failed": t_fail,
                "tests_passed": t_pass,
                "tests_total": t_total,
                "suite_path": str(suite_path),
                "details": f"Benchmark pytest: {t_pass} passed, {t_fail} failed.",
            }
        except Exception as exc:
            return {
                "passed": False,
                "tests_failed": 1,
                "tests_passed": 0,
                "tests_total": 1,
                "suite_path": str(suite_path),
                "details": f"Errore esecuzione benchmark suite: {exc}",
            }

    def verify_ecosystem(
        self,
        root_dir: Optional[Path] = None,
        run_pytest: bool = False,
        profile: str = "code_rsi",
        benchmark_suite: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Esegue la verifica completa Guardia G6 sull'ecosistema o directory target."""
        if isinstance(root_dir, bool):
            should_run_pytest = root_dir or bool(run_pytest)
            root = self.workspace_root
        else:
            should_run_pytest = bool(run_pytest)
            root = Path(root_dir).resolve() if root_dir else self.workspace_root

        canonical_profile = RSIProfileRegistry.get(profile).name
        violations: List[str] = []
        checks: Dict[str, Any] = {}

        # 1. Verifica integrita AGENTS.md e budget di byte
        agents_md = self._resolve_candidate(root, ".agents/AGENTS.md")
        anti_crash_md = self._resolve_candidate(
            root, ".agents/rules/anti_crash_rules.md"
        )

        if agents_md.exists():
            agents_bytes = agents_md.stat().st_size
            crash_bytes = (
                anti_crash_md.stat().st_size if anti_crash_md.exists() else 0
            )
            combined_bytes = agents_bytes + crash_bytes
            budget_ok = agents_bytes < 24000
            if not budget_ok:
                violations.append(
                    f"AGENTS.md supera il limite di 24000 byte ({agents_bytes} B)."
                )

            agents_text = agents_md.read_text(encoding="utf-8", errors="replace")
            ste_res = verify_ste100_compliance(agents_text)
            if "[RULE-STE100]" in agents_text and not ste_res["passed"]:
                violations.extend(ste_res["violations"][:5])

            checks["agents_md"] = {
                "passed": budget_ok
                and (ste_res["passed"] or "[RULE-STE100]" not in agents_text),
                "agents_bytes": agents_bytes,
                "combined_bytes": combined_bytes,
                "ste100_passed": ste_res["passed"],
            }

        # 2. Verifica link ausiliari nelle Skill o file Markdown in directory di test
        skills_dir = self._resolve_candidate(root, ".agents/skills")
        broken_links: List[str] = []
        ste100_issues: List[str] = []

        if skills_dir.exists() and skills_dir.is_dir():
            for skill_folder in sorted(skills_dir.iterdir()):
                if not skill_folder.is_dir():
                    continue
                skill_md = self._resolve_candidate(
                    root, f".agents/skills/{skill_folder.name}/SKILL.md"
                )
                if not skill_md.exists():
                    continue
                content = skill_md.read_text(encoding="utf-8", errors="replace")
                if "v3.0.0" in content or "v3.1.0" in content or "v3.2.0" in content:
                    ste_skill = verify_ste100_compliance(content)
                    if not ste_skill["passed"]:
                        ste100_issues.extend(
                            f"{skill_folder.name}: {v}"
                            for v in ste_skill["violations"][:2]
                        )
                for m in re.finditer(
                    r"\]\(((?:resources|references)/[^\)]+)\)", content
                ):
                    rel_link = m.group(1)
                    target_aux = self._resolve_candidate(
                        root, f".agents/skills/{skill_folder.name}/{rel_link}"
                    )
                    if not target_aux.exists():
                        broken_links.append(f"{skill_folder.name}/{rel_link}")
        else:
            # Directory esterna o temporanea: esclude EXCLUDED_SCAN_DIRS (OPT-9) e filtra STE100 (OPT-2)
            for md_file in root.rglob("*.md"):
                if _is_excluded_rel_path(md_file, root):
                    continue
                content = md_file.read_text(encoding="utf-8", errors="replace")
                has_nk_marker = (
                    ".agents" in md_file.parts
                    or md_file.name == "SKILL.md"
                    or ".agents" in content
                    or "SKILL.md" in content
                    or "[RULE-STE100]" in content
                )
                if canonical_profile in ("ste100_rsi", "spec_rsi") or has_nk_marker:
                    ste_md = verify_ste100_compliance(content)
                    if not ste_md["passed"]:
                        ste100_issues.extend(
                            f"{md_file.name}: {v}" for v in ste_md["violations"]
                        )
                for m in re.finditer(r"\]\(([^\)]+)\)", content):
                    link_target = m.group(1)
                    if link_target.startswith(
                        (
                            "http://",
                            "https://",
                            "file://",
                            "#",
                            "conversation://",
                            "mailto:",
                        )
                    ):
                        continue
                    if not (md_file.parent / link_target).exists():
                        broken_links.append(f"{md_file.name} -> {link_target}")

        if broken_links:
            violations.append(f"Link ausiliari interrotti: {broken_links}")
        if ste100_issues:
            violations.extend(ste100_issues)

        checks["skills_and_markdown"] = {
            "passed": len(broken_links) == 0 and len(ste100_issues) == 0,
            "broken_links": broken_links,
            "ste100_issues": ste100_issues,
        }

        # 3. Verifica CoVe CLI AST Gate sui flag --flag citati nei Markdown (EXT-07)
        cove_res = self.verify_cli_flags_cove(root)
        checks["cli_flags_cove"] = cove_res
        if not cove_res["passed"]:
            violations.extend(
                f"Flag CLI non valido: {inv}" for inv in cove_res["invalid_flags"]
            )

        # 4. Verifica catena telemetrica se presente
        telemetry_file = self._resolve_candidate(root, "nk_tracking/rsi_telemetry.jsonl")
        chain_ok, chain_count, chain_msg = self.verify_telemetry_chain(telemetry_file)
        if not chain_ok:
            violations.append(chain_msg)
        checks["telemetry_chain"] = {
            "passed": chain_ok,
            "records_verified": chain_count,
            "details": chain_msg,
        }

        # 5. Esegue eventuale suite di benchmark funzionale o pytest se richiesto
        bench_failed = 0
        bench_passed = 100
        bench_total = 100
        if benchmark_suite or should_run_pytest:
            target_suite = benchmark_suite if benchmark_suite else str(root / "tests")
            bench_res = self.run_benchmark_suite(target_suite, root_dir=root)
            checks["benchmark_suite"] = bench_res
            bench_failed = int(bench_res["tests_failed"])
            bench_passed = int(bench_res["tests_passed"])
            bench_total = int(bench_res["tests_total"])
            if not bench_res["passed"]:
                violations.append(bench_res["details"])

        defects = RSIDefectVector(
            tests_failed=bench_failed,
            tests_passed=bench_passed,
            tests_total=bench_total,
            contract_violations=len(broken_links)
            + len(cove_res["invalid_flags"])
            + (0 if chain_ok else 1),
            doc_drift=len(ste100_issues),
        )
        delta_k = self.compute_delta(defects, profile=canonical_profile)
        fitness_q = self.compute_fitness(
            defects, delta_k=delta_k, profile=canonical_profile
        )
        passed = len(violations) == 0 and delta_k == 0

        return {
            "status": "CONVERGED_OPTIMAL" if passed else "REFINING",
            "passed": passed,
            "profile": canonical_profile,
            "delta_k": delta_k,
            "fitness_q": fitness_q,
            "checks": checks,
            "violations": violations,
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point CLI per il motore di convergenza RSI."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Motore di Convergenza RSI Nexus Keystone v3.2.0-Tensor-RSI"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Esegue la verifica completa Guardia G6 sull'ecosistema",
    )
    parser.add_argument(
        "--vibe-check",
        nargs="?",
        const=".",
        type=str,
        default=None,
        help="Esegue il micro-loop Vibe Check (<500ms) sul file o directory target",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="code_rsi",
        help="Profilo Tensor-RSI attivo (code_rsi, vibe_sprint_micro_rsi, spec_rsi, ui_ux_rsi, ste100_rsi)",
    )
    parser.add_argument(
        "--benchmark-suite",
        type=str,
        default=None,
        help="Percorso opzionale a file o cartella pytest di benchmark funzionale",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice da verificare",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )

    args = parser.parse_args(argv)
    root_path = Path(args.root).resolve() if args.root else _workspace_root
    engine = RSIConvergenceEngine(workspace_root=root_path, root=root_path)

    if args.vibe_check:
        vibe_profile = (
            args.profile if args.profile != "code_rsi" else "vibe_sprint_micro_rsi"
        )
        if args.vibe_check == ".":
            agents_cand = (
                root_path / ".staging" / ".agents"
                if (root_path / ".staging" / ".agents").exists()
                else (
                    root_path / ".agents"
                    if (root_path / ".agents").exists()
                    else root_path
                )
            )
            vibe_target = str(agents_cand)
        else:
            vibe_target = args.vibe_check
        vibe_res = engine.run_vibe_check(vibe_target, profile=vibe_profile)
        if args.json:
            print(json.dumps(vibe_res, indent=2))
        else:
            sym = "🟢" if vibe_res["passed"] else "🔴"
            print(
                f"{sym} [RSI-VIBE-CHECK] Stato: {vibe_res['status']} | Delta: {vibe_res['delta_k']} | Q: {vibe_res['fitness_q']} ({vibe_res['elapsed_ms']} ms)"
            )
            for v in vibe_res["violations"]:
                print(f"  - {v}")
        return 0 if vibe_res["passed"] else 1

    res = engine.verify_ecosystem(
        root_dir=root_path,
        run_pytest=False,
        profile=args.profile,
        benchmark_suite=args.benchmark_suite,
    )
    if args.json or not args.verify:
        print(json.dumps(res, indent=2))
    else:
        sym = "🟢" if res["passed"] else "🔴"
        print(
            f"{sym} [RSI-VERIFY] Stato: {res['status']} | Profilo: {res['profile']} | Delta: {res['delta_k']} | Q: {res['fitness_q']}"
        )
        for v in res["violations"]:
            print(f"  - {v}")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
