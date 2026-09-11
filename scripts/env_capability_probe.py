"""
Nexus Keystone v1.1.0-Universal - Platform Capability & Environment Probe
Module: env_capability_probe.py
Author: NK-Platform-Builder

Features:
- Deterministic runtime discovery (Python version, OS architecture, codepage/encoding, CPU topology).
- Verification and introspection of standard library and third-party modules.
- Structured capability reports for platform diagnostics, CI/CD, and preflight validation.
- CLI interface with --json, --check-module, and --export options.
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


def check_module_availability(module_name: str) -> Dict[str, Any]:
    """
    Check if a specific Python module or package is available in the current environment.
    Safely discovers availability, version, and file/origin location without side-effects.

    Args:
        module_name: Canonical or package name of the module.

    Returns:
        Dict with keys: module, available, version, location, error.
    """
    cleaned_name = module_name.strip()
    result: Dict[str, Any] = {
        "module": cleaned_name,
        "available": False,
        "version": None,
        "location": None,
        "error": None,
    }

    # Special handling for pywin32 which maps to win32api internally
    target_import = cleaned_name
    if cleaned_name.lower() == "pywin32":
        target_import = "win32api"

    try:
        spec = importlib.util.find_spec(target_import)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    if spec is None:
        # If spec not found, check if it's installed package metadata (e.g. pywin32)
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

    # Attempt to resolve version cleanly
    version: Optional[str] = None
    # 1. Try importlib.metadata
    try:
        version = importlib.metadata.version(cleaned_name)
    except Exception:
        pass

    # 2. Try importing module to read __version__ if metadata didn't provide it
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

    # 3. If it is standard library, mark version with Python runtime version
    stdlib_names = getattr(sys, "stdlib_module_names", set())
    if version is None and cleaned_name in stdlib_names:
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    result["version"] = version
    return result


def probe_environment() -> Dict[str, Any]:
    """
    Perform deep deterministic environment discovery and capability audit.

    Returns:
        Structured dictionary containing Python, OS, codepage/encoding, CPU,
        standard modules, and third-party modules status.
    """
    # 1. Python runtime
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

    # 2. Operating System
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

    # 3. Codepage / Encodings
    encoding_info: Dict[str, Any] = {
        "default_encoding": sys.getdefaultencoding(),
        "filesystem_encoding": sys.getfilesystemencoding(),
        "preferred_encoding": locale.getpreferredencoding(False),
        "stdout_encoding": getattr(sys.stdout, "encoding", None),
        "stderr_encoding": getattr(sys.stderr, "encoding", None),
        "stdin_encoding": getattr(sys.stdin, "encoding", None),
    }

    # 4. CPU & Hardware Topology
    cpu_info: Dict[str, Any] = {
        "count": os.cpu_count(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "architecture": platform.architecture()[0],
    }

    # 5. Standard Modules Scan
    std_modules_map: Dict[str, Dict[str, Any]] = {}
    for mod_name in STANDARD_MODULES_TO_PROBE:
        std_modules_map[mod_name] = check_module_availability(mod_name)

    # 6. Third Party Modules Scan
    third_party_map: Dict[str, Dict[str, Any]] = {}
    for mod_name in THIRD_PARTY_MODULES_TO_PROBE:
        third_party_map[mod_name] = check_module_availability(mod_name)

    # 7. Summary metrics
    all_std_ok = all(info["available"] for info in std_modules_map.values())
    total_probed = len(std_modules_map) + len(third_party_map)
    total_available = sum(1 for m in list(std_modules_map.values()) + list(third_party_map.values()) if m["available"])
    total_missing = total_probed - total_available

    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": python_info,
        "os": os_info,
        "encoding": encoding_info,
        "cpu": cpu_info,
        "standard_modules": std_modules_map,
        "third_party_modules": third_party_map,
        "summary": {
            "total_probed": total_probed,
            "available_count": total_available,
            "missing_count": total_missing,
            "all_standard_available": all_std_ok,
            "status": "PASS" if all_std_ok else "DEGRADED",
        },
    }

    return report


def format_human_readable(data: Dict[str, Any]) -> str:
    """Format probe results into a clean human-readable diagnostic text."""
    lines: List[str] = [
        "=" * 80,
        "NEXUS KEYSTONE - ENVIRONMENT CAPABILITY PROBE",
        "=" * 80,
        f"Timestamp:   {data.get('timestamp')}",
        f"Python:      {data['python']['version'].split()[0]} ({data['python']['implementation']} {data['python']['version_major']}.{data['python']['version_minor']}.{data['python']['version_micro']})",
        f"Executable:  {data['python']['executable']}",
        f"OS:          {data['os']['system']} {data['os']['release']} ({data['os']['platform']})",
        f"CPU:         {data['cpu']['processor'] or data['cpu']['machine']} ({data['cpu']['count']} cores, {data['cpu']['architecture']})",
        f"Encodings:   default={data['encoding']['default_encoding']}, fs={data['encoding']['filesystem_encoding']}, stdout={data['encoding']['stdout_encoding']}",
        "-" * 80,
        "[STANDARD LIBRARY MODULES]",
    ]

    for name, info in data["standard_modules"].items():
        status = "[AVAILABLE]" if info["available"] else "[MISSING]"
        ver = f"v{info['version']}" if info["version"] else ""
        lines.append(f"  {status:12} {name:15} {ver}")

    lines.append("-" * 80)
    lines.append("[THIRD PARTY MODULES]")
    for name, info in data["third_party_modules"].items():
        status = "[AVAILABLE]" if info["available"] else "[MISSING]"
        ver = f"v{info['version']}" if info["version"] else ""
        lines.append(f"  {status:12} {name:15} {ver}")

    lines.append("=" * 80)
    summary = data["summary"]
    lines.append(
        f"STATUS: {summary['status']} | Available: {summary['available_count']}/{summary['total_probed']} | Missing: {summary['missing_count']}"
    )
    lines.append("=" * 80)
    return "\n".join(lines)


def main() -> int:
    """CLI entry point for environment capability probe."""
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Environment Capability Probe",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostics in formatted JSON format",
    )
    parser.add_argument(
        "--check-module",
        type=str,
        default=None,
        metavar="NAME",
        help="Check capability and availability of a specific module",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="PATH",
        help="Export full probe results to specified JSON file path",
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
