# -*- coding: utf-8 -*-
"""
Golden Test GT-NEW-03 v6.4.0-Carbon: DSM AST Tarjan SCC, Kahn Topological Sort e GT-14 CRIT-01.
Modulo: tests/test_gt14_and_dsm.py.
Zero mock/stub; verifica 0 cicli Tarjan, 37/37 Kahn, 116/116 classi uniche, 6 flag fastguard e GT-14.
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        load_script_by_relpath as _load_mod,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        load_script_by_relpath as _load_mod,
    )

pytestmark = pytest.mark.fast

idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")


def _overlay_python_files(include_internal: bool) -> Dict[str, Path]:
    """Raccoglie i moduli scripts/ privilegiando .staging/ rispetto alla produzione."""
    prod_scripts = _WORKSPACE_ROOT / "scripts"
    stg_scripts = _WORKSPACE_ROOT / ".staging" / "scripts"
    files_by_rel: Dict[str, Path] = {}

    if include_internal:
        for base in (prod_scripts, stg_scripts):
            if not base.is_dir():
                continue
            for py_path in sorted(base.rglob("*.py")):
                rel = py_path.relative_to(base).as_posix()
                files_by_rel[rel] = py_path
    else:
        for base in (prod_scripts, stg_scripts):
            if not base.is_dir():
                continue
            for py_path in sorted(base.glob("*.py")):
                rel = py_path.relative_to(base).as_posix()
                files_by_rel[rel] = py_path
            schemas_dir = base / "schemas"
            if schemas_dir.is_dir():
                for py_path in sorted(schemas_dir.glob("*.py")):
                    rel = py_path.relative_to(base).as_posix()
                    files_by_rel[rel] = py_path
    return files_by_rel


_AST_CACHE: Dict[Path, ast.Module] = {}
_AST_FACTS_CACHE: Dict[Path, Tuple[Tuple[str, ...], Tuple[Tuple[int, str, Tuple[str, ...]], ...], Tuple[str, ...]]] = {}


def _parse_cached_ast(py_path: Path) -> ast.Module:
    """Esegue parsing AST con cache per evitare riletture duplicate dei moduli."""
    cached = _AST_CACHE.get(py_path)
    if cached is not None:
        return cached
    tree = ast.parse(py_path.read_text(encoding="utf-8-sig"), filename=py_path.name)
    _AST_CACHE[py_path] = tree
    return tree


def _collect_ast_facts(
    py_path: Path,
) -> Tuple[Tuple[str, ...], Tuple[Tuple[int, str, Tuple[str, ...]], ...], Tuple[str, ...]]:
    """Estrae import e nomi classe in una singola scansione AST memoizzata per file."""
    cached = _AST_FACTS_CACHE.get(py_path)
    if cached is not None:
        return cached
    tree = _parse_cached_ast(py_path)
    imports: List[str] = []
    from_imports: List[Tuple[int, str, Tuple[str, ...]]] = []
    class_names: List[str] = []
    stack: List[Any] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
            continue
        if isinstance(node, ast.ImportFrom):
            from_imports.append((node.level, node.module or "", tuple(a.name for a in node.names)))
            continue
        if isinstance(node, ast.ClassDef):
            class_names.append(node.name)
        for attr in ("body", "orelse", "finalbody", "handlers", "cases"):
            sub = getattr(node, attr, None)
            if isinstance(sub, list):
                stack.extend(sub)
    facts = (tuple(imports), tuple(from_imports), tuple(class_names))
    _AST_FACTS_CACHE[py_path] = facts
    return facts


def _module_name_from_rel(rel_posix: str) -> str:
    p = Path(rel_posix)
    no_ext = p.with_suffix("")
    parts = no_ext.parts[:-1] if p.name == "__init__.py" else no_ext.parts
    return ".".join(parts) if parts else "__root__"


def _compute_tarjan_and_kahn(files_by_rel: Dict[str, Path]) -> Tuple[int, List[str]]:
    """Calcola gli SCC di Tarjan e l'ordinamento topologico di Kahn sul grafo import AST."""
    mod_to_path: Dict[str, Path] = {
        _module_name_from_rel(rel): path for rel, path in sorted(files_by_rel.items())
    }
    adj: Dict[str, Set[str]] = {m: set() for m in mod_to_path}

    for mod_name, py_path in mod_to_path.items():
        imports, from_imports, _ = _collect_ast_facts(py_path)
        pkg = mod_name if py_path.name == "__init__.py" else (mod_name.rsplit(".", 1)[0] if "." in mod_name else "")
        for imp_name in imports:
            cand = imp_name.removeprefix("scripts.")
            if cand in mod_to_path and cand != mod_name:
                adj[mod_name].add(cand)
        for level, raw_mod, alias_names in from_imports:
            base = raw_mod
            if level > 0:
                pkg_parts = pkg.split(".") if pkg else []
                keep_n = max(0, len(pkg_parts) - (level - 1))
                prefix = ".".join(pkg_parts[:keep_n])
                base = f"{prefix}.{base}".strip(".") if base else prefix
            base = base.removeprefix("scripts.")
            for alias_name in alias_names:
                cand = f"{base}.{alias_name}".strip(".")
                if cand in mod_to_path and cand != mod_name:
                    adj[mod_name].add(cand)
            if base in mod_to_path and base != mod_name:
                adj[mod_name].add(base)

    index_counter = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    sccs: List[List[str]] = []

    def strongconnect(node_id: str) -> None:
        nonlocal index_counter
        indices[node_id] = index_counter
        lowlink[node_id] = index_counter
        index_counter += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for nxt in sorted(adj[node_id]):
            if nxt not in indices:
                strongconnect(nxt)
                lowlink[node_id] = min(lowlink[node_id], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node_id] = min(lowlink[node_id], indices[nxt])
        if lowlink[node_id] == indices[node_id]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == node_id:
                    break
            sccs.append(comp)

    for node_id in sorted(adj):
        if node_id not in indices:
            strongconnect(node_id)

    cycles = [c for c in sccs if len(c) > 1 or (c[0] in adj[c[0]])]

    indegree: Dict[str, int] = {m: 0 for m in adj}
    for src_m, nbrs in adj.items():
        for dst_m in nbrs:
            indegree[dst_m] += 1
    queue: deque[str] = deque(sorted(m for m, deg in indegree.items() if deg == 0))
    kahn_order: List[str] = []
    while queue:
        cur = queue.popleft()
        kahn_order.append(cur)
        for dst_m in sorted(adj[cur]):
            indegree[dst_m] -= 1
            if indegree[dst_m] == 0:
                queue.append(dst_m)

    return len(cycles), kahn_order


def test_ast_tarjan_scc_and_kahn_topological_sort_on_scripts() -> None:
    """Verifica 0 cicli Tarjan SCC e ordinamento topologico di Kahn su canonici e su tutto scripts/."""
    canon_files = _overlay_python_files(include_internal=False)
    assert len(canon_files) >= 35
    canon_cycles, canon_kahn = _compute_tarjan_and_kahn(canon_files)
    assert canon_cycles == 0
    assert len(canon_kahn) == len(canon_files)

    all_files = _overlay_python_files(include_internal=True)
    assert len(all_files) >= 130
    all_cycles, all_kahn = _compute_tarjan_and_kahn(all_files)
    assert all_cycles == 0
    assert len(all_kahn) == len(all_files)
    assert all(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) <= 400 for p in all_files.values())


def test_unique_class_defs_fastguard_flags_and_gt14_crit01_governance() -> None:
    """Verifica classi AST uniche, 6 flag CLI di nk_acs_fastguard e audit GT-14 CRIT-01."""
    from _internal.nk_common.catalog import get_catalog_counts

    all_files = _overlay_python_files(include_internal=True)
    class_names: List[str] = []
    for py_path in all_files.values():
        class_names.extend(_collect_ast_facts(py_path)[2])

    assert len(class_names) > 0
    assert len(class_names) == len(set(class_names))

    acs_path = all_files["nk_acs_fastguard.py"]
    acs_meta = idx_mod.NKRegistryIndexer._extract_script_metadata(acs_path)
    assert len(acs_meta["cli_flags"]) == 6
    assert set(acs_meta["cli_flags"]) == {
        "--conversation-id",
        "--event",
        "--help",
        "--native-contract",
        "--project-root",
        "--transcript",
    }

    counts = get_catalog_counts(_WORKSPACE_ROOT)
    gov = idx_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT).verify_gt14_crit01_governance()
    assert gov["passed"] is True
    assert gov["agents_checked"] == counts["agents"]
    assert gov["skills_checked"] == counts["skills"]
    assert gov["issues"] == []
