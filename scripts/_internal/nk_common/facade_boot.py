# -*- coding: utf-8 -*-
"""Bootstrap unificato delle facciate CLI con supporto overlay .staging/[lanes/<id>/] e produzione."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Optional, Sequence


def _prepend_pkg_overlay(
    pkg_name: str, stg_dir: str, prod_dir: Optional[str] = None
) -> None:
    """Inserisce stg_dir in testa a __path__ ed assicura prod_dir come fallback."""
    if not os.path.isdir(stg_dir):
        return
    try:
        pkg_obj = importlib.import_module(pkg_name)
    except ImportError:
        return
    pkg_path = getattr(pkg_obj, "__path__", None)
    if isinstance(pkg_path, list):
        if stg_dir in pkg_path:
            if pkg_path[0] != stg_dir:
                pkg_path.remove(stg_dir)
                pkg_path.insert(0, stg_dir)
        else:
            pkg_path.insert(0, stg_dir)
        if prod_dir and os.path.isdir(prod_dir):
            norm_prod = os.path.normcase(os.path.realpath(prod_dir))
            has_prod = any(
                os.path.normcase(os.path.realpath(p)) == norm_prod
                for p in pkg_path
                if p
            )
            if not has_prod:
                pkg_path.append(prod_dir)


def _resolve_facade_dirs(facade_file: str) -> tuple[str, str, bool]:
    script_dir = os.path.dirname(os.path.realpath(facade_file))
    parent_dir = os.path.dirname(script_dir)
    grand_dir = os.path.dirname(parent_dir)
    great_dir = os.path.dirname(grand_dir)
    if os.path.basename(parent_dir) == ".staging":
        return script_dir, os.path.join(grand_dir, "scripts"), True
    if os.path.basename(grand_dir) == "lanes" and os.path.basename(great_dir) == ".staging":
        return script_dir, os.path.join(os.path.dirname(great_dir), "scripts"), True
    return script_dir, script_dir, False


def init_nk_facade(facade_file: str, pkg: Optional[str] = None) -> str:
    """Configura sys.path e l'overlay __path__ di _internal per la facciata CLI."""
    script_dir, prod_scripts_dir, is_staged = _resolve_facade_dirs(facade_file)
    stg_sibling_dir = os.path.join(
        os.path.dirname(prod_scripts_dir), ".staging", "scripts"
    )

    for cand_str in (script_dir, prod_scripts_dir):
        if os.path.exists(cand_str) and cand_str not in sys.path:
            sys.path.append(cand_str)

    if os.path.exists(prod_scripts_dir):
        if prod_scripts_dir in sys.path:
            sys.path.remove(prod_scripts_dir)
        insert_idx = 0
        norm_stg = os.path.normcase(os.path.realpath(stg_sibling_dir))
        for idx, entry in enumerate(sys.path):
            if entry and os.path.normcase(os.path.realpath(entry)) == norm_stg:
                insert_idx = idx + 1
                break
        sys.path.insert(insert_idx, prod_scripts_dir)

    if is_staged and os.path.exists(script_dir):
        if script_dir in sys.path:
            sys.path.remove(script_dir)
        sys.path.insert(0, script_dir)

    cached_internal = sys.modules.get("_internal")
    if cached_internal is not None:
        cached_file = getattr(cached_internal, "__file__", "") or ""
        if cached_file:
            cached_root_norm = os.path.normcase(
                os.path.dirname(os.path.dirname(os.path.realpath(cached_file)))
            )
            allowed_roots = {
                os.path.normcase(script_dir),
                os.path.normcase(prod_scripts_dir),
                os.path.normcase(os.path.realpath(stg_sibling_dir)),
            }
            if cached_root_norm not in allowed_roots:
                for mod_k in [
                    k
                    for k in list(sys.modules)
                    if k == "_internal" or k.startswith("_internal.")
                ]:
                    sys.modules.pop(mod_k, None)

    stg_internal_dir = os.path.join(script_dir, "_internal")
    prod_internal_dir = os.path.join(prod_scripts_dir, "_internal")
    if script_dir != prod_scripts_dir and os.path.isdir(stg_internal_dir):
        _prepend_pkg_overlay("_internal", stg_internal_dir, prod_internal_dir)
        _prepend_pkg_overlay(
            "_internal.nk_common",
            os.path.join(stg_internal_dir, "nk_common"),
            os.path.join(prod_internal_dir, "nk_common"),
        )
        if pkg:
            _prepend_pkg_overlay(
                f"_internal.{pkg}",
                os.path.join(stg_internal_dir, pkg),
                os.path.join(prod_internal_dir, pkg),
            )

    return prod_scripts_dir


def resolve_facade_attr(
    mod_names: Sequence[str], name: str, default: Any = None
) -> Any:
    """Risolve un attributo da moduli facciata in sys.modules preservando monkeypatch."""
    for mod_name in mod_names:
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        try:
            mod_items = vars(mod).copy().items()
        except TypeError:
            continue
        for key, val in mod_items:
            if key == name:
                return val
    return default
