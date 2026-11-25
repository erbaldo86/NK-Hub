# -*- coding: utf-8 -*-
"""Test rapidi Wave 6 per nk_acs_fastguard l0_exempt_rules."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

pytestmark = pytest.mark.fast

load_nk_script_module("nk_acs_fastguard")

from _internal.nk_acs_fastguard import l0_exempt_rules  # noqa: E402


@pytest.mark.fast
def test_strip_xml_wrapper_fast_counts_and_unwraps() -> None:
    """Verifica estrazione singolo <USER_REQUEST> e conservazione con tag multipli."""
    fn = l0_exempt_rules._strip_xml_wrapper_fast
    assert fn("<USER_REQUEST>  avvia nk  </USER_REQUEST>") == "avvia nk"
    two_pairs = "<USER_REQUEST>a</USER_REQUEST><USER_REQUEST>b</USER_REQUEST>"
    assert fn(two_pairs) == two_pairs
    two_open_one_close = "<USER_REQUEST>a</USER_REQUEST><USER_REQUEST>b"
    assert fn(two_open_one_close) == two_open_one_close
    one_open_two_close = "<USER_REQUEST>a</USER_REQUEST></USER_REQUEST>"
    assert fn(one_open_two_close) == one_open_two_close


@pytest.mark.fast
def test_read_last_user_prompt_guards_and_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica file vuoto 0-byte, path mancante, JSONL valido e guard sz <= 0."""
    fn = l0_exempt_rules._read_last_user_prompt
    zero_file = tmp_path / "empty_transcript.jsonl"
    zero_file.write_bytes(b"")

    res_empty = fn(str(zero_file))
    assert res_empty == "" and isinstance(res_empty, str)

    res_missing = fn(str(tmp_path / "missing_transcript.jsonl"))
    assert res_missing == "" and isinstance(res_missing, str)

    jsonl_file = tmp_path / "valid_transcript.jsonl"
    line = json.dumps({"type": "USER_INPUT", "content": "<USER_REQUEST>esegui check</USER_REQUEST>"})
    jsonl_file.write_text(f"{line}\n", encoding="utf-8")
    assert fn(str(jsonl_file)) == "esegui check"

    def _deny_open(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("must not open 0-byte file")

    with monkeypatch.context() as mp:
        mp.setattr(builtins, "open", _deny_open)
        res_zero = fn(str(zero_file))
    assert res_zero == "" and isinstance(res_zero, str)
