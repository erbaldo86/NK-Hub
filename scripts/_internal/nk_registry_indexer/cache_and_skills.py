"""Cache persistente Fast-Stat, SHA-256 e scansione skill di NKRegistryIndexer."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.io import atomic_write_text
from _internal.nk_registry_indexer.skills_scan import (
    collect_priority_skills_impl,  # noqa: F401
    load_staging_deleted_paths_impl,  # noqa: F401
    parse_skill_metadata_impl,  # noqa: F401
    resolve_skill_native_subagent_impl,  # noqa: F401
)
from _internal.nk_registry_indexer.taxonomy import (
    DOMAIN_TAXONOMY,
    TETRALOGY_FILENAMES,
)


def get_persistent_cache_file_impl(cls) -> Path:
    """Restituisce il percorso del file di cache persistente Fast-Stat in %TEMP%."""
    tmp_base = Path(os.environ.get("TEMP", tempfile.gettempdir()))
    return tmp_base / "nk_diagnostics" / "registry_fast_stat_cache.json"


def get_persistent_meta_cache_file_impl(cls) -> Path:
    """Restituisce il percorso del file di cache persistente metadati AST in %TEMP%."""
    tmp_base = Path(os.environ.get("TEMP", tempfile.gettempdir()))
    return tmp_base / "nk_diagnostics" / "registry_meta_fast_stat_cache.json"


def load_persistent_hash_cache_impl(cls) -> None:
    """Carica la cache SHA-256 e metadati AST persistente da %TEMP% per azzerare le letture su Google Drive."""
    if cls._PERSISTENT_CACHE_LOADED:
        return
    cls._PERSISTENT_CACHE_LOADED = True
    cfile = cls._get_persistent_cache_file()
    if cfile.is_file():
        try:
            raw = json.loads(cfile.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k_str, sha_val in raw.items():
                    parts = k_str.split("|")
                    if len(parts) == 3 and isinstance(sha_val, str):
                        cls._HASH_CACHE[(parts[0], int(parts[1]), int(parts[2]))] = sha_val
        except Exception:
            pass
    mfile = cls._get_persistent_meta_cache_file()
    if mfile.is_file():
        try:
            raw_m = json.loads(mfile.read_text(encoding="utf-8"))
            if isinstance(raw_m, dict):
                for k_str, meta_val in raw_m.items():
                    parts = k_str.split("|")
                    if len(parts) == 3 and isinstance(meta_val, dict):
                        cls._META_CACHE[(parts[0], int(parts[1]), int(parts[2]))] = meta_val
        except Exception:
            pass


def save_persistent_hash_cache_impl(cls) -> None:
    """Salva atomicamente la cache SHA-256 e metadati AST Fast-Stat in %TEMP%/nk_diagnostics."""
    cfile = cls._get_persistent_cache_file()
    try:
        serializable: Dict[str, str] = {}
        items = list(cls._HASH_CACHE.items())[-600:]
        for (p_str, mtime_ns, sz), sha_val in items:
            serializable[f"{p_str}|{mtime_ns}|{sz}"] = sha_val
        atomic_write_text(cfile, json.dumps(serializable), fsync_data=False)
    except Exception:
        pass
    mfile = cls._get_persistent_meta_cache_file()
    try:
        serializable_m: Dict[str, Dict[str, Any]] = {}
        m_items = list(cls._META_CACHE.items())[-300:]
        for (p_str, mtime_ns, sz), meta_val in m_items:
            serializable_m[f"{p_str}|{mtime_ns}|{sz}"] = meta_val
        atomic_write_text(mfile, json.dumps(serializable_m), fsync_data=False)
    except Exception:
        pass


def resolve_genome_dir_impl(
    self, root: Optional[Path] = None
) -> Tuple[Path, bool]:
    """Risolve la cartella genome preferendo nk_genome/ rispetto al fallback legacy genome/."""
    base = Path(root).resolve() if root is not None else self.workspace_root
    preferred = base / "nk_genome"
    legacy = base / "genome"
    if preferred.exists() and preferred.is_dir():
        return preferred, False
    if legacy.exists() and legacy.is_dir():
        return legacy, True
    return preferred, False


def resolve_tetralogy_files_impl(
    self, root: Optional[Path] = None
) -> Dict[str, Any]:
    """Risolve i documenti della Pentad supportando nk_genome/ e genome/ legacy."""
    base = Path(root).resolve() if root is not None else self.workspace_root
    genome_dir, is_legacy = self.resolve_genome_dir(base)
    files_map: Dict[str, Optional[str]] = {}
    missing: List[str] = []
    for fname in TETRALOGY_FILENAMES:
        cand_pref = base / "nk_genome" / fname
        cand_leg = base / "genome" / fname
        if cand_pref.exists():
            files_map[fname] = str(cand_pref)
        elif cand_leg.exists():
            files_map[fname] = str(cand_leg)
            is_legacy = True
        else:
            files_map[fname] = None
            missing.append(fname)
    warning_msg = (
        f"Rilevata cartella legacy genome/ in '{base}'; migra verso nk_genome/."
        if is_legacy
        else None
    )
    return {
        "genome_dir": str(genome_dir),
        "is_legacy_genome": is_legacy,
        "warning": warning_msg,
        "files": files_map,
        "missing_files": missing,
    }


def compute_sha256_impl(file_path: Path, hash_cache: Optional[Dict[Tuple[str, int, int], str]] = None) -> str:
    """Calcola l'hash crittografico SHA-256 del file specificato."""
    _hcache = hash_cache if hash_cache is not None else {}
    st = file_path.stat()
    cache_key = (str(file_path), st.st_mtime_ns, st.st_size)
    if st.st_size > 256 and cache_key in _hcache:
        return _hcache[cache_key]
    hasher = hashlib.sha256()
    if file_path.suffix.lower() not in (
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".whl",
        ".exe",
        ".dll",
        ".pyd",
    ):
        raw = file_path.read_bytes().replace(b"\r\n", b"\n")
    else:
        raw = file_path.read_bytes()
    hasher.update(raw)
    digest = hasher.hexdigest()
    _hcache[cache_key] = digest
    return digest


def scan_skills_impl(self) -> Dict[str, Dict[str, Any]]:
    """Scansiona tutte le skill supportando auto-registrazione Hot-Swap via YAML."""
    skill_map = self._collect_priority_skills()
    skills_index: Dict[str, Dict[str, Any]] = {}
    for sk_name in sorted(skill_map.keys()):
        resolved, st = skill_map[sk_name]
        rel_path = f".agents/skills/{sk_name}/SKILL.md"
        ckey = (str(resolved), st.st_mtime_ns, st.st_size)
        if st.st_size > 128 and ckey in type(self)._SKILL_CACHE:
            sha_hex, loc_cnt, parsed = type(self)._SKILL_CACHE[ckey]
        else:
            raw_bytes = resolved.read_bytes().replace(b"\r\n", b"\n")
            sha_hex = hashlib.sha256(raw_bytes).hexdigest()
            type(self)._HASH_CACHE[ckey] = sha_hex
            content = raw_bytes.decode("utf-8", errors="replace")
            loc_cnt = len(content.splitlines())
            parsed = self._parse_skill_metadata(content)
            type(self)._SKILL_CACHE[ckey] = (sha_hex, loc_cnt, parsed)
        declared_dom = parsed.get("domain_id", "").strip().upper()
        dom_id = (
            declared_dom
            if declared_dom in DOMAIN_TAXONOMY
            else (
                parsed.get("domain_id")
                or self._skill_to_domain.get(sk_name, "DOM-02")
            )
        )
        if dom_id not in DOMAIN_TAXONOMY:
            dom_id = "DOM-02"
        dom_name = DOMAIN_TAXONOMY[dom_id]["name"]
        sector = parsed.get("sector") or dom_name
        native_subagent = self._resolve_skill_native_subagent(sk_name, dom_id)

        skills_index[sk_name] = {
            "name": parsed["name"] or sk_name,
            "domain_id": dom_id,
            "domain_name": dom_name,
            "sector": sector,
            "native_subagent": native_subagent,
            "version": parsed["version"],
            "description": parsed["description"],
            "thinking_level": parsed["thinking_level"],
            "role_identity": parsed["role_identity"],
            "enable_mcp_tools": bool(parsed.get("enable_mcp_tools", False)),
            "tools": list(parsed["tools"]),
            "auxiliary_links": list(parsed["auxiliary_links"]),
            "loc": loc_cnt,
            "bytes": st.st_size,
            "sha256": sha_hex,
            "path": rel_path,
            "source_layer": (
                "staging" if self.stage_dir in resolved.parents else "production"
            ),
        }
    return skills_index
