"""Classe canonica VibeSprintRouter e wrapper pubblici di modulo."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.lane_paths import resolve_staging_dir
from _internal.vibe_sprint_router.ast_risk_and_capsule import (
    compute_ast_risk_score_impl,
    diff_changed_lines_impl,
    estimate_changed_loc_impl,
    format_compact_env_capsule_impl,
    generate_env_capsule_impl,
    generate_inline_micro_spec_impl,
    load_prewarmed_capsule_impl,
    validate_generated_prompt_impl,
)
from _internal.vibe_sprint_router.constants_core import (
    MODE_D_KEYWORDS,
    _DEFAULT_WORKSPACE_ROOT,
)
from _internal.vibe_sprint_router.domain_matcher import (
    load_registry_manifest_impl,
    resolve_domain_from_manifest_impl,
)
from _internal.vibe_sprint_router.envelope_builder import (
    build_meta_prompt_envelope_impl,
    evaluate_meta_prompt_gate_impl,
)
from _internal.vibe_sprint_router.intent_classifier import classify_prompt_intent_impl
from _internal.vibe_sprint_router.stt_normalize import (
    format_meta_prompt_markdown_impl,
    is_gate_exempt_impl,
    is_passive_state_handoff_impl,
    normalize_voice_stt_input_impl,
    resolve_intrinsic_vibe_protocols_impl,
)


def _facade_workspace_root() -> Path:
    for mod_name in ("vibe_sprint_router", "scripts.vibe_sprint_router"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "_DEFAULT_WORKSPACE_ROOT"):
            val = getattr(mod, "_DEFAULT_WORKSPACE_ROOT")
            if isinstance(val, Path):
                return val
    return _DEFAULT_WORKSPACE_ROOT


def _attach_intent_track_metadata(res: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    from _internal.vibe_sprint_router.intent_track_classifier import (
        classify_intent_track,
        resolve_intent_track_profile,
    )
    eff_text = str(res.get("optimized_meta_prompt") or prompt)
    track = "CONTROL" if (res.get("recommended_mode") == "mode_d" and res.get("bypassed")) else classify_intent_track(eff_text)
    res.setdefault("classified_track", track)
    res.setdefault("intent_track", track)
    res.setdefault("rsi_profile", resolve_intent_track_profile(track))
    return res


class VibeSprintRouter:
    """Valuta il rischio strutturale AST e seleziona la modalita operativa (Mode A, B, C o D)."""

    MODE_C_MAX_LOC: int = 150
    MODE_C_MAX_PROMPT_CHARS: int = 400
    DISCOVERY_KEYWORDS: Tuple[str, ...] = MODE_D_KEYWORDS

    def __init__(
        self, workspace_root: Optional[Path] = None, lane_id: Optional[str] = None
    ) -> None:
        if workspace_root is None:
            self.workspace_root = _facade_workspace_root()
        else:
            self.workspace_root = Path(workspace_root).resolve()
        self.staging_dir, self.lane_id = resolve_staging_dir(
            self.workspace_root, lane_id=lane_id
        )

    def _load_registry_manifest(self) -> Dict[str, Any]:
        """Carica nk_registry_manifest.json da staging o root con cache statica O(1)."""
        return load_registry_manifest_impl(self)

    def is_passive_state_handoff(self, raw_prompt: str) -> bool:
        """Verifica se il prompt e un handoff di stato passivo o standby autenticato."""
        return is_passive_state_handoff_impl(self, raw_prompt)

    def resolve_intrinsic_vibe_protocols(
        self, prompt: str, recommended_mode: str = "mode_c"
    ) -> Dict[str, Any]:
        """Rileva trigger semantici naturali e restituisce i protocolli intrinseci equivalenti (/goal, /boost, /plan)."""
        return resolve_intrinsic_vibe_protocols_impl(self, prompt, recommended_mode=recommended_mode)

    def normalize_voice_stt_input(self, raw_prompt: str) -> Dict[str, Any]:
        """Normalizza prompt grezzi da dettatura vocale (STT), rimuovendo auto-correzioni e refusi tecnici."""
        return normalize_voice_stt_input_impl(self, raw_prompt)

    def is_gate_exempt(self, raw_prompt: str) -> bool:
        """Verifica esenzioni deterministiche anti-loop per il Meta-Prompt Gate di Livello 0."""
        return is_gate_exempt_impl(self, raw_prompt)

    def evaluate_meta_prompt_gate(self, raw_prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Valuta il Gate L0 sul prompt fornito delegando a build_meta_prompt_envelope."""
        return evaluate_meta_prompt_gate_impl(self, raw_prompt, **kwargs)

    def build_meta_prompt_envelope(
        self,
        prompt: str,
        gate_enabled: bool = True,
        gate_mode: str = "CONFIRM",
        files: Optional[List[str]] = None,
        compact: bool = False,
        auto_bypass_readonly: bool = True,
        mode: Optional[str] = None,
        changed_lines: Optional[int] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Costruisce e valida il contratto MetaPromptGateContract di Livello 0 con IntentTrack."""
        res = build_meta_prompt_envelope_impl(
            self,
            prompt,
            gate_enabled=gate_enabled,
            gate_mode=gate_mode,
            files=files,
            compact=compact,
            auto_bypass_readonly=auto_bypass_readonly,
            mode=mode,
            changed_lines=changed_lines,
            conversation_id=conversation_id,
        )
        return _attach_intent_track_metadata(res, prompt)

    def format_meta_prompt_markdown(self, envelope: Dict[str, Any]) -> str:
        """Formatta il blocco Markdown visibile di Livello 0 per il campo content prima di ask_question."""
        return format_meta_prompt_markdown_impl(self, envelope)

    def resolve_domain_from_manifest(self, prompt: str) -> Dict[str, Any]:
        """Risolve il dominio, l'agente e il sub-agente dal manifesto in O(1) con regole granulari."""
        return resolve_domain_from_manifest_impl(self, prompt)

    @staticmethod
    def _diff_changed_lines(prod_lines: List[str], staged_lines: List[str]) -> int:
        """Conta le righe realmente inserite/sostituite rispetto al file in produzione."""
        return diff_changed_lines_impl(prod_lines, staged_lines)

    def _estimate_changed_loc(
        self, files: Optional[List[str]] = None, changed_lines: Optional[int] = None
    ) -> Optional[int]:
        """Stima il delta LOC effettivo per file staged rispetto alla produzione."""
        return estimate_changed_loc_impl(self, files=files, changed_lines=changed_lines)

    def classify_prompt_intent(
        self,
        prompt: str,
        files: Optional[List[str]] = None,
        changed_lines: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Classifica il prompt per decidere Mode D, selezione nodi dashboard o routing Mode A/B/C."""
        return classify_prompt_intent_impl(
            self, prompt, files=files, changed_lines=changed_lines, mode=mode
        )

    def validate_generated_prompt(self, file_or_text: str, mode: str = "auto") -> Dict[str, Any]:
        """Valida un prompt generato (file o testo inline) contro gli anti-pattern AP-1..AP-13."""
        return validate_generated_prompt_impl(self, file_or_text, mode=mode)

    def compute_ast_risk_score(self, source_code: str, filename: str = "") -> Dict[str, Any]:
        """Analizza il codice Python via AST e determina l'idoneita Mode C."""
        return compute_ast_risk_score_impl(self, source_code, filename=filename)

    def generate_inline_micro_spec(
        self, target_file: str, change_intent: str, risk_info: Dict[str, Any]
    ) -> str:
        """Genera una Micro-Spec inline a zero burocrazia per Mode C."""
        return generate_inline_micro_spec_impl(self, target_file, change_intent, risk_info)

    def load_prewarmed_capsule(self, compact: bool = False) -> Dict[str, Any]:
        """Carica la capsula di memoria Tier-1 pre-riscaldata."""
        return load_prewarmed_capsule_impl(self, compact=compact)

    def format_compact_env_capsule(self) -> str:
        """Restituisce il blocco <env_capsule> compatto da includere negli handoff."""
        return format_compact_env_capsule_impl(self)

    def generate_env_capsule(self) -> str:
        """Alias pubblico per formattare il blocco <env_capsule> anti-stallo."""
        return generate_env_capsule_impl(self)


def resolve_domain_from_manifest(prompt: str, workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Funzione helper di modulo per risolvere il dominio O(1) dal manifesto SSOT."""
    return VibeSprintRouter(workspace_root=workspace_root).resolve_domain_from_manifest(prompt=prompt)


def resolve_intrinsic_vibe_protocols(
    prompt: str, recommended_mode: str = "mode_c", workspace_root: Optional[Path] = None
) -> Dict[str, Any]:
    """Funzione helper di modulo per risolvere i protocolli intrinseci /goal, /boost e /plan."""
    return VibeSprintRouter(workspace_root=workspace_root).resolve_intrinsic_vibe_protocols(
        prompt=prompt, recommended_mode=recommended_mode
    )


def classify_prompt_intent(
    prompt: str, files: Optional[List[str]] = None, workspace_root: Optional[Path] = None,
    changed_lines: Optional[int] = None, mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per classificare l'intento del prompt (Mode D vs A/B/C)."""
    return VibeSprintRouter(workspace_root=workspace_root).classify_prompt_intent(
        prompt=prompt, files=files, changed_lines=changed_lines, mode=mode
    )


def normalize_voice_stt_input(raw_prompt: str, workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Funzione helper di modulo per normalizzare l'input vocale STT."""
    return VibeSprintRouter(workspace_root=workspace_root).normalize_voice_stt_input(raw_prompt=raw_prompt)


def is_gate_exempt(raw_prompt: str, workspace_root: Optional[Path] = None) -> bool:
    """Funzione helper di modulo per verificare le esenzioni anti-loop."""
    return VibeSprintRouter(workspace_root=workspace_root).is_gate_exempt(raw_prompt=raw_prompt)


def build_meta_prompt_envelope(
    prompt: str,
    gate_enabled: bool = True,
    gate_mode: str = "CONFIRM",
    files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
    compact: bool = False,
    auto_bypass_readonly: bool = True,
    mode: Optional[str] = None,
    changed_lines: Optional[int] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per costruire il contratto MetaPromptGateContract."""
    return VibeSprintRouter(workspace_root=workspace_root).build_meta_prompt_envelope(
        prompt=prompt,
        gate_enabled=gate_enabled,
        gate_mode=gate_mode,
        files=files,
        compact=compact,
        auto_bypass_readonly=auto_bypass_readonly,
        mode=mode,
        changed_lines=changed_lines,
        conversation_id=conversation_id,
    )


def evaluate_meta_prompt_gate(
    raw_prompt: str, workspace_root: Optional[Path] = None, **kwargs: Any
) -> Dict[str, Any]:
    """Funzione helper di modulo per valutare il Gate L0 tramite build_meta_prompt_envelope."""
    return VibeSprintRouter(workspace_root=workspace_root).build_meta_prompt_envelope(
        prompt=raw_prompt, **kwargs
    )


def format_meta_prompt_markdown(
    envelope: Dict[str, Any], workspace_root: Optional[Path] = None
) -> str:
    """Funzione helper di modulo per formattare il blocco Markdown visibile di Livello 0."""
    return VibeSprintRouter(workspace_root=workspace_root).format_meta_prompt_markdown(envelope=envelope)


def validate_generated_prompt(
    file_or_text: str, workspace_root: Optional[Path] = None, mode: str = "auto"
) -> Dict[str, Any]:
    """Funzione helper di modulo per validare un prompt contro gli anti-pattern AP-1..AP-13."""
    return VibeSprintRouter(workspace_root=workspace_root).validate_generated_prompt(
        file_or_text=file_or_text, mode=mode
    )


def load_prewarmed_capsule(
    workspace_root: Optional[Path] = None, compact: bool = False
) -> Dict[str, Any]:
    """Funzione helper di modulo per caricare la capsula Tier-1 pre-riscaldata."""
    return VibeSprintRouter(workspace_root=workspace_root).load_prewarmed_capsule(compact=compact)


def format_compact_env_capsule(workspace_root: Optional[Path] = None) -> str:
    """Funzione helper di modulo per formattare <env_capsule> deduplicato."""
    return VibeSprintRouter(workspace_root=workspace_root).format_compact_env_capsule()


def generate_env_capsule(workspace_root: Optional[Path] = None) -> str:
    """Alias di modulo per generare il blocco <env_capsule> anti-stallo."""
    return format_compact_env_capsule(workspace_root=workspace_root)
