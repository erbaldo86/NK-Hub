# -*- coding: utf-8 -*-
"""Gate Cold-to-Warm, CladeBandit Seeded HMAC, ParetoArchive<=12, NoveltyGate, VoI e Flaky."""
from __future__ import annotations
import ast, hashlib, math, random, xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union
from _internal.nk_common.isolated_test_runner import run_detached_pytest
from _internal.nk_common.staging_manifest import safe_finite_float
from _internal.tensor_rsi.config_loader import get_bandit_config
from _internal.tensor_rsi.helper_ops import beta_quantile_bisect, pareto_add_node
from _internal.tensor_rsi.schemas import ACSZoneLiteral, ColdWarmDecision, MacroOperatorLiteral, StatisticalRegimeLiteral
from _internal.tensor_rsi.ticket_auth import derive_hmac_seed_int

_PRIOR_TABLES: Dict[str, Dict[MacroOperatorLiteral, float]] = {
    "sast_or_test_local": {"SURGICAL_LOCAL_PATCH": 0.85, "ISOLATED_SUBAGENT_SLICE": 0.70, "TEST_ORACLE_HARDENING": 0.55, "DECOMPOSITION_HELPER_EXTRACT": 0.45},
    "complexity_or_loc": {"DECOMPOSITION_HELPER_EXTRACT": 0.85, "SURGICAL_LOCAL_PATCH": 0.65, "ISOLATED_SUBAGENT_SLICE": 0.60, "TEST_ORACLE_HARDENING": 0.45},
    "coverage_or_mutation": {"TEST_ORACLE_HARDENING": 0.85, "SURGICAL_LOCAL_PATCH": 0.65, "DECOMPOSITION_HELPER_EXTRACT": 0.55, "ISOLATED_SUBAGENT_SLICE": 0.50},
    "high_context_or_multifile": {"ISOLATED_SUBAGENT_SLICE": 0.88, "SURGICAL_LOCAL_PATCH": 0.70, "TEST_ORACLE_HARDENING": 0.50, "DECOMPOSITION_HELPER_EXTRACT": 0.40},
    "doc_track": {"OP_DOC_ALIGN": 0.90},
}

def compute_structural_ast_hash(source: str, rel_path: str = "") -> str:
    """Calcola hash strutturale AST (<10ms) ignorando whitespace/commenti sui .py."""
    if rel_path.endswith(".py") or not rel_path:
        try:
            return hashlib.sha256(ast.dump(ast.parse(source), include_attributes=False).encode("utf-8")).hexdigest()
        except SyntaxError:
            pass
    return hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest()

class NoveltyGate:
    """Filtro AST/hash sub-10ms che scarta patch duplicate prima della suite C1/C2."""
    def __init__(self, initial_hashes: Optional[Sequence[str]] = None) -> None:
        self._seen: Set[str] = set(initial_hashes or ())

    def fingerprint(self, files_map: Dict[str, str]) -> str:
        raw = "|".join(f"{k}:{compute_structural_ast_hash(txt, k)}" for k, txt in sorted(files_map.items()))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_novel(self, files_map: Dict[str, str], *, register: bool = True) -> Tuple[bool, str]:
        fp = self.fingerprint(files_map)
        if fp in self._seen:
            return False, fp
        if register:
            self._seen.add(fp)
        return True, fp

def _secondary_vals(sec: Any) -> Tuple[float, ...]:
    if isinstance(sec, dict):
        return tuple(safe_finite_float(v, 0.0) for _, v in sorted(sec.items()))
    return tuple(safe_finite_float(v, 0.0) for v in sec) if isinstance(sec, (list, tuple)) else (0.0,)

def _dominates(va: Tuple[float, ...], vb: Tuple[float, ...]) -> bool:
    return len(va) == len(vb) and all(a >= b - 1e-12 for a, b in zip(va, vb)) and any(a > b + 1e-12 for a, b in zip(va, vb))

class ParetoArchive:
    """Archivio Pareto non-dominato limitato per nicchia (footprint x delta_cc)."""
    def __init__(self, max_size: int = 0, workspace_root: Optional[Union[str, Path]] = None) -> None:
        cfg_max = int(get_bandit_config(workspace_root).get("pareto_archive_max", 12))
        self.max_size = max(1, min(12, int(max_size if max_size > 0 else cfg_max)))
        self.entries: List[Dict[str, Any]] = []

    @staticmethod
    def niche_key(file_count: int, delta_cc: int) -> Tuple[int, int]:
        return (min(4, max(0, file_count) // 2), min(4, max(0, delta_cc) // 3))

    def _evict_crowded(self) -> None:
        counts: Dict[Tuple[int, int], int] = {}
        for e in self.entries:
            counts[e["niche"]] = counts.get(e["niche"], 0) + 1
        self.entries.remove(min(self.entries, key=lambda e: (-counts[e["niche"]], e["score"])))

    def add_feasible(self, entry: Dict[str, Any]) -> bool:
        updated = pareto_add_node(self.entries, entry, self.max_size, self.niche_key, _secondary_vals, _dominates, safe_finite_float)
        if updated is None:
            return False
        self.entries = updated
        if len(self.entries) > self.max_size:
            self._evict_crowded()
        return True

def wilson_lcb_95(successes: float, trials: float, z: float = 1.96) -> float:
    """Restituisce Wilson LCB onesto (0.0 quando trials <= 0 o non finito)."""
    s, n = safe_finite_float(successes, -1.0), safe_finite_float(trials, -1.0)
    if n <= 0.0 or s < 0.0:
        return 0.0
    p_hat, z2 = max(0.0, min(1.0, s / n)), z * z
    rad = z * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
    return round(max(0.0, min(1.0, (p_hat + z2 / (2.0 * n) - rad) / (1.0 + z2 / n))), 6)

def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    d = 1e-30 if abs(1.0 - qab * x / qap) < 1e-30 else 1.0 / (1.0 - qab * x / qap)
    c, h = 1.0, d
    for m in range(1, 160):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1e-30 if abs(1.0 + aa * d) < 1e-30 else 1.0 / (1.0 + aa * d)
            c = 1e-30 if abs(1.0 + aa / c) < 1e-30 else (1.0 + aa / c)
            h *= d * c
            if aa < 0 and abs(d * c - 1.0) < 1e-12:
                return h
    return h

def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0 or x >= 1.0:
        return 0.0 if x <= 0.0 else 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    return (bt * _betacf(a, b, x) / a) if x < (a + 1.0) / (a + b + 2.0) else (1.0 - bt * _betacf(b, a, 1.0 - x) / b)

def jeffreys_lcb_90_stochastic(successes: float, trials: float) -> float:
    """Quantile esatto Beta(s+0.5, n-s+0.5) al 10% in stdlib (zero scipy)."""
    return beta_quantile_bisect(_betainc, successes, trials, safe_finite_float, 0.10)

def select_prior_signature(
    *, sast_critical: int = 0, tests_failed: int = 0, cc_or_loc_issue: bool = False,
    k_mut: float = 1.0, c_branch: float = 1.0, acs_zone: ACSZoneLiteral = "Z0", file_count: int = 1, is_doc_track: bool = False,
) -> str:
    """Seleziona deterministicamente la firma di prior Pi_0."""
    if is_doc_track:
        return "doc_track"
    if acs_zone in ("Z1", "Z2") or file_count >= 3:
        return "high_context_or_multifile"
    if sast_critical > 0 or tests_failed > 0:
        return "sast_or_test_local"
    return "complexity_or_loc" if cc_or_loc_issue else ("coverage_or_mutation" if (k_mut < 0.85 or c_branch < 0.82) else "sast_or_test_local")

def _compute_operator_posteriors(
    history: Sequence[Dict[str, Any]], allowed_ops: Sequence[MacroOperatorLiteral],
    prior_sig: str, gamma: float = 0.92, m0: float = 4.0,
) -> Dict[MacroOperatorLiteral, Dict[str, float]]:
    prior_map = _PRIOR_TABLES.get(prior_sig, _PRIOR_TABLES["sast_or_test_local"])
    stats: Dict[MacroOperatorLiteral, Dict[str, float]] = {}
    n_hist = len(history)
    for op in allowed_ops:
        p0 = float(prior_map.get(op, 0.5))
        d_rew, d_acc, d_n, raw_s, raw_n = 0.0, 0.0, 0.0, 0.0, 0.0
        for idx, rec in enumerate(history):
            if rec.get("operator") != op:
                continue
            acc_v = 1.0 if rec.get("accepted") else 0.0
            rew_v = max(0.0, min(1.0, safe_finite_float(rec.get("reward"), acc_v)))
            w = gamma ** max(0, (n_hist - 1) - idx)
            d_rew, d_acc, d_n, raw_s, raw_n = d_rew + w * rew_v, d_acc + w * acc_v, d_n + w, raw_s + acc_v, raw_n + 1.0
        stats[op] = {"p0": p0, "alpha": m0 * p0 + d_rew, "beta": m0 * (1.0 - p0) + max(0.0, d_n - d_rew), "alpha_acc": m0 * p0 + d_acc, "beta_acc": m0 * (1.0 - p0) + max(0.0, d_n - d_acc), "raw_s": raw_s, "raw_n": raw_n}
    return stats

def _compute_calibration_metrics(history: Sequence[Dict[str, Any]], brier_cap: float = 0.25, mae_cap: float = 0.35) -> Tuple[Optional[float], Optional[float], bool]:
    recent = [r for r in history[-50:] if r.get("predicted_accept_prob") is not None]
    if len(recent) < 12:
        return None, None, False
    probs = [max(0.0, min(1.0, safe_finite_float(r.get("predicted_accept_prob"), 0.5))) for r in recent]
    ys = [1.0 if r.get("accepted") else 0.0 for r in recent]
    brier = sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(recent)
    mae = sum(abs(p - y) for p, y in zip(probs, ys)) / len(recent)
    return round(brier, 6), round(mae, 6), (brier > brier_cap or mae > mae_cap)

def compute_voi_stop(
    *, n_samples: int, g_hard: int, iteration: int, q_star: float, expected_improvement_k: float,
    elapsed_s: float = 0.0, time_budget_s: float = 120.0, max_iters: int = 4, warm_max_n: int = 30,
) -> Tuple[Optional[float], bool]:
    """VoI normalizzato su (100 - Q* + eps) attivo SOLO con N>=warm_max_n, g_hard==1, k>=2."""
    if n_samples < warm_max_n or g_hard != 1 or iteration < 2:
        return None, False
    gap = max(1e-6, 100.0 - max(0.0, min(100.0, safe_finite_float(q_star, 0.0))))
    voi_norm = max(0.0, safe_finite_float(expected_improvement_k, 0.0)) / gap
    delta_b = max(max(0.0, safe_finite_float(elapsed_s, 0.0)) / max(1.0, float(time_budget_s)), 1.0 / max(1, int(max_iters)))
    return round(voi_norm, 6), bool(voi_norm < delta_b)

def select_operator_cold_warm(
    history: Sequence[Dict[str, Any]], allowed_ops: Sequence[MacroOperatorLiteral], *,
    prior_sig: str, session_id: str, step_seq: int, iteration: int, ledger_tail_hash: str,
    g_hard: int = 1, q_star: float = 0.0, expected_improvement_k: float = 5.0,
    elapsed_s: float = 0.0, max_iters: int = 4, key_path: Optional[Path] = None, workspace_root: Optional[Union[str, Path]] = None,
) -> ColdWarmDecision:
    """Seleziona il macro-operatore rispettando il gate progressivo COLD / WARM / CALIBRATED."""
    b_cfg = get_bandit_config(workspace_root)
    cold_max, warm_max = int(b_cfg.get("cold_max_n", 12)), int(b_cfg.get("warm_max_n", 30))
    gamma, m0, c_ucb = float(b_cfg.get("decay_gamma", 0.92)), float(b_cfg.get("prior_strength_m0", 4.0)), float(b_cfg.get("ucb_cold_c", 0.25))
    verified = [r for r in history if int(bool(r.get("dry_run", 0))) == 0 and int(r.get("deception_gaming_count", r.get("gaming", 0))) == 0]
    n_samples = len(verified)
    regime: StatisticalRegimeLiteral = "COLD" if n_samples < cold_max else ("WARM_BANDIT" if n_samples < warm_max else "CALIBRATED_VOI")
    stats = _compute_operator_posteriors(verified, allowed_ops, prior_sig, gamma=gamma, m0=m0)
    ucb_scores = {op: ((m0 * st["p0"] + st["raw_n"] * ((st["raw_s"] / st["raw_n"]) if st["raw_n"] > 0 else 0.0)) / (m0 + st["raw_n"])) + c_ucb * math.sqrt(math.log(n_samples + 2.0) / (st["raw_n"] + 1.0)) for op, st in stats.items()}
    brier, mae, cal_degraded = _compute_calibration_metrics(verified, float(b_cfg.get("brier_circuit_breaker", 0.25)), float(b_cfg.get("mae_circuit_breaker", 0.35))) if regime == "CALIBRATED_VOI" else (None, None, False)
    seed_digest: Optional[str] = None
    if regime == "COLD":
        best_op = max(allowed_ops, key=lambda op: (ucb_scores[op], stats[op]["p0"]))
    else:
        seed = derive_hmac_seed_int(f"thompson:{session_id}:{iteration}:{step_seq}:{ledger_tail_hash}", key_path=key_path)
        seed_digest = hashlib.sha256(str(seed).encode("ascii")).hexdigest()
        rng = random.Random(seed)
        draws = {op: rng.betavariate(stats[op]["alpha"], stats[op]["beta"]) for op in allowed_ops}
        if cal_degraded:
            draws = {op: 0.5 * draws[op] + 0.5 * ucb_scores[op] for op in allowed_ops}
        best_op = max(allowed_ops, key=lambda op: (draws[op], ucb_scores[op]))
    st_b = stats[best_op]
    voi_ratio, voi_stop = compute_voi_stop(n_samples=n_samples, g_hard=g_hard, iteration=iteration, q_star=q_star, expected_improvement_k=expected_improvement_k, elapsed_s=elapsed_s, max_iters=max_iters, warm_max_n=warm_max)
    return ColdWarmDecision(
        regime=regime, n_samples=n_samples, selected_operator=best_op, allowed_operators=tuple(allowed_ops),
        predicted_accept_prob=round(st_b["alpha_acc"] / (st_b["alpha_acc"] + st_b["beta_acc"]), 6),
        wilson_lcb_95=wilson_lcb_95(st_b["raw_s"], st_b["raw_n"]), lcb_90_stochastic=jeffreys_lcb_90_stochastic(st_b["raw_s"], st_b["raw_n"]),
        ucb_score=round(ucb_scores[best_op], 6), thompson_seed_digest=seed_digest, brier_score=brier, mae_score=mae, calibration_degraded=cal_degraded, voi_ratio=voi_ratio, voi_should_stop=voi_stop,
    )

def check_conservation_invariants(base_counts: Dict[str, int], curr_counts: Dict[str, int], *, approved_reduction: bool = False) -> Tuple[bool, Tuple[str, ...]]:
    """Verifica gli invarianti di conservazione (tests_total, assert_count, doc_link_count, skill_count)."""
    if approved_reduction:
        return True, ()
    dropped = [f"{k}:{base_counts.get(k, 0)}->{curr_counts.get(k, 0)}" for k in ("tests_total", "assert_count", "doc_link_count", "skill_count") if int(curr_counts.get(k, 0)) < int(base_counts.get(k, 0))]
    return (not dropped), tuple(dropped)

def _format_junit_nodeid(cls_n: str, name: str) -> str:
    if not cls_n:
        return name
    parts = cls_n.split(".")
    return f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{name}" if (len(parts) > 1 and parts[-1][:1].isupper()) else f"{'/'.join(parts)}.py::{name}"

def extract_failed_nodeids_from_junit(xml_path: Path) -> List[str]:
    """Estrae i nodeid falliti da JUnit XML rifiutando <!ENTITY fail-closed."""
    if not xml_path.is_file():
        return []
    txt = xml_path.read_text(encoding="utf-8-sig")
    if "<!ENTITY" in txt.upper():
        raise ValueError(f"Dichiarazione XML ENTITY non consentita: {xml_path}")
    failed: List[str] = []
    for tc in ET.fromstring(txt).iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            nodeid = _format_junit_nodeid(tc.attrib.get("classname", ""), tc.attrib.get("name", ""))
            if nodeid and nodeid not in failed:
                failed.append(nodeid)
    return failed

def classify_flaky_nodeids(
    failed_nodeids: Sequence[str], rerun_fn: Optional[Callable[[str], bool]] = None, *, reruns: int = 0, cwd: Optional[Path] = None
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Riesegue in NVMe isolato i nodeid falliti; marca flaky se passes > 0."""
    eff_r = max(1, int(reruns if reruns > 0 else int(get_bandit_config(cwd).get("flaky_rerun_count", 3))))
    root_w = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    runner = rerun_fn or (lambda nid: bool(run_detached_pytest(root_w, targets=(nid,), extra_args=("-q", "--tb=short"), timeout_sec=60.0, apply_overlay=True).get("success", False)))
    flaky, consistent = [], []
    for nid in failed_nodeids:
        (flaky if sum(1 for _ in range(eff_r) if runner(nid)) > 0 else consistent).append(nid)
    return tuple(flaky), tuple(consistent)
