"""Validazione record Pydantic e risoluzione ricorsiva re-export locali."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.ast_guard_validator.signature_collector import SignatureCollector
from _internal.ast_guard_validator.validator_helpers import load_file_ast_cached
from _internal.nk_common.lane_paths import LANE_CONTAINER_DIRNAME, strip_staging_rel_parts

try:
    from _internal.nk_common.ast_exports import (
        extract_lazy_export_specs,
        group_lazy_exports_by_module,
        resolve_dotted_module_file,
    )
except ImportError:  # pragma: no cover
    import _internal.nk_common as _nk_common_pkg

    _stg_common_dir = str(Path(__file__).resolve().parent.parent / "nk_common")
    if hasattr(_nk_common_pkg, "__path__") and _stg_common_dir not in _nk_common_pkg.__path__:
        _nk_common_pkg.__path__.insert(0, _stg_common_dir)
    from _internal.nk_common.ast_exports import (
        extract_lazy_export_specs,
        group_lazy_exports_by_module,
        resolve_dotted_module_file,
    )


def validate_pydantic_catalog_records(
    records: List[Dict[str, Any]], model_cls: Any
) -> Dict[str, Any]:
    """Valida in RAM una lista di record di catalogo contro un modello Pydantic ([RULE-02.5])."""
    errors: List[Dict[str, Any]] = []
    valid_count = 0
    validate_fn = getattr(model_cls, "model_validate", None)
    for idx, rec in enumerate(records):
        try:
            if callable(validate_fn):
                validate_fn(rec)
            else:
                model_cls(**rec)
            valid_count += 1
        except Exception as exc:
            errors.append({"index": idx, "error": str(exc)})
    return {
        "passed": len(errors) == 0,
        "total_records": len(records),
        "valid_records": valid_count,
        "invalid_records": len(errors),
        "errors": errors,
    }


def _resolve_target_path(target_file: str) -> Path:
    """Risolve un percorso file rispetto a cwd gestendo errori OSError su path sintetici."""
    raw_path = Path(target_file)
    base = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
    try:
        return base.resolve()
    except OSError:
        return base


def _staging_hub_from_scripts_anc(anc: Path) -> Optional[Path]:
    """Restituisce hub_root se anc e .staging/scripts oppure .staging/lanes/<id>/scripts."""
    if anc.parent.name == ".staging":
        return anc.parent.parent
    if anc.parent.parent.name == LANE_CONTAINER_DIRNAME and anc.parent.parent.parent.name == ".staging":
        return anc.parent.parent.parent.parent
    return None


def _collect_roots_from_staging_dir(anc: Path, resolved: Path) -> List[Path]:
    """Raccoglie le root scripts/ dalla directory .staging/ o dalla sua lane."""
    idx, _rel, lane = strip_staging_rel_parts(resolved.parts)
    stg_scripts = (anc / LANE_CONTAINER_DIRNAME / lane / "scripts") if (idx >= 0 and lane) else (anc / "scripts")
    prod_scripts = anc.parent / "scripts"
    roots: List[Path] = []
    if stg_scripts.is_dir():
        roots.append(stg_scripts)
    if prod_scripts.is_dir():
        roots.append(prod_scripts)
    return roots


def _resolve_prod_from_staging_dir(anc: Path, resolved: Path) -> Tuple[List[Path], Optional[Path]]:
    """Restituisce (prod_roots, pre_cur) per file dentro .staging/ o lane."""
    prod_scripts = anc.parent / "scripts"
    roots = [prod_scripts] if prod_scripts.is_dir() else []
    _idx, rel_parts, _lane = strip_staging_rel_parts(resolved.parent.parts)
    cand_dir = anc.parent.joinpath(*rel_parts) if rel_parts else None
    pre_cur = cand_dir if (cand_dir is not None and cand_dir.is_dir()) else None
    return roots, pre_cur


def _resolve_local_import_roots(
    target_file: str,
) -> Tuple[List[Path], Optional[Path]]:
    """Determina le directory scripts overlay (staging/lane > prod) e la directory target."""
    if not target_file or target_file.startswith("<"):
        return [], None
    resolved = _resolve_target_path(target_file)
    roots: List[Path] = []
    for anc in (resolved.parent, *resolved.parent.parents):
        if anc.name == "scripts":
            hub_from_stg = _staging_hub_from_scripts_anc(anc)
            if hub_from_stg is not None:
                roots.append(anc)
                prod_scripts = hub_from_stg / "scripts"
                if prod_scripts.is_dir() and prod_scripts != anc:
                    roots.append(prod_scripts)
            else:
                stg_scripts = anc.parent / ".staging" / "scripts"
                if stg_scripts.is_dir() and stg_scripts != anc:
                    roots.append(stg_scripts)
                roots.append(anc)
            break
        if anc.name == ".staging":
            roots.extend(_collect_roots_from_staging_dir(anc, resolved))
            break
    cur_dir = resolved.parent if resolved.parent.is_dir() else None
    return roots, cur_dir


def _resolve_prod_import_roots(
    target_file: str,
) -> Tuple[List[Path], Optional[Path]]:
    """Determina esclusivamente le directory scripts di produzione per pre_collector (H4*)."""
    if not target_file or target_file.startswith("<"):
        return [], None
    resolved = _resolve_target_path(target_file)
    for anc in (resolved.parent, *resolved.parent.parents):
        if anc.name == "scripts":
            hub_from_stg = _staging_hub_from_scripts_anc(anc)
            if hub_from_stg is not None:
                prod_scripts = hub_from_stg / "scripts"
                if not prod_scripts.is_dir():
                    return [], None
                cand_dir = prod_scripts / resolved.parent.relative_to(anc)
                return [prod_scripts], (cand_dir if cand_dir.is_dir() else prod_scripts)
            cur_dir = resolved.parent if resolved.parent.is_dir() else None
            return [anc], cur_dir
        if anc.name == ".staging":
            return _resolve_prod_from_staging_dir(anc, resolved)
    cur_dir = resolved.parent if resolved.parent.is_dir() else None
    return [], cur_dir


def _is_type_checking_guard(test_node: ast.AST) -> bool:
    """Restituisce True se il test corrisponde a TYPE_CHECKING o typing.TYPE_CHECKING."""
    if isinstance(test_node, ast.Name):
        return test_node.id == "TYPE_CHECKING"
    if isinstance(test_node, ast.Attribute):
        return test_node.attr == "TYPE_CHECKING"
    return False


def _is_negated_type_checking_guard(test_node: ast.AST) -> bool:
    """Restituisce True per guardie 'if not TYPE_CHECKING:'."""
    return (
        isinstance(test_node, ast.UnaryOp)
        and isinstance(test_node.op, ast.Not)
        and _is_type_checking_guard(test_node.operand)
    )


def _iter_compound_children(stmt: ast.AST) -> List[ast.AST]:
    """Estrae i figli eseguibili a runtime di statement composti escludendo TYPE_CHECKING."""
    if isinstance(stmt, ast.If):
        if _is_type_checking_guard(stmt.test):
            return list(stmt.orelse)
        if _is_negated_type_checking_guard(stmt.test):
            return list(stmt.body)
    children: List[ast.AST] = []
    for attr in ("body", "orelse", "handlers", "finalbody"):
        sub = getattr(stmt, attr, None)
        if isinstance(sub, list):
            for child in sub:
                if isinstance(child, ast.ExceptHandler):
                    children.extend(child.body)
                else:
                    children.append(child)
    return children


def _iter_top_level_import_from(tree: ast.AST) -> List[ast.ImportFrom]:
    """Estrae i nodi ast.ImportFrom eseguiti al livello top-level escludendo TYPE_CHECKING."""
    collected: List[ast.ImportFrom] = []
    stack: List[ast.AST] = list(getattr(tree, "body", []))
    while stack:
        stmt = stack.pop(0)
        if isinstance(stmt, ast.ImportFrom):
            collected.append(stmt)
        elif isinstance(
            stmt, (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor)
        ):
            stack.extend(_iter_compound_children(stmt))
    return collected


def _resolve_import_from_module_file(
    node: ast.ImportFrom,
    search_roots: List[Path],
    cur_dir: Optional[Path],
    alias_name: Optional[str] = None,
) -> Optional[Path]:
    """Risolve un ast.ImportFrom locale verso il file .py corrispondente nell'overlay."""
    return resolve_dotted_module_file(
        node.module or "",
        search_roots,
        cur_dir=cur_dir,
        level=node.level,
        alias_name=alias_name,
    )


def _merge_symbol_from_collector(
    src_collector: SignatureCollector,
    orig_name: str,
    as_name: str,
    dst_collector: SignatureCollector,
) -> None:
    """Copia classi, basi ereditarie, metodi e funzioni importate nel collector di destinazione."""
    if orig_name == "*":
        for cls_name in list(src_collector.classes):
            if not cls_name.startswith("_"):
                _merge_symbol_from_collector(
                    src_collector, cls_name, cls_name, dst_collector
                )
        for sig_key in list(src_collector.signatures):
            if "." not in sig_key and not sig_key.startswith("_"):
                _merge_symbol_from_collector(
                    src_collector, sig_key, sig_key, dst_collector
                )
        for gname in list(src_collector.defined_globals):
            if not gname.startswith("_"):
                dst_collector.defined_globals.add(gname)
        return

    if orig_name in src_collector.classes or orig_name in src_collector.class_bases:
        dst_collector.classes.add(as_name)
        dst_collector.class_bases[as_name] = list(
            src_collector.class_bases.get(orig_name, [])
        )
        prefix = f"{orig_name}."
        for sig_key, sig_val in src_collector.signatures.items():
            if sig_key.startswith(prefix):
                suffix = sig_key[len(prefix) :]
                dst_collector.signatures[f"{as_name}.{suffix}"] = sig_val
        for nested_key, nested_bases in src_collector.class_bases.items():
            if nested_key.startswith(prefix):
                suffix = nested_key[len(prefix) :]
                dst_collector.classes.add(nested_key.split(".")[-1])
                dst_collector.class_bases[f"{as_name}.{suffix}"] = list(nested_bases)

    if orig_name in src_collector.signatures:
        src_sig = src_collector.signatures[orig_name]
        if as_name != orig_name:
            src_sig = src_sig.model_copy(update={"name": as_name})
        dst_collector.signatures[as_name] = src_sig

    dst_collector.defined_globals.add(as_name)
    dst_collector.imported_names.add(as_name)


def _load_valid_module_ast(rp: Path) -> Optional[ast.AST]:
    """Carica AST modulo locale tramite RepoSnapshotCache restituendo None su errore."""
    tree, syn_err = load_file_ast_cached(rp)
    return tree if (syn_err is None and tree is not None) else None


def _collect_resolved_module(
    module_path: Path,
    search_roots: List[Path],
    skip_unparse: bool,
    visited: Set[Path],
    cache: Dict[Path, SignatureCollector],
) -> SignatureCollector:
    """Analizza ricorsivamente un modulo locale risolvendone i re-export senza cicli infiniti."""
    rp = module_path.resolve()
    if rp in cache:
        return cache[rp]
    mod_collector = SignatureCollector()
    if skip_unparse:
        mod_collector.skip_unparse = True  # type: ignore[attr-defined]
    if rp in visited:
        return mod_collector
    tree = _load_valid_module_ast(rp)
    if tree is None:
        cache[rp] = mod_collector
        return mod_collector
    mod_collector.visit(tree)
    _resolve_local_import_exports(
        tree=tree,
        collector=mod_collector,
        search_roots=search_roots,
        cur_dir=rp.parent,
        skip_unparse=skip_unparse,
        visited=visited | {rp},
        cache=cache,
    )
    cache[rp] = mod_collector
    return mod_collector


def _resolve_local_import_exports(
    tree: ast.AST,
    collector: SignatureCollector,
    search_roots: List[Path],
    cur_dir: Optional[Path],
    skip_unparse: bool,
    visited: Set[Path],
    cache: Dict[Path, SignatureCollector],
) -> None:
    """Arricchisce un SignatureCollector risolvendo i re-export da moduli locali e _LAZY_EXPORT_MAP."""
    for imp_node in _iter_top_level_import_from(tree):
        for alias in imp_node.names:
            mod_file = _resolve_import_from_module_file(
                imp_node,
                search_roots,
                cur_dir,
                alias_name=alias.name if imp_node.module is None else None,
            )
            if mod_file is None:
                continue
            src_collector = _collect_resolved_module(
                mod_file,
                search_roots=search_roots,
                skip_unparse=skip_unparse,
                visited=visited,
                cache=cache,
            )
            as_name = alias.asname or alias.name
            _merge_symbol_from_collector(src_collector, alias.name, as_name, collector)

    lazy_by_mod = group_lazy_exports_by_module(tree)
    if not lazy_by_mod:
        return
    lazy_specs = extract_lazy_export_specs(tree)
    for mod_name, export_names in lazy_by_mod.items():
        mod_file = resolve_dotted_module_file(
            mod_name, search_roots, cur_dir=cur_dir
        )
        if mod_file is None:
            continue
        src_collector = _collect_resolved_module(
            mod_file,
            search_roots=search_roots,
            skip_unparse=skip_unparse,
            visited=visited,
            cache=cache,
        )
        matched_pairs = [
            (orig_sym, as_sym)
            for as_sym, (spec_mod, orig_sym) in lazy_specs.items()
            if spec_mod == mod_name and orig_sym in export_names
        ]
        if not matched_pairs:
            matched_pairs = [(sym, sym) for sym in sorted(export_names)]
        for orig_sym, as_sym in matched_pairs:
            _merge_symbol_from_collector(src_collector, orig_sym, as_sym, collector)
