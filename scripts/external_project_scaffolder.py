#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scaffolder deterministico per progetti esterni di Nexus Keystone v3.0.0-STE100-Unified.
Impedisce la creazione di progetti dentro NK-Hub ([RULE-PROJECT-ISOLATION]) e crea nk_genome/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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

    def __init__(
        self,
        project_name: str,
        target_dir: Path,
        retrofit: bool = False,
        dry_run: bool = False,
        force: bool = False,
    ) -> None:
        reconfigure_streams()
        self.project_name = project_name.strip()
        self.target_dir = Path(target_dir).resolve()
        self.hub_root = _workspace_root.resolve()
        self.retrofit_mode = bool(retrofit)
        self.dry_run = bool(dry_run)
        self.force = bool(force)
        self._validate_isolation()

    def _validate_isolation(self) -> None:
        """Rifiuta qualsiasi percorso target situato dentro la radice di NK-Hub."""
        if self.target_dir == self.hub_root or self.hub_root in self.target_dir.parents:
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: la cartella target '{self.target_dir}' "
                f"non puo risiedere dentro NK-Hub ('{self.hub_root}')."
            )

    def retrofit(self, dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """Esegue l'adeguamento non distruttivo creando solo le cartelle e i file mancanti."""
        return self.scaffold(retrofit=True, dry_run=dry_run, force=False)

    def scaffold(
        self,
        retrofit: Optional[bool] = None,
        dry_run: Optional[bool] = None,
        force: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Crea l'albero delle cartelle, i file di configurazione e la Tetralogia nk_genome/."""
        self._validate_isolation()

        is_retrofit = self.retrofit_mode if retrofit is None else bool(retrofit)
        is_dry_run = self.dry_run if dry_run is None else bool(dry_run)
        is_force = self.force if force is None else bool(force)

        if not is_dry_run and not self.target_dir.exists():
            self.target_dir.mkdir(parents=True, exist_ok=True)

        created_files: List[str] = []
        created_dirs: List[str] = []
        skipped_existing: List[str] = []

        dirs_to_create = [
            self.target_dir / ".staging",
            self.target_dir / "nk_genome",
            self.target_dir / "nk_tracking",
            self.target_dir / "nk_tracking" / "reports_and_briefs",
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
            if not d.exists():
                if not is_dry_run:
                    d.mkdir(parents=True, exist_ok=True)
                created_dirs.append(str(d))
            else:
                created_dirs.append(str(d))

        def _write_file(rel_path: str, content: str) -> None:
            fpath = self.target_dir / rel_path
            if fpath.exists():
                if is_retrofit or not is_force:
                    skipped_existing.append(rel_path)
                    return
            if not is_dry_run:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
            created_files.append(rel_path)

        _write_file(".staging/.gitkeep", "")

        baseline_payload = {
            "_version": "3.5.1",
            "project_name": self.project_name,
            "metrics": {
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
        _write_file(
            "nk_tracking/quality_baseline.json",
            json.dumps(baseline_payload, indent=2, ensure_ascii=False) + "\n",
        )

        req_content = (
            "fastapi>=0.111.0,<1.0.0\n"
            "uvicorn>=0.30.0,<1.0.0\n"
            "pydantic>=2.7.0,<3.0.0\n"
            "httpx>=0.27.0,<1.0.0\n"
            "pytest>=8.2.0,<10.0.0\n"
            "pytest-asyncio>=0.23.0,<1.0.0\n"
        )
        _write_file("requirements.txt", req_content)

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
        _write_file("pytest.ini", pytest_ini_content)

        gitignore_content = (
            "__pycache__/\n"
            "*.py[cod]\n"
            ".pytest_cache/\n"
            ".staging/\n"
            "*.log\n"
            ".env\n"
        )
        _write_file(".gitignore", gitignore_content)

        readme_content = (
            f"# {self.project_name}\n\n"
            f"Progetto esterno inizializzato con Nexus Keystone v3.0.0-STE100-Unified.\n"
            f"Percorso: `{self.target_dir}`\n"
        )
        _write_file("README.md", readme_content)

        tetralogy_files = {
            "concept_map.md": f"# Concept Map: {self.project_name}\n\nVisione architetturale del progetto.\n",
            "structural_tree.md": f"# Structural Tree: {self.project_name}\n\nAlbero strutturale DDD del progetto.\n",
            "implementation_plan.md": f"# Implementation Plan: {self.project_name}\n\nPiano esecutivo atomico.\n",
            "repo_map.md": f"# Repo Map: {self.project_name}\n\nMappa AST del repository.\n",
        }
        for t_name, t_body in tetralogy_files.items():
            legacy_cand = self.target_dir / "genome" / t_name
            effective_body = t_body
            if legacy_cand.exists() and legacy_cand.is_file():
                try:
                    effective_body = legacy_cand.read_text(encoding="utf-8")
                except Exception:
                    effective_body = t_body
            _write_file(f"nk_genome/{t_name}", effective_body)

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

        for pkg_rel in (
            "src/__init__.py",
            "src/core/__init__.py",
            "src/engine/__init__.py",
            "src/api/__init__.py",
            "src/ui/__init__.py",
            "tests/__init__.py",
        ):
            _write_file(pkg_rel, init_content)

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
        _write_file("tests/test_ast_purity.py", ast_test_content)

        return {
            "status": "DRY_RUN" if is_dry_run else "SUCCESS",
            "mode": "retrofit" if is_retrofit else "standard",
            "dry_run": is_dry_run,
            "force": is_force,
            "project_name": self.project_name,
            "target_dir": str(self.target_dir),
            "created_dirs_count": len(created_dirs),
            "created_files_count": len(created_files),
            "created_files": created_files,
            "skipped_existing_count": len(skipped_existing),
            "skipped_existing": skipped_existing,
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
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
        required=False,
        default=None,
        help="Percorso assoluto esterno a NK-Hub",
    )
    parser.add_argument(
        "--retrofit",
        action="store_true",
        help="Adegua un progetto esistente creando solo le cartelle e i file mancanti",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula le operazioni senza modificare il filesystem",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forza la sovrascrittura dei file esistenti in modalita standard",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )

    args = parser.parse_args(argv)
    target_str = (
        args.target
        if args.target is not None
        else str(_workspace_root.parent / "NK_External_Projects" / args.name)
    )
    try:
        scaffolder = ExternalProjectScaffolder(
            project_name=args.name,
            target_dir=Path(target_str),
            retrofit=bool(args.retrofit),
            dry_run=bool(args.dry_run),
            force=bool(args.force),
        )
        res = scaffolder.scaffold()
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"[NK-SCAFFOLDER] {res['status']} ({res['mode']}): {res['project_name']} -> {res['target_dir']} "
                f"(creati: {res['created_files_count']}, preservati: {res['skipped_existing_count']})"
            )
        return 0
    except ValueError as exc:
        print(f"[ERRORE] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
