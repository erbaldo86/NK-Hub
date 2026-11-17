"""Estrattore poliglotta JS/TS/CSS/HTML, cache atomica e budget adattivo."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.ast_repo_mapper.models import (
    EdgeType,
    SymbolEdge,
    SymbolNode,
    SymbolType,
)
from _internal.nk_common.io import atomic_write_json


class PolyglotExtractor:
    """
    Estrae in modo deterministico i contratti frontend da JS, TS, CSS e HTML.
    """

    _JS_TS_KEYWORDS: Set[str] = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
        "typeof",
        "import",
        "export",
        "super",
        "constructor",
        "await",
        "yield",
        "throw",
        "delete",
        "void",
    }

    @classmethod
    def extract_symbols(cls, file_path: str, content: str) -> List[SymbolNode]:
        clean_path = file_path.replace("\\", "/")
        ext = Path(file_path).suffix.lower()
        nodes: List[SymbolNode] = []

        if ext in (".js", ".ts", ".jsx", ".tsx"):
            nodes.extend(cls._extract_js_ts(clean_path, content))
        elif ext == ".css":
            nodes.extend(cls._extract_css(clean_path, content))
        elif ext in (".html", ".htm"):
            nodes.extend(cls._extract_html(clean_path, content))

        return nodes

    @classmethod
    def _strip_js_comments(cls, content: str) -> List[str]:
        no_block = re.sub(
            r"/\*[\s\S]*?\*/",
            lambda m: "\n" * m.group(0).count("\n"),
            content,
        )
        return [re.sub(r"//.*$", "", ln) for ln in no_block.splitlines()]

    @classmethod
    def _compute_js_block_end(cls, clean_lines: List[str], start_line: int, fallback_end: int) -> int:
        brace_depth = 0
        paren_depth = 0
        opened = False
        for idx in range(start_line - 1, len(clean_lines)):
            ln = clean_lines[idx]
            for ch in ln:
                if not opened:
                    if ch == "(":
                        paren_depth += 1
                    elif ch == ")" and paren_depth > 0:
                        paren_depth -= 1
                    elif ch == "{" and paren_depth == 0:
                        brace_depth = 1
                        opened = True
                else:
                    if ch == "{":
                        brace_depth += 1
                    elif ch == "}":
                        brace_depth -= 1
                        if brace_depth <= 0:
                            return idx + 1
            if not opened and idx >= fallback_end - 1:
                return fallback_end
        return fallback_end

    @classmethod
    def _extract_js_ts(cls, path: str, content: str) -> List[SymbolNode]:
        raw_defs: List[Tuple[int, str, SymbolType, str, str]] = []
        lines = content.splitlines()
        clean_lines = cls._strip_js_comments(content)

        fn_pattern = re.compile(
            r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>]*>)?\s*\((.*?)\)",
            re.MULTILINE,
        )
        cls_pattern = re.compile(
            r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)(?:<[^>]*>)?(?:\s+extends\s+([a-zA-Z_$][a-zA-Z0-9_$.]*))?",
            re.MULTILINE,
        )
        const_fn_pattern = re.compile(
            r"^(?:export\s+)?const\s+([a-zA-Z_$][a-zA-Z0-9_$]*)(?:\s*:[^=]+)?\s*=\s*(?:async\s*)?(?:<[^>]*>\s*)?\((.*?)\)(?:\s*:[^=]+)?\s*=>",
            re.MULTILINE,
        )

        for idx, line in enumerate(lines, start=1):
            m_fn = fn_pattern.search(line)
            if m_fn:
                name = m_fn.group(1)
                params = m_fn.group(2).strip()
                sig = f"function {name}({params}): ..."
                raw_defs.append((idx, name, SymbolType.FUNCTION, sig, line.strip()))
                continue

            m_cls = cls_pattern.search(line)
            if m_cls:
                name = m_cls.group(1)
                parent = m_cls.group(2)
                sig = f"class {name}" + (f" extends {parent}" if parent else "") + ": ..."
                raw_defs.append((idx, name, SymbolType.CLASS, sig, line.strip()))
                continue

            m_const = const_fn_pattern.search(line)
            if m_const:
                name = m_const.group(1)
                params = m_const.group(2).strip()
                sig = f"const {name} = ({params}) => ..."
                raw_defs.append((idx, name, SymbolType.FUNCTION, sig, line.strip()))

        nodes: List[SymbolNode] = []
        total_lines = max(1, len(lines))
        for i, (start_ln, name, stype, sig, raw_src) in enumerate(raw_defs):
            next_bound = raw_defs[i + 1][0] - 1 if i + 1 < len(raw_defs) else total_lines
            fallback = max(start_ln, next_bound)
            end_ln = max(start_ln, cls._compute_js_block_end(clean_lines, start_ln, fallback))
            nodes.append(
                SymbolNode(
                    id=f"{path}:{name}",
                    name=name,
                    symbol_type=stype,
                    module_path=path,
                    line_start=start_ln,
                    line_end=end_ln,
                    signature=sig,
                    raw_source=raw_src,
                )
            )

        return nodes

    @classmethod
    def extract_call_edges(
        cls,
        file_path: str,
        content: str,
        nodes: Optional[List[SymbolNode]] = None,
    ) -> Tuple[List[SymbolEdge], Dict[str, Set[str]]]:
        """Estrae tramite regex leggera gli archi CALL nei file JS, TS, JSX e TSX."""
        clean_path = file_path.replace("\\", "/")
        ext = Path(file_path).suffix.lower()
        if ext not in (".js", ".ts", ".jsx", ".tsx"):
            return [], {}
        sym_nodes = nodes if nodes is not None else cls.extract_symbols(clean_path, content)
        if not sym_nodes:
            return [], {}

        name_to_ids: Dict[str, Set[str]] = {}
        for nd in sym_nodes:
            name_to_ids.setdefault(nd.name, set()).add(nd.id)

        clean_lines = cls._strip_js_comments(content)
        call_pat = re.compile(r"\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>\n;{}]*>)?\s*\(")
        jsx_pat = re.compile(r"<([A-Z][a-zA-Z0-9_$]*)\b")

        edges: List[SymbolEdge] = []
        seen_edges: Set[Tuple[str, str]] = set()
        scope_calls: Dict[str, Set[str]] = {}

        for nd in sym_nodes:
            s_idx = max(0, nd.line_start - 1)
            e_idx = min(len(clean_lines), max(nd.line_start, nd.line_end))
            segment = list(clean_lines[s_idx:e_idx])
            if not segment:
                continue
            head = segment[0]
            if "=>" in head:
                segment[0] = head.split("=>", 1)[1]
            elif "{" in head:
                segment[0] = head.split("{", 1)[1]
            else:
                segment[0] = ""
            body_text = "\n".join(segment)

            callees: Set[str] = set()
            for cname in call_pat.findall(body_text):
                if cname not in cls._JS_TS_KEYWORDS and cname != nd.name:
                    callees.add(cname)
            if ext in (".jsx", ".tsx"):
                for comp_name in jsx_pat.findall(body_text):
                    if comp_name != nd.name:
                        callees.add(comp_name)

            if callees:
                scope_calls[nd.id] = callees
                for cname in sorted(callees):
                    for tid in sorted(name_to_ids.get(cname, ())):
                        if tid != nd.id and (nd.id, tid) not in seen_edges:
                            seen_edges.add((nd.id, tid))
                            edges.append(
                                SymbolEdge(
                                    source_id=nd.id,
                                    target_id=tid,
                                    edge_type=EdgeType.CALL,
                                    weight=1.5,
                                )
                            )

        return edges, scope_calls

    @classmethod
    def _extract_css(cls, path: str, content: str) -> List[SymbolNode]:
        nodes: List[SymbolNode] = []
        rules = re.findall(r"([.#][a-zA-Z0-9_-]+)\s*\{", content)
        seen = set()
        for idx, rule in enumerate(rules[:30], start=1):
            if rule not in seen:
                seen.add(rule)
                nodes.append(
                    SymbolNode(
                        id=f"{path}:{rule}",
                        name=rule,
                        symbol_type=SymbolType.CSS_RULE,
                        module_path=path,
                        line_start=idx,
                        line_end=idx,
                        signature=f"{rule} {{ ... }}",
                        raw_source=f"{rule} {{ ... }}",
                    )
                )
        return nodes

    @classmethod
    def _extract_html(cls, path: str, content: str) -> List[SymbolNode]:
        nodes: List[SymbolNode] = []
        ids = re.findall(r'id=["\']([a-zA-Z0-9_-]+)["\']', content)
        seen = set()
        for idx, elem_id in enumerate(ids[:20], start=1):
            if elem_id not in seen:
                seen.add(elem_id)
                nodes.append(
                    SymbolNode(
                        id=f"{path}:#{elem_id}",
                        name=f"#{elem_id}",
                        symbol_type=SymbolType.JS_COMPONENT,
                        module_path=path,
                        line_start=idx,
                        line_end=idx,
                        signature=f'<... id="{elem_id}">',
                        raw_source=f'id="{elem_id}"',
                    )
                )
        return nodes


class AtomicCacheManager:
    """
    Gestisce la lettura e scrittura atomica della cache in %TEMP%\\nk_diagnostics\\.
    Delega la scrittura atomica a nk_common.io con file temporanei univoci e retry contro WinError 32.
    """

    @classmethod
    def get_default_cache_path(cls, root_dir: Optional[Path | str] = None) -> Path:
        cache_dir = Path(tempfile.gettempdir()) / "nk_diagnostics"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target_root = root_dir if root_dir is not None else Path.cwd()
        repo_hash = hashlib.sha256(
            os.path.realpath(str(target_root)).lower().encode("utf-8")
        ).hexdigest()[:12]
        return cache_dir / f"repo_map_cache_{repo_hash}.json"

    @classmethod
    def save_atomic(cls, payload: Dict[str, Any], cache_path: Path, max_retries: int = 8) -> bool:
        try:
            delays = [0.01 * (i + 1) for i in range(max(1, int(max_retries)))]
            ok, _ = atomic_write_json(
                cache_path,
                payload,
                indent=2,
                ensure_ascii=False,
                ensure_parent=True,
                delays=delays,
            )
            return ok
        except Exception:
            return False

    @classmethod
    def load_safe(cls, cache_path: Path, max_retries: int = 5) -> Optional[Dict[str, Any]]:
        if not cache_path.exists():
            return None
        for attempt in range(max_retries):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (PermissionError, json.JSONDecodeError):
                time.sleep(0.01 * (2 ** attempt))
            except Exception:
                return None
        return None


class GraduatedSkillAdapter:
    """Fornisce la graduazione del budget token in base alla modalita e alla skill."""

    BLACKLIST = {"NK-Scribe-Memory", "NK-Agent-Instruction-Forge"}

    @classmethod
    def get_token_budget(cls, skill_name: str, speed_mode: str = "auto") -> int:
        if skill_name in cls.BLACKLIST:
            return 0
        mode = speed_mode.lower()
        if "generation_mode_c" in mode or "carbon_mode_c" in mode or "argon_mode_c" in mode:
            return 512
        if "generation_mode_b" in mode or "carbon_mode_b" in mode or "argon_mode_b" in mode:
            return 1500
        if "generation_mode_a" in mode or "carbon_mode_a" in mode or "argon_mode_a" in mode:
            return 4000
        if "mode_c" in mode or "vibe" in mode:
            return 256
        elif "mode_b" in mode or "fast" in mode:
            return 512
        else:
            return 1024
