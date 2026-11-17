"""Dispatcher CLI lazy fast-path per HookGateV2 invocato da scripts/nk_hook_gate.py."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Dict

from _internal.nk_hook_gate.core_env import _READ_ONLY_TOOLS_SET
from _internal.nk_hook_gate.json_io import (
    _extract_args_dict,
    _extract_tool_identity,
    _has_unsafe_readonly_args,
    _log_shadow_decision,
    _read_fasttrack_streak,
    _read_stdin_payload_ex,
    _resolve_conv_id,
    _update_fasttrack_streak,
    _write_probe_record,
)
from _internal.nk_hook_gate.stop_evidence_cli import (
    _handle_stop_evidence_cli,
    _resolve_proj_root_path,
)

if TYPE_CHECKING:
    import argparse
else:
    from types import SimpleNamespace

    argparse = SimpleNamespace(Namespace=Any)


def _format_write_gate_output(
    res: Dict[str, Any], native_contract: bool
) -> Dict[str, Any]:
    """Normalizza la risposta write-gate secondo il contratto nativo ProtoJSON."""
    if not native_contract:
        return res
    if "decision" not in res:
        return {"decision": "allow"}
    if res.get("reason"):
        return {"decision": str(res["decision"]), "reason": str(res["reason"])}
    return {"decision": str(res["decision"])}


def dispatch_hook_cli(args: argparse.Namespace) -> int:
    """Esegue il sottocomando CLI HookGateV2 con caricamento lazy per fast-path < 80ms."""
    skip_stdin = args.subcommand == "integrity" or (
        args.event == "Unknown"
        and bool(args.target or args.command or args.init or args.check)
    )
    if skip_stdin:
        payload, stdin_parse_error = {}, False
    else:
        payload, stdin_parse_error = _read_stdin_payload_ex()

    conv_id = _resolve_conv_id(args.conversation_id, payload)

    if args.subcommand == "probe" or os.environ.get(
        "NK_HOOK_DEBUG", "0"
    ).strip().lower() in ("1", "true", "yes"):
        _write_probe_record(conv_id, args.event, payload)

    if args.subcommand == "probe":
        print("{}")
        return 0

    if args.subcommand == "fasttrack":
        if args.native_contract and args.event == "PreInvocation":
            streak_val = _read_fasttrack_streak(conv_id)
            if streak_val > 12:
                warn_ft = (
                    f"[RULE-01] Fast-Track streak ({streak_val} > 12). "
                    "Delegate work via invoke_subagent."
                )
                if args.shadow:
                    _log_shadow_decision(
                        conv_id, "fasttrack", args.event, {"ephemeralMessage": warn_ft}
                    )
                print(
                    json.dumps(
                        {"injectSteps": [{"ephemeralMessage": warn_ft}]},
                        ensure_ascii=True,
                    )
                )
            else:
                print("{}")
            return 0

        res = _update_fasttrack_streak(conv_id, payload)
        if args.native_contract and args.event == "PostToolUse":
            print("{}")
            return 0
        if args.native_contract and res.get("ephemeralMessage"):
            print(
                json.dumps(
                    {"injectSteps": [{"ephemeralMessage": res["ephemeralMessage"]}]},
                    ensure_ascii=True,
                )
            )
            return 0
        print(json.dumps(res, ensure_ascii=True))
        return 0

    if args.subcommand == "write-gate":
        malformed_pre = stdin_parse_error or (
            args.event == "PreToolUse"
            and not payload
            and not (args.target or args.command)
        )
        if malformed_pre:
            res: Dict[str, Any] = {
                "decision": "deny",
                "reason": "Malformed or empty JSON payload on PreToolUse hook (fail-closed).",
            }
        else:
            if (
                not args.shadow
                and not args.strict_external
                and not args.target
                and not args.command
                and not args.content
            ):
                tool_call, tool_name = _extract_tool_identity(payload)
                if tool_name.lower() in _READ_ONLY_TOOLS_SET:
                    tool_args = _extract_args_dict(payload, tool_call)
                    if not _has_unsafe_readonly_args(tool_args):
                        out_fast = {"decision": "allow"} if args.native_contract else {}
                        print(json.dumps(out_fast, ensure_ascii=True))
                        return 0

            from _internal.nk_hook_gate.write_gate import _handle_write_gate

            res = _handle_write_gate(
                payload,
                _resolve_proj_root_path(args.project_root, payload),
                args.strict_external,
                args.target,
                args.command,
                args.content,
            )

        if args.shadow:
            if res.get("decision") in ("deny", "ask"):
                _log_shadow_decision(conv_id, "write-gate", args.event, res)
            out_wg = {"decision": "allow"} if args.native_contract else {}
            print(json.dumps(out_wg, ensure_ascii=True))
            return 0

        out_res = _format_write_gate_output(res, args.native_contract)
        print(json.dumps(out_res, ensure_ascii=True))
        return 0

    if args.subcommand == "session-start":
        from _internal.nk_hook_gate.integrity_and_fasttrack import _handle_integrity

        _handle_integrity(
            conv_id,
            _resolve_proj_root_path(args.project_root, payload),
            init_mode=True,
            check_mode=False,
        )
        raw_profile = os.environ.get("NK_MODEL_PROFILE", "generation").strip() or "generation"
        profile_low = raw_profile.lower()
        profile_label = profile_low.capitalize()
        if args.native_contract:
            msg_txt = (
                f"[NK-HUB] {profile_label} profile active. [RULE-00.6] Emit visible L0 "
                "Conceptual Mirror in content before ask_question (content_len > 0 mandatory)."
            )
            print(
                json.dumps(
                    {"injectSteps": [{"systemMessage": {"systemMessage": msg_txt}}]},
                    ensure_ascii=True,
                )
            )
        else:
            print(
                json.dumps(
                    {"status": "OK", "profile": profile_low, "pythonutf8": "1"},
                    ensure_ascii=True,
                )
            )
        return 0

    if args.subcommand == "integrity":
        from _internal.nk_hook_gate.integrity_and_fasttrack import _handle_integrity

        res, code = _handle_integrity(
            conv_id,
            _resolve_proj_root_path(args.project_root, payload),
            args.init,
            args.check,
        )
        print(json.dumps(res, ensure_ascii=True))
        return code

    if args.subcommand == "stop-evidence":
        return _handle_stop_evidence_cli(args, conv_id, payload, stdin_parse_error)

    print("{}")
    return 0


__all__ = [
    "_format_write_gate_output",
    "_handle_stop_evidence_cli",
    "_resolve_proj_root_path",
    "dispatch_hook_cli",
]
