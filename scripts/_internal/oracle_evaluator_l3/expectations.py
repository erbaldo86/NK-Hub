# -*- coding: utf-8 -*-
"""Estrazione aspettative Markdown/JSON e validazione vincoli DOM strutturali."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from _internal.oracle_evaluator_l3.models_and_dom import (
    DOMDeltaItem,
    DOMNode,
    _FENCED_HTML_BLOCK_RE,
    _MD_BULLET_PREFIX_RE,
    _MD_HEADING_RE,
    _MD_ID_TOKEN_RE,
    _MD_PAIRED_HTML_RE,
    _MD_QUOTED_TEXT_RE,
    _MD_TAG_TOKEN_RE,
    _collect_dom_index,
)


def _append_unique(target: List[str], item: str) -> None:
    if item and item not in target:
        target.append(item)


def _parse_markdown_bullet_and_tokens(
    line_s: str, req_ids: List[str], req_tags: List[str], req_texts: List[str]
) -> None:
    """Estrae #id, <tag>, testi quotati ed elementi elenco da una riga Markdown."""
    for fid in _MD_ID_TOKEN_RE.findall(line_s):
        _append_unique(req_ids, fid)
    for ftag in _MD_TAG_TOKEN_RE.findall(line_s):
        _append_unique(req_tags, ftag.lower())
    quoted_items = _MD_QUOTED_TEXT_RE.findall(line_s)
    for q in quoted_items:
        _append_unique(req_texts, q)
    bm = _MD_BULLET_PREFIX_RE.match(line_s)
    if bm and not quoted_items:
        cleaned_body = _MD_ID_TOKEN_RE.sub("", _MD_TAG_TOKEN_RE.sub("", bm.group(1).strip()))
        cleaned_body = re.sub(
            r"^(?:required[_\s]?(?:tag|id|class|text)|tag|id|class|text)\s*:\s*",
            "", cleaned_body, flags=re.IGNORECASE,
        ).strip(" `,-:")
        if cleaned_body and not re.fullmatch(r"#[A-Za-z_][A-Za-z0-9_-]*", cleaned_body):
            _append_unique(req_texts, cleaned_body)


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
        _parse_markdown_bullet_and_tokens(line_s, req_ids, req_tags, req_texts)

    return {
        "mode": "structured", "headings": headings, "required_tags": req_tags,
        "required_ids": req_ids, "required_classes": [], "required_texts": req_texts,
    }


def _check_heading_expectations(
    headings: List[Tuple[str, str]],
    idx: Dict[str, Any],
    path_prefix: str,
    deltas: List[DOMDeltaItem],
) -> int:
    """Verifica i vincoli sulle intestazioni attese contro l'indice DOM."""
    count = 0
    for h_tag, h_text in headings:
        count += 1
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
    return count


def _check_membership_constraints(
    items: List[Any],
    present_set: set[str],
    strip_chars: str,
    lower_val: bool,
    change_type: str,
    path_prefix: str,
    fmt_kind: str,
    deltas: List[DOMDeltaItem],
) -> int:
    """Verifica presenza di tag, id o classi CSS richieste nell'indice DOM."""
    count = 0
    for raw_item in items:
        count += 1
        val = str(raw_item).strip()
        for ch in strip_chars:
            val = val.strip(ch)
        if lower_val:
            val = val.lower()
        if not val or val in present_set:
            continue
        if fmt_kind == "tag":
            p_str, exp_s, det = f"{path_prefix}/tag:{val}", f"<{val}>", f"Required tag <{val}> missing from actual DOM"
        elif fmt_kind == "id":
            p_str, exp_s, det = f"{path_prefix}#{val}", val, f"Required element id '#{val}' missing from actual DOM"
        else:
            p_str, exp_s, det = f"{path_prefix}.{val}", val, f"Required CSS class '.{val}' missing from actual DOM"
        deltas.append(DOMDeltaItem(change_type=change_type, path=p_str, expected=exp_s, actual=None, details=det))
    return count


def _check_text_constraints(
    req_texts: List[Any], full_text: str, path_prefix: str, deltas: List[DOMDeltaItem]
) -> int:
    """Verifica la presenza dei testi richiesti nel testo normalizzato del DOM."""
    count = 0
    for req_txt in req_texts:
        count += 1
        txt_norm = " ".join(str(req_txt).split())
        if txt_norm and txt_norm not in full_text:
            deltas.append(
                DOMDeltaItem(
                    change_type="TEXT_MISMATCH", path=f"{path_prefix}/text",
                    expected=txt_norm, actual=full_text[:200],
                    details=f"Required text '{txt_norm}' missing from actual DOM",
                )
            )
    return count


def validate_structured_expectations_impl(
    spec: Dict[str, Any],
    act_root: DOMNode,
    path_prefix: str,
    deltas: List[DOMDeltaItem],
) -> int:
    """Valida vincoli strutturali JSON o Markdown contro l'albero DOM effettivo."""
    idx = _collect_dom_index(act_root)
    checks_count = _check_heading_expectations(spec.get("headings", []), idx, path_prefix, deltas)
    checks_count += _check_membership_constraints(
        spec.get("required_tags", []), idx["tags"], "<>", True, "REMOVED", path_prefix, "tag", deltas
    )
    checks_count += _check_membership_constraints(
        spec.get("required_ids", []), idx["ids"], "#", False, "ATTRIBUTE_MISMATCH", path_prefix, "id", deltas
    )
    checks_count += _check_membership_constraints(
        spec.get("required_classes", []), idx["classes"], ".", False, "ATTRIBUTE_MISMATCH", path_prefix, "cls", deltas
    )
    checks_count += _check_text_constraints(spec.get("required_texts", []), idx["full_text"], path_prefix, deltas)

    if checks_count == 0:
        deltas.append(
            DOMDeltaItem(
                change_type="TEXT_MISMATCH", path=path_prefix,
                expected="html|expected_html|required_*|headings", actual="empty",
                details="Structured expectation file contains no valid DOM assertions.",
            )
        )
    return checks_count
