# -*- coding: utf-8 -*-
"""Tensore deterministico di politica Policy(Intent, ModelTier, ACSZone) (DOM-01)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from _internal.tensor_rsi.config_loader import get_model_tier_maps, load_tensor_v3_config
from _internal.tensor_rsi.helper_ops import acs_spike_match, resolve_fg_numbers, select_cell_ops
from _internal.tensor_rsi.schemas import (
    ACSZoneLiteral, ClassifiedTrackLiteral, IntentCategoryLiteral,
    IntentTrackLiteral, MacroOperatorLiteral, ModelTierLiteral, PolicyCell, PytestModeLiteral,
)
from _internal.vibe_sprint_router.intent_track_classifier import resolve_intent_category

_CONV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DEFAULT_ACS: Dict[str, int] = {
    "z1_tokens": 160_000, "z2_tokens": 185_000, "z3_tokens": 205_000,
    "z1_steps": 120, "z2_steps": 150, "z3_steps": 180,
    "velocity_floor": 140_000, "velocity_step_floor": 100, "velocity_jump": 25_000,
}
_DEFAULT_CELLS: Dict[Tuple[ACSZoneLiteral, ModelTierLiteral], Dict[str, Any]] = {
    ("Z0", "NEON"): {"br": 3, "del": False, "fan": 3, "it_c": 4, "it_m": 2, "pm": "FULL_ISOLATED_COV", "cmp": False, "hlt": False},
    ("Z0", "CARBON_GEN"): {"br": 3, "del": False, "fan": 3, "it_c": 4, "it_m": 2, "pm": "FULL_ISOLATED_COV", "cmp": False, "hlt": False},
    ("Z0", "PRO"): {"br": 2, "del": False, "fan": 2, "it_c": 3, "it_m": 2, "pm": "FULL_ISOLATED_COV", "cmp": False, "hlt": False},
    ("Z0", "FLASH"): {"br": 1, "del": True, "fan": 1, "it_c": 2, "it_m": 1, "pm": "FAST_MARK_ISOLATED", "cmp": False, "hlt": False},
    ("Z0", "STANDARD"): {"br": 2, "del": False, "fan": 1, "it_c": 2, "it_m": 1, "pm": "FULL_ISOLATED_COV", "cmp": False, "hlt": False},
    ("Z1", "NEON"): {"br": 1, "del": True, "fan": 2, "it_c": 2, "it_m": 1, "pm": "TARGETED_SLICE", "cmp": False, "hlt": False},
    ("Z1", "CARBON_GEN"): {"br": 1, "del": True, "fan": 2, "it_c": 2, "it_m": 1, "pm": "TARGETED_SLICE", "cmp": False, "hlt": False},
    ("Z1", "PRO"): {"br": 1, "del": True, "fan": 2, "it_c": 2, "it_m": 1, "pm": "TARGETED_SLICE", "cmp": False, "hlt": False},
    ("Z1", "FLASH"): {"br": 1, "del": True, "fan": 1, "it_c": 1, "it_m": 1, "pm": "TARGETED_SLICE", "cmp": True, "hlt": False},
    ("Z1", "STANDARD"): {"br": 1, "del": True, "fan": 1, "it_c": 1, "it_m": 1, "pm": "TARGETED_SLICE", "cmp": True, "hlt": False},
}
_Z2_ROW = {"br": 1, "del": True, "fan": 1, "it_c": 1, "it_m": 0, "pm": "TARGETED_SLICE", "cmp": True, "hlt": False}
_Z3_ROW = {"br": 0, "del": False, "fan": 0, "it_c": 0, "it_m": 0, "pm": "SKIP_READONLY", "cmp": True, "hlt": True}


def resolve_model_tier(tier_hint: Optional[str] = None, workspace_root: Optional[Union[str, Path]] = None) -> ModelTierLiteral:
    """Risolve deterministicamente ModelTier da config v3 o env profilo."""
    profile_map, _ = get_model_tier_maps(workspace_root)
    raw = str(tier_hint or os.environ.get("NK_MODEL_TIER", "") or os.environ.get("NK_MODEL_PROFILE", "") or "generation").strip().lower()
    return profile_map.get(raw, "STANDARD")  # type: ignore[return-value]


def _load_json_overlay(workspace_root: Path, rel_path: str) -> Dict[str, Any]:
    for cand in (workspace_root / ".staging" / rel_path, workspace_root / rel_path):
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    return data
            except (OSError, UnicodeDecodeError, ValueError):
                continue
    return {}


def resolve_conversation_id(conversation_id: Optional[str], workspace_root: Optional[Union[str, Path]] = None) -> str:
    """Valida e risolve conversation_id allineato a nk_acs_fastguard."""
    if conversation_id is not None and str(conversation_id).strip():
        cid = str(conversation_id).strip()
        if not _CONV_ID_RE.fullmatch(cid):
            raise ValueError(f"conversation_id non valido: {conversation_id!r}")
        return cid
    for env_k in ("NK_CONVERSATION_ID", "ANTIGRAVITY_CONVERSATION_ID"):
        env_v = os.environ.get(env_k, "").strip()
        if env_v and _CONV_ID_RE.fullmatch(env_v):
            return env_v
    seed = str(Path(workspace_root).resolve()).lower() if workspace_root else "nk_default"
    return f"default_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"


def _find_fastguard_state_path(conversation_id: Optional[str], workspace_root: Optional[Union[str, Path]] = None) -> Optional[Path]:
    cid = resolve_conversation_id(conversation_id, workspace_root)
    env_hooks = os.environ.get("NK_HOOKS_TEMP_DIR", "").strip()
    if env_hooks:
        roots = [Path(env_hooks)]
    else:
        base = os.environ.get("TEMP", "").strip() or os.environ.get("TMP", "").strip() or tempfile.gettempdir()
        roots = [Path(base), Path(tempfile.gettempdir())]
    for d_root in roots:
        cand = d_root / "nk_hooks" / f"fastguard_{cid}.json"
        if cand.is_file():
            return cand
    return None


def _read_fastguard_dict(conversation_id: Optional[str], workspace_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Carica il dizionario fastguard_<cid>.json se presente e valido."""
    fg_path = _find_fastguard_state_path(conversation_id, workspace_root)
    if fg_path is None:
        return {}
    try:
        loaded = json.loads(fg_path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, UnicodeDecodeError, ValueError):
        return {}


def _is_acs_velocity_spike(cur_tok: int, prev_tok: int, steps: int, acs: Dict[str, Any], fg_data: Dict[str, Any]) -> bool:
    """Verifica lo spike Z3 via last_velocity_delta, delta diretto o epoca Z3."""
    return acs_spike_match(cur_tok, prev_tok, steps, acs, fg_data)


def _resolve_acs_zone(cur_tok: int, prev_tok: int, steps: int, acs: Dict[str, Any], fg_data: Dict[str, Any]) -> ACSZoneLiteral:
    """Classifica la zona Z0..Z3 da token, step, velocity spike ed epoca Z3."""
    if _is_acs_velocity_spike(cur_tok, prev_tok, steps, acs, fg_data):
        return "Z3"
    thresholds: Tuple[Tuple[ACSZoneLiteral, str, str], ...] = (("Z3", "z3_tokens", "z3_steps"), ("Z2", "z2_tokens", "z2_steps"), ("Z1", "z1_tokens", "z1_steps"))
    for zone, tok_k, step_k in thresholds:
        if cur_tok >= int(acs[tok_k]) or steps >= int(acs[step_k]):
            return zone
    return "Z0"


def _load_opt_fg(conversation_id: Optional[str], tokens_override: Optional[int], workspace_root: Union[str, Path]) -> Dict[str, Any]:
    return {} if (tokens_override is not None and conversation_id is None) else _read_fastguard_dict(conversation_id, workspace_root)


def _select_acs_zone(
    zone_override: Optional[ACSZoneLiteral], cur_tok: int, prev_tok: int, steps: int,
    acs: Dict[str, Any], fg_data: Dict[str, Any], tokens_override: Optional[int],
) -> ACSZoneLiteral:
    if zone_override in ("Z0", "Z1", "Z2", "Z3"):
        return zone_override  # type: ignore[return-value]
    return _resolve_acs_zone(cur_tok, prev_tok, steps, acs, fg_data if tokens_override is None else {})


def read_acs_state(
    workspace_root: Union[str, Path],
    conversation_id: Optional[str] = None,
    *,
    tokens_override: Optional[int] = None,
    steps_override: Optional[int] = None,
    zone_override: Optional[ACSZoneLiteral] = None,
) -> Tuple[ACSZoneLiteral, int, int]:
    """Legge fastguard_<cid>.json e soglie ACS restituendo (ACSZone, tokens, steps)."""
    raw_acs = _load_json_overlay(Path(workspace_root), "nk_genome/configs/saturation_thresholds.json").get("autonomous_context_shield")
    acs = {**_DEFAULT_ACS, **(raw_acs if isinstance(raw_acs, dict) else {})}
    fg_data = _load_opt_fg(conversation_id, tokens_override, workspace_root)
    cur_tok, prev_tok, steps = resolve_fg_numbers(tokens_override, steps_override, fg_data)
    zone = _select_acs_zone(zone_override, cur_tok, prev_tok, steps, acs, fg_data, tokens_override)
    return zone, cur_tok, steps


def _lookup_matrix_row(cfg_v3: Dict[str, Any], zone: ACSZoneLiteral, tier: ModelTierLiteral, tier_cap: int) -> Dict[str, Any]:
    matrix = cfg_v3.get("policy_matrix")
    if isinstance(matrix, dict) and isinstance(matrix.get(zone), dict):
        entry = matrix[zone].get(tier) or matrix[zone].get("DEFAULT")
        if isinstance(entry, dict):
            return {
                "br": int(entry.get("max_in_context_branches", 1)), "del": bool(entry.get("delegate_subagent_slices", True)),
                "fan": int(entry.get("max_subagent_fanout", 1)), "cap": int(entry.get("subagent_slice_token_cap", tier_cap)),
                "it_c": int(entry.get("max_rsi_iterations_code", 1)), "it_m": int(entry.get("max_rsi_iterations_micro", 0)),
                "pm": str(entry.get("pytest_mode", "TARGETED_SLICE")), "cmp": bool(entry.get("recommend_compact", False)),
                "hlt": bool(entry.get("halt_for_handoff", False)),
            }
    base = dict(_Z3_ROW) if zone == "Z3" else (dict(_Z2_ROW) if zone == "Z2" else dict(_DEFAULT_CELLS[(zone, tier)]))
    base["cap"] = tier_cap
    return base


def build_policy_cell(
    workspace_root: Union[str, Path],
    classified_track: ClassifiedTrackLiteral,
    *,
    model_tier: Optional[str] = None,
    acs_zone: Optional[ACSZoneLiteral] = None,
    conversation_id: Optional[str] = None,
    is_micro: bool = False,
    tokens_override: Optional[int] = None,
    steps_override: Optional[int] = None,
) -> PolicyCell:
    """Calcola la PolicyCell deterministica per (Intent, ModelTier, ACSZone)."""
    root = Path(workspace_root)
    cfg_v3 = load_tensor_v3_config(root)
    _, tier_caps = get_model_tier_maps(root)
    eff_tier = resolve_model_tier(model_tier, root)
    eff_zone, _, _ = read_acs_state(root, conversation_id=conversation_id, tokens_override=tokens_override, steps_override=steps_override, zone_override=acs_zone)
    ctw = cfg_v3.get("classified_track_weights", {}).get(classified_track, {})
    intent_track: IntentTrackLiteral = str(ctw.get("intent_track", "DOC_TRACK" if classified_track == "DOC_SPEC" else "CODE_TRACK"))  # type: ignore[assignment]
    intent_cat: IntentCategoryLiteral = resolve_intent_category(classified_track, is_micro=is_micro)
    row = _lookup_matrix_row(cfg_v3, eff_zone, eff_tier, int(tier_caps.get(eff_tier, 1200)))
    max_iter = row["it_m"] if intent_cat == "MICRO_VIBE" else row["it_c"]
    max_br, del_slices, fanout = row["br"], bool(row["del"]), row["fan"]
    pytest_mode: PytestModeLiteral = row["pm"]
    if intent_cat == "AUDIT_RO":
        max_iter, del_slices, fanout, pytest_mode, max_br = 0, False, 0, "SKIP_READONLY", (0 if eff_zone == "Z3" else min(1, max_br))
    if eff_zone in ("Z1", "Z2"):
        max_br = min(1, max_br)
    if eff_zone == "Z3":
        max_br, max_iter, fanout, del_slices, pytest_mode = 0, 0, 0, False, "SKIP_READONLY"
    raw_fields: Dict[str, Any] = {
        "intent": intent_cat, "intent_track": intent_track, "classified_track": classified_track,
        "model_tier": eff_tier, "acs_zone": eff_zone, "max_rsi_iterations": max(0, min(4, max_iter)),
        "max_in_context_branches": max(0, min(3, max_br)), "delegate_subagent_slices": del_slices,
        "subagent_slice_token_cap": max(128, min(1200, int(row["cap"]))), "max_subagent_fanout": max(0, min(3, fanout)),
        "pytest_mode": pytest_mode, "recommend_compact": bool(row["cmp"]), "halt_for_handoff": bool(eff_zone == "Z3" or row["hlt"]),
    }
    cell_hash = hashlib.sha256(json.dumps(raw_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return PolicyCell(**raw_fields, policy_cell_hash=cell_hash)


def _track_ops_from_cfg(intent_track: IntentTrackLiteral, workspace_root: Optional[Union[str, Path]]) -> Tuple[str, ...]:
    ops_cfg = load_tensor_v3_config(workspace_root).get("macro_operators", ())
    return tuple(str(o["name"]) for o in ops_cfg if isinstance(o, dict) and intent_track in (o.get("tracks") or ()))


def allowed_operators_for_cell(
    cell: PolicyCell, *, file_count: int = 1, workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[MacroOperatorLiteral, ...]:
    """Maschera i macro-operatori ammissibili rispetto alla PolicyCell e a macro_operators."""
    return select_cell_ops(cell.acs_zone, cell.intent, cell.intent_track, file_count, _track_ops_from_cfg(cell.intent_track, workspace_root))  # type: ignore[return-value]
