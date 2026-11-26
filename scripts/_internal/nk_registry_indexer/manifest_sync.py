"""Sincronizzazione atomica di nk_registry_manifest.json, SKILL_INDEX.md e plugin mirrors."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.io import atomic_write_bytes, atomic_write_json, atomic_write_text
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex
from _internal.nk_common.win32_mutex import (  # noqa: F401
    create_or_open_named_mutex,
    release_win32_mutex,
)
from _internal.nk_registry_indexer.scripts_and_agents import collect_internal_integrity_index
from _internal.nk_registry_indexer.shards import (
    build_shards_and_slim_manifest,
    rehydrate_manifest_from_shards,
)
from _internal.nk_registry_indexer.taxonomy import _DEFAULT_WORKSPACE_ROOT


def _strip_yaml_frontmatter(raw_text: str) -> str:
    """Rimuove il blocco YAML frontmatter iniziale se presente."""
    if not raw_text.startswith("---"):
        return raw_text
    lines = raw_text.splitlines(keepends=True)
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "".join(lines[idx + 1 :]).lstrip("\r\n")
    return raw_text


def sync_nk_gate_plugin_mirrors_impl(
    self, write_to_staging: bool, root_genome: Path
) -> List[str]:
    """Sincronizza i mirror di agent.md e rules/AGENTS.md in .agents/plugins/nk-gate/."""
    synced_paths: List[str] = []
    if write_to_staging:
        target_layer_root: Optional[Path] = self.stage_dir
        source_roots: Tuple[Path, ...] = (self.stage_dir, self.workspace_root)
    elif self._is_within_dir(root_genome, self.workspace_root):
        target_layer_root = self.workspace_root
        source_roots = (self.workspace_root,)
    else:
        return synced_paths

    plugin_agents_dir = (
        target_layer_root / ".agents" / "plugins" / "nk-gate" / "agents"
    )
    plugin_rules_dir = (
        target_layer_root / ".agents" / "plugins" / "nk-gate" / "rules"
    )
    deleted_paths = self._load_staging_deleted_paths()

    plugin_agents_dir.mkdir(parents=True, exist_ok=True)
    seen_agents: Set[str] = set()
    for src_root in source_roots:
        agents_base = src_root / ".agents" / "agents"
        if not agents_base.is_dir():
            continue
        is_prod_src = src_root == self.workspace_root and src_root != self.stage_dir
        for ag_dir in sorted(agents_base.iterdir()):
            if not ag_dir.is_dir() or ag_dir.name in seen_agents:
                continue
            if is_prod_src and f".agents/agents/{ag_dir.name}/agent.md" in deleted_paths:
                continue
            src_ag = ag_dir / "agent.md"
            if not src_ag.is_file():
                continue
            seen_agents.add(ag_dir.name)
            dst_ag = plugin_agents_dir / f"{ag_dir.name}.md"
            src_bytes = src_ag.read_bytes()
            if not dst_ag.exists() or dst_ag.read_bytes() != src_bytes:
                atomic_write_bytes(dst_ag, src_bytes)
            synced_paths.append(str(dst_ag))

    plugin_rules_dir.mkdir(parents=True, exist_ok=True)
    for src_root in source_roots:
        src_rule = src_root / ".agents" / "rules" / "anti_crash_rules.md"
        if src_rule.is_file():
            dst_rule = plugin_rules_dir / "AGENTS.md"
            clean_rule = _strip_yaml_frontmatter(
                src_rule.read_text(encoding="utf-8", errors="replace")
            )
            if len(clean_rule.encode("utf-8")) >= 24000:
                raise ValueError("Mirror nk-gate rules/AGENTS.md supera 24000 byte.")
            if not dst_rule.exists() or dst_rule.read_text(encoding="utf-8", errors="replace") != clean_rule:
                atomic_write_text(dst_rule, clean_rule)
            synced_paths.append(str(dst_rule))
            break

    return synced_paths


def _write_genome_bundle_unlocked(
    genome_dir: Path,
    shards_payload: Dict[str, str],
    manifest_json: str,
    md_content: str,
    check_unchanged: bool = False,
) -> None:
    """Scrive shards, nk_registry_manifest.json e SKILL_INDEX.md assumendo mutex gia' acquisito."""
    genome_dir.mkdir(parents=True, exist_ok=True)
    shards_dir = genome_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    for s_name, s_json in shards_payload.items():
        s_path = shards_dir / s_name
        if not check_unchanged or not s_path.exists() or s_path.read_text(encoding="utf-8", errors="replace") != s_json:
            atomic_write_text(s_path, s_json)
    m_path = genome_dir / "nk_registry_manifest.json"
    if not check_unchanged or not m_path.exists() or m_path.read_text(encoding="utf-8", errors="replace") != manifest_json:
        atomic_write_text(m_path, manifest_json)
    sk_path = genome_dir / "SKILL_INDEX.md"
    if not check_unchanged or not sk_path.exists() or sk_path.read_text(encoding="utf-8", errors="replace") != md_content:
        atomic_write_text(sk_path, md_content)


def _sync_integrity_index_unlocked(self_obj: Any, write_to_staging: bool) -> bool:
    """Aggiorna internal_integrity_index.json sotto il mutex globale GenomeSync."""
    try:
        integrity_payload = collect_internal_integrity_index(
            self_obj.workspace_root,
            self_obj.stage_dir,
            self_obj._load_staging_deleted_paths(),
        )
        tgt_track = (
            (self_obj.stage_dir if write_to_staging else self_obj.workspace_root)
            / "nk_tracking"
            / "internal_integrity_index.json"
        )
        ok, _ = atomic_write_json(tgt_track, integrity_payload)
        return bool(ok)
    except (OSError, ValueError, TypeError, RuntimeError):
        return False


def sync_impl(
    self, sync_staging: bool = False, allow_ratchet_down: bool = False
) -> Dict[str, Any]:
    """Genera manifest, shard, 6/6 mirror e indice integrita sotto mutex fail-closed."""
    t0 = time.perf_counter()
    manifest = self.build_manifest()
    root_genome, is_legacy = self.resolve_genome_dir(self.workspace_root)
    root_manifest_path = root_genome / "nk_registry_manifest.json"

    default_prod_staging = (_DEFAULT_WORKSPACE_ROOT / ".staging").resolve()
    is_prod_staging = self.stage_dir.resolve() == default_prod_staging
    write_to_staging = bool(sync_staging) or (
        self._explicit_stage_dir and not is_prod_staging
    )

    target_manifest_path = (
        self.stage_dir / "nk_genome" / "nk_registry_manifest.json"
        if write_to_staging
        else root_manifest_path
    )
    check_candidates: List[Path] = [target_manifest_path]
    if sync_staging:
        prod_manifest_path = self.workspace_root / "nk_genome" / "nk_registry_manifest.json"
        if prod_manifest_path not in check_candidates:
            check_candidates.append(prod_manifest_path)

    prev_skills = 0
    prev_scripts = 0
    for cand_manifest in check_candidates:
        if cand_manifest.is_file():
            try:
                prev_data = json.loads(cand_manifest.read_text(encoding="utf-8"))
                if isinstance(prev_data, dict):
                    prev_skills = max(
                        prev_skills, len(prev_data.get("skills_index", {}))
                    )
                    prev_scripts = max(
                        prev_scripts, len(prev_data.get("scripts_index", {}))
                    )
            except Exception:
                pass

    new_skills = len(manifest.get("skills_index", {}))
    new_scripts = len(manifest.get("scripts_index", {}))
    if (new_skills < prev_skills or new_scripts < prev_scripts) and not allow_ratchet_down:
        return {
            "passed": False, "status": "RATCHET_BLOCKED", "error_code": "ERR_REGISTRY_RATCHET_DOWN",
            "prev_skills": prev_skills, "new_skills": new_skills,
            "prev_scripts": prev_scripts, "new_scripts": new_scripts,
            "sync_staging": bool(write_to_staging),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    slim_manifest, shards_payload = build_shards_and_slim_manifest(self, manifest)

    if root_manifest_path.exists():
        try:
            existing_data = json.loads(root_manifest_path.read_text(encoding="utf-8"))
            if isinstance(existing_data, dict):
                curr_cmp = {k: v for k, v in slim_manifest.items() if k != "generated_at"}
                exist_cmp = {k: v for k, v in existing_data.items() if k != "generated_at"}
                if curr_cmp == exist_cmp and "generated_at" in existing_data:
                    slim_manifest["generated_at"] = existing_data["generated_at"]
        except Exception:
            pass

    md_content = self.render_skill_index_markdown(manifest)
    manifest_json = json.dumps(slim_manifest, separators=(",", ":"), ensure_ascii=False) + "\n"

    primary_manifest_path = root_manifest_path
    primary_skill_index_path = root_genome / "SKILL_INDEX.md"
    m_hash = hashlib.sha256(str(root_genome.resolve()).lower().encode("utf-8")).hexdigest()[:16]

    with FailClosedNamedMutex(f"Global\\NK_GenomeSync_{m_hash}", wait_ms=5000):
        if write_to_staging:
            target_genome_dir = self.stage_dir / "nk_genome"
            _write_genome_bundle_unlocked(
                target_genome_dir, shards_payload, manifest_json, md_content, check_unchanged=False
            )
            primary_manifest_path = target_genome_dir / "nk_registry_manifest.json"
            primary_skill_index_path = target_genome_dir / "SKILL_INDEX.md"

        if self.workspace_root != _DEFAULT_WORKSPACE_ROOT or not write_to_staging:
            _write_genome_bundle_unlocked(
                root_genome, shards_payload, manifest_json, md_content, check_unchanged=True
            )

        self._sync_nk_gate_plugin_mirrors(
            write_to_staging=write_to_staging, root_genome=root_genome
        )
        _sync_integrity_index_unlocked(self, write_to_staging)

    type(self)._MANIFEST_CACHE.clear()
    self._last_verify_cache = None
    self._save_persistent_hash_cache()
    tetralogy_info = self.resolve_tetralogy_files(self.workspace_root)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "status": "SYNCED",
        "passed": True,
        "sync_staging": bool(write_to_staging),
        "manifest_path": str(primary_manifest_path),
        "skill_index_path": str(primary_skill_index_path),
        "shards_written": sorted(shards_payload.keys()),
        "genome_dir": str(root_genome),
        "is_legacy_genome": is_legacy,
        "legacy_warning": tetralogy_info["warning"],
        "summary": manifest["summary"],
        "global_hygiene_profile": manifest["global_hygiene_profile"],
        "elapsed_ms": elapsed_ms,
    }


def load_manifest_impl(self) -> Optional[Dict[str, Any]]:
    """Carica nk_registry_manifest.json e reidrata eventuali shard DOM-00..DOM-06."""
    candidates = (
        self.stage_dir / "nk_genome" / "nk_registry_manifest.json",
        self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
        self.workspace_root / "genome" / "nk_registry_manifest.json",
    )
    for cand in candidates:
        if cand.exists() and cand.is_file():
            try:
                st = cand.stat()
                ckey = (str(cand), st.st_mtime_ns, st.st_size)
                if ckey in type(self)._MANIFEST_CACHE:
                    return type(self)._MANIFEST_CACHE[ckey]
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "shards" in data:
                        data = rehydrate_manifest_from_shards(cand, data)
                    type(self)._MANIFEST_CACHE[ckey] = data
                    return data
            except Exception:
                pass
    return None
