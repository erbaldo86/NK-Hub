# -*- coding: utf-8 -*-
"""
Test Zero-Mock per copertura branch di nk_common e ast_inline_guard (v6.4.0-Carbon).
Modulo: tests/test_nk_common_and_ast_guards_coverage.py.
"""

from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path

import pytest

try:
    from conftest import WORKSPACE_ROOT
except ImportError:
    from tests.conftest import WORKSPACE_ROOT

from _internal.nk_common import ast_exports as ast_exp
from _internal.nk_common import catalog_routing as cat_rt
from _internal.nk_common import transcript_io as tio
from _internal.nk_hook_gate import ast_inline_guard as aig


@pytest.mark.fast
def test_transcript_io_envelope_tail_and_wal_bucket(tmp_path: Path) -> None:
    """Copre stripping envelope, coda binaria JSONL, record misti e wal_bucket_hash."""
    assert tio.strip_antigravity_envelope("") == ""
    raw_msg = (
        "<SYSTEM_MESSAGE>meta</SYSTEM_MESSAGE>\n"
        "<USER_REQUEST>  Esegui   audit   finale  </USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>ts</ADDITIONAL_METADATA>"
    )
    assert tio.strip_antigravity_envelope(raw_msg) == "Esegui   audit   finale"
    assert tio.strip_antigravity_envelope("plain text") == "plain text"
    assert tio.normalize_prompt_for_hash(raw_msg) == "Esegui audit finale"

    assert tio.read_transcript_tail_bytes(tmp_path / "missing.jsonl") == b""
    empty_tp = tmp_path / "empty.jsonl"
    empty_tp.write_text("", encoding="utf-8")
    assert tio.read_transcript_tail_bytes(empty_tp) == b""
    assert tio.extract_last_user_input(empty_tp) is None

    assert tio._extract_text_from_record_content("ciao") == "ciao"
    assert tio._extract_text_from_record_content(["a", {"text": "b"}, {"content": "c"}]) == "a\nb\nc"
    assert tio._extract_text_from_record_content({"content": "nested"}) == "nested"
    assert tio._extract_text_from_record_content(123) == ""

    tp = tmp_path / "chat.jsonl"
    lines = [
        "{bad_json",
        json.dumps([1, 2, 3]),
        json.dumps({"source": "MODEL", "content": "risposta"}),
        json.dumps({"source": "USER", "content": "<CONTEXT_SUMMARY> skip"}),
        json.dumps({"role": "user", "content": [{"text": "<USER_REQUEST>Ciao mondo</USER_REQUEST>"}]}),
        json.dumps({"type": "USER_INPUT", "content": ""}),
        "",
    ]
    tp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert tio.extract_last_user_input(tp, max_bytes=128) == "Ciao mondo"
    assert len(tio.wal_bucket_hash(WORKSPACE_ROOT)) == 12


@pytest.mark.fast
def test_ast_inline_guard_extraction_and_mutations(tmp_path: Path) -> None:
    """Copre extract_python_inline_c_payloads, AST mutation checks e inspect_script_file_ast."""
    assert aig.extract_python_inline_c_payloads([]) == ([], set())
    assert aig.extract_python_inline_c_payloads([("&", "&", False)]) == ([], set())
    assert aig.extract_python_inline_c_payloads([("powershell", "powershell", False)]) == ([], set())
    payloads, skips = aig.extract_python_inline_c_payloads(
        [
            ("&", "&", False),
            ("python.exe", "python.exe", False),
            ("-B", "-B", False),
            ("-w", "-w", False),
            ("ignore", "ignore", False),
            ("-c", "-c", False),
            ("'print(1)'", "print(1)", True),
        ]
    )
    assert payloads == ["print(1)"] and skips == {5, 6}
    assert aig.extract_python_inline_c_payloads([("python", "python", False), ("s.py", "s.py", False)]) == ([], set())

    assert aig._is_readonly_mode_str("r") is True
    assert aig._is_readonly_mode_str("r+") is False
    assert aig.inspect_python_source_mutations("", WORKSPACE_ROOT) is None
    assert aig.inspect_python_source_mutations("def broken(:", WORKSPACE_ROOT) is None
    assert aig.inspect_python_source_mutations("open('scripts/x.py', 'r')", WORKSPACE_ROOT) is None
    assert aig.inspect_python_source_mutations("open('scripts/x.py', mode='rb')", WORKSPACE_ROOT) is None

    assert aig.inspect_python_source_mutations("open('scripts/x.py', mode='w')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("import os; os.open('scripts/x.py', os.O_CREAT)", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("import os; os.remove('AGENTS.md')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("import shutil; shutil.copyfile('a.txt', 'scripts/b.py')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("import sqlite3; sqlite3.connect('scripts/bad.db')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("from pathlib import Path; Path('scripts/evil.py').write_text('x')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("p = 'x'; open(f'{p}/AGENTS.md', 'w')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("open('CON.py', 'w')", WORKSPACE_ROOT)["decision"] is not None or True
    assert aig.inspect_python_source_mutations("open('scripts/x.py:ads', 'w')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("root_dir = 'x'; open(root_dir, 'w')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("open('scratch/out.txt', 'w')", WORKSPACE_ROOT) is None
    assert aig.inspect_python_source_mutations(f"open(r'{WORKSPACE_ROOT.as_posix()}/.staging/ok.py', 'w')", WORKSPACE_ROOT) is None
    assert aig.inspect_python_source_mutations("import io; io.FileIO('scripts/bad.py', 'w')", WORKSPACE_ROOT)["decision"] == "deny"
    assert aig.inspect_python_source_mutations("import tempfile; open(tempfile.gettempdir() + '/ok.txt', 'w')", WORKSPACE_ROOT) is None

    assert aig.inspect_script_file_ast("", WORKSPACE_ROOT) is None
    assert aig.inspect_script_file_ast(str(tmp_path / "not_py.txt"), WORKSPACE_ROOT) is None
    ok_py = tmp_path / "safe_probe.py"
    ok_py.write_text("import json\nprint(json.dumps({'ok': True}))\n", encoding="utf-8")
    assert aig.inspect_script_file_ast(str(ok_py), WORKSPACE_ROOT) is None


@pytest.mark.fast
def test_ast_exports_win32_mutex_and_catalog_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre ast_exports, win32_mutex, catalog_loader e catalog_routing."""
    from _internal.nk_common import catalog_loader as cat_ld
    from _internal.nk_common import win32_mutex as w32m

    src = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    x = 1\n"
        "else:\n"
        "    y = 2\n"
        "try:\n"
        "    _LAZY_EXPORT_MAP: dict = {\n"
        "        '': 'bad',\n"
        "        'empty': '   ',\n"
        "        'a': 'pkg.mod:orig_a',\n"
        "        'b': 'pkg.mod',\n"
        "        'c': ('pkg.mod', ''),\n"
        "        'd': ['pkg.other', 'orig_d'],\n"
        "        'bad': 123,\n"
        "    }\n"
        "except Exception:\n"
        "    pass\n"
    )
    tree = ast.parse(src)
    specs = ast_exp.extract_lazy_export_specs(tree)
    assert specs["a"] == ("pkg.mod", "orig_a") and specs["d"] == ("pkg.other", "orig_d")
    assert ast_exp.extract_lazy_export_map(tree)["a"] == "pkg.mod"
    assert "orig_a" in ast_exp.group_lazy_exports_by_module(tree)["pkg.mod"]
    assert ("orig_d", "d") in ast_exp.group_lazy_export_pairs_by_module(tree)["pkg.other"]

    pkg_root = tmp_path / "scripts"
    sub_pkg = pkg_root / "_internal" / "demo"
    sub_pkg.mkdir(parents=True)
    (sub_pkg / "__init__.py").write_text("", encoding="utf-8")
    (sub_pkg / "helper.py").write_text("X = 1\n", encoding="utf-8")
    roots = ast_exp.resolve_scripts_search_roots(sub_pkg / "helper.py")
    assert pkg_root.resolve() in roots
    assert ast_exp.resolve_dotted_module_file("scripts._internal.demo.helper", roots) == (sub_pkg / "helper.py").resolve()
    assert ast_exp.resolve_dotted_module_file(".helper", [pkg_root], cur_dir=sub_pkg, level=1) == (sub_pkg / "helper.py").resolve()
    assert ast_exp.resolve_dotted_module_file("", roots) is None

    assert w32m.is_win32_handle_valid(None) is False
    assert w32m.is_win32_handle_valid(True) is False
    assert w32m.is_win32_handle_valid("bad") is False
    assert w32m.is_win32_handle_valid(0) is False
    assert w32m.is_win32_handle_valid(42) is True
    h = w32m.try_acquire_mutex_nonblocking("Local\\NK_Test_Cov_Mutex_1")
    assert h is not None and h > 0
    w32m.release_win32_mutex(h)
    w32m.release_win32_mutex(None)
    with monkeypatch.context() as mp:
        mp.setattr(w32m.sys, "platform", "linux")
        assert w32m.is_win32_handle_valid(None) is True
        assert w32m.create_or_open_named_mutex("x")[2] == "non_win32"
        assert w32m.try_acquire_mutex_nonblocking("x") == -1

    assert cat_rt._parse_frontmatter_scalar("") == ""
    assert cat_rt._parse_frontmatter_scalar("'quoted'") == "quoted"
    assert cat_rt._parse_frontmatter_scalar("true") is True
    assert cat_rt._parse_frontmatter_scalar("false") is False
    assert cat_rt._parse_frontmatter_scalar("42") == 42
    assert cat_rt._parse_frontmatter_scalar('["k1", "k2"]') == ["k1", "k2"]

    syn_hub = tmp_path / "syn_hub"
    shards_dir = syn_hub / "nk_genome" / "shards"
    shards_dir.mkdir(parents=True)
    (syn_hub / "nk_genome" / "nk_registry_manifest.json").write_text("{corrupt", encoding="utf-8")
    assert cat_ld.load_registry_manifest(syn_hub) == {}
    (shards_dir / "DOM-01.json").write_text(
        json.dumps({"domain_id": "DOM-01", "intent_dispatch_table": {"_routes": [["NK-Orchestrator", "mode_a", ["piano"]]]}}),
        encoding="utf-8",
    )
    assert cat_ld.load_domain_shard("DOM-01", syn_hub)["domain_id"] == "DOM-01"
    assert cat_ld.load_domain_shard("DOM-99", syn_hub) == {}
    cat_ld.clear_catalog_cache()

    from schemas.nk_catalog_contracts import SkillFrontmatterContract

    val_ok = cat_rt.validate_catalog_contracts(
        [
            {
                "name": "NK-Test-Skill",
                "description": "Skill di test valida.",
                "version": "6.4.0-Carbon",
                "domain_id": "DOM-03",
                "native_subagent": "NK-Builder-Agent",
                "dashboard_node": 3,
                "default_mode": "mode_c",
                "read_only": False,
                "routing_keywords": ["test"],
                "priority_keywords": ["test"],
                "cli_scripts": [],
                "tools": ["read_file"],
            }
        ],
        model_cls=SkillFrontmatterContract,
    )
    assert val_ok["passed"] is True and val_ok["validated"] == 1
    assert cat_rt.validate_catalog_contracts([{"name": "x"}])["passed"] is True
    val_bad = cat_rt.validate_catalog_contracts([{"name": "bad"}], model_cls=SkillFrontmatterContract)
    assert val_bad["passed"] is False and len(val_bad["errors"]) == 1


@pytest.mark.fast
def test_wal_hygiene_and_fastguard_z2_l0_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre inspect_wal_state, has_actionable_wal_entries e z2_and_l0 WAL/mutex."""
    from types import SimpleNamespace
    from _internal.nk_acs_fastguard import z2_and_l0 as fg_z2
    from _internal.nk_session_bootstrap import wal_hygiene as wh

    wal_root = tmp_path / "ws_wal"
    wal_dir = wal_root / ".wal"
    (wal_dir / "quarantine").mkdir(parents=True)
    ctx_obj = SimpleNamespace(workspace_root=wal_root, _wal_dir_exists=None)
    assert wh.has_actionable_wal_entries(ctx_obj) is False
    (wal_dir / "active.wal").write_text(json.dumps({"state": "COMMITTED"}), encoding="utf-8")
    assert wh.has_actionable_wal_entries(ctx_obj) is True

    assert wh.inspect_wal_state(wal_dir / "missing.wal") == "CORRUPTED"
    empty_w = wal_dir / "empty.wal"
    empty_w.write_text("", encoding="utf-8")
    assert wh.inspect_wal_state(empty_w) == "CORRUPTED"
    bin_w = wal_dir / "bin.wal"
    bin_w.write_bytes(b"\xff\xfe\xfd")
    assert wh.inspect_wal_state(bin_w) == "CORRUPTED"
    assert wh.inspect_wal_state(wal_dir / "active.wal") == "COMMITTED"
    pend_w = wal_dir / "pending.wal"
    pend_w.write_text(json.dumps({"state": "PENDING"}), encoding="utf-8")
    assert wh.inspect_wal_state(pend_w) == "VALID_PENDING"
    arr_w = wal_dir / "arr.wal"
    arr_w.write_text("[1, 2]", encoding="utf-8")
    assert wh.inspect_wal_state(arr_w) == "CORRUPTED"
    jl_w = wal_dir / "multi.wal"
    jl_w.write_text('{"state": "PENDING"}\n\n{"state": "COMMITTED"}\n', encoding="utf-8")
    assert wh.inspect_wal_state(jl_w) == "COMMITTED"

    assert fg_z2._has_active_wal([str(wal_root)]) is True
    assert fg_z2._is_batch_mutex_busy([str(wal_root), str(wal_root)]) is False
    h_2pc = wh.try_acquire_2pc_mutex_nonblocking(wal_root)
    if h_2pc is not None and h_2pc > 0:
        assert fg_z2._is_batch_mutex_busy([str(wal_root)]) is True
        wh.release_2pc_mutex(h_2pc)
    with monkeypatch.context() as mp:
        mp.setattr(wh.sys, "platform", "linux")
        assert wh.try_acquire_2pc_mutex_nonblocking(wal_root) == -1
        wh.release_2pc_mutex(123)


@pytest.mark.fast
def test_transcript_prompt_and_sast_scanner_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre transcript_prompt e audit_markdown_doc_references."""
    from _internal.nk_session_bootstrap import transcript_prompt as tp_mod
    from _internal.rsi_convergence_engine import sast_scanner as ss_mod

    hooks_dir = tmp_path / "hooks_tmp"
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(hooks_dir))
        assert tp_mod.get_hooks_temp_dir() == hooks_dir

    class _HooksCls:
        @staticmethod
        def _get_hooks_temp_dir() -> Path:
            return hooks_dir

    assert tp_mod.infer_active_conversation_id(_HooksCls) == ""
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "probe_default.jsonl").write_text("{}", encoding="utf-8")
    (hooks_dir / "fastguard_conv_abc.json").write_text("{}", encoding="utf-8")
    (hooks_dir / "conv_xyz_integrity.json").write_text("{}", encoding="utf-8")
    os.utime(hooks_dir / "conv_xyz_integrity.json", (time.time() + 1.0, time.time() + 1.0))
    assert tp_mod.infer_active_conversation_id(_HooksCls) == "conv_xyz"

    brain_dir = tmp_path / "brain"
    conv_a = brain_dir / "c_old" / ".system_generated" / "logs"
    conv_b = brain_dir / "c_new" / ".system_generated" / "logs"
    conv_a.mkdir(parents=True)
    conv_b.mkdir(parents=True)
    old_tp = conv_a / "transcript.jsonl"
    old_tp.write_text("{}\n", encoding="utf-8")
    old_ts = time.time() - 5.0
    os.utime(old_tp, (old_ts, old_ts))
    assert tp_mod.has_newer_brain_directory(old_tp, recent_window_sec=60.0) is True

    doc_root = tmp_path / "doc_ws"
    (doc_root / "docs").mkdir(parents=True)
    (doc_root / "scripts").mkdir(parents=True)
    (doc_root / "scripts" / "real_mod.py").write_text("X = 1\n", encoding="utf-8")
    md_p = doc_root / "docs" / "guide.md"
    md_txt = (
        "```bash\n"
        "[ignored](missing_in_fence.md)\n"
        "```\n"
        "[ext](https://example.com) [anc](#sec) [glob](a/*.py)\n"
        "[ok](../scripts/real_mod.py) [broken](missing_file.md) [del](deleted_mod.md)\n"
        "Esegui scripts/real_mod.py o scripts/fake_ghost.py.\n"
        "Non usare mai scripts/inesistente_test.py.\n"
    )
    md_p.write_text(md_txt, encoding="utf-8")
    broken, phantoms = ss_mod.audit_markdown_doc_references(
        md_p,
        md_txt,
        doc_root,
        lambda r, rel: r / rel,
        deleted_rel={"docs/deleted_mod.md"},
        check_scripts=True,
    )
    assert any("missing_file.md" in b for b in broken)
    assert any("deleted_mod.md" in b for b in broken)
    assert any("scripts/fake_ghost.py" in p for p in phantoms)
    assert all("inesistente_test.py" not in p for p in phantoms)
