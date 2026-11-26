"""CLI unificata SSOT per SBFL Pytest Bridge e motore matriciale SBFL."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from _internal.nk_common.paths import reconfigure_streams

_PYTEST_CMD_RE = re.compile(r"(?:^|\s)(?:[\"']?[^\s\"']*[/\\])?pytest(?:\.exe)?(?=$|\s)|(?:^|\s)-m\s+pytest(?=$|\s)", re.IGNORECASE)
_QUIET_FLAG_RE = re.compile(r"^-q+$|^--quiet$")
_VERBOSE_FLAG_RE = re.compile(r"^-v+$|^--verbose$")


def _is_pytest_command(cmd_str: str) -> bool:
    return bool(_PYTEST_CMD_RE.search(cmd_str or ""))


def _split_tokens_keep_quotes(cmd_str: str) -> List[str]:
    tokens: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    for ch in cmd_str:
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            buf.append(ch)
        elif ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf.clear()
        else:
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def _strip_quiet_and_add_verbose(cmd: Sequence[str] | str) -> Sequence[str] | str:
    if isinstance(cmd, str):
        tokens = [tok for tok in _split_tokens_keep_quotes(cmd) if not _QUIET_FLAG_RE.fullmatch(tok)]
        if not any(_VERBOSE_FLAG_RE.fullmatch(tok) for tok in tokens):
            tokens.append("-v")
        return " ".join(tokens)
    tokens_seq = [str(part) for part in cmd if not _QUIET_FLAG_RE.fullmatch(str(part))]
    if not any(_VERBOSE_FLAG_RE.fullmatch(tok) for tok in tokens_seq):
        tokens_seq.append("-v")
    return tokens_seq


def _append_pytest_iso_flags(cmd: Sequence[str] | str, basetemp_dir: Path) -> Sequence[str] | str:
    bt_flag = f"--basetemp={basetemp_dir.as_posix()}"
    if isinstance(cmd, str):
        parts = [cmd]
        if "no:cacheprovider" not in cmd:
            parts.append("-p no:cacheprovider")
        if "--basetemp" not in cmd:
            parts.append(bt_flag)
        return " ".join(parts)
    out = [str(part) for part in cmd]
    joined = " ".join(out)
    if "no:cacheprovider" not in joined:
        out.extend(["-p", "no:cacheprovider"])
    if "--basetemp" not in joined:
        out.append(bt_flag)
    return out


def _rewrite_cmd_for_mirror(cmd: Sequence[str] | str, src_root: Path, mirror_dir: Path) -> Sequence[str] | str:
    variants = tuple(dict.fromkeys((str(src_root), src_root.as_posix(), str(src_root).replace("/", "\\"))))
    mirror_posix = mirror_dir.as_posix()
    if isinstance(cmd, str):
        res = cmd
        for v in variants:
            if v and v in res:
                res = res.replace(v, mirror_posix)
        return res
    out: List[str] = []
    for part in cmd:
        s = str(part)
        for v in variants:
            if v and v in s:
                s = s.replace(v, mirror_posix)
        out.append(s)
    return out


def _normalize_mirror_output(text: str, mirror_dir: Path) -> str:
    if not text:
        return text
    out = text
    for pref in (f"{mirror_dir.as_posix()}/", f"{str(mirror_dir)}\\", mirror_dir.as_posix(), str(mirror_dir)):
        if pref:
            out = out.replace(pref, "")
    return out


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NK Hub Generation 1.0.0-Generation SSOT Pytest-SBFL Ochiai Bridge & Engine")
    parser.add_argument("--test-cmd", type=str, default=None, help="Comando pytest da eseguire in modalita bridge")
    parser.add_argument("--target-file", type=str, default=None, help="File sorgente target da localizzare")
    parser.add_argument("--cwd", type=str, default=None, help="Directory di lavoro")
    parser.add_argument("--stage-dir", type=str, default=None, help="Cartella staging opzionale")
    parser.add_argument("--lane-id", type=str, default=None, help="ID lane isolata in .staging/lanes/<id>/")
    parser.add_argument("--collect-pass-coverage", action=argparse.BooleanOptionalAction, default=True, help="Raccoglie copertura pass/fail per calibrare spettro")
    parser.add_argument("--records-file", type=str, default=None, help="File JSON contenente una lista di CoverageRecord")
    parser.add_argument("--hybrid-fl", action="store_true", help="Emette al massimo 3 slice AST/sorgente compatte")
    parser.add_argument("--json", action="store_true", help="Stampa il payload JSON compatto")
    return parser


def _compute_matrix_payload(records_file: Optional[str]) -> Tuple[Any, List[Any]]:
    from _internal.sbfl_pytest_bridge.matrix_engine import CoverageMatrix, SBFLEngine
    from _internal.sbfl_pytest_bridge.models import CoverageRecord

    if records_file:
        raw_data = json.loads(Path(records_file).read_text(encoding="utf-8-sig"))
        records = [CoverageRecord.model_validate(item) for item in raw_data]
    else:
        records = [CoverageRecord(test_id="T1", passed=False, executed_statements=["module.py:10"]), CoverageRecord(test_id="T2", passed=True, executed_statements=["module.py:20"])]
    engine = SBFLEngine()
    ranked = engine.analyze(CoverageMatrix.from_records(records))
    return engine.generate_diagnostic_payload(ranked), ranked


def _run_matrix_cli(records_file: Optional[str]) -> int:
    payload, _ = _compute_matrix_payload(records_file)
    print(payload.to_compact_json())
    return 0


def _emit_hybrid_matrix_cli(records_file: Optional[str], cwd: Optional[str]) -> int:
    from _internal.sbfl_pytest_bridge.frame_extractor import build_hybrid_fl_slices
    from _internal.sbfl_pytest_bridge.scoring_helpers import split_stmt

    payload, ranked = _compute_matrix_payload(records_file)
    cands = [(*split_stmt(item.statement), float(item.ochiai)) for item in ranked[:3]]
    slices = build_hybrid_fl_slices(cands, [Path(cwd).resolve() if cwd else Path.cwd()], max_blocks=3, max_tokens=80)
    out = json.loads(payload.to_compact_json())
    out["hybrid_slices"] = slices
    print(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    return 0


def _emit_bridge_result(summary: Any, loc: Any, as_json: bool) -> int:
    if as_json:
        print(loc.render_payload_json() if loc else json.dumps({"status": "PASSED", "total_tests": summary.total_tests}, separators=(",", ":"), ensure_ascii=False))
    elif loc:
        tar, dst = float(getattr(loc, "tarantula", 0.0)), float(getattr(loc, "dstar", 0.0))
        print(f"🔴 [SBFL-OCHIAI] Fault detected at {loc.file_path}:{loc.line_number} (Score: {loc.suspiciousness})")
        print(f"   SBFL: Ochiai={loc.suspiciousness:.4f} Tarantula={tar:.4f} DStar={dst:.4f} Spectrum=(ef={int(getattr(loc, 'n_ef', 0))}, ep={int(getattr(loc, 'n_ep', 0))}, nf={int(getattr(loc, 'n_nf', 0))}, np={int(getattr(loc, 'n_np', 0))})")
        print(f"   Error: {loc.error_type}: {loc.error_message}")
        if loc.failing_line_content:
            print(f"   Code:  {loc.failing_line_content}")
        print(f"   Compact Payload: {loc.render_payload_json()}")
    else:
        print(f"🟢 [SBFL-OCHIAI] All {summary.total_tests} tests PASSED.")
    return int(summary.exit_code)


def _emit_hybrid_bridge_result(summary: Any, loc: Any, bridge: Any, as_json: bool) -> int:
    from _internal.sbfl_pytest_bridge.frame_extractor import build_hybrid_fl_slices
    from _internal.sbfl_pytest_bridge.scoring_helpers import split_stmt

    ranked = getattr(bridge, "last_ranked_scores", []) or []
    cands: List[Tuple[str, int, float]] = [(*split_stmt(item.statement), float(item.ochiai)) for item in ranked[:3]]
    if not cands and loc is not None:
        cands = [(str(loc.file_path), int(loc.line_number), float(loc.suspiciousness))]
    slices = build_hybrid_fl_slices(cands, [getattr(bridge, "_active_mirror_dir", None), getattr(bridge, "cwd", Path.cwd())], max_blocks=3, max_tokens=80)
    if as_json:
        base_obj = json.loads(loc.render_payload_json()) if loc else {"status": "PASSED", "total_tests": summary.total_tests}
        base_obj["hybrid_slices"] = slices
        print(json.dumps(base_obj, separators=(",", ":"), ensure_ascii=False))
        return int(summary.exit_code)
    rc = _emit_bridge_result(summary, loc, False)
    for idx, sl in enumerate(slices, start=1):
        print(f"   [HYBRID-FL #{idx} {sl['loc']} | {sl['tokens']} tok]\n{sl['slice']}")
    return rc


def _instantiate_sbfl_bridge(bridge_cls: Any, args: Any) -> Any:
    kw: dict[str, Any] = {"cwd": Path(args.cwd) if args.cwd else None}
    try:
        params = inspect.signature(bridge_cls).parameters
        has_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        for k, v in (("lane_id", getattr(args, "lane_id", None)), ("stage_dir", Path(args.stage_dir) if getattr(args, "stage_dir", None) else None)):
            if v is not None and (has_var or k in params):
                kw[k] = v
    except (TypeError, ValueError):
        pass
    return bridge_cls(**kw)


def _dispatch_cli_args(args: Any) -> int:
    if not args.test_cmd:
        return _emit_hybrid_matrix_cli(args.records_file, args.cwd) if getattr(args, "hybrid_fl", False) else _run_matrix_cli(args.records_file)
    bridge_cls = importlib.import_module("_internal.sbfl_pytest_bridge.bridge_core").SBFLPytestBridge
    bridge = _instantiate_sbfl_bridge(bridge_cls, args)
    summary, loc = bridge.run_and_diagnose(test_cmd=args.test_cmd, target_file_hint=args.target_file, collect_pass_coverage=bool(args.collect_pass_coverage))
    if getattr(args, "hybrid_fl", False):
        return _emit_hybrid_bridge_result(summary, loc, bridge, bool(args.json))
    return _emit_bridge_result(summary, loc, bool(args.json))


def main(argv: Optional[Sequence[str]] = None) -> int:
    reconfigure_streams()
    args = _build_cli_parser().parse_args(argv)
    return _dispatch_cli_args(args)
