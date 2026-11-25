# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per nk_registry_indexer.py di NK Hub Generation 1.0.0-Generation.
Modulo: tests/test_nk_registry_indexer.py.
Valida sync, verify, CRIT-01 MCP fantasma, lookup O(1), Hot-Swap, shard, twin parity e SSOT.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict

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

RETIRED_SCRIPTS = (
    "invisible_healing_loop.py",
    "nk_auto_inning.py",
    "micro_hud_renderer.py",
    "nk_active_runtime_sentinel.py",
    "nk_swarm_messenger.py",
    "sbfl_engine.py",
)

EXPECTED_SIX_AGENTS = (
    "NK-Arch-Specifier",
    "NK-Builder-Agent",
    "NK-RSI-Auditor",
    "NK-Scribe-Agent",
    "NK-Security-DAST-Auditor",
    "NK-Specifier-Agent",
)

_MODULE_SYNCED_CACHE: Dict[str, Any] = {}


@pytest.fixture(scope="module")
def synced_mirror_env(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Esegue --sync una sola volta per modulo per i test @pytest.mark.integration."""
    base_dir = tmp_path_factory.mktemp("nk_registry_sync_mod")
    stage_dir = base_dir / ".staging"
    stage_dir.mkdir(parents=True, exist_ok=True)
    del_src = WORKSPACE_ROOT / ".staging" / ".deleted_files.json"
    if del_src.is_file():
        shutil.copy2(del_src, stage_dir / ".deleted_files.json")

    no_cfg = base_dir / "no_cfg"
    no_cfg.mkdir(parents=True, exist_ok=True)
    rc = indexer_mod.main(["--sync", "--stage-dir", str(stage_dir)])
    manifest_path = stage_dir / "nk_genome" / "nk_registry_manifest.json"
    skill_index_path = stage_dir / "nk_genome" / "SKILL_INDEX.md"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rehydrated = NKRegistryIndexer(
        workspace_root=WORKSPACE_ROOT, stage_dir=stage_dir, global_config_dir=no_cfg
    ).load_manifest()
    _MODULE_SYNCED_CACHE.clear()
    _MODULE_SYNCED_CACHE.update({
        "rc": rc, "stage_dir": stage_dir, "no_cfg": no_cfg,
        "manifest_path": manifest_path, "skill_index_path": skill_index_path,
        "manifest": manifest, "rehydrated": rehydrated or {},
    })
    try:
        yield _MODULE_SYNCED_CACHE
    finally:
        _MODULE_SYNCED_CACHE.clear()


@pytest.mark.integration
def test_nk_registry_sync_without_staging_and_grounding_legacy_genome(tmp_path: Path) -> None:
    """1. Verifica G3-02 sync senza --sync-staging, grounding report e fallback legacy genome/."""
    prod_stg_manifest = WORKSPACE_ROOT / ".staging" / "nk_genome" / "nk_registry_manifest.json"
    existed_before = prod_stg_manifest.exists()
    mtime_before = prod_stg_manifest.stat().st_mtime_ns if existed_before else None

    g3_ws = tmp_path / "g3_no_stg_ws"
    (g3_ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True, exist_ok=True)
    (g3_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndescription: Mini.\nversion: '6.0.0-Carbon'\ndomain_id: 'DOM-01'\n---\n# Hub\n", encoding="utf-8"
    )
    (g3_ws / "scripts").mkdir(parents=True, exist_ok=True)
    (g3_ws / "scripts" / "mini.py").write_text('"""Mini.\n@domain_id: DOM-01\n"""\n', encoding="utf-8")

    no_stg_indexer = NKRegistryIndexer(workspace_root=g3_ws, global_config_dir=tmp_path / "no_cfg")
    no_stg_indexer.resolve_genome_dir = lambda root=None: (tmp_path / "isolated_prod_genome", False)  # type: ignore[method-assign]
    res_no_stg = no_stg_indexer.sync(sync_staging=False)
    assert res_no_stg["passed"] is True and res_no_stg["sync_staging"] is False
    assert not (g3_ws / ".staging" / "nk_genome" / "nk_registry_manifest.json").exists()
    assert (prod_stg_manifest.stat().st_mtime_ns == mtime_before) if existed_before else (not prod_stg_manifest.exists())

    bad_rep = tmp_path / "bad_report.md"
    bad_rep.write_text("Esegui scripts/atomic_2pc_commit.py ora.\n", encoding="utf-8")
    assert tr_mod.verify_report_grounding(bad_rep)["exit_code"] == 1
    good_rep = tmp_path / "good_report.md"
    good_rep.write_text("Esegui scripts/win32_2pc_engine.py ora.\n", encoding="utf-8")
    assert tr_mod.verify_report_grounding(good_rep)["exit_code"] == 0

    legacy_ws = tmp_path / "legacy_ext_ws"
    (legacy_ws / "genome").mkdir(parents=True, exist_ok=True)
    (legacy_ws / "genome" / "concept_map.md").write_text("# Concept\n", encoding="utf-8")
    tetra = NKRegistryIndexer(workspace_root=legacy_ws, stage_dir=legacy_ws / ".staging", global_config_dir=tmp_path / "no_cfg").resolve_tetralogy_files()
    assert tetra["is_legacy_genome"] is True and tetra["warning"] is not None and tetra["files"]["concept_map.md"] is not None


def _assert_hotswap_verify_and_cli_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sb_ws = tmp_path / "verify_ws"
    for d in (".agents/skills/NK-Orchestrator", ".agents/skills/NK-Custom-HotSwap", ".agents/agents/NK-Reader-Auditor", "scripts/schemas"):
        (sb_ws / d).mkdir(parents=True, exist_ok=True)
    (sb_ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text("---\nname: NK-Orchestrator\nversion: '1.0.0-Generation'\ndomain_id: 'DOM-01'\n---\n# Hub\n", encoding="utf-8")
    (sb_ws / ".agents" / "skills" / "NK-Custom-HotSwap" / "SKILL.md").write_text('---\nname: NK-Custom-HotSwap\nversion: "1.0.0-Generation"\ndomain_id: "DOM-03"\nsector: "BUILD_AND_HEAL"\n---\n# HS\n', encoding="utf-8")
    (sb_ws / ".agents" / "agents" / "NK-Reader-Auditor" / "agent.md").write_text("---\nname: NK-Reader-Auditor\nenable_write_tools: false\nenable_subagent_tools: false\n---\n", encoding="utf-8")
    script_py = sb_ws / "scripts" / "nk_registry_indexer.py"
    script_py.write_text('"""Modulo indicizzatore.\n@domain_id: DOM-01\n"""\nimport argparse\n', encoding="utf-8")
    (sb_ws / "scripts" / "schemas" / "nk_ipc_contracts.py").write_text('"""Contratti."""\nfrom pydantic import BaseModel\n', encoding="utf-8")

    indexer = NKRegistryIndexer(workspace_root=sb_ws, stage_dir=sb_ws / ".staging_verify", global_config_dir=tmp_path / "no_cfg")
    assert indexer.sync(sync_staging=True)["passed"] is True
    manifest = indexer.load_manifest()
    assert manifest is not None
    assert manifest["skills_index"]["NK-Custom-HotSwap"]["sector"] == "BUILD_AND_HEAL"
    assert manifest["scripts_index"]["schemas/nk_ipc_contracts.py"]["domain_id"] == "DOM-01"
    verify_res = indexer.verify()
    assert verify_res["passed"] is True
    assert verify_res["status"] == "VALID"
    assert indexer.verify()["passed"] is True

    monkeypatch.setattr(sys, "argv", ["nk_registry_indexer.py", "--root", str(sb_ws), "--verify"])
    assert indexer_mod.main(["--root", str(sb_ws), "--stage-dir", str(sb_ws / ".staging_verify"), "--verify"]) == 0
    assert "VALID" in capsys.readouterr().out

    script_py.write_text('"""Modulo indicizzatore modificato."""\nimport sys\n', encoding="utf-8")
    drift_res = indexer.verify()
    assert drift_res["passed"] is False
    assert drift_res["status"] == "DRIFT_DETECTED"
    assert any("nk_registry_indexer.py" in i for i in drift_res["issues"])


@pytest.mark.integration
def test_nk_registry_indexer_verify_hotswap_and_cli_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """2. Verifica verify SHA-256, Hot-Swap, MISSING_MANIFEST, DRIFT GT-14/RULE-01 e cache verify (migrazione cli_core_gates)."""
    assert NKRegistryIndexer(workspace_root=tmp_path / "no_manifest_ws").verify()["status"] == "MISSING_MANIFEST"

    drift_ws = tmp_path / "drift_ws"
    for d in (".agents/skills/NK-S1", ".agents/agents/NK-Test-Auditor", "scripts", "nk_genome"):
        (drift_ws / d).mkdir(parents=True)
    (drift_ws / ".agents" / "skills" / "NK-S1" / "SKILL.md").write_text("---\nname: NK-S1\ndomain_id: DOM-01\n---\n# Skill\n", encoding="utf-8")
    (drift_ws / ".agents" / "agents" / "NK-Test-Auditor" / "agent.md").write_text("---\nname: NK-Test-Auditor\nenable_write_tools: true\nenable_subagent_tools: true\n---\n", encoding="utf-8")
    (drift_ws / "scripts" / "s1.py").write_text("X = 1\n", encoding="utf-8")
    bad_manifest = {
        "version": "6.0.0-Carbon", "domains": {"DOM-01": {"scripts": ["scripts/s1.py"]}},
        "skills_index": {"NK-S1": {"sha256": "0" * 64}}, "scripts_index": {"s1.py": {"sha256": "0" * 64}},
        "native_agents_index": {"NK-Test-Auditor": {"sha256": "0" * 64, "enable_write_tools": True, "enable_subagent_tools": True}},
        "intent_dispatch_table": {"bad_str_entry": "not_a_dict", "bad_dom_entry": {"domain_id": "DOM-99"}},
    }
    (drift_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps(bad_manifest), encoding="utf-8")
    v_res = NKRegistryIndexer(workspace_root=drift_ws).verify()
    assert v_res["status"] == "DRIFT_DETECTED"
    assert any("GT-14" in i for i in v_res["issues"])
    assert any("RULE-01" in i for i in v_res["issues"])
    _assert_hotswap_verify_and_cli_drift(tmp_path, monkeypatch, capsys)


@pytest.mark.integration
def test_global_skill_filter_hygiene_and_corrupt_config(tmp_path: Path) -> None:
    """3. Verifica consolidamento plugin, disattivazione skill globali e quarantena config.json corrotto."""
    temp_cfg_dir = tmp_path / "gemini_config"
    skills_dir, plugins_dir = temp_cfg_dir / "skills", temp_cfg_dir / "plugins"
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
    after = idx.scan_global_hygiene_profile(11)
    assert after["active_external_skills_count"] == 0 and after["disabled_external_skills_count"] == 4 and after["context_pollution_detected"] is False

    corrupt_cfg_dir = tmp_path / "corrupt_gemini_cfg"
    (corrupt_cfg_dir / "skills").mkdir(parents=True, exist_ok=True)
    corrupt_raw = '{"userSettings": {"customKey": "preserve_me"}, "broken": '
    cfg_file = corrupt_cfg_dir / "config.json"
    cfg_file.write_text(corrupt_raw, encoding="utf-8")
    res_corr = NKRegistryIndexer(workspace_root=WORKSPACE_ROOT, stage_dir=tmp_path / ".staging_corrupt", global_config_dir=corrupt_cfg_dir).apply_global_filter()
    assert res_corr["applied"] is True and res_corr.get("config_corrupt") is True and res_corr.get("config_preserved") is True
    assert cfg_file.read_text(encoding="utf-8") == corrupt_raw
    assert Path(str(res_corr.get("quarantined_config_path", ""))).read_text(encoding="utf-8") == corrupt_raw


def _assert_ratchet_forbidden_tools_and_taxonomy(rat_idx: Any, agent_md: Path) -> None:
    for bad_tool in ("search_web", "call_mcp_tool", "write_file"):
        agent_md.write_text(f"---\nname: NK-Arch-Specifier\ndomain_id: DOM-02\ntools:\n  - read_file\n  - {bad_tool}\n  - send_message\n---\n", encoding="utf-8")
        res_bad = rat_idx.verify_gt14_crit01_governance()
        assert res_bad["passed"] is False and any(bad_tool in i for i in res_bad["issues"])

    assert "aligner" not in indexer_mod.DOMAIN_TAXONOMY["DOM-01"]["keywords"]
    assert "forge" not in indexer_mod.DOMAIN_TAXONOMY["DOM-02"]["keywords"]


@pytest.mark.integration
def test_nk_registry_ratchet_down_and_gt14_governance(tmp_path: Path) -> None:
    """4. Verifica ERR_REGISTRY_RATCHET_DOWN, CRIT-01 MCP fantasma, tool RO locali e DOMAIN_TAXONOMY."""
    rat_ws = tmp_path / "ratchet_ws"
    for sk in ("NK-Orchestrator", "NK-Ideator", "NK-System-Architect", "NK-Oracle-Evaluator"):
        (rat_ws / ".agents" / "skills" / sk).mkdir(parents=True, exist_ok=True)
        (rat_ws / ".agents" / "skills" / sk / "SKILL.md").write_text(f"---\nname: {sk}\nversion: '1.0.0-Generation'\n---\n# {sk}\n", encoding="utf-8")
    (rat_ws / ".agents" / "agents" / "NK-Arch-Specifier").mkdir(parents=True, exist_ok=True)
    agent_md = rat_ws / ".agents" / "agents" / "NK-Arch-Specifier" / "agent.md"
    agent_md.write_text(
        "---\nname: NK-Arch-Specifier\ndomain_id: DOM-02\nenable_write_tools: false\nenable_subagent_tools: false\nenable_mcp_tools: false\n"
        "tools:\n  - read_file\n  - grep_search\n  - find_by_name\n  - list_dir\n  - view_file_outline\n  - view_code_item\n  - send_message\n---\n# Specifier\n",
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
    assert blocked_sync["passed"] is False and blocked_sync["status"] == "RATCHET_BLOCKED" and blocked_sync["error_code"] == "ERR_REGISTRY_RATCHET_DOWN"
    assert manifest_file.read_bytes() == before_bytes
    assert rat_idx.sync(allow_ratchet_down=True)["passed"] is True
    assert rat_idx.verify_gt14_crit01_governance()["passed"] is True
    _assert_ratchet_forbidden_tools_and_taxonomy(rat_idx, agent_md)


def _assert_nkgate_rule_drift_checks(idx: Any, rule_mir: Path) -> None:
    rule_mir.write_text("# Regole\nTesto difforme.\n", encoding="utf-8")
    assert any("disallineato" in i for i in idx.verify()["issues"])
    rule_mir.unlink()
    assert any("mancante" in i for i in idx.verify()["issues"])
    rule_mir.write_text("---\nbad: true\n---\n# Regole\n", encoding="utf-8")
    assert any("frontmatter" in i for i in idx.verify()["issues"])
    rule_mir.write_bytes(b"# Regole\nRegola valida.\n")


def _assert_nkgate_drift_eol_and_corrupted_schemas(
    ws: Path, idx: Any, agent_names: list[str], rule_mir: Path
) -> None:
    for ag in agent_names:
        mir = ws / ".agents" / "plugins" / "nk-gate" / "agents" / f"{ag}.md"
        assert (mir.is_file(), mir.read_bytes()) == (True, (ws / ".agents" / "agents" / ag / "agent.md").read_bytes())

    rule_text = rule_mir.read_text(encoding="utf-8")
    assert (not rule_text.lstrip().startswith("---"), len(rule_text.encode("utf-8")) < 24000, "# Regole\nRegola valida." in rule_text) == (True, True, True)
    assert idx.verify()["passed"] is True

    drift_mir = ws / ".agents" / "plugins" / "nk-gate" / "agents" / "NK-Bug-Hunter.md"
    orig_bytes = drift_mir.read_bytes()
    drift_mir.write_text("# Drift\n", encoding="utf-8")
    assert any("NK-Bug-Hunter.md" in i for i in idx.verify()["issues"])
    drift_mir.write_bytes(orig_bytes.replace(b"\r\n", b"\n"))
    assert idx.verify()["passed"] is True
    drift_mir.unlink()
    assert any("mancante" in i for i in idx.verify()["issues"])
    drift_mir.write_bytes(orig_bytes)
    _assert_nkgate_rule_drift_checks(idx, rule_mir)


@pytest.mark.integration
def test_p0_bug_03_nk_gate_6_of_6_sync_and_verify_drift(tmp_path: Path) -> None:
    """5. Verifica sync 6/6 di nk-gate/agents e rules/AGENTS.md senza frontmatter + verify drift."""
    ws = tmp_path / "gate_ws"
    (ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True)
    (ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text("---\nname: NK-Orchestrator\ndomain_id: DOM-01\n---\n# Hub\n", encoding="utf-8")
    (ws / ".agents" / "rules").mkdir(parents=True)
    (ws / ".agents" / "rules" / "anti_crash_rules.md").write_text("---\ntrigger: always_on\ndescription: Anti-crash\n---\n# Regole\nRegola valida.\n", encoding="utf-8")
    (ws / ".agents" / "plugins" / "nk-gate").mkdir(parents=True)
    (ws / ".agents" / "plugins" / "nk-gate" / "plugin.json").write_text('{"name": "nk-gate", "version": "1.0.0-Generation"}', encoding="utf-8")
    (ws / "scripts").mkdir(parents=True)
    (ws / "scripts" / "nk_registry_indexer.py").write_text('"""Idx."""\n', encoding="utf-8")

    agent_names = ["NK-Bug-Hunter", "NK-Memory-Scribe", "NK-Oracle-Gate", "NK-RSI-Auditor", "NK-Sandbox-Runner", "NK-Security-Sentinel"]
    for ag in agent_names:
        ag_dir = ws / ".agents" / "agents" / ag
        ag_dir.mkdir(parents=True)
        (ag_dir / "agent.md").write_text(f"---\nname: {ag}\ndomain_id: DOM-04\ntools:\n  - read_file\n---\n# {ag}\n", encoding="utf-8")

    idx = NKRegistryIndexer(workspace_root=ws, global_config_dir=tmp_path / "no_cfg")
    assert idx.verify()["status"] == "MISSING_MANIFEST"
    idx.sync()
    rule_mir = ws / ".agents" / "plugins" / "nk-gate" / "rules" / "AGENTS.md"
    _assert_nkgate_drift_eol_and_corrupted_schemas(ws, idx, agent_names, rule_mir)

    lf_sha = hashlib.sha256(b"# Regole\nRegola valida.\n").hexdigest()
    crlf_sha = hashlib.sha256(b"# Regole\r\nRegola valida.\r\n").hexdigest()
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", "") is False
    assert idx._sha256_matches_eol_normalized(ws / "missing_file.md", "deadbeef", "cafebabe") is False
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", crlf_sha) is True
    rule_mir.write_bytes(b"# Regole\r\nRegola valida.\r\n")
    assert idx._sha256_matches_eol_normalized(rule_mir, "deadbeef", lf_sha) is True
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
    issues_joined = "\n".join(idx.verify()["issues"])
    assert all(tok in issues_joined for tok in ("global_hygiene_profile", "DOM-05", "bad_scalar", "DOM-99", "Drift SHA-256 rilevato sulla skill", "Drift SHA-256 rilevato sullo script", "Drift SHA-256 rilevato sul sub-agente nativo"))

    corrupted_counts = json.loads(json.dumps(full_manifest))
    corrupted_counts.pop("shards", None)
    corrupted_counts["skills_index"]["NK-Fake-Skill"] = {"domain_id": "DOM-02", "sha256": "0" * 64}
    corrupted_counts["scripts_index"]["fake_missing_script.py"] = {"domain_id": "DOM-03", "sha256": "0" * 64}
    corrupted_counts["native_agents_index"]["NK-Fake-Agent"] = {"domain_id": "DOM-04", "sha256": "0" * 64}
    manifest_file.write_text(json.dumps(corrupted_counts), encoding="utf-8")
    NKRegistryIndexer._MANIFEST_CACHE.clear()
    cnt_issues = "\n".join(idx.verify()["issues"])
    assert all(tok in cnt_issues for tok in ("Conteggio o nomi skill disallineati", "Conteggio o nomi script disallineati", "Conteggio o nomi native agents disallineati"))

    manifest_file.write_text(orig_manifest_raw, encoding="utf-8")
    NKRegistryIndexer._MANIFEST_CACHE.clear()
    assert idx.verify()["passed"] is True


@pytest.mark.fast
def test_shards_rehydration_and_manifest_builder_resolution_branches(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """6. Chiude i branch di shards.py, manifest_builder.py e cache_and_skills.py."""
    from _internal.nk_registry_indexer import shards as shards_mod

    slim_path = tmp_path / "nk_registry_manifest.json"
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir(parents=True)
    (shards_dir / "corrupt.json").write_text("{bad", encoding="utf-8")
    (shards_dir / "nondict.json").write_text("[1, 2]", encoding="utf-8")
    (shards_dir / "dom00.json").write_text(json.dumps({"global_hygiene_profile": {"ok": True}, "docs_and_setup_index": {"doc.md": {"relative_path": "nk_docs_and_setup/doc.md"}}, "milestone_anchor_id": "M-1"}), encoding="utf-8")
    (shards_dir / "dom06.json").write_text(json.dumps({"release": "1.0.0"}), encoding="utf-8")
    (shards_dir / "dom09.json").write_text(
        json.dumps({"domain": {"domain_id": "DOM-09", "name": "D9", "primary_skill": "SkX", "keywords": ["k0"]}, "skills_index": {"SkX": {"sector": "SEC"}}, "scripts_index": {"sc.py": {"classes": []}}, "native_agents_index": {"AgX": {"enable_mcp_tools": True}}, "intent_dispatch_table": {"k_str": "mode_d", "k_list": ["Ag", "mode_b"], "k_dict": {"recommended_mode": "mode_c", "primary_agent": "A"}}}),
        encoding="utf-8",
    )
    slim_payload = {"domains": {"DOM-99": {"name": "FallbackDom"}}, "shards": {"DOM-00": "shards/dom00.json", "DOM-06": "shards/dom06.json", "DOM-09": "shards/dom09.json", "DOM-MISS": "shards/missing.json", "DOM-BAD": "shards/corrupt.json", "DOM-LIST": "shards/nondict.json"}}
    merged = shards_mod.rehydrate_manifest_from_shards(slim_path, slim_payload)
    assert merged["milestone_anchor_id"] == "M-1" and merged["release_meta"] == {"release": "1.0.0"}
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
    assert docs_idx.resolve_library_path("nonexistent.md") is None and "bundle.zip" not in docs_idx.scan_docs_and_setup()
    (docs_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"docs_and_setup_index": {"guide.md": {"relative_path": "nk_docs_and_setup/guide.md"}}, "scripts_index": {"sub/tool.py": {"path": "scripts/sub/tool.py"}, "top_tool.py": {"path": "scripts/top_tool.py"}}}), encoding="utf-8")
    assert docs_idx.resolve_library_path("guide.md") == "nk_docs_and_setup/guide.md"
    assert docs_idx.resolve_library_path("sub/tool.py") == "scripts/sub/tool.py"
    assert docs_idx.resolve_library_path("nested/top_tool.py") == "scripts/top_tool.py"


def _assert_installers_lookup_and_preflight(idx: Any, tmp_path: Path) -> None:
    for inst_name in ("install.ps1", "install.sh"):
        inst_text = (WORKSPACE_ROOT / "nk_docs_and_setup" / inst_name).read_text(encoding="utf-8")
        assert ("entries" in inst_text, "NK_Hub/.agents/skills" in inst_text, "root_bridge_AGENTS.md" in inst_text) == (True, True, True)
        assert 'echo "{}" >' not in inst_text

    assert idx.lookup("GOV_AND_ROUTING")["match_type"] == "domain"
    assert idx.lookup("NK-Builder-Agent")["match_type"] == "native_agent"
    assert idx.lookup("zzzxxyy_unknown_query_999")["match_type"] == "fallback"

    custom_ws = tmp_path / "custom_ssot_ws"
    for folder in ("nk_genome", "nk_tracking/anchor", ".staging"):
        (custom_ws / folder).mkdir(parents=True, exist_ok=True)
    (custom_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"version": "1.0.0-Generation", "summary": {"total_skills": 18, "total_domains": 5, "total_scripts": 32}, "skills_index": {f"NK-Skill-{i}": {"domain_id": "DOM-01"} for i in range(18)}}), encoding="utf-8")
    (custom_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"_version": "1.0.0-Generation", "metrics": {"skills_audited": 18, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}), encoding="utf-8")
    alignment = PreflightHealthChecker(workspace_root=custom_ws)._check_baseline_alignment()
    assert (alignment["passed"], alignment["expected_skills"], alignment["skills_audited"]) == (True, 18, 18)


def _assert_release_zip_and_preflight_alignment(
    ws: Path, idx: Any, tmp_path: Path
) -> None:
    tas_md = idx.generate_tas_certification_matrix()
    assert ("# Matrice di Certificazione TAS" in tas_md, "SK-Card" in tas_md, "NK-Builder-Agent" in tas_md) == (True, True, True)
    out_zip = ws / "release_inside.zip"
    assert (idx.build_release_zip(out_zip)["passed"], out_zip.is_file()) == (True, True)
    with zipfile.ZipFile(out_zip, "r") as zf:
        names = set(zf.namelist())
        assert {".agents/AGENTS.md", ".agents/skills.json", ".agents/plugins.json", "NK_External_Projects/.gitkeep"}.issubset(names)
        assert bool(json.loads(zf.read(".agents/skills.json").decode("utf-8"))["entries"])
        assert bool(json.loads(zf.read(".agents/plugins.json").decode("utf-8"))["entries"])
    _assert_installers_lookup_and_preflight(idx, tmp_path)


@pytest.mark.integration
def test_p0_bug_07_release_zip_twin_synthetic_matrix_and_lookup(tmp_path: Path) -> None:
    """7. Verifica release ZIP, twin parity sintetica, matrix/skills_scan, preflight e lookup synthetic."""
    from _internal.nk_registry_indexer import skills_scan as sk_scan
    load_nk_script_module("rsi_convergence_engine")
    from _internal.rsi_convergence_engine import eco_audits as rsi_eco

    ws = tmp_path / "mat_zip_ws"
    for d in (".agents/skills/SK-Card", ".agents/skills/SK-Del", ".staging/.agents/skills/SK-Card", ".agents/agents/NK-Builder-Agent", ".agents/plugins/nk-gate/agents", "scripts/schemas", "nk_tracking", "nk_docs_and_setup"):
        (ws / d).mkdir(parents=True)
    (ws / "nk_docs_and_setup" / "root_bridge_AGENTS.md").write_text("# Bridge Root\n", encoding="utf-8")
    (ws / ".agents" / "skills" / "SK-Card" / "SKILL.md").write_text("# Old prod\n", encoding="utf-8")
    (ws / ".agents" / "skills" / "SK-Del" / "SKILL.md").write_text("# Deleted\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps([".agents/skills/SK-Del/SKILL.md"]), encoding="utf-8")
    staged_card = ws / ".staging" / ".agents" / "skills" / "SK-Card" / "SKILL.md"
    staged_card.write_text(
        "---\nname: SK-Card\nrouting_keywords:\n  - async\n  - wal\npriority_keywords: [\"p1\", \"p2\"]\ncli_scripts: [bad, \"ok.py\"]\ntools: read_file, edit_file\n---\n"
        "<yaml_metadata_card>\nrole_identity: \"Tester\"\ndomain_id: \"DOM-03\"\nversion: \"1.0.0-Generation\"\nsector: \"BUILD\"\nenable_mcp_tools: true\n</yaml_metadata_card>\nVedi [ref](references/guide.md).\n",
        encoding="utf-8",
    )
    (ws / ".agents" / "agents" / "NK-Builder-Agent" / "agent.md").write_text("---\nname: NK-Builder-Agent\ndomain_id: DOM-03\ntools:\n  - read_file\n---\n# B\n", encoding="utf-8")
    (ws / ".agents" / "plugins" / "nk-gate" / "agents" / "NK-Builder-Agent.md").write_text("---\nname: NK-Builder-Agent\ndomain_id: DOM-03\ntools:\n  - read_file\n---\n# B\n", encoding="utf-8")
    (ws / "scripts" / "nk_registry_indexer.py").write_text('"""Idx."""\n', encoding="utf-8")
    (ws / "scripts" / "schemas" / "nk_ipc_contracts.py").write_text('"""IPC."""\n', encoding="utf-8")
    (ws / "nk_tracking" / ".wal_2pc.jsonl").write_text("{}", encoding="utf-8")
    (ws / "nk_tracking" / "dast_report_1.json").write_text("{}", encoding="utf-8")
    (ws / "nk_tracking" / "junk.tmp").write_text("x", encoding="utf-8")

    parsed_meta = sk_scan.parse_skill_metadata_impl(staged_card.read_text(encoding="utf-8"))
    assert parsed_meta["routing_keywords"] == ["async", "wal"]
    assert parsed_meta["priority_keywords"] == ["p1", "p2"]
    assert parsed_meta["enable_mcp_tools"] is True
    assert parsed_meta["auxiliary_links"] == ["references/guide.md"]
    assert sk_scan.resolve_skill_native_subagent_impl("SK-Card", "DOM-03", {"native_subagent": "Custom-Ag"}) == "Custom-Ag"

    idx = NKRegistryIndexer(workspace_root=ws, stage_dir=ws / ".staging", global_config_dir=tmp_path / "no_cfg")
    assert "SK-Del" not in idx._collect_priority_skills()
    assert rsi_eco.audit_twin_manifest_parity_impl(ws)["passed"] is True
    (ws / ".agents" / "plugins" / "nk-gate" / "agents" / "NK-Builder-Agent.md").write_text("# Drifted\n", encoding="utf-8")
    assert rsi_eco.audit_twin_manifest_parity_impl(ws)["passed"] is False
    _assert_release_zip_and_preflight_alignment(ws, idx, tmp_path)


@pytest.mark.integration
@pytest.mark.usefixtures("synced_mirror_env")
def test_nk_registry_indexer_sync_generates_manifest_and_skill_index(
    tmp_path: Path,
) -> None:
    """8. Verifica che --sync generi nk_registry_manifest.json e SKILL_INDEX.md completi sul repo reale."""
    _ = tmp_path
    assert _MODULE_SYNCED_CACHE["rc"] == 0
    assert _MODULE_SYNCED_CACHE["manifest_path"].exists() and _MODULE_SYNCED_CACHE["skill_index_path"].exists()
    manifest = _MODULE_SYNCED_CACHE["manifest"]
    for key in ("version", "domains", "skills_index", "scripts_index", "intent_dispatch_table", "global_hygiene_profile"):
        assert key in manifest
    assert set(manifest["domains"].keys()) == {"DOM-01", "DOM-02", "DOM-03", "DOM-04", "DOM-05"}
    assert len(manifest["skills_index"]) == 11 and len(manifest["scripts_index"]) >= 32
    assert manifest["scripts_index"]["schemas/dual_ledgers.py"]["domain_id"] == "DOM-01"
    assert manifest["scripts_index"]["schemas/nk_ipc_contracts.py"]["domain_id"] == "DOM-01"
    md_text = _MODULE_SYNCED_CACHE["skill_index_path"].read_text(encoding="utf-8")
    assert "DOM-01" in md_text and "DOM-05" in md_text and "NK-Python-Async-Builder" in md_text


def _assert_lookup_o1_timings(indexer: Any, max_ms: float) -> None:
    t0 = time.perf_counter()
    res_dom = indexer.lookup("DOM-04")
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert (res_dom["found"], res_dom["domain_name"], dt_ms < max_ms) == (True, "AUDIT_DAST_AND_RCA", True)
    res_skill = indexer.lookup("NK-Python-Async-Builder")
    assert (res_skill["found"], res_skill["domain_id"], res_skill["elapsed_ms"] < max_ms) == (True, "DOM-03", True)
    res_script = indexer.lookup("vibe_sprint_router.py")
    assert (res_script["found"], "--discovery-check" in res_script["cli_flags"], res_script["elapsed_ms"] < max_ms) == (True, True, True)
    res_intent = indexer.lookup("Esegui recall memoria episodica")
    assert (res_intent["found"], res_intent["domain_id"], res_intent["elapsed_ms"] < max_ms) == (True, "DOM-05", True)

    for query_txt, expected_mode in (("stato dell'arte read-only analisi", "mode_d"), ("esegui cold review 6 gate turno 4", "mode_a"), ("diagnosi sbfl ochiai rca", "mode_b")):
        m_res = indexer.lookup(query_txt)
        assert (m_res["found"], m_res["recommended_mode"]) == (True, expected_mode)


def _assert_real_ecosystem_agents_and_parity(synced: Dict[str, Any], rsi_eco: Any) -> None:
    real_idx = NKRegistryIndexer(workspace_root=WORKSPACE_ROOT, stage_dir=WORKSPACE_ROOT / ".staging", global_config_dir=synced["no_cfg"])
    assert len(real_idx._collect_priority_native_agents()) == 6
    assert "NK-Arch-Specifier" in real_idx._collect_priority_native_agents()
    skills = real_idx._collect_priority_skills()
    assert "NK-Oracle-Evaluator" in skills
    assert "NK-Plan-Aligner" not in skills
    assert "NK-State-Router" not in skills
    assert real_idx.verify_gt14_crit01_governance()["passed"] is True

    real_parity = rsi_eco.audit_twin_manifest_parity_impl(WORKSPACE_ROOT)
    assert real_parity["passed"] is True and real_parity["checked_agents"] == 6 and real_parity["mismatches"] == []
    for ag_name in EXPECTED_SIX_AGENTS:
        assert (WORKSPACE_ROOT / ".agents" / "agents" / ag_name / "agent.md").read_bytes().replace(b"\r\n", b"\n") == (WORKSPACE_ROOT / ".agents" / "plugins" / "nk-gate" / "agents" / f"{ag_name}.md").read_bytes().replace(b"\r\n", b"\n")
    active_scripts = synced["rehydrated"].get("scripts_index", {})
    for retired_name in RETIRED_SCRIPTS:
        assert retired_name not in active_scripts and f"scripts/{retired_name}" not in active_scripts


@pytest.mark.integration
def test_nk_registry_lookup_o1_real_ecosystem_6_agents_and_twin_parity(
    synced_mirror_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """9. Verifica lookup O(1) <50ms, 6 agent GT-14 reali, parita gemelli, SSOT router e lookup CLI."""
    load_nk_script_module("rsi_convergence_engine")
    from _internal.rsi_convergence_engine import eco_audits as rsi_eco

    indexer = NKRegistryIndexer(
        workspace_root=WORKSPACE_ROOT, stage_dir=synced_mirror_env["stage_dir"], global_config_dir=synced_mirror_env["no_cfg"]
    )
    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    max_ms = (250.0 if is_cov_instrumented() else 150.0) if is_ci else (150.0 if is_cov_instrumented() else 50.0)
    _assert_lookup_o1_timings(indexer, max_ms)
    _assert_real_ecosystem_agents_and_parity(synced_mirror_env, rsi_eco)

    router = VibeSprintRouter(workspace_root=WORKSPACE_ROOT)
    assert router.resolve_domain_from_manifest("Esegui audit SAST e diagnosi SBFL Ochiai")["domain_id"] == "DOM-04"
    assert router.classify_prompt_intent("Esegui discovery e benchmark architettura")["domain_id"] == "DOM-02"
    assert router.classify_prompt_intent("Implementa modulo async con pydantic")["domain_id"] == "DOM-03"

    monkeypatch.setattr(sys, "argv", ["nk_registry_indexer.py", "--root", str(WORKSPACE_ROOT), "--lookup", "commit atomico 2pc"])
    assert indexer_mod.main(["--root", str(WORKSPACE_ROOT), "--lookup", "commit atomico 2pc"]) == 0
    assert capsys.readouterr().out.strip() != ""


@pytest.mark.integration
def test_registry_indexer_cli_entrypoints_inprocess(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """10. Esercita nk_registry_indexer.py main() CLI su --sync, --lookup, --generate-tas-matrix, --build-release-zip e --verify."""
    ws = tmp_path / "cli_reg_ws"
    (ws / ".agents" / "skills" / "NK-Orchestrator").mkdir(parents=True)
    (ws / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text("---\nname: NK-Orchestrator\ndomain_id: DOM-01\nversion: '1.0.0-Generation'\n---\n# Hub\n", encoding="utf-8")
    (ws / "scripts").mkdir(parents=True)
    (ws / "scripts" / "nk_registry_indexer.py").write_text('"""Idx.\n@domain_id: DOM-01\n"""\n', encoding="utf-8")

    stg = ws / ".staging"
    zip_p = tmp_path / "cli_out.zip"
    for argv_run in (
        ["--root", str(ws), "--stage-dir", str(stg), "--sync", "--json"],
        ["--root", str(ws), "--stage-dir", str(stg), "--sync"],
        ["--root", str(ws), "--stage-dir", str(stg), "--lookup", "DOM-01", "--json"],
        ["--root", str(ws), "--stage-dir", str(stg), "--lookup", "DOM-01"],
        ["--root", str(ws), "--stage-dir", str(stg), "--generate-tas-matrix", "--json"],
        ["--root", str(ws), "--stage-dir", str(stg), "--generate-tas-matrix"],
        ["--root", str(ws), "--stage-dir", str(stg), "--build-release-zip", str(zip_p), "--json"],
        ["--root", str(ws), "--stage-dir", str(stg), "--build-release-zip", str(zip_p)],
        ["--root", str(ws), "--stage-dir", str(stg), "--verify", "--json"],
        ["--root", str(ws), "--stage-dir", str(stg), "--verify"],
    ):
        assert indexer_mod.main(argv_run) == 0 and len(capsys.readouterr().out) > 0

    (ws / ".agents" / "skills" / "NK-Second").mkdir(parents=True)
    (ws / ".agents" / "skills" / "NK-Second" / "SKILL.md").write_text("---\nname: NK-Second\ndomain_id: DOM-02\n---\n# S2\n", encoding="utf-8")
    assert indexer_mod.main(["--root", str(ws), "--stage-dir", str(stg), "--sync"]) == 0
    capsys.readouterr()
    (ws / ".agents" / "skills" / "NK-Second" / "SKILL.md").unlink()
    assert indexer_mod.main(["--root", str(ws), "--stage-dir", str(stg), "--sync"]) == 1
    assert "ERR_REGISTRY_RATCHET_DOWN" in capsys.readouterr().out
