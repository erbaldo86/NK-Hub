# -*- coding: utf-8 -*-
"""
Suite Mutation-Killing & Branch-Coverage Zero-Mock per i 4 moduli M2:
lane_paths, lane_registry, active_slot_io e nvme_mirror_helpers.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

from _internal.nk_common import lane_paths as lp
from _internal.nk_common import lane_registry as lreg
from _internal.nk_common import nvme_mirror_helpers as nmh
from _internal.tensor_rsi import active_slot_io as sio
from _internal.tensor_rsi.ticket_auth import TicketAuthError


@pytest.mark.fast
def test_mut_lane_paths_id_and_strip() -> None:
    """Copre validate_lane_id, strip_staging_rel_parts ed extract_lane_id_from_path."""
    for bad in (None, 123, "", "   ", "a/b", "a\\b", "a..b", "a\x00b", "-lead", "A" * 49):
        with pytest.raises(ValueError):
            lp.validate_lane_id(bad)  # type: ignore[arg-type]
    for reserved in ("lanes", "LEGACY", "Active", "default", "index", "ALL", "con", "com1", "lpt9"):
        with pytest.raises(ValueError):
            lp.validate_lane_id(reserved)
    assert (lp.validate_lane_id("Z9_ok-1"), len(lp.validate_lane_id("a" * 48))) == ("z9_ok-1", 48)
    assert (
        lp.strip_staging_rel_parts(("scripts", "a.py")),
        lp.strip_staging_rel_parts((".Staging", "lanes", "Lane1", "scripts", "a.py")),
        lp.strip_staging_rel_parts(("root", ".staging", "file.py")),
    ) == ((-1, ("scripts", "a.py"), None), (0, ("scripts", "a.py"), "Lane1"), (1, ("file.py",), None))
    assert (
        lp.extract_lane_id_from_path(123), lp.extract_lane_id_from_path("scripts/x.py"),  # type: ignore[arg-type]
        lp.extract_lane_id_from_path(".staging/lanes/"), lp.extract_lane_id_from_path(".staging/lanes/beta/scripts/x.py"),
    ) == (None, None, None, "beta")


@pytest.mark.fast
def test_mut_lane_paths_resolve_and_tokens(tmp_path: Path) -> None:
    """Copre resolve_staging_dir, is_skipped_lane_root_entry, subpath e token guard."""
    repo = tmp_path / "repo_lp"
    (repo / ".staging" / "lanes").mkdir(parents=True)
    with pytest.raises(ValueError):
        lp.resolve_staging_dir(repo, staging_dir=repo / ".staging" / "lanes")
    with pytest.raises(ValueError):
        lp.resolve_staging_dir(repo, staging_dir=repo / ".staging" / "lanes" / "a" / "nested")

    custom_stg, stg_root = repo / "custom_stg", (repo / ".staging").resolve()
    assert (
        lp.resolve_staging_dir(repo, staging_dir="custom_stg"),
        lp.resolve_staging_dir(repo, lane_id="ok1", staging_dir=".staging/lanes/ok1"),
        lp.is_skipped_lane_root_entry(repo / ".staging", ("lanes", "x.py")),
        lp.is_skipped_lane_root_entry(repo / "other", ("lanes",)),
    ) == (
        (custom_stg.resolve(), None),
        ((repo / ".staging" / "lanes" / "ok1").resolve(), "ok1"),
        True,
        False,
    )
    assert (
        lp.is_valid_lane_subpath_no_reparse(stg_root, stg_root),
        lp.is_valid_lane_subpath_no_reparse(repo.resolve(), stg_root),
        lp.is_valid_lane_subpath_no_reparse(stg_root / "lanes", stg_root),
        lp.is_valid_lane_subpath_no_reparse(stg_root / "lanes" / "registry.json" / "x", stg_root),
        lp.is_valid_lane_subpath_no_reparse(stg_root / "lanes" / "nul" / "x.py", stg_root),
        lp.is_valid_lane_subpath_no_reparse(stg_root / "lanes" / "ok1" / "x.py", stg_root),
    ) == (True, False, False, False, False, True)
    assert (
        lp.is_unsafe_lane_staged_token(""),
        lp.is_unsafe_lane_staged_token("NK_Hub/.staging/scripts/a.py"),
        lp.is_unsafe_lane_staged_token('".staging/lanes/x"'),
        lp.is_unsafe_lane_staged_token(".staging/lanes/registry.json/a"),
        lp.is_unsafe_lane_staged_token(".staging/lanes/aux/a.py"),
        lp.is_unsafe_lane_staged_token(".staging/lanes/lane_ok/scripts/a.py"),
    ) == (False, False, True, True, True, False)


@pytest.mark.fast
def test_mut_lane_registry_validation(tmp_path: Path) -> None:
    """Copre is_valid_owner_cid e tutti i blocchi di validazione in register_lane."""
    for bad_cid in (None, 42, "", "x" * 65, "bad/cid", "auto", "DEFAULT", "default_7"):
        assert lreg.is_valid_owner_cid(bad_cid) is False  # type: ignore[arg-type]
    repo = tmp_path / "repo_lr_val"
    repo.mkdir()
    assert (lreg.is_valid_owner_cid(" cid-Ok_1 "), lreg.resolve_lane_registry_path(repo).name) == (
        True,
        "lane_registry.json",
    )
    for kw in (
        {"owner": "default_0", "extra": {}},
        {"owner": "cid-own", "extra": {"parent_cid": "auto"}},
        {"owner": "cid-own", "extra": {"claim_ttl_sec": 0.0}},
        {"owner": "cid-own", "extra": {"claim_ttl_sec": 10.5}},
        {"owner": "cid-own", "extra": {"authorized_cids": ("default_x",)}},
    ):
        with pytest.raises(ValueError):
            lreg.register_lane(repo, "l1", str(kw["owner"]), **kw["extra"])  # type: ignore[arg-type]


@pytest.mark.fast
def test_mut_lane_registry_ttl_and_claim_guards(tmp_path: Path) -> None:
    """Copre re-register fail-closed, claim precondizioni, scadenza TTL e replay."""
    repo = tmp_path / "repo_lr_ttl"
    repo.mkdir()
    try:
        r1 = lreg.register_lane(
            repo, "l1", "cid-own", authorized_cids=("cid-own", "cid-peer"),
            claim_ttl_sec=0.01, base_repo_seq=3, declared_write_set=("b.py", " ", "a.py"),
        )
        assert (r1["authorized_cids"], r1["declared_write_set"], r1["base_repo_seq"]) == (
            ["cid-own", "cid-peer"], ["a.py", "b.py"], 3,
        )
        with pytest.raises(PermissionError):
            lreg.register_lane(repo, "l1", "cid-other")
        with pytest.raises(ValueError):
            lreg.claim_lane(repo, "l1", "auto", r1["claim_secret"])
        with pytest.raises(ValueError):
            lreg.claim_lane(repo, "l1", "cid-ch", "")
        with pytest.raises(PermissionError):
            lreg.claim_lane(repo, "missing_lane", "cid-ch", "secret")
        with pytest.raises(PermissionError):
            lreg.claim_lane(repo, "l1", "cid-ch", r1["claim_secret"], parent_cid="cid-wrong")

        time.sleep(0.025)
        with pytest.raises(TimeoutError):
            lreg.claim_lane(repo, "l1", "cid-ch", r1["claim_secret"])
    finally:
        lreg.release_lane(repo, "l1", "cid-own", force=True)


@pytest.mark.fast
def test_mut_lane_registry_claim_verify_and_release(tmp_path: Path) -> None:
    """Copre secret mismatch, consumo singolo, verify_lane_access e release_lane."""
    repo = tmp_path / "repo_lr_verify"
    repo.mkdir()
    try:
        r2 = lreg.register_lane(repo, "l1", "cid-own", authorized_cids=("cid-peer",), claim_ttl_sec=5.0)
        with pytest.raises(PermissionError):
            lreg.claim_lane(repo, "l1", "cid-ch", "0" * 32)
        lreg.claim_lane(repo, "l1", "cid-ch", r2["claim_secret"])
        with pytest.raises(PermissionError):
            lreg.claim_lane(repo, "l1", "cid-ch2", r2["claim_secret"])
        assert (
            lreg.verify_lane_access(repo, "bad/id", "cid-own"),
            lreg.verify_lane_access(repo, "l1", "default_1"),
            lreg.verify_lane_access(repo, "unreg", "cid-own"),
            lreg.verify_lane_access(repo, "l1", "cid-peer"),
            lreg.verify_lane_access(repo, "l1", "cid-ch"),
            lreg.release_lane(repo, "unreg", "cid-own"),
        ) == (
            (False, "invalid_lane_id"),
            (False, "invalid_or_default_cid"),
            (False, "lane_not_registered"),
            (True, "authorized_child"),
            (True, "authorized_child"),
            False,
        )
        with pytest.raises(PermissionError):
            lreg.release_lane(repo, "l1", "auto")
        assert lreg.release_lane(repo, "l1", "cid-own") is True
    finally:
        lreg.release_lane(repo, "l1", "cid-own", force=True)


@pytest.mark.fast
def test_mut_active_slot_io_all_guards_and_clamps(tmp_path: Path) -> None:
    """Copre validazione HMAC, TTL clamp, write_file=False, strict_owner e cleanup."""
    repo = tmp_path / "repo_sio"
    repo.mkdir()
    with pytest.raises(TicketAuthError):
        sio.verify_slot_payload_integrity({"hmac_sha256": "short"})

    slot_leg = sio.claim_active_session_slot(
        repo, "s-leg", ttl_seconds=99999, base_repo_seq=5, accepted=False
    )
    data = json.loads(slot_leg.read_text(encoding="utf-8"))
    no_write_p = sio.claim_active_session_slot(repo, "s-nw", lane_id="l_nw", write_file=False)
    sio.claim_active_session_slot(repo, "s-l1", lane_id="l1", ttl_seconds=5, accepted=True)
    d_l1 = json.loads(sio.resolve_active_slot_path(repo, "l1").read_text(encoding="utf-8"))
    assert (data["ttl_seconds"], data["base_repo_seq"], no_write_p.exists(), d_l1["ttl_seconds"]) == (7200, 5, False, 60)

    sio.assert_slot_owner_or_idle(None, "any")
    sio.assert_slot_owner_or_idle(d_l1, "other-sess", strict_owner=False)
    with pytest.raises(TicketAuthError):
        sio.assert_slot_owner_or_idle(d_l1, "other-sess", strict_owner=True)
    with pytest.raises(TicketAuthError):
        sio.verify_slot_payload_integrity(dict(d_l1), lane_id=None)

    tampered = dict(d_l1)
    tampered["phase"] = "TAMPERED"
    with pytest.raises(TicketAuthError):
        sio.verify_slot_payload_integrity(tampered, lane_id="l1")

    sio.close_active_slot(repo, "none-sess", lane_id="missing_l")
    with pytest.raises(TicketAuthError):
        sio.close_active_slot(repo, "foreign-sess", lane_id="l1")
    sio.close_active_slot(repo, "s-l1", lane_id="l1")
    sio.close_active_slot(repo, "s-leg")


@pytest.mark.fast
def test_mut_nvme_mirror_safety_and_ignore_rules(tmp_path: Path) -> None:
    """Copre safe_rmtree readonly, _is_safe_local_dir, _is_mirror_ignored_name e root/subdir."""
    ro_dir = tmp_path / "ro_tree"
    ro_dir.mkdir()
    ro_file = ro_dir / "locked.txt"
    ro_file.write_text("ro", encoding="utf-8")
    os.chmod(ro_file, stat.S_IREAD)
    ws = tmp_path / "ws_nh"
    trk = ws / "nk_tracking"
    trk.mkdir(parents=True)
    (ws / "01_blueprint").mkdir()
    (tmp_path / "NK_External_Projects").mkdir()

    assert (
        nmh.safe_rmtree(ro_dir), ro_dir.exists(), nmh.safe_rmtree(tmp_path / "absent"),
        nmh._is_safe_local_dir(trk, ws), nmh._is_safe_local_dir(ws, ws),
        nmh._is_safe_local_dir(tmp_path, ws), nmh._is_safe_local_dir(ws / "missing", ws),
    ) == (True, False, True, True, False, False, False)
    assert (
        nmh._is_mirror_ignored_name("app.pyc", ws, False),
        nmh._is_mirror_ignored_name(".env.prod", ws, False),
        nmh._is_mirror_ignored_name("sessions", trk, True),
        nmh._is_mirror_ignored_name("sessions", ws, False),
        nmh._is_mirror_ignored_name("mod.py", ws, False),
        "01_blueprint" in nmh._iter_mirror_subdir_names(ws),
        nmh._is_sibling_projects_parent(tmp_path / "NK_External_Projects"),
        nmh._is_mirror_root_file(ws / "README.md"),
        nmh._is_mirror_root_file(ws / "secret.db"),
    ) == (True, True, True, False, False, True, True, True, False)


@pytest.mark.fast
def test_mut_nvme_mirror_overlay_tombstones_and_targets(tmp_path: Path) -> None:
    """Copre exclude_lanes depth-0, tombstones overlay, _sync_staging_tests e target normalization."""
    ws = tmp_path / "ws_ov"
    stg = ws / ".staging"
    (stg / "lanes" / "x").mkdir(parents=True)
    (stg / "lanes" / "x" / "skip.py").write_text("S=1", encoding="utf-8")
    (stg / "scripts" / "lanes").mkdir(parents=True)
    (stg / "scripts" / "lanes" / "keep.py").write_text("K=1", encoding="utf-8")
    (stg / ".gitkeep").write_text("", encoding="utf-8")
    (stg / ".deleted_files.json").write_text(json.dumps(["scripts/old.py", "tests/old_dir", "../escape.py"]), encoding="utf-8")

    mirror = tmp_path / "mirror_out"
    (mirror / "scripts").mkdir(parents=True)
    (mirror / "scripts" / "old.py").write_text("OLD", encoding="utf-8")
    (mirror / "tests" / "old_dir").mkdir(parents=True)
    (mirror / "tests" / "old_dir" / "t.py").write_text("T", encoding="utf-8")
    (mirror / ".staging" / "tests").mkdir(parents=True)
    (mirror / ".staging" / "tests" / "test_stg.py").write_text("def test_s(): assert True\n", encoding="utf-8")
    (mirror / ".staging" / ".deleted_files.json").write_text(
        json.dumps(["tests/rm_t.py", "tests/absent_t.py", "scripts/not_test.py"]),
        encoding="utf-8",
    )
    (mirror / "tests" / "rm_t.py").write_text("RM", encoding="utf-8")
    bad_stg = ws / "bad_stg"
    bad_stg.mkdir()
    (bad_stg / ".deleted_files.json").write_text("{corrupt", encoding="utf-8")

    nmh._apply_staging_overlay_to_mirror(mirror, stg, ws, exclude_lanes=True)
    nmh._sync_staging_tests_for_pytest(mirror, ws)
    assert (
        nmh._load_deleted_set(stg), nmh._load_deleted_set(bad_stg),
        (mirror / "lanes").exists(), (mirror / "scripts" / "lanes" / "keep.py").is_file(),
        (mirror / "scripts" / "old.py").exists(), (mirror / "tests" / "old_dir").exists(),
        (mirror / ".gitkeep").exists(), (mirror / "tests" / "test_stg.py").is_file(), (mirror / "tests" / "rm_t.py").exists(),
    ) == ({"scripts/old.py", "tests/old_dir", "../escape.py"}, set(), False, True, False, False, False, True, False)
    nmh.safe_rmtree(mirror / ".staging" / "tests")
    nmh._sync_staging_tests_for_pytest(mirror, ws)

    base_dst = tmp_path / "base_clone"
    (ws / "scripts").mkdir(exist_ok=True)
    (ws / "scripts" / "b.py").write_text("B = 1\n", encoding="utf-8")
    (ws / "README.md").write_text("# Doc\n", encoding="utf-8")
    nmh._mirror_project_base(ws, base_dst)
    assert ((base_dst / "scripts" / "b.py").is_file(), (base_dst / "README.md").is_file()) == (True, True)
    assert nmh._resolve_mirror_targets(
        mirror, ws,
        ["", "./tests/a.py", f"{mirror.name}/tests/b.py", f"{ws.as_posix()}/tests/c.py", ".staging/lanes/la/tests/d.py", ".staging/lanes/la/scripts/m.py"],
    ) == ["tests/a.py", "tests/b.py", "tests/c.py", "tests/d.py", ".staging/scripts/m.py"]
    assert nmh._resolve_mirror_targets(mirror, ws, []) == ["tests"]


@pytest.mark.integration
def test_mut_reparse_junction_and_locked_safe_rmtree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre junction reparse reale (lane_paths) e retry loop fail-closed su safe_rmtree."""
    if os.name == "nt":
        stg_root, tgt = tmp_path / "j_stg", tmp_path / "j_tgt"
        junc = stg_root / "lanes" / "jl"
        junc.parent.mkdir(parents=True)
        tgt.mkdir()
        subprocess.run(["cmd", "/c", "mklink", "/J", str(junc), str(tgt)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            assert (lp._has_reparse_in_chain(stg_root, junc / "x.py"), lp.is_valid_lane_subpath_no_reparse(junc / "x.py", stg_root), nmh._is_mirror_ignored_name("jl", junc.parent, False)) == (True, False, True)
        finally:
            os.rmdir(junc)
    busy_dir, calls, sleeps, kws = tmp_path / "busy_rm", [], [], []
    busy_dir.mkdir()
    with monkeypatch.context() as mp:
        mp.setattr(nmh.shutil, "rmtree", lambda *_a, **kw: (calls.append(1), kws.extend(kw.keys()), (_ for _ in ()).throw(OSError("busy"))))
        mp.setattr(nmh.time, "sleep", lambda s: sleeps.append(round(float(s), 3)))
        assert (nmh.safe_rmtree(busy_dir), len(calls), sleeps, "onexc" in kws) == (False, 5, [0.04, 0.08, 0.12, 0.16, 0.2], True)
