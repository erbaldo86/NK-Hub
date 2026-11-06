# -*- coding: utf-8 -*-
"""
Sonda deterministica delle capacita dell'ambiente per Nexus Keystone v3.0.0-STE100-Unified.
Separa i moduli core dell'Hub dai moduli opzionali mantenendo invariato total_probed (GT-09).
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import locale
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

try:
    from platform_runner import reconfigure_streams
except ImportError:
    try:
        from scripts.platform_runner import reconfigure_streams
    except ImportError:
        def reconfigure_streams() -> None:
            pass

STANDARD_MODULES_TO_PROBE: List[str] = [
    "sqlite3",
    "json",
    "csv",
    "re",
    "asyncio",
    "pathlib",
    "typing",
]

THIRD_PARTY_MODULES_TO_PROBE: List[str] = [
    "fastapi",
    "pydantic",
    "pytest",
    "uvicorn",
    "httpx",
    "psutil",
    "pywin32",
    "sqlalchemy",
]

CORE_HUB_MODULES: List[str] = [
    "pydantic",
    "psutil",
    "pytest",
]

OPTIONAL_APP_MODULES: List[str] = [
    "fastapi",
    "uvicorn",
    "httpx",
    "pywin32",
    "sqlalchemy",
]


def check_module_availability(module_name: str) -> Dict[str, Any]:
    """Verifica la disponibilita, la versione e il percorso di un modulo Python."""
    cleaned_name = module_name.strip()
    result: Dict[str, Any] = {
        "module": cleaned_name,
        "available": False,
        "version": None,
        "location": None,
        "error": None,
    }

    target_import = cleaned_name
    if cleaned_name.lower() == "pywin32":
        target_import = "win32api"

    try:
        spec = importlib.util.find_spec(target_import)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    if spec is None:
        try:
            ver = importlib.metadata.version(cleaned_name)
            result["available"] = True
            result["version"] = ver
            result["location"] = "site-packages (package metadata)"
            return result
        except Exception:
            return result

    result["available"] = True
    result["location"] = getattr(spec, "origin", None) or "built-in / namespace"

    version: Optional[str] = None
    try:
        version = importlib.metadata.version(cleaned_name)
    except Exception:
        pass

    if version is None:
        try:
            mod = sys.modules.get(target_import)
            if mod is None:
                mod = importlib.import_module(target_import)
            ver_attr = getattr(mod, "__version__", None)
            if ver_attr is not None:
                version = str(ver_attr)
        except Exception:
            pass

    stdlib_names = getattr(sys, "stdlib_module_names", set())
    if version is None and cleaned_name in stdlib_names:
        version = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

    result["version"] = version
    return result


def probe_environment() -> Dict[str, Any]:
    """Esegue la scansione completa dell'ambiente runtime e dei moduli installati."""
    reconfigure_streams()

    python_info: Dict[str, Any] = {
        "version": sys.version,
        "version_major": sys.version_info.major,
        "version_minor": sys.version_info.minor,
        "version_micro": sys.version_info.micro,
        "releaselevel": sys.version_info.releaselevel,
        "serial": sys.version_info.serial,
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "is_64bit": sys.maxsize > (2**32),
    }

    os_info: Dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "platform": platform.platform(),
        "name": os.name,
        "is_windows": platform.system().lower() == "windows",
        "is_linux": platform.system().lower() == "linux",
        "is_darwin": platform.system().lower() == "darwin",
    }

    encoding_info: Dict[str, Any] = {
        "default_encoding": sys.getdefaultencoding(),
        "filesystem_encoding": sys.getfilesystemencoding(),
        "preferred_encoding": locale.getpreferredencoding(False),
        "stdout_encoding": getattr(sys.stdout, "encoding", None),
        "stderr_encoding": getattr(sys.stderr, "encoding", None),
        "stdin_encoding": getattr(sys.stdin, "encoding", None),
    }

    cpu_info: Dict[str, Any] = {
        "count": os.cpu_count(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "architecture": platform.architecture()[0],
    }

    std_modules_map: Dict[str, Dict[str, Any]] = {}
    for mod_name in STANDARD_MODULES_TO_PROBE:
        std_modules_map[mod_name] = check_module_availability(mod_name)

    third_party_map: Dict[str, Dict[str, Any]] = {}
    for mod_name in THIRD_PARTY_MODULES_TO_PROBE:
        third_party_map[mod_name] = check_module_availability(mod_name)

    core_hub_map: Dict[str, Dict[str, Any]] = {
        m: third_party_map.get(m, check_module_availability(m))
        for m in CORE_HUB_MODULES
    }
    optional_app_map: Dict[str, Dict[str, Any]] = {
        m: third_party_map.get(m, check_module_availability(m))
        for m in OPTIONAL_APP_MODULES
    }

    all_std_ok = all(info["available"] for info in std_modules_map.values())
    all_core_ok = all(info["available"] for info in core_hub_map.values())
    total_probed = len(std_modules_map) + len(third_party_map)
    total_available = sum(
        1
        for m in list(std_modules_map.values()) + list(third_party_map.values())
        if m["available"]
    )
    total_missing = total_probed - total_available

    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": python_info,
        "os": os_info,
        "encoding": encoding_info,
        "cpu": cpu_info,
        "standard_modules": std_modules_map,
        "third_party_modules": third_party_map,
        "core_hub_modules": core_hub_map,
        "optional_app_modules": optional_app_map,
        "summary": {
            "total_probed": total_probed,
            "available_count": total_available,
            "missing_count": total_missing,
            "all_standard_available": all_std_ok,
            "all_core_hub_available": all_core_ok,
            "status": "PASS" if (all_std_ok and all_core_ok) else "DEGRADED",
        },
    }

    return report


def format_human_readable(data: Dict[str, Any]) -> str:
    """Formatta i risultati della sonda in un rapporto testuale leggibile."""
    lines: List[str] = [
        "=" * 80,
        "NEXUS KEYSTONE - ENVIRONMENT CAPABILITY PROBE",
        "=" * 80,
        f"Timestamp:   {data.get('timestamp')}",
        f"Python:      {data['python']['version'].split()[0]} ({data['python']['implementation']})",
        f"Executable:  {data['python']['executable']}",
        f"OS:          {data['os']['system']} {data['os']['release']}",
        "-" * 80,
        "[STANDARD LIBRARY MODULES]",
    ]

    for name, info in data["standard_modules"].items():
        status = "[AVAILABLE]" if info["available"] else "[MISSING]"
        ver = f"v{info['version']}" if info["version"] else ""
        lines.append(f"  {status:12} {name:15} {ver}")

    lines.append("-" * 80)
    lines.append("[CORE HUB MODULES]")
    for name, info in data.get("core_hub_modules", {}).items():
        status = "[AVAILABLE]" if info["available"] else "[MISSING]"
        ver = f"v{info['version']}" if info["version"] else ""
        lines.append(f"  {status:12} {name:15} {ver}")

    lines.append("-" * 80)
    lines.append("[OPTIONAL APP MODULES]")
    for name, info in data.get("optional_app_modules", {}).items():
        status = "[AVAILABLE]" if info["available"] else "[MISSING]"
        ver = f"v{info['version']}" if info["version"] else ""
        lines.append(f"  {status:12} {name:15} {ver}")

    lines.append("=" * 80)
    summary = data["summary"]
    lines.append(
        f"STATUS: {summary['status']} | Available: {summary['available_count']}/{summary['total_probed']}"
    )
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> int:
    """Punto di ingresso CLI per la sonda delle capacita di ambiente."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Environment Capability Probe",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il rapporto in formato JSON",
    )
    parser.add_argument(
        "--check-module",
        type=str,
        default=None,
        metavar="NAME",
        help="Verifica la disponibilita di un singolo modulo",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="PATH",
        help="Esporta il rapporto completo nel percorso file JSON specificato",
    )

    args = parser.parse_args()

    if args.check_module:
        mod_info = check_module_availability(args.check_module)
        if args.json:
            print(json.dumps(mod_info, indent=2))
        else:
            status = "AVAILABLE" if mod_info["available"] else "NOT AVAILABLE"
            ver_str = f" (v{mod_info['version']})" if mod_info["version"] else ""
            loc_str = f" from {mod_info['location']}" if mod_info["location"] else ""
            print(f"Module '{mod_info['module']}': {status}{ver_str}{loc_str}")
        return 0 if mod_info["available"] else 1

    report = probe_environment()

    if args.export:
        export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not args.json:
            print(f"[EXPORT] Report successfully written to: {export_path}")

    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.export:
        print(format_human_readable(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
