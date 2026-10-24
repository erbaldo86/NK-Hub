# -*- coding: utf-8 -*-
"""
Suite permanente di 7 Golden Test Zero-Mock per l'integrita olistica dell'ambiente Nexus Keystone v4.5.0.
Modulo: tests/test_holistic_environment_integrity.py.
Verifica la copertura tassonomica dei 34 script, il flag --json in preflight_health_check.py,
l'assenza di file .bak* in nk_tracking/, la parita di PATCH_NOTES.md, la guida bilingue,
la guardia GT-14 sugli Auditor e i 4 marker costituzionali epistemici su agent.md, SKILL.md e regole.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Set

_THIS_FILE = Path(__file__).resolve()
_WORKSPACE_ROOT = _THIS_FILE.parent.parent
if _WORKSPACE_ROOT.name == ".staging":
    _WORKSPACE_ROOT = _WORKSPACE_ROOT.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def _resolve_staged_or_prod_path(rel_path: str) -> Path:
    """Risolve un percorso relativo dando priorita a .staging/ rispetto alla root."""
    stg_cand = _WORKSPACE_ROOT / ".staging" / rel_path
    if stg_cand.exists():
        return stg_cand
    return _WORKSPACE_ROOT / rel_path


def _load_staged_or_prod_mod(mod_name: str, rel_script: str) -> Any:
    """Carica dinamicamente un modulo Python dando priorita a .staging/scripts/."""
    target = _resolve_staged_or_prod_path(rel_script)
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_01_all_34_indexed_scripts_belong_to_domain_taxonomy() -> None:
    """1. Verifica che tutti i 34 script indicizzati appartengano a DOMAIN_TAXONOMY."""
    indexer_mod = _load_staged_or_prod_mod(
        "nk_registry_indexer_holistic", "scripts/nk_registry_indexer.py"
    )
    taxonomy_scripts: Set[str] = set()
    for dom_meta in indexer_mod.DOMAIN_TAXONOMY.values():
        taxonomy_scripts.update(dom_meta.get("scripts", []))

    indexer = indexer_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT)
    scripts_index = indexer.scan_scripts()

    assert len(scripts_index) == 34, (
        f"Attesi 34 script indicizzati, trovati {len(scripts_index)}: {sorted(scripts_index.keys())}"
    )
    missing_from_taxonomy = set(scripts_index.keys()) - taxonomy_scripts
    assert not missing_from_taxonomy, (
        f"Script non mappati in DOMAIN_TAXONOMY: {sorted(missing_from_taxonomy)}"
    )
    assert len(taxonomy_scripts) == 34


def test_02_preflight_health_check_check_only_json_cli() -> None:
    """2. Verifica che preflight_health_check.py --check-only --json restituisca exit 0 e JSON valido."""
    script_path = _resolve_staged_or_prod_path("scripts/preflight_health_check.py")
    proc = subprocess.run(
        [sys.executable, str(script_path), "--check-only", "--json"],
        cwd=str(_WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert proc.returncode == 0, f"preflight_health_check fallito: {proc.stderr}\n{proc.stdout}"
    payload = json.loads(proc.stdout.strip())
    assert isinstance(payload, dict)
    assert payload.get("status") in ("PASS", "HEALTHY_GREEN")
    assert payload.get("auto_fix") is False


def test_03_no_backup_relic_files_in_nk_tracking() -> None:
    """3. Verifica l'assenza totale di file .bak* dentro nk_tracking/."""
    tracking_dir = _WORKSPACE_ROOT / "nk_tracking"
    assert tracking_dir.is_dir()
    bak_files = [
        p.relative_to(_WORKSPACE_ROOT).as_posix()
        for p in tracking_dir.rglob("*")
        if p.is_file() and (".bak" in p.name.lower() or p.name.lower().endswith("~"))
    ]
    assert not bak_files, f"Rilevati file relitto .bak* in nk_tracking/: {bak_files}"


def test_04_patch_notes_byte_for_byte_ssot_parity() -> None:
    """4. Verifica la parita byte-per-byte tra nk_genome/PATCH_NOTES.md e PATCH_NOTES.md."""
    genome_pn = _resolve_staged_or_prod_path("nk_genome/PATCH_NOTES.md")
    root_pn = _resolve_staged_or_prod_path("PATCH_NOTES.md")
    assert genome_pn.is_file(), f"File mancante: {genome_pn}"
    assert root_pn.is_file(), f"File mancante: {root_pn}"
    assert genome_pn.read_bytes() == root_pn.read_bytes(), (
        "Disallineamento SSOT rilevato tra nk_genome/PATCH_NOTES.md e PATCH_NOTES.md"
    )


def test_05_installation_guide_bilingual_it_and_en() -> None:
    """5. Verifica la presenza bilingue (Italiano + Inglese) in GUIDA_INSTALLAZIONE.md."""
    guide_path = _resolve_staged_or_prod_path("GUIDA_INSTALLAZIONE.md")
    assert guide_path.is_file(), f"GUIDA_INSTALLAZIONE.md non trovato: {guide_path}"
    text = guide_path.read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    assert "guida di installazione" in low or "requisiti di sistema" in low or "italiano" in low
    assert (
        "english" in low
        or "installation guide" in low
        or "system requirements" in low
        or "quick start" in low
    ), "Sezione English mancante in GUIDA_INSTALLAZIONE.md"


def test_06_gt14_auditors_read_only_and_run_command_capability() -> None:
    """6. Verifica la guardia GT-14 (enable_write_tools: false e run_command) sui 2 Auditor nativi."""
    auditors = ("NK-Security-DAST-Auditor", "NK-RSI-Auditor")
    for aud_name in auditors:
        ag_file = _resolve_staged_or_prod_path(f".agents/agents/{aud_name}/agent.md")
        assert ag_file.is_file(), f"File agent.md mancante per {aud_name}"
        content = ag_file.read_text(encoding="utf-8", errors="replace")
        low = content.lower()
        assert "enable_write_tools: false" in low, (
            f"Violazione GT-14: enable_write_tools non impostato a false in {aud_name}"
        )
        assert "enable_write_tools: true" not in low
        assert "run_command" in content, (
            f"Capacita run_command mancante nell'Auditor {aud_name}"
        )


def test_07_epistemic_governance_markers_100_percent_coverage() -> None:
    """7. Verifica la copertura 100% dei 4 marker epistemici su 5 agent.md, 16 SKILL.md, anti_crash e prompt_templates."""
    required_markers = (
        "[RULE-EPISTEMIC-HONESTY]",
        "[RULE-EVIDENCE]",
        "[RULE-DATA-PROVENANCE]",
        "[RULE-ORACLE-LOCK]",
    )

    agent_names = (
        "NK-Specifier-Agent",
        "NK-Builder-Agent",
        "NK-Security-DAST-Auditor",
        "NK-RSI-Auditor",
        "NK-Scribe-Agent",
    )
    skills_dir = _WORKSPACE_ROOT / ".agents" / "skills"
    skill_names = sorted(
        d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    )
    assert len(skill_names) == 16

    target_rel_paths: List[str] = [
        f".agents/agents/{ag}/agent.md" for ag in agent_names
    ]
    target_rel_paths.extend(f".agents/skills/{sk}/SKILL.md" for sk in skill_names)
    target_rel_paths.append(".agents/rules/anti_crash_rules.md")
    target_rel_paths.append(
        ".agents/skills/NK-Session-Controller/resources/prompt_templates.md"
    )

    missing_report: List[str] = []
    for rel_p in target_rel_paths:
        resolved = _resolve_staged_or_prod_path(rel_p)
        if not resolved.is_file():
            missing_report.append(f"{rel_p}: FILE_NOT_FOUND")
            continue
        txt = resolved.read_text(encoding="utf-8", errors="replace")
        for marker in required_markers:
            if marker not in txt:
                missing_report.append(f"{rel_p}: missing {marker}")

    assert not missing_report, (
        f"Copertura incompleta dei marker epistemici ({len(missing_report)} gap): {missing_report[:15]}"
    )
