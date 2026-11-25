#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Bootstrap Gate Fast-Stat per NK Hub Generation 1.0.0-Generation.
Modulo: nk_session_bootstrap.py.
@domain_id: DOM-01
Implementa [RULE-00.4], [RULE-00.5], BOOT-01, mutex canonico 2PC, quarantena WAL e --handoff-verify.
"""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from _internal.nk_session_bootstrap.bootstrap import NKSessionBootstrap  # noqa: E402
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
    _register_facade_module,
    reconfigure_streams,
)

_register_facade_module(sys.modules.get(__name__))

_B = "_internal.nk_session_bootstrap.bootstrap"
_HV = "_internal.nk_session_bootstrap.handoff_verify"
_CH = "_internal.nk_session_bootstrap.compaction_and_head"
_C = "_internal.nk_session_bootstrap.constants"
_RT = "_internal.nk_session_bootstrap.resilience_tail"

_LAZY_EXPORT_MAP: Dict[str, tuple[str, str]] = {
    "_compute_fast_traffic_light": (_CH, "_compute_fast_traffic_light"),
    "_is_compaction_record_dict": (_CH, "_is_compaction_record_dict"),
    "NKContextSentry": (_C, "NKContextSentry"),
    "_get_win32_k32": (_C, "_get_win32_k32"),
    "_k32": (_C, "_k32"),
    "_k32_initialized": (_C, "_k32_initialized"),
    "_parse_iso_epoch": (_C, "_parse_iso_epoch"),
    "_register_facade_module": (_C, "_register_facade_module"),
    "_scripts_dir": (_C, "_scripts_dir"),
    "_staging_scripts_dir": (_C, "_staging_scripts_dir"),
    "_valid_token_int": (_C, "_valid_token_int"),
    "_workspace_root": (_C, "_workspace_root"),
    "_analyze_step_record_resilience": (_RT, "_analyze_step_record_resilience"),
    "_build_context_warning": (_RT, "_build_context_warning"),
    "_extract_record_context_tokens": (_RT, "_extract_record_context_tokens"),
    "_inspect_tail_resilience_risks": (_RT, "_inspect_tail_resilience_risks"),
}


def run_bootstrap(
    workspace_root: Optional[Path] = None,
    transcript_path: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    fast_stat: bool = True,
    prompt: Optional[str] = None,
    handoff_verify: bool = False,
    handoff_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Delega pigramente l'esecuzione bootstrap Fast-Stat preservando il contratto facciata."""
    return importlib.import_module(_B).run_bootstrap(
        workspace_root=workspace_root, transcript_path=transcript_path, conversation_id=conversation_id,
        fast_stat=fast_stat, prompt=prompt, handoff_verify=handoff_verify, handoff_file=handoff_file,
    )


def verify_fast_stat_invariant(workspace_root: Optional[Path] = None, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Delega pigramente la verifica dell'invariante Fast-Stat."""
    return importlib.import_module(_B).verify_fast_stat_invariant(workspace_root=workspace_root, conversation_id=conversation_id)


def verify_project_isolation(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Delega pigramente la verifica dell'isolamento della root."""
    return importlib.import_module(_B).verify_project_isolation(workspace_root=workspace_root)


def enforce_wal_hygiene(workspace_root: Optional[Path] = None, ttl_seconds: float = 60.0) -> Dict[str, Any]:
    """Delega pigramente la bonifica dei file WAL scaduti."""
    return importlib.import_module(_B).enforce_wal_hygiene(workspace_root=workspace_root, ttl_seconds=ttl_seconds)


def verify_handoff_envelope_live(
    hub_root: Path,
    project_root: Path,
    prompt_text: Optional[str] = None,
    handoff_file: Optional[Path] = None,
    transcript_path: Optional[Path] = None,
    receiver_cid: Optional[str] = None,
) -> Dict[str, Any]:
    """Delega pigramente verify_handoff_envelope_live evitando import di handoff_verify su Fast-Stat."""
    return importlib.import_module(_HV).verify_handoff_envelope_live(
        hub_root=hub_root, project_root=project_root, prompt_text=prompt_text,
        handoff_file=handoff_file, transcript_path=transcript_path, receiver_cid=receiver_cid,
    )


def get_canonical_repo_batch_mutex_name(root: Path) -> str:
    """Calcola il nome mutex canonico 2PC delegando al modulo leggero constants."""
    return importlib.import_module(_C).get_canonical_repo_batch_mutex_name(root)


def __getattr__(name: str) -> Any:
    """Risolve pigramente le costanti e gli helper diagnostici secondari."""
    spec = _LAZY_EXPORT_MAP.get(name)
    if spec is not None:
        val = getattr(importlib.import_module(spec[0]), spec[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def _first_str_value(mapping: Dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    """Restituisce la prima stringa non vuota associata alle chiavi fornite."""
    for key in keys:
        raw = mapping.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _read_hook_stdin_fields(
    conv_id: Optional[str], transcript_arg: Optional[str], prompt_arg: Optional[str]
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Estrae conversationId, transcriptPath e prompt dallo stdin hook JSON."""
    if sys.stdin.isatty():
        return conv_id, transcript_arg, prompt_arg
    try:
        raw_stdin = sys.stdin.read()
        hp = json.loads(raw_stdin) if raw_stdin.strip() else None
    except (OSError, ValueError):
        # Ignora payload stdin non JSON in modalita hook mantenendo gli argomenti CLI.
        return conv_id, transcript_arg, prompt_arg
    if not isinstance(hp, dict):
        return conv_id, transcript_arg, prompt_arg
    conv_id = conv_id or _first_str_value(hp, ("conversationId", "conversation_id"))
    transcript_arg = transcript_arg or _first_str_value(hp, ("transcriptPath", "transcript_path"))
    if prompt_arg is None:
        prompt_arg = _first_str_value(hp, ("lastUserInput", "last_user_input", "prompt", "userPrompt", "user_prompt"))
    return conv_id, transcript_arg, prompt_arg


def _print_bootstrap_human_report(res: Dict[str, Any]) -> None:
    """Formatta su stdout il riepilogo leggibile dei controlli Bootstrap Fast-Stat."""
    status = res["status"]
    elapsed_ms = float(res.get("duration_ms", 0.0))
    checks = res.get("checks", {})
    iso_ok = checks.get("project_isolation", {}).get("passed", True)
    wal_ok = checks.get("wal_hygiene", {}).get("passed", True)
    ctx_st = str(checks.get("context_sentry", {}).get("status", "GREEN"))
    ob_label = "BYPASSED" if res.get("onboarding_bypass") == "ONBOARDING_BYPASS_VERIFIED" else "GATE_ACTIVE"
    print(f"[BOOTSTRAP: {status} | {elapsed_ms:.2f}ms | Root: {'PASS' if iso_ok else 'FAIL'} | WAL: {'PASS' if wal_ok else 'FAIL'} | Context: {ctx_st} | ONBOARDING: {ob_label}]")
    hv_chk = checks.get("handoff_verify")
    if isinstance(hv_chk, dict):
        print(f"[HANDOFF_VERIFY: {hv_chk.get('status', 'UNKNOWN')} | Provenance: {hv_chk.get('provenance', '')} | Cache: {hv_chk.get('cache_mode', '')}]")
    for check_name, check_data in checks.items():
        print(f"  - {check_name}: {check_data.get('details', check_data)}")
    if res.get("staging_dirty_warning"):
        print("  - staging_dirty_warning: True (.staging contains pending files)")
    for issue in res.get("issues", []):
        print(f"  ⚠️ [ALERT] {issue}")


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il Bootstrap Gate Fast-Stat di NK Hub Generation."""
    import argparse

    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    reconfigure_streams()
    parser = argparse.ArgumentParser(description="NK Hub Generation Fast-Stat Session Bootstrap Gate 1.0.0-Generation")
    parser.add_argument("--force-full", action="store_true", help="Ignora la cache Fast-Stat ed esegue la scansione completa")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato in formato JSON")
    parser.add_argument("--conversation-id", type=str, default=None, help="ID della conversazione attiva")
    parser.add_argument("--transcript", type=str, default=None, help="Percorso esplicito del file transcript.jsonl")
    parser.add_argument("--prompt", type=str, default=None, help="Prompt utente esplicito per verifica single-pass onboarding (BOOT-01)")
    parser.add_argument("--hook", action="store_true", help="Esegue il bootstrap in modalita hook SessionStart")
    parser.add_argument("--project-root", type=str, default=None, help="Percorso radice del workspace o progetto da verificare")
    parser.add_argument("--handoff-verify", action="store_true", help="Verifica live integrita, staging e SHA-256 dell'handoff ricevuto")
    parser.add_argument("--handoff-file", type=str, default=None, help="Percorso opzionale del file handoff da verificare")

    args = parser.parse_args(argv)
    conv_id, transcript_arg, prompt_arg = (
        _read_hook_stdin_fields(args.conversation_id, args.transcript, args.prompt)
        if args.hook
        else (args.conversation_id, args.transcript, args.prompt)
    )
    ws_root = Path(args.project_root).resolve() if args.project_root else None
    tp_path = Path(transcript_arg).resolve() if transcript_arg else None
    hf_path = Path(args.handoff_file).resolve() if args.handoff_file else None
    bootstrap = NKSessionBootstrap(
        workspace_root=ws_root,
        conversation_id=conv_id,
        transcript_path=tp_path,
        prompt=prompt_arg,
        hook_mode=bool(args.hook),
        handoff_verify=bool(args.handoff_verify),
        handoff_file=hf_path,
    )
    res = bootstrap.run_bootstrap(
        fast_stat=not args.force_full,
        prompt=prompt_arg,
        handoff_verify=bool(args.handoff_verify),
        handoff_file=hf_path,
    )
    if args.json or args.hook:
        print(json.dumps(res, indent=2))
    else:
        _print_bootstrap_human_report(res)
    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
