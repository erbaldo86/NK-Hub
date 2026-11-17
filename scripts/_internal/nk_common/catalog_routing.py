"""Helper stdlib di routing dinamico da frontmatter SKILL.md e catalogo SSOT."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from _internal.nk_common.catalog_loader import _resolve_base_root, load_registry_manifest

_SECTOR_BY_DOMAIN: Dict[str, str] = {
    "DOM-01": "GOV_AND_ROUTING",
    "DOM-02": "IDEATION_AND_ARCH",
    "DOM-03": "BUILD_AND_HEAL",
    "DOM-04": "AUDIT_DAST_AND_RCA",
    "DOM-05": "MEMORY_TELEMETRY_AND_DOCS",
}

_FM_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def _parse_frontmatter_scalar(raw_val: str) -> Any:
    """Converte uno scalare o lista JSON inline dal frontmatter YAML senza dipendenze esterne."""
    s = raw_val.strip()
    if not s:
        return ""
    if s.startswith("[") or s.startswith("{") or s.startswith('"'):
        try:
            return json.loads(s)
        except Exception:
            pass
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(s)
    except ValueError:
        return s


def _read_skill_frontmatter_cached(md_path: Path) -> Dict[str, Any]:
    """Legge e mette in cache il frontmatter YAML di un file SKILL.md."""
    try:
        st = md_path.stat()
    except OSError:
        return {}
    key = str(md_path)
    cached = _FM_CACHE.get(key)
    if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return dict(cached[2])
    try:
        text = md_path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: Dict[str, Any] = {}
    cur_list_key: Optional[str] = None
    for raw_line in parts[1].splitlines():
        s = raw_line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- ") and cur_list_key is not None:
            lst = meta.setdefault(cur_list_key, [])
            if isinstance(lst, list):
                lst.append(_parse_frontmatter_scalar(s[2:]))
            continue
        if ":" in raw_line:
            k, v = raw_line.split(":", 1)
            k_clean = k.strip()
            v_clean = v.strip()
            if not v_clean:
                meta[k_clean] = []
                cur_list_key = k_clean
            else:
                meta[k_clean] = _parse_frontmatter_scalar(v_clean)
                cur_list_key = None
    _FM_CACHE[key] = (st.st_mtime_ns, st.st_size, meta)
    return dict(meta)


def _iter_overlay_skill_frontmatters(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Raccoglie i frontmatter delle skill privilegiando .staging/.agents/skills/."""
    base_root = _resolve_base_root(workspace_root)
    skills: Dict[str, Dict[str, Any]] = {}
    for base in (
        base_root / ".staging" / ".agents" / "skills",
        base_root / ".agents" / "skills",
    ):
        if not base.is_dir():
            continue
        for md_path in sorted(base.glob("*/SKILL.md")):
            sk_name = md_path.parent.name
            if sk_name in skills:
                continue
            fm = _read_skill_frontmatter_cached(md_path)
            if fm:
                skills[sk_name] = fm
    return skills


def get_skill_routing_rules(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[Tuple[str, str, str, str, Tuple[str, ...]], ...]:
    """Costruisce SKILL_ROUTING_RULES dinamicamente da manifest/shard e frontmatter SKILL.md."""
    base_root = _resolve_base_root(workspace_root)
    manifest = load_registry_manifest(base_root, rehydrate=True)
    fm_map = _iter_overlay_skill_frontmatters(base_root)
    skills_idx = manifest.get("skills_index") if isinstance(manifest.get("skills_index"), dict) else {}

    all_names = list(dict.fromkeys(list(fm_map.keys()) + list(skills_idx.keys())))
    rules: list[Tuple[str, str, str, str, Tuple[str, ...]]] = []
    for sk_name in all_names:
        fm = fm_map.get(sk_name, {})
        idx_meta = skills_idx.get(sk_name, {}) if isinstance(skills_idx.get(sk_name), dict) else {}
        node_val = str(fm.get("dashboard_node") or idx_meta.get("dashboard_node") or "")
        if node_val == "Hub":
            continue
        dom_id = str(fm.get("domain_id") or idx_meta.get("domain_id") or "DOM-03")
        sector = str(fm.get("sector") or idx_meta.get("sector") or _SECTOR_BY_DOMAIN.get(dom_id, "BUILD_AND_HEAL"))
        subagent = str(fm.get("native_subagent") or idx_meta.get("native_subagent") or "")
        pkws = fm.get("priority_keywords") or idx_meta.get("priority_keywords") or []
        rkws = fm.get("routing_keywords") or idx_meta.get("routing_keywords") or []
        merged_kws = tuple(dict.fromkeys(
            str(k).strip().lower() for k in ([*pkws, *rkws]) if str(k).strip()
        ))
        if merged_kws and subagent:
            rules.append((sk_name, dom_id, sector, subagent, merged_kws))
    return tuple(rules)


def get_dashboard_node_map(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Dict[int, Tuple[str, str, str, str, bool]]:
    """Costruisce DASHBOARD_NODE_MAP dinamicamente dai frontmatter SKILL.md e dal manifesto."""
    base_root = _resolve_base_root(workspace_root)
    manifest = load_registry_manifest(base_root, rehydrate=True)
    fm_map = _iter_overlay_skill_frontmatters(base_root)
    skills_idx = manifest.get("skills_index") if isinstance(manifest.get("skills_index"), dict) else {}

    node_map: Dict[int, Tuple[str, str, str, str, bool]] = {}
    for sk_name in sorted(set(fm_map) | set(skills_idx)):
        fm = fm_map.get(sk_name, {})
        idx_meta = skills_idx.get(sk_name, {}) if isinstance(skills_idx.get(sk_name), dict) else {}
        raw_node = fm.get("dashboard_node", idx_meta.get("dashboard_node"))
        if raw_node is None or str(raw_node) == "Hub":
            continue
        try:
            node_idx = int(str(raw_node))
        except ValueError:
            continue
        dom_id = str(fm.get("domain_id") or idx_meta.get("domain_id") or "DOM-03")
        sector = str(fm.get("sector") or idx_meta.get("sector") or _SECTOR_BY_DOMAIN.get(dom_id, "BUILD_AND_HEAL"))
        subagent = str(fm.get("native_subagent") or idx_meta.get("native_subagent") or "")
        ro = bool(fm.get("read_only", idx_meta.get("read_only", False)))
        node_map[node_idx] = (sk_name, dom_id, sector, subagent, ro)
    return dict(sorted(node_map.items()))


def get_skill_mode_map(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Dict[str, str]:
    """Restituisce {skill_name: recommended_mode} da default_mode/read_only dei frontmatter SKILL.md."""
    base_root = _resolve_base_root(workspace_root)
    fm_map = _iter_overlay_skill_frontmatters(base_root)
    modes: Dict[str, str] = {}
    for sk_name, fm in fm_map.items():
        if bool(fm.get("read_only", False)):
            modes[sk_name] = "mode_d"
            continue
        raw_mode = str(fm.get("default_mode", "") or "").strip().lower()
        if raw_mode in ("mode_a", "mode_b", "mode_c", "mode_d"):
            modes[sk_name] = raw_mode
    return modes


def get_catalog_counts(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Dict[str, int]:
    """Restituisce i conteggi dinamici di skill, sub-agenti e nodi dashboard dal catalogo SSOT."""
    base_root = _resolve_base_root(workspace_root)
    manifest = load_registry_manifest(base_root, rehydrate=True)
    fm_map = _iter_overlay_skill_frontmatters(base_root)
    skills_n = len(fm_map) if fm_map else len(manifest.get("skills_index", {}))
    agents_n = len(manifest.get("native_agents_index", {}))
    if agents_n == 0:
        for base in (base_root / ".staging" / ".agents" / "agents", base_root / ".agents" / "agents"):
            if base.is_dir():
                agents_n = len(list(base.glob("*/agent.md")))
                if agents_n:
                    break
    nodes_n = len(get_dashboard_node_map(base_root))
    if workspace_root is not None and skills_n == 0 and agents_n == 0:
        hub_root = _resolve_base_root(None)
        if hub_root != base_root:
            return get_catalog_counts(workspace_root=None)
    return {"skills": skills_n, "agents": agents_n, "dashboard_nodes": nodes_n}


def validate_catalog_contracts(
    records: list[Dict[str, Any]], model_cls: Any = None
) -> Dict[str, Any]:
    """Valida opzionalmente i record frontmatter contro un modello Pydantic compile-time."""
    if model_cls is None:
        return {"passed": True, "errors": [], "validated": len(records)}
    errors: list[str] = []
    for idx, rec in enumerate(records):
        try:
            model_cls.model_validate(rec)
        except Exception as exc:
            errors.append(f"record[{idx}]: {exc}")
    return {"passed": not errors, "errors": errors, "validated": len(records)}
