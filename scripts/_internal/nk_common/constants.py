# -*- coding: utf-8 -*-
"""Costanti condivise pure stdlib per i gate di NK Hub Generation 1.0.0-Generation."""

from __future__ import annotations

from typing import Tuple

VERSION: str = "1.0.0-Generation"
DEFAULT_MILESTONE_ID: str = "NK-GEN-1.0.0"

SUPPORTED_MODEL_PROFILES: Tuple[str, ...] = (
    "generation",
    "carbon",
    "argon",
    "standard",
)

HIGH_CAPACITY_PROFILES: Tuple[str, ...] = (
    "generation",
    "carbon",
    "argon",
)

LEGACY_ONBOARDING_TRIGGERS: Tuple[str, ...] = (
    "avvia ambiente nk",
    "avvia nk hub",
    "avvia nk",
    "avvia hub",
    "start nk",
    "start hub",
    "attiva nk",
    "attiva ambiente nk",
)

GENERATION_ONBOARDING_TRIGGERS: Tuple[str, ...] = (
    "avvia generation",
    "avvia nk generation",
    "avvia nk hub generation",
    "avvia ambiente generation",
    "start generation",
    "start nk generation",
    "attiva generation",
    "attiva ambiente generation",
)

ONBOARDING_TRIGGERS: Tuple[str, ...] = (
    LEGACY_ONBOARDING_TRIGGERS + GENERATION_ONBOARDING_TRIGGERS
)

HALLUCINATED_SCRIPT_DENYLIST: Tuple[str, ...] = (
    "atomic_2pc_commit.py",
    "nk_2pc_promoter.py",
    "nk_2pc_commit.py",
    "nk_ast_guard.py",
    "nk_ast_mapper.py",
    "nk_memory_engine.py",
    "nk_memory_compactor.py",
    "nk_oracle_lock.py",
    "nk_quality_ratchet.py",
    "nk_rsi_engine.py",
    "nk_sbfl_engine.py",
    "nk_sast_scanner.py",
    "nk_dast_runner.py",
    "nk_prompt_linter.py",
    "nk_ste100_validator.py",
    "nk_mutation_runner.py",
    "agent_Context_Rot_Sentinel.py",
    "bootstrap_nk_hub_scaffold.py",
    "context_pruner.py",
    "generate_golden_tests.py",
    "goal_checkpoint_engine.py",
    "knowledge_graph_engine.py",
    "micro_ui_hud_renderer.py",
    "nk_Dag_Orchestrator.py",
    "nk_genome_validator.py",
    "nk_git_Engine.py",
    "nk_ipc_pointer_engine.py",
    "nk_Mutation_Scorer.py",
    "nk_Prompt_Gate.py",
    "owasp_sast_scanner.py",
    "sbfl_ochiai_localizer.py",
    "telemetry_logger.py",
)
