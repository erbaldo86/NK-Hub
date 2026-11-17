"""Scansione SAST/Mojibake/JSON in Overlay Union e audit grounding report TAS."""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import HALLUCINATED_SCRIPT_DENYLIST
from _internal.rsi_convergence_engine.constants import (
    EXCLUDED_SCAN_DIRS,
    _extract_sast_report_count,
    _get_cached_file_and_ast,
    _is_excluded_rel_path,
    _workspace_root,
)
from _internal.rsi_convergence_engine.lazy_bridge import (
    get_ast_guard_validator,
    get_report_grounding_validator,
)

_MD_LINK_RE = re.compile(r"\]\(([^\)\r\n]+)\)")
_MD_SCRIPT_RE = re.compile(
    r"scripts[/\\]((?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?[a-zA-Z0-9_]+\.py)"
)
_MD_NEGATION_RE = re.compile(
    r"\b(?:inesistent\w*|allucinat\w*|non\s+esist\w*|denylist\w*|vietat\w*|proibit\w*|rimoss\w*|mai\s+usar\w*)\b",
    re.IGNORECASE,
)


def _strip_fenced_code(text: str) -> str:
    """Rimuove i blocchi di codice recintati per evitare falsi positivi sui link."""
    out_lines: List[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out_lines.append("")
            continue
        out_lines.append("" if in_fence else line)
    return "\n".join(out_lines)


def audit_markdown_doc_references(
    md_file: Path,
    content: str,
    root: Path,
    resolve_candidate_fn: Callable[[Path, str], Path],
    deleted_rel: Optional[Set[str]] = None,
    check_scripts: bool = True,
) -> Tuple[List[str], List[str]]:
    """Verifica link relativi rotti e script mancanti o vietati nei documenti attivi."""
    broken_links: List[str] = []
    phantom_scripts: List[str] = []
    del_set = {
        str(item).strip().replace("\\", "/").lstrip("./")
        for item in (deleted_rel or set())
        if str(item).strip()
    }
    resolved_root = Path(root).resolve()
    resolved_md = Path(md_file).resolve()
    try:
        rel_md = resolved_md.relative_to(resolved_root).as_posix()
    except ValueError:
        rel_md = resolved_md.name
    is_staged = rel_md.startswith(".staging/")
    logical_rel = rel_md[len(".staging/") :] if is_staged else rel_md
    logical_dir = posixpath.dirname(logical_rel)

    prose_only = _strip_fenced_code(content)
    for match in _MD_LINK_RE.finditer(prose_only):
        raw_inner = match.group(1).strip()
        if not raw_inner or raw_inner.startswith(
            ("http://", "https://", "file://", "#", "conversation://", "mailto:")
        ):
            continue
        link_raw = re.split(r'\s+["\']', raw_inner, maxsplit=1)[0].strip()
        link_path = link_raw.split("#", 1)[0].strip().strip("<>")
        if not link_path or any(
            ch in link_path for ch in ("*", "?", "{", "}", "^", "$", "[", "]", "\\", "<", ">")
        ):
            continue
        norm_link = link_path.replace("\\", "/")
        cand_rel = (
            posixpath.normpath(f"{logical_dir}/{norm_link}")
            if logical_dir
            else posixpath.normpath(norm_link)
        )
        direct_exists = (resolved_md.parent / link_path).exists()
        overlay_exists = False
        if not cand_rel.startswith("..") and cand_rel not in del_set:
            overlay_exists = resolve_candidate_fn(resolved_root, cand_rel).exists()
        root_rel = norm_link.lstrip("./")
        root_exists = (
            root_rel not in del_set
            and resolve_candidate_fn(resolved_root, root_rel).exists()
        )
        direct_deleted = not cand_rel.startswith("..") and cand_rel in del_set
        if not ((direct_exists and not direct_deleted) or overlay_exists or root_exists):
            broken_links.append(f"{logical_rel} -> {raw_inner}")

    if check_scripts:
        seen_phantoms: Set[str] = set()
        for line in content.splitlines():
            if _MD_NEGATION_RE.search(line):
                continue
            for m_sc in _MD_SCRIPT_RE.finditer(line):
                rel_sc = f"scripts/{m_sc.group(1).replace(chr(92), '/')}"
                if rel_sc in seen_phantoms:
                    continue
                cand_sc = resolve_candidate_fn(resolved_root, rel_sc)
                if rel_sc in del_set or not cand_sc.exists():
                    seen_phantoms.add(rel_sc)
                    phantom_scripts.append(f"{logical_rel}: script mancante '{rel_sc}'")
            for h_sc in HALLUCINATED_SCRIPT_DENYLIST:
                if h_sc in seen_phantoms:
                    continue
                if re.search(rf"\b{re.escape(h_sc)}\b", line, re.IGNORECASE):
                    seen_phantoms.add(h_sc)
                    phantom_scripts.append(f"{logical_rel}: script vietato '{h_sc}'")

    return broken_links, phantom_scripts


def scan_sast_and_mojibake_impl(
    engine: Any,
    root: Path,
    sast_report: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Scansiona .staging/ e produzione (codice, JSON e doc) per SAST, syntax e U+FFFD."""
    sast_count = _extract_sast_report_count(sast_report)
    sast_issues: List[str] = []
    mojibake_files: List[str] = []
    invalid_json_files: List[str] = []

    is_hub_root = root.resolve() == _workspace_root.resolve()
    staging_excluded = EXCLUDED_SCAN_DIRS - {".staging"}
    deleted_rel = {
        str(item).strip().replace("\\", "/").lstrip("./")
        for item in engine._load_staging_deleted_set(root)
    }

    overlay_map: Dict[str, Path] = {}
    stg_root = root / ".staging"
    if is_hub_root:
        for p in root.iterdir():
            if p.is_file() and p.suffix in (".py", ".md", ".json"):
                rel_k = p.relative_to(root).as_posix()
                if rel_k not in deleted_rel:
                    overlay_map[rel_k] = p
        for sub in ("scripts", "tests", ".agents", "nk_genome", "nk_tracking"):
            sub_dir = root / sub
            if sub_dir.is_dir():
                for p in sub_dir.rglob("*"):
                    if (
                        p.is_file()
                        and p.suffix in (".py", ".md", ".json")
                        and not _is_excluded_rel_path(p, root)
                    ):
                        rel_k = p.relative_to(root).as_posix()
                        if rel_k not in deleted_rel:
                            overlay_map[rel_k] = p
        if stg_root.is_dir():
            for p in stg_root.rglob("*"):
                if (
                    p.is_file()
                    and p.suffix in (".py", ".md", ".json")
                    and not any(
                        part in staging_excluded
                        for part in p.relative_to(stg_root).parts
                    )
                ):
                    overlay_map[p.relative_to(stg_root).as_posix()] = p
    else:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".md", ".json"):
                rel_parts = p.relative_to(root).parts
                if ".staging" in rel_parts or any(
                    part in staging_excluded for part in rel_parts
                ):
                    continue
                rel_k = p.relative_to(root).as_posix()
                if rel_k not in deleted_rel:
                    overlay_map[rel_k] = p
        if stg_root.is_dir():
            for p in stg_root.rglob("*"):
                if (
                    p.is_file()
                    and p.suffix in (".py", ".md", ".json")
                    and not any(
                        part in staging_excluded
                        for part in p.relative_to(stg_root).parts
                    )
                ):
                    overlay_map[p.relative_to(stg_root).as_posix()] = p

    agv_cls: Any = None
    unique_files = sorted({p.resolve() for p in overlay_map.values()})
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
            except Exception as exc:
                invalid_json_files.append(f"{rel_label}: {exc}")
        elif fpath.suffix == ".py":
            if agv_cls is None:
                agv_cls = get_ast_guard_validator()
            if agv_cls is not None:
                try:
                    v_list = agv_cls.check_sast_constructs(
                        text, target_file=fpath.as_posix()
                    )
                except TypeError:
                    v_list = agv_cls.check_sast_constructs(text)
                if v_list:
                    sast_count += len(v_list)
                    for v in v_list[:3]:
                        sast_issues.append(f"{rel_label}: {v.message}")

    return {
        "passed": sast_count == 0
        and len(mojibake_files) == 0
        and len(invalid_json_files) == 0,
        "sast_critical": sast_count,
        "sast_issues": sast_issues,
        "mojibake_count": len(mojibake_files),
        "mojibake_files": mojibake_files,
        "invalid_json_count": len(invalid_json_files),
        "invalid_json_files": invalid_json_files,
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
        tas_patterns = ("tas_certification_report*.md", "TAS_Report_*.md")
        prod_rep_dir = root / "nk_tracking" / "reports_and_briefs"
        if prod_rep_dir.exists() and prod_rep_dir.is_dir():
            for t_pat in tas_patterns:
                for rep_p in sorted(prod_rep_dir.glob(t_pat)):
                    if (
                        rep_p.is_file()
                        and rep_p.relative_to(root).as_posix() not in tas_deleted
                    ):
                        tas_map[rep_p.name] = rep_p
        stg_rep_dir = root / ".staging" / "nk_tracking" / "reports_and_briefs"
        if stg_rep_dir.exists() and stg_rep_dir.is_dir():
            for t_pat in tas_patterns:
                for rep_p in sorted(stg_rep_dir.glob(t_pat)):
                    if rep_p.is_file():
                        tas_map[rep_p.name] = rep_p
        for rep_name, rep_path in sorted(tas_map.items()):
            verified_files.append(rep_path)
            g_res = verify_report_grounding(rep_path)
            tas_grounding_reports.append(g_res)
            h_list = g_res.get("hallucinated_scripts", [])
            if h_list:
                hallucinated_refs_count += len(h_list)
                violations.append(
                    f"{rep_name}: script allucinati rilevati da verify_report_grounding: {h_list}"
                )

    return hallucinated_refs_count, {
        "passed": hallucinated_refs_count == 0,
        "reports_checked": len(tas_grounding_reports),
        "hallucinated_refs": hallucinated_refs_count,
        "details": tas_grounding_reports,
    }
