# -*- coding: utf-8 -*-
"""Punto di ingresso CLI per nk_session_handoff."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_session_handoff.constants import (
    HANDOFF_VERSION,
    _discover_default_transcript,
    _resolve_git_executable,
    _workspace_root,
    resolve_session_tracking_dir,
)
from _internal.nk_session_handoff.context_view import generate_active_context_view
from _internal.nk_session_handoff.ecosystem_scanner import resolve_hub_and_project_roots
from _internal.nk_session_handoff.handoff_engine import (
    build_handoff_manifest_v1,
    record_fsm_checkpoint,
    record_idle_checkpoint_anchor,
    resume_from_anchor,
    serialize_handoff_v2,
)
from _internal.nk_session_handoff.session_state import (
    SESSION_RETENTION_LIMIT,
    Win32NamedMutex,
    _atomic_commit_bytes,
    _check_git_dirty_fast,
    _compute_staging_state_sha256,
    _compute_workspace_state_sha256,
    _has_dirty_staging_inprocess,
    _parse_optional_turn,
    _read_baseline_pass_rate,
    _read_baseline_tests_count,
    get_handoff_state_mutex_name,
    prune_session_tracking_dirs,
    select_auto_checkpoint_template,
)
from _internal.nk_session_handoff.templates_compiler import (
    compile_template_11_prompt,
    compile_template_12_state_handoff,
    persist_intent_brief,
)
from _internal.nk_session_handoff.transcript_cursor import _inspect_transcript_fast

try:
    from nk_transcript_tools import lint_prompt_text, locate_transcript
except ImportError:
    from scripts.nk_transcript_tools import lint_prompt_text, locate_transcript  # type: ignore[no-redef]

try:
    from win32_2pc_engine import Win32LockError, Win32LockTimeoutError, get_repo_batch_mutex_name
except ImportError:
    from scripts.win32_2pc_engine import (  # type: ignore[no-redef]
        Win32LockError,
        Win32LockTimeoutError,
        get_repo_batch_mutex_name,
    )

_FACADES = ("nk_session_handoff", "scripts.nk_session_handoff")


def _persist_auto_checkpoint_locked(
    args: argparse.Namespace, effective_root: Path, effective_milestone: str,
    shared_state_sha256: Optional[str], staging_state_sha256: Optional[str],
    eff_cid: Optional[str], fsm_cp_turn: Optional[int], latest_file: Path,
    prompt_file: Path, active_ctx_path: Path, sess_dir: Optional[Path],
    metadata: Dict[str, Any], compiled_prompt: Optional[str],
) -> int:
    repo_hash16 = hashlib.sha256(os.path.realpath(str(effective_root)).lower().replace("/", "\\").rstrip("\\").encode("utf-8")).hexdigest()[:16]
    mutex_cls = resolve_facade_attr(_FACADES, "Win32NamedMutex", Win32NamedMutex)
    try:
        with ExitStack() as stack:
            stack.enter_context(mutex_cls(f"Global\\NK_HandoffWorker_{repo_hash16}", timeout_ms=0, is_path=False))
            stack.enter_context(mutex_cls(get_repo_batch_mutex_name(effective_root.resolve()), timeout_ms=2000, is_path=False))
            stack.enter_context(mutex_cls(get_handoff_state_mutex_name(effective_root.resolve()), timeout_ms=2000, is_path=False))
            gate_st = str(args.gate_status or "PASS")
            anchor_res = (
                record_fsm_checkpoint(turn=fsm_cp_turn, gate_status=gate_st, milestone_id=effective_milestone, root=effective_root, state_sha256_override=shared_state_sha256, staging_state_sha256=staging_state_sha256, conversation_id=eff_cid)
                if fsm_cp_turn is not None
                else record_idle_checkpoint_anchor(gate_status=gate_st, milestone_id=effective_milestone, root=effective_root, state_sha256_override=shared_state_sha256, staging_state_sha256=staging_state_sha256, conversation_id=eff_cid, handoff_template=metadata["handoff_template"])
            )
            _write_dual_files(effective_root, latest_file, sess_dir, "session_handoff_latest.json", json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"))
            ctx_res = generate_active_context_view(root=effective_root, profile=str(args.profile or "generation"), dry_run=False, conversation_id=eff_cid, state_sha256_override=shared_state_sha256)
            if compiled_prompt is not None:
                _write_dual_files(effective_root, prompt_file, sess_dir, "next_session_prompt.md", compiled_prompt.encode("utf-8"))
    except (Win32LockTimeoutError, Win32LockError) as lock_exc:
        print(json.dumps({"status": "SKIPPED_LOCK_BUSY", "passed": True, "skipped": True, "reason": str(lock_exc), "project_root": str(effective_root)}, indent=2, ensure_ascii=False))
        return 0
    cp_receipt: Dict[str, Any] = {
        "status": "CHECKPOINT_SAVED", "passed": bool(ctx_res.get("passed", True)), "project_root": str(effective_root),
        "handoff_template": metadata["handoff_template"], "latest_path": str(latest_file), "prompt_path": str(prompt_file),
        "active_context_path": str(ctx_res.get("output_path", active_ctx_path)), "anchor_recorded": anchor_res is not None, "metadata": metadata,
    }
    print(json.dumps(cp_receipt, indent=2, ensure_ascii=False))
    return 0 if cp_receipt["passed"] else 1


def _normalize_cli_conv_id(raw_cid: Optional[str]) -> Optional[str]:
    """Normalizza conversation_id CLI scartando valori vuoti o 'auto'."""
    clean = str(raw_cid or "").strip()
    if not clean or clean.lower() == "auto":
        return None
    return clean


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NK Hub Generation Session Handoff & Template 11/12 Prompt Compiler 1.0.0-Generation")
    parser.add_argument("--transcript", required=False, default=None, help="Percorso al file transcript.jsonl")
    parser.add_argument("--output-dir", required=False, default=None, help="Directory di destinazione handoff")
    parser.add_argument("--project-root", required=False, default=None, help="Percorso radice del progetto")
    parser.add_argument("--generate-prompt", action="store_true", help="Genera next_session_prompt.md (Template 12)")
    parser.add_argument("--compile-handoff-prompt", action="store_true", help="Genera Template 12")
    parser.add_argument("--compile-state-handoff", action="store_true", help="Alias Template 12")
    parser.add_argument("--compile-template-11", action="store_true", help="Genera Template 11")
    parser.add_argument("--compile-task-prompt", action="store_true", help="Compila Template 11")
    parser.add_argument("--persist-brief-id", required=False, default=None, help="ID dell'Intent Brief")
    parser.add_argument("--prompt-text", required=False, default="", help="Testo dell'Intent Brief")
    parser.add_argument("--root", required=False, default=None, help="Percorso radice workspace")
    parser.add_argument("--checkpoint-turn", type=int, required=False, default=None, help="Turno FSM (1..5)")
    parser.add_argument("--gate-status", type=str, required=False, default="PASS", help="Stato del gate FSM")
    parser.add_argument("--milestone-id", type=str, required=False, default="", help="Milestone Anchor ID")
    parser.add_argument("--resume-from-anchor", action="store_true", help="Ripristina ultimo checkpoint FSM")
    parser.add_argument("--generate-active-context", action="store_true", help="Genera active_context.md")
    parser.add_argument("--profile", type=str, required=False, default="generation", help="Profilo budget token")
    parser.add_argument("--git-stash", action="store_true", help="Controlla git diff generando stash_patch")
    parser.add_argument("--auto-checkpoint", action="store_true", help="Esegue checkpoint atomico unificato")
    parser.add_argument("--serialize", action="store_true", help="Serializza envelope HANDOFF_V2 deterministico")
    parser.add_argument("--ecosystem-scan", action="store_true", help="Include NK_Hub e NK_External_Projects/*")
    parser.add_argument("--mode", choices=("PASSIVE_STANDBY", "ACTIVE_CONTINUATION"), default="PASSIVE_STANDBY", help="Modalita handoff v2")
    parser.add_argument("--target-repos", type=str, required=False, default=None, help="Repository target separati da virgola")
    parser.add_argument("--json", action="store_true", help="Stampa output JSON strutturato")
    parser.add_argument("--dry-run", action="store_true", help="Simula senza scrivere su disco")
    parser.add_argument("--conversation-id", type=str, required=False, default=None, help="ID conversazione")
    parser.add_argument("--turn", type=str, required=False, default=None, help="Turno FSM corrente (0..5)")
    return parser


def _write_dual_files(
    effective_root: Path, dst_file: Path, sess_dir: Optional[Path], sess_name: str, payload: bytes
) -> None:
    """Scrive atomicamente un artefatto handoff sia globale sia nella directory di sessione."""
    _atomic_commit_bytes(effective_root, dst_file, payload)
    if sess_dir is not None:
        _atomic_commit_bytes(effective_root, (sess_dir / sess_name).resolve(), payload)
        prune_session_tracking_dirs(effective_root, active_conversation_id=sess_dir.name, max_sessions=SESSION_RETENTION_LIMIT)


def _resolve_transcript_arg(args: argparse.Namespace) -> Optional[str]:
    loc_fn = resolve_facade_attr(_FACADES, "locate_transcript", locate_transcript)
    tp = args.transcript
    cid = _normalize_cli_conv_id(getattr(args, "conversation_id", None))
    if not tp and cid:
        try:
            loc_data, _ = loc_fn(conversation_id=cid)
            tp = str(loc_data.get("transcript_path") or "") or None
        except Exception:
            tp = None
    if not tp and not cid:
        tp = _discover_default_transcript()
    return tp


def _run_serialize_mode(args: argparse.Namespace, hub_root: Path, project_root: Path) -> int:
    is_dry_run = bool(args.dry_run)
    cid = _normalize_cli_conv_id(getattr(args, "conversation_id", None))
    try:
        cli_turn = _parse_optional_turn(getattr(args, "turn", None))
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "passed": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    cli_ms = (getattr(args, "milestone_id", "") or "").strip() or None
    tp = _resolve_transcript_arg(args)
    target_repos = [r.strip() for r in args.target_repos.split(",") if r.strip()] if args.target_repos else None
    if args.persist_brief_id and not is_dry_run and args.prompt_text:
        persist_intent_brief(brief_id=args.persist_brief_id, prompt_text=args.prompt_text, project_root=str(project_root))

    ser_res = serialize_handoff_v2(
        hub_root=hub_root, project_root=project_root, mode=str(args.mode or "PASSIVE_STANDBY"),
        ecosystem_scan=bool(args.ecosystem_scan), conversation_id=cid,
        transcript_path=Path(tp) if tp else None, active_brief_id=args.persist_brief_id,
        target_repo_ids=target_repos, prompt_text=args.prompt_text or None,
        milestone_id=cli_ms, turn=cli_turn,
    )
    lint_res = ser_res["lint_result"]
    if not bool(lint_res.get("passed", False)) or int(lint_res.get("return_code", 0)) != 0:
        print(json.dumps({"status": "LINT_FAILED", "passed": False, "lint_result": lint_res}, indent=2, ensure_ascii=False))
        return 1

    out_dir = Path(args.output_dir) if args.output_dir else (project_root / "nk_tracking" / "handoff")
    latest_file = out_dir / "session_handoff_latest.json"
    prompt_file = out_dir / "next_session_prompt.md"
    ser_res["handoff_path"], ser_res["latest_json_path"] = str(prompt_file), str(latest_file)
    if not is_dry_run:
        sess_dir = resolve_session_tracking_dir(project_root, cid) if not args.output_dir else None
        mutex_cls = resolve_facade_attr(_FACADES, "Win32NamedMutex", Win32NamedMutex)
        with mutex_cls(get_handoff_state_mutex_name(project_root.resolve()), timeout_ms=2000, is_path=False):
            _write_dual_files(project_root, prompt_file, sess_dir, "next_session_prompt.md", ser_res["compiled_markdown"].encode("utf-8"))
            _write_dual_files(project_root, latest_file, sess_dir, "session_handoff_latest.json", json.dumps(ser_res["envelope"], indent=2, ensure_ascii=False).encode("utf-8"))

    if args.json:
        print(json.dumps(ser_res, indent=2, ensure_ascii=False))
    else:
        md_out = ser_res["compiled_markdown"]
        print(md_out, end="" if md_out.endswith("\n") else "\n")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Genera metadati di handoff e prompt Template 11/12 o HANDOFF_V2."""
    args = _build_parser().parse_args(argv)
    eff_ws_root = Path(resolve_facade_attr(_FACADES, "_workspace_root", _workspace_root)).resolve()
    if args.root and args.project_root:
        hub_root, _ = resolve_hub_and_project_roots(Path(args.root))
        _, project_root = resolve_hub_and_project_roots(Path(args.project_root))
    elif args.root or args.project_root:
        hub_root, project_root = resolve_hub_and_project_roots(Path(args.root or args.project_root))
    else:
        hub_root, project_root = eff_ws_root, eff_ws_root
    effective_root = project_root

    if args.serialize:
        return _run_serialize_mode(args, hub_root, project_root)

    eff_cid = _normalize_cli_conv_id(args.conversation_id)
    is_dry_run, is_auto_checkpoint = bool(args.dry_run), bool(args.auto_checkpoint)
    try:
        cli_turn = _parse_optional_turn(args.turn)
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "passed": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2

    force_template_11 = bool(args.compile_template_11 or args.compile_task_prompt)
    want_prompt = bool(is_auto_checkpoint or args.generate_prompt or args.compile_handoff_prompt or args.compile_state_handoff or force_template_11)
    if not is_auto_checkpoint:
        use_template_11 = force_template_11
    else:
        use_template_11 = True if force_template_11 else (select_auto_checkpoint_template(_has_dirty_staging_inprocess(effective_root), cli_turn) == "Template 11")

    persisted_ib_path: Optional[Path] = None
    persisted_ib_sha256: Optional[str] = None
    if args.persist_brief_id and not is_dry_run:
        persisted_ib_path = persist_intent_brief(brief_id=args.persist_brief_id, prompt_text=args.prompt_text or "Intent Brief salvato da CLI.", project_root=str(effective_root))
        persisted_ib_sha256 = hashlib.sha256(persisted_ib_path.read_bytes()).hexdigest()

    shared_state_sha256: Optional[str] = None
    if is_auto_checkpoint or args.checkpoint_turn is not None or (want_prompt and not use_template_11) or persisted_ib_path is not None or args.resume_from_anchor or args.generate_active_context:
        shared_state_sha256 = _compute_workspace_state_sha256(effective_root)
    staging_state_sha256: Optional[str] = _compute_staging_state_sha256(effective_root) if (is_auto_checkpoint or args.checkpoint_turn is not None or cli_turn is not None) else None

    if not is_auto_checkpoint and args.checkpoint_turn is not None:
        if is_dry_run:
            cp_turn_check = _parse_optional_turn(args.checkpoint_turn)
            if cp_turn_check is None or not (1 <= cp_turn_check <= 5):
                raise ValueError(f"Il turno FSM deve essere compreso tra 1 e 5: {args.checkpoint_turn}")
            cp_res: Dict[str, Any] = {
                "event": "fsm_checkpoint", "type": "fsm_checkpoint", "event_type": "fsm_checkpoint",
                "turn": cp_turn_check, "gate_status": str(args.gate_status or "PASS").strip(),
                "milestone_id": str(args.milestone_id or "Auto-Saved Milestone").strip(),
                "state_sha256": shared_state_sha256, "staging_state_sha256": staging_state_sha256,
                "status": "DRY_RUN", "dry_run": True, "passed": True,
                "anchor_path": str(effective_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"),
            }
        else:
            cp_res = record_fsm_checkpoint(
                turn=int(args.checkpoint_turn), gate_status=str(args.gate_status or "PASS"),
                milestone_id=str(args.milestone_id or "Auto-Saved Milestone"), root=effective_root,
                state_sha256_override=shared_state_sha256, staging_state_sha256=staging_state_sha256,
                conversation_id=eff_cid,
            )
        if not args.resume_from_anchor and not args.generate_active_context and not want_prompt and (persisted_ib_path is None or is_dry_run):
            print(json.dumps(cp_res, indent=2, ensure_ascii=False))
            return 0

    if not is_auto_checkpoint and args.resume_from_anchor:
        res_anchor = resume_from_anchor(root=effective_root, conversation_id=eff_cid, state_sha256_override=shared_state_sha256)
        print(json.dumps(res_anchor, indent=2, ensure_ascii=False))
        return 0 if res_anchor.get("passed") else 1

    if not is_auto_checkpoint and args.generate_active_context and not want_prompt:
        ctx_res = generate_active_context_view(root=effective_root, profile=str(args.profile or "generation"), dry_run=is_dry_run, conversation_id=eff_cid, state_sha256_override=shared_state_sha256)
        print(json.dumps(ctx_res, indent=2, ensure_ascii=False))
        return 0 if ctx_res.get("passed") else 1

    transcript_path = _resolve_transcript_arg(args)
    output_dir = args.output_dir or str(effective_root / "nk_tracking" / "handoff")
    sess_dir = resolve_session_tracking_dir(effective_root, eff_cid) if not args.output_dir else None

    steps, total_chars, capsule, actual_tokens = _inspect_transcript_fast(transcript_path or "")
    estimated_tokens = max(1, total_chars // 4)
    tokens = actual_tokens if (actual_tokens is not None and actual_tokens > 0) else estimated_tokens

    dirty_files = _has_dirty_staging_inprocess(effective_root)
    project_dirty_files = dirty_files if effective_root != eff_ws_root else False
    stash_patch = None
    if args.git_stash and not is_dry_run:
        dirty_files, stash_patch = _check_git_dirty_fast(effective_root, _resolve_git_executable(), stash_output_dir=output_dir if args.output_dir else None)
        if effective_root != eff_ws_root and effective_root.exists():
            project_dirty_files = dirty_files

    if is_auto_checkpoint and not force_template_11:
        use_template_11 = select_auto_checkpoint_template(dirty_files, cli_turn) == "Template 11"

    effective_milestone = str(args.milestone_id or "Auto-Saved Milestone").strip()
    metadata: Dict[str, Any] = {
        "version": HANDOFF_VERSION, "steps": steps, "tokens": tokens, "dirty_files": dirty_files,
        "project_root": str(effective_root), "project_dirty_files": project_dirty_files, "stash_patch": stash_patch,
        "baseline_tests": _read_baseline_tests_count(effective_root),
        "baseline_pass_rate_pct": _read_baseline_pass_rate(effective_root),
        "milestone": effective_milestone, "handoff_template": "Template 11" if use_template_11 else "Template 12",
        "standby_mode": not use_template_11, "unverified_claims": [],
    }
    if actual_tokens is not None:
        metadata["actual_tokens"], metadata["estimated_tokens"] = actual_tokens, estimated_tokens
    if eff_cid:
        metadata["conversation_id"] = eff_cid
    if cli_turn is not None:
        metadata["turn"] = cli_turn
    if shared_state_sha256 is not None:
        metadata["state_sha256"] = shared_state_sha256
    if staging_state_sha256 is not None:
        metadata["staging_state_sha256"] = staging_state_sha256
    if persisted_ib_path is not None and persisted_ib_sha256 is not None:
        metadata["intent_brief_path"], metadata["intent_brief_sha256"] = str(persisted_ib_path), persisted_ib_sha256
    if is_auto_checkpoint:
        turn_phase = f"TURN_{cli_turn}" if (cli_turn is not None and 1 <= cli_turn <= 5) else "IDLE_CHECKPOINT"
        metadata["turn_phase"] = turn_phase
        metadata["manifest"] = build_handoff_manifest_v1(
            hub_root, effective_root, str(eff_cid or ""), effective_milestone,
            "SESSION_HANDOFF" if use_template_11 else "PASSIVE_STATE_HANDOFF",
            "MODE_A_SOVEREIGN" if use_template_11 else "MODE_D_DISCOVERY",
            turn_phase if use_template_11 else "BYPASSED",
            "[3] NK-Python-Async-Builder" if use_template_11 else "[4] NK-Delta-Architect",
        )
        metadata["pending_actions"] = []
        metadata["last_summary"] = f"Auto-checkpoint {metadata['handoff_template']} su {effective_milestone}."
        metadata["last_failed_checks"] = []

    compiled_prompt: Optional[str] = None
    lint_report: Optional[Dict[str, Any]] = None
    lint_mode = "auto" if use_template_11 else "state-handoff"
    if want_prompt:
        compiled_prompt = compile_template_11_prompt(str(effective_root), effective_milestone, capsule) if use_template_11 else compile_template_12_state_handoff(str(effective_root), effective_milestone, capsule, state_sha256_override=shared_state_sha256)
        lint_fn = resolve_facade_attr(_FACADES, "lint_prompt_text", lint_prompt_text)
        lint_report, lint_rc = lint_fn(compiled_prompt, mode=lint_mode)
        metadata["prompt_lint"] = {"mode": lint_mode, "passed": bool(lint_report.get("passed", False)), "violations_count": int(lint_report.get("violations_count", 0))}
        if lint_rc != 0 and is_auto_checkpoint:
            print(json.dumps({"status": "LINT_FAILED", "passed": False, "mode": lint_mode, "lint_report": lint_report}, indent=2, ensure_ascii=False))
            return 1

    latest_file, prompt_file = Path(output_dir) / "session_handoff_latest.json", Path(output_dir) / "next_session_prompt.md"
    active_ctx_path, anchor_file_path = effective_root / "nk_tracking" / "active_context.md", effective_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    fsm_cp_turn: Optional[int] = int(args.checkpoint_turn) if args.checkpoint_turn is not None else (cli_turn if is_auto_checkpoint and cli_turn is not None and 1 <= cli_turn <= 5 else None)

    if is_dry_run:
        would_write = [str(latest_file)] + ([str(sess_dir / "session_handoff_latest.json")] if sess_dir else [])
        if want_prompt:
            would_write.extend([str(prompt_file)] + ([str(sess_dir / "next_session_prompt.md")] if sess_dir else []))
        ctx_preview: Optional[Dict[str, Any]] = None
        if is_auto_checkpoint or args.generate_active_context:
            ctx_preview = generate_active_context_view(root=effective_root, profile=str(args.profile or "generation"), dry_run=True, conversation_id=eff_cid, state_sha256_override=shared_state_sha256)
            would_write.extend([str(active_ctx_path)] + ([str(sess_dir / "active_context.md")] if sess_dir else []))
        if is_auto_checkpoint:
            would_write.extend([str(anchor_file_path)] + ([str(sess_dir / "session_anchor.jsonl")] if sess_dir else []))
        dry_payload: Dict[str, Any] = {"status": "DRY_RUN", "dry_run": True, "passed": True, "project_root": str(effective_root), "handoff_template": metadata["handoff_template"], "would_write": would_write, "metadata": metadata}
        if lint_report is not None:
            dry_payload["lint_report"] = lint_report
        if ctx_preview is not None:
            dry_payload["active_context"] = ctx_preview
        if compiled_prompt is not None:
            dry_payload["compiled_prompt"] = compiled_prompt
        print(json.dumps(dry_payload, indent=2, ensure_ascii=False))
        return 0

    if is_auto_checkpoint:
        return _persist_auto_checkpoint_locked(
            args, effective_root, effective_milestone, shared_state_sha256, staging_state_sha256,
            eff_cid, fsm_cp_turn, latest_file, prompt_file, active_ctx_path, sess_dir, metadata, compiled_prompt,
        )

    _write_dual_files(effective_root, latest_file, sess_dir, "session_handoff_latest.json", json.dumps(metadata, indent=2).encode("utf-8"))
    if want_prompt and compiled_prompt is not None:
        _write_dual_files(effective_root, prompt_file, sess_dir, "next_session_prompt.md", compiled_prompt.encode("utf-8"))
        if args.compile_handoff_prompt or args.compile_state_handoff or args.compile_template_11 or args.compile_task_prompt:
            print(compiled_prompt)
    return 0
