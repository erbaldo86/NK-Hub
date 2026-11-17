"""Analisi script Temp/scratch e argomenti verso percorsi protetti (P1-BUG-08)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from _internal.nk_hook_gate.constants import (
    _HUB_ROOT,
    _PROD_DIR_PREFIXES,
    _PROTECTED_DIR_CMD_RE,
    _PROTECTED_FILE_EXTS,
    _PROTECTED_ROOT_FILENAMES,
    _UNSTAGE_CODE_DIR_CMD_RE,
    _WORKSPACE_ROOT,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _is_safe_redirection_target,
    _is_safe_temp_marker_path,
    _is_valid_staging_path,
    _resolve_target_path,
)
from _internal.nk_hook_gate.shell_parser import (
    _deobfuscate_ps_backticks,
    _norm_cmd_verb,
    _split_shell_segments,
    _tokenize_shell_tokens,
    _unwrap_shell_subcommands,
)

_INTERPRETER_VERBS = frozenset(("python", "python3", "py", "powershell", "pwsh", "cmd"))
_SCRIPT_EXTS = frozenset((".py", ".ps1", ".bat", ".cmd", ".vbs", ".js"))
_PY_FLAGS_WITH_ARG = frozenset(("-w", "-x", "--check-hash-based-pycs"))
_PS_FLAGS_WITH_ARG = frozenset(
    ("-executionpolicy", "-ep", "-windowstyle", "-inputformat", "-outputformat")
)
_CORE_SCRIPT_BASENAMES = frozenset(
    (
        "win32_2pc_engine.py",
        "nk_hook_gate.py",
        "nk_acs_fastguard.py",
        "nk_session_bootstrap.py",
        "vibe_sprint_router.py",
        "ast_guard_validator.py",
        "nk_registry_indexer.py",
    )
)


def _is_temp_or_scratch_script_token(tok: str) -> bool:
    """Verifica se un argomento punta a uno script in Temp/scratch fuori da .staging/."""
    cleaned = _strip_wrapping_quotes(tok).strip()
    if not cleaned:
        return False
    norm = cleaned.replace("\\", "/")
    low = norm.lower()
    if ".staging/" in low and not any(bad in low.split(".staging/", 1)[0] for bad in _PROD_DIR_PREFIXES):
        return False
    if _is_safe_temp_marker_path(low):
        return True
    if low.startswith(("scratch/", "./scratch/")) or "/scratch/" in low:
        prefix = low.split("scratch/", 1)[0]
        if not any(bad in prefix for bad in _PROD_DIR_PREFIXES):
            return True
    try:
        import tempfile

        temp_canon = _canonical_path(tempfile.gettempdir())
        cand = Path(cleaned)
        if cand.is_absolute():
            cand_c = _canonical_path(cand)
            if cand_c == temp_canon or temp_canon in cand_c.parents:
                return True
    except Exception:
        pass
    return False


def _arg_targets_protected_outside_staging(raw_arg: str, project_root: Path) -> bool:
    """Verifica se un argomento di script Temp punta a dir o file protetti fuori da .staging/."""
    val = _strip_wrapping_quotes(raw_arg)
    if not val:
        return False
    if "=" in val and not (len(val) > 2 and val[1] == ":"):
        val = _strip_wrapping_quotes(val.split("=", 1)[1])
    norm = val.replace("\\", "/")
    low = norm.lower()
    if not low or low.startswith("-"):
        return False
    if ".staging/" in low:
        cand = _resolve_target_path(val, project_root)
        if _is_valid_staging_path(cand, project_root):
            return False
    if _is_safe_temp_marker_path(low):
        return False
    if (
        _PROTECTED_DIR_CMD_RE.search(f" {low} ")
        or _UNSTAGE_CODE_DIR_CMD_RE.search(f" {low} ")
        or "nk_tracking" in low
        or "oracle_lock.json" in low
    ):
        return True
    base = os.path.basename(low.rstrip("/"))
    if base in _PROTECTED_ROOT_FILENAMES:
        return True
    _, ext = os.path.splitext(base)
    return ext in _PROTECTED_FILE_EXTS and not _is_safe_redirection_target(val, project_root)


def _find_invoked_script_index(words: List[str], first_idx: int, v0: str) -> Optional[int]:
    """Individua l'indice dello script invocato dall'interprete ignorando i soli flag dell'interprete."""
    i = first_idx + 1
    n = len(words)
    if v0 in ("python", "python3", "py"):
        while i < n:
            wl = words[i].lower()
            if wl in ("-c", "-m"):
                return None
            if wl in _PY_FLAGS_WITH_ARG:
                i += 2
                continue
            if wl.startswith("-"):
                i += 1
                continue
            return i
        return None
    if v0 in ("powershell", "pwsh"):
        while i < n:
            wl = words[i].lower()
            if wl in ("-c", "-command", "-encodedcommand", "-enc", "-ec"):
                return None
            if wl in ("-file", "-f"):
                return i + 1 if i + 1 < n else None
            if wl in _PS_FLAGS_WITH_ARG:
                i += 2
                continue
            if wl.startswith("-"):
                i += 1
                continue
            return i
        return None
    if v0 == "cmd":
        while i < n:
            wl = words[i].lower()
            if wl in ("/c", "/k", "/d", "/a", "/u", "/q", "/s", "/x", "/y", "/e:on", "/e:off"):
                i += 1
                continue
            if wl.startswith("/"):
                i += 1
                continue
            return i
    return None


def _has_unstaged_temp_script_targeting_protected(
    cmd_str: str, project_root: Path = _WORKSPACE_ROOT
) -> bool:
    """Rileva script in Temp/scratch con argomenti o AST che mutano percorsi protetti (P1-BUG-08)."""
    if not cmd_str:
        return False
    from _internal.nk_hook_gate.ast_inline_guard import inspect_script_file_ast

    for raw_sub in (
        cmd_str,
        _deobfuscate_ps_backticks(cmd_str),
        *_unwrap_shell_subcommands(cmd_str),
    ):
        for seg in _split_shell_segments(raw_sub):
            tokens = _tokenize_shell_tokens(seg)
            if not tokens or len(tokens) < 2:
                continue
            words = [u for _, u, _ in tokens]
            first_idx = 1 if len(words) > 1 and words[0] == "&" else 0
            if first_idx >= len(words):
                continue
            v0 = _norm_cmd_verb(words[first_idx])
            if v0 not in _INTERPRETER_VERBS:
                continue
            script_idx = _find_invoked_script_index(words, first_idx, v0)
            if script_idx is None or script_idx >= len(words):
                continue
            script_tok = words[script_idx]
            if not _is_temp_or_scratch_script_token(script_tok):
                continue
            cleaned_tok = _strip_wrapping_quotes(script_tok).strip()
            tok_low = cleaned_tok.replace("\\", "/").lower()
            if "/nk_sandbox_" not in tok_low and (
                "/scripts/" in tok_low
                or os.path.basename(tok_low) in _CORE_SCRIPT_BASENAMES
                or (_HUB_ROOT / "scripts" / os.path.basename(tok_low)).is_file()
            ):
                return True
            _, ext = os.path.splitext(cleaned_tok.lower())
            if ext and ext not in _SCRIPT_EXTS:
                continue
            if v0 in ("python", "python3", "py"):
                if inspect_script_file_ast(script_tok, project_root) is not None:
                    return True
            for idx_w in range(first_idx + 1, len(words)):
                if idx_w == script_idx:
                    continue
                if _arg_targets_protected_outside_staging(words[idx_w], project_root):
                    return True
    return False
