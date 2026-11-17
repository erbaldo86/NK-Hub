# -*- coding: utf-8 -*-
"""Guardia AST pure-stdlib per inline python -c e script in scratch/Temp (P0-BUG-06 / P1-BUG-08)."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_hook_gate.constants import (
    _PROTECTED_PROJECT_SEGMENTS,
    _PROTECTED_ROOT_FILENAMES,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.path_safety import (
    _canonical_path,
    _has_ancestor_reparse_escape,
    _has_ntfs_ads_stream,
    _is_safe_temp_marker_path,
    _is_valid_staging_path,
    _is_whitelisted_outside_staging,
    _resolve_effective_hub_root,
    _resolve_target_path,
)

_PY_VERBS = frozenset(("python", "python3", "py"))
_PY_ARG_FLAGS = frozenset(("-w", "-x", "--check-hash-based-pycs"))
_PATH_MUTATION_METHODS = frozenset(
    (
        "write_text",
        "write_bytes",
        "replace",
        "rename",
        "unlink",
        "rmdir",
        "mkdir",
        "touch",
        "chmod",
        "symlink_to",
        "hardlink_to",
        "link_to",
    )
)
_OS_MUTATION_FUNCS = frozenset(
    ("remove", "unlink", "rmdir", "mkdir", "makedirs", "rename", "replace", "system")
)
_SHUTIL_MUTATION_FUNCS = frozenset(
    ("copy", "copy2", "copyfile", "copyfileobj", "copytree", "move", "rmtree", "unpack_archive")
)
_PROTECTED_HINTS = tuple(_PROTECTED_PROJECT_SEGMENTS) + (
    "nk_tracking",
    "oracle_lock",
    "quality_baseline",
    "patch_notes",
    ".wal",
)


def _norm_py_verb(tok: str) -> str:
    """Normalizza il nome dell'eseguibile Python rimuovendo percorso e .exe."""
    base = os.path.basename(_strip_wrapping_quotes(tok).replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


def extract_python_inline_c_payloads(
    tokens: Sequence[Tuple[str, str, bool]],
) -> Tuple[List[str], Set[int]]:
    """Isola gli argomenti inline di python/py -c ignorando powershell -Command."""
    if not tokens:
        return [], set()
    words = [u for _, u, _ in tokens]
    first_idx = 1 if len(words) > 1 and words[0] == "&" else 0
    if first_idx >= len(words):
        return [], set()
    if _norm_py_verb(words[first_idx]) not in _PY_VERBS:
        return [], set()

    payloads: List[str] = []
    skip_indices: Set[int] = set()
    i = first_idx + 1
    n = len(words)
    while i < n:
        wl = words[i].lower()
        if wl == "-c":
            skip_indices.add(i)
            if i + 1 < n:
                payloads.append(words[i + 1])
                skip_indices.add(i + 1)
            break
        if wl in _PY_ARG_FLAGS:
            i += 2
            continue
        if wl.startswith("-"):
            i += 1
            continue
        break
    return payloads, skip_indices


def _get_call_name(node: ast.Call) -> Tuple[str, str]:
    """Estrae (oggetto_base, funzione_o_metodo) con attr_nm vuoto su chiamate dirette Name()."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id, ""
    if isinstance(func, ast.Attribute):
        attr = func.attr
        val = func.value
        if isinstance(val, ast.Name):
            return val.id, attr
        if isinstance(val, ast.Attribute):
            return val.attr, attr
        return "__expr__", attr
    return "", ""


def _is_readonly_mode_str(mode: str) -> bool:
    """Verifica se la modalita di apertura open() e di sola lettura."""
    m = mode.strip().lower()
    return bool(m) and ("r" in m) and all(c not in m for c in ("+", "w", "a", "x"))


def _literal_str_from_node(node: ast.AST) -> Optional[str]:
    """Estrae una stringa letterale costante o un argomento Path('...')."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):
        _, attr = _get_call_name(node)
        target_nm = attr or (node.func.id if isinstance(node.func, ast.Name) else "")
        if target_nm.lower() in ("path", "posixpath", "windowspath", "purepath") and node.args:
            return _literal_str_from_node(node.args[0])
    return None


def _collect_string_hints(node: ast.AST) -> List[str]:
    """Raccoglie stringhe e identificatori contenuti in un sottoalbero AST."""
    hints: List[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            hints.append(sub.value)
        elif isinstance(sub, ast.Name):
            hints.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            hints.append(sub.attr)
    return hints


def _is_target_write_allowed(target_str: str, project_root: Path) -> bool:
    """Verifica se il percorso target ricade in .staging/, scratch/ o tempdir sicuri."""
    cleaned = _strip_wrapping_quotes(target_str).strip()
    if not cleaned:
        return True
    if _has_ntfs_ads_stream(cleaned):
        return False
    if _has_ancestor_reparse_escape(cleaned, project_root):
        return False
    cand = _resolve_target_path(cleaned, project_root)
    if _is_valid_staging_path(cand, project_root):
        return True
    if _is_whitelisted_outside_staging(cand, project_root):
        return True
    if cand.name.lower().split(":", 1)[0].rstrip(". ") in _PROTECTED_ROOT_FILENAMES:
        return False
    eff_root = _resolve_effective_hub_root(project_root)
    proj_canon = _canonical_path(project_root)
    if any(cand == br or br in cand.parents for br in (eff_root, proj_canon)):
        return False
    norm = cleaned.replace("\\", "/").lower()
    if _is_safe_temp_marker_path(norm):
        return True
    if norm.startswith(("scratch/", "./scratch/")) or "/scratch/" in norm:
        prefix = norm.split("scratch/", 1)[0]
        if not any(seg in prefix for seg in _PROTECTED_PROJECT_SEGMENTS):
            return True
    return False


def inspect_python_source_mutations(
    source_code: str, project_root: Path
) -> Optional[Dict[str, Any]]:
    """Ispeziona il sorgente Python con ast.parse bloccando scritture fuori .staging/."""
    if not source_code or not source_code.strip():
        return None
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base_nm, attr_nm = _get_call_name(node)
        func_nm = attr_nm or base_nm
        func_low = func_nm.lower()
        base_low = base_nm.lower()

        target_nodes: List[ast.AST] = []
        is_mut = False

        if not attr_nm and func_low == "open":
            mode_val = "r"
            if len(node.args) >= 2:
                lit_m = _literal_str_from_node(node.args[1])
                mode_val = lit_m if lit_m is not None else "__dynamic__"
            for kw in node.keywords:
                if kw.arg == "mode":
                    lit_m = _literal_str_from_node(kw.value)
                    mode_val = lit_m if lit_m is not None else "__dynamic__"
            if not _is_readonly_mode_str(mode_val):
                is_mut = True
                if node.args:
                    target_nodes.append(node.args[0])
        elif (
            (attr_nm and func_low in ("open", "open_code") and base_low in ("io", "_io", "codecs", "builtins"))
            or (func_low == "fileio" and base_low in ("io", "_io", ""))
        ):
            is_mut = True
            target_nodes.extend(node.args[:1])
        elif attr_nm and func_low in _PATH_MUTATION_METHODS:
            is_mut = True
            if isinstance(node.func, ast.Attribute):
                target_nodes.append(node.func.value)
            target_nodes.extend(node.args[:1])
        elif base_low == "os" and func_low == "open":
            is_mut = True
            target_nodes.extend(node.args[:1])
        elif base_low == "os" and func_low in _OS_MUTATION_FUNCS:
            is_mut = True
            target_nodes.extend(node.args[:2])
        elif (base_low == "shutil" and func_low in _SHUTIL_MUTATION_FUNCS) or func_low in (
            "copyfile",
            "copytree",
            "rmtree",
            "unpack_archive",
        ):
            is_mut = True
            target_nodes.extend(node.args[:2])
        elif func_low == "connect" and base_low in ("sqlite3", ""):
            is_mut = True
            target_nodes.extend(node.args[:1])

        if not is_mut:
            continue

        for tgt in target_nodes:
            lit = _literal_str_from_node(tgt)
            if lit is not None:
                if not _is_target_write_allowed(lit, project_root):
                    return {
                        "decision": "deny",
                        "reason": (
                            f"Python AST guard: direct write/mutation outside .staging/ is forbidden ({lit})."
                        ),
                    }
                continue
            hints = [h.replace("\\", "/").lower() for h in _collect_string_hints(tgt)]
            joined_hints = " ".join(hints)
            if ".staging/" in joined_hints or "gettempdir" in joined_hints:
                continue
            if any(ph in joined_hints for ph in _PROTECTED_HINTS) or any(
                fn in joined_hints for fn in _PROTECTED_ROOT_FILENAMES
            ):
                return {
                    "decision": "deny",
                    "reason": "Python AST guard: dynamic mutation targeting protected NK paths is forbidden.",
                }
            if any(kw in joined_hints for kw in ("path", "root", "hub", "script", "agent", "genome")):
                return {
                    "decision": "deny",
                    "reason": "Python AST guard: unresolved dynamic write target is forbidden outside .staging/.",
                }

    return None


def inspect_script_file_ast(script_token: str, project_root: Path) -> Optional[Dict[str, Any]]:
    """Verifica via AST uno script Python non-staged in scratch/ o tempdir."""
    cleaned = _strip_wrapping_quotes(script_token).strip()
    if not cleaned:
        return None
    cand = _resolve_target_path(cleaned, project_root)
    try:
        if not cand.is_file() or cand.suffix.lower() != ".py":
            return None
        if cand.stat().st_size > 524_288:
            return None
        source = cand.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return inspect_python_source_mutations(source, project_root)
