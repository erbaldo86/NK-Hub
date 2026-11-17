# -*- coding: utf-8 -*-
"""Modelli Pydantic DOM, costanti HTML5, parser e indice strutturale per oracle_evaluator_l3."""

from __future__ import annotations

from html.parser import HTMLParser
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.facade_boot import resolve_facade_attr

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
_FACADE_MOD_NAMES: Tuple[str, ...] = (
    "oracle_evaluator_l3",
    "scripts.oracle_evaluator_l3",
)


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


HTML5_VOID_TAGS: Set[str] = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

ALLOWED_HTML_EXTENSIONS: Tuple[str, ...] = (".html", ".htm")
ALLOWED_EXPECTED_EXTENSIONS: Tuple[str, ...] = (".html", ".htm", ".md", ".json")

_HTML5_CLOSES_OPEN_P: Set[str] = {
    "address",
    "article",
    "aside",
    "blockquote",
    "details",
    "div",
    "dl",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hgroup",
    "hr",
    "main",
    "menu",
    "nav",
    "ol",
    "p",
    "pre",
    "search",
    "section",
    "table",
    "ul",
}

_NON_HTML_EXT_RE = re.compile(
    r"\.(?:env|json|ya?ml|toml|ini|cfg|conf|py|pyc|txt|md|xml|csv|sqlite3?|db|key|pem|crt|log|lock|sh|bat|cmd|ps1|exe|dll)$",
    re.IGNORECASE,
)
_FENCED_HTML_BLOCK_RE = re.compile(
    r"```(?:html|htm)\s*\n([\s\S]*?)```", re.IGNORECASE
)
_MD_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_MD_PAIRED_HTML_RE = re.compile(
    r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>[\s\S]*?</\1>"
)
_MD_ID_TOKEN_RE = re.compile(r"(?:`#|(?:^|[\s,(])#)([A-Za-z_][A-Za-z0-9_-]*)")
_MD_TAG_TOKEN_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
_MD_QUOTED_TEXT_RE = re.compile(r'"([^"\n]{2,})"')
_MD_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")


class DOMNode(BaseModel):
    """Rappresentazione strutturale normalizzata di un elemento DOM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    tag: str
    attrs: Dict[str, str] = Field(default_factory=dict)
    text: str = ""
    children: List[DOMNode] = Field(default_factory=list)


class DOMDeltaItem(BaseModel):
    """Differenza strutturale rilevata tra due stati DOM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    change_type: str = Field(
        description="ADDED, REMOVED, TAG_MISMATCH, ATTRIBUTE_MISMATCH, TEXT_MISMATCH"
    )
    path: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    details: str = ""


class DOMEvaluationReport(BaseModel):
    """Rapporto di verifica emesso dall'Oracolo DOM L3."""

    model_config = ConfigDict(strict=True, extra="forbid")

    verdict: str = Field(description="PASS oppure FAIL")
    total_expected_nodes: int = Field(ge=0)
    total_actual_nodes: int = Field(ge=0)
    discrepancy_count: int = Field(ge=0)
    deltas: List[DOMDeltaItem] = Field(default_factory=list)
    summary_message: str


class _DOMBuilderParser(HTMLParser):
    """Parser HTML5 leggero con gestione void tag e chiusure implicite."""

    def __init__(self) -> None:
        super().__init__()
        self.root: DOMNode = DOMNode(tag="__root__")
        self.stack: List[DOMNode] = [self.root]

    def _close_implicit_open_tags(self, incoming_tag: str) -> None:
        """Applica le regole HTML5 di chiusura implicita per tag opzionali ripetuti."""
        if len(self.stack) <= 1:
            return

        if incoming_tag == "li":
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag == "li":
                    self.stack = self.stack[:i]
                    break
                if open_tag in ("ul", "ol", "menu", "template"):
                    break
        elif incoming_tag in _HTML5_CLOSES_OPEN_P:
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag == "p":
                    self.stack = self.stack[:i]
                    break
                if open_tag in ("td", "th", "caption", "table", "template", "html", "body"):
                    break
        elif incoming_tag in ("dt", "dd"):
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag in ("dt", "dd"):
                    self.stack = self.stack[:i]
                    break
                if open_tag in ("dl", "template"):
                    break
        elif incoming_tag == "option":
            if self.stack[-1].tag == "option":
                self.stack.pop()
        elif incoming_tag == "optgroup":
            if self.stack[-1].tag == "option":
                self.stack.pop()
            if len(self.stack) > 1 and self.stack[-1].tag == "optgroup":
                self.stack.pop()
        elif incoming_tag in ("td", "th"):
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag in ("td", "th"):
                    self.stack = self.stack[:i]
                    break
                if open_tag in ("tr", "table", "thead", "tbody", "tfoot", "template"):
                    break
        elif incoming_tag == "tr":
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag == "tr":
                    self.stack = self.stack[:i]
                    break
                if open_tag in ("table", "thead", "tbody", "tfoot", "template"):
                    break
        elif incoming_tag in ("thead", "tbody", "tfoot"):
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag in ("thead", "tbody", "tfoot"):
                    self.stack = self.stack[:i]
                    break
                if open_tag in ("table", "template"):
                    break

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        tag_low = tag.lower()
        self._close_implicit_open_tags(tag_low)
        attr_dict = {k: (v if v is not None else "") for k, v in attrs}
        node = DOMNode(tag=tag_low, attrs=attr_dict)
        if self.stack:
            self.stack[-1].children.append(node)
        if tag_low not in HTML5_VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        tag_low = tag.lower()
        self._close_implicit_open_tags(tag_low)
        attr_dict = {k: (v if v is not None else "") for k, v in attrs}
        node = DOMNode(tag=tag_low, attrs=attr_dict)
        if self.stack:
            self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag_low = tag.lower()
        if tag_low in HTML5_VOID_TAGS:
            return
        if len(self.stack) > 1:
            for i in range(len(self.stack) - 1, 0, -1):
                if self.stack[i].tag == tag_low:
                    self.stack = self.stack[:i]
                    break

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned and self.stack:
            curr = self.stack[-1]
            curr.text = f"{curr.text} {cleaned}".strip() if curr.text else cleaned


def _collect_dom_index(root: DOMNode) -> Dict[str, Any]:
    """Indicizza tag, id, classi CSS, intestazioni e testo aggregato del DOM reale."""
    tags: Set[str] = set()
    ids: Set[str] = set()
    classes: Set[str] = set()
    text_parts: List[str] = []
    headings: Dict[str, List[str]] = {}

    def _walk(node: DOMNode) -> None:
        if node.tag != "__root__":
            tags.add(node.tag)
            if "id" in node.attrs and node.attrs["id"]:
                ids.add(node.attrs["id"])
            if "class" in node.attrs and node.attrs["class"]:
                for cls_tok in node.attrs["class"].split():
                    classes.add(cls_tok)
            if node.text:
                text_parts.append(node.text)
            if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6") and node.text:
                headings.setdefault(node.tag, []).append(" ".join(node.text.split()))
        for child in node.children:
            _walk(child)

    _walk(root)
    return {
        "tags": tags,
        "ids": ids,
        "classes": classes,
        "full_text": " ".join(" ".join(text_parts).split()),
        "headings": headings,
    }
