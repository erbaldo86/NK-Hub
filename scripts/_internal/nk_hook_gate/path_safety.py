"""Canonicalizzazione percorsi, blocco NTFS ADS/reparse e whitelist staging."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from _internal.nk_hook_gate.constants import (
    _PROD_DIR_PREFIXES,
    _SAFE_DIR_COMPONENTS,
    _SAFE_ROOT_FILENAMES,
    _WORKSPACE_ROOT,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.json_io import _is_path_reparse_point

_SAFE_TEMP_PREFIXES = ("%temp%/", "$env:temp/", "${env:temp}/", "/tmp/")
_SAFE_TEMP_MARKERS = ("appdata/local/temp/", ".gemini/antigravity/brain/")
_PS_ENV_PREFIX_RE = re.compile(
    r"^(?:\$env:[A-Za-z0-9_]+|\$\{env:[^}:/\\]+\})(?=$|[/\\])",
    re.IGNORECASE,
)


def _is_safe_temp_marker_path(norm_low: str) -> bool:
    """Verifica se un path normalizzato punta a temp/brain senza traversal ne prefissi produzione."""
    if not norm_low or ".." in norm_low or ".wal" in norm_low:
        return False
    if norm_low.startswith(_SAFE_TEMP_PREFIXES):
        return True
    for marker in _SAFE_TEMP_MARKERS:
        if marker in norm_low:
            prefix = norm_low.split(marker, 1)[0]
            if not any(bad in prefix for bad in _PROD_DIR_PREFIXES):
                return True
    return False


def _canonical_path(p: Path | str) -> Path:
    """Normalizza il percorso verificando realpath anche sul primo antenato esistente."""
    raw_s = str(p).strip()
    if raw_s.startswith(("\\\\?\\UNC\\", "//?/UNC/")):
        raw_s = "\\\\" + raw_s[8:]
    elif raw_s.startswith(("\\\\?\\", "//?/", "\\\\.\\", "//./")):
        raw_s = raw_s[4:]
    norm_s = os.path.normpath(raw_s.replace("/", os.sep).replace("\\", os.sep))
    try:
        curr = Path(norm_s)
        missing_parts: List[str] = []
        while not curr.exists() and not curr.is_symlink():
            parent = curr.parent
            if parent == curr:
                break
            missing_parts.append(curr.name)
            curr = parent
        real_anc = Path(os.path.normpath(os.path.realpath(str(curr))))
        for part in reversed(missing_parts):
            real_anc = real_anc / part
        return Path(os.path.normpath(os.path.realpath(str(real_anc))))
    except Exception:
        return Path(norm_s).resolve(strict=False)


def _has_ntfs_ads_stream(raw_target: str) -> bool:
    """Rileva NTFS Alternate Data Streams (:) ignorando drive Windows e prefissi PowerShell $env:."""
    s = _strip_wrapping_quotes(raw_target)
    if s.startswith(("\\\\?\\UNC\\", "//?/UNC/")):
        s = s[8:]
    elif s.startswith(("\\\\?\\", "//?/", "\\\\.\\", "//./")):
        s = s[4:]
    s = _PS_ENV_PREFIX_RE.sub("", s, count=1)
    if len(s) >= 2 and s[0].isalpha() and s[1] == ":":
        s = s[2:]
    return ":" in s


def _resolve_effective_hub_root(project_root: Path) -> Path:
    """Risolve la sottocartella NK_Hub quando project_root punta alla cartella padre."""
    root = _canonical_path(project_root)
    nk_hub_sub = root / "NK_Hub"
    if not (root / "nk_tracking").exists() and nk_hub_sub.is_dir():
        if (
            (nk_hub_sub / "nk_tracking").exists()
            or (nk_hub_sub / ".staging").exists()
            or (nk_hub_sub / "scripts").exists()
        ):
            return _canonical_path(nk_hub_sub)
    return root


def _has_ancestor_reparse_escape(target_str: str, project_root: Path) -> bool:
    """Verifica symlink o reparse point sugli antenati esistenti contro evasioni TOCTOU."""
    cleaned = _strip_wrapping_quotes(target_str)
    if not cleaned:
        return False
    if cleaned.startswith(("\\\\?\\UNC\\", "//?/UNC/")):
        cleaned = "\\\\" + cleaned[8:]
    elif cleaned.startswith(("\\\\?\\", "//?/", "\\\\.\\", "//./")):
        cleaned = cleaned[4:]
    cleaned = cleaned.replace("/", os.sep).replace("\\", os.sep)
    raw_p = Path(os.path.normpath(cleaned))
    proj_canon = _canonical_path(project_root)
    eff_root = _resolve_effective_hub_root(proj_canon)
    if raw_p.is_absolute():
        lex_p = raw_p
    elif raw_p.parts and raw_p.parts[0].lower() == "nk_hub":
        base = proj_canon.parent if proj_canon.name.lower() == "nk_hub" else proj_canon
        lex_p = Path(os.path.normpath(str(base / raw_p)))
    else:
        lex_p = Path(os.path.normpath(str(eff_root / raw_p)))

    lex_parts_low = [pt.lower().rstrip(". ") for pt in lex_p.parts]
    in_lexical_staging = ".staging" in lex_parts_low
    staging_canon = _canonical_path(eff_root / ".staging")

    curr = lex_p
    visited = set()
    while True:
        key = str(curr).lower()
        if (
            key in visited
            or curr == eff_root
            or curr == proj_canon
            or curr.parent == curr
        ):
            break
        visited.add(key)
        if curr.exists() or curr.is_symlink():
            if _is_path_reparse_point(curr):
                real_curr = Path(os.path.normpath(os.path.realpath(str(curr))))
                if in_lexical_staging and (
                    real_curr != staging_canon
                    and staging_canon not in real_curr.parents
                ):
                    return True
                if (
                    real_curr != eff_root
                    and eff_root not in real_curr.parents
                    and real_curr != proj_canon
                    and proj_canon not in real_curr.parents
                ):
                    return True
        curr = curr.parent
    return False


def _resolve_target_path(target_str: str, project_root: Path) -> Path:
    """Risolve e normalizza i segmenti '..' e i prefissi UNC di un target rispetto a project_root."""
    cleaned = _strip_wrapping_quotes(target_str)
    if cleaned.startswith(("\\\\?\\UNC\\", "//?/UNC/")):
        cleaned = "\\\\" + cleaned[8:]
    elif cleaned.startswith(("\\\\?\\", "//?/", "\\\\.\\", "//./")):
        cleaned = cleaned[4:]
    cleaned = cleaned.replace("/", os.sep).replace("\\", os.sep)
    raw_p = Path(os.path.normpath(cleaned))
    if raw_p.is_absolute():
        return _canonical_path(raw_p)
    root = _canonical_path(project_root)
    hub_root = _resolve_effective_hub_root(root)
    if raw_p.parts and raw_p.parts[0].lower() == "nk_hub":
        base = root.parent if root.name.lower() == "nk_hub" else root
        return _canonical_path(base / raw_p)
    cand_direct = _canonical_path(root / raw_p)
    if hub_root != root and not cand_direct.exists():
        return _canonical_path(hub_root / raw_p)
    return cand_direct


def _is_valid_staging_path(cand: Path, project_root: Path) -> bool:
    """Verifica che il percorso canonico risieda realmente sotto la cartella .staging della root."""
    cand_res = _canonical_path(cand)
    root_res = _canonical_path(project_root)
    hub_res = _resolve_effective_hub_root(root_res)
    ws_res = _canonical_path(_WORKSPACE_ROOT)
    for base_root in (root_res, hub_res, root_res / "NK_Hub", ws_res):
        staging_root = _canonical_path(base_root / ".staging")
        if cand_res == staging_root or staging_root in cand_res.parents:
            return True
        if base_root.name.lower() == "nk_hub":
            parent_bridge_stg = _canonical_path(
                base_root.parent / ".staging" / ".agents" / "AGENTS.md"
            )
            parent_bridge_dir = parent_bridge_stg.parent
            if cand_res in (
                parent_bridge_stg,
                parent_bridge_dir,
                parent_bridge_dir.parent,
            ):
                return True
    parts_low = [p.lower().rstrip(". ") for p in cand_res.parts]
    if "nk_external_projects" in parts_low:
        idx = parts_low.index("nk_external_projects")
        if len(parts_low) > idx + 2 and parts_low[idx + 2] == ".staging":
            return True
    return False


def _is_safe_redirection_target(raw_target: str, project_root: Path) -> bool:
    """Verifica se una destinazione di redirezione o output punta a un path temporaneo, nullo o staged sicuro."""
    cleaned = _strip_wrapping_quotes(raw_target)
    if not cleaned or cleaned == "__empty_redirect__" or "`" in raw_target:
        return False
    if _has_ntfs_ads_stream(cleaned):
        return False
    norm = cleaned.replace("\\", "/")
    low = norm.lower()
    if ".." in low or ".wal" in low:
        return False
    if low in ("nul", "/dev/null", "$null"):
        return True
    if _is_safe_temp_marker_path(low):
        return True
    if low.startswith(("nk_diagnostics/", "./nk_diagnostics/")):
        return not _has_ancestor_reparse_escape(cleaned, project_root)
    if "/nk_diagnostics/" in low:
        prefix = low.split("/nk_diagnostics/", 1)[0]
        if any(bad in (prefix + "/") for bad in _PROD_DIR_PREFIXES):
            return False
        if prefix.startswith(("%temp%", "$env:temp", "${env:temp}", "/tmp")):
            return True
    if low.startswith(("%", "$")):
        return False
    if _has_ancestor_reparse_escape(cleaned, project_root):
        return False
    cand = _resolve_target_path(cleaned, project_root)
    if _is_valid_staging_path(cand, project_root):
        return True
    eff_root = _resolve_effective_hub_root(project_root)
    proj_canon = _canonical_path(project_root)
    ws_root = _canonical_path(_WORKSPACE_ROOT)
    in_repo = any(
        cand == br or br in cand.parents for br in (eff_root, proj_canon, ws_root)
    )
    if not in_repo:
        import tempfile

        temp_root = _canonical_path(tempfile.gettempdir())
        if cand == temp_root or temp_root in cand.parents:
            return True
        if "nk_diagnostics" in [p.lower().rstrip(". ") for p in cand.parts]:
            return True
        return False
    for base_r in (eff_root, proj_canon):
        if cand == base_r or base_r in cand.parents:
            try:
                rel_parts = [
                    p.lower().rstrip(". ") for p in cand.relative_to(base_r).parts
                ]
                if rel_parts and rel_parts[0] == "nk_diagnostics":
                    return True
            except ValueError:
                continue
    return False


def _sanitize_staged_tokens_in_cmd(cmd_low: str) -> str:
    """Rimuove dal comando shell i soli token che puntano legittimamente a .staging/ o %TEMP%."""

    def _repl(match: re.Match[str]) -> str:
        tok = match.group(0)
        if ".." in tok or ".wal" in tok:
            return tok
        prefix = tok.split(".staging/", 1)[0]
        if any(bad in prefix for bad in _PROD_DIR_PREFIXES):
            return tok
        return " __staged_safe__ "

    def _repl_temp(match: re.Match[str]) -> str:
        tok = match.group(0)
        if ".." in tok:
            return tok
        norm_tok = tok.lstrip("./\"'")
        if norm_tok.startswith(("%temp%", "$env:temp", "${env:temp}", "/tmp/")):
            return " __temp_safe__ "
        for marker in ("appdata/local/temp", ".gemini/antigravity/brain/"):
            if marker in norm_tok:
                prefix = norm_tok.split(marker, 1)[0]
                if not any(bad in prefix for bad in _PROD_DIR_PREFIXES):
                    return " __temp_safe__ "
        return tok

    norm_cmd = cmd_low.replace("\\", "/")
    sanitized = re.sub(
        r'"[^"\n\r;|&]*?\.staging/[^"\n\r;|&]+"'
        r"|'[^'\n\r;|&]*?\.staging/[^'\n\r;|&]+'"
        r"|(?:^|(?<=[\s\"'=,(\[]))[^\s\"';|&,)\]]*?\.staging/[^\s\"';|&,)\]]+",
        _repl,
        norm_cmd,
    )
    sanitized = re.sub(
        r'"[^"\n\r;|&]*?(?:%temp%|\$env:temp|\$\{env:temp\}|/tmp/|appdata/local/temp|\.gemini/antigravity/brain/)[^"\n\r;|&]*"'
        r"|'[^'\n\r;|&]*?(?:%temp%|\$env:temp|\$\{env:temp\}|/tmp/|appdata/local/temp|\.gemini/antigravity/brain/)[^'\n\r;|&]*'"
        r"|(?:^|(?<=[\s\"'=,(\[]))[^\s\"';|&,)\]]*?(?:%temp%|\$env:temp|\$\{env:temp\}|/tmp/|appdata/local/temp|\.gemini/antigravity/brain/)[^\s\"';|&,)\]]*",
        _repl_temp,
        sanitized,
    )
    return sanitized


def _is_whitelisted_outside_staging(cand: Path, project_root: Path) -> bool:
    """Verifica se un target fuori da .staging/ appartiene alla whitelist esplicita e sicura."""
    cand = _canonical_path(cand)
    cand_norm_posix = cand.as_posix().lower()
    ws_root = _canonical_path(_WORKSPACE_ROOT)
    eff_root = _resolve_effective_hub_root(project_root)
    proj_canon = _canonical_path(project_root)

    in_proj = cand == proj_canon or proj_canon in cand.parents
    in_eff = cand == eff_root or eff_root in cand.parents
    in_ws = cand == ws_root or ws_root in cand.parents

    if not in_proj and not in_eff and not in_ws:
        if ".gemini/antigravity/brain/" in cand_norm_posix:
            return True
        import tempfile

        temp_root = _canonical_path(tempfile.gettempdir())
        if cand == temp_root or temp_root in cand.parents:
            return True

    for base_r in (eff_root, proj_canon, ws_root):
        if cand == base_r or base_r in cand.parents:
            try:
                rel_parts = [
                    p.lower().rstrip(". ") for p in cand.relative_to(base_r).parts
                ]
            except ValueError:
                continue
            if not rel_parts:
                return False
            first = rel_parts[0]
            if first in _SAFE_DIR_COMPONENTS or first.startswith("nk_sandbox_"):
                return True
            if len(rel_parts) >= 2 and rel_parts[:2] in (
                ["nk_tracking", "reports_and_briefs"],
                ["nk_tracking", "anchor"],
                ["nk_tracking", "sessions"],
            ):
                return True
            if len(rel_parts) == 1 and first in _SAFE_ROOT_FILENAMES:
                return True
            if (
                len(rel_parts) == 2
                and first == "nk_docs_and_setup"
                and rel_parts[1] in _SAFE_ROOT_FILENAMES
            ):
                return True
    return False
