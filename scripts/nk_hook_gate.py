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
_DELEGATION_TOOLS = ("invoke_subagent", "define_subagent", "send_message")
_SAFE_MARKERS = (
    ".staging/",
    "/.staging/",
    "nk_genome/",
    "/genome/",
    "scratch/",
    "appdata/local/temp",
    "/temp/",
    "%temp%",
    "nk_hooks",
    "nk_sandbox_",
    "nk_diagnostics",
    "patch_notes.md",
    "readme",
)
_CERT_RE = re.compile(r"(\bCONVERGED_OPTIMAL\b|\b\d+/\d+\s+PASS\b)", re.IGNORECASE)


def _get_hooks_temp_dir() -> Path:
    """Restituisce e crea la directory temporanea per lo stato degli hook."""
    base = Path(os.environ.get("NK_HOOKS_TEMP_DIR") or tempfile.gettempdir()) / "nk_hooks"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _read_stdin_payload() -> Dict[str, Any]:
    """Legge eventuale JSON da stdin in modo sicuro senza bloccare su terminale."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
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
    root = project_root.resolve()
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

    if init_mode or not check_mode:
        snap = {"root": root.as_posix(), "checkpoints": checkpoints, "patch_notes": patch_info}
        state_file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": "INITIALIZED", "passed": True, "checkpoints_count": len(checkpoints)}, 0

    if not state_file.exists():
        return {"status": "UNINITIALIZED", "passed": False, "violations": ["Missing integrity snapshot"]}, 1

    saved = json.loads(state_file.read_text(encoding="utf-8"))
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
        req_sec = old_meta.get("first_section", "")
        if req_sec and req_sec not in cur_txt:
            violations.append(f"Destructive overwrite of history in {rel_pn}")

    passed = len(violations) == 0
    return {"status": "VALID" if passed else "VIOLATION", "passed": passed, "violations": violations}, (0 if passed else 1)


def _handle_write_gate(
    payload: Dict[str, Any], project_root: Path, strict_external: bool, cli_target: str, cli_cmd: str, cli_content: str
) -> Dict[str, Any]:
    """Valuta la sicurezza delle scritture su file o dei comandi prima dell'esecuzione."""
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    args = payload.get("args") or payload.get("arguments") or tool_call.get("args") or payload
    if not isinstance(args, dict):
        args = {}
    target = str(
        cli_target
        or args.get("TargetFile")
        or args.get("Path")
        or args.get("AbsolutePath")
        or args.get("file")
        or args.get("target")
        or ""
    )
    cmd = str(cli_cmd or args.get("CommandLine") or args.get("command") or "")
    new_content = str(cli_content or args.get("Content") or args.get("Replacement") or args.get("content") or "")
    norm_t = target.replace("\\", "/")
    norm_low = norm_t.lower()
    cmd_low = cmd.replace("\\", "/").lower()

    if any(m in norm_low for m in (".staging/", "/.staging/")):
        return {}

    if "checkpoint_" in norm_low and norm_low.endswith(".json"):
        cand = Path(target) if Path(target).is_absolute() else (project_root / target)
        if cand.exists():
            return {"decision": "deny", "reason": "Cannot overwrite existing historical checkpoint_*.json (D-02)."}

    if norm_low.endswith("patch_notes.md"):
        cand_pn = Path(target) if Path(target).is_absolute() else (project_root / target)
        if cand_pn.exists():
            old_txt = cand_pn.read_text(encoding="utf-8", errors="replace").strip()
            anchor = _extract_first_section(old_txt)
            if old_txt and (not new_content or (anchor and anchor not in new_content)):
                return {"decision": "deny", "reason": "PATCH_NOTES.md is prepend-only: preserve previous history."}

    if any(m in norm_low for m in _SAFE_MARKERS):
        return {}

    ext_unstage = (
        ("nk_external_projects/" in norm_low or "/src_app/" in norm_low or norm_low.startswith("src_app/") or "/tests/" in norm_low or norm_low.startswith("tests/"))
        and ".staging/" not in norm_low
    ) or (
        "nk_external_projects/" in cmd_low
        and ".staging" not in cmd_low
        and "win32_2pc_engine.py" not in cmd_low
        and any(w in cmd_low for w in ("src_app/", "tests/", "checkpoint_", "patch_notes.md"))
    )
    if ext_unstage:
        return {
            "decision": "deny" if strict_external else "ask",
            "reason": "Direct write to src_app/ or tests/ outside .staging/ is blocked; stage and promote via win32_2pc_engine.py.",
        }

    if "nk_tracking/" in norm_low:
        return {}
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
    args = parser.parse_args(argv)

    payload = _read_stdin_payload()
    conv_id = _resolve_conv_id(args.conversation_id, payload)
    proj_root = Path(args.project_root).resolve() if args.project_root else _WORKSPACE_ROOT
    _handle_probe(conv_id, args.event, payload)

    if args.subcommand == "probe":
        print("{}")
        return 0
    if args.subcommand == "session-start":
        os.environ["NK_MODEL_PROFILE"] = "argon"
        _handle_integrity(conv_id, proj_root, init_mode=True, check_mode=False)
        print(json.dumps({"status": "OK", "profile": "argon", "pythonutf8": "1"}))
        return 0
    if args.subcommand == "write-gate":
        res = _handle_write_gate(payload, proj_root, args.strict_external, args.target, args.command, args.content)
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if args.subcommand == "fasttrack":
        res = _handle_fasttrack(conv_id, payload)
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if args.subcommand == "integrity":
        res, code = _handle_integrity(conv_id, proj_root, args.init, args.check)
        print(json.dumps(res, ensure_ascii=False))
        return code
    if args.subcommand == "stop-evidence":
        msg = str(payload.get("content") or payload.get("message") or payload.get("response") or "")
        if _CERT_RE.search(msg) and not payload.get("verifiedExitZero", True):
            print(json.dumps({"ephemeralMessage": "[RULE-EVIDENCE] Unverified PASS/CONVERGED_OPTIMAL claim detected."}))
        else:
            print("{}")
        return 0
    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
