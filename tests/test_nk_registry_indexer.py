# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per nk_registry_indexer.py di Nexus Keystone v6.4.0-Carbon.
Modulo: tests/test_nk_registry_indexer.py.
Valida sync, verify, CRIT-01 MCP fantasma, lookup O(1), Hot-Swap, shard e SSOT.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import WORKSPACE_ROOT, is_cov_instrumented, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, is_cov_instrumented, load_nk_script_module

indexer_mod = load_nk_script_module("nk_registry_indexer")
router_mod = load_nk_script_module("vibe_sprint_router")
preflight_mod = load_nk_script_module("preflight_health_check")
tr_mod = load_nk_script_module("nk_transcript_tools")

NKRegistryIndexer = indexer_mod.NKRegistryIndexer
VibeSprintRouter = router_mod.VibeSprintRouter
PreflightHealthChecker = preflight_mod.PreflightHealthChecker

pytestmark = pytest.mark.fast


def test_nk_registry_indexer_sync_generates_manifest_and_skill_index(
    tmp_path: Path,
) -> None:
    """Verifica che --sync generi nk_registry_manifest.json e SKILL_INDEX.md."""
    stage_dir = tmp_path / ".staging"
    rc = indexer_mod.main(["--sync", "--stage-dir", str(stage_dir)])
    assert rc == 0

    manifest_path = stage_dir / "nk_genome" / "nk_registry_manifest.json"
    skill_index_path = stage_dir / "nk_genome" / "SKILL_INDEX.md"
    assert manifest_path.exists()
    assert skill_index_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("version", "domains", "skills_index", "scripts_index", "intent_dispatch_table", "global_hygiene_profile"):
        assert key in manifest

    assert set(manifest["domains"].keys()) == {"DOM-01", "DOM-02", "DOM-03", "DOM-04", "DOM-05"}
    assert len(manifest["skills_index"]) == 11
    assert len(manifest["scripts_index"]) >= 32
    assert "nk_registry_indexer.py" in manifest["scripts_index"]
    assert "schemas/dual_ledgers.py" in manifest["scripts_index"]
    assert "schemas/nk_ipc_contracts.py" in manifest["scripts_index"]
    assert manifest["scripts_index"]["schemas/dual_ledgers.py"]["domain_id"] == "DOM-01"
    assert manifest["scripts_index"]["schemas/nk_ipc_contracts.py"]["domain_id"] == "DOM-01"

    md_text = skill_index_path.read_text(encoding="utf-8")
    assert "DOM-01" in md_text and "DOM-05" in md_text
    assert "NK-Python-Async-Builder" in md_text


def test_nk_registry_sync_without_staging_preserves_prod(tmp_path: Path) -> None:
    """Verifica G3-02: sync senza --sync-staging non tocca .staging di produzione."""
    prod_stg_manifest = WORKSPACE_ROOT / ".staging" / "nk_genome" / "nk_registry_manifest.json"
    existed_before = prod_stg_manifest.exists()
    mtime_before = prod_stg_manifest.stat().st_mtime_ns if existed_before else None

    g3_ws = tmp_path / "g3_no_stg_ws"
    (g3_ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True, exist_ok=True)
    (g3_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndescription: Mini.\nversion: '6.0.0-Carbon'\ndomain_id: 'DOM-01'\n---\n# Hub\n",
        encoding="utf-8",
    )
    (g3_ws / "scripts").mkdir(parents=True, exist_ok=True)
    (g3_ws / "scripts" / "mini.py").write_text('"""Mini.\n@domain_id: DOM-01\n"""\n', encoding="utf-8")

    no_stg_indexer = NKRegistryIndexer(workspace_root=g3_ws)
    no_stg_indexer.resolve_genome_dir = lambda root=None: (tmp_path / "isolated_prod_genome", False)  # type: ignore[method-assign]
    res_no_stg = no_stg_indexer.sync(sync_staging=False)
    assert res_no_stg["passed"] is True
    assert res_no_stg["sync_staging"] is False
    assert not (g3_ws / ".staging" / "nk_genome" / "nk_registry_manifest.json").exists()
    if not existed_before:
        assert not prod_stg_manifest.exists()
    else:
        assert prod_stg_manifest.stat().st_mtime_ns == mtime_before


def test_nk_registry_indexer_verify_detects_clean_and_drift(tmp_path: Path) -> None:
    """Verifica che --verify certifichi integrita SHA-256 e rilevi drift."""
    with tempfile.TemporaryDirectory() as td_sync:
        sb_ws = Path(td_sync)
        (sb_ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True, exist_ok=True)
        (sb_ws / "scripts").mkdir(parents=True, exist_ok=True)
        (sb_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
            "---\nname: NK-Orchestrator\ndescription: Sovrano L3.\nversion: '6.0.0-Carbon'\ndomain_id: 'DOM-01'\n---\n# Hub\n",
            encoding="utf-8",
        )
        (sb_ws / "scripts" / "nk_registry_indexer.py").write_text(
            '"""Modulo indicizzatore.\n@domain_id: DOM-01\n"""\nimport argparse\n',
            encoding="utf-8",
        )
        indexer = NKRegistryIndexer(workspace_root=sb_ws, stage_dir=sb_ws / ".staging_verify")
        indexer.sync(sync_staging=True)
        verify_res = indexer.verify()
        assert verify_res["passed"] is True and verify_res["status"] == "VALID"
        assert "unindexed_files" in verify_res and verify_res["elapsed_ms"] < 350.0

    mini_ws = tmp_path / "mini_ws"
    (mini_ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True, exist_ok=True)
    (mini_ws / "scripts").mkdir(parents=True, exist_ok=True)
    (mini_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndescription: Sovrano L3.\nversion: '6.0.0-Carbon'\n---\n# Hub\n",
        encoding="utf-8",
    )
    script_py = mini_ws / "scripts" / "nk_registry_indexer.py"
    script_py.write_text('"""Modulo indicizzatore."""\nimport argparse\n', encoding="utf-8")

    tmp_indexer = NKRegistryIndexer(workspace_root=mini_ws, stage_dir=mini_ws / ".staging")
    tmp_indexer.sync()
    assert tmp_indexer.verify()["passed"] is True

    script_py.write_text('"""Modulo indicizzatore modificato."""\nimport sys\n', encoding="utf-8")
    drift_res = tmp_indexer.verify()
    assert drift_res["passed"] is False and drift_res["status"] == "DRIFT_DETECTED"
    assert any("nk_registry_indexer.py" in issue for issue in drift_res["issues"])


def test_registry_grounding_and_legacy_genome_fallback(tmp_path: Path) -> None:
    """Verifica grounding report e dual-resolver Tetralogia su cartella legacy genome/."""
    bad_rep = tmp_path / "bad_report.md"
    bad_rep.write_text("Esegui scripts/atomic_2pc_commit.py ora.\n", encoding="utf-8")
    bad_res = tr_mod.verify_report_grounding(bad_rep)
    assert bad_res["passed"] is False and bad_res["exit_code"] == 1

    good_rep = tmp_path / "good_report.md"
    good_rep.write_text("Esegui scripts/win32_2pc_engine.py ora.\n", encoding="utf-8")
    good_res = tr_mod.verify_report_grounding(good_rep)
    assert good_res["passed"] is True and good_res["exit_code"] == 0

    legacy_ws = tmp_path / "legacy_ext_ws"
    (legacy_ws / "genome").mkdir(parents=True, exist_ok=True)
    (legacy_ws / "genome" / "concept_map.md").write_text("# Concept\n", encoding="utf-8")
    leg_indexer = NKRegistryIndexer(workspace_root=legacy_ws, stage_dir=legacy_ws / ".staging")
    tetra = leg_indexer.resolve_tetralogy_files()
    assert tetra["is_legacy_genome"] is True
    assert tetra["warning"] is not None and tetra["files"]["concept_map.md"] is not None


def test_nk_registry_indexer_lookup_o1_latency_under_50ms(tmp_path: Path) -> None:
    """Verifica che --lookup risolva dominio, skill, script e intento (<50ms, <150ms con cov)."""
    indexer = NKRegistryIndexer(
        workspace_root=WORKSPACE_ROOT, stage_dir=tmp_path / ".staging_lookup"
    )
    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    max_ms = (250.0 if is_cov_instrumented() else 150.0) if is_ci else (150.0 if is_cov_instrumented() else 50.0)

    t0 = time.perf_counter()
    res_dom = indexer.lookup("DOM-04")
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert res_dom["found"] is True and res_dom["domain_id"] == "DOM-04"
    assert res_dom["domain_name"] == "AUDIT_DAST_AND_RCA"
    assert dt_ms < max_ms and res_dom["elapsed_ms"] < max_ms

    res_skill = indexer.lookup("NK-Python-Async-Builder")
    assert res_skill["found"] is True and res_skill["match_type"] == "skill"
    assert res_skill["domain_id"] == "DOM-03" and res_skill["elapsed_ms"] < max_ms

    res_script = indexer.lookup("vibe_sprint_router.py")
    assert res_script["found"] is True and res_script["match_type"] == "script"
    assert res_script["domain_id"] == "DOM-01" and "--discovery-check" in res_script["cli_flags"]
    assert res_script["elapsed_ms"] < max_ms

    res_intent = indexer.lookup("Esegui recall memoria episodica")
    assert res_intent["found"] is True and res_intent["domain_id"] == "DOM-05"
    assert res_intent["elapsed_ms"] < max_ms


def test_ssot_integration_vibe_sprint_router_and_preflight_health_check(
    tmp_path: Path,
) -> None:
    """Verifica il disaccoppiamento SSOT in vibe_sprint_router.py e preflight_health_check.py."""
    router = VibeSprintRouter(workspace_root=WORKSPACE_ROOT)
    assert router.resolve_domain_from_manifest("Esegui audit SAST e diagnosi SBFL Ochiai")["domain_id"] == "DOM-04"

    intent_d = router.classify_prompt_intent("Esegui discovery e benchmark architettura")
    assert intent_d["recommended_mode"] == "mode_d" and intent_d["primary_agent"] == "NK-Ideator"
    assert intent_d["domain_id"] == "DOM-02"

    intent_c = router.classify_prompt_intent("Implementa modulo async con pydantic")
    assert intent_c["recommended_mode"] == "mode_c" and intent_c["primary_agent"] == "NK-Python-Async-Builder"
    assert intent_c["domain_id"] == "DOM-03"

    custom_ws = tmp_path / "custom_ssot_ws"
    for folder in ("nk_genome", "nk_tracking/anchor", ".staging"):
        (custom_ws / folder).mkdir(parents=True, exist_ok=True)
    custom_manifest = {
        "version": "6.0.0-Carbon",
        "summary": {"total_skills": 18, "total_domains": 5, "total_scripts": 32},
        "skills_index": {f"NK-Skill-{i}": {"domain_id": "DOM-01"} for i in range(18)},
    }
    (custom_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps(custom_manifest), encoding="utf-8")
    (custom_ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"_version": "6.0.0-Carbon", "metrics": {"skills_audited": 18, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )

    checker = PreflightHealthChecker(workspace_root=custom_ws)
    alignment = checker._check_baseline_alignment()
    assert alignment["passed"] is True and alignment["expected_skills"] == 18 and alignment["skills_audited"] == 18


def test_nk_registry_indexer_hotswap_zero_touch_registration(tmp_path: Path) -> None:
    """Verifica che una nuova skill con domain_id: DOM-03 venga auto-registrata da --sync."""
    hs_ws = tmp_path / "hotswap_ws"
    custom_skill_dir = hs_ws / ".agents" / "skills" / "NK-Custom-HotSwap"
    scripts_dir = hs_ws / "scripts" / "schemas"
    custom_skill_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    (custom_skill_dir / "SKILL.md").write_text(
        '---\nname: NK-Custom-HotSwap\ndescription: Modulo Hot-Swap.\nversion: "6.0.0-Carbon"\ndomain_id: "DOM-03"\nsector: "BUILD_AND_HEAL"\nthinking_level: "HIGH"\n---\n# HS\n',
        encoding="utf-8",
    )
    (hs_ws / "scripts" / "custom_auditor_probe.py").write_text('"""Sonda.\n@domain_id: DOM-04\n"""\nimport sys\n', encoding="utf-8")
    (scripts_dir / "nk_ipc_contracts.py").write_text('"""Contratti."""\nfrom pydantic import BaseModel\n', encoding="utf-8")

    hs_indexer = NKRegistryIndexer(
        workspace_root=hs_ws, stage_dir=hs_ws / ".staging", global_config_dir=tmp_path / "empty_global_cfg"
    )
    assert hs_indexer.sync()["passed"] is True
    manifest = hs_indexer.load_manifest()
    assert manifest is not None
    assert manifest["skills_index"]["NK-Custom-HotSwap"]["domain_id"] == "DOM-03"
    assert manifest["skills_index"]["NK-Custom-HotSwap"]["sector"] == "BUILD_AND_HEAL"
    assert "NK-Custom-HotSwap" in manifest["domains"]["DOM-03"]["skills"]
    assert manifest["scripts_index"]["custom_auditor_probe.py"]["domain_id"] == "DOM-04"
    assert manifest["scripts_index"]["schemas/nk_ipc_contracts.py"]["domain_id"] == "DOM-01"


def test_global_skill_filter_and_hygiene_isolation(tmp_path: Path) -> None:
    """Verifica consolidamento plugin e disattivazione skill globali in config.json."""
    temp_cfg_dir = tmp_path / "gemini_config"
    skills_dir = temp_cfg_dir / "skills"
    plugins_dir = temp_cfg_dir / "plugins"
    skills_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    (skills_dir / "bigquery-data-transfer-service").mkdir(parents=True)
    (skills_dir / "bigquery-data-transfer-service" / "SKILL.md").write_text("# BQ Transfer\n", encoding="utf-8")
    (skills_dir / ".datacloud_skills_manifest").write_text("{}", encoding="utf-8")
    (skills_dir / "managing-python-dependencies").mkdir(parents=True)
    (skills_dir / "managing-python-dependencies" / "SKILL.md").write_text("# Py Deps\n", encoding="utf-8")
    (plugins_dir / "science" / "skills" / "alphafold-database").mkdir(parents=True)
    (plugins_dir / "science" / "skills" / "alphafold-database" / "SKILL.md").write_text("# AlphaFold\n", encoding="utf-8")
    (plugins_dir / "android-cli-plugin" / "skills").mkdir(parents=True)
    (plugins_dir / "android-cli-plugin" / "skills" / "SKILL.md").write_text("# Android\n", encoding="utf-8")
    (temp_cfg_dir / "config.json").write_text(
        json.dumps({"plugins": {"android-cli-plugin": {"enabled": True}, "science": {"enabled": True}, "firebase": {"enabled": True}}, "sidecars": {"science/viewer": {"schemaVersion": 1}}, "userSettings": {"useAiCredits": False}}),
        encoding="utf-8",
    )

    idx = NKRegistryIndexer(workspace_root=WORKSPACE_ROOT, stage_dir=tmp_path / ".staging", global_config_dir=temp_cfg_dir)
    before = idx.scan_global_hygiene_profile(11)
    assert before["installed_external_skills_count"] == 4 and before["context_pollution_detected"] is True
    assert idx.apply_global_filter()["applied"] is True
    assert (plugins_dir / "gcp-data-cloud-plugin" / "skills" / "bigquery-data-transfer-service" / "SKILL.md").exists()
    assert (plugins_dir / "dev-utilities-plugin" / "skills" / "managing-python-dependencies" / "SKILL.md").exists()

    after = idx.scan_global_hygiene_profile(11)
    assert after["active_external_skills_count"] == 0 and after["disabled_external_skills_count"] == 4
    assert after["total_flat_skills"] == 11 and after["context_pollution_detected"] is False


def test_registry_crit01_blocks_phantom_mcp_tools(tmp_path: Path) -> None:
    """Verifica CRIT-01: blocco tool MCP fantasma (call_mcp_tool) nei file agent.md."""
    phantom_ws = tmp_path / "phantom_mcp_ws"
    (phantom_ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True)
    (phantom_ws / ".agents" / "agents" / "NK-Builder-Agent").mkdir(parents=True)
    (phantom_ws / "scripts").mkdir(parents=True)
    (phantom_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\nversion: '6.0.0-Carbon'\ndomain_id: DOM-01\n---\n# Hub\n", encoding="utf-8"
    )
    (phantom_ws / ".agents" / "agents" / "NK-Builder-Agent" / "agent.md").write_text(
        "---\nname: NK-Builder-Agent\ndomain_id: DOM-03\nenable_write_tools: true\nenable_subagent_tools: false\ntools:\n  - read_file\n  - call_mcp_tool\n  - send_message\n---\n# Builder\n",
        encoding="utf-8",
    )
    (phantom_ws / "scripts" / "nk_registry_indexer.py").write_text('"""Indexer.\n@domain_id: DOM-01\n"""\nimport argparse\n', encoding="utf-8")

    phantom_idx = NKRegistryIndexer(workspace_root=phantom_ws, stage_dir=phantom_ws / ".staging", global_config_dir=tmp_path / "no_global_cfg")
    phantom_idx.sync()
    phantom_ver = phantom_idx.verify()
    assert phantom_ver["passed"] is False and phantom_ver["status"] == "DRIFT_DETECTED"
    assert any("call_mcp_tool" in issue for issue in phantom_ver["issues"])


def test_nk_registry_ratchet_down_and_gt14_governance(tmp_path: Path) -> None:
    """Verifica ERR_REGISTRY_RATCHET_DOWN su riduzione skill e conformita GT-14."""
    rat_ws = tmp_path / "ratchet_ws"
    for sk in ("NK-Orchestrator", "NK-Ideator", "NK-System-Architect", "NK-Oracle-Evaluator"):
        (rat_ws / ".agents" / "skills" / sk).mkdir(parents=True, exist_ok=True)
        (rat_ws / ".agents" / "skills" / sk / "SKILL.md").write_text(f"---\nname: {sk}\nversion: '6.0.0-Carbon'\n---\n# {sk}\n", encoding="utf-8")
    (rat_ws / ".agents" / "agents" / "NK-Arch-Specifier").mkdir(parents=True, exist_ok=True)
    agent_md = rat_ws / ".agents" / "agents" / "NK-Arch-Specifier" / "agent.md"
    agent_md.write_text(
        "---\nname: NK-Arch-Specifier\ndomain_id: DOM-02\nenable_write_tools: false\nenable_subagent_tools: false\nenable_mcp_tools: false\ntools:\n  - read_file\n  - send_message\n---\n# Specifier\n",
        encoding="utf-8",
    )
    (rat_ws / "scripts").mkdir(parents=True, exist_ok=True)
    (rat_ws / "scripts" / "nk_registry_indexer.py").write_text('"""Indexer.\n@domain_id: DOM-01\n"""\n', encoding="utf-8")

    rat_idx = NKRegistryIndexer(workspace_root=rat_ws, stage_dir=rat_ws / ".staging", global_config_dir=tmp_path / "no_global_cfg")
    assert rat_idx.sync()["passed"] is True
    manifest_file = rat_ws / "nk_genome" / "nk_registry_manifest.json"
    before_bytes = manifest_file.read_bytes()

    (rat_ws / ".agents" / "skills" / "NK-System-Architect" / "SKILL.md").unlink()
    blocked_sync = rat_idx.sync(allow_ratchet_down=False)
    assert blocked_sync["passed"] is False and blocked_sync["status"] == "RATCHET_BLOCKED"
    assert blocked_sync["error_code"] == "ERR_REGISTRY_RATCHET_DOWN" and manifest_file.read_bytes() == before_bytes
    assert rat_idx.sync(allow_ratchet_down=True)["passed"] is True
    assert rat_idx.verify_gt14_crit01_governance()["passed"] is True

    agent_md.write_text(
        "---\nname: NK-Arch-Specifier\ndomain_id: DOM-02\nenable_write_tools: true\nenable_subagent_tools: false\nenable_mcp_tools: false\ntools:\n  - read_file\n  - search_web\n  - send_message\n---\n# Bad\n",
        encoding="utf-8",
    )
    bad_gt14 = rat_idx.verify_gt14_crit01_governance()
    assert bad_gt14["passed"] is False and len(bad_gt14["issues"]) >= 2


def test_registry_real_ecosystem_6_agents_and_gt14(tmp_path: Path) -> None:
    """Verifica che l'ecosistema reale esponga i 6 leaf agent GT-14 e superi la verifica governance."""
    real_idx = NKRegistryIndexer(workspace_root=WORKSPACE_ROOT, stage_dir=WORKSPACE_ROOT / ".staging", global_config_dir=tmp_path / "no_global_cfg_2")
    real_agents = real_idx._collect_priority_native_agents()
    assert len(real_agents) == 6 and "NK-Arch-Specifier" in real_agents
    skills = real_idx._collect_priority_skills()
    assert "NK-Oracle-Evaluator" in skills
    assert "NK-Plan-Aligner" not in skills and "NK-State-Router" not in skills
    assert real_idx.verify_gt14_crit01_governance()["passed"] is True


def test_hygiene_filter_quarantines_and_preserves_corrupt_config_json(tmp_path: Path) -> None:
    """Verifica [P1-4b]: config.json corrotto viene preservato/quarantinato senza wipe."""
    corrupt_cfg_dir = tmp_path / "corrupt_gemini_cfg"
    (corrupt_cfg_dir / "skills").mkdir(parents=True, exist_ok=True)
    corrupt_raw = '{"userSettings": {"customKey": "preserve_me"}, "broken": '
    cfg_file = corrupt_cfg_dir / "config.json"
    cfg_file.write_text(corrupt_raw, encoding="utf-8")

    idx = NKRegistryIndexer(workspace_root=WORKSPACE_ROOT, stage_dir=tmp_path / ".staging_corrupt", global_config_dir=corrupt_cfg_dir)
    res = idx.apply_global_filter()
    assert res["applied"] is True and res.get("config_corrupt") is True and res.get("config_preserved") is True
    assert cfg_file.read_text(encoding="utf-8") == corrupt_raw
    quarantine_path = Path(str(res.get("quarantined_config_path", "")))
    assert quarantine_path.is_file() and quarantine_path.read_text(encoding="utf-8") == corrupt_raw


def test_shards_rehydration_and_manifest_builder_resolution_branches(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Chiude i branch di shards.py, manifest_builder.py e cache_and_skills.py."""
    from _internal.nk_registry_indexer import shards as shards_mod

    slim_path = tmp_path / "nk_registry_manifest.json"
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir(parents=True)
    (shards_dir / "corrupt.json").write_text("{bad", encoding="utf-8")
    (shards_dir / "nondict.json").write_text("[1, 2]", encoding="utf-8")
    (shards_dir / "dom00.json").write_text(json.dumps({"global_hygiene_profile": {"ok": True}, "docs_and_setup_index": {"doc.md": {"relative_path": "nk_docs_and_setup/doc.md"}}, "milestone_anchor_id": "M-1"}), encoding="utf-8")
    (shards_dir / "dom06.json").write_text(json.dumps({"release": "6.4.0"}), encoding="utf-8")
    (shards_dir / "dom09.json").write_text(
        json.dumps({"domain": {"domain_id": "DOM-09", "name": "D9", "primary_skill": "SkX", "keywords": ["k0"]}, "skills_index": {"SkX": {"sector": "SEC"}}, "scripts_index": {"sc.py": {"classes": []}}, "native_agents_index": {"AgX": {"enable_mcp_tools": True}}, "intent_dispatch_table": {"k_str": "mode_d", "k_list": ["Ag", "mode_b"], "k_dict": {"recommended_mode": "mode_c", "primary_agent": "A"}}}),
        encoding="utf-8",
    )
    slim_payload = {
        "domains": {"DOM-99": {"name": "FallbackDom"}},
        "shards": {"DOM-00": "shards/dom00.json", "DOM-06": "shards/dom06.json", "DOM-09": "shards/dom09.json", "DOM-MISS": "shards/missing.json", "DOM-BAD": "shards/corrupt.json", "DOM-LIST": "shards/nondict.json"},
    }
    merged = shards_mod.rehydrate_manifest_from_shards(slim_path, slim_payload)
    assert merged["milestone_anchor_id"] == "M-1" and merged["release_meta"] == {"release": "6.4.0"}
    assert "SkX" in merged["skills_index"] and "sc.py" in merged["scripts_index"] and "AgX" in merged["native_agents_index"]
    assert merged["intent_dispatch_table"]["k_str"]["recommended_mode"] == "mode_d"
    assert merged["intent_dispatch_table"]["k_list"]["recommended_mode"] == "mode_b"
    assert shards_mod.rehydrate_manifest_from_shards(slim_path, {"domains": {}}) == {"domains": {}}

    docs_ws = tmp_path / "docs_ws"
    (docs_ws / "nk_docs_and_setup").mkdir(parents=True)
    (docs_ws / "nk_docs_and_setup" / "bundle.zip").write_bytes(b"PK")
    (docs_ws / "nk_docs_and_setup" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (docs_ws / "nk_genome").mkdir(parents=True)
    (docs_ws / "nk_genome" / "extra.md").write_text("# Extra\n", encoding="utf-8")
    monkeypatch.setenv("TEMP", str(tmp_path / "reg_tmp"))
    docs_idx = NKRegistryIndexer(workspace_root=docs_ws, stage_dir=docs_ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    assert docs_idx.resolve_library_path("") is None
    assert docs_idx.resolve_library_path("guide.md") == "nk_docs_and_setup/guide.md"
    assert docs_idx.resolve_library_path("extra.md") == "nk_genome/extra.md"
    assert docs_idx.resolve_library_path("nonexistent.md") is None
    assert "bundle.zip" not in docs_idx.scan_docs_and_setup()
    (docs_ws / "nk_genome" / "nk_registry_manifest.json").write_text(
        json.dumps({"docs_and_setup_index": {"guide.md": {"relative_path": "nk_docs_and_setup/guide.md"}}, "scripts_index": {"sub/tool.py": {"path": "scripts/sub/tool.py"}, "top_tool.py": {"path": "scripts/top_tool.py"}}}),
        encoding="utf-8",
    )
    assert docs_idx.resolve_library_path("guide.md") == "nk_docs_and_setup/guide.md"
    assert docs_idx.resolve_library_path("sub/tool.py") == "scripts/sub/tool.py"
    assert docs_idx.resolve_library_path("nested/top_tool.py") == "scripts/top_tool.py"


def test_gt14_allows_local_ro_search_tools_and_blocks_forbidden(tmp_path: Path) -> None:
    """Verifica tool ricerca locale RO su GT-14, blocco CRIT-01 e sync rules/taxonomy."""
    ro_ws = tmp_path / "ro_search_ws"
    (ro_ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True)
    (ro_ws / ".agents" / "agents" / "NK-RSI-Auditor").mkdir(parents=True)
    (ro_ws / "scripts").mkdir(parents=True)
    (ro_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndomain_id: DOM-01\n---\n# Hub\n", encoding="utf-8"
    )
    (ro_ws / "scripts" / "nk_registry_indexer.py").write_text('"""Idx."""\n', encoding="utf-8")
    aud_md = ro_ws / ".agents" / "agents" / "NK-RSI-Auditor" / "agent.md"
    aud_md.write_text(
        "---\nname: NK-RSI-Auditor\ndomain_id: DOM-04\nmodel: inherit\nthinking_level: HIGH\n"
        "tools:\n  - read_file\n  - grep_search\n  - find_by_name\n  - list_dir\n"
        "  - view_file_outline\n  - view_code_item\n  - send_message\n---\n# Auditor\n",
        encoding="utf-8",
    )
    idx = NKRegistryIndexer(workspace_root=ro_ws, stage_dir=ro_ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    parsed_meta = idx._parse_native_agent_metadata(aud_md.read_text(encoding="utf-8"))
    assert "model" not in parsed_meta and "thinking_level" not in parsed_meta and parsed_meta["enable_write_tools"] is False
    assert idx.verify_gt14_crit01_governance()["passed"] is True

    for bad_tool in ("search_web", "call_mcp_tool", "write_file"):
        aud_md.write_text(
            f"---\nname: NK-RSI-Auditor\ndomain_id: DOM-04\ntools:\n  - read_file\n  - {bad_tool}\n  - send_message\n---\n",
            encoding="utf-8",
        )
        res_bad = idx.verify_gt14_crit01_governance()
        assert res_bad["passed"] is False and any(bad_tool in i for i in res_bad["issues"])

    assert "aligner" not in indexer_mod.DOMAIN_TAXONOMY["DOM-01"]["keywords"]
    assert "forge" not in indexer_mod.DOMAIN_TAXONOMY["DOM-02"]["keywords"]


def test_p0_bug_03_nk_gate_6_of_6_sync_and_verify_drift(tmp_path: Path) -> None:
    """Verifica sync 6/6 di nk-gate/agents e rules/AGENTS.md senza frontmatter + verify drift."""
    import hashlib

    ws = tmp_path / "gate_ws"
    (ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True)
    (ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndomain_id: DOM-01\n---\n# Hub\n",
        encoding="utf-8",
    )
    (ws / ".agents" / "rules").mkdir(parents=True)
    (ws / ".agents" / "rules" / "anti_crash_rules.md").write_text(
        "---\ntrigger: always_on\ndescription: Anti-crash\n---\n# Regole\nRegola valida.\n",
        encoding="utf-8",
    )
    (ws / ".agents" / "plugins" / "nk-gate").mkdir(parents=True)
    (ws / ".agents" / "plugins" / "nk-gate" / "plugin.json").write_text(
        '{"name": "nk-gate", "version": "6.4.0"}',
        encoding="utf-8",
    )
    (ws / "scripts").mkdir(parents=True)
    (ws / "scripts" / "nk_registry_indexer.py").write_text('"""Idx."""\n', encoding="utf-8")

    agent_names = [
        "NK-Bug-Hunter",
        "NK-Memory-Scribe",
        "NK-Oracle-Gate",
        "NK-RSI-Auditor",
        "NK-Sandbox-Runner",
        "NK-Security-Sentinel",
    ]
    for ag in agent_names:
        ag_dir = ws / ".agents" / "agents" / ag
        ag_dir.mkdir(parents=True)
        (ag_dir / "agent.md").write_text(
            f"---\nname: {ag}\ndomain_id: DOM-04\ntools:\n  - read_file\n---\n# {ag}\n",
            encoding="utf-8",
        )

    idx = NKRegistryIndexer(
        workspace_root=ws,
        global_config_dir=tmp_path / "no_cfg",
    )
    missing_res = idx.verify()
    assert missing_res["passed"] is False and missing_res["status"] == "MISSING_MANIFEST"
    idx.sync()

    for ag in agent_names:
        mir = ws / ".agents" / "plugins" / "nk-gate" / "agents" / f"{ag}.md"
        assert mir.is_file()
        assert mir.read_bytes() == (ws / ".agents" / "agents" / ag / "agent.md").read_bytes()

    rule_mir = ws / ".agents" / "plugins" / "nk-gate" / "rules" / "AGENTS.md"
    assert rule_mir.is_file()
    rule_text = rule_mir.read_text(encoding="utf-8")
    assert not rule_text.lstrip().startswith("---")
    assert len(rule_text.encode("utf-8")) < 24000
    assert "# Regole\nRegola valida." in rule_text
    assert idx.verify()["passed"] is True

    drift_mir = ws / ".agents" / "plugins" / "nk-gate" / "agents" / "NK-Bug-Hunter.md"
    orig_bytes = drift_mir.read_bytes()
    drift_mir.write_text("# Drift\n", encoding="utf-8")
    res_drift = idx.verify()
    assert res_drift["passed"] is False
    assert any("NK-Bug-Hunter.md" in i for i in res_drift["issues"])
    drift_mir.write_bytes(orig_bytes)

    lf_bytes = orig_bytes.replace(b"\r\n", b"\n")
    drift_mir.write_bytes(lf_bytes)
    assert idx.verify()["passed"] is True
    drift_mir.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
    assert idx.verify()["passed"] is True
    drift_mir.unlink()
    res_missing_ag = idx.verify()
    assert res_missing_ag["passed"] is False
    assert any("mancante" in i for i in res_missing_ag["issues"])
    drift_mir.write_bytes(orig_bytes)

    rule_mir.write_text("# Regole\nTesto difforme.\n", encoding="utf-8")
    res_rule_diff = idx.verify()
    assert res_rule_diff["passed"] is False
    assert any("disallineato" in i for i in res_rule_diff["issues"])
    rule_mir.write_bytes(b"# Regole\nRegola valida.\n")
    assert idx.verify()["passed"] is True
    rule_mir.write_bytes(b"# Regole\r\nRegola valida.\r\n")
    assert idx.verify()["passed"] is True
    rule_mir.unlink()
    res_missing_rule = idx.verify()
    assert res_missing_rule["passed"] is False
    assert any("mancante" in i for i in res_missing_rule["issues"])
    rule_mir.write_text("# Regole\nRegola valida.\n", encoding="utf-8")

    rule_mir.write_bytes(b"# Regole\nRegola valida.\n")
    lf_sha = hashlib.sha256(b"# Regole\nRegola valida.\n").hexdigest()
    crlf_sha = hashlib.sha256(b"# Regole\r\nRegola valida.\r\n").hexdigest()
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", "") is False
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", "cafebabe") is False
    assert idx._sha256_matches_eol_normalized(ws / "missing_file.md", "deadbeef", "cafebabe") is False
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", crlf_sha) is True
    rule_mir.write_bytes(b"# Regole\r\nRegola valida.\r\n")
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", lf_sha) is True
    rule_mir.write_text("# Regole\nRegola valida.\n", encoding="utf-8")

    rule_mir.write_text("---\nbad: true\n---\n# Regole\n", encoding="utf-8")
    res_fm = idx.verify()
    assert res_fm["passed"] is False
    assert any("frontmatter" in i for i in res_fm["issues"])
    rule_mir.write_text("# Regole\nRegola valida.\n", encoding="utf-8")

    manifest_file = next(ws.rglob("nk_registry_manifest.json"))
    orig_manifest_raw = manifest_file.read_text(encoding="utf-8")
    full_manifest = idx.load_manifest()
    assert full_manifest is not None

    corrupted_schema = json.loads(json.dumps(full_manifest))
    corrupted_schema.pop("shards", None)
    corrupted_schema.pop("global_hygiene_profile", None)
    corrupted_schema["domains"].pop("DOM-05", None)
    corrupted_schema["intent_dispatch_table"]["bad_scalar"] = "invalid"
    corrupted_schema["intent_dispatch_table"]["bad_dom"] = {"domain_id": "DOM-99"}
    corrupted_schema["skills_index"][next(iter(corrupted_schema["skills_index"]))]["sha256"] = "0" * 64
    corrupted_schema["scripts_index"][next(iter(corrupted_schema["scripts_index"]))]["sha256"] = "0" * 64
    corrupted_schema["native_agents_index"][next(iter(corrupted_schema["native_agents_index"]))]["sha256"] = "0" * 64
    manifest_file.write_text(json.dumps(corrupted_schema), encoding="utf-8")
    NKRegistryIndexer._MANIFEST_CACHE.clear()
    res_drift_meta = idx.verify()
    assert res_drift_meta["passed"] is False
    issues_joined = "\n".join(res_drift_meta["issues"])
    assert "global_hygiene_profile" in issues_joined
    assert "DOM-05" in issues_joined
    assert "bad_scalar" in issues_joined
    assert "DOM-99" in issues_joined
    assert "Drift SHA-256 rilevato sulla skill" in issues_joined
    assert "Drift SHA-256 rilevato sullo script" in issues_joined
    assert "Drift SHA-256 rilevato sul sub-agente nativo" in issues_joined

    corrupted_counts = json.loads(json.dumps(full_manifest))
    corrupted_counts.pop("shards", None)
    corrupted_counts["skills_index"]["NK-Fake-Skill"] = {"domain_id": "DOM-02", "sha256": "0" * 64}
    corrupted_counts["scripts_index"]["fake_missing_script.py"] = {"domain_id": "DOM-03", "sha256": "0" * 64}
    corrupted_counts["native_agents_index"]["NK-Fake-Agent"] = {"domain_id": "DOM-04", "sha256": "0" * 64}
    manifest_file.write_text(json.dumps(corrupted_counts), encoding="utf-8")
    NKRegistryIndexer._MANIFEST_CACHE.clear()
    res_cnt = idx.verify()
    assert res_cnt["passed"] is False
    cnt_issues_joined = "\n".join(res_cnt["issues"])
    assert "Conteggio o nomi skill disallineati" in cnt_issues_joined
    assert "Conteggio o nomi script disallineati" in cnt_issues_joined
    assert "Conteggio o nomi native agents disallineati" in cnt_issues_joined

    manifest_file.write_text(orig_manifest_raw, encoding="utf-8")
    NKRegistryIndexer._MANIFEST_CACHE.clear()
    assert idx.verify()["passed"] is True


def test_p0_bug_07_release_zip_root_bridge_and_installers(tmp_path: Path) -> None:
    """Verifica P0-BUG-07: root bridge nello ZIP di release e assenza di {} negli installer."""
    import zipfile

    ws = tmp_path / "zip_ws"
    (ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True)
    (ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndomain_id: DOM-01\n---\n# Hub\n",
        encoding="utf-8",
    )
    (ws / "nk_docs_and_setup").mkdir(parents=True)
    (ws / "nk_docs_and_setup" / "root_bridge_AGENTS.md").write_text(
        "# Bridge Root\n",
        encoding="utf-8",
    )
    (ws / "scripts").mkdir(parents=True)
    (ws / "scripts" / "nk_registry_indexer.py").write_text('"""Idx."""\n', encoding="utf-8")

    idx = NKRegistryIndexer(
        workspace_root=ws,
        stage_dir=ws / ".staging",
        global_config_dir=tmp_path / "no_cfg",
    )
    zip_out = tmp_path / "nk_release.zip"
    idx.build_release_zip(output_path=zip_out)
    assert zip_out.is_file()

    with zipfile.ZipFile(zip_out, "r") as zf:
        names = set(zf.namelist())
        assert ".agents/AGENTS.md" in names
        assert ".agents/skills.json" in names
        assert ".agents/plugins.json" in names
        assert "NK_External_Projects/.gitkeep" in names
        skills_data = json.loads(zf.read(".agents/skills.json").decode("utf-8"))
        plugins_data = json.loads(zf.read(".agents/plugins.json").decode("utf-8"))
        assert "entries" in skills_data and isinstance(skills_data["entries"], list) and skills_data["entries"]
        assert "entries" in plugins_data and isinstance(plugins_data["entries"], list) and plugins_data["entries"]

    for inst_name in ("install.ps1", "install.sh"):
        inst_path = WORKSPACE_ROOT / "nk_docs_and_setup" / inst_name
        inst_text = inst_path.read_text(encoding="utf-8")
        assert "entries" in inst_text
        assert "NK_Hub/.agents/skills" in inst_text
        assert "NK_Hub/.agents/plugins" in inst_text
        assert "root_bridge_AGENTS.md" in inst_text
        assert 'echo "{}" >' not in inst_text and "WriteAllText($SkillsJsonPath, \"{}\"" not in inst_text
