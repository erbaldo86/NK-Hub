# -*- coding: utf-8 -*-
"""Suite integration zero-mock CLI/Gate per Milestone 4 NK-GEN-4.0.4."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def test_sublane_default_combined_gate_no_lane_dir_conflict(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.sublane_consolidator import _run_default_combined_gate

    repo = tmp_path / "sub_def_gate_repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_smoke.py").write_text("def test_ok() -> None:\n    assert True\n", encoding="utf-8")
    tmp_merge = tmp_path / "nk_merge_tmp"
    (tmp_merge / "scripts" / "pkg").mkdir(parents=True)
    (tmp_merge / "scripts" / "pkg" / "ok.py").write_text("def val() -> int:\n    return 1\n", encoding="utf-8")

    res = _run_default_combined_gate(repo, tmp_merge, "w1")
    assert res["passed"] is True
    assert res["ast_guard"]["passed"] is True
    assert res["pytest"]["passed"] is True
