# -*- coding: utf-8 -*-
"""Primitive stdlib SSOT per I/O deterministico dei moduli TAS DOM-04/DOM-05."""

from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.gt14_envelope import (
    DEFAULT_GT14_MAX_TOKENS, DEFAULT_GT14_PACK_MAX_BYTES,
    build_gt14_evidence_pack, build_gt14_exec_digest,
    default_gt14_diagnostics_dir, default_gt14_pointer_uri,
    estimate_compact_tokens, write_gt14_two_tier_envelope,
)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PYTEST_TOKEN_RE = re.compile(
    r"\b(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected)\b",
    re.IGNORECASE,
)
_PYTEST_DUR_RE = re.compile(r"\bin\s+(\d+(?:\.\d+)?)\s*s\b", re.IGNORECASE)
_PYTEST_NO_TESTS_RE = re.compile(
    r"^(?:=+\s*)?no\s+tests\s+ran(?:\s+in\s+(\d+(?:\.\d+)?)\s*s)?(?:\s*=+)?$",
    re.IGNORECASE,
)
_DOT_PROGRESS_RE = re.compile(r"^([.sxXFE]+)\s+\[\s*\d+%\]", re.MULTILINE)


def reconfigure_stdio_utf8() -> None:
    """Forza UTF-8 sui flussi stdio su Win32 senza fallire su stream mockati o chiusi."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                pass


def parse_deleted_files_manifest(manifest_path: Union[str, Path]) -> List[str]:
    """Valida e carica .deleted_files.json in modalita strict fail-closed."""
    p = Path(manifest_path)
    if not p.exists():
        return []
    if not p.is_file():
        raise ValueError(f"Percorso manifest .deleted_files.json non valido: {p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Errore parsing JSON .deleted_files.json ({p}): {exc}") from exc

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict) and isinstance(raw.get("deleted_files"), list):
        items = raw["deleted_files"]
    else:
        raise ValueError(
            "Formato invalido per .deleted_files.json: attesa lista o chiave 'deleted_files'."
        )

    cleaned: List[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(
                f"Elemento non stringa in .deleted_files.json all'indice {idx}: {type(item).__name__}"
            )
        norm_item = item.strip()
        if norm_item:
            cleaned.append(norm_item)
    return cleaned


def _safe_int_attr(elem: ET.Element, attr: str) -> int:
    raw = elem.attrib.get(attr, "0")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Attributo intero JUnit non valido ({attr}={raw!r})") from exc


def _safe_float_attr(elem: ET.Element, attr: str) -> float:
    raw = elem.attrib.get(attr, "0.0")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Attributo float JUnit non valido ({attr}={raw!r})") from exc


def parse_junit_xml_summary(xml_path: Union[str, Path]) -> Dict[str, Any]:
    """Estrae metriche aggregate da un report JUnit XML di pytest in modalita sicura."""
    xp = Path(xml_path)
    if not xp.is_file():
        raise FileNotFoundError(f"Report JUnit XML assente: {xp}")

    xml_text = xp.read_text(encoding="utf-8-sig")
    if "<!ENTITY" in xml_text.upper():
        raise ValueError("Dichiarazione XML ENTITY non consentita nel report JUnit.")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Report JUnit XML corrotto ({xp}): {exc}") from exc

    suites: List[ET.Element]
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = [child for child in root if child.tag == "testsuite"] or [root]
    else:
        raise ValueError(f"Tag radice JUnit non valido: {root.tag!r}")

    total = sum(_safe_int_attr(s, "tests") for s in suites)
    failed = sum(_safe_int_attr(s, "failures") for s in suites)
    errors = sum(_safe_int_attr(s, "errors") for s in suites)
    skipped = sum(_safe_int_attr(s, "skipped") for s in suites)
    duration_s = round(sum(_safe_float_attr(s, "time") for s in suites), 3)
    passed = max(0, total - failed - errors - skipped)
    executed = passed + failed + errors
    pass_rate_pct = round((passed / executed) * 100.0, 2) if executed > 0 else 0.0
    return {
        "source": "junit_xml", "total": total, "passed": passed,
        "failed": failed, "errors": errors, "skipped": skipped,
        "xfailed": 0, "tests_skipped": skipped, "deselected": 0,
        "duration_s": duration_s, "pass_rate_pct": pass_rate_pct, "found": True,
    }


_TOKEN_BUCKET: Dict[str, str] = {
    "passed": "passed", "xpassed": "passed", "failed": "failed",
    "error": "errors", "errors": "errors", "skipped": "skipped",
    "xfailed": "xfailed", "deselected": "deselected",
}


def _accumulate_pytest_tokens(tokens: List[Tuple[str, str]]) -> Dict[str, int]:
    """Somma i contatori dei token riepilogativi pytest tramite tabella uniforme."""
    counts: Dict[str, int] = {
        "passed": 0, "failed": 0, "errors": 0,
        "skipped": 0, "xfailed": 0, "deselected": 0,
    }
    for num_s, kind in tokens:
        bucket = _TOKEN_BUCKET.get(kind.lower())
        if bucket:
            counts[bucket] += int(num_s)
    return counts


def _match_pytest_summary_line(line: str) -> Optional[Dict[str, Any]]:
    clean = _ANSI_ESCAPE_RE.sub("", line).strip()
    if not clean:
        return None
    m_none = _PYTEST_NO_TESTS_RE.match(clean)
    if m_none:
        dur = round(float(m_none.group(1)), 3) if m_none.group(1) else 0.0
        return {
            "source": "stdout_tail",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "xfailed": 0,
            "tests_skipped": 0,
            "deselected": 0,
            "duration_s": dur,
            "pass_rate_pct": 0.0,
            "found": True,
        }

    tokens = _PYTEST_TOKEN_RE.findall(clean)
    if not tokens:
        return None
    has_dur = _PYTEST_DUR_RE.search(clean)
    has_banner = clean.startswith("=") and clean.endswith("=")
    if not has_dur and not has_banner:
        bare = re.sub(
            r"(?:\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed|deselected)\s*,?\s*)+",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        if bare:
            return None

    counts = _accumulate_pytest_tokens(tokens)
    total = (
        counts["passed"]
        + counts["failed"]
        + counts["errors"]
        + counts["skipped"]
        + counts["xfailed"]
    )
    executed = counts["passed"] + counts["failed"] + counts["errors"]
    duration_s = round(float(has_dur.group(1)), 3) if has_dur else 0.0
    pass_rate_pct = round((counts["passed"] / executed) * 100.0, 2) if executed > 0 else 0.0
    return {
        "source": "stdout_tail",
        "total": total,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "xfailed": counts["xfailed"],
        "tests_skipped": counts["skipped"] + counts["xfailed"],
        "deselected": counts["deselected"],
        "duration_s": duration_s,
        "pass_rate_pct": pass_rate_pct,
        "found": True,
    }


def _parse_dot_progress_fallback(stdout: str, stderr: str) -> Optional[Dict[str, Any]]:
    """Ricava il conteggio dai caratteri dot-progress solo se manca il riepilogo pytest."""
    combined = f"{stdout or ''}\n{stderr or ''}".replace("\r\n", "\n")
    chars = "".join(m.group(1) for m in _DOT_PROGRESS_RE.finditer(combined))
    if not chars:
        return None
    passed = chars.count(".") + chars.count("X")
    failed = chars.count("F")
    errors = chars.count("E")
    skipped = chars.count("s")
    xfailed = chars.count("x")
    total = passed + failed + errors + skipped + xfailed
    executed = passed + failed + errors
    return {
        "source": "stdout_dots",
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "xfailed": xfailed,
        "tests_skipped": skipped + xfailed,
        "deselected": 0,
        "duration_s": 0.0,
        "pass_rate_pct": round((passed / executed) * 100.0, 2) if executed > 0 else 0.0,
        "found": total > 0,
    }


def _try_parse_junit_xml(
    junit_xml_path: Optional[Union[str, Path]],
) -> Optional[Dict[str, Any]]:
    """Parsa junit_xml_path se fornito e presente su disco."""
    if junit_xml_path is None:
        return None
    xp = Path(junit_xml_path)
    return parse_junit_xml_summary(xp) if xp.is_file() else None


def _scan_pytest_summary_lines(
    stdout: str, stderr: str
) -> Optional[Dict[str, Any]]:
    """Scansiona in ordine inverso le righe di stdout e stderr per il riepilogo pytest."""
    for text in (stdout or "", stderr or ""):
        for raw_line in reversed(text.splitlines()):
            parsed = _match_pytest_summary_line(raw_line)
            if parsed is not None:
                return parsed
    return None


def parse_pytest_summary(
    stdout: str,
    stderr: str = "",
    junit_xml_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Estrae il riepilogo pytest privilegiando JUnit XML e scansione bottom-up."""
    xml_parsed = _try_parse_junit_xml(junit_xml_path)
    if xml_parsed is not None:
        return xml_parsed

    line_parsed = _scan_pytest_summary_lines(stdout, stderr)
    if line_parsed is not None:
        return line_parsed

    dot_parsed = _parse_dot_progress_fallback(stdout, stderr)
    if dot_parsed is not None:
        return dot_parsed

    return {
        "source": "stdout_tail",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "tests_skipped": 0,
        "deselected": 0,
        "duration_s": 0.0,
        "pass_rate_pct": 0.0,
        "found": False,
    }


def _decode_jsonl_dict(raw_line: str) -> Dict[str, Any]:
    parsed = json.loads(raw_line)
    if not isinstance(parsed, dict):
        raise ValueError("Ultima riga JSONL non rappresenta un oggetto JSON.")
    return parsed


def _read_tail_last_line(p: Path, step: int, limit: int) -> Optional[str]:
    size = p.stat().st_size
    if size <= 0:
        return None
    buf = b""
    pos = size
    read_total = 0
    with open(p, "rb") as fh:
        while pos > 0 and read_total < limit:
            to_read = min(step, pos)
            pos -= to_read
            fh.seek(pos, os.SEEK_SET)
            buf = fh.read(to_read) + buf
            read_total += to_read
            stripped = buf.rstrip(b" \t\r\n")
            nl_idx = stripped.rfind(b"\n")
            if stripped and nl_idx != -1:
                return stripped[nl_idx + 1 :].decode("utf-8-sig")
    return None


def read_last_jsonl_entry(
    jsonl_path: Union[str, Path],
    chunk_size: int = 8192,
    max_tail_bytes: int = 262144,
) -> Optional[Dict[str, Any]]:
    """Legge in O(1) da EOF l'ultima riga JSON non vuota di un file JSONL."""
    p = Path(jsonl_path)
    if not p.is_file():
        return None
    tail_line = _read_tail_last_line(p, max(256, int(chunk_size)), max(256, int(max_tail_bytes)))
    if tail_line is not None:
        return _decode_jsonl_dict(tail_line)

    for candidate in reversed(p.read_bytes().decode("utf-8-sig").splitlines()):
        s = candidate.strip()
        if s:
            return _decode_jsonl_dict(s)
    return None


def build_compact_diagnostic_verdict(
    status: str, hard_gate: int, metrics: Dict[str, Any], top_findings: List[str],
    pointer_uri: str, max_tokens: int = DEFAULT_GT14_MAX_TOKENS,
    certification_tier: Optional[str] = None,
) -> Dict[str, Any]:
    """Costruisce il Tier A gt14_exec_digest garantito sotto max_tokens con pointer_uri."""
    return build_gt14_exec_digest(
        status=status, hard_gate=hard_gate, metrics=metrics,
        top_findings=top_findings, pointer_uri=pointer_uri,
        max_tokens=max_tokens, certification_tier=certification_tier,
    )


__all__ = [
    "DEFAULT_GT14_MAX_TOKENS", "DEFAULT_GT14_PACK_MAX_BYTES",
    "build_compact_diagnostic_verdict", "build_gt14_evidence_pack",
    "build_gt14_exec_digest", "default_gt14_diagnostics_dir",
    "default_gt14_pointer_uri", "estimate_compact_tokens",
    "parse_deleted_files_manifest", "parse_junit_xml_summary",
    "parse_pytest_summary", "read_last_jsonl_entry",
    "reconfigure_stdio_utf8", "write_gt14_two_tier_envelope",
]
