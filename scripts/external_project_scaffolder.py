#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scaffolder deterministico per progetti esterni di NK Hub Generation 1.0.0-Generation.
Modulo: scripts/external_project_scaffolder.py.
@domain_id: DOM-02
Impedisce la creazione di progetti dentro NK-Hub ([RULE-PROJECT-ISOLATION]) e crea la Pentad Sovrana 4+1 in nk_genome/.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__nk_domain__: str = "DOM-02"
__nk_role__: str = "facade"
__nk_facade__: str = "external_project_scaffolder"

_CLI_FLAGS: Tuple[str, ...] = (
    "--dry-run",
    "--force",
    "--json",
    "--name",
    "--retrofit",
    "--target",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="external_project_scaffolder")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "SCAFFOLDER_VERSION": ("_internal.external_project_scaffolder.templates", "SCAFFOLDER_VERSION"),
    "_FILE_ATTRIBUTE_REPARSE_POINT": ("_internal.external_project_scaffolder.templates", "_FILE_ATTRIBUTE_REPARSE_POINT"),
    "_scripts_dir": ("_internal.external_project_scaffolder.templates", "_scripts_dir"),
    "_workspace_root": ("_internal.external_project_scaffolder.templates", "_workspace_root"),
    "_is_symlink_or_reparse": ("_internal.external_project_scaffolder.templates", "_is_symlink_or_reparse"),
    "ExternalProjectScaffolder": ("_internal.external_project_scaffolder.scaffolder_cli", "ExternalProjectScaffolder"),
    "_build_cli_parser": ("_internal.external_project_scaffolder.scaffolder_cli", "_build_cli_parser"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.external_project_scaffolder."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="external_project_scaffolder")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per lo scaffolder dei progetti esterni."""
    init_nk_facade(__file__, pkg="external_project_scaffolder")
    return importlib.import_module(
        "_internal.external_project_scaffolder.scaffolder_cli"
    ).main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
