"""Classe canonica NKRegistryIndexer con delega ai submoduli interni."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import DEFAULT_MILESTONE_ID, VERSION
from _internal.nk_registry_indexer.cache_and_skills import (
    collect_priority_skills_impl,
    compute_sha256_impl,
    get_persistent_cache_file_impl,
    get_persistent_meta_cache_file_impl,
    load_persistent_hash_cache_impl,
    load_staging_deleted_paths_impl,
    parse_skill_metadata_impl,
    resolve_genome_dir_impl,
    resolve_skill_native_subagent_impl,
    resolve_tetralogy_files_impl,
    save_persistent_hash_cache_impl,
    scan_skills_impl,
)
from _internal.nk_registry_indexer.governance_and_verify import (
    audit_gt14_crit01_entries_impl,
    sha256_matches_eol_normalized_impl,
    verify_gt14_crit01_governance_impl,
    verify_impl,
)
from _internal.nk_registry_indexer.hygiene_filter import (
    apply_global_filter_impl,
    build_intent_dispatch_table_impl,
    is_within_dir_impl,
    scan_global_hygiene_profile_impl,
)
from _internal.nk_registry_indexer.lookup import lookup_impl
from _internal.nk_registry_indexer.manifest_builder import (
    build_manifest_impl,
    render_skill_index_markdown_impl,
    resolve_library_path_impl,
    scan_docs_and_setup_impl,
)
from _internal.nk_registry_indexer.manifest_sync import (
    load_manifest_impl,
    sync_impl,
    sync_nk_gate_plugin_mirrors_impl,
)
from _internal.nk_registry_indexer.matrix_and_release import (
    build_release_zip_impl,
    generate_tas_certification_matrix_impl,
)
from _internal.nk_registry_indexer.scripts_and_agents import (
    collect_priority_native_agents_impl,
    collect_priority_scripts_impl,
    extract_script_metadata_impl,
    parse_native_agent_metadata_impl,
    scan_native_agents_impl,
    scan_scripts_impl,
)
from _internal.nk_registry_indexer.taxonomy import (
    DEFAULT_GLOBAL_CONFIG_DIR,
    DEV_UTILITY_SKILLS,
    DOMAIN_TAXONOMY,
    FORBIDDEN_PHANTOM_MCP_TOOLS,
    GCP_DATA_SKILLS,
    NATIVE_AGENT_DOMAIN_MAP,
    _DEFAULT_WORKSPACE_ROOT,
)


class NKRegistryIndexer:
    """Indicizzatore deterministico O(1) per skill, script, sub-agenti nativi e domini di NK Hub Generation."""

    MANIFEST_VERSION: str = VERSION
    RELEASE_VERSION: str = VERSION
    MILESTONE_ID: str = DEFAULT_MILESTONE_ID
    NATIVE_AGENT_DOMAIN_MAP: Dict[str, str] = NATIVE_AGENT_DOMAIN_MAP
    FORBIDDEN_PHANTOM_MCP_TOOLS: Tuple[str, ...] = FORBIDDEN_PHANTOM_MCP_TOOLS

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
        self._explicit_stage_dir = stage_dir is not None
        if stage_dir is not None:
            s_path = Path(stage_dir)
            self.stage_dir = (
                s_path.resolve()
                if s_path.is_absolute()
                else (self.workspace_root / s_path).resolve()
            )
        else:
            self.stage_dir = self.workspace_root / ".staging"

        self._explicit_global_config_dir = global_config_dir is not None
        self.global_config_dir = (
            Path(global_config_dir).resolve()
            if global_config_dir is not None
            else DEFAULT_GLOBAL_CONFIG_DIR.resolve()
        )
        self._readonly_filter_applied = False

        self._skill_to_domain: Dict[str, str] = {}
        self._script_to_domain: Dict[str, str] = {}
        for dom_id, dom_meta in DOMAIN_TAXONOMY.items():
            for sk in dom_meta["skills"]:
                self._skill_to_domain[sk] = dom_id
            for sc in dom_meta["scripts"]:
                self._script_to_domain[sc] = dom_id
        self._load_persistent_hash_cache()
        self._last_verify_cache: Optional[Tuple[float, Dict[str, Any]]] = None

    _HASH_CACHE: Dict[Tuple[str, int, int], str] = {}
    _META_CACHE: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    _SKILL_CACHE: Dict[Tuple[str, int, int], Tuple[str, int, Dict[str, Any]]] = {}
    _HYGIENE_CACHE: Optional[Tuple[float, str, int, Dict[str, Any]]] = None
    _MANIFEST_CACHE: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    _PERSISTENT_CACHE_LOADED: bool = False

    GCP_DATA_SKILLS: Tuple[str, ...] = GCP_DATA_SKILLS
    DEV_UTILITY_SKILLS: Tuple[str, ...] = DEV_UTILITY_SKILLS

    @classmethod
    def _get_persistent_cache_file(cls) -> Path:
        """Restituisce il percorso del file di cache persistente Fast-Stat in %TEMP%."""
        return get_persistent_cache_file_impl(cls)

    @classmethod
    def _get_persistent_meta_cache_file(cls) -> Path:
        """Restituisce il percorso del file di cache persistente metadati AST in %TEMP%."""
        return get_persistent_meta_cache_file_impl(cls)

    @classmethod
    def _load_persistent_hash_cache(cls) -> None:
        """Carica la cache SHA-256 e metadati AST persistente da %TEMP% per azzerare le letture su Google Drive."""
        return load_persistent_hash_cache_impl(cls)

    @classmethod
    def _save_persistent_hash_cache(cls) -> None:
        """Salva atomicamente la cache SHA-256 e metadati AST Fast-Stat in %TEMP%/nk_diagnostics."""
        return save_persistent_hash_cache_impl(cls)

    def resolve_genome_dir(
        self, root: Optional[Path] = None
    ) -> Tuple[Path, bool]:
        """Risolve la cartella genome preferendo nk_genome/ rispetto al fallback legacy genome/."""
        return resolve_genome_dir_impl(self, root)

    def resolve_tetralogy_files(
        self, root: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Risolve i documenti della Pentad supportando nk_genome/ e genome/ legacy."""
        return resolve_tetralogy_files_impl(self, root)

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Calcola l'hash crittografico SHA-256 del file specificato."""
        return compute_sha256_impl(file_path, hash_cache=NKRegistryIndexer._HASH_CACHE)

    def _load_staging_deleted_paths(self) -> Set[str]:
        """Carica i percorsi relativi eliminati in .staging/.deleted_files.json."""
        return load_staging_deleted_paths_impl(self)

    def _collect_priority_skills(self) -> Dict[str, Tuple[Path, os.stat_result]]:
        """Raccoglie la mappa skill_name -> (SKILL.md, stat) con una sola stat per skill."""
        return collect_priority_skills_impl(self)

    def _collect_priority_scripts(self) -> Dict[str, Tuple[Path, os.stat_result]]:
        """Raccoglie la mappa script_name -> (Path, stat) a costo zero tramite os.scandir."""
        return collect_priority_scripts_impl(self)

    @staticmethod
    def _parse_skill_metadata(content: str) -> Dict[str, Any]:
        """Estrae frontmatter YAML (inclusi domain_id e sector), card e link da SKILL.md."""
        return parse_skill_metadata_impl(content)

    @staticmethod
    def _extract_script_metadata(script_path: Path) -> Dict[str, Any]:
        """Estrae docstring, @domain_id, flag CLI add_argument, LOC e SHA-256 da uno script."""
        return extract_script_metadata_impl(script_path, hash_cache=NKRegistryIndexer._HASH_CACHE, meta_cache=NKRegistryIndexer._META_CACHE)

    def scan_skills(self) -> Dict[str, Dict[str, Any]]:
        """Scansiona tutte le skill supportando auto-registrazione Hot-Swap via YAML."""
        return scan_skills_impl(self)

    @staticmethod
    def _resolve_skill_native_subagent(sk_name: str, dom_id: str) -> str:
        """Risolve il sub-agente nativo associato a una skill vocazionale e al suo dominio."""
        return resolve_skill_native_subagent_impl(sk_name, dom_id)

    def _collect_priority_native_agents(
        self,
    ) -> Dict[str, Tuple[Path, os.stat_result]]:
        """Raccoglie la mappa agent_name -> (agent.md, stat) dando priorita a .staging/."""
        return collect_priority_native_agents_impl(self)

    @staticmethod
    def _parse_native_agent_metadata(content: str) -> Dict[str, Any]:
        """Estrae frontmatter YAML, permessi hardware e lista tools da un file agent.md."""
        return parse_native_agent_metadata_impl(content)

    def scan_native_agents(self) -> Dict[str, Dict[str, Any]]:
        """Scansiona i sub-agenti nativi in .agents/agents/*/agent.md dando priorita a .staging/."""
        return scan_native_agents_impl(self)

    def scan_scripts(self) -> Dict[str, Dict[str, Any]]:
        """Scansiona gli script in scripts/ e scripts/schemas/ dando priorita a .staging/."""
        return scan_scripts_impl(self)

    @staticmethod
    def _is_within_dir(target: Path, base: Path) -> bool:
        """Verifica se target risiede strettamente dentro la directory base risolta."""
        return is_within_dir_impl(target, base)

    def apply_global_filter(self) -> Dict[str, Any]:
        """Valuta in sola lettura il profilo globale senza modificare file fuori dal workspace."""
        return apply_global_filter_impl(self)

    def scan_global_hygiene_profile(
        self, workspace_skills_count: int
    ) -> Dict[str, Any]:
        """Scansiona il profilo globale ~/.gemini/config distinguendo skill attive e disabilitate."""
        return scan_global_hygiene_profile_impl(self, workspace_skills_count)

    def build_intent_dispatch_table(self) -> Dict[str, Dict[str, Any]]:
        """Costruisce la tabella O(1) di dispatch deduplicando la lista scripts."""
        return build_intent_dispatch_table_impl(self)

    def scan_docs_and_setup(self) -> Dict[str, Dict[str, Any]]:
        """Indicizza i file documentali e di setup presenti in nk_docs_and_setup/."""
        return scan_docs_and_setup_impl(self)

    def resolve_library_path(self, filename: str) -> Optional[str]:
        """Risolve in O(1) il percorso relativo di un file della libreria NK-Hub."""
        return resolve_library_path_impl(self, filename)

    def build_manifest(self) -> Dict[str, Any]:
        """Genera il dizionario completo di nk_registry_manifest.json con Hot-Swap dinamico."""
        return build_manifest_impl(self)

    def render_skill_index_markdown(self, manifest: Dict[str, Any]) -> str:
        """Genera il documento SKILL_INDEX.md conforme allo standard ASD-STE100."""
        return render_skill_index_markdown_impl(self, manifest)

    def _sync_nk_gate_plugin_mirrors(
        self, write_to_staging: bool, root_genome: Path
    ) -> List[str]:
        """Sincronizza i mirror di agent.md e anti_crash_rules.md in .agents/plugins/nk-gate/."""
        return sync_nk_gate_plugin_mirrors_impl(self, write_to_staging, root_genome)

    def sync(
        self, sync_staging: bool = False, allow_ratchet_down: bool = False
    ) -> Dict[str, Any]:
        """Genera nk_registry_manifest.json e SKILL_INDEX.md preservando la pulizia di .staging/."""
        return sync_impl(self, sync_staging, allow_ratchet_down)

    def load_manifest(self) -> Optional[Dict[str, Any]]:
        """Carica nk_registry_manifest.json supportando staging, nk_genome/ e genome/ legacy."""
        return load_manifest_impl(self)

    @staticmethod
    def _sha256_matches_eol_normalized(
        file_path: Path, live_sha: str, recorded_sha: str
    ) -> bool:
        """Verifica l'uguaglianza SHA-256 tollerando differenze di fine riga CRLF e LF."""
        return sha256_matches_eol_normalized_impl(file_path, live_sha, recorded_sha)

    def _audit_gt14_crit01_entries(
        self,
        agent_map: Dict[str, Tuple[Path, os.stat_result]],
        skill_map: Dict[str, Tuple[Path, os.stat_result]],
        manifest_agents: Optional[Dict[str, Any]] = None,
        manifest_skills: Optional[Dict[str, Any]] = None,
        unchanged_agents: Optional[Set[str]] = None,
        unchanged_skills: Optional[Set[str]] = None,
    ) -> List[str]:
        """Applica le guardie deterministiche GT-14, RULE-01 (2-Tier) e CRIT-01 su agenti e skill."""
        return audit_gt14_crit01_entries_impl(self, agent_map, skill_map, manifest_agents, manifest_skills, unchanged_agents, unchanged_skills)

    def verify_gt14_crit01_governance(self) -> Dict[str, Any]:
        """Verifica la conformita GT-14 e CRIT-01 direttamente sui file overlay su disco."""
        return verify_gt14_crit01_governance_impl(self)

    def verify(self) -> Dict[str, Any]:
        """Verifica gli hash SHA-256 su disco e le guardie GT-14, RULE-01 e Runtime 2.0 in meno di 30 ms."""
        return verify_impl(self)

    def lookup(self, query: str) -> Dict[str, Any]:
        """Esegue una ricerca O(1) nel manifesto per dominio, skill, native_agent, script o intento."""
        return lookup_impl(self, query)

    def generate_tas_certification_matrix(self) -> str:
        """Genera la tabella Markdown certificata dei script, skill e sub-agenti con domini e SHA-256."""
        return generate_tas_certification_matrix_impl(self)

    def build_release_zip(self, output_path: Path) -> Dict[str, Any]:
        """Crea un pacchetto ZIP pulito con prefisso radice NK_Hub/ escludendo artefatti effimeri."""
        return build_release_zip_impl(self, output_path)


def generate_tas_certification_matrix(workspace_root: Optional[Path] = None) -> str:
    """Funzione helper di modulo per generare la matrice di certificazione TAS."""
    return NKRegistryIndexer(workspace_root=workspace_root).generate_tas_certification_matrix()
