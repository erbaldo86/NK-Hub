"""Valutatore Z1/Z2/Z3 e loop principale nk_acs_fastguard (pure stdlib)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_acs_fastguard.compaction import (
    _advance_cursor,
    _is_subagent_transcript,
)
from _internal.nk_acs_fastguard.constants import (
    _Z1_STEPS,
    _Z3_STEPS,
    _fg_attr,
    _load_acs_thresholds,
    _read_stdin_safe,
    _reconfigure_streams,
    _warn_stderr,
)
from _internal.nk_acs_fastguard.state_rmw import (
    _acquire_fastguard_mutex,
    _candidate_roots,
    _get_hooks_temp_dir,
    _load_state,
    _load_state_with_exists,
    _persist_state_or_warn,
    _release_fastguard_mutex,
    _resolve_conv_id,
    _resolve_eff_root,
    _resolve_explicit_conv_id,
    _resolve_transcript_path,
)
from _internal.nk_acs_fastguard.z2_and_l0 import (
    _check_l0_gate_one_shot,
    _has_active_wal,
    _is_batch_mutex_busy,
    _is_l0_exempt_fast,
    _maybe_spawn_z2,
    _read_anchor_meta,
    _strip_xml_wrapper_fast,
)


def _parse_fastguard_args(
    argv: Optional[List[str]],
) -> Tuple[Optional[str], bool, Optional[str], Optional[str], Optional[str]]:
    """Parsing leggero da argv senza importare argparse/dataclasses/inspect/shutil."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    event: Optional[str] = None
    native_contract = False
    conv_id: Optional[str] = None
    transcript: Optional[str] = None
    project_root: Optional[str] = None
    i = 0
    n = len(args_list)
    while i < n:
        tok = args_list[i]
        if tok in ("-h", "--help"):
            print(
                "usage: nk_acs_fastguard.py [-h] [--event {PreInvocation,PostInvocation}] "
                "[--native-contract] [--conversation-id ID] [--transcript PATH] [--project-root ROOT]"
            )
            raise SystemExit(0)
        if tok == "--native-contract":
            native_contract = True
        elif tok.startswith("--event="):
            event = tok.split("=", 1)[1]
        elif tok == "--event" and i + 1 < n:
            i += 1
            event = args_list[i]
        elif tok.startswith("--conversation-id="):
            conv_id = tok.split("=", 1)[1]
        elif tok == "--conversation-id" and i + 1 < n:
            i += 1
            conv_id = args_list[i]
        elif tok.startswith("--transcript="):
            transcript = tok.split("=", 1)[1]
        elif tok == "--transcript" and i + 1 < n:
            i += 1
            transcript = args_list[i]
        elif tok.startswith("--project-root="):
            project_root = tok.split("=", 1)[1]
        elif tok == "--project-root" and i + 1 < n:
            i += 1
            project_root = args_list[i]
        i += 1
    if event is not None and event not in ("PreInvocation", "PostInvocation"):
        raise SystemExit(2)
    return event, native_contract, conv_id, transcript, project_root


def _format_hook_output(
    sys_msg: str, user_markdown: Optional[str], native_contract: bool
) -> Dict[str, Any]:
    """Costruisce il payload JSON nativo (injectSteps) oppure legacy compatibile."""
    meta = {"user_markdown": user_markdown} if user_markdown is not None else None
    if native_contract:
        msg_obj: Dict[str, Any] = {"systemMessage": sys_msg}
        if meta is not None:
            msg_obj["metadata"] = meta
        return {"injectSteps": [{"systemMessage": msg_obj}]}
    out: Dict[str, Any] = {"systemMessage": sys_msg}
    if meta is not None:
        out["metadata"] = meta
    return out


def _evaluate_fallback_no_transcript(
    roots: List[str],
    explicit_conv_id: Optional[str],
    event: str,
    native_contract: bool,
) -> int:
    """Gestisce il caso tp_path is None usando contatore fallback per conversazione valida."""
    if explicit_conv_id is None or explicit_conv_id.startswith("default_"):
        print("{}")
        return 0
    hooks_dir = _get_hooks_temp_dir()
    state_path = os.path.join(hooks_dir, f"fastguard_{explicit_conv_id}.json") if hooks_dir is not None else None
    fg_mutex: Optional[int] = _acquire_fastguard_mutex(explicit_conv_id)
    try:
        state = _load_state(state_path)
        cfg = _load_acs_thresholds(roots)
        if int(state.get("epoch_baseline_tokens", 0)) == 0 and cfg["epoch_baseline_tokens"] > 0:
            state["epoch_baseline_tokens"] = cfg["epoch_baseline_tokens"]
        fb_steps = int(state.get("fallback_steps", 0)) + 1
        state["fallback_steps"] = fb_steps
        fb_cfg = cfg["fallback_steps"]
        epoch = int(state.get("compaction_epoch", 0))
        out_fb: Dict[str, Any] = {}
        if event == "PreInvocation":
            if fb_steps >= int(fb_cfg.get("z3", _Z3_STEPS)):
                if int(state.get("z3_pre_epoch", -1)) != epoch:
                    state["z3_pre_epoch"] = epoch
                    state["z1_epoch"] = epoch
                    out_fb = _format_hook_output(
                        f"[ACS-Z3 CRITICO] Soglia fallback raggiunta ({fb_steps} step senza transcript). Concludi il turno senza avviare task multi-file.",
                        None, native_contract,
                    )
            elif fb_steps >= int(fb_cfg.get("z1", _Z1_STEPS)):
                if int(state.get("z1_epoch", -1)) != epoch:
                    state["z1_epoch"] = epoch
                    out_fb = _format_hook_output(
                        f"[ACS-Z1 SOFT-FOLDING] Fallback a {fb_steps} step senza transcript. Usa letture mirate, invoke_subagent e risposte compatte.",
                        None, native_contract,
                    )
        _persist_state_or_warn(state_path, state)
        print(json.dumps(out_fb, ensure_ascii=True))
    finally:
        _release_fastguard_mutex(fg_mutex)
    return 0


def _update_velocity_delta(state: Dict[str, Any], cur_tokens: int, prev_actual: int) -> None:
    if cur_tokens > 0:
        state["last_velocity_delta"] = max(0, cur_tokens - prev_actual) if prev_actual > 0 else 0
        state["prev_actual_tokens"] = cur_tokens
    elif prev_actual == 0 and int(state.get("last_velocity_delta", 0)) != 0:
        state["last_velocity_delta"] = 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point rapido della guardia ACS PreInvocation e PostInvocation."""
    _reconfigure_streams()
    arg_event, native_contract, arg_conv_id, arg_transcript, arg_project_root = _parse_fastguard_args(argv)
    payload: Dict[str, Any] = {}
    try:
        cleaned_stdin = _read_stdin_safe().lstrip("\ufeff").strip()
        if cleaned_stdin:
            loaded = json.loads(cleaned_stdin)
            if isinstance(loaded, dict):
                payload = loaded
    except Exception as exc:
        _warn_stderr("stdin_parse_failed", f"reason={exc}")
        print("{}")
        return 0

    event = arg_event or str(payload.get("hookEventName") or payload.get("hook_event_name") or "PreInvocation")
    if event not in ("PreInvocation", "PostInvocation"):
        print("{}")
        return 0

    fg_mutex: Optional[int] = None
    try:
        explicit_conv_id = _fg_attr("_resolve_explicit_conv_id", _resolve_explicit_conv_id)(arg_conv_id, payload)
        tp_path = _resolve_transcript_path(arg_transcript, payload, explicit_conv_id)
        eff_root = _resolve_eff_root(payload, arg_project_root)
        roots = _candidate_roots(eff_root)

        if tp_path is None:
            return _evaluate_fallback_no_transcript(roots, explicit_conv_id, event, native_contract)

        if _is_subagent_transcript(tp_path):
            print("{}")
            return 0

        cfg = _load_acs_thresholds(roots)
        conv_id = explicit_conv_id if explicit_conv_id is not None else _resolve_conv_id(arg_conv_id, payload, eff_root)
        hooks_dir = _get_hooks_temp_dir()
        state_path = os.path.join(hooks_dir, f"fastguard_{conv_id}.json") if hooks_dir is not None else None
        fg_mutex = _acquire_fastguard_mutex(conv_id)
        state, state_exists, state_recovered = _load_state_with_exists(state_path)
        if not state_exists and int(cfg["epoch_baseline_tokens"]) > 0:
            state["epoch_baseline_tokens"] = int(cfg["epoch_baseline_tokens"])
        state_before = dict(state)

        prev_actual = int(state.get("prev_actual_tokens", 0))
        old_epoch = int(state.get("compaction_epoch", 0))
        _advance_cursor(tp_path, state)
        cur_tokens = int(state.get("last_actual_tokens", 0))
        steps = int(state.get("steps", 0))
        epoch = int(state.get("compaction_epoch", 0))
        if epoch != old_epoch or int(state.get("prev_actual_tokens", 0)) == 0:
            prev_actual = 0

        velocity_trigger = (
            prev_actual > 0
            and (cur_tokens - prev_actual) >= int(cfg["vel_delta"])
            and (cur_tokens >= int(cfg["vel_cur"]) or steps >= int(cfg["vel_steps"]))
        )
        is_z3 = cur_tokens >= int(cfg["z3_tokens"]) or steps >= int(cfg["z3_steps"]) or velocity_trigger
        is_z2 = is_z3 or cur_tokens >= int(cfg["z2_tokens"]) or steps >= int(cfg["z2_steps"])
        is_z1 = cur_tokens >= int(cfg["z1_tokens"]) or steps >= int(cfg["z1_steps"])
        spawn_fn = _fg_attr("_maybe_spawn_z2", _maybe_spawn_z2)

        out: Dict[str, Any] = {}
        if event == "PreInvocation":
            msgs: List[str] = []
            l0_msg = _check_l0_gate_one_shot(tp_path, conv_id, hooks_dir, state, epoch)
            if l0_msg:
                msgs.append(l0_msg)
            cp_off = int(state.get("checkpoint_byte_offset", 0))
            if cp_off > 0 and cp_off != int(state.get("reanchor_emitted_offset", -1)):
                state["reanchor_emitted_offset"] = cp_off
                msgs.append("[RULE-REHYDRATE] Compaction rilevata: leggi nk_tracking/active_context.md prima di continuare.")
            if is_z3:
                spawn_fn(roots, tp_path, conv_id, payload, state, cooldown_s=float(cfg["cooldown_s"]))
                if int(state.get("z3_pre_epoch", -1)) != epoch:
                    state["z3_pre_epoch"] = epoch
                    state["z1_epoch"] = epoch
                    msgs.append(f"[ACS-Z3 CRITICO] Contesto critico ({cur_tokens} token, {steps} step). Concludi il turno senza avviare task multi-file.")
            elif is_z2:
                spawn_fn(roots, tp_path, conv_id, payload, state, cooldown_s=float(cfg["cooldown_s"]))
            elif is_z1 and int(state.get("z1_epoch", -1)) != epoch:
                state["z1_epoch"] = epoch
                msgs.append(f"[ACS-Z1 SOFT-FOLDING] Contesto a {cur_tokens} token ({steps} step). Usa letture mirate, invoke_subagent e risposte compatte.")
            if msgs:
                out = _format_hook_output("\n".join(msgs), None, native_contract)
        else:
            if is_z3:
                if int(state.get("z3_post_epoch", -1)) != epoch:
                    state["z3_post_epoch"] = epoch
                    user_md = (
                        f"### [ACS-Z3] Saturazione Critica Contesto ({cur_tokens:,} token / {steps} step)\n\n"
                        "Auto-checkpoint avviato in background. Concludi la fase corrente e riparti da `active_context.md`."
                    )
                    out = _format_hook_output("", user_md, native_contract)
                spawn_fn(roots, tp_path, conv_id, payload, state, cooldown_s=float(cfg["cooldown_s"]))
            elif is_z2:
                spawn_fn(roots, tp_path, conv_id, payload, state, cooldown_s=float(cfg["cooldown_s"]))

        _update_velocity_delta(state, cur_tokens, prev_actual)
        if not state_exists or state_recovered or state != state_before:
            _persist_state_or_warn(state_path, state)
        print(json.dumps(out, ensure_ascii=True))
    except Exception as exc:
        _warn_stderr("main_unexpected_error", f"event={event} reason={exc}")
        print("{}")
    finally:
        _release_fastguard_mutex(fg_mutex)
    return 0
