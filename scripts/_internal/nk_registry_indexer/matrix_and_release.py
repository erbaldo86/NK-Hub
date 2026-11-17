"""Generazione matrice di certificazione TAS e pacchetto ZIP di rilascio."""

from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List


def generate_tas_certification_matrix_impl(self) -> str:
    """Genera la tabella Markdown certificata di script, schemi, skill e sub-agenti con domini e SHA-256."""
    manifest = self.load_manifest()
    if not manifest or not manifest.get("scripts_index"):
        manifest = self.build_manifest()

    scripts_idx = manifest.get("scripts_index", {})
    skills_idx = manifest.get("skills_index", {})
    agents_idx = manifest.get("native_agents_index", {})
    schema_count = sum(1 for k in scripts_idx if k.startswith("schemas/"))
    script_only_count = len(scripts_idx) - schema_count

    lines: List[str] = [
        f"# Matrice di Certificazione TAS ({len(scripts_idx)} Script inclusi {schema_count} Schemi, {len(skills_idx)} Skill, {len(agents_idx)} Sub-Agenti Nativi)",
        "",
        f"## 1. Script e Schemi Certificati ({len(scripts_idx)} file: {script_only_count} Script + {schema_count} Schemi)",
        "",
        "| # | Script / Schema | Dominio | Path Relativo | SHA-256 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for idx, (sc_key, sc_info) in enumerate(sorted(scripts_idx.items()), start=1):
        dom_id = sc_info.get("domain_id", "DOM-03")
        rel_p = sc_info.get("path", f"scripts/{sc_key}")
        sha = sc_info.get("sha256", "")
        lines.append(f"| {idx} | `{sc_key}` | `{dom_id}` | `{rel_p}` | `{sha}` |")

    lines.extend(
        [
            "",
            f"## 2. Skill Modulari Certificate ({len(skills_idx)} Skill)",
            "",
            "| # | Skill | Dominio | Sub-Agente Nativo | Path Relativo | SHA-256 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for idx, (sk_name, sk_info) in enumerate(sorted(skills_idx.items()), start=1):
        dom_id = sk_info.get("domain_id", "DOM-01")
        sub_ag = sk_info.get("native_subagent") or self._resolve_skill_native_subagent(
            sk_name, dom_id
        )
        rel_p = sk_info.get("path", f".agents/skills/{sk_name}/SKILL.md")
        sha = sk_info.get("sha256", "")
        lines.append(
            f"| {idx} | `{sk_name}` | `{dom_id}` | `{sub_ag}` | `{rel_p}` | `{sha}` |"
        )

    lines.extend(
        [
            "",
            f"## 3. Sub-Agenti Nativi Certificati ({len(agents_idx)} Sub-Agenti)",
            "",
            "| # | Sub-Agente Nativo | Dominio | Write Tools | Path Relativo | SHA-256 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for idx, (ag_name, ag_info) in enumerate(sorted(agents_idx.items()), start=1):
        dom_id = ag_info.get("domain_id", "DOM-01")
        w_tools = str(bool(ag_info.get("enable_write_tools", False))).lower()
        rel_p = ag_info.get("path", f".agents/agents/{ag_name}.md")
        sha = ag_info.get("sha256", "")
        lines.append(
            f"| {idx} | `{ag_name}` | `{dom_id}` | `{w_tools}` | `{rel_p}` | `{sha}` |"
        )

    return "\n".join(lines) + "\n"


def build_release_zip_impl(self, output_path: Path) -> Dict[str, Any]:
    """Crea un pacchetto ZIP pulito con prefisso radice NK_Hub/ escludendo artefatti effimeri."""
    t0 = time.perf_counter()
    out_zip = Path(output_path).resolve()
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = out_zip.with_suffix(f"{out_zip.suffix}.tmp")

    excluded_dirs = {
        ".staging",
        "__pycache__",
        ".wal",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "ENV",
        "node_modules",
        ".archive",
        "anchor",
        "handoff",
        "cockpit",
        "sessions",
    }
    excluded_suffixes = (".pyc", ".pyo", ".pyd", ".tmp", ".log", ".zip")
    excluded_filenames = {
        ".coverage",
        ".wal_2pc.jsonl",
        "session_anchor.jsonl",
        "session_bootstrap_state.json",
        "session_handoff_latest.json",
        "next_session_prompt.md",
        "active_context.md",
        "dast_last_report.json",
    }
    excluded_prefixes = (
        ".coverage.",
        "dast_report_",
        "FORENSIC_INSPECTOR_",
        "PROMPT_A_",
        "PROMPT_B_",
    )

    files_archived = 0
    with zipfile.ZipFile(
        tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for cur_root, dirnames, filenames in os.walk(self.workspace_root):
            dirnames[:] = sorted(
                d for d in dirnames if d not in excluded_dirs
            )
            cur_path = Path(cur_root)
            for fname in sorted(filenames):
                if (
                    fname in excluded_filenames
                    or fname.startswith(excluded_prefixes)
                    or ".bak" in fname
                ):
                    continue
                fpath = cur_path / fname
                try:
                    resolved_f = fpath.resolve()
                except OSError:
                    continue
                if resolved_f in (out_zip, tmp_zip):
                    continue
                if fpath.suffix.lower() in excluded_suffixes:
                    continue
                rel_posix = fpath.relative_to(self.workspace_root).as_posix()
                if any(part in excluded_dirs for part in rel_posix.split("/")):
                    continue
                zf.write(fpath, arcname=f"NK_Hub/{rel_posix}")
                files_archived += 1

        # Includi i manifesti Bridge alla radice ZIP (fuori NK_Hub/) e NK_External_Projects/.gitkeep
        zf.writestr(
            ".agents/skills.json",
            '{\n  "entries": [\n    {\n      "path": "NK_Hub/.agents/skills"\n    }\n  ]\n}\n',
        )
        zf.writestr(
            ".agents/plugins.json",
            '{\n  "entries": [\n    {\n      "path": "NK_Hub/.agents/plugins"\n    }\n  ]\n}\n',
        )
        bridge_candidates = (
            self.stage_dir / "nk_docs_and_setup" / "root_bridge_AGENTS.md",
            self.workspace_root / "nk_docs_and_setup" / "root_bridge_AGENTS.md",
            self.workspace_root.parent / ".agents" / "AGENTS.md",
        )
        bridge_text = ""
        for bc in bridge_candidates:
            if bc.is_file():
                bridge_text = bc.read_text(encoding="utf-8", errors="replace")
                break
        if bridge_text:
            zf.writestr(".agents/AGENTS.md", bridge_text)
        zf.writestr("NK_External_Projects/.gitkeep", "")
        files_archived += 4 if bridge_text else 3

    os.replace(str(tmp_zip), str(out_zip))
    size_bytes = out_zip.stat().st_size
    return {
        "status": "OK",
        "passed": True,
        "zip_path": str(out_zip),
        "root_prefix": "NK_Hub/",
        "files_archived": files_archived,
        "size_bytes": size_bytes,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
    }
