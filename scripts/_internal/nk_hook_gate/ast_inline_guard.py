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
    _cmd_mentions_nk_proget_online,
    _deny_online_readonly,
    _has_ancestor_reparse_escape,
    _has_ntfs_ads_stream,
    _is_nk_proget_locale_target,
    _is_nk_proget_online_target,
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
    "nk_external_projects",
    "nk proget",
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


def _is_non_staged_target_allowed(
    cand: Path, cleaned: str, project_root: Path
) -> bool:
    """Verifica tempdir e scratch/ fuori da .staging/ bloccando Locale/ e path protetti."""
    if _is_nk_proget_locale_target(cand):
        return False
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


def _is_target_write_allowed(target_str: str, project_root: Path) -> bool:
    """Verifica se il percorso target ricade in .staging/, scratch/ o tempdir sicuri."""
    cleaned = _strip_wrapping_quotes(target_str).strip()
    if not cleaned:
        return True
    if _has_ntfs_ads_stream(cleaned) or _has_ancestor_reparse_escape(cleaned, project_root):
        return False
    if _cmd_mentions_nk_proget_online(cleaned):
        return False
    cand = _resolve_target_path(cleaned, project_root)
    if _is_nk_proget_online_target(cand):
        return False
    if _is_valid_staging_path(cand, project_root) or _is_whitelisted_outside_staging(cand, project_root):
        return True
    return _is_non_staged_target_allowed(cand, cleaned, project_root)


def _classify_dynamic_ast_hints(tgt: ast.AST) -> Optional[Dict[str, Any]]:
    """Classifica target AST dinamici verificando Online lock prima degli hint .staging/."""
    hints = [h.replace("\\", "/").lower() for h in _collect_string_hints(tgt)]
    joined_hints = " ".join(hints)
    if _cmd_mentions_nk_proget_online(joined_hints) or (
        "nk proget" in joined_hints and "online" in joined_hints
    ):
        return _deny_online_readonly()
    if ".staging/" in joined_hints or "gettempdir" in joined_hints:
        return None
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


def _classify_ast_target_node(
    tgt: ast.AST, project_root: Path
) -> Optional[Dict[str, Any]]:
    """Valuta un nodo AST target letterale o dinamico contro Online lock e staging."""
    lit = _literal_str_from_node(tgt)
    if lit is None:
        return _classify_dynamic_ast_hints(tgt)
    if _is_target_write_allowed(lit, project_root):
        return None
    if _cmd_mentions_nk_proget_online(lit) or _is_nk_proget_online_target(
        _resolve_target_path(lit, project_root)
    ):
        return _deny_online_readonly()
    return {
        "decision": "deny",
        "reason": f"Python AST guard: direct write/mutation outside .staging/ is forbidden ({lit}).",
    }


_INLINE_2PC_FUNCS = frozenset(
    ("promote_staging_to_production", "win32_atomic_replace", "quarantine_staging", "twophasecommitengine")
)
_GOV_ENV_HINT_EXACT = frozenset(
    ("nk_allow_governance_override", "nk_holdout_dir", "proget_root", "nk_proget_root")
)
_GOV_ENV_HINT_PREFIXES = ("nk_governance_", "nk_tensor_")


def _has_gov_env_hint(node: ast.AST) -> bool:
    """Rileva chiavi o nomi di variabili ambiente di governance in un sottoalbero AST."""
    for h in (s.strip().lower() for s in _collect_string_hints(node)):
        if h in _GOV_ENV_HINT_EXACT or h.startswith(_GOV_ENV_HINT_PREFIXES):
            return True
    return False


def _is_os_environ_expr(node: ast.AST) -> bool:
    """Verifica se il nodo AST fa riferimento a os.environ o environ."""
    if isinstance(node, ast.Name):
        return node.id == "environ"
    return isinstance(node, ast.Attribute) and node.attr == "environ"


def _is_gov_sub_target(tgt: ast.AST) -> bool:
    """Verifica se un target AST Assign/Delete muta os.environ su chiavi di governance."""
    return isinstance(tgt, ast.Subscript) and _is_os_environ_expr(tgt.value) and _has_gov_env_hint(tgt.slice)


def _is_gov_env_call(node: ast.Call) -> bool:
    """Verifica se una chiamata AST muta os.putenv/unsetenv o os.environ.* su chiavi protette."""
    base_nm, attr_nm = _get_call_name(node)
    b_low, f_low = base_nm.lower(), (attr_nm or base_nm).lower()
    if b_low == "os" and f_low in ("putenv", "unsetenv"):
        return _has_gov_env_hint(node)
    if b_low == "environ" and f_low in ("update", "setdefault", "pop"):
        return _has_gov_env_hint(node)
    return b_low == "environ" and f_low == "clear"


def _check_inline_env_tamper(tree: ast.AST) -> Optional[Dict[str, Any]]:
    """Blocca manomissioni AST inline su os.environ, os.putenv o os.unsetenv."""
    denial = {
        "decision": "deny",
        "reason_code": "UNAUTHORIZED_GOVERNANCE_OVERRIDE",
        "reason": "Python AST guard: inline governance os.environ tampering is forbidden ([RULE-00]).",
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
            targets = [node.target] if isinstance(node, ast.AugAssign) else node.targets
            if any(_is_gov_sub_target(t) for t in targets):
                return denial
        elif isinstance(node, ast.Call) and _is_gov_env_call(node):
            return denial
    return None


def _is_2pc_call_match(node: ast.Call, base_nm: str, attr_nm: str) -> bool:
    """Riconosce invocazioni inline dirette o dinamiche alle API di commit 2PC."""
    f_low, b_low = (attr_nm or base_nm).lower(), base_nm.lower()
    if f_low in _INLINE_2PC_FUNCS:
        return True
    if attr_nm and f_low == "atomic_write":
        return True
    if attr_nm and f_low in ("commit", "prepare") and ("twophasecommitengine" in b_low or "engine" in b_low or "2pc" in b_low):
        return True
    return f_low == "getattr" and len(node.args) >= 2 and (_literal_str_from_node(node.args[1]) or "").lower() in _INLINE_2PC_FUNCS


def _check_inline_2pc_call(node: ast.Call, base_nm: str, attr_nm: str) -> Optional[Dict[str, Any]]:
    """Blocca invocazioni Python inline dirette a funzioni di commit/promozione 2PC."""
    if not _is_2pc_call_match(node, base_nm, attr_nm):
        return None
    func_nm = attr_nm or base_nm
    return {"decision": "deny", "reason_code": "INLINE_2PC_FORBIDDEN", "reason": f"Python AST guard: inline 2PC call {func_nm}() is forbidden; use CLI win32_2pc_engine.py."}


def _open_mode_from_call(node: ast.Call) -> str:
    """Estrae la stringa mode letterale da open(...) o '__dynamic__' se non costante."""
    mode_val = _literal_str_from_node(node.args[1]) if len(node.args) >= 2 else "r"
    if len(node.args) >= 2 and mode_val is None:
        return "__dynamic__"
    for kw in node.keywords:
        if kw.arg == "mode":
            lit_m = _literal_str_from_node(kw.value)
            return lit_m if lit_m is not None else "__dynamic__"
    return mode_val or "r"


def _io_or_path_call_targets(node: ast.Call, base_low: str, func_low: str, attr_nm: str) -> Optional[List[ast.AST]]:
    """Estrae target da open(), io.open/FileIO o metodi mutanti Path."""
    if not attr_nm and func_low == "open":
        return list(node.args[:1]) if not _is_readonly_mode_str(_open_mode_from_call(node)) else []
    if (attr_nm and func_low in ("open", "open_code") and base_low in ("io", "_io", "codecs", "builtins")) or (
        func_low == "fileio" and base_low in ("io", "_io", "")
    ):
        return list(node.args[:1])
    if attr_nm and func_low in _PATH_MUTATION_METHODS:
        owner = [node.func.value] if isinstance(node.func, ast.Attribute) else []
        return owner + list(node.args[:1])
    return None


def _extract_call_mutation_targets(node: ast.Call, base_nm: str, attr_nm: str) -> List[ast.AST]:
    """Estrae i nodi AST target di chiamate mutanti open/Path/os/shutil/sqlite3."""
    func_low, base_low = (attr_nm or base_nm).lower(), base_nm.lower()
    if (hit := _io_or_path_call_targets(node, base_low, func_low, attr_nm)) is not None:
        return hit
    if base_low == "os" and func_low == "open":
        return list(node.args[:1])
    if (base_low == "os" and func_low in _OS_MUTATION_FUNCS) or (base_low == "shutil" and func_low in _SHUTIL_MUTATION_FUNCS):
        return list(node.args[:2])
    if func_low in ("copyfile", "copytree", "rmtree", "unpack_archive"):
        return list(node.args[:2])
    return list(node.args[:1]) if (func_low == "connect" and base_low in ("sqlite3", "")) else []


def inspect_python_source_mutations(source_code: str, project_root: Path) -> Optional[Dict[str, Any]]:
    """Ispeziona il sorgente Python con ast.parse bloccando scritture fuori .staging/."""
    if not source_code or not source_code.strip():
        return None
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None

    if (env_denial := _check_inline_env_tamper(tree)) is not None:
        return env_denial

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base_nm, attr_nm = _get_call_name(node)
        if (tpc_denial := _check_inline_2pc_call(node, base_nm, attr_nm)) is not None:
            return tpc_denial
        for tgt in _extract_call_mutation_targets(node, base_nm, attr_nm):
            if (denial := _classify_ast_target_node(tgt, project_root)) is not None:
                return denial

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
