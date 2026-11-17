# -*- coding: utf-8 -*-
"""Valutatore deterministico DOMOracleEvaluator e confronto SequenceMatcher."""

from __future__ import annotations

import difflib
import json
from typing import Any, Dict, List, Optional

from _internal.nk_common.paths import reconfigure_streams
from _internal.oracle_evaluator_l3.gate_validators import (
    _extract_markdown_expectations,
    resolve_expected_source,
    resolve_html_source,
    validate_structured_expectations_impl,
)
from _internal.oracle_evaluator_l3.models_and_dom import (
    DOMDeltaItem,
    DOMEvaluationReport,
    DOMNode,
    _DOMBuilderParser,
)


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

    def _validate_structured_expectations(
        self,
        spec: Dict[str, Any],
        act_root: DOMNode,
        path_prefix: str,
        deltas: List[DOMDeltaItem],
    ) -> int:
        """Valida vincoli strutturali JSON o Markdown contro l'albero DOM effettivo."""
        return validate_structured_expectations_impl(spec, act_root, path_prefix, deltas)

    def evaluate_deltas(
        self,
        expected_html: str,
        actual_html: str,
        path_prefix: str = "root",
        expected_kind: Optional[str] = None,
    ) -> DOMEvaluationReport:
        """Confronta la struttura attesa con il DOM HTML effettivo."""
        if expected_kind is None:
            exp_content, exp_kind = resolve_expected_source(expected_html)
        else:
            exp_content = expected_html
            exp_kind = expected_kind

        act_content = resolve_html_source(actual_html)
        act_root = self.parse_html(act_content)
        act_count = self.count_nodes(act_root)

        deltas: List[DOMDeltaItem] = []
        exp_count = 0

        if exp_kind == "json":
            try:
                spec_obj = json.loads(exp_content)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid expected JSON specification: {exc}") from exc
            if not isinstance(spec_obj, dict):
                raise ValueError("Expected JSON specification must be a JSON object.")
            html_payload = spec_obj.get("html") or spec_obj.get("expected_html")
            has_structured = any(
                k in spec_obj
                for k in (
                    "required_tags",
                    "required_ids",
                    "required_classes",
                    "required_texts",
                )
            )
            if isinstance(html_payload, str) and html_payload.strip():
                exp_root = self.parse_html(html_payload)
                exp_count += self.count_nodes(exp_root)
                self._compare_nodes(exp_root, act_root, path_prefix, deltas)
            if has_structured or not (isinstance(html_payload, str) and html_payload.strip()):
                exp_count += self._validate_structured_expectations(
                    spec_obj, act_root, path_prefix, deltas
                )
        elif exp_kind == "md":
            md_spec = _extract_markdown_expectations(exp_content)
            if md_spec["mode"] == "html":
                exp_root = self.parse_html(md_spec["html"])
                exp_count = self.count_nodes(exp_root)
                self._compare_nodes(exp_root, act_root, path_prefix, deltas)
            else:
                exp_count = self._validate_structured_expectations(
                    md_spec, act_root, path_prefix, deltas
                )
        else:
            exp_root = self.parse_html(exp_content)
            exp_count = self.count_nodes(exp_root)
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

        exp_attrs = {k: v for k, v in exp.attrs.items() if k not in self.ignored_attrs}
        act_attrs = {k: v for k, v in act.attrs.items() if k not in self.ignored_attrs}

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
                self._compare_nodes(exp.children[i], act.children[i], child_path, deltas)
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
                    self._compare_nodes(exp.children[idx_e], act.children[idx_a], child_path, deltas)
            elif tag_op == "replace":
                span_e = i2 - i1
                span_a = j2 - j1
                common = min(span_e, span_a)
                for offset in range(common):
                    idx_e = i1 + offset
                    idx_a = j1 + offset
                    child_path = f"{path}/{exp.children[idx_e].tag}[{idx_e}]"
                    self._compare_nodes(exp.children[idx_e], act.children[idx_a], child_path, deltas)
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
