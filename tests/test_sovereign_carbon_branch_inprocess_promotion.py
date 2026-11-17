# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Matrice In-Process Promozione 2PC & Ecosistema (split 3/4).
Modulo: tests/test_sovereign_carbon_branch_inprocess_promotion.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main as _call_main,
        load_script_by_relpath as _load_mod,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT as _WORKSPACE_ROOT,
        call_script_main as _call_main,
        load_script_by_relpath as _load_mod,
    )

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
dast_mod = _load_mod("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
clean_mod = _load_mod("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
bridge_mod = _load_mod("sbfl_pytest_bridge", "scripts/sbfl_pytest_bridge.py")
tr_mod = _load_mod("nk_transcript_tools", "scripts/nk_transcript_tools.py")
rsi_mod = _load_mod("rsi_convergence_engine", "scripts/rsi_convergence_engine.py")
idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
comp_mod = _load_mod("nk_compliance_checker", "scripts/nk_compliance_checker.py")


def _build_cold_help_probe_src(target_script: Path) -> str:
    """Costruisce il sorgente di sonda --help senza caricamento pydantic."""
    return (
        "import runpy, sys\n"
        f"sys.argv = [{str(target_script)!r}, '--help']\n"
        "try:\n"
        "    runpy.run_path(sys.argv[0], run_name='__main__')\n"
        "except SystemExit as exc:\n"
        "    if exc.code not in (0, None):\n"
        "        raise RuntimeError(f'Unexpected exit code: {exc.code}')\n"
        "assert 'pydantic' not in sys.modules, f'pydantic loaded for {sys.argv[0]}'\n"
    )


def _assert_cold_cli_help_no_pydantic(rel_script: str) -> None:
    """Verifica in sottoprocesso freddo che --help non importi pydantic."""
    stg_cand = _WORKSPACE_ROOT / ".staging" / rel_script
    prod_cand = _WORKSPACE_ROOT / rel_script
    target_script = stg_cand if stg_cand.is_file() else prod_cand
    assert target_script.is_file(), f"Missing script: {target_script}"
    py_roots = [
        str(_WORKSPACE_ROOT / ".staging" / "scripts"),
        str(_WORKSPACE_ROOT / ".staging"),
        str(_WORKSPACE_ROOT / "scripts"),
        str(_WORKSPACE_ROOT),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(py_roots)
    proc = subprocess.run(
        [sys.executable, "-B", "-c", _build_cold_help_probe_src(target_script)],
        cwd=str(_WORKSPACE_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20.0,
        shell=False,
    )
    assert proc.returncode == 0, f"{rel_script} --help failed:\n{proc.stdout}\n{proc.stderr}"


def _build_type_hints_sweep_src(stg_scripts: Path, prod_scripts: Path) -> str:
    """Costruisce il codice di verifica typing.get_type_hints su scripts/."""
    return (
        "import importlib, inspect, sys, typing\n"
        "from pathlib import Path\n"
        f"stg_s, prod_s = Path({str(stg_scripts)!r}), Path({str(prod_scripts)!r})\n"
        "if stg_s.is_dir() and (stg_s / '_internal').is_dir():\n"
        "    import _internal\n"
        "    stg_int = str(stg_s / '_internal')\n"
        "    if stg_int in _internal.__path__:\n"
        "        _internal.__path__.remove(stg_int)\n"
        "    _internal.__path__.insert(0, stg_int)\n"
        "    for sub in sorted((stg_s / '_internal').iterdir(), key=lambda p: (0 if p.name == 'nk_common' else 1, p.name)):\n"
        "        if sub.is_dir() and sub.name != '__pycache__' and ((sub / '__init__.py').is_file() or (prod_s / '_internal' / sub.name / '__init__.py').is_file()):\n"
        "            sp = importlib.import_module(f'_internal.{sub.name}')\n"
        "            if hasattr(sp, '__path__'):\n"
        "                s_str = str(sub)\n"
        "                if s_str in sp.__path__:\n"
        "                    sp.__path__.remove(s_str)\n"
        "                sp.__path__.insert(0, s_str)\n"
        "if stg_s.is_dir() and (stg_s / 'schemas').is_dir():\n"
        "    try:\n"
        "        import schemas\n"
        "        stg_sch = str(stg_s / 'schemas')\n"
        "        if hasattr(schemas, '__path__'):\n"
        "            if stg_sch in schemas.__path__:\n"
        "                schemas.__path__.remove(stg_sch)\n"
        "            schemas.__path__.insert(0, stg_sch)\n"
        "    except ImportError:\n"
        "        pass\n"
        "overlay = {}\n"
        "for base in (prod_s, stg_s):\n"
        "    if base.is_dir():\n"
        "        for pf in sorted(base.rglob('*.py')):\n"
        "            if '__pycache__' not in pf.parts:\n"
        "                overlay[pf.relative_to(base).as_posix()] = pf\n"
        "assert len(overlay) >= 130, f'Expected >=130 scripts, got {len(overlay)}'\n"
        "failures = []\n"
        "for rel in sorted(overlay):\n"
        "    parts = Path(rel).with_suffix('').parts\n"
        "    if parts[-1] == '__init__':\n"
        "        if len(parts) == 1:\n"
        "            continue\n"
        "        mod_name = '.'.join(parts[:-1])\n"
        "    else:\n"
        "        mod_name = '.'.join(parts)\n"
        "    if '.' in mod_name:\n"
        "        pkg_name = mod_name.rsplit('.', 1)[0]\n"
        "        try:\n"
        "            pkg_mod = importlib.import_module(pkg_name)\n"
        "            stg_pkg_dir = stg_s / pkg_name.replace('.', '/')\n"
        "            if stg_pkg_dir.is_dir() and hasattr(pkg_mod, '__path__'):\n"
        "                sp_str = str(stg_pkg_dir)\n"
        "                if sp_str in pkg_mod.__path__:\n"
        "                    pkg_mod.__path__.remove(sp_str)\n"
        "                pkg_mod.__path__.insert(0, sp_str)\n"
        "        except ImportError:\n"
        "            pass\n"
        "    if stg_s.is_dir():\n"
        "        stg_str = str(stg_s)\n"
        "        if stg_str in sys.path:\n"
        "            sys.path.remove(stg_str)\n"
        "        sys.path.insert(0, stg_str)\n"
        "    try:\n"
        "        mod = importlib.import_module(mod_name)\n"
        "    except Exception as exc:\n"
        "        failures.append((mod_name, '<import>', repr(exc)))\n"
        "        continue\n"
        "    for name, obj in list(vars(mod).items()):\n"
        "        if inspect.isfunction(obj) and getattr(obj, '__module__', None) == mod.__name__:\n"
        "            try:\n"
        "                typing.get_type_hints(obj)\n"
        "            except Exception as exc:\n"
        "                failures.append((mod_name, name, repr(exc)))\n"
        "        elif inspect.isclass(obj) and getattr(obj, '__module__', None) == mod.__name__:\n"
        "            for m_name, m_obj in list(vars(obj).items()):\n"
        "                fn = m_obj.__func__ if isinstance(m_obj, (staticmethod, classmethod)) else m_obj\n"
        "                if inspect.isfunction(fn):\n"
        "                    try:\n"
        "                        typing.get_type_hints(fn)\n"
        "                    except Exception as exc:\n"
        "                        failures.append((mod_name, f'{name}.{m_name}', repr(exc)))\n"
        "if failures:\n"
        "    for item in failures:\n"
        "        print('TYPE_HINT_FAILURE:', item)\n"
        "    sys.exit(1)\n"
    )


def _assert_all_scripts_type_hints_valid() -> None:
    """Verifica typing.get_type_hints() su tutti i moduli e classi sotto scripts/."""
    stg_scripts = _WORKSPACE_ROOT / ".staging" / "scripts"
    prod_scripts = _WORKSPACE_ROOT / "scripts"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(stg_scripts), str(prod_scripts), str(_WORKSPACE_ROOT)]
    )
    proc = subprocess.run(
        [sys.executable, "-B", "-c", _build_type_hints_sweep_src(stg_scripts, prod_scripts)],
        cwd=str(_WORKSPACE_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60.0,
        shell=False,
    )
    assert proc.returncode == 0, f"typing.get_type_hints() failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.fast
def test_prom_rsi_overlay_cove_and_lazy_loaders(tmp_path: Path) -> None:
    """Verifica RSI run_vibe_check, verify_cli_flags_cove, overlay md e lazy loaders."""
    v_ws = tmp_path / "vibe_ws"
    (v_ws / ".agents").mkdir(parents=True)
    (v_ws / ".staging").mkdir(parents=True)
    rsi_e = rsi_mod.RSIConvergenceEngine(workspace_root=v_ws)
    rsi_e.root = v_ws.resolve()
    assert rsi_e.run_vibe_check(tmp_path / "no_vibe_target")["passed"] is False
    (v_ws / ".agents" / "doc.md").write_text(
        "Questa frase supera volutamente il limite massimo consentito di venti parole imposto dallo "
        "standard tecnico italiano per attivare il controllo automatico di conformita.\n"
        "Esegui `python scripts/ghost_missing.py --flag-inesistente`.\n",
        encoding="utf-8",
    )
    (v_ws / ".staging" / "bad.json").write_text("{bad_json", encoding="utf-8")
    (v_ws / ".staging" / "moj.md").write_text("errore \ufffd rilevato\n", encoding="utf-8")
    sast_f = v_ws / ".staging" / "sast_bad.py"
    sast_f.write_text("import sys\nx = sys.modules['pytest']\n", encoding="utf-8")
    vc_res = rsi_e.run_vibe_check(v_ws)
    assert vc_res["passed"] is False and len(vc_res["violations"]) >= 2
    cove_res = rsi_e.verify_cli_flags_cove(v_ws)
    assert cove_res["passed"] is False and cove_res["checked_flags_count"] >= 1
    assert len(rsi_mod._collect_overlay_md_files(v_ws / ".staging", "", recursive=True)) >= 1
    (v_ws / ".staging" / ".deleted_files.json").write_text('[".agents/doc.md"]', encoding="utf-8")
    assert rsi_mod._collect_overlay_md_files(v_ws, ".agents", recursive=True) == []
    assert rsi_mod._collect_overlay_md_files(v_ws, ".agents", recursive=False) == []
    src1, tree1 = rsi_mod._get_cached_file_and_ast(sast_f)
    src2, tree2 = rsi_mod._get_cached_file_and_ast(sast_f)
    assert src1 == src2 and tree1 is tree2
    rsi_mod._LAZY_HEALING_SNAPSHOT_LOADED = False
    snap_cls = rsi_mod._get_healing_snapshot_manager_cls()
    assert snap_cls.__name__ == "HealingSnapshotManager"
    rsi_mod._LAZY_GROUNDING_FN = None
    ground_fn = rsi_mod._get_report_grounding_validator()
    assert callable(ground_fn) and ground_fn.__name__ == "verify_report_grounding"


@pytest.mark.fast
def test_prom_win32_2pc_scan_cleanup_shadow_and_ipc(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica 2PC scan canonico, JSON validation, cleanup, shadow swap, IPC e anchor."""
    scan_root = tmp_path / "w2_root"
    stg_scan = scan_root / ".staging"
    for sub in (".git", "__pycache__", "scripts", "other_dir"):
        (stg_scan / sub).mkdir(parents=True)
    (stg_scan / ".git" / "config").write_text("cfg", encoding="utf-8")
    (stg_scan / "__pycache__" / "a.pyc").write_bytes(b"\x00")
    (stg_scan / ".gitkeep").write_text("", encoding="utf-8")
    (stg_scan / ".deleted_files.json").write_text("[]", encoding="utf-8")
    (stg_scan / "scripts" / "ok.py").write_text("X = 1\n", encoding="utf-8")
    (stg_scan / "scripts" / "tmp.pyc").write_bytes(b"\x00")
    (stg_scan / "other_dir" / "skip.py").write_text("Y = 2\n", encoding="utf-8")
    assert w2pc_mod._scan_staging_canonical(stg_scan, scan_root, subdirs=["scripts"]) == [
        stg_scan / "scripts" / "ok.py"
    ]
    (stg_scan / "bad_utf8.json").write_bytes(b"\xff\xfe\x00")
    (stg_scan / "fffd.json").write_text('{"k": "\ufffd"}', encoding="utf-8")
    (stg_scan / "syn.json").write_text("{bad", encoding="utf-8")
    ok_j, err_j = w2pc_mod.validate_staging_json_files(stg_scan)
    assert ok_j is False and len(err_j) >= 3
    w2pc_mod._cleanup_promoted_staging(
        stg_scan,
        [stg_scan / "scripts" / "ok.py", stg_scan / "other_dir" / "skip.py"],
        deleted_manifest=stg_scan / ".deleted_files.json",
    )
    assert (stg_scan / ".gitkeep").is_file()
    (scan_root / "scripts" / "__pycache__").mkdir(parents=True)
    (scan_root / "scripts" / "__pycache__" / "old.pyc").write_bytes(b"\x00")
    w2pc_mod._purge_production_bytecode(scan_root)
    assert not (scan_root / "scripts" / "__pycache__").exists()
    eng2pc = w2pc_mod.TwoPhaseCommitEngine()
    src_sw, dst_sw = tmp_path / "sw_src.txt", tmp_path / "sw_dst.txt"
    src_sw.write_text("payload_nuovo", encoding="utf-8")
    dst_sw.write_text("payload_vecchio", encoding="utf-8")
    assert eng2pc._shadow_swap_fallback(src_sw, dst_sw) is True
    assert dst_sw.read_text(encoding="utf-8") == "payload_nuovo"
    ptr = eng2pc.create_ipc_pointer(tmp_path / "ipc_p.txt", "ipc payload", mime_type="text/plain")
    assert ptr.status == "OK" and ptr.byte_size == len("ipc payload")
    src_rep, dst_rep = tmp_path / "rep_src.txt", tmp_path / "rep_dst.txt"
    src_rep.write_text("atomico", encoding="utf-8")
    w2pc_mod.win32_atomic_replace(src_rep, dst_rep)
    assert dst_rep.read_text(encoding="utf-8") == "atomico"
    w2pc_mod.record_session_anchor_commit(scan_root, "", [{"relative_path": "scripts/ok.py"}], deleted_files=["old.py"])
    assert (scan_root / "nk_tracking" / "anchor" / "session_anchor.jsonl").is_file()
    with w2pc_mod.Win32NamedMutex(tmp_path / "reentrant.lock") as mx1:
        assert mx1.acquired is True
        mx1.acquire()
        mx1.release()


@pytest.mark.fast
def test_prom_indexer_l3_hook_and_transcript_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica NKRegistryIndexer metadata, Oracle L3, Hook Gate UNC/ADS e Transcript."""
    no_argp = tmp_path / "custom_no_argp.py"
    no_argp.write_text(
        '"""@domain_id: DOM-03\nModulo: custom_no_argp.py\nDescrizione script.\n"""\n# '
        + ("P" * 300)
        + '\nFLAG_CUSTOM = "--alpha-flag"\n',
        encoding="utf-8",
    )
    meta_1 = idx_mod.NKRegistryIndexer._extract_script_metadata(no_argp)
    meta_2 = idx_mod.NKRegistryIndexer._extract_script_metadata(no_argp)
    assert meta_1 == meta_2 and "--alpha-flag" in meta_1["cli_flags"] and meta_1["domain_id"] == "DOM-03"
    broken_s = tmp_path / "broken_meta.py"
    broken_s.write_text("# @domain_id: DOM-04\ndef broken(:\n", encoding="utf-8")
    assert idx_mod.NKRegistryIndexer._extract_script_metadata(broken_s)["domain_id"] == "DOM-04"
    g_cfg = tmp_path / "glob_cfg"
    g_cfg.mkdir()
    (g_cfg / "config.json").write_text(json.dumps({"disabledPlugins": ["science"]}), encoding="utf-8")
    idx_inst = idx_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT, global_config_dir=g_cfg)
    idx_inst._readonly_filter_applied = True
    assert "science" in idx_inst.scan_global_hygiene_profile(16)["disabled_plugins"]
    ev_l3 = l3_mod.DOMOracleEvaluator()
    html_exp = (
        "<ul><li>One<li>Two</ul><p>Para<div><img src='a.png'/><span>A</span></div>"
        "<dl><dt>T1<dd>D1<dt>T2</dl>"
        "<select><optgroup label='g1'><option>A<option>B</select>"
        "<table><thead><tr><th>H1<th>H2<tbody><tr><td>C1<td>C2</table>"
    )
    rep_l3 = ev_l3.evaluate_deltas(html_exp, "<ul><li>One</ul><div><b>B</b><i>I</i></div>")
    assert rep_l3.verdict == "FAIL" and rep_l3.discrepancy_count >= 2
    exp_h, act_h = tmp_path / "exp_dom.html", tmp_path / "act_dom.html"
    exp_h.write_text("<div><h1>Carbon</h1></div>", encoding="utf-8")
    act_h.write_text("<div><h1>Carbon</h1></div>", encoding="utf-8")
    assert _call_main(l3_mod, ["--expected-file", str(exp_h), "--actual-file", str(act_h)], monkeypatch) == 0
    assert hook_mod._canonical_path("\\\\?\\C:\\Temp\\nonexistent_x\\f.txt").name == "f.txt"
    assert hook_mod._has_ntfs_ads_stream("\\\\?\\C:\\dir\\file.txt:zone") is True
    assert hook_mod._has_ntfs_ads_stream("\\\\?\\UNC\\srv\\share\\f.txt") is False
    p_ws = tmp_path / "parent_ws"
    (p_ws / "NK_Hub" / "scripts").mkdir(parents=True)
    (p_ws / "NK_Hub" / ".staging").mkdir(parents=True)
    assert hook_mod._resolve_effective_hub_root(p_ws).name == "NK_Hub"
    assert hook_mod._resolve_target_path("NK_Hub/.staging/x.py", p_ws).name == "x.py"
    assert hook_mod._has_ancestor_reparse_escape("NK_Hub/.staging/x.py", p_ws) is False
    assert hook_mod._is_valid_staging_path(p_ws / "NK_External_Projects" / "DemoApp" / ".staging" / "main.py", p_ws) is True


@pytest.mark.fast
def test_prom_transcript_and_compliance_rsi_score(tmp_path: Path) -> None:
    """Verifica helper tool_call di Transcript Tools e lettura score RSI in Compliance."""
    assert tr_mod.clean_tool_str('"\\"hello\\""') == '"hello"'
    assert tr_mod.clean_tool_str("'abc'") == "abc"
    assert tr_mod.extract_tool_args({"arguments": '{"k": 1}'}) == {"k": 1}
    assert tr_mod.extract_tool_args({"arguments": "{bad"}) == {}
    assert tr_mod._extract_call_id({"tool_result": {"call_id": "c1"}}) == "c1"
    assert tr_mod._extract_call_id({"tool_results": [{"id": "c2"}]}) == "c2"
    assert tr_mod._pop_correlated_tool_call([{"id": "a"}, {"id": "b"}], {"id": "b"}) == {"id": "b"}
    assert tr_mod.is_read_file_output("File Path: `file:///C:/a.py`") is True
    assert tr_mod.extract_command_exit_code("Command exited with code 4", correlated_tool="run_command") == 4
    assert tr_mod.extract_command_exit_code("Command exited with code 4", correlated_tool="read_file") is None
    c_ws = tmp_path / "comp_ws"
    (c_ws / "nk_tracking").mkdir(parents=True)
    sess_dir = tmp_path / "sess_abc123"
    sess_dir.mkdir()
    sess_tp = sess_dir / "transcript.jsonl"
    sess_tp.write_text('{"role": "USER", "content": "hi"}\n', encoding="utf-8")
    (c_ws / "nk_tracking" / "rsi_telemetry.jsonl").write_text(
        json.dumps({"session_id": "other", "fitness_q": 40.0, "delta_k": 5})
        + "\n"
        + json.dumps({"session_id": "sess_abc123", "fitness_q": 92.0, "delta_k": 0})
        + "\n",
        encoding="utf-8",
    )
    chk_c = comp_mod.NKComplianceChecker(workspace_root=c_ws)
    assert chk_c._read_rsi_convergence_score(sess_tp, saw_converged_optimal=True) == 92.0
    assert chk_c._read_rsi_convergence_score(sess_tp, saw_converged_optimal=False) == 92.0
    empty_ws = tmp_path / "comp_empty_ws"
    (empty_ws / "nk_tracking").mkdir(parents=True)
    assert comp_mod.NKComplianceChecker(workspace_root=empty_ws)._read_rsi_convergence_score(
        sess_tp, saw_converged_optimal=True
    ) == 0


@pytest.mark.fast
def test_prom_2pc_cli_promotion_and_governance_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica CLI promozione 2PC, PATCH_NOTES guard e denylist oracle_lock."""
    assert _call_main(w2pc_mod, [], monkeypatch) == 0
    p_root = tmp_path / "p_repo"
    (p_root / "nk_tracking").mkdir(parents=True)
    (p_root / ".staging" / "scripts").mkdir(parents=True)
    (p_root / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"total_tests": 10, "pass_rate_pct": 100.0, "metrics": {"unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )
    (p_root / "PATCH_NOTES.md").write_text("## [1.0.0]\n- Init.\n", encoding="utf-8")
    (p_root / ".staging" / "PATCH_NOTES.md").write_text("## [2.0.0]\n- Upd.\n\n## [1.0.0]\n- Init.\n", encoding="utf-8")
    (p_root / "same.py").write_text("SAME = True\n", encoding="utf-8")
    (p_root / ".staging" / "same.py").write_text("SAME = True\n", encoding="utf-8")
    (p_root / "obsolete.py").write_text("OLD = 1\n", encoding="utf-8")
    (p_root / ".staging" / ".deleted_files.json").write_text(
        json.dumps({"deleted_files": ["obsolete.py"]}), encoding="utf-8"
    )
    (p_root / ".staging" / "data.json").write_text('{"valid": true}', encoding="utf-8")
    (p_root / ".staging" / "scripts" / "promoted.py").write_text("PROMOTED = 1\n", encoding="utf-8")
    assert _call_main(
        w2pc_mod,
        ["--promote-staging", "--repo-root", str(p_root), "--milestone", "MS-6", "--verify-baseline"],
        monkeypatch,
    ) == 0
    assert (p_root / "scripts" / "promoted.py").is_file() and not (p_root / "obsolete.py").exists()
    (p_root / ".staging" / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (p_root / ".staging" / "nk_tracking" / "oracle_lock.json").write_text('{"locked": true}', encoding="utf-8")
    assert _call_main(w2pc_mod, ["--promote-staging", "--repo-root", str(p_root)], monkeypatch) == 1
    assert _call_main(
        w2pc_mod,
        ["--promote-staging", "--repo-root", str(p_root), "--allow-governance-override"],
        monkeypatch,
    ) == 0


@pytest.mark.fast
def test_prom_cleanup_sbfl_bridge_and_dast_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica safe_cleanup_dev_servers, sbfl_pytest_bridge e DAST shadow verification."""
    assert clean_mod.parse_ports_arg(None) == clean_mod.TARGET_PORTS
    assert clean_mod.parse_ports_arg("8001, bad, 70000, 8001, 8002") == [8001, 8002]
    assert clean_mod.parse_ports_arg([8010, 8010, 0]) == [8010]
    assert clean_mod.parse_ports_arg("nessuna") == clean_mod.TARGET_PORTS
    assert clean_mod._is_subpath_str("", "c:\\a") is False
    assert clean_mod._is_subpath_str("c:\\a\\b", "c:\\a") is True
    assert clean_mod.is_target_workspace_process(0) is False
    assert clean_mod.is_target_workspace_process(os.getpid()) is False
    assert clean_mod.is_target_workspace_process(99999999, workspace_root=tmp_path) is False
    ports_set = clean_mod.scan_listening_port_range(65500, 65505, workspace_root=tmp_path)
    assert ports_set == set() or all(65500 <= p <= 65505 for p in ports_set)
    assert clean_mod.kill_pid_tree(0) is False and clean_mod.kill_pid_tree(os.getpid()) is False
    srv_ws = tmp_path / "srv_ws"
    srv_ws.mkdir()
    assert _call_main(clean_mod, ["--workspace-root", str(srv_ws), "--ports", "65511,65512", "--dry-run"], monkeypatch) == 0
    assert _call_main(clean_mod, ["--workspace-root", str(srv_ws), "--ports", "65511", "--json"], monkeypatch) == 0
    br = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    assert br.collect_passed_line_counts(["tests/test_x.py::test_ok"]) == {}
    calc_f = tmp_path / "calc_bug.py"
    calc_f.write_text("def div(a, b):\n    return a / b\n", encoding="utf-8")
    ok_sum = br.parse_pytest_output("2 passed in 0.05s\n", "", 0, 0.05)
    assert br.extract_failure_location(ok_sum) is None
    fail_sum = br.parse_pytest_output(
        "FAILED test_c.py::test_div\ncalc_bug.py:2: in div\n>   return a / b\nE   ZeroDivisionError: div0\n1 failed, 2 passed in 0.1s\n",
        "",
        1,
        0.1,
    )
    loc_ep = br.extract_failure_location(fail_sum, target_file_hint="calc_bug.py", passed_line_counts={("calc_bug.py", 2): 1})
    loc_no_ep = br.extract_failure_location(fail_sum, passed_line_counts=None)
    assert loc_ep is not None and loc_ep.line_number == 2 and loc_no_ep is not None and loc_no_ep.line_number == 2
    fail_no_arrow = br.parse_pytest_output("FAILED test_c.py::test_a\ncalc_bug.py:2: in div\nE   assert False\n1 failed in 0.1s\n", "", 1, 0.1)
    loc_disk = br.extract_failure_location(fail_no_arrow)
    assert loc_disk is not None and "return a / b" in loc_disk.failing_line_content
    assert dast_mod.run_staging_shadow_verification(tmp_path / "no_dast_repo")["passed"] is False
    mini_dast = tmp_path / "mini_dast"
    for dsub in ("scripts", "tests", "data", ".staging/scripts", ".staging/data"):
        (mini_dast / dsub).mkdir(parents=True)
    (mini_dast / "scripts" / "mod.py").write_text("A = 1\n", encoding="utf-8")
    (mini_dast / "tests" / "test_holdout_secret.py").write_text("def test_h(): assert True\n", encoding="utf-8")
    (mini_dast / "to_remove.txt").write_text("bye", encoding="utf-8")
    (mini_dast / ".staging" / "scripts" / "mod2.py").write_text("B = 2\n", encoding="utf-8")
    (mini_dast / ".staging" / "data" / "ov.json").write_text('{"ov": true}', encoding="utf-8")
    (mini_dast / ".staging" / ".deleted_files.json").write_text('["to_remove.txt"]', encoding="utf-8")
    sh_res = dast_mod.run_staging_shadow_verification(mini_dast, run_pytest=False, run_ast_guard=False, profile="builder")
    assert sh_res["passed"] is True and sh_res["overlay_files_count"] >= 2
    assert _call_main(dast_mod, [], monkeypatch) == 0
    assert _call_main(dast_mod, ["--script", str(tmp_path / "no_script.py")], monkeypatch) == 1


@pytest.mark.fast
def test_prom_bootstrap_and_ecosystem_compliance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica nk_session_bootstrap, RSI verify_convergence e Compliance audit_transcript."""
    b_ws = tmp_path / "boot_clean_ws"
    for sub in ("nk_tracking", ".wal", ".staging"):
        (b_ws / sub).mkdir(parents=True)
    (b_ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"pass_rate_pct": 100.0, "metrics": {"unit_tests_pass_pct": 100.0}}), encoding="utf-8"
    )
    bad_w = b_ws / ".wal" / "corrupt_old.wal"
    bad_w.write_text("{corrupt", encoding="utf-8")
    old_t = time.time() - 3600.0
    os.utime(bad_w, (old_t, old_t))
    tp_b = tmp_path / "boot_tp.jsonl"
    tp_b.write_text('{"source": "USER", "type": "USER_INPUT", "content": "avvia nk hub"}\n', encoding="utf-8")
    rb1 = boot_mod.run_bootstrap(workspace_root=b_ws, transcript_path=tp_b, conversation_id="conv-b1", fast_stat=False, prompt="avvia nk hub")
    assert rb1["status"] == "PASS"
    assert boot_mod.verify_fast_stat_invariant(workspace_root=b_ws, conversation_id="conv-b1")["passed"] is True
    assert boot_mod.verify_project_isolation(workspace_root=b_ws)["passed"] is True
    assert boot_mod.enforce_wal_hygiene(workspace_root=b_ws, ttl_seconds=1.0)["passed"] is True
    assert _call_main(boot_mod, ["--project-root", str(b_ws), "--conversation-id", "conv-b1", "--transcript", str(tp_b), "--prompt", "avvia nk hub"], monkeypatch) == 0
    with open(tp_b, "a", encoding="utf-8") as f_tp:
        f_tp.write('{"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Pronto."}\n')
    assert _call_main(boot_mod, ["--project-root", str(b_ws), "--conversation-id", "conv-b1", "--transcript", str(tp_b), "--json"], monkeypatch) == 0
    ec_ws = tmp_path / "eco_ws"
    (ec_ws / ".agents" / "rules").mkdir(parents=True)
    (ec_ws / ".agents" / "skills" / "Demo").mkdir(parents=True)
    (ec_ws / ".staging").mkdir(parents=True)
    (ec_ws / ".agents" / "AGENTS.md").write_text("# Costituzione [RULE-STE100]\nRegola breve.\n", encoding="utf-8")
    (ec_ws / ".agents" / "rules" / "anti_crash_rules.md").write_text("# Anti Crash\nUsa UTF-8.\n", encoding="utf-8")
    (ec_ws / ".agents" / "skills" / "Demo" / "SKILL.md").write_text("---\nname: Demo\ndescription: Demo.\n---\n# Demo\nLink [x](missing.md).\n", encoding="utf-8")
    (ec_ws / ".staging" / "moj.md").write_text("carattere \ufffd invalido\n", encoding="utf-8")
    rsi_ec = rsi_mod.RSIConvergenceEngine(workspace_root=ec_ws)
    sast_scan = rsi_ec._scan_sast_and_mojibake(ec_ws)
    assert sast_scan["passed"] is False and sast_scan["mojibake_count"] >= 1
    assert rsi_ec.run_benchmark_suite(tmp_path / "missing_bench.py", root_dir=ec_ws)["passed"] is False
    eco_rep = rsi_ec.verify_convergence(root_dir=ec_ws, run_pytest=False, persist_telemetry=False)
    assert "delta_k" in eco_rep and eco_rep["passed"] is False
    chk_c = comp_mod.NKComplianceChecker(workspace_root=ec_ws)
    assert chk_c.audit_transcript(tmp_path / "no_audit_tp.jsonl")["status"] == "ERROR"
    rich_tp = tmp_path / "rich_audit.jsonl"
    rich_records = [
        {"source": "USER", "type": "USER_INPUT", "content": "Esegui verifica."},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "tool_calls": [
            {"id": "c_rf", "name": "read_file", "args": {"Path": "missing.py"}},
            {"id": "c_rc", "name": "run_command", "args": {"CommandLine": "python scripts/ast_guard_validator.py"}},
            {"id": "c_wf1", "name": "write_file", "args": {"Path": "C:/outside_unstage/prod.py"}},
            {"id": "c_wf2", "name": "write_file", "args": {"Path": ".staging/scripts/ok.py"}},
        ]},
        {"source": "TOOL", "type": "TOOL_RESULT", "id": "c_rf", "content": "FileNotFoundError: missing.py"},
        {"source": "TOOL", "type": "TOOL_RESULT", "id": "c_rc", "content": "Command exited with code 2"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Eseguito rsi_convergence_engine.py CONVERGED_OPTIMAL."},
    ]
    rich_tp.write_text("\n".join(json.dumps(r) for r in rich_records) + "\n", encoding="utf-8")
    aud_res = chk_c.audit_transcript(rich_tp)
    assert aud_res["total_steps"] >= 4 and aud_res["metrics"]["ast_guard_executed"] is True and aud_res["metrics"]["healing_loop_executed"] is False


@pytest.mark.integration
def test_carbon_inprocess_promotion_and_ecosystem(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Verifica --help freddo senza pydantic e typing.get_type_hints() su scripts/."""
    _assert_cold_cli_help_no_pydantic("scripts/rsi_convergence_engine.py")
    _assert_all_scripts_type_hints_valid()
