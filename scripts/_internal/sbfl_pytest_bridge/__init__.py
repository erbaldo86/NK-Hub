"""Pacchetto interno SBFL Pytest Bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def _ensure_staging_pkg(pkg_dir: Optional[Path] = None) -> None:
    """Assicura che i sottomoduli fratelli siano caricati da .staging durante gli overlay."""
    here = Path(pkg_dir).resolve() if pkg_dir is not None else Path(__file__).resolve().parent
    if len(here.parents) > 2 and here.parents[2].name == ".staging":
        pkg = sys.modules.get("_internal.sbfl_pytest_bridge")
        if pkg is not None and hasattr(pkg, "__path__"):
            pkg.__path__ = [str(here), *[p for p in pkg.__path__ if p != str(here)]]
        for sib_path in here.glob("*.py"):
            full = f"_internal.sbfl_pytest_bridge.{sib_path.stem}"
            cur = sys.modules.get(full)
            cur_f = Path(getattr(cur, "__file__", "") or "").resolve() if cur else None
            if cur is not None and cur_f != sib_path.resolve():
                sys.modules.pop(full, None)
