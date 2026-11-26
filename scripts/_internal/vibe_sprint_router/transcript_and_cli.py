"""Parsing transcript, autotest e dispatcher CLI di vibe_sprint_router."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.paths import get_hooks_temp_dir_common
from _internal.nk_common.transcript_io import normalize_prompt_for_hash
from _internal.vibe_sprint_router.cli_handlers import (
    _extract_user_text_from_record,  # noqa: F401
    _facade_attr,
    _read_latest_user_input_from_transcript,  # noqa: F401
    _resolve_effective_cli_prompt,
)
from _internal.vibe_sprint_router.constants_core import _normalize_explicit_mode
from _internal.vibe_sprint_router.router_core import VibeSprintRouter


def run_test() -> int:
    """Esegue l'autotest rapido del router Mode C, Mode D e Meta-Prompt Gate."""
    router = VibeSprintRouter()
    code_sample = '''
def calculate_vat(amount: float, rate: float = 0.22) -> float:
    """Calcola l'IVA per una transazione."""
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    return round(amount * rate, 2)
'''
    res = router.compute_ast_risk_score(code_sample, "tax_calculator.py")
    if res["mode_eligible"] is not True:
        raise AssertionError(f"Expected mode_eligible is True, got {res['mode_eligible']!r}")
    if res["max_depth"] < 2:
        raise AssertionError(f"Expected max_depth >= 2, got {res['max_depth']!r}")
    spec = router.generate_inline_micro_spec("src_app/utils/tax.py", "Add VAT calculation", res)
    if "NK-VIBE-SPRINT-SPEC" not in spec:
        raise AssertionError("Missing NK-VIBE-SPRINT-SPEC in micro_spec")
    disc = router.classify_prompt_intent("Esegui audit e benchmark copertura bandi")
    if disc["recommended_mode"] != "mode_d":
        raise AssertionError(f"Expected mode_d, got {disc['recommended_mode']!r}")
    if "domain_id" not in disc:
        raise AssertionError("Missing domain_id in classification result")
    audit_tas = router.classify_prompt_intent(
        "Analizza refactoring recente, individua incongruenze ed esegui controllo TAS"
    )
    if audit_tas["domain_id"] != "DOM-04":
        raise AssertionError(f"Expected DOM-04, got {audit_tas['domain_id']!r}")
    if audit_tas["primary_agent"] != "NK-Security-Auditor":
        raise AssertionError(f"Expected NK-Security-Auditor, got {audit_tas['primary_agent']!r}")
    env = router.build_meta_prompt_envelope("Analizza primaLa struttura e l'implementazione attuale")
    if env["fsm_state"] != "BYPASSED":
        raise AssertionError(f"Expected BYPASSED, got {env['fsm_state']!r}")
    if env["gate_mode"] != "SINGLE_GATE_MODE_D":
        raise AssertionError(f"Expected SINGLE_GATE_MODE_D, got {env['gate_mode']!r}")
    if env["bypass_reason"] != "READONLY_MODE_D_BYPASS":
        raise AssertionError(f"Expected READONLY_MODE_D_BYPASS, got {env['bypass_reason']!r}")
    env_forced = router.build_meta_prompt_envelope(
        "Analizza primaLa struttura e l'implementazione attuale", auto_bypass_readonly=False
    )
    if env_forced["fsm_state"] != "AWAIT_CONFIRM":
        raise AssertionError(f"Expected AWAIT_CONFIRM, got {env_forced['fsm_state']!r}")
    if len(env["intent_hash_sha256"]) != 64:
        raise AssertionError("Expected 64-char SHA-256 intent_hash_sha256")
    if "INTRINSIC_BOOST" not in env["intrinsic_protocols"]:
        raise AssertionError("Expected INTRINSIC_BOOST in intrinsic_protocols")
    print(f"VibeSprintRouter test PASS: Risk {res['risk_score']} | Depth {res['max_depth']}")
    return 0


def _persist_l0_gate_state(
    effective_prompt: str, envelope: Dict[str, Any], args: Any
) -> None:
    """Salva atomicamente lo stato L0 gate per la conversazione corrente."""
    try:
        raw_cid = (
            getattr(args, "conversation_id", None)
            or os.environ.get("NK_CONVERSATION_ID")
            or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
            or "default"
        )
        conv_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw_cid).strip()) or "default"
        hooks_dir = get_hooks_temp_dir_common(create=True)
        norm_p = normalize_prompt_for_hash(effective_prompt)
        turn_sha = hashlib.sha256(norm_p.encode("utf-8")).hexdigest()
        payload = {
            "turn_prompt_sha256": turn_sha,
            "brief_id": str(envelope.get("brief_id") or ""),
            "fsm_state": str(envelope.get("fsm_state") or ""),
            "bypassed": bool(envelope.get("bypassed", False)),
            "classified_track": str(envelope.get("classified_track") or ""),
            "rsi_profile": str(envelope.get("rsi_profile") or ""),
            "lane_id": getattr(args, "lane_id", None),
            "ts": time.time(),
        }
        atomic_write_json(hooks_dir / f"l0_gate_{conv_id}.json", payload)
    except Exception:
        pass


def _build_router_for_cli(args: Any) -> Any:
    """Istanzia VibeSprintRouter propagando --lane-id solo se specificato."""
    router_cls = _facade_attr("VibeSprintRouter", VibeSprintRouter)
    lane_id = getattr(args, "lane_id", None)
    return router_cls(lane_id=lane_id) if lane_id else router_cls()


def dispatch_router_cli(args: argparse.Namespace) -> int:
    """Esegue il comando CLI parsato da vibe_sprint_router.main."""
    if args.test:
        return _facade_attr("run_test", run_test)()

    router = _build_router_for_cli(args)
    try:
        effective_prompt = _facade_attr(
            "_resolve_effective_cli_prompt", _resolve_effective_cli_prompt
        )(args, workspace_root=router.workspace_root)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.validate_generated_prompt is not None:
        target_lint_input = (
            effective_prompt
            if args.validate_generated_prompt == "__USE_PROMPT__"
            else args.validate_generated_prompt
        )
        lint_res = router.validate_generated_prompt(target_lint_input, mode=args.mode or "auto")
        if args.json:
            print(json.dumps(lint_res, indent=2, ensure_ascii=False))
        else:
            status_str = "PASS" if lint_res["valid"] else "FAIL"
            print(f"[NK-PROMPT-LINTER] Status: {status_str} | Violations: {lint_res['violation_count']}")
            for v in lint_res["violations"]:
                print(f"  - [{v['id']}] ({v['severity']}): {v['msg']}")
        return 0 if lint_res["valid"] else 1

    if args.meta_prompt_gate or args.no_gate:
        envelope = router.build_meta_prompt_envelope(
            effective_prompt,
            gate_enabled=not args.no_gate,
            gate_mode="OFF" if args.no_gate else "CONFIRM",
            files=args.files,
            compact=bool(args.compact),
            auto_bypass_readonly=not bool(args.force_gate),
            mode=args.mode,
            changed_lines=args.changed_lines,
            conversation_id=getattr(args, "conversation_id", None),
        )
        if args.meta_prompt_gate:
            _persist_l0_gate_state(effective_prompt, envelope, args)
        if args.json:
            print(json.dumps(envelope, indent=2 if not args.compact else None, ensure_ascii=False))
        elif args.compact:
            print(
                f"[L0-COMPACT] {envelope['brief_id']} | {envelope['fsm_state']} | "
                f"{envelope['recommended_mode']} | {envelope['primary_agent']}"
            )
        else:
            protos = ",".join(envelope.get("intrinsic_protocols", []))
            print(
                f"[META-PROMPT-GATE] Brief: {envelope['brief_id']} | "
                f"State: {envelope['fsm_state']} | Mode: {envelope['recommended_mode']} | "
                f"Protocols: {protos} | Scope: {envelope.get('bypass_scope', 'NONE')} | "
                f"Agent: {envelope['primary_agent']} | SHA256: {envelope['intent_hash_sha256'][:12]}"
            )
            print()
            print(envelope["rendered_markdown"])
        return 0

    if args.files:
        explicit_cli_mode = _normalize_explicit_mode(args.mode)
        results: List[Dict[str, Any]] = []
        for file_arg in args.files:
            p = Path(file_arg)
            if not p.is_absolute():
                p = (router.workspace_root / p).resolve()
            if p.exists() and p.is_file():
                info = router.compute_ast_risk_score(p.read_text(encoding="utf-8", errors="replace"), p.name)
            else:
                info = router.compute_ast_risk_score("", p.name)
            if args.changed_lines is not None:
                info["changed_lines"] = max(0, int(args.changed_lines))
                if args.changed_lines > router.MODE_C_MAX_LOC and info["recommended_mode"] == "mode_c":
                    info["recommended_mode"] = "mode_b"
                    info["mode_eligible"] = False
                    info["fast_bypass_eligible"] = False
                    info["reason"] = f"Escalated from Mode C to Mode B due to changed_lines={args.changed_lines} > 150"
            if explicit_cli_mode is not None:
                info["recommended_mode"] = explicit_cli_mode
                info["mode_eligible"] = explicit_cli_mode == "mode_c"
                info["fast_bypass_eligible"] = bool(info["fast_bypass_eligible"] and explicit_cli_mode == "mode_c")
            info["file"] = str(file_arg)
            info["micro_spec"] = router.generate_inline_micro_spec(str(file_arg), effective_prompt, info)
            results.append(info)
        payload: Dict[str, Any] = {"files": results}
        if args.capsule:
            payload["tier1_capsule"] = router.load_prewarmed_capsule(compact=bool(args.compact))
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for item in results:
                print(item["micro_spec"])
        return 0

    intent = router.classify_prompt_intent(
        effective_prompt, files=args.files, changed_lines=args.changed_lines, mode=args.mode
    )
    prompt_explicit = (
        args.classify_prompt is not None
        or args.discovery_check
        or args.changed_lines is not None
        or args.mode is not None
        or args.prompt_file is not None
        or args.stdin
        or effective_prompt != "Vibe Sprint Change"
    )
    if prompt_explicit or intent["is_discovery"]:
        if args.capsule:
            intent["tier1_capsule"] = router.load_prewarmed_capsule(compact=bool(args.compact))
        if args.json:
            print(json.dumps(intent, indent=2, ensure_ascii=False))
        else:
            print(
                f"[{intent['mode_label']}] | Mode: {intent['recommended_mode']} | "
                f"Agent: {intent['primary_agent']} | Subagent: {intent['native_subagent']} | "
                f"Domain: {intent['domain_id']}"
            )
        return 0

    if args.capsule:
        print(json.dumps(router.load_prewarmed_capsule(compact=bool(args.compact)), indent=2, ensure_ascii=False))
        return 0

    print("VibeSprintRouter CLI ready. Use --test to validate.")
    return 0
