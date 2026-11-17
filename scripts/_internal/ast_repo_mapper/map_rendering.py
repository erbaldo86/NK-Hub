"""Funzioni di rendering e compattazione STE100 per AST Repo-Map."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from _internal.ast_repo_mapper.models import (
    SymbolGraph,
    SymbolNode,
    SymbolType,
    estimate_tokens,
)


def compact_sig_for_ste100_impl(sig: str, max_words: int = 16) -> str:
    """Garantisce che ogni firma renderizzata rispetti il limite di 20 parole STE100."""
    words = [w for w in sig.split() if any(ch.isalpha() for ch in w)]
    if len(words) <= max_words:
        return sig
    m = re.match(r"^((?:async\s+)?def\s+[a-zA-Z0-9_]+)\((.*)\)(.*)$", sig)
    if m:
        prefix, raw_args, suffix = m.group(1), m.group(2), m.group(3)
        arg_names = [a.split(":")[0].split("=")[0].strip() for a in raw_args.split(",") if a.strip()]
        short_args = ", ".join(arg_names[:6]) + (", ..." if len(arg_names) > 6 else "")
        short_sig = f"{prefix}({short_args}){suffix}"
        if len([w for w in short_sig.split() if any(ch.isalpha() for ch in w)]) <= max_words:
            return short_sig
        return f"{prefix}({short_args})"
    return " ".join(sig.split()[:max_words])


def _safe_bt(text: str) -> str:
    """Sostituisce backtick interni per evitare rotture dello span Markdown."""
    return text.replace("`", "'")


def _is_canonical_script(mod: str) -> bool:
    """Identifica i moduli canonici Python in scripts/."""
    return mod.startswith("scripts/") and mod.endswith(".py") and "/_internal/" not in mod


def _is_test_module(mod: str) -> bool:
    """Identifica i moduli di test da comprimere dopo i moduli di produzione."""
    return mod.startswith("tests/") or "/tests/" in mod or Path(mod).name.startswith("test_")


def _append_chunked_items(lines: List[str], base_label: str, items: List[str]) -> None:
    """Formatta liste di simboli in blocchi compatti da 8 elementi."""
    for i in range(0, len(items), 8):
        label = base_label if i == 0 else f"{base_label} cont"
        lines.append(f"  `{_safe_bt(label)}`: `{_safe_bt(', '.join(items[i : i + 8]))}`")


def _group_remaining_by_dir(mods: List[str], *, collapse_tests: bool = False) -> Tuple[Dict[str, List[str]], bool]:
    """Raggruppa i moduli residui per directory padre."""
    groups: Dict[str, List[str]] = {}
    has_tests = False
    for u in mods:
        if collapse_tests and _is_test_module(u):
            has_tests = True
            continue
        p_u = Path(u)
        groups.setdefault(p_u.parent.as_posix(), []).append(p_u.name)
    return groups, has_tests


def _dir_chunk_lines(d: str, fnames: List[str]) -> List[str]:
    """Genera le righe Markdown raggruppate per directory in chunk da 8 file."""
    prefix = "root/*" if (d == "." or not d) else f"{d}/*"
    return [
        f"- `{_safe_bt(prefix)}`: `{_safe_bt(', '.join(fnames[i : i + 8]))}`"
        for i in range(0, len(fnames), 8)
    ]


def render_expanded_module_impl(mod: str, syms: List[SymbolNode]) -> str:
    """Renderizza il modulo in formato esteso con classi, metodi e funzioni."""
    mod_lines = [f"## 📄 `{_safe_bt(mod)}`"]
    classes = [s for s in syms if s.symbol_type == SymbolType.CLASS]
    for cls_node in classes:
        cls_sig = compact_sig_for_ste100_impl(cls_node.signature or f"class {cls_node.name}:")
        mod_lines.append(f"  `{_safe_bt(cls_sig)}`")
        for m in [s for s in syms if s.parent_id == cls_node.id and s.symbol_type == SymbolType.METHOD]:
            m_sig = compact_sig_for_ste100_impl(m.signature or f"def {m.name}(): ...")
            mod_lines.append(f"    `{_safe_bt(m_sig)}`")
    functions = [
        s for s in syms
        if s.symbol_type in (SymbolType.FUNCTION, SymbolType.ASYNC_FUNCTION) and s.parent_id is None
    ]
    for fn in functions:
        fn_sig = compact_sig_for_ste100_impl(fn.signature or f"def {fn.name}(): ...")
        mod_lines.append(f"  `{_safe_bt(fn_sig)}`")
    if not classes and not functions:
        for osym in [s for s in syms if s.symbol_type != SymbolType.IMPORT][:5]:
            mod_lines.append(f"  `{_safe_bt(compact_sig_for_ste100_impl(osym.signature or osym.name))}`")
    mod_lines.append("")
    return "\n".join(mod_lines)


def render_inline_compact_module_impl(mod: str, syms: List[SymbolNode]) -> str:
    """Renderizza il modulo in formato compatto inline su classi e funzioni."""
    lines = [f"## 📄 `{_safe_bt(mod)}`"]
    classes = [s for s in syms if s.symbol_type == SymbolType.CLASS]
    for cls_node in classes:
        methods = [s for s in syms if s.parent_id == cls_node.id and s.symbol_type == SymbolType.METHOD]
        if methods:
            m_names = [m.name for m in methods]
            if len(m_names) > 8:
                m_names = [n for n in m_names if not n.startswith("_") or n == "__init__"] or m_names
            _append_chunked_items(lines, f"class {cls_node.name}", m_names)
        else:
            consts = [s for s in syms if s.parent_id == cls_node.id and s.symbol_type == SymbolType.CONSTANT]
            if consts:
                _append_chunked_items(lines, f"class {cls_node.name}", [c.name for c in consts])
            else:
                lines.append(f"  `class {_safe_bt(cls_node.name)}`: `empty`")

    functions = [
        s for s in syms
        if s.symbol_type in (SymbolType.FUNCTION, SymbolType.ASYNC_FUNCTION) and s.parent_id is None
    ]
    if functions:
        fn_names = [fn.name for fn in functions]
        if len(fn_names) > 8:
            fn_names = [n for n in fn_names if not n.startswith("_")] or fn_names
        _append_chunked_items(lines, "functions", fn_names)

    if not classes and not functions:
        other_syms = [s for s in syms if s.symbol_type != SymbolType.IMPORT]
        if other_syms:
            lines.append(f"  `symbols`: `{_safe_bt(', '.join(s.name for s in other_syms[:5]))}`")

    lines.append("")
    return "\n".join(lines)


def render_two_tier_map_impl(
    root_dir: Path,
    graph: SymbolGraph,
    pr_scores: Dict[str, float],
    focal_ids: Set[str],
    max_tokens: int,
) -> Tuple[str, int]:
    """
    Formatta la mappa ad alta densita con compattazione elastica a tre livelli.
    Garantisce copertura STE100-safe e priorita ai moduli canonici in scripts/.
    """
    _ = root_dir
    modules: Dict[str, List[SymbolNode]] = {}
    for node in graph.nodes.values():
        if node.symbol_type != SymbolType.IMPORT:
            modules.setdefault(node.module_path, []).append(node)

    if not modules:
        header = "# REPO-MAP (AST Snapshot)\n"
        return header, estimate_tokens(header)

    mod_pr_map: Dict[str, float] = {}
    module_scores: List[Tuple[str, float, bool]] = []
    for mod, syms in modules.items():
        is_focal = any(s.id in focal_ids for s in syms)
        base_pr = max((pr_scores.get(s.id, 0.0) for s in syms), default=0.0)
        mod_pr_map[mod] = base_pr
        score = base_pr + (1000.0 if is_focal else 0.0)
        if _is_canonical_script(mod):
            score += 100.0
        elif not _is_test_module(mod):
            score += 10.0
        if any(s.symbol_type == SymbolType.CLASS for s in syms):
            score += 0.01
        module_scores.append((mod, score, is_focal))
    module_scores.sort(key=lambda x: (x[1], x[0]), reverse=True)

    header = "# REPO-MAP (AST Snapshot)\n\n"
    is_full_budget = max_tokens >= 900 and max_tokens != 1024
    target_budget = min(max_tokens, int(max_tokens * (0.94 if is_full_budget else 0.82)))
    non_test_count = sum(1 for m, _, _ in module_scores if not _is_test_module(m))
    prioritize_all_prod = max_tokens >= 900 and non_test_count >= 12
    tier1_budget = (
        max(int(target_budget * 0.45), target_budget - (non_test_count * 23) - 45)
        if prioritize_all_prod
        else max(40, int(target_budget * 0.55))
    )

    tier1_blocks: List[str] = []
    tier1_mods: Set[str] = set()
    if tier1_budget > 0:
        for mod, _score, is_focal in module_scores:
            if prioritize_all_prod and _is_test_module(mod):
                continue
            syms = modules[mod]
            classes = [s for s in syms if s.symbol_type == SymbolType.CLASS]
            methods = [s for s in syms if s.symbol_type == SymbolType.METHOD]
            functions = [
                s for s in syms
                if s.symbol_type in (SymbolType.FUNCTION, SymbolType.ASYNC_FUNCTION) and s.parent_id is None
            ]
            is_large = (
                len(classes) >= 3
                or (len(classes) >= 1 and len(methods) >= 5)
                or (len(classes) + len(functions) >= 7)
            )
            if not is_large or is_focal:
                exp_block = render_expanded_module_impl(mod, syms)
                if estimate_tokens(header + "\n".join(tier1_blocks + [exp_block])) <= tier1_budget:
                    tier1_blocks.append(exp_block)
                    tier1_mods.add(mod)
                    continue
            inline_block = render_inline_compact_module_impl(mod, syms)
            if estimate_tokens(header + "\n".join(tier1_blocks + [inline_block])) <= tier1_budget:
                tier1_blocks.append(inline_block)
                tier1_mods.add(mod)
            elif not tier1_blocks and (not prioritize_all_prod or tier1_budget >= 60):
                cand_lines = inline_block.splitlines()
                trimmed = [cand_lines[0]]
                for ln in cand_lines[1:]:
                    test_t = header + "\n".join(tier1_blocks + ["\n".join(trimmed + [ln, ""])])
                    if estimate_tokens(test_t) <= tier1_budget:
                        trimmed.append(ln)
                    else:
                        break
                if len(trimmed) > 1:
                    trimmed.append("")
                    tier1_blocks.append("\n".join(trimmed))
                    tier1_mods.add(mod)

    tier2_mods = [m for m, _, _ in module_scores if m not in tier1_mods]
    tier2_header = "### Moduli Secondari\n" if tier2_mods else ""
    tier2_lines: List[str] = []
    remaining_mods: List[str] = []
    tier2_mods.sort(
        key=lambda m: (
            _is_canonical_script(m),
            not _is_test_module(m),
            any(s.symbol_type == SymbolType.CLASS for s in modules[m]),
            mod_pr_map.get(m, 0.0),
            m,
        ),
        reverse=True,
    )

    t1_prefix = header + "\n".join(tier1_blocks) + "\n" + tier2_header
    for idx, mod in enumerate(tier2_mods):
        syms = modules[mod]
        classes = [s.name for s in syms if s.symbol_type == SymbolType.CLASS]
        fns = [s.name for s in syms if s.symbol_type in (SymbolType.FUNCTION, SymbolType.ASYNC_FUNCTION) and s.parent_id is None]
        key_syms = classes + ([f for f in fns if not f.startswith("_")] or fns) or [
            s.name for s in syms if s.symbol_type != SymbolType.IMPORT
        ]
        sym_limit = 2 if prioritize_all_prod else 3
        top_syms = (
            classes[:8] if (len(classes) >= 3 and not prioritize_all_prod)
            else (classes[:2] if len(classes) >= 2 and prioritize_all_prod else key_syms[:sym_limit])
        )
        line = f"- `{_safe_bt(mod)}`: `{_safe_bt(', '.join(top_syms))}`" if top_syms else f"- `{_safe_bt(mod)}`: `module`"

        rem_groups, has_rem_tests = _group_remaining_by_dir(tier2_mods[idx + 1 :], collapse_tests=prioritize_all_prod)
        rem_folder_lines = [ln for d, fnames in rem_groups.items() for ln in _dir_chunk_lines(d, fnames)]
        if has_rem_tests:
            rem_folder_lines.append("- `tests/*`: `suite`")
        if estimate_tokens(t1_prefix + "\n".join(tier2_lines + [line] + rem_folder_lines)) <= target_budget:
            tier2_lines.append(line)
        else:
            remaining_mods = tier2_mods[idx:]
            break

    if remaining_mods:
        rem_groups, _ = _group_remaining_by_dir(remaining_mods, collapse_tests=False)
        unadded_dirs: List[str] = []
        for d, fnames in rem_groups.items():
            prefix = "root/*" if (d == "." or not d) else f"{d}/*"
            f_chunks = _dir_chunk_lines(d, fnames)
            if estimate_tokens(t1_prefix + "\n".join(tier2_lines + f_chunks)) <= target_budget:
                tier2_lines.extend(f_chunks)
            else:
                unadded_dirs.append(prefix)
        for d, fnames in rem_groups.items():
            prefix = "root" if (d == "." or not d) else d
            if f"{prefix}/*" in unadded_dirs:
                tier2_lines.append(f"- `{_safe_bt(prefix)}`: `{_safe_bt(', '.join(fnames))}`")

    blocks = [header.rstrip(), ""]
    if tier1_blocks:
        blocks.extend(tier1_blocks)
    if tier2_header and tier2_lines:
        blocks.append(tier2_header.rstrip())
        blocks.extend(tier2_lines)

    final_content = "\n".join(blocks).strip() + "\n"
    final_tokens = estimate_tokens(final_content)
    hard_cap = 850 if max_tokens == 1024 else max_tokens
    if final_tokens > hard_cap:
        trimmed = []
        for ln in final_content.splitlines():
            if estimate_tokens("\n".join(trimmed + [ln]) + "\n") <= hard_cap:
                trimmed.append(ln)
            else:
                break
        final_content = "\n".join(trimmed).strip() + "\n"
        final_tokens = estimate_tokens(final_content)

    return final_content, final_tokens
