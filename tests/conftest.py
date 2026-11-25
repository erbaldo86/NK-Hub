# -*- coding: utf-8 -*-
"""
Configurazione Pytest e cache globale dei moduli per NK Hub Generation 1.0.0-Generation.
Modulo: tests/conftest.py.
Fornisce overlay .staging/, caricamento moduli, isolamento ambiente e fixture di sessione.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

import pytest

CONFTEST_VERSION: str = "1.0.0-Generation"

_CONFTEST_FILE = Path(__file__).resolve()
CURRENT_DIR = _CONFTEST_FILE.parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    _CONFTEST_FILE.parents[2]
    if STAGING_DIR.name == ".staging"
    else _CONFTEST_FILE.parents[1]
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
STAGING_ROOT = WORKSPACE_ROOT / ".staging"
STAGING_SCRIPTS_DIR = STAGING_ROOT / "scripts"
STAGING_SCHEMAS_DIR = STAGING_SCRIPTS_DIR / "schemas"
STAGING_INTERNAL_DIR = STAGING_SCRIPTS_DIR / "_internal"
STAGING_TESTS_DIR = STAGING_ROOT / "tests"
PROD_INTERNAL_DIR = SCRIPTS_DIR / "_internal"
PROD_TESTS_DIR = WORKSPACE_ROOT / "tests"


def _prepend_pkg_path(
    pkg_obj: Any, overlay_dir: Path, prod_dir: Optional[Path] = None
) -> None:
    """Inserisce overlay_dir in testa a __path__ preservando prod_dir come fallback."""
    pkg_path = getattr(pkg_obj, "__path__", None)
    if pkg_path is None:
        return
    if prod_dir is not None and prod_dir.is_dir():
        prod_str = str(prod_dir)
        if prod_str not in pkg_path:
            pkg_path.append(prod_str)
    if overlay_dir.is_dir():
        ov_str = str(overlay_dir)
        if ov_str in pkg_path:
            pkg_path.remove(ov_str)
        pkg_path.insert(0, ov_str)


def _overlay_internal_packages() -> None:
    """Applica l'overlay .staging/ ai pacchetti _internal, _internal.* e scripts._internal.*."""
    if not STAGING_INTERNAL_DIR.is_dir():
        return
    if (PROD_INTERNAL_DIR / "__init__.py").is_file() or (
        STAGING_INTERNAL_DIR / "__init__.py"
    ).is_file():
        internal_pkg = importlib.import_module("_internal")
        _prepend_pkg_path(internal_pkg, STAGING_INTERNAL_DIR, PROD_INTERNAL_DIR)
        if (SCRIPTS_DIR / "__init__.py").is_file():
            scripts_internal = importlib.import_module("scripts._internal")
            _prepend_pkg_path(
                scripts_internal, STAGING_INTERNAL_DIR, PROD_INTERNAL_DIR
            )

    for sub_dir in sorted(
        STAGING_INTERNAL_DIR.iterdir(),
        key=lambda p: (0 if p.name == "nk_common" else 1, p.name),
    ):
        if not sub_dir.is_dir() or sub_dir.name == "__pycache__":
            continue
        prod_sub = PROD_INTERNAL_DIR / sub_dir.name
        if (sub_dir / "__init__.py").is_file() or (prod_sub / "__init__.py").is_file():
            for prefix in ("_internal", "scripts._internal"):
                try:
                    sub_pkg = importlib.import_module(f"{prefix}.{sub_dir.name}")
                except ImportError:
                    continue
                _prepend_pkg_path(sub_pkg, sub_dir, prod_sub)

    for mod_name, mod_obj in list(sys.modules.items()):
        if mod_obj is None or not hasattr(mod_obj, "__path__"):
            continue
        rel_parts: Optional[List[str]] = None
        if mod_name == "_internal" or mod_name.startswith("_internal."):
            rel_parts = mod_name.split(".")[1:]
        elif mod_name == "scripts._internal" or mod_name.startswith(
            "scripts._internal."
        ):
            rel_parts = mod_name.split(".")[2:]
        if rel_parts is not None:
            ov_target = STAGING_INTERNAL_DIR.joinpath(*rel_parts)
            pr_target = PROD_INTERNAL_DIR.joinpath(*rel_parts)
            _prepend_pkg_path(mod_obj, ov_target, pr_target)


def _install_staging_import_overlay() -> None:
    """Configura sys.path e __path__ per dare priorita a .staging/ su scripts, schemas e _internal."""
    for cand in (
        WORKSPACE_ROOT,
        PROD_TESTS_DIR,
        CURRENT_DIR,
        SCRIPTS_DIR,
        STAGING_ROOT,
        STAGING_SCRIPTS_DIR,
    ):
        if cand.exists():
            cand_str = str(cand)
            if cand_str in sys.path:
                sys.path.remove(cand_str)
            sys.path.insert(0, cand_str)

    if STAGING_TESTS_DIR.exists() and (PROD_TESTS_DIR / "__init__.py").exists():
        import tests as _tests_pkg

        _prepend_pkg_path(_tests_pkg, STAGING_TESTS_DIR, PROD_TESTS_DIR)

    if STAGING_SCRIPTS_DIR.exists() and (SCRIPTS_DIR / "__init__.py").exists():
        import scripts as _scripts_pkg

        _prepend_pkg_path(_scripts_pkg, STAGING_SCRIPTS_DIR, SCRIPTS_DIR)

    if STAGING_SCHEMAS_DIR.exists() and (SCRIPTS_DIR / "schemas" / "__init__.py").exists():
        import schemas as _schemas_pkg
        import scripts.schemas as _scripts_schemas_pkg

        prod_schemas = SCRIPTS_DIR / "schemas"
        _prepend_pkg_path(_schemas_pkg, STAGING_SCHEMAS_DIR, prod_schemas)
        _prepend_pkg_path(_scripts_schemas_pkg, STAGING_SCHEMAS_DIR, prod_schemas)

    _overlay_internal_packages()


_install_staging_import_overlay()

_GLOBAL_MODULE_CACHE: Dict[str, Any] = {}
_CACHED_DEP_IDS: Set[int] = set()
_TRANSIENT_RELOAD_KEYS: Set[str] = set()
_SCRIPTS_RESOLVED: Path = SCRIPTS_DIR.resolve()
_STAGING_SCRIPTS_RESOLVED: Path = STAGING_SCRIPTS_DIR.resolve()
_STDLIB_MODULE_NAMES: FrozenSet[str] = frozenset(
    getattr(sys, "stdlib_module_names", ())
) | frozenset({"sys", "os", "builtins", "importlib"})
_PRESERVED_MODULE_PREFIXES: Tuple[str, ...] = (
    "pytest",
    "_pytest",
    "pluggy",
    "pydantic",
    "pydantic_core",
    "coverage",
    "_coverage",
)


def _handle_rm_readonly(func: Any, path: str, _exc: Any) -> None:
    """Rimuove il bit sola lettura su Windows durante la pulizia ricorsiva."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def safe_rmtree(path: Path, retries: int = 5, delay: float = 0.025) -> bool:
    """Rimuove ricorsivamente una directory gestendo bit sola lettura e retry [WinError 32]."""
    target = Path(path)
    if not target.exists() and not target.is_symlink():
        return True
    kw: Dict[str, Any] = (
        {"onexc": _handle_rm_readonly}
        if sys.version_info >= (3, 12)
        else {"onerror": _handle_rm_readonly}
    )
    attempts = max(1, int(retries))
    for idx in range(attempts):
        try:
            if target.is_symlink():
                target.unlink(missing_ok=True)
            else:
                shutil.rmtree(target, **kw)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if idx + 1 < attempts:
                time.sleep(max(0.0, float(delay)))
    return not target.exists() and not target.is_symlink()


def _normalize_staged_rel(raw_path: str) -> str:
    """Normalizza un percorso relativo POSIX rimuovendo prefissi ./ e /."""
    clean = str(raw_path or "").strip().strip("\"'").replace("\\", "/")
    while clean.startswith("./"):
        clean = clean[2:]
    clean = clean.strip("/")
    return clean.lower() if os.name == "nt" else clean


def _load_staged_deleted_set(staging_dir: Optional[Path] = None) -> Set[str]:
    """Carica in modo fail-safe i percorsi eliminati da .staging/.deleted_files.json."""
    base_stg = staging_dir if staging_dir is not None else STAGING_ROOT
    manifest = base_stg / ".deleted_files.json"
    if not manifest.is_file():
        return set()
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict) and isinstance(raw.get("deleted_files"), list):
        items = raw["deleted_files"]
    else:
        return set()
    return {
        norm
        for item in items
        if isinstance(item, str) and (norm := _normalize_staged_rel(item))
    }


_STAGED_DELETED_SET: Set[str] = _load_staged_deleted_set()


def _is_path_in_staged_deleted(rel_path: str) -> bool:
    """True se rel_path o una sua directory antenata figura in _STAGED_DELETED_SET."""
    norm_rel = _normalize_staged_rel(rel_path)
    if not norm_rel or not _STAGED_DELETED_SET:
        return False
    norm_low = norm_rel.lower()
    return any(
        norm_rel == d
        or norm_rel.startswith(f"{d}/")
        or norm_low == d.lower()
        or norm_low.startswith(f"{d.lower()}/")
        for d in _STAGED_DELETED_SET
    )


def _record_load_outcome(
    target_key: str,
    mod_name: str,
    mod: Any,
    pre_keys: Set[str],
    force_reload: bool,
) -> None:
    """Aggiorna cache globale o traccia alias force_reload per la pulizia di fine test."""
    if force_reload:
        _TRANSIENT_RELOAD_KEYS.add(mod_name)
        return
    _TRANSIENT_RELOAD_KEYS.discard(mod_name)
    _GLOBAL_MODULE_CACHE[target_key] = mod
    for loaded_name, loaded_obj in list(sys.modules.items()):
        if loaded_name not in pre_keys and loaded_obj is not None:
            _CACHED_DEP_IDS.add(id(loaded_obj))


def _is_real_workspace_module(mod_name: str, mod_obj: Any) -> bool:
    """True se il modulo risiede nei pacchetti scripts/ o .staging/scripts/ reali."""
    if mod_name in _TRANSIENT_RELOAD_KEYS:
        return False
    mod_file = getattr(mod_obj, "__file__", None)
    if not isinstance(mod_file, str) or not mod_file:
        return False
    try:
        mod_res = Path(mod_file).resolve()
    except OSError:
        return False
    return mod_res.is_relative_to(_SCRIPTS_RESOLVED) or mod_res.is_relative_to(
        _STAGING_SCRIPTS_RESOLVED
    )


def is_cov_instrumented() -> bool:
    """Verifica se l'esecuzione corrente usa coverage o tracing Python attivo."""
    if sys.gettrace() is not None:
        return True
    if hasattr(sys, "monitoring") and hasattr(sys.monitoring, "COVERAGE_ID"):
        if sys.monitoring.get_tool(sys.monitoring.COVERAGE_ID) is not None:
            return True
    return "COV_CORE_SOURCE" in os.environ


def _resolve_staged_or_prod(rel_path: str) -> Path:
    """Risolve un percorso relativo dando priorita alla copia in .staging/."""
    staged = WORKSPACE_ROOT / ".staging" / rel_path
    if staged.exists() or _is_path_in_staged_deleted(rel_path):
        return staged
    return WORKSPACE_ROOT / rel_path


def load_script_by_relpath(
    mod_name: str, rel_script: str, *, force_reload: bool = False
) -> Any:
    """Carica un modulo relativo al workspace con cache globale per path risolto."""
    target = _resolve_staged_or_prod(rel_script).resolve()
    target_key = str(target)
    dotted = (
        rel_script[:-3].replace("/", ".")
        if rel_script.endswith(".py")
        else mod_name
    )
    canonical = Path(rel_script).stem if rel_script.endswith(".py") else mod_name

    if not force_reload:
        cached = _GLOBAL_MODULE_CACHE.get(target_key)
        if cached is not None:
            sys.modules.setdefault(mod_name, cached)
            sys.modules.setdefault(canonical, cached)
            sys.modules.setdefault(dotted, cached)
            return cached
        for cand_key in (mod_name, canonical, dotted):
            existing = sys.modules.get(cand_key)
            if existing is not None:
                ex_file = getattr(existing, "__file__", None)
                if ex_file and Path(ex_file).resolve() == target:
                    _GLOBAL_MODULE_CACHE[target_key] = existing
                    sys.modules.setdefault(mod_name, existing)
                    sys.modules.setdefault(canonical, existing)
                    sys.modules.setdefault(dotted, existing)
                    return existing

    _install_staging_import_overlay()
    spec_name = canonical if not force_reload else mod_name
    spec = importlib.util.spec_from_file_location(spec_name, target_key)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossibile caricare il modulo {mod_name} da {target}")
    pre_load_keys = set(sys.modules.keys())
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    if not force_reload:
        sys.modules[canonical] = mod
        sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    _overlay_internal_packages()
    _record_load_outcome(target_key, mod_name, mod, pre_load_keys, force_reload)
    return mod


def load_nk_script_module(
    mod_name: str, rel_subpath: str = "scripts", *, force_reload: bool = False
) -> Any:
    """Carica e memorizza nella cache globale un modulo da .staging/ o produzione."""
    return load_script_by_relpath(
        mod_name, f"{rel_subpath}/{mod_name}.py", force_reload=force_reload
    )


def call_script_main(mod: Any, argv: List[str], monkeypatch: Any) -> int:
    """Invoca mod.main() con sys.argv simulato gestendo SystemExit in codice intero."""
    monkeypatch.setattr(sys, "argv", [f"{mod.__name__}.py", *argv])
    try:
        rc = mod.main()
        return int(rc or 0)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return int(exc.code) if isinstance(exc.code, int) else 1


def call_script_main_captured(
    mod: Any, argv: List[str], stdin_text: str = ""
) -> Tuple[int, str, str]:
    """Invoca mod.main(argv) o mod.main() in-process catturando stdout e stderr."""
    old_argv = list(sys.argv)
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    sys.argv = [getattr(mod, "__file__", f"{mod.__name__}.py"), *argv]
    sys.stdin = io.StringIO(stdin_text)
    sys.stdout = buf_out
    sys.stderr = buf_err
    rc = 0
    try:
        try:
            ret = mod.main(argv)
        except TypeError:
            ret = mod.main()
        if isinstance(ret, int):
            rc = ret
    except SystemExit as exc:
        if exc.code is None:
            rc = 0
        else:
            rc = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = old_argv
        sys.stdin = old_stdin
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    return rc, buf_out.getvalue(), buf_err.getvalue()


def _is_preserved_sys_module(
    mod_name: str,
    mod_obj: Any,
    baseline_keys: Set[str],
    cached_ids: Set[int],
) -> bool:
    """True se il modulo in sys.modules va preservato dopo il singolo test."""
    if mod_name in baseline_keys:
        return True
    if mod_obj is not None and (id(mod_obj) in cached_ids or id(mod_obj) in _CACHED_DEP_IDS):
        return True
    top_pkg = mod_name.split(".", 1)[0]
    if top_pkg in _STDLIB_MODULE_NAMES or mod_name.startswith(_PRESERVED_MODULE_PREFIXES):
        return True
    if _is_real_workspace_module(mod_name, mod_obj):
        return True
    mod_file = getattr(mod_obj, "__file__", "") or ""
    return isinstance(mod_file, str) and mod_file.lower().endswith((".pyd", ".so", ".dll"))


@pytest.fixture(autouse=True)
def _isolate_transient_sys_modules():
    """Rimuove le chiavi transitorie aggiunte a sys.modules preservando cache, stdlib e pytest."""
    baseline_keys = set(sys.modules.keys())
    yield
    cached_ids = {id(m) for m in _GLOBAL_MODULE_CACHE.values() if m is not None}
    for mod_name in list(sys.modules.keys()):
        if not _is_preserved_sys_module(
            mod_name, sys.modules.get(mod_name), baseline_keys, cached_ids
        ):
            sys.modules.pop(mod_name, None)


def _is_fast_guard_active(request: pytest.FixtureRequest) -> bool:
    """Attiva la guardia 0-Subprocess / 0-Sleep solo con -m fast su test marcati fast."""
    markexpr = str(getattr(request.config.option, "markexpr", "") or "").lower()
    if "fast" not in markexpr or "not fast" in markexpr:
        return False
    node = request.node
    has_fast = node.get_closest_marker("fast") is not None
    has_heavy = (
        node.get_closest_marker("integration") is not None
        or node.get_closest_marker("stress") is not None
    )
    return has_fast and not has_heavy


@pytest.fixture(autouse=True)
def _fast_guard_no_subprocess_or_sleep(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    """Impedisce sottoprocessi reali e sleep > 0.05s durante i test -m fast."""
    if not _is_fast_guard_active(request):
        yield
        return
    real_sleep = time.sleep

    def _forbidden_subprocess(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail(
            "[FAST-GUARD] Real subprocess forbidden in @pytest.mark.fast; move test to @pytest.mark.integration."
        )

    def _guarded_sleep(secs: float, *args: Any, **kwargs: Any) -> Any:
        if float(secs) > 0.05:
            pytest.fail(
                f"[FAST-GUARD] time.sleep({secs}) > 0.05s forbidden in @pytest.mark.fast"
            )
        return real_sleep(secs, *args, **kwargs)

    for mod_obj, attr_name in (
        (subprocess, "Popen"),
        (subprocess, "run"),
        (subprocess, "call"),
        (subprocess, "check_call"),
        (subprocess, "check_output"),
        (os, "system"),
    ):
        monkeypatch.setattr(mod_obj, attr_name, _forbidden_subprocess)
    monkeypatch.setattr(time, "sleep", _guarded_sleep)
    yield


@pytest.fixture(scope="session")
def session_registry_manifest() -> Dict[str, Any]:
    """Memorizza in cache di sessione il manifesto JSON nk_registry_manifest.json."""
    manifest_path = _resolve_staged_or_prod("nk_genome/nk_registry_manifest.json")
    if not manifest_path.is_file():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def session_genome_docs() -> Dict[str, str]:
    """Memorizza in cache di sessione i documenti Markdown della Pentad."""
    docs: Dict[str, str] = {}
    for rel_doc in (
        "nk_genome/idea_canvas.md",
        "nk_genome/concept_map.md",
        "nk_genome/structural_tree.md",
        "nk_genome/implementation_plan.md",
        "nk_genome/repo_map.md",
        "nk_genome/PATCH_NOTES.md",
    ):
        target = _resolve_staged_or_prod(rel_doc)
        if target.is_file():
            docs[Path(rel_doc).name] = target.read_text(encoding="utf-8")
    return docs


@pytest.fixture(scope="session")
def session_skill_files() -> Dict[str, str]:
    """Memorizza in cache di sessione il testo delle 11 skill in .agents/skills/."""
    skills_map: Dict[str, str] = {}
    skills_root = WORKSPACE_ROOT / ".agents" / "skills"
    if not skills_root.is_dir():
        return skills_map
    for sdir in sorted(skills_root.iterdir()):
        if sdir.is_dir() and (sdir / "SKILL.md").is_file():
            target = _resolve_staged_or_prod(
                f".agents/skills/{sdir.name}/SKILL.md"
            )
            skills_map[sdir.name] = target.read_text(encoding="utf-8")
    return skills_map


@pytest.fixture
def temp_test_dir():
    """Fornisce una directory temporanea isolata per le operazioni di test."""
    tmp = tempfile.mkdtemp(prefix="nk_test_dir_")
    path = Path(tmp)
    yield path
    safe_rmtree(path)


@pytest.fixture
def clean_sandbox_dir():
    """Fornisce una directory sandbox isolata per i test."""
    tmp = tempfile.mkdtemp(prefix="nk_sandbox_test_")
    path = Path(tmp)
    yield path
    safe_rmtree(path)


@pytest.fixture(scope="session")
def session_router() -> Any:
    """Istanza VibeSprintRouter condivisa a livello di sessione."""
    router_mod = load_nk_script_module("vibe_sprint_router")
    return router_mod.VibeSprintRouter(workspace_root=WORKSPACE_ROOT)


@pytest.fixture(scope="session")
def session_indexer() -> Any:
    """Istanza NKRegistryIndexer condivisa a livello di sessione."""
    idx_mod = load_nk_script_module("nk_registry_indexer")
    return idx_mod.NKRegistryIndexer(workspace_root=WORKSPACE_ROOT)


@pytest.fixture
def isolated_nk_env(tmp_path: Path, monkeypatch: Any) -> Path:
    """Isola NK_HOOKS_TEMP_DIR, TEMP e TMP sotto tmp_path senza inquinare la sandbox."""
    hooks_tmp = tmp_path / "nk_hooks_env"
    sys_tmp = tmp_path / "nk_sys_tmp"
    hooks_tmp.mkdir(parents=True, exist_ok=True)
    sys_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))
    monkeypatch.setenv("TEMP", str(sys_tmp))
    monkeypatch.setenv("TMP", str(sys_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(sys_tmp))
    return tmp_path


@pytest.fixture
def isolated_nk_ws_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Tuple[Dict[str, str], Path, Path]]:
    """Fornisce una factory per creare ambienti NK isolati sotto tmp_path."""

    def _factory(
        subdir: str = "nk_ws_env",
        extra: Optional[Dict[str, str]] = None,
        *,
        apply_inproc: bool = False,
    ) -> Tuple[Dict[str, str], Path, Path]:
        base_dir = tmp_path / subdir if subdir else tmp_path
        hooks_tmp = base_dir / "hooks_tmp"
        sys_tmp = base_dir / "sys_tmp"
        hooks_tmp.mkdir(parents=True, exist_ok=True)
        sys_tmp.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["NK_HOOKS_TEMP_DIR"] = str(hooks_tmp)
        env["TEMP"] = str(sys_tmp)
        env["TMP"] = str(sys_tmp)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if extra:
            for key, val in extra.items():
                env[key] = val
        if apply_inproc:
            for key in ("NK_HOOKS_TEMP_DIR", "TEMP", "TMP"):
                monkeypatch.setenv(key, env[key])
            if extra:
                for key, val in extra.items():
                    monkeypatch.setenv(key, val)
            monkeypatch.setattr(tempfile, "tempdir", str(sys_tmp))
        return env, hooks_tmp, sys_tmp

    return _factory
