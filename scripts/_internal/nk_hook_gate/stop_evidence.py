"""Stop-evidence anchor tracking, compaction verification e spawn Z2 checkpoint."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.transcript_guards import is_verified_compaction
from _internal.nk_common.transcript_io import wal_bucket_hash
from _internal.nk_hook_gate.constants import (
    _SAFE_CONV_ID_RE,
    _SCRIPT_DIR,
    _WORKSPACE_ROOT,
)
from _internal.nk_hook_gate.json_io import (
    _get_hooks_temp_dir,
    _is_path_reparse_point,
    _read_json_safe,
    _write_json_atomic_safe,
)


def _stop_is_verified_compaction(rec: Dict[str, Any]) -> bool:
    """Verifica TV-08 anti-spoof prima di resettare i token su compaction/CHECKPOINT."""
    return is_verified_compaction(rec)


def _stop_extract_tokens(rec: Dict[str, Any]) -> Optional[int]:
    """Estrae input_tokens + cache_read_tokens con fallback sicuro e rifiuto bool."""

    def _vint(v: Any) -> Optional[int]:
        return None if isinstance(v, bool) or not isinstance(v, int) or v < 0 else v

    for mapping in (
        rec,
        rec.get("usage") if isinstance(rec.get("usage"), dict) else None,
    ):
        if mapping is None:
            continue
        has_in = "input_tokens" in mapping
        has_cr = "cache_read_tokens" in mapping
        in_t = _vint(mapping.get("input_tokens")) if has_in else None
        cr_t = _vint(mapping.get("cache_read_tokens")) if has_cr else None
        if (in_t is not None or cr_t is not None) and not (
            (has_in and isinstance(mapping.get("input_tokens"), bool))
            or (has_cr and isinstance(mapping.get("cache_read_tokens"), bool))
        ):
            return (in_t or 0) + (cr_t or 0)
        for key in ("actual_context_tokens", "context_tokens", "prompt_tokens"):
            val = _vint(mapping.get(key))
            if val is not None:
                return val
    return None


def _stop_read_tokens_and_epoch(
    tp_path: Path, conv_id: str
) -> Tuple[int, int, int]:
    """Restituisce (tokens, steps, epoch) dal fastguard cacheato o dal transcript."""
    try:
        file_size = tp_path.stat().st_size
    except OSError:
        return 0, 0, 0
    if file_size == 0:
        return 0, 0, 0
    hooks_dir = _get_hooks_temp_dir()
    fg_state = _read_json_safe(hooks_dir / f"fastguard_{conv_id}.json")
    fg_offset = int(fg_state.get("byte_offset", -1)) if fg_state is not None else -1
    if fg_state is not None and fg_offset == file_size:
        return (
            int(fg_state.get("last_actual_tokens", 0)),
            int(fg_state.get("steps", 0)),
            int(fg_state.get("compaction_epoch", 0)),
        )
    resumed = fg_state is not None and 0 < fg_offset < file_size
    tokens = int(fg_state.get("last_actual_tokens", 0)) if resumed else 0
    steps = int(fg_state.get("steps", 0)) if resumed else 0
    epoch = int(fg_state.get("compaction_epoch", 0)) if resumed else 0
    read_start = fg_offset if resumed else max(0, file_size - 524288)
    try:
        with open(tp_path, "rb") as f:
            if read_start > 0:
                f.seek(read_start)
            data = f.read()
        if read_start > 0 and not resumed:
            first_nl = data.find(b"\n")
            data = data[first_nl + 1 :] if first_nl != -1 else b""
        last_nl = data.rfind(b"\n")
        if last_nl == -1:
            return tokens, steps, epoch
        for raw_line in data[:last_nl].split(b"\n"):
            s = raw_line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            if _stop_is_verified_compaction(rec):
                epoch += 1
                steps = 0
                tokens = 0
                continue
            steps += 1
            tok = _stop_extract_tokens(rec)
            if tok is not None:
                tokens = tok
    except Exception:
        return 0, 0, 0
    return tokens, steps, epoch


def _stop_is_batch_mutex_or_wal_busy(roots: Sequence[Path]) -> bool:
    """Verifica OpenMutexW Global\\ / Local\\ NK_RepoBatchLock e file .wal attivi."""
    import hashlib

    if sys.platform == "win32":
        import ctypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
        k32.OpenMutexW.restype = ctypes.c_void_p
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.restype = ctypes.c_int
        seen: set[str] = set()
        for root in roots:
            norm = os.path.realpath(str(root)).lower().replace("/", "\\").rstrip("\\")
            h16 = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
            if h16 in seen:
                continue
            seen.add(h16)
            for prefix in ("Global", "Local"):
                ctypes.set_last_error(0)
                handle = k32.OpenMutexW(
                    0x00100000, False, f"{prefix}\\NK_RepoBatchLock_{h16}"
                )
                err = ctypes.get_last_error()
                if handle:
                    k32.CloseHandle(handle)
                    return True
                if err == 5:
                    return True
    cutoff = time.time() - 120.0
    import tempfile

    temp_wal = Path(tempfile.gettempdir()) / "nk_2pc_wal"
    wal_dirs: List[Path] = [temp_wal] if temp_wal.is_dir() else []
    for root in roots:
        wal_dirs.append(root / ".wal")
        try:
            ws_h = wal_bucket_hash(root)
            wal_dirs.append(temp_wal / ws_h)
        except OSError:
            pass
    for wd in wal_dirs:
        if not wd.is_dir() or _is_path_reparse_point(wd):
            continue
        try:
            for wf in wd.glob("*.wal"):
                if not _is_path_reparse_point(wf) and wf.stat().st_mtime >= cutoff:
                    return True
        except OSError:
            continue
    return False


def _stop_read_anchor_meta(
    roots: Sequence[Path], payload: Dict[str, Any], conv_id: Optional[str] = None
) -> Tuple[str, int]:
    """Estrae milestone_id e turn dall'ancora corrente senza scansioni complete."""
    mid = str(
        payload.get("milestoneId")
        or payload.get("milestone_id")
        or os.environ.get("NK_MILESTONE_ID")
        or ""
    ).strip()
    turn_val = 1
    valid_cid = (
        conv_id.strip()
        if isinstance(conv_id, str)
        and _SAFE_CONV_ID_RE.fullmatch(conv_id.strip())
        and not conv_id.strip().startswith("default_")
        else ""
    )
    for root in roots:
        anchor_cands: List[Path] = []
        if valid_cid:
            anchor_cands.append(
                root / "nk_tracking" / "sessions" / valid_cid / "session_anchor.jsonl"
            )
        anchor_cands.append(root / "nk_tracking" / "anchor" / "session_anchor.jsonl")
        for anchor in anchor_cands:
            if not anchor.is_file() or _is_path_reparse_point(anchor):
                continue
            try:
                sz = anchor.stat().st_size
                with open(anchor, "rb") as f:
                    if sz > 4096:
                        f.seek(sz - 4096)
                    lines = f.read().decode("utf-8", errors="replace").splitlines()
                for ln in reversed(lines):
                    if not ln.strip():
                        continue
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        if not mid:
                            mid = str(
                                rec.get("milestone_id") or rec.get("milestone") or ""
                            ).strip()
                        rt = rec.get("turn")
                        if isinstance(rt, int) and not isinstance(rt, bool) and 1 <= rt <= 5:
                            turn_val = rt
                        break
                if mid:
                    break
            except Exception:
                continue
        if mid:
            break
    return mid or "NK-ACS-AUTO", turn_val


def _maybe_spawn_stop_idle_checkpoint(
    conv_id: str,
    proj_root: Path,
    tp_path: Optional[Path],
    payload: Dict[str, Any],
) -> None:
    """Su idle sicuro >=150k con latch e mutex liberi spawna detached --auto-checkpoint live."""
    try:
        if tp_path is None:
            try:
                import nk_transcript_tools as _ntt

                if not conv_id.startswith("default_"):
                    loc_res, loc_code = _ntt.locate_transcript(None, conv_id)
                    if loc_code == 0 and loc_res.get("transcript_path"):
                        cand = Path(str(loc_res["transcript_path"]))
                        if cand.is_file():
                            tp_path = cand
            except Exception:
                tp_path = None
        if tp_path is None or not tp_path.is_file() or _is_path_reparse_point(tp_path):
            return
        try:
            import nk_transcript_tools as _ntt

            if _ntt.is_subagent_transcript_file(tp_path):
                return
        except Exception:
            pass
        cur_tokens, cur_steps, cur_epoch = _stop_read_tokens_and_epoch(tp_path, conv_id)
        if cur_tokens < 150_000 and cur_steps < 150:
            return
        hooks_dir = _get_hooks_temp_dir()
        if _is_path_reparse_point(hooks_dir):
            return
        latch_file = hooks_dir / f"stop_ckpt_{conv_id}.json"
        latch = _read_json_safe(latch_file)
        if latch is not None and int(latch.get("epoch", -1)) == cur_epoch:
            return
        fg_state = _read_json_safe(hooks_dir / f"fastguard_{conv_id}.json")
        now = time.time()
        if fg_state is not None and int(fg_state.get("z2_last_spawn_epoch", -1)) == cur_epoch:
            if (now - float(fg_state.get("z2_last_spawn_ts", 0.0))) < 60.0:
                return
        roots = [proj_root] if proj_root == _WORKSPACE_ROOT else [proj_root, _WORKSPACE_ROOT]
        if _stop_is_batch_mutex_or_wal_busy(roots):
            return
        handoff_script = _SCRIPT_DIR / "nk_session_handoff.py"
        if not handoff_script.is_file():
            handoff_script = _WORKSPACE_ROOT / "scripts" / "nk_session_handoff.py"
        if not handoff_script.is_file() or _is_path_reparse_point(handoff_script):
            return
        import subprocess

        milestone_id, turn_val = _stop_read_anchor_meta(roots, payload, conv_id=conv_id)
        cmd = [
            sys.executable,
            "-B",
            "-u",
            str(handoff_script),
            "--auto-checkpoint",
            "--project-root",
            str(proj_root),
            "--transcript",
            str(tp_path),
            "--conversation-id",
            conv_id,
            "--milestone-id",
            milestone_id,
            "--turn",
            str(turn_val),
        ]
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                cwd=str(proj_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=0x00000008 | 0x08000000 | 0x00000200,
            )
        else:
            subprocess.Popen(
                cmd,
                cwd=str(proj_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        _write_json_atomic_safe(
            latch_file, {"epoch": cur_epoch, "ts": now, "tokens": cur_tokens}
        )
    except Exception:
        pass
