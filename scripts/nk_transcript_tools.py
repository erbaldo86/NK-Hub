#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strumenti forensi per transcript, oracle-lock SHA-256 e linting prompt di Nexus Keystone v6.0.0.
Modulo: scripts/nk_transcript_tools.py.
@domain_id: DOM-04
Implementa i sottocomandi locate, compliance, evidence, oracle-lock, report-conflict e lint-prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_DIRECT_TOOLS = (
    "view_file",
    "read_file",
    "run_command",
    "replace_file_content",
    "write_to_file",
    "write_file",
    "edit_file",
    "grep_search",
    "find_by_name",
)
_DELEGATION_TOOLS = ("invoke_subagent", "define_subagent", "send_message")
_SAFE_WRITE_MARKERS = (
    ".staging/",
    "/.staging/",
    "nk_genome/",
    "nk_tracking/",
    "scratch/",
    "appdata/local/temp",
    "/temp/",
    "%temp%",
    "brain/",
    "patch_notes.md",
    "readme",
)
_READONLY_CMD_MARKERS = (
    "pytest",
    "rsi_convergence_engine.py",
    "ast_guard_validator.py",
    "nk_session_bootstrap.py",
    "dast_sandbox_runner.py",
    "compliance",
    "evidence",
    "oracle-lock verify",
    "oracle-lock",
    "--verify",
    "win32_2pc_engine.py",
)
_WRITE_CMD_RE = re.compile(
    r"(\bset-content\b|\bout-file\b|\badd-content\b|\bcopy-item\b|\bmove-item\b"
    r"|\bnew-item\b|\bremove-item\b|--promote-staging|>>|(?<![-\w])>(?![>=]))",
    re.IGNORECASE,
)
_CLAIM_RE = re.compile(
    r"(\bCONVERGED_OPTIMAL\b|\b\d+/\d+\s+PASS\b|\b100(?:\.0)?%\s+PASS\b)",
    re.IGNORECASE,
)
_EXIT_ZERO_RE = re.compile(
    r"(exited with code\s+0\b|\"exit_code\"\s*:\s*0\b|\"returncode\"\s*:\s*0\b)",
    re.IGNORECASE,
)
_PASS_FALSE_RE = re.compile(
    r"(\"pass\"\s*:\s*false\b|\bpass\s*:\s*false\b)", re.IGNORECASE
)
_PASS_TRUE_RE = re.compile(
    r"(\"pass\"\s*:\s*true\b|\bpass\s*:\s*true\b)", re.IGNORECASE
)
_SCRIPT_RE = re.compile(r"([a-zA-Z0-9_]+\.py)\b")
_PHASE_RE = re.compile(r"\b(?:FASE|PHASE|MACRO-FASE)\s*\d+\b", re.IGNORECASE)


def _prefer_full_transcript(path: Path) -> Path:
    """Restituisce transcript_full.jsonl se presente accanto a transcript.jsonl."""
    if path.name == "transcript.jsonl":
        full_cand = path.parent / "transcript_full.jsonl"
        if full_cand.is_file():
            return full_cand.resolve()
    return path.resolve()


def locate_transcript(
    transcript_arg: Optional[str] = None,
    conversation_id: Optional[str] = None,
    brain_dir: Optional[Path] = None,
) -> Tuple[Dict[str, Any], int]:
    """Risolve il percorso del transcript senza fallback cieco su st_mtime."""
    if transcript_arg:
        p = Path(transcript_arg).resolve()
        if p.is_file():
            best_p = _prefer_full_transcript(p)
            return {"status": "LOCATED", "passed": True, "transcript_path": best_p.as_posix()}, 0
        return {"status": "UNMEASURED", "passed": False, "error": f"Transcript not found: {p}"}, 2

    if conversation_id:
        base = (
            Path(brain_dir).resolve()
            if brain_dir
            else Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "brain"
        )
        for rel in (
            f"{conversation_id}/.system_generated/logs/transcript_full.jsonl",
            f"{conversation_id}/.system_generated/logs/transcript.jsonl",
            f"{conversation_id}/transcript_full.jsonl",
            f"{conversation_id}/transcript.jsonl",
        ):
            cand = base / rel
            if cand.is_file():
                return {"status": "LOCATED", "passed": True, "transcript_path": cand.resolve().as_posix()}, 0
        return {"status": "UNMEASURED", "passed": False, "error": f"No transcript for conversation_id={conversation_id}"}, 2

    return {"status": "UNMEASURED", "passed": False, "error": "Explicit --transcript or --conversation-id required (no st_mtime fallback)."}, 2


def analyze_compliance(transcript_path: Path) -> Dict[str, Any]:
    """Analizza un transcript.jsonl calcolando streak dirette, scritture non staged e metriche forensi."""
    if not transcript_path.is_file():
        return {"passed": False, "error": f"Missing transcript: {transcript_path}"}

    effective_path = _prefer_full_transcript(transcript_path)
    max_streak = 0
    cur_streak = 0
    delegations = 0
    ext_writes = 0
    polling_list_calls = 0
    oversized_swarm_messages = 0
    prev_was_poll = False
    scripts_seen: List[str] = []
    last_model_text = ""

    for raw in effective_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        src = str(rec.get("source") or rec.get("type") or "").upper()
        rec_type = str(rec.get("type") or "").upper()
        is_turn_boundary = ("USER" in src) or (rec_type == "SYSTEM_MESSAGE") or ("SYSTEM_MESSAGE" in src)
        content = str(rec.get("content") or rec.get("output") or "")
        if src in ("MODEL", "ASSISTANT", "PLANNER_RESPONSE") and content.strip():
            last_model_text = content

        if is_turn_boundary:
            prev_was_poll = False

        calls = rec.get("tool_calls") or []
        step_delegated = False
        step_direct = 0
        for call in calls:
            tname = str(call.get("name") or call.get("toolName") or call.get("tool_name") or "")
            args = call.get("args") or call.get("arguments") or {}
            act_val = str(args.get("Action") or args.get("action") or "").strip().lower()
            is_poll_call = (tname == "manage_subagents" and act_val == "list") or (
                tname == "manage_task" and act_val == "status"
            )
            if is_poll_call:
                if prev_was_poll:
                    polling_list_calls += 1
                prev_was_poll = True
            elif tname:
                prev_was_poll = False

            if tname == "send_message":
                msg_body = str(args.get("Message") or args.get("message") or args.get("content") or "")
                if len(msg_body) > 1800:
                    oversized_swarm_messages += 1

            if tname in _DELEGATION_TOOLS:
                step_delegated = True
                if tname == "invoke_subagent":
                    delegations += 1
            elif tname in _DIRECT_TOOLS:
                step_direct += 1

            if tname in ("write_to_file", "write_file", "replace_file_content", "edit_file"):
                tf = str(args.get("TargetFile") or args.get("Path") or args.get("file") or "").replace("\\", "/").lower()
                if tf and not any(m in tf for m in _SAFE_WRITE_MARKERS):
                    ext_writes += 1
            elif tname == "run_command":
                cmd = str(args.get("CommandLine") or args.get("command") or "")
                for sm in _SCRIPT_RE.findall(cmd):
                    if sm not in scripts_seen:
                        scripts_seen.append(sm)
                cmd_low = cmd.replace("\\", "/").lower()
                if "nk_external_projects/" in cmd_low and ".staging" not in cmd_low:
                    if not any(ro in cmd_low for ro in _READONLY_CMD_MARKERS):
                        if _WRITE_CMD_RE.search(cmd) and not any(
                            sm in cmd_low for sm in ("patch_notes.md", "readme")
                        ):
                            ext_writes += 1

        if step_delegated or is_turn_boundary:
            cur_streak = 0
        elif step_direct > 0:
            cur_streak += step_direct
            if cur_streak > max_streak:
                max_streak = cur_streak

    clean_final = re.sub(r"```.*?```", " ", last_model_text, flags=re.DOTALL)
    sentences = [s.strip() for s in re.split(r"[.!?]+(?:\s+|$)", clean_final) if s.strip()]
    long_sentences = sum(1 for s in sentences if len(re.findall(r"\b\w+\b", s)) > 20)

    return {
        "passed": max_streak <= 12 and ext_writes == 0 and oversized_swarm_messages == 0,
        "max_consecutive_direct_tools": max_streak,
        "subagent_delegations": delegations,
        "external_writes_outside_staging": ext_writes,
        "polling_list_calls": polling_list_calls,
        "oversized_swarm_messages": oversized_swarm_messages,
        "nk_scripts_invoked": scripts_seen,
        "unverified_final_sentences_over_20_words": long_sentences,
    }


def check_evidence(transcript_path: Optional[Path] = None, message: str = "") -> Tuple[Dict[str, Any], int]:
    """Verifica che le certificazioni PASS o CONVERGED_OPTIMAL abbiano exit code 0 dopo l'ultimo input utente."""
    records: List[Dict[str, Any]] = []
    if transcript_path and transcript_path.is_file():
        effective_path = _prefer_full_transcript(transcript_path)
        for ln in effective_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.strip():
                try:
                    records.append(json.loads(ln))
                except Exception:
                    pass

    last_user_idx = -1
    for idx, rec in enumerate(records):
        src = str(rec.get("source") or rec.get("type") or "").upper()
        rec_type = str(rec.get("type") or "").upper()
        if "USER" in src or rec_type == "SYSTEM_MESSAGE" or "SYSTEM_MESSAGE" in src:
            last_user_idx = idx

    turn_records = records[last_user_idx + 1 :] if last_user_idx >= 0 else records
    verified_exit_zero = False
    unresolved_pass_false = False
    final_msg = message
    for rec in turn_records:
        txt = str(rec.get("content") or rec.get("output") or json.dumps(rec))
        if _EXIT_ZERO_RE.search(txt):
            verified_exit_zero = True
        if _PASS_FALSE_RE.search(txt):
            unresolved_pass_false = True
        if _PASS_TRUE_RE.search(txt):
            unresolved_pass_false = False
        if not message and str(rec.get("source") or rec.get("type") or "").upper() in ("MODEL", "ASSISTANT", "PLANNER_RESPONSE"):
            if rec.get("content"):
                final_msg = str(rec.get("content"))

    claims = [m.group(0) for m in _CLAIM_RE.finditer(final_msg or "")]
    passed = (not claims) or (verified_exit_zero and not unresolved_pass_false)
    return {
        "passed": passed,
        "claims_detected": claims,
        "verified_exit_zero": verified_exit_zero,
        "unresolved_pass_false": unresolved_pass_false,
    }, (0 if passed else 1)


def _hash_target_files(target: Path) -> Dict[str, str]:
    """Calcola la mappa percorso_relativo -> sha256 per un file o una directory."""
    resolved = target.resolve()
    if resolved.is_file():
        return {resolved.name: hashlib.sha256(resolved.read_bytes()).hexdigest()}
    files_map: Dict[str, str] = {}
    if resolved.is_dir():
        for f in sorted(resolved.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                rel = f.relative_to(resolved).as_posix()
                files_map[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return files_map


def handle_oracle_lock(action: str, target: Path, lock_file: Path) -> Tuple[Dict[str, Any], int]:
    """Crea o verifica il manifesto SHA-256 della ground truth e dei test."""
    current_map = _hash_target_files(target)
    if not current_map:
        return {"status": "ERROR", "passed": False, "error": f"Empty or missing target: {target}"}, 1

    combined = hashlib.sha256(json.dumps(current_map, sort_keys=True).encode("utf-8")).hexdigest()
    if action in ("create", "freeze"):
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"target": target.resolve().as_posix(), "files": current_map, "combined_sha256": combined}
        lock_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": "LOCKED", "passed": True, "files_count": len(current_map), "combined_sha256": combined}, 0

    if not lock_file.is_file():
        return {"status": "FAIL: oracle_lock missing", "passed": False, "mismatches": ["Lock file not found"]}, 1

    saved = json.loads(lock_file.read_text(encoding="utf-8"))
    saved_files = saved.get("files", {})
    mismatches: List[str] = []
    for rel, old_sha in saved_files.items():
        cur_sha = current_map.get(rel)
        if cur_sha is None:
            mismatches.append(f"deleted:{rel}")
        elif cur_sha != old_sha:
            mismatches.append(f"modified:{rel}")
    for rel in current_map:
        if rel not in saved_files:
            mismatches.append(f"added:{rel}")

    if mismatches or combined != saved.get("combined_sha256"):
        return {"status": "FAIL: oracle_lock mismatch", "passed": False, "mismatches": mismatches}, 1
    return {"status": "VERIFIED", "passed": True, "mismatches": []}, 0


def handle_report_conflict(
    root: Optional[Path] = None,
    test_a: str = "",
    test_b: str = "",
    reason: str = "",
    output: Optional[Path] = None,
) -> Tuple[Dict[str, Any], int]:
    """Genera epistemic_conflict_report.json e ferma il ciclo con HALT_EPISTEMIC_CONFLICT."""
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


def lint_prompt_text(prompt_text: str) -> Tuple[Dict[str, Any], int]:
    """Verifica gli anti-pattern AP-1..AP-9 e AP-2b su un prompt generato."""
    txt = prompt_text or ""
    low = txt.lower()
    phases = _PHASE_RE.findall(txt)
    violations: List[Dict[str, str]] = []

    if "!diretto" in low and (len(txt) > 1500 or len(phases) >= 2):
        violations.append({"code": "AP-1", "message": "!diretto forbidden on prompts >1500 chars or >=2 phases."})

    has_ctrl = any(k in low for k in ("session-controller", "controller"))
    has_eval = any(k in low for k in ("oracle-evaluator", "security-auditor", "auditor", "evaluator"))
    has_write_intent = any(k in low for k in ("src_app", "implementa", "modifica", "scrivi", "aggiorna", "build", "codice"))
    if (has_ctrl and has_eval and has_write_intent and "define_subagent" not in low) or (
        len(txt) > 1500 and "invoke_subagent" not in low and "define_subagent" not in low
    ):
        violations.append({"code": "AP-2", "message": "Incompatible role fusion or missing subagent delegation on large prompt."})

    if has_write_intent and (len(phases) >= 2 or "nk-builder-agent" in low or "builder" in low):
        if not (("define_subagent" in low and ("enablewritetools" in low or "enable_write_tools" in low)) or '"self"' in low or "'self'" in low):
            violations.append({"code": "AP-2b", "message": "Missing define_subagent(..., EnableWriteTools=True) or self for Builder (G3-01)."})

    if any(p in low for p in ("src_app/", "src_app\\", "tests/", "tests\\")) and has_write_intent:
        if ".staging" not in low or "win32_2pc_engine.py" not in low:
            violations.append({"code": "AP-3", "message": "Writes to src_app/ or tests/ without .staging/ and win32_2pc_engine.py."})

    if re.search(r"(finché|finche|until)[^\n]{0,120}100(?:\.0)?%\s*pass", low) and "oracle-lock" not in low and "oracle_lock" not in low:
        violations.append({"code": "AP-4", "message": "Goodhart loop ('until 100% PASS') in same turn without oracle-lock."})

    if "rsi_convergence_engine.py" in low and "--verify" in low and "nk_external_projects" in low and "--root" not in low:
        violations.append({"code": "AP-5", "message": "rsi_convergence_engine.py --verify missing --root on external project."})

    if len(phases) >= 3 and "stop_gate" not in low and "oracle-lock" not in low and "oracle_lock" not in low:
        violations.append({"code": "AP-6", "message": ">=3 macro-phases in single turn without STOP_GATE or oracle-lock."})

    if "search_web" in low and "tavily" in low:
        high_q = any(int(n) > 10 for n in re.findall(r"\b(\d+)\s*(?:query|queries|ricerche|fonti|portali)\b", low))
        if (high_q or "15-20" in low or "30 " in low) and "research" not in low:
            violations.append({"code": "AP-7", "message": "Simultaneous search_web + tavily >10 queries without research subagent sharding."})

    has_builder_role = any(b in low for b in ("nk-builder-agent", "nk-triad-rsi-builder", "builder"))
    has_holdout_secret = any(h in low for h in ("holdout set b", "battery_b_holdout", "holdout_set_b"))
    if has_builder_role and has_holdout_secret:
        violations.append({"code": "AP-8", "message": "Holdout Set B secret test cases leaked to Builder prompt."})

    if "<env_capsule>" in low and "!diretto" not in low and "invoke_subagent" not in low:
        has_user_spoof_markers = (
            any(m in low for m in ("opera come nk-session-controller", "opera come nk-master-hub", "prompt utente iniziale", "user prompt:"))
            or (len(phases) >= 2 and not any(w in low for w in ("builder shard", "sub-agente", "subagent", "worker")))
        )
        if has_user_spoof_markers:
            violations.append({"code": "AP-9", "message": "Improper <env_capsule> in initial user prompt without !diretto or invoke_subagent."})

    passed = len(violations) == 0
    return {"passed": passed, "violations_count": len(violations), "violations": violations}, (0 if passed else 1)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per gli strumenti transcript e prompt linter."""
    parser = argparse.ArgumentParser(description="Nexus Keystone Transcript & Prompt Tools")
    parser.add_argument(
        "subcommand",
        choices=("locate", "compliance", "evidence", "oracle-lock", "lint-prompt", "report-conflict"),
    )
    parser.add_argument("action", nargs="?", default="")
    parser.add_argument("--transcript", type=str, default=None)
    parser.add_argument("--conversation-id", type=str, default=None)
    parser.add_argument("--brain-dir", type=str, default=None)
    parser.add_argument("--message", type=str, default="")
    parser.add_argument("--root", type=str, default="")
    parser.add_argument("--target", type=str, default="")
    parser.add_argument("--lock-file", type=str, default="")
    parser.add_argument("--test-a", type=str, default="")
    parser.add_argument("--test-b", type=str, default="")
    parser.add_argument("--reason", type=str, default="")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--file", type=str, default=None)
    parser.add_argument("--text", type=str, default=None)
    args = parser.parse_args(argv)

    brain_p = Path(args.brain_dir) if args.brain_dir else None

    if args.subcommand == "locate":
        res, code = locate_transcript(args.transcript, args.conversation_id, brain_p)
    elif args.subcommand == "compliance":
        tr_path_str = args.transcript
        if not tr_path_str and args.conversation_id:
            loc_res, loc_code = locate_transcript(None, args.conversation_id, brain_p)
            if loc_code != 0:
                print(json.dumps(loc_res, indent=2, ensure_ascii=False))
                return loc_code
            tr_path_str = str(loc_res.get("transcript_path", ""))
        res = analyze_compliance(Path(tr_path_str or ""))
        code = 0 if res.get("passed") else 1
    elif args.subcommand == "evidence":
        tr_path_str = args.transcript
        if not tr_path_str and args.conversation_id:
            loc_res, loc_code = locate_transcript(None, args.conversation_id, brain_p)
            if loc_code != 0 and not args.message:
                print(json.dumps(loc_res, indent=2, ensure_ascii=False))
                return loc_code
            tr_path_str = str(loc_res.get("transcript_path", "")) if loc_code == 0 else None
        res, code = check_evidence(Path(tr_path_str) if tr_path_str else None, args.message)
    elif args.subcommand == "oracle-lock":
        act = args.action if args.action in ("create", "freeze", "verify") else "verify"
        target_p = Path(args.target) if args.target else (Path(args.root) / "tests" if args.root else Path("tests"))
        lock_p = (
            Path(args.lock_file)
            if args.lock_file
            else (Path(args.root) / "nk_tracking" / "oracle_lock.json" if args.root else Path("nk_tracking/oracle_lock.json"))
        )
        res, code = handle_oracle_lock(act, target_p, lock_p)
    elif args.subcommand == "report-conflict":
        res, code = handle_report_conflict(
            root=Path(args.root) if args.root else None,
            test_a=args.test_a,
            test_b=args.test_b,
            reason=args.reason,
            output=Path(args.output) if args.output else None,
        )
    else:
        txt = args.text or (Path(args.file).read_text(encoding="utf-8", errors="replace") if args.file else "")
        res, code = lint_prompt_text(txt)

    print(json.dumps(res, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
