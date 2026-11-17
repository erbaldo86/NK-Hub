"""Telemetria SHA-256 Guardia G4 e verifica flag CLI CoVe per RSI."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.rsi_convergence_engine.constants import (
    _TELEMETRY_LOCK,
    RSIIterationRecord,
    _collect_overlay_md_files,
    _get_cached_file_and_ast,
)


def compute_record_hash_impl(record_dict: Dict[str, Any]) -> str:
    """Calcola l'hash SHA-256 canonico di un record telemetrico."""
    payload = {k: v for k, v in record_dict.items() if k != "record_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_last_telemetry_hash_impl(engine: Any) -> str:
    """Legge l'ultimo record_hash dal file rsi_telemetry.jsonl."""
    if not engine.telemetry_path.exists():
        return "0" * 64
    last_hash = "0" * 64
    try:
        with open(engine.telemetry_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                last_hash = data.get("record_hash", last_hash)
    except Exception:
        pass
    return last_hash


def append_telemetry_record_impl(
    engine: Any, record: RSIIterationRecord
) -> RSIIterationRecord:
    """Aggiunge in modo thread-safe un record alla catena SHA-256 (Guardia G4)."""
    with _TELEMETRY_LOCK:
        engine.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        prev_hash = engine._get_last_telemetry_hash()
        rec_dict = record.model_dump()
        rec_dict["prev_hash"] = prev_hash
        rec_hash = engine._compute_record_hash(rec_dict)
        rec_dict["record_hash"] = rec_hash

        signed_record = RSIIterationRecord.model_validate(rec_dict)
        with open(engine.telemetry_path, "a", encoding="utf-8") as f:
            f.write(signed_record.model_dump_json() + "\n")
            f.flush()
        return signed_record


def verify_telemetry_chain_impl(
    engine: Any, telemetry_path: Optional[Path] = None
) -> Tuple[bool, int, str]:
    """Verifica l'integrita crittografica della catena SHA-256 in rsi_telemetry.jsonl."""
    target = Path(telemetry_path) if telemetry_path else engine.telemetry_path
    if not target.exists():
        return True, 0, "Nessun file telemetrico presente."

    expected_prev = "0" * 64
    count = 0
    try:
        with open(target, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                actual_prev = data.get("prev_hash", "")
                if actual_prev != expected_prev:
                    return (
                        False,
                        count,
                        f"Violazione catena alla riga {idx}: prev_hash non corrisponde.",
                    )
                computed = engine._compute_record_hash(data)
                if data.get("record_hash", "") != computed:
                    return (
                        False,
                        count,
                        f"Violazione integrita alla riga {idx}: record_hash alterato.",
                    )
                expected_prev = computed
                count += 1
    except Exception as exc:
        return False, count, f"Errore lettura catena telemetrica: {exc}"

    return True, count, f"Catena SHA-256 integra ({count} record verificati)."


def extract_script_supported_flags_impl(script_path: Path) -> Set[str]:
    """Estrae i flag CLI --flag supportati nell'AST inclusi i sottomoduli _internal/<stem>."""
    ignored_external = {"--porcelain", "--tb=short", "--version"}
    if not script_path.exists() or not script_path.is_file():
        return set()
    flags: Set[str] = set()
    scan_paths: List[Path] = [script_path]
    if script_path.parent.name == "scripts":
        sub_pkg_dir = script_path.parent / "_internal" / script_path.stem
        if sub_pkg_dir.is_dir():
            scan_paths.extend(sorted(sub_pkg_dir.glob("*.py")))
    for cand_p in scan_paths:
        try:
            source_text, tree = _get_cached_file_and_ast(cand_p)
            if tree is None:
                continue
            if (
                "argparse" in source_text
                or "ArgumentParser" in source_text
                or "sys.argv" in source_text
            ):
                flags.add("--help")
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    val = node.value.strip()
                    if (
                        val.startswith("--")
                        and "*" not in val
                        and val not in ignored_external
                    ):
                        flag_token = val.split("=", 1)[0]
                        if (
                            flag_token not in ignored_external
                            and re.match(r"^--[a-zA-Z0-9][a-zA-Z0-9_-]*$", flag_token)
                        ):
                            flags.add(flag_token)
        except Exception:
            continue
    return flags


def extract_cove_args_tail(content: str, match_start: int, match_end: int) -> str:
    """Estrae gli argomenti sulla riga corrente rispettando apici e delimitatori."""
    line_start = content.rfind("\n", 0, match_start) + 1
    line_end = content.find("\n", match_end)
    if line_end == -1:
        line_end = len(content)
    prefix_line = content[line_start:match_start]
    tail_end = line_end
    if prefix_line.count("`") % 2 == 1:
        close_tick = content.find("`", match_end, line_end)
        if close_tick != -1:
            tail_end = close_tick
    raw_tail = content[match_end:tail_end]
    m_tail = re.match(r"""^['"]?[ \t]+(.*)$""", raw_tail)
    if not m_tail:
        return ""
    args_tail = m_tail.group(1)
    sanitized = re.sub(
        r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        '""',
        args_tail,
    )
    return re.split(r"&&|\|\||[;|]", sanitized, maxsplit=1)[0]


def verify_cli_flags_cove_impl(
    engine: Any, root_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Verifica i flag CLI su skill, agent e workflow inclusi moduli _internal e schemas."""
    root = Path(root_dir).resolve() if root_dir else engine.workspace_root
    invalid_flags: List[str] = []
    checked_invocations = 0

    has_agents_tree = (root / ".agents").is_dir() or (
        root / ".staging" / ".agents"
    ).is_dir()
    if has_agents_tree:
        md_files = _collect_overlay_md_files(root, ".agents", recursive=True)
    else:
        md_files = _collect_overlay_md_files(root, "", recursive=True)

    flag_cache: Dict[str, Tuple[bool, Set[str]]] = {}
    pattern = re.compile(
        r"scripts[/\\]((?:_internal[/\\](?:[a-zA-Z0-9_]+[/\\])*|schemas[/\\])?[a-zA-Z0-9_]+\.py)"
    )

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for match in pattern.finditer(content):
            script_rel = match.group(1).replace("\\", "/")
            args_tail = extract_cove_args_tail(content, match.start(), match.end())
            if not args_tail:
                continue
            cited_flags = re.findall(
                r"(?<![-\w])(--(?:\*|[a-zA-Z0-9][a-zA-Z0-9_-]*))(?:=[^\s]*)?",
                args_tail,
            )
            if not cited_flags:
                continue

            if script_rel not in flag_cache:
                cand_script = engine._resolve_candidate(root, f"scripts/{script_rel}")
                if not cand_script.exists():
                    cand_script = engine._resolve_candidate(
                        engine.workspace_root, f"scripts/{script_rel}"
                    )
                exists = cand_script.exists() and cand_script.is_file()
                supported_set = (
                    engine._extract_script_supported_flags(cand_script)
                    if exists
                    else set()
                )
                flag_cache[script_rel] = (exists, supported_set)

            script_exists, supported = flag_cache[script_rel]
            if not script_exists:
                for fl in cited_flags:
                    checked_invocations += 1
                    invalid_flags.append(
                        f"{md_file.name}: {script_rel} {fl} (script not found)"
                    )
                continue

            for fl in cited_flags:
                checked_invocations += 1
                if fl == "--*" or fl not in supported:
                    invalid_flags.append(f"{md_file.name}: {script_rel} {fl}")

    return {
        "passed": len(invalid_flags) == 0,
        "checked_flags_count": checked_invocations,
        "files_checked": len(md_files),
        "invalid_flags": invalid_flags,
    }
