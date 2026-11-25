"""Verifica fail-closed dei holdout dell'oracolo in Shadow Sandbox (profilo evaluator)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import NK_MANDATORY_HUB_LOCKS
from _internal.nk_common.oracle_lock import (
    compute_combined_sha256,
    compute_lf_sha256,
    is_valid_sha256_hex,
    sha256_eol_matches,
    verify_oracle_lock_manifest,
)
from _internal.dast_sandbox_runner.holdout_assets_helpers import (  # noqa: F401
    _HUB_MARKER_DIRS,
    _LOCK_FILENAMES,
    _PROTECTED_EXACT,
    _PROTECTED_PREFIXES,
    _check_extra_sb_holdout_files,
    _check_oracle_holdout_assets,
    _check_overlay_and_tombstones,
    _check_required_holdout_assets,
    _collect_holdout_pair_errors,
    _compare_prod_holdout_file,
    _has_nonempty_holdout_dir,
    _is_external_app_repo,
    _is_protected_holdout_path,
    _validate_holdout_json_file,
    _validate_suite_dir,
)


def _resolve_lock_rel_target(lock_name: str, raw_target: Any, root: Path, sb_dir: Path) -> Path:
    """Risolve il percorso relativo base del manifest lock rispetto alla root del workspace."""
    if isinstance(raw_target, str) and raw_target.strip():
        t_path = Path(raw_target.strip())
        for anchor in (root.resolve(), sb_dir.resolve()):
            try:
                if t_path == anchor or t_path.is_relative_to(anchor):
                    return t_path.relative_to(anchor)
            except (OSError, ValueError):
                pass
        t_low = raw_target.replace("\\", "/").rstrip("/").lower()
        for suffix in (
            "nk_tracking/oracle_holdout",
            "nk_genome/configs/tensor_rsi",
            "scripts/_internal/tensor_rsi",
            "tests",
            ".agents",
            "scripts",
        ):
            if t_low.endswith(f"/{suffix}") or t_low == suffix:
                return Path(suffix)
        if t_low.endswith(f"/{root.name.lower()}") or t_low.endswith(f"/{sb_dir.name.lower()}"):
            return Path(".")
    return Path("tests") if lock_name == "oracle_lock.json" else Path(".")


def _overlaid_lock_result(cand_rel: str) -> Tuple[int, List[str], List[str]]:
    """Valuta un file bloccato sovrascritto da staging permettendo i soli file non protetti."""
    if _is_protected_holdout_path(cand_rel, include_all_tests=True):
        return 0, [cand_rel], [f"overlaid_locked_holdout:{cand_rel}"]
    return 0, [cand_rel], []


def _check_single_locked_entry(
    sb_dir: Path, sb_resolved: Path, rel_key: str, expected_sha: str,
    overlay_set: Set[str], deleted_set: Set[str], rel_target: Path = Path("tests"),
) -> Tuple[int, List[str], List[str]]:
    """Valuta un singolo file protetto nel manifest lock rispetto alla sandbox senza blind spot."""
    cand = (sb_dir / rel_target / rel_key).resolve()
    if cand == sb_resolved or not cand.is_relative_to(sb_resolved):
        return 0, [], [f"escaped_lock_path:{rel_key}"]
    cand_rel = cand.relative_to(sb_resolved).as_posix()
    cand_rel_low = cand_rel.lower()
    ov_low = {s.replace("\\", "/").lstrip("/").lower() for s in overlay_set}
    del_low = {s.replace("\\", "/").lstrip("/").lower() for s in deleted_set}
    if cand_rel_low in del_low:
        return 0, [], [f"deleted_locked:{cand_rel}"]
    if cand_rel_low in ov_low:
        return _overlaid_lock_result(cand_rel)
    if not cand.is_file():
        return 0, [], [f"missing_locked:{cand_rel}"]
    if not sha256_eol_matches(cand, expected_sha):
        return 0, [], [f"modified_locked:{cand_rel}"]
    return 1, [], []


def _verify_prod_extra_lock(
    lock_name: str, prod_lock: Path, root: Path, lock_data: Dict[str, Any], rel_target: Path
) -> Optional[str]:
    """Verifica l'integrita di un manifest lock aggiuntivo in produzione."""
    if rel_target != Path(".") and (root / rel_target).exists():
        res = verify_oracle_lock_manifest(prod_lock, root / rel_target)
        return _format_prod_extra_err(lock_name, res)

    saved_files = lock_data.get("files")
    saved_comb = lock_data.get("combined_sha256")
    if not isinstance(saved_files, dict) or not saved_files or not is_valid_sha256_hex(saved_comb):
        return f"Schema non valido in {lock_name} produzione"
    root_res = root.resolve()
    eff_map: Dict[str, str] = {}
    for raw_k, exp_sha in saved_files.items():
        if not is_valid_sha256_hex(exp_sha):
            return f"Digest non valido in {lock_name} per {raw_k}"
        cand = (root_res / rel_target / str(raw_k)).resolve()
        if not cand.is_relative_to(root_res) or not sha256_eol_matches(cand, str(exp_sha)):
            return f"Mismatch produzione in {lock_name}: {raw_k}"
        eff_map[str(raw_k)] = compute_lf_sha256(cand)
    if compute_combined_sha256(eff_map) != str(saved_comb).lower():
        return f"Mismatch combined_sha256 produzione in {lock_name}"
    return None


def _format_prod_extra_err(lock_name: str, res: Dict[str, Any]) -> Optional[str]:
    """Normalizza il prefisso lock_name nell'errore restituito da verify_oracle_lock_manifest."""
    if res.get("passed"):
        return None
    status_msg = str(res.get("status") or "").replace("oracle_lock", lock_name.removesuffix(".json"))
    return f"Integrita {lock_name} produzione fallita: {status_msg}"


def _load_and_compare_lock_pair(
    lock_name: str, prod_lock: Path, sb_lock: Path
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Carica i manifest lock di produzione e sandbox verificandone l'equivalenza."""
    errors: List[str] = []
    try:
        prod_data = json.loads(prod_lock.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [f"JSON corrotto in {lock_name}: {exc}"]
    if not isinstance(prod_data, dict) or not isinstance(prod_data.get("files"), dict):
        return None, [f"Schema non valido in {lock_name}"]
    try:
        sb_data = json.loads(sb_lock.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [f"JSON corrotto in {lock_name} sandbox: {exc}"]
    if not isinstance(sb_data, dict) or sb_data.get("files") != prod_data.get("files") or sb_data.get("combined_sha256") != prod_data.get("combined_sha256"):
        errors.append(f"Manifest lock alterato in sandbox: nk_tracking/{lock_name}")
    return prod_data, errors


def _missing_both_locks_result(
    lock_name: str, is_mandatory: bool
) -> Tuple[int, List[str], List[str], List[str], bool]:
    """Restituisce l'esito fail-closed o skip quando il file lock manca in prod e sandbox."""
    if is_mandatory:
        return 0, [], [], [f"Manifest lock obbligatorio mancante: nk_tracking/{lock_name}"], False
    return 0, [], [], [], True


def _verify_single_lock_manifest(
    lock_name: str, root: Path, sb_dir: Path, overlay_set: Set[str], deleted_set: Set[str],
    *, is_mandatory: bool = False,
) -> Tuple[int, List[str], List[str], List[str], bool]:
    """Verifica produzione + sandbox di un manifest lock su tutte le voci bloccate."""
    prod_lock, sb_lock = root / "nk_tracking" / lock_name, sb_dir / "nk_tracking" / lock_name
    if not prod_lock.is_file() and not sb_lock.is_file():
        return _missing_both_locks_result(lock_name, is_mandatory)
    if not prod_lock.is_file():
        return 0, [], [], [f"Manifest lock non autorizzato solo in sandbox: nk_tracking/{lock_name}"], False
    if not sb_lock.is_file():
        return 0, [], [], [f"Manifest lock mancante in sandbox: nk_tracking/{lock_name}"], False

    lock_data, errors = _load_and_compare_lock_pair(lock_name, prod_lock, sb_lock)
    if lock_data is None:
        return 0, [], [], errors, False

    rel_target = _resolve_lock_rel_target(lock_name, lock_data.get("target"), root, sb_dir)
    if lock_name == "oracle_lock.json":
        prod_res = verify_oracle_lock_manifest(prod_lock, root / rel_target)
        prod_ok = bool(prod_res.get("passed"))
        if not prod_ok:
            errors.append(f"Integrita oracle_lock produzione fallita: {prod_res.get('status')}")
    else:
        extra_err = _verify_prod_extra_lock(lock_name, prod_lock, root, lock_data, rel_target)
        prod_ok = extra_err is None
        if extra_err:
            errors.append(extra_err)

    sb_resolved, saved_files = sb_dir.resolve(), lock_data["files"]
    if not saved_files:
        errors.append(f"Mappa files vuota in {lock_name}")
    verified_count, overlaid, mismatches = 0, [], []
    for rel_key, expected_sha in saved_files.items():
        v, ov, mm = _check_single_locked_entry(
            sb_dir, sb_resolved, str(rel_key), str(expected_sha), overlay_set, deleted_set, rel_target=rel_target
        )
        verified_count += v
        overlaid.extend(ov)
        mismatches.extend(mm)
    return verified_count, overlaid, mismatches, errors, prod_ok


def _verify_sandbox_lock_entries(
    sb_dir: Path, overlay_set: Set[str], deleted_set: Set[str]
) -> Tuple[int, List[str], List[str], List[str]]:
    """Verifica gli SHA-256 dei file protetti in oracle_lock.json nella sandbox."""
    sb_lock_file = sb_dir / "nk_tracking" / "oracle_lock.json"
    if not sb_lock_file.is_file():
        return 0, [], [], []
    verified_count, overlaid, mismatches, errors = 0, [], [], []
    sb_resolved = sb_dir.resolve()
    try:
        lock_data = json.loads(sb_lock_file.read_text(encoding="utf-8-sig"))
        saved_files = lock_data.get("files", {}) if isinstance(lock_data, dict) else {}
        rel_target = _resolve_lock_rel_target("oracle_lock.json", lock_data.get("target"), sb_dir, sb_dir)
        for rel_key, expected_sha in (saved_files.items() if isinstance(saved_files, dict) else ()):
            v, ov, mm = _check_single_locked_entry(sb_dir, sb_resolved, str(rel_key), str(expected_sha), overlay_set, deleted_set, rel_target=rel_target)
            verified_count, overlaid, mismatches = verified_count + v, overlaid + ov, mismatches + mm
    except Exception as exc:
        errors.append(f"Errore verifica manifest sandbox: {exc}")
    return verified_count, overlaid, mismatches, errors


def _is_full_hub_repo(root: Path) -> bool:
    """Riconosce la struttura reale di NK_Hub per rendere obbligatori tutti i lock Hub."""
    return (
        (root / ".agents" / "skills").is_dir()
        and (root / "nk_genome").is_dir()
        and (root / "scripts" / "tensor_rsi.py").is_file()
    )


def _run_all_lock_verifications(
    root: Path, sb_dir: Path, overlay_set: Set[str], deleted_set: Set[str]
) -> Tuple[int, List[str], List[str], List[str], bool, List[str]]:
    """Esegue la verifica completa su tutti i manifest lock Hub obbligatori e opzionali presenti."""
    verified_count, overlaid_locked, mismatches, errors, checked_locks = 0, [], [], [], []
    prod_oracle_ok = True
    mandatory_set = frozenset(NK_MANDATORY_HUB_LOCKS) if _is_full_hub_repo(root) else frozenset({"oracle_lock.json"})
    for lock_name in _LOCK_FILENAMES:
        is_mandatory = lock_name in mandatory_set
        if not is_mandatory and not ((root / "nk_tracking" / lock_name).is_file() or (sb_dir / "nk_tracking" / lock_name).is_file()):
            continue
        checked_locks.append(lock_name)
        vc, ov, mm, lk_errs, p_ok = _verify_single_lock_manifest(
            lock_name, root, sb_dir, overlay_set, deleted_set, is_mandatory=is_mandatory
        )
        verified_count += vc
        overlaid_locked.extend(ov)
        mismatches.extend(mm)
        errors.extend(lk_errs)
        if not p_ok:
            prod_oracle_ok = False
    return (
        verified_count,
        list(dict.fromkeys(overlaid_locked)),
        list(dict.fromkeys(mismatches)),
        errors,
        prod_oracle_ok,
        checked_locks,
    )


def verify_sandbox_holdouts(
    root: Path, sb_dir: Path, norm_prof: str, overlay_files: List[str], deleted_applied: List[str]
) -> Dict[str, Any]:
    """Valida holdout protetti, manifest di lock e integrita in profilo evaluator."""
    if norm_prof != "evaluator":
        return {"executed": True, "passed": False, "profile": norm_prof, "error": f"--verify-holdout richiede il profilo 'evaluator' (ricevuto: {norm_prof!r})", "mismatches": [], "overlaid_locked_files": []}

    overlay_set = {p.replace("\\", "/").lstrip("/").lower() for p in overlay_files}
    deleted_set = {p.replace("\\", "/").lstrip("/").lower() for p in deleted_applied}
    errors = _check_required_holdout_assets(sb_dir) + _check_overlay_and_tombstones(overlay_set, deleted_applied) + _check_oracle_holdout_assets(root, sb_dir)
    vc, overlaid_locked, mismatches, lk_errs, prod_oracle_ok, checked_locks = _run_all_lock_verifications(root, sb_dir, overlay_set, deleted_set)
    errors.extend(lk_errs)
    passed = (len(errors) == 0) and (len(mismatches) == 0)
    return {
        "executed": True, "passed": passed, "profile": norm_prof, "prod_oracle_lock_passed": prod_oracle_ok,
        "checked_locks": checked_locks, "verified_locked_count": vc, "overlaid_locked_count": len(overlaid_locked),
        "overlaid_locked_files": overlaid_locked, "mismatches": mismatches, "errors": errors,
    }
