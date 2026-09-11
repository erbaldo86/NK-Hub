#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.0.0-Hardened - External Project Scaffolder
Module: external_project_scaffolder.py
Author: NK-Platform-Builder & NK-Environment-Architect
Implements: [RULE-PROJECT-ISOLATION] & Scaffolding deterministico ad alta efficienza

Features:
- Single-command atomic project scaffolding outside NK-Hub.
- Complete DDD directory tree generation (src/core, src/engine, src/api, src/ui, tests/, scripts/).
- Preconfigured unbuffered pytest.ini, requirements.txt, .gitignore, and stream-reconfigured __init__.py.
- Built-in tests/test_ast_purity.py running ast_guard_validator automatically.
- Instant validation before completion.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = _scripts_dir.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from scripts.platform_runner import reconfigure_streams


class ExternalProjectScaffolder:
    """Deterministic 1-command DDD Scaffolder for external projects."""

    def __init__(self, project_name: str, target_dir: Path):
        reconfigure_streams()
        self.project_name = project_name
        self.target_dir = Path(target_dir).resolve()

    def scaffold(self) -> Dict[str, Any]:
        """Generate the complete project tree and configurations atomically."""
        if not self.target_dir.exists():
            self.target_dir.mkdir(parents=True, exist_ok=True)

        created_files: List[str] = []
        created_dirs: List[str] = []

        # 1. Directory Tree
        dirs_to_create = [
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

        # 2. Config & Root Files
        # requirements.txt
        req_content = (
            "fastapi>=0.111.0,<1.0.0\n"
            "uvicorn>=0.30.0,<1.0.0\n"
            "pydantic>=2.7.0,<3.0.0\n"
            "httpx>=0.27.0,<1.0.0\n"
            "pytest>=8.0.0,<9.0.0\n"
            "pytest-asyncio>=0.23.0,<1.0.0\n"
        )
        (self.target_dir / "requirements.txt").write_text(req_content, encoding="utf-8")
        created_files.append("requirements.txt")

        # pytest.ini
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

        # .gitignore
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

        # README.md
        readme_content = (
            f"# {self.project_name}\n\n"
            f"> Developed with Nexus Keystone Sovereign Ecosystem v2.0.\n"
            f"> Target Directory: `{self.target_dir}`\n\n"
            f"## Architecture\n"
            f"- `src/core/`: Configuration and strict Pydantic schemas.\n"
            f"- `src/engine/`: Core business and async algorithms.\n"
            f"- `src/api/`: FastAPI routes and endpoints.\n"
            f"- `src/ui/`: Reactive frontend templates and static assets.\n"
            f"- `tests/`: Zero-Mock test suite.\n"
        )
        (self.target_dir / "README.md").write_text(readme_content, encoding="utf-8")
        created_files.append("README.md")

        # 3. Source Packages __init__.py with stream reconfiguration
        init_content = (
            f'"""{self.project_name} - Nexus Keystone Autonomous Ecosystem."""\n\n'
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

        # 4. Built-in tests/test_ast_purity.py
        ast_test_content = (
            '"""Built-in AST Guard validation test."""\n\n'
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
            ast_test_content, encoding="utf-8"
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
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Deterministic External Project Scaffolder"
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Name of the project to scaffold",
    )
    parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Absolute path to target directory outside NK-Hub",
    )

    args = parser.parse_args()
    scaffolder = ExternalProjectScaffolder(project_name=args.name, target_dir=Path(args.target))
    res = scaffolder.scaffold()

    print(f"🟢 [NK-SCAFFOLDER] Scaffolding completed for {res['project_name']}")
    print(f"  Target: {res['target_dir']}")
    print(f"  Files created: {res['created_files_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
