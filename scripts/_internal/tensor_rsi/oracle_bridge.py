# -*- coding: utf-8 -*-
"""Adapter Read-Only verso RSIConvergenceEngine (DOM-04) con diff_aware=True e multi-lane."""

from __future__ import annotations

import ast, hashlib, inspect, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from _internal.nk_common.epistemic_firewall_rules import strip_l3_persuasive_narrative
from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir
from _internal.nk_common.staging_manifest import safe_finite_float
from _internal.tensor_rsi.pareto_gate import compute_secondary_vector
from _internal.tensor_rsi.schemas import (
    IntentTrackLiteral, MetricSnapshot, ParetoDecisionResult, PolicyCell,
    PrimaryInvariantVector, TensorRSIStateTicket,
)
from rsi_convergence_engine import RSIConvergenceEngine, RSIDefectVector, RSIIterationRecord

_MD_LINK_COUNT_RE = re.compile(r"\]\([^\)\r\n]+\)")

def _safe_int(val: Any, default: int = 0) -> int:
    if isinstance(val, bool) or val is None:
        return default
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return default

def _safe_float(val: Any, default: float = 0.0) -> float:
    return safe_finite_float(val, default=default)

def _safe_duration_s(raw: Any) -> float:
    if raw is None:
        return 0.0
    val = safe_finite_float(raw, default=-1.0)
    return val if val >= 0.0 else float("nan")

def _iter_repo_count_files(stg: Path, excl_lanes: bool) -> List[Path]:
    out: List[Path] = []
    for fp in sorted(stg.rglob("*")):
        if not fp.is_file() or "__pycache__" in fp.parts:
            continue
        if excl_lanes and is_lane_container_entry(fp.relative_to(stg).parts):
            continue
        out.append(fp)
    return out

def _derive_repo_counts(workspace_root: Path, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Tuple[int, int, int]:
    """Deriva deterministicamente (assert_count, doc_link_count, loc_delta) da staging/lane vs produzione."""
    if staging_dir is not None:
        stg, excl_lanes = Path(staging_dir).resolve(), False
    else:
        stg, norm_lane = resolve_staging_dir(workspace_root, lane_id=lane_id)
        excl_lanes = norm_lane is None and stg.name == ".staging"
    if not stg.is_dir():
        return 0, 0, 0
    asserts, doc_links, loc_delta = 0, 0, 0
    for fp in _iter_repo_count_files(stg, excl_lanes):
        suf = fp.suffix.lower()
        try:
            txt = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if suf == ".py":
            try:
                asserts += sum(1 for n in ast.walk(ast.parse(txt)) if isinstance(n, ast.Assert))
            except SyntaxError:
                pass
            prod = workspace_root / fp.relative_to(stg)
            prod_lines = len(prod.read_text(encoding="utf-8", errors="replace").splitlines()) if prod.is_file() else 0
            loc_delta += abs(len(txt.splitlines()) - prod_lines)
        elif suf == ".md":
            doc_links += len(_MD_LINK_COUNT_RE.findall(txt))
    return asserts, doc_links, loc_delta

def _attach_opt_verify_kwargs(
    kwargs: Dict[str, Any], params: Any, coverage_report: Optional[Any], lane_id: Optional[str], staging_dir: Optional[Path] = None,
) -> None:
    has_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if has_kw or "diff_aware" in params:
        kwargs["diff_aware"] = True
    if has_kw or "strict_unmeasured_gate" in params:
        kwargs["strict_unmeasured_gate"] = True
    if coverage_report is not None and (has_kw or "coverage_report" in params):
        kwargs["coverage_report"] = coverage_report
    if lane_id is not None and (has_kw or "lane_id" in params):
        kwargs["lane_id"] = lane_id
    if staging_dir is not None and (has_kw or "staging_dir" in params):
        kwargs["staging_dir"] = staging_dir

def _invoke_verify_ecosystem_ro(
    engine: RSIConvergenceEngine, workspace_root: Path, *, profile: str, run_pytest: bool,
    strict_verify: bool, benchmark_suite: Optional[str], sast_report: Optional[Union[str, Path]],
    test_report: Optional[Dict[str, Any]], dast_report: Optional[Union[str, Path]],
    mutation_report: Optional[Any], coverage_report: Optional[Any], allowed_files: Optional[Union[str, Sequence[str]]],
    lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Chiama verify_ecosystem(..., diff_aware=True, strict_unmeasured_gate=True) in sola lettura."""
    kwargs: Dict[str, Any] = {
        "root_dir": workspace_root, "run_pytest": run_pytest, "profile": profile,
        "benchmark_suite": benchmark_suite, "sast_report": sast_report, "strict_verify": strict_verify,
        "persist_telemetry": False, "test_report": test_report, "dast_report": dast_report,
        "mutation_report": mutation_report, "allowed_files": allowed_files,
    }
    try:
        params = inspect.signature(engine.verify_ecosystem).parameters
    except (TypeError, ValueError):
        params = {}
    _attach_opt_verify_kwargs(kwargs, params, coverage_report, lane_id, staging_dir)
    return engine.verify_ecosystem(**kwargs)

def _as_dict(mapping: Dict[str, Any], key: str) -> Dict[str, Any]:
    val = mapping.get(key)
    return val if isinstance(val, dict) else {}

def _extract_primary_from_oracle(
    res: Dict[str, Any], checks: Dict[str, Any], intent_track: IntentTrackLiteral
) -> Tuple[PrimaryInvariantVector, Dict[str, Any]]:
    bench, mut = _as_dict(checks, "benchmark_suite"), _as_dict(checks, "mutation_gate")
    qd, md, sast_chk = _as_dict(checks, "quality_diff_and_frontend"), _as_dict(checks, "skills_and_markdown"), _as_dict(checks, "sast_and_mojibake")
    ast_mt, sast_rep, cov_chk = _as_dict(checks, "ast_mock_and_taint"), _as_dict(checks, "sast_report"), _as_dict(checks, "coverage_report")
    dast, twin = _as_dict(checks, "dast_report"), _as_dict(checks, "twin_manifest_parity")
    t_tot, t_pass, t_fail = _safe_int(bench.get("tests_total")), _safe_int(bench.get("tests_passed")), _safe_int(bench.get("tests_failed"))
    p_pass = (float(t_pass) / float(t_tot)) if t_tot > 0 else 0.0
    k_mut = _safe_float(mut.get("kill_rate"), 0.0) if mut else (1.0 if intent_track == "DOC_TRACK" else 0.0)
    raw_cov = bench.get("true_branch_coverage_pct", bench.get("branch_coverage_pct"))
    if raw_cov is None and cov_chk.get("passed", False):
        raw_cov = cov_chk.get("true_branch_coverage_pct", cov_chk.get("branch_coverage_pct"))
    c_branch = (_safe_float(raw_cov) / 100.0) if raw_cov is not None else (1.0 if intent_track == "DOC_TRACK" else 0.0)
    crit = max(_safe_int(sast_chk.get("sast_critical")), _safe_int(sast_rep.get("sast_critical")))
    dast_hi = max(_safe_int(res.get("dast_high_findings")), _safe_int(dast.get("high_findings")))
    high_cnt = _safe_int(qd.get("high_findings")) + _safe_int(mut.get("high_findings")) + _safe_int(cov_chk.get("high_findings")) + dast_hi
    twin_mm = max(_safe_int(res.get("twin_mismatches_count")), len(twin.get("mismatches", ())))
    doc_drift = len(md.get("broken_links", ())) + len(md.get("phantom_scripts", ()))
    sem_drift = _safe_int(qd.get("semantic_drift_findings")) + twin_mm
    s_taint = _safe_int(ast_mt.get("sast_taint", ast_mt.get("s_taint"))) + _safe_int(sast_rep.get("sast_taint", sast_rep.get("s_taint"))) + _safe_int(sast_chk.get("s_taint", sast_chk.get("sast_taint")))
    mock_cnt = _safe_int(ast_mt.get("mock_count")) + _safe_int(sast_chk.get("mock_count"))
    primary = PrimaryInvariantVector(
        p_pass=round(max(0.0, min(1.0, p_pass)), 6), k_mut=round(max(0.0, min(1.0, k_mut)), 6),
        c_branch=round(max(0.0, min(1.0, c_branch)), 6), critical_count=crit, high_count=high_cnt,
        doc_drift_count=doc_drift, semantic_drift_count=sem_drift,
    )
    return primary, {
        "bench": bench, "qd": qd, "md": md, "sast": sast_chk, "t_tot": t_tot, "t_fail": t_fail,
        "t_skip": _safe_int(bench.get("tests_skipped")), "xfailed": _safe_int(bench.get("xfailed_count")),
        "deselected": _safe_int(bench.get("deselected_count")), "crit": crit, "doc_drift": doc_drift,
        "sem_drift": sem_drift, "s_taint": s_taint, "mock_count": mock_cnt,
    }

def _resolve_state_hash(res: Dict[str, Any]) -> str:
    state_hash = str(res.get("state_hash") or "")
    return state_hash if len(state_hash) == 64 else hashlib.sha256(str(res).encode("utf-8")).hexdigest()

def _resolve_tier(res: Dict[str, Any]) -> str:
    tier = str(res.get("certification_tier") or "UNMEASURED")
    return tier if tier in ("CERTIFIED_PASS", "STATIC_PASS", "UNMEASURED", "FAIL") else "UNMEASURED"

def _extract_holdout_failures(res: Dict[str, Any], dast: Dict[str, Any], canary: Dict[str, Any]) -> int:
    dast_f = _safe_int(dast.get("f_holdout"), 0)
    if dast.get("holdout_passed") is False and dast_f == 0:
        dast_f = 1
    canary_f = 0
    if canary and not canary.get("passed", True):
        tot, ok_cnt, decep = _safe_int(canary.get("total_tasks")), _safe_int(canary.get("conflict_reported_count")), _safe_int(canary.get("deception_gaming_count"))
        canary_f = max(1, (tot - ok_cnt) + decep)
    return max(_safe_int(res.get("f_holdout")), dast_f + canary_f)

def _compute_contract_violations(res: Dict[str, Any], checks: Dict[str, Any], sast: Dict[str, Any], hyg: Dict[str, Any], gt14: Dict[str, Any]) -> int:
    cove, tel = _as_dict(checks, "cli_flags_cove"), _as_dict(checks, "telemetry_chain")
    six_sources = (
        len(cove.get("invalid_flags", ())) + _safe_int(sast.get("mojibake_count")) + _safe_int(sast.get("invalid_json_count"))
        + len(gt14.get("issues", ())) + len(hyg.get("dirty_files", ())) + (0 if tel.get("passed", True) else 1)
    )
    return max(_safe_int(res.get("contract_violations_count")), six_sources)

def _resolve_dast_ok(dast: Dict[str, Any], intent_track: IntentTrackLiteral, tier: str, strict_verify: bool) -> int:
    if dast and not bool(dast.get("skipped")):
        return int(bool(dast.get("passed", False)))
    has_py = intent_track == "CODE_TRACK" and tier != "STATIC_PASS"
    return 0 if (strict_verify and has_py) else 1

def _build_snapshot_meta(
    res: Dict[str, Any], raw: Dict[str, Any], dast: Dict[str, Any], canary: Dict[str, Any],
    gt14: Dict[str, Any], twin: Dict[str, Any], intent_track: IntentTrackLiteral, strict_verify: bool,
) -> Dict[str, Any]:
    unmeasured = tuple(dict.fromkeys(str(x) for x in [*(res.get("unmeasured_reasons") or ()), *(res.get("unmeasured_components") or ())]))
    tier = _resolve_tier(res)
    dry_run_flag = int(bool(res.get("dry_run")) or ("UNMEASURED_DRY_RUN" in unmeasured))
    eff_g_hard = 1 if (int(res.get("g_hard", 0)) == 1 and tier != "UNMEASURED" and not unmeasured and dry_run_flag == 0) else 0
    gaming_pen = min(0, int(res.get("gaming_penalty", 0)))
    deception_cnt = max(int(gaming_pen < 0), _safe_int(res.get("deception_gaming_count")), _safe_int(canary.get("deception_gaming_count")))
    return {
        "unmeasured": unmeasured, "tier": tier, "dry_run_flag": dry_run_flag, "eff_g_hard": eff_g_hard,
        "gaming_pen": gaming_pen, "deception_cnt": deception_cnt,
        "dast_ok": _resolve_dast_ok(dast, intent_track, tier, strict_verify),
        "gt14_ok": int(res["gt14_governance_ok"]) if "gt14_governance_ok" in res else int(bool(gt14.get("passed", True))),
        "twin_ok": int(res["twin_parity_ok"]) if "twin_parity_ok" in res else int(bool(twin.get("passed", True))),
    }


def snapshot_from_oracle_result(
    res: Dict[str, Any], intent_track: IntentTrackLiteral, *,
    loc_delta: int = 0, assert_count: int = 0, doc_link_count: int = 0, strict_verify: bool = False,
) -> MetricSnapshot:
    """Converte il payload di verify_ecosystem in MetricSnapshot strict."""
    checks = _as_dict(res, "checks")
    primary, raw = _extract_primary_from_oracle(res, checks, intent_track)
    hyg, dast, canary = _as_dict(checks, "workspace_clean_hygiene"), _as_dict(checks, "dast_report"), _as_dict(checks, "canary_holdout")
    gt14, twin, tas_chk = _as_dict(checks, "gt14_crit01_governance"), _as_dict(checks, "twin_manifest_parity"), _as_dict(checks, "tas_report_grounding")
    secondary = compute_secondary_vector(
        medium_findings=_safe_int(raw["qd"].get("medium_findings")), low_findings=_safe_int(raw["qd"].get("low_findings")),
        dirty_orphans=len(hyg.get("dirty_files", ())), doc_drift=raw["doc_drift"], semantic_drift=raw["sem_drift"],
        duration_s=_safe_duration_s(res.get("duration_s")), loc_delta=loc_delta, ste100_warnings=len(res.get("ste100_warnings") or ()),
    )
    meta = _build_snapshot_meta(res, raw, dast, canary, gt14, twin, intent_track, strict_verify)
    contract_viol = _compute_contract_violations(res, checks, raw["sast"], hyg, gt14)
    return MetricSnapshot(
        intent_track=intent_track, g_hard=meta["eff_g_hard"], failed_hard_gates=tuple(str(x) for x in (res.get("failed_hard_gates") or ())),
        epistemic_conflict=bool(res.get("epistemic_conflict", False)), gaming_penalty=meta["gaming_pen"],
        q_v2=max(0.0, min(100.0, _safe_float(res.get("q_v2"), 0.0))), delta_k=_safe_int(res.get("delta_k")),
        certification_tier=meta["tier"], state_hash=_resolve_state_hash(res), primary=primary, secondary=secondary,  # type: ignore[arg-type]
        tests_total=raw["t_tot"], failed_tests=raw["t_fail"], tests_skipped=raw["t_skip"],
        xfailed=raw["xfailed"], deselected=raw["deselected"], s_taint=raw["s_taint"],
        sast_critical=raw["crit"], dast_passed=meta["dast_ok"], poc_confirmed_exploits=_safe_int(dast.get("poc_confirmed_exploits")),
        deception_gaming_count=meta["deception_cnt"], mock_count=raw["mock_count"], f_holdout=_extract_holdout_failures(res, dast, canary),
        scope_creep=raw["sem_drift"], contract_violations=contract_viol,
        hallucinated_refs=max(_safe_int(res.get("hallucinated_refs")), _safe_int(tas_chk.get("hallucinated_refs"))),
        dry_run=meta["dry_run_flag"], broken_links=len(raw["md"].get("broken_links", ())),
        phantom_scripts=len(raw["md"].get("phantom_scripts", ())), invalid_json=_safe_int(raw["sast"].get("invalid_json_count")),
        mojibake=_safe_int(raw["sast"].get("mojibake_count")), gt14_governance_ok=meta["gt14_ok"], twin_parity_ok=meta["twin_ok"],
        assert_count=max(0, int(assert_count)), doc_link_count=max(0, int(doc_link_count)),
        skill_count=_safe_int(raw["md"].get("skills_verified")), unmeasured_reasons=meta["unmeasured"],
    )


def _resolve_eff_ro_counts(
    root: Path, loc_delta: int, assert_count: int, doc_link_count: int, *, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Tuple[int, int, int]:
    d_assert, d_doc, d_loc = _derive_repo_counts(root, lane_id=lane_id, staging_dir=staging_dir)
    return (d_loc if loc_delta < 0 else int(loc_delta), d_assert if assert_count < 0 else int(assert_count), d_doc if doc_link_count < 0 else int(doc_link_count))

def evaluate_ecosystem_ro(
    workspace_root: Union[str, Path], *, profile: str = "code_rsi", intent_track: IntentTrackLiteral = "CODE_TRACK",
    run_pytest: bool = False, strict_verify: bool = False, benchmark_suite: Optional[str] = None,
    sast_report: Optional[Union[str, Path]] = None, test_report: Optional[Dict[str, Any]] = None,
    dast_report: Optional[Union[str, Path]] = None, mutation_report: Optional[Any] = None,
    coverage_report: Optional[Any] = None, allowed_files: Optional[Union[str, Sequence[str]]] = None,
    loc_delta: int = -1, assert_count: int = -1, doc_link_count: int = -1,
    lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Tuple[MetricSnapshot, Dict[str, Any]]:
    """Esegue la verifica DOM-04 RO sanitizzando l'output contro AP-01..AP-13."""
    root = Path(workspace_root).resolve()
    eff_loc, eff_assert, eff_doc = _resolve_eff_ro_counts(root, loc_delta, assert_count, doc_link_count, lane_id=lane_id, staging_dir=staging_dir)
    engine = RSIConvergenceEngine(workspace_root=root, root=root)
    raw_res = strip_l3_persuasive_narrative(_invoke_verify_ecosystem_ro(
        engine, root, profile=profile, run_pytest=run_pytest, strict_verify=strict_verify,
        benchmark_suite=benchmark_suite, sast_report=sast_report, test_report=test_report,
        dast_report=dast_report, mutation_report=mutation_report, coverage_report=coverage_report,
        allowed_files=allowed_files, lane_id=lane_id, staging_dir=staging_dir,
    ))
    return snapshot_from_oracle_result(raw_res, intent_track, loc_delta=eff_loc, assert_count=eff_assert, doc_link_count=eff_doc, strict_verify=strict_verify), raw_res


def append_v1_telemetry_projection(
    root: Path, cand: MetricSnapshot, ticket: TensorRSIStateTicket, cell: PolicyCell, pareto: ParetoDecisionResult
) -> None:
    """Proietta la decisione Tensor-RSI in rsi_telemetry.jsonl con xfailed sottratti e campi Q_v2."""
    defects = RSIDefectVector(
        sast_critical=cand.sast_critical, tests_failed=cand.failed_tests,
        tests_passed=max(0, cand.tests_total - cand.failed_tests - cand.tests_skipped - cand.xfailed),
        tests_total=cand.tests_total, contract_violations=cand.contract_violations,
        high_findings=cand.primary.high_count, doc_drift=cand.primary.doc_drift_count,
        poc_confirmed_exploits=cand.poc_confirmed_exploits, semantic_drift_findings=cand.primary.semantic_drift_count,
        hallucinated_refs=cand.hallucinated_refs, deception_gaming_count=cand.deception_gaming_count,
        unmeasured_components=list(cand.unmeasured_reasons),
    )
    verdict_map = {"CONVERGED_OPTIMAL": "CONVERGED_OPTIMAL", "REJECT_TIER0_HARD_GATE": "ROLLED_BACK_HARD_GATE"}
    v1_verdict = verdict_map.get(pareto.verdict, "ACCEPT_PARETO" if pareto.accepted else "REFINING")
    rec = RSIIterationRecord(
        session_id=ticket.session_id, iteration=ticket.iteration, mode="mode_d" if cell.intent == "AUDIT_RO" else "mode_a",
        defects=defects, delta_k=cand.delta_k, fitness_q=cand.q_v2, state_hash=cand.state_hash,
        verdict=v1_verdict, rolled_back=not pareto.accepted, q_v2=cand.q_v2, g_hard=cand.g_hard,
        delta_hard=len(cand.failed_hard_gates), certification_tier=cand.certification_tier,
    )
    RSIConvergenceEngine(workspace_root=root, root=root).append_telemetry_record(
        RSIIterationRecord.model_validate(rec.model_dump(exclude_none=True))
    )
