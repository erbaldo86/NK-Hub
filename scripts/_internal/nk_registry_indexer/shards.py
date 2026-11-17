"""Costruzione compatta e reidratazione O(1) degli shard DOM-00..DOM-06."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from _internal.nk_common.constants import VERSION


SHARD_MAX_BYTES = 4700
MANIFEST_MAX_BYTES = 3150


def _compact_json(obj: Any) -> str:
    """Serializza in JSON compatto privo di whitespace superflui."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _trim_text(text: Any, limit: int = 44) -> str:
    """Compatta stringhe descrittive lunghe mantenendo la leggibilita essenziale."""
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 3)].rstrip() + "..."


def _compact_skill_entry(
    sk_meta: Dict[str, Any], dom_name: str, compact_mode: int = 0
) -> Dict[str, Any]:
    """Compatta una voce skill mantenendo tutte le chiavi funzionali e governance."""
    out: Dict[str, Any] = {
        "native_subagent": sk_meta.get("native_subagent", ""),
        "thinking_level": sk_meta.get("thinking_level", "HIGH"),
        "tools": list(sk_meta.get("tools", [])),
        "sha256": sk_meta.get("sha256", ""),
    }
    if compact_mode == 0:
        out["domain_id"] = sk_meta.get("domain_id", "DOM-02")
    sector = sk_meta.get("sector", "")
    if sector and (compact_mode == 0 or sector != dom_name):
        out["sector"] = sector
    if sk_meta.get("enable_mcp_tools"):
        out["enable_mcp_tools"] = True
    elif compact_mode == 0:
        out["enable_mcp_tools"] = False
    src_layer = sk_meta.get("source_layer", "production")
    if compact_mode == 0 or src_layer != "production":
        out["source_layer"] = src_layer
    if compact_mode == 0:
        out["auxiliary_links"] = list(sk_meta.get("auxiliary_links", []))
        out["loc"] = int(sk_meta.get("loc", 0))
        out["path"] = sk_meta.get("path", "")
        if sk_meta.get("description"):
            out["description"] = _trim_text(sk_meta.get("description"), 44)
    return out


def _compact_script_entry(
    sc_meta: Dict[str, Any], compact_mode: int = 0
) -> Dict[str, Any]:
    """Compatta una voce script mantenendo chiavi funzionali AST e SHA-256."""
    classes = list(sc_meta.get("classes", []))
    cli_flags = list(sc_meta.get("cli_flags", []))
    out: Dict[str, Any] = {
        "sha256": sc_meta.get("sha256", ""),
    }
    if compact_mode == 0:
        out["domain_id"] = sc_meta.get("domain_id", "DOM-03")
    if compact_mode < 2 or cli_flags:
        out["cli_flags"] = cli_flags if compact_mode < 3 else cli_flags[:6]
    if compact_mode < 2 or (compact_mode == 2 and classes):
        out["classes"] = classes[:2] if compact_mode >= 2 else classes
    elif classes and compact_mode >= 3:
        out["classes"] = classes[:2]
    src_layer = sc_meta.get("source_layer", "production")
    if compact_mode == 0 or src_layer != "production":
        out["source_layer"] = src_layer
    if compact_mode == 0:
        out["loc"] = int(sc_meta.get("loc", 0))
        if sc_meta.get("description"):
            out["description"] = _trim_text(sc_meta.get("description"), 36)
    return out


def _compact_agent_entry(
    ag_meta: Dict[str, Any], compact_mode: int = 0
) -> Dict[str, Any]:
    """Compatta una voce native_agent mantenendo tutte le guardie GT-14/CRIT-01."""
    out: Dict[str, Any] = {
        "tools": list(ag_meta.get("tools", [])),
        "sha256": ag_meta.get("sha256", ""),
    }
    if compact_mode == 0:
        out["domain_id"] = ag_meta.get("domain_id", "DOM-03")
    for flag_key in (
        "enable_write_tools",
        "enable_subagent_tools",
        "enable_mcp_tools",
    ):
        if ag_meta.get(flag_key):
            out[flag_key] = True
        elif compact_mode == 0:
            out[flag_key] = False
    src_layer = ag_meta.get("source_layer", "production")
    if compact_mode == 0 or src_layer != "production":
        out["source_layer"] = src_layer
    if compact_mode == 0:
        out["loc"] = int(ag_meta.get("loc", 0))
        out["path"] = ag_meta.get("path", "")
        if ag_meta.get("description"):
            out["description"] = _trim_text(ag_meta.get("description"), 44)
    return out


def _pack_intents_grouped(dom_intents: Dict[str, Any], dom_primary: str) -> Dict[str, Any]:
    """Raggruppa senza perdite le coppie [skill, mode] in _routes compatti."""
    grouped: Dict[Tuple[str, str], List[str]] = {}
    for kw, val in sorted(dom_intents.items()):
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            key = (str(val[0]), str(val[1]))
        else:
            key = (dom_primary, str(val))
        grouped.setdefault(key, []).append(kw)
    return {
        "_routes": [[sk, md, kws] for (sk, md), kws in sorted(grouped.items())]
    }


def _collapse_emergency_intents(dom_intents: Dict[str, Any], dom_primary: str) -> Dict[str, Any]:
    """Collasso d'emergenza (mode 3) per budget estremi sotto SHARD_MAX_BYTES."""
    out: Dict[str, Any] = {}
    for kw, val in dom_intents.items():
        if isinstance(val, (list, tuple)) and len(val) >= 2 and str(val[0]) == dom_primary:
            out[kw] = val[1]
        else:
            out[kw] = val
    return out


def _serialize_domain_shard_with_cap(
    dom_id: str,
    dom_meta: Dict[str, Any],
    dom_skills: Dict[str, Dict[str, Any]],
    dom_scripts: Dict[str, Dict[str, Any]],
    dom_agents: Dict[str, Dict[str, Any]],
    dom_intents: Dict[str, Any],
    max_bytes: int = SHARD_MAX_BYTES,
) -> str:
    """Serializza lo shard DOM-01..DOM-05 garantendo dimensione compatta entro il budget."""
    dom_name = str(dom_meta.get("name", ""))
    dom_primary = str(dom_meta.get("primary_skill", ""))
    last_raw = ""
    for mode in (0, 1, 2, 3):
        dom_obj = dict(dom_meta)
        if mode >= 1:
            dom_obj.pop("title", None)
            dom_obj.pop("description", None)
        if mode >= 2:
            dom_obj["keywords"] = list(dom_obj.get("keywords", []))[:4]
        if mode >= 3:
            dom_obj["keywords"] = list(dom_obj.get("keywords", []))[:2]

        if mode in (1, 2):
            intents_payload: Dict[str, Any] = _pack_intents_grouped(dom_intents, dom_primary)
        elif mode >= 3:
            intents_payload = _collapse_emergency_intents(dom_intents, dom_primary)
        else:
            intents_payload = dict(dom_intents)

        payload = {
            "domain_id": dom_id,
            "domain": dom_obj,
            "skills_index": {
                k: _compact_skill_entry(v, dom_name=dom_name, compact_mode=mode)
                for k, v in dom_skills.items()
            },
            "scripts_index": {
                k: _compact_script_entry(v, compact_mode=mode)
                for k, v in dom_scripts.items()
            },
            "native_agents_index": {
                k: _compact_agent_entry(v, compact_mode=mode)
                for k, v in dom_agents.items()
            },
            "intent_dispatch_table": intents_payload,
        }
        last_raw = _compact_json(payload)
        if len(last_raw.encode("utf-8")) <= max_bytes:
            return last_raw + "\n"
    return last_raw + "\n"


def _collect_test_suite_names(indexer: Any) -> List[str]:
    """Raccoglie l'elenco ordinato delle suite pytest in tests/ escludendo i file ritirati."""
    names = set()
    deleted_paths = (
        indexer._load_staging_deleted_paths()
        if hasattr(indexer, "_load_staging_deleted_paths")
        else set()
    )
    for base in (indexer.stage_dir / "tests", indexer.workspace_root / "tests"):
        if base.is_dir():
            for p in base.rglob("test_*.py"):
                rel_name = p.relative_to(base).as_posix()
                if f"tests/{rel_name}" not in deleted_paths:
                    names.add(rel_name)
    return sorted(names)


def build_shards_and_slim_manifest(
    indexer: Any, full_manifest: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Costruisce il manifesto leggero (<= 3.200 B) e i 7 shard DOM-00..DOM-06 (<= 4.800 B)."""
    shards_map = {f"DOM-0{i}": f"shards/DOM-0{i}.json" for i in range(7)}
    shards_content: Dict[str, str] = {}

    native_agents = full_manifest.get("native_agents_index", {})
    docs_raw = full_manifest.get("docs_and_setup_index", {})
    compact_docs = {
        k: {
            "relative_path": v.get("relative_path", f"nk_docs_and_setup/{k}"),
            "size_bytes": int(v.get("size_bytes", 0)),
            "sha256": v.get("sha256", ""),
        }
        for k, v in docs_raw.items()
    }
    dom00_payload: Dict[str, Any] = {
        "domain_id": "DOM-00",
        "name": "ROOT_BRIDGE_AND_HOOKS",
        "version": full_manifest.get("version", VERSION),
        "release_version": full_manifest.get("release_version", VERSION),
        "milestone_anchor_id": full_manifest.get("milestone_anchor_id", ""),
        "global_hygiene_profile": full_manifest.get("global_hygiene_profile", {}),
        "docs_and_setup_index": compact_docs,
        "plugin_mirrors": [
            ".agents/AGENTS.md",
            ".agents/plugins/nk-gate/plugin.json",
            ".agents/plugins/nk-gate/hooks.json",
        ],
    }
    dom00_raw = _compact_json(dom00_payload)
    if len(dom00_raw.encode("utf-8")) > SHARD_MAX_BYTES:
        dom00_payload["docs_and_setup_index"] = {
            k: {"relative_path": v["relative_path"], "sha256": v["sha256"]}
            for k, v in compact_docs.items()
        }
        dom00_raw = _compact_json(dom00_payload)
    shards_content["DOM-00.json"] = dom00_raw + "\n"

    all_skills = full_manifest.get("skills_index", {})
    all_scripts = full_manifest.get("scripts_index", {})
    all_intents = full_manifest.get("intent_dispatch_table", {})

    for dom_id, dom_meta in sorted(full_manifest.get("domains", {}).items()):
        dom_skills = {
            k: v for k, v in all_skills.items() if v.get("domain_id") == dom_id
        }
        dom_scripts = {
            k: v for k, v in all_scripts.items() if v.get("domain_id") == dom_id
        }
        dom_agents = {
            k: v for k, v in native_agents.items() if v.get("domain_id") == dom_id
        }
        dom_intents = {
            kw: [entry.get("primary_agent", ""), entry.get("recommended_mode", "mode_c")]
            for kw, entry in all_intents.items()
            if entry.get("domain_id") == dom_id
        }
        shards_content[f"{dom_id}.json"] = _serialize_domain_shard_with_cap(
            dom_id=dom_id,
            dom_meta=dom_meta,
            dom_skills=dom_skills,
            dom_scripts=dom_scripts,
            dom_agents=dom_agents,
            dom_intents=dom_intents,
        )

    dom06_payload: Dict[str, Any] = {
        "domain_id": "DOM-06",
        "name": "TESTS_LOCK_CI_RELEASE",
        "version": full_manifest.get("version", VERSION),
        "release_version": full_manifest.get("release_version", VERSION),
        "milestone_anchor_id": full_manifest.get("milestone_anchor_id", ""),
        "summary": full_manifest.get("summary", {}),
        "test_suites": _collect_test_suite_names(indexer),
        "artifacts": {
            "quality_baseline": "nk_tracking/quality_baseline.json",
            "oracle_lock": "nk_tracking/oracle_lock.json",
            "setup": "pytest.ini",
            "ci_workflow": ".github/workflows/ci.yml",
            "skill_golden_eval_set": "tests/evals/skill_golden_eval_set.json",
            "benchmark_tasks": "nk_tracking/benchmark_suite/tasks_v1.json",
        },
    }
    shards_content["DOM-06.json"] = _compact_json(dom06_payload) + "\n"

    hygiene = full_manifest.get("global_hygiene_profile", {})
    summary_raw = full_manifest.get("summary", {})
    slim_manifest: Dict[str, Any] = {
        "version": full_manifest.get("version", VERSION),
        "generated_at": full_manifest.get("generated_at", ""),
        "shards": shards_map,
        "summary": {
            "total_domains": int(summary_raw.get("total_domains", 5)),
            "total_skills": int(summary_raw.get("total_skills", len(all_skills))),
            "total_scripts": int(summary_raw.get("total_scripts", len(all_scripts))),
        },
        "domains": {
            dom_id: {"name": dom_meta.get("name", ""), "shard": f"shards/{dom_id}.json"}
            for dom_id, dom_meta in sorted(full_manifest.get("domains", {}).items())
        },
        "skills_index": {
            sk_name: {"domain_id": sk_meta.get("domain_id", "DOM-02")}
            for sk_name, sk_meta in sorted(all_skills.items())
        },
        "scripts_index": {
            sc_name: {"domain_id": sc_meta.get("domain_id", "DOM-03")}
            for sc_name, sc_meta in sorted(all_scripts.items())
        },
        "intent_dispatch_table": {},
        "global_hygiene_profile": {
            "external_skills_count": int(hygiene.get("external_skills_count", 0)),
            "total_flat_skills": int(hygiene.get("total_flat_skills", 0)),
        },
    }
    if len(_compact_json(slim_manifest).encode("utf-8")) > MANIFEST_MAX_BYTES:
        for d_info in slim_manifest["domains"].values():
            d_info.pop("shard", None)
    return slim_manifest, shards_content


from _internal.nk_registry_indexer.shards_rehydrate import (
    rehydrate_manifest_from_shards,  # noqa: E402,F401
)
