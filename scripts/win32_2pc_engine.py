#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore transazionale Win32 Two-Phase Commit per NK Hub Generation 1.0.0-Generation.
Garantisce mutua esclusione rientrante, integrita SHA-256, rollback pre-immagine e Commit Train.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional


def _build_cli_parser() -> Any:
    """Costruisce il parser CLI senza caricare i sottomoduli 2PC su --help."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Win32 Two-Phase Commit (2PC) & Staging Promotion Engine 1.0.0-Generation",
    )
    parser.add_argument("--promote-staging", action="store_true", help="Promuove i file modificati da .staging alla produzione")
    parser.add_argument("--commit-train", action="store_true", help="Promuove una lane tramite Commit Train OCC, Re-Gate e CAS")
    parser.add_argument("--consolidate-sublanes", action="store_true", help="Fonde e promuove le sub-lane di parent-lane tramite 2PC")
    parser.add_argument("--parent-lane", type=str, default=None, help="Nome lane padre per consolidamento sub-lanes")
    parser.add_argument("--quarantine-staging", action="store_true", help="Sposta il contenuto corrente di .staging in quarantena isolata")
    parser.add_argument("--milestone", type=str, default=None, help="Milestone Anchor ID")
    parser.add_argument("--repo-root", type=str, default=None, help="Percorso alla radice del repository")
    parser.add_argument("--staging-dir", type=str, default=".staging", help="Nome della cartella di staging")
    parser.add_argument("--lane-id", type=str, default=None, help="ID lane isolata in .staging/lanes/<id>/")
    parser.add_argument("--base-seq", type=int, default=0, help="Sequenza T0 del Commit Train per controllo OCC")
    parser.add_argument("--git-sync", action="store_true", help="Esegue git add sui file promossi")
    parser.add_argument("--verify-baseline", action="store_true", help="Verifica l'assenza di regressioni sul baseline prima del commit")
    parser.add_argument("--keep-staging", action="store_true", help="Mantiene i file in .staging dopo la promozione")
    parser.add_argument("--allow-governance-override", action="store_true", help="Consente la promozione esplicita di file protetti previa motivazione audit")
    parser.add_argument("--override-reason", type=str, default=None, help="Motivazione obbligatoria (>= 8 caratteri) per --allow-governance-override")
    parser.add_argument("--governance-token", type=str, default=None, help="Token HMAC governance per --allow-governance-override")
    parser.add_argument("--sandbox-report", type=str, default=None, help="Percorso al report DAST/Sandbox da validare prima del commit")
    return parser


if __name__ == "__main__" and (len(sys.argv) <= 1 or any(arg in ("-h", "--help") for arg in sys.argv[1:])):
    _cli_parser = _build_cli_parser()
    if len(sys.argv) <= 1:
        _cli_parser.print_help()
        raise SystemExit(0)
    _cli_parser.parse_args()
    raise SystemExit(0)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    for _pkg_obj, _stg_dir in ((_stg_int, str(_SCRIPT_DIR / "_internal")), (_stg_nkc, str(_SCRIPT_DIR / "_internal" / "nk_common"))):
        _cur_p = list(getattr(_pkg_obj, "__path__", ()))
        _pkg_obj.__path__ = [_stg_dir] + [p for p in _cur_p if os.path.normcase(p) != os.path.normcase(_stg_dir)]

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
from _internal.nk_common.tas_ssot_io import reconfigure_stdio_utf8  # noqa: E402

init_nk_facade(__file__, pkg="win32_2pc_engine")

from _internal.win32_2pc_engine.constants import (  # noqa: E402
    ERROR_ACCESS_DENIED, ERROR_LOCK_VIOLATION, ERROR_SHARING_VIOLATION, FILE_ATTRIBUTE_REPARSE_POINT,
    IGNORED_STAGING_SUFFIXES, INFINITE, INVALID_FILE_ATTRIBUTES, INVALID_HANDLE_VALUE,
    MOVEFILE_COPY_ALLOWED, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    PROTECTED_GOVERNANCE_DENYLIST, PROTECTED_GOVERNANCE_PREFIXES, RETRY_ATTEMPTS_IO, RETRY_DELAY_SEC_IO,
    WAIT_ABANDONED_0, WAIT_OBJECT_0, WAIT_TIMEOUT, _IPC_LOAD_LOCK, _PATCH_NOTES_HEADER_RE,
    _POSIX_HELD_LOCKS, _UNSET, IPCPointerReturn, TwoPhaseCommitError, TwoPhaseCommitPrepare,
    TwoPhaseCommitVerdict, Win32LockError, Win32LockTimeoutError, _ensure_ipc_contracts_loaded,
    _fcntl, _get_win32_last_error, _kernel32, _register_facade_module, compute_crc32,
    compute_sha256, is_protected_governance_path,
)
from _internal.win32_2pc_engine.engine import TwoPhaseCommitEngine, win32_atomic_replace  # noqa: E402
from _internal.win32_2pc_engine.governance_auth import (  # noqa: E402
    authorize_governance_override, ensure_governance_hmac_key, mint_governance_token,
    resolve_governance_hmac_key_path, verify_governance_token,
)
from _internal.win32_2pc_engine.io_and_paths import (  # noqa: E402
    _assert_no_external_reparse, _atomic_write_bytes, _extract_patch_notes_headers, _get_repo_hash16,
    _is_reparse_point, _replace_with_retry, _resolve_repo_root, _unlink_with_retry,
    _validate_win32_canonical_rel_path, _win_long_path, get_mutex_name_for_path, get_repo_batch_mutex_name,
)
from _internal.win32_2pc_engine.journal import BatchJournalV2  # noqa: E402
from _internal.win32_2pc_engine.mutex import Win32NamedMutex  # noqa: E402
from _internal.win32_2pc_engine.promoter import promote_staging_to_production  # noqa: E402
from _internal.win32_2pc_engine.promoter_helpers import quarantine_staging  # noqa: E402
from _internal.win32_2pc_engine.staging_guards import (  # noqa: E402
    _cleanup_promoted_staging, _extract_dual_schema_baseline, _purge_production_bytecode,
    _scan_staging_canonical, _verify_quality_baseline_ratchet, record_governance_override_audit,
    record_session_anchor_commit, validate_sandbox_report_not_dry_run, validate_staging_json_files,
)
from _internal.win32_2pc_engine.wal import WriteAheadLogManager  # noqa: E402

_register_facade_module(sys.modules.get(__name__))


def _run_commit_train_cli(args: Any) -> int:
    try:
        from _internal.win32_2pc_engine.commit_train_orchestrator import run_commit_train_promote

        ct_res = run_commit_train_promote(
            repo_root=args.repo_root, lane_id=args.lane_id or "", base_seq=int(args.base_seq or 0),
            milestone=args.milestone, git_sync=args.git_sync, verify_baseline=args.verify_baseline,
            cleanup_staging=not bool(args.keep_staging), allow_governance_override=bool(args.allow_governance_override),
            governance_override_reason=args.override_reason, sandbox_report=args.sandbox_report,
            governance_token=args.governance_token,
        )
        print(ct_res.model_dump_json(indent=2))
        return 0 if ct_res.passed else 1
    except Exception as exc:
        print(f"[!] Error during Commit Train promotion: {exc}", file=sys.stderr)
        return 1


def _run_consolidate_sublanes_cli(args: Any) -> int:
    try:
        from _internal.win32_2pc_engine.sublane_consolidator import consolidate_sublanes_and_promote

        res = consolidate_sublanes_and_promote(
            repo_root=args.repo_root, parent_lane=args.parent_lane or args.lane_id or "",
            base_seq=int(args.base_seq or 0), milestone=args.milestone, use_commit_train=bool(args.commit_train),
            allow_governance_override=bool(args.allow_governance_override), governance_override_reason=args.override_reason,
            governance_token=args.governance_token, sandbox_report=args.sandbox_report,
            git_sync=bool(args.git_sync), verify_baseline=bool(args.verify_baseline),
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("passed") else 1
    except Exception as exc:
        print(f"[!] Error during sublane consolidation: {exc}", file=sys.stderr)
        return 1


def _run_promote_cli(args: Any) -> int:
    if args.commit_train:
        return _run_commit_train_cli(args)
    try:
        res = promote_staging_to_production(
            repo_root=args.repo_root, milestone=args.milestone, staging_dirname=args.staging_dir,
            git_sync=args.git_sync, verify_baseline=args.verify_baseline, cleanup_staging=not bool(args.keep_staging),
            allow_governance_override=bool(args.allow_governance_override), governance_override_reason=args.override_reason,
            sandbox_report=args.sandbox_report, governance_token=args.governance_token,
            enforce_nonce_replay=True, lane_id=args.lane_id,
        )
        print(json.dumps(res, indent=2))
        return 0
    except Exception as exc:
        print(f"[!] Error during 2PC staging promotion: {exc}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il motore Win32 Two-Phase Commit 1.0.0-Generation."""
    reconfigure_stdio_utf8()
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    if args.quarantine_staging:
        try:
            print(json.dumps(quarantine_staging(repo_root=args.repo_root, staging_dirname=args.staging_dir, lane_id=args.lane_id), indent=2))
            return 0
        except Exception as exc:
            print(f"[!] Error during staging quarantine: {exc}", file=sys.stderr)
            return 1

    if args.consolidate_sublanes:
        return _run_consolidate_sublanes_cli(args)

    if args.promote_staging or args.commit_train:
        return _run_promote_cli(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
