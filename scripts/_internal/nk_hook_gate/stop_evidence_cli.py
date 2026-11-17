"""Handler CLI stop-evidence e risoluzione project root per HookGateV2."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, Dict, Optional

from _internal.nk_hook_gate.core_env import _WORKSPACE_ROOT

if TYPE_CHECKING:
    import argparse
    from pathlib import Path
else:
    from types import SimpleNamespace

    argparse = SimpleNamespace(Namespace=Any)
    Path = Any


def _resolve_proj_root_path(
    raw_root: Optional[str], payload: Optional[Dict[str, Any]] = None
) -> Path:
    """Risolve la root effettiva da CLI o da payload JSON (workspacePaths, projectRoot, cwd)."""
    from pathlib import Path

    if isinstance(raw_root, str) and raw_root.strip():
        return Path(raw_root.strip()).resolve()

    if isinstance(payload, dict):
        candidates: list[str] = []
        ws_paths = payload.get("workspacePaths") or payload.get("workspace_paths")
        if isinstance(ws_paths, (list, tuple)):
            for item in ws_paths:
                if isinstance(item, str) and item.strip():
                    candidates.append(item.strip())
        for key in (
            "projectRoot",
            "project_root",
            "workspacePath",
            "workspace_path",
            "workspace_root",
            "cwd",
        ):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())

        existing_dirs: list[Path] = []
        for raw_c in candidates:
            try:
                cand_p = Path(raw_c).resolve()
            except OSError:
                continue
            if cand_p.is_dir():
                existing_dirs.append(cand_p)
                if (cand_p / "scripts").is_dir() or (cand_p / ".staging").is_dir():
                    return cand_p
                nk_sub = cand_p / "NK_Hub"
                if nk_sub.is_dir() and (
                    (nk_sub / "scripts").is_dir() or (nk_sub / ".staging").is_dir()
                ):
                    return nk_sub.resolve()
        if existing_dirs:
            return existing_dirs[0]

    return Path(_WORKSPACE_ROOT)


def _handle_stop_evidence_cli(
    args: argparse.Namespace,
    conv_id: str,
    payload: Dict[str, Any],
    stdin_parse_error: bool,
) -> int:
    """Gestisce il sottocomando stop-evidence in fail-closed senza auto-allow su ripetizioni."""
    import hashlib
    from pathlib import Path

    from _internal.nk_hook_gate.constants import (
        _CERT_RE,
        _SCRIPT_DIR,
        _WORKSPACE_ROOT as _WS_PATH,
        _strip_markdown_code_spans,
    )
    from _internal.nk_hook_gate.integrity_and_fasttrack import (
        _extract_last_planner_message,
    )
    from _internal.nk_hook_gate.json_io import (
        _get_hooks_temp_dir,
        _is_path_reparse_point,
        _log_shadow_decision,
        _read_json_safe,
        _write_json_atomic_safe,
    )
    from _internal.nk_hook_gate.stop_evidence import _maybe_spawn_stop_idle_checkpoint

    proj_root = _resolve_proj_root_path(args.project_root, payload)
    retry_file = _get_hooks_temp_dir() / f"stop_retry_{conv_id}.json"

    if stdin_parse_error:
        warn_malformed = (
            "[RULE-EVIDENCE] Malformed JSON payload on Stop hook (fail-closed)."
        )
        if args.enforce_stop and not args.shadow:
            rdata = _read_json_safe(retry_file)
            prev_count = int(rdata.get("count", 0)) if isinstance(rdata, dict) else 0
            _write_json_atomic_safe(
                retry_file,
                {"last_msg_sha256": "malformed", "count": prev_count + 1},
            )
            print(
                json.dumps(
                    {"decision": "continue", "reason": warn_malformed},
                    ensure_ascii=True,
                )
            )
            return 0
        print(
            json.dumps(
                {"decision": "allow", "reason": warn_malformed}
                if args.native_contract
                else {"ephemeralMessage": warn_malformed},
                ensure_ascii=True,
            )
        )
        return 0

    raw_term = (
        payload.get("terminationReason")
        if "terminationReason" in payload
        else payload.get("termination_reason", "NO_TOOL_CALL")
    )
    term_reason = str(raw_term or "NO_TOOL_CALL").strip().upper() or "NO_TOOL_CALL"
    cont_active = bool(
        payload.get("continuationActive")
        if "continuationActive" in payload
        else payload.get("continuation_active", False)
    )
    fully_idle = bool(
        payload.get("fullyIdle")
        if "fullyIdle" in payload
        else payload.get("fully_idle", True)
    )

    if (
        cont_active
        or term_reason in ("ERROR", "USER_CANCELED", "INJECTED_RESPONSE")
        or term_reason.startswith(("MAX_", "TERMINAL_"))
    ):
        if (
            retry_file.exists()
            and not _is_path_reparse_point(retry_file.parent)
            and not _is_path_reparse_point(retry_file)
        ):
            try:
                retry_file.unlink(missing_ok=True)
            except Exception:
                pass
        print(
            json.dumps({"decision": "allow"}, ensure_ascii=True)
            if args.native_contract
            else "{}"
        )
        return 0

    msg = str(
        payload.get("content")
        or payload.get("message")
        or payload.get("response")
        or payload.get("last_assistant_message")
        or payload.get("lastAssistantMessage")
        or ""
    )
    tp_raw = payload.get("transcriptPath") or payload.get("transcript_path")
    tp_path: Optional[Path] = (
        Path(str(tp_raw))
        if tp_raw
        and Path(str(tp_raw)).is_file()
        and not _is_path_reparse_point(Path(str(tp_raw)))
        else None
    )

    for p_cand in (_WS_PATH / "scripts", _SCRIPT_DIR):
        if p_cand.exists() and str(p_cand) not in sys.path:
            sys.path.insert(0, str(p_cand))

    has_vez_key = "verifiedExitZero" in payload or "verified_exit_zero" in payload
    raw_vez = (
        payload.get("verifiedExitZero")
        if "verifiedExitZero" in payload
        else payload.get("verified_exit_zero")
    )
    if has_vez_key and raw_vez is not True:
        verified_ok = False
    else:
        verified_ok = False
        try:
            import nk_transcript_tools as _ntt

            if tp_path is None and not conv_id.startswith("default_"):
                loc_res, loc_code = _ntt.locate_transcript(None, conv_id)
                if loc_code == 0 and loc_res.get("transcript_path"):
                    cand_tp = Path(str(loc_res["transcript_path"]))
                    if cand_tp.is_file() and not _is_path_reparse_point(cand_tp):
                        tp_path = cand_tp

            if tp_path is not None and tp_path.is_file():
                if not msg:
                    msg = _extract_last_planner_message(tp_path)
                ev_res, _ = _ntt.check_evidence(tp_path, msg)
                verified_ok = bool(ev_res.get("passed", False)) and bool(
                    ev_res.get("verified_exit_zero", False)
                )
            elif has_vez_key and raw_vez is True:
                verified_ok = True
        except Exception:
            verified_ok = bool(has_vez_key and raw_vez is True and tp_path is None)

    if tp_path is not None and tp_path.is_file() and not msg:
        msg = _extract_last_planner_message(tp_path)

    if _CERT_RE.search(_strip_markdown_code_spans(msg)) and not verified_ok:
        warn_ev = "[RULE-EVIDENCE] Unverified PASS/CONVERGED_OPTIMAL claim detected."
        if args.shadow:
            _log_shadow_decision(
                conv_id, "stop-evidence", args.event, {"ephemeralMessage": warn_ev}
            )
        if args.enforce_stop and not args.shadow:
            msg_hash = hashlib.sha256(msg.encode("utf-8")).hexdigest()
            prev_count = 0
            rdata = _read_json_safe(retry_file)
            if rdata is not None:
                try:
                    prev_count = int(rdata.get("count", 0))
                except Exception:
                    prev_count = 0
            _write_json_atomic_safe(
                retry_file,
                {
                    "last_msg_sha256": msg_hash,
                    "msg_sha256": msg_hash,
                    "count": prev_count + 1,
                },
            )
            out_stop: Dict[str, Any] = {"decision": "continue", "reason": warn_ev}
            if not args.native_contract:
                out_stop["ephemeralMessage"] = warn_ev
            print(json.dumps(out_stop, ensure_ascii=True))
        elif args.native_contract:
            print(
                json.dumps({"decision": "allow", "reason": warn_ev}, ensure_ascii=True)
            )
        else:
            print(json.dumps({"ephemeralMessage": warn_ev}, ensure_ascii=True))
    else:
        if (
            retry_file.exists()
            and not _is_path_reparse_point(retry_file.parent)
            and not _is_path_reparse_point(retry_file)
        ):
            try:
                retry_file.unlink(missing_ok=True)
            except Exception:
                pass
        if (
            term_reason == "NO_TOOL_CALL"
            and fully_idle
            and not cont_active
            and not args.shadow
        ):
            _maybe_spawn_stop_idle_checkpoint(conv_id, proj_root, tp_path, payload)
        print(
            json.dumps({"decision": "allow"}, ensure_ascii=True)
            if args.native_contract
            else "{}"
        )
    return 0
