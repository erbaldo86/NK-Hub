# -*- coding: utf-8 -*-
"""Guardia AST pure-stdlib per inline python -c e script in scratch/Temp (P0-BUG-06 / P1-BUG-08)."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_hook_gate.constants import _PROTECTED_PROJECT_SEGMENTS, _PROTECTED_ROOT_FILENAMES, _strip_wrapping_quotes
from _internal.nk_hook_gate.path_safety import (
    _canonical_path, _cmd_mentions_nk_proget_online, _deny_online_readonly, _has_ancestor_reparse_escape,
    _has_ntfs_ads_stream, _is_nk_proget_locale_target, _is_nk_proget_online_target, _is_safe_temp_marker_path,
    _is_valid_staging_path, _is_whitelisted_outside_staging, _resolve_effective_hub_root, _resolve_target_path,
)
from _internal.nk_hook_gate.shell_redaction import build_ast_symtab, collect_resolved_ast_hints, has_unsafe_dynamic_ast, resolve_ast_literals

_PY_VERBS = frozenset(("python", "python3", "py"))
_PY_ARG_FLAGS = frozenset(("-w", "-x", "--check-hash-based-pycs"))
_PY_C_FLAG_RE = re.compile(r"^-[bdeiopqrsuvx]*c(.*)$", re.IGNORECASE)
_PATH_MUTATION_METHODS = frozenset(
    ("write_text", "write_bytes", "replace", "rename", "unlink", "rmdir", "mkdir", "touch", "chmod", "symlink_to", "hardlink_to", "link_to")
)
_OS_MUTATION_FUNCS = frozenset(("remove", "unlink", "rmdir", "mkdir", "makedirs", "rename", "replace", "system"))
_SHUTIL_MUTATION_FUNCS = frozenset(("copy", "copy2", "copyfile", "copyfileobj", "copytree", "move", "rmtree", "unpack_archive"))
_PROTECTED_HINTS = tuple(_PROTECTED_PROJECT_SEGMENTS) + (
    "nk_tracking", "oracle_lock", "quality_baseline", "patch_notes", ".wal", "nk_external_projects", "nk proget",
)


def _norm_py_verb(tok: str) -> str:
    """Normalizza il nome dell'eseguibile Python rimuovendo &, parentesi, percorso e .exe."""
    cleaned = _strip_wrapping_quotes(tok).lstrip("&({").rstrip(")}").strip("\"'").replace("\\", "/")
    base = os.path.basename(cleaned).lower()
    return base[:-4] if base.endswith(".exe") else base


def _consume_py_c_flag(words: List[str], idx: int, payloads: List[str], skip_indices: Set[int]) -> bool:
    """Riconosce flag inline Python -c o combinati (-Bc, -Pc, -Rc, -c'code') estraendo il codice."""
    m = _PY_C_FLAG_RE.match(words[idx])
    if not m:
        return False
    skip_indices.add(idx)
    inline_tail = m.group(1)
    if inline_tail:
        payloads.append(inline_tail)
    elif idx + 1 < len(words):
        payloads.append(words[idx + 1])
        skip_indices.add(idx + 1)
    return True


def extract_python_inline_c_payloads(tokens: Sequence[Tuple[str, str, bool]]) -> Tuple[List[str], Set[int]]:
    """Isola gli argomenti inline di python/py -c/-Bc/-Pc ignorando powershell -Command."""
    if not tokens:
        return [], set()
    words = [u for _, u, _ in tokens]
    first_idx = 0
    while first_idx < len(words) and words[first_idx] in ("&", "(", "{", "$(", "@("):
        first_idx += 1
    if first_idx >= len(words) or _norm_py_verb(words[first_idx]) not in _PY_VERBS:
        return [], set()

    payloads: List[str] = []
    skip_indices: Set[int] = set()
    i, n = first_idx + 1, len(words)
    while i < n:
        wl = words[i].lower()
        if _consume_py_c_flag(words, i, payloads, skip_indices):
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
        attr, val = func.attr, func.value
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


def _is_non_staged_target_allowed(cand: Path, cleaned: str, project_root: Path) -> bool:
    """Verifica tempdir e scratch/ fuori da .staging/ bloccando Locale/ e path protetti."""
    if _is_nk_proget_locale_target(cand) or cand.name.lower().split(":", 1)[0].rstrip(". ") in _PROTECTED_ROOT_FILENAMES:
        return False
    eff_root, proj_canon = _resolve_effective_hub_root(project_root), _canonical_path(project_root)
    if any(cand == br or br in cand.parents for br in (eff_root, proj_canon)):
        return False
    norm = cleaned.replace("\\", "/").lower()
    if _is_safe_temp_marker_path(norm):
        return True
    if norm.startswith(("scratch/", "./scratch/")) or "/scratch/" in norm:
        return not any(seg in norm.split("scratch/", 1)[0] for seg in _PROTECTED_PROJECT_SEGMENTS)
    return False


def _is_target_write_allowed(target_str: str, project_root: Path) -> bool:
    """Verifica se il percorso target ricade in .staging/, scratch/ o tempdir sicuri."""
    cleaned = _strip_wrapping_quotes(target_str).strip()
    if not cleaned:
        return True
    if _has_ntfs_ads_stream(cleaned) or _has_ancestor_reparse_escape(cleaned, project_root) or _cmd_mentions_nk_proget_online(cleaned):
        return False
    cand = _resolve_target_path(cleaned, project_root)
    if _is_nk_proget_online_target(cand):
        return False
    if _is_valid_staging_path(cand, project_root) or _is_whitelisted_outside_staging(cand, project_root):
        return True
    return _is_non_staged_target_allowed(cand, cleaned, project_root)


def _has_protected_non_staged_hint(raw_hints: Sequence[str]) -> bool:
    """Rileva hint protetti o traversal '..' non contenuti dentro .staging/."""
    for raw_h in raw_hints:
        hn = raw_h.replace("\\", "/").lower()
        if ".." in hn:
            return True
        if ".staging/" not in hn and (any(ph in hn for ph in _PROTECTED_HINTS) or any(fn in hn for fn in _PROTECTED_ROOT_FILENAMES)):
            return True
    return False


def _deny_dynamic_hint_rule(raw_hints: Sequence[str], joined_hints: str) -> Optional[Dict[str, Any]]:
    """Blocca hint dinamici su Online lock, percorsi protetti o .staging/lanes/."""
    if _cmd_mentions_nk_proget_online(joined_hints) or ("nk proget" in joined_hints and "online" in joined_hints):
        return _deny_online_readonly()
    if _has_protected_non_staged_hint(raw_hints):
        return {"decision": "deny", "reason": "Python AST guard: dynamic mutation targeting protected NK paths is forbidden."}
    if ".staging/" in joined_hints and "lanes" in joined_hints:
        return {"decision": "deny", "reason_code": "LANE_OWNERSHIP_DENIED", "reason": "Python AST guard: unresolved dynamic write under .staging/lanes/ is forbidden."}
    return None


def _classify_dynamic_ast_hints(tgt: ast.AST, symtab: Optional[Dict[str, List[ast.AST]]] = None, conv_id: str = "") -> Optional[Dict[str, Any]]:
    """Classifica target AST dinamici in modo fail-closed fuori da .staging/ e tempdir sicuri."""
    _ = conv_id
    raw_hints = collect_resolved_ast_hints(tgt, symtab) if symtab is not None else _collect_string_hints(tgt)
    joined_hints = " ".join(h.replace("\\", "/").lower() for h in raw_hints)
    if (rule_denial := _deny_dynamic_hint_rule(raw_hints, joined_hints)) is not None:
        return rule_denial
    if not has_unsafe_dynamic_ast(tgt, symtab) and any(ok_m in joined_hints for ok_m in (".staging/", "gettempdir", "tmp_path", "tempfile")):
        return None
    return {"decision": "deny", "reason": "Python AST guard: unresolved dynamic write target is forbidden outside .staging/."}


def _deny_disallowed_ast_literal(lit: str, project_root: Path) -> Dict[str, Any]:
    """Restituisce deny Online oppure generico per un target letterale AST fuori .staging/."""
    if _cmd_mentions_nk_proget_online(lit) or _is_nk_proget_online_target(_resolve_target_path(lit, project_root)):
        return _deny_online_readonly()
    return {"decision": "deny", "reason": f"Python AST guard: direct write/mutation outside .staging/ is forbidden ({lit})."}


def _deny_ast_lits_lane_if_needed(lits: Sequence[str], project_root: Path, conv_id: str) -> Optional[Dict[str, Any]]:
    """Verifica ownership della lane sui letterali risolti che puntano a .staging/lanes/."""
    from _internal.nk_common.lane_paths import extract_lane_id_from_path, strip_staging_rel_parts
    from _internal.nk_common.lane_registry import verify_lane_access

    for lit_val in lits:
        cand = _resolve_target_path(_strip_wrapping_quotes(lit_val).strip(), project_root)
        lane_id = extract_lane_id_from_path(cand) if _is_valid_staging_path(cand, project_root) else None
        if lane_id is None:
            continue
        idx, _rel, _raw = strip_staging_rel_parts(cand.parts)
        repo_root = Path(*cand.parts[:idx]) if idx > 0 else _resolve_effective_hub_root(_canonical_path(project_root))
        try:
            ok, code = verify_lane_access(repo_root, lane_id, conv_id)
        except (OSError, ValueError, TimeoutError) as exc:
            ok, code = False, str(exc)
        if not ok:
            return {"decision": "deny", "reason_code": "LANE_OWNERSHIP_DENIED", "reason": f"Accesso negato alla lane '.staging/lanes/{lane_id}/' per conversation_id={conv_id!r} ({code})."}
    return None


def _resolve_ast_base_cand(tgt: ast.AST, symtab: Optional[Dict[str, List[ast.AST]]]) -> List[str]:
    if symtab is not None:
        return resolve_ast_literals(tgt, symtab)
    lit = _literal_str_from_node(tgt)
    return [lit] if lit is not None else []


def _classify_ast_target_node(
    tgt: ast.AST, project_root: Path, symtab: Optional[Dict[str, List[ast.AST]]] = None, conv_id: str = ""
) -> Optional[Dict[str, Any]]:
    """Valuta un nodo AST target letterale, risolto o dinamico contro Online lock, staging e lane."""
    lits = _resolve_ast_base_cand(tgt, symtab)
    if not lits:
        return _classify_dynamic_ast_hints(tgt, symtab=symtab, conv_id=conv_id)
    bad_lit = next((x for x in lits if not _is_target_write_allowed(x, project_root)), None)
    return _deny_disallowed_ast_literal(bad_lit, project_root) if bad_lit is not None else _deny_ast_lits_lane_if_needed(lits, project_root, conv_id)


_INLINE_2PC_FUNCS = frozenset(("promote_staging_to_production", "win32_atomic_replace", "quarantine_staging", "twophasecommitengine", "run_commit_train_promote", "append_commit_train_entry", "consolidate_post_commit", "close_active_tensor_session_post_commit", "materialize_changelog_fragments", "release_lane", "update_baseline_metrics"))
_GOV_ENV_HINT_EXACT = frozenset(("nk_allow_governance_override", "nk_holdout_dir", "proget_root", "nk_proget_root", "nk_hooks_temp_dir", "antigravity_conversation_id", "nk_conversation_id"))
_GOV_ENV_HINT_PREFIXES = ("nk_governance_", "nk_tensor_", "nk_lane_", "nk_commit_train_")


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
    denial = {"decision": "deny", "reason_code": "UNAUTHORIZED_GOVERNANCE_OVERRIDE", "reason": "Python AST guard: inline governance os.environ tampering is forbidden ([RULE-00])."}
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

def _call_path_args(node: ast.Call, pos_limit: int, kw_names: Tuple[str, ...]) -> List[ast.AST]:
    """Estrae argomenti posizionali, keyword nominali e **kwargs per target fail-closed."""
    return list(node.args[:pos_limit]) + [kw.value for kw in node.keywords if kw.arg is None or kw.arg in kw_names]

def _open_mode_from_call(node: ast.Call, mode_idx: int = 1) -> str:
    """Estrae la stringa mode letterale da open(...)/Path.open(...) o '__dynamic__' se variabile."""
    if any(kw.arg is None for kw in node.keywords):
        return "__dynamic__"
    mode_val = _literal_str_from_node(node.args[mode_idx]) if len(node.args) > mode_idx else "r"
    if len(node.args) > mode_idx and mode_val is None:
        return "__dynamic__"
    for kw in node.keywords:
        if kw.arg == "mode":
            lit_m = _literal_str_from_node(kw.value)
            return lit_m if lit_m is not None else "__dynamic__"
    return mode_val or "r"

_IO_MOD_BASES, _NON_PATH_OPEN_BASES = frozenset(("io", "_io", "codecs", "builtins")), frozenset(("io", "_io", "codecs", "builtins", "os"))
_PATH_TARGET_ARG_METHODS = frozenset(("replace", "rename", "symlink_to", "hardlink_to", "link_to"))
def _attr_owner_list(node: ast.Call) -> List[ast.AST]: return [node.func.value] if isinstance(node.func, ast.Attribute) else []
def _path_open_targets(node: ast.Call) -> List[ast.AST]: return [] if _is_readonly_mode_str(_open_mode_from_call(node, 0)) else _attr_owner_list(node)
def _is_io_mod_open_or_fileio(base_low: str, func_low: str, attr_nm: str) -> bool: return (bool(attr_nm) and func_low in ("open", "open_code") and base_low in _IO_MOD_BASES) or (func_low == "fileio" and base_low in ("io", "_io", ""))
def _path_method_targets(node: ast.Call, func_low: str) -> List[ast.AST]: return _attr_owner_list(node) + (_call_path_args(node, 1, ("target",)) if func_low in _PATH_TARGET_ARG_METHODS else [])


def _io_or_path_call_targets(node: ast.Call, base_low: str, func_low: str, attr_nm: str) -> Optional[List[ast.AST]]:
    """Estrae target da open(file=...), io.open/FileIO, Path.open() e metodi mutanti Path."""
    if not attr_nm and func_low == "open":
        return [] if _is_readonly_mode_str(_open_mode_from_call(node, 1)) else _call_path_args(node, 1, ("file",))
    if _is_io_mod_open_or_fileio(base_low, func_low, attr_nm):
        return _call_path_args(node, 1, ("file", "filename", "path"))
    if attr_nm and func_low == "open" and base_low not in _NON_PATH_OPEN_BASES:
        return _path_open_targets(node)
    return _path_method_targets(node, func_low) if (attr_nm and func_low in _PATH_MUTATION_METHODS) else None


def _extract_call_mutation_targets(node: ast.Call, base_nm: str, attr_nm: str) -> List[ast.AST]:
    """Estrae i nodi AST target di chiamate mutanti open/Path/os/shutil/sqlite3."""
    func_low, base_low = (attr_nm or base_nm).lower(), base_nm.lower()
    if (hit := _io_or_path_call_targets(node, base_low, func_low, attr_nm)) is not None:
        return hit
    if base_low == "os" and func_low == "open":
        return _call_path_args(node, 1, ("path",))
    if (base_low == "os" and func_low in _OS_MUTATION_FUNCS) or (base_low == "shutil" and func_low in _SHUTIL_MUTATION_FUNCS):
        return _call_path_args(node, 2, ("path", "src", "dst", "filename", "extract_dir", "command"))
    if func_low in ("copyfile", "copytree", "rmtree", "unpack_archive"):
        return _call_path_args(node, 2, ("src", "dst", "path", "filename", "extract_dir"))
    return _call_path_args(node, 1, ("database", "file")) if (func_low == "connect" and base_low in ("sqlite3", "")) else []

def _check_inline_2pc_import(tree: ast.AST) -> Optional[Dict[str, Any]]:
    bad = next((a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names if a.name.lower() in _INLINE_2PC_FUNCS), None)
    return {"decision": "deny", "reason_code": "INLINE_2PC_FORBIDDEN", "reason": f"Python AST guard: inline 2PC import {bad} is forbidden; use CLI win32_2pc_engine.py."} if bad else None

def _check_inline_pre_ast(tree: ast.AST) -> Optional[Dict[str, Any]]: return _check_inline_env_tamper(tree) or _check_inline_2pc_import(tree)


def inspect_python_source_mutations(source_code: str, project_root: Path, conv_id: str = "") -> Optional[Dict[str, Any]]:
    """Ispeziona il sorgente Python con ast.parse bloccando scritture fuori .staging/."""
    if not source_code or not source_code.strip():
        return None
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None
    if (env_denial := _check_inline_pre_ast(tree)) is not None:
        return env_denial
    symtab = build_ast_symtab(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base_nm, attr_nm = _get_call_name(node)
        if (tpc_denial := _check_inline_2pc_call(node, base_nm, attr_nm)) is not None:
            return tpc_denial
        for tgt in _extract_call_mutation_targets(node, base_nm, attr_nm):
            if (denial := _classify_ast_target_node(tgt, project_root, symtab=symtab, conv_id=conv_id)) is not None:
                return denial
    return None

def inspect_script_file_ast(script_token: str, project_root: Path, conv_id: str = "") -> Optional[Dict[str, Any]]:
    """Verifica via AST uno script Python non-staged in scratch/ o tempdir."""
    cleaned = _strip_wrapping_quotes(script_token).strip()
    if not cleaned:
        return None
    cand = _resolve_target_path(cleaned, project_root)
    try:
        if not cand.is_file() or cand.suffix.lower() != ".py" or cand.stat().st_size > 524_288:
            return None
        source = cand.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return inspect_python_source_mutations(source, project_root, conv_id=conv_id)
