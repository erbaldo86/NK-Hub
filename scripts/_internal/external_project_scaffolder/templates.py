# -*- coding: utf-8 -*-
"""Costanti, guardie symlink e template testuali per external_project_scaffolder."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from _internal.nk_common.constants import VERSION
from _internal.nk_common.facade_boot import resolve_facade_attr

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
_FACADE_MOD_NAMES: Tuple[str, ...] = (
    "external_project_scaffolder",
    "scripts.external_project_scaffolder",
)

SCAFFOLDER_VERSION: str = VERSION
_FILE_ATTRIBUTE_REPARSE_POINT: int = 0x0400

PACKAGE_INIT_TARGETS: Tuple[str, ...] = (
    "src/__init__.py",
    "src/core/__init__.py",
    "src/engine/__init__.py",
    "src/api/__init__.py",
    "src/ui/__init__.py",
    "tests/__init__.py",
)


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


def _is_symlink_or_reparse(path_obj: Path) -> bool:
    """Rileva symlink o reparse point Win32 senza seguire il collegamento."""
    try:
        if path_obj.is_symlink():
            return True
        st = os.lstat(path_obj)
        if (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) != 0:
            return True
    except OSError:
        pass
    return False


def build_baseline_json(project_name: str) -> str:
    """Genera il contenuto JSON iniziale per nk_tracking/quality_baseline.json."""
    payload = {
        "_version": SCAFFOLDER_VERSION,
        "project_name": project_name,
        "metrics": {
            "unit_tests_total": {
                "value": 1,
                "direction": "higher_is_better",
            },
            "unit_tests_pass_pct": {
                "value": 100.0,
                "direction": "higher_is_better",
            },
            "sast_critical_violations": {
                "value": 0,
                "direction": "lower_is_better",
            },
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def build_static_project_templates(project_name: str, target_dir: Path) -> Dict[str, str]:
    """Restituisce i file statici di configurazione del progetto esterno."""
    req_content = (
        "fastapi>=0.111.0,<1.0.0\n"
        "uvicorn>=0.30.0,<1.0.0\n"
        "pydantic>=2.7.0,<3.0.0\n"
        "httpx>=0.27.0,<1.0.0\n"
        "pytest>=8.2.0,<10.0.0\n"
        "pytest-asyncio>=0.23.0,<1.0.0\n"
    )
    pytest_ini_content = (
        "[pytest]\n"
        "testpaths = tests\n"
        "python_files = test_*.py\n"
        "python_classes = Test*\n"
        "python_functions = test_*\n"
        "asyncio_mode = strict\n"
        "filterwarnings =\n"
        "    ignore::DeprecationWarning\n"
    )
    gitignore_content = (
        "__pycache__/\n"
        "*.py[cod]\n"
        ".pytest_cache/\n"
        ".staging/\n"
        "*.log\n"
        ".env\n"
    )
    readme_content = (
        f"# {project_name}\n\n"
        f"Progetto esterno inizializzato con NK Hub Generation {SCAFFOLDER_VERSION} (Pentad Sovrana 4+1).\n"
        f"Percorso: `{target_dir}`\n"
    )
    ast_test_content = (
        '"""Test automatico di purezza sintattica AST."""\n\n'
        "import ast\n"
        "from pathlib import Path\n\n"
        "def test_ast_syntax_purity():\n"
        "    root_dir = Path(__file__).resolve().parent.parent\n"
        "    src_dir = root_dir / 'src' if (root_dir / 'src').exists() else root_dir\n"
        "    py_files = list(src_dir.rglob('*.py'))\n"
        "    assert len(py_files) > 0, 'Source files must exist'\n"
        "    for py_file in py_files:\n"
        "        code = py_file.read_text(encoding='utf-8')\n"
        "        tree = ast.parse(code, filename=str(py_file))\n"
        "        assert tree is not None, f'Failed parsing {py_file}'\n"
    )
    return {
        ".staging/.gitkeep": "",
        "nk_tracking/quality_baseline.json": build_baseline_json(project_name),
        "requirements.txt": req_content,
        "pytest.ini": pytest_ini_content,
        ".gitignore": gitignore_content,
        "README.md": readme_content,
        "tests/test_ast_purity.py": ast_test_content,
    }


def build_pentad_genome_templates(project_name: str) -> Dict[str, str]:
    """Genera i template della Pentad Sovrana 4+1 per la cartella nk_genome/."""
    return {
        "concept_map.md": f"# Concept Map: {project_name}\n\nVisione architetturale della Pentad Sovrana 4+1.\n",
        "structural_tree.md": f"# Structural Tree: {project_name}\n\nAlbero strutturale DDD del progetto.\n",
        "implementation_plan.md": f"# Implementation Plan: {project_name}\n\nPiano esecutivo atomico.\n",
        "repo_map.md": f"# Repo Map: {project_name}\n\nMappa AST del repository.\n",
        "PATCH_NOTES.md": f"# Patch Notes SSOT: {project_name}\n\nRegistro cronologico delle modifiche verificate.\n",
    }


def build_package_init_content(project_name: str) -> str:
    """Genera il contenuto standard per i file __init__.py del progetto."""
    return (
        f'"""{project_name}: Progetto esterno NK Hub Generation {SCAFFOLDER_VERSION}."""\n\n'
        "import sys\n\n"
        "if hasattr(sys.stdout, 'reconfigure'):\n"
        "    try:\n"
        "        sys.stdout.reconfigure(encoding='utf-8', errors='replace')\n"
        "        sys.stderr.reconfigure(encoding='utf-8', errors='replace')\n"
        "    except Exception:\n"
        "        pass\n\n"
        '__version__ = "0.1.0"\n'
    )
