# -*- coding: utf-8 -*-
"""Test rapidi Wave 6 per transcript_prompt, handoff_verify, anchor_store, ecosystem_scanner e handoff_engine."""

from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

_boot_mod = load_nk_script_module("nk_session_bootstrap")
_handoff_mod = load_nk_script_module("nk_session_handoff")

from _internal.nk_session_bootstrap import handoff_verify, handoff_verify_io, transcript_prompt  # noqa: E402
from _internal.nk_session_handoff import anchor_store, context_view, ecosystem_helpers, ecosystem_scanner, handoff_engine  # noqa: E402

pytestmark = pytest.mark.fast


def _write_jsonl(path: Path, rows: List[Any]) -> Path:
    """Scrive righe JSONL UTF-8 creando le directory padre."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


class _BadResolvePath:
    """Stub Path la cui risoluzione genera OSError."""

    def resolve(self) -> Path:
        raise OSError("boom")


class _PromptSelfStub:
    """Stub minimale per _scan_open_transcript_tail."""

    @staticmethod
    def _extract_user_prompt_from_line(line_bytes: bytes) -> Optional[str]:
        return transcript_prompt.extract_user_prompt_from_line(line_bytes)


@pytest.mark.fast
def test_transcript_temp_root_flags_and_flatten() -> None:
    """Verifica tuple fallback su OSError e flatten sicuro su valori non stringa."""
    flags = transcript_prompt._temp_root_flags(_BadResolvePath(), _BadResolvePath())  # type: ignore[arg-type]
    flat = transcript_prompt._flatten_user_content([{"text": 123}, {"content": "   "}, {"text": "ciao"}])
    assert isinstance(flags, tuple) and flags == (False, False)
    assert flat == "ciao"


@pytest.mark.fast
def test_scan_open_transcript_tail_empty_and_multichunk() -> None:
    """Verifica EOF vuoto senza IndexError e scansione multi-chunk USER_INPUT."""
    stub = _PromptSelfStub()
    assert transcript_prompt._scan_open_transcript_tail(stub, io.BytesIO(b""), 100, 50) is None
    raw = (
        b'{"type":"USER_INPUT","content":"first prompt"}\n'
        b'{"type":"PLANNER_RESPONSE","content":"ignored reply padding line"}\n'
        b'{"type":"USER_INPUT","content":"latest prompt"}\n'
    )
    found = transcript_prompt._scan_open_transcript_tail(stub, io.BytesIO(raw), len(raw), 40)
    assert found == "latest prompt"


@pytest.mark.fast
def test_build_v2_repo_specs_id_resolution(tmp_path: Path) -> None:
    """Verifica risoluzione rid con fallback id, project_root.name e repo_id."""
    v2_pl = {
        "ecosystem_repos": [
            {"id": "alt-id", "repo_root": str(tmp_path)},
            {"repo_root": str(tmp_path)},
            {"repo_id": "main-id", "repo_root": str(tmp_path)},
        ]
    }
    specs = handoff_verify._build_v2_repo_specs(tmp_path, {}, v2_pl, {})
    assert [rid for rid, _, _ in specs] == ["alt-id", tmp_path.name, "main-id"]
    assert all(rroot == tmp_path for _, rroot, _ in specs)


@pytest.mark.fast
def test_run_repo_pool_duplicate_id_and_cache_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica fusione drift duplicati e propagazione cache_mode non FAST_STAT_HIT."""
    specs = [("NK_Hub", tmp_path, {"idx": 0}), ("NK_Hub", tmp_path, {"idx": 1})]
    case_a = [
        {"status": "SYNC", "drifts": ["D1"], "cache_mode": "FULL_SCAN"},
        {"status": "SYNC", "drifts": ["D2"], "cache_mode": "FAST_STAT_HIT"},
    ]
    case_b = [
        {"status": "OK", "drifts": [], "cache_mode": "FAST_STAT_HIT"},
        {"status": "OK", "drifts": [], "cache_mode": "FULL_SCAN"},
    ]
    active = [case_a]

    def _stub_verify(rid: str, _rroot: Path, snap: Dict[str, Any], *_a: Any) -> Tuple[str, Dict[str, Any]]:
        return rid, dict(active[0][snap["idx"]])

    monkeypatch.setattr(handoff_verify, "_verify_single_repo", _stub_verify)
    roots = (tmp_path, tmp_path, tmp_path)
    res_a = handoff_verify._run_repo_pool(specs, "cid-1", ["NK_Hub"], 1, (None, None, None), (), roots)["NK_Hub"]
    active[0] = case_b
    res_b = handoff_verify._run_repo_pool(specs, "cid-1", ["NK_Hub"], 1, (None, None, None), (), roots)["NK_Hub"]
    assert (res_a["drifts"], res_a["status"], res_a["cache_mode"]) == (["D1", "D2", "DUPLICATE_REPO_ID"], "DRIFT", "FULL_SCAN")
    assert (res_b["status"], res_b["cache_mode"], res_b["drifts"]) == ("DRIFT", "FULL_SCAN", ["DUPLICATE_REPO_ID"])


@pytest.mark.fast
def test_process_meta_entry_exclusions(tmp_path: Path) -> None:
    """Verifica filtraggio ex_dirs, skip_dirs, ex_files e skip_files in _process_meta_entry."""
    for dname in ("ex_d", "skip_d", "keep_d"):
        (tmp_path / dname).mkdir()
    for fname in ("ex.txt", "skip.txt", "keep.txt"):
        (tmp_path / fname).write_text("ok", encoding="utf-8")
    excl = ({"ex_d"}, {"ex.txt"}, {"skip_d"}, ("skip_d/",), {"skip.txt"})
    meta: Dict[str, List[int]] = {}
    stack: List[Tuple[str, str]] = []
    with os.scandir(tmp_path) as it:
        for entry in it:
            handoff_verify_io._process_meta_entry(entry, "", excl, meta, stack)
    assert [rel for _, rel in stack] == ["keep_d"]
    assert list(meta.keys()) == ["keep.txt"] and meta["keep.txt"][1] == 2


@pytest.mark.fast
def test_read_rsi_file_variants(tmp_path: Path) -> None:
    """Verifica validazione status fail-closed, range fitness_q e gate v2 in _read_rsi_file."""
    p1 = _write_jsonl(tmp_path / "a.jsonl", [{"iteration": 3, "delta_k": 1, "fitness_q": 95.5, "status": "REFINING"}])
    p2 = _write_jsonl(tmp_path / "b.jsonl", [{"iteration": 1, "delta_k": 0, "fitness_q": 100.0, "status": ""}])
    p3 = _write_jsonl(tmp_path / "c.jsonl", [{"iteration": 1, "delta_k": 0, "fitness_q": 150.0, "status": "BOGUS"}])
    p4 = _write_jsonl(tmp_path / "d.jsonl", [{"iteration": -1, "delta_k": -2, "fitness_q": -5.0, "status": "CONVERGED_OPTIMAL"}])
    p5 = _write_jsonl(tmp_path / "e.jsonl", [{"iteration": 1, "delta_k": 0, "fitness_q": 100.0, "g_hard": 0, "status": "CONVERGED_OPTIMAL"}])
    assert handoff_engine._read_rsi_file(p1) == {"iteration": 3, "delta_k": 1, "fitness_q": 95.5, "status": "REFINING"}
    assert handoff_engine._read_rsi_file(p2) == {"iteration": 1, "delta_k": 0, "fitness_q": 100.0, "status": "REFINING"}
    assert handoff_engine._read_rsi_file(p3) == {"iteration": 1, "delta_k": 0, "fitness_q": 0.0, "status": "REFINING"}
    assert handoff_engine._read_rsi_file(p4) == {"iteration": 0, "delta_k": 0, "fitness_q": 0.0, "status": "CONVERGED_OPTIMAL"}
    assert handoff_engine._read_rsi_file(p5) == {"iteration": 1, "delta_k": 0, "fitness_q": 100.0, "status": "REFINING"}


@pytest.mark.fast
def test_redact_obj_strings_selective_keys() -> None:
    """Verifica scrub AP-14 limitato alle sole chiavi free-text consentite."""
    payload = {
        "last_summary": "Traceback (most recent call last): err",
        "plain_key": "Traceback (most recent call last): err",
    }
    redacted, cnt = handoff_engine._redact_obj_strings(payload)
    assert cnt == 0
    assert "[FILTERED]" in redacted["last_summary"]
    assert redacted["plain_key"] == "Traceback (most recent call last): err"


@pytest.mark.fast
def test_read_latest_2pc_promotion_milestone(tmp_path: Path) -> None:
    """Verifica precedenza ultimo 2PC senza timestamp e override con timestamp."""
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    _write_jsonl(root_a / "nk_tracking" / "anchor" / "session_anchor.jsonl", [
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-2.1.0-OLD"},
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-2.1.0-NEW"},
    ])
    _write_jsonl(root_b / "nk_tracking" / "anchor" / "session_anchor.jsonl", [
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-2.1.0-NOTS"},
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-2.1.0-TS", "timestamp": "2026-11-23T12:00:00Z"},
    ])
    assert anchor_store._read_latest_2pc_promotion_milestone(root_a) == ("NK-GEN-2.1.0-NEW", 0)
    ms_b, ts_b = anchor_store._read_latest_2pc_promotion_milestone(root_b)
    assert ms_b == "NK-GEN-2.1.0-TS" and ts_b > 0


@pytest.mark.fast
def test_scan_last_fsm_checkpoint_states(tmp_path: Path) -> None:
    """Verifica gestione lista JSON, evento non checkpoint e checkpoint valido."""
    f_list = _write_jsonl(tmp_path / "list.jsonl", [[1, 2]])
    f_other = _write_jsonl(tmp_path / "other.jsonl", [{"event": "other"}])
    cp_rec = {"event": "fsm_checkpoint", "turn": 3, "state_sha256": "a" * 64}
    f_ok = _write_jsonl(tmp_path / "ok.jsonl", [{"event": "other"}, cp_rec])
    assert anchor_store._scan_last_fsm_checkpoint(f_list) == (None, True)
    assert anchor_store._scan_last_fsm_checkpoint(f_other) == (None, False)
    assert anchor_store._scan_last_fsm_checkpoint(f_ok) == (cp_rec, False)


@pytest.mark.fast
def test_read_anchor_start_ns_filters_and_fallback(tmp_path: Path) -> None:
    """Verifica filtro CID, boundary > 0 e fallback su anchor di sessione."""
    root_a, root_b, root_c = tmp_path / "ra", tmp_path / "rb", tmp_path / "rc"
    _write_jsonl(root_a / "nk_tracking" / "anchor" / "session_anchor.jsonl", [
        {"conversation_id": "other", "timestamp_ns": 111},
        {"conversation_id": "cid-1", "timestamp_ns": 222},
    ])
    _write_jsonl(root_b / "nk_tracking" / "anchor" / "session_anchor.jsonl", [
        {"timestamp_ns": 0},
        {"timestamp_ns": 1.5e-9},
    ])
    _write_jsonl(root_c / "nk_tracking" / "sessions" / "cid-2" / "session_anchor.jsonl", [{"timestamp_ns": 555}])
    assert ecosystem_scanner._read_anchor_start_ns(root_a, "cid-1") == 222_000_000_000
    assert ecosystem_scanner._read_anchor_start_ns(root_b, "") == 1
    assert ecosystem_scanner._read_anchor_start_ns(root_c, "cid-2") == 555_000_000_000
    miss = ecosystem_scanner._read_anchor_start_ns(root_c, "cid-9")
    assert isinstance(miss, int) and miss == 0


@pytest.mark.fast
def test_extract_first_patch_section() -> None:
    """Verifica estrazione sezione PATCH_NOTES e fallback senza intestazioni."""
    plain = ecosystem_scanner._extract_first_patch_section(["plain 1", "", "plain 2"])
    headed = ecosystem_scanner._extract_first_patch_section(
        ["## [v1.0] Title", "bullet 1", "## [v0.9] Old", "old bullet"]
    )
    assert plain == ("", ["plain 1", "plain 2"])
    assert headed == ("[v1.0] Title", ["bullet 1"])


@pytest.mark.fast
def test_read_tail_lines_window_and_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica taglio riga parziale su max_bytes e lista vuota su OSError."""
    p = tmp_path / "tail.txt"
    p.write_bytes(b"FIRST_LONG_LINE_12345\nSECOND_LINE\nTHIRD_LINE\n")
    assert ecosystem_helpers._read_tail_lines(p, max_bytes=25) == ["SECOND_LINE", "THIRD_LINE"]
    p_small = tmp_path / "small.txt"
    p_small.write_bytes(b"ALPHA\nBETA\n")
    assert ecosystem_helpers._read_tail_lines(p_small, max_bytes=25) == ["ALPHA", "BETA"]
    with monkeypatch.context() as mp:
        mp.setattr(builtins, "open", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("io fail")))
        res = ecosystem_helpers._read_tail_lines(p)
    assert isinstance(res, list) and res == []


@pytest.mark.fast
def test_z2_anchor_meta_2pc_promotion_precedence(tmp_path: Path) -> None:
    """Verifica precedenza 2PC_ATOMIC_PROMOTION rispetto a session_anchor, boundary tie e coda >8KB."""
    load_nk_script_module("nk_acs_fastguard")
    from _internal.nk_acs_fastguard import z2_and_l0 as z2

    ws = tmp_path / "z2_ws"
    glob_rows: List[Dict[str, Any]] = [
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-3.0.1-OLDER", "timestamp": "2026-11-24T15:00:00Z"},
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-3.0.2-NEW", "timestamp": "2026-11-24T16:11:40Z"},
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "2PC_PROMOTE", "timestamp": "2026-11-24T16:11:50Z"},
    ] + [{"event": "auto_checkpoint_idle", "milestone_id": "NK-STALE-IDLE", "pad": "p" * 110} for _ in range(80)]
    _write_jsonl(ws / "nk_tracking" / "anchor" / "session_anchor.jsonl", glob_rows)
    _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_old" / "session_anchor.jsonl", [{"event": "auto_checkpoint_idle", "milestone_id": "NK-GEN-3.0.1-OLD", "timestamp": "2026-11-24T16:11:15Z"}])
    _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_tie" / "session_anchor.jsonl", [{"event": "fsm_checkpoint", "turn": 2, "milestone_id": "NK-SESS-TIE", "timestamp": "2026-11-24T16:11:40Z"}])
    _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_new" / "session_anchor.jsonl", [{"event": "fsm_checkpoint", "turn": 3, "milestone_id": "NK-SESS-NEW", "timestamp": "2026-11-24T16:12:00Z"}])
    _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_nots" / "session_anchor.jsonl", [{"milestone_id": "NK-SESS-NOTS"}])
    assert (z2._read_anchor_meta([str(ws)], {}, conv_id="cid_old", default_turn=0), z2._read_anchor_meta([str(ws)], {}, conv_id="cid_tie", default_turn=0), z2._read_anchor_meta([str(ws)], {}, conv_id="cid_new", default_turn=0)) == (("NK-GEN-3.0.2-NEW", 0), ("NK-SESS-TIE", 2), ("NK-SESS-NEW", 3))
    assert (z2._read_anchor_meta([str(ws)], {}, conv_id="cid_nots", default_turn=0), z2._read_anchor_meta([str(ws)], {}, conv_id="cid_fresh", default_turn=0), z2._read_anchor_meta([str(ws)], {"milestone_id": "NK-EXPLICIT"}, conv_id="cid_fresh", default_turn=0)) == (("NK-GEN-3.0.2-NEW", 0), ("NK-GEN-3.0.2-NEW", 0), ("NK-EXPLICIT", 0))

    p_tail = tmp_path / "z2_tail.txt"
    p_tail.write_bytes(b"FIRST_LONG_LINE_12345\nSECOND_LINE\nTHIRD_LINE\n")
    assert z2._read_tail_8k(str(p_tail), max_bytes=25) == ["SECOND_LINE", "THIRD_LINE"]

    ws_np = tmp_path / "z2_nopromo"
    _write_jsonl(ws_np / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"milestone_id": "NK-GLOB-IDLE"}])
    for cid, t_val in (("cid_t1", 1), ("cid_t0", 0), ("cid_t5", 5)):
        _write_jsonl(ws_np / "nk_tracking" / "sessions" / cid / "session_anchor.jsonl", [{"milestone_id": "NK-SESS-ONLY", "turn": t_val}])
    assert (z2._read_anchor_meta([str(ws_np)], {}, conv_id="cid_t1", default_turn=0), z2._read_anchor_meta([str(ws_np)], {}, conv_id="cid_t0", default_turn=1), z2._read_anchor_meta([str(ws_np)], {}, conv_id="cid_t5", default_turn=0), z2._read_anchor_meta([str(ws_np)], {}, conv_id="cid_t5", default_turn=1)) == (("NK-SESS-ONLY", 1), ("NK-SESS-ONLY", 1), ("NK-SESS-ONLY", 0), ("NK-SESS-ONLY", 5))

    ws_nots = tmp_path / "z2_nots"
    _write_jsonl(ws_nots / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-PROMO-NOTS"}])
    _write_jsonl(ws_nots / "nk_tracking" / "sessions" / "cid_nots" / "session_anchor.jsonl", [{"milestone_id": "NK-SESS-NOTS", "turn": 2}])
    assert z2._read_anchor_meta([str(ws_nots)], {}, conv_id="cid_nots", default_turn=0) == ("NK-SESS-NOTS", 2)


@pytest.mark.fast
def test_context_view_and_handoff_milestone_precedence(tmp_path: Path) -> None:
    """Verifica precedenza milestone in context_view, handoff_engine e anchor_store."""
    ws = tmp_path / "cv_ws"
    (ws / "nk_genome").mkdir(parents=True)
    (ws / "nk_genome" / "PATCH_NOTES.md").write_text("## [NK-PATCH-OLD] (2026-11-24)\n", encoding="utf-8")
    (ws / "nk_tracking" / "handoff").mkdir(parents=True)
    _write_jsonl(ws / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-3.0.2-PROMO", "timestamp": "2026-11-24T16:00:00Z"}])
    latest_p = ws / "nk_tracking" / "handoff" / "session_handoff_latest.json"
    latest_p.write_text(json.dumps({"milestone": "NK-OLD-LATEST", "timestamp": "2026-11-24T15:00:00Z"}), encoding="utf-8")
    assert "`NK-GEN-3.0.2-PROMO`" in context_view.generate_active_context_view(root=ws, dry_run=True)["content"]
    latest_p.write_text(json.dumps({"milestone": "NK-FRESH-LATEST", "timestamp": "2026-11-24T17:00:00Z"}), encoding="utf-8")
    assert "`NK-FRESH-LATEST`" in context_view.generate_active_context_view(root=ws, dry_run=True)["content"]

    promo_ns = 1_795_536_000_000_000_000  # 2026-11-24T16:00:00Z
    ws_1ns, ws_p0 = tmp_path / "ws_1ns", tmp_path / "ws_p0"
    _write_jsonl(ws_1ns / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "M-1NS", "timestamp_ns": 1.5e-9}])
    _write_jsonl(ws_p0 / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "M-P0"}])
    assert (handoff_engine._prefer_newer_promo(ws, "NK-TIE-SESS", promo_ns), handoff_engine._prefer_newer_promo(ws, "NK-OLD-SESS", promo_ns - 1), handoff_engine._prefer_newer_promo(ws, "NK-NOTS-SESS", 0)) == ("NK-TIE-SESS", "NK-GEN-3.0.2-PROMO", "NK-GEN-3.0.2-PROMO")
    assert (handoff_engine._prefer_newer_promo(ws_1ns, "NK-C0", 0), handoff_engine._prefer_newer_promo(ws_1ns, "NK-C1", 1), handoff_engine._prefer_newer_promo(ws_p0, "NK-C0", 0)) == ("M-1NS", "NK-C1", "NK-C0")

    sess_idle = _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_idle" / "session_anchor.jsonl", [{"event": "auto_checkpoint_idle", "milestone_id": "NK-OLD-SESS", "timestamp": "2026-11-24T15:00:00Z"}])
    _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_fsm" / "session_anchor.jsonl", [{"event": "fsm_checkpoint", "turn": 2, "milestone_id": "NK-NEW-FSM", "state_sha256": "a" * 64, "timestamp": "2026-11-24T17:00:00Z"}])
    _write_jsonl(ws / "nk_tracking" / "sessions" / "cid_old_fsm" / "session_anchor.jsonl", [{"event": "fsm_checkpoint", "turn": 2, "milestone_id": "NK-OLD-FSM", "state_sha256": "a" * 64, "timestamp": "2026-11-24T15:00:00Z"}])
    assert anchor_store._resolve_own_anchor_milestone_with_ts(sess_idle)[0] == "NK-OLD-SESS"
    assert anchor_store.resume_from_anchor(root=ws, conversation_id="cid_fsm")["milestone_ts_ns"] > promo_ns
    assert (handoff_engine.serialize_handoff_v2(ws, ws, mode="PASSIVE_STANDBY", conversation_id="cid_idle")["envelope"]["milestone"], handoff_engine.serialize_handoff_v2(ws, ws, mode="PASSIVE_STANDBY", conversation_id="cid_fsm")["envelope"]["milestone"]) == ("NK-GEN-3.0.2-PROMO", "NK-NEW-FSM")
    assert "`NK-GEN-3.0.2-PROMO`" in context_view.generate_active_context_view(root=ws, dry_run=True, conversation_id="cid_old_fsm")["content"]

    ws_glob = tmp_path / "glob_resumed"
    (ws_glob / "nk_tracking" / "handoff").mkdir(parents=True)
    _write_jsonl(ws_glob / "nk_tracking" / "anchor" / "session_anchor.jsonl", [
        {"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GLOB-PROMO", "timestamp": "2026-11-24T16:00:00Z"},
        {"event": "fsm_checkpoint", "turn": 2, "milestone_id": "NK-GLOB-FSM", "state_sha256": handoff_engine._compute_workspace_state_sha256(ws_glob), "timestamp": "2026-11-24T15:00:00Z"},
    ])
    (ws_glob / "nk_tracking" / "handoff" / "session_handoff_latest.json").write_text(json.dumps({"milestone": "NK-OTHER-LATEST", "last_summary": "S" * 72, "timestamp": "2026-11-24T17:00:00Z"}), encoding="utf-8")
    assert "`NK-GLOB-PROMO`" in context_view.generate_active_context_view(root=ws_glob, dry_run=True, conversation_id="cid_no_sess")["content"]
    (ws_glob / ".staging" / "scripts").mkdir(parents=True)
    for i in range(16):
        (ws_glob / ".staging" / "scripts" / f"mod_b_{i:02d}_aaaaaaaaaa.py").write_text("X = 1\n", encoding="utf-8")
    std_txt = context_view.generate_active_context_view(root=ws_glob, profile="standard", dry_run=True)["content"]
    assert "altri file in .staging/" in std_txt
    assert len(std_txt) <= 1400


@pytest.mark.fast
def test_cli_auto_checkpoint_write_order_and_dry_run_guards(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica ordine scritture --auto-checkpoint e guardie CLI su --dry-run."""
    ws_cli = tmp_path / "cli_order_ws"
    (ws_cli / "nk_tracking" / "handoff").mkdir(parents=True)
    (ws_cli / "nk_tracking" / "handoff" / "session_handoff_latest.json").write_text(json.dumps({"milestone": "NK-STALE-PREV", "last_summary": "Auto-checkpoint Template 12 su NK-STALE-PREV.", "timestamp": "2026-11-24T15:00:00Z"}), encoding="utf-8")
    (tp_44 := tmp_path / "tp_44.jsonl").write_text('{"type":"USER_INPUT","content":"012345678"}\n', encoding="utf-8")
    capsys.readouterr()
    assert _handoff_mod.main(["--auto-checkpoint", "--project-root", str(ws_cli), "--transcript", str(tp_44), "--turn", "0", "--dry-run"]) == 0
    dry_ac = json.loads(capsys.readouterr().out)
    assert (dry_ac["handoff_template"], dry_ac["metadata"]["tokens"]) == ("Template 12", 11)
    assert _handoff_mod.main(["--project-root", str(ws_cli), "--compile-template-11", "--dry-run"]) == 0
    assert "Template 11" in capsys.readouterr().out
    assert _handoff_mod.main(["--project-root", str(ws_cli), "--generate-prompt", "--turn", "2", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["handoff_template"] == "Template 12"
    assert _handoff_mod.main(["--project-root", str(ws_cli), "--checkpoint-turn", "1", "--dry-run"]) == 0
    assert len(json.loads(capsys.readouterr().out)["state_sha256"]) == 64
    assert _handoff_mod.main(["--project-root", str(ws_cli), "--checkpoint-turn", "5", "--dry-run"]) == 0
    capsys.readouterr()
    for bad_t in ("0", "6"):
        with pytest.raises(ValueError):
            _handoff_mod.main(["--project-root", str(ws_cli), "--checkpoint-turn", bad_t, "--dry-run"])
    rc = _handoff_mod.main(["--auto-checkpoint", "--project-root", str(ws_cli), "--conversation-id", "cid_cli_order", "--milestone-id", "NK-FRESH-CLI", "--turn", "0"])
    ctx_txt = (ws_cli / "nk_tracking" / "active_context.md").read_text(encoding="utf-8")
    assert (rc, "`NK-FRESH-CLI`" in ctx_txt, "Auto-checkpoint Template 12 su NK-FRESH-CLI." in ctx_txt, "NK-STALE-PREV" not in ctx_txt) == (0, True, True, True)


@pytest.mark.fast
def test_hook_parent_workspace_root_resolution_with_staging_and_tracking(tmp_path: Path) -> None:
    """Verifica redirect parent -> NK_Hub nonostante .staging/ e nk_tracking/ nel padre."""
    load_nk_script_module("nk_acs_fastguard")
    load_nk_script_module("nk_hook_gate")
    from _internal.nk_acs_fastguard import state_rmw as srmw, z2_and_l0 as z2
    from _internal.nk_hook_gate import path_safety as ps, stop_evidence as se, stop_evidence_cli as sec

    parent = tmp_path / "AntigravityParent"
    hub = parent / "NK_Hub"
    (parent / ".staging").mkdir(parents=True)
    (parent / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    (hub / "scripts").mkdir(parents=True)
    _write_jsonl(parent / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-3.0.1-OLD", "timestamp": "2026-11-24T08:00:00Z"}])
    _write_jsonl(hub / "nk_tracking" / "anchor" / "session_anchor.jsonl", [{"event": "2PC_ATOMIC_PROMOTION", "milestone_id": "NK-GEN-3.0.2-NEW", "timestamp": "2026-11-24T17:00:00Z"}])

    eff = srmw._resolve_eff_root({"workspacePath": str(parent), "cwd": str(parent)}, None)
    proj = sec._resolve_proj_root_path(None, {"workspacePaths": [str(parent)]})
    assert (eff, z2._read_anchor_meta(srmw._candidate_roots(eff), {}, conv_id="cid_p", default_turn=0)) == (os.path.realpath(str(hub)), ("NK-GEN-3.0.2-NEW", 0))
    assert (proj, se._stop_read_anchor_meta([proj], {}, conv_id="cid_p", default_turn=0)) == (hub.resolve(), ("NK-GEN-3.0.2-NEW", 0))
    assert (ps._resolve_effective_hub_root(parent), ps._is_valid_staging_path(parent / ".staging" / ".agents" / "AGENTS.md", hub)) == (ps._canonical_path(hub), True)

    parent_fs = tmp_path / "ParentFileScripts"
    (parent_fs / "NK_Hub" / "scripts").mkdir(parents=True)
    (parent_fs / "scripts").write_text("not_a_dir", encoding="utf-8")
    assert Path(srmw._resolve_eff_root({"cwd": str(parent_fs)}, None)) == (parent_fs / "NK_Hub").resolve()

    ext_app = tmp_path / "NK_External_Projects" / "AppOnly"
    for d in (".staging", "nk_tracking"):
        (ext_app / d).mkdir(parents=True)
    assert (Path(srmw._resolve_eff_root({"cwd": str(ext_app)}, None)), sec._resolve_proj_root_path(None, {"workspacePaths": [str(ext_app)]}), ps._resolve_effective_hub_root(ext_app)) == (ext_app.resolve(), ext_app.resolve(), ps._canonical_path(ext_app))

    own_scripts = tmp_path / "OwnScripts"
    for d in ("scripts", "nk_tracking", "NK_Hub/scripts"):
        (own_scripts / d).mkdir(parents=True)
    assert (Path(srmw._resolve_eff_root({"cwd": str(own_scripts)}, None)), sec._resolve_proj_root_path(None, {"workspacePaths": [str(own_scripts)]}), ps._resolve_effective_hub_root(own_scripts)) == (own_scripts.resolve(), own_scripts.resolve(), ps._canonical_path(own_scripts))

    wrap_stg = tmp_path / "WrapStgOnly"
    (wrap_stg / "NK_Hub" / ".staging").mkdir(parents=True)
    assert (Path(srmw._resolve_eff_root({"cwd": str(wrap_stg)}, None)), sec._resolve_proj_root_path(None, {"workspacePaths": [str(wrap_stg)]}), ps._resolve_effective_hub_root(wrap_stg)) == (wrap_stg.resolve(), (wrap_stg / "NK_Hub").resolve(), ps._canonical_path(wrap_stg / "NK_Hub"))
    plain_dir = tmp_path / "PlainFirst"
    plain_dir.mkdir()
    assert srmw._resolve_eff_root({"projectRoot": str(tmp_path / "no_such_root"), "cwd": str(parent)}, None) == os.path.realpath(str(hub))
    assert (sec._resolve_proj_root_path(None, {"workspacePaths": [str(plain_dir), str(own_scripts)]}), sec._resolve_proj_root_path(None, {"workspacePaths": ["   ", 123, str(parent)]})) == (own_scripts.resolve(), hub.resolve())
