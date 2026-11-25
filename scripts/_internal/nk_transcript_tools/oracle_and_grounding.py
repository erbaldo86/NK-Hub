# -*- coding: utf-8 -*-
"""Oracle lock, report-conflict e verify_report_grounding per nk_transcript_tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import HALLUCINATED_SCRIPT_DENYLIST, NK_LOCK_FILENAMES
from _internal.nk_common.oracle_lock import (
    compute_lf_sha256,
    sha256_eol_matches,
    verify_oracle_lock_manifest,
    write_oracle_lock_manifest,
)
from _internal.nk_common.paths import resolve_workspace_root
from _internal.nk_transcript_tools.constants import validate_intent_brief_id

_GROUNDING_SCRIPT_PATH_RE = re.compile(
    r"scripts[/\\]((?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?[a-zA-Z0-9_]+\.py)"
)
_GROUNDING_TABLE_SCRIPT_RE = re.compile(
    r"^\s*\|\s*(?:\d+\s*\|\s*)?`?(?:scripts[/\\]((?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?))?([a-zA-Z0-9_]+\.py)`?\s*\|"
)
_EXPLICIT_SCRIPT_NEGATION_RE = re.compile(
    r"\b(?:inesistent\w*|allucinat\w*|non\s+esist\w*|denylist\w*|vietat\w*|proibit\w*|non\s+usar\w*|mai\s+usar\w*)\b",
    re.IGNORECASE,
)


def _hash_benchmark_suite_dir(
    ws_root: Path, files_map: Dict[str, str], skip_fn: Any
) -> None:
    """Calcola e registra gli SHA-256 LF-normalizzati dei file *.json in nk_tracking/benchmark_suite."""
    bench_dir = ws_root / "nk_tracking" / "benchmark_suite"
    if not bench_dir.is_dir():
        return
    for bf in sorted(bench_dir.rglob("*.json")):
        if not skip_fn(bf, bench_dir):
            rel_bf = bf.relative_to(bench_dir).as_posix()
            files_map[f"../nk_tracking/benchmark_suite/{rel_bf}"] = compute_lf_sha256(bf)


def _normalize_exclude_set(exclude_paths: Optional[Set[Path]]) -> Set[Path]:
    """Normalizza i percorsi assoluti esclusi dal calcolo SHA-256."""
    if not exclude_paths:
        return set()
    return {p.resolve() for p in exclude_paths}


def _is_ignored_oracle_file(
    file_p: Path,
    ignored_suffixes: Set[str],
    ignored_names: Set[str],
    exclude_set: Set[Path],
) -> bool:
    """Verifica se il file appartiene a suffissi effimeri o file lock esclusi."""
    if file_p.suffix.lower() in ignored_suffixes or file_p.name in ignored_names:
        return True
    return bool(exclude_set and file_p.resolve() in exclude_set)


def _hash_target_files(
    target: Path,
    exclude_paths: Optional[Set[Path]] = None,
) -> Dict[str, str]:
    """Calcola la mappa percorso_relativo -> sha256 per un file o target multi-root."""
    resolved = target.resolve()
    if resolved.is_file():
        return {resolved.name: compute_lf_sha256(resolved)}
    ignored_parts = {"__pycache__", ".pytest_cache", ".git", ".staging", ".wal"}
    ignored_suffixes = {".zip", ".tmp", ".bak"}
    ignored_names = {
        *NK_LOCK_FILENAMES,
        ".bootstrap_fast_cache.json",
        ".fast_stat_cache.json",
        ".session_state.json",
        "session_anchor.jsonl",
    }
    exclude_set = _normalize_exclude_set(exclude_paths)

    def _skip_entry(file_p: Path, base_p: Path) -> bool:
        if not file_p.is_file():
            return True
        if _is_ignored_oracle_file(file_p, ignored_suffixes, ignored_names, exclude_set):
            return True
        if any(pt in ignored_parts for pt in file_p.parts):
            return True
        try:
            rel_parts = file_p.relative_to(base_p).parts
        except ValueError:
            return True
        return bool((resolved / "NK_Hub").is_dir() and rel_parts and rel_parts[0] == ".agents")

    files_map: Dict[str, str] = {}
    if resolved.is_dir():
        for f in sorted(resolved.rglob("*")):
            if not _skip_entry(f, resolved):
                files_map[f.relative_to(resolved).as_posix()] = compute_lf_sha256(f)
        if resolved.name == "tests" and (resolved.parent / "scripts").is_dir():
            ws_root = resolved.parent
            scripts_dir = ws_root / "scripts"
            for sf in sorted(scripts_dir.rglob("*.py")):
                if not _skip_entry(sf, scripts_dir):
                    files_map[f"../scripts/{sf.relative_to(scripts_dir).as_posix()}"] = compute_lf_sha256(sf)

            pytest_ini = ws_root / "pytest.ini"
            if pytest_ini.is_file():
                files_map["../pytest.ini"] = compute_lf_sha256(pytest_ini)

            _hash_benchmark_suite_dir(ws_root, files_map, _skip_entry)

            for sub_name in (".agents", ".github"):
                sub_dir = ws_root / sub_name
                if sub_dir.is_dir():
                    for af in sorted(sub_dir.rglob("*")):
                        if not _skip_entry(af, sub_dir):
                            files_map[f"../{sub_name}/{af.relative_to(sub_dir).as_posix()}"] = compute_lf_sha256(af)

            genome_dir = ws_root / "nk_genome"
            if genome_dir.is_dir():
                excluded = {"PATCH_NOTES.md", "repo_map.md", "SKILL_INDEX.md", "nk_registry_manifest.json"}
                for nf in sorted(genome_dir.rglob("*.md")):
                    if _skip_entry(nf, genome_dir):
                        continue
                    rel_n = nf.relative_to(genome_dir).as_posix()
                    if rel_n == "shards" or rel_n.startswith("shards/") or rel_n in excluded:
                        continue
                    if "/" in rel_n and not rel_n.startswith("modules/"):
                        continue
                    files_map[f"../nk_genome/{rel_n}"] = compute_lf_sha256(nf)
    return files_map


def _sha256_eol_matches(file_path: Path, expected_sha: str) -> bool:
    """Verifica la corrispondenza SHA-256 normalizzando CRLF e LF."""
    return sha256_eol_matches(file_path, expected_sha)


def handle_oracle_lock(action: str, target: Path, lock_file: Path) -> Tuple[Dict[str, Any], int]:
    """Crea o verifica il manifesto SHA-256 della ground truth e dei test."""
    current_map = _hash_target_files(target, exclude_paths={lock_file.resolve()})
    if not current_map:
        return {"status": "ERROR", "passed": False, "error": f"Empty or missing target: {target}"}, 1
    if action in ("create", "freeze"):
        res = write_oracle_lock_manifest(lock_file, target, current_map)
        return res, (0 if res.get("passed") else 1)
    res = verify_oracle_lock_manifest(lock_file, target, current_map=current_map)
    return res, (0 if res.get("passed") else 1)


def handle_report_conflict(
    root: Optional[Path] = None,
    test_a: str = "",
    test_b: str = "",
    reason: str = "",
    output: Optional[Path] = None,
) -> Tuple[Dict[str, Any], int]:
    """Genera epistemic_conflict_report.json con HALT_EPISTEMIC_CONFLICT."""
    base_root = Path(root).resolve() if root else Path(".").resolve()
    out_path = Path(output).resolve() if output else (base_root / "nk_tracking" / "epistemic_conflict_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "status": "HALT_EPISTEMIC_CONFLICT",
        "passed": True,
        "test_a": test_a,
        "test_b": test_b,
        "reason": reason or "Epistemic conflict detected between locked oracle tests or requirements.",
        "report_path": out_path.as_posix(),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload, 0


def _is_explicitly_negated_script_mention(
    line: str, match_start: int, match_end: int, script_name: str
) -> bool:
    """Determina se la specifica occorrenza di uno script risulta negata."""
    prefix_window = line[max(0, match_start - 55) : match_start]
    if re.search(
        r"\b(?:python3?|py|esegui\w*|lancia\w*|invoca\w*|chiama\w*)\s+[`\"']?(?:scripts[/\\](?:(?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?)?)?$",
        prefix_window,
        re.IGNORECASE,
    ):
        return False

    local_ctx = line[max(0, match_start - 60) : min(len(line), match_end + 60)]
    if _EXPLICIT_SCRIPT_NEGATION_RE.search(local_ctx):
        return True

    esc_name = re.escape(script_name)
    targeted_status_re = re.compile(
        rf"(?:(?:script|modulo|file)\s+(?:rimoss\w*|bloccat\w*)[^.;,\n]{{0,25}}{esc_name})"
        rf"|(?:(?:rimoss\w*|bloccat\w*)\s+[`\"']?(?:scripts[/\\](?:(?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?)?)?{esc_name})"
        rf"|(?:{esc_name}[`\"']?\s*(?:\([^)]*(?:rimoss|bloccat|inesistent|allucinat|denylist)[^)]*\)|(?:\s+e\s+|\s+è\s+|\s+stato\s+)(?:rimoss|bloccat)))",
        re.IGNORECASE,
    )
    return bool(targeted_status_re.search(line))


def _collect_grounding_valid_scripts(root_dir: Path, mpath: Path) -> Tuple[Set[str], Set[str]]:
    """Raccoglie basename e percorsi scripts/**/*.py da filesystem, manifest e index."""
    valid_basenames: Set[str] = set()
    valid_rel_paths: Set[str] = set()

    def _register_entry(raw_key: str) -> None:
        norm_k = re.sub(r"^(?:\./)+", "", str(raw_key).strip().replace("\\", "/")).lstrip("/")
        if not norm_k.endswith(".py"):
            return
        valid_basenames.add(Path(norm_k).name)
        if norm_k.startswith("scripts/"):
            valid_rel_paths.add(norm_k)
        elif norm_k.startswith(("_internal/", "schemas/")):
            valid_rel_paths.add(f"scripts/{norm_k}")
        elif "/" not in norm_k:
            valid_rel_paths.add(f"scripts/{norm_k}")

    if mpath.is_file():
        try:
            mdata = json.loads(mpath.read_text(encoding="utf-8"))
            for k in mdata.get("scripts_index", {}).keys():
                _register_entry(k)
        except Exception:
            pass

    index_candidates = [
        root_dir / ".staging" / "nk_tracking" / "internal_integrity_index.json",
        root_dir / "nk_tracking" / "internal_integrity_index.json",
    ]
    if mpath.parent.name == "nk_genome":
        index_candidates.append(mpath.parent.parent / "nk_tracking" / "internal_integrity_index.json")
    for idx_path in index_candidates:
        if not idx_path.is_file():
            continue
        try:
            idata = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(idata, dict):
            for sect_k in ("files", "scripts_index", "internal_index", "modules"):
                sect = idata.get(sect_k)
                if isinstance(sect, dict):
                    for k in sect.keys():
                        _register_entry(k)
                elif isinstance(sect, list):
                    for item in sect:
                        if isinstance(item, str):
                            _register_entry(item)
            for k in idata.keys():
                _register_entry(k)

    for sdir in (root_dir / "scripts", root_dir / ".staging" / "scripts"):
        if sdir.is_dir():
            for p in sdir.rglob("*.py"):
                if "__pycache__" in p.parts:
                    continue
                valid_basenames.add(p.name)
                valid_rel_paths.add(f"scripts/{p.relative_to(sdir).as_posix()}")

    return valid_basenames, valid_rel_paths


def verify_report_grounding(
    report_path: Path,
    manifest_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verifica che il report citi solo script reali registrati inclusi _internal e schemas."""
    rpath = Path(report_path).resolve()
    if not rpath.is_file():
        return {
            "passed": False,
            "status": "MISSING_REPORT",
            "report": str(rpath),
            "verified_scripts": [],
            "hallucinated_scripts": [],
            "intent_brief_ids": [],
            "exit_code": 1,
        }
    root_dir = Path(resolve_workspace_root(__file__)).resolve()
    mpath = (
        Path(manifest_path).resolve()
        if manifest_path
        else (root_dir / "nk_genome" / "nk_registry_manifest.json")
    )
    if manifest_path and mpath.parent.name == "nk_genome":
        root_dir = mpath.parent.parent
    valid_basenames, valid_rel_paths = _collect_grounding_valid_scripts(root_dir, mpath)

    denylist_set = {s.lower() for s in HALLUCINATED_SCRIPT_DENYLIST}
    content = rpath.read_text(encoding="utf-8", errors="replace")
    ib_info = validate_intent_brief_id(content)
    referenced: List[Tuple[str, bool]] = []
    seen_refs: Set[Tuple[str, bool]] = set()

    for line in content.splitlines():
        for m in _GROUNDING_SCRIPT_PATH_RE.finditer(line):
            rel_part = m.group(1).replace("\\", "/")
            full_ref = f"scripts/{rel_part}"
            sc_name = Path(rel_part).name
            has_subdir = "/" in rel_part
            is_missing = sc_name.lower() in denylist_set or full_ref not in valid_rel_paths
            if is_missing and _is_explicitly_negated_script_mention(line, m.start(), m.end(), sc_name):
                continue
            ref_key = (full_ref if has_subdir else sc_name, has_subdir)
            if ref_key not in seen_refs:
                seen_refs.add(ref_key)
                referenced.append(ref_key)

        for m in _GROUNDING_TABLE_SCRIPT_RE.finditer(line):
            sub_prefix = (m.group(1) or "").replace("\\", "/")
            sc_name = m.group(2)
            has_scripts_prefix = m.group(1) is not None
            has_subdir = bool(sub_prefix)
            if has_scripts_prefix:
                full_ref = f"scripts/{sub_prefix}{sc_name}"
                is_missing = sc_name.lower() in denylist_set or full_ref not in valid_rel_paths
                ref_label = full_ref if has_subdir else sc_name
            else:
                is_missing = sc_name.lower() in denylist_set or sc_name not in valid_basenames
                ref_label = sc_name
            if is_missing and _is_explicitly_negated_script_mention(line, m.start(), m.end(), sc_name):
                continue
            ref_key = (ref_label, has_scripts_prefix)
            if ref_key not in seen_refs:
                seen_refs.add(ref_key)
                referenced.append(ref_key)

        for h_sc in HALLUCINATED_SCRIPT_DENYLIST:
            for m_h in re.finditer(rf"\b{re.escape(h_sc)}\b", line, re.IGNORECASE):
                if not _is_explicitly_negated_script_mention(line, m_h.start(), m_h.end(), h_sc):
                    ref_key = (h_sc, False)
                    if ref_key not in seen_refs:
                        seen_refs.add(ref_key)
                        referenced.append(ref_key)

    verified: List[str] = []
    hallucinated: List[str] = []
    for ref_label, check_rel in sorted(referenced, key=lambda item: item[0]):
        sc_base = Path(ref_label).name
        if sc_base.lower() in denylist_set:
            hallucinated.append(ref_label)
        elif check_rel:
            rel_check = ref_label if ref_label.startswith("scripts/") else f"scripts/{ref_label}"
            (verified if rel_check in valid_rel_paths else hallucinated).append(ref_label)
        elif ref_label in valid_basenames:
            verified.append(ref_label)
        else:
            hallucinated.append(ref_label)
    passed = len(hallucinated) == 0
    return {
        "passed": passed,
        "status": "GROUNDED" if passed else "HALLUCINATED_SCRIPTS_DETECTED",
        "report": str(rpath),
        "verified_scripts": verified,
        "hallucinated_scripts": hallucinated,
        "intent_brief_ids": ib_info["ids"],
        "exit_code": 0 if passed else 1,
    }
