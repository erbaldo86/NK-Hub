# -*- coding: utf-8 -*-
"""Punto di ingresso CLI per nk_session_handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
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
from _internal.nk_session_handoff.handoff_engine import record_fsm_checkpoint, resume_from_anchor
from _internal.nk_session_handoff.session_state import (
    Win32NamedMutex,
    _atomic_commit_bytes,
    _check_git_dirty_fast,
    _compute_staging_state_sha256,
    _compute_workspace_state_sha256,
    _has_dirty_staging_inprocess,
    _parse_optional_turn,
    _read_baseline_pass_rate,
    _read_baseline_tests_count,
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


def main(argv: Optional[List[str]] = None) -> int:
    """Genera metadati di handoff e prompt Template 11/12."""
    args = _build_parser().parse_args(argv)
    root_arg = args.root or args.project_root
    effective_root = Path(root_arg).resolve() if root_arg else _workspace_root.resolve()
    if not (effective_root / "scripts").is_dir() and (effective_root / "NK_Hub" / "scripts").is_dir():
        effective_root = (effective_root / "NK_Hub").resolve()
    is_dry_run = bool(args.dry_run)
    is_auto_checkpoint = bool(args.auto_checkpoint)

    try:
        cli_turn = _parse_optional_turn(args.turn)
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "passed": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2

    force_template_11 = bool(args.compile_template_11 or args.compile_task_prompt)
    want_prompt = bool(
        is_auto_checkpoint or args.generate_prompt or args.compile_handoff_prompt
        or args.compile_state_handoff or force_template_11
    )
    if not is_auto_checkpoint:
        use_template_11 = force_template_11
    else:
        dirty_check_pre = _has_dirty_staging_inprocess(effective_root)
        use_template_11 = True if force_template_11 else (select_auto_checkpoint_template(dirty_check_pre, cli_turn) == "Template 11")

    persisted_ib_path: Optional[Path] = None
    persisted_ib_sha256: Optional[str] = None
    if args.persist_brief_id and not is_dry_run:
        persisted_ib_path = persist_intent_brief(
            brief_id=args.persist_brief_id,
            prompt_text=args.prompt_text or "Intent Brief salvato da CLI.",
            project_root=str(effective_root),
        )
        persisted_ib_sha256 = hashlib.sha256(persisted_ib_path.read_bytes()).hexdigest()

    shared_state_sha256: Optional[str] = None
    if (
        is_auto_checkpoint or args.checkpoint_turn is not None or (want_prompt and not use_template_11)
        or persisted_ib_path is not None or args.resume_from_anchor or args.generate_active_context
    ):
        shared_state_sha256 = _compute_workspace_state_sha256(effective_root)

    staging_state_sha256: Optional[str] = (
        _compute_staging_state_sha256(effective_root)
        if (is_auto_checkpoint or args.checkpoint_turn is not None or cli_turn is not None)
        else None
    )

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
                conversation_id=args.conversation_id,
            )
        if not args.resume_from_anchor and not args.generate_active_context and not want_prompt and (persisted_ib_path is None or is_dry_run):
            print(json.dumps(cp_res, indent=2, ensure_ascii=False))
            return 0

    if not is_auto_checkpoint and args.resume_from_anchor:
        res_anchor = resume_from_anchor(root=effective_root, conversation_id=args.conversation_id, state_sha256_override=shared_state_sha256)
        print(json.dumps(res_anchor, indent=2, ensure_ascii=False))
        return 0 if res_anchor.get("passed") else 1

    if not is_auto_checkpoint and args.generate_active_context and not want_prompt:
        ctx_res = generate_active_context_view(
            root=effective_root, profile=str(args.profile or "generation"),
            dry_run=is_dry_run, conversation_id=args.conversation_id, state_sha256_override=shared_state_sha256,
        )
        print(json.dumps(ctx_res, indent=2, ensure_ascii=False))
        return 0 if ctx_res.get("passed") else 1

    loc_fn = resolve_facade_attr(_FACADES, "locate_transcript", locate_transcript)
    transcript_path = args.transcript
    if not transcript_path and args.conversation_id:
        try:
            loc_data, _ = loc_fn(conversation_id=args.conversation_id)
            transcript_path = str(loc_data.get("transcript_path") or "") or None
        except Exception:
            transcript_path = None
    if not transcript_path and not args.conversation_id:
        transcript_path = _discover_default_transcript()

    output_dir = args.output_dir or str(effective_root / "nk_tracking" / "handoff")
    sess_dir = resolve_session_tracking_dir(effective_root, args.conversation_id) if not args.output_dir else None

    steps, total_chars, capsule, actual_tokens = _inspect_transcript_fast(transcript_path or "")
    estimated_tokens = max(1, total_chars // 4)
    tokens = actual_tokens if (actual_tokens is not None and actual_tokens > 0) else estimated_tokens

    dirty_files = _has_dirty_staging_inprocess(effective_root)
    project_dirty_files = dirty_files if effective_root != _workspace_root else False
    stash_patch = None
    if args.git_stash and not is_dry_run:
        dirty_files, stash_patch = _check_git_dirty_fast(
            effective_root, _resolve_git_executable(), stash_output_dir=output_dir if args.output_dir else None
        )
        if effective_root != _workspace_root and effective_root.exists():
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
    if args.conversation_id:
        metadata["conversation_id"] = str(args.conversation_id).strip()
    if cli_turn is not None:
        metadata["turn"] = cli_turn
    if shared_state_sha256 is not None:
        metadata["state_sha256"] = shared_state_sha256
    if staging_state_sha256 is not None:
        metadata["staging_state_sha256"] = staging_state_sha256
    if persisted_ib_path is not None and persisted_ib_sha256 is not None:
        metadata["intent_brief_path"], metadata["intent_brief_sha256"] = str(persisted_ib_path), persisted_ib_sha256

    compiled_prompt: Optional[str] = None
    lint_report: Optional[Dict[str, Any]] = None
    lint_mode = "auto" if use_template_11 else "state-handoff"
    if want_prompt:
        compiled_prompt = (
            compile_template_11_prompt(str(effective_root), effective_milestone, capsule)
            if use_template_11
            else compile_template_12_state_handoff(str(effective_root), effective_milestone, capsule, state_sha256_override=shared_state_sha256)
        )
        lint_fn = resolve_facade_attr(_FACADES, "lint_prompt_text", lint_prompt_text)
        lint_report, lint_rc = lint_fn(compiled_prompt, mode=lint_mode)
        metadata["prompt_lint"] = {
            "mode": lint_mode, "passed": bool(lint_report.get("passed", False)),
            "violations_count": int(lint_report.get("violations_count", 0)),
        }
        if lint_rc != 0 and is_auto_checkpoint:
            print(json.dumps({"status": "LINT_FAILED", "passed": False, "mode": lint_mode, "lint_report": lint_report}, indent=2, ensure_ascii=False))
            return 1

    latest_file = Path(output_dir) / "session_handoff_latest.json"
    prompt_file = Path(output_dir) / "next_session_prompt.md"
    active_ctx_path = effective_root / "nk_tracking" / "active_context.md"
    anchor_file_path = effective_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    fsm_cp_turn: Optional[int] = (
        int(args.checkpoint_turn) if args.checkpoint_turn is not None
        else (cli_turn if is_auto_checkpoint and cli_turn is not None and 1 <= cli_turn <= 5 else None)
    )

    if is_dry_run:
        would_write = [str(latest_file)] + ([str(sess_dir / "session_handoff_latest.json")] if sess_dir else [])
        if want_prompt:
            would_write.extend([str(prompt_file)] + ([str(sess_dir / "next_session_prompt.md")] if sess_dir else []))
        ctx_preview: Optional[Dict[str, Any]] = None
        if is_auto_checkpoint or args.generate_active_context:
            ctx_preview = generate_active_context_view(
                root=effective_root, profile=str(args.profile or "generation"), dry_run=True,
                conversation_id=args.conversation_id, state_sha256_override=shared_state_sha256,
            )
            would_write.extend([str(active_ctx_path)] + ([str(sess_dir / "active_context.md")] if sess_dir else []))
        if is_auto_checkpoint and fsm_cp_turn is not None:
            would_write.extend([str(anchor_file_path)] + ([str(sess_dir / "session_anchor.jsonl")] if sess_dir else []))
        dry_payload: Dict[str, Any] = {
            "status": "DRY_RUN", "dry_run": True, "passed": True, "project_root": str(effective_root),
            "handoff_template": metadata["handoff_template"], "would_write": would_write, "metadata": metadata,
        }
        if lint_report is not None:
            dry_payload["lint_report"] = lint_report
        if ctx_preview is not None:
            dry_payload["active_context"] = ctx_preview
        if compiled_prompt is not None:
            dry_payload["compiled_prompt"] = compiled_prompt
        print(json.dumps(dry_payload, indent=2, ensure_ascii=False))
        return 0

    if is_auto_checkpoint:
        repo_hash16 = hashlib.sha256(str(effective_root.resolve()).lower().encode("utf-8")).hexdigest()[:16]
        mutex_cls = resolve_facade_attr(_FACADES, "Win32NamedMutex", Win32NamedMutex)
        try:
            with mutex_cls(f"Global\\NK_HandoffWorker_{repo_hash16}", timeout_ms=0, is_path=False):
                with mutex_cls(get_repo_batch_mutex_name(effective_root.resolve()), timeout_ms=2000, is_path=False):
                    anchor_res = (
                        record_fsm_checkpoint(
                            turn=fsm_cp_turn, gate_status=str(args.gate_status or "PASS"), milestone_id=effective_milestone,
                            root=effective_root, state_sha256_override=shared_state_sha256,
                            staging_state_sha256=staging_state_sha256, conversation_id=args.conversation_id,
                        )
                        if fsm_cp_turn is not None else None
                    )
                    ctx_res = generate_active_context_view(
                        root=effective_root, profile=str(args.profile or "generation"), dry_run=False,
                        conversation_id=args.conversation_id, state_sha256_override=shared_state_sha256,
                    )
                    _write_dual_files(effective_root, latest_file, sess_dir, "session_handoff_latest.json", json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"))
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

    _write_dual_files(effective_root, latest_file, sess_dir, "session_handoff_latest.json", json.dumps(metadata, indent=2).encode("utf-8"))
    if want_prompt and compiled_prompt is not None:
        _write_dual_files(effective_root, prompt_file, sess_dir, "next_session_prompt.md", compiled_prompt.encode("utf-8"))
        if args.compile_handoff_prompt or args.compile_state_handoff or args.compile_template_11 or args.compile_task_prompt:
            print(compiled_prompt)
    return 0
