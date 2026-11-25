# -*- coding: utf-8 -*-
"""Guardie anti-LFI confinate, blocco UNC/junction, RepoSnapshotCache e vincoli DOM."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Sequence, Tuple

from _internal.nk_common.isolated_test_runner import _is_reparse_entry
from _internal.oracle_evaluator_l3 import _INITIAL_SYSTEM_TEMP
from _internal.oracle_evaluator_l3.expectations import (  # noqa: F401
    _extract_markdown_expectations,
    validate_structured_expectations_impl,
)
from _internal.oracle_evaluator_l3.models_and_dom import (
    ALLOWED_EXPECTED_EXTENSIONS,
    ALLOWED_HTML_EXTENSIONS,
    DOMDeltaItem,
    DOMNode,
    _MD_BULLET_PREFIX_RE,
    _MD_HEADING_RE,
    _NON_HTML_EXT_RE,
    _root_dir,
)

try:
    from _internal.nk_common.repo_snapshot_cache import get_repo_snapshot_cache
except ImportError:
    get_repo_snapshot_cache = None  # type: ignore[assignment]


def _is_unc_or_device_path(raw_path: str) -> bool:
    """Rileva percorsi UNC Win32 (\\\\server\\share, //server/share, \\\\?\\UNC\\) o device."""
    cleaned = str(raw_path or "").strip()
    if not cleaned:
        return False
    norm_slash = cleaned.replace("\\", "/").lower()
    return cleaned.startswith(("\\\\", "//")) or norm_slash.startswith(("//?/unc/", "//./", "//"))


def _validate_non_unc_path(raw_path: str) -> None:
    """Solleva ValueError se il percorso e un UNC Win32 o namespace device."""
    if _is_unc_or_device_path(raw_path):
        raise ValueError(f"LFI blocked: Win32 UNC/device path forbidden: {raw_path}")


def _read_oracle_text(path: Path) -> str:
    """Legge il file sfruttando RepoSnapshotCache se disponibile in staging/prod."""
    if get_repo_snapshot_cache is not None:
        return get_repo_snapshot_cache().get_text(path)
    return path.read_text(encoding="utf-8")


def _extract_candidate_file_str(candidate: str) -> str:
    """Estrae il percorso file base rimuovendo selettori e preservando la lettera di unita."""
    if ":" not in candidate or Path(candidate).suffix.lower() in ALLOWED_EXPECTED_EXTENSIONS:
        return candidate
    parts = candidate.rsplit(":", 2)
    base_str = parts[0]
    if len(base_str) == 1 and len(parts) >= 2:
        base_str = f"{parts[0]}:{parts[1]}"
    return base_str


def _has_traversal_segment(raw_path: str) -> bool:
    """Rileva segmenti di path traversal '..' su separatori POSIX o Windows."""
    return ".." in [seg for seg in re.split(r"[\\/]+", raw_path) if seg]


def _clean_explicit_roots(allowed_roots: Sequence[Path]) -> Tuple[Path, ...]:
    """Valida e risolve le radici esplicite bloccando eventuali path UNC."""
    resolved_list = []
    for raw_r in allowed_roots:
        _validate_non_unc_path(str(raw_r))
        resolved_list.append(Path(raw_r).resolve())
    return tuple(resolved_list)


def _resolve_allowed_oracle_roots(
    allowed_roots: Optional[Sequence[Path]] = None,
) -> Tuple[Path, ...]:
    """Restituisce le radici consentite escludendo qualsiasi percorso UNC."""
    if allowed_roots is not None:
        return _clean_explicit_roots(allowed_roots)
    env_root = os.environ.get("NK_ORACLE_ROOT", "").strip()
    if env_root:
        _validate_non_unc_path(env_root)
        return (Path(env_root).resolve(),)
    return tuple(
        dict.fromkeys(
            (
                _root_dir.resolve(),
                Path.cwd().resolve(),
                Path(tempfile.gettempdir()).resolve(),
                _INITIAL_SYSTEM_TEMP,
            )
        )
    )


def _assert_no_reparse_escape(target: Path, roots: Tuple[Path, ...]) -> None:
    """Blocca junction Win32 o symlink diretti/intermedi verso l'esterno delle radici."""
    curr = target
    while True:
        try:
            curr_res = curr.resolve(strict=False)
        except OSError as exc:
            raise ValueError(f"LFI blocked: invalid oracle path {curr}: {exc}") from exc
        if curr_res in roots:
            break
        if _is_reparse_entry(curr):
            if not curr.is_symlink() or not any(curr_res.is_relative_to(r) for r in roots):
                raise ValueError(f"LFI blocked: symlink/junction outside allowed roots: {target}")
        if curr == curr.parent:
            break
        curr = curr.parent


def _enforce_confined_oracle_path(
    target: Path, allowed_roots: Optional[Sequence[Path]] = None
) -> Path:
    """Blocca path UNC, esterni alle radici consentite, junction e symlink esterni."""
    _validate_non_unc_path(str(target))
    roots = _resolve_allowed_oracle_roots(allowed_roots)
    try:
        resolved = target.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"LFI blocked: invalid oracle path {target}: {exc}") from exc
    _validate_non_unc_path(str(resolved))
    if not any(resolved.is_relative_to(r) for r in roots):
        raise ValueError(f"LFI blocked: path outside allowed roots: {target}")
    _assert_no_reparse_escape(target, roots)
    return resolved


def _matches_disallowed_path_shape(base_str: str) -> bool:
    """Verifica estensioni vietate, percorsi UNC, slash o prefissi drive Win32."""
    if _NON_HTML_EXT_RE.search(base_str) or _is_unc_or_device_path(base_str):
        return True
    if (base_str.startswith(".") or "/" in base_str or "\\" in base_str) and " " not in base_str:
        return True
    return bool(re.match(r"^[a-zA-Z]:[\\/]", base_str))


def _looks_like_disallowed_file_reference(base_str: str) -> bool:
    """Identifica riferimenti a file non HTML per bloccare tentativi di LFI."""
    if not base_str or any(ch in base_str for ch in ("\n", "\r")):
        return False
    return _matches_disallowed_path_shape(base_str)


def _expected_kind_from_path(base_str: str) -> str:
    """Mappa l'estensione del target atteso nel tipo canonico html, md oppure json."""
    ext = Path(base_str).suffix.lower()
    if ext == ".json":
        return "json"
    return "md" if ext == ".md" else "html"


def _read_validated_html_file(
    file_path_str: str, allowed_roots: Optional[Sequence[Path]] = None
) -> str:
    """Legge esclusivamente file .html o .htm confinati bloccando traversal, UNC e LFI."""
    cleaned = file_path_str.strip()
    if not cleaned:
        raise ValueError("Empty HTML file path provided.")
    _validate_non_unc_path(cleaned)
    base_str = _extract_candidate_file_str(cleaned)
    if _has_traversal_segment(cleaned) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in HTML source: {file_path_str}")
    if not base_str.lower().endswith(ALLOWED_HTML_EXTENSIONS):
        raise ValueError(f"Non-HTML file extension blocked (only .html/.htm allowed): {base_str}")
    target = Path(base_str)
    _enforce_confined_oracle_path(target, allowed_roots=allowed_roots)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"HTML file not found: {file_path_str}")
    return _read_oracle_text(target)


def _read_validated_expected_file(
    file_path_str: str, allowed_roots: Optional[Sequence[Path]] = None
) -> Tuple[str, str]:
    """Legge file attesi ammessi e confinati bloccando traversal, UNC ed estensioni vietate."""
    cleaned = file_path_str.strip()
    if not cleaned:
        raise ValueError("Empty expected file path provided.")
    _validate_non_unc_path(cleaned)
    base_str = _extract_candidate_file_str(cleaned)
    if _has_traversal_segment(cleaned) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in expected source: {file_path_str}")
    if not base_str.lower().endswith(ALLOWED_EXPECTED_EXTENSIONS):
        raise ValueError(
            f"Unsupported expected file extension blocked (allowed: .html, .htm, .md, .json): {base_str}"
        )
    target = Path(base_str)
    _enforce_confined_oracle_path(target, allowed_roots=allowed_roots)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Expected file not found: {file_path_str}")
    return _read_oracle_text(target), _expected_kind_from_path(base_str)


def resolve_html_source(
    source_or_path: str, allowed_roots: Optional[Sequence[Path]] = None
) -> str:
    """Risolve una stringa HTML o un file .html/.htm bloccando traversal, UNC e LFI."""
    candidate = source_or_path.strip()
    if not candidate or "<" in candidate or ">" in candidate:
        return source_or_path
    _validate_non_unc_path(candidate)

    base_str = _extract_candidate_file_str(candidate)
    _validate_non_unc_path(base_str)
    if _has_traversal_segment(candidate) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in HTML source: {source_or_path}")

    if base_str.lower().endswith(ALLOWED_HTML_EXTENSIONS):
        p_html = Path(base_str)
        _enforce_confined_oracle_path(p_html, allowed_roots=allowed_roots)
        if p_html.exists() and p_html.is_file():
            return _read_oracle_text(p_html)
        raise FileNotFoundError(f"HTML file not found: {candidate}")

    p_direct, p_base = Path(candidate), Path(base_str)
    if (
        (p_direct.exists() and p_direct.is_file())
        or (p_base.exists() and p_base.is_file())
        or _looks_like_disallowed_file_reference(base_str)
    ):
        raise ValueError(
            f"Non-HTML file read blocked by LFI guard (only .html/.htm allowed): {base_str}"
        )
    return source_or_path


def resolve_expected_source(
    source_or_path: str, allowed_roots: Optional[Sequence[Path]] = None
) -> Tuple[str, str]:
    """Risolve una specifica attesa inline o da file con guardia anti-LFI e blocco UNC."""
    candidate = source_or_path.strip()
    if not candidate:
        return source_or_path, "html"

    if candidate.startswith("{"):
        try:
            if isinstance(json.loads(candidate), dict):
                return source_or_path, "json"
        except json.JSONDecodeError:
            pass

    if "```html" in candidate.lower() or "```htm" in candidate.lower():
        return source_or_path, "md"

    if not candidate.startswith("<") and any(
        _MD_HEADING_RE.match(ln) or _MD_BULLET_PREFIX_RE.match(ln)
        for ln in candidate.splitlines()
    ):
        return source_or_path, "md"

    if "<" in candidate or ">" in candidate:
        return source_or_path, "html"

    _validate_non_unc_path(candidate)
    base_str = _extract_candidate_file_str(candidate)
    _validate_non_unc_path(base_str)
    if _has_traversal_segment(candidate) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in expected source: {source_or_path}")

    if base_str.lower().endswith(ALLOWED_EXPECTED_EXTENSIONS):
        p_exp = Path(base_str)
        _enforce_confined_oracle_path(p_exp, allowed_roots=allowed_roots)
        if p_exp.exists() and p_exp.is_file():
            return _read_oracle_text(p_exp), _expected_kind_from_path(base_str)
        raise FileNotFoundError(f"Expected file not found: {candidate}")

    p_direct, p_base = Path(candidate), Path(base_str)
    if (
        (p_direct.exists() and p_direct.is_file())
        or (p_base.exists() and p_base.is_file())
        or _looks_like_disallowed_file_reference(base_str)
    ):
        raise ValueError(
            f"Disallowed expected file reference blocked (allowed: .html, .htm, .md, .json): {base_str}"
        )
    return source_or_path, "html"
