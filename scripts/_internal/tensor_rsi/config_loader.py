# -*- coding: utf-8 -*-
"""Caricatore cached per nk_genome/configs/tensor_rsi/tensor_rsi_v3.json (DOM-01)."""

from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

_CONFIG_REL = Path("nk_genome/configs/tensor_rsi/tensor_rsi_v3.json")

_DEFAULT_V3_CONFIG: Dict[str, Any] = {
    "profiles": {
        "vibe_sprint_micro_rsi": {"profile_id": "P1", "intent_track": "CODE_TRACK", "intent_category": "MICRO_VIBE"},
        "code_rsi": {"profile_id": "P2", "intent_track": "CODE_TRACK", "intent_category": "CODE_BUILD"},
        "spec_rsi": {"profile_id": "P3", "intent_track": "DOC_TRACK", "intent_category": "SPEC_DOC"},
        "ui_ux_rsi": {"profile_id": "P4", "intent_track": "CODE_TRACK", "intent_category": "CODE_BUILD"},
        "ste100_rsi": {"profile_id": "P5", "intent_track": "DOC_TRACK", "intent_category": "SPEC_DOC"},
        "refactor_rsi": {"profile_id": "P6", "intent_track": "CODE_TRACK", "intent_category": "CODE_BUILD"},
    },
    "intent_tracks": {
        "CODE_TRACK": {"secondary_epsilon": [0.015, 0.015, 0.04, 0.02], "min_effect": 0.005, "hard_floors": {"min_kill_rate": 0.8, "min_branch_coverage": 0.82}},
        "DOC_TRACK": {"secondary_epsilon": [0.01, 0.02, 0.03, 0.005], "min_effect": 0.005, "hard_floors": {"min_kill_rate": 0.0, "min_branch_coverage": 0.0}},
    },
    "classified_track_weights": {
        "IMPROVEMENT": {"intent_track": "CODE_TRACK", "intent_category": "CODE_BUILD", "weights": [0.35, 0.35, 0.2, 0.1], "read_only": False},
        "OPTIMIZATION": {"intent_track": "CODE_TRACK", "intent_category": "CODE_BUILD", "weights": [0.2, 0.3, 0.4, 0.1], "read_only": False},
        "DOC_SPEC": {"intent_track": "DOC_TRACK", "intent_category": "SPEC_DOC", "weights": [0.15, 0.3, 0.15, 0.4], "read_only": False},
        "CONTROL": {"intent_track": "CODE_TRACK", "intent_category": "AUDIT_RO", "weights": [0.35, 0.35, 0.2, 0.1], "read_only": True},
    },
    "model_tiers": {
        "NEON": {"profiles": ["neon"], "tier1_token_cap": 1200, "high_capacity": True},
        "CARBON_GEN": {"profiles": ["generation", "carbon", "argon", "carbon_gen"], "tier1_token_cap": 1200, "high_capacity": True},
        "PRO": {"profiles": ["pro"], "tier1_token_cap": 1200, "high_capacity": True},
        "FLASH": {"profiles": ["flash"], "tier1_token_cap": 800, "high_capacity": False},
        "STANDARD": {"profiles": ["standard"], "tier1_token_cap": 350, "high_capacity": False},
    },
    "policy_matrix": {
        "Z0": {
            "NEON": {"max_in_context_branches": 3, "delegate_subagent_slices": False, "subagent_slice_token_cap": 1200, "max_subagent_fanout": 3, "max_rsi_iterations_code": 4, "max_rsi_iterations_micro": 2, "pytest_mode": "FULL_ISOLATED_COV", "recommend_compact": False, "halt_for_handoff": False},
            "CARBON_GEN": {"max_in_context_branches": 3, "delegate_subagent_slices": False, "subagent_slice_token_cap": 1200, "max_subagent_fanout": 3, "max_rsi_iterations_code": 4, "max_rsi_iterations_micro": 2, "pytest_mode": "FULL_ISOLATED_COV", "recommend_compact": False, "halt_for_handoff": False},
            "PRO": {"max_in_context_branches": 2, "delegate_subagent_slices": False, "subagent_slice_token_cap": 1200, "max_subagent_fanout": 2, "max_rsi_iterations_code": 3, "max_rsi_iterations_micro": 2, "pytest_mode": "FULL_ISOLATED_COV", "recommend_compact": False, "halt_for_handoff": False},
            "FLASH": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "subagent_slice_token_cap": 800, "max_subagent_fanout": 1, "max_rsi_iterations_code": 2, "max_rsi_iterations_micro": 1, "pytest_mode": "FAST_MARK_ISOLATED", "recommend_compact": False, "halt_for_handoff": False},
            "STANDARD": {"max_in_context_branches": 2, "delegate_subagent_slices": False, "subagent_slice_token_cap": 350, "max_subagent_fanout": 1, "max_rsi_iterations_code": 2, "max_rsi_iterations_micro": 1, "pytest_mode": "FULL_ISOLATED_COV", "recommend_compact": False, "halt_for_handoff": False},
        },
        "Z1": {
            "NEON": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "subagent_slice_token_cap": 1200, "max_subagent_fanout": 2, "max_rsi_iterations_code": 2, "max_rsi_iterations_micro": 1, "pytest_mode": "TARGETED_SLICE", "recommend_compact": False, "halt_for_handoff": False},
            "CARBON_GEN": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "subagent_slice_token_cap": 1200, "max_subagent_fanout": 2, "max_rsi_iterations_code": 2, "max_rsi_iterations_micro": 1, "pytest_mode": "TARGETED_SLICE", "recommend_compact": False, "halt_for_handoff": False},
            "PRO": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "subagent_slice_token_cap": 1200, "max_subagent_fanout": 2, "max_rsi_iterations_code": 2, "max_rsi_iterations_micro": 1, "pytest_mode": "TARGETED_SLICE", "recommend_compact": False, "halt_for_handoff": False},
            "FLASH": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "subagent_slice_token_cap": 800, "max_subagent_fanout": 1, "max_rsi_iterations_code": 1, "max_rsi_iterations_micro": 1, "pytest_mode": "TARGETED_SLICE", "recommend_compact": True, "halt_for_handoff": False},
            "STANDARD": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "subagent_slice_token_cap": 350, "max_subagent_fanout": 1, "max_rsi_iterations_code": 1, "max_rsi_iterations_micro": 1, "pytest_mode": "TARGETED_SLICE", "recommend_compact": True, "halt_for_handoff": False},
        },
        "Z2": {"DEFAULT": {"max_in_context_branches": 1, "delegate_subagent_slices": True, "max_subagent_fanout": 1, "max_rsi_iterations_code": 1, "max_rsi_iterations_micro": 0, "pytest_mode": "TARGETED_SLICE", "recommend_compact": True, "halt_for_handoff": False}},
        "Z3": {"DEFAULT": {"max_in_context_branches": 0, "delegate_subagent_slices": False, "max_subagent_fanout": 0, "max_rsi_iterations_code": 0, "max_rsi_iterations_micro": 0, "pytest_mode": "SKIP_READONLY", "recommend_compact": True, "halt_for_handoff": True}},
    },
    "macro_operators": [
        {"id": "O1", "name": "SURGICAL_LOCAL_PATCH", "tracks": ["CODE_TRACK"]},
        {"id": "O2", "name": "DECOMPOSITION_HELPER_EXTRACT", "tracks": ["CODE_TRACK"]},
        {"id": "O3", "name": "TEST_ORACLE_HARDENING", "tracks": ["CODE_TRACK"]},
        {"id": "O4", "name": "ISOLATED_SUBAGENT_SLICE", "tracks": ["CODE_TRACK"]},
        {"id": "OD", "name": "OP_DOC_ALIGN", "tracks": ["DOC_TRACK"]},
    ],
    "bandit": {"cold_max_n": 12, "warm_max_n": 30, "decay_gamma": 0.92, "prior_strength_m0": 4.0, "ucb_cold_c": 0.25, "brier_circuit_breaker": 0.25, "mae_circuit_breaker": 0.35, "pareto_archive_max": 12, "flaky_rerun_count": 3},
    "gate_rules": {
        "GATE_1_SCOPE": {"order": 1, "fail_closed": True}, "GATE_2_CODE_GROUNDING": {"order": 2, "fail_closed": True},
        "GATE_3_BRIEF_GROUNDING": {"order": 3, "fail_closed": True}, "GATE_4_PRESERVATION": {"order": 4, "fail_closed": True},
        "GATE_5_TRUTH_DAST": {"order": 5, "fail_closed": True}, "GATE_6_RSI_CONVERGENCE": {"order": 6, "fail_closed": True},
    },
}


@lru_cache(maxsize=8)
def _cached_read_v3(stg_str: str, stg_mtime: int, prod_str: str, prod_mtime: int) -> Dict[str, Any]:
    merged: Dict[str, Any] = copy.deepcopy(_DEFAULT_V3_CONFIG)
    for p_str in (prod_str, stg_str):
        p = Path(p_str)
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    merged.update(raw)
            except (OSError, UnicodeDecodeError, ValueError):
                pass
    return merged


def load_tensor_v3_config(workspace_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Carica con cache mtime tensor_rsi_v3.json preferendo .staging/."""
    if workspace_root is None:
        return copy.deepcopy(_DEFAULT_V3_CONFIG)
    root = Path(workspace_root).resolve()
    stg, prod = root / ".staging" / _CONFIG_REL, root / _CONFIG_REL
    stg_m = int(stg.stat().st_mtime_ns) if stg.is_file() else -1
    prod_m = int(prod.stat().st_mtime_ns) if prod.is_file() else -1
    return _cached_read_v3(str(stg), stg_m, str(prod), prod_m)


def resolve_profile_for_track(classified_track: str, workspace_root: Optional[Union[str, Path]] = None) -> str:
    """Risolve il profilo RSI coerente con profiles e classified_track_weights."""
    cfg = load_tensor_v3_config(workspace_root)
    if classified_track == "OPTIMIZATION" and "refactor_rsi" in cfg.get("profiles", {}):
        return "refactor_rsi"
    spec = cfg.get("classified_track_weights", {}).get(classified_track, {})
    target_track = str(spec.get("intent_track", "CODE_TRACK"))
    target_cat = str(spec.get("intent_category", "CODE_BUILD"))
    if classified_track == "DOC_SPEC" and "spec_rsi" in cfg.get("profiles", {}):
        return "spec_rsi"
    for prof_name, p_spec in cfg.get("profiles", {}).items():
        if p_spec.get("intent_track") == target_track and p_spec.get("intent_category") == target_cat and prof_name != "ui_ux_rsi":
            return str(prof_name)
    return "spec_rsi" if target_track == "DOC_TRACK" else "code_rsi"


def get_model_tier_maps(workspace_root: Optional[Union[str, Path]] = None) -> Tuple[Dict[str, str], Dict[str, int]]:
    tiers = load_tensor_v3_config(workspace_root).get("model_tiers", {})
    p_map: Dict[str, str] = {}
    caps: Dict[str, int] = {}
    for tier_name, spec in tiers.items():
        if isinstance(spec, dict):
            caps[str(tier_name)] = int(spec.get("tier1_token_cap", 1200))
            for prof in spec.get("profiles", ()):
                p_map[str(prof).strip().lower()] = str(tier_name)
    return p_map, caps


def get_bandit_config(workspace_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    return dict(load_tensor_v3_config(workspace_root).get("bandit", _DEFAULT_V3_CONFIG["bandit"]))
