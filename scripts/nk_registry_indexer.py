#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Indicizzatore modulare O(1) e generatore del manifesto SSOT per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/nk_registry_indexer.py.
Mappa i cinque domini funzionali, le skill Hot-Swap e i moduli Python certificati.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    for _pkg_obj, _stg_dir in (
        (_stg_int, str(_SCRIPT_DIR / "_internal")),
        (_stg_nkc, str(_SCRIPT_DIR / "_internal" / "nk_common")),
    ):
        _cur_p = list(getattr(_pkg_obj, "__path__", ()))
        _pkg_obj.__path__ = [_stg_dir] + [p for p in _cur_p if os.path.normcase(p) != os.path.normcase(_stg_dir)]

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="nk_registry_indexer")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "NKRegistryIndexer": ("_internal.nk_registry_indexer.indexer", "NKRegistryIndexer"),
    "generate_tas_certification_matrix": ("_internal.nk_registry_indexer.indexer", "generate_tas_certification_matrix"),
    "CRIT01_FORBIDDEN_TOOLS": ("_internal.nk_registry_indexer.taxonomy", "CRIT01_FORBIDDEN_TOOLS"),
    "DEFAULT_GLOBAL_CONFIG_DIR": ("_internal.nk_registry_indexer.taxonomy", "DEFAULT_GLOBAL_CONFIG_DIR"),
    "DEV_UTILITY_SKILLS": ("_internal.nk_registry_indexer.taxonomy", "DEV_UTILITY_SKILLS"),
    "DOMAIN_TAXONOMY": ("_internal.nk_registry_indexer.taxonomy", "DOMAIN_TAXONOMY"),
    "FORBIDDEN_PHANTOM_MCP_TOOLS": ("_internal.nk_registry_indexer.taxonomy", "FORBIDDEN_PHANTOM_MCP_TOOLS"),
    "GCP_DATA_SKILLS": ("_internal.nk_registry_indexer.taxonomy", "GCP_DATA_SKILLS"),
    "NATIVE_AGENT_DOMAIN_MAP": ("_internal.nk_registry_indexer.taxonomy", "NATIVE_AGENT_DOMAIN_MAP"),
    "TETRALOGY_FILENAMES": ("_internal.nk_registry_indexer.taxonomy", "TETRALOGY_FILENAMES"),
    "get_skill_routing_rules": ("_internal.nk_common.catalog", "get_skill_routing_rules"),
    "_DEFAULT_WORKSPACE_ROOT": ("_internal.nk_registry_indexer.taxonomy", "_DEFAULT_WORKSPACE_ROOT"),
    "_EXCLUDED_SUBPROCESS_FLAGS": ("_internal.nk_registry_indexer.taxonomy", "_EXCLUDED_SUBPROCESS_FLAGS"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli della facciata senza caricare moduli pesanti su --help."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per l'indicizzatore modulare di NK Hub Generation."""
    parser = argparse.ArgumentParser(
        description="Indicizzatore Modulare O(1) NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Genera nk_registry_manifest.json e SKILL_INDEX.md",
    )
    parser.add_argument(
        "--sync-staging",
        action="store_true",
        help="Sincronizza esplicitamente nk_registry_manifest.json anche in .staging/nk_genome/",
    )
    parser.add_argument(
        "--allow-ratchet-down",
        action="store_true",
        help="Consente la riduzione controllata del conteggio skill o script nel manifesto",
    )
    parser.add_argument(
        "--verify",
        "--check",
        action="store_true",
        dest="verify",
        help="Verifica l'allineamento SHA-256 tra manifesto e file su disco",
    )
    parser.add_argument(
        "--lookup",
        type=str,
        default=None,
        help="Interroga in O(1) un dominio, una skill, uno script o un intento",
    )
    parser.add_argument(
        "--build-release-zip",
        type=str,
        default=None,
        help="Crea un archivio ZIP di rilascio con prefisso NK_Hub/ escludendo artefatti effimeri",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice del workspace da indicizzare",
    )
    parser.add_argument(
        "--stage-dir",
        type=str,
        default=None,
        help="Directory di staging target per la scrittura del manifesto",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa l'output in formato JSON strutturato",
    )
    parser.add_argument(
        "--apply-global-filter",
        action="store_true",
        help="Valuta in sola lettura il filtro delle skill globali prima di eseguire sync",
    )
    parser.add_argument(
        "--generate-tas-matrix",
        action="store_true",
        help="Genera e stampa la matrice Markdown certificata TAS di skill, script e sub-agenti",
    )
    args = parser.parse_args(argv)
    import json

    _self_mod = sys.modules[__name__]
    getattr(_self_mod, "reconfigure_streams")()
    root_path = Path(args.root).resolve() if args.root else None
    stage_path = Path(args.stage_dir) if args.stage_dir else None
    indexer = getattr(_self_mod, "NKRegistryIndexer")(workspace_root=root_path, stage_dir=stage_path)

    if args.build_release_zip:
        res = indexer.build_release_zip(Path(args.build_release_zip))
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"🟢 [NK-RELEASE-ZIP] Path: {res['zip_path']} | "
                f"Files: {res['files_archived']} | "
                f"Bytes: {res['size_bytes']} ({res['elapsed_ms']} ms)"
            )
        return 0 if res.get("passed") else 1

    if args.generate_tas_matrix:
        matrix_md = indexer.generate_tas_certification_matrix()
        if args.json:
            print(
                json.dumps(
                    {"status": "OK", "tas_matrix_markdown": matrix_md},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(matrix_md, end="")
        return 0

    if args.apply_global_filter:
        flt = indexer.apply_global_filter()
        res = indexer.sync(
            sync_staging=bool(args.sync_staging),
            allow_ratchet_down=bool(args.allow_ratchet_down),
        )
        res["global_filter"] = flt
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif res.get("passed", True):
            print(
                f"🟢 [NK-GLOBAL-FILTER] Status: {res['status']} | "
                f"Installed External: {res['global_hygiene_profile']['installed_external_skills_count']} | "
                f"Active External: {res['global_hygiene_profile']['active_external_skills_count']} | "
                f"Total Flat Skills: {res['global_hygiene_profile']['total_flat_skills']} ({res['elapsed_ms']} ms)"
            )
        else:
            print(
                f"🔴 [NK-GLOBAL-FILTER] Status: {res['status']} | "
                f"Error: {res.get('error_code', 'ERR')} ({res['elapsed_ms']} ms)"
            )
        return 0 if res.get("passed", True) else 1

    if args.sync or args.sync_staging:
        res = indexer.sync(
            sync_staging=bool(args.sync_staging),
            allow_ratchet_down=bool(args.allow_ratchet_down),
        )
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif res.get("passed", True):
            print(
                f"🟢 [NK-REGISTRY-SYNC] Status: {res['status']} | "
                f"Domains: {res['summary']['total_domains']} | "
                f"Skills: {res['summary']['total_skills']} | "
                f"Scripts: {res['summary']['total_scripts']} ({res['elapsed_ms']} ms)"
            )
        else:
            print(
                f"🔴 [NK-REGISTRY-SYNC] Status: {res['status']} | "
                f"Error: {res.get('error_code', 'ERR')} | "
                f"Skills: {res.get('prev_skills')} -> {res.get('new_skills')} | "
                f"Scripts: {res.get('prev_scripts')} -> {res.get('new_scripts')} ({res['elapsed_ms']} ms)"
            )
        return 0 if res.get("passed", True) else 1

    if args.lookup is not None:
        res = indexer.lookup(args.lookup)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"[NK-REGISTRY-LOOKUP] Match: {res['match_type']} | "
                f"Domain: {res['domain_id']} ({res['domain_name']}) | "
                f"Primary Skill: {res['primary_skill']} ({res['elapsed_ms']} ms)"
            )
        return 0 if res["found"] else 1

    res = indexer.verify()
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        sym = "🟢" if res["passed"] else "🔴"
        print(
            f"{sym} [NK-REGISTRY-VERIFY] Status: {res['status']} | "
            f"Skills: {res.get('total_skills', 0)} | "
            f"Scripts: {res.get('total_scripts', 0)} ({res['elapsed_ms']} ms)"
        )
        for issue in res.get("issues", []):
            print(f"  - {issue}")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
