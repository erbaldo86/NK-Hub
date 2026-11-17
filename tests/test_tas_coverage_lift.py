# -*- coding: utf-8 -*-
"""
Test Zero-Mock aggiuntivi per copertura branch TAS su hook/bridge/memory/thresholds/shards (1.0.0-Generation).
Modulo: tests/test_tas_coverage_lift.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

try:
    from conftest import WORKSPACE_ROOT, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, load_nk_script_module


@pytest.mark.fast
def test_stop_evidence_resolve_proj_root_branches(tmp_path: Path) -> None:
    """Copre _resolve_proj_root_path su raw_root, workspacePaths, projectRoot e fallback."""
    from _internal.nk_hook_gate import stop_evidence_cli as se_cli

    assert se_cli._resolve_proj_root_path(str(tmp_path)) == tmp_path.resolve()
    nk_parent = tmp_path / "parent_ws"
    (nk_parent / "NK_Hub" / "scripts").mkdir(parents=True)
    assert se_cli._resolve_proj_root_path(None, {"workspacePaths": ["", str(nk_parent)]}) == (nk_parent / "NK_Hub").resolve()

    direct_ws = tmp_path / "direct_ws"
    (direct_ws / ".staging").mkdir(parents=True)
    assert se_cli._resolve_proj_root_path(None, {"projectRoot": str(direct_ws)}) == direct_ws.resolve()

    plain_dir = tmp_path / "plain_only"
    plain_dir.mkdir(parents=True)
    assert se_cli._resolve_proj_root_path(None, {"cwd": str(plain_dir)}) == plain_dir.resolve()
    assert se_cli._resolve_proj_root_path(None, {"project_root": str(tmp_path / "missing")}) == Path(se_cli._WORKSPACE_ROOT)


@pytest.mark.fast
def test_lazy_bridge_memory_models_and_thresholds_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre facade_get_* in lazy_bridge, memory_3tier_engine.models e nk_common.thresholds."""
    from _internal.memory_3tier_engine import models as mem_m
    from _internal.nk_common import thresholds as thr
    from _internal.rsi_convergence_engine import lazy_bridge as lb

    ns_hit = {
        "_LAZY_AST_GUARD_LOADED": True,
        "_LAZY_AST_GUARD_CLS": object,
        "_LAZY_STE100_FN": lambda *_a, **_kw: {},
        "_LAZY_GROUNDING_FN": lambda *_a, **_kw: {},
    }
    assert lb.facade_get_ast_guard_validator(ns_hit) is object
    assert callable(lb.facade_get_ste100_validator(ns_hit, lambda: None))
    assert callable(lb.facade_get_report_grounding_validator(ns_hit, lambda: None))

    ns_fresh = {"_SCRIPT_DIR": WORKSPACE_ROOT / "scripts", "_PROD_SCRIPTS": WORKSPACE_ROOT / "scripts", "_workspace_root": WORKSPACE_ROOT}
    assert lb.facade_get_ast_guard_validator(ns_fresh) is not None
    assert callable(lb.facade_get_ste100_validator(ns_fresh, lambda: None))
    assert callable(lb.facade_get_report_grounding_validator(ns_fresh, lambda: None))

    assert mem_m.resolve_domain("SEC") == "04_Governance_and_Rules"
    assert mem_m.resolve_domain("sec") == "04_Governance_and_Rules"
    with pytest.raises(ValueError):
        mem_m.resolve_domain("UNKNOWN_DOMAIN_XYZ")
    src_f = tmp_path / "mem_src.txt"
    dst_f = tmp_path / "mem_dst.txt"
    src_f.write_text("payload_1", encoding="utf-8")
    mem_m.win32_atomic_replace(src_f, dst_f)
    assert dst_f.read_text(encoding="utf-8") == "payload_1" and not src_f.exists()

    with monkeypatch.context() as mp:
        for mod_k in ("memory_3tier_engine", "scripts.memory_3tier_engine"):
            fac_mod = sys.modules.get(mod_k)
            if fac_mod is not None and "_kernel32" in vars(fac_mod):
                mp.setattr(fac_mod, "_kernel32", mem_m._UNSET)
            if fac_mod is not None and "_win32_2pc_atomic_replace" in vars(fac_mod):
                mp.setattr(fac_mod, "_win32_2pc_atomic_replace", None)
        mp.setattr(mem_m, "_win32_2pc_atomic_replace", None)
        mp.setattr(mem_m, "_kernel32", mem_m._UNSET)
        mp.setattr(mem_m.os, "name", "posix")
        assert mem_m._get_kernel32() is None
        src2 = tmp_path / "mem_src2.txt"
        src2.write_text("payload_2", encoding="utf-8")
        mem_m.win32_atomic_replace(src2, dst_f)
        assert dst_f.read_text(encoding="utf-8") == "payload_2"

    cfg_f = tmp_path / "sat.json"
    cfg_f.write_text('{"profiles": {"carbon": {"max_steps": 120}}}', encoding="utf-8")
    thr.clear_thresholds_cache()
    assert thr.load_saturation_thresholds(thresholds_path=cfg_f)["profiles"]["carbon"]["max_steps"] == 120
    assert thr.load_saturation_thresholds(thresholds_path=cfg_f)["profiles"]["carbon"]["max_steps"] == 120
    assert thr.load_saturation_thresholds(thresholds_path=tmp_path / "missing_sat.json") == {}
    assert thr._safe_pos_int(True, 7) == 7 and thr._safe_pos_int(-5, 7) == 7 and thr._safe_pos_int("abc", 7) == 7

    del_dict_f = tmp_path / "del_d.json"
    del_dict_f.write_text(json.dumps({"deleted_files": ["./scripts/a.py", "  ", 42]}), encoding="utf-8")
    assert thr.load_deleted_files(deleted_manifest=del_dict_f) == {"scripts/a.py"}
    del_list_f = tmp_path / "del_l.json"
    del_list_f.write_text(json.dumps(["/scripts/b.py"]), encoding="utf-8")
    assert thr.load_deleted_files(deleted_manifest=del_list_f) == {"scripts/b.py"}
    del_bad_f = tmp_path / "del_bad.json"
    del_bad_f.write_text("{bad", encoding="utf-8")
    assert thr.load_deleted_files(deleted_manifest=del_bad_f) == set()


@pytest.mark.fast
def test_registry_shards_compaction_modes_and_emergency_collapse() -> None:
    """Copre tutti i rami compact_mode 0..3, _trim_text e emergency collapse in shards.py."""
    from _internal.nk_registry_indexer import shards as sh

    assert sh._trim_text("breve", 10) == "breve"
    assert sh._trim_text("descrizione molto lunga che supera limite", 16).endswith("...")

    sk_meta = {
        "native_subagent": "NK-Builder-Agent",
        "thinking_level": "HIGH",
        "tools": ["read_file", "write_file"],
        "sha256": "abc",
        "domain_id": "DOM-03",
        "sector": "ALTRO",
        "enable_mcp_tools": True,
        "source_layer": "staging",
        "auxiliary_links": ["a.md"],
        "loc": 42,
        "path": ".agents/skills/X/SKILL.md",
        "description": "Descrizione molto lunga di esempio per la skill.",
    }
    sc_meta = {
        "sha256": "def",
        "domain_id": "DOM-03",
        "cli_flags": [f"--f{i}" for i in range(8)],
        "classes": ["C1", "C2", "C3"],
        "source_layer": "staging",
        "loc": 120,
        "description": "Descrizione lunga script di utilita",
    }
    ag_meta = {
        "tools": ["read_file"],
        "sha256": "ghi",
        "domain_id": "DOM-03",
        "enable_write_tools": True,
        "enable_subagent_tools": False,
        "enable_mcp_tools": True,
        "source_layer": "staging",
        "loc": 35,
        "path": ".agents/agents/X/agent.md",
        "description": "Descrizione lunga agente nativo",
    }

    assert "auxiliary_links" in sh._compact_skill_entry(sk_meta, "BUILD", compact_mode=0)
    assert sh._compact_script_entry(sc_meta, compact_mode=2)["classes"] == ["C1", "C2"]
    assert len(sh._compact_script_entry(sc_meta, compact_mode=3)["cli_flags"]) == 6
    assert sh._compact_agent_entry(ag_meta, compact_mode=0)["enable_subagent_tools"] is False

    raw_tight = sh._serialize_domain_shard_with_cap(
        dom_id="DOM-03",
        dom_meta={"name": "BUILD", "primary_skill": "NK-A", "title": "T", "description": "D", "keywords": ["a", "b", "c", "d", "e"]},
        dom_skills={"NK-A": sk_meta},
        dom_scripts={"s.py": sc_meta},
        dom_agents={"AG": ag_meta},
        dom_intents={"kw1": ["NK-A", "mode_c"], "kw2": ["NK-B", "mode_d"]},
        max_bytes=40,
    )
    parsed = json.loads(raw_tight)
    assert parsed["domain"]["keywords"] == ["a", "b"]
    assert parsed["intent_dispatch_table"] == {"kw1": "mode_c", "kw2": ["NK-B", "mode_d"]}


@pytest.mark.fast
def test_hook_gate_cli_parser_platform_runner_tokenizer_and_prune(tmp_path: Path) -> None:
    """Copre _parse_hook_cli_args, _tokenize_command_no_shell e _prune_deleted_parent_dirs."""
    from _internal.win32_2pc_engine.promoter import _prune_deleted_parent_dirs

    hg_mod = load_nk_script_module("nk_hook_gate")
    pr_mod = load_nk_script_module("platform_runner")

    ns_ok = hg_mod._parse_hook_cli_args(["integrity", "--check", "--event=PreInvocation", "--native-contract"])
    assert ns_ok.subcommand == "integrity" and ns_ok.check is True and ns_ok.event == "PreInvocation"
    with pytest.raises(SystemExit) as exc_h:
        hg_mod._parse_hook_cli_args(["--help"])
    assert exc_h.value.code == 0
    with pytest.raises(SystemExit):
        hg_mod._parse_hook_cli_args(["--event"])
    with pytest.raises(SystemExit):
        hg_mod._parse_hook_cli_args(["--unknown-flag-xyz"])

    toks = pr_mod._tokenize_command_no_shell('python -c "a\\"b" \'single\'   ok')
    assert toks == ["python", "-c", 'a"b', "single", "ok"]
    for bad_cmd in ("a\x00b", "echo a & calc", "echo $(whoami)", 'unbalanced "quote'):
        with pytest.raises(ValueError):
            pr_mod._tokenize_command_no_shell(bad_cmd)

    ws_root = tmp_path / "ws_prune"
    prot_ag = ws_root / ".agents"
    nested = ws_root / "old_pkg" / "leaf"
    prot_ag.mkdir(parents=True)
    nested.mkdir(parents=True)
    _prune_deleted_parent_dirs([nested, prot_ag, tmp_path / "outside"], ws_root, ws_root.resolve())
    assert prot_ag.is_dir() and not (ws_root / "old_pkg").exists()


@pytest.mark.fast
def test_heartbeat_signaler_and_facade_resolver_branches(tmp_path: Path) -> None:
    """Copre AsyncHeartbeatSignaler e ast_repo_mapper.facade_resolver."""
    from _internal.ast_repo_mapper import facade_resolver as fr

    hb_mod = load_nk_script_module("async_heartbeat_signaler")
    hb_file = tmp_path / "hb.jsonl"
    hb = hb_mod.AsyncHeartbeatSignaler(
        step_name="tas_cov", cadence_sec=0.05, watchdog_sec=5.0, telemetry_file=hb_file
    )
    hb.reset_step("tas_cov_2")
    hb.start()
    hb.start()
    hb.stop()
    dump_p = hb.dump_diagnostics()
    assert hb_file.is_file() and dump_p.is_file()
    dump_p.unlink(missing_ok=True)

    roots = fr._candidate_scripts_roots(WORKSPACE_ROOT / "scripts" / "vibe_sprint_router.py", WORKSPACE_ROOT)
    assert any(r.name == "scripts" for r in roots)
    assert fr._resolve_internal_file("os", roots) is None
    assert fr._resolve_internal_file("scripts._internal.nk_common.catalog", roots) is not None
    assert fr._resolve_relative_module("a.b.c", None, 0, Path("c.py")) == ""
    assert fr._resolve_relative_module("_internal.pkg", "sub", 1, Path("__init__.py")) == "_internal.pkg.sub"
    assert fr._resolve_relative_module("_internal.pkg.mod", "peer", 1, Path("mod.py")) == "_internal.pkg.peer"
    assert fr._resolve_relative_module("_internal.pkg.mod", "top", 5, Path("mod.py")) == "top"


@pytest.mark.fast
def test_oracle_lock_verifier_and_auto_inning_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _verify_oracle_lock_files e nk_auto_inning.main CLI reale."""
    from _internal.nk_hook_gate import integrity_and_fasttrack as ift

    ws = tmp_path / "lock_ws"
    (ws / "tests").mkdir(parents=True)
    lock_p = ws / "oracle_lock.json"
    assert ift._verify_oracle_lock_files(ws, lock_p) == []
    lock_p.write_text("{corrupt", encoding="utf-8")
    assert ift._verify_oracle_lock_files(ws, lock_p) == ["Invalid JSON in oracle_lock.json"]
    lock_p.write_text("[]", encoding="utf-8")
    assert ift._verify_oracle_lock_files(ws, lock_p) == ["Invalid root object in oracle_lock.json"]
    lock_p.write_text(json.dumps({"files": {}}), encoding="utf-8")
    assert ift._verify_oracle_lock_files(ws, lock_p) == []

    real_f = ws / "tests" / "ok.py"
    real_f.write_text("x = 1\n", encoding="utf-8")
    lock_p.write_text(
        json.dumps(
            {
                "files": {
                    "../../escape.py": "0" * 64,
                    "missing.py": "0" * 64,
                    "ok.py": "not_hex",
                }
            }
        ),
        encoding="utf-8",
    )
    viols = ift._verify_oracle_lock_files(ws, lock_p)
    assert any("path escape" in v for v in viols)
    assert any("missing target" in v for v in viols)
    assert any("invalid SHA-256" in v for v in viols)

    tp = tmp_path / "inning_tp.jsonl"
    tp.write_text('{"tool": "read_file"}\n', encoding="utf-8")
    tune = tmp_path / "tuning.json"
    ai_mod = load_nk_script_module("nk_auto_inning")
    with monkeypatch.context() as mp:
        mp.setattr(sys, "argv", ["nk_auto_inning.py", "--transcript", str(tp), "--tuning-file", str(tune), "--json"])
        ai_mod.main()
    parsed = json.loads(tune.read_text(encoding="utf-8"))
    assert parsed["steps"] == 1


@pytest.mark.fast
def test_messenger_hud_and_api_cache_cli_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Copre main CLI e stream check di nk_swarm_messenger, micro_hud_renderer e deterministic_api_cache."""
    from types import SimpleNamespace

    msg_mod = load_nk_script_module("nk_swarm_messenger")
    hud_mod = load_nk_script_module("micro_hud_renderer")
    dac_mod = load_nk_script_module("deterministic_api_cache")

    pf = tmp_path / "msg.txt"
    pf.write_text("messaggio_breve", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(sys, "argv", ["nk_swarm_messenger.py", "--sender", "S1", "--payload", "ciao"])
        msg_mod.main()
        mp.setattr(sys, "argv", ["nk_swarm_messenger.py", "--payload-file", str(pf)])
        msg_mod.main()
    out_msg = capsys.readouterr().out
    assert "[Swarm-Envelope: S1 -> parent]" in out_msg and "messaggio_breve" in out_msg

    assert hud_mod.is_unicode_stream_supported(SimpleNamespace(encoding=None)) is True
    assert hud_mod.is_unicode_stream_supported(SimpleNamespace(encoding="ascii")) is False
    assert hud_mod.is_unicode_stream_supported(SimpleNamespace(encoding="utf-8")) is True
    with monkeypatch.context() as mp:
        mp.setattr(sys, "argv", ["micro_hud_renderer.py", "--percent", "88", "--ascii"])
        assert hud_mod.main() == 0
        mp.setattr(sys, "argv", ["micro_hud_renderer.py", "--json"])
        assert hud_mod.main() == 0
    out_hud = capsys.readouterr().out
    assert "88%" in out_hud and '"agent_id"' in out_hud

    cache_db = tmp_path / "test_api_cache.db"
    cache_inst = dac_mod.DeterministicApiCache(db_path=cache_db)
    cache_inst.set("/v1/ping", 200, '{"ok":true}', method="GET")
    assert cache_inst.get("/v1/ping", method="GET") is not None
    assert cache_inst.health_check() is True
    assert cache_inst.get_stats()["entries"] == 1
    assert cache_inst.clear() == 1
    cache_inst.close()
    with monkeypatch.context() as mp:
        orig_dac_cls = dac_mod.DeterministicApiCache
        created_caches = []

        def _make_cache():
            inst = orig_dac_cls(db_path=tmp_path / "cli_api.db")
            created_caches.append(inst)
            return inst

        mp.setattr(dac_mod, "DeterministicApiCache", _make_cache)
        for argv in (
            ["deterministic_api_cache.py", "--health"],
            ["deterministic_api_cache.py", "--stats"],
            ["deterministic_api_cache.py", "--clear"],
            ["deterministic_api_cache.py", "--force-refresh"],
            ["deterministic_api_cache.py"],
        ):
            mp.setattr(sys, "argv", argv)
            assert dac_mod.main() == 0
        mp.delenv("NK_FORCE_NETWORK_REFRESH", raising=False)
        for inst in created_caches:
            inst.close()


def test_env_capability_probe_cli_and_probe_branches(tmp_path: Path, monkeypatch) -> None:
    """Esercita env_capability_probe: check_module, probe_environment, format e CLI."""
    import scripts.env_capability_probe as ecp_mod

    ok_mod = ecp_mod.check_module_availability("json")
    assert ok_mod["available"] is True
    assert isinstance(ok_mod["version"], str)

    pywin_info = ecp_mod.check_module_availability("pywin32")
    assert pywin_info["module"] == "pywin32"

    missing_mod = ecp_mod.check_module_availability("nk_nonexistent_module_99999")
    assert missing_mod["available"] is False

    bad_mod = ecp_mod.check_module_availability("invalid..module")
    assert bad_mod["available"] is False and bad_mod["error"] is not None

    report = ecp_mod.probe_environment()
    assert report["summary"]["total_probed"] == 15
    assert report["summary"]["all_standard_available"] is True
    human = ecp_mod.format_human_readable(report)
    assert "NK HUB GENERATION: ENVIRONMENT CAPABILITY PROBE" in human

    export_a = tmp_path / "ecp_a.json"
    export_b = tmp_path / "ecp_b.json"
    with monkeypatch.context() as mp:
        for argv, expected_rc in (
            (["env_capability_probe.py", "--check-module", "json"], 0),
            (["env_capability_probe.py", "--check-module", "json", "--json"], 0),
            (["env_capability_probe.py", "--check-module", "nk_nonexistent_module_99999"], 1),
            (["env_capability_probe.py", "--export", str(export_a), "--json"], 0),
            (["env_capability_probe.py", "--export", str(export_b)], 0),
            (["env_capability_probe.py"], 0),
        ):
            mp.setattr(sys, "argv", argv)
            assert ecp_mod.main() == expected_rc
    assert export_a.exists() and export_b.exists()
