"""Resilient CST/AST parser per recupero chunk Python con errori di sintassi."""

from __future__ import annotations

import ast
import re
from typing import List, Optional, Tuple


class ResilientParser:
    """
    Analizza il codice sorgente resistendo a errori intermedi di sintassi.
    Preserva i token parziali dei parametri senza emettere firme vuote.
    """

    @classmethod
    def parse_safe(cls, source: str, filename: str = "<string>") -> Tuple[Optional[ast.AST], List[str]]:
        warnings: List[str] = []
        try:
            tree = ast.parse(source, filename=filename)
            return tree, warnings
        except SyntaxError as se:
            warnings.append(f"SyntaxError on line {se.lineno}, col {se.offset}: {se.msg}")

        sanitized_tree = cls._recover_ast_chunks(source, filename, warnings)
        return sanitized_tree, warnings

    @classmethod
    def _recover_ast_chunks(cls, source: str, filename: str, warnings: List[str]) -> Optional[ast.AST]:
        lines = source.splitlines(keepends=True)
        if not lines:
            return ast.parse("")

        block_ranges: List[Tuple[int, int]] = []
        start_idx = 0
        for i in range(1, len(lines)):
            line = lines[i]
            if line and not line[0].isspace() and not line.strip().startswith("#"):
                block_ranges.append((start_idx, i))
                start_idx = i
        block_ranges.append((start_idx, len(lines)))

        valid_nodes: List[ast.stmt] = []
        for b_start, b_end in block_ranges:
            block_code = "".join(lines[b_start:b_end])
            try:
                sub_tree = ast.parse(block_code, filename=filename)
                for node in sub_tree.body:
                    cls._offset_linenos(node, b_start)
                    valid_nodes.append(node)
            except SyntaxError as block_se:
                warnings.append(
                    f"Recovering malformed block at lines {b_start+1}-{b_end}: {block_se.msg}"
                )
                stub_nodes = cls._extract_stubs_from_broken_block(block_code, b_start)
                valid_nodes.extend(stub_nodes)

        mod = ast.Module(body=valid_nodes, type_ignores=[])
        return mod

    @classmethod
    def _offset_linenos(cls, node: ast.AST, offset: int) -> None:
        for child in ast.walk(node):
            if hasattr(child, "lineno"):
                child.lineno += offset  # type: ignore[misc]
            if hasattr(child, "end_lineno") and child.end_lineno is not None:
                child.end_lineno += offset  # type: ignore[misc]

    @classmethod
    def _extract_stubs_from_broken_block(cls, block_code: str, line_offset: int) -> List[ast.stmt]:
        stubs: List[ast.stmt] = []
        lines = block_code.splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            fn_match = re.match(r"^(async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)(?:\)|:|$)", stripped)
            if fn_match:
                is_async = bool(fn_match.group(1))
                fn_name = fn_match.group(2)
                raw_params = fn_match.group(3).strip()
                cur_line = line_offset + idx + 1
                try:
                    param_names = [p.split(":")[0].strip() for p in raw_params.split(",") if p.strip()]
                    cleaned_params = [p for p in param_names if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", p)]
                    param_sig = ", ".join(cleaned_params)
                    stub_src = f"{'async ' if is_async else ''}def {fn_name}({param_sig}): pass"
                    stub_tree = ast.parse(stub_src)
                    fn_node = stub_tree.body[0]
                    fn_node.lineno = cur_line
                    fn_node.end_lineno = cur_line + 1
                    stubs.append(fn_node)
                except Exception:
                    pass
                continue

            cls_match = re.match(r"^class\s+([a-zA-Z_][a-zA-Z0-9_]*)(\(.*?\))?:", stripped)
            if cls_match:
                cls_name = cls_match.group(1)
                cur_line = line_offset + idx + 1
                try:
                    stub_src = f"class {cls_name}: pass"
                    stub_tree = ast.parse(stub_src)
                    c_node = stub_tree.body[0]
                    c_node.lineno = cur_line
                    c_node.end_lineno = cur_line + 1
                    stubs.append(c_node)
                except Exception:
                    pass
        return stubs
