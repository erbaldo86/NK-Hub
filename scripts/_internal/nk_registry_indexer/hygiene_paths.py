"""Helper di confinamento path e filtro plugin globali per hygiene_filter."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.io import atomic_write_bytes, atomic_write_text


def is_within_dir_impl(target: Path, base: Path) -> bool:
    """Verifica se target risiede strettamente dentro la directory base risolta."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _move_skills_to_disabled_plugin(
    skills_root: Path,
    plugins_root: Path,
    plugin_name: str,
    display_name: str,
    description: str,
    release_version: str,
    skill_names: Sequence[str],
    *,
    move_datacloud_manifest: bool = False,
) -> List[str]:
    """Sposta le skill esterne nel plugin disabilitato e scrive plugin.json atomico."""
    plugin_dir = plugins_root / plugin_name
    plugin_skills_dir = plugin_dir / "skills"
    plugin_skills_dir.mkdir(parents=True, exist_ok=True)
    moved: List[str] = []

    for sk_name in skill_names:
        src = skills_root / sk_name
        if src.exists() and src.is_dir():
            dst = plugin_skills_dir / sk_name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(src), str(dst))
            moved.append(sk_name)

    if move_datacloud_manifest:
        dc_manifest = skills_root / ".datacloud_skills_manifest"
        if dc_manifest.exists():
            dst_manifest = plugin_skills_dir / ".datacloud_skills_manifest"
            if dst_manifest.exists():
                dst_manifest.unlink()
            shutil.move(str(dc_manifest), str(dst_manifest))

    atomic_write_text(
        plugin_dir / "plugin.json",
        json.dumps(
            {
                "name": plugin_name,
                "displayName": display_name,
                "version": release_version,
                "description": description,
                "disabled": True,
            },
            indent=2,
        )
        + "\n",
    )
    return moved


def _update_global_config_json(
    cfg_path: Path, disabled_targets: Sequence[str]
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Aggiorna config.json disabilitando i plugin o mette in quarantena file corrotti."""
    cfg_data: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("config.json root must be a JSON object")
            cfg_data = loaded
        except (json.JSONDecodeError, ValueError) as exc:
            quarantine_path = cfg_path.with_name(
                f"{cfg_path.name}.corrupt.{time.time_ns()}.bak"
            )
            quarantined: Optional[str] = None
            try:
                q_ok, _ = atomic_write_bytes(quarantine_path, cfg_path.read_bytes())
                if q_ok:
                    quarantined = quarantine_path.as_posix()
            except OSError:
                pass
            return True, quarantined, str(exc)
        except OSError as exc:
            return True, None, str(exc)

    plugins_cfg = cfg_data.setdefault("plugins", {})
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
        cfg_data["plugins"] = plugins_cfg
    for target_plug in disabled_targets:
        entry = plugins_cfg.get(target_plug)
        if isinstance(entry, dict):
            entry["enabled"] = False
        else:
            plugins_cfg[target_plug] = {"enabled": False}

    ok_cfg, err_cfg = atomic_write_text(
        cfg_path,
        json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n",
    )
    if not ok_cfg:
        raise OSError(f"Failed to write config.json atomically: {err_cfg}")
    return False, None, None


def apply_global_filter_impl(self) -> Dict[str, Any]:
    """Valuta in sola lettura il profilo globale senza modificare file fuori dal workspace."""
    if not self.global_config_dir.exists():
        return {"applied": False, "reason": "global_config_dir_not_found"}

    disabled_targets = (
        "android-cli-plugin",
        "science",
        "gcp-data-cloud-plugin",
        "dev-utilities-plugin",
    )
    skills_root = self.global_config_dir / "skills"
    cfg_path = self.global_config_dir / "config.json"

    real_gemini_root = (Path.home() / ".gemini").resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    in_workspace = self._is_within_dir(self.global_config_dir, self.workspace_root)
    in_ephemeral_test_sandbox = (
        self._explicit_stage_dir
        and self._explicit_global_config_dir
        and self.stage_dir.parent != self.workspace_root
        and self._is_within_dir(self.global_config_dir, temp_root)
        and self._is_within_dir(self.global_config_dir, self.stage_dir.parent)
        and not self._is_within_dir(self.global_config_dir, real_gemini_root)
    )

    if not in_workspace and not in_ephemeral_test_sandbox:
        matched_gcp = [
            sk
            for sk in self.GCP_DATA_SKILLS
            if (skills_root / sk).exists() and (skills_root / sk).is_dir()
        ]
        matched_dev = [
            sk
            for sk in self.DEV_UTILITY_SKILLS
            if (skills_root / sk).exists() and (skills_root / sk).is_dir()
        ]
        self._readonly_filter_applied = True
        return {
            "applied": True,
            "read_only": True,
            "moved_gcp_skills": len(matched_gcp),
            "moved_dev_skills": len(matched_dev),
            "disabled_plugins": list(disabled_targets),
            "config_path": cfg_path.as_posix(),
        }

    plugins_root = self.global_config_dir / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    moved_gcp = _move_skills_to_disabled_plugin(
        skills_root,
        plugins_root,
        "gcp-data-cloud-plugin",
        "GCP Data Cloud & BigQuery",
        "Google Cloud Data Pipelines, BigQuery, Dataform, dbt, Dataflow, and Spark skills.",
        self.RELEASE_VERSION,
        self.GCP_DATA_SKILLS,
        move_datacloud_manifest=True,
    )
    moved_dev = _move_skills_to_disabled_plugin(
        skills_root,
        plugins_root,
        "dev-utilities-plugin",
        "General Dev & ML Utilities",
        "Standalone Python dependency, ML best practices, data loss prevention, and skill repair utilities.",
        self.RELEASE_VERSION,
        self.DEV_UTILITY_SKILLS,
        move_datacloud_manifest=False,
    )

    for p_name in ("science", "android-cli-plugin"):
        p_json = plugins_root / p_name / "plugin.json"
        if p_json.exists():
            try:
                p_data = json.loads(p_json.read_text(encoding="utf-8"))
                if isinstance(p_data, dict):
                    p_data["disabled"] = True
                    atomic_write_text(
                        p_json,
                        json.dumps(p_data, indent=2, ensure_ascii=False) + "\n",
                    )
            except (OSError, json.JSONDecodeError):
                pass

    config_corrupt, quarantined_config_path, config_error = _update_global_config_json(
        cfg_path, disabled_targets
    )
    res: Dict[str, Any] = {
        "applied": True,
        "read_only": False,
        "moved_gcp_skills": len(moved_gcp),
        "moved_dev_skills": len(moved_dev),
        "disabled_plugins": list(disabled_targets),
        "config_path": cfg_path.as_posix(),
    }
    if config_corrupt:
        res["config_corrupt"] = True
        res["config_preserved"] = True
        if quarantined_config_path:
            res["quarantined_config_path"] = quarantined_config_path
        if config_error:
            res["config_error"] = config_error
    return res
