# -*- coding: utf-8 -*-
"""Suite @pytest.mark.fast zero-mock per Milestone 4 NK-GEN-4.0.4 (Kahn Waves, Preflight, Sub-Lane, FE Shadow)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

pytestmark = pytest.mark.fast

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _make_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    (repo / "scripts" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / ".agents").mkdir(parents=True)
    (repo / "nk_tracking" / "anchor").mkdir(parents=True)
    (repo / "nk_genome" / "changelog.d").mkdir(parents=True)
    (repo / "nk_genome" / "plans").mkdir(parents=True)
    (repo / ".staging").mkdir(parents=True)
    return repo


# ---------------------------------------------------------------------------
# 1. Kahn DAG Wave Scheduler (dag_wave_scheduler.py)
# ---------------------------------------------------------------------------

def _build_m4_dag_nodes() -> list:
    from schemas.dual_ledgers_models import TaskDAGNode

    return [
        TaskDAGNode.create("t1", "edit", "NK-Builder-Agent", declared_write_set=["scripts/A.py"], target_repo_root="Hub"),
        TaskDAGNode.create("t2", "edit", "NK-Builder-Agent", declared_write_set=["scripts/a.py"], target_repo_root="hub"),
        TaskDAGNode.create("t3", "edit", "NK-Builder-Agent", declared_write_set=["scripts/a.py"], target_repo_root="App2"),
        TaskDAGNode.create("t4_ro", "audit", "NK-RSI-Auditor", declared_write_set=[], target_repo_root="Hub"),
        TaskDAGNode.create(
            "t5", "merge", "NK-Builder-Agent", parent_ids=["t1", "t1", "t2"],
            lane_id="custom_w", declared_write_set=["scripts/out.py"], target_repo_root="Hub",
        ),
    ]


def test_dag_wave_scheduler_levels_and_coloring() -> None:
    from _internal.nk_common.dag_wave_scheduler import compute_parallel_waves

    plan = compute_parallel_waves(_build_m4_dag_nodes(), parent_lane_prefix="wv", max_lanes=2)
    assert plan.total_tasks == 5
    w0_ids = {t.task_id: t for t in plan.waves[0].tasks}
    assert {"t1", "t3", "t4_ro"}.issubset(w0_ids.keys())
    assert "t2" not in w0_ids

    all_scheduled = [t.task_id for w in plan.waves for t in w.tasks]
    assert sorted(all_scheduled) == ["t1", "t2", "t3", "t4_ro", "t5"]
    t5_item = [t for t in plan.waves[-1].tasks if t.task_id == "t5"][0]
    assert t5_item.lane_id == "custom_w"


def test_dag_wave_scheduler_multirepo_ro_and_ready_wave() -> None:
    from _internal.nk_common.dag_wave_scheduler import compute_parallel_waves, get_ready_wave

    nodes = _build_m4_dag_nodes()
    plan = compute_parallel_waves(nodes, parent_lane_prefix="wv", max_lanes=2)
    w0_ids = {t.task_id: t for t in plan.waves[0].tasks}
    assert w0_ids["t4_ro"].is_read_only is True
    assert w0_ids["t4_ro"].lane_id is None
    assert w0_ids["t1"].lane_id is not None
    assert w0_ids["t1"].lane_id.startswith("wv_0_")

    ready = get_ready_wave(nodes, completed_ids=(), running_ids=["t1", "unknown_id"], max_lanes=2)
    ready_ids = {t.task_id for t in ready.tasks}
    assert "t3" in ready_ids
    assert "t4_ro" in ready_ids
    assert "t2" not in ready_ids


def test_dag_wave_scheduler_error_branches() -> None:
    from schemas.dual_ledgers_models import TaskDAGNode
    from _internal.nk_common.dag_wave_scheduler import compute_parallel_waves, get_ready_wave

    a = TaskDAGNode.create("a", "edit", "NK-Builder-Agent")
    a_dup = TaskDAGNode.create("a", "edit", "NK-Builder-Agent")
    with pytest.raises(ValueError, match="max_lanes"):
        compute_parallel_waves([a], max_lanes=0)
    with pytest.raises(ValueError, match="max_lanes"):
        get_ready_wave([a], (), (), max_lanes=0)
    with pytest.raises(ValueError, match="Duplicate"):
        compute_parallel_waves([a, a_dup])

    orphan = TaskDAGNode.create("b", "edit", "NK-Builder-Agent", parent_ids=["missing_parent"])
    with pytest.raises(ValueError, match="Missing parent"):
        compute_parallel_waves([a, orphan])

    c1 = TaskDAGNode.create("c1", "edit", "NK-Builder-Agent", parent_ids=["c2"])
    c2 = TaskDAGNode.create("c2", "edit", "NK-Builder-Agent", parent_ids=["c1"])
    with pytest.raises(ValueError, match="cycle"):
        compute_parallel_waves([c1, c2])


# ---------------------------------------------------------------------------
# 2. Pre-Flight AST Conflict Predictor (preflight_conflict_predictor.py)
# ---------------------------------------------------------------------------

def test_preflight_predictor_extract_and_all_severities(tmp_path: Path) -> None:
    from _internal.nk_common.lane_registry import register_lane, release_lane
    from _internal.nk_common.preflight_conflict_predictor import (
        extract_python_imported_targets,
        predict_lane_conflicts,
    )

    bad_ast = extract_python_imported_targets("def broken(:\n", file_rel="bad.py")
    assert bad_ast["parse_error"] != ""

    ok_ast = extract_python_imported_targets(
        "import os\nfrom pkg.mod_x import fn_x\nVAL = 1\nclass C:\n    pass\n",
        file_rel="ok.py",
    )
    assert "os" in ok_ast["imported_modules"]
    assert "pkg.mod_x" in ok_ast["imported_modules"]
    assert "fn_x" in ok_ast["imported_names"]
    assert {"val", "c"}.issubset(set(ok_ast["defined_symbols"]))

    repo = _make_repo(tmp_path)
    (repo / "scripts" / "cand_consumer.py").write_text(
        "from pkg.provider_a import make_widget\n", encoding="utf-8"
    )
    (repo / "scripts" / "cand_sym.py").write_text(
        "from alias_helper import shared_fn\n", encoding="utf-8"
    )
    (repo / "scripts" / "cand_rev.py").write_text(
        "def rev_symbol():\n    return 42\n", encoding="utf-8"
    )
    (repo / "scripts" / "notes.txt").write_text("plain text", encoding="utf-8")

    lane_dir = repo / ".staging" / "lanes" / "l_sem" / "scripts" / "pkg"
    lane_dir.mkdir(parents=True)
    (repo / ".staging" / "lanes" / "l_sem" / ".gitkeep").write_text("", encoding="utf-8")
    (lane_dir / "provider_a.py").write_text(
        "from scripts.cand_rev import rev_symbol\ndef make_widget():\n    return 1\n", encoding="utf-8"
    )
    (lane_dir / "helper.py").write_text("def shared_fn():\n    return 2\n", encoding="utf-8")
    (lane_dir / "l_rev.py").write_text(
        "from alias_cand_rev import rev_symbol\n", encoding="utf-8"
    )
    (lane_dir / "bad.py").write_text("def oops(:\n", encoding="utf-8")

    register_lane(repo, "l_sem", "conv_sem_1", declared_write_set=["scripts/extra.py"])
    register_lane(repo, "l_self", "conv_sem_1", declared_write_set=["scripts/cand_consumer.py"])
    try:
        rep_disjoint = predict_lane_conflicts(
            repo, ["scripts/notes.txt", "scripts/missing.py"], exclude_lane_id="l_self"
        )
        assert rep_disjoint.severity == "DISJOINT"
        assert "l_self" not in rep_disjoint.active_lanes_checked

        rep_sem = predict_lane_conflicts(
            repo,
            ["scripts/cand_consumer.py", "scripts/cand_sym.py", "scripts/cand_rev.py"],
            exclude_lane_id="l_self",
        )
        assert rep_sem.severity == "SEMANTIC_COUPLED"
        reasons = {item["reason"].split(":", 1)[0] for item in rep_sem.semantic_couplings}
        assert {
            "candidate_imports_lane_module",
            "lane_imports_candidate_module",
            "symbol_contract_dependency",
            "reverse_symbol_dependency",
        }.issubset(reasons)

        rep_hard = predict_lane_conflicts(
            repo,
            ["./Scripts\\Extra.py"],
            active_lanes_override={"l_sem": {"declared_write_set": ["scripts/extra.py"]}},
        )
        assert rep_hard.severity == "HARD_CONFLICT"
        assert rep_hard.hard_conflicts[0]["overlapping_paths"] == ["scripts/extra.py"]
        assert rep_hard.duration_ms < 500.0
    finally:
        release_lane(repo, "l_sem", None, force=True)
        release_lane(repo, "l_self", None, force=True)


# ---------------------------------------------------------------------------
# 3. TaskDAGNode Backward Compatibility & Ledger Integrity
# ---------------------------------------------------------------------------

def test_task_dag_node_backward_compat_and_m4_hash(tmp_path: Path) -> None:
    from schemas.dual_ledgers_models import TaskDAGNode
    from _internal.nk_common.ledger_runtime import TaskLedger

    legacy_node = TaskDAGNode.create("t_leg", "edit", "NK-Builder-Agent", payload={"k": 1}, prev_hash="0" * 64)
    rehydrated = TaskDAGNode.model_validate(json.loads(legacy_node.model_dump_json()))
    assert rehydrated.verify_integrity("0" * 64) is True
    assert rehydrated.lane_id is None and rehydrated.declared_write_set == [] and rehydrated.target_repo_root is None

    ledger = TaskLedger(tmp_path / "tasks.jsonl")
    n1 = ledger.add_task("t_leg", "edit", "NK-Builder-Agent", payload={"x": 1})
    n2 = ledger.add_task(
        "t_m4", "build", "NK-Builder-Agent", parent_ids=["t_leg"],
        lane_id="w_0_0", declared_write_set=["scripts/a.py"], target_repo_root="NK_Hub",
    )
    assert n2.verify_integrity(n1.node_hash) is True
    tampered = n2.model_copy(update={"lane_id": "w_other"})
    assert tampered.verify_integrity(n1.node_hash) is False


# ---------------------------------------------------------------------------
# 4. Sub-Lane Consolidator & CLI (sublane_consolidator.py, win32_2pc_engine.py)
# ---------------------------------------------------------------------------

def test_sublane_helpers_and_no_sublanes(tmp_path: Path) -> None:
    import win32_2pc_engine
    from _internal.win32_2pc_engine.sublane_consolidator import (
        consolidate_sublanes_and_promote,
        discover_sublanes,
        is_sublane_of,
    )

    assert is_sublane_of("w1_a", "w1") is True
    assert is_sublane_of("w1-b", "w1") is True
    assert is_sublane_of("w1", "w1") is False
    assert is_sublane_of("other", "w1") is False

    repo = _make_repo(tmp_path, "consolidate_repo")
    assert discover_sublanes(repo, "w1") == []

    no_sub = consolidate_sublanes_and_promote(repo, "w1")
    assert no_sub["passed"] is False
    assert no_sub["status"] == "NO_SUBLANES_FOUND"
    assert win32_2pc_engine.main(["--consolidate-sublanes", "--repo-root", str(repo), "--parent-lane", "w1"]) == 1

    bad_dir = repo / ".staging" / "lanes" / "CON"
    bad_dir.mkdir(parents=True)
    assert discover_sublanes(repo, "w1") == []


def test_sublane_conflict_and_gate_failures(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.sublane_consolidator import consolidate_sublanes_and_promote

    repo = _make_repo(tmp_path, "consolidate_conflict_repo")
    sub_a = repo / ".staging" / "lanes" / "w1_a"
    sub_b = repo / ".staging" / "lanes" / "w1-b"
    (sub_a / "docs").mkdir(parents=True)
    (sub_b / "docs").mkdir(parents=True)
    (sub_a / "docs" / "Same.txt").write_text("A", encoding="utf-8")
    (sub_b / "docs" / "same.txt").write_text("B", encoding="utf-8")

    conf = consolidate_sublanes_and_promote(repo, "w1")
    assert conf["passed"] is False
    assert conf["status"] == "SUBLANE_WRITE_CONFLICT"

    (sub_b / "docs" / "same.txt").unlink()
    (sub_b / "docs" / "b.txt").write_text("from_b", encoding="utf-8")

    with pytest.raises(ValueError, match="non e sub-lane"):
        consolidate_sublanes_and_promote(repo, "w1", sublane_ids=["not_child"])

    gate_fail = consolidate_sublanes_and_promote(
        repo, "w1", run_combined_gate_fn=lambda _dir, _pid: {"passed": False, "reason": "test_fail"}
    )
    assert gate_fail["passed"] is False
    assert gate_fail["status"] == "COMBINED_GATE_FAILED"


def test_sublane_full_merge_and_promote_cleanup(tmp_path: Path) -> None:
    from _internal.nk_common.lane_registry import register_lane, release_lane
    from _internal.win32_2pc_engine.sublane_consolidator import consolidate_sublanes_and_promote

    repo = _make_repo(tmp_path, "consolidate_ok_repo")
    sub_a = repo / ".staging" / "lanes" / "w1_a"
    sub_b = repo / ".staging" / "lanes" / "w1-b"
    (sub_a / "docs").mkdir(parents=True)
    (sub_b / "docs").mkdir(parents=True)
    (sub_a / "docs" / "Same.txt").write_text("A", encoding="utf-8")
    (sub_b / "docs" / "b.txt").write_text("from_b", encoding="utf-8")

    obsolete = repo / "docs" / "obsolete.txt"
    obsolete.parent.mkdir(parents=True, exist_ok=True)
    obsolete.write_text("old", encoding="utf-8")
    (sub_b / ".deleted_files.json").write_text(json.dumps(["docs/obsolete.txt"]), encoding="utf-8")

    register_lane(repo, "w1", "conv_p")
    register_lane(repo, "w1_a", "conv_p")
    register_lane(repo, "w1-b", "conv_p")
    ok_res = consolidate_sublanes_and_promote(
        repo, "w1", milestone="NK-GEN-4.0.4",
        run_combined_gate_fn=lambda tmp_dir, pid: {
            "passed": (tmp_dir / "docs" / "Same.txt").is_file() and (tmp_dir / "docs" / "b.txt").is_file(),
            "lane": pid,
        },
    )
    assert ok_res["passed"] is True
    assert ok_res["status"] == "CONSOLIDATED_PROMOTED"
    assert (repo / "docs" / "Same.txt").read_text(encoding="utf-8") == "A"
    assert (repo / "docs" / "b.txt").read_text(encoding="utf-8") == "from_b"
    assert not obsolete.exists()
    assert not sub_a.exists()
    assert not sub_b.exists()
    release_lane(repo, "w1", None, force=True)


# ---------------------------------------------------------------------------
# 5. PATCH_NOTES.md Frontmatter Preservation (post_commit_consolidator.py)
# ---------------------------------------------------------------------------

def test_patch_notes_frontmatter_preserved_on_materialize(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.post_commit_consolidator import materialize_changelog_fragments

    repo = _make_repo(tmp_path)
    pn = repo / "nk_genome" / "PATCH_NOTES.md"
    pn.write_text(
        "---\ntitle: \"PN\"\nversion: \"1.0\"\n---\n\n# Patch Notes\n\n> Header\n\n---\n\n## [OLD] (2026-01-01)\n\n* old item\n",
        encoding="utf-8",
    )
    (repo / "nk_genome" / "changelog.d" / "001.md").write_text("## [NEW] (2026-11-25)\n\n* new item", encoding="utf-8")
    (repo / "nk_genome" / "changelog.d" / "002_dup.md").write_text("## [OLD] (2026-01-01)\n\n* dup", encoding="utf-8")

    consumed = materialize_changelog_fragments(repo)
    assert consumed == ["001.md", "002_dup.md"]
    out = pn.read_text(encoding="utf-8")
    assert out.startswith("---\ntitle: \"PN\"")
    assert out.index("## [NEW]") < out.index("## [OLD]")
    assert out.count("## [OLD]") == 1
    assert not (repo / "nk_genome" / "changelog.d" / "001.md").exists()

    # Fallback when file has no ## section yet
    pn2 = repo / "nk_genome" / "PATCH_NOTES.md"
    pn2.write_text("---\nk: v\n---\n\n# Title\n", encoding="utf-8")
    (repo / "nk_genome" / "changelog.d" / "003.md").write_text("## [FIRST] (2026-11-25)\n\n* init", encoding="utf-8")
    materialize_changelog_fragments(repo)
    out2 = pn2.read_text(encoding="utf-8")
    assert out2.startswith("---\nk: v\n---\n\n# Title") and "## [FIRST]" in out2


# ---------------------------------------------------------------------------
# 6. Ownership nk_genome/plans/<lane_id>.md & Promote Tokens
# ---------------------------------------------------------------------------

def test_lane_plan_ownership_and_promote_tokens(tmp_path: Path) -> None:
    from _internal.nk_common.lane_paths import extract_lane_plan_id_from_rel_parts, is_valid_lane_plan_rel_parts
    from _internal.nk_common.lane_registry import register_lane, release_lane
    from _internal.nk_hook_gate.constants_patterns import has_win32_2pc_promote_tokens
    from _internal.nk_hook_gate.lane_write_guard import extract_promote_lane_and_staging
    from _internal.nk_hook_gate.write_gate import _handle_write_gate

    assert extract_lane_plan_id_from_rel_parts(("nk_genome", "plans", "w1_a.md")) == "w1_a"
    assert is_valid_lane_plan_rel_parts(("nk_genome", "plans", "CON.md")) is False
    assert is_valid_lane_plan_rel_parts(("nk_genome", "plans", "a.txt")) is False
    assert has_win32_2pc_promote_tokens(["python", "win32_2pc_engine.py", "--consolidate-sublanes", "--parent-lane", "w1"]) is True
    assert extract_promote_lane_and_staging(["--consolidate-sublanes", "--parent-lane=w1"]) == ("w1", None)
    with pytest.raises(ValueError, match="conflitto"):
        extract_promote_lane_and_staging(["--parent-lane", "w1", "--lane-id", "w2"])

    repo = _make_repo(tmp_path)
    register_lane(repo, "w1_a", "conv_owner_1")
    try:
        allow_v = _handle_write_gate(
            {}, repo, True, str(repo / "nk_genome" / "plans" / "w1_a.md"), "", "plan", conv_id="conv_owner_1"
        )
        assert allow_v == {}

        deny_other = _handle_write_gate(
            {}, repo, True, str(repo / "nk_genome" / "plans" / "w1_a.md"), "", "plan", conv_id="conv_stranger_2"
        )
        assert deny_other.get("decision") == "deny" and deny_other.get("reason_code") == "LANE_OWNERSHIP_DENIED"

        deny_bad_name = _handle_write_gate(
            {}, repo, True, str(repo / "nk_genome" / "plans" / "con.md"), "", "plan", conv_id="conv_owner_1"
        )
        assert deny_bad_name.get("decision") == "deny"

        deny_cross = _handle_write_gate(
            {}, repo, True, str(repo / ".staging" / "lanes" / "w1_a" / "nk_genome" / "plans" / "w1_b.md"),
            "", "plan", conv_id="conv_owner_1",
        )
        assert deny_cross.get("decision") == "deny" and deny_cross.get("reason_code") == "LANE_OWNERSHIP_DENIED"
    finally:
        release_lane(repo, "w1_a", None, force=True)


# ---------------------------------------------------------------------------
# 7. Frontend Shadow Sandbox (fe_shadow.py) & Real NTFS Junction Teardown
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_cmd",
    [
        ["npm", "install"],
        "npm ci",
        ["npx", "npm", "i", "pkg"],
        "yarn",
        ["yarn", "add", "react"],
        ["pnpm", "install"],
        ["bun", "add", "zod"],
        "echo hi && npm update",
        ["npm", "--prefix", ".", "install"],
        ["npm", "--loglevel", "verbose", "ci"],
        ["pnpm", "-C", "web", "add", "zod"],
        ["yarn", "--cwd", "."],
        ["yarn", "--cwd", "web", "add", "react"],
        ["cmd", "/c", "npm install"],
        ["cmd", "/c", "npm", "install"],
        "cmd /c npm install",
        "powershell -Command npm ci",
        ["npm", "exec", "--", "npm", "install"],
        ["npm", "exec", "npm", "install"],
    ],
)
def test_fe_shadow_blocks_node_modules_mutation_commands(bad_cmd: object) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import assert_no_node_modules_mutation_cmd

    with pytest.raises(ValueError, match="NODE_MODULES_MUTATION_FORBIDDEN"):
        assert_no_node_modules_mutation_cmd(bad_cmd)


def test_fe_shadow_allows_readonly_cmds_and_reparse_guard(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import (
        assert_no_node_modules_mutation_cmd,
        remove_junction_safely,
    )

    assert_no_node_modules_mutation_cmd(["npm", "test", "--", "--run"])
    assert_no_node_modules_mutation_cmd(["npx", "vitest", "run"])
    assert_no_node_modules_mutation_cmd(["npm", "--prefix", ".", "test", "--", "--run"])
    assert_no_node_modules_mutation_cmd(["npm", "run", "build"])

    real_dir = tmp_path / "real_not_junction"
    real_dir.mkdir()
    with pytest.raises(ValueError, match="reparse"):
        remove_junction_safely(real_dir)
    assert remove_junction_safely(tmp_path / "nonexistent") is True


@pytest.mark.integration
def test_fe_shadow_ntfs_junction_sandbox_and_lease_cleanup(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import FrontendShadowSandbox
    from _internal.nk_common.lane_leases import list_active_leases

    repo = _make_repo(tmp_path)
    host_nm = tmp_path / "host_node_modules"
    (host_nm / "pkg").mkdir(parents=True)
    sentinel = host_nm / "pkg" / "sentinel.txt"
    sentinel.write_text("KEEP_ME_INTACT", encoding="utf-8")

    with FrontendShadowSandbox(repo, lane_id="fe_junc", host_node_modules=host_nm) as sb:
        assert sb.shadow_dir is not None
        assert sb.fe_port != sb.be_port
        assert (sb.shadow_dir / "node_modules" / "pkg" / "sentinel.txt").read_text(encoding="utf-8") == "KEEP_ME_INTACT"
        proc = sb.run_command([sys.executable, "-c", "import os; print(os.environ['PORT'], os.environ['API_PORT'])"])
        assert proc.returncode == 0
        with pytest.raises(ValueError, match="NODE_MODULES_MUTATION_FORBIDDEN"):
            sb.run_command(["npm", "install"])
        sb_path = sb.shadow_dir
        lease_id = sb.lease_id

    assert not sb_path.exists()
    assert sentinel.read_text(encoding="utf-8") == "KEEP_ME_INTACT"
    assert all(entry["lease_id"] != lease_id for entry in list_active_leases(repo, prune_dead=False))


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction check requires Windows")
def test_fe_shadow_safe_rmtree_preserves_junction_target(tmp_path: Path) -> None:
    from _internal.nk_common.nvme_mirror_helpers import safe_rmtree

    host_nm = tmp_path / "host_node_modules"
    (host_nm / "pkg").mkdir(parents=True)
    sentinel = host_nm / "pkg" / "sentinel.txt"
    sentinel.write_text("KEEP_ME_INTACT", encoding="utf-8")

    outer = tmp_path / "outer_with_junc"
    outer.mkdir()
    inner_j = outer / "linked_nm"
    mk_proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(inner_j), str(host_nm)], capture_output=True, text=True)
    assert mk_proc.returncode == 0
    assert safe_rmtree(outer) is True
    assert not outer.exists()
    assert sentinel.read_text(encoding="utf-8") == "KEEP_ME_INTACT"


@pytest.mark.integration
def test_fe_shadow_detect_and_e2e_suite_gates(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import (
        detect_frontend_project,
        evaluate_frontend_test_suite,
    )

    fe_proj = tmp_path / "fe_proj"
    fe_proj.mkdir()
    assert detect_frontend_project(fe_proj)["is_frontend"] is False
    (fe_proj / "package.json").write_text(json.dumps({"name": "fe", "scripts": {}}), encoding="utf-8")
    (fe_proj / "e2e").mkdir()
    assert detect_frontend_project(fe_proj)["empty_e2e_dir"] is True

    runner_fn = lambda cmd, cwd, env, timeout_sec: subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout_sec)
    res_empty = evaluate_frontend_test_suite(fe_proj, os.environ.copy(), 15.0, runner_fn)
    assert res_empty["passed"] is False
    assert res_empty["exit_code"] == 5

    (fe_proj / "e2e" / "app.spec.ts").write_text("export {};\n", encoding="utf-8")
    assert detect_frontend_project(fe_proj)["e2e_test_files_count"] == 1
    res_nocmd = evaluate_frontend_test_suite(fe_proj, os.environ.copy(), 15.0, runner_fn)
    assert res_nocmd["passed"] is False
    assert res_nocmd["exit_code"] == 5

    res_mut = evaluate_frontend_test_suite(fe_proj, os.environ.copy(), 15.0, runner_fn, cmd_override=["npm", "ci"])
    assert res_mut["passed"] is False
    assert res_mut["exit_code"] == 2

    res_ok = evaluate_frontend_test_suite(
        fe_proj, os.environ.copy(), 15.0, runner_fn, lane_id="fe_w1",
        cmd_override=[sys.executable, "-c", "import os; print('ok', os.environ['NK_FE_PORT'])"],
    )
    assert res_ok["passed"] is True
    assert res_ok["exit_code"] == 0
    assert "ok" in res_ok["stdout"]


# ---------------------------------------------------------------------------
# 8. Wave Dispatch Anchor (nk_session_handoff.py)
# ---------------------------------------------------------------------------

def test_record_wave_dispatch_anchor_and_validation(tmp_path: Path) -> None:
    import nk_session_handoff

    repo = _make_repo(tmp_path)
    res = nk_session_handoff.record_wave_dispatch_anchor(
        0, [{"task_id": "t1", "lane_id": "w_0_0"}], milestone_id="NK-GEN-4.0.4", root=repo,
    )
    assert res["passed"] is True and res["event"] == "wave_dispatch" and res["task_count"] == 1
    anchor_lines = Path(res["anchor_path"]).read_text(encoding="utf-8").splitlines()
    assert json.loads(anchor_lines[-1])["milestone_id"] == "NK-GEN-4.0.4"

    with pytest.raises(ValueError, match="booleano"):
        nk_session_handoff.record_wave_dispatch_anchor(True, [], root=repo)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=">= 0"):
        nk_session_handoff.record_wave_dispatch_anchor(-1, [], root=repo)


# ---------------------------------------------------------------------------
# 9. Hook Purity python -B -S (Zero pydantic)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_hook_stdlib_purity_under_python_dash_s() -> None:
    code = (
        "import sys; "
        "import _internal.nk_common.lane_paths, _internal.nk_common.lane_registry, "
        "_internal.nk_hook_gate.constants_patterns, _internal.nk_hook_gate.path_safety, "
        "_internal.nk_hook_gate.lane_write_guard, _internal.nk_hook_gate.write_gate; "
        "assert 'pydantic' not in sys.modules, 'pydantic leaked under -S'"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS_DIR)
    proc = subprocess.run([sys.executable, "-B", "-S", "-c", code], env=env, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_fe_shadow_edge_guards_malformed_pkg_and_no_junction(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import (
        FrontendShadowSandbox,
        assert_no_node_modules_mutation_cmd,
        detect_frontend_project,
    )

    assert_no_node_modules_mutation_cmd("echo ok &&   ")
    assert_no_node_modules_mutation_cmd(["npx"])

    repo = _make_repo(tmp_path, "fe_plain_repo")
    unentered = FrontendShadowSandbox(repo, lane_id="fe_plain")
    with pytest.raises(RuntimeError, match="non attivo"):
        unentered.run_command(["echo", "hi"])

    with FrontendShadowSandbox(repo, lane_id="fe_plain") as sb:
        assert sb.junction_path is None
        assert sb.shadow_dir is not None

    bad_fe = tmp_path / "bad_fe"
    (bad_fe / "e2e").mkdir(parents=True)
    (bad_fe / "e2e" / "readme.txt").write_text("not a spec", encoding="utf-8")
    (bad_fe / "package.json").write_text("{broken json", encoding="utf-8")
    info = detect_frontend_project(bad_fe)
    assert info["is_frontend"] is False
    assert info["empty_e2e_dir"] is True


def test_sublane_edge_filters_explicit_ids_delete_conflict_and_preclean(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.sublane_consolidator import (
        consolidate_sublanes_and_promote,
        discover_sublanes,
    )

    repo = _make_repo(tmp_path, "sub_edge_repo")
    lanes_dir = repo / ".staging" / "lanes"
    lanes_dir.mkdir(parents=True, exist_ok=True)
    (lanes_dir / "note.txt").write_text("ignore", encoding="utf-8")
    (lanes_dir / "other_w").mkdir()
    sub_a = lanes_dir / "w2_a"
    sub_b = lanes_dir / "w2-b"
    sub_a.mkdir()
    (sub_b / "docs").mkdir(parents=True)
    (sub_a / ".gitkeep").write_text("", encoding="utf-8")
    (sub_a / ".deleted_files.json").write_text(json.dumps(["docs/dup.txt"]), encoding="utf-8")
    (sub_b / ".deleted_files.json").write_text(json.dumps(["docs/dup.txt"]), encoding="utf-8")

    found_ids = [sid for sid, _ in discover_sublanes(repo, "w2")]
    assert found_ids == ["w2-b", "w2_a"]

    del_conf = consolidate_sublanes_and_promote(repo, "w2", sublane_ids=["w2_a", "w2-b"])
    assert del_conf["passed"] is False
    assert del_conf["status"] == "SUBLANE_WRITE_CONFLICT"

    (sub_b / ".deleted_files.json").unlink()
    (sub_b / "docs" / "ok.txt").write_text("ok", encoding="utf-8")
    stale_parent = lanes_dir / "w2"
    stale_parent.mkdir()
    (stale_parent / "old.txt").write_text("stale", encoding="utf-8")

    res = consolidate_sublanes_and_promote(
        repo, "w2", sublane_ids=["w2_a", "w2-b"], cleanup_sublanes=False, release_sublanes=False,
        run_combined_gate_fn=lambda _d, _p: {"passed": True},
    )
    assert res["passed"] is True
    assert res["status"] == "CONSOLIDATED_PROMOTED"
    assert sub_a.exists()
    assert sub_b.exists()


def test_sublane_commit_train_branch_dispatch(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry, ensure_commit_train_hmac_key
    from _internal.win32_2pc_engine.sublane_consolidator import consolidate_sublanes_and_promote

    repo = _make_repo(tmp_path, "sub_ct_repo")
    ct_key = tmp_path / "ct_hmac.key"
    ensure_commit_train_hmac_key(ct_key)
    append_commit_train_entry(
        repo, batch_id="b1", lane_id="other", milestone="M4",
        committed_files=["docs/c.txt"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=ct_key,
    )
    sub_a = repo / ".staging" / "lanes" / "w3_a" / "docs"
    sub_a.mkdir(parents=True)
    (sub_a / "c.txt").write_text("c", encoding="utf-8")

    res = consolidate_sublanes_and_promote(
        repo, "w3", use_commit_train=True, base_seq=0, key_path=ct_key,
        run_combined_gate_fn=lambda _d, _p: {"passed": True},
    )
    assert res["passed"] is False
    assert res["status"] == "OCC_WRITE_CONFLICT"
    assert res["promote_result"]["status"] == "OCC_WRITE_CONFLICT"


def test_dag_wave_scheduler_three_parent_join() -> None:
    from schemas.dual_ledgers_models import TaskDAGNode
    from _internal.nk_common.dag_wave_scheduler import compute_parallel_waves

    nodes = [
        TaskDAGNode.create("p1", "edit", "NK-Builder-Agent", declared_write_set=["scripts/p1.py"]),
        TaskDAGNode.create("p2", "edit", "NK-Builder-Agent", declared_write_set=["scripts/p2.py"]),
        TaskDAGNode.create("p3", "edit", "NK-Builder-Agent", declared_write_set=["scripts/p3.py"]),
        TaskDAGNode.create("join", "merge", "NK-Builder-Agent", parent_ids=["p1", "p2", "p3"], declared_write_set=["scripts/j.py"]),
    ]
    plan = compute_parallel_waves(nodes, parent_lane_prefix="wj", max_lanes=3)
    assert plan.total_tasks == 4
    assert [t.task_id for t in plan.waves[-1].tasks] == ["join"]


def test_preflight_reads_live_declared_write_set_for_semantic_ast(tmp_path: Path) -> None:
    from _internal.nk_common.preflight_conflict_predictor import predict_lane_conflicts

    repo = _make_repo(tmp_path, "preflight_live_repo")
    (repo / "scripts" / "pkg" / "live_target.py").write_text("def exported_api() -> int:\n    return 1\n", encoding="utf-8")
    (repo / "scripts" / "pkg" / "cand_user.py").write_text("from scripts.pkg.live_target import exported_api\n", encoding="utf-8")

    active = {
        "w_live": {
            "lane_id": "w_live",
            "status": "ACTIVE",
            "declared_write_set": ["scripts/pkg/live_target.py"],
        }
    }
    report = predict_lane_conflicts(repo, ["scripts/pkg/cand_user.py"], active_lanes_override=active)
    assert report.severity == "SEMANTIC_COUPLED"
    assert len(report.semantic_couplings) >= 1


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction check requires Windows")
def test_preflight_skips_reparse_lane_dir_junction(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import remove_junction_safely
    from _internal.nk_common.preflight_conflict_predictor import predict_lane_conflicts

    repo = _make_repo(tmp_path, "preflight_junc_repo")
    ext_dir = tmp_path / "ext_lane_target"
    (ext_dir / "scripts" / "pkg").mkdir(parents=True)
    (ext_dir / "scripts" / "pkg" / "secret.py").write_text("x = 1\n", encoding="utf-8")

    junc_lane = repo / ".staging" / "lanes" / "w_junc"
    junc_lane.parent.mkdir(parents=True, exist_ok=True)
    mk = subprocess.run(["cmd", "/c", "mklink", "/J", str(junc_lane), str(ext_dir)], capture_output=True, text=True)
    assert mk.returncode == 0
    try:
        active = {"w_junc": {"lane_id": "w_junc", "status": "ACTIVE", "declared_write_set": []}}
        report = predict_lane_conflicts(repo, ["scripts/pkg/secret.py"], active_lanes_override=active)
        assert report.severity == "DISJOINT"
        assert report.hard_conflicts == []
    finally:
        remove_junction_safely(junc_lane)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction check requires Windows")
def test_sublane_rejects_reparse_dir_inside_sublane(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import remove_junction_safely
    from _internal.win32_2pc_engine.sublane_consolidator import consolidate_sublanes_and_promote

    repo = _make_repo(tmp_path, "sub_reparse_repo")
    ext_dir = tmp_path / "ext_sub_dir"
    ext_dir.mkdir(parents=True)
    sub_a = repo / ".staging" / "lanes" / "w4_a"
    sub_a.mkdir(parents=True)
    junc = sub_a / "linked_dir"
    mk = subprocess.run(["cmd", "/c", "mklink", "/J", str(junc), str(ext_dir)], capture_output=True, text=True)
    assert mk.returncode == 0
    try:
        with pytest.raises(OSError, match="Reparse"):
            consolidate_sublanes_and_promote(repo, "w4")
    finally:
        remove_junction_safely(junc)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction check requires Windows")
def test_fe_shadow_e2e_counts_nested_and_skips_junctions(tmp_path: Path) -> None:
    from _internal.dast_sandbox_runner.fe_shadow import detect_frontend_project, remove_junction_safely

    ext_specs = tmp_path / "ext_specs"
    ext_specs.mkdir()
    (ext_specs / "ext.spec.ts").write_text("export {};\n", encoding="utf-8")
    (ext_specs / "ext2.spec.ts").write_text("export {};\n", encoding="utf-8")

    proj1 = tmp_path / "fe_nested_junc"
    (proj1 / "e2e" / "nested").mkdir(parents=True)
    (proj1 / "package.json").write_text(json.dumps({"name": "fe1", "scripts": {"test": "vitest"}}), encoding="utf-8")
    (proj1 / "e2e" / "nested" / "sub.spec.ts").write_text("export {};\n", encoding="utf-8")
    j_sub = proj1 / "e2e" / "linked_ext"
    mk1 = subprocess.run(["cmd", "/c", "mklink", "/J", str(j_sub), str(ext_specs)], capture_output=True, text=True)
    assert mk1.returncode == 0

    proj2 = tmp_path / "fe_root_junc"
    proj2.mkdir()
    (proj2 / "package.json").write_text(json.dumps({"name": "fe2", "scripts": {}}), encoding="utf-8")
    j_root = proj2 / "e2e"
    mk2 = subprocess.run(["cmd", "/c", "mklink", "/J", str(j_root), str(ext_specs)], capture_output=True, text=True)
    assert mk2.returncode == 0

    try:
        info1 = detect_frontend_project(proj1)
        assert info1["has_e2e_dir"] is True
        assert info1["e2e_test_files_count"] == 1
        info2 = detect_frontend_project(proj2)
        assert info2["has_e2e_dir"] is False
        assert info2["e2e_test_files_count"] == 0
    finally:
        remove_junction_safely(j_sub)
        remove_junction_safely(j_root)
