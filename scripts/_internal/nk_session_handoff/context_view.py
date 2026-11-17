# -*- coding: utf-8 -*-
"""Generazione della vista active_context.md per nk_session_handoff."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import (
    HIGH_CAPACITY_PROFILES,
    SUPPORTED_MODEL_PROFILES,
)
from _internal.nk_session_handoff.constants import (
    DEFAULT_MILESTONE_ID,
    HANDOFF_VERSION,
    _workspace_root,
    resolve_session_tracking_dir,
)
from _internal.nk_session_handoff.handoff_engine import resume_from_anchor
from _internal.nk_session_handoff.session_state import (
    _atomic_commit_bytes,
    _read_baseline_pass_rate,
    _read_baseline_tests_count,
    _sanitize_ste100_inline,
)


def _collect_staging_relative_files(target_root: Path, limit: int = 15) -> Tuple[List[str], int]:
    """Enumera i file modificati in .staging/ relativi a target_root."""
    staging_dir = target_root / ".staging"
    if not staging_dir.is_dir():
        return [], 0
    found: List[str] = []
    stack: List[Path] = [staging_dir]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    name = entry.name
                    if name in (".gitkeep", "__pycache__", ".pytest_cache") or name.endswith((".pyc", ".pyo")):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            found.append(Path(entry.path).relative_to(target_root).as_posix())
                        except ValueError:
                            found.append(f".staging/{name}")
        except OSError:
            continue
    found.sort()
    return found[:limit], len(found)


def _read_latest_handoff_state(
    target_root: Path, sess_dir: Optional[Path], out_file: Path
) -> Dict[str, Any]:
    """Carica session_handoff_latest.json dalla sessione o dalla directory handoff."""
    candidates: List[Path] = []
    if sess_dir is not None:
        candidates.append(sess_dir / "session_handoff_latest.json")
    candidates.append(target_root / "nk_tracking" / "handoff" / "session_handoff_latest.json")
    candidates.append(out_file.parent / "session_handoff_latest.json")
    for cand in candidates:
        try:
            if cand.is_file():
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            continue
    return {}


def _format_handoff_list_field(raw_val: Any, max_items: int = 3) -> str:
    """Normalizza campi lista o stringa per il riepilogo operativo STE100."""
    _ = max_items
    if isinstance(raw_val, list):
        items = [_sanitize_ste100_inline(str(x), "") for x in raw_val if str(x).strip()]
        return "; ".join(it for it in items if it)[:140]
    if isinstance(raw_val, str) and raw_val.strip():
        return _sanitize_ste100_inline(raw_val, "")
    return ""


def _build_active_context_delta_lines(
    target_root: Path,
    sess_dir: Optional[Path],
    out_file: Path,
    anchor_state: Dict[str, Any],
    base_char_len: int,
    max_tokens: int,
) -> List[str]:
    """Costruisce la sezione Delta e Stato Operativo Corrente entro il budget token."""
    max_chars = max_tokens * 4
    item_cap = 120 if max_tokens >= 1200 else 72
    latest_data = _read_latest_handoff_state(target_root, sess_dir, out_file)
    staged_top, total_staged = _collect_staging_relative_files(target_root, limit=15)

    raw_pending = anchor_state.get("pending_actions")
    if raw_pending is None:
        raw_pending = latest_data.get("pending_actions")
    raw_summary = anchor_state.get("last_summary") or (
        latest_data.get("last_summary")
        or latest_data.get("completed_summary")
        or latest_data.get("summary")
    )
    raw_failed = anchor_state.get("last_failed_checks")
    if raw_failed is None:
        raw_failed = latest_data.get("last_failed_checks") or latest_data.get("failed_checks")

    delta_lines: List[str] = ["", "## Delta & Stato Operativo Corrente"]
    used_chars = base_char_len + sum(len(ln) + 1 for ln in delta_lines) + 2

    def _try_append(line: str) -> bool:
        nonlocal used_chars
        if used_chars + len(line) + 1 > max_chars:
            return False
        delta_lines.append(line)
        used_chars += len(line) + 1
        return True

    summary_txt = _format_handoff_list_field(raw_summary, max_items=1)
    if summary_txt:
        _try_append(f"- **Ultimo Riepilogo:** {summary_txt[:item_cap]}.")
    pending_txt = _format_handoff_list_field(raw_pending, max_items=3)
    if pending_txt:
        _try_append(f"- **Azioni Pendenti:** {pending_txt[:item_cap]}.")
    failed_txt = _format_handoff_list_field(raw_failed, max_items=3)
    if failed_txt:
        _try_append(f"- **Controlli Falliti:** {failed_txt[:item_cap]}.")

    if not staged_top:
        _try_append("- **File in .staging/:** nessuno.")
    else:
        _try_append(f"- **File in .staging/ ({total_staged}):**")
        added_files = 0
        for rel_p in staged_top:
            clean_p = rel_p.replace(" - ", "_").replace("\u2014", "_").replace("\u2013", "_")
            if _try_append(f"  - `{clean_p}`"):
                added_files += 1
            else:
                break
        remaining = total_staged - added_files
        if remaining > 0:
            _try_append(f"  - *(+{remaining} altri file in .staging/)*")
    return delta_lines


def generate_active_context_view(
    root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    profile: str = "generation",
    dry_run: bool = False,
    conversation_id: Optional[str] = None,
    state_sha256_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Genera nk_tracking/active_context.md in standard ASD-STE100."""
    target_root = Path(root).resolve() if root is not None else _workspace_root.resolve()
    if output_path is not None:
        raw_out = Path(output_path)
        out_file = raw_out.resolve() if raw_out.is_absolute() else (target_root / raw_out).resolve()
        sess_dir: Optional[Path] = None
    else:
        out_file = (target_root / "nk_tracking" / "active_context.md").resolve()
        sess_dir = resolve_session_tracking_dir(target_root, conversation_id)

    if not out_file.resolve().is_relative_to(target_root.resolve()):
        raise ValueError(f"Percorso output_path fuori da target_root vietato: {out_file}")

    raw_prof = str(profile).strip().lower()
    norm_profile = raw_prof if raw_prof in SUPPORTED_MODEL_PROFILES else "generation"
    max_tokens = 1200 if norm_profile in HIGH_CAPACITY_PROFILES else 350

    anchor_state = resume_from_anchor(
        root=target_root,
        conversation_id=conversation_id,
        state_sha256_override=state_sha256_override,
    )
    last_turn = int(anchor_state.get("turn", 0))
    last_gate = _sanitize_ste100_inline(str(anchor_state.get("gate_status") or "READY"), "READY")
    ms_id = _sanitize_ste100_inline(str(anchor_state.get("milestone_id") or DEFAULT_MILESTONE_ID), DEFAULT_MILESTONE_ID)
    total_tests = _read_baseline_tests_count(target_root)
    pass_rate = _read_baseline_pass_rate(target_root)

    lines = [
        "# Contesto Operativo Attivo NK Hub Generation",
        "",
        "## Stato Corrente della Sessione",
        f"1. **Versione Attiva:** `{HANDOFF_VERSION}`.",
        f"2. **Profilo Modello:** `{norm_profile}`.",
        f"3. **Milestone Attivo:** `{ms_id}`.",
        f"4. **Ultimo Turno FSM:** `{last_turn}` con stato `{last_gate}`.",
        f"5. **Baseline Test:** `{total_tests}` test con pass rate `{pass_rate:.1f}%`.",
        "",
        "## Regole Operative Prioritarie",
        "1. Esegui tutte le modifiche esclusivamente nella directory `.staging/`.",
        "2. Valida ogni modifica con `ast_guard_validator.py` prima della promozione.",
        "3. Verifica la convergenza matematica con `rsi_convergence_engine.py`.",
        "4. Promuovi i file in produzione tramite `win32_2pc_engine.py`.",
    ]
    base_len = sum(len(ln) + 1 for ln in lines)
    lines.extend(
        _build_active_context_delta_lines(
            target_root=target_root,
            sess_dir=sess_dir,
            out_file=out_file,
            anchor_state=anchor_state,
            base_char_len=base_len,
            max_tokens=max_tokens,
        )
    )
    content = "\n".join(lines) + "\n"
    if not dry_run:
        encoded = content.encode("utf-8")
        _atomic_commit_bytes(target_root, out_file, encoded)
        if sess_dir is not None:
            _atomic_commit_bytes(target_root, (sess_dir / "active_context.md").resolve(), encoded)

    estimated_tokens = max(1, len(content) // 4)
    return {
        "status": "DRY_RUN" if dry_run else "GENERATED",
        "dry_run": bool(dry_run),
        "passed": estimated_tokens <= max_tokens,
        "output_path": str(out_file),
        "profile": norm_profile,
        "max_tokens": max_tokens,
        "estimated_tokens": estimated_tokens,
        "char_count": len(content),
        "content": content,
    }
