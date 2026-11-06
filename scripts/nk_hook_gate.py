#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gate runtime leggero per gli hook del ciclo di vita di Nexus Keystone v6.0.0.
Modulo: scripts/nk_hook_gate.py.
@domain_id: DOM-01
Usa solo la libreria standard Python per garantire avvio inferiore a 50 ms.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = (
    _SCRIPT_DIR.parent.parent
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR.parent
)
HALLUCINATED_SCRIPT_DENYLIST = (
    "atomic_2pc_commit.py",
    "nk_2pc_promoter.py",
    "nk_2pc_commit.py",
    "nk_ast_guard.py",
    "nk_ast_mapper.py",
    "nk_memory_engine.py",
    "nk_memory_compactor.py",
    "nk_oracle_lock.py",
    "nk_quality_ratchet.py",
    "nk_rsi_engine.py",
    "nk_sbfl_engine.py",
    "nk_sast_scanner.py",
    "nk_dast_runner.py",
    "nk_prompt_linter.py",
    "nk_ste100_validator.py",
    "nk_mutation_runner.py",
    "agent_Context_Rot_Sentinel.py",
    "bootstrap_nk_hub_scaffold.py",
    "context_pruner.py",
    "generate_golden_tests.py",
    "goal_checkpoint_engine.py",
    "knowledge_graph_engine.py",
    "micro_ui_hud_renderer.py",
    "nk_Dag_Orchestrator.py",
    "nk_genome_validator.py",
    "nk_git_Engine.py",
    "nk_ipc_pointer_engine.py",
    "nk_Mutation_Scorer.py",
    "nk_Prompt_Gate.py",
    "owasp_sast_scanner.py",
    "sbfl_ochiai_localizer.py",
    "telemetry_logger.py",
)

def pre_command_gate(cmd: str) -> Dict[str, Any]:
    """Blocca qualsiasi comando che invochi uno dei 16 script allucinati."""
    cmd_low = (cmd or "").replace("\\", "/").lower()
    for h_script in HALLUCINATED_SCRIPT_DENYLIST:
        if h_script.lower() in cmd_low:
            return {
                "decision": "deny",
                "reason_code": "HALLUCINATED_SCRIPT_BLOCKED",
                "reason": f"Blocked hallucinated script invocation: {h_script}",
            }
    return {}

_DELEGATION_TOOLS = ("invoke_subagent", "define_subagent", "send_message")
_READ_ONLY_TOOLS = (
    "read_file",
    "view_file",
    "view_file_outline",
    "view_code_item",
    "list_dir",
    "find_by_name",
    "grep_search",
    "list_resources",
    "read_resource",
    "search_web",
)
_SAFE_DIR_COMPONENTS = (
    "nk_genome",
    "genome",
    "scratch",
    "nk_hooks",
    "nk_diagnostics",
)
_SAFE_ROOT_FILENAMES = (
    "readme.md",
    "readme.it.md",
    "patch_notes.md",
)
_CMD_WRITE_INDICATORS = (
    ">",
    "set-content",
    "add-content",
    "out-file",
    "remove-item",
    "copy-item",
    "move-item",
    "new-item",
    "clear-content",
    "rename-item",
    "tee-object",
    "start-process",
    "[system.io.file]::",
    "[io.file]::",
    "del ",
    "rm ",
    "cp ",
    "mv ",
    "write_text",
    "write_bytes",
    "shutil.",
    "os.replace",
    "os.remove",
    "unlink(",
)
_CERT_RE = re.compile(r"(\bCONVERGED_OPTIMAL\b|\b\d+/\d+\s+PASS\b)", re.IGNORECASE)
_OPEN_WRITE_RE = re.compile(
    r"\bopen\s*\([^)]*(?:['\"][wax+][b+t]*['\"]|mode\s*=\s*['\"][wax+])|\bopen\s*\([^)]*\)\s*\.\s*write",
    re.IGNORECASE,
)
_ENCODED_CMD_RE = re.compile(
    r"(?:^|[\s\"';|&])-(?:encodedcommand|enc|ec)\b",
    re.IGNORECASE,
)
_DESTRUCTIVE_GIT_RE = re.compile(
    r"\bgit\s+(?:"
    r"reset\s+[^\n;|&]*--hard\b"
    r"|clean\s+[^\n;|&]*(?:-[a-zA-Z]*f[a-zA-Z]*|--force)\b"
    r"|checkout\s+(?:--\s+|\.|-(?:f|-force)\b|(?:HEAD\s+--\s+)|(?:[^\n;|&]*\b(?:scripts|\.agents|src_app|tests|nk_tracking)\b))"
    r"|restore\s+(?!--staged\b)[^\n;|&]*"
    r")",
    re.IGNORECASE,
)
_PROTECTED_DIR_CMD_RE = re.compile(
    r"(?:^|[\s\"'/\\])(?:scripts|\.agents)(?:$|[\s\"'/\\])",
    re.IGNORECASE,
)
_UNSTAGE_CODE_DIR_CMD_RE = re.compile(
    r"(?:^|[\s\"'/\\])(?:src_app|tests)(?:$|[\s\"'/\\])|checkpoint_|patch_notes\.md",
    re.IGNORECASE,
)


def _has_cmd_write_indicator(cmd_low: str) -> bool:
    """Rileva indicatori di scrittura o cancellazione shell incluso open(..., 'w')."""
    return any(ind in cmd_low for ind in _CMD_WRITE_INDICATORS) or bool(
        _OPEN_WRITE_RE.search(cmd_low)
    )


def _get_hooks_temp_dir() -> Path:
    """Restituisce e crea la directory temporanea per lo stato degli hook."""
    base = Path(os.environ.get("NK_HOOKS_TEMP_DIR") or tempfile.gettempdir()) / "nk_hooks"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _read_stdin_payload() -> Dict[str, Any]:
    """Legge eventuale JSON da stdin in modo sicuro senza bloccare su terminale o pipe aperta."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        if os.name == "nt" and hasattr(sys.stdin, "fileno"):
            try:
                import ctypes
                import msvcrt

                fd = sys.stdin.fileno()
                handle = msvcrt.get_osfhandle(fd)
                avail = ctypes.c_ulong(0)
                ok = ctypes.windll.kernel32.PeekNamedPipe(
                    ctypes.c_void_p(handle), None, 0, None, ctypes.byref(avail), None
                )
                if ok and avail.value == 0:
                    return {}
            except Exception:
                pass
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _resolve_conv_id(cli_id: Optional[str], payload: Dict[str, Any]) -> str:
    """Risolve l'identificativo di conversazione da CLI, payload o ambiente."""
    raw = (
        cli_id
        or payload.get("conversationId")
        or payload.get("conversation_id")
        or os.environ.get("NK_CONVERSATION_ID")
        or "default"
    )
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", str(raw))


def _sha256_file(path: Path) -> str:
    """Calcola l'hash SHA-256 del file indicato."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_first_section(text: str) -> str:
    """Estrae la prima sezione storica da PATCH_NOTES.md per il controllo prepend-only."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for idx, ln in enumerate(lines):
        if ln.startswith("## "):
            return "\n".join(lines[idx : idx + 6])
    return "\n".join(lines[:6])


def _extract_historical_headers(text: str) -> List[str]:
    """Estrae tutte le intestazioni di sezione storiche da PATCH_NOTES.md."""
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip().startswith(("## ", "### "))
    ]


def _resolve_effective_hub_root(project_root: Path) -> Path:
    """Risolve la sottocartella NK_Hub quando project_root punta alla cartella padre."""
    root = Path(os.path.normpath(str(project_root))).resolve(strict=False)
    nk_hub_sub = root / "NK_Hub"
    if not (root / "nk_tracking").exists() and nk_hub_sub.is_dir():
        if (
            (nk_hub_sub / "nk_tracking").exists()
            or (nk_hub_sub / ".staging").exists()
            or (nk_hub_sub / "scripts").exists()
        ):
            return Path(os.path.normpath(str(nk_hub_sub.resolve(strict=False))))
    return root


def _resolve_target_path(target_str: str, project_root: Path) -> Path:
    """Risolve e normalizza i segmenti '..' di un target rispetto a project_root o NK_Hub."""
    cleaned = target_str.strip().replace("/", os.sep).replace("\\", os.sep)
    raw_p = Path(os.path.normpath(cleaned))
    if raw_p.is_absolute():
        return Path(os.path.normpath(str(raw_p.resolve(strict=False))))
    root = Path(os.path.normpath(str(project_root))).resolve(strict=False)
    hub_root = _resolve_effective_hub_root(root)
    if raw_p.parts and raw_p.parts[0].lower() == "nk_hub":
        base = root.parent if root.name.lower() == "nk_hub" else root
        return Path(os.path.normpath(str((base / raw_p).resolve(strict=False))))
    cand_direct = Path(os.path.normpath(str((root / raw_p).resolve(strict=False))))
    if hub_root != root and not cand_direct.exists():
        return Path(os.path.normpath(str((hub_root / raw_p).resolve(strict=False))))
    return cand_direct


def _is_valid_staging_path(cand: Path, project_root: Path) -> bool:
    """Verifica che il percorso risieda realmente sotto la cartella .staging della root."""
    cand_res = Path(os.path.normpath(str(cand.resolve(strict=False))))
    root_res = Path(os.path.normpath(str(project_root.resolve(strict=False))))
    hub_res = _resolve_effective_hub_root(root_res)
    for base_root in (root_res, hub_res, root_res / "NK_Hub"):
        staging_root = Path(
            os.path.normpath(str((base_root / ".staging").resolve(strict=False)))
        )
        if cand_res == staging_root or staging_root in cand_res.parents:
            return True
    parts_low = [p.lower() for p in cand_res.parts]
    if "nk_external_projects" in parts_low:
        idx = parts_low.index("nk_external_projects")
        if len(parts_low) > idx + 2 and parts_low[idx + 2] == ".staging":
            return True
    return False


def _sanitize_staged_tokens_in_cmd(cmd_low: str) -> str:
    """Rimuove dal comando shell i soli token che puntano legittimamente a .staging/ o %TEMP%."""
    def _repl(match: re.Match[str]) -> str:
        tok = match.group(0)
        if ".." in tok:
            return tok
        prefix = tok.split(".staging/", 1)[0]
        if any(bad in prefix for bad in ("scripts/", ".agents/", "src_app/", "tests/")):
            return tok
        return " __staged_safe__ "

    def _repl_temp(match: re.Match[str]) -> str:
        tok = match.group(0)
        if ".." in tok:
            return tok
        return " __temp_safe__ "

    sanitized = re.sub(
        r"(?:^|(?<=[\s\"'=]))[^\s\"';|&]*?\.staging/[^\s\"';|&]+",
        _repl,
        cmd_low,
    )
    sanitized = re.sub(
        r"(?:^|(?<=[\s\"'=]))[^\s\"';|&]*?(?:%temp%|appdata/local/temp|/temp/|nk_diagnostics|nk_sandbox_|scratch/)[^\s\"';|&]+",
        _repl_temp,
        sanitized,
    )
    return sanitized


def _is_authorized_script_invocation(cmd_str: str) -> bool:
    """Verifica che il comando invochi realmente uno script autorizzato senza concatenazioni o scritture."""
    norm = cmd_str.replace("\\", "/").strip()
    norm_low = norm.lower()
    if any(sep in norm_low for sep in (";", "|", "&", "\n", "\r")):
        return False
    if any(ind in norm_low for ind in _CMD_WRITE_INDICATORS):
        return False
    return bool(
        re.match(
            r"^\s*(?:[\"']?[^\s\"']*?(?:python(?:3)?|py)(?:\.exe)?[\"']?)\s+(?:-[a-zA-Z0-9]+\s+)*[\"']?(?:[^\s\"']*?/)?(?:\.staging/)?scripts/(?:win32_2pc_engine|nk_registry_indexer|healing_snapshot_rollback|ast_repo_mapper)\.py\b",
            norm,
            re.IGNORECASE,
        )
    )


def _log_shadow_decision(
    conv_id: str, subcommand: str, event: str, res: Dict[str, Any]
) -> None:
    """Registra in modalita shadow i potenziali blocchi o avvisi nel file shadow jsonl."""
    shadow_file = _get_hooks_temp_dir() / f"shadow_{conv_id}.jsonl"
    decision_val = res.get("decision") or ("warn" if res.get("ephemeralMessage") else "allow")
    record = {
        "timestamp": time.time(),
        "subcommand": subcommand,
        "event": event,
        "conversation_id": conv_id,
        "would_decide": decision_val,
        "decision": decision_val,
        "reason": res.get("reason") or res.get("ephemeralMessage") or "",
    }
    with open(shadow_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _handle_probe(conv_id: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Salva l'evento e le chiavi del payload stdin nel log jsonl della sonda."""
    probe_file = _get_hooks_temp_dir() / f"probe_{conv_id}.jsonl"
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    record = {
        "timestamp": time.time(),
        "event": event,
        "conversation_id": conv_id,
        "payload_keys": sorted(payload.keys()),
        "tool_name": payload.get("toolName") or tool_call.get("name") or "",
    }
    with open(probe_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {}


def _handle_integrity(
    conv_id: str, project_root: Path, init_mode: bool, check_mode: bool
) -> tuple[Dict[str, Any], int]:
    """Salva o verifica gli hash SHA-256 dei checkpoint e la sezione di PATCH_NOTES.md."""
    state_file = _get_hooks_temp_dir() / f"{conv_id}_integrity.json"
    root = _resolve_effective_hub_root(project_root)
    tracking_dir = root / "nk_tracking"
    checkpoints: Dict[str, str] = {}
    if tracking_dir.exists():
        for cp in sorted(tracking_dir.rglob("checkpoint_*.json")):
            if cp.is_file():
                rel = cp.relative_to(root).as_posix()
                checkpoints[rel] = _sha256_file(cp)

    patch_candidates = [root / "PATCH_NOTES.md", root / "nk_genome" / "PATCH_NOTES.md"]
    patch_info: Dict[str, Dict[str, str]] = {}
    for pc in patch_candidates:
        if pc.is_file():
            rel_p = pc.relative_to(root).as_posix()
            txt = pc.read_text(encoding="utf-8", errors="replace")
            patch_info[rel_p] = {
                "sha256": _sha256_file(pc),
                "first_section": _extract_first_section(txt),
            }

    oracle_lock_file = tracking_dir / "oracle_lock.json"
    if not oracle_lock_file.is_file() and (root / "oracle_lock.json").is_file():
        oracle_lock_file = root / "oracle_lock.json"
    oracle_lock_sha256 = (
        _sha256_file(oracle_lock_file)
        if oracle_lock_file.is_file()
        else hashlib.sha256(b"").hexdigest()
    )

    tests_map: Dict[str, str] = {}
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        for tf in sorted(tests_dir.rglob("*")):
            if (
                tf.is_file()
                and tf.suffix.lower() in (".py", ".json")
                and "__pycache__" not in tf.parts
            ):
                rel_tf = tf.relative_to(root).as_posix()
                tests_map[rel_tf] = _sha256_file(tf)
    tests_manifest_sha256 = hashlib.sha256(
        json.dumps(tests_map, sort_keys=True).encode("utf-8")
    ).hexdigest()

    telemetry_file = tracking_dir / "rsi_telemetry.jsonl"
    last_telemetry_line = ""
    if telemetry_file.is_file():
        try:
            with open(telemetry_file, "rb") as tf_bin:
                tf_bin.seek(0, os.SEEK_END)
                fsize = tf_bin.tell()
                tf_bin.seek(max(0, fsize - 4096), os.SEEK_SET)
                tail_txt = tf_bin.read().decode("utf-8", errors="replace")
            for ln in reversed(tail_txt.splitlines()):
                if ln.strip():
                    last_telemetry_line = ln.strip()
                    break
        except Exception:
            pass
    chain_anchor_sha256 = hashlib.sha256(
        f"{oracle_lock_sha256}|{tests_manifest_sha256}|{last_telemetry_line}".encode("utf-8")
    ).hexdigest()

    if init_mode or not check_mode:
        snap = {
            "root": root.as_posix(),
            "checkpoints": checkpoints,
            "patch_notes": patch_info,
            "oracle_lock_sha256": oracle_lock_sha256,
            "tests_manifest_sha256": tests_manifest_sha256,
            "chain_anchor_sha256": chain_anchor_sha256,
        }
        state_file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "status": "INITIALIZED",
            "passed": True,
            "checkpoints_count": len(checkpoints),
            "oracle_lock_sha256": oracle_lock_sha256,
            "tests_manifest_sha256": tests_manifest_sha256,
            "chain_anchor_sha256": chain_anchor_sha256,
        }, 0

    if not state_file.exists():
        return {"status": "UNINITIALIZED", "passed": False, "violations": ["Missing integrity snapshot"]}, 1

    try:
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return {
                "status": "CORRUPTED_SNAPSHOT",
                "passed": False,
                "violations": ["Corrupted integrity snapshot"],
            }, 1
    except Exception:
        return {
            "status": "CORRUPTED_SNAPSHOT",
            "passed": False,
            "violations": ["Corrupted integrity snapshot"],
        }, 1

    violations: List[str] = []
    for rel_cp, old_sha in saved.get("checkpoints", {}).items():
        cur_sha = checkpoints.get(rel_cp)
        if cur_sha is None:
            violations.append(f"Deleted historical checkpoint: {rel_cp}")
        elif cur_sha != old_sha:
            violations.append(f"Tampered historical checkpoint: {rel_cp}")

    for rel_pn, old_meta in saved.get("patch_notes", {}).items():
        pn_file = root / rel_pn
        if not pn_file.is_file():
            violations.append(f"Deleted PATCH_NOTES file: {rel_pn}")
            continue
        cur_txt = pn_file.read_text(encoding="utf-8", errors="replace")
        norm_cur = "\n".join(ln.strip() for ln in cur_txt.splitlines() if ln.strip())
        req_sec = old_meta.get("first_section", "")
        if req_sec and req_sec not in cur_txt and req_sec not in norm_cur:
            violations.append(f"Destructive overwrite of history in {rel_pn}")

    saved_oracle = saved.get("oracle_lock_sha256")
    if saved_oracle and saved_oracle != hashlib.sha256(b"").hexdigest():
        if oracle_lock_sha256 != saved_oracle:
            violations.append("Tampered or deleted oracle_lock.json")

    saved_tests = saved.get("tests_manifest_sha256")
    if saved_tests and saved_tests != hashlib.sha256(b"{}").hexdigest():
        if tests_manifest_sha256 != saved_tests:
            violations.append("Tampered tests/ manifest SHA-256")

    passed = len(violations) == 0
    return {
        "status": "VALID" if passed else "VIOLATION",
        "passed": passed,
        "violations": violations,
        "oracle_lock_sha256": oracle_lock_sha256,
        "tests_manifest_sha256": tests_manifest_sha256,
        "chain_anchor_sha256": chain_anchor_sha256,
    }, (0 if passed else 1)


def _classify_protected_target(
    target: str,
    cmd: str = "",
    project_root: Path = _WORKSPACE_ROOT,
    strict_external: bool = False,
) -> Dict[str, Any]:
    if not cmd and (" " in target or "-encodedcommand" in target.lower()):
        cmd = target
        target = ""
    """Classifica i target protetti (oracle_lock.json, scripts/, .agents/) e i comandi python -c multi-riga."""
    cmd_str = str(cmd or "")

    if ("\n" in cmd_str or "\r" in cmd_str) and re.search(
        r"\b(?:python(?:3)?|py)(?:\.exe)?\b[^\n\r]*\s-c\b", cmd_str, re.IGNORECASE
    ):
        return {
            "decision": "deny",
            "reason": "Multi-line python -c one-liner is forbidden ([RULE-01]); write a script in scratch/ or %TEMP%\\nk_diagnostics\\.",
        }

    if _ENCODED_CMD_RE.search(cmd_str):
        return {
            "decision": "deny",
            "reason": "Obfuscated PowerShell -EncodedCommand / -ec execution is forbidden in run_command.",
        }

    if _DESTRUCTIVE_GIT_RE.search(cmd_str):
        return {
            "decision": "deny",
            "reason": "Destructive git command (checkout/restore/reset --hard/clean -f) is forbidden.",
        }

    if target and target.strip():
        cand = _resolve_target_path(target, project_root)
        cand_parts_low = [p.lower() for p in cand.parts]
        cand_name_low = cand.name.lower()

        if _is_valid_staging_path(cand, project_root):
            return {}

        if cand_name_low == "oracle_lock.json":
            return {
                "decision": "deny",
                "reason": "Direct write to oracle_lock.json outside .staging/ is forbidden ([RULE-ORACLE-LOCK]).",
            }

        if any(p in ("scripts", ".agents") for p in cand_parts_low):
            return {
                "decision": "deny" if strict_external else "ask",
                "reason": "Direct write to scripts/ or .agents/ outside .staging/ is blocked; stage in .staging/ and promote via win32_2pc_engine.py.",
            }

    cmd_low = cmd_str.replace("\\", "/").lower()
    if cmd_low:
        if "nk_transcript_tools.py" in cmd_low and "oracle-lock" in cmd_low:
            if "verify" in cmd_low and not _has_cmd_write_indicator(cmd_low):
                return {}
            if ("freeze" in cmd_low or "create" in cmd_low) and strict_external:
                return {
                    "decision": "ask",
                    "reason": "Re-freezing oracle_lock.json requires explicit user approval ([RULE-ORACLE-LOCK]).",
                }
            if not _has_cmd_write_indicator(cmd_low):
                return {}

        sanitized_cmd = _sanitize_staged_tokens_in_cmd(cmd_low)
        has_write_ind = _has_cmd_write_indicator(cmd_low)

        if "oracle_lock.json" in sanitized_cmd and has_write_ind:
            return {
                "decision": "deny",
                "reason": "Direct write to oracle_lock.json outside .staging/ is forbidden ([RULE-ORACLE-LOCK]).",
            }

        if (
            not _is_authorized_script_invocation(cmd_str)
            and bool(_PROTECTED_DIR_CMD_RE.search(sanitized_cmd))
            and has_write_ind
        ):
            return {
                "decision": "deny" if strict_external else "ask",
                "reason": "Direct shell write to scripts/ or .agents/ outside .staging/ is blocked; stage in .staging/ and promote via win32_2pc_engine.py.",
            }

    return {}


def _handle_write_gate(
    payload: Dict[str, Any], project_root: Path, strict_external: bool, cli_target: str, cli_cmd: str, cli_content: str
) -> Dict[str, Any]:
    """Valuta la sicurezza delle scritture su file o dei comandi prima dell'esecuzione."""
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tool_name = str(
        payload.get("toolName")
        or payload.get("name")
        or tool_call.get("name")
        or ""
    ).strip()
    if tool_name in _READ_ONLY_TOOLS:
        return {}

    args = payload.get("args") or payload.get("arguments") or tool_call.get("args") or payload
    if not isinstance(args, dict):
        args = {}
    target = str(
        cli_target
        or args.get("TargetFile")
        or args.get("Path")
        or args.get("AbsolutePath")
        or args.get("NotebookPath")
        or args.get("file")
        or args.get("target")
        or ""
    )
    cmd = str(cli_cmd or args.get("CommandLine") or args.get("command") or "")
    chunks = args.get("ReplacementChunks") if isinstance(args.get("ReplacementChunks"), list) else []
    new_content = str(
        cli_content
        or args.get("Content")
        or args.get("CodeContent")
        or args.get("Replacement")
        or args.get("ReplacementContent")
        or args.get("new_string")
        or args.get("content")
        or ""
    )
    if not new_content and chunks:
        new_content = "\n".join(
            str(
                c.get("ReplacementContent")
                or c.get("Replacement")
                or c.get("new_string")
                or ""
            )
            for c in chunks
            if isinstance(c, dict)
        )

    cmd_low = cmd.replace("\\", "/").lower()
    hallucinated_res = pre_command_gate(cmd)
    if hallucinated_res:
        return hallucinated_res

    protected_res = _classify_protected_target(
        target, cmd, project_root, strict_external=strict_external
    )
    if protected_res:
        return protected_res

    if target.strip():
        cand = _resolve_target_path(target, project_root)
        cand_parts_low = [p.lower() for p in cand.parts]
        cand_name_low = cand.name.lower()

        if _is_valid_staging_path(cand, project_root):
            return {}

        if cand_name_low.startswith("checkpoint_") and cand_name_low.endswith(".json"):
            if cand.exists():
                return {"decision": "deny", "reason": "Cannot overwrite existing historical checkpoint_*.json (D-02)."}

        if cand_name_low == "patch_notes.md":
            if cand.exists():
                old_txt = cand.read_text(encoding="utf-8", errors="replace").strip()
                anchor = _extract_first_section(old_txt)
                old_headers = _extract_historical_headers(old_txt)
                if old_txt and anchor:
                    if chunks:
                        sim_txt = old_txt
                        for c in chunks:
                            if isinstance(c, dict):
                                t_c = str(
                                    c.get("TargetContent")
                                    or c.get("Target")
                                    or c.get("old_string")
                                    or ""
                                ).strip()
                                r_c = str(
                                    c.get("ReplacementContent")
                                    or c.get("Replacement")
                                    or c.get("new_string")
                                    or ""
                                )
                                if t_c and t_c in sim_txt:
                                    sim_txt = sim_txt.replace(t_c, r_c)
                                else:
                                    sim_txt = r_c
                    elif (
                        args.get("Target")
                        or args.get("TargetContent")
                        or args.get("old_string")
                    ):
                        tgt_s = str(
                            args.get("Target")
                            or args.get("TargetContent")
                            or args.get("old_string")
                            or ""
                        )
                        rep_raw = (
                            args.get("Replacement")
                            if "Replacement" in args
                            else (
                                args.get("ReplacementContent")
                                if "ReplacementContent" in args
                                else (
                                    args.get("new_string")
                                    if "new_string" in args
                                    else new_content
                                )
                            )
                        )
                        rep_s = str(rep_raw if rep_raw is not None else "")
                        sim_txt = old_txt.replace(tgt_s, rep_s) if (tgt_s and tgt_s in old_txt) else rep_s
                    else:
                        sim_txt = new_content

                    norm_sim = "\n".join(
                        ln.strip() for ln in str(sim_txt or "").splitlines() if ln.strip()
                    )
                    if (
                        not sim_txt
                        or (anchor not in sim_txt and anchor not in norm_sim)
                        or any(h not in sim_txt for h in old_headers)
                    ):
                        return {"decision": "deny", "reason": "PATCH_NOTES.md is prepend-only: preserve previous history."}
            return {}

        if any(p in ("nk_external_projects", "src_app", "tests") for p in cand_parts_low):
            return {
                "decision": "deny" if strict_external else "ask",
                "reason": "Direct write to src_app/ or tests/ outside .staging/ is blocked; stage and promote via win32_2pc_engine.py.",
            }

        if (
            any(p in _SAFE_DIR_COMPONENTS or p.startswith("nk_sandbox_") for p in cand_parts_low)
            or cand_name_low in _SAFE_ROOT_FILENAMES
        ):
            return {}

    if cmd_low:
        sanitized_cmd = _sanitize_staged_tokens_in_cmd(cmd_low)
        has_write_ind = _has_cmd_write_indicator(cmd_low)
        is_pure_pytest = ("pytest" in cmd_low) and not has_write_ind
        is_auth_script = _is_authorized_script_invocation(cmd)
        ext_cmd_unstage = (
            "nk_external_projects/" in sanitized_cmd
            and not is_auth_script
            and not is_pure_pytest
            and bool(_UNSTAGE_CODE_DIR_CMD_RE.search(sanitized_cmd))
        )
        local_cmd_unstage = (
            not is_auth_script
            and bool(_UNSTAGE_CODE_DIR_CMD_RE.search(sanitized_cmd))
            and has_write_ind
        )
        if ext_cmd_unstage or local_cmd_unstage:
            return {
                "decision": "deny" if strict_external else "ask",
                "reason": "Direct write to src_app/ or tests/ outside .staging/ is blocked; stage and promote via win32_2pc_engine.py.",
            }

    return {}


def _handle_fasttrack(conv_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Traccia le chiamate dirette consecutive e avvisa oltre la soglia di 12."""
    ft_file = _get_hooks_temp_dir() / f"fasttrack_{conv_id}.json"
    state = {"streak": 0}
    if ft_file.exists():
        try:
            state = json.loads(ft_file.read_text(encoding="utf-8"))
        except Exception:
            state = {"streak": 0}

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tname = str(payload.get("toolName") or payload.get("name") or tool_call.get("name") or "")
    if tname in _DELEGATION_TOOLS or payload.get("reset") is True:
        state["streak"] = 0
    else:
        state["streak"] = int(state.get("streak", 0)) + 1

    ft_file.write_text(json.dumps(state), encoding="utf-8")
    if state["streak"] > 12:
        return {
            "streak": state["streak"],
            "ephemeralMessage": f"[RULE-01] Fast-Track streak ({state['streak']} > 12). Delegate work via invoke_subagent.",
        }
    return {}


def _extract_last_planner_message(transcript_path: Path) -> str:
    """Estrae l'ultimo messaggio PLANNER_RESPONSE dal file transcript indicato."""
    last_msg = ""
    if not transcript_path.is_file():
        return last_msg
    for raw in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        src = str(rec.get("source") or rec.get("type") or rec.get("role") or "").upper()
        content = str(rec.get("content") or rec.get("message") or rec.get("response") or "")
        if src in ("PLANNER_RESPONSE", "ASSISTANT", "MODEL") and content.strip():
            last_msg = content
    return last_msg


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per il gate degli hook di Nexus Keystone."""
    os.environ["PYTHONUTF8"] = "1"
    parser = argparse.ArgumentParser(description="Nexus Keystone Fast Stdlib Hook Gate")
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="probe",
        choices=("probe", "session-start", "write-gate", "fasttrack", "stop-evidence", "integrity"),
    )
    parser.add_argument("--event", type=str, default="Unknown")
    parser.add_argument("--conversation-id", type=str, default=None)
    parser.add_argument("--project-root", type=str, default=None)
    parser.add_argument("--target", type=str, default="")
    parser.add_argument("--command", type=str, default="")
    parser.add_argument("--content", type=str, default="")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--strict-external", action="store_true")
    parser.add_argument("--native-contract", action="store_true")
    parser.add_argument("--shadow", action="store_true")
    parser.add_argument("--enforce-stop", action="store_true")
    args = parser.parse_args(argv)

    skip_stdin = args.subcommand == "integrity" or (
        args.event == "Unknown" and bool(args.target or args.command or args.init or args.check)
    )
    payload = {} if skip_stdin else _read_stdin_payload()
    conv_id = _resolve_conv_id(args.conversation_id, payload)
    proj_root = Path(args.project_root).resolve() if args.project_root else _WORKSPACE_ROOT
    if args.subcommand == "probe" or os.environ.get("NK_HOOK_DEBUG", "0").strip().lower() in ("1", "true", "yes"):
        _handle_probe(conv_id, args.event, payload)

    if args.subcommand == "probe":
        print("{}")
        return 0
    if args.subcommand == "session-start":
        _handle_integrity(conv_id, proj_root, init_mode=True, check_mode=False)
        if args.native_contract:
            msg_txt = (
                "[NK-HUB] Argon profile active. [RULE-00.6] Emit visible L0 "
                "Conceptual Mirror in content before ask_question (content_len > 0 mandatory)."
            )
            print(
                json.dumps(
                    {
                        "injectSteps": [
                            {
                                "ephemeralMessage": msg_txt,
                                "systemMessage": {"systemMessage": msg_txt},
                            }
                        ]
                    }
                )
            )
        else:
            print(json.dumps({"status": "OK", "profile": "argon", "pythonutf8": "1"}))
        return 0
    if args.subcommand == "write-gate":
        res = _handle_write_gate(payload, proj_root, args.strict_external, args.target, args.command, args.content)
        if args.shadow:
            if res.get("decision") in ("deny", "ask"):
                _log_shadow_decision(conv_id, "write-gate", args.event, res)
            out_wg = {"decision": "allow"} if args.native_contract else {}
            print(json.dumps(out_wg, ensure_ascii=False))
            return 0
        if args.native_contract and "decision" not in res:
            res = {"decision": "allow"}
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if args.subcommand == "fasttrack":
        if args.native_contract and args.event == "PreInvocation":
            ft_file = _get_hooks_temp_dir() / f"fasttrack_{conv_id}.json"
            streak_val = 0
            if ft_file.exists():
                try:
                    streak_val = int(json.loads(ft_file.read_text(encoding="utf-8")).get("streak", 0))
                except Exception:
                    streak_val = 0
            if streak_val > 12:
                warn_ft = f"[RULE-01] Fast-Track streak ({streak_val} > 12). Delegate work via invoke_subagent."
                if args.shadow:
                    _log_shadow_decision(conv_id, "fasttrack", args.event, {"ephemeralMessage": warn_ft})
                print(json.dumps({"injectSteps": [{"ephemeralMessage": warn_ft}]}, ensure_ascii=False))
            else:
                print("{}")
            return 0

        res = _handle_fasttrack(conv_id, payload)
        if args.native_contract and args.event == "PostToolUse":
            print("{}")
            return 0
        if args.native_contract and res.get("ephemeralMessage"):
            print(json.dumps({"injectSteps": [{"ephemeralMessage": res["ephemeralMessage"]}]}, ensure_ascii=False))
            return 0
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if args.subcommand == "integrity":
        res, code = _handle_integrity(conv_id, proj_root, args.init, args.check)
        print(json.dumps(res, ensure_ascii=False))
        return code
    if args.subcommand == "stop-evidence":
        msg = str(payload.get("content") or payload.get("message") or payload.get("response") or "")
        tp_raw = payload.get("transcriptPath") or payload.get("transcript_path")
        tp_path: Optional[Path] = Path(str(tp_raw)) if tp_raw and Path(str(tp_raw)).is_file() else None

        for p_cand in (_SCRIPT_DIR, _WORKSPACE_ROOT / "scripts"):
            if p_cand.exists() and str(p_cand) not in sys.path:
                sys.path.insert(0, str(p_cand))

        if "verifiedExitZero" in payload:
            verified_ok = bool(payload.get("verifiedExitZero"))
        else:
            verified_ok = True
            try:
                import nk_transcript_tools as _ntt

                if tp_path is None and conv_id != "unknown":
                    loc_res, loc_code = _ntt.locate_transcript(None, conv_id)
                    if loc_code == 0 and loc_res.get("transcript_path"):
                        cand_tp = Path(str(loc_res["transcript_path"]))
                        if cand_tp.is_file():
                            tp_path = cand_tp

                if tp_path is not None and tp_path.is_file():
                    if not msg:
                        msg = _extract_last_planner_message(tp_path)
                    ev_res, _ = _ntt.check_evidence(tp_path, msg)
                    verified_ok = bool(ev_res.get("passed", True))
            except Exception:
                verified_ok = True

        if tp_path is not None and tp_path.is_file() and not msg:
            msg = _extract_last_planner_message(tp_path)

        retry_file = _get_hooks_temp_dir() / f"stop_retry_{conv_id}.json"
        if _CERT_RE.search(msg) and not verified_ok:
            warn_ev = "[RULE-EVIDENCE] Unverified PASS/CONVERGED_OPTIMAL claim detected."
            if args.shadow:
                _log_shadow_decision(conv_id, "stop-evidence", args.event, {"ephemeralMessage": warn_ev})
            if args.enforce_stop and not args.shadow:
                msg_hash = hashlib.sha256(msg.encode("utf-8")).hexdigest()
                prev_hash = ""
                prev_count = 0
                if retry_file.exists():
                    try:
                        rdata = json.loads(retry_file.read_text(encoding="utf-8"))
                        if isinstance(rdata, dict):
                            prev_hash = str(
                                rdata.get("last_msg_sha256")
                                or rdata.get("msg_sha256")
                                or ""
                            )
                            prev_count = int(rdata.get("count", 0))
                    except Exception:
                        prev_hash = ""
                        prev_count = 0
                if prev_hash and prev_hash == msg_hash:
                    retry_file.write_text(
                        json.dumps(
                            {
                                "last_msg_sha256": msg_hash,
                                "msg_sha256": msg_hash,
                                "count": prev_count + 1,
                            }
                        ),
                        encoding="utf-8",
                    )
                    print(json.dumps({"decision": "allow"}))
                else:
                    retry_file.write_text(
                        json.dumps(
                            {
                                "last_msg_sha256": msg_hash,
                                "msg_sha256": msg_hash,
                                "count": 1,
                            }
                        ),
                        encoding="utf-8",
                    )
                    print(
                        json.dumps(
                            {
                                "decision": "continue",
                                "reason": warn_ev,
                                "ephemeralMessage": warn_ev,
                            }
                        )
                    )
            elif args.native_contract:
                print(json.dumps({"ephemeralMessage": warn_ev, "injectSteps": [{"ephemeralMessage": warn_ev}]}))
            else:
                print(json.dumps({"ephemeralMessage": warn_ev}))
        else:
            if retry_file.exists():
                try:
                    retry_file.unlink(missing_ok=True)
                except Exception:
                    pass
            print("{}")
        return 0
    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
