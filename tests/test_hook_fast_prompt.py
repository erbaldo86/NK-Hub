# -*- coding: utf-8 -*-
"""
Golden Test GT-NEW-02 v6.4.0-Carbon: Thresholds ACS, Fastpath -S e Sicurezza Hook/Prompt.
Modulo: tests/test_hook_fast_prompt.py.
Zero mock/stub; verifica saturation_thresholds, execution -S -B -u, MCP classifier e prompt masking.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main_captured,
        load_script_by_relpath as _load_mod,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main_captured,
        load_script_by_relpath as _load_mod,
    )

acs_mod = _load_mod("nk_acs_fastguard", "scripts/nk_acs_fastguard.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")


def _resolve_script(rel_path: str) -> Path:
    stg = _WORKSPACE_ROOT / ".staging" / rel_path
    return stg if stg.is_file() else (_WORKSPACE_ROOT / rel_path)


@pytest.mark.integration
def test_saturation_thresholds_and_minimal_python_subprocess(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica saturation_thresholds.json (160k/185k/205k, 120/150/180) e avvio reale python -S -B -u."""
    assert isolated_nk_env.is_dir() and tmp_path.is_dir()
    thresh_path = _resolve_script("nk_genome/configs/saturation_thresholds.json")
    assert thresh_path.is_file()
    acs_section = json.loads(thresh_path.read_text(encoding="utf-8"))["autonomous_context_shield"]
    assert acs_section["z1_tokens"] == 160000 and acs_section["z2_tokens"] == 185000 and acs_section["z3_tokens"] == 205000
    assert acs_section["z1_steps"] == 120 and acs_section["z2_steps"] == 150 and acs_section["z3_steps"] == 180

    loaded = acs_mod._load_acs_thresholds([str(_WORKSPACE_ROOT)])
    assert loaded["z1_tokens"] == 160000 and loaded["z2_tokens"] == 185000 and loaded["z3_tokens"] == 205000
    assert loaded["z1_steps"] == 120 and loaded["z2_steps"] == 150 and loaded["z3_steps"] == 180

    acs_script = _resolve_script("scripts/nk_acs_fastguard.py")
    t0 = time.perf_counter()
    res_acs = subprocess.run(
        [sys.executable, "-S", "-B", "-u", str(acs_script), "--event", "PreInvocation", "--conversation-id", "gt_new_02_fast", "--project-root", str(_WORKSPACE_ROOT)],
        input="{}", text=True, capture_output=True, timeout=10,
    )
    elapsed_acs = time.perf_counter() - t0
    assert res_acs.returncode == 0
    assert json.loads(res_acs.stdout.strip()) == {}
    assert elapsed_acs < 3.0

    t1 = time.perf_counter()
    rc_hook, out_hook, _ = call_script_main_captured(
        hook_mod, ["probe", "--conversation-id", "gt_new_02_fast"], stdin_text="{}"
    )
    elapsed_hook = time.perf_counter() - t1
    assert rc_hook == 0
    assert json.loads(out_hook.strip()) == {}
    assert elapsed_hook < 3.0


def _make_mcp_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "mcp_ws"
    (ws / ".staging" / "scripts").mkdir(parents=True, exist_ok=True)
    (ws / "scripts").mkdir(parents=True, exist_ok=True)
    (ws / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (ws / "nk_genome").mkdir(parents=True, exist_ok=True)
    return ws


@pytest.mark.fast
def test_mcp_classifier_fail_closed_and_balanced_prompt_masking(tmp_path: Path) -> None:
    """Verifica fail-closed su _classify_mcp_tool_call per chiamate non consentite."""
    ws = _make_mcp_ws(tmp_path)

    assert hook_mod._classify_mcp_tool_call({}, ws)["decision"] == "deny"
    assert (
        hook_mod._classify_mcp_tool_call(
            {"ServerName": "custom-mcp", "ToolName": "unknown_action"}, ws
        )["decision"]
        == "deny"
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {
                "ServerName": "google-docs-mcp",
                "ToolName": "append_to_google_doc",
                "Arguments": {"document_id": "d1"},
            },
            ws,
        )["decision"]
        == "deny"
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {"ServerName": "firebase-mcp-server", "ToolName": "firebase_deploy", "Arguments": {}},
            ws,
        )["decision"]
        == "deny"
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {"ServerName": "tavily-mcp", "ToolName": "tavily_search", "Arguments": {"path": "data.txt:ads"}},
            ws,
        )["decision"]
        == "deny"
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {
                "ServerName": "tavily-mcp",
                "ToolName": "tavily_search",
                "Arguments": {"path": str(ws / "nk_tracking" / "oracle_lock.json")},
            },
            ws,
        )["decision"]
        == "deny"
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {
                "ServerName": "tavily-mcp",
                "ToolName": "tavily_search",
                "Arguments": {"path": str(ws / "scripts" / "target.py")},
            },
            ws,
        )["decision"]
        == "deny"
    )


@pytest.mark.fast
def test_mcp_classifier_allows_staging_and_readonly_tools(tmp_path: Path) -> None:
    """Verifica il permesso su tool MCP read-only e path confinati in .staging/."""
    ws = _make_mcp_ws(tmp_path)
    assert (
        hook_mod._classify_mcp_tool_call(
            {
                "ServerName": "tavily-mcp",
                "ToolName": "tavily_search",
                "Arguments": {
                    "query": "FastAPI docs",
                    "path": str(ws / ".staging" / "scripts" / "ok.py"),
                },
            },
            ws,
        )
        == {}
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {"ServerName": "google-docs-mcp", "ToolName": "read_google_doc", "Arguments": {"document_id": "doc1"}},
            ws,
        )
        == {}
    )
    assert (
        hook_mod._classify_mcp_tool_call(
            {"ServerName": "chrome-devtools-mcp", "ToolName": "take_snapshot", "Arguments": {}},
            ws,
        )
        == {}
    )


@pytest.mark.fast
def test_balanced_prompt_masking_and_write_indicators(tmp_path: Path) -> None:
    """Verifica _mask_balanced_prompt_payloads e rilevamento scritture non quotate."""
    ws = _make_mcp_ws(tmp_path)
    safe_prompt_cmd = (
        'python -u scripts/vibe_sprint_router.py --meta-prompt-gate '
        '--prompt "Analizza cp, mv, rm | del; copy && si nel prompt"'
    )
    masked = hook_mod._mask_balanced_prompt_payloads(safe_prompt_cmd, safe_prompt_cmd)
    assert '"__SAFE_PROMPT__"' in masked
    assert hook_mod._has_cmd_write_indicator(safe_prompt_cmd, ws) is False

    unquoted_chained = 'python -u scripts/vibe_sprint_router.py --prompt ok && set-content scripts/prod.py "x"'
    assert hook_mod._mask_balanced_prompt_payloads(unquoted_chained, unquoted_chained) == unquoted_chained
    assert hook_mod._has_cmd_write_indicator(unquoted_chained, ws) is True

    unquoted_redir = "python -u scripts/vibe_sprint_router.py --prompt ok > scripts/evil.py"
    assert hook_mod._has_cmd_write_indicator(unquoted_redir, ws) is True

    unbalanced_quote = 'python -u scripts/vibe_sprint_router.py --prompt "aperta rm scripts/a.py'
    assert hook_mod._has_cmd_write_indicator(unbalanced_quote, ws) is True


def test_s2b_inline_python_pwsh_trojan_and_workspace_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica S2-B: python -c / pwsh -Command, trojan scratch/*.py senza args e workspacePaths."""
    from _internal.nk_hook_gate import cli_dispatch

    ws = tmp_path / "nk_ws"
    (ws / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")

    res_py_ok = hook_mod._handle_write_gate({"tool_name": "run_command", "tool_input": {"CommandLine": "python -c \"print('a:b')\""}}, ws, False, None, None, None)
    assert res_py_ok.get("decision", "allow") == "allow"

    res_py_bad = hook_mod._handle_write_gate({"tool_name": "run_command", "tool_input": {"CommandLine": "python -c \"open('scripts/x.py','w')\""}}, ws, False, None, None, None)
    assert res_py_bad.get("decision") == "deny"

    res_pwsh_ok = hook_mod._handle_write_gate(
        {"tool_name": "run_command", "tool_input": {"CommandLine": f"pwsh -Command \"Get-Content '{(ws / '.agents' / 'AGENTS.md').as_posix()}'\""}},
        ws, False, None, None, None,
    )
    assert res_pwsh_ok.get("decision", "allow") == "allow"

    scratch_dir = tmp_path / "brain" / "scratch"
    (scratch_dir / "scripts").mkdir(parents=True)
    evil_zero = scratch_dir / "evil_zero.py"
    evil_zero.write_text(f"open(r'{(ws / 'scripts' / 'x.py').as_posix()}', 'w').write('pwn')\n", encoding="utf-8")
    res_evil = hook_mod._handle_write_gate({"tool_name": "run_command", "tool_input": {"CommandLine": f'python "{evil_zero}"'}}, ws, False, None, None, None)
    assert res_evil.get("decision") == "deny"

    trojan_2pc = scratch_dir / "scripts" / "win32_2pc_engine.py"
    res_trojan_run = hook_mod._handle_write_gate({"tool_name": "run_command", "tool_input": {"CommandLine": f'python "{trojan_2pc}"'}}, ws, False, None, None, None)
    assert res_trojan_run.get("decision") == "deny"

    ext_proj = tmp_path / "NK_External_Projects" / "DemoApp"
    ext_proj.mkdir(parents=True)
    (ext_proj / "scripts").mkdir()
    resolved = cli_dispatch._resolve_proj_root_path(None, {"workspacePaths": [str(ext_proj)]})
    assert resolved == ext_proj.resolve()
