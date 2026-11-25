# -*- coding: utf-8 -*-
"""
Test di regressione Zero-Mock Wave 3 (NK-GEN-2.0.0-W3) per nk_registry_indexer.
Modulo: tests/test_nk_registry_indexer_w3.py.
Valida filtro 32 char, tassonomia DOM-04, shard cap <= 4700B, reidratazione, lookup e STE100.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import pytest

try:
    from conftest import WORKSPACE_ROOT, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, load_nk_script_module

indexer_mod = load_nk_script_module("nk_registry_indexer")
tr_mod = load_nk_script_module("nk_transcript_tools")

from _internal.nk_registry_indexer import lookup as lk_mod  # noqa: E402
from _internal.nk_registry_indexer import shards as shards_mod  # noqa: E402
from _internal.nk_registry_indexer import shards_rehydrate as rehyd_mod  # noqa: E402
from _internal.nk_registry_indexer import taxonomy as tax_mod  # noqa: E402

NKRegistryIndexer = indexer_mod.NKRegistryIndexer


def _make_w3_skill_md(
    name: str, dom_id: str, subagent: str, routing_kws: list[str], priority_kws: list[str]
) -> str:
    return (
        f"---\nname: {name}\ndescription: Skill {name}.\nversion: \"1.0.0-Generation\"\n"
        f"domain_id: \"{dom_id}\"\nnative_subagent: \"{subagent}\"\ndefault_mode: \"mode_d\"\n"
        f"read_only: true\ntools: [\"read_file\", \"send_message\"]\n"
        f"routing_keywords: {json.dumps(routing_kws)}\npriority_keywords: {json.dumps(priority_kws)}\n---\n# {name}\n"
    )


def _setup_w3_synthetic_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "w3_ws"
    for d in (
        ".agents/skills/NK-Security-Auditor",
        ".agents/skills/NK-Oracle-Evaluator",
        ".agents/skills/NK-Dynamic-Sandbox-StressTester",
        ".agents/skills/NK-Bug-Diagnostic-Engine",
        ".agents/skills/NK-Orchestrator",
        ".agents/agents/NK-RSI-Auditor",
        ".agents/agents/NK-Security-DAST-Auditor",
        "scripts",
    ):
        (ws / d).mkdir(parents=True, exist_ok=True)
    skills_spec = (
        ("NK-Security-Auditor", "DOM-04", "NK-Security-DAST-Auditor", ["sast", "audit di sicurezza", "audit forense", "valuta", "keyword decisamente sopra trentadue caratteri"], ["sast"]),
        ("NK-Oracle-Evaluator", "DOM-04", "NK-RSI-Auditor", ["oracolo", "convergenza rsi", "dag di kahn", "6 gate"], ["oracolo", "convergenza rsi"]),
        ("NK-Dynamic-Sandbox-StressTester", "DOM-04", "NK-Security-DAST-Auditor", ["dast", "sandbox", "stress test"], ["dast"]),
        ("NK-Bug-Diagnostic-Engine", "DOM-04", "NK-Security-DAST-Auditor", ["sbfl", "ochiai", "bug", "causa radice"], ["sbfl"]),
        ("NK-Orchestrator", "DOM-01", "Orchestrator-Direct", ["orchestratore", "2pc"], ["orchestratore"]),
    )
    for sk_name, dom_id, subag, rkws, pkws in skills_spec:
        (ws / ".agents" / "skills" / sk_name / "SKILL.md").write_text(
            _make_w3_skill_md(sk_name, dom_id, subag, rkws, pkws), encoding="utf-8"
        )
    for ag_name in ("NK-RSI-Auditor", "NK-Security-DAST-Auditor"):
        (ws / ".agents" / "agents" / ag_name / "agent.md").write_text(
            f"---\nname: {ag_name}\ndomain_id: DOM-04\nenable_write_tools: false\n"
            "tools:\n  - read_file\n  - send_message\n---\n# Auditor\n",
            encoding="utf-8",
        )
    for sc in tax_mod.DOMAIN_TAXONOMY["DOM-04"]["scripts"]:
        (ws / "scripts" / sc).write_text('"""Script DOM-04.\n@domain_id: DOM-04\n"""\n', encoding="utf-8")
    (ws / "scripts" / "vibe_sprint_router.py").write_text('"""Router.\n@domain_id: DOM-01\n"""\n', encoding="utf-8")
    return ws


def _assert_taxonomy_maps() -> None:
    dom01_kws = tax_mod.DOMAIN_TAXONOMY["DOM-01"]["keywords"]
    assert ("dag" not in dom01_kws, "kahn" not in dom01_kws, "aligner" not in dom01_kws) == (True, True, True)
    assert "forge" not in tax_mod.DOMAIN_TAXONOMY["DOM-02"]["keywords"]
    assert tax_mod.SKILL_PRIMARY_SCRIPTS == {
        "NK-Security-Auditor": ("ast_guard_validator.py",),
        "NK-Oracle-Evaluator": ("oracle_evaluator_l3.py", "rsi_convergence_engine.py", "nk_transcript_tools.py"),
        "NK-Dynamic-Sandbox-StressTester": ("dast_sandbox_runner.py", "oracle_evaluator_l3.py"),
        "NK-Bug-Diagnostic-Engine": ("sbfl_pytest_bridge.py",),
    }
    assert tax_mod.SCRIPT_SKILL_MAP == {
        "oracle_evaluator_l3.py": "NK-Oracle-Evaluator",
        "rsi_convergence_engine.py": "NK-Oracle-Evaluator",
        "nk_transcript_tools.py": "NK-Oracle-Evaluator",
        "dast_sandbox_runner.py": "NK-Dynamic-Sandbox-StressTester",
        "sbfl_pytest_bridge.py": "NK-Bug-Diagnostic-Engine",
    }


def _assert_hygiene_dispatch_entries(dispatch: Dict[str, Any]) -> None:
    for multi_kw, expected_sk in (
        ("convergenza rsi", "NK-Oracle-Evaluator"),
        ("audit di sicurezza", "NK-Security-Auditor"),
        ("audit forense", "NK-Security-Auditor"),
    ):
        assert dispatch[multi_kw]["primary_agent"] == expected_sk


@pytest.mark.fast
def test_w3_taxonomy_constants_and_hygiene_32_char_filter(tmp_path: Path) -> None:
    """1. Verifica rimozione dag/kahn da DOM-01, mappe SKILL_PRIMARY_SCRIPTS/SCRIPT_SKILL_MAP e filtro <= 32."""
    _assert_taxonomy_maps()
    ws = _setup_w3_synthetic_ws(tmp_path)
    idx = NKRegistryIndexer(workspace_root=ws, stage_dir=ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    dispatch = idx.build_intent_dispatch_table()
    _assert_hygiene_dispatch_entries(dispatch)
    assert "keyword decisamente sopra trentadue caratteri" not in dispatch

    real_idx = NKRegistryIndexer(
        workspace_root=WORKSPACE_ROOT, stage_dir=WORKSPACE_ROOT / ".staging", global_config_dir=tmp_path / "no_cfg"
    )
    real_dispatch = real_idx.build_intent_dispatch_table()
    assert real_dispatch["convergenza rsi"]["primary_agent"] == "NK-Oracle-Evaluator"


def _build_dense_dom04_inputs() -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    dense_skills: Dict[str, Any] = {}
    for i in range(4):
        dense_skills[f"NK-Skill-{i}"] = {
            "domain_id": "DOM-04",
            "native_subagent": "NK-RSI-Auditor" if i == 1 else "NK-Security-DAST-Auditor",
            "thinking_level": "HIGH",
            "tools": ["read_file", "send_message"],
            "sha256": f"{i}" * 64,
            "sector": "AUDIT_DAST_AND_RCA",
        }
    flags = [f"--flag-{j:02d}" for j in range(12)]
    dense_scripts = {
        sc: {"domain_id": "DOM-04", "sha256": "a" * 64, "cli_flags": flags, "classes": ["ClassOne", "ClassTwo", "ClassThree"]}
        for sc in tax_mod.DOMAIN_TAXONOMY["DOM-04"]["scripts"]
    }
    dense_agents = {
        ag: {"domain_id": "DOM-04", "tools": ["read_file", "send_message"], "sha256": "b" * 64}
        for ag in ("NK-RSI-Auditor", "NK-Security-DAST-Auditor")
    }
    dense_intents = {
        f"multi_word_keyword_dom04_{k:02d}": ["NK-Oracle-Evaluator" if k % 2 == 0 else "NK-Security-Auditor", "mode_d"]
        for k in range(55)
    }
    return dense_skills, dense_scripts, dense_agents, dense_intents


def _load_or_build_real_manifest(real_idx: NKRegistryIndexer) -> Dict[str, Any]:
    """Riusa il manifesto reidratato in sessione evitando la riscansione AST di 311 script."""
    cached = real_idx.load_manifest()
    return cached if cached is not None else real_idx.build_manifest()


def _assert_dense_dom04_shrink_and_real_shards(tmp_path: Path) -> str:
    dense_skills, dense_scripts, dense_agents, dense_intents = _build_dense_dom04_inputs()
    dom_meta = dict(tax_mod.DOMAIN_TAXONOMY["DOM-04"])
    mode_sizes: list[int] = []
    for md in (0, 1, 2, 3):
        pl = shards_mod._build_domain_shard_payload(
            "DOM-04", dom_meta, dense_skills, dense_scripts, dense_agents, dense_intents, md
        )
        mode_sizes.append(len(shards_mod._compact_json(pl).encode("utf-8")))
    assert mode_sizes[0] > shards_mod.SHARD_MAX_BYTES
    assert mode_sizes[0] >= mode_sizes[1] >= mode_sizes[2] >= mode_sizes[3]

    serialized = shards_mod._serialize_domain_shard_with_cap(
        "DOM-04", dom_meta, dense_skills, dense_scripts, dense_agents, dense_intents
    )
    assert len(serialized.encode("utf-8")) <= shards_mod.SHARD_MAX_BYTES
    assert "_routes" in json.loads(serialized)["intent_dispatch_table"]

    real_idx = NKRegistryIndexer(
        workspace_root=WORKSPACE_ROOT, stage_dir=WORKSPACE_ROOT / ".staging", global_config_dir=tmp_path / "no_cfg"
    )
    slim_m, shards_out = shards_mod.build_shards_and_slim_manifest(
        real_idx, _load_or_build_real_manifest(real_idx)
    )
    assert len(shards_mod._compact_json(slim_m).encode("utf-8")) <= shards_mod.MANIFEST_MAX_BYTES
    assert all(len(v.encode("utf-8")) <= shards_mod.SHARD_MAX_BYTES for v in shards_out.values())
    return serialized


def _assert_rehydrate_attaches_primary_scripts(tmp_path: Path, serialized_dom04: str) -> None:
    man_path = tmp_path / "rehyd" / "nk_registry_manifest.json"
    (tmp_path / "rehyd" / "shards").mkdir(parents=True)
    (tmp_path / "rehyd" / "shards" / "DOM-04.json").write_text(serialized_dom04, encoding="utf-8")
    (tmp_path / "rehyd" / "shards" / "DOM-01.json").write_text(
        json.dumps(
            {
                "domain": {"domain_id": "DOM-01", "name": "GOV_AND_ROUTING", "primary_skill": "NK-Orchestrator", "keywords": ["gov"]},
                "intent_dispatch_table": {
                    "_routes": [["NK-Orchestrator", "mode_a", ["commit"]]],
                    "str_ora": "mode_d",
                    "dict_bug": {"domain_id": "DOM-04", "domain_name": "AUDIT_DAST_AND_RCA", "primary_agent": "NK-Bug-Diagnostic-Engine", "recommended_mode": "mode_d"},
                },
            }
        ),
        encoding="utf-8",
    )
    rehyd = rehyd_mod.rehydrate_manifest_from_shards(
        man_path, {"shards": {"DOM-01": "shards/DOM-01.json", "DOM-04": "shards/DOM-04.json"}}
    )
    tbl = rehyd["intent_dispatch_table"]
    assert tbl["multi_word_keyword_dom04_00"]["scripts"] == list(tax_mod.SKILL_PRIMARY_SCRIPTS["NK-Oracle-Evaluator"])
    assert tbl["multi_word_keyword_dom04_01"]["scripts"] == list(tax_mod.SKILL_PRIMARY_SCRIPTS["NK-Security-Auditor"])
    assert tbl["dict_bug"]["scripts"] == list(tax_mod.SKILL_PRIMARY_SCRIPTS["NK-Bug-Diagnostic-Engine"])
    assert "scripts" not in tbl["commit"]


@pytest.mark.fast
def test_w3_shards_monotonic_shrink_dom04_cap_and_rehydrate_scripts(tmp_path: Path) -> None:
    """2. Verifica mode 3 con _pack_intents_grouped (DOM-04 <= 4700B) e reidratazione script per skill."""
    assert not hasattr(shards_mod, "_collapse_emergency_intents")
    serialized_dom04 = _assert_dense_dom04_shrink_and_real_shards(tmp_path)
    _assert_rehydrate_attaches_primary_scripts(tmp_path, serialized_dom04)


def _assert_lookup_2b_and_3(idx: Any) -> None:
    res_ag = idx.lookup("NK-RSI-Auditor")
    assert (res_ag["match_type"], res_ag["primary_skill"], res_ag["matched_skills"]) == (
        "native_agent", "NK-Oracle-Evaluator", ["NK-Oracle-Evaluator"]
    )
    res_dast_ag = idx.lookup("NK-Security-DAST-Auditor")
    assert res_dast_ag["primary_skill"] == "NK-Security-Auditor"
    assert {"NK-Bug-Diagnostic-Engine", "NK-Dynamic-Sandbox-StressTester"}.issubset(set(res_dast_ag["matched_skills"]))

    for sc_name, exp_sk, exp_ag in (
        ("rsi_convergence_engine.py", "NK-Oracle-Evaluator", "NK-RSI-Auditor"),
        ("oracle_evaluator_l3.py", "NK-Oracle-Evaluator", "NK-RSI-Auditor"),
        ("nk_transcript_tools.py", "NK-Oracle-Evaluator", "NK-RSI-Auditor"),
        ("dast_sandbox_runner.py", "NK-Dynamic-Sandbox-StressTester", "NK-Security-DAST-Auditor"),
        ("sbfl_pytest_bridge.py", "NK-Bug-Diagnostic-Engine", "NK-Security-DAST-Auditor"),
    ):
        res_sc = idx.lookup(sc_name)
        assert (res_sc["match_type"], res_sc["primary_skill"], res_sc["native_subagent"]) == ("script", exp_sk, exp_ag)


def _assert_lookup_4a_and_4c(idx: Any, tmp_path: Path) -> None:
    res_4a = idx.lookup("convergenza rsi")
    assert (res_4a["match_type"], res_4a["primary_skill"], res_4a["native_subagent"]) == (
        "intent", "NK-Oracle-Evaluator", "NK-RSI-Auditor"
    )
    assert res_4a["scripts"] == list(tax_mod.SKILL_PRIMARY_SCRIPTS["NK-Oracle-Evaluator"])
    for dom04_kw in ("bug", "valuta"):
        res_kw = idx.lookup(dom04_kw)
        assert (res_kw["found"], res_kw["domain_id"]) == (True, "DOM-04")

    fb_ws = tmp_path / "fallback_4c_ws"
    (fb_ws / "nk_genome").mkdir(parents=True)
    fb_manifest: Dict[str, Any] = {
        "version": "1.0.0-Generation",
        "domains": {
            "DOM-04": {
                "domain_id": "DOM-04",
                "name": "AUDIT_DAST_AND_RCA",
                "primary_skill": "NK-Security-Auditor",
                "skills": ["NK-Security-Auditor", "NK-Oracle-Evaluator"],
                "scripts": list(tax_mod.DOMAIN_TAXONOMY["DOM-04"]["scripts"]),
                "keywords": ["audit"],
            }
        },
        "skills_index": {"NK-Oracle-Evaluator": {"domain_id": "DOM-04", "domain_name": "AUDIT_DAST_AND_RCA", "native_subagent": "NK-RSI-Auditor"}},
        "scripts_index": {},
        "native_agents_index": {"NK-RSI-Auditor": {"domain_id": "DOM-04", "domain_name": "AUDIT_DAST_AND_RCA"}},
        "intent_dispatch_table": {
            "convergenza rsi": {
                "domain_id": "DOM-04",
                "domain_name": "AUDIT_DAST_AND_RCA",
                "primary_agent": "NK-Oracle-Evaluator",
                "recommended_mode": "mode_d",
            }
        },
    }
    (fb_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps(fb_manifest), encoding="utf-8")
    fb_idx = NKRegistryIndexer(workspace_root=fb_ws, stage_dir=fb_ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    res_4c = fb_idx.lookup("esegui verifica convergenza rsi ora")
    assert (res_4c["match_type"], res_4c["primary_skill"], res_4c["native_subagent"]) == (
        "intent", "NK-Oracle-Evaluator", "NK-RSI-Auditor"
    )
    assert res_4c["scripts"] == list(tax_mod.SKILL_PRIMARY_SCRIPTS["NK-Oracle-Evaluator"])


def _assert_lookup_mutation_boundaries(idx: NKRegistryIndexer) -> None:
    """Verifica fallback native_subagent, calcolo elapsed_ms e soglia keyword len>=5."""
    no_sub = {"NK-Oracle-Evaluator": {"domain_id": "DOM-04", "domain_name": "AUDIT_DAST_AND_RCA"}}
    assert lk_mod._resolve_skills_for_native_agent(idx, no_sub, "NK-RSI-Auditor", "DOM-04") == ["NK-Oracle-Evaluator"]
    dom_map = idx.build_manifest()["domains"]
    dom_res = lk_mod._lookup_domain(dom_map, "DOM-04", "DOM-04", time.perf_counter() - 0.05)
    assert dom_res is not None and 20.0 <= dom_res["elapsed_ms"] < 5000.0
    assert lk_mod._count_rule_keyword_hits(("audit",), "auditing", {"auditing"}) == 1
    assert lk_mod._count_rule_keyword_hits(("test",), "contest", {"contest"}) == 0


@pytest.mark.integration
def test_w3_lookup_steps_2b_3_4a_and_4c(tmp_path: Path) -> None:
    """3. Verifica lookup step 2b (NK-RSI-Auditor), step 3 (script->skill/subagent) e step 4a/4c."""
    ws = _setup_w3_synthetic_ws(tmp_path)
    idx = NKRegistryIndexer(workspace_root=ws, stage_dir=ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    assert idx.sync(sync_staging=True)["passed"] is True
    _assert_lookup_2b_and_3(idx)
    _assert_lookup_4a_and_4c(idx, tmp_path)
    _assert_lookup_mutation_boundaries(idx)


@pytest.mark.integration
def test_w3_manifest_builder_skill_index_header_and_ste100(tmp_path: Path) -> None:
    """4. Verifica intestazione corretta (5 domini, 7 shard) e conformita ASD-STE100 di SKILL_INDEX.md."""
    ws = _setup_w3_synthetic_ws(tmp_path)
    idx = NKRegistryIndexer(workspace_root=ws, stage_dir=ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    manifest = idx.build_manifest()
    md = idx.render_skill_index_markdown(manifest)
    expected_hdr = (
        f"Manifesto `{manifest['version']}` con `5` domini (`7` shard), "
        f"`{manifest['summary']['total_skills']}` skill e `{manifest['summary']['total_scripts']}` script."
    )
    assert expected_hdr in md
    assert "sharded su" not in md
    ste_res = tr_mod.verify_ste100_compliance(md)
    assert (ste_res["passed"], ste_res["violations_count"]) == (True, 0)
