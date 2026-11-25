# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per governance NK Proget/Locale e sola lettura NK Proget/Online.
Modulo: tests/test_nk_proget_locale_online_governance.py.
Copre CRIT-01, CRIT-02 e allineamento HIGH-07 di runner, bootstrap, cleanup e compliance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

hook_gate_mod = load_nk_script_module("nk_hook_gate")
tpc_mod = load_nk_script_module("win32_2pc_engine")
scaffolder_mod = load_nk_script_module("external_project_scaffolder")
cleanup_mod = load_nk_script_module("safe_cleanup_dev_servers")


def _mk_dirs(base: Path, *subs: str) -> Path:
    """Crea la directory radice e le sottodirectory specificate."""
    base.mkdir(parents=True, exist_ok=True)
    for sub in subs:
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def _build_synthetic_ecosystem(base_dir: Path) -> Dict[str, Path]:
    """Costruisce un ecosistema sintetico Antigravity + NK Proget in tmp_path."""
    drive = base_dir / "Drive"
    hub_dir = _mk_dirs(drive / "Antigravity" / "NK_Hub", "scripts", ".staging", "nk_tracking", "nk_genome")
    proget_dir = drive / "NK Proget"
    locale_dir = _mk_dirs(proget_dir / "Locale")
    online_dir = _mk_dirs(proget_dir / "Online")
    locale_bandi = _mk_dirs(locale_dir / "NK-Bandi", ".staging", "src_app", "nk_genome", "nk_tracking")
    online_bandi = _mk_dirs(online_dir / "NK-Bandi", ".staging", "src_app", "nk_genome", "nk_tracking")
    legacy_app = _mk_dirs(drive / "Antigravity" / "NK_External_Projects" / "LegacyApp", "nk_genome", "nk_tracking")
    return {
        "drive": drive,
        "hub": hub_dir,
        "proget": proget_dir,
        "locale_root": locale_dir,
        "online_root": online_dir,
        "locale_bandi": locale_bandi,
        "online_bandi": online_bandi,
        "legacy_app": legacy_app,
    }


def _assert_path_predicates(nk_paths: object) -> None:
    """Verifica i predicati path per Online, Locale e staging esterno."""
    online_cases = (
        "G:/Il mio Drive/NK Proget/Online/NK-Bandi/src_app/a.py",
        r"G:\Il mio Drive\NK Proget\Online\NK-Bandi\src_app\a.py",
        r"\\?\G:\Il mio Drive\nk proget\online\NK-Bandi\a.py",
        "G:/Il mio Drive/NK Proget/Online/NK-Bandi/.staging/a.py",
        "G:/Il mio Drive/NK Proget/Online/NK Proget/Locale/a.py",
    )
    locale_direct = "G:/Il mio Drive/NK Proget/Locale/NK-Bandi/src_app/a.py"
    locale_staged = "G:/Il mio Drive/NK Proget/Locale/NK-Bandi/.staging/src_app/a.py"
    locale_root_staged = "G:/Il mio Drive/NK Proget/Locale/.staging/a.py"
    legacy_staged = "G:/Il mio Drive/Antigravity/NK_External_Projects/Demo/.staging/a.py"
    online_staged = "G:/Il mio Drive/NK Proget/Online/NK-Bandi/.staging/a.py"
    nested_spoof = "G:/Il mio Drive/NK Proget/Online/NK Proget/Locale/a.py"

    assert [nk_paths.is_nk_proget_online_path(p) for p in online_cases] == [True] * 5  # type: ignore[attr-defined]
    assert (
        nk_paths.is_nk_proget_online_path(locale_direct),  # type: ignore[attr-defined]
        nk_paths.is_nk_proget_locale_path(locale_direct),  # type: ignore[attr-defined]
        nk_paths.is_nk_proget_locale_path(online_cases[0]),  # type: ignore[attr-defined]
        nk_paths.is_nk_proget_locale_path(nested_spoof),  # type: ignore[attr-defined]
    ) == (False, True, False, False)
    assert (
        nk_paths.is_external_projects_staging_path(locale_staged),  # type: ignore[attr-defined]
        nk_paths.is_external_projects_staging_path(legacy_staged),  # type: ignore[attr-defined]
        nk_paths.is_external_projects_staging_path(locale_direct),  # type: ignore[attr-defined]
        nk_paths.is_external_projects_staging_path(locale_root_staged),  # type: ignore[attr-defined]
        nk_paths.is_external_projects_staging_path(online_staged),  # type: ignore[attr-defined]
    ) == (True, True, False, False, False)


def _assert_cmd_mention_predicates(nk_paths: object) -> None:
    """Verifica il rilevamento testuale dei comandi verso Online, Locale e legacy."""
    assert (
        nk_paths.cmd_mentions_nk_proget_online('Set-Content "G:/NK Proget/Online/NK-Bandi/a.py" x'),  # type: ignore[attr-defined]
        nk_paths.cmd_mentions_nk_proget_online('Get-Content "G:/NK Proget/Locale/NK-Bandi/a.py"'),  # type: ignore[attr-defined]
        nk_paths.cmd_mentions_nk_proget_locale('dir "G:/NK Proget/Locale/NK-Bandi"'),  # type: ignore[attr-defined]
        nk_paths.cmd_mentions_nk_proget_locale('dir "G:/NK Proget/Online/NK-Bandi"'),  # type: ignore[attr-defined]
        nk_paths.cmd_mentions_external_project('cat "G:/NK Proget/Locale/NK-Bandi/a.py"'),  # type: ignore[attr-defined]
        nk_paths.cmd_mentions_external_project('cat "G:/NK_External_Projects/Demo/a.py"'),  # type: ignore[attr-defined]
        nk_paths.cmd_mentions_external_project("cat NK_Hub/README.md"),  # type: ignore[attr-defined]
    ) == (True, False, True, False, True, True, False)


@pytest.mark.fast
def test_paths_nk_proget_classification_and_root_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica classificazione Online/Locale/staging e risoluzione root NK Proget."""
    from _internal.nk_common import paths as nk_paths

    _assert_path_predicates(nk_paths)
    _assert_cmd_mention_predicates(nk_paths)

    eco = _build_synthetic_ecosystem(tmp_path)
    custom_proget = _mk_dirs(tmp_path / "CustomRoot", "Locale", "Online")
    monkeypatch.setenv("NK_PROGET_ROOT", str(custom_proget))
    loc_env, onl_env = nk_paths.resolve_nk_proget_roots(eco["hub"])
    assert (loc_env, onl_env) == (
        (custom_proget / "Locale").resolve(),
        (custom_proget / "Online").resolve(),
    )

    monkeypatch.delenv("NK_PROGET_ROOT", raising=False)
    loc_disc, onl_disc = nk_paths.resolve_nk_proget_roots(eco["hub"])
    assert (loc_disc, onl_disc) == (
        eco["locale_root"].resolve(),
        eco["online_root"].resolve(),
    )


@pytest.mark.integration
def test_crit01_online_readonly_blocks_hooks_2pc_and_scaffolder(tmp_path: Path) -> None:
    """Verifica blocco fail-closed CRIT-01 su hook gate, 2PC promoter e scaffolder per Online."""
    eco = _build_synthetic_ecosystem(tmp_path)
    hub_dir = eco["hub"]
    online_repo = eco["online_bandi"]
    online_direct = online_repo / "src_app" / "main.py"
    online_staged = online_repo / ".staging" / "src_app" / "main.py"

    for tgt in (online_direct, online_staged):
        res_t = hook_gate_mod._handle_write_gate({}, hub_dir, False, str(tgt), "", "")
        assert res_t.get("decision") == "deny"
        assert res_t.get("reason_code") == "NK_PROGET_ONLINE_READONLY"

    onl_posix = online_repo.as_posix()
    onl_stg_posix = online_staged.as_posix()
    mutating_cmds = (
        f'echo hi > "{onl_posix}/a.txt"',
        f'Set-Content -Path "{onl_posix}/a.txt" -Value "x"',
        f'python -B -u NK_Hub/scripts/win32_2pc_engine.py --promote-staging --repo-root "{onl_posix}"',
        f'python -B -u NK_Hub/scripts/external_project_scaffolder.py --name X --target "{onl_posix}"',
        f'git -C "{onl_posix}" commit -m "blocked"',
        f'python -B -u NK_Hub/scripts/nk_transcript_tools.py oracle-lock freeze --root "{onl_posix}"',
        f'python -B -u -c "open(r\'{onl_stg_posix}\', \'w\').write(\'x\')"',
    )
    for cmd in mutating_cmds:
        res_c = hook_gate_mod._handle_write_gate({}, hub_dir, False, "", cmd, "")
        assert res_c.get("decision") == "deny"
        assert res_c.get("reason_code") == "NK_PROGET_ONLINE_READONLY"

    mcp_payload = {
        "tool_name": "call_mcp_tool",
        "arguments": {
            "ServerName": "fs",
            "ToolName": "read_file",
            "Arguments": {"Path": str(online_direct)},
        },
    }
    res_mcp = hook_gate_mod._handle_write_gate(mcp_payload, hub_dir, False, "", "", "")
    assert res_mcp.get("decision") == "deny"
    assert res_mcp.get("reason_code") == "NK_PROGET_ONLINE_READONLY"

    ro_cmds = (
        f'git -C "{onl_posix}" status',
        f'git -C "{onl_posix}" fsck',
        f'Get-Content "{onl_posix}/README.md"',
    )
    for ro_cmd in ro_cmds:
        assert hook_gate_mod._handle_write_gate({}, hub_dir, False, "", ro_cmd, "") == {}

    with pytest.raises(tpc_mod.TwoPhaseCommitError, match="NK_PROGET_ONLINE_READONLY"):
        tpc_mod.promote_staging_to_production(repo_root=online_repo, milestone="TEST")

    with pytest.raises(ValueError, match="NK_PROGET_ONLINE_READONLY"):
        scaffolder_mod.ExternalProjectScaffolder(project_name="NK-Bandi", target_dir=online_repo)


@pytest.mark.fast
def test_crit02_locale_staging_allowed_and_unstaged_denied(tmp_path: Path) -> None:
    """Verifica CRIT-02: consente .staging/ in Locale e nega scritture dirette non staged."""
    from _internal.nk_hook_gate.mcp_classifier import _check_mcp_candidate_path
    from _internal.nk_hook_gate.shell_ast_paths import _arg_targets_protected_outside_staging

    eco = _build_synthetic_ecosystem(tmp_path)
    hub_dir = eco["hub"]
    locale_repo = eco["locale_bandi"]
    online_repo = eco["online_bandi"]

    locale_staged = locale_repo / ".staging" / "src_app" / "fix.py"
    locale_direct = locale_repo / "src_app" / "fix.py"
    online_staged = online_repo / ".staging" / "src_app" / "fix.py"

    assert hook_gate_mod._handle_write_gate({}, hub_dir, False, str(locale_staged), "", "") == {}
    res_dir = hook_gate_mod._handle_write_gate({}, hub_dir, False, str(locale_direct), "", "")
    assert res_dir.get("decision") == "deny"

    py_ok = f'python -B -u -c "open(r\'{locale_staged.as_posix()}\', \'w\').write(\'x\')"'
    py_bad = f'python -B -u -c "open(r\'{locale_direct.as_posix()}\', \'w\').write(\'x\')"'
    assert hook_gate_mod._handle_write_gate({}, hub_dir, False, "", py_ok, "") == {}
    assert hook_gate_mod._handle_write_gate({}, hub_dir, False, "", py_bad, "").get("decision") == "deny"

    hub_res = hub_dir.resolve()
    assert _check_mcp_candidate_path(str(locale_staged), hub_dir, hub_res, hub_res, hub_res) is None
    mcp_bad = _check_mcp_candidate_path(str(locale_direct), hub_dir, hub_res, hub_res, hub_res)
    assert isinstance(mcp_bad, dict) and mcp_bad.get("decision") == "deny"

    assert _arg_targets_protected_outside_staging(str(locale_staged), hub_dir) is False
    assert _arg_targets_protected_outside_staging(str(locale_direct), hub_dir) is True
    assert _arg_targets_protected_outside_staging(str(online_staged), hub_dir) is True


@pytest.mark.fast
def test_high07_isolated_runner_blueprints_and_locale_siblings(tmp_path: Path) -> None:
    """Verifica HIGH-07: mirror blueprint numerati e progetti fratelli sotto Locale."""
    from _internal.nk_common import isolated_test_runner as itr

    eco = _build_synthetic_ecosystem(tmp_path)
    locale_dir = eco["locale_root"]
    online_dir = eco["online_root"]
    cloud_repo = _mk_dirs(locale_dir / "NK-Cloud-Platform", "01_Architettura_Generale", "tests")
    (cloud_repo / "01_Architettura_Generale" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (cloud_repo / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")

    bandi_mod = eco["locale_bandi"] / "src_app" / "mod.py"
    bandi_mod.write_text("VALUE = 1\n", encoding="utf-8")

    mirror_dir = itr.mirror_workspace_to_nvme(cloud_repo, apply_overlay=False, mirror_siblings=True)
    try:
        assert (mirror_dir / "01_Architettura_Generale" / "spec.md").is_file() is True
        assert (mirror_dir.parent / "NK-Bandi" / "src_app" / "mod.py").is_file() is True
        assert itr._is_sibling_projects_parent(locale_dir) is True
        assert itr._is_sibling_projects_parent(online_dir) is False
    finally:
        itr.safe_rmtree(mirror_dir.parent)


@pytest.mark.fast
def test_high07_ecosystem_scanner_and_handoff_verify_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica HIGH-07: scanner ecosistema, scope handoff_verify e default scaffolder."""
    from _internal.external_project_scaffolder import scaffolder_cli as sc_cli
    from _internal.nk_session_bootstrap import handoff_verify as hv
    from _internal.nk_session_bootstrap import handoff_verify_io as hvio
    from _internal.nk_session_handoff import ecosystem_scanner as eco_scan

    monkeypatch.delenv("NK_PROGET_ROOT", raising=False)
    eco = _build_synthetic_ecosystem(tmp_path)
    hub_res = eco["hub"].resolve()
    locale_bandi = eco["locale_bandi"].resolve()
    online_bandi = eco["online_bandi"].resolve()
    legacy_app = eco["legacy_app"].resolve()

    assert eco_scan.resolve_hub_and_project_roots(eco["locale_bandi"]) == (hub_res, locale_bandi)

    discovered = eco_scan.discover_ecosystem_repos(eco["hub"], eco["hub"], True)
    assert hub_res in discovered
    assert locale_bandi in discovered
    assert legacy_app in discovered
    assert online_bandi not in discovered

    allowed = hv._build_allowed_repo_roots(hub_res, hub_res)
    assert len(allowed) == 4
    assert hvio._is_repo_root_in_scope(locale_bandi, allowed) is True
    assert hvio._is_repo_root_in_scope(online_bandi, allowed) is False
    assert hvio._is_repo_root_in_scope(legacy_app, allowed[:3]) is True
    assert hvio._is_repo_root_in_scope(online_bandi, allowed[:3]) is False

    assert sc_cli._resolve_default_external_root(eco["hub"]) == eco["locale_root"].resolve()


@pytest.mark.fast
def test_high07_cleanup_ports_and_compliance_scanners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica HIGH-07: porta 8090, filtro win32_proc e scanner compliance Locale/Online."""
    from _internal.nk_compliance_checker import transcript_scan as tscan
    from _internal.nk_transcript_tools import locate_and_compliance as loc
    from _internal.safe_cleanup_dev_servers import win32_proc as wp

    monkeypatch.delenv("NK_PROGET_ROOT", raising=False)
    eco = _build_synthetic_ecosystem(tmp_path)
    hub_dir = eco["hub"]
    locale_crm = _mk_dirs(eco["locale_root"] / "NK-Studio-CRM")
    online_crm = _mk_dirs(eco["online_root"] / "NK-Studio-CRM")

    assert 8090 in wp.TARGET_PORTS
    monkeypatch.setattr(cleanup_mod, "_workspace_root", hub_dir, raising=False)
    cmd_loc_crm = f"python {str(locale_crm).lower()}\\app.py"
    cmd_onl_crm = f"python {str(online_crm).lower()}\\app.py"
    assert wp._matches_workspace_paths("python.exe", cmd_loc_crm, "", "", None) is True
    assert wp._matches_workspace_paths("python.exe", cmd_loc_crm, "", "", hub_dir) is True
    assert wp._matches_workspace_paths("python.exe", cmd_onl_crm, "", "", None) is False

    assert tscan._is_external_unstage_write("G:/Il mio Drive/NK Proget/Online/NK-Bandi/.staging/a.py", False) is True
    assert tscan._is_external_unstage_write('Set-Content "G:/NK Proget/Online/NK-Bandi/a.py" x', True) is True
    assert tscan._is_external_unstage_write('git -C "G:/NK Proget/Online/NK-Bandi" status', True) is False
    assert tscan._is_external_unstage_write("G:/Il mio Drive/NK Proget/Locale/NK-Bandi/src_app/a.py", False) is True
    assert tscan._is_external_unstage_write("G:/Il mio Drive/NK Proget/Locale/NK-Bandi/.staging/src_app/a.py", False) is False

    tr_ok = tmp_path / "tr_ok.jsonl"
    tr_ok.write_text(
        json.dumps({
            "step_index": 0,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [{"name": "write_file", "arguments": {"Path": "G:/Il mio Drive/NK Proget/Locale/NK-Bandi/.staging/src_app/a.py"}}],
        }) + "\n",
        encoding="utf-8",
    )
    assert loc.analyze_compliance(tr_ok)["external_writes_outside_staging"] == 0

    tr_bad = tmp_path / "tr_bad.jsonl"
    tr_bad.write_text(
        "\n".join([
            json.dumps({
                "step_index": 0,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "write_file", "arguments": {"Path": "G:/Il mio Drive/NK Proget/Online/NK-Bandi/.staging/src_app/a.py"}}],
            }),
            json.dumps({
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "write_file", "arguments": {"Path": "G:/Il mio Drive/NK Proget/Locale/NK-Bandi/src_app/a.py"}}],
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    res_bad = loc.analyze_compliance(tr_bad)
    assert res_bad["external_writes_outside_staging"] == 2
    assert res_bad["passed"] is False


def _assert_shell_write_bypasses(hub_dir: Path) -> None:
    """Verifica blocco write gate su powershell posizionale/multi-arg, stdin pipe e scriptblock."""
    shell_write_bypass_cmds = (
        'powershell -NoProfile "echo x > scripts/pwn.py"',
        r'''C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile "echo x > scripts/pwn.py"''',
        'pwsh -NoProfile { echo x > scripts/pwn.py }',
        'echo "echo x > scripts/pwn.py" | powershell -Command -',
        'echo "echo x > scripts/pwn.py" | pwsh -c -',
        'echo "echo x > scripts/pwn.py" | powershell -NoProfile -',
        'echo "echo x > scripts/pwn.py" | cmd',
        'powershell -NoProfile -Command - < payload.txt',
        'powershell -NoProfile "echo ok;" "echo x > scripts/pwn.py"',
        'powershell -Command "echo ok;" "echo x > scripts/pwn.py"',
        'powershell -Command:"echo ok;" "echo x > scripts/pwn.py"',
        'echo "echo x > scripts/pwn.py" | &"powershell"',
        'echo "echo x > scripts/pwn.py" | &"pwsh"',
        'echo "echo x > scripts/pwn.py" | &"cmd.exe"',
        '&"powershell" -NoProfile "echo ok;" "echo x > scripts/pwn.py"',
    )
    for sw_cmd in shell_write_bypass_cmds:
        res_sw = hook_gate_mod._handle_write_gate({}, hub_dir, False, "", sw_cmd, "")
        assert res_sw.get("decision") == "deny"


@pytest.mark.fast
def test_crit01_online_cd_redirection_bypass_and_mcp_space_paths(
    tmp_path: Path,
) -> None:
    """Verifica blocco CRIT-01 su bypass cd+redirezione, cmd/powershell posizionale/stdin e path MCP."""
    from _internal.nk_hook_gate.mcp_classifier import _extract_mcp_candidate_paths

    eco = _build_synthetic_ecosystem(tmp_path)
    hub_dir = eco["hub"]

    bypass_cmds = (
        r'cd /d "G:\Il mio Drive\NK Proget\Online\NK-Bandi" && echo x > .staging/pwn.py',
        r'cd /d "G:\Il mio Drive\NK Proget\Online\NK-Bandi" && echo x > README.md',
        'powershell -Command "Set-Location \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\'; echo x > .staging/pwn.py"',
        r'''cmd /c "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''cmd /d /c "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''cmd.exe /q /s /d /c "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > README.md" && echo ok''',
        'powershell -NoProfile -Command "cmd /d /c \\"cd /d \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\' && echo x > .staging/pwn.py\\""',
        r'cmd /d /c copy "G:\Il mio Drive\NK Proget\Locale\NK-Bandi\README.md" "G:\Il mio Drive\NK Proget\Online\NK-Bandi\README.md"',
        'python -B -u NK_Hub/scripts/nk_transcript_tools.py oracle-lock verify --root "G:/Il mio Drive/NK Proget/Online/NK-Bandi" --output "G:/Il mio Drive/NK Proget/Online/NK-Bandi/out.json"',
        r'''cmd /c"cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''cmd /d/c "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''cmd/d/c"cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > README.md"''',
        r'''cmd /d/c"copy 'G:\Il mio Drive\NK Proget\Locale\NK-Bandi\README.md' 'G:\Il mio Drive\NK Proget\Online\NK-Bandi\README.md'"''',
        'powershell -Command:"Set-Location \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\'; echo x > .staging/pwn.py"',
        'pwsh -NoProfile -c:"cmd /d/c\\"cd /d \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\' && echo x > .staging/pwn.py\\""',
        r'''C:\Windows\System32\cmd.exe /c "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''C:\Windows\System32\cmd.exe /d/c"copy 'G:\Il mio Drive\NK Proget\Locale\NK-Bandi\README.md' 'G:\Il mio Drive\NK Proget\Online\NK-Bandi\README.md'"''',
        r'''"cmd.exe" /c "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''& "C:\Windows\System32\cmd.exe" /d/c"cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > README.md"''',
        'powershell -Command "cmd /d/c\\"cd /d \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\' && echo x > .staging/pwn.py\\" && echo ok"',
        'powershell -Command "cmd /c `"cd /d \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\' && echo x > .staging/pwn.py`""',
        'powershell -Command "cmd /c `"cd /d \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\' && echo x > .staging/pwn.py`" && echo ok"',
        r'''cmd /r "cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        r'''%COMSPEC% /c"cd /d 'G:\Il mio Drive\NK Proget\Online\NK-Bandi' && echo x > .staging/pwn.py"''',
        'powershell -NoProfile "Set-Location \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\'; echo x > .staging/pwn.py"',
        'pwsh -EP Bypass -NoLogo -NoP "Set-Location \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\'; echo x > .staging/pwn.py"',
        r'cd /d "G:\Il mio Drive\NK Proget\.\Online\NK-Bandi" && echo x > .staging/pwn.py',
        r'cd /d "G:\Il mio Drive\NK Proget\Locale\..\Online\NK-Bandi" && echo x > .staging/pwn.py',
        r'cd /d "G:\Il mio Drive\NK Proget\Locale\NK-Bandi" && cd ..\..\Online\NK-Bandi && echo x > .staging/pwn.py',
        r'cd /d "G:\Il mio Drive\NK Proget\Online.\NK-Bandi" && echo x > .staging/pwn.py',
        'echo "Set-Location \'G:\\Il mio Drive\\NK Proget\\Online\\NK-Bandi\'; echo x > .staging/pwn.py" | powershell -Command -',
        'powershell -NoProfile "Set-Location \'G:\\Il mio Drive\\NK Proget\\Locale\\NK-Bandi\';" "Set-Location ..\\..\\Online\\NK-Bandi; echo x > .staging/pwn.py"',
        'powershell -Command "Set-Location \'G:\\Il mio Drive\\NK Proget\\Locale\\NK-Bandi\';" "Set-Location ..\\..\\Online\\NK-Bandi; echo x > .staging/pwn.py"',
    )
    for b_cmd in bypass_cmds:
        res_b = hook_gate_mod._handle_write_gate({}, hub_dir, False, "", b_cmd, "")
        assert res_b.get("decision") == "deny"
        assert res_b.get("reason_code") == "NK_PROGET_ONLINE_READONLY"

    _assert_shell_write_bypasses(hub_dir)

    ro_null_cmds = (
        'git -C "G:/Il mio Drive/NK Proget/Online/NK-Bandi" status 2>nul',
        'cmd /d /c "git -C \'G:/Il mio Drive/NK Proget/Online/NK-Bandi\' status 2>nul"',
        'cmd /d/c"git -C \'G:/Il mio Drive/NK Proget/Online/NK-Bandi\' status 2>nul"',
        r'''C:\Windows\System32\cmd.exe /r "git -C 'G:/Il mio Drive/NK Proget/Online/NK-Bandi' status 2>nul" && echo ok''',
        'powershell -NoProfile "git -C \'G:/Il mio Drive/NK Proget/Online/NK-Bandi\' status 2>nul"',
        r'cd /d "G:\Il mio Drive\NK Proget\.\Online\NK-Bandi" && git status 2>nul',
    )
    for ro_null_cmd in ro_null_cmds:
        assert hook_gate_mod._handle_write_gate({}, hub_dir, False, "", ro_null_cmd, "") == {}

    assert _extract_mcp_candidate_paths({"note": "NK Proget/Online/NK-Bandi/src_app/a.py"}) == [
        "NK Proget/Online/NK-Bandi/src_app/a.py"
    ]
    assert _extract_mcp_candidate_paths({"note": "Il mio Drive/NK Proget/Online/NK-Bandi/a.py"}) == [
        "Il mio Drive/NK Proget/Online/NK-Bandi/a.py"
    ]

    mcp_space_payload = {
        "tool_name": "call_mcp_tool",
        "arguments": {
            "ServerName": "fs",
            "ToolName": "read_file",
            "Arguments": {"note": "NK Proget/Online/NK-Bandi/src_app/a.py"},
        },
    }
    res_mcp = hook_gate_mod._handle_write_gate(mcp_space_payload, hub_dir, False, "", "", "")
    assert res_mcp.get("decision") == "deny"
    assert res_mcp.get("reason_code") == "NK_PROGET_ONLINE_READONLY"
