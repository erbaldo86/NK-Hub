"""Scansione script scripts/ e sub-agenti nativi .agents/agents/."""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.ast_exports import collect_exported_class_names
from _internal.nk_common.constants import VERSION
from _internal.nk_registry_indexer.taxonomy import _EXCLUDED_SUBPROCESS_FLAGS

_WRITE_CAPABLE_AGENT_TOOLS: Set[str] = {
    "write_file",
    "edit_file",
    "run_command",
    "write_to_file",
    "replace_file_content",
}
_SUBAGENT_CAPABLE_AGENT_TOOLS: Set[str] = {"invoke_subagent", "define_subagent"}
_CANONICAL_AGENT_STR_KEYS: Set[str] = {"name", "description", "domain_id"}
_CANONICAL_AGENT_BOOL_KEYS: Set[str] = {
    "enable_write_tools",
    "enable_subagent_tools",
    "enable_mcp_tools",
}


def extract_script_metadata_impl(script_path: Path, hash_cache: Optional[Dict[Tuple[str, int, int], str]] = None, meta_cache: Optional[Dict[Tuple[str, int, int], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Estrae docstring, @domain_id, flag CLI add_argument, LOC e SHA-256 da uno script."""
    _hcache = hash_cache if hash_cache is not None else {}
    _mcache = meta_cache if meta_cache is not None else {}
    st = script_path.stat()
    cache_key = (str(script_path), st.st_mtime_ns, st.st_size)
    if st.st_size > 256 and cache_key in _mcache and "classes" in _mcache[cache_key]:
        return _mcache[cache_key]

    raw_bytes = script_path.read_bytes().replace(b"\r\n", b"\n")
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    _hcache[cache_key] = sha256_hex

    source = raw_bytes.decode("utf-8", errors="replace")
    lines = source.splitlines()
    loc = len(lines)
    byte_size = st.st_size

    description = f"Modulo operativo {script_path.name}."
    domain_id = ""
    flags: Set[str] = set()
    classes: List[str] = []

    try:
        tree = ast.parse(source, filename=script_path.name)
        classes = collect_exported_class_names(tree, script_path)
        doc = ast.get_docstring(tree)
        if doc:
            dom_match = re.search(
                r"@?domain_id\s*:\s*(DOM-0[1-5])", doc, re.IGNORECASE
            )
            if dom_match:
                domain_id = dom_match.group(1).upper()
            for doc_line in doc.splitlines():
                cleaned = doc_line.strip()
                if (
                    cleaned
                    and not cleaned.lower().startswith("modulo:")
                    and not cleaned.lower().startswith("@domain_id")
                    and not cleaned.lower().startswith("domain_id:")
                ):
                    description = cleaned
                    break

        has_add_argument = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if func_name == "add_argument":
                    has_add_argument = True
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(
                            arg.value, str
                        ):
                            val = arg.value.strip()
                            if (
                                val.startswith("--")
                                and val not in _EXCLUDED_SUBPROCESS_FLAGS
                                and re.match(r"^--[a-zA-Z0-9][a-zA-Z0-9_-]*$", val)
                            ):
                                flags.add(val)

        if not has_add_argument:
            scan_extra: List[Path] = []
            if script_path.parent.name == "scripts":
                sub_pkg = script_path.parent / "_internal" / script_path.stem
                if sub_pkg.is_dir():
                    scan_extra.extend(sorted(sub_pkg.glob("*.py")))
            extra_trees = [tree]
            for ep in scan_extra:
                try:
                    extra_trees.append(ast.parse(ep.read_text(encoding="utf-8", errors="replace"), filename=ep.name))
                except Exception:
                    pass
            for sub_t in extra_trees:
                for node in ast.walk(sub_t):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        val = node.value.strip()
                        if (
                            val.startswith("--")
                            and val not in _EXCLUDED_SUBPROCESS_FLAGS
                            and re.match(r"^--[a-zA-Z0-9][a-zA-Z0-9_-]*$", val)
                        ):
                            flags.add(val)
    except Exception:
        pass

    if not domain_id:
        nk_dom_match = re.search(
            r"__nk_domain__(?:\s*:\s*str)?\s*=\s*[\"'](DOM-0[1-5])[\"']",
            source[:1200],
            re.IGNORECASE,
        )
        if nk_dom_match:
            domain_id = nk_dom_match.group(1).upper()
    if not domain_id:
        header_match = re.search(
            r"@?domain_id\s*:\s*(DOM-0[1-5])", source[:600], re.IGNORECASE
        )
        if header_match:
            domain_id = header_match.group(1).upper()

    res = {
        "description": description,
        "domain_id": domain_id,
        "cli_flags": sorted(flags),
        "classes": classes,
        "loc": loc,
        "bytes": byte_size,
        "sha256": sha256_hex,
    }
    _mcache[cache_key] = res
    return res


def parse_native_agent_metadata_impl(content: str) -> Dict[str, Any]:
    """Estrae frontmatter nativo, permessi derivati da tools e chiavi canoniche da agent.md."""
    meta: Dict[str, Any] = {
        "name": "",
        "description": "",
        "domain_id": "",
        "enable_write_tools": False,
        "enable_subagent_tools": False,
        "enable_mcp_tools": False,
        "tools": [],
    }

    fm_match = re.match(
        r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", content, re.DOTALL
    )
    block_to_parse = fm_match.group(1) if fm_match else content[:800]
    collecting_tools = False
    parsed_tools: List[str] = []

    for line in block_to_parse.splitlines():
        stripped_ln = line.strip()
        if collecting_tools:
            if stripped_ln.startswith("-"):
                item = stripped_ln.lstrip("-").strip().strip('"').strip("'")
                if item:
                    parsed_tools.append(item)
                continue
            collecting_tools = False
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        raw_val = v.strip()
        val = raw_val.strip('"').strip("'")
        if key in _CANONICAL_AGENT_STR_KEYS:
            meta[key] = val
        elif key in _CANONICAL_AGENT_BOOL_KEYS:
            meta[key] = val.lower() in ("true", "1", "yes")
        elif key == "tools":
            if not raw_val:
                collecting_tools = True
            else:
                inner = raw_val[1:-1] if (raw_val.startswith("[") and raw_val.endswith("]")) else raw_val
                if not raw_val.startswith("[") or raw_val.endswith("]"):
                    parsed_tools.extend(
                        t.strip().strip('"').strip("'")
                        for t in inner.split(",")
                        if t.strip().strip('"').strip("'")
                    )

    if not parsed_tools:
        fm_tools_m = re.search(
            r"(?ms)^\s*tools\s*:\s*\[([^\]]*)\]", block_to_parse
        )
        if fm_tools_m:
            parsed_tools = [
                t.strip().strip('"').strip("'")
                for t in fm_tools_m.group(1).split(",")
                if t.strip().strip('"').strip("'")
            ]
    if parsed_tools:
        meta["tools"] = parsed_tools

    explicit_write = bool(meta["enable_write_tools"]) or bool(
        re.search(r"(?m)^\s*enable_write_tools\s*:\s*true\b", block_to_parse, re.IGNORECASE)
    )
    has_write_tool = any(t in _WRITE_CAPABLE_AGENT_TOOLS for t in parsed_tools)
    meta["enable_write_tools"] = bool(has_write_tool or explicit_write)
    if any(t in _SUBAGENT_CAPABLE_AGENT_TOOLS for t in parsed_tools):
        meta["enable_subagent_tools"] = True
    return meta


def collect_internal_integrity_index(
    workspace_root: Path, stage_dir: Path, deleted_paths: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """Indicizza SHA-256 e package per scripts/_internal/**/*.py, schemas/*.py e tests/**/*.py."""
    deleted = deleted_paths or set()
    entries: Dict[str, Dict[str, Any]] = {}
    for sub_rel, kind in (
        ("scripts/_internal", "internal"),
        ("scripts/schemas", "schema"),
        ("tests", "test"),
    ):
        found: Dict[str, Path] = {}
        for base_root, is_prod in ((stage_dir, False), (workspace_root, True)):
            sub_dir = base_root / sub_rel
            if not sub_dir.is_dir():
                continue
            for py_f in sorted(sub_dir.rglob("*.py")):
                rel = py_f.relative_to(base_root).as_posix()
                if rel in found or (is_prod and rel in deleted):
                    continue
                found[rel] = py_f
        for rel, py_f in sorted(found.items()):
            raw = py_f.read_bytes().replace(b"\r\n", b"\n")
            pkg = py_f.parent.name
            entries[rel] = {
                "kind": kind,
                "package": pkg,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "loc": len(raw.decode("utf-8", errors="replace").splitlines()),
            }
    return {"schema_version": VERSION, "total_files": len(entries), "files": entries}
