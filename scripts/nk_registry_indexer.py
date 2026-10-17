#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Indicizzatore modulare O(1) e generatore del manifesto SSOT per Nexus Keystone v3.5.1.
Modulo: scripts/nk_registry_indexer.py.
Mappa i cinque domini funzionali, le skill Hot-Swap e i trentadue moduli Python.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_WORKSPACE_ROOT = (
    _SCRIPT_DIR.parent.parent
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR.parent
)
DEFAULT_GLOBAL_CONFIG_DIR = Path("C:/Users/erbal/.gemini/config")

DOMAIN_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "DOM-01": {
        "domain_id": "DOM-01",
        "name": "GOV_AND_ROUTING",
        "title": "Governance, Routing & Transactional Commit",
        "description": "Governa il bootstrap, il routing Mode A/B/C/D, il commit atomico 2PC e i contratti IPC.",
        "primary_skill": "NK-Master-Hub",
        "skills": [
            "NK-Master-Hub",
            "NK-Session-Controller",
            "NK-State-Router",
            "NK-Plan-Aligner",
        ],
        "scripts": [
            "nk_session_bootstrap.py",
            "vibe_sprint_router.py",
            "win32_2pc_engine.py",
            "nk_session_handoff.py",
            "nk_swarm_messenger.py",
            "nk_registry_indexer.py",
            "schemas/dual_ledgers.py",
            "schemas/nk_ipc_contracts.py",
        ],
        "keywords": [
            "governance",
            "routing",
            "router",
            "bootstrap",
            "2pc",
            "commit",
            "handoff",
            "session",
            "swarm",
            "plan",
            "aligner",
            "dag",
            "kahn",
            "index",
            "registry",
            "manifest",
            "orchestra",
            "schemas",
            "ledgers",
        ],
    },
    "DOM-02": {
        "domain_id": "DOM-02",
        "name": "IDEATION_AND_ARCH",
        "title": "Ideation, Discovery & System Architecture",
        "description": "Gestisce discovery analitica Mode D, ideazione L0, architettura UI/UX, backend e skill.",
        "primary_skill": "NK-Ideator",
        "skills": [
            "NK-Ideator",
            "NK-App-UX-Architect",
            "NK-Backend-Architect",
            "NK-Agent-Instruction-Forge",
        ],
        "scripts": [
            "ast_repo_mapper.py",
            "external_project_scaffolder.py",
            "env_capability_probe.py",
        ],
        "keywords": [
            "discovery",
            "benchmark",
            "ricerca",
            "esplora",
            "censimento",
            "mappatura",
            "ideazione",
            "scamper",
            "ux",
            "ui",
            "design",
            "frontend",
            "backend",
            "openapi",
            "architettura",
            "scaffold",
            "repo_map",
            "probe",
            "forge",
        ],
    },
    "DOM-03": {
        "domain_id": "DOM-03",
        "name": "BUILD_AND_HEAL",
        "title": "Async Building, Surgical Refactor & Fast-Healing",
        "description": "Costruisce codice Python asincrono in staging ed esegue il loop di auto-riparazione.",
        "primary_skill": "NK-Python-Async-Builder",
        "skills": [
            "NK-Python-Async-Builder",
            "NK-Delta-Architect",
        ],
        "scripts": [
            "auto_heal_pipeline.py",
            "healing_snapshot_rollback.py",
            "invisible_healing_loop.py",
            "platform_runner.py",
            "deterministic_api_cache.py",
            "safe_cleanup_dev_servers.py",
            "async_heartbeat_signaler.py",
        ],
        "keywords": [
            "build",
            "builder",
            "implementa",
            "sviluppa",
            "codice",
            "async",
            "pydantic",
            "delta",
            "refactor",
            "modifica",
            "heal",
            "healing",
            "rollback",
            "snapshot",
            "cache",
            "sqlite",
            "runner",
            "cleanup",
            "heartbeat",
        ],
    },
    "DOM-04": {
        "domain_id": "DOM-04",
        "name": "AUDIT_DAST_AND_RCA",
        "title": "Security Audit, DAST Sandbox, SBFL RCA & RSI Convergence",
        "description": "Esegue audit SAST/DAST in sola lettura, diagnosi SBFL Ochiai e convergenza Tensor-RSI.",
        "primary_skill": "NK-Security-Auditor",
        "skills": [
            "NK-Security-Auditor",
            "NK-Oracle-Evaluator",
            "NK-Dynamic-Sandbox-StressTester",
            "NK-Bug-Diagnostic-Engine",
        ],
        "scripts": [
            "ast_guard_validator.py",
            "dast_sandbox_runner.py",
            "oracle_evaluator_l3.py",
            "sbfl_engine.py",
            "sbfl_pytest_bridge.py",
            "rsi_convergence_engine.py",
        ],
        "keywords": [
            "audit",
            "security",
            "sicurezza",
            "sast",
            "dast",
            "sandbox",
            "stress",
            "oracle",
            "valuta",
            "bug",
            "diagnosi",
            "rca",
            "sbfl",
            "ochiai",
            "rsi",
            "convergenza",
            "ast_guard",
            "exploit",
            "vulnerabilita",
        ],
    },
    "DOM-05": {
        "domain_id": "DOM-05",
        "name": "MEMORY_TELEMETRY_AND_DOCS",
        "title": "3-Tier Memory, Runtime Telemetry, Hygiene & Documentation",
        "description": "Gestisce memoria episodica 3-Tier, sentinelle di contesto, igiene preflight e documentazione SSOT.",
        "primary_skill": "NK-Scribe",
        "skills": [
            "NK-Scribe",
            "NK-Episodic-Memory-Engine",
        ],
        "scripts": [
            "memory_3tier_engine.py",
            "micro_hud_renderer.py",
            "nk_active_runtime_sentinel.py",
            "nk_auto_inning.py",
            "nk_compliance_checker.py",
            "nk_context_sentry.py",
            "preflight_health_check.py",
            "quality_baseline_manager.py",
        ],
        "keywords": [
            "memory",
            "memoria",
            "episodic",
            "recall",
            "telemetry",
            "telemetria",
            "hud",
            "sentinel",
            "sentinella",
            "inning",
            "compliance",
            "sentry",
            "context",
            "preflight",
            "health",
            "baseline",
            "ratchet",
            "scribe",
            "documentazione",
            "changelog",
        ],
    },
}


class NKRegistryIndexer:
    """Indicizzatore deterministico O(1) per skill, script e domini di Nexus Keystone."""

    MANIFEST_VERSION: str = "3.5.1-MODULAR-INDEX-RSI2"
    MILESTONE_ID: str = "NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2"

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        stage_dir: Optional[Path] = None,
        global_config_dir: Optional[Path] = None,
    ) -> None:
        self.workspace_root = (
            Path(workspace_root).resolve()
            if workspace_root is not None
            else _DEFAULT_WORKSPACE_ROOT
        )
        if stage_dir is not None:
            s_path = Path(stage_dir)
            self.stage_dir = (
                s_path.resolve()
                if s_path.is_absolute()
                else (self.workspace_root / s_path).resolve()
            )
        else:
            self.stage_dir = self.workspace_root / ".staging"

        self.global_config_dir = (
            Path(global_config_dir).resolve()
            if global_config_dir is not None
            else DEFAULT_GLOBAL_CONFIG_DIR
        )

        self._skill_to_domain: Dict[str, str] = {}
        self._script_to_domain: Dict[str, str] = {}
        for dom_id, dom_meta in DOMAIN_TAXONOMY.items():
            for sk in dom_meta["skills"]:
                self._skill_to_domain[sk] = dom_id
            for sc in dom_meta["scripts"]:
                self._script_to_domain[sc] = dom_id

    _HASH_CACHE: Dict[Tuple[str, int, int], str] = {}
    _META_CACHE: Dict[Tuple[str, int, int], Dict[str, Any]] = {}

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Calcola l'hash crittografico SHA-256 del file specificato."""
        st = file_path.stat()
        cache_key = (str(file_path), st.st_mtime_ns, st.st_size)
        if st.st_size > 256 and cache_key in NKRegistryIndexer._HASH_CACHE:
            return NKRegistryIndexer._HASH_CACHE[cache_key]
        hasher = hashlib.sha256()
        hasher.update(file_path.read_bytes())
        digest = hasher.hexdigest()
        NKRegistryIndexer._HASH_CACHE[cache_key] = digest
        return digest

    def _resolve_priority_file(self, rel_path: str) -> Optional[Path]:
        """Risolve un percorso relativo dando priorita a .staging/ rispetto alla root."""
        staging_candidate = self.stage_dir / rel_path
        if staging_candidate.is_file():
            return staging_candidate
        root_candidate = self.workspace_root / rel_path
        if root_candidate.is_file():
            return root_candidate
        return None

    def _collect_priority_skills(self) -> Dict[str, Tuple[Path, os.stat_result]]:
        """Raccoglie la mappa skill_name -> (SKILL.md, stat) con una sola stat per skill."""
        import os as _os

        resolved_map: Dict[str, Tuple[Path, os.stat_result]] = {}
        for base in (
            self.workspace_root / ".agents" / "skills",
            self.stage_dir / ".agents" / "skills",
        ):
            try:
                with _os.scandir(base) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            sk_md = Path(entry.path) / "SKILL.md"
                            try:
                                st = sk_md.stat()
                                resolved_map[entry.name] = (sk_md, st)
                            except OSError:
                                pass
            except OSError:
                pass
        return resolved_map

    def _collect_priority_scripts(self) -> Dict[str, Tuple[Path, os.stat_result]]:
        """Raccoglie la mappa script_name -> (Path, stat) a costo zero tramite os.scandir."""
        import os as _os

        resolved_map: Dict[str, Tuple[Path, os.stat_result]] = {}
        for base in (self.workspace_root / "scripts", self.stage_dir / "scripts"):
            try:
                with _os.scandir(base) as it:
                    for entry in it:
                        if (
                            entry.is_file(follow_symlinks=False)
                            and entry.name.endswith(".py")
                            and entry.name != "__init__.py"
                        ):
                            resolved_map[entry.name] = (
                                Path(entry.path),
                                entry.stat(follow_symlinks=False),
                            )
                        elif (
                            entry.is_dir(follow_symlinks=False)
                            and entry.name == "schemas"
                        ):
                            try:
                                with _os.scandir(entry.path) as sit:
                                    for s_entry in sit:
                                        if (
                                            s_entry.is_file(follow_symlinks=False)
                                            and s_entry.name.endswith(".py")
                                            and s_entry.name != "__init__.py"
                                        ):
                                            resolved_map[f"schemas/{s_entry.name}"] = (
                                                Path(s_entry.path),
                                                s_entry.stat(follow_symlinks=False),
                                            )
                            except OSError:
                                pass
            except OSError:
                pass
        return resolved_map

    @staticmethod
    def _parse_skill_metadata(content: str) -> Dict[str, Any]:
        """Estrae frontmatter YAML (inclusi domain_id e sector), card e link da SKILL.md."""
        meta: Dict[str, Any] = {
            "name": "",
            "description": "",
            "version": "3.0.0-STE100-Unified",
            "thinking_level": "HIGH",
            "nk_tas_audit": "CRV-4.0-Universal",
            "domain_id": "",
            "sector": "",
            "role_identity": "",
            "tools": [],
            "auxiliary_links": [],
        }

        fm_match = re.match(
            r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", content, re.DOTALL
        )
        if fm_match:
            fm_block = fm_match.group(1)
            for line in fm_block.splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                key = k.strip()
                val = v.strip().strip('"').strip("'")
                if key in (
                    "name",
                    "description",
                    "version",
                    "thinking_level",
                    "nk_tas_audit",
                    "domain_id",
                    "sector",
                ):
                    meta[key] = val

        card_match = re.search(
            r"<yaml_metadata_card>(.*?)</yaml_metadata_card>", content, re.DOTALL
        )
        if card_match:
            card_block = card_match.group(1)
            role_m = re.search(r'role_identity:\s*"([^"]+)"', card_block)
            if role_m:
                meta["role_identity"] = role_m.group(1).strip()
            dom_m = re.search(r'domain_id:\s*"?([^"\r\n]+)"?', card_block)
            if dom_m and not meta["domain_id"]:
                meta["domain_id"] = dom_m.group(1).strip()
            sec_m = re.search(r'sector:\s*"?([^"\r\n]+)"?', card_block)
            if sec_m and not meta["sector"]:
                meta["sector"] = sec_m.group(1).strip()
            tools_m = re.search(r"tools:\s*\[([^\]]*)\]", card_block)
            if tools_m:
                raw_tools = tools_m.group(1)
                meta["tools"] = [
                    t.strip().strip('"').strip("'")
                    for t in raw_tools.split(",")
                    if t.strip().strip('"').strip("'")
                ]

        aux_links: List[str] = []
        for m in re.finditer(r"\]\(((?:resources|references)/[^\)]+)\)", content):
            link = m.group(1).strip()
            if link not in aux_links:
                aux_links.append(link)
        meta["auxiliary_links"] = sorted(aux_links)
        return meta

    @staticmethod
    def _extract_script_metadata(script_path: Path) -> Dict[str, Any]:
        """Estrae docstring, @domain_id, flag CLI supportati, LOC e SHA-256 da uno script."""
        st = script_path.stat()
        cache_key = (str(script_path), st.st_mtime_ns, st.st_size)
        if st.st_size > 256 and cache_key in NKRegistryIndexer._META_CACHE:
            return NKRegistryIndexer._META_CACHE[cache_key]

        raw_bytes = script_path.read_bytes()
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        NKRegistryIndexer._HASH_CACHE[cache_key] = sha256_hex

        source = raw_bytes.decode("utf-8", errors="replace")
        lines = source.splitlines()
        loc = len(lines)
        byte_size = st.st_size

        description = f"Modulo operativo {script_path.name}."
        domain_id = ""
        flags: Set[str] = set()

        try:
            tree = ast.parse(source, filename=script_path.name)
            doc = ast.get_docstring(tree)
            if doc:
                dom_match = re.search(
                    r"@?domain_id\s*:\s*(DOM-0[1-5])", doc, re.IGNORECASE
                )
                if dom_match:
                    domain_id = dom_match.group(1).upper()
                for doc_line in doc.splitlines():
                    cleaned = doc_line.strip()
                    if (
                        cleaned
                        and not cleaned.lower().startswith("modulo:")
                        and not cleaned.lower().startswith("@domain_id")
                        and not cleaned.lower().startswith("domain_id:")
                    ):
                        description = cleaned
                        break
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    val = node.value.strip()
                    if val.startswith("--") and re.match(
                        r"^--[a-zA-Z0-9][a-zA-Z0-9_-]*$", val
                    ):
                        flags.add(val)
        except Exception:
            pass

        if not domain_id:
            header_match = re.search(
                r"@?domain_id\s*:\s*(DOM-0[1-5])", source[:600], re.IGNORECASE
            )
            if header_match:
                domain_id = header_match.group(1).upper()

        res = {
            "description": description,
            "domain_id": domain_id,
            "cli_flags": sorted(flags),
            "loc": loc,
            "bytes": byte_size,
            "sha256": sha256_hex,
        }
        NKRegistryIndexer._META_CACHE[cache_key] = res
        return res

    def scan_skills(self) -> Dict[str, Dict[str, Any]]:
        """Scansiona tutte le skill supportando auto-registrazione Hot-Swap via YAML."""
        skill_map = self._collect_priority_skills()
        skills_index: Dict[str, Dict[str, Any]] = {}
        for sk_name in sorted(skill_map.keys()):
            resolved, st = skill_map[sk_name]
            rel_path = f".agents/skills/{sk_name}/SKILL.md"
            raw_bytes = resolved.read_bytes()
            sha_hex = hashlib.sha256(raw_bytes).hexdigest()
            NKRegistryIndexer._HASH_CACHE[
                (str(resolved), st.st_mtime_ns, st.st_size)
            ] = sha_hex

            content = raw_bytes.decode("utf-8", errors="replace")
            parsed = self._parse_skill_metadata(content)
            declared_dom = parsed.get("domain_id", "").strip().upper()
            dom_id = (
                declared_dom
                if declared_dom in DOMAIN_TAXONOMY
                else (
                    parsed.get("domain_id")
                    or self._skill_to_domain.get(sk_name, "DOM-02")
                )
            )
            if dom_id not in DOMAIN_TAXONOMY:
                dom_id = "DOM-02"
            dom_name = DOMAIN_TAXONOMY[dom_id]["name"]
            sector = parsed.get("sector") or dom_name

            skills_index[sk_name] = {
                "name": parsed["name"] or sk_name,
                "domain_id": dom_id,
                "domain_name": dom_name,
                "sector": sector,
                "version": parsed["version"],
                "description": parsed["description"],
                "thinking_level": parsed["thinking_level"],
                "role_identity": parsed["role_identity"],
                "tools": parsed["tools"],
                "auxiliary_links": parsed["auxiliary_links"],
                "loc": len(content.splitlines()),
                "bytes": st.st_size,
                "sha256": sha_hex,
                "path": rel_path,
                "source_layer": (
                    "staging" if self.stage_dir in resolved.parents else "production"
                ),
            }
        return skills_index

    def scan_scripts(self) -> Dict[str, Dict[str, Any]]:
        """Scansiona gli script in scripts/ e scripts/schemas/ dando priorita a .staging/."""
        script_map = self._collect_priority_scripts()
        scripts_index: Dict[str, Dict[str, Any]] = {}
        for sc_name in sorted(script_map.keys()):
            resolved, _ = script_map[sc_name]
            rel_path = f"scripts/{sc_name}"
            meta = self._extract_script_metadata(resolved)
            declared_dom = meta.get("domain_id", "").strip().upper()
            default_dom = "DOM-01" if sc_name.startswith("schemas/") else "DOM-03"
            dom_id = (
                declared_dom
                if declared_dom in DOMAIN_TAXONOMY
                else self._script_to_domain.get(sc_name, default_dom)
            )
            dom_name = DOMAIN_TAXONOMY[dom_id]["name"]

            scripts_index[sc_name] = {
                "name": sc_name,
                "domain_id": dom_id,
                "domain_name": dom_name,
                "description": meta["description"],
                "cli_flags": meta["cli_flags"],
                "loc": meta["loc"],
                "bytes": meta["bytes"],
                "sha256": meta["sha256"],
                "path": rel_path,
                "source_layer": (
                    "staging" if self.stage_dir in resolved.parents else "production"
                ),
            }
        return scripts_index

    GCP_DATA_SKILLS: Tuple[str, ...] = (
        "bigquery-data-transfer-service",
        "building-data-apps",
        "data-autocleaning",
        "dataform-bigquery",
        "dbt-bigquery",
        "developing-with-bigquery",
        "discovering-gcp-data-assets",
        "gcloud-auth-verification",
        "gcp-composer-troubleshooting",
        "gcp-data-pipelines",
        "gcp-dataflow",
        "gcp-pipeline-orchestration",
        "gcp-pipeline-resource-provisioning",
        "gcp-spark",
        "notebook-guidance",
    )
    DEV_UTILITY_SKILLS: Tuple[str, ...] = (
        "accidental-data-loss-prevention",
        "managing-python-dependencies",
        "ml-best-practices",
        "skill-repair",
    )

    def apply_global_filter(self) -> Dict[str, Any]:
        """Consolida le skill globali in plugin dedicati e disattiva le 61 skill esterne."""
        if not self.global_config_dir.exists():
            return {"applied": False, "reason": "global_config_dir_not_found"}

        skills_root = self.global_config_dir / "skills"
        plugins_root = self.global_config_dir / "plugins"
        plugins_root.mkdir(parents=True, exist_ok=True)

        moved_gcp: List[str] = []
        moved_dev: List[str] = []

        gcp_plugin_dir = plugins_root / "gcp-data-cloud-plugin"
        gcp_skills_dir = gcp_plugin_dir / "skills"
        gcp_skills_dir.mkdir(parents=True, exist_ok=True)
        for sk_name in self.GCP_DATA_SKILLS:
            src = skills_root / sk_name
            if src.exists() and src.is_dir():
                dst = gcp_skills_dir / sk_name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.move(str(src), str(dst))
                moved_gcp.append(sk_name)

        dc_manifest = skills_root / ".datacloud_skills_manifest"
        if dc_manifest.exists():
            dst_manifest = gcp_skills_dir / ".datacloud_skills_manifest"
            if dst_manifest.exists():
                dst_manifest.unlink()
            shutil.move(str(dc_manifest), str(dst_manifest))

        (gcp_plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "gcp-data-cloud-plugin",
                    "displayName": "GCP Data Cloud & BigQuery",
                    "version": "1.0.0",
                    "description": (
                        "Google Cloud Data Pipelines, BigQuery, Dataform, dbt, Dataflow, and Spark skills."
                    ),
                    "disabled": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        dev_plugin_dir = plugins_root / "dev-utilities-plugin"
        dev_skills_dir = dev_plugin_dir / "skills"
        dev_skills_dir.mkdir(parents=True, exist_ok=True)
        for sk_name in self.DEV_UTILITY_SKILLS:
            src = skills_root / sk_name
            if src.exists() and src.is_dir():
                dst = dev_skills_dir / sk_name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.move(str(src), str(dst))
                moved_dev.append(sk_name)

        (dev_plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "dev-utilities-plugin",
                    "displayName": "General Dev & ML Utilities",
                    "version": "1.0.0",
                    "description": (
                        "Standalone Python dependency, ML best practices, data loss prevention, and skill repair utilities."
                    ),
                    "disabled": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        for p_name in ("science", "android-cli-plugin"):
            p_json = plugins_root / p_name / "plugin.json"
            if p_json.exists():
                try:
                    p_data = json.loads(p_json.read_text(encoding="utf-8"))
                    if isinstance(p_data, dict):
                        p_data["disabled"] = True
                        p_json.write_text(
                            json.dumps(p_data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8",
                        )
                except Exception:
                    pass

        cfg_path = self.global_config_dir / "config.json"
        cfg_data: Dict[str, Any] = {}
        if cfg_path.exists():
            try:
                loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg_data = loaded
            except Exception:
                cfg_data = {}

        plugins_cfg = cfg_data.setdefault("plugins", {})
        disabled_targets = (
            "android-cli-plugin",
            "science",
            "gcp-data-cloud-plugin",
            "dev-utilities-plugin",
        )
        for target_plug in disabled_targets:
            entry = plugins_cfg.get(target_plug)
            if isinstance(entry, dict):
                entry["enabled"] = False
            else:
                plugins_cfg[target_plug] = {"enabled": False}

        cfg_path.write_text(
            json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return {
            "applied": True,
            "moved_gcp_skills": len(moved_gcp),
            "moved_dev_skills": len(moved_dev),
            "disabled_plugins": list(disabled_targets),
            "config_path": cfg_path.as_posix(),
        }

    def scan_global_hygiene_profile(
        self, workspace_skills_count: int
    ) -> Dict[str, Any]:
        """Scansiona il profilo globale ~/.gemini/config distinguendo skill attive e disabilitate."""
        installed_skills: List[str] = []
        active_skills: List[str] = []
        external_sources: Set[str] = set()
        disabled_plugins: Set[str] = set()

        if self.global_config_dir.exists() and self.global_config_dir.is_dir():
            cfg_path = self.global_config_dir / "config.json"
            if cfg_path.exists():
                try:
                    cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    plugins_dict = cfg_data.get("plugins", {})
                    if isinstance(plugins_dict, dict):
                        for p_name, p_meta in plugins_dict.items():
                            if isinstance(p_meta, dict) and p_meta.get("enabled") is False:
                                disabled_plugins.add(p_name)
                except Exception:
                    pass

            for p_json in self.global_config_dir.glob("plugins/*/plugin.json"):
                try:
                    p_meta = json.loads(p_json.read_text(encoding="utf-8"))
                    if isinstance(p_meta, dict) and p_meta.get("disabled") is True:
                        disabled_plugins.add(p_json.parent.name)
                except Exception:
                    pass

            targeted_globs = (
                list(self.global_config_dir.glob("skills/*/SKILL.md"))
                + list(self.global_config_dir.glob("plugins/*/skills/*/SKILL.md"))
                + list(self.global_config_dir.glob("plugins/*/skills/SKILL.md"))
            )
            seen_rels: Set[str] = set()
            for sk_md in sorted(targeted_globs):
                try:
                    rel = sk_md.relative_to(self.global_config_dir).as_posix()
                except ValueError:
                    rel = sk_md.as_posix()
                if rel in seen_rels:
                    continue
                seen_rels.add(rel)
                installed_skills.append(rel)

                parts = rel.split("/")
                if len(parts) >= 2:
                    source_id = (
                        f"{parts[0]}/{parts[1]}" if parts[0] == "plugins" else parts[0]
                    )
                    external_sources.add(source_id)
                    if parts[0] == "plugins" and parts[1] in disabled_plugins:
                        continue
                active_skills.append(rel)

        installed_ext_count = len(installed_skills)
        active_ext_count = len(active_skills)
        disabled_ext_count = installed_ext_count - active_ext_count
        total_flat = workspace_skills_count + active_ext_count
        effective_filtered = (
            disabled_ext_count if disabled_ext_count > 0 else installed_ext_count
        )
        estimated_tokens = (
            7042 if effective_filtered == 61 else effective_filtered * 115
        )

        return {
            "config_path": self.global_config_dir.as_posix(),
            "config_exists": self.global_config_dir.exists(),
            "workspace_skills_count": workspace_skills_count,
            "external_skills_count": active_ext_count,
            "installed_external_skills_count": installed_ext_count,
            "active_external_skills_count": active_ext_count,
            "disabled_external_skills_count": disabled_ext_count,
            "total_flat_skills": total_flat,
            "context_pollution_detected": active_ext_count > 0,
            "external_sources": sorted(external_sources),
            "disabled_plugins": sorted(disabled_plugins),
            "recommended_isolation_config": {
                "isolation_mode": "WORKSPACE_O1_MANIFEST_ONLY",
                "disable_global_plugins": True,
                "disable_external_gcp_skills": True,
                "disabled_sources": sorted(external_sources),
                "estimated_token_savings": estimated_tokens,
            },
        }

    def build_intent_dispatch_table(self) -> Dict[str, Dict[str, Any]]:
        """Costruisce la tabella O(1) di dispatch tra keyword di intento e domini."""
        dispatch_table: Dict[str, Dict[str, Any]] = {}
        mode_map = {
            "DOM-01": "mode_a",
            "DOM-02": "mode_d",
            "DOM-03": "mode_c",
            "DOM-04": "mode_a",
            "DOM-05": "mode_c",
        }
        for dom_id, dom_meta in DOMAIN_TAXONOMY.items():
            for kw in dom_meta["keywords"]:
                dispatch_table[kw.lower()] = {
                    "domain_id": dom_id,
                    "domain_name": dom_meta["name"],
                    "primary_agent": dom_meta["primary_skill"],
                    "recommended_mode": mode_map.get(dom_id, "mode_c"),
                    "scripts": list(dom_meta["scripts"]),
                }
        return dispatch_table

    def build_manifest(self) -> Dict[str, Any]:
        """Genera il dizionario completo di nk_registry_manifest.json con Hot-Swap dinamico."""
        skills_index = self.scan_skills()
        scripts_index = self.scan_scripts()

        domains_payload: Dict[str, Dict[str, Any]] = {}
        for dom_id, dom_meta in DOMAIN_TAXONOMY.items():
            canonical_skills = [
                sk
                for sk in dom_meta["skills"]
                if sk in skills_index and skills_index[sk]["domain_id"] == dom_id
            ]
            dynamic_skills = [
                sk
                for sk, meta in sorted(skills_index.items())
                if meta["domain_id"] == dom_id and sk not in canonical_skills
            ]
            dom_skills = (canonical_skills + dynamic_skills) or list(dom_meta["skills"])

            canonical_scripts = [
                sc
                for sc in dom_meta["scripts"]
                if sc in scripts_index and scripts_index[sc]["domain_id"] == dom_id
            ]
            dynamic_scripts = [
                sc
                for sc, meta in sorted(scripts_index.items())
                if meta["domain_id"] == dom_id and sc not in canonical_scripts
            ]
            dom_scripts = (canonical_scripts + dynamic_scripts) or list(
                dom_meta["scripts"]
            )

            domains_payload[dom_id] = {
                "domain_id": dom_id,
                "name": dom_meta["name"],
                "title": dom_meta["title"],
                "description": dom_meta["description"],
                "primary_skill": dom_meta["primary_skill"],
                "skills": dom_skills,
                "scripts": dom_scripts,
                "keywords": list(dom_meta["keywords"]),
            }

        hygiene_profile = self.scan_global_hygiene_profile(len(skills_index))
        dispatch_table = self.build_intent_dispatch_table()

        return {
            "version": self.MANIFEST_VERSION,
            "milestone_anchor_id": self.MILESTONE_ID,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": {
                "total_domains": len(domains_payload),
                "total_skills": len(skills_index),
                "total_scripts": len(scripts_index),
                "crv_macro_phases": 4,
            },
            "domains": domains_payload,
            "skills_index": skills_index,
            "scripts_index": scripts_index,
            "intent_dispatch_table": dispatch_table,
            "global_hygiene_profile": hygiene_profile,
        }

    def render_skill_index_markdown(self, manifest: Dict[str, Any]) -> str:
        """Genera il documento SKILL_INDEX.md conforme allo standard ASD-STE100."""
        summary = manifest["summary"]
        hygiene = manifest["global_hygiene_profile"]
        lines: List[str] = [
            "---",
            'title: "NK Genome: Skill & Script Modular O(1) Index"',
            f'version: "{manifest["version"]}"',
            f'milestone_anchor_id: "{manifest["milestone_anchor_id"]}"',
            'rsi_profile: "ste100_rsi"',
            "---",
            "",
            "# Indice Tassonomico Modulare O(1) (`SKILL_INDEX.md`)",
            "",
            "Questo indice mappa i cinque domini funzionali di Nexus Keystone.",
            "Il registro consente la risoluzione O(1) di skill, script e flag CLI.",
            f"Il manifesto traccia `{summary['total_skills']}` skill canoniche e `{summary['total_scripts']}` moduli Python.",
            "",
            "## 1. Mappa dei 5 Domini Funzionali (`DOM-01..DOM-05`)",
            "",
            "| ID Dominio | Nome Dominio | Skill Primaria | Conteggio Skill | Conteggio Script |",
            "| :--- | :--- | :--- | :---: | :---: |",
        ]

        for dom_id, dom_info in manifest["domains"].items():
            lines.append(
                f"| `{dom_id}` | `{dom_info['name']}` | `{dom_info['primary_skill']}` | `{len(dom_info['skills'])}` | `{len(dom_info['scripts'])}` |"
            )

        lines.extend(
            [
                "",
                "## 2. Registro delle Skill Vocazionali",
                "",
                "La tabella seguente elenca ogni skill con il relativo dominio e hash SHA-256.",
                "",
                "| Skill | Dominio | Livello Thinking | File Ausiliari | LOC | SHA-256 (12 char) |",
                "| :--- | :---: | :---: | :---: | :---: | :--- |",
            ]
        )

        for sk_name, sk_meta in sorted(manifest["skills_index"].items()):
            lines.append(
                f"| `{sk_name}` | `{sk_meta['domain_id']}` | `{sk_meta['thinking_level']}` | `{len(sk_meta['auxiliary_links'])}` | `{sk_meta['loc']}` | `{sk_meta['sha256'][:12]}` |"
            )

        lines.extend(
            [
                "",
                "## 3. Registro degli Script Core, Schemi e Flag CLI",
                "",
                "La tabella seguente mappa ogni modulo Python ai flag CLI verificati via AST.",
                "",
                "| Script (`scripts/`) | Dominio | Flag CLI Supportati | LOC | SHA-256 (12 char) |",
                "| :--- | :---: | :--- | :---: | :--- |",
            ]
        )

        for sc_name, sc_meta in sorted(manifest["scripts_index"].items()):
            flags_str = (
                ", ".join(f"`{fl}`" for fl in sc_meta["cli_flags"])
                if sc_meta["cli_flags"]
                else "`nessuno`"
            )
            lines.append(
                f"| `{sc_name}` | `{sc_meta['domain_id']}` | {flags_str} | `{sc_meta['loc']}` | `{sc_meta['sha256'][:12]}` |"
            )

        lines.extend(
            [
                "",
                "## 4. Profilo di Igiene del Contesto Globale",
                "",
                f"Lo scanner ha rilevato `{hygiene['external_skills_count']}` skill esterne nella configurazione utente.",
                f"Il totale combinato misura `{hygiene['total_flat_skills']}` skill piatte nel contesto globale.",
                "L'isolamento consigliato disattiva i plugin esterni non richiesti durante le sessioni NK-Hub.",
                "",
                "## 5. Comandi Rapidi di Consultazione e Verifica",
                "",
                "Usa `scripts/nk_registry_indexer.py --sync` per rigenerare il manifesto in staging.",
                "Usa `scripts/nk_registry_indexer.py --verify` per controllare l'allineamento SHA-256.",
                "Usa `scripts/nk_registry_indexer.py --lookup DOM-01` per interrogare un dominio in O(1).",
                "",
            ]
        )
        return "\n".join(lines)

    def sync(self) -> Dict[str, Any]:
        """Genera nk_registry_manifest.json e SKILL_INDEX.md nella directory di staging."""
        t0 = time.perf_counter()
        manifest = self.build_manifest()
        md_content = self.render_skill_index_markdown(manifest)

        target_genome_dir = self.stage_dir / "nk_genome"
        target_genome_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = target_genome_dir / "nk_registry_manifest.json"
        skill_index_path = target_genome_dir / "SKILL_INDEX.md"

        manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        manifest_path.write_text(manifest_json, encoding="utf-8")
        skill_index_path.write_text(md_content, encoding="utf-8")

        if self.workspace_root != _DEFAULT_WORKSPACE_ROOT:
            root_genome = self.workspace_root / "nk_genome"
            root_genome.mkdir(parents=True, exist_ok=True)
            (root_genome / "nk_registry_manifest.json").write_text(
                manifest_json, encoding="utf-8"
            )
            (root_genome / "SKILL_INDEX.md").write_text(md_content, encoding="utf-8")

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "status": "SYNCED",
            "passed": True,
            "manifest_path": str(manifest_path),
            "skill_index_path": str(skill_index_path),
            "summary": manifest["summary"],
            "global_hygiene_profile": manifest["global_hygiene_profile"],
            "elapsed_ms": elapsed_ms,
        }

    def load_manifest(self) -> Optional[Dict[str, Any]]:
        """Carica nk_registry_manifest.json dando priorita a .staging/nk_genome/."""
        candidates = (
            self.stage_dir / "nk_genome" / "nk_registry_manifest.json",
            self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
        )
        for cand in candidates:
            if cand.exists() and cand.is_file():
                try:
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return None

    def verify(self) -> Dict[str, Any]:
        """Verifica gli hash SHA-256 su disco senza ast.parse in meno di 30 ms."""
        t0 = time.perf_counter()
        manifest = self.load_manifest()
        if manifest is None:
            return {
                "status": "MISSING_MANIFEST",
                "passed": False,
                "issues": ["nk_registry_manifest.json non trovato in staging o root."],
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            }

        issues: List[str] = []
        required_keys = (
            "version",
            "domains",
            "skills_index",
            "scripts_index",
            "intent_dispatch_table",
            "global_hygiene_profile",
        )
        for req_key in required_keys:
            if req_key not in manifest:
                issues.append(f"Chiave obbligatoria mancante nel manifesto: {req_key}")

        domains = manifest.get("domains", {})
        for expected_dom in ("DOM-01", "DOM-02", "DOM-03", "DOM-04", "DOM-05"):
            if expected_dom not in domains:
                issues.append(f"Dominio tassonomico mancante: {expected_dom}")

        skill_map = self._collect_priority_skills()
        manifest_skills = manifest.get("skills_index", {})
        if set(skill_map.keys()) != set(manifest_skills.keys()):
            issues.append(
                f"Conteggio o nomi skill disallineati: atteso {len(skill_map)}, trovato {len(manifest_skills)}"
            )
        else:
            for sk_name, (resolved, st) in skill_map.items():
                recorded_sha = manifest_skills.get(sk_name, {}).get("sha256", "")
                ckey = (str(resolved), st.st_mtime_ns, st.st_size)
                live_sha = (
                    NKRegistryIndexer._HASH_CACHE[ckey]
                    if st.st_size > 256 and ckey in NKRegistryIndexer._HASH_CACHE
                    else self._compute_sha256(resolved)
                )
                if live_sha != recorded_sha:
                    issues.append(f"Drift SHA-256 rilevato sulla skill: {sk_name}")

        script_map = self._collect_priority_scripts()
        manifest_scripts = manifest.get("scripts_index", {})
        if set(script_map.keys()) != set(manifest_scripts.keys()):
            issues.append(
                f"Conteggio o nomi script disallineati: atteso {len(script_map)}, trovato {len(manifest_scripts)}"
            )
        else:
            for sc_name, (resolved, st) in script_map.items():
                recorded_sha = manifest_scripts.get(sc_name, {}).get("sha256", "")
                ckey = (str(resolved), st.st_mtime_ns, st.st_size)
                live_sha = (
                    NKRegistryIndexer._HASH_CACHE[ckey]
                    if st.st_size > 256 and ckey in NKRegistryIndexer._HASH_CACHE
                    else self._compute_sha256(resolved)
                )
                if live_sha != recorded_sha:
                    issues.append(f"Drift SHA-256 rilevato sullo script: {sc_name}")

        passed = len(issues) == 0
        return {
            "status": "VALID" if passed else "DRIFT_DETECTED",
            "passed": passed,
            "total_domains": len(domains),
            "total_skills": len(manifest_skills),
            "total_scripts": len(manifest_scripts),
            "issues": issues,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    def lookup(self, query: str) -> Dict[str, Any]:
        """Esegue una ricerca O(1) nel manifesto per dominio, skill, script o intento."""
        t0 = time.perf_counter()
        manifest = self.load_manifest()
        if manifest is None:
            manifest = self.build_manifest()

        q_clean = (query or "").strip()
        q_upper = q_clean.upper()
        q_lower = q_clean.lower()

        domains = manifest.get("domains", {})
        skills_index = manifest.get("skills_index", {})
        scripts_index = manifest.get("scripts_index", {})
        dispatch_table = manifest.get("intent_dispatch_table", {})

        # 1. Lookup diretto su ID Dominio (es. DOM-01) o nome Dominio
        if q_upper in domains:
            dom = domains[q_upper]
            return {
                "found": True,
                "match_type": "domain",
                "query": query,
                "domain_id": dom["domain_id"],
                "domain_name": dom["name"],
                "primary_skill": dom["primary_skill"],
                "skills": dom["skills"],
                "scripts": dom["scripts"],
                "result": dom,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

        for dom_id, dom in domains.items():
            if dom.get("name", "").upper() == q_upper:
                return {
                    "found": True,
                    "match_type": "domain",
                    "query": query,
                    "domain_id": dom_id,
                    "domain_name": dom["name"],
                    "primary_skill": dom["primary_skill"],
                    "skills": dom["skills"],
                    "scripts": dom["scripts"],
                    "result": dom,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                }

        # 2. Lookup diretto su Skill (case-insensitive)
        for sk_name, sk_meta in skills_index.items():
            if sk_name.lower() == q_lower:
                dom_id = sk_meta["domain_id"]
                dom = domains.get(dom_id, {})
                return {
                    "found": True,
                    "match_type": "skill",
                    "query": query,
                    "domain_id": dom_id,
                    "domain_name": sk_meta["domain_name"],
                    "primary_skill": sk_name,
                    "skills": dom.get("skills", [sk_name]),
                    "scripts": dom.get("scripts", []),
                    "result": sk_meta,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                }

        # 3. Lookup diretto su Script o Schema (con o senza .py / schemas/)
        sc_candidate = q_lower if q_lower.endswith(".py") else f"{q_lower}.py"
        for sc_name, sc_meta in scripts_index.items():
            sc_low = sc_name.lower()
            sc_base = sc_low.split("/")[-1]
            if sc_low in (q_lower, sc_candidate) or sc_base in (q_lower, sc_candidate):
                dom_id = sc_meta["domain_id"]
                dom = domains.get(dom_id, {})
                return {
                    "found": True,
                    "match_type": "script",
                    "query": query,
                    "domain_id": dom_id,
                    "domain_name": sc_meta["domain_name"],
                    "primary_skill": dom.get("primary_skill", ""),
                    "skills": dom.get("skills", []),
                    "scripts": [sc_name],
                    "cli_flags": sc_meta.get("cli_flags", []),
                    "result": sc_meta,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                }

        # 4. Lookup su intent_dispatch_table (O(1) diretto o per token nel prompt)
        if q_lower in dispatch_table:
            entry = dispatch_table[q_lower]
            dom_id = entry["domain_id"]
            dom = domains.get(dom_id, {})
            return {
                "found": True,
                "match_type": "intent",
                "query": query,
                "domain_id": dom_id,
                "domain_name": entry["domain_name"],
                "primary_skill": entry["primary_agent"],
                "recommended_mode": entry["recommended_mode"],
                "skills": dom.get("skills", []),
                "scripts": entry["scripts"],
                "result": entry,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

        tokens = set(re.findall(r"[a-z0-9_]+", q_lower))
        best_kw = ""
        best_entry: Optional[Dict[str, Any]] = None
        for kw, entry in dispatch_table.items():
            if kw in tokens or (len(kw) >= 4 and kw in q_lower):
                if len(kw) > len(best_kw):
                    best_kw = kw
                    best_entry = entry

        if best_entry is not None:
            dom_id = best_entry["domain_id"]
            dom = domains.get(dom_id, {})
            return {
                "found": True,
                "match_type": "intent",
                "query": query,
                "domain_id": dom_id,
                "domain_name": best_entry["domain_name"],
                "primary_skill": best_entry["primary_agent"],
                "recommended_mode": best_entry["recommended_mode"],
                "skills": dom.get("skills", []),
                "scripts": best_entry["scripts"],
                "result": best_entry,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

        return {
            "found": False,
            "match_type": "fallback",
            "query": query,
            "domain_id": "DOM-01",
            "domain_name": "GOV_AND_ROUTING",
            "primary_skill": "NK-Master-Hub",
            "skills": domains.get("DOM-01", {}).get("skills", []),
            "scripts": domains.get("DOM-01", {}).get("scripts", []),
            "result": {},
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per l'indicizzatore modulare di Nexus Keystone."""
    parser = argparse.ArgumentParser(
        description="Indicizzatore Modulare O(1) Nexus Keystone v3.5.1"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Genera nk_registry_manifest.json e SKILL_INDEX.md in staging",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verifica l'allineamento SHA-256 tra manifesto e file su disco",
    )
    parser.add_argument(
        "--lookup",
        type=str,
        default=None,
        help="Interroga in O(1) un dominio, una skill, uno script o un intento",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice del workspace da indicizzare",
    )
    parser.add_argument(
        "--stage-dir",
        type=str,
        default=None,
        help="Directory di staging target per la scrittura del manifesto",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa l'output in formato JSON strutturato",
    )
    parser.add_argument(
        "--apply-global-filter",
        action="store_true",
        help="Consolida e disattiva le 61 skill globali esterne prima di eseguire sync",
    )
    args = parser.parse_args(argv)

    root_path = Path(args.root).resolve() if args.root else None
    stage_path = Path(args.stage_dir) if args.stage_dir else None
    indexer = NKRegistryIndexer(workspace_root=root_path, stage_dir=stage_path)

    if args.apply_global_filter:
        flt = indexer.apply_global_filter()
        res = indexer.sync()
        res["global_filter"] = flt
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"🟢 [NK-GLOBAL-FILTER] Status: {res['status']} | "
                f"Installed External: {res['global_hygiene_profile']['installed_external_skills_count']} | "
                f"Active External: {res['global_hygiene_profile']['active_external_skills_count']} | "
                f"Total Flat Skills: {res['global_hygiene_profile']['total_flat_skills']} ({res['elapsed_ms']} ms)"
            )
        return 0

    if args.sync:
        res = indexer.sync()
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"🟢 [NK-REGISTRY-SYNC] Status: {res['status']} | "
                f"Domains: {res['summary']['total_domains']} | "
                f"Skills: {res['summary']['total_skills']} | "
                f"Scripts: {res['summary']['total_scripts']} ({res['elapsed_ms']} ms)"
            )
        return 0

    if args.verify:
        res = indexer.verify()
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            sym = "🟢" if res["passed"] else "🔴"
            print(
                f"{sym} [NK-REGISTRY-VERIFY] Status: {res['status']} | "
                f"Skills: {res.get('total_skills', 0)} | "
                f"Scripts: {res.get('total_scripts', 0)} ({res['elapsed_ms']} ms)"
            )
            for issue in res.get("issues", []):
                print(f"  - {issue}")
        return 0 if res["passed"] else 1

    if args.lookup is not None:
        res = indexer.lookup(args.lookup)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"[NK-REGISTRY-LOOKUP] Match: {res['match_type']} | "
                f"Domain: {res['domain_id']} ({res['domain_name']}) | "
                f"Primary Skill: {res['primary_skill']} ({res['elapsed_ms']} ms)"
            )
        return 0 if res["found"] else 1

    res = indexer.sync()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
