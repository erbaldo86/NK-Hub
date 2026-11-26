# -*- coding: utf-8 -*-
"""Scansione SAST/Mojibake/JSON in Overlay, grounding report TAS e verifica flag CLI CoVe."""

from __future__ import annotations

import ast, json, posixpath, re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import HALLUCINATED_SCRIPT_DENYLIST
from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir, strip_staging_rel_parts  # noqa: F401
from _internal.rsi_convergence_engine.constants import (
    EXCLUDED_SCAN_DIRS, _collect_overlay_md_files, _get_cached_file_and_ast, _is_excluded_rel_path,
    _workspace_root, get_ast_guard_validator, get_report_grounding_validator, load_staging_deleted_set_impl,
    normalize_rel_for_root, resolve_effective_staging,
)
from _internal.rsi_convergence_engine.report_sanitizers import audit_sast_report_payload

_MD_LINK_RE = re.compile(r"\]\(([^\)\r\n]+)\)")
_MD_SCRIPT_RE = re.compile(r"scripts[/\\]((?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?[a-zA-Z0-9_]+\.py)")
_MD_NEGATION_RE = re.compile(
    r"\b(?:inesistent\w*|allucinat\w*|non\s+esist\w*|denylist\w*|vietat\w*|proibit\w*|rimoss\w*|mai\s+usar\w*)\b", re.IGNORECASE,
)
_SKIP_LINK_PREFIXES = ("http://", "https://", "file://", "#", "conversation://", "mailto:")
_SPECIAL_LINK_CHARS = frozenset("*?{}^$[]\\<>")
_IGNORED_CLI_FLAGS = frozenset({"--porcelain", "--tb=short", "--version"})


def _strip_fenced_code(text: str) -> str:
    """Rimuove i blocchi di codice recintati per evitare falsi positivi sui link."""
    out_lines: List[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out_lines.append("")
            continue
        out_lines.append("" if in_fence else line)
    return "\n".join(out_lines)


def _is_valid_md_link_target(
    link_path: str, resolved_md: Path, resolved_root: Path, logical_dir: str,
    resolve_candidate_fn: Callable[[Path, str], Path], del_set: Set[str],
) -> bool:
    norm_link = link_path.replace("\\", "/")
    cand_rel = posixpath.normpath(f"{logical_dir}/{norm_link}") if logical_dir else posixpath.normpath(norm_link)
    cand_rel = normalize_rel_for_root(resolved_root, cand_rel)
    if (resolved_md.parent / link_path).exists() and (cand_rel.startswith("..") or cand_rel not in del_set):
        return True
    if not cand_rel.startswith("..") and cand_rel not in del_set and resolve_candidate_fn(resolved_root, cand_rel).exists():
        return True
    root_rel = normalize_rel_for_root(resolved_root, norm_link)
    return bool(root_rel) and root_rel not in del_set and resolve_candidate_fn(resolved_root, root_rel).exists()


def _check_markdown_links(
    prose_only: str, resolved_md: Path, resolved_root: Path, logical_rel: str,
    logical_dir: str, resolve_candidate_fn: Callable[[Path, str], Path], del_set: Set[str],
) -> List[str]:
    """Verifica tutti i link relativi presenti nel documento Markdown."""
    broken: List[str] = []
    for match in _MD_LINK_RE.finditer(prose_only):
        raw_inner = match.group(1).strip()
        if not raw_inner or raw_inner.startswith(_SKIP_LINK_PREFIXES):
            continue
        link_raw = re.split(r'\s+["\']', raw_inner, maxsplit=1)[0].strip()
        link_path = link_raw.split("#", 1)[0].strip().strip("<>")
        if not link_path or any(ch in _SPECIAL_LINK_CHARS for ch in link_path):
            continue
        if not _is_valid_md_link_target(link_path, resolved_md, resolved_root, logical_dir, resolve_candidate_fn, del_set):
            broken.append(f"{logical_rel} -> {raw_inner}")
    return broken


def _check_markdown_scripts(
    content: str, resolved_root: Path, logical_rel: str,
    resolve_candidate_fn: Callable[[Path, str], Path], del_set: Set[str],
) -> List[str]:
    """Verifica gli script referenziati e i nomi vietati in un documento Markdown."""
    phantom: List[str] = []
    seen: Set[str] = set()
    hub_root = _workspace_root() if callable(_workspace_root) else _workspace_root
    for line in content.splitlines():
        if _MD_NEGATION_RE.search(line):
            continue
        for m_sc in _MD_SCRIPT_RE.finditer(line):
            rel_sc = f"scripts/{m_sc.group(1).replace(chr(92), '/')}"
            if rel_sc in seen:
                continue
            is_hub_ref = line[: m_sc.start()].lower().endswith(("nk_hub/", "nk_hub\\"))
            if is_hub_ref:
                is_missing = not (hub_root / rel_sc).exists() and not (hub_root / ".staging" / rel_sc).exists()
            else:
                is_missing = rel_sc in del_set or not resolve_candidate_fn(resolved_root, rel_sc).exists()
            if is_missing:
                seen.add(rel_sc)
                phantom.append(f"{logical_rel}: script mancante '{rel_sc}'")
        for h_sc in HALLUCINATED_SCRIPT_DENYLIST:
            if h_sc not in seen and re.search(rf"\b{re.escape(h_sc)}\b", line, re.IGNORECASE):
                seen.add(h_sc)
                phantom.append(f"{logical_rel}: script vietato '{h_sc}'")
    return phantom


def _normalize_deleted_rel_set(items: Any) -> Set[str]:
    return {
        re.sub(r"^(?:\./)+", "", str(item).strip().replace("\\", "/")).lstrip("/")
        for item in (items or ())
        if str(item).strip()
    }


def audit_markdown_doc_references(
    md_file: Path, content: str, root: Path, resolve_candidate_fn: Callable[[Path, str], Path],
    deleted_rel: Optional[Set[str]] = None, check_scripts: bool = True,
) -> Tuple[List[str], List[str]]:
    """Verifica link relativi rotti e script mancanti o vietati nei documenti attivi."""
    del_set = _normalize_deleted_rel_set(deleted_rel)
    resolved_root, resolved_md = Path(root).resolve(), Path(md_file).resolve()
    try:
        rel_md = resolved_md.relative_to(resolved_root).as_posix()
    except ValueError:
        rel_md = resolved_md.name
    stg_idx, rel_after, _lane = strip_staging_rel_parts(Path(rel_md).parts)
    logical_rel = "/".join(rel_after) if stg_idx == 0 else rel_md
    logical_dir = posixpath.dirname(logical_rel)
    broken_links = _check_markdown_links(
        _strip_fenced_code(content), resolved_md, resolved_root, logical_rel, logical_dir, resolve_candidate_fn, del_set
    )
    phantom_scripts = _check_markdown_scripts(content, resolved_root, logical_rel, resolve_candidate_fn, del_set) if check_scripts else []
    return broken_links, phantom_scripts


def _should_skip_overlay_prod(p: Path, root: Path, is_hub_root: bool, idx: int, staging_excluded: Set[str]) -> bool:
    rel_parts = p.relative_to(root).parts
    if ".staging" in rel_parts:
        return True
    if is_hub_root and idx > 0:
        return _is_excluded_rel_path(p, root)
    return (not is_hub_root) and any(part in staging_excluded for part in rel_parts)


def _collect_prod_overlay_files(
    root: Path, deleted_rel: Set[str], staging_excluded: Set[str], overlay_map: Dict[str, Path]
) -> None:
    is_hub_root = root.resolve() == _workspace_root.resolve()
    sub_dirs = [root / s for s in ("scripts", "tests", ".agents", "nk_genome", "nk_tracking") if (root / s).is_dir()]
    base_dirs = ([root] + sub_dirs) if is_hub_root else [root]
    for idx, base in enumerate(base_dirs):
        iterator = base.iterdir() if (is_hub_root and idx == 0) else base.rglob("*")
        for p in iterator:
            if not p.is_file() or p.suffix not in (".py", ".md", ".json"):
                continue
            if _should_skip_overlay_prod(p, root, is_hub_root, idx, staging_excluded):
                continue
            rel_k = p.relative_to(root).as_posix()
            if rel_k not in deleted_rel:
                overlay_map[rel_k] = p


def _collect_stg_overlay_entries(stg_root: Path, staging_excluded: Set[str], overlay_map: Dict[str, Path], exclude_lanes: Optional[bool] = None) -> None:
    """Raccoglie i file .py/.md/.json da staging_dir o lane escludendo lanes/ in legacy."""
    if not stg_root.is_dir():
        return
    is_base_stg = (stg_root.name == ".staging") if exclude_lanes is None else bool(exclude_lanes)
    for p in stg_root.rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".md", ".json"):
            continue
        rel_parts = p.relative_to(stg_root).parts
        if (is_base_stg and rel_parts and is_lane_container_entry(rel_parts)) or any(part in staging_excluded for part in rel_parts):
            continue
        overlay_map[p.relative_to(stg_root).as_posix()] = p

def _collect_overlay_scan_files(root: Path, deleted_rel: Set[str], lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> List[Path]:
    """Raccoglie i file .py, .md e .json attivi in overlay .staging/ > produzione."""
    staging_excluded, overlay_map = EXCLUDED_SCAN_DIRS - {".staging"}, {}
    _collect_prod_overlay_files(root, deleted_rel, staging_excluded, overlay_map)
    stg_root = resolve_effective_staging(root, lane_id=lane_id, staging_dir=staging_dir)
    _collect_stg_overlay_entries(stg_root, staging_excluded, overlay_map, exclude_lanes=(lane_id is None and staging_dir is None and stg_root.name == ".staging"))
    return sorted({p.resolve() for p in overlay_map.values()})

def _audit_external_sast_report(sast_report: Optional[Path | str]) -> Tuple[int, List[str]]:
    if sast_report is None:
        return 0, []
    rep_chk = audit_sast_report_payload(sast_report)
    sast_count = int(rep_chk.get("sast_critical", 0)) + int(rep_chk.get("sast_taint", 0))
    return (max(1, sast_count), list(rep_chk.get("violations", []))) if not rep_chk.get("passed", False) else (sast_count, [])

def _collect_deleted_and_overlay_files(engine: Any, root: Path, lane_id: Optional[str], staging_dir: Optional[Path]) -> List[Path]:
    raw_del = load_staging_deleted_set_impl(root, lane_id=lane_id, staging_dir=staging_dir) if (lane_id is not None or staging_dir is not None) else engine._load_staging_deleted_set(root)
    return _collect_overlay_scan_files(root, _normalize_deleted_rel_set(raw_del), lane_id=lane_id, staging_dir=staging_dir)

def scan_sast_and_mojibake_impl(engine: Any, root: Path, sast_report: Optional[Path | str] = None, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Scansiona .staging/ e produzione (codice, JSON e doc) per SAST, syntax e U+FFFD."""
    sast_count, sast_issues = _audit_external_sast_report(sast_report)
    mojibake_files, invalid_json_files = [], []
    unique_files = _collect_deleted_and_overlay_files(engine, root, lane_id, staging_dir)
    agv_cls: Any = None
    for fpath in unique_files:
        try:
            rel_label = fpath.relative_to(root.resolve()).as_posix()
        except ValueError:
            rel_label = fpath.name
        try:
            text, _cached_ast = _get_cached_file_and_ast(fpath)
        except OSError as exc:
            if fpath.suffix == ".py":
                sast_count += 1
                sast_issues.append(f"{rel_label}: errore lettura file ({exc})")
            else:
                invalid_json_files.append(f"{rel_label}: errore lettura file ({exc})")
            continue
        if "\ufffd" in text:
            mojibake_files.append(rel_label)
        if fpath.suffix == ".json":
            try:
                json.loads(text)
            except (json.JSONDecodeError, ValueError) as exc:
                invalid_json_files.append(f"{rel_label}: {exc}")
        elif fpath.suffix == ".py":
            if agv_cls is None:
                agv_cls = get_ast_guard_validator()
            if agv_cls is not None:
                try:
                    v_list = agv_cls.check_sast_constructs(text, target_file=fpath.as_posix())
                except TypeError:
                    v_list = agv_cls.check_sast_constructs(text)
                if v_list:
                    sast_count += len(v_list)
                    sast_issues.extend(f"{rel_label}: {v.message}" for v in v_list[:3])
    return {
        "passed": sast_count == 0 and not mojibake_files and not invalid_json_files,
        "sast_critical": sast_count, "sast_issues": sast_issues,
        "mojibake_count": len(mojibake_files), "mojibake_files": mojibake_files,
        "invalid_json_count": len(invalid_json_files), "invalid_json_files": invalid_json_files,
        "scanned_files": unique_files,
    }


def audit_tas_reports_impl(
    engine: Any, root: Path, verified_files: List[Path], violations: List[str]
) -> Tuple[int, Dict[str, Any]]:
    """Verifica Grounding dei report TAS (tas_certification_report*.md)."""
    hallucinated_refs_count = 0
    tas_grounding_reports: List[Dict[str, Any]] = []
    verify_report_grounding = get_report_grounding_validator()
    if verify_report_grounding is not None:
        tas_deleted = engine._load_staging_deleted_set(root)
        tas_map: Dict[str, Path] = {}
        for is_stg, rep_dir in ((False, root / "nk_tracking" / "reports_and_briefs"), (True, root / ".staging" / "nk_tracking" / "reports_and_briefs")):
            if not rep_dir.is_dir():
                continue
            for t_pat in ("tas_certification_report*.md", "TAS_Report_*.md"):
                for rep_p in sorted(rep_dir.glob(t_pat)):
                    if rep_p.is_file() and (is_stg or rep_p.relative_to(root).as_posix() not in tas_deleted):
                        tas_map[rep_p.name] = rep_p
        for rep_name, rep_path in sorted(tas_map.items()):
            verified_files.append(rep_path)
            g_res = verify_report_grounding(rep_path)
            tas_grounding_reports.append(g_res)
            h_list = g_res.get("hallucinated_scripts", [])
            if h_list:
                hallucinated_refs_count += len(h_list)
                violations.append(f"{rep_name}: script allucinati rilevati da verify_report_grounding: {h_list}")
    return hallucinated_refs_count, {
        "passed": hallucinated_refs_count == 0, "reports_checked": len(tas_grounding_reports),
        "hallucinated_refs": hallucinated_refs_count, "details": tas_grounding_reports,
    }


def _collect_ast_cli_flags(tree: ast.AST) -> Set[str]:
    found: Set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        val = node.value.strip()
        if not val.startswith("--") or "*" in val or val in _IGNORED_CLI_FLAGS:
            continue
        flag_token = val.split("=", 1)[0]
        if flag_token not in _IGNORED_CLI_FLAGS and re.match(r"^--[a-zA-Z0-9][a-zA-Z0-9_-]*$", flag_token):
            found.add(flag_token)
    return found


def _collect_internal_subpkg_files(script_path: Path) -> List[Path]:
    """Raccoglie i moduli _internal/<stem>/*.py unendo produzione e overlay .staging/."""
    if script_path.parent.name != "scripts":
        return []
    sub_map: Dict[str, Path] = {}
    stg_idx, _r, _l = strip_staging_rel_parts(script_path.parts)
    if stg_idx >= 0:
        prod_sub = Path(*script_path.parts[:stg_idx]) / "scripts" / "_internal" / script_path.stem
        if prod_sub.is_dir():
            for pf in sorted(prod_sub.glob("*.py")):
                sub_map[pf.name] = pf
    sub_pkg = script_path.parent / "_internal" / script_path.stem
    if sub_pkg.is_dir():
        for sf in sorted(sub_pkg.glob("*.py")):
            sub_map[sf.name] = sf
    return [sub_map[k] for k in sorted(sub_map)]


def extract_script_supported_flags_impl(script_path: Path) -> Set[str]:
    """Estrae i flag CLI --flag supportati nell'AST inclusi i sottomoduli _internal/<stem>."""
    if not script_path.exists() or not script_path.is_file():
        return set()
    flags: Set[str] = set()
    scan_paths: List[Path] = [script_path]
    scan_paths.extend(_collect_internal_subpkg_files(script_path))
    for cand_p in scan_paths:
        try:
            source_text, tree = _get_cached_file_and_ast(cand_p)
        except OSError:
            continue
        if tree is None:
            continue
        if any(tok in source_text for tok in ("argparse", "ArgumentParser", "sys.argv")):
            flags.add("--help")
        flags.update(_collect_ast_cli_flags(tree))
    return flags


def extract_cove_args_tail(content: str, match_start: int, match_end: int) -> str:
    """Estrae gli argomenti sulla riga corrente rispettando apici e delimitatori."""
    line_start = content.rfind("\n", 0, match_start) + 1
    line_end = content.find("\n", match_end)
    line_end = len(content) if line_end == -1 else line_end
    tail_end = line_end
    if content[line_start:match_start].count("`") % 2 == 1:
        close_tick = content.find("`", match_end, line_end)
        if close_tick != -1:
            tail_end = close_tick
    m_tail = re.match(r"""^['"]?[ \t]+(.*)$""", content[match_end:tail_end])
    if not m_tail:
        return ""
    sanitized = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', m_tail.group(1))
    return re.split(r"&&|\|\||[;|]", sanitized, maxsplit=1)[0]


def _resolve_script_flag_entry(engine: Any, root: Path, script_rel: str, flag_cache: Dict[str, Tuple[bool, Set[str]]]) -> Tuple[bool, Set[str]]:
    if script_rel not in flag_cache:
        cand_script = engine._resolve_candidate(root, f"scripts/{script_rel}")
        if not cand_script.exists():
            cand_script = engine._resolve_candidate(engine.workspace_root, f"scripts/{script_rel}")
        exists = cand_script.exists() and cand_script.is_file()
        flag_cache[script_rel] = (exists, engine._extract_script_supported_flags(cand_script) if exists else set())
    return flag_cache[script_rel]


def _inspect_md_cli_flags(
    md_file: Path, engine: Any, root: Path, pattern: re.Pattern[str], flag_cache: Dict[str, Tuple[bool, Set[str]]], invalid_flags: List[str]
) -> int:
    try:
        content = md_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    checked = 0
    for match in pattern.finditer(content):
        args_tail = extract_cove_args_tail(content, match.start(), match.end())
        cited_flags = re.findall(r"(?<![-\w])(--(?:\*|[a-zA-Z0-9][a-zA-Z0-9_-]*))(?:=[^\s]*)?", args_tail) if args_tail else []
        if not cited_flags:
            continue
        script_rel = match.group(1).replace("\\", "/")
        script_exists, supported = _resolve_script_flag_entry(engine, root, script_rel, flag_cache)
        for fl in cited_flags:
            checked += 1
            if not script_exists:
                invalid_flags.append(f"{md_file.name}: {script_rel} {fl} (script not found)")
            elif fl == "--*" or fl not in supported:
                invalid_flags.append(f"{md_file.name}: {script_rel} {fl}")
    return checked


def verify_cli_flags_cove_impl(engine: Any, root_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Verifica i flag CLI su skill, agent e workflow inclusi moduli _internal e schemas."""
    root = Path(root_dir).resolve() if root_dir else engine.workspace_root
    invalid_flags, checked_invocations, flag_cache = [], 0, {}
    has_agents_tree = (root / ".agents").is_dir() or (root / ".staging" / ".agents").is_dir()
    md_files = _collect_overlay_md_files(root, ".agents" if has_agents_tree else "", recursive=True)
    pattern = re.compile(r"scripts[/\\]((?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?[a-zA-Z0-9_]+\.py)")
    for md_file in md_files:
        checked_invocations += _inspect_md_cli_flags(md_file, engine, root, pattern, flag_cache, invalid_flags)
    return {"passed": not invalid_flags, "checked_flags_count": checked_invocations, "files_checked": len(md_files), "invalid_flags": invalid_flags}
