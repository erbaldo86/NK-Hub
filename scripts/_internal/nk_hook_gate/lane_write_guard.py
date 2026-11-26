"""Guardia multi-lane e promozione --lane-id pure-stdlib per write_gate."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.lane_paths import (
    extract_lane_id_from_path,
    extract_lane_plan_id_from_rel_parts,
    resolve_staging_dir,
    strip_staging_rel_parts,
    validate_lane_id,
)
from _internal.nk_common.lane_registry import verify_lane_access
from _internal.nk_hook_gate.constants import _WORKSPACE_ROOT, _strip_wrapping_quotes
from _internal.nk_hook_gate.path_safety import (
    _canonical_path, _has_ancestor_reparse_escape, _resolve_effective_hub_root, _resolve_target_path,
)

_LANE_PATH_TOKEN_RE = re.compile(
    r'"[^"\n\r;|&]*?\.staging[/\\]lanes[/\\][^"\n\r;|&]+"'
    r"|'[^'\n\r;|&]*?\.staging[/\\]lanes[/\\][^'\n\r;|&]+'"
    r"|[^\s\"';|&()\[\]=<>]*?\.staging[/\\]lanes[/\\][^\s\"';|&()\[\],<>]+",
    re.IGNORECASE,
)
_PROMOTE_SKIP_VALUE_FLAGS = frozenset(("--milestone", "--override-reason", "--governance-token", "--sandbox-report", "--root", "--repo-root", "--base-seq"))


def _parse_flag_step(words: List[str], idx: int, low: str, tok: str, names: Tuple[str, ...]) -> Tuple[Optional[str], int]:
    """Estrae (valore, next_idx) se tok corrisponde a uno dei flag in names."""
    if low in names:
        val = _strip_wrapping_quotes(words[idx + 1]).strip() if idx + 1 < len(words) else ""
        return val, idx + (2 if idx + 1 < len(words) else 1)
    for nm in names:
        if low.startswith(nm + "="):
            return _strip_wrapping_quotes(tok.split("=", 1)[1]).strip(), idx + 1
    return None, idx


def _scan_promote_flags(words: List[str]) -> Tuple[List[str], List[str]]:
    """Scansiona token CLI win32_2pc_engine saltando i valori di altri flag."""
    lanes: List[str] = []
    stagings: List[str] = []
    idx = 0
    while idx < len(words):
        tok, low = words[idx], words[idx].lower()
        if low in _PROMOTE_SKIP_VALUE_FLAGS:
            idx += 2
            continue
        lane_v, nxt = _parse_flag_step(words, idx, low, tok, ("--lane-id", "--parent-lane"))
        if nxt != idx:
            if lane_v:
                lanes.append(lane_v)
            idx = nxt
            continue
        stg_v, nxt = _parse_flag_step(words, idx, low, tok, ("--staging-dir", "--stage-dir"))
        if nxt != idx:
            if stg_v:
                stagings.append(stg_v)
            idx = nxt
            continue
        idx += 1
    return lanes, stagings


def extract_promote_lane_id(words: List[str]) -> Optional[str]:
    """Estrae l'eventuale valore --lane-id o --parent-lane (last-wins) dai token CLI di win32_2pc_engine."""
    lanes, _ = _scan_promote_flags(words)
    return lanes[-1] if lanes else None


def extract_promote_lane_and_staging(words: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Estrae (lane_id, staging_dir) bloccando flag duplicati in conflitto."""
    lanes, stagings = _scan_promote_flags(words)
    if len({validate_lane_id(x) for x in lanes}) > 1:
        raise ValueError(f"Flag --lane-id/--parent-lane duplicato in conflitto: {lanes}")
    if len(set(stagings)) > 1:
        raise ValueError(f"Flag --staging-dir duplicato in conflitto: {stagings}")
    return (lanes[-1] if lanes else None), (stagings[-1] if stagings else None)


def _collect_promote_target_pairs(
    cmd_deobf: str, project_root: Path, has_inline: bool, extract_roots_fn: Any
) -> List[Tuple[Path, Optional[str], Optional[str]]]:
    """Raccoglie triple uniche (repo_root, lane_id, staging_dir) per ogni segmento promote."""
    from _internal.nk_hook_gate.constants_patterns import has_win32_2pc_promote_tokens
    from _internal.nk_hook_gate.shell_parser import _split_shell_segments, _tokenize_shell_tokens, _unwrap_shell_subcommands

    seen: Dict[Tuple[Path, Optional[str], Optional[str]], None] = {}
    for cand in (cmd_deobf, *_unwrap_shell_subcommands(cmd_deobf)):
        for seg in _split_shell_segments(cand) or [cand]:
            words = [u for _, u, _ in _tokenize_shell_tokens(seg)]
            if has_win32_2pc_promote_tokens(words):
                lane_id, raw_stg = extract_promote_lane_and_staging(words)
                for rc in extract_roots_fn(words, project_root):
                    seen[(rc, lane_id, raw_stg)] = None
    if has_inline:
        for rc in extract_roots_fn([], project_root):
            seen[(rc, None, None)] = None
    return list(seen.keys())


def verify_promote_targets_with_lanes(
    cmd_deobf: str, project_root: Path, has_inline: bool, extract_roots_fn: Any
) -> Dict[str, Any]:
    """Verifica verify_active_tensor_session per ogni tripla (root, lane_id, staging_dir)."""
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.tensor_session_guard import verify_active_tensor_session

    try:
        pairs = _collect_promote_target_pairs(cmd_deobf, project_root, has_inline, extract_roots_fn)
        for root_cand, raw_lane, raw_stg in pairs:
            stg_dir, norm_lane = resolve_staging_dir(root_cand, lane_id=raw_lane, staging_dir=raw_stg)
            verify_active_tensor_session(root_cand, stg_dir, lane_id=norm_lane)
    except (TwoPhaseCommitError, ValueError, OSError) as exc:
        return {"decision": "deny", "reason_code": "ACTIVE_TENSOR_SESSION_UNAPPROVED", "reason": f"Promozione staging bloccata: {exc}"}
    return {}


def check_lane_plan_write_authorization(cand: Path, project_root: Path, conv_id: str) -> Dict[str, Any]:
    """Consente nk_genome/plans/<lane_id>.md solo all'owner/child autorizzato della lane."""
    cand_res = _canonical_path(cand)
    eff_root = _resolve_effective_hub_root(_canonical_path(project_root))
    proj_canon = _canonical_path(project_root)
    ws_root = _canonical_path(_WORKSPACE_ROOT)
    for base_r in (eff_root, proj_canon, ws_root):
        if cand_res == base_r or base_r in cand_res.parents:
            try:
                rel_parts = cand_res.relative_to(base_r).parts
            except ValueError:
                continue
            plan_lane = extract_lane_plan_id_from_rel_parts(rel_parts)
            if plan_lane is not None:
                try:
                    ok, code = verify_lane_access(base_r, plan_lane, conv_id)
                except (OSError, ValueError, TimeoutError) as exc:
                    ok, code = False, str(exc)
                if not ok:
                    return {
                        "decision": "deny",
                        "reason_code": "LANE_OWNERSHIP_DENIED",
                        "reason": f"Accesso negato al piano 'nk_genome/plans/{plan_lane}.md' per conversation_id={conv_id!r} ({code}).",
                    }
    return {}


def _check_staged_lane_plan_subpath(rel: Tuple[str, ...], lane_id: str) -> Dict[str, Any]:
    """Blocca piani non validi o cross-lane sotto .staging/lanes/<id>/nk_genome/plans/."""
    if len(rel) >= 2 and str(rel[0]).lower() == "nk_genome" and str(rel[1]).lower() == "plans":
        inner_plan = extract_lane_plan_id_from_rel_parts(rel)
        if inner_plan is None or inner_plan != validate_lane_id(lane_id):
            return {
                "decision": "deny",
                "reason_code": "LANE_OWNERSHIP_DENIED",
                "reason": f"Piano non valido o cross-lane in '.staging/lanes/{lane_id}/nk_genome/plans/'.",
            }
    return {}


def check_lane_write_authorization(cand: Path, project_root: Path, conv_id: str) -> Dict[str, Any]:
    """Verifica ownership della lane in .staging/lanes/<id>/ in modalita fail-closed."""
    lane_id = extract_lane_id_from_path(cand)
    if lane_id is None:
        return {}
    idx, rel, _raw = strip_staging_rel_parts(cand.parts)
    repo_root = Path(*cand.parts[:idx]) if idx > 0 else _resolve_effective_hub_root(_canonical_path(project_root))
    try:
        ok, code = verify_lane_access(repo_root, lane_id, conv_id)
    except (OSError, ValueError, TimeoutError) as exc:
        ok, code = False, str(exc)
    if not ok:
        return {
            "decision": "deny",
            "reason_code": "LANE_OWNERSHIP_DENIED",
            "reason": f"Accesso negato alla lane '.staging/lanes/{lane_id}/' per conversation_id={conv_id!r} ({code}).",
        }
    return _check_staged_lane_plan_subpath(rel, lane_id)


def _collect_shell_lane_write_candidates(seg: str, project_root: Path) -> List[Path]:
    """Estrae i target .staging/lanes/<id>/ interessati da redirezioni o indicatori write."""
    from _internal.nk_hook_gate.shell_parser import (
        _extract_archive_targets, _extract_output_flag_targets, _extract_redirection_targets, _tokenize_shell_tokens,
    )
    from _internal.nk_hook_gate.shell_write_detector import _has_non_redirection_write_indicator

    raw_targets: List[str] = _extract_redirection_targets(seg) + _extract_output_flag_targets(seg) + _extract_archive_targets(seg)
    if _has_non_redirection_write_indicator(seg):
        raw_targets.extend(m.group(0) for m in _LANE_PATH_TOKEN_RE.finditer(seg))
        for _, unq, _ in _tokenize_shell_tokens(seg):
            if ".staging/lanes/" in unq.replace("\\", "/").lower():
                raw_targets.append(unq)
    cands, seen = [], set()
    for raw_t in raw_targets:
        cleaned = _strip_wrapping_quotes(raw_t).strip()
        if "lanes" not in cleaned.lower():
            continue
        if _has_ancestor_reparse_escape(cleaned, project_root):
            raise ValueError(f"Reparse/symlink escape rilevato verso lane: {cleaned}")
        cand = _resolve_target_path(cleaned, project_root)
        if cand not in seen:
            seen.add(cand)
            cands.append(cand)
    return cands


def _check_inline_python_lane_seg(seg: str, project_root: Path, conv_id: str) -> Optional[Dict[str, Any]]:
    """Verifica eventuali payload inline python -c in seg rispetto a lane_id ownership."""
    from _internal.nk_hook_gate.ast_inline_guard import extract_python_inline_c_payloads, inspect_python_source_mutations
    from _internal.nk_hook_gate.shell_parser import _tokenize_shell_tokens

    payloads, _ = extract_python_inline_c_payloads(_tokenize_shell_tokens(seg))
    for code_str in payloads:
        if (denial := inspect_python_source_mutations(code_str, project_root, conv_id=conv_id)) is not None:
            return denial
    return None


def check_shell_lane_write_authorization(cmd: str, project_root: Path, conv_id: str) -> Dict[str, Any]:
    """Blocca scritture shell e python -c cross-lane verso .staging/lanes/<id>/ di altre conversazioni."""
    from _internal.nk_hook_gate.shell_parser import _deobfuscate_ps_backticks, _split_shell_segments, _unwrap_shell_subcommands

    cmd_deobf = _deobfuscate_ps_backticks(cmd)
    has_lanes = ".staging/lanes/" in cmd_deobf.replace("\\", "/").lower()
    for cand_cmd in (cmd_deobf, *_unwrap_shell_subcommands(cmd_deobf)):
        for seg in _split_shell_segments(cand_cmd) or [cand_cmd]:
            if (py_denial := _check_inline_python_lane_seg(seg, project_root, conv_id)) is not None:
                return py_denial
            if not has_lanes:
                continue
            try:
                cands = _collect_shell_lane_write_candidates(seg, project_root)
            except ValueError as exc:
                return {"decision": "deny", "reason_code": "LANE_OWNERSHIP_DENIED", "reason": str(exc)}
            for cand_path in cands:
                if (denied := check_lane_write_authorization(cand_path, project_root, conv_id)):
                    return denied
    return {}
