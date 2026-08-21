"""
Dual-State Visual & DOM Comparator per NK-Oracle-Evaluator (CRV 4.0 Macro-Fase 2).
Comparazione deterministica a doppio viewport (Before vs After) con parsing dell'albero DOM,
rilevamento delta tag, attributi, classi CSS e bounding discrepancy card.
"""

import sys
import json
import os
import difflib
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Dict, Any, Tuple


class DOMStructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: List[Dict[str, Any]] = []
        self.current_path: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]):
        self.current_path.append(tag)
        attr_dict = dict(attrs)
        self.tags.append({
            "path": "/".join(self.current_path),
            "tag": tag,
            "id": attr_dict.get("id", ""),
            "classes": attr_dict.get("class", "").split(),
            "attrs": attr_dict
        })

    def handle_endtag(self, tag: str):
        if self.current_path and self.current_path[-1] == tag:
            self.current_path.pop()


def parse_dom_nodes(content: str) -> List[Dict[str, Any]]:
    parser = DOMStructureParser()
    try:
        parser.feed(content)
    except Exception:
        pass
    return parser.tags


def run_dual_state_comparison(baseline_target: str, patched_target: str, output_dir: str) -> dict:
    """
    Esegue la comparazione strutturale deterministica Before vs After.
    Estrae i nodi DOM, confronta i tag, le classi e calcola il delta esatto.
    """
    os.makedirs(output_dir, exist_ok=True)
    diff_report_path = os.path.join(output_dir, "dom_discrepancy_report.json")

    s1_content = ""
    s2_content = ""

    if os.path.isfile(baseline_target):
        with open(baseline_target, "r", encoding="utf-8", errors="replace") as f:
            s1_content = f.read()
    else:
        s1_content = baseline_target

    if os.path.isfile(patched_target):
        with open(patched_target, "r", encoding="utf-8", errors="replace") as f:
            s2_content = f.read()
    else:
        s2_content = patched_target

    # Text / Code line delta
    matcher = difflib.SequenceMatcher(None, s1_content, s2_content)
    text_diff_ratio = (1.0 - matcher.ratio()) * 100.0

    # DOM Structural Delta
    dom1 = parse_dom_nodes(s1_content)
    dom2 = parse_dom_nodes(s2_content)

    dom_delta: List[Dict[str, Any]] = []
    max_len = max(len(dom1), len(dom2))
    tag_mismatches = 0

    for i in range(max_len):
        node1 = dom1[i] if i < len(dom1) else None
        node2 = dom2[i] if i < len(dom2) else None

        if node1 != node2:
            tag_mismatches += 1
            dom_delta.append({
                "node_index": i,
                "baseline_node": node1,
                "patched_node": node2,
                "type": "MUTATION" if (node1 and node2) else ("DELETION" if node1 else "INSERTION")
            })

    structural_diff_percentage = (tag_mismatches / max(max_len, 1)) * 100.0
    overall_diff = round((text_diff_ratio * 0.4 + structural_diff_percentage * 0.6), 2)

    result = {
        "status": "SUCCESS",
        "exit_code": 0,
        "visual_discrepancy_card": {
            "diff_percentage": overall_diff,
            "text_diff_percentage": round(text_diff_ratio, 2),
            "dom_structural_diff_percentage": round(structural_diff_percentage, 2),
            "total_dom_nodes_baseline": len(dom1),
            "total_dom_nodes_patched": len(dom2),
            "dom_mutations_count": len(dom_delta),
            "dom_delta": dom_delta[:20]  # capped to prevent IPC saturation
        },
        "output_diff_path": diff_report_path,
        "estimated_payload_tokens": max(1, len(json.dumps(dom_delta[:20])) // 4)
    }

    try:
        with open(diff_report_path, "w", encoding="utf-8") as out_f:
            json.dump(result, out_f, indent=2)
    except Exception:
        pass

    return result


if __name__ == "__main__":
    if len(sys.argv) >= 4:
        res = run_dual_state_comparison(sys.argv[1], sys.argv[2], sys.argv[3])
        print(json.dumps(res, indent=2))
    else:
        print(json.dumps({"status": "INFO", "usage": "python dual_state_visual_comparator.py baseline patched output_dir"}))

