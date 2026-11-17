# -*- coding: utf-8 -*-
"""
Suite di valutazione Zero-Mock per le 11 skill di NK Hub Generation 1.0.0-Generation.
Modulo: tests/test_skill_evals.py.
Valida tutte le regole di skill_golden_eval_set.json in overlay .staging/.agents/skills/ > .agents/skills/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest
from conftest import WORKSPACE_ROOT, load_nk_script_module

tr_mod = load_nk_script_module("nk_transcript_tools")


def _load_golden_eval_config() -> Dict[str, Any]:
    """Carica il file JSON di golden eval privilegiando eventuale override in .staging/."""
    stg_cfg = WORKSPACE_ROOT / ".staging" / "tests" / "evals" / "skill_golden_eval_set.json"
    prod_cfg = WORKSPACE_ROOT / "tests" / "evals" / "skill_golden_eval_set.json"
    cfg_path = stg_cfg if stg_cfg.is_file() else prod_cfg
    assert cfg_path.is_file(), f"Config golden eval mancante: {cfg_path}"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _resolve_overlay_skill_file(skill_rel_path: str) -> Path:
    """Risolve la SKILL.md in overlay (.staging/ prima di produzione)."""
    stg_cand = WORKSPACE_ROOT / ".staging" / skill_rel_path
    if stg_cand.is_file():
        return stg_cand
    prod_cand = WORKSPACE_ROOT / skill_rel_path
    assert prod_cand.is_file(), f"Skill file mancante: {skill_rel_path}"
    return prod_cand


def _parse_frontmatter_tools_and_version(content: str) -> Dict[str, Any]:
    """Estrae version e lista tools dal frontmatter YAML senza dipendenze esterne."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {"version": "", "tools": []}
    fm_lines: List[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)

    version = ""
    tools: List[str] = []
    in_tools_list = False
    for line in fm_lines:
        stripped = line.strip()
        if in_tools_list:
            if stripped.startswith("- "):
                tools.append(stripped[2:].strip().strip("\"'"))
                continue
            if stripped and not stripped.startswith("#"):
                in_tools_list = False
        m_ver = re.match(r"^version\s*:\s*['\"]?([^'\"]+)['\"]?\s*$", stripped)
        if m_ver:
            version = m_ver.group(1).strip()
            continue
        if stripped.startswith("tools:"):
            rhs = stripped.split(":", 1)[1].strip()
            if rhs.startswith("[") and rhs.endswith("]"):
                inner = rhs[1:-1].strip()
                if inner:
                    tools.extend(
                        part.strip().strip("\"'")
                        for part in inner.split(",")
                        if part.strip()
                    )
            elif not rhs:
                in_tools_list = True
    return {"version": version, "tools": tools}


def _strip_frontmatter_and_code(content: str) -> str:
    """Rimuove frontmatter YAML, blocchi codice e backtick inline per check trattini spaziati."""
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


_EVAL_CFG = _load_golden_eval_config()
_SKILL_SPECS: List[Dict[str, Any]] = list(_EVAL_CFG.get("skills", []))


@pytest.mark.fast
@pytest.mark.parametrize("skill_spec", _SKILL_SPECS, ids=[s["name"] for s in _SKILL_SPECS])
def test_skill_golden_eval_contract_and_ste100(skill_spec: Dict[str, Any]) -> None:
    """Verifica contratto, tool RO/RW, substring obbligatorie, STE100 e assenza trattini."""
    global_inv = _EVAL_CFG["global_invariants"]
    skill_file = _resolve_overlay_skill_file(skill_spec["skill_path"])
    content = skill_file.read_text(encoding="utf-8")
    meta = _parse_frontmatter_tools_and_version(content)

    req_ver = str(global_inv["required_version_tag"])
    assert meta["version"] == req_ver, (
        f"{skill_spec['name']}: version={meta['version']!r}, atteso {req_ver!r}"
    )
    assert req_ver in content

    req_section = str(global_inv["required_section"])
    assert req_section in content, f"{skill_spec['name']}: sezione {req_section} assente"

    tools_set = set(meta["tools"])
    for req_tool in skill_spec.get("required_tools", []):
        assert req_tool in tools_set, f"{skill_spec['name']}: tool richiesto assente {req_tool}"
    for forb_tool in skill_spec.get("forbidden_tools", []):
        assert forb_tool not in tools_set, (
            f"{skill_spec['name']}: tool vietato presente {forb_tool}"
        )

    for substr in skill_spec.get("required_substrings", []):
        assert substr in content, (
            f"{skill_spec['name']}: substring obbligatoria assente {substr!r}"
        )

    if global_inv.get("forbid_spaced_dashes", True):
        prose = _strip_frontmatter_and_code(content)
        for dash in (" \u2014 ", " \u2013 "):
            assert dash not in prose, f"{skill_spec['name']}: rilevato trattino spaziato {dash!r}"

    max_words = int(global_inv.get("max_sentence_words", 20))
    ste_res = tr_mod.verify_ste100_compliance(content, max_sentence_words=max_words)
    assert ste_res["passed"] is True, (
        f"{skill_spec['name']}: violazioni STE100 {ste_res.get('violations')}"
    )


@pytest.mark.fast
def test_skill_golden_eval_covers_all_eleven_skills() -> None:
    """Verifica che il set golden eval copra tutte le undici skill e nodi Dashboard."""
    assert len(_SKILL_SPECS) == 11
    names = {s["name"] for s in _SKILL_SPECS}
    assert "NK-Orchestrator" in names and "NK-Oracle-Evaluator" in names


@pytest.mark.fast
def test_all_domain_shards_valid_modes_and_budget() -> None:
    """Verifica che tutti gli shard DOM-00..DOM-06 rispettino il budget e i mode canonici."""
    stg_shards = WORKSPACE_ROOT / ".staging" / "nk_genome" / "shards"
    prod_shards = WORKSPACE_ROOT / "nk_genome" / "shards"
    shards_dir = stg_shards if stg_shards.is_dir() else prod_shards
    valid_modes = {"mode_a", "mode_b", "mode_c", "mode_d"}
    for shard_file in sorted(shards_dir.glob("DOM-*.json")):
        assert shard_file.stat().st_size <= 4700, f"{shard_file.name} supera 4700B"
        data = json.loads(shard_file.read_text(encoding="utf-8"))
        table = data.get("intent_dispatch_table", {})
        if isinstance(table, dict) and "_routes" in table:
            for route in table["_routes"]:
                assert route[1] in valid_modes, f"{shard_file.name} mode invalido: {route}"
        elif isinstance(table, dict):
            for kw, val in table.items():
                mode_val = val[1] if isinstance(val, list) else val
                assert mode_val in valid_modes, f"{shard_file.name} {kw} mode invalido: {val}"
