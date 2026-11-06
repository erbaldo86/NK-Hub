# -*- coding: utf-8 -*-
"""
Configurazione Pytest e cache globale dei moduli per Nexus Keystone v4.7.0-STE100-Unified.
Modulo: tests/conftest.py.
Fornisce il caricamento in-memory cachato degli script e le fixture di sessione.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

CONFTEST_VERSION: str = "4.7.0-STE100-Unified"

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


def _resolve_staged_or_prod(rel_path: str) -> Path:
    """Risolve un percorso relativo dando priorita alla copia in .staging/."""
    staged = WORKSPACE_ROOT / ".staging" / rel_path
    if staged.exists():
        return staged
    return WORKSPACE_ROOT / rel_path


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


@pytest.fixture(scope="session")
def session_registry_manifest() -> Dict[str, Any]:
    """Memorizza in cache di sessione il manifesto JSON nk_registry_manifest.json."""
    manifest_path = _resolve_staged_or_prod("nk_genome/nk_registry_manifest.json")
    if not manifest_path.is_file():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def session_genome_docs() -> Dict[str, str]:
    """Memorizza in cache di sessione i documenti Markdown della Tetralogia."""
    docs: Dict[str, str] = {}
    for rel_doc in (
        "nk_genome/idea_canvas.md",
        "nk_genome/concept_map.md",
        "nk_genome/structural_tree.md",
        "nk_genome/implementation_plan.md",
        "nk_genome/repo_map.md",
        "nk_genome/PATCH_NOTES.md",
    ):
        target = _resolve_staged_or_prod(rel_doc)
        if target.is_file():
            docs[Path(rel_doc).name] = target.read_text(encoding="utf-8")
    return docs


@pytest.fixture(scope="session")
def session_skill_files() -> Dict[str, str]:
    """Memorizza in cache di sessione il testo delle 16 skill in .agents/skills/."""
    skills_map: Dict[str, str] = {}
    skills_root = WORKSPACE_ROOT / ".agents" / "skills"
    if not skills_root.is_dir():
        return skills_map
    for sdir in sorted(skills_root.iterdir()):
        if sdir.is_dir() and (sdir / "SKILL.md").is_file():
            target = _resolve_staged_or_prod(
                f".agents/skills/{sdir.name}/SKILL.md"
            )
            skills_map[sdir.name] = target.read_text(encoding="utf-8")
    return skills_map


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
