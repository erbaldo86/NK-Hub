#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Valutatore DOM L3 e Oracolo E2E per Nexus Keystone v3.0.0-STE100-Unified.
Gestisce i void tag HTML5 senza sbilanciare lo stack e risolve i path Windows con rsplit.
"""

from __future__ import annotations

import argparse
import difflib
from html.parser import HTMLParser
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

_scripts_dir = Path(__file__).resolve().parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
for _d in (
    _scripts_dir,
    _root_dir / "scripts",
    _root_dir / ".staging" / "scripts",
    _root_dir,
):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    from scripts.platform_runner import reconfigure_streams

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


def resolve_html_source(source_or_path: str) -> str:
    """Risolve una stringa HTML o un percorso file Windows preservando la lettera di unita."""
    candidate = source_or_path.strip()
    if "<" not in candidate and ">" not in candidate:
        p_direct = Path(candidate)
        if p_direct.exists() and p_direct.is_file():
            return p_direct.read_text(encoding="utf-8")
        if ":" in candidate:
            parts = candidate.rsplit(":", 2)
            base_str = parts[0]
            if len(base_str) == 1 and len(parts) >= 2:
                base_str = f"{parts[0]}:{parts[1]}"
            p_base = Path(base_str)
            if p_base.exists() and p_base.is_file():
                return p_base.read_text(encoding="utf-8")
    return source_or_path


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
    """Parser HTML leggero che costruisce l'albero DOM ignorando i void tag nello stack."""

    def __init__(self) -> None:
        super().__init__()
        self.root: DOMNode = DOMNode(tag="__root__")
        self.stack: List[DOMNode] = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        tag_low = tag.lower()
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


class DOMOracleEvaluator:
    """Valutatore deterministico delle differenze DOM per la verifica UI."""

    def __init__(self, ignored_attrs: Optional[List[str]] = None) -> None:
        reconfigure_streams()
        self.ignored_attrs = set(ignored_attrs or ["data-v-inspect", "tabindex"])

    def parse_html(self, html_content: str) -> DOMNode:
        """Converte una stringa HTML nell'albero radice DOMNode."""
        parser = _DOMBuilderParser()
        parser.feed(html_content)
        return parser.root

    def count_nodes(self, node: DOMNode) -> int:
        """Conta ricorsivamente i nodi presenti nell'albero DOM."""
        count = 1 if node.tag != "__root__" else 0
        for child in node.children:
            count += self.count_nodes(child)
        return count

    def evaluate_deltas(
        self,
        expected_html: str,
        actual_html: str,
        path_prefix: str = "root",
    ) -> DOMEvaluationReport:
        """Confronta la struttura DOM attesa con quella effettiva."""
        exp_content = resolve_html_source(expected_html)
        act_content = resolve_html_source(actual_html)

        exp_root = self.parse_html(exp_content)
        act_root = self.parse_html(act_content)

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
        self,
        exp: DOMNode,
        act: DOMNode,
        path: str,
        deltas: List[DOMDeltaItem],
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

        exp_attrs = {
            k: v for k, v in exp.attrs.items() if k not in self.ignored_attrs
        }
        act_attrs = {
            k: v for k, v in act.attrs.items() if k not in self.ignored_attrs
        }

        all_keys = set(exp_attrs.keys()) | set(act_attrs.keys())
        for k in sorted(all_keys):
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

        exp_len = len(exp.children)
        act_len = len(act.children)

        def _node_sig(n: DOMNode) -> str:
            key = n.attrs.get("id") or n.attrs.get("data-key") or ""
            return f"{n.tag}#{key}" if key else n.tag

        exp_keys = [c.attrs.get("id") or c.attrs.get("data-key") for c in exp.children]
        act_keys = [c.attrs.get("id") or c.attrs.get("data-key") for c in act.children]

        if exp_len == act_len and exp_keys == act_keys:
            for i in range(exp_len):
                child_path = f"{path}/{exp.children[i].tag}[{i}]"
                self._compare_nodes(
                    exp.children[i], act.children[i], child_path, deltas
                )
            return

        exp_sigs = [_node_sig(c) for c in exp.children]
        act_sigs = [_node_sig(c) for c in act.children]
        matcher = difflib.SequenceMatcher(None, exp_sigs, act_sigs, autojunk=False)

        for tag_op, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag_op == "equal":
                for offset in range(i2 - i1):
                    idx_e = i1 + offset
                    idx_a = j1 + offset
                    child_path = f"{path}/{exp.children[idx_e].tag}[{idx_e}]"
                    self._compare_nodes(
                        exp.children[idx_e], act.children[idx_a], child_path, deltas
                    )
            elif tag_op == "replace":
                span_e = i2 - i1
                span_a = j2 - j1
                common = min(span_e, span_a)
                for offset in range(common):
                    idx_e = i1 + offset
                    idx_a = j1 + offset
                    child_path = f"{path}/{exp.children[idx_e].tag}[{idx_e}]"
                    self._compare_nodes(
                        exp.children[idx_e], act.children[idx_a], child_path, deltas
                    )
                if span_e > common:
                    for idx_e in range(i1 + common, i2):
                        missing = exp.children[idx_e]
                        deltas.append(
                            DOMDeltaItem(
                                change_type="REMOVED",
                                path=f"{path}/{missing.tag}[{idx_e}]",
                                expected=f"<{missing.tag}>",
                                actual=None,
                                details=f"Expected child <{missing.tag}> missing at index {idx_e}",
                            )
                        )
                elif span_a > common:
                    for idx_a in range(j1 + common, j2):
                        extra = act.children[idx_a]
                        deltas.append(
                            DOMDeltaItem(
                                change_type="ADDED",
                                path=f"{path}/{extra.tag}[{idx_a}]",
                                expected=None,
                                actual=f"<{extra.tag}>",
                                details=f"Unexpected extra child <{extra.tag}> found at index {idx_a}",
                            )
                        )
            elif tag_op == "delete":
                for idx_e in range(i1, i2):
                    missing = exp.children[idx_e]
                    deltas.append(
                        DOMDeltaItem(
                            change_type="REMOVED",
                            path=f"{path}/{missing.tag}[{idx_e}]",
                            expected=f"<{missing.tag}>",
                            actual=None,
                            details=f"Expected child <{missing.tag}> missing at index {idx_e}",
                        )
                    )
            elif tag_op == "insert":
                for idx_a in range(j1, j2):
                    extra = act.children[idx_a]
                    deltas.append(
                        DOMDeltaItem(
                            change_type="ADDED",
                            path=f"{path}/{extra.tag}[{idx_a}]",
                            expected=None,
                            actual=f"<{extra.tag}>",
                            details=f"Unexpected extra child <{extra.tag}> found at index {idx_a}",
                        )
                    )


def main() -> int:
    """Punto di ingresso CLI per il valutatore DOM L3."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone L3 DOM Reader & E2E Oracle Evaluator"
    )
    parser.add_argument(
        "--expected",
        type=str,
        help="Stringa HTML attesa o percorso al file HTML",
    )
    parser.add_argument(
        "--actual",
        type=str,
        help="Stringa HTML effettiva o percorso al file HTML",
    )
    parser.add_argument("--json", action="store_true", help="Stampa rapporto JSON")

    args = parser.parse_args()
    if not args.expected or not args.actual:
        parser.print_help()
        return 2

    exp_text = resolve_html_source(args.expected)
    act_text = resolve_html_source(args.actual)

    evaluator = DOMOracleEvaluator()
    report = evaluator.evaluate_deltas(exp_text, act_text)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"[ORACLE-DOM-L3] Verdict: {report.verdict}")
        print(f"  {report.summary_message}")
        for delta in report.deltas:
            print(f"  - [{delta.change_type}] {delta.path}: {delta.details}")

    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
