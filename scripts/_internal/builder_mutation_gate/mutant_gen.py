# -*- coding: utf-8 -*-
"""Generazione deterministica di mutanti AST differenziali sulle sole funzioni modificate."""

from __future__ import annotations

import ast
import copy
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict

from _internal.builder_mutation_gate.hotspot_audit import (
    _parse_ast_cached,
    _rank_hotspot_nodes,
    _strip_docstring_stmts,
    _unique_func_qname,
    get_repo_snapshot_cache,
    select_hotspot_functions,
)
from _internal.builder_mutation_gate.operators import (
    OP_ORDER,
    apply_node_mutation,
    is_boundary_context,  # noqa: F401
    is_ignored_scope_node,
    is_path_div_binop,  # noqa: F401
    is_path_expr,  # noqa: F401
    iter_owned_children,
    match_operator_for_node,
    replace_unary_not_child,  # noqa: F401
)

_OP_ORDER = OP_ORDER


class MutantSpec(BaseModel):
    """Specifica immutabile di un singolo mutante AST differenziale."""

    model_config = ConfigDict(strict=True, extra="forbid")
    mutant_id: str
    operator: str
    rel_path: str
    function_name: str
    line_number: int
    original_snippet: str
    mutated_snippet: str
    mutated_source: str


def _iter_func_nodes(tree: ast.AST) -> List[Tuple[str, ast.AST]]:
    """Elenca in ordine deterministico i nodi funzione/metodo con chiave univoca."""
    found: List[Tuple[str, ast.AST]] = []
    seen: Set[str] = set()

    def _visit(body: List[ast.stmt], prefix: str) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                nxt = f"{prefix}.{stmt.name}" if prefix else stmt.name
                _visit(stmt.body, nxt)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = _unique_func_qname(stmt, prefix, seen)
                found.append((qname, stmt))
                _visit(stmt.body, qname)

    if isinstance(tree, ast.Module):
        _visit(tree.body, "")
    return found


def _dump_func_executable(stmt: ast.AST) -> str:
    """Serializza AST della funzione ignorando la sola docstring iniziale."""
    cloned = copy.copy(stmt)
    if hasattr(cloned, "body"):
        cloned.body = _strip_docstring_stmts(getattr(stmt, "body", []))
    return ast.dump(cloned, include_attributes=False)


def _collect_func_dumps(tree: ast.AST) -> Dict[str, str]:
    """Mappa il nome qualificato univoco di ogni funzione al dump AST eseguibile."""
    return {
        qname: _dump_func_executable(stmt)
        for qname, stmt in _iter_func_nodes(tree)
    }


def _dump_module_executable(tree: ast.Module) -> str:
    """Serializza il modulo AST ignorando la docstring iniziale per rilevare diff eseguibili."""
    cloned = copy.copy(tree)
    cloned.body = [
        copy.copy(st) if not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) else st
        for st in _strip_docstring_stmts(tree.body)
    ]
    for idx, st in enumerate(cloned.body):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(st, "body"):
            fn_copy = copy.copy(st)
            fn_copy.body = _strip_docstring_stmts(st.body)
            cloned.body[idx] = fn_copy
    return ast.dump(cloned, include_attributes=False)


def has_executable_python_diff(pre_code: Optional[str], post_code: str) -> bool:
    """True se tra pre_code e post_code esiste una modifica AST eseguibile non limitata a docstring."""
    post_tree = _parse_ast_cached(post_code)
    if post_tree is None:
        return True
    if pre_code is None or not pre_code.strip():
        return bool(_strip_docstring_stmts(post_tree.body))
    pre_tree = _parse_ast_cached(pre_code)
    if pre_tree is None:
        return True
    return _dump_module_executable(pre_tree) != _dump_module_executable(post_tree)


def find_touched_functions(pre_code: Optional[str], post_code: str) -> Set[str]:
    """Restituisce i nomi qualificati delle funzioni aggiunte o modificate rispetto a pre_code."""
    post_tree = _parse_ast_cached(post_code)
    if post_tree is None:
        return set()
    post_dumps = _collect_func_dumps(post_tree)
    if pre_code is None or not pre_code.strip():
        return set(post_dumps.keys())
    pre_tree = _parse_ast_cached(pre_code)
    if pre_tree is None:
        return set(post_dumps.keys())
    pre_dumps = _collect_func_dumps(pre_tree)
    return {q for q, dump_s in post_dumps.items() if pre_dumps.get(q) != dump_s}


def _iter_owned_body_nodes(
    func_node: ast.AST,
) -> List[Tuple[int, ast.AST, Optional[ast.AST]]]:
    """Elenca i nodi AST nel corpo escludendo docstring, firme, type annotations e sotto-scope."""
    body = _strip_docstring_stmts(getattr(func_node, "body", []))
    items: List[Tuple[int, ast.AST, Optional[ast.AST]]] = []
    stack: List[Tuple[ast.AST, Optional[ast.AST]]] = [(stmt, func_node) for stmt in reversed(body)]
    while stack:
        node, parent = stack.pop()
        if is_ignored_scope_node(node):
            continue
        items.append((len(items), node, parent))
        for child in reversed(iter_owned_children(node)):
            stack.append((child, node))
    return items


def _match_operator_for_node(node: ast.AST, parent: Optional[ast.AST]) -> Optional[str]:
    """Classifica il singolo nodo AST in una delle 8 famiglie tramite tabella lookup."""
    return match_operator_for_node(node, parent)


def _apply_node_mutation(node: ast.AST, op_name: str, parent: Optional[ast.AST] = None) -> str:
    """Applica in-place la mutazione richiesta restituendo lo snippet mutato."""
    return apply_node_mutation(node, op_name, parent=parent)


def _select_round_robin(
    buckets: Dict[str, List[Tuple[str, int, ast.AST]]],
    limit: int,
) -> List[Tuple[str, str, int, ast.AST]]:
    """Seleziona fino a limit candidati in round-robin tra le famiglie di mutazione."""
    selected: List[Tuple[str, str, int, ast.AST]] = []
    cursors: Dict[str, int] = {op: 0 for op in _OP_ORDER}
    while len(selected) < limit:
        progressed = False
        for op_name in _OP_ORDER:
            items = buckets.get(op_name, [])
            idx = cursors[op_name]
            if idx < len(items):
                qname, node_idx, orig_node = items[idx]
                selected.append((op_name, qname, node_idx, orig_node))
                cursors[op_name] = idx + 1
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
    return selected


def _materialize_mutant(
    base_tree: ast.AST,
    rel_path: str,
    post_code: str,
    seq_no: int,
    op_name: str,
    qname: str,
    node_idx: int,
    orig_node: ast.AST,
) -> Optional[MutantSpec]:
    """Crea una copia AST mutata, verifica la compilabilita syntax e restituisce MutantSpec."""
    _ = post_code
    mut_tree = copy.deepcopy(base_tree)
    target_fn = next((fn for name, fn in _iter_func_nodes(mut_tree) if name == qname), None)
    if target_fn is None:
        return None
    owned_nodes = _iter_owned_body_nodes(target_fn)
    if node_idx >= len(owned_nodes):
        return None
    orig_unparsed = ast.unparse(base_tree)
    _, mut_node, mut_parent = owned_nodes[node_idx]
    orig_snip = ast.unparse(orig_node)
    mut_snip = _apply_node_mutation(mut_node, op_name, parent=mut_parent)
    ast.fix_missing_locations(mut_tree)
    mut_src = ast.unparse(mut_tree)
    if mut_src == orig_unparsed:
        return None
    if _parse_ast_cached(mut_src) is None:
        return None
    return MutantSpec(
        mutant_id=f"MUT-{seq_no:02d}-{op_name}",
        operator=op_name,
        rel_path=rel_path,
        function_name=qname,
        line_number=int(getattr(orig_node, "lineno", 1)),
        original_snippet=orig_snip[:160],
        mutated_snippet=mut_snip[:160],
        mutated_source=mut_src + "\n",
    )


def generate_differential_mutants(
    rel_path: str,
    pre_code: Optional[str],
    post_code: str,
    *,
    max_mutants: int = 8,
) -> List[MutantSpec]:
    """Genera fino a max_mutants mutanti AST deterministici sulle sole funzioni modificate."""
    cap = max(0, min(int(max_mutants), 8))
    if cap == 0:
        return []
    touched = find_touched_functions(pre_code, post_code)
    if not touched:
        return []
    post_tree = _parse_ast_cached(post_code)
    if post_tree is None:
        return []

    buckets: Dict[str, List[Tuple[str, int, ast.AST]]] = {op: [] for op in _OP_ORDER}
    for qname, fn_node in _iter_func_nodes(post_tree):
        if qname not in touched:
            continue
        for node_idx, node, parent in _iter_owned_body_nodes(fn_node):
            op_name = _match_operator_for_node(node, parent)
            if op_name is not None:
                buckets[op_name].append((qname, node_idx, node))

    picks = _select_round_robin(buckets, cap * 2)
    mutants: List[MutantSpec] = []
    for op_name, qname, node_idx, orig_node in picks:
        spec = _materialize_mutant(
            post_tree, rel_path, post_code, len(mutants) + 1, op_name, qname, node_idx, orig_node
        )
        if spec is not None:
            mutants.append(spec)
            if len(mutants) >= cap:
                break
    return mutants


def _collect_hotspot_buckets(fn_node: ast.AST, qname: str) -> Dict[str, List[Tuple[str, int, ast.AST]]]:
    """Raccoglie i nodi mutabili di una funzione hotspot raggruppati per operatore."""
    buckets: Dict[str, List[Tuple[str, int, ast.AST]]] = {op: [] for op in _OP_ORDER}
    for node_idx, node, parent in _iter_owned_body_nodes(fn_node):
        if (op_name := _match_operator_for_node(node, parent)) is not None:
            buckets[op_name].append((qname, node_idx, node))
    return buckets


def generate_audit_mutants(
    rel_path: str,
    post_code: str,
    *,
    max_audit_mutants: int = 16,
) -> List[MutantSpec]:
    """Genera fino a 16 mutanti AST prioritari sulle funzioni hotspot del modulo."""
    if (cap := min(int(max_audit_mutants), 16)) <= 0 or (post_tree := _parse_ast_cached(post_code)) is None:
        return []
    picks: List[Tuple[str, str, int, ast.AST]] = []
    for qname, fn_node in _rank_hotspot_nodes(post_tree):
        picks.extend(_select_round_robin(_collect_hotspot_buckets(fn_node, qname), cap * 2))
        if len(picks) >= cap * 2:
            break
    mutants: List[MutantSpec] = []
    for op_name, qname, node_idx, orig_node in picks:
        if (spec := _materialize_mutant(post_tree, rel_path, post_code, len(mutants) + 1, op_name, qname, node_idx, orig_node)) is None:
            continue
        mutants.append(spec)
        if len(mutants) >= cap:
            break
    return mutants
