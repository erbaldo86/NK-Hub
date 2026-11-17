#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Bootstrap Gate Fast-Stat per NK Hub Generation 1.0.0-Generation.
Modulo: nk_session_bootstrap.py.
@domain_id: DOM-01
Implementa [RULE-00.4], [RULE-00.5], BOOT-01, mutex canonico 2PC e quarantena WAL.

Funzionalita principali:
1. Verifica invarianti Fast-Stat sotto 15 millisecondi su cache hit con TTL 900s.
2. Emette ONBOARDING_BYPASS_VERIFIED solo su vero trigger utente verificato (BOOT-01).
3. Sincronizza wal_hygiene col mutex canonico Global\\NK_RepoBatchLock_<sha256[:16]>.
4. Analizza rpc_stream_burst_risk solo su tool_calls reali di scrittura post-compattazione.
"""

from __future__ import annotations

import json
import os
import pkgutil
import sys
from pathlib import Path
from typing import List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc
    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
    _stg_nkc_dir = str(_SCRIPT_DIR / "_internal" / "nk_common")
    if isinstance(_stg_nkc.__path__, list):
        if _stg_nkc_dir in _stg_nkc.__path__:
            _stg_nkc.__path__.remove(_stg_nkc_dir)
        _stg_nkc.__path__.insert(0, _stg_nkc_dir)
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
init_nk_facade(__file__, pkg="nk_session_bootstrap")

from _internal.nk_session_bootstrap.bootstrap import (  # noqa: E402
    NKSessionBootstrap,
    enforce_wal_hygiene,
    run_bootstrap,
    verify_fast_stat_invariant,
    verify_project_isolation,
)
from _internal.nk_session_bootstrap.compaction_and_head import (  # noqa: E402
    _compute_fast_traffic_light,
    _is_compaction_record_dict,
)
from _internal.nk_session_bootstrap.constants import (  # noqa: E402
    BINARY_CHUNK_SIZE,
    FAST_CACHE_TTL_SECONDS,
    HUB_ROOT,
    MAX_EXACT_COUNT_BYTES,
    ONBOARDING_TRIGGERS,
    STATE_CACHE_TTL_SECONDS,
    SUPPORTED_MODEL_PROFILES,
    TAIL_READ_BYTES_LIMIT,
    TRANSCRIPT_MAX_AGE_SECONDS,
    _BOOTSTRAP_LOCK,
    _ERROR_ACCESS_DENIED,
    _INVALID_HANDLE_VALUE,
    _UNTRUSTED_COMPACTION_SOURCES,
    _UNTRUSTED_COMPACTION_TYPES,
    _WAIT_ABANDONED_0,
    _WAIT_OBJECT_0,
    NKContextSentry,
    _get_win32_k32,
    _k32,
    _k32_initialized,
    _parse_iso_epoch,
    _register_facade_module,
    _scripts_dir,
    _staging_scripts_dir,
    _valid_token_int,
    _workspace_root,
    get_canonical_repo_batch_mutex_name,
    reconfigure_streams,
)
from _internal.nk_session_bootstrap.resilience_tail import (  # noqa: E402
    _analyze_step_record_resilience,
    _build_context_warning,
    _extract_record_context_tokens,
    _inspect_tail_resilience_risks,
)

_register_facade_module(sys.modules.get(__name__))


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il Bootstrap Gate Fast-Stat di NK Hub Generation."""
    import argparse

    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="NK Hub Generation Fast-Stat Session Bootstrap Gate 1.0.0-Generation"
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Ignora la cache Fast-Stat ed esegue la scansione completa",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )
    parser.add_argument(
        "--conversation-id",
        type=str,
        default=None,
        help="ID della conversazione attiva per isolare cache e transcript",
    )
    parser.add_argument(
        "--transcript",
        type=str,
        default=None,
        help="Percorso esplicito del file transcript.jsonl",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Prompt utente esplicito per verifica single-pass onboarding (BOOT-01)",
    )
    parser.add_argument(
        "--hook",
        action="store_true",
        help="Esegue il bootstrap in modalita hook SessionStart",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Percorso radice del workspace o progetto da verificare",
    )

    args = parser.parse_args(argv)
    conv_id = args.conversation_id
    transcript_arg = args.transcript
    prompt_arg = args.prompt

    if args.hook and not sys.stdin.isatty():
        try:
            raw_stdin = sys.stdin.read()
            if raw_stdin.strip():
                hook_payload = json.loads(raw_stdin)
                if isinstance(hook_payload, dict):
                    raw_cid = str(
                        hook_payload.get("conversationId")
                        or hook_payload.get("conversation_id")
                        or ""
                    ).strip()
                    if raw_cid and not conv_id:
                        conv_id = raw_cid
                    raw_tp = str(
                        hook_payload.get("transcriptPath")
                        or hook_payload.get("transcript_path")
                        or ""
                    ).strip()
                    if raw_tp and not transcript_arg:
                        transcript_arg = raw_tp
                    if prompt_arg is None:
                        raw_hp_prompt = (
                            hook_payload.get("lastUserInput")
                            or hook_payload.get("last_user_input")
                            or hook_payload.get("prompt")
                            or hook_payload.get("userPrompt")
                            or hook_payload.get("user_prompt")
                        )
                        if isinstance(raw_hp_prompt, str) and raw_hp_prompt.strip():
                            prompt_arg = raw_hp_prompt
        except Exception:
            pass

    ws_root = Path(args.project_root).resolve() if args.project_root else None
    tp_path = Path(transcript_arg).resolve() if transcript_arg else None
    bootstrap = NKSessionBootstrap(
        workspace_root=ws_root,
        conversation_id=conv_id,
        transcript_path=tp_path,
        prompt=prompt_arg,
        hook_mode=bool(args.hook),
    )
    res = bootstrap.run_bootstrap(fast_stat=not args.force_full, prompt=prompt_arg)

    if args.json or args.hook:
        print(json.dumps(res, indent=2))
    else:
        status = res["status"]
        elapsed_ms = float(res.get("duration_ms", 0.0))
        checks = res.get("checks", {})
        iso_chk = checks.get("project_isolation", {})
        wal_chk = checks.get("wal_hygiene", {})
        ctx_chk = checks.get("context_sentry", {})
        hygiene = {"status": "PASS" if iso_chk.get("passed", True) else "FAIL"}
        wal_hygiene = {"status": "PASS" if wal_chk.get("passed", True) else "FAIL"}
        ctx_sentry = {"status": str(ctx_chk.get("status", "GREEN"))}
        ob_label = (
            "BYPASSED"
            if res.get("onboarding_bypass") == "ONBOARDING_BYPASS_VERIFIED"
            else "GATE_ACTIVE"
        )
        print(
            f"[BOOTSTRAP: {status} | {elapsed_ms:.2f}ms | Root: {hygiene['status']} | WAL: {wal_hygiene['status']} | Context: {ctx_sentry['status']} | ONBOARDING: {ob_label}]"
        )
        for check_name, check_data in checks.items():
            print(f"  - {check_name}: {check_data.get('details', check_data)}")
        if res.get("staging_dirty_warning"):
            print("  - staging_dirty_warning: True (.staging contains pending files)")
        for issue in res.get("issues", []):
            print(f"  ⚠️ [ALERT] {issue}")

    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
