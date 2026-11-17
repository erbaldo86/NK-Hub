# -*- coding: utf-8 -*-
"""
Contratti Pydantic v2 strict (compile-time) per il Catalogo Plug-and-Play SSOT (1.0.0-Generation).
Valida i frontmatter di SKILL.md, agent.md e gli artefatti compilati (manifest e shard).
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from _internal.nk_common.constants import VERSION

DomainIdLiteral = Literal["DOM-00", "DOM-01", "DOM-02", "DOM-03", "DOM-04", "DOM-05"]
ExecutionModeDefaultLiteral = Literal["mode_a", "mode_b", "mode_c", "mode_d"]


class SkillFrontmatterContract(BaseModel):
    """Contratto strict per il frontmatter YAML di .agents/skills/<Nome>/SKILL.md."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1, description="Identificatore univoco della skill")
    description: str = Field(min_length=1, description="Descrizione breve della skill")
    version: str = Field(default=VERSION, description="Versione del playbook")
    domain_id: DomainIdLiteral = Field(description="Dominio SSOT di appartenenza")
    native_subagent: str = Field(
        default="", description="Sub-agente nativo associato alla skill"
    )
    dashboard_node: Optional[int] = Field(
        default=None, ge=0, description="Indice nodo nella dashboard NK-Orchestrator"
    )
    default_mode: ExecutionModeDefaultLiteral = Field(
        default="mode_c", description="Modalita operativa predefinita"
    )
    read_only: bool = Field(
        default=False, description="True se la skill opera solo in lettura"
    )
    tools: List[str] = Field(
        default_factory=list, description="Tool dichiarati dalla skill"
    )
    routing_keywords: List[str] = Field(
        default_factory=list, description="Keyword di instradamento della skill"
    )
    priority_keywords: List[str] = Field(
        default_factory=list,
        description="Keyword ad alta priorita per disambiguazione",
    )
    cli_scripts: List[str] = Field(
        default_factory=list, description="Script CLI autorizzati dalla skill"
    )
    repo_map_budget_exempt: bool = Field(
        default=False, description="Esenzione dal budget standard repo_map"
    )
    role_identity: Optional[str] = Field(default=None, description="Identita di ruolo")
    sector: Optional[str] = Field(default=None, description="Settore applicativo")
    thinking_level: Optional[str] = Field(default=None, description="Livello reasoning")
    nk_tas_audit: Optional[str] = Field(default=None, description="Tag audit TAS")


class AgentFrontmatterContract(BaseModel):
    """Contratto strict per il frontmatter YAML di .agents/agents/<Nome>/agent.md."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1, description="Identificatore univoco del sub-agente")
    description: str = Field(min_length=1, description="Descrizione del sub-agente")
    version: str = Field(default=VERSION, description="Versione del profilo")
    subagent: bool = Field(default=True, description="Flag di profilo sub-agente")
    mainAgent: bool = Field(default=False, description="Flag agente principale")
    domain_id: DomainIdLiteral = Field(description="Dominio SSOT di appartenenza")
    enable_write_tools: bool = Field(
        default=False, description="Abilita strumenti di scrittura"
    )
    enable_subagent_tools: bool = Field(
        default=False, description="Abilita invocazione di sotto-agenti"
    )
    enable_mcp_tools: bool = Field(
        default=False, description="Abilita strumenti MCP esterni"
    )
    allowed_write_scopes: List[str] = Field(
        default_factory=list, description="Perimetri autorizzati per scritture"
    )
    tools: List[str] = Field(
        default_factory=list, description="Elenco tool consentiti al sub-agente"
    )
    nk_tas_audit: Optional[str] = Field(default=None, description="Tag audit TAS")
    patch_version: Optional[int] = Field(default=None, ge=0, description="Patch")
    nk_tas_date: Optional[str] = Field(default=None, description="Data audit TAS")


class RegistryManifestContract(BaseModel):
    """Contratto strict per nk_genome/nk_registry_manifest.json."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: str = Field(default=VERSION)
    milestone_anchor_id: str = Field(min_length=1)
    generated_at_utc: str = Field(min_length=1)
    total_domains: int = Field(ge=1)
    total_skills: int = Field(ge=1)
    total_native_agents: int = Field(ge=0)
    total_scripts: int = Field(ge=1)
    skills_index: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    native_agents_index: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    scripts_index: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    dashboard_nodes: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    domains: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)


class DomainShardContract(BaseModel):
    """Contratto strict per i singoli shard nk_genome/shards/DOM-00..06.json."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: str = Field(default=VERSION)
    domain_id: str = Field(min_length=1)
    milestone_anchor_id: str = Field(min_length=1)
    skills_index: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    native_agents_index: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    scripts_index: Dict[str, Dict[str, JsonValue]] = Field(default_factory=dict)
    intent_dispatch_table: Dict[str, List[str]] = Field(default_factory=dict)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)
