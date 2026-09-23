#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.5.0-Hardened - L3 DOM Reader & E2E Oracle Evaluator
Module: oracle_evaluator_l3.py
Author: NK-Oracle-Evaluator (Node 10) & NK-Platform-Builder
Implements: Macro-Fase 2 Cold Review E2E DOM Delta Verification

Features:
- Pure-Python deterministic HTML/DOM structural parsing via html.parser.
- Zero-mock comparison between expected and actual DOM state.
- Attribute, class, ID and hierarchy difference detection.
- Pydantic v2 Strict Mode serialization with compact diff emission.
- CLI interface with JSON/compact report support.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field

_scripts_dir = Path(__file__).resolve().parent
_root_dir = _scripts_dir.parent.parent if _scripts_dir.parent.name == ".staging" else _scripts_dir.parent
for _d in (_scripts_dir, _root_dir / "scripts", _root_dir / ".staging" / "scripts", _root_dir):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    from scripts.platform_runner import reconfigure_streams


class DOMNode(BaseModel):
    """Normalized structural representation of a DOM element."""
    model_config = ConfigDict(strict=True, extra="forbid")

    tag: str
    attrs: Dict[str, str] = Field(default_factory=dict)
    text: str = ""
    children: List[DOMNode] = Field(default_factory=list)


class DOMDeltaItem(BaseModel):
    """Specific structural difference between two DOM states."""
    model_config = ConfigDict(strict=True, extra="forbid")

    change_type: str = Field(description="ADDED, REMOVED, ATTRIBUTE_MISMATCH, TEXT_MISMATCH")
    path: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    details: str = ""


class DOMEvaluationReport(BaseModel):
    """Forensic report emitted by the L3 DOM Oracle."""
    model_config = ConfigDict(strict=True, extra="forbid")

    verdict: str = Field(description="PASS or FAIL")
    total_expected_nodes: int = Field(ge=0)
    total_actual_nodes: int = Field(ge=0)
    discrepancy_count: int = Field(ge=0)
    deltas: List[DOMDeltaItem] = Field(default_factory=list)
    summary_message: str


class _DOMBuilderParser(HTMLParser):
    """Internal lightweight HTML parser constructing DOMNode tree."""

    def __init__(self):
        super().__init__()
        self.root: DOMNode = DOMNode(tag="__root__")
        self.stack: List[DOMNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attr_dict = {k: (v if v is not None else "") for k, v in attrs}
        node = DOMNode(tag=tag.lower(), attrs=attr_dict)
        if self.stack:
            self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag: str):
        if len(self.stack) > 1:
            for i in range(len(self.stack) - 1, 0, -1):
                if self.stack[i].tag == tag.lower():
                    self.stack = self.stack[:i]
                    break

    def handle_data(self, data: str):
        cleaned = data.strip()
        if cleaned and self.stack:
            curr = self.stack[-1]
            curr.text = f"{curr.text} {cleaned}".strip() if curr.text else cleaned


class DOMOracleEvaluator:
    """Deterministic DOM delta evaluator for UI/Web verification."""

    def __init__(self, ignored_attrs: Optional[List[str]] = None):
        reconfigure_streams()
        self.ignored_attrs = set(ignored_attrs or ["data-v-inspect", "tabindex"])

    def parse_html(self, html_content: str) -> DOMNode:
        """Parses HTML string into root DOMNode tree."""
        parser = _DOMBuilderParser()
        parser.feed(html_content)
        return parser.root

    def count_nodes(self, node: DOMNode) -> int:
        """Recursively count nodes in tree."""
        count = 1 if node.tag != "__root__" else 0
        for child in node.children:
            count += self.count_nodes(child)
        return count

    def evaluate_deltas(
        self, expected_html: str, actual_html: str, path_prefix: str = "root"
    ) -> DOMEvaluationReport:
        """Performs full structural delta evaluation."""
        exp_root = self.parse_html(expected_html)
        act_root = self.parse_html(actual_html)

        exp_count = self.count_nodes(exp_root)
        act_count = self.count_nodes(act_root)

        deltas: List[DOMDeltaItem] = []
        self._compare_nodes(exp_root, act_root, path_prefix, deltas)

        verdict = "PASS" if not deltas else "FAIL"
        summary = (
            f"DOM verification {verdict}: {len(deltas)} discrepancy items found "
            f"(Expected {exp_count} nodes, Actual {act_count} nodes)."
        )

        return DOMEvaluationReport(
            verdict=verdict,
            total_expected_nodes=exp_count,
            total_actual_nodes=act_count,
            discrepancy_count=len(deltas),
            deltas=deltas,
            summary_message=summary,
        )

    def _compare_nodes(
        self, exp: DOMNode, act: DOMNode, path: str, deltas: List[DOMDeltaItem]
    ) -> None:
        if exp.tag != act.tag:
            deltas.append(
                DOMDeltaItem(
                    change_type="TAG_MISMATCH",
                    path=path,
                    expected=exp.tag,
                    actual=act.tag,
                    details=f"Expected tag <{exp.tag}> but found <{act.tag}>",
                )
            )
            return

        # Compare attributes
        exp_attrs = {k: v for k, v in exp.attrs.items() if k not in self.ignored_attrs}
        act_attrs = {k: v for k, v in act.attrs.items() if k not in self.ignored_attrs}

        all_keys = set(exp_attrs.keys()) | set(act_attrs.keys())
        for k in all_keys:
            v_exp = exp_attrs.get(k)
            v_act = act_attrs.get(k)
            if v_exp != v_act:
                deltas.append(
                    DOMDeltaItem(
                        change_type="ATTRIBUTE_MISMATCH",
                        path=f"{path}@{k}",
                        expected=v_exp,
                        actual=v_act,
                        details=f"Attribute '{k}' mismatch: expected '{v_exp}' != actual '{v_act}'",
                    )
                )

        # Compare text content if leaf node
        if not exp.children and not act.children:
            if exp.text.strip() != act.text.strip():
                deltas.append(
                    DOMDeltaItem(
                        change_type="TEXT_MISMATCH",
                        path=path,
                        expected=exp.text.strip(),
                        actual=act.text.strip(),
                        details=f"Text mismatch at {path}",
                    )
                )

        # Compare children count and elements
        exp_len = len(exp.children)
        act_len = len(act.children)
        min_len = min(exp_len, act_len)

        for i in range(min_len):
            child_path = f"{path}/{exp.children[i].tag}[{i}]"
            self._compare_nodes(exp.children[i], act.children[i], child_path, deltas)

        if exp_len > act_len:
            for i in range(act_len, exp_len):
                missing = exp.children[i]
                deltas.append(
                    DOMDeltaItem(
                        change_type="REMOVED",
                        path=f"{path}/{missing.tag}[{i}]",
                        expected=f"<{missing.tag}>",
                        actual=None,
                        details=f"Expected child <{missing.tag}> missing at index {i}",
                    )
                )
        elif act_len > exp_len:
            for i in range(exp_len, act_len):
                extra = act.children[i]
                deltas.append(
                    DOMDeltaItem(
                        change_type="ADDED",
                        path=f"{path}/{extra.tag}[{i}]",
                        expected=None,
                        actual=f"<{extra.tag}>",
                        details=f"Unexpected extra child <{extra.tag}> found at index {i}",
                    )
                )


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(description="Nexus Keystone L3 DOM Reader & E2E Oracle Evaluator")
    parser.add_argument("--expected", type=str, help="Expected HTML string or path to HTML file")
    parser.add_argument("--actual", type=str, help="Actual HTML string or path to HTML file")
    parser.add_argument("--json", action="store_true", help="Output JSON report")

    args = parser.parse_args()
    if not args.expected or not args.actual:
        parser.print_help()
        return 2

    exp_text = Path(args.expected).read_text(encoding="utf-8") if Path(args.expected).exists() else args.expected
    act_text = Path(args.actual).read_text(encoding="utf-8") if Path(args.actual).exists() else args.actual

    evaluator = DOMOracleEvaluator()
    report = evaluator.evaluate_deltas(exp_text, act_text)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        status_sym = "🟢" if report.verdict == "PASS" else "🔴"
        print(f"{status_sym} [ORACLE-DOM-L3] Verdict: {report.verdict}")
        print(f"  {report.summary_message}")
        for delta in report.deltas:
            print(f"  - [{delta.change_type}] {delta.path}: {delta.details}")

    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
