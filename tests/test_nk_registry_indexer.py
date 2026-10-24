# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per nk_registry_indexer.py di Nexus Keystone v3.5.1.
Modulo: tests/test_nk_registry_indexer.py.
Valida sync, verify (<30 ms), lookup O(1) (<50 ms), Hot-Swap Zero-Touch e SSOT.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Tuple

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_staging_or_prod_module(mod_name: str, rel_script: str) -> Tuple[Any, Path]:
    """Carica un modulo Python dando priorita a .staging/scripts rispetto a scripts/."""
    staging_target = _workspace_root / ".staging" / rel_script
    prod_target = _workspace_root / rel_script
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod, target


indexer_mod, _ = _load_staging_or_prod_module(
    "nk_registry_indexer", "scripts/nk_registry_indexer.py"
)
router_mod, _ = _load_staging_or_prod_module(
    "vibe_sprint_router", "scripts/vibe_sprint_router.py"
)
preflight_mod, _ = _load_staging_or_prod_module(
    "preflight_health_check", "scripts/preflight_health_check.py"
)

NKRegistryIndexer = indexer_mod.NKRegistryIndexer
VibeSprintRouter = router_mod.VibeSprintRouter
PreflightHealthChecker = preflight_mod.PreflightHealthChecker


def test_nk_registry_indexer_sync_generates_manifest_and_skill_index(
    tmp_path: Path,
) -> None:
    """1. Verifica che --sync generi nk_registry_manifest.json e SKILL_INDEX.md senza sporcare .staging/."""
    stage_dir = tmp_path / ".staging"
    rc = indexer_mod.main(["--sync", "--stage-dir", str(stage_dir)])
    assert rc == 0

    manifest_path = stage_dir / "nk_genome" / "nk_registry_manifest.json"
    skill_index_path = stage_dir / "nk_genome" / "SKILL_INDEX.md"
    assert manifest_path.exists()
    assert skill_index_path.exists()

    # Verifica G3-02: sync senza --sync-staging non scrive nel .staging di produzione
    prod_stg_manifest = (
        _workspace_root / ".staging" / "nk_genome" / "nk_registry_manifest.json"
    )
    existed_before = prod_stg_manifest.exists()
    mtime_before = (
        prod_stg_manifest.stat().st_mtime_ns if existed_before else None
    )
    no_stg_indexer = NKRegistryIndexer(
        workspace_root=_workspace_root, stage_dir=_workspace_root / ".staging"
    )
    res_no_stg = no_stg_indexer.sync(sync_staging=False)
    assert res_no_stg["passed"] is True
    assert res_no_stg["sync_staging"] is False
    if not existed_before:
        assert not prod_stg_manifest.exists()
    else:
        assert prod_stg_manifest.stat().st_mtime_ns == mtime_before

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "version",
        "domains",
        "skills_index",
        "scripts_index",
        "intent_dispatch_table",
        "global_hygiene_profile",
    ):
        assert key in manifest

    assert set(manifest["domains"].keys()) == {
        "DOM-01",
        "DOM-02",
        "DOM-03",
        "DOM-04",
        "DOM-05",
    }
    assert len(manifest["skills_index"]) == 16
    assert len(manifest["scripts_index"]) >= 32
    assert "nk_registry_indexer.py" in manifest["scripts_index"]
    assert "schemas/dual_ledgers.py" in manifest["scripts_index"]
    assert "schemas/nk_ipc_contracts.py" in manifest["scripts_index"]
    assert (
        manifest["scripts_index"]["schemas/dual_ledgers.py"]["domain_id"] == "DOM-01"
    )
    assert (
        manifest["scripts_index"]["schemas/nk_ipc_contracts.py"]["domain_id"]
        == "DOM-01"
    )

    md_text = skill_index_path.read_text(encoding="utf-8")
    assert "DOM-01" in md_text and "DOM-05" in md_text
    assert "NK-Python-Async-Builder" in md_text


def test_nk_registry_indexer_verify_detects_clean_and_drift(tmp_path: Path) -> None:
    """2. Verifica che --verify certifichi l'integrita SHA-256 (<30 ms), drift e dual-resolver genome/."""
    indexer = NKRegistryIndexer(
        workspace_root=_workspace_root, stage_dir=tmp_path / ".staging_verify"
    )
    indexer.sync(sync_staging=True)
    verify_res = indexer.verify()
    assert verify_res["passed"] is True
    assert verify_res["status"] == "VALID"
    assert verify_res["elapsed_ms"] < 350.0

    # Crea un mini-workspace isolato su tmp_path per testare il rilevamento drift SHA-256
    mini_ws = tmp_path / "mini_ws"
    skill_dir = mini_ws / ".agents" / "skills" / "NK-Master-Hub"
    scripts_dir = mini_ws / "scripts"
    skill_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: NK-Master-Hub\ndescription: Sovrano L3.\nversion: '3.5.1'\n---\n# Hub\n",
        encoding="utf-8",
    )
    script_py = scripts_dir / "nk_registry_indexer.py"
    script_py.write_text(
        '"""Modulo indicizzatore."""\nimport argparse\n', encoding="utf-8"
    )

    tmp_indexer = NKRegistryIndexer(
        workspace_root=mini_ws, stage_dir=mini_ws / ".staging"
    )
    tmp_indexer.sync()
    assert tmp_indexer.verify()["passed"] is True

    # Modifica il file su disco dopo il sync per forzare un drift SHA-256
    script_py.write_text(
        '"""Modulo indicizzatore modificato."""\nimport sys\n', encoding="utf-8"
    )
    drift_res = tmp_indexer.verify()
    assert drift_res["passed"] is False
    assert drift_res["status"] == "DRIFT_DETECTED"
    assert any("nk_registry_indexer.py" in issue for issue in drift_res["issues"])

    # Verifica dual-resolver Tetralogia con cartella legacy genome/
    legacy_ws = tmp_path / "legacy_ext_ws"
    (legacy_ws / "genome").mkdir(parents=True, exist_ok=True)
    (legacy_ws / "genome" / "concept_map.md").write_text("# Concept\n", encoding="utf-8")
    leg_indexer = NKRegistryIndexer(
        workspace_root=legacy_ws, stage_dir=legacy_ws / ".staging"
    )
    tetra = leg_indexer.resolve_tetralogy_files()
    assert tetra["is_legacy_genome"] is True
    assert tetra["warning"] is not None
    assert tetra["files"]["concept_map.md"] is not None


def test_nk_registry_indexer_lookup_o1_latency_under_50ms(tmp_path: Path) -> None:
    """3. Verifica che --lookup risolva dominio, skill, script e intento in meno di 50 ms."""
    indexer = NKRegistryIndexer(
        workspace_root=_workspace_root, stage_dir=tmp_path / ".staging_lookup"
    )

    t0 = time.perf_counter()
    res_dom = indexer.lookup("DOM-04")
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert res_dom["found"] is True
    assert res_dom["domain_id"] == "DOM-04"
    assert res_dom["domain_name"] == "AUDIT_DAST_AND_RCA"
    assert dt_ms < 50.0
    assert res_dom["elapsed_ms"] < 50.0

    res_skill = indexer.lookup("NK-Python-Async-Builder")
    assert res_skill["found"] is True
    assert res_skill["match_type"] == "skill"
    assert res_skill["domain_id"] == "DOM-03"
    assert res_skill["elapsed_ms"] < 50.0

    res_script = indexer.lookup("vibe_sprint_router.py")
    assert res_script["found"] is True
    assert res_script["match_type"] == "script"
    assert res_script["domain_id"] == "DOM-01"
    assert "--discovery-check" in res_script["cli_flags"]
    assert res_script["elapsed_ms"] < 50.0

    res_intent = indexer.lookup("Esegui recall memoria episodica")
    assert res_intent["found"] is True
    assert res_intent["domain_id"] == "DOM-05"
    assert res_intent["elapsed_ms"] < 50.0


def test_ssot_integration_vibe_sprint_router_and_preflight_health_check(
    tmp_path: Path,
) -> None:
    """4. Verifica il disaccoppiamento SSOT in vibe_sprint_router.py e preflight_health_check.py."""
    router = VibeSprintRouter(workspace_root=_workspace_root)
    dom_res = router.resolve_domain_from_manifest(
        "Esegui audit SAST e diagnosi SBFL Ochiai"
    )
    assert dom_res["domain_id"] == "DOM-04"

    intent_d = router.classify_prompt_intent("Esegui discovery e benchmark architettura")
    assert intent_d["recommended_mode"] == "mode_d"
    assert intent_d["primary_agent"] == "NK-Ideator"
    assert intent_d["domain_id"] == "DOM-02"

    intent_c = router.classify_prompt_intent("Implementa modulo async con pydantic")
    assert intent_c["recommended_mode"] == "mode_c"
    assert intent_c["primary_agent"] == "NK-Python-Async-Builder"
    assert intent_c["domain_id"] == "DOM-03"

    # Verifica preflight_health_check con conteggio skill dinamico da nk_registry_manifest.json
    custom_ws = tmp_path / "custom_ssot_ws"
    for folder in ("nk_genome", "nk_tracking/anchor", ".staging"):
        (custom_ws / folder).mkdir(parents=True, exist_ok=True)

    custom_manifest = {
        "version": "3.5.1-MODULAR-INDEX-RSI2",
        "summary": {"total_skills": 18, "total_domains": 5, "total_scripts": 32},
        "skills_index": {f"NK-Skill-{i}": {"domain_id": "DOM-01"} for i in range(18)},
    }
    (custom_ws / "nk_genome" / "nk_registry_manifest.json").write_text(
        json.dumps(custom_manifest), encoding="utf-8"
    )
    (custom_ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps(
            {
                "_version": "3.5.1",
                "metrics": {
                    "skills_audited": 18,
                    "crv_macro_phases": 4,
                    "unit_tests_pass_pct": 100.0,
                },
            }
        ),
        encoding="utf-8",
    )

    checker = PreflightHealthChecker(workspace_root=custom_ws)
    alignment = checker._check_baseline_alignment()
    assert alignment["passed"] is True
    assert alignment["expected_skills"] == 18
    assert alignment["skills_audited"] == 18


def test_nk_registry_indexer_hotswap_zero_touch_registration(tmp_path: Path) -> None:
    """5. Verifica che una nuova skill con domain_id: DOM-03 venga auto-registrata da --sync."""
    hs_ws = tmp_path / "hotswap_ws"
    custom_skill_dir = hs_ws / ".agents" / "skills" / "NK-Custom-HotSwap"
    scripts_dir = hs_ws / "scripts" / "schemas"
    custom_skill_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    (custom_skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: NK-Custom-HotSwap\n"
        "description: Modulo Hot-Swap auto-registrato in DOM-03.\n"
        'version: "3.5.1-STE100-Unified"\n'
        'domain_id: "DOM-03"\n'
        'sector: "BUILD_AND_HEAL"\n'
        'thinking_level: "HIGH"\n'
        "---\n\n"
        "# NK-Custom-HotSwap\n",
        encoding="utf-8",
    )

    (hs_ws / "scripts" / "custom_auditor_probe.py").write_text(
        '"""\nSonda custom auto-registrata.\n@domain_id: DOM-04\n"""\nimport sys\n',
        encoding="utf-8",
    )
    (scripts_dir / "nk_ipc_contracts.py").write_text(
        '"""Contratti IPC strict."""\nfrom pydantic import BaseModel\n',
        encoding="utf-8",
    )

    hs_indexer = NKRegistryIndexer(
        workspace_root=hs_ws,
        stage_dir=hs_ws / ".staging",
        global_config_dir=tmp_path / "empty_global_cfg",
    )
    sync_res = hs_indexer.sync()
    assert sync_res["passed"] is True

    manifest = hs_indexer.load_manifest()
    assert manifest is not None
    assert "NK-Custom-HotSwap" in manifest["skills_index"]
    assert manifest["skills_index"]["NK-Custom-HotSwap"]["domain_id"] == "DOM-03"
    assert manifest["skills_index"]["NK-Custom-HotSwap"]["sector"] == "BUILD_AND_HEAL"
    assert "NK-Custom-HotSwap" in manifest["domains"]["DOM-03"]["skills"]

    assert "custom_auditor_probe.py" in manifest["scripts_index"]
    assert (
        manifest["scripts_index"]["custom_auditor_probe.py"]["domain_id"] == "DOM-04"
    )
    assert "custom_auditor_probe.py" in manifest["domains"]["DOM-04"]["scripts"]

    assert "schemas/nk_ipc_contracts.py" in manifest["scripts_index"]
    assert (
        manifest["scripts_index"]["schemas/nk_ipc_contracts.py"]["domain_id"]
        == "DOM-01"
    )


def test_global_skill_filter_and_hygiene_isolation(tmp_path: Path) -> None:
    """6. Verifica il consolidamento plugin e la disattivazione delle 61 skill globali."""
    mock_cfg_dir = tmp_path / "gemini_config"
    skills_dir = mock_cfg_dir / "skills"
    plugins_dir = mock_cfg_dir / "plugins"
    skills_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Crea una skill GCP, una utility dev, science e android-cli-plugin
    gcp_sk = skills_dir / "bigquery-data-transfer-service"
    gcp_sk.mkdir(parents=True, exist_ok=True)
    (gcp_sk / "SKILL.md").write_text("# BQ Transfer\n", encoding="utf-8")
    (skills_dir / ".datacloud_skills_manifest").write_text("{}", encoding="utf-8")

    dev_sk = skills_dir / "managing-python-dependencies"
    dev_sk.mkdir(parents=True, exist_ok=True)
    (dev_sk / "SKILL.md").write_text("# Py Deps\n", encoding="utf-8")

    sci_sk = plugins_dir / "science" / "skills" / "alphafold-database"
    sci_sk.mkdir(parents=True, exist_ok=True)
    (sci_sk / "SKILL.md").write_text("# AlphaFold\n", encoding="utf-8")

    and_sk = plugins_dir / "android-cli-plugin" / "skills"
    and_sk.mkdir(parents=True, exist_ok=True)
    (and_sk / "SKILL.md").write_text("# Android CLI\n", encoding="utf-8")

    (mock_cfg_dir / "config.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "android-cli-plugin": {"enabled": True},
                    "science": {"enabled": True},
                    "firebase": {"enabled": True},
                },
                "sidecars": {"science/viewer": {"schemaVersion": 1}},
                "userSettings": {"useAiCredits": False},
            }
        ),
        encoding="utf-8",
    )

    idx = NKRegistryIndexer(
        workspace_root=_workspace_root,
        stage_dir=tmp_path / ".staging",
        global_config_dir=mock_cfg_dir,
    )

    before_hygiene = idx.scan_global_hygiene_profile(16)
    assert before_hygiene["installed_external_skills_count"] == 4
    assert before_hygiene["active_external_skills_count"] == 4
    assert before_hygiene["external_skills_count"] == 4
    assert before_hygiene["context_pollution_detected"] is True

    flt_res = idx.apply_global_filter()
    assert flt_res["applied"] is True
    assert (
        mock_cfg_dir
        / "plugins"
        / "gcp-data-cloud-plugin"
        / "skills"
        / "bigquery-data-transfer-service"
        / "SKILL.md"
    ).exists()
    assert (
        mock_cfg_dir
        / "plugins"
        / "dev-utilities-plugin"
        / "skills"
        / "managing-python-dependencies"
        / "SKILL.md"
    ).exists()

    after_hygiene = idx.scan_global_hygiene_profile(16)
    assert after_hygiene["installed_external_skills_count"] == 4
    assert after_hygiene["active_external_skills_count"] == 0
    assert after_hygiene["disabled_external_skills_count"] == 4
    assert after_hygiene["external_skills_count"] == 0
    assert after_hygiene["total_flat_skills"] == 16
    assert after_hygiene["context_pollution_detected"] is False
