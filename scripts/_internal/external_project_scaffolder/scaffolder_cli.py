# -*- coding: utf-8 -*-
"""Motore ExternalProjectScaffolder e punto di ingresso CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from _internal.external_project_scaffolder.templates import (
    PACKAGE_INIT_TARGETS,
    _facade_attr,
    _is_symlink_or_reparse,
    _workspace_root,
    build_package_init_content,
    build_pentad_genome_templates,
    build_static_project_templates,
)
from _internal.nk_common.paths import (
    is_nk_proget_online_path,
    reconfigure_streams,
    resolve_nk_proget_roots,
)


def _resolve_default_external_root(ws_root: Path) -> Path:
    """Risolve la radice predefinita dei progetti esterni preferendo NK Proget/Locale."""
    locale_root, _ = resolve_nk_proget_roots(ws_root)
    if locale_root is not None and locale_root.exists():
        return locale_root
    legacy_inner = ws_root / "NK_External_Projects"
    return legacy_inner if legacy_inner.exists() else (ws_root.parent / "NK_External_Projects")


class ExternalProjectScaffolder:
    """Genera la struttura DDD completa e la Pentad Sovrana 4+1 in nk_genome/."""

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
        self._raw_target = Path(target_dir)
        self._raw_target_str = str(target_dir)
        self.target_dir = self._raw_target.resolve()
        ws_root = Path(_facade_attr("_workspace_root", _workspace_root))
        self.hub_root = ws_root.resolve()
        self.retrofit_mode = bool(retrofit)
        self.dry_run = bool(dry_run)
        self.force = bool(force)
        self._validate_isolation()

    def _assert_not_readonly_online(self, real_target: Path) -> None:
        """Blocca lo scaffolding sul mirror read-only NK Proget/Online."""
        for cand in (self._raw_target, self.target_dir, real_target):
            if is_nk_proget_online_path(cand):
                raise ValueError(
                    f"Violazione [NK_PROGET_ONLINE_READONLY]: il mirror read-only '{self.target_dir}' e protetto da scrittura."
                )

    def _validate_isolation(self) -> None:
        """Rifiuta traversal, symlink, escape e percorsi interni a NK-Hub."""
        if (
            not self.project_name
            or self.project_name in (".", "..")
            or ".." in self.project_name
            or "/" in self.project_name
            or "\\" in self.project_name
            or ":" in self.project_name
            or "\x00" in self.project_name
            or self.project_name != self.project_name.rstrip(". ")
        ):
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: nome progetto invalido o traversal rilevato: '{self.project_name}'."
            )

        raw_s = self._raw_target_str
        if not raw_s.strip() or "\x00" in raw_s:
            raise ValueError(
                "Violazione [RULE-PROJECT-ISOLATION]: percorso target vuoto o null-byte rilevato."
            )

        tail_after_drive = (
            raw_s[2:] if (len(raw_s) >= 2 and raw_s[1] == ":") else raw_s
        )
        if ":" in tail_after_drive:
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: Alternate Data Stream vietato in '{raw_s}'."
            )

        raw_parts = raw_s.replace("\\", "/").split("/")
        if ".." in self._raw_target.parts or ".." in raw_parts:
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: path traversal '..' vietato in target_dir '{raw_s}'."
            )

        skip_sym = _facade_attr("_is_symlink_or_reparse", _is_symlink_or_reparse)
        if skip_sym(self._raw_target):
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: symlink o junction vietato su target_dir '{self._raw_target}'."
            )

        curr_anc = self._raw_target.parent
        while curr_anc != curr_anc.parent:
            if curr_anc.exists() and curr_anc.is_symlink():
                raise ValueError(
                    f"Violazione [RULE-PROJECT-ISOLATION]: symlink antenato vietato '{curr_anc}'."
                )
            if curr_anc.exists() and skip_sym(curr_anc):
                if len(curr_anc.parts) > 2:
                    raise ValueError(
                        f"Violazione [RULE-PROJECT-ISOLATION]: junction antenata vietata '{curr_anc}'."
                    )
            curr_anc = curr_anc.parent

        real_target = Path(os.path.realpath(str(self._raw_target)))
        real_hub = Path(os.path.realpath(str(self.hub_root)))
        self._assert_not_readonly_online(real_target)

        for cand_t, cand_h in (
            (self.target_dir, self.hub_root),
            (real_target, real_hub),
        ):
            is_inside_hub = cand_t == cand_h or (
                cand_h in cand_t.parents
                and (
                    "NK_External_Projects" not in cand_t.parts
                    or cand_t.name == "NK_External_Projects"
                )
            )
            if is_inside_hub:
                raise ValueError(
                    f"Violazione [RULE-PROJECT-ISOLATION]: la cartella target '{self.target_dir}' "
                    f"non puo risiedere dentro NK-Hub ('{self.hub_root}')."
                )

    def _assert_safe_child_path(self, child_path: Path) -> None:
        """Garantisce che child_path resti confinato in target_dir senza escape."""
        skip_sym = _facade_attr("_is_symlink_or_reparse", _is_symlink_or_reparse)
        real_base = Path(os.path.realpath(str(self.target_dir)))
        curr = child_path
        while curr != self.target_dir and curr != curr.parent:
            if skip_sym(curr):
                raise ValueError(
                    f"Violazione [RULE-PROJECT-ISOLATION]: symlink o reparse point interno vietato '{curr}'."
                )
            curr = curr.parent
        real_child = Path(os.path.realpath(str(child_path)))
        if real_child != real_base and real_base not in real_child.parents:
            raise ValueError(
                f"Violazione [RULE-PROJECT-ISOLATION]: path escape rilevato '{child_path}' -> '{real_child}'."
            )

    def retrofit(self, dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """Adegua un progetto esistente creando solo cartelle e file mancanti."""
        return self.scaffold(retrofit=True, dry_run=dry_run, force=False)

    def scaffold(
        self,
        retrofit: Optional[bool] = None,
        dry_run: Optional[bool] = None,
        force: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Crea albero DDD, file di configurazione e Pentad Sovrana 4+1 in nk_genome/."""
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
            self._assert_safe_child_path(d)
            if not d.exists() and not is_dry_run:
                d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(d))

        def _write_file(rel_path: str, content: str) -> None:
            if ".." in Path(rel_path).parts:
                raise ValueError(
                    f"Violazione [RULE-PROJECT-ISOLATION]: traversal '..' vietato in '{rel_path}'."
                )
            fpath = self.target_dir / rel_path
            self._assert_safe_child_path(fpath)
            if fpath.exists():
                if is_retrofit or not is_force:
                    skipped_existing.append(rel_path)
                    return
            if not is_dry_run:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
            created_files.append(rel_path)

        static_map = build_static_project_templates(self.project_name, self.target_dir)
        for rel_p in (
            ".staging/.gitkeep",
            "nk_tracking/quality_baseline.json",
            "requirements.txt",
            "pytest.ini",
            ".gitignore",
            "README.md",
        ):
            _write_file(rel_p, static_map[rel_p])

        skip_sym = _facade_attr("_is_symlink_or_reparse", _is_symlink_or_reparse)
        pentad_files = build_pentad_genome_templates(self.project_name)
        for p_name, p_body in pentad_files.items():
            legacy_cand = self.target_dir / "genome" / p_name
            effective_body = p_body
            if (
                not skip_sym(self.target_dir / "genome")
                and not skip_sym(legacy_cand)
                and legacy_cand.exists()
                and legacy_cand.is_file()
            ):
                try:
                    self._assert_safe_child_path(legacy_cand)
                    effective_body = legacy_cand.read_text(encoding="utf-8")
                except Exception:
                    effective_body = p_body
            _write_file(f"nk_genome/{p_name}", effective_body)

        init_content = build_package_init_content(self.project_name)
        for pkg_rel in PACKAGE_INIT_TARGETS:
            _write_file(pkg_rel, init_content)

        _write_file("tests/test_ast_purity.py", static_map["tests/test_ast_purity.py"])

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


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI per external_project_scaffolder."""
    parser = argparse.ArgumentParser(
        description="NK Hub Generation 1.0.0-Generation Deterministic External Project Scaffolder"
    )
    parser.add_argument("--name", type=str, required=True, help="Nome del progetto da inizializzare")
    parser.add_argument("--target", type=str, required=False, default=None, help="Percorso assoluto esterno a NK-Hub")
    parser.add_argument("--retrofit", action="store_true", help="Adegua un progetto esistente senza sovrascrivere")
    parser.add_argument("--dry-run", action="store_true", help="Simula le operazioni senza scrivere su disco")
    parser.add_argument("--force", action="store_true", help="Forza la sovrascrittura dei file in modalita standard")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato in formato JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per lo scaffolder dei progetti esterni."""
    reconfigure_streams()
    args = _build_cli_parser().parse_args(argv)
    ws_root = Path(_facade_attr("_workspace_root", _workspace_root))
    default_ext_root = _resolve_default_external_root(ws_root)
    target_str = args.target if args.target is not None else str(default_ext_root / args.name)
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
