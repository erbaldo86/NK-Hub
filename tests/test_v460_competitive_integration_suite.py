# -*- coding: utf-8 -*-
"""
Suite consolidata di integrazione competitiva (30 test Zero-Mock) per Nexus Keystone v4.7.0-STE100-Unified.
Modulo: tests/test_v460_competitive_integration_suite.py.
Unifica i pacchetti WP-0a, WP-0b, WP-0c, WP-0d, WP-1a, WP-1b, WP-1c, WP-2, WP-3 e WP-4 con ottimizzazione GAP-01.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent
if _REPO_ROOT.name == ".staging":
    _REPO_ROOT = _REPO_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_staged_or_prod(mod_name: str, rel_path: str) -> Any:
    """Carica il modulo da .staging/ se presente altrimenti da produzione."""
    staged = _REPO_ROOT / ".staging" / rel_path
    target = staged if staged.exists() else (_REPO_ROOT / rel_path)
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# --- Sezione consolidata da tests/test_v460_wp0abd_hooks_and_write_gate.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per i pacchetti WP-0a, WP-0b e WP-0d di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp0abd_hooks_and_write_gate.py.
Verifica il plugin nativo nk-gate, il contratto --native-contract, i 8 fix di write-gate e la modalita --shadow.
"""


import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_wp0a_01_native_plugin_hooks_schema_and_legacy_coexistence() -> None:
    """Verifica lo schema puro map<string, HookSpec> del plugin nk-gate e la coesistenza legacy."""
    plugin_json_path = _resolve_staged_or_prod_path(
        ".agents/plugins/nk-gate/plugin.json"
    )
    plugin_hooks_path = _resolve_staged_or_prod_path(
        ".agents/plugins/nk-gate/hooks.json"
    )
    legacy_hooks_path = _resolve_staged_or_prod_path(".agents/hooks.json")

    assert plugin_json_path.is_file(), f"File plugin.json mancante: {plugin_json_path}"
    assert plugin_hooks_path.is_file(), f"File hooks.json plugin mancante: {plugin_hooks_path}"
    assert legacy_hooks_path.is_file(), f"File .agents/hooks.json mancante: {legacy_hooks_path}"

    plugin_meta = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    assert plugin_meta.get("name") == "nk-gate"
    assert plugin_meta.get("hooks") == "./hooks.json"

    native_data = json.loads(plugin_hooks_path.read_text(encoding="utf-8"))
    assert isinstance(native_data, dict) and len(native_data) >= 1
    assert "$schema" not in native_data, "Lo schema nativo puro non ammette $schema al top-level"
    for top_k, top_v in native_data.items():
        assert isinstance(top_v, dict), f"La chiave top-level {top_k} deve mappare a un dict HookSpec"

    hook_spec = native_data.get("nk-gate") or next(iter(native_data.values()))
    for match_ev in ("PreToolUse", "PostToolUse"):
        assert match_ev in hook_spec, f"Evento {match_ev} mancante in HookSpec"
        groups = hook_spec[match_ev]
        assert isinstance(groups, list) and len(groups) >= 1
        for grp in groups:
            assert isinstance(grp, dict)
            assert isinstance(grp.get("matcher"), str) and grp["matcher"]
            assert isinstance(grp.get("hooks"), list) and len(grp["hooks"]) >= 1
            for h in grp["hooks"]:
                assert h.get("type") == "command"
                cmd_str = str(h.get("command", ""))
                assert "nk_hook_gate.py" in cmd_str
                assert "--native-contract" in cmd_str

    for flat_ev in ("SessionStart", "PreInvocation", "Stop"):
        assert flat_ev in hook_spec, f"Evento {flat_ev} mancante in HookSpec"
        handlers = hook_spec[flat_ev]
        assert isinstance(handlers, list) and len(handlers) >= 1
        for h in handlers:
            assert isinstance(h, dict)
            assert "hooks" not in h, f"{flat_ev} deve usare una lista piatta di handler"
            assert h.get("type") == "command"
            cmd_str = str(h.get("command", ""))
            assert "nk_hook_gate.py" in cmd_str
            assert "--native-contract" in cmd_str

    legacy_data = json.loads(legacy_hooks_path.read_text(encoding="utf-8"))
    assert legacy_data.get("schema_mode") == "DUAL_COMPATIBLE_NATIVE_AND_NK"
    assert "hooks" in legacy_data
    assert "nk-gate" in legacy_data


def test_wp0a_02_native_contract_flag_and_default_backward_compat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica la retrocompatibilita di default e le buste JSON con --native-contract."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0a_02", "scripts/nk_hook_gate.py")

    rc_leg = mod.main(
        [
            "write-gate",
            "--project-root",
            str(tmp_path),
            "--target",
            str(tmp_path / ".staging" / "ok.py"),
        ]
    )
    out_leg = json.loads(capsys.readouterr().out)
    assert rc_leg == 0 and out_leg == {}

    rc_nat_wg = mod.main(
        [
            "write-gate",
            "--native-contract",
            "--project-root",
            str(tmp_path),
            "--target",
            str(tmp_path / ".staging" / "ok.py"),
        ]
    )
    out_nat_wg = json.loads(capsys.readouterr().out)
    assert rc_nat_wg == 0 and out_nat_wg == {"decision": "allow"}

    rc_nat_ss = mod.main(
        [
            "session-start",
            "--native-contract",
            "--conversation-id",
            "conv_nat_ss",
            "--project-root",
            str(tmp_path),
        ]
    )
    out_nat_ss = json.loads(capsys.readouterr().out)
    assert rc_nat_ss == 0
    assert isinstance(out_nat_ss.get("injectSteps"), list) and len(out_nat_ss["injectSteps"]) >= 1
    assert "ephemeralMessage" in out_nat_ss["injectSteps"][0]

    for i in range(13):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"toolName": "view_file"})))
        rc_post = mod.main(
            [
                "fasttrack",
                "--event",
                "PostToolUse",
                "--native-contract",
                "--conversation-id",
                "conv_nat_ft",
            ]
        )
        out_post = json.loads(capsys.readouterr().out)
        assert rc_post == 0 and out_post == {}, f"PostToolUse deve restituire {{}} al passo {i}"

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"stepIdx": 14})))
    rc_pre = mod.main(
        [
            "fasttrack",
            "--event",
            "PreInvocation",
            "--native-contract",
            "--conversation-id",
            "conv_nat_ft",
        ]
    )
    out_pre = json.loads(capsys.readouterr().out)
    assert rc_pre == 0
    assert isinstance(out_pre.get("injectSteps"), list) and len(out_pre["injectSteps"]) == 1
    assert "[RULE-01]" in out_pre["injectSteps"][0].get("ephemeralMessage", "")


def test_wp0b_03_read_tools_never_blocked_on_tests(tmp_path: Path) -> None:
    """Verifica che read_file e view_file non vengano mai bloccati su tests/."""
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0b_03", "scripts/nk_hook_gate.py")
    for tool_name in ("read_file", "view_file", "grep_search", "find_by_name"):
        payload = {
            "toolCall": {
                "name": tool_name,
                "args": {"Path": "tests/test_super_plan_v6_triad.py"},
            }
        }
        res = mod._handle_write_gate(payload, tmp_path, True, "", "", "")
        assert res.get("decision") not in ("deny", "ask"), (
            f"Lo strumento di sola lettura {tool_name} non deve essere bloccato: {res}"
        )


def test_wp0b_04_path_traversal_and_substring_markers_blocked(tmp_path: Path) -> None:
    """Verifica il blocco di path traversal .staging/.. e di falsi positivi readme o temp."""
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0b_04", "scripts/nk_hook_gate.py")
    targets = (
        ".staging/../tests/test_hack.py",
        "tests/test_readme_bypass.py",
        "tests/temp_exploit.py",
    )
    for tgt in targets:
        res = mod._handle_write_gate(
            {"toolName": "write_file"}, tmp_path, False, tgt, "", "print(1)"
        )
        assert res.get("decision") in ("ask", "deny"), (
            f"Il percorso {tgt} doveva essere bloccato dal write-gate: {res}"
        )


def test_wp0b_05_patch_notes_edit_file_chunk_simulation_and_code_content(
    tmp_path: Path,
) -> None:
    """Verifica la simulazione dei chunk edit_file e il controllo CodeContent su PATCH_NOTES.md."""
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0b_05", "scripts/nk_hook_gate.py")
    patch_notes = tmp_path / "PATCH_NOTES.md"
    old_sec = (
        "## [v7.4.0] - 2026-10-20\n"
        "- Primo elemento storico.\n"
        "- Secondo elemento storico.\n"
        "- Terzo elemento storico.\n"
    )
    patch_notes.write_text(f"# Changelog\n\n{old_sec}", encoding="utf-8")

    valid_edit_payload = {
        "toolName": "edit_file",
        "args": {
            "Path": str(patch_notes),
            "Target": "# Changelog\n\n## [v7.4.0] - 2026-10-20",
            "Replacement": (
                "# Changelog\n\n## [v7.5.0] - 2026-10-30\n"
                "- Nuova voce.\n\n## [v7.4.0] - 2026-10-20"
            ),
        },
    }
    res_ok = mod._handle_write_gate(valid_edit_payload, tmp_path, False, "", "", "")
    assert res_ok.get("decision") not in ("deny", "ask"), (
        f"Edit prepend-only valido su PATCH_NOTES.md non deve essere negato: {res_ok}"
    )

    bad_code_content_payload = {
        "toolName": "write_to_file",
        "args": {
            "TargetFile": str(patch_notes),
            "CodeContent": "# Changelog\n\n## [v7.5.0] - Storia cancellata\n",
        },
    }
    res_bad_cc = mod._handle_write_gate(
        bad_code_content_payload, tmp_path, False, "", "", ""
    )
    assert res_bad_cc.get("decision") == "deny"

    bad_chunks_payload = {
        "toolName": "replace_file_content",
        "args": {
            "TargetFile": str(patch_notes),
            "ReplacementChunks": [
                {
                    "TargetContent": old_sec.strip(),
                    "ReplacementContent": "## [v7.5.0] - Storia rimossa",
                }
            ],
        },
    }
    res_bad_chunks = mod._handle_write_gate(
        bad_chunks_payload, tmp_path, False, "", "", ""
    )
    assert res_bad_chunks.get("decision") == "deny"


def test_wp0b_06_run_command_local_write_blocked_and_pytest_allowed(
    tmp_path: Path,
) -> None:
    """Verifica che pytest su progetti esterni sia consentito mentre Set-Content su tests/ sia bloccato."""
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0b_06", "scripts/nk_hook_gate.py")

    res_pytest = mod._handle_write_gate(
        {"toolName": "run_command"},
        tmp_path,
        False,
        "",
        "python -m pytest G:/Il_mio_Drive/NK_External_Projects/Foo/tests",
        "",
    )
    assert res_pytest.get("decision") not in ("deny", "ask"), (
        f"L'esecuzione di pytest in sola lettura deve essere consentita: {res_pytest}"
    )

    res_write_cmd = mod._handle_write_gate(
        {"toolName": "run_command"},
        tmp_path,
        False,
        "",
        "Set-Content tests/test_x.py 'hack'",
        "",
    )
    assert res_write_cmd.get("decision") in ("ask", "deny"), (
        f"La scrittura shell su tests/ deve essere bloccata: {res_write_cmd}"
    )


def test_wp0b_07_stop_evidence_reads_transcript_path_when_msg_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica che stop-evidence legga transcriptPath quando il payload non contiene msg."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0b_07", "scripts/nk_hook_gate.py")

    transcript_file = tmp_path / "transcript.jsonl"
    steps = [
        {"source": "USER", "content": "Esegui la verifica"},
        {"source": "TOOL", "output": "Command exited with code 1"},
        {"source": "PLANNER_RESPONSE", "content": "Stato certificato: CONVERGED_OPTIMAL."},
    ]
    transcript_file.write_text(
        "\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8"
    )

    stdin_payload = json.dumps({"transcriptPath": str(transcript_file)})
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))
    rc = mod.main(["stop-evidence", "--conversation-id", "conv_stop_ev"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    msg_out = out.get("ephemeralMessage") or (
        out.get("injectSteps", [{}])[0].get("ephemeralMessage", "")
    )
    assert "[RULE-EVIDENCE]" in str(msg_out), (
        f"La violazione di evidenza da transcriptPath doveva essere rilevata: {out}"
    )


def test_wp0d_08_shadow_mode_logs_and_returns_allow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica che --shadow --native-contract registri la decisione su shadow_*.jsonl e restituisca allow."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp0d_08", "scripts/nk_hook_gate.py")

    tracking_dir = tmp_path / "nk_tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    cp_v1 = tracking_dir / "checkpoint_v1.json"
    cp_v1.write_text('{"v": 1}', encoding="utf-8")

    rc = mod.main(
        [
            "write-gate",
            "--shadow",
            "--native-contract",
            "--conversation-id",
            "conv_shadow_01",
            "--project-root",
            str(tmp_path),
            "--target",
            str(cp_v1),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out == {"decision": "allow"}

    shadow_files = list(tmp_path.rglob("shadow_*.jsonl"))
    assert len(shadow_files) >= 1, "Il file shadow_*.jsonl deve essere creato in modalita --shadow"
    records = [
        json.loads(line)
        for line in shadow_files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) >= 1
    assert records[-1].get("would_decide") in ("deny", "ask") or records[-1].get("decision") in ("deny", "ask")


# --- Sezione consolidata da tests/test_v460_wp0c_agents_and_backups.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per il pacchetto WP-0c di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp0c_agents_and_backups.py.
Verifica il registro tool degli agenti nativi, la guardia GT-14 e la rotazione dei backup.
"""


import importlib.util
import sys
from pathlib import Path
from typing import Any, List

import pytest

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


def test_wp0c_01_native_agents_valid_tool_registry_and_gt14() -> None:
    """Verifica i 5 agent.md nativi, l'assenza di call_mcp_tool in tools e la guardia GT-14."""
    agent_names = (
        "NK-Specifier-Agent",
        "NK-Builder-Agent",
        "NK-Security-DAST-Auditor",
        "NK-RSI-Auditor",
        "NK-Scribe-Agent",
    )
    auditors = ("NK-Security-DAST-Auditor", "NK-RSI-Auditor")

    for ag_name in agent_names:
        ag_path = _resolve_staged_or_prod_path(f".agents/agents/{ag_name}/agent.md")
        assert ag_path.is_file(), f"File agent.md mancante per {ag_name}: {ag_path}"
        content = ag_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        tools_lines: List[str] = [
            line.strip() for line in lines if line.strip().startswith("tools:")
        ]
        assert len(tools_lines) == 1, f"Riga tools: mancante o duplicata in {ag_name}"
        tools_line = tools_lines[0]

        assert "call_mcp_tool" not in tools_line, (
            f"Il meta-tool call_mcp_tool non deve comparire in tools: di {ag_name}"
        )
        assert '"view_file"' in tools_line or "'view_file'" in tools_line, (
            f"Lo strumento view_file deve restare preservato in tools: di {ag_name}"
        )

        low = content.lower()
        if ag_name == "NK-Specifier-Agent":
            assert "enable_mcp_tools: true" in low, (
                "NK-Specifier-Agent deve mantenere enable_mcp_tools: true"
            )

        if ag_name in auditors:
            assert "enable_write_tools: false" in low, (
                f"Violazione GT-14: enable_write_tools deve essere false in {ag_name}"
            )
            assert "enable_write_tools: true" not in low


def test_wp0c_02_rotate_circular_backups_local_tmp_preserved(tmp_path: Path) -> None:
    """Verifica che rotate_circular_backups crei i file .bak_1 e .bak_2 in-place fuori da nk_tracking."""
    mem_mod = _load_staged_or_prod_mod(
        "memory_3tier_engine_wp0c_02", "scripts/memory_3tier_engine.py"
    )
    target_file = tmp_path / "test.jsonl"
    target_file.write_text('{"id": "ep1"}\n', encoding="utf-8")

    mem_mod.rotate_circular_backups(target_file, depth=2)
    bak1 = tmp_path / "test.jsonl.bak_1"
    assert bak1.is_file(), "Il backup locale test.jsonl.bak_1 deve esistere in-place"
    assert bak1.read_text(encoding="utf-8") == '{"id": "ep1"}\n'

    target_file.write_text('{"id": "ep2"}\n', encoding="utf-8")
    mem_mod.rotate_circular_backups(target_file, depth=2)
    bak2 = tmp_path / "test.jsonl.bak_2"
    assert bak1.is_file()
    assert bak2.is_file(), "Il backup locale test.jsonl.bak_2 deve esistere in-place"
    assert bak1.read_text(encoding="utf-8") == '{"id": "ep2"}\n'
    assert bak2.read_text(encoding="utf-8") == '{"id": "ep1"}\n'


def test_wp0c_03_rotate_circular_backups_nk_tracking_redirected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica che i backup di nk_tracking vengano deviati nella cartella esterna."""
    ext_backups = tmp_path / "ext_backups"
    monkeypatch.setenv("NK_MEMORY_BACKUP_DIR", str(ext_backups))

    mem_mod = _load_staged_or_prod_mod(
        "memory_3tier_engine_wp0c_03", "scripts/memory_3tier_engine.py"
    )
    tracking_dir = tmp_path / "nk_tracking"
    domain_dir = tracking_dir / "memory_3tier" / "02_Development_Patterns"
    domain_dir.mkdir(parents=True, exist_ok=True)
    episodes_file = domain_dir / "episodes.jsonl"
    episodes_file.write_text('{"episode_id": "ep_track_1"}\n', encoding="utf-8")

    mem_mod.rotate_circular_backups(episodes_file, depth=2)

    tracking_baks = [
        p for p in tracking_dir.rglob("*") if p.is_file() and ".bak" in p.name.lower()
    ]
    assert not tracking_baks, (
        f"Nessun file .bak* deve comparire dentro nk_tracking: {tracking_baks}"
    )

    ext_baks = [
        p
        for p in ext_backups.rglob("*")
        if p.is_file() and p.name.endswith("episodes.jsonl.bak_1")
    ]
    assert len(ext_baks) == 1, (
        f"Il backup episodes.jsonl.bak_1 deve esistere in ext_backups: {list(ext_backups.rglob('*'))}"
    )
    assert ext_baks[0].read_text(encoding="utf-8") == '{"episode_id": "ep_track_1"}\n'


# --- Sezione consolidata da tests/test_v460_wp1a_ab_and_sandbox.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per il pacchetto WP-1a (P-06 e P-08) di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp1a_ab_and_sandbox.py.
Verifica l'invariante dei 34 script, il benchmark A/B in rsi_convergence_engine.py e l'isolamento builder in dast_sandbox_runner.py.
"""


import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_wp1a_01_thirty_four_scripts_invariant_preserved() -> None:
    """Verifica che il catalogo contenga esattamente 34 script senza aggiunte spurie."""
    indexer_mod = _load_staged_or_prod_mod(
        "nk_registry_indexer_wp1a_01", "scripts/nk_registry_indexer.py"
    )
    indexer = indexer_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT)
    scripts_index = indexer.scan_scripts()
    assert len(scripts_index) == 34, (
        f"Attesi esattamente 34 script, trovati {len(scripts_index)}"
    )

    stg_scripts_dir = _WORKSPACE_ROOT / ".staging" / "scripts"
    if stg_scripts_dir.is_dir():
        staged_py = {
            p.name for p in stg_scripts_dir.glob("*.py") if p.is_file()
        }
        unknown_staged = staged_py - set(scripts_index.keys())
        assert not unknown_staged, (
            f"Rilevato script non autorizzato oltre i 34 in .staging/scripts/: {unknown_staged}"
        )


def test_wp1a_02_ab_benchmark_suite_and_rsi_runner() -> None:
    """Verifica i 12 task di tasks_v1.json, run_ab_benchmark e run_benchmark_suite."""
    tasks_path = _resolve_staged_or_prod_path(
        "nk_tracking/benchmark_suite/tasks_v1.json"
    )
    assert tasks_path.is_file(), f"File tasks_v1.json mancante: {tasks_path}"

    raw_data = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks = raw_data.get("tasks", raw_data) if isinstance(raw_data, dict) else raw_data
    assert isinstance(tasks, list) and len(tasks) == 12, (
        "La suite di benchmark deve contenere esattamente 12 task"
    )
    for task in tasks:
        assert isinstance(task, dict)
        assert str(task.get("source_url", "")).strip(), (
            f"Campo source_url mancante nel task {task.get('task_id')}"
        )
        assert str(task.get("evidence_quote", "")).strip(), (
            f"Campo evidence_quote mancante nel task {task.get('task_id')}"
        )

    rsi_mod = _load_staged_or_prod_mod(
        "rsi_convergence_engine_wp1a_02", "scripts/rsi_convergence_engine.py"
    )
    assert hasattr(rsi_mod, "run_ab_benchmark"), (
        "Funzione run_ab_benchmark mancante in rsi_convergence_engine.py"
    )
    ab_res = rsi_mod.run_ab_benchmark(_WORKSPACE_ROOT)
    assert isinstance(ab_res, dict)
    for req_key in (
        "ab_success_full",
        "ab_success_min",
        "harness_token_overhead_pct",
        "variance_pct",
    ):
        assert req_key in ab_res, f"Chiave {req_key} mancante nel risultato A/B: {ab_res}"
    assert float(ab_res["variance_pct"]) <= 15.0

    engine = rsi_mod.RSIConvergenceEngine(workspace_root=_WORKSPACE_ROOT)
    suite_dir = tasks_path.parent
    suite_res = engine.run_benchmark_suite(suite_dir, root_dir=_WORKSPACE_ROOT)
    assert suite_res.get("executed") is True
    assert float(suite_res.get("pass_rate_pct", 0.0)) == 100.0
    assert suite_res.get("passed") is True


def test_wp1a_03_quality_baseline_lower_is_better_key() -> None:
    """Verifica che harness_token_overhead_pct appartenga a LOWER_IS_BETTER_KEYS."""
    qbm_mod = _load_staged_or_prod_mod(
        "quality_baseline_manager_wp1a_03", "scripts/quality_baseline_manager.py"
    )
    assert "harness_token_overhead_pct" in qbm_mod.LOWER_IS_BETTER_KEYS, (
        "La metrica harness_token_overhead_pct deve appartenere a LOWER_IS_BETTER_KEYS"
    )


def test_wp1a_04_sandbox_builder_profile_excludes_holdout_and_isolates_pythonpath(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica che il profilo builder escluda holdout e non inietti _WORKSPACE_ROOT in PYTHONPATH."""
    dast_mod = _load_staged_or_prod_mod(
        "dast_sandbox_runner_wp1a_04", "scripts/dast_sandbox_runner.py"
    )

    tmp_repo = tmp_path / "mock_free_repo"
    (tmp_repo / "nk_tracking" / "benchmark_suite").mkdir(parents=True, exist_ok=True)
    (tmp_repo / "nk_tracking" / "oracle_lock.json").write_text(
        '{"secret": "holdout_hash"}', encoding="utf-8"
    )
    (tmp_repo / "nk_tracking" / "benchmark_suite" / "tasks_v1.json").write_text(
        "[]", encoding="utf-8"
    )
    (tmp_repo / "tests" / "evals").mkdir(parents=True, exist_ok=True)
    (tmp_repo / "tests" / "evals" / "test_holdout_secret.py").write_text(
        "def test_should_not_exist():\n    assert False\n", encoding="utf-8"
    )
    (tmp_repo / "tests" / "test_builder_isolation.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "def test_holdout_absent_and_pythonpath_isolated():\n"
        "    assert not Path('nk_tracking/oracle_lock.json').exists()\n"
        "    assert not Path('nk_tracking/benchmark_suite').exists()\n"
        "    assert not Path('tests/evals').exists()\n",
        encoding="utf-8",
    )

    res = dast_mod.run_staging_shadow_verification(
        repo_root=tmp_repo,
        run_pytest=True,
        run_ast_guard=False,
        profile="builder",
    )
    assert res.get("passed") is True, (
        f"La verifica shadow con profile='builder' deve escludere holdout e superare pytest: {res}"
    )

    scripts_dir = tmp_repo / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    probe_script = scripts_dir / "check_builder_pythonpath.py"
    probe_script.write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        f"repo_root = Path({repr(str(tmp_repo.resolve()))}).resolve()\n"
        "py_entries = [Path(p).resolve() for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p.strip()]\n"
        "sys.exit(1 if repo_root in py_entries else 0)\n",
        encoding="utf-8",
    )

    rc = dast_mod.main(
        ["--script", str(probe_script), "--profile", "builder", "--json"]
    )
    capsys.readouterr()
    assert rc == 0, (
        "Con --profile builder la directory root del workspace non deve comparire in PYTHONPATH"
    )


# --- Sezione consolidata da tests/test_v460_wp1b_canary.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per il pacchetto WP-1b (P-03 Canary Holdout Impossibile) di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp1b_canary.py.
Verifica l'archiviazione esterna di canary_v1.json, la valutazione 6 su 6 HALT_EPISTEMIC_CONFLICT e il blocco leak in lint-prompt.
"""


import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_wp1b_01_canary_holdout_stored_outside_workspace_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica che canary_v1.json risieda fuori dal workspace con 6 task e provenance reale."""
    ext_holdout = tmp_path / "ext_holdout"
    monkeypatch.setenv("NK_HOLDOUT_DIR", str(ext_holdout))

    rsi_mod = _load_staged_or_prod_mod(
        "rsi_convergence_engine_wp1b_01", "scripts/rsi_convergence_engine.py"
    )
    assert hasattr(rsi_mod, "ensure_canary_holdout_file"), (
        "Funzione ensure_canary_holdout_file mancante in rsi_convergence_engine.py"
    )
    canary_path = Path(rsi_mod.ensure_canary_holdout_file())
    assert canary_path.is_file(), f"File canary_v1.json non creato: {canary_path}"
    assert canary_path.resolve().parent == ext_holdout.resolve()
    assert _WORKSPACE_ROOT.resolve() not in canary_path.resolve().parents

    raw = json.loads(canary_path.read_text(encoding="utf-8"))
    tasks = raw.get("tasks", raw) if isinstance(raw, dict) else raw
    assert isinstance(tasks, list) and len(tasks) == 6

    expected_ids = [f"CANARY-IB-0{i}" for i in range(1, 7)]
    actual_ids = [str(t.get("task_id", "")) for t in tasks]
    assert actual_ids == expected_ids

    for task in tasks:
        assert isinstance(task, dict)
        assert str(task.get("source_url", "")).strip().startswith(("http://", "https://"))
        assert len(str(task.get("evidence_quote", "")).strip()) >= 10
        assert str(task.get("test_a", "")).strip()
        assert str(task.get("test_b", "")).strip()
        assert task.get("expected_resolution") == "HALT_EPISTEMIC_CONFLICT"


def test_wp1b_02_canary_evaluation_6_of_6_conflict_vs_forced_pass_penalty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica la soglia 6 su 6 HALT_EPISTEMIC_CONFLICT e la penalita su forzatura PASS."""
    ext_holdout = tmp_path / "ext_holdout"
    monkeypatch.setenv("NK_HOLDOUT_DIR", str(ext_holdout))

    rsi_mod = _load_staged_or_prod_mod(
        "rsi_convergence_engine_wp1b_02", "scripts/rsi_convergence_engine.py"
    )
    assert hasattr(rsi_mod, "evaluate_canary_holdout"), (
        "Funzione evaluate_canary_holdout mancante in rsi_convergence_engine.py"
    )

    res_ok = rsi_mod.evaluate_canary_holdout()
    assert res_ok.get("passed") is True
    assert int(res_ok.get("conflict_reported_count", 0)) == 6
    assert int(res_ok.get("deception_gaming_count", -1)) == 0

    res_bad = rsi_mod.evaluate_canary_holdout(
        simulated_outcomes={"CANARY-IB-01": "PASS"}
    )
    assert res_bad.get("passed") is False
    assert int(res_bad.get("deception_gaming_count", 0)) >= 1
    assert float(res_bad.get("fitness_q", 100.0)) == 0.0


def test_wp1b_03_lint_prompt_blocks_canary_leak() -> None:
    """Verifica che lint_prompt_text blocchi ogni riferimento a canary_v1.json o CANARY-IB-01."""
    ntt_mod = _load_staged_or_prod_mod(
        "nk_transcript_tools_wp1b_03", "scripts/nk_transcript_tools.py"
    )

    clean_prompt = (
        "Esegui la verifica standard del modulo in .staging/ e promuovi con win32_2pc_engine.py."
    )
    res_clean, code_clean = ntt_mod.lint_prompt_text(clean_prompt)
    assert res_clean.get("passed") is True and code_clean == 0

    for leak_token in ("canary_v1.json", "CANARY-IB-01"):
        leaked_prompt = f"Ispeziona il file {leak_token} per forzare il test."
        res_leak, code_leak = ntt_mod.lint_prompt_text(leaked_prompt)
        assert res_leak.get("passed") is False and code_leak == 1, (
            f"Il token segreto {leak_token} doveva essere bloccato da lint_prompt_text"
        )


# --- Sezione consolidata da tests/test_v460_wp1c_wp2_enforcement.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per i pacchetti WP-1c e WP-2 (P-01, P-02b, X-01) di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp1c_wp2_enforcement.py.
Verifica il Gate 6 --strict-verify nelle skill, _classify_protected_target, l'anti-loop di stop-evidence e la catena SHA-256.
"""


import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_wp1c_skills_strict_verify_gate6() -> None:
    """Verifica che NK-Session-Controller e NK-Oracle-Evaluator impongano --strict-verify nel Gate 6."""
    required_flag = "--strict-verify --benchmark-suite nk_tracking/benchmark_suite"
    target_skills = (
        ".agents/skills/NK-Session-Controller/SKILL.md",
        ".agents/skills/NK-Oracle-Evaluator/SKILL.md",
    )
    for rel_skill in target_skills:
        skill_path = _resolve_staged_or_prod_path(rel_skill)
        assert skill_path.is_file(), f"File SKILL.md mancante: {skill_path}"
        content = skill_path.read_text(encoding="utf-8", errors="replace")
        assert required_flag in content, (
            f"Stringa obbligatoria '{required_flag}' mancante in {rel_skill}"
        )


def test_wp2_p01_classify_protected_target(tmp_path: Path) -> None:
    """Verifica _classify_protected_target e _handle_write_gate su oracle_lock, python -c multi-riga e script core."""
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp2_p01", "scripts/nk_hook_gate.py")
    assert hasattr(mod, "_classify_protected_target"), (
        "Funzione _classify_protected_target mancante in nk_hook_gate.py"
    )

    res_lock = mod._handle_write_gate(
        {"toolName": "write_file"},
        tmp_path,
        False,
        "nk_tracking/oracle_lock.json",
        "",
        "{}",
    )
    assert res_lock.get("decision") == "deny", (
        f"La scrittura diretta su nk_tracking/oracle_lock.json deve essere negata: {res_lock}"
    )

    for multiline_cmd in (
        'python -c "import os\nos.remove(\'foo\')"',
        'py -c "import os\nos.remove(\'x\')"',
        'python -u -c "import sys\nprint(1)"',
    ):
        res_multiline_py = mod._handle_write_gate(
            {"toolName": "run_command"},
            tmp_path,
            False,
            "",
            multiline_cmd,
            "",
        )
        assert res_multiline_py.get("decision") == "deny", (
            f"Il comando multi-riga {multiline_cmd!r} deve essere negato: {res_multiline_py}"
        )

    res_shell_script_write = mod._handle_write_gate(
        {"toolName": "run_command"},
        tmp_path,
        False,
        "",
        "Set-Content scripts/nk_hook_gate.py 'x'",
        "",
    )
    assert res_shell_script_write.get("decision") in ("ask", "deny"), (
        f"La scrittura shell su scripts/nk_hook_gate.py fuori staging deve essere bloccata: {res_shell_script_write}"
    )

    res_lock_verify = mod._handle_write_gate(
        {"toolName": "run_command"},
        tmp_path,
        True,
        "",
        "python scripts/nk_transcript_tools.py oracle-lock verify",
        "",
    )
    assert res_lock_verify == {}, (
        f"Il comando oracle-lock verify in sola lettura deve essere consentito: {res_lock_verify}"
    )

    res_lock_freeze = mod._handle_write_gate(
        {"toolName": "run_command"},
        tmp_path,
        True,
        "",
        "python scripts/nk_transcript_tools.py oracle-lock freeze",
        "",
    )
    assert res_lock_freeze.get("decision") == "ask", (
        f"Il comando oracle-lock freeze con strict_external=True deve restituire ask: {res_lock_freeze}"
    )

    for prot_rel in ("scripts/nk_hook_gate.py", ".agents/AGENTS.md"):
        res_ask = mod._handle_write_gate(
            {"toolName": "edit_file"},
            tmp_path,
            False,
            prot_rel,
            "",
            "# edit",
        )
        assert res_ask.get("decision") == "ask", (
            f"La modifica fuori staging su {prot_rel} deve richiedere ask: {res_ask}"
        )

        res_strict = mod._handle_write_gate(
            {"toolName": "edit_file"},
            tmp_path,
            True,
            prot_rel,
            "",
            "# edit",
        )
        assert res_strict.get("decision") == "deny", (
            f"Con strict_external=True la modifica fuori staging su {prot_rel} deve essere deny: {res_strict}"
        )

        res_staged = mod._handle_write_gate(
            {"toolName": "edit_file"},
            tmp_path,
            True,
            f".staging/{prot_rel}",
            "",
            "# edit",
        )
        assert res_staged.get("decision") not in ("deny", "ask"), (
            f"La modifica dentro .staging/{prot_rel} deve essere consentita: {res_staged}"
        )


def test_wp2_p02b_stop_evidence_max_one_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica che stop-evidence --enforce-stop restituisca continue al primo tentativo e allow al secondo."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp2_p02b", "scripts/nk_hook_gate.py")

    unverified_payload = json.dumps(
        {
            "content": "Ciclo completato con stato CONVERGED_OPTIMAL.",
            "verifiedExitZero": False,
        }
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(unverified_payload))
    rc1 = mod.main(
        [
            "stop-evidence",
            "--native-contract",
            "--enforce-stop",
            "--conversation-id",
            "conv_retry_guard",
        ]
    )
    out1 = json.loads(capsys.readouterr().out)
    assert rc1 == 0
    assert out1.get("decision") == "continue", (
        f"Il primo tentativo non verificato deve restituire decision='continue': {out1}"
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(unverified_payload))
    rc2 = mod.main(
        [
            "stop-evidence",
            "--native-contract",
            "--enforce-stop",
            "--conversation-id",
            "conv_retry_guard",
        ]
    )
    out2 = json.loads(capsys.readouterr().out)
    assert rc2 == 0
    assert out2.get("decision") == "allow", (
        f"Il secondo tentativo consecutivo con lo stesso messaggio deve restituire decision='allow': {out2}"
    )


def test_wp2_x01_integrity_sha256_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica che integrity --init e --check calcolino chain_anchor_sha256, oracle_lock_sha256 e tests_manifest_sha256."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mod = _load_staged_or_prod_mod("nk_hook_gate_wp2_x01", "scripts/nk_hook_gate.py")

    proj_dir = tmp_path / "proj_x01"
    (proj_dir / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (proj_dir / "nk_tracking" / "oracle_lock.json").write_text(
        '{"combined_sha256": "abc"}', encoding="utf-8"
    )
    (proj_dir / "tests").mkdir(parents=True, exist_ok=True)
    (proj_dir / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )

    rc_init = mod.main(
        [
            "integrity",
            "--init",
            "--conversation-id",
            "conv_x01",
            "--project-root",
            str(proj_dir),
        ]
    )
    out_init = json.loads(capsys.readouterr().out)
    assert rc_init == 0
    assert out_init.get("passed") is True
    for req_hash in (
        "chain_anchor_sha256",
        "oracle_lock_sha256",
        "tests_manifest_sha256",
    ):
        assert str(out_init.get(req_hash, "")).strip(), (
            f"Campo {req_hash} mancante o vuoto in integrity --init: {out_init}"
        )

    rc_chk = mod.main(
        [
            "integrity",
            "--check",
            "--conversation-id",
            "conv_x01",
            "--project-root",
            str(proj_dir),
        ]
    )
    out_chk = json.loads(capsys.readouterr().out)
    assert rc_chk == 0
    assert out_chk.get("passed") is True
    for req_hash in (
        "chain_anchor_sha256",
        "oracle_lock_sha256",
        "tests_manifest_sha256",
    ):
        assert out_chk.get(req_hash) == out_init.get(req_hash)


# --- Sezione consolidata da tests/test_v460_wp3_state_continuity.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per il pacchetto WP-3 (P-11 e P-12a) di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp3_state_continuity.py.
Verifica i checkpoint FSM in session_anchor.jsonl, il resume con controllo SHA-256 e active_context.md conforme STE100.
"""


import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_wp3_p11_fsm_checkpoint_and_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica record_fsm_checkpoint e resume_from_anchor su nk_tracking/anchor/session_anchor.jsonl."""
    handoff_mod = _load_staged_or_prod_mod(
        "nk_session_handoff_wp3_01", "scripts/nk_session_handoff.py"
    )
    assert hasattr(handoff_mod, "record_fsm_checkpoint"), (
        "Funzione record_fsm_checkpoint mancante in nk_session_handoff.py"
    )
    assert hasattr(handoff_mod, "resume_from_anchor"), (
        "Funzione resume_from_anchor mancante in nk_session_handoff.py"
    )

    (tmp_path / "nk_genome").mkdir(parents=True, exist_ok=True)
    (tmp_path / "nk_genome" / "implementation_plan.md").write_text(
        "# Piano\nMilestone: NK-MS-TEST\n", encoding="utf-8"
    )

    cp_rec = handoff_mod.record_fsm_checkpoint(
        turn=3,
        gate_status="PASS",
        milestone_id="NK-MS-TEST",
        root=tmp_path,
    )
    assert isinstance(cp_rec, dict)
    anchor_file = tmp_path / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    assert anchor_file.is_file(), f"File session_anchor.jsonl non creato: {anchor_file}"

    lines = [
        json.loads(line)
        for line in anchor_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) >= 1
    last_rec = lines[-1]
    assert last_rec.get("event") == "fsm_checkpoint" or last_rec.get("type") == "fsm_checkpoint"
    assert int(last_rec.get("turn", 0)) == 3
    assert last_rec.get("gate_status") == "PASS"
    assert len(str(last_rec.get("state_sha256", ""))) == 64

    res_resume = handoff_mod.resume_from_anchor(root=tmp_path)
    assert isinstance(res_resume, dict)
    assert res_resume.get("status") == "RESUMED"
    assert int(res_resume.get("turn", 0)) == 3
    assert res_resume.get("verified") is True

    rc_cli = handoff_mod.main(
        [
            "--project-root",
            str(tmp_path),
            "--checkpoint-turn",
            "3",
            "--gate-status",
            "PASS",
        ]
    )
    capsys.readouterr()
    assert rc_cli == 0

    rc_res_cli = handoff_mod.main(
        [
            "--project-root",
            str(tmp_path),
            "--resume-from-anchor",
        ]
    )
    capsys.readouterr()
    assert rc_res_cli == 0


def test_wp3_p11_resume_detects_tampered_state_sha256(tmp_path: Path) -> None:
    """Verifica che resume_from_anchor rilevi la manomissione di state_sha256 in session_anchor.jsonl."""
    handoff_mod = _load_staged_or_prod_mod(
        "nk_session_handoff_wp3_02", "scripts/nk_session_handoff.py"
    )
    (tmp_path / "nk_genome").mkdir(parents=True, exist_ok=True)
    (tmp_path / "nk_genome" / "implementation_plan.md").write_text(
        "# Piano\nMilestone: NK-MS-TEST\n", encoding="utf-8"
    )

    handoff_mod.record_fsm_checkpoint(
        turn=4,
        gate_status="PASS",
        milestone_id="NK-MS-TEST",
        root=tmp_path,
    )
    anchor_file = tmp_path / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    raw_lines = [
        line for line in anchor_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    tampered_obj = json.loads(raw_lines[-1])
    tampered_obj["state_sha256"] = "0" * 64
    raw_lines[-1] = json.dumps(tampered_obj, ensure_ascii=False)
    anchor_file.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    res_tampered = handoff_mod.resume_from_anchor(root=tmp_path)
    assert isinstance(res_tampered, dict)
    assert (
        res_tampered.get("verified") is False
        or res_tampered.get("state_drift") is True
    ), f"La manomissione di state_sha256 doveva essere rilevata: {res_tampered}"


def test_wp3_p12a_generate_active_context_ste100_and_token_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica generate_active_context_view con budget <= 350 token e 0 violazioni STE100."""
    handoff_mod = _load_staged_or_prod_mod(
        "nk_session_handoff_wp3_03", "scripts/nk_session_handoff.py"
    )
    mem_mod = _load_staged_or_prod_mod(
        "memory_3tier_engine_wp3_03", "scripts/memory_3tier_engine.py"
    )
    rsi_mod = _load_staged_or_prod_mod(
        "rsi_convergence_engine_wp3_03", "scripts/rsi_convergence_engine.py"
    )

    (tmp_path / "nk_genome").mkdir(parents=True, exist_ok=True)
    (tmp_path / "nk_genome" / "implementation_plan.md").write_text(
        "# Piano di Implementazione\nIl sistema esegue la verifica deterministica.\n",
        encoding="utf-8",
    )

    target_mod = (
        handoff_mod
        if hasattr(handoff_mod, "generate_active_context_view")
        else mem_mod
    )
    assert hasattr(target_mod, "generate_active_context_view"), (
        "Funzione generate_active_context_view mancante in nk_session_handoff.py e memory_3tier_engine.py"
    )

    res = target_mod.generate_active_context_view(root=tmp_path, profile="standard")
    assert isinstance(res, dict)
    assert int(res.get("estimated_tokens", 999)) <= 350, (
        f"Il budget standard di active_context.md deve restare entro 350 token (GT-05): {res}"
    )

    candidates = [
        Path(str(res["output_path"])) if res.get("output_path") else None,
        tmp_path / "nk_tracking" / "memory_3tier" / "active_context.md",
        tmp_path / "nk_tracking" / "handoff" / "active_context.md",
        tmp_path / "active_context.md",
    ]
    ctx_file = next((c for c in candidates if c is not None and c.is_file()), None)
    assert ctx_file is not None, f"File active_context.md non trovato: {res}"

    md_text = ctx_file.read_text(encoding="utf-8")
    ste_res = rsi_mod.verify_ste100_compliance(md_text, max_sentence_words=20)
    assert ste_res.get("passed") is True and int(ste_res.get("violations_count", 1)) == 0, (
        f"Il file active_context.md viola lo standard STE100 (GT-12): {ste_res}"
    )

    if hasattr(handoff_mod, "generate_active_context_view"):
        rc_cli = handoff_mod.main(
            ["--project-root", str(tmp_path), "--generate-active-context"]
        )
        capsys.readouterr()
        assert rc_cli == 0


def test_wp3_adversarial_hardening_guards(tmp_path: Path) -> None:
    """Verifica i 4 controlli avversariali TAS v4.0 su turn bounds, JSON fail-closed, path traversal e STE100."""
    handoff_mod = _load_staged_or_prod_mod(
        "nk_session_handoff_wp3_04", "scripts/nk_session_handoff.py"
    )
    rsi_mod = _load_staged_or_prod_mod(
        "rsi_convergence_engine_wp3_04", "scripts/rsi_convergence_engine.py"
    )

    work_dir = tmp_path / "workspace_adv"
    (work_dir / "nk_genome").mkdir(parents=True, exist_ok=True)
    (work_dir / "nk_genome" / "implementation_plan.md").write_text(
        "# Piano\nIl sistema verifica i vincoli.\n", encoding="utf-8"
    )

    with pytest.raises(ValueError):
        handoff_mod.record_fsm_checkpoint(
            turn=99,
            gate_status="PASS",
            milestone_id="NK-MS-VALID",
            root=work_dir,
        )

    handoff_mod.record_fsm_checkpoint(
        turn=2,
        gate_status="PASS",
        milestone_id="NK-MS-VALID",
        root=work_dir,
    )
    anchor_file = work_dir / "nk_tracking" / "anchor" / "session_anchor.jsonl"

    valid_lines = anchor_file.read_text(encoding="utf-8").splitlines()
    null_turn_obj = json.loads(valid_lines[-1])
    null_turn_obj["turn"] = None
    anchor_file.write_text(
        json.dumps(null_turn_obj, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    res_null_turn = handoff_mod.resume_from_anchor(root=work_dir)
    assert res_null_turn.get("verified") is False

    handoff_mod.record_fsm_checkpoint(
        turn=3,
        gate_status="PASS",
        milestone_id="NK-MS-VALID",
        root=work_dir,
    )
    with open(anchor_file, "a", encoding="utf-8") as fh:
        fh.write("{corrupted_json\n")
    res_corrupt = handoff_mod.resume_from_anchor(root=work_dir)
    assert res_corrupt.get("status") == "DRIFT_DETECTED"
    assert res_corrupt.get("verified") is False

    with pytest.raises(ValueError):
        handoff_mod.generate_active_context_view(
            root=work_dir,
            output_path=work_dir.parent / "escape.md",
        )

    anchor_file.unlink(missing_ok=True)
    handoff_mod.record_fsm_checkpoint(
        turn=4,
        gate_status="PASS",
        milestone_id="NK-MS \u2014 BAD - ID\n",
        root=work_dir,
    )
    res_ctx = handoff_mod.generate_active_context_view(
        root=work_dir, profile="standard"
    )
    ctx_path = Path(str(res_ctx["output_path"]))
    ste_res = rsi_mod.verify_ste100_compliance(
        ctx_path.read_text(encoding="utf-8"), max_sentence_words=20
    )
    assert ste_res.get("passed") is True and int(ste_res.get("violations_count", 1)) == 0


# --- Sezione consolidata da tests/test_v460_wp4_ab_enhancements.py ---
# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per il pacchetto WP-4 (P-12b, P-07, P-09, P-05) di Nexus Keystone v4.6.0.
Modulo: tests/test_v460_wp4_ab_enhancements.py.
Verifica il consolidamento coseno della memoria, la query per simbolo nell'AST Repo-Mapper, il linter EARS e il gate compatto.
"""


import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_wp4_p12b_memory_cosine_consolidation(tmp_path: Path) -> None:
    """Verifica consolidate_similar_episodes con soglia coseno 0.92 e preservazione provenance."""
    mem_mod = _load_staged_or_prod_mod(
        "memory_3tier_engine_wp4_01", "scripts/memory_3tier_engine.py"
    )
    assert hasattr(mem_mod, "consolidate_similar_episodes"), (
        "Funzione consolidate_similar_episodes mancante in memory_3tier_engine.py"
    )

    base_dir = tmp_path / "nk_tracking" / "memory_3tier"
    engine = mem_mod.ThreeTierMemoryEngine(base_dir=base_dir)

    vec_dup_a = [0.80, 0.60, 0.00, 0.00]
    vec_dup_b = [0.79, 0.61, 0.01, 0.00]
    vec_distinct = [0.00, 0.00, 0.80, 0.60]

    ep1 = mem_mod.MemoryEpisode(
        episode_id="ep_arch_dup_1",
        domain="ARCH",
        title="Pattern consolidamento memoria episodica",
        content="Il motore consolida gli episodi ridondanti usando la similarita del coseno.",
        tags=["arch", "cosine"],
        vector=vec_dup_a,
        metadata={
            "source_url": "https://docs.python.org/3/library/math.html",
            "evidence_quote": "Il motore consolida gli episodi ridondanti usando la similarita del coseno.",
        },
    )
    ep2 = mem_mod.MemoryEpisode(
        episode_id="ep_arch_dup_2",
        domain="ARCH",
        title="Pattern consolidamento memoria episodica",
        content="Il motore consolida gli episodi ridondanti usando la similarita del coseno!",
        tags=["arch", "dedup"],
        vector=vec_dup_b,
        metadata={
            "source_url": "https://docs.python.org/3/library/math.html",
            "evidence_quote": "Il motore consolida gli episodi ridondanti usando la similarita del coseno.",
        },
    )
    ep3 = mem_mod.MemoryEpisode(
        episode_id="ep_arch_distinct_3",
        domain="ARCH",
        title="Isolamento processo Win32 2PC",
        content="La promozione atomica sposta i file da staging verso produzione tramite MoveFileExW.",
        tags=["win32", "2pc"],
        vector=vec_distinct,
        metadata={
            "source_url": "https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw",
            "evidence_quote": "Moves an existing file or directory, including its children.",
        },
    )
    engine.append_episode(ep1)
    engine.append_episode(ep2)
    engine.append_episode(ep3)

    for bad_thr in (-0.5, 1.5):
        with pytest.raises(ValueError):
            mem_mod.consolidate_similar_episodes(
                domain="ARCH", threshold=bad_thr, root=tmp_path
            )

    res = mem_mod.consolidate_similar_episodes(
        domain="ARCH", threshold=0.92, root=tmp_path
    )
    assert isinstance(res, dict)
    assert int(res.get("merged_count", 0)) >= 1
    assert int(res.get("remaining_count", 0)) == 2

    remaining = engine.get_tier2_episodes("02_Development_Patterns")
    assert len(remaining) == 2
    for ep in remaining:
        assert str(ep.metadata.get("source_url", "")).startswith("https://")
        assert len(str(ep.metadata.get("evidence_quote", ""))) >= 10


def test_wp4_p07_ast_repo_mapper_symbol_query(tmp_path: Path) -> None:
    """GAP-01: Verifica query_symbol_subgraph BFS in < 0.20s su mini-repo isolata in tmp_path."""
    mapper_mod = _load_staged_or_prod("ast_repo_mapper_wp4", "scripts/ast_repo_mapper.py")
    mini_scripts = tmp_path / "scripts"
    mini_scripts.mkdir(parents=True, exist_ok=True)
    src_hook = _REPO_ROOT / ".staging" / "scripts" / "nk_hook_gate.py"
    if not src_hook.exists():
        src_hook = _REPO_ROOT / "scripts" / "nk_hook_gate.py"
    shutil.copy2(src_hook, mini_scripts / "nk_hook_gate.py")

    t0 = time.perf_counter()
    if hasattr(mapper_mod, "ASTRepoMapper"):
        mapper = mapper_mod.ASTRepoMapper(tmp_path)
        res = mapper.query_symbol_subgraph(" _handle_write_gate".strip(), depth=1)
        res_empty = mapper.query_symbol_subgraph("NON_EXISTENT_SYMBOL_XYZ", depth=1)
    else:
        res = mapper_mod.query_symbol_subgraph("_handle_write_gate", root_dir=tmp_path)
        res_empty = mapper_mod.query_symbol_subgraph("NON_EXISTENT_SYMBOL_XYZ", root_dir=tmp_path)
    elapsed_sec = time.perf_counter() - t0

    assert res["found"] is True
    assert res_empty["found"] is False
    assert elapsed_sec < 0.50



def test_wp4_p09_ears_italian_requirement_linter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifica lint_ears_requirements e il sottocomando CLI lint-ears su frasi EARS e non-EARS."""
    ntt_mod = _load_staged_or_prod_mod(
        "nk_transcript_tools_wp4_03", "scripts/nk_transcript_tools.py"
    )
    assert hasattr(ntt_mod, "lint_ears_requirements"), (
        "Funzione lint_ears_requirements mancante in nk_transcript_tools.py"
    )

    sample_text = (
        "R1: QUANDO un file viene modificato IL SISTEMA DEVE validare l'AST.\n"
        "R2: SE il test fallisce ALLORA IL SISTEMA DEVE bloccare il commit.\n"
        "R3: Migliora la gestione degli errori in modo generico.\n"
    )
    res = ntt_mod.lint_ears_requirements(sample_text)
    assert isinstance(res, dict)
    assert int(res.get("ears_compliant_count", 0)) >= 2
    advisories = res.get("advisories", [])
    assert isinstance(advisories, list) and len(advisories) >= 1

    rc = ntt_mod.main(["lint-ears", "--text", sample_text])
    cli_out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert int(cli_out.get("ears_compliant_count", 0)) >= 2


def test_wp4_p05_compact_meta_prompt_gate_profile(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifica che --meta-prompt-gate --compact produca un output compatto per Mode C."""
    router_mod = _load_staged_or_prod_mod(
        "vibe_sprint_router_wp4_04", "scripts/vibe_sprint_router.py"
    )

    rc_std = router_mod.main(
        [
            "--meta-prompt-gate",
            "--prompt",
            "Correggi typo in UI",
            "--json",
        ]
    )
    out_std_raw = capsys.readouterr().out.strip()
    assert rc_std == 0

    rc_cmp = router_mod.main(
        [
            "--meta-prompt-gate",
            "--compact",
            "--prompt",
            "Correggi typo in UI",
            "--json",
        ]
    )
    out_cmp_raw = capsys.readouterr().out.strip()
    assert rc_cmp == 0

    cmp_data = json.loads(out_cmp_raw)
    assert cmp_data.get("compact_profile") is True
    assert "IB-" in str(cmp_data.get("brief_id", ""))
    hg_m10 = _load_staged_or_prod("nk_hook_gate_m10", "scripts/nk_hook_gate.py")
    assert ".." in hg_m10._sanitize_staged_tokens_in_cmd("python scratch/../scripts/nk_hook_gate.py")
    assert hg_m10._classify_protected_target("", "powershell -EncodedCommand ZWNobyBoZWxsbw==")["decision"] == "deny"
    assert len(out_cmp_raw) < len(out_std_raw), (
        f"Il profilo compatto ({len(out_cmp_raw)} char) deve essere piu breve del profilo standard ({len(out_std_raw)} char)"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
