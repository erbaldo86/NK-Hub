# -*- coding: utf-8 -*-
"""Validatore ASD-STE100, prompt linter AP e linter EARS per nk_transcript_tools."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from _internal.nk_common.prompt_linter_core import evaluate_ap_rules

_STE100_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_STE100_INLINE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
_STE100_EMPTY_BACKTICKS_RE = re.compile(r"`+")
_STE100_MD_LINK_URL_RE = re.compile(r"\[([^\]]+)\]\((?:[^()\s]|\([^()\s]*\))+\)")
_STE100_URL_RE = re.compile(r"(?:https?://|file:///|conversation://)\S+", re.IGNORECASE)
_STE100_TABLE_SEP_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$|^\s*\|[\s:\-\|]+\|\s*$"
)
_STE100_HR_RE = re.compile(r"^\s*(?:-\s*-\s*-[-\s]*|\*\s*\*\s*\*[\*\s]*|_\s*_\s*_[_\s]*)$")
_STE100_LIST_PREFIX_RE = re.compile(r"^\s*(?:>+\s*)*(?:[-*+]\s+|\d+\.\s+|#{1,6}\s+)*")
_STE100_SPACED_DASH_ALL_RE = re.compile(r" [\u2014\u2013-] ")
_STE100_ABBREV_RE = re.compile(
    r"\b(es|fig|art|dott|prof|cap|sez|pag|ecc|vs|v|n|cfr)\.", re.IGNORECASE
)
_STE100_IDENTIFIER_DOT_RE = re.compile(r"(?<=\w)\.(?=\w)")
_STE100_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_STE100_ALPHA_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")

_EARS_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("EVENT_DRIVEN", re.compile(r"\bQUANDO\b.+\bIL\s+SISTEMA\s+DEVE\b", re.IGNORECASE)),
    ("UNWANTED_BEHAVIOR", re.compile(r"\bSE\b.+(?:\bALLORA\s+)?\bIL\s+SISTEMA\s+DEVE\b", re.IGNORECASE)),
    ("STATE_DRIVEN", re.compile(r"\bMENTRE\b.+\bIL\s+SISTEMA\s+DEVE\b", re.IGNORECASE)),
    ("OPTIONAL_FEATURE", re.compile(r"\bDOVE\b.+\bIL\s+SISTEMA\s+DEVE\b", re.IGNORECASE)),
    ("UBIQUITOUS", re.compile(r"\bIL\s+SISTEMA\s+DEVE\b", re.IGNORECASE)),
)
_REQ_LINE_RE = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)?(?:\*\*)?(R\d+)\b[:\s]*(.+)$")


def verify_ste100_compliance(text: str, max_sentence_words: int = 20) -> Dict[str, Any]:
    """Valida in modo Code-Safe la conformita ASD-STE100 su Markdown."""
    violations: List[str] = []
    checked_sentences = 0
    in_yaml_frontmatter = False
    in_yaml_card = False
    in_html_comment = False
    seen_first_content = False
    fence_char = ""
    fence_min_len = 0

    for line_idx, raw_line in enumerate((text or "").splitlines(), start=1):
        stripped = raw_line.strip()
        if not seen_first_content and not stripped:
            continue
        if not seen_first_content:
            seen_first_content = True
            if stripped == "---":
                in_yaml_frontmatter = True
                continue
        elif in_yaml_frontmatter:
            if stripped in ("---", "..."):
                in_yaml_frontmatter = False
            continue

        if fence_char:
            if re.match(rf"^\s*({re.escape(fence_char)}{{{fence_min_len},}})\s*$", raw_line):
                fence_char = ""
                fence_min_len = 0
            continue

        m_open = _STE100_FENCE_OPEN_RE.match(raw_line)
        if m_open:
            marker = m_open.group(1)
            fence_char = marker[0]
            fence_min_len = len(marker)
            continue

        if in_yaml_card:
            if "</yaml_metadata_card>" in stripped:
                in_yaml_card = False
            continue
        if "<yaml_metadata_card>" in stripped:
            if "</yaml_metadata_card>" not in stripped:
                in_yaml_card = True
            continue

        work_line = raw_line
        if in_html_comment:
            end_idx = work_line.find("-->")
            if end_idx == -1:
                continue
            work_line = work_line[end_idx + 3 :]
            in_html_comment = False

        work_line = re.sub(r"<!--.*?-->", " ", work_line)
        start_comment = work_line.find("<!--")
        if start_comment != -1:
            work_line = work_line[:start_comment]
            in_html_comment = True

        stripped_work = work_line.strip()
        if (
            not stripped_work
            or stripped_work.startswith(("http://", "https://", "file:///", "conversation://"))
            or _STE100_HR_RE.match(stripped_work)
            or ("--" in stripped_work and _STE100_TABLE_SEP_RE.match(stripped_work))
        ):
            continue

        masked_line = _STE100_INLINE_SPAN_RE.sub("CODETOKEN", work_line)
        masked_line = _STE100_EMPTY_BACKTICKS_RE.sub("", masked_line)
        masked_line = _STE100_MD_LINK_URL_RE.sub(r"\1", masked_line)
        masked_line = _STE100_URL_RE.sub("URLTOKEN", masked_line)

        is_table_row = "|" in masked_line and (
            stripped_work.startswith("|") or stripped_work.endswith("|")
        )
        raw_segments = masked_line.split("|") if is_table_row else [masked_line]

        dash_violation_on_line = False
        for seg in raw_segments:
            if not seg.strip():
                continue
            seg_body = _STE100_LIST_PREFIX_RE.sub("", seg)
            if not dash_violation_on_line and _STE100_SPACED_DASH_ALL_RE.search(seg_body):
                violations.append(
                    f"Riga {line_idx}: Rilevato inciso con trattino spaziato vietato da [RULE-STE100]."
                )
                dash_violation_on_line = True

            clean_seg = _STE100_ABBREV_RE.sub(r"\1", seg_body)
            clean_seg = _STE100_IDENTIFIER_DOT_RE.sub("", clean_seg)

            for raw_sent in _STE100_SENTENCE_SPLIT_RE.split(clean_seg):
                sent_norm = (
                    raw_sent.replace("\u2014", " ")
                    .replace("\u2013", " ")
                    .replace("/", " ")
                    .strip()
                )
                if not sent_norm:
                    continue
                words = _STE100_ALPHA_WORD_RE.findall(sent_norm)
                if not words:
                    continue
                checked_sentences += 1
                if len(words) > max_sentence_words:
                    violations.append(
                        f"Riga {line_idx}: Frase troppo lunga ({len(words)} parole > {max_sentence_words})."
                    )

    return {
        "passed": len(violations) == 0,
        "violations_count": len(violations),
        "violations": violations,
        "checked_sentences": checked_sentences,
    }


def lint_prompt_text(prompt_text: str, mode: str = "auto") -> Tuple[Dict[str, Any], int]:
    """Verifica gli anti-pattern canonici AP-1..AP-13 e AP-2b."""
    res = evaluate_ap_rules(prompt_text, mode=mode)
    return res, (0 if res["passed"] else 1)


def lint_ears_requirements(text: str) -> Dict[str, Any]:
    """Valida i requisiti in sintassi EARS italiana."""
    raw_lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    req_candidates: List[Tuple[str, str]] = []
    for ln in raw_lines:
        if ln.startswith("#") or ln.startswith("```"):
            continue
        m_req = _REQ_LINE_RE.match(ln)
        if m_req:
            req_candidates.append((m_req.group(1), m_req.group(2).strip()))

    if not req_candidates:
        for idx, ln in enumerate(raw_lines, start=1):
            if not ln.startswith("#") and not ln.startswith("```"):
                req_candidates.append((f"L{idx}", ln))

    violations: List[Dict[str, str]] = []
    valid_reqs: List[Dict[str, str]] = []
    matched_patterns: List[str] = []

    if not req_candidates:
        violations.append(
            {
                "id": "EARS-EMPTY",
                "requirement_id": "NONE",
                "message": "Nessun requisito trovato nel testo fornito.",
            }
        )
    else:
        for req_id, req_text in req_candidates:
            matched_type = next(
                (p_name for p_name, p_regex in _EARS_PATTERNS if p_regex.search(req_text)),
                "",
            )
            if matched_type:
                valid_reqs.append({"requirement_id": req_id, "pattern": matched_type, "text": req_text})
                matched_patterns.append(matched_type)
            else:
                violations.append(
                    {
                        "id": "EARS-01",
                        "requirement_id": req_id,
                        "message": f"Requisito {req_id} non conforme ai pattern EARS italiani ('IL SISTEMA DEVE'): {req_text}",
                    }
                )

    passed = len(violations) == 0 and len(valid_reqs) > 0
    return {
        "status": "PASS" if passed else "ADVISORY",
        "passed": passed,
        "valid": passed,
        "total_requirements": len(req_candidates),
        "ears_compliant_count": len(valid_reqs),
        "valid_count": len(valid_reqs),
        "violations_count": len(violations),
        "violations": violations,
        "advisories": violations,
        "matched_patterns": matched_patterns,
        "requirements": valid_reqs,
    }
