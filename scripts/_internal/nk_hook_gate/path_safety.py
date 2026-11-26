"""Canonicalizzazione percorsi, blocco NTFS ADS/reparse, Online lock e whitelist staging."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from _internal.nk_common.lane_paths import (
    is_unsafe_lane_staged_token,
    is_valid_lane_plan_rel_parts,
    is_valid_lane_subpath_no_reparse,
    strip_staging_rel_parts,
)
from _internal.nk_common.paths import (
    cmd_mentions_external_project, cmd_mentions_nk_proget_online, is_external_projects_staging_path,
    is_nk_proget_locale_path, is_nk_proget_online_path,
)
from _internal.nk_hook_gate.constants import (
    _PROD_DIR_PREFIXES, _SAFE_DIR_COMPONENTS, _SAFE_ROOT_FILENAMES, _WORKSPACE_ROOT, _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.json_io import _is_path_reparse_point

_SAFE_TEMP_PREFIXES = ("%temp%/", "$env:temp/", "${env:temp}/", "/tmp/")
_SAFE_TEMP_MARKERS = ("appdata/local/temp/", ".gemini/antigravity/brain/")
_PS_ENV_PREFIX_RE = re.compile(
    r"^(?:\$env:[A-Za-z0-9_]+|\$\{env:[^}:/\\]+\})(?=$|[/\\])",
    re.IGNORECASE,
)

_is_nk_proget_online_target = is_nk_proget_online_path
_is_nk_proget_locale_target = is_nk_proget_locale_path
_cmd_mentions_nk_proget_online = cmd_mentions_nk_proget_online
_cmd_mentions_external_project = cmd_mentions_external_project


def _deny_online_readonly() -> Dict[str, Any]:
    """Restituisce il verdetto di blocco fail-closed per target o comandi in NK Proget/Online/."""
    return {
        "decision": "deny",
        "reason_code": "NK_PROGET_ONLINE_READONLY",
        "reason": "Direct write, mutation, or staging inside NK Proget/Online/ is forbidden (read-only production release mirror).",
    }


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
    if nk_hub_sub.is_dir() and (
        (not (root / "scripts").is_dir() and (nk_hub_sub / "scripts").is_dir())
        or (
            not (root / "nk_tracking").exists()
            and ((nk_hub_sub / "nk_tracking").exists() or (nk_hub_sub / ".staging").exists() or (nk_hub_sub / "scripts").exists())
        )
    ):
        return _canonical_path(nk_hub_sub)
    return root


def _is_reparse_escaping_target(
    curr: Path, eff_root: Path, proj_canon: Path, staging_canon: Path, in_lexical_staging: bool
) -> bool:
    """True se curr e un reparse point interno a .staging o con destinazione esterna a root."""
    if not _is_path_reparse_point(curr):
        return False
    if any(pt.lower().rstrip(". ") == ".staging" for pt in curr.parts):
        return True
    real_curr = Path(os.path.normpath(os.path.realpath(str(curr))))
    if in_lexical_staging and real_curr != staging_canon and staging_canon not in real_curr.parents:
        return True
    return real_curr != eff_root and eff_root not in real_curr.parents and real_curr != proj_canon and proj_canon not in real_curr.parents


def _has_ancestor_reparse_escape(target_str: str, project_root: Path) -> bool:
    """Verifica symlink o reparse point sugli antenati esistenti contro evasioni TOCTOU."""
    cleaned = _strip_wrapping_quotes(target_str)
    if not cleaned:
        return False
    if cleaned.startswith(("\\\\?\\UNC\\", "//?/UNC/")):
        cleaned = "\\\\" + cleaned[8:]
    elif cleaned.startswith(("\\\\?\\", "//?/", "\\\\.\\", "//./")):
        cleaned = cleaned[4:]
    raw_p = Path(os.path.normpath(cleaned.replace("/", os.sep).replace("\\", os.sep)))
    proj_canon = _canonical_path(project_root)
    eff_root = _resolve_effective_hub_root(proj_canon)
    if raw_p.is_absolute():
        lex_p = raw_p
    elif raw_p.parts and raw_p.parts[0].lower() == "nk_hub":
        lex_p = Path(os.path.normpath(str((proj_canon.parent if proj_canon.name.lower() == "nk_hub" else proj_canon) / raw_p)))
    else:
        lex_p = Path(os.path.normpath(str(eff_root / raw_p)))

    in_lexical_staging = ".staging" in [pt.lower().rstrip(". ") for pt in lex_p.parts]
    staging_canon = _canonical_path(eff_root / ".staging")
    curr, visited = lex_p, set()
    while True:
        key = str(curr).lower()
        if key in visited or curr in (eff_root, proj_canon) or curr.parent == curr:
            break
        visited.add(key)
        if (curr.exists() or curr.is_symlink()) and _is_reparse_escaping_target(curr, eff_root, proj_canon, staging_canon, in_lexical_staging):
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


def _is_valid_external_staging_path(cand_res: Path) -> bool:
    """Valida path staging di progetti esterni bloccando sotto-percorsi lane malformati."""
    return is_external_projects_staging_path(cand_res) and not is_unsafe_lane_staged_token(cand_res.as_posix())


def _is_forbidden_staged_subpath(tok: str) -> bool:
    """True per riferimenti Online o sotto-percorsi .staging/lanes/ non consentiti."""
    return cmd_mentions_nk_proget_online(tok) or is_unsafe_lane_staged_token(tok)


def _is_valid_staging_path(cand: Path, project_root: Path) -> bool:
    """Verifica che il percorso canonico risieda realmente sotto .staging/ di Hub, bridge o Locale."""
    stg_idx, _rel, _lane = strip_staging_rel_parts(cand.parts)
    if stg_idx >= 0:
        raw_stg = Path(*cand.parts[: stg_idx + 1])
        if not is_valid_lane_subpath_no_reparse(cand, raw_stg):
            return False
    cand_res = _canonical_path(cand)
    if is_nk_proget_online_path(cand_res):
        return False
    root_res = _canonical_path(project_root)
    hub_res = _resolve_effective_hub_root(root_res)
    ws_res = _canonical_path(_WORKSPACE_ROOT)
    for base_root in (root_res, hub_res, root_res / "NK_Hub", ws_res):
        staging_root = _canonical_path(base_root / ".staging")
        if cand_res == staging_root or staging_root in cand_res.parents:
            return is_valid_lane_subpath_no_reparse(cand_res, staging_root)
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
    return _is_valid_external_staging_path(cand_res)


def _has_forbidden_redir_prefix(cleaned: str, raw_target: str, low: str) -> bool:
    """Verifica blocchi preliminari su target di redirezione (vuoto, backtick, ADS, .., .wal, Online)."""
    if not cleaned or cleaned == "__empty_redirect__" or "`" in raw_target:
        return True
    if _has_ntfs_ads_stream(cleaned) or ".." in low or ".wal" in low:
        return True
    return cmd_mentions_nk_proget_online(low)


def _is_safe_redirection_target(raw_target: str, project_root: Path) -> bool:
    """Verifica se una destinazione di redirezione o output punta a un path temporaneo, nullo o staged sicuro."""
    cleaned = _strip_wrapping_quotes(raw_target)
    norm = cleaned.replace("\\", "/")
    low = norm.lower()
    if _has_forbidden_redir_prefix(cleaned, raw_target, low):
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
    if is_nk_proget_online_path(cand):
        return False
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


def _is_unsafe_staged_token(tok: str) -> bool:
    """Identifica token .staging/ non sanitizzabili (traversal, .wal, lane malformate o Online)."""
    return ".." in tok or ".wal" in tok or _is_forbidden_staged_subpath(tok)


def _sanitize_staged_tokens_in_cmd(cmd_low: str) -> str:
    """Rimuove dal comando shell i soli token che puntano legittimamente a .staging/ o %TEMP%."""

    def _repl(match: re.Match[str]) -> str:
        tok = match.group(0)
        if _is_unsafe_staged_token(tok):
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


def _is_non_workspace_whitelisted(cand: Path, cand_norm_posix: str) -> bool:
    """Verifica whitelist per artefatti brain/ o tempdir fuori dai confini workspace."""
    if is_nk_proget_locale_path(cand):
        return False
    if ".gemini/antigravity/brain/" in cand_norm_posix:
        return True
    import tempfile

    temp_root = _canonical_path(tempfile.gettempdir())
    return cand == temp_root or temp_root in cand.parents


def _is_rel_parts_whitelisted(raw_parts: Tuple[str, ...]) -> bool:
    """Valuta la whitelist sui segmenti relativi a una root canonica."""
    rel_parts = [p.lower().rstrip(". ") for p in raw_parts]
    if not rel_parts:
        return False
    first = rel_parts[0]
    if first in _SAFE_DIR_COMPONENTS or first.startswith("nk_sandbox_") or is_valid_lane_plan_rel_parts(raw_parts):
        return True
    if len(rel_parts) >= 2 and rel_parts[:2] in (
        ["nk_tracking", "reports_and_briefs"],
        ["nk_tracking", "anchor"],
        ["nk_tracking", "sessions"],
    ):
        return True
    if len(rel_parts) == 1 and first in _SAFE_ROOT_FILENAMES:
        return True
    return len(rel_parts) == 2 and first == "nk_docs_and_setup" and rel_parts[1] in _SAFE_ROOT_FILENAMES


def _is_whitelisted_outside_staging(cand: Path, project_root: Path) -> bool:
    """Verifica se un target fuori da .staging/ appartiene alla whitelist esplicita e sicura."""
    cand = _canonical_path(cand)
    if is_nk_proget_online_path(cand):
        return False
    cand_norm_posix = cand.as_posix().lower()
    ws_root = _canonical_path(_WORKSPACE_ROOT)
    eff_root = _resolve_effective_hub_root(project_root)
    proj_canon = _canonical_path(project_root)

    in_proj = cand == proj_canon or proj_canon in cand.parents
    in_eff = cand == eff_root or eff_root in cand.parents
    in_ws = cand == ws_root or ws_root in cand.parents

    if not in_proj and not in_eff and not in_ws:
        if _is_non_workspace_whitelisted(cand, cand_norm_posix):
            return True

    for base_r in (eff_root, proj_canon, ws_root):
        if cand == base_r or base_r in cand.parents:
            try:
                raw_parts = cand.relative_to(base_r).parts
            except ValueError:
                continue
            if _is_rel_parts_whitelisted(raw_parts):
                return True
    return False
