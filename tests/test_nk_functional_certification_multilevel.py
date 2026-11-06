# -*- coding: utf-8 -*-
"""
Suite di certificazione funzionale multilivello per Nexus Keystone v4.7.0-STE100-Unified.
Modulo: tests/test_nk_functional_certification_multilevel.py.
Valida i 15 invarianti ortogonali L1, L2 e L3 senza mock e senza parametrizzazioni.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, List

_THIS_FILE = Path(__file__).resolve()
_WORKSPACE_ROOT = _THIS_FILE.parent.parent
if _WORKSPACE_ROOT.name == ".staging":
    _WORKSPACE_ROOT = _WORKSPACE_ROOT.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def _resolve_staged_or_prod_path(rel_path: str) -> Path:
    """Risolve un percorso relativo dando priorita alla copia in .staging/."""
    staged = _WORKSPACE_ROOT / ".staging" / rel_path
    if staged.exists():
        return staged
    return _WORKSPACE_ROOT / rel_path


def _load_staged_or_prod(mod_name: str, rel_script: str) -> Any:
    """Carica dinamicamente il modulo dando priorita a .staging/scripts/."""
    target = _resolve_staged_or_prod_path(rel_script)
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_l1_01_zero_filesystem_relics_and_orphan_stashes() -> None:
    """Verifica assenza di file .bak, .wal e .patch orfani in nk_tracking/."""
    tracking_dir = _WORKSPACE_ROOT / "nk_tracking"
    assert tracking_dir.is_dir()

    relics: List[str] = []
    for item in tracking_dir.rglob("*"):
        if not item.is_file():
            continue
        name = item.name
        if (
            ".bak" in name
            or name.endswith("~")
            or name.endswith(".wal")
            or name.endswith(".wal_2pc.jsonl")
        ):
            relics.append(str(item.relative_to(_WORKSPACE_ROOT)))
    assert relics == [], f"Relitti rilevati in nk_tracking: {relics}"

    stashes_dir = tracking_dir / "handoff" / "stashes"
    if stashes_dir.exists():
        patches = list(stashes_dir.glob("*.patch"))
        assert patches == [], f"Patch orfani rilevati in stashes: {patches}"

    manifests_dir = tracking_dir / "manifests"
    assert manifests_dir.is_dir()

    pf_mod = _load_staged_or_prod(
        "preflight_cert_l1", "scripts/preflight_health_check.py"
    )
    checker = pf_mod.PreflightHealthChecker(workspace_root=_WORKSPACE_ROOT)
    report = checker.run_full_check(auto_fix=False)
    assert report["status"] in ("PASS", "HEALTHY_GREEN")
    assert len(report["issues_detected"]) == 0


def test_l1_02_scripts_and_tests_ast_sast_zero_violations() -> None:
    """Verifica che ASTGuardValidator rilevi zero violazioni SAST su scripts e tests."""
    ast_mod = _load_staged_or_prod(
        "ast_guard_cert_l1", "scripts/ast_guard_validator.py"
    )
    validator = ast_mod.ASTGuardValidator()
    scripts_target = _resolve_staged_or_prod_path("scripts")
    tests_target = _resolve_staged_or_prod_path("tests")

    for py_file in sorted(scripts_target.glob("*.py")):
        code = py_file.read_text(encoding="utf-8")
        violations = validator.check_sast_constructs(
            code, target_file=py_file.as_posix()
        )
        assert violations == [], f"Violazione SAST in {py_file.name}: {violations}"

    for py_file in sorted(tests_target.glob("*.py")):
        code = py_file.read_text(encoding="utf-8")
        violations = validator.check_sast_constructs(
            code, target_file=py_file.as_posix()
        )
        assert violations == [], f"Violazione SAST in {py_file.name}: {violations}"


def test_l1_03_registry_o1_manifest_and_sha256_integrity() -> None:
    """Verifica integrita del manifesto O(1) su 16 skill, 5 agenti e 34 script."""
    reg_mod = _load_staged_or_prod(
        "registry_indexer_cert_l1", "scripts/nk_registry_indexer.py"
    )
    indexer = reg_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT)
    manifest_path = _resolve_staged_or_prod_path(
        "nk_genome/nk_registry_manifest.json"
    )
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = manifest.get("summary", {})
    assert manifest.get("version") == "4.7.0-STE100-Unified"
    assert summary.get("total_skills") == 16
    assert summary.get("total_scripts") == 34
    assert summary.get("total_native_agents") == 5
    assert len(manifest.get("skills_index", {})) == 16
    assert len(manifest.get("native_agents_index", {})) == 5
    assert len(manifest.get("scripts_index", {})) == 34

    assert len(manifest.get("docs_and_setup_index", {})) >= 8
    assert indexer.resolve_library_path("install.ps1") == "nk_docs_and_setup/install.ps1"
    assert (
        indexer.resolve_library_path("GUIDA_INSTALLAZIONE.md")
        == "nk_docs_and_setup/GUIDA_INSTALLAZIONE.md"
    )
    assert indexer.resolve_library_path("PATCH_NOTES.md") == "nk_genome/PATCH_NOTES.md"

    ver_res = indexer.verify()
    assert ver_res["status"] == "VALID"
    assert ver_res["passed"] is True
    assert ver_res["issues"] == []
    ver_cached = indexer.verify()
    assert ver_cached["elapsed_ms"] < 30.0


def test_l1_04_skill_auxiliary_resources_and_references_exist() -> None:
    """Verifica che i 16 file ausiliari delle 16 skill esistano e siano linkati."""
    skills_root = _WORKSPACE_ROOT / ".agents" / "skills"
    assert skills_root.is_dir()

    skill_dirs = sorted(
        d for d in skills_root.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()
    )
    assert len(skill_dirs) == 16

    aux_files: List[Path] = []
    for sdir in skill_dirs:
        staged_skill_md = (
            _WORKSPACE_ROOT / ".staging" / ".agents" / "skills" / sdir.name / "SKILL.md"
        )
        skill_md = staged_skill_md if staged_skill_md.exists() else (sdir / "SKILL.md")
        skill_text = skill_md.read_text(encoding="utf-8")
        for sub_name in ("resources", "references", "scripts", "examples"):
            sub_dir = sdir / sub_name
            if sub_dir.is_dir():
                for fpath in sorted(sub_dir.rglob("*")):
                    if fpath.is_file():
                        aux_files.append(fpath)
                        assert fpath.name in skill_text, (
                            f"File ausiliario {fpath.name} non linkato in {sdir.name}/SKILL.md"
                        )

    assert len(aux_files) == 16


def test_l1_05_native_subagents_gt14_and_domain_mapping() -> None:
    """Verifica i 5 sub-agenti nativi e la guardia GT-14 sui permessi di scrittura."""
    agents_root = _WORKSPACE_ROOT / ".agents" / "agents"
    expected_write = {
        "NK-Specifier-Agent": "true",
        "NK-Builder-Agent": "true",
        "NK-Security-DAST-Auditor": "false",
        "NK-RSI-Auditor": "false",
        "NK-Scribe-Agent": "true",
    }
    for agent_name, exp_flag in expected_write.items():
        staged_md = (
            _WORKSPACE_ROOT
            / ".staging"
            / ".agents"
            / "agents"
            / agent_name
            / "agent.md"
        )
        agent_md = (
            staged_md
            if staged_md.exists()
            else (agents_root / agent_name / "agent.md")
        )
        assert agent_md.is_file(), f"File mancante per {agent_name}"
        content = agent_md.read_text(encoding="utf-8")
        assert f"enable_write_tools: {exp_flag}" in content
        assert "enable_subagent_tools: false" in content


def test_l2_06_tetralogy_4of4_and_idea_canvas_completeness() -> None:
    """Verifica esistenza e completezza della Tetralogia Sovrana 4/4 e di idea_canvas.md."""
    genome_files = (
        "nk_genome/idea_canvas.md",
        "nk_genome/concept_map.md",
        "nk_genome/structural_tree.md",
        "nk_genome/implementation_plan.md",
        "nk_genome/repo_map.md",
    )
    for rel_file in genome_files:
        target = _resolve_staged_or_prod_path(rel_file)
        assert target.is_file(), f"File del genoma mancante: {rel_file}"
        text = target.read_text(encoding="utf-8").strip()
        assert len(text) > 500, f"File del genoma troppo corto: {rel_file}"


def test_l2_07_structural_tree_test_files_1to1_truthfulness() -> None:
    """Verifica allineamento 1:1 dei file di test citati in structural_tree.md."""
    st_path = _resolve_staged_or_prod_path("nk_genome/structural_tree.md")
    st_text = st_path.read_text(encoding="utf-8")

    assert "test_holistic_sanitation_v45.py" not in st_text
    required_tests = (
        "test_v460_competitive_integration_suite.py",
        "test_core_platform_utilities.py",
        "test_v470_holistic_stress_suite.py",
        "test_intrinsic_vibe_sandbox_stress.py",
        "test_nk_functional_certification_multilevel.py",
    )
    for req_test in required_tests:
        assert req_test in st_text, f"File {req_test} mancante in structural_tree.md"
        test_disk = _resolve_staged_or_prod_path(f"tests/{req_test}")
        assert test_disk.is_file(), f"File {req_test} non presente su disco"


def test_l2_08_patch_notes_ssot_and_version_parity() -> None:
    """Verifica che nk_genome/PATCH_NOTES.md non sia vuoto e contenga l'header di versione corrente."""
    ssot_path = _resolve_staged_or_prod_path("nk_genome/PATCH_NOTES.md")
    assert ssot_path.is_file()

    ssot_bytes = ssot_path.read_bytes()
    assert len(ssot_bytes) > 0
    ssot_text = ssot_bytes.decode("utf-8")
    assert ssot_text.strip().startswith("#")
    assert "v4.7.0-STE100-Unified" in ssot_text
    assert "NK-MS-20261031-HOLISTIC-STRESS-AND-TEST-CONSOLIDATION-v4.7.0-RSI" in ssot_text


def test_l2_09_quality_baseline_and_test_count_alignment() -> None:
    """Verifica che quality_baseline.json riporti 245 test con pass rate 100.0%."""
    qb_path = _resolve_staged_or_prod_path("nk_tracking/quality_baseline.json")
    data = json.loads(qb_path.read_text(encoding="utf-8"))
    assert data.get("_version") == "4.7.0-STE100-Unified"
    assert data.get("total_golden_tests") == 245

    metrics = data.get("metrics", {})
    assert metrics["total_golden_tests"]["value"] == 245
    assert metrics["unit_tests_total"]["value"] == 245
    assert metrics["unit_tests_passed"]["value"] == 245
    assert float(metrics["unit_tests_pass_pct"]["value"]) == 100.0
    assert metrics["skills_audited"]["value"] == 16
    assert metrics["crv_macro_phases"]["value"] == 4

    qbm_mod = _load_staged_or_prod(
        "qbm_cert_l2", "scripts/quality_baseline_manager.py"
    )
    assert qbm_mod.CONSTITUTIONAL_GOLDEN_FLOOR == 68
    ver = qbm_mod.check_baseline_compliance(
        str(qb_path),
        {"unit_tests_pass_pct": 100.0, "total_golden_tests": 245},
    )
    assert ver["verdict"] == "PASS"
    assert ver["regressions"] == []


def test_l2_10_ci_workflow_and_installers_alignment() -> None:
    """Verifica allineamento di .github/workflows/ci.yml, install.ps1, install.sh e workspace."""
    ci_path = _resolve_staged_or_prod_path(".github/workflows/ci.yml")
    assert ci_path.is_file()
    ci_text = ci_path.read_text(encoding="utf-8")
    assert "preflight_health_check.py --check-only" in ci_text
    assert "245 Golden & Stress Tests" in ci_text
    assert "nk_docs_and_setup/requirements.txt" in ci_text

    ps1_path = _resolve_staged_or_prod_path("nk_docs_and_setup/install.ps1")
    sh_path = _resolve_staged_or_prod_path("nk_docs_and_setup/install.sh")
    ws_path = _resolve_staged_or_prod_path("nk_docs_and_setup/Antigravity.code-workspace")
    assert ps1_path.is_file()
    assert sh_path.is_file()
    assert ws_path.is_file()

    ps1_text = ps1_path.read_text(encoding="utf-8")
    sh_text = sh_path.read_text(encoding="utf-8")
    ws_text = ws_path.read_text(encoding="utf-8")
    assert "nk_docs_and_setup/requirements.txt" in ps1_text and "245" in ps1_text
    assert "nk_docs_and_setup/requirements.txt" in sh_text and "245" in sh_text
    assert "NK_Hub" in ws_text and "NK_External_Projects" in ws_text

    for dup_root_file in ("install.ps1", "install.sh", "requirements.txt", "PATCH_NOTES.md"):
        assert not (_WORKSPACE_ROOT / dup_root_file).exists()


def test_l3_11_vibe_sprint_router_modes_and_l0_gate_contract() -> None:
    """Verifica classificazione Mode A/B/C/D e contratto L0 in VibeSprintRouter."""
    router_mod = _load_staged_or_prod(
        "vibe_router_cert_l3", "scripts/vibe_sprint_router.py"
    )
    router = router_mod.VibeSprintRouter(workspace_root=_WORKSPACE_ROOT)

    res_d = router.classify_prompt_intent("Esegui audit e benchmark copertura bandi")
    assert res_d["recommended_mode"] == "mode_d"

    res_a = router.classify_prompt_intent(
        "Allinea 1:1 la Tetralogia al Turno 4 con refactoring multi-file e Cold Review a 6 Gate"
    )
    assert res_a["recommended_mode"] == "mode_a"

    res_b = router.classify_prompt_intent(
        "Esegui diagnosi causa radice RCA con SBFL Ochiai sul bug"
    )
    assert res_b["recommended_mode"] == "mode_b"

    env = router.build_meta_prompt_envelope(
        "Implementa e verifica il modulo fino a convergenza ottimale RSI"
    )
    assert env["fsm_state"] == "AWAIT_CONFIRM"
    assert len(env["intent_hash_sha256"]) == 64
    assert "INTRINSIC_GOAL" in env["intrinsic_protocols"]

    t12_prompt = (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n"
        "### 1. Identità e Percorsi Operativi\n"
        "- Modalità Ricezione: STANDBY\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )
    env_t12 = router.build_meta_prompt_envelope(t12_prompt)
    assert env_t12["fsm_state"] == "BYPASSED"
    assert env_t12.get("bypass_reason") == "STATE_HANDOFF_STANDBY"
    assert env_t12.get("standby_mode") is True
    assert env_t12["intrinsic_protocols"] == []
    assert env_t12["autonomous_slash_equivalence"]["goal"] is False
    assert env_t12["autonomous_slash_equivalence"]["plan"] is False


def test_l3_12_rsi_convergence_ste100_and_code_profiles_optimal() -> None:
    """Verifica convergenza ottimale RSI e conformita STE100 di repo_map.md."""
    rsi_mod = _load_staged_or_prod(
        "rsi_engine_cert_l3", "scripts/rsi_convergence_engine.py"
    )
    repo_map_path = _resolve_staged_or_prod_path("nk_genome/repo_map.md")
    ste_res = rsi_mod.verify_ste100_compliance(
        repo_map_path.read_text(encoding="utf-8")
    )
    assert ste_res["passed"] is True
    assert ste_res["violations_count"] == 0

    defects = rsi_mod.RSIDefectVector(
        sast_critical=0,
        tests_failed=0,
        tests_passed=245,
        tests_total=245,
    )
    for profile_name in ("code_rsi", "spec_rsi", "ste100_rsi"):
        delta_k = rsi_mod.RSIConvergenceEngine.compute_delta(
            defects, profile=profile_name
        )
        fitness_q = rsi_mod.RSIConvergenceEngine.compute_fitness(
            defects, delta_k=delta_k, profile=profile_name
        )
        assert delta_k == 0
        assert fitness_q == 100.0
        assert (
            rsi_mod.RSIConvergenceEngine.is_converged(defects, profile=profile_name)
            is True
        )


def test_l3_13_hook_gate_and_transcript_prompt_linter_ap1_to_ap10(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica nk_hook_gate.py e il linter AP-1..AP-10 in nk_transcript_tools.py."""
    hook_mod = _load_staged_or_prod("hook_gate_cert_l3", "scripts/nk_hook_gate.py")
    tt_mod = _load_staged_or_prod(
        "transcript_tools_cert_l3", "scripts/nk_transcript_tools.py"
    )

    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    rc_probe = hook_mod.main(
        ["probe", "--event", "SessionStart", "--conversation-id", "cert_l3_conv"]
    )
    assert rc_probe == 0

    clean_prompt = (
        "Esegui python -m pytest tests/ in G:/Il mio Drive/Antigravity/.staging/ "
        "con protocolli INTRINSIC_GOAL e INTRINSIC_PLAN attivi."
    )
    res_clean, code_clean = tt_mod.lint_prompt_text(clean_prompt)
    assert code_clean == 0
    assert res_clean["passed"] is True
    assert res_clean["violations_count"] == 0

    bad_prompt = (
        "Digita manualmente /goal oppure /plan per avviare il flusso e usa python -c 'import os'."
    )
    res_bad, code_bad = tt_mod.lint_prompt_text(bad_prompt)
    assert code_bad == 1
    assert res_bad["passed"] is False
    codes = {v["code"] for v in res_bad["violations"]}
    assert "AP-10" in codes

    handoff_mod = _load_staged_or_prod(
        "handoff_cert_l3", "scripts/nk_session_handoff.py"
    )
    t12_clean = handoff_mod.compile_template_12_state_handoff(
        project_root=str(_WORKSPACE_ROOT)
    )
    res_t12_ok, code_t12_ok = tt_mod.lint_prompt_text(t12_clean, mode="state-handoff")
    assert code_t12_ok == 0
    assert res_t12_ok["passed"] is True
    assert res_t12_ok["violations_count"] == 0

    t12_contaminated = (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n"
        "Esegui INTRINSIC_GOAL e invoca ask_question autonomo.\n"
        "Pista 1A: Modulo Bandi. Seleziona quale pista avviare.\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )
    res_t12_bad, code_t12_bad = tt_mod.lint_prompt_text(
        t12_contaminated, mode="state-handoff"
    )
    assert code_t12_bad == 1
    assert res_t12_bad["passed"] is False
    t12_codes = {v["code"] for v in res_t12_bad["violations"]}
    assert "AP-12" in t12_codes
    assert "AP-13" in t12_codes


def test_l3_14_memory_3tier_and_deterministic_cache_contracts(
    tmp_path: Path,
) -> None:
    """Verifica Memory3TierEngine sui 4 alias e DeterministicApiCache in SQLite WAL."""
    mem_mod = _load_staged_or_prod(
        "mem_3tier_cert_l3", "scripts/memory_3tier_engine.py"
    )
    cache_mod = _load_staged_or_prod(
        "api_cache_cert_l3", "scripts/deterministic_api_cache.py"
    )

    assert mem_mod.TIER1_TOKEN_CAP == 350
    assert mem_mod.TIER1_TOKEN_CAP_ARGON == 1200
    for alias in ("ARCH", "SEC", "OPS", "DEVX"):
        resolved = mem_mod.resolve_domain(alias)
        assert resolved in mem_mod.NK_DOMAINS

    mem_engine = mem_mod.ThreeTierMemoryEngine(
        base_dir=tmp_path / "mem_store",
        cache_dir=tmp_path / "mem_cache",
        profile="argon",
    )
    ep = mem_mod.MemoryEpisode(
        episode_id="EP-CERT-243",
        domain="ARCH",
        title="Certificazione v4.7.0",
        content="Verifica persistenza episodica Zero-Mock sul dominio ARCH.",
        tags=["v452", "cert"],
    )
    mem_engine.append_episode(ep)
    recalled = mem_engine.recall_hybrid("ARCH", "Certificazione v4.7.0", top_k=3)
    assert len(recalled) == 1
    assert recalled[0][0].episode_id == "EP-CERT-243"

    with cache_mod.DeterministicApiCache(db_path=tmp_path / "api_wal.db") as api_cache:
        h = api_cache.set(
            endpoint="https://example.org/api/v1/status",
            status_code=200,
            response_body='{"ok": true}',
        )
        assert len(h) == 64
        cached_hit = api_cache.get("https://example.org/api/v1/status")
        assert cached_hit is not None
        assert cached_hit[0] == 200
        assert cached_hit[1] == '{"ok": true}'


def test_l3_15_session_bootstrap_fast_stat_under_120ms() -> None:
    """Verifica che NKSessionBootstrap completi il controllo Fast-Stat con esito PASS."""
    boot_mod = _load_staged_or_prod(
        "bootstrap_cert_l3", "scripts/nk_session_bootstrap.py"
    )
    boot = boot_mod.NKSessionBootstrap(workspace_root=_WORKSPACE_ROOT)
    first_res = boot.run_bootstrap(fast_stat=True)
    assert first_res["status"] == "PASS"

    second_res = boot.run_bootstrap(fast_stat=True)
    assert second_res["status"] == "PASS"
    assert float(second_res.get("duration_ms", 0.0)) < 120.0


def test_all_scripts_compile_and_expose_valid_ast() -> None:
    """Verifica che tutti i 34 script in scripts/ compilino con AST valido e appartengano a DOMAIN_TAXONOMY."""
    reg_mod = _load_staged_or_prod(
        "registry_indexer_ast_cert", "scripts/nk_registry_indexer.py"
    )
    taxonomy_scripts = set()
    for dom_meta in reg_mod.DOMAIN_TAXONOMY.values():
        taxonomy_scripts.update(dom_meta.get("scripts", []))

    indexer = reg_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT)
    scripts_index = indexer.scan_scripts()
    assert len(scripts_index) == 34
    assert set(scripts_index.keys()) == taxonomy_scripts

    for script_name in sorted(scripts_index.keys()):
        script_path = _resolve_staged_or_prod_path(f"scripts/{script_name}")
        assert script_path.is_file(), f"Script mancante: {script_name}"
        source = script_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(script_path))
        assert isinstance(tree, ast.Module)
        assert len(tree.body) > 0


def test_win32_2pc_engine_transactional_integrity(tmp_path: Path) -> None:
    """Verifica l'integrita transazionale 2PC di promote_staging_to_production su tmp_path."""
    w2pc_mod = _load_staged_or_prod(
        "win32_2pc_cert_l3", "scripts/win32_2pc_engine.py"
    )
    repo_dir = tmp_path / "mini_repo"
    stg_dir = repo_dir / ".staging"
    (stg_dir / "nk_genome").mkdir(parents=True, exist_ok=True)
    (repo_dir / "nk_genome").mkdir(parents=True, exist_ok=True)
    (repo_dir / "nk_tracking").mkdir(parents=True, exist_ok=True)

    target_doc = stg_dir / "nk_genome" / "idea_canvas.md"
    target_doc.write_text("# Idea Canvas Transactional Test\n", encoding="utf-8")

    res = w2pc_mod.promote_staging_to_production(
        repo_root=str(repo_dir),
        verify_baseline=False,
    )
    assert res.get("status") in ("SUCCESS", "COMMITTED", "PASS") or len(res.get("committed", [])) >= 1
    promoted_file = repo_dir / "nk_genome" / "idea_canvas.md"
    assert promoted_file.is_file()
    assert "Transactional Test" in promoted_file.read_text(encoding="utf-8")
