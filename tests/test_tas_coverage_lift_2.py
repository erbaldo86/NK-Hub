# -*- coding: utf-8 -*-
"""Test unitari aggiuntivi in-process per superare ampiamente il ratchet TAS."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve()
_WS_ROOT = _HERE.parents[2] if _HERE.parents[1].name == ".staging" else _HERE.parents[1]
_SCRIPTS_DIR = _WS_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_catalog_loader_cache_rehydration_and_fallbacks(tmp_path: Path) -> None:
    """Esercita cache stat, JSON malformati e reidratazione DOM-00..DOM-06."""
    import _internal.nk_common.catalog_loader as cl

    cl.clear_catalog_cache()
    assert cl.load_domain_shard("", workspace_root=tmp_path) == {}
    assert cl.load_all_domain_shards(workspace_root=tmp_path) == {}
    assert cl.load_registry_manifest(workspace_root=tmp_path) == {}

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{broken", encoding="utf-8")
    assert cl._read_json_cached(bad_json, {}) is None

    list_json = tmp_path / "list.json"
    list_json.write_text("[1, 2, 3]", encoding="utf-8")
    assert cl._read_json_cached(list_json, {}) is None

    cache_box = {}
    ok_json = tmp_path / "ok.json"
    ok_json.write_text('{"k": 1}', encoding="utf-8")
    assert cl._read_json_cached(ok_json, cache_box) == {"k": 1}
    assert cl._read_json_cached(ok_json, cache_box) == {"k": 1}

    shards_dir = tmp_path / "nk_genome" / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    (shards_dir / "DOM-00.json").write_text(
        json.dumps(
            {
                "global_hygiene_profile": {"ok": True},
                "docs_and_setup_index": {"d": 1},
                "milestone_anchor_id": "MS-TEST",
            }
        ),
        encoding="utf-8",
    )
    (shards_dir / "DOM-01.json").write_text(
        json.dumps(
            {
                "domain": {
                    "domain_id": "DOM-01",
                    "name": "Ops",
                    "primary_skill": "NK-Orchestrator",
                    "keywords": ["base"],
                },
                "intent_dispatch_table": {
                    "_routes": [["NK-Orchestrator", "mode_a", ["route1"]]],
                    "str_kw": "mode_c",
                    "dict_kw": {
                        "domain_id": "DOM-01",
                        "domain_name": "Ops",
                        "primary_agent": "NK-Orchestrator",
                        "recommended_mode": "mode_a",
                    },
                },
                "skills_index": {"NK-Orchestrator": {"read_only": False}},
                "scripts_index": {"nk_registry_indexer.py": {"role": "cli"}},
                "native_agents_index": {"NK-Arch-Specifier": {"domain_id": "DOM-02"}},
            }
        ),
        encoding="utf-8",
    )
    (shards_dir / "DOM-06.json").write_text(
        json.dumps({"release": "6.4.0"}), encoding="utf-8"
    )

    manifest_file = tmp_path / "nk_genome" / "nk_registry_manifest.json"
    slim = {
        "shards": {
            "DOM-00": {},
            "DOM-01": {},
            "DOM-02": {},
            "DOM-06": {},
        }
    }
    manifest_file.write_text(json.dumps(slim), encoding="utf-8")

    assert cl._rehydrate_from_shards({"shards": {}}, tmp_path) == {"shards": {}}
    raw_manifest = cl.load_registry_manifest(workspace_root=tmp_path, rehydrate=False)
    assert "shards" in raw_manifest
    rehydrated = cl.load_registry_manifest(workspace_root=tmp_path, rehydrate=True)
    assert rehydrated["milestone_anchor_id"] == "MS-TEST"
    assert rehydrated["release_meta"]["release"] == "6.4.0"
    assert rehydrated["intent_dispatch_table"]["str_kw"]["recommended_mode"] == "mode_c"
    assert rehydrated["intent_dispatch_table"]["route1"]["recommended_mode"] == "mode_a"
    assert rehydrated["intent_dispatch_table"]["dict_kw"]["primary_agent"] == "NK-Orchestrator"
    cl.clear_catalog_cache()


def test_facade_boot_staging_overlay_and_stale_cleanup(tmp_path: Path) -> None:
    """Verifica overlay .staging/ e rimozione modulo _internal obsoleto."""
    import _internal.nk_common.facade_boot as fb

    prod_scripts = tmp_path / "scripts"
    (prod_scripts / "_internal" / "demo_pkg").mkdir(parents=True, exist_ok=True)
    (prod_scripts / "_internal" / "__init__.py").write_text("", encoding="utf-8")
    (prod_scripts / "_internal" / "demo_pkg" / "__init__.py").write_text("", encoding="utf-8")

    stg_scripts = tmp_path / ".staging" / "scripts"
    (stg_scripts / "_internal" / "demo_pkg").mkdir(parents=True, exist_ok=True)
    (stg_scripts / "_internal" / "__init__.py").write_text("", encoding="utf-8")
    (stg_scripts / "_internal" / "demo_pkg" / "__init__.py").write_text("", encoding="utf-8")
    facade_file = stg_scripts / "demo_cli.py"
    facade_file.write_text("# demo\n", encoding="utf-8")

    saved_path = list(sys.path)
    saved_internal = {
        k: v for k, v in sys.modules.items() if k == "_internal" or k.startswith("_internal.")
    }
    try:
        for k in list(saved_internal):
            sys.modules.pop(k, None)
        sys.modules["_internal"] = SimpleNamespace(
            __file__=str(tmp_path / "foreign" / "scripts" / "_internal" / "__init__.py")
        )
        out = fb.init_nk_facade(str(facade_file), pkg="demo_pkg")
        assert Path(out).resolve() == prod_scripts.resolve()
        loaded_pkg = sys.modules.get("_internal.demo_pkg")
        assert loaded_pkg is not None
        assert str((stg_scripts / "_internal" / "demo_pkg").resolve()) in [
            str(Path(p).resolve()) for p in getattr(loaded_pkg, "__path__", [])
        ]
    finally:
        for k in [m for m in list(sys.modules) if m == "_internal" or m.startswith("_internal.")]:
            sys.modules.pop(k, None)
        sys.modules.update(saved_internal)
        sys.path[:] = saved_path


def test_fastguard_z2_l0_and_transcript_prompt_extraction(
    tmp_path: Path, monkeypatch
) -> None:
    """Esercita WAL/Mutex guard, anchor meta, esenzioni L0, one-shot L0 e parser transcript."""
    import _internal.nk_acs_fastguard.z2_and_l0 as z2
    import _internal.nk_session_bootstrap.transcript_prompt as tp_mod

    assert tp_mod.extract_user_prompt_from_line(b"") is None
    assert tp_mod.extract_user_prompt_from_line(b"not-json") is None
    assert tp_mod.extract_user_prompt_from_line(b"{bad") is None
    assert tp_mod.extract_user_prompt_from_line(b"[1, 2]") is None
    assert (
        tp_mod.extract_user_prompt_from_line(b'{"type":"MODEL","content":"hi"}')
        is None
    )
    assert (
        tp_mod.extract_user_prompt_from_line(
            json.dumps(
                {
                    "type": "USER_INPUT",
                    "content": ["prima riga", {"text": "seconda riga"}],
                }
            ).encode("utf-8")
        )
        == "prima riga\nseconda riga"
    )
    assert (
        tp_mod.extract_user_prompt_from_line(
            json.dumps(
                {"type": "USER_INPUT", "content": "<CONTEXT_SUMMARY>\ntrunc"}
            ).encode("utf-8")
        )
        is None
    )

    wal_dir = tmp_path / ".wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    assert z2._has_active_wal([str(tmp_path)]) is False
    (wal_dir / "active.wal").write_text("wal", encoding="utf-8")
    assert z2._has_active_wal([str(tmp_path)]) is True

    assert z2._is_batch_mutex_busy([str(tmp_path), str(tmp_path)]) is False
    fake_k32 = SimpleNamespace(OpenMutexW=lambda *_a: 0, CloseHandle=lambda *_a: True)
    fake_ct = SimpleNamespace(
        set_last_error=lambda _v: None,
        get_last_error=lambda: z2._ERROR_ACCESS_DENIED,
    )
    with monkeypatch.context() as mp:
        mp.setattr(
            z2,
            "_fg_attr",
            lambda name, default=None: (lambda: (fake_ct, fake_k32))
            if name == "_get_k32"
            else default,
        )
        assert z2._is_batch_mutex_busy([str(tmp_path)]) is True
        mp.setattr(
            z2,
            "_fg_attr",
            lambda name, default=None: (lambda: (None, None))
            if name == "_get_k32"
            else default,
        )
        assert z2._is_batch_mutex_busy([str(tmp_path)]) is False

    sess_dir = tmp_path / "nk_tracking" / "sessions" / "conv1234abcd"
    sess_dir.mkdir(parents=True, exist_ok=True)
    (sess_dir / "session_anchor.jsonl").write_text(
        json.dumps({"milestone_id": "MS-Z2-TEST", "turn": 3}) + "\n",
        encoding="utf-8",
    )
    assert z2._read_anchor_meta([str(tmp_path)], {}, conv_id="conv1234abcd") == (
        "MS-Z2-TEST",
        3,
    )
    assert z2._read_anchor_meta([str(tmp_path)], {"milestone_id": "MS-PAY"}, conv_id="default_x") == (
        "MS-PAY",
        1,
    )

    assert z2._is_l0_exempt_fast("") is True
    assert z2._is_l0_exempt_fast("<env_capsule>ok") is True
    assert z2._is_l0_exempt_fast("[3]") is True
    assert z2._is_l0_exempt_fast("4") is True
    assert z2._is_l0_exempt_fast("/compact") is True
    assert z2._is_l0_exempt_fast("procedi") is True
    assert z2._is_l0_exempt_fast("scrivi nuovo endpoint profilo") is False

    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    assert z2._check_l0_gate_one_shot("", "conv-1", str(hooks_dir), {}, 1) is None
    assert z2._check_l0_gate_one_shot(str(tmp_path / "missing.jsonl"), "conv-1", "", {}, 1) is None

    tp_file = tmp_path / "transcript.jsonl"
    tp_file.write_text("", encoding="utf-8")
    assert (
        z2._check_l0_gate_one_shot(str(tp_file), "conv-1", str(hooks_dir), {}, 1)
        is None
    )

    prompt_txt = "implementa modulo auth sicuro"
    tp_file.write_text(
        "\n".join(
            [
                "{broken",
                json.dumps([1, 2]),
                json.dumps({"type": "MODEL", "content": "risposta"}),
                json.dumps({"type": "USER_INPUT", "content": prompt_txt}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gate_path = hooks_dir / "l0_gate_conv-1.json"
    gate_path.write_text("{corrupt", encoding="utf-8")
    state: dict = {}
    warn = z2._check_l0_gate_one_shot(
        str(tp_file), "conv-1", str(hooks_dir), state, 1
    )
    assert warn is not None and "[RULE-00.6-ENFORCE]" in warn
    assert (
        z2._check_l0_gate_one_shot(str(tp_file), "conv-1", str(hooks_dir), state, 1)
        is None
    )

    prompt_sha = hashlib.sha256(" ".join(prompt_txt.split()).encode("utf-8")).hexdigest()
    gate_path.write_text(json.dumps({"turn_prompt_sha256": prompt_sha}), encoding="utf-8")
    assert (
        z2._check_l0_gate_one_shot(str(tp_file), "conv-1", str(hooks_dir), {}, 1)
        is None
    )


def test_integrity_tamper_detection_and_z2_spawn_guards(
    tmp_path: Path, monkeypatch
) -> None:
    """Esercita _handle_integrity, _handle_fasttrack e guardie _maybe_spawn_z2."""
    import _internal.nk_acs_fastguard.z2_and_l0 as z2
    import _internal.nk_hook_gate.integrity_and_fasttrack as iaf

    hooks_dir = tmp_path / "hooks_int"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    ws = tmp_path / "ws_int"
    (ws / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (ws / "nk_genome").mkdir(parents=True, exist_ok=True)
    (ws / "scripts").mkdir(parents=True, exist_ok=True)
    (ws / "tests").mkdir(parents=True, exist_ok=True)
    (ws / ".agents").mkdir(parents=True, exist_ok=True)

    cp_file = ws / "nk_tracking" / "checkpoint_1.json"
    cp_file.write_text('{"step": 1}', encoding="utf-8")
    pn_file = ws / "nk_genome" / "PATCH_NOTES.md"
    pn_file.write_text("## [v6.4.0] - 2026-11-16\n- Riga 1\n", encoding="utf-8")
    sc_file = ws / "scripts" / "s.py"
    sc_file.write_text("X = 1\n", encoding="utf-8")
    te_file = ws / "tests" / "t.py"
    te_file.write_text("def test_ok(): assert True\n", encoding="utf-8")
    ag_file = ws / ".agents" / "r.md"
    ag_file.write_text("# Regola\n", encoding="utf-8")
    (ws / "nk_tracking" / "rsi_telemetry.jsonl").write_text(
        '{"iter": 1}\n', encoding="utf-8"
    )

    sc_sha = hashlib.sha256(sc_file.read_bytes()).hexdigest()
    lock_files = {"scripts/s.py": sc_sha}
    comb_sha = hashlib.sha256(
        json.dumps(lock_files, sort_keys=True).encode("utf-8")
    ).hexdigest()
    (ws / "oracle_lock.json").write_text(
        json.dumps({"files": lock_files, "combined_sha256": comb_sha}),
        encoding="utf-8",
    )

    with monkeypatch.context() as mp:
        mp.setattr(iaf, "_get_hooks_temp_dir", lambda: hooks_dir)
        mp.setattr(iaf, "_resolve_effective_hub_root", lambda _p: ws)

        res_uninit, rc_uninit = iaf._handle_integrity("c_int", ws, False, True)
        assert res_uninit["status"] == "UNINITIALIZED" and rc_uninit == 1

        res_init, rc_init = iaf._handle_integrity("c_int", ws, True, False)
        assert res_init["status"] == "INITIALIZED" and rc_init == 0

        res_ok, rc_ok = iaf._handle_integrity("c_int", ws, False, True)
        assert res_ok["status"] == "VALID" and rc_ok == 0

        cp_file.unlink()
        pn_file.write_text("OVERWRITTEN\n", encoding="utf-8")
        sc_file.write_text("X = 2\n", encoding="utf-8")
        te_file.write_text("def test_ok(): assert False\n", encoding="utf-8")
        ag_file.write_text("# Tampered\n", encoding="utf-8")
        res_bad, rc_bad = iaf._handle_integrity("c_int", ws, False, True)
        assert res_bad["status"] == "VIOLATION" and rc_bad == 1
        assert len(res_bad["violations"]) >= 5

        snap_p = hooks_dir / "c_int_integrity.json"
        snap_p.write_text("[1, 2]", encoding="utf-8")
        res_c1, rc_c1 = iaf._handle_integrity("c_int", ws, False, True)
        assert res_c1["status"] == "CORRUPTED_SNAPSHOT" and rc_c1 == 1

        snap_p.write_text("{broken", encoding="utf-8")
        res_c2, rc_c2 = iaf._handle_integrity("c_int", ws, False, True)
        assert res_c2["status"] == "CORRUPTED_SNAPSHOT" and rc_c2 == 1

        iaf._handle_fasttrack("c_ft", {"toolName": "invoke_subagent"})
        for _ in range(13):
            ft_res = iaf._handle_fasttrack("c_ft", {"toolName": "write_file"})
        assert ft_res.get("streak") == 13
        assert "ephemeralMessage" in ft_res
        ft_rst = iaf._handle_fasttrack("c_ft", {"toolName": "invoke_subagent"})
        assert ft_rst == {}

    assert iaf._extract_last_planner_message(tmp_path / "missing_tp.jsonl") == ""
    planner_tp = tmp_path / "planner_tp.jsonl"
    planner_tp.write_text(
        "\n".join(
            [
                "",
                "{bad",
                json.dumps({"type": "GENERIC", "source": "MODEL", "content": "ignore"}),
                json.dumps({"type": "PLANNER_RESPONSE", "content": "final answer"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert iaf._extract_last_planner_message(planner_tp) == "final answer"

    z2._maybe_spawn_z2(
        [str(ws)],
        "",
        "conv1234abcd",
        {},
        {"compaction_epoch": 1, "z2_last_spawn_ts": time.time(), "z2_last_spawn_epoch": 1},
        cooldown_s=30.0,
    )
    with monkeypatch.context() as mp:
        mp.setattr(
            z2,
            "_fg_attr",
            lambda name, default=None: (lambda _r: True)
            if name == "_is_batch_mutex_busy"
            else (str(ws / "scripts") if name == "_SCRIPT_DIR" else (str(ws) if name == "_WORKSPACE_ROOT" else default)),
        )
        z2._maybe_spawn_z2([str(ws)], "", "conv1234abcd", {}, {}, cooldown_s=0.0)
        mp.setattr(
            z2,
            "_fg_attr",
            lambda name, default=None: (lambda _r: False)
            if name in ("_is_batch_mutex_busy", "_has_active_wal")
            else (str(ws / "scripts") if name == "_SCRIPT_DIR" else (str(ws) if name == "_WORKSPACE_ROOT" else default)),
        )
        z2._maybe_spawn_z2([str(ws)], "", "conv1234abcd", {}, {}, cooldown_s=0.0)
