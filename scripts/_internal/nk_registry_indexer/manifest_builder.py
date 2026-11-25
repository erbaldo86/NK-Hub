"""Costruzione del manifesto SSOT e rendering deterministico di SKILL_INDEX.md."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from _internal.nk_registry_indexer.taxonomy import DOMAIN_TAXONOMY


def _scan_docs_dir(
    base: Path,
    compute_sha256: Callable[[Path], str],
    docs_index: Dict[str, Dict[str, Any]],
) -> None:
    """Scansiona una singola directory nk_docs_and_setup/ popolando docs_index."""
    try:
        with os.scandir(base) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if entry.name.lower().endswith(".zip"):
                    continue
                fpath = Path(entry.path)
                st = entry.stat(follow_symlinks=False)
                docs_index[entry.name] = {
                    "name": entry.name,
                    "relative_path": f"nk_docs_and_setup/{entry.name}",
                    "size_bytes": st.st_size,
                    "sha256": compute_sha256(fpath),
                }
    except OSError:
        pass


def scan_docs_and_setup_impl(self) -> Dict[str, Dict[str, Any]]:
    """Indicizza i file documentali e di setup presenti in nk_docs_and_setup/."""
    docs_index: Dict[str, Dict[str, Any]] = {}
    for base in (
        self.workspace_root / "nk_docs_and_setup",
        self.stage_dir / "nk_docs_and_setup",
    ):
        _scan_docs_dir(base, self._compute_sha256, docs_index)
    return dict(sorted(docs_index.items()))


def resolve_library_path_impl(self, filename: str) -> Optional[str]:
    """Risolve in O(1) il percorso relativo di un file della libreria NK-Hub."""
    clean = (filename or "").strip().replace("\\", "/").lstrip("/")
    if not clean:
        return None
    base_name = clean.split("/")[-1]
    manifest = self.load_manifest()
    if manifest is not None:
        docs_idx = manifest.get("docs_and_setup_index", {})
        if base_name in docs_idx:
            return str(docs_idx[base_name]["relative_path"])
        scripts_idx = manifest.get("scripts_index", {})
        if clean in scripts_idx:
            return str(scripts_idx[clean]["path"])
        if base_name in scripts_idx:
            return str(scripts_idx[base_name]["path"])

    candidates = (
        f"nk_docs_and_setup/{base_name}",
        f"nk_genome/{base_name}",
        f"scripts/{base_name}",
        f".agents/{base_name}",
        clean,
    )
    for rel in candidates:
        if (self.workspace_root / rel).exists():
            return rel
    return None


def _collect_domain_ordered_names(
    canonical_names: Sequence[str],
    entity_index: Dict[str, Dict[str, Any]],
    dom_id: str,
) -> List[str]:
    """Combina i nomi canonici seguiti da quelli dinamici appartenenti a dom_id."""
    canonical: List[str] = []
    for name in canonical_names:
        if name in entity_index and entity_index[name]["domain_id"] == dom_id:
            canonical.append(name)
    dynamic: List[str] = []
    for name, meta in sorted(entity_index.items()):
        if meta["domain_id"] == dom_id and name not in canonical:
            dynamic.append(name)
    return (canonical + dynamic) or list(canonical_names)


def _build_domain_entry(
    dom_id: str,
    dom_meta: Dict[str, Any],
    skills_index: Dict[str, Dict[str, Any]],
    scripts_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Costruisce la voce di dominio per nk_registry_manifest.json."""
    return {
        "domain_id": dom_id,
        "name": dom_meta["name"],
        "title": dom_meta["title"],
        "description": dom_meta["description"],
        "primary_skill": dom_meta["primary_skill"],
        "skills": _collect_domain_ordered_names(
            dom_meta["skills"], skills_index, dom_id
        ),
        "scripts": _collect_domain_ordered_names(
            dom_meta["scripts"], scripts_index, dom_id
        ),
        "keywords": list(dom_meta["keywords"]),
    }


def build_manifest_impl(self) -> Dict[str, Any]:
    """Genera il dizionario completo di nk_registry_manifest.json con Hot-Swap dinamico."""
    skills_index = self.scan_skills()
    scripts_index = self.scan_scripts()
    native_agents_index = self.scan_native_agents()

    domains_payload: Dict[str, Dict[str, Any]] = {}
    for dom_id, dom_meta in DOMAIN_TAXONOMY.items():
        domains_payload[dom_id] = _build_domain_entry(
            dom_id, dom_meta, skills_index, scripts_index
        )

    docs_and_setup_index = self.scan_docs_and_setup()
    hygiene_profile = self.scan_global_hygiene_profile(len(skills_index))
    dispatch_table = self.build_intent_dispatch_table()

    return {
        "version": self.MANIFEST_VERSION,
        "release_version": self.RELEASE_VERSION,
        "milestone_anchor_id": self.MILESTONE_ID,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "total_domains": len(domains_payload),
            "total_skills": len(skills_index),
            "total_scripts": len(scripts_index),
            "total_native_agents": len(native_agents_index),
            "total_docs_and_setup": len(docs_and_setup_index),
            "crv_macro_phases": 4,
        },
        "domains": domains_payload,
        "skills_index": skills_index,
        "scripts_index": scripts_index,
        "native_agents_index": native_agents_index,
        "docs_and_setup_index": docs_and_setup_index,
        "intent_dispatch_table": dispatch_table,
        "global_hygiene_profile": hygiene_profile,
    }


def render_skill_index_markdown_impl(self, manifest: Dict[str, Any]) -> str:
    """Genera SKILL_INDEX.md compatto (<= 3.200 B) e conforme allo standard ASD-STE100."""
    summary = manifest["summary"]
    hygiene = manifest["global_hygiene_profile"]
    lines: List[str] = [
        "---",
        'title: "NK Genome: Skill Index O(1)"',
        f'version: "{manifest["version"]}"',
        f'release_version: "{manifest.get("release_version", self.RELEASE_VERSION)}"',
        'rsi_profile: "ste100_rsi"',
        "---",
        "",
        "# Indice Skill O(1) (`SKILL_INDEX.md`)",
        "",
        f"Manifesto `{manifest.get('version', self.MANIFEST_VERSION)}` con `{summary['total_domains']}` domini (`7` shard), `{summary['total_skills']}` skill e `{summary['total_scripts']}` script.",
        "",
        "## 1. Domini Funzionali (`DOM-01..DOM-05`)",
        "",
        "| ID | Nome | Skill Primaria | Skill | Script | Shard |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for dom_id, dom_info in sorted(manifest["domains"].items()):
        lines.append(
            f"| {dom_id} | {dom_info['name']} | {dom_info['primary_skill']} | {len(dom_info['skills'])} | {len(dom_info['scripts'])} | `shards/{dom_id}.json` |"
        )

    lines.extend(
        [
            "",
            "## 2. Skill Canoniche",
            "",
            "| Skill | Dominio | Sub-Agente | Livello | SHA-256 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for sk_name, sk_meta in sorted(manifest["skills_index"].items()):
        sub_ag = sk_meta.get("native_subagent") or self._resolve_skill_native_subagent(
            sk_name, sk_meta.get("domain_id", "DOM-02")
        )
        lines.append(
            f"| {sk_name} | {sk_meta['domain_id']} | {sub_ag} | {sk_meta['thinking_level']} | {sk_meta['sha256'][:8]} |"
        )

    lines.extend(
        [
            "",
            "## 3. Script, Igiene e Lookup",
            "",
            f"Igiene globale: `{hygiene['external_skills_count']}` skill esterne attive su `{hygiene['total_flat_skills']}` totali.",
            "Dettagli CLI e SHA script risiedono in `shards/DOM-00.json`..`DOM-06.json`.",
            "Usa `nk_registry_indexer.py --lookup DOM-01` o `--verify` per controllo O(1).",
            "",
        ]
    )
    return "\n".join(lines)
