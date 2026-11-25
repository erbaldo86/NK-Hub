# -*- coding: utf-8 -*-
"""Preparazione path, caricamento sorgenti ed esecuzione pytest per builder_mutation_gate."""

from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from _internal.builder_mutation_gate.report_builders import (
    MutationGateReport,
    _build_missing_target_report,
    _build_syntax_error_report,
)
from _internal.dast_sandbox_runner.sandbox_fs import _build_sanitized_sandbox_env

try:
    from _internal.nk_common.repo_snapshot_cache import get_repo_snapshot_cache
except ImportError:
    get_repo_snapshot_cache = None  # type: ignore[assignment]

try:
    from platform_runner import safe_subprocess_run
except ImportError:
    from scripts.platform_runner import safe_subprocess_run


def _strip_workspace_prefixes(raw: str, workspace_root: Path) -> str:
    """Rimuove prefissi relativi del workspace e .staging/ in modo dinamico."""
    cleaned = raw[2:] if raw.startswith("./") else raw
    ws_name = workspace_root.resolve().name
    prefixes = [f"{ws_name}/.staging/", f"{ws_name}/"] if ws_name else []
    for base_pref in ("NK_Hub/.staging/", ".staging/", "NK_Hub/"):
        if base_pref not in prefixes:
            prefixes.append(base_pref)
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    if cleaned.startswith(".staging/"):
        cleaned = cleaned[len(".staging/") :]
    return cleaned.lstrip("/")


def _check_ads_and_drive(raw_clean: str, orig: str) -> None:
    """Blocca ADS NTFS ':' e path Windows drive-relative."""
    has_drive = os.name == "nt" and len(raw_clean) >= 2 and raw_clean[0].isalpha() and raw_clean[1] == ":"
    if ":" in (raw_clean[2:] if has_drive else raw_clean):
        raise ValueError(f"NTFS ADS or invalid colon in target path: {orig!r}")
    if has_drive and (len(raw_clean) < 3 or raw_clean[2] not in ("/", "\\")):
        raise ValueError(f"Drive-relative target path forbidden: {orig!r}")


def _validate_raw_target_path(target_rel_path: str) -> str:
    """Valida il path grezzo bloccando vuoto, null-byte, UNC, '..' e ADS ':'."""
    raw_clean = str(target_rel_path).strip()
    if not raw_clean or "\x00" in raw_clean:
        raise ValueError(f"Target path empty or contains null byte: {target_rel_path!r}")
    if raw_clean.startswith(("\\\\", "//")):
        raise ValueError(f"UNC target path forbidden: {target_rel_path!r}")
    _check_ads_and_drive(raw_clean, target_rel_path)
    slash = raw_clean.replace("\\", "/")
    if ".." in [seg for seg in slash.split("/") if seg] or ".." in Path(raw_clean).parts:
        raise ValueError(f"Path traversal '..' forbidden: {target_rel_path!r}")
    return slash


def _ensure_confined_stripped_path(workspace_root: Path, ws_res: Path, rel_raw: str, target_rel_path: str) -> str:
    """Rimuove prefissi .staging/ e verifica che il percorso normalizzato resti confinato."""
    stripped = _strip_workspace_prefixes(rel_raw, workspace_root)
    if not stripped or stripped == ".staging":
        raise ValueError(f"Invalid normalized target path: {target_rel_path!r}")
    norm_res = (ws_res / stripped).resolve()
    if norm_res == ws_res or not norm_res.is_relative_to(ws_res):
        raise ValueError(f"Normalized target escapes workspace root: {target_rel_path!r}")
    return stripped


def _normalize_target_rel_path(workspace_root: Path, target_rel_path: str) -> str:
    """Normalizza target_rel_path rispetto a workspace_root rimuovendo prefissi .staging/."""
    slash = _validate_raw_target_path(target_rel_path)
    ws_res, cand = workspace_root.resolve(), Path(slash)
    cand_res = cand.resolve() if cand.is_absolute() else (ws_res / cand).resolve()
    if cand_res == ws_res or not cand_res.is_relative_to(ws_res):
        raise ValueError(f"Target path escapes workspace root: {target_rel_path!r}")
    rel_raw = cand_res.relative_to(ws_res).as_posix() if cand.is_absolute() else slash
    return _ensure_confined_stripped_path(workspace_root, ws_res, rel_raw, target_rel_path)


def _is_explicit_staged_target(ws_root: Path, stg_dir: Path, target_rel_path: str) -> bool:
    """Rileva se target_rel_path indica esplicitamente un file sotto .staging/."""
    raw = str(target_rel_path).replace("\\", "/").strip()
    if raw.startswith("./"):
        raw = raw[2:]
    cand = Path(raw)
    if cand.is_absolute():
        res_cand = cand.resolve()
        if res_cand.is_relative_to(stg_dir.resolve()):
            return True
        try:
            raw = res_cand.relative_to(ws_root.resolve()).as_posix()
        except ValueError:
            return ".staging" in cand.parts
    ws_name = ws_root.resolve().name
    staged_prefixes = [".staging/", "NK_Hub/.staging/"] + ([f"{ws_name}/.staging/"] if ws_name else [])
    return any(raw.startswith(pref) for pref in staged_prefixes)


def _read_text_via_cache(file_path: Path) -> str:
    """Legge il file tramite RepoSnapshotCache se disponibile, altrimenti da disco."""
    return get_repo_snapshot_cache().get_text(file_path) if get_repo_snapshot_cache is not None else file_path.read_text(encoding="utf-8-sig", errors="replace")


def _read_optional_text(file_path: Path) -> Optional[str]:
    """Legge un file UTF-8 se presente, restituendo None altrimenti."""
    return _read_text_via_cache(file_path) if file_path.is_file() else None


def _check_source_syntax(post_code: str) -> Optional[SyntaxError]:
    """Valida la sintassi del sorgente sfruttando RepoSnapshotCache."""
    if get_repo_snapshot_cache is not None:
        return get_repo_snapshot_cache().parse_source_cached(post_code)[1]
    try:
        ast.parse(post_code)
        return None
    except SyntaxError as exc:
        return exc


def _load_pre_and_post_source(ws_root: Path, stg_dir: Path, rel_target: str, require_staged: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """Carica il sorgente pre-modifica da produzione e post-modifica da staging o root."""
    pre_code = _read_optional_text(ws_root / rel_target)
    post_code = _read_optional_text(stg_dir / rel_target)
    if post_code is None and not require_staged:
        post_code = pre_code
    return pre_code, post_code


def _build_invalid_target_report(target_file: str, detail: str, min_kill_rate: float, t0: float) -> MutationGateReport:
    """Costruisce il rapporto fail-closed quando target_rel_path e invalido."""
    return MutationGateReport(
        status="FAIL", passed=False, baseline_passed=False, target_file=target_file, touched_functions=[],
        mutants_total=0, mutants_killed=0, mutants_survived=0, mutants_timed_out=0, mutants_crashed=0,
        kill_rate=0.0, min_kill_rate=min_kill_rate, budget_exhausted=False, elapsed_sec=round(time.perf_counter() - t0, 4),
        outcomes=[], message=f"Invalid target path: {detail}",
    )


def _prepare_target_source(
    ws_root: Path, stg_dir: Path, target_rel_path: str, min_kill_rate: float, t0: float, *, require_staged: bool = False,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[MutationGateReport]]:
    """Normalizza, carica e valida sintatticamente il sorgente target in modo fail-closed."""
    try:
        rel_target = _normalize_target_rel_path(ws_root, target_rel_path)
    except ValueError as exc:
        return None, None, None, _build_invalid_target_report(str(target_rel_path), str(exc), min_kill_rate, t0)
    staged_req = bool(require_staged) or _is_explicit_staged_target(ws_root, stg_dir, target_rel_path)
    pre_code, post_code = _load_pre_and_post_source(ws_root, stg_dir, rel_target, require_staged=staged_req)
    if post_code is None:
        return None, None, None, _build_missing_target_report(ws_root, rel_target, staged_req, min_kill_rate, t0)
    if (syn_err := _check_source_syntax(post_code)) is not None:
        return None, None, None, _build_syntax_error_report(rel_target, syn_err, min_kill_rate, t0)
    return rel_target, pre_code, post_code, None


def _run_pytest_fail_fast(sandbox_dir: Path, test_targets: Sequence[str], basetemp_dir: Path, timeout_sec: float) -> Tuple[int, float]:
    """Esegue pytest -x -q nella ShadowSandbox su NVMe con ambiente sanitizzato."""
    cmd = [sys.executable, "-B", "-m", "pytest", *[str(t).strip() for t in test_targets if str(t).strip()], "-x", "-q", "--no-header", "-p", "no:cacheprovider", f"--basetemp={basetemp_dir.as_posix()}"]
    hooks_iso = basetemp_dir / "nk_hooks_iso"
    hooks_iso.mkdir(parents=True, exist_ok=True)
    env: Dict[str, str] = _build_sanitized_sandbox_env({
        "PYTHONPATH": str(sandbox_dir),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "NK_HOOKS_TEMP_DIR": str(hooks_iso),
    })
    t0 = time.perf_counter()
    rc, _, _ = safe_subprocess_run(cmd=cmd, cwd=str(sandbox_dir), timeout=timeout_sec, env=env, replace_env=True)
    return rc, round(time.perf_counter() - t0, 4)
