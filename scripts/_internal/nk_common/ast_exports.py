# -*- coding: utf-8 -*-
"""Estrattore AST condiviso per re-export locali e tabelle _LAZY_EXPORT_MAP."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple


def _iter_module_level_statements(tree: ast.AST) -> List[ast.stmt]:
    """Restituisce gli statement eseguibili a livello modulo saltando TYPE_CHECKING."""
    collected: List[ast.stmt] = []
    stack: List[ast.stmt] = list(getattr(tree, "body", []))
    while stack:
        stmt = stack.pop(0)
        collected.append(stmt)
        if isinstance(stmt, ast.If):
            test = stmt.test
            is_tc = (
                isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
            ) or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                continue
            stack = list(stmt.body) + list(stmt.orelse) + stack
        elif isinstance(stmt, (ast.Try, ast.With, ast.AsyncWith)):
            for attr in ("body", "orelse", "handlers", "finalbody"):
                sub = getattr(stmt, attr, None)
                if isinstance(sub, list):
                    for child in sub:
                        if isinstance(child, ast.ExceptHandler):
                            stack.extend(child.body)
                        elif isinstance(child, ast.stmt):
                            stack.append(child)
    return collected


def _parse_lazy_export_entry(
    export_name: str, val_node: ast.AST
) -> Optional[Tuple[str, str]]:
    """Normalizza una voce di _LAZY_EXPORT_MAP in (modulo_puntato, simbolo_origine)."""
    if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
        raw_val = val_node.value.strip()
        if not raw_val:
            return None
        if ":" in raw_val:
            mod_name, orig_name = raw_val.split(":", 1)
            mod_name = mod_name.strip()
            orig_name = orig_name.strip() or export_name
            return (mod_name, orig_name) if mod_name else None
        return (raw_val, export_name)

    if isinstance(val_node, (ast.Tuple, ast.List)) and len(val_node.elts) == 2:
        mod_node, sym_node = val_node.elts
        if (
            isinstance(mod_node, ast.Constant)
            and isinstance(mod_node.value, str)
            and isinstance(sym_node, ast.Constant)
            and isinstance(sym_node.value, str)
        ):
            mod_name = mod_node.value.strip()
            orig_name = sym_node.value.strip() or export_name
            if mod_name:
                return (mod_name, orig_name)
    return None


def extract_lazy_export_specs(tree: ast.AST) -> Dict[str, Tuple[str, str]]:
    """Estrae da AST la mappa simbolo_esportato -> (modulo_puntato, simbolo_origine)."""
    specs: Dict[str, Tuple[str, str]] = {}
    for stmt in _iter_module_level_statements(tree):
        val_node: Optional[ast.AST] = None
        if isinstance(stmt, ast.Assign):
            has_target = any(
                isinstance(t, ast.Name) and t.id == "_LAZY_EXPORT_MAP"
                for t in stmt.targets
            )
            if has_target:
                val_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            if (
                isinstance(stmt.target, ast.Name)
                and stmt.target.id == "_LAZY_EXPORT_MAP"
            ):
                val_node = stmt.value

        if not isinstance(val_node, ast.Dict):
            continue
        for k_node, v_node in zip(val_node.keys, val_node.values):
            if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                continue
            export_name = k_node.value.strip()
            if not export_name:
                continue
            parsed = _parse_lazy_export_entry(export_name, v_node)
            if parsed is not None:
                specs[export_name] = parsed
    return specs


def extract_lazy_export_map(tree: ast.AST) -> Dict[str, str]:
    """Estrae da AST la mappa simbolo_esportato -> modulo_puntato."""
    specs = extract_lazy_export_specs(tree)
    return {sym: mod_name for sym, (mod_name, _) in specs.items()}


def group_lazy_exports_by_module(tree: ast.AST) -> Dict[str, Set[str]]:
    """Raggruppa i simboli origine per modulo di destinazione."""
    grouped: Dict[str, Set[str]] = {}
    for _, (mod_name, orig_sym) in extract_lazy_export_specs(tree).items():
        grouped.setdefault(mod_name, set()).add(orig_sym)
    return grouped


def group_lazy_export_pairs_by_module(
    tree: ast.AST,
) -> Dict[str, List[Tuple[str, str]]]:
    """Raggruppa coppie (simbolo_origine, alias_esportato) per modulo."""
    grouped: Dict[str, List[Tuple[str, str]]] = {}
    for export_sym, (mod_name, orig_sym) in extract_lazy_export_specs(tree).items():
        grouped.setdefault(mod_name, []).append((orig_sym, export_sym))
    return grouped


def resolve_dotted_module_file(
    module_name: str,
    search_roots: Sequence[Path],
    cur_dir: Optional[Path] = None,
    level: int = 0,
    alias_name: Optional[str] = None,
) -> Optional[Path]:
    """Risolve un nome modulo puntato o relativo verso il file .py corrispondente."""
    clean_mod = (module_name or "").split(":", 1)[0].strip()
    eff_level = level
    if clean_mod.startswith(".") and eff_level == 0:
        stripped = clean_mod.lstrip(".")
        eff_level = len(clean_mod) - len(stripped)
        clean_mod = stripped

    if eff_level > 0:
        if cur_dir is None:
            return None
        rel_cur: Optional[Path] = None
        for root in search_roots:
            try:
                rel_cur = cur_dir.resolve().relative_to(root.resolve())
                break
            except ValueError:
                continue
        if rel_cur is None:
            return None
        up = eff_level - 1
        cur_parts = list(rel_cur.parts)
        if up > len(cur_parts):
            return None
        base_parts = cur_parts[: len(cur_parts) - up] if up > 0 else cur_parts
        mod_parts = [p for p in clean_mod.split(".") if p] if clean_mod else []
        if not mod_parts and alias_name and alias_name != "*":
            mod_parts = [alias_name]
        if not mod_parts:
            return None
        rel_parts = [*base_parts, *mod_parts]
    else:
        if not clean_mod:
            return None
        parts = [p for p in clean_mod.split(".") if p]
        if not parts:
            return None
        rel_parts = parts[1:] if (parts[0] == "scripts" and len(parts) > 1) else parts

    for root in search_roots:
        py_cand = root.joinpath(*rel_parts).with_suffix(".py")
        if py_cand.is_file():
            return py_cand.resolve()
        pkg_cand = root.joinpath(*rel_parts, "__init__.py")
        if pkg_cand.is_file():
            return pkg_cand.resolve()
    return None


def resolve_scripts_search_roots(file_path: Path) -> List[Path]:
    """Restituisce le cartelle scripts overlay (staging prima di produzione) da file_path."""
    try:
        resolved = file_path.resolve()
    except OSError:
        resolved = file_path
    roots: List[Path] = []
    seen: Set[Path] = set()

    def _add(cand: Path) -> None:
        if cand.is_dir():
            try:
                res = cand.resolve()
            except OSError:
                res = cand
            if res not in seen:
                seen.add(res)
                roots.append(cand)

    for anc in (resolved.parent, *resolved.parent.parents):
        if anc.name == "scripts":
            if anc.parent.name == ".staging":
                _add(anc)
                _add(anc.parent.parent / "scripts")
            else:
                _add(anc.parent / ".staging" / "scripts")
                _add(anc)
            break
        if anc.name == ".staging":
            _add(anc / "scripts")
            _add(anc.parent / "scripts")
            break
    if not roots:
        _add(resolved.parent)
    return roots


_CLASS_EXPORT_CACHE: Dict[Tuple[Path, int, int], List[str]] = {}


def collect_exported_class_names(
    tree: ast.AST,
    file_path: Path,
    search_roots: Optional[Sequence[Path]] = None,
    visited: Optional[Set[Path]] = None,
    _memo: Optional[Dict[Path, Set[str]]] = None,
) -> List[str]:
    """Raccoglie le ClassDef dirette e quelle riesportate localmente via ImportFrom o _LAZY_EXPORT_MAP."""
    direct_classes = [
        node.name
        for node in getattr(tree, "body", [])
        if isinstance(node, ast.ClassDef)
    ]
    memo = _memo if _memo is not None else {}
    seen_visited = set(visited or ())
    cur_resolved: Optional[Path] = None
    try:
        cur_resolved = file_path.resolve()
        if cur_resolved in memo:
            return sorted(memo[cur_resolved])
        seen_visited.add(cur_resolved)
    except OSError:
        pass
    roots = list(search_roots) if search_roots else resolve_scripts_search_roots(file_path)
    cur_dir = file_path.parent
    result: List[str] = list(direct_classes)
    seen_names: Set[str] = set(result)

    def _local_mod_classes(
        mod_file: Path, wanted: Optional[Set[str]]
    ) -> Set[str]:
        rp = mod_file.resolve()
        if rp in memo:
            cached = memo[rp]
            return cached if wanted is None else (cached & wanted)
        if rp in seen_visited:
            return set()
        try:
            st = rp.stat()
            ckey = (rp, st.st_mtime_ns, st.st_size)
            if ckey in _CLASS_EXPORT_CACHE:
                cls_set = set(_CLASS_EXPORT_CACHE[ckey])
                memo[rp] = cls_set
                return cls_set if wanted is None else (cls_set & wanted)
            sub_src = rp.read_text(encoding="utf-8-sig")
            sub_tree = ast.parse(sub_src, filename=rp.name)
        except Exception:
            memo[rp] = set()
            return set()
        nested = collect_exported_class_names(
            sub_tree, rp, search_roots=roots, visited=seen_visited | {rp}, _memo=memo
        )
        cls_set = set(nested)
        memo[rp] = cls_set
        _CLASS_EXPORT_CACHE[ckey] = sorted(cls_set)
        return cls_set if wanted is None else (cls_set & wanted)

    for stmt in _iter_module_level_statements(tree):
        if not isinstance(stmt, ast.ImportFrom):
            continue
        mod_name = stmt.module or ""
        clean_mod = mod_name[len("scripts.") :] if mod_name.startswith("scripts.") else mod_name
        is_local = stmt.level > 0 or clean_mod.startswith(("_internal.", "schemas.")) or clean_mod in ("_internal", "schemas")
        if not is_local:
            continue
        grouped_aliases: Dict[Path, List[ast.alias]] = {}
        for alias in stmt.names:
            mod_file = resolve_dotted_module_file(
                mod_name,
                roots,
                cur_dir=cur_dir,
                level=stmt.level,
                alias_name=alias.name if stmt.module is None else None,
            )
            if mod_file is not None:
                grouped_aliases.setdefault(mod_file, []).append(alias)
        for mod_file, aliases in grouped_aliases.items():
            has_star = any(a.name == "*" for a in aliases)
            wanted_syms = None if has_star else {a.name for a in aliases}
            avail = _local_mod_classes(mod_file, wanted_syms)
            for alias in aliases:
                if alias.name == "*":
                    for cls_n in sorted(avail):
                        if not cls_n.startswith("_") and cls_n not in seen_names:
                            seen_names.add(cls_n)
                            result.append(cls_n)
                elif alias.name in avail:
                    pub_name = alias.asname or alias.name
                    if pub_name not in seen_names:
                        seen_names.add(pub_name)
                        result.append(pub_name)

    for mod_name, pairs in group_lazy_export_pairs_by_module(tree).items():
        clean_mod = mod_name[len("scripts.") :] if mod_name.startswith("scripts.") else mod_name
        if not (clean_mod.startswith(("_internal.", "schemas.", ".")) or clean_mod in ("_internal", "schemas")):
            continue
        mod_file = resolve_dotted_module_file(mod_name, roots, cur_dir=cur_dir)
        if mod_file is None:
            continue
        avail = _local_mod_classes(mod_file, {orig for orig, _ in pairs})
        for orig_sym, export_sym in pairs:
            if orig_sym in avail and export_sym not in seen_names:
                seen_names.add(export_sym)
                result.append(export_sym)

    if cur_resolved is not None:
        memo[cur_resolved] = set(result)
    return result
