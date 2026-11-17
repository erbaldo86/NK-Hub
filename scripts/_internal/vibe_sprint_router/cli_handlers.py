"""Parsing transcript, autotest e dispatcher CLI di vibe_sprint_router."""

from __future__ import annotations

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


def _read_latest_user_input_from_transcript(
    transcript_arg: Optional[str] = None,
) -> Optional[str]:
    """Legge l'ultimo USER_INPUT dal transcript attivo (CLI, env o brain Antigravity)."""
    cand_paths: List[Path] = []
    if transcript_arg:
        cand_paths.append(Path(transcript_arg))
    else:
        for env_k in ("NK_TRANSCRIPT_PATH", "ANTIGRAVITY_TRANSCRIPT_PATH"):
            env_v = os.environ.get(env_k, "").strip()
            if env_v:
                cand_paths.append(Path(env_v))

        brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
        for cid_env in ("NK_CONVERSATION_ID", "ANTIGRAVITY_CONVERSATION_ID"):
            cid = os.environ.get(cid_env, "").strip()
            if cid and brain_dir.is_dir():
                cand_paths.append(
                    brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
                )

        if not cand_paths and brain_dir.is_dir():
            now_ts = time.time()
            recent_logs: List[Tuple[float, Path]] = []
            try:
                for conv_dir in brain_dir.iterdir():
                    if not conv_dir.is_dir():
                        continue
                    tp = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
                    if tp.is_file():
                        st_mtime = tp.stat().st_mtime
                        if now_ts - st_mtime <= 1800.0:
                            recent_logs.append((st_mtime, tp))
                if recent_logs:
                    recent_logs.sort(key=lambda item: item[0], reverse=True)
                    cand_paths.append(recent_logs[0][1])
            except Exception:
                pass

    for tp in cand_paths:
        try:
            if not tp.exists() or not tp.is_file():
                continue
            fsize = tp.stat().st_size
            if fsize <= 0:
                continue
            with tp.open("rb") as fh:
                if fsize > 131072:
                    fh.seek(fsize - 131072)
                tail_bytes = fh.read()
            lines = tail_bytes.decode("utf-8", errors="replace").splitlines()
            for raw_line in reversed(lines):
                line_s = raw_line.strip()
                if not line_s or not line_s.startswith("{"):
                    continue
                try:
                    rec = json.loads(line_s)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    extracted = _extract_user_text_from_record(rec)
                    if extracted:
                        return extracted
        except Exception:
            continue
    return None


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
        from_transcript = _facade_attr(
            "_read_latest_user_input_from_transcript",
            _read_latest_user_input_from_transcript,
        )(
            getattr(args, "transcript", None)
        )
        if from_transcript:
            return from_transcript

    return str(args.prompt)
