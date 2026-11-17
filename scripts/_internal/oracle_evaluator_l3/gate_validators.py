# -*- coding: utf-8 -*-
"""Guardie anti-LFI, risoluzione sorgenti e validazione vincoli strutturali DOM."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from _internal.oracle_evaluator_l3.models_and_dom import (
    ALLOWED_EXPECTED_EXTENSIONS,
    ALLOWED_HTML_EXTENSIONS,
    DOMDeltaItem,
    DOMNode,
    _FENCED_HTML_BLOCK_RE,
    _MD_BULLET_PREFIX_RE,
    _MD_HEADING_RE,
    _MD_ID_TOKEN_RE,
    _MD_PAIRED_HTML_RE,
    _MD_QUOTED_TEXT_RE,
    _MD_TAG_TOKEN_RE,
    _NON_HTML_EXT_RE,
    _collect_dom_index,
)


def _extract_candidate_file_str(candidate: str) -> str:
    """Estrae il percorso file base rimuovendo selettori e preservando la lettera di unita."""
    if ":" not in candidate or Path(candidate).suffix.lower() in ALLOWED_EXPECTED_EXTENSIONS:
        return candidate
    parts = candidate.rsplit(":", 2)
    base_str = parts[0]
    if len(base_str) == 1 and len(parts) >= 2:
        base_str = f"{parts[0]}:{parts[1]}"
    return base_str


def _has_traversal_segment(raw_path: str) -> bool:
    """Rileva segmenti di path traversal '..' su separatori POSIX o Windows."""
    return ".." in [seg for seg in re.split(r"[\\/]+", raw_path) if seg]


def _looks_like_disallowed_file_reference(base_str: str) -> bool:
    """Identifica riferimenti a file non HTML per bloccare tentativi di LFI."""
    if not base_str or any(ch in base_str for ch in ("\n", "\r")):
        return False
    if _NON_HTML_EXT_RE.search(base_str):
        return True
    if base_str.startswith(".") and " " not in base_str:
        return True
    if ("/" in base_str or "\\" in base_str) and " " not in base_str:
        return True
    return bool(re.match(r"^[a-zA-Z]:[\\/]", base_str))


def _expected_kind_from_path(base_str: str) -> str:
    """Mappa l'estensione del target atteso nel tipo canonico html, md oppure json."""
    ext = Path(base_str).suffix.lower()
    if ext == ".json":
        return "json"
    return "md" if ext == ".md" else "html"


def _read_validated_html_file(file_path_str: str) -> str:
    """Legge esclusivamente file .html o .htm bloccando traversal e LFI."""
    cleaned = file_path_str.strip()
    if not cleaned:
        raise ValueError("Empty HTML file path provided.")
    base_str = _extract_candidate_file_str(cleaned)
    if _has_traversal_segment(cleaned) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in HTML source: {file_path_str}")
    if not base_str.lower().endswith(ALLOWED_HTML_EXTENSIONS):
        raise ValueError(f"Non-HTML file extension blocked (only .html/.htm allowed): {base_str}")
    target = Path(base_str)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"HTML file not found: {file_path_str}")
    return target.read_text(encoding="utf-8")


def _read_validated_expected_file(file_path_str: str) -> Tuple[str, str]:
    """Legge file attesi ammessi bloccando traversal ed estensioni vietate."""
    cleaned = file_path_str.strip()
    if not cleaned:
        raise ValueError("Empty expected file path provided.")
    base_str = _extract_candidate_file_str(cleaned)
    if _has_traversal_segment(cleaned) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in expected source: {file_path_str}")
    if not base_str.lower().endswith(ALLOWED_EXPECTED_EXTENSIONS):
        raise ValueError(
            f"Unsupported expected file extension blocked (allowed: .html, .htm, .md, .json): {base_str}"
        )
    target = Path(base_str)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Expected file not found: {file_path_str}")
    return target.read_text(encoding="utf-8"), _expected_kind_from_path(base_str)


def resolve_html_source(source_or_path: str) -> str:
    """Risolve una stringa HTML o un file .html/.htm bloccando path traversal e LFI."""
    candidate = source_or_path.strip()
    if not candidate or "<" in candidate or ">" in candidate:
        return source_or_path

    base_str = _extract_candidate_file_str(candidate)
    if _has_traversal_segment(candidate) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in HTML source: {source_or_path}")

    if base_str.lower().endswith(ALLOWED_HTML_EXTENSIONS):
        p_html = Path(base_str)
        if p_html.exists() and p_html.is_file():
            return p_html.read_text(encoding="utf-8")
        raise FileNotFoundError(f"HTML file not found: {candidate}")

    p_direct, p_base = Path(candidate), Path(base_str)
    if (
        (p_direct.exists() and p_direct.is_file())
        or (p_base.exists() and p_base.is_file())
        or _looks_like_disallowed_file_reference(base_str)
    ):
        raise ValueError(
            f"Non-HTML file read blocked by LFI guard (only .html/.htm allowed): {base_str}"
        )
    return source_or_path


def resolve_expected_source(source_or_path: str) -> Tuple[str, str]:
    """Risolve una specifica attesa inline o da file con guardia anti-LFI."""
    candidate = source_or_path.strip()
    if not candidate:
        return source_or_path, "html"

    if candidate.startswith("{"):
        try:
            if isinstance(json.loads(candidate), dict):
                return source_or_path, "json"
        except json.JSONDecodeError:
            pass

    if "```html" in candidate.lower() or "```htm" in candidate.lower():
        return source_or_path, "md"

    if not candidate.startswith("<") and any(
        _MD_HEADING_RE.match(ln) or _MD_BULLET_PREFIX_RE.match(ln)
        for ln in candidate.splitlines()
    ):
        return source_or_path, "md"

    if "<" in candidate or ">" in candidate:
        return source_or_path, "html"

    base_str = _extract_candidate_file_str(candidate)
    if _has_traversal_segment(candidate) or _has_traversal_segment(base_str):
        raise ValueError(f"Path traversal '..' blocked in expected source: {source_or_path}")

    if base_str.lower().endswith(ALLOWED_EXPECTED_EXTENSIONS):
        p_exp = Path(base_str)
        if p_exp.exists() and p_exp.is_file():
            return p_exp.read_text(encoding="utf-8"), _expected_kind_from_path(base_str)
        raise FileNotFoundError(f"Expected file not found: {candidate}")

    p_direct, p_base = Path(candidate), Path(base_str)
    if (
        (p_direct.exists() and p_direct.is_file())
        or (p_base.exists() and p_base.is_file())
        or _looks_like_disallowed_file_reference(base_str)
    ):
        raise ValueError(
            f"Disallowed expected file reference blocked (allowed: .html, .htm, .md, .json): {base_str}"
        )
    return source_or_path, "html"


def _extract_markdown_expectations(md_text: str) -> Dict[str, Any]:
    """Estrae blocchi HTML o vincoli strutturali da un file Markdown."""
    fenced_blocks = _FENCED_HTML_BLOCK_RE.findall(md_text)
    if fenced_blocks:
        return {"mode": "html", "html": "\n".join(fenced_blocks)}

    has_heading = any(_MD_HEADING_RE.match(ln) for ln in md_text.splitlines())
    if not has_heading and md_text.lstrip().startswith("<") and _MD_PAIRED_HTML_RE.search(md_text):
        return {"mode": "html", "html": md_text}

    headings: List[Tuple[str, str]] = []
    req_ids: List[str] = []
    req_tags: List[str] = []
    req_texts: List[str] = []
    in_code_fence = False

    for raw_line in md_text.splitlines():
        line_s = raw_line.strip()
        if line_s.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line_s:
            continue

        hm = _MD_HEADING_RE.match(line_s)
        if hm:
            h_text = hm.group(2).strip(" `*")
            if h_text:
                headings.append((f"h{len(hm.group(1))}", h_text))
            continue

        for fid in _MD_ID_TOKEN_RE.findall(line_s):
            if fid not in req_ids:
                req_ids.append(fid)
        for ftag in _MD_TAG_TOKEN_RE.findall(line_s):
            tl = ftag.lower()
            if tl not in req_tags:
                req_tags.append(tl)

        quoted_items = _MD_QUOTED_TEXT_RE.findall(line_s)
        for q in quoted_items:
            if q not in req_texts:
                req_texts.append(q)

        bm = _MD_BULLET_PREFIX_RE.match(line_s)
        if bm and not quoted_items:
            cleaned_body = _MD_ID_TOKEN_RE.sub("", _MD_TAG_TOKEN_RE.sub("", bm.group(1).strip()))
            cleaned_body = re.sub(
                r"^(?:required[_\s]?(?:tag|id|class|text)|tag|id|class|text)\s*:\s*",
                "", cleaned_body, flags=re.IGNORECASE,
            ).strip(" `,-:")
            if cleaned_body and not re.fullmatch(r"#[A-Za-z_][A-Za-z0-9_-]*", cleaned_body):
                if cleaned_body not in req_texts:
                    req_texts.append(cleaned_body)

    return {
        "mode": "structured", "headings": headings, "required_tags": req_tags,
        "required_ids": req_ids, "required_classes": [], "required_texts": req_texts,
    }


def validate_structured_expectations_impl(
    spec: Dict[str, Any],
    act_root: DOMNode,
    path_prefix: str,
    deltas: List[DOMDeltaItem],
) -> int:
    """Valida vincoli strutturali JSON o Markdown contro l'albero DOM effettivo."""
    idx = _collect_dom_index(act_root)
    checks_count = 0

    for h_tag, h_text in spec.get("headings", []):
        checks_count += 1
        norm_expected_h = " ".join(str(h_text).split())
        actual_h_list = idx["headings"].get(h_tag, [])
        if h_tag not in idx["tags"]:
            deltas.append(
                DOMDeltaItem(
                    change_type="TAG_MISMATCH", path=f"{path_prefix}/{h_tag}",
                    expected=f"<{h_tag}>{norm_expected_h}</{h_tag}>", actual=None,
                    details=f"Expected heading tag <{h_tag}> missing from actual DOM",
                )
            )
        elif not any(norm_expected_h in ah for ah in actual_h_list):
            deltas.append(
                DOMDeltaItem(
                    change_type="TEXT_MISMATCH", path=f"{path_prefix}/{h_tag}",
                    expected=norm_expected_h, actual="; ".join(actual_h_list) if actual_h_list else "",
                    details=f"Expected heading <{h_tag}> text '{norm_expected_h}' not found",
                )
            )

    for req_tag in spec.get("required_tags", []):
        checks_count += 1
        t_low = str(req_tag).strip().lstrip("<").rstrip(">").lower()
        if t_low and t_low not in idx["tags"]:
            deltas.append(
                DOMDeltaItem(
                    change_type="REMOVED", path=f"{path_prefix}/tag:{t_low}",
                    expected=f"<{t_low}>", actual=None,
                    details=f"Required tag <{t_low}> missing from actual DOM",
                )
            )

    for req_id in spec.get("required_ids", []):
        checks_count += 1
        id_clean = str(req_id).strip().lstrip("#")
        if id_clean and id_clean not in idx["ids"]:
            deltas.append(
                DOMDeltaItem(
                    change_type="ATTRIBUTE_MISMATCH", path=f"{path_prefix}#{id_clean}",
                    expected=id_clean, actual=None,
                    details=f"Required element id '#{id_clean}' missing from actual DOM",
                )
            )

    for req_cls in spec.get("required_classes", []):
        checks_count += 1
        cls_clean = str(req_cls).strip().lstrip(".")
        if cls_clean and cls_clean not in idx["classes"]:
            deltas.append(
                DOMDeltaItem(
                    change_type="ATTRIBUTE_MISMATCH", path=f"{path_prefix}.{cls_clean}",
                    expected=cls_clean, actual=None,
                    details=f"Required CSS class '.{cls_clean}' missing from actual DOM",
                )
            )

    for req_txt in spec.get("required_texts", []):
        checks_count += 1
        txt_norm = " ".join(str(req_txt).split())
        if txt_norm and txt_norm not in idx["full_text"]:
            deltas.append(
                DOMDeltaItem(
                    change_type="TEXT_MISMATCH", path=f"{path_prefix}/text",
                    expected=txt_norm, actual=idx["full_text"][:200],
                    details=f"Required text '{txt_norm}' missing from actual DOM",
                )
            )

    if checks_count == 0:
        deltas.append(
            DOMDeltaItem(
                change_type="TEXT_MISMATCH", path=path_prefix,
                expected="html|expected_html|required_*|headings", actual="empty",
                details="Structured expectation file contains no valid DOM assertions.",
            )
        )
    return checks_count
