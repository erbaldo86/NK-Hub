"""Template sorgente del plugin pytest temporaneo per tracciamento setup/call SBFL."""

from __future__ import annotations

from typing import Optional, Sequence

_PLUGIN_TEMPLATE = r'''from __future__ import annotations
import json, os, sys
import pytest

_EXEC_NORM = os.path.normcase(os.path.abspath(__EXEC_ROOT__))
_HINT_RAW = __HINT_RAW__
_HINT_NAME = _HINT_RAW.lower() if _HINT_RAW is not None else None
_OUT_JSON = __OUT_JSON__
_RECORDS_JSON = __RECORDS_JSON__
_SELECTED_FILTER = set(__SELECTED_NODEIDS__)
_PREFER_SETTRACE = __PREFER_SETTRACE__
_FILE_CACHE: dict[str, str | None] = {}
_COUNTS: dict[str, int] = {}
_RECORDS: list[dict[str, object]] = []
_ACTIVE_LINES: set[tuple[str, int]] = set()
_MON = getattr(sys, "monitoring", None)
_DISABLE = getattr(_MON, "DISABLE", None) if _MON is not None else None
_STATE: dict[str, object] = {
    "tid": None,
    "use_trace": False,
    "item_id": "",
    "setup_ok": False,
    "recorded": False,
}

def _is_ignored_test_file(rel_posix: str) -> bool:
    base = os.path.basename(rel_posix).lower()
    return base == "conftest.py" or base.startswith("test_") or base.endswith("_test.py")

def _map_filename(co_filename: str) -> str | None:
    cached = _FILE_CACHE.get(co_filename, False)
    if cached is not False:
        return cached  # type: ignore[return-value]
    norm = os.path.normcase(os.path.abspath(co_filename))
    try:
        rel = os.path.relpath(norm, _EXEC_NORM).replace("\\", "/")
    except ValueError:
        _FILE_CACHE[co_filename] = None
        return None
    if rel == "." or rel.startswith(".."):
        _FILE_CACHE[co_filename] = None
        return None
    if _HINT_NAME is not None:
        if os.path.basename(rel).lower() != _HINT_NAME:
            _FILE_CACHE[co_filename] = None
            return None
    elif _is_ignored_test_file(rel):
        _FILE_CACHE[co_filename] = None
        return None
    _FILE_CACHE[co_filename] = rel
    return rel

def _on_line_mon(code: object, lineno: int) -> object:
    rel = _map_filename(getattr(code, "co_filename", ""))
    if rel is None:
        return _DISABLE
    _ACTIVE_LINES.add((rel, int(lineno)))
    return _DISABLE

def _on_line_trace(frame: object, event: str, arg: object) -> object:
    if event == "line":
        code = getattr(frame, "f_code", None)
        rel = _map_filename(getattr(code, "co_filename", ""))
        if rel is not None:
            _ACTIVE_LINES.add((rel, int(getattr(frame, "f_lineno", 0))))
    return _on_line_trace

def _ensure_mon_tool_id() -> int | None:
    if _MON is None:
        return None
    cur = _STATE["tid"]
    if isinstance(cur, int):
        return cur
    for tid in (3, 4, 2, 5):
        try:
            if _MON.get_tool(tid) is None:
                _MON.use_tool_id(tid, "nk_sbfl_pass_cov")
                _MON.register_callback(tid, _MON.events.LINE, _on_line_mon)
                _STATE["tid"] = tid
                return tid
        except ValueError:
            continue
    return None

def _reset_test_buffer(nodeid: str = "", *, setup_ok: bool = False) -> None:
    _ACTIVE_LINES.clear()
    _STATE["item_id"] = nodeid
    _STATE["setup_ok"] = setup_ok
    _STATE["recorded"] = False

def _start_tracing(restart: bool = False) -> None:
    if _PREFER_SETTRACE and sys.gettrace() is None:
        sys.settrace(_on_line_trace)
        _STATE["use_trace"] = True
        return
    tid = _ensure_mon_tool_id()
    if tid is not None and _MON is not None:
        _MON.set_events(tid, _MON.events.LINE)
        if restart:
            restart_fn = getattr(_MON, "restart_events", None)
            if callable(restart_fn):
                restart_fn()
        _STATE["use_trace"] = False
        return
    if sys.gettrace() is None:
        sys.settrace(_on_line_trace)
        _STATE["use_trace"] = True

def _stop_tracing() -> None:
    tid = _STATE["tid"]
    if isinstance(tid, int) and _MON is not None:
        _MON.set_events(tid, 0)
    if _STATE.get("use_trace"):
        sys.settrace(None)
        _STATE["use_trace"] = False

def _record_item(passed: bool) -> None:
    if _STATE.get("recorded"):
        return
    _STATE["recorded"] = True
    stmts = sorted(f"{rel}:{lno}" for rel, lno in _ACTIVE_LINES)
    nodeid = str(_STATE.get("item_id") or "")
    if nodeid:
        _RECORDS.append({"test_id": nodeid, "passed": passed, "executed_statements": stmts})
    if passed:
        for rel, lno in _ACTIVE_LINES:
            key = f"{rel}::{lno}"
            _COUNTS[key] = _COUNTS.get(key, 0) + 1
    _ACTIVE_LINES.clear()
    _STATE["item_id"] = ""
    _STATE["setup_ok"] = False

def pytest_collection_modifyitems(items: list[object]) -> None:
    if not _SELECTED_FILTER:
        return
    items[:] = [it for it in items if getattr(it, "nodeid", "") in _SELECTED_FILTER]

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: object) -> object:
    _reset_test_buffer(getattr(item, "nodeid", ""), setup_ok=False)
    _start_tracing(restart=True)
    try:
        outcome = yield
    finally:
        _stop_tracing()
    excinfo = getattr(outcome, "excinfo", None)
    if excinfo is None:
        _STATE["setup_ok"] = True
    elif getattr(excinfo[0], "__name__", "") not in ("Skipped", "XFailed"):
        _record_item(False)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: object) -> object:
    cur_id = getattr(item, "nodeid", "")
    if _STATE.get("item_id") != cur_id:
        _reset_test_buffer(cur_id, setup_ok=True)
        _start_tracing(restart=True)
    else:
        _start_tracing(restart=False)
    try:
        outcome = yield
    finally:
        _stop_tracing()
    excinfo = getattr(outcome, "excinfo", None)
    if excinfo is None:
        if _STATE.get("setup_ok", True):
            _record_item(True)
    elif getattr(excinfo[0], "__name__", "") not in ("Skipped", "XFailed"):
        _record_item(False)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: object) -> object:
    _stop_tracing()
    try:
        yield
    finally:
        _stop_tracing()
        _reset_test_buffer("", setup_ok=False)

def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    _stop_tracing()
    _ACTIVE_LINES.clear()
    tid = _STATE["tid"]
    if isinstance(tid, int) and _MON is not None:
        try:
            _MON.free_tool_id(tid)
        except ValueError:
            _STATE["tid"] = None
        _STATE["tid"] = None
    tmp_out = f"{_OUT_JSON}.tmp"
    with open(tmp_out, "w", encoding="utf-8") as fh:
        json.dump(_COUNTS, fh)
    os.replace(tmp_out, _OUT_JSON)
    if _RECORDS_JSON:
        tmp_rec = f"{_RECORDS_JSON}.tmp"
        with open(tmp_rec, "w", encoding="utf-8") as fh:
            json.dump(_RECORDS, fh)
        os.replace(tmp_rec, _RECORDS_JSON)
'''


def _build_pass_cov_plugin_source(
    exec_root_posix: str,
    norm_hint_name: Optional[str],
    out_json_posix: str,
    *,
    prefer_settrace: bool = False,
    records_json_posix: Optional[str] = None,
    selected_nodeids: Optional[Sequence[str]] = None,
) -> str:
    """Genera il sorgente Python del plugin pytest temporaneo (setup + call, sys.monitoring/settrace)."""
    nodeids_tuple = tuple(selected_nodeids) if selected_nodeids else ()
    return (
        _PLUGIN_TEMPLATE.replace("__EXEC_ROOT__", repr(exec_root_posix))
        .replace("__HINT_RAW__", repr(norm_hint_name))
        .replace("__OUT_JSON__", repr(out_json_posix))
        .replace("__RECORDS_JSON__", repr(records_json_posix))
        .replace("__SELECTED_NODEIDS__", repr(nodeids_tuple))
        .replace("__PREFER_SETTRACE__", repr(bool(prefer_settrace)))
    )
