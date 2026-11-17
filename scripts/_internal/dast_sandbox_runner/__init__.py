"""Sottomoduli e registro facciata pure-stdlib per dast_sandbox_runner 1.0.0-Generation."""

from __future__ import annotations

import pkgutil
from typing import Any, List

__path__ = pkgutil.extend_path(__path__, __name__)

_FACADE_MOD_NAMES: List[str] = ["dast_sandbox_runner", "scripts.dast_sandbox_runner"]


def register_facade_module(mod_name: str) -> None:
    """Registra il nome modulo della facciata per i monkeypatch di test."""
    if mod_name and mod_name not in _FACADE_MOD_NAMES:
        _FACADE_MOD_NAMES.insert(0, mod_name)


def _facade_attr(name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    from _internal.nk_common.facade_boot import resolve_facade_attr

    return resolve_facade_attr(_FACADE_MOD_NAMES, name, default)
