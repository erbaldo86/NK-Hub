#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scaffolder deterministico per progetti esterni di Nexus Keystone v3.0.0-STE100-Unified.
Impedisce la creazione di progetti dentro NK-Hub ([RULE-PROJECT-ISOLATION]) e crea nk_genome/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

_scripts_dir = Path(__file__).resolve().parent
if _scripts_dir.parent.name == ".staging":
    _workspace_root = _scripts_dir.parent.parent
else:
    _workspace_root = _scripts_dir.parent

if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    from scripts.platform_runner import reconfigure_streams


class ExternalProjectScaffolder:
    """Genera la struttura DDD completa e la Tetralogia Sovrana in una cartella esterna."""

    def __init__(self, project_name: str, target_dir: Path):
        reconfigure_streams()
        self.project_name = project_name.strip()
        self.target_dir = Path(target_dir).resolve()
        self.hub_root = _workspace_root.resolve()
        self._validate_isolation()

    def _validate_isolation(self) -> None:
        """Rifiuta qualsiasi percorso target situato dentro la radice di NK-Hub."""
        if self.target_dir == self.hub_root or self.hub_root in self.target_dir.parents:
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: la cartella target '{self.target_dir}' "
                f"non puo risiedere dentro NK-Hub ('{self.hub_root}')."
            )

    def scaffold(self) -> Dict[str, Any]:
        """Crea l'albero delle cartelle, i file di configurazione e la Tetralogia nk_genome/."""
        self._validate_isolation()

        if not self.target_dir.exists():
            self.target_dir.mkdir(parents=True, exist_ok=True)

        created_files: List[str] = []
        created_dirs: List[str] = []

        dirs_to_create = [
            self.target_dir / "nk_genome",
            self.target_dir / "src",
            self.target_dir / "src" / "core",
            self.target_dir / "src" / "engine",
            self.target_dir / "src" / "api",
            self.target_dir / "src" / "ui",
            self.target_dir / "src" / "ui" / "templates",
            self.target_dir / "src" / "ui" / "static",
            self.target_dir / "tests",
            self.target_dir / "scripts",
        ]

        for d in dirs_to_create:
            d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(d))

        req_content = (
            "fastapi>=0.111.0,<1.0.0\n"
            "uvicorn>=0.30.0,<1.0.0\n"
            "pydantic>=2.7.0,<3.0.0\n"
            "httpx>=0.27.0,<1.0.0\n"
            "pytest>=8.2.0,<10.0.0\n"
            "pytest-asyncio>=0.23.0,<1.0.0\n"
        )
        (self.target_dir / "requirements.txt").write_text(req_content, encoding="utf-8")
        created_files.append("requirements.txt")

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
        (self.target_dir / "pytest.ini").write_text(pytest_ini_content, encoding="utf-8")
        created_files.append("pytest.ini")

        gitignore_content = (
            "__pycache__/\n"
            "*.py[cod]\n"
            ".pytest_cache/\n"
            ".staging/\n"
            "*.log\n"
            ".env\n"
        )
        (self.target_dir / ".gitignore").write_text(gitignore_content, encoding="utf-8")
        created_files.append(".gitignore")

        readme_content = (
            f"# {self.project_name}\n\n"
            f"Progetto esterno inizializzato con Nexus Keystone v3.0.0-STE100-Unified.\n"
            f"Percorso: `{self.target_dir}`\n"
        )
        (self.target_dir / "README.md").write_text(readme_content, encoding="utf-8")
        created_files.append("README.md")

        tetralogy_files = {
            "concept_map.md": f"# Concept Map: {self.project_name}\n\nVisione architetturale del progetto.\n",
            "structural_tree.md": f"# Structural Tree: {self.project_name}\n\nAlbero strutturale DDD del progetto.\n",
            "implementation_plan.md": f"# Implementation Plan: {self.project_name}\n\nPiano esecutivo atomico.\n",
            "repo_map.md": f"# Repo Map: {self.project_name}\n\nMappa AST del repository.\n",
        }
        for t_name, t_body in tetralogy_files.items():
            t_path = self.target_dir / "nk_genome" / t_name
            t_path.write_text(t_body, encoding="utf-8")
            created_files.append(f"nk_genome/{t_name}")

        init_content = (
            f'"""{self.project_name} - Progetto esterno Nexus Keystone."""\n\n'
            f"import sys\n\n"
            f"if hasattr(sys.stdout, 'reconfigure'):\n"
            f"    try:\n"
            f"        sys.stdout.reconfigure(encoding='utf-8', errors='replace')\n"
            f"        sys.stderr.reconfigure(encoding='utf-8', errors='replace')\n"
            f"    except Exception:\n"
            f"        pass\n\n"
            f'__version__ = "1.0.0"\n'
        )

        for pkg in [
            self.target_dir / "src" / "__init__.py",
            self.target_dir / "src" / "core" / "__init__.py",
            self.target_dir / "src" / "engine" / "__init__.py",
            self.target_dir / "src" / "api" / "__init__.py",
            self.target_dir / "src" / "ui" / "__init__.py",
            self.target_dir / "tests" / "__init__.py",
        ]:
            pkg.write_text(init_content, encoding="utf-8")
            created_files.append(str(pkg.relative_to(self.target_dir)))

        ast_test_content = (
            '"""Test automatico di purezza sintattica AST."""\n\n'
            "import ast\n"
            "from pathlib import Path\n\n"
            "def test_ast_syntax_purity():\n"
            "    src_dir = Path(__file__).resolve().parent.parent / 'src'\n"
            "    py_files = list(src_dir.rglob('*.py'))\n"
            "    assert len(py_files) > 0, 'Source files must exist'\n"
            "    for py_file in py_files:\n"
            "        code = py_file.read_text(encoding='utf-8')\n"
            "        tree = ast.parse(code, filename=str(py_file))\n"
            "        assert tree is not None, f'Failed parsing {py_file}'\n"
        )
        (self.target_dir / "tests" / "test_ast_purity.py").write_text(
            ast_test_content,
            encoding="utf-8",
        )
        created_files.append("tests/test_ast_purity.py")

        return {
            "status": "SUCCESS",
            "project_name": self.project_name,
            "target_dir": str(self.target_dir),
            "created_dirs_count": len(created_dirs),
            "created_files_count": len(created_files),
            "created_files": created_files,
        }


def main() -> int:
    """Punto di ingresso CLI per lo scaffolder dei progetti esterni."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Deterministic External Project Scaffolder"
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Nome del progetto da inizializzare",
    )
    parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Percorso assoluto esterno a NK-Hub",
    )

    args = parser.parse_args()
    try:
        scaffolder = ExternalProjectScaffolder(
            project_name=args.name,
            target_dir=Path(args.target),
        )
        res = scaffolder.scaffold()
        print(f"[NK-SCAFFOLDER] Progetto creato: {res['project_name']} -> {res['target_dir']}")
        return 0
    except ValueError as exc:
        print(f"[ERRORE] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
