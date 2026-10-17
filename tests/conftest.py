# -*- coding: utf-8 -*-
"""
Configurazione Pytest e cache globale dei moduli per Nexus Keystone v3.3.0.
Modulo: tests/conftest.py.
Fornisce il caricamento in-memory cachato degli script e le directory temporanee isolate.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
STAGING_SCRIPTS_DIR = WORKSPACE_ROOT / ".staging" / "scripts"

for _cand in (STAGING_SCRIPTS_DIR, SCRIPTS_DIR, WORKSPACE_ROOT):
    if _cand.exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

_GLOBAL_MODULE_CACHE: Dict[str, Any] = {}


def load_nk_script_module(mod_name: str, rel_subpath: str = "scripts") -> Any:
    """Carica e memorizza nella cache globale un modulo da .staging/ o produzione."""
    cache_key = f"{rel_subpath}:{mod_name}"
    if cache_key in _GLOBAL_MODULE_CACHE:
        return _GLOBAL_MODULE_CACHE[cache_key]

    staging_target = WORKSPACE_ROOT / ".staging" / rel_subpath / f"{mod_name}.py"
    prod_target = WORKSPACE_ROOT / rel_subpath / f"{mod_name}.py"
    target = staging_target if staging_target.exists() else prod_target

    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossibile caricare il modulo {mod_name} da {target}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    _GLOBAL_MODULE_CACHE[cache_key] = mod
    return mod


@pytest.fixture
def temp_test_dir():
    """Fornisce una directory temporanea isolata per le operazioni di test."""
    tmp = tempfile.mkdtemp(prefix="nk_test_dir_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def clean_sandbox_dir():
    """Fornisce una directory sandbox isolata per i test."""
    tmp = tempfile.mkdtemp(prefix="nk_sandbox_test_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)
