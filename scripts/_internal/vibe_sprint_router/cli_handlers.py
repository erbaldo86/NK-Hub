"""Parsing transcript, autotest e dispatcher CLI di vibe_sprint_router."""

from __future__ import annotations

import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.transcript_io import strip_antigravity_envelope
from _internal.vibe_sprint_router.constants_core import _USER_TRANSCRIPT_ROLES


def _facade_attr(name: str, default: Any) -> Any:
    """Risolve un attributo facciata delegando a nk_common.facade_boot."""
    return resolve_facade_attr(
        ("vibe_sprint_router", "scripts.vibe_sprint_router"), name, default
    )


def _extract_user_text_from_record(rec: Dict[str, Any]) -> Optional[str]:
    """Estrae il testo utente da un record JSONL di transcript se appartiene a USER_INPUT."""
    role_candidates = (
        str(rec.get("type") or ""),
        str(rec.get("event_type") or ""),
        str(rec.get("source") or ""),
        str(rec.get("role") or ""),
        str(rec.get("kind") or ""),
    )
    is_user_rec = any(
        rc.strip().lower() in _USER_TRANSCRIPT_ROLES for rc in role_candidates if rc
    ) or ("user_input" in rec)
    if not is_user_rec:
        return None

    for key in ("user_input", "content", "prompt", "text", "message", "input"):
        val = rec.get(key)
        if isinstance(val, str) and val.strip():
            s = strip_antigravity_envelope(val.strip())
            if not s or s.startswith("<CONTEXT_SUMMARY>"):
                continue
            return s
        if isinstance(val, list):
            parts: List[str] = []
            for item in val:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    t_val = item.get("text") or item.get("content") or item.get("user_input")
                    if isinstance(t_val, str) and t_val.strip():
                        parts.append(t_val.strip())
            joined = strip_antigravity_envelope("\n".join(parts).strip())
            if joined and not joined.startswith("<CONTEXT_SUMMARY>"):
                return joined
    return None


def _collect_env_transcript_candidates() -> List[Path]:
    """Raccoglie eventuali path transcript espliciti dalle variabili ambiente."""
    cands: List[Path] = []
    for env_k in ("NK_TRANSCRIPT_PATH", "ANTIGRAVITY_TRANSCRIPT_PATH"):
        if env_v := os.environ.get(env_k, "").strip():
            cands.append(Path(env_v))
    return cands


def _collect_brain_transcript_candidates(
    brain_dir: Path, conversation_id: Optional[str]
) -> List[Path]:
    """Risolve il transcript da CID esplicito o fails-closed su ambiguita multi-chat (BS-08)."""
    if not brain_dir.is_dir():
        return []
    explicit_cid = (
        (conversation_id or "").strip()
        or os.environ.get("NK_CONVERSATION_ID", "").strip()
        or os.environ.get("ANTIGRAVITY_CONVERSATION_ID", "").strip()
    )
    if explicit_cid:
        return [brain_dir / explicit_cid / ".system_generated" / "logs" / "transcript.jsonl"]
    now_ts = time.time()
    recent_logs: List[Tuple[float, Path]] = []
    try:
        for conv_dir in brain_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            tp = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if tp.is_file() and (now_ts - (st_mtime := tp.stat().st_mtime)) <= 1800.0:
                recent_logs.append((st_mtime, tp))
    except OSError:
        return []
    if not recent_logs:
        return []
    recent_logs.sort(key=lambda item: item[0], reverse=True)
    if len(recent_logs) >= 2 and (recent_logs[0][0] - recent_logs[1][0]) < 15.0:
        return []
    return [recent_logs[0][1]]


def _read_tail_user_input(tp: Path) -> Optional[str]:
    """Estrae l'ultimo USER_INPUT dalla coda di un file transcript.jsonl."""
    try:
        if not tp.exists() or not tp.is_file() or (fsize := tp.stat().st_size) <= 0:
            return None
        with tp.open("rb") as fh:
            if fsize > 131072:
                fh.seek(fsize - 131072)
            tail_bytes = fh.read()
        for raw_line in reversed(tail_bytes.decode("utf-8", errors="replace").splitlines()):
            line_s = raw_line.strip()
            if not line_s or not line_s.startswith("{"):
                continue
            try:
                rec = json.loads(line_s)
            except ValueError:
                continue
            if isinstance(rec, dict) and (extracted := _extract_user_text_from_record(rec)):
                return extracted
    except OSError:
        return None
    return None


def _read_latest_user_input_from_transcript(
    transcript_arg: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Optional[str]:
    """Legge l'ultimo USER_INPUT dal transcript isolato per conversazione (BS-08)."""
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if transcript_arg:
        cand_paths = [Path(transcript_arg)]
    elif (conversation_id or "").strip():
        cand_paths = _collect_brain_transcript_candidates(brain_dir, conversation_id)
    else:
        cand_paths = _collect_env_transcript_candidates()
        cand_paths.extend(_collect_brain_transcript_candidates(brain_dir, None))
    for tp in cand_paths:
        if extracted := _read_tail_user_input(tp):
            return extracted
    return None


def _invoke_transcript_reader(reader_fn: Any, args: Any) -> Optional[str]:
    """Invoca il lettore transcript passando conversation_id solo se supportato."""
    tp_arg = getattr(args, "transcript", None)
    cid_arg = getattr(args, "conversation_id", None)
    try:
        params = inspect.signature(reader_fn).parameters
        has_cid = "conversation_id" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except (TypeError, ValueError):
        has_cid = False
    return reader_fn(tp_arg, conversation_id=cid_arg) if has_cid else reader_fn(tp_arg)


def _resolve_effective_cli_prompt(
    args: Any, workspace_root: Optional[Path] = None
) -> str:
    """Risolve il prompt CLI effettivo da file, stdin, argomenti o transcript attivo."""
    prompt_file_arg = getattr(args, "prompt_file", None)
    if prompt_file_arg:
        pf = Path(prompt_file_arg)
        if not pf.is_absolute() and not pf.exists() and workspace_root is not None:
            cand_ws = workspace_root / pf
            if cand_ws.exists():
                pf = cand_ws
        if not pf.exists() or not pf.is_file():
            raise FileNotFoundError(f"Prompt file non trovato: {prompt_file_arg}")
        return pf.read_text(encoding="utf-8", errors="replace")

    if getattr(args, "stdin", False):
        return sys.stdin.read()

    if (
        args.classify_prompt is not None
        and args.classify_prompt != "__USE_PROMPT__"
        and args.prompt == "Vibe Sprint Change"
    ):
        return str(args.classify_prompt)

    pos_tokens = getattr(args, "positional_prompt", None) or []
    if args.prompt == "Vibe Sprint Change" and pos_tokens:
        joined = " ".join(str(t) for t in pos_tokens if str(t).strip()).strip()
        if joined:
            return joined

    if args.prompt == "Vibe Sprint Change" and (
        getattr(args, "meta_prompt_gate", False)
        or getattr(args, "no_gate", False)
        or getattr(args, "transcript", None) is not None
    ):
        reader_fn = _facade_attr(
            "_read_latest_user_input_from_transcript",
            _read_latest_user_input_from_transcript,
        )
        from_transcript = _invoke_transcript_reader(reader_fn, args)
        if from_transcript:
            return from_transcript

    return str(args.prompt)
