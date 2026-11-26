# -*- coding: utf-8 -*-
"""Punto di ingresso CLI per nk_transcript_tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence, Tuple

from _internal.nk_common.paths import resolve_workspace_root
from _internal.nk_transcript_tools.evidence_and_ears import check_evidence
from _internal.nk_transcript_tools.locate_and_compliance import (
    analyze_compliance,
    locate_transcript,
)
from _internal.nk_transcript_tools.oracle_and_grounding import (
    handle_oracle_lock,
    handle_report_conflict,
    verify_report_grounding,
)
from _internal.nk_transcript_tools.prompt_and_ste100 import (
    lint_ears_requirements,
    lint_prompt_text,
    verify_ste100_compliance,
)


def _resolve_cli_path(raw_val: str, root_dir: Path, require_exists: bool, has_explicit_root: bool) -> Path:
    cand = Path(raw_val)
    if cand.is_absolute():
        return cand.resolve()
    if has_explicit_root:
        return (root_dir / cand).resolve()
    if cand.exists() or (not require_exists and cand.parent.exists()):
        return cand.resolve()
    return (root_dir / cand).resolve()


def _read_saved_lock_target(lock_p: Path, default_root: Path) -> Optional[Path]:
    if not lock_p.is_file():
        return None
    try:
        saved = json.loads(lock_p.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    raw_t = saved.get("target") if isinstance(saved, dict) else None
    if not isinstance(raw_t, str) or not raw_t.strip():
        return None
    cand = Path(raw_t.strip()).resolve()
    if (cand == default_root or default_root in cand.parents) and cand.exists():
        return cand
    return None


_DEFAULT_LOCK_TARGETS = {
    "oracle_lock_holdout.json": ("nk_tracking", "oracle_holdout"),
    "governance_lock.json": ("scripts",),
    "tensor_rsi_lock.json": ("nk_genome", "configs", "tensor_rsi"),
}


def _infer_default_lock_target(act: str, lock_p: Path, default_root: Path) -> Path:
    if act == "verify":
        saved_t = _read_saved_lock_target(lock_p, default_root)
        if saved_t is not None:
            return saved_t
    sub_parts = _DEFAULT_LOCK_TARGETS.get(lock_p.name.lower())
    if sub_parts is not None:
        cand = default_root.joinpath(*sub_parts).resolve()
        if cand.exists():
            return cand
    return (default_root / "tests").resolve()


def _resolve_oracle_lock_args(args: argparse.Namespace) -> Tuple[str, Path, Path]:
    act = args.action if args.action in ("create", "freeze", "verify") else "verify"
    has_root = bool(args.root)
    default_root = Path(args.root).resolve() if has_root else Path(resolve_workspace_root(__file__)).resolve()
    lock_p = _resolve_cli_path(args.lock_file, default_root, False, has_root) if args.lock_file else (default_root / "nk_tracking" / "oracle_lock.json").resolve()
    target_p = _resolve_cli_path(args.target, default_root, True, has_root) if args.target else _infer_default_lock_target(act, lock_p, default_root)
    return act, target_p, lock_p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per gli strumenti transcript, STE100 e prompt linter."""
    parser = argparse.ArgumentParser(description="NK Hub Generation 1.0.0-Generation Transcript & Prompt Tools")
    parser.add_argument(
        "subcommand",
        choices=("locate", "compliance", "evidence", "oracle-lock", "lint-prompt", "report-conflict", "lint-ears", "verify-grounding", "lint-ste100"),
    )
    parser.add_argument("action", nargs="?", default="")
    parser.add_argument("--transcript", type=str, default=None)
    parser.add_argument("--conversation-id", type=str, default=None)
    parser.add_argument("--brain-dir", type=str, default=None)
    parser.add_argument("--message", type=str, default="")
    parser.add_argument("--root", type=str, default="")
    parser.add_argument("--target", type=str, default="")
    parser.add_argument("--lock-file", type=str, default="")
    parser.add_argument("--lane-id", type=str, default=None)
    parser.add_argument("--test-a", type=str, default="")
    parser.add_argument("--test-b", type=str, default="")
    parser.add_argument("--reason", type=str, default="")
    parser.add_argument("--report", type=str, default="")
    parser.add_argument("--manifest", type=str, default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--file", type=str, default=None)
    parser.add_argument("--text", type=str, default=None)
    parser.add_argument("--max-words", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--mode", type=str, choices=("auto", "task", "state-handoff"), default="auto")
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
        act, target_p, lock_p = _resolve_oracle_lock_args(args)
        res, code = handle_oracle_lock(act, target_p, lock_p)
    elif args.subcommand == "report-conflict":
        res, code = handle_report_conflict(
            root=Path(args.root) if args.root else None, test_a=args.test_a, test_b=args.test_b,
            reason=args.reason, output=Path(args.output) if args.output else None, lane_id=args.lane_id,
        )
    elif args.subcommand == "lint-ears":
        txt_ears = args.text or (Path(args.file).read_text(encoding="utf-8", errors="replace") if args.file else "")
        res = lint_ears_requirements(txt_ears)
        code = 0
    elif args.subcommand == "verify-grounding":
        rep_arg = args.report or args.file or args.target or args.action
        man_arg = Path(args.manifest) if args.manifest else None
        res = verify_report_grounding(Path(rep_arg), manifest_path=man_arg)
        code = int(res.get("exit_code", 0))
    elif args.subcommand == "lint-ste100":
        txt_ste = args.text or (Path(args.file).read_text(encoding="utf-8", errors="replace") if args.file else "")
        res = verify_ste100_compliance(txt_ste, max_sentence_words=args.max_words)
        if args.strict:
            res = {**res, "advisory": False}
            code = 0 if res.get("passed") else 1
        else:
            res = {**res, "advisory": True}
            code = 0
    else:
        txt = args.text or (Path(args.file).read_text(encoding="utf-8", errors="replace") if args.file else "")
        res, code = lint_prompt_text(txt, mode=args.mode)

    print(json.dumps(res, indent=2, ensure_ascii=False))
    return code
