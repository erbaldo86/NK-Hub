# -*- coding: utf-8 -*-
"""Scanner multi-repo dell'ecosistema, ownership .staging/ fail-closed e PATCH_NOTES head."""

from __future__ import annotations

import difflib
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_common.epistemic_firewall_rules import redact_pii_deterministic
from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.paths import (
    is_nk_proget_locale_path,
    is_nk_proget_online_path,
    resolve_nk_proget_roots,
)
from _internal.nk_session_handoff.constants import _NK_REPO_MARKERS, _workspace_root, resolve_session_tracking_dir
from _internal.nk_session_handoff.ecosystem_helpers import (  # noqa: F401
    _AP14_FREE_TEXT_RE, _AP14_TOK_ALT, _PATCH_SECTION_RE, _STAGING_IGNORED_EXTS, _STAGING_IGNORED_NAMES, _T12_HEAD_SMUGGLE_RE, _build_exempt_cid_set, _clean_str,
    _collect_staging_raw_items, _entry_stat_item, _first_rec_ts_ns, _inspect_anchor_tail_writers, _inspect_latest_handoff_writer, _inspect_tracking_state,
    _is_concurrent_ts, _load_json_dict, _parse_ts_ns, _read_tail_lines, _scandir_safe, _scrub_handoff_free_text, _trim_excerpt_clean,
)
from _internal.nk_session_handoff.session_state import _compute_workspace_state_sha256, _hash_file_cached, _read_fastguard_session_start_ns, resolve_baseline_verification_source

_FACADES = ("nk_session_handoff", "scripts.nk_session_handoff")


def _pick_existing_hub(candidates: Sequence[Path], eff_ws_root: Path) -> Path:
    """Seleziona il primo candidato NK_Hub esistente o usa eff_ws_root."""
    for sib in candidates:
        if (sib / "scripts").is_dir() or sib.is_dir():
            return sib.resolve()
    return eff_ws_root


def _resolve_external_project_hub(cand: Path, eff_ws_root: Path) -> Optional[Path]:
    """Risolve NK_Hub per progetti in NK_External_Projects o NK Proget/Locale."""
    if cand.parent.name == "NK_External_Projects":
        return _pick_existing_hub((cand.parent.parent / "NK_Hub",), eff_ws_root)
    if is_nk_proget_locale_path(cand) and cand.parent.name.lower() == "locale":
        base = cand.parent.parent.parent
        return _pick_existing_hub((base / "Antigravity" / "NK_Hub", base / "NK_Hub"), eff_ws_root)
    return None


def resolve_hub_and_project_roots(raw_root: Path) -> Tuple[Path, Path]:
    """Risolve (hub_root, project_root) preservando parent_ws -> NK_Hub e repo esterni."""
    eff_ws_root = Path(resolve_facade_attr(_FACADES, "_workspace_root", _workspace_root)).resolve()
    cand = Path(raw_root).resolve()
    if (ext_hub := _resolve_external_project_hub(cand, eff_ws_root)) is not None:
        return ext_hub, cand
    if not (cand / "scripts").is_dir() and (cand / "NK_Hub" / "scripts").is_dir():
        hub_root = (cand / "NK_Hub").resolve()
        return hub_root, hub_root
    return cand, cand


def _iter_ext_dirs(ext_root: Path) -> List[Path]:
    return sorted((p for p in ext_root.iterdir() if p.is_dir() and not p.name.startswith(".") and not p.is_symlink()), key=lambda p: p.name.lower()) if ext_root.is_dir() else []


def _iter_all_ecosystem_ext_dirs(hub_res: Path) -> List[Path]:
    """Raccoglie le directory esterne in NK_External_Projects e NK Proget/Locale escludendo Online."""
    roots: List[Path] = [hub_res.parent / "NK_External_Projects"]
    locale_root, _ = resolve_nk_proget_roots(hub_res)
    if locale_root is not None:
        roots.append(locale_root)
    found: List[Path] = []
    seen: Set[Path] = set()
    for ext_root in roots:
        for ext_p in _iter_ext_dirs(ext_root):
            res_p = ext_p.resolve()
            if res_p in seen or is_nk_proget_online_path(res_p):
                continue
            seen.add(res_p)
            found.append(ext_p)
    return found


def discover_ecosystem_repos_detailed(hub_root: Path, primary_root: Optional[Path] = None, ecosystem_scan: bool = True) -> Tuple[List[Path], List[str]]:
    """Scopre i repo NK dell'ecosistema restituendo anche le cartelle non-NK escluse."""
    hub_res = Path(hub_root).resolve()
    proj_res = Path(primary_root).resolve() if primary_root is not None else hub_res
    if not ecosystem_scan:
        return [proj_res], []
    repos, seen, ignored_non_nk = [hub_res], {hub_res}, []
    for ext_p in _iter_all_ecosystem_ext_dirs(hub_res):
        res_p = ext_p.resolve()
        if res_p not in (proj_res, hub_res) and not any((ext_p / m).exists() for m in _NK_REPO_MARKERS):
            ignored_non_nk.append(ext_p.name)
            continue
        if res_p not in seen:
            repos.append(res_p)
            seen.add(res_p)
    if proj_res not in seen:
        repos.append(proj_res)
    return repos, sorted(ignored_non_nk, key=lambda s: (s.lower(), s))


def discover_ecosystem_repos(hub_root: Path, project_root: Path, ecosystem_scan: bool) -> List[Path]:
    """Scopre i repository target dell'ecosistema ordinati deterministicamente."""
    return discover_ecosystem_repos_detailed(hub_root, project_root, ecosystem_scan)[0]


def _read_transcript_start_ns(transcript_path: Path) -> int:
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as tf:
            non_empty = [s for _ in range(24) if (ln := tf.readline()) and (s := ln.strip())][:12]
    except OSError:
        return 0
    for line in non_empty:
        if (rec := _load_json_dict(line)) is not None and (ts_ns := _first_rec_ts_ns(rec, ("timestamp_ns", "created_at_ns", "created_at", "timestamp", "ts"))) > 0:
            return ts_ns
    return 0


def _read_anchor_start_ns(hub_res: Path, cid: str) -> int:
    sess_dir = resolve_session_tracking_dir(hub_res, cid)
    for anc_p in ([sess_dir / "session_anchor.jsonl"] if sess_dir else []) + [hub_res / "nk_tracking" / "anchor" / "session_anchor.jsonl"]:
        for ln in _read_tail_lines(anc_p):
            if (rec := _load_json_dict(ln)) is None:
                continue
            rcid = _clean_str(rec.get("conversation_id"))
            if cid and (rcid != cid if rcid else anc_p.parent.name != cid):
                continue
            if (ts_ns := _first_rec_ts_ns(rec, ("timestamp_ns", "timestamp", "ts"))) > 0:
                return ts_ns
    return 0


def resolve_session_start_ns(hub_root: Path, conversation_id: str, transcript_path: Optional[Path] = None) -> int:
    """Risolve deterministicamente session_start_ns da fastguard, transcript o session_anchor."""
    hub_res, cid = Path(hub_root).resolve(), _clean_str(conversation_id)
    if (fg_ns := _read_fastguard_session_start_ns(hub_res, cid)) > 0:
        return fg_ns
    if transcript_path is not None and Path(transcript_path).is_file() and (tr_ns := _read_transcript_start_ns(Path(transcript_path))) > 0:
        return tr_ns
    return _read_anchor_start_ns(hub_res, cid)


def _read_file_sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _classify_staging_ownership(rel_sub: str, mtime_ns: int, cond_repo: bool, conc_detected: bool, own_cids: Set[str], session_start_ns: int) -> str:
    if not cond_repo or conc_detected:
        return "EXTERNAL_CONCURRENT"
    is_own_sess = any(rel_sub.startswith(f"sessions/{c}/") or f"/sessions/{c}/" in f"/{rel_sub}" for c in own_cids)
    return "OWN_SESSION" if (is_own_sess or (session_start_ns > 0 and mtime_ns >= session_start_ns)) else "EXTERNAL_CONCURRENT"


def _walk_staging_with_tracking(repo_root: Path, current_cid: str, target_repo_ids: Sequence[str], session_start_ns: int, exempt_cids: Optional[Sequence[str]] = None) -> Tuple[List[Dict[str, Any]], bool, List[str], Optional[str], Optional[str], str]:
    """Esegue walk .staging/ e ispezione tracking in una singola passata."""
    repo_res, cid_clean = Path(repo_root).resolve(), _clean_str(current_cid)
    conc_det, conc_cids, anc_warn, last_cid, rec_sha = _inspect_tracking_state(repo_res, cid_clean, session_start_ns, exempt_cids=exempt_cids)
    staging_dir = repo_res / ".staging"
    if not staging_dir.is_dir() or staging_dir.is_symlink():
        return [], conc_det, conc_cids, anc_warn, last_cid, rec_sha
    cond_repo = repo_res.name in {str(r).strip() for r in target_repo_ids if str(r).strip()}
    own_cids = {c for c in _build_exempt_cid_set(cid_clean, exempt_cids) if not c.startswith("default_")}
    entries: List[Dict[str, Any]] = []
    for rel_sub, ep, fsize, mtime_ns in sorted(_collect_staging_raw_items(staging_dir), key=lambda x: x[0]):
        if not (sha := _hash_file_cached(ep) or _read_file_sha256(ep)):
            continue
        own = _classify_staging_ownership(rel_sub, mtime_ns, cond_repo, conc_det, own_cids, session_start_ns)
        entries.append({"rel_path": f".staging/{rel_sub}", "sha256": sha, "size_bytes": fsize, "mtime_ns": mtime_ns, "ownership": own})
    return entries, conc_det, conc_cids, anc_warn, last_cid, rec_sha

def walk_staging_entries_recursive(repo_root: Path, current_cid: str, target_repo_ids: Sequence[str], session_start_ns: int, exempt_cids: Optional[Sequence[str]] = None) -> Tuple[List[Dict[str, Any]], bool, List[str], Optional[str]]:
    """Walk ricorsivo iterativo su .staging/ con attribuzione ownership fail-closed a 3 condizioni."""
    entries, conc_det, conc_cids, anc_warn, _, _ = _walk_staging_with_tracking(repo_root, current_cid, target_repo_ids, session_start_ns, exempt_cids=exempt_cids)
    return entries, conc_det, conc_cids, anc_warn


def _extract_first_patch_section(lines: List[str]) -> Tuple[str, List[str]]:
    title_raw, sec_lines, in_sec = "", [], False
    for ln in lines:
        if _PATCH_SECTION_RE.match(ln.strip()):
            if not in_sec:
                in_sec, title_raw = True, ln.strip().lstrip("#").strip()
                continue
            break
        if in_sec:
            sec_lines.append(ln)
    if not in_sec:
        sec_lines = [ln for ln in lines if ln.strip()]
    return title_raw, sec_lines


def extract_patch_notes_head(repo_root: Path, max_excerpt_chars: int = 280) -> Dict[str, Any]:
    """Estrae la prima sezione ## [ di PATCH_NOTES.md con redazione PII e scrub AP-14."""
    repo_res = Path(repo_root).resolve()
    empty = {"patch_notes_head": {"present_on_disk": False, "rel_path": None, "patch_notes_sha256": None, "first_section_title": "", "first_section_excerpt": ""}, "redactions_count": 0}
    target_p, rel_p = next(((repo_res / r, r) for r in ("nk_genome/PATCH_NOTES.md", "PATCH_NOTES.md") if (repo_res / r).is_file()), (None, None))
    if target_p is None:
        return empty
    try:
        raw_bytes = target_p.read_bytes()
        sha, lines = hashlib.sha256(raw_bytes).hexdigest(), raw_bytes.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return empty
    title_raw, sec_lines = _extract_first_patch_section(lines)
    title_clean, red_t = redact_pii_deterministic(title_raw)
    exc_clean, red_e = redact_pii_deterministic("\n".join([ln.rstrip() for ln in sec_lines if ln.strip()][:6]).strip())
    return {
        "patch_notes_head": {
            "present_on_disk": True, "rel_path": rel_p, "patch_notes_sha256": sha,
            "first_section_title": _scrub_handoff_free_text(title_clean, include_t12=True),
            "first_section_excerpt": _trim_excerpt_clean(_scrub_handoff_free_text(exc_clean, include_t12=True), max_excerpt_chars),
        },
        "redactions_count": red_t + red_e,
    }


def _scan_single_repo_snapshot(repo_root: Path, hub_root: Path, conversation_id: str, target_repo_ids: Sequence[str], session_start_ns: int) -> Tuple[Dict[str, Any], int]:
    """Esegue la scansione completa dello stato di un singolo repository."""
    repo_res, cid_clean = Path(repo_root).resolve(), _clean_str(conversation_id)
    state_sha = _compute_workspace_state_sha256(repo_res)
    lock_p = repo_res / "nk_tracking" / "oracle_lock.json"
    lock_sha = _read_file_sha256(lock_p) if lock_p.is_file() else None
    staging_entries, conc_det, conc_cids, anc_warn, last_cid, rec_sha = _walk_staging_with_tracking(repo_res, cid_clean, target_repo_ids, session_start_ns)
    base_cnt, _, verified_sess, ver_src = resolve_baseline_verification_source(repo_res, cid_clean, session_start_ns=session_start_ns)
    pn_res = extract_patch_notes_head(repo_res)
    has_ext = any(ent["ownership"] == "EXTERNAL_CONCURRENT" for ent in staging_entries)
    snap = {
        "repo_id": repo_res.name, "repo_root": str(repo_res), "is_external": repo_res != Path(hub_root).resolve(),
        "state_sha256": state_sha, "oracle_lock_status": "PRESENT" if lock_sha else "ABSENT_ON_DISK",
        "oracle_lock_sha256": lock_sha, "staging_dirty": len(staging_entries) > 0, "staging_entries": staging_entries,
        "concurrent_writer_detected": conc_det, "concurrent_writer_cids": conc_cids, "anchor_tail_warning": anc_warn,
        "tracking_drift_detected": bool(conc_det or anc_warn is not None or (rec_sha and rec_sha != state_sha)),
        "tracking_last_conversation_id": last_cid, "tests_baseline_count": int(base_cnt),
        "tests_verified_in_session": bool(verified_sess), "verification_source": ver_src, "patch_notes_head": pn_res["patch_notes_head"],
        "action_policy_hint": "DO_NOT_TOUCH_OR_PROMOTE" if (conc_det or has_ext) else "SAFE",
    }
    return snap, int(pn_res["redactions_count"])


def _scan_ecosystem_snapshots_detailed(hub_root: Path, project_root: Path, ecosystem_scan: bool, conversation_id: str, target_repo_ids: Sequence[str], transcript_path: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """Scansiona i repository target restituendo snapshots, redazioni e dir escluse."""
    hub_res, proj_res = Path(hub_root).resolve(), Path(project_root).resolve()
    repos, ignored_non_nk = discover_ecosystem_repos_detailed(hub_res, proj_res, ecosystem_scan)
    sess_start_ns = resolve_session_start_ns(hub_res, conversation_id, transcript_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda r: _scan_single_repo_snapshot(r, hub_res, conversation_id, target_repo_ids, sess_start_ns), repos))
    return [snap for snap, _ in results], sum(cnt for _, cnt in results), ignored_non_nk

def scan_ecosystem_snapshots(hub_root: Path, project_root: Path, ecosystem_scan: bool, conversation_id: str, target_repo_ids: Sequence[str], transcript_path: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Scansiona in parallelo (ThreadPoolExecutor max_workers=4) tutti i repository target."""
    snaps, red_cnt, _ = _scan_ecosystem_snapshots_detailed(hub_root, project_root, ecosystem_scan, conversation_id, target_repo_ids, transcript_path)
    return snaps, red_cnt


def build_staging_diffs_for_continuation(repo_snapshots: Sequence[Dict[str, Any]], max_diff_chars: int = 4000) -> Tuple[List[Dict[str, Any]], int]:
    """Costruisce i diff di continuazione rispettando il blocco fail-closed EXTERNAL_CONCURRENT."""
    diffs: List[Dict[str, Any]] = []
    total_red = 0
    for snap in repo_snapshots:
        repo_id, repo_root = str(snap["repo_id"]), Path(str(snap["repo_root"]))
        for entry in snap.get("staging_entries", []):
            rel_p, own = str(entry["rel_path"]), str(entry["ownership"])
            if own == "EXTERNAL_CONCURRENT":
                diffs.append({"repo_id": repo_id, "rel_path": rel_p, "sha256": str(entry["sha256"]), "ownership": own, "action_policy": "DO_NOT_TOUCH_OR_PROMOTE", "diff_patch": None})
                continue
            sub_rel = rel_p[len(".staging/") :] if rel_p.startswith(".staging/") else rel_p
            stg_f, prod_f, patch_val = repo_root / ".staging" / sub_rel, repo_root / sub_rel, None
            try:
                prod_ln = prod_f.read_text(encoding="utf-8", errors="replace").splitlines() if prod_f.is_file() else []
                stg_ln = stg_f.read_text(encoding="utf-8", errors="replace").splitlines()
                raw_d = "\n".join(difflib.unified_diff(prod_ln, stg_ln, fromfile=f"prod/{sub_rel}", tofile=f"staging/{sub_rel}", lineterm=""))
                red_d, r_cnt = redact_pii_deterministic(raw_d[:max_diff_chars])
                total_red += r_cnt
                patch_val = _scrub_handoff_free_text(red_d)
            except OSError:
                pass
            diffs.append({"repo_id": repo_id, "rel_path": rel_p, "sha256": str(entry["sha256"]), "ownership": "OWN_SESSION", "action_policy": "INCLUDE_FOR_CONTINUATION", "diff_patch": patch_val})
    return diffs, total_red
