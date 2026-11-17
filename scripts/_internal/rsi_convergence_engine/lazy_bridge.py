"""Bridge lazy per hook della facciata rsi_convergence_engine senza cicli di importazione."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from _internal.nk_common.paths import reconfigure_streams as _nk_reconfigure_streams
from _internal.rsi_convergence_engine.constants import _scripts_dir, _workspace_root


_HOOKS: Dict[str, Any] = {}
_FALLBACK_STATE: Dict[str, Any] = {
    "streams_reconfigured": False,
    "hsm_cls": None,
    "hsm_loaded": False,
    "agv_cls": None,
    "agv_loaded": False,
    "ste100_fn": None,
    "grounding_fn": None,
}


def register_lazy_hooks(
    *,
    reconfigure_fn: Callable[[], None],
    hsm_fn: Callable[[], Any],
    agv_fn: Callable[[], Any],
    ste100_fn: Callable[[], Callable[..., Dict[str, Any]]],
    grounding_fn: Callable[[], Optional[Callable[..., Dict[str, Any]]]],
) -> None:
    """Registra i callback lazy della facciata RSI."""
    _HOOKS["reconfigure"] = reconfigure_fn
    _HOOKS["hsm"] = hsm_fn
    _HOOKS["agv"] = agv_fn
    _HOOKS["ste100"] = ste100_fn
    _HOOKS["grounding"] = grounding_fn


def fallback_reconfigure_streams() -> None:
    """Fallback per configurazione stream UTF-8 quando gli hook non sono registrati."""
    if _FALLBACK_STATE["streams_reconfigured"]:
        return
    _FALLBACK_STATE["streams_reconfigured"] = True
    out_enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    err_enc = (getattr(sys.stderr, "encoding", "") or "").lower()
    if out_enc == "utf-8" and err_enc == "utf-8":
        return
    try:
        from platform_runner import reconfigure_streams as _pr_reconfigure

        _pr_reconfigure()
    except ImportError:
        try:
            from scripts.platform_runner import reconfigure_streams as _pr_reconfigure2

            _pr_reconfigure2()
        except ImportError:
            pass


def fallback_load_ntt_module(
    scripts_dir: Optional[Path] = None, workspace_root: Optional[Path] = None
) -> Any:
    """Risolve nk_transcript_tools privilegiando la copia locale o di staging."""
    s_dir = scripts_dir or _scripts_dir
    ws_dir = workspace_root or _workspace_root
    for mod_cand in (
        s_dir / "nk_transcript_tools.py",
        ws_dir / ".staging" / "scripts" / "nk_transcript_tools.py",
        ws_dir / "scripts" / "nk_transcript_tools.py",
    ):
        if mod_cand.is_file():
            spec = importlib.util.spec_from_file_location(
                "_nk_transcript_tools_ssot", str(mod_cand)
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


def facade_reconfigure_streams(facade_ns: Dict[str, Any]) -> None:
    """Configura gli stream UTF-8 una sola volta sullo stato della facciata."""
    if facade_ns.get("_STREAMS_RECONFIGURED"):
        return
    facade_ns["_STREAMS_RECONFIGURED"] = True
    _nk_reconfigure_streams()


def facade_get_healing_snapshot_manager_cls(facade_ns: Dict[str, Any]) -> Any:
    """Carica pigramente HealingSnapshotManager mantenendo lo stato sulla facciata."""
    if facade_ns.get("_LAZY_HEALING_SNAPSHOT_LOADED"):
        return facade_ns.get("_LAZY_HEALING_SNAPSHOT_CLS")
    facade_ns["_LAZY_HEALING_SNAPSHOT_LOADED"] = True
    cls_res: Any = None
    try:
        from healing_snapshot_rollback import HealingSnapshotManager as _hsm

        cls_res = _hsm
    except ImportError:
        try:
            from scripts.healing_snapshot_rollback import (
                HealingSnapshotManager as _hsm2,
            )

            cls_res = _hsm2
        except ImportError:
            cls_res = None
    facade_ns["_LAZY_HEALING_SNAPSHOT_CLS"] = cls_res
    return cls_res


def facade_get_ast_guard_validator(facade_ns: Dict[str, Any]) -> Any:
    """Carica pigramente ASTGuardValidator privilegiando .staging/ quando disponibile."""
    if facade_ns.get("_LAZY_AST_GUARD_LOADED"):
        return facade_ns.get("_LAZY_AST_GUARD_CLS")
    facade_ns["_LAZY_AST_GUARD_LOADED"] = True
    f_scripts = Path(facade_ns.get("_SCRIPT_DIR", _scripts_dir))
    f_prod = Path(facade_ns.get("_PROD_SCRIPTS", _scripts_dir))
    f_ws = Path(facade_ns.get("_workspace_root", _workspace_root))
    stg_agv = f_scripts / "ast_guard_validator.py"
    if (
        f_scripts != f_prod
        and stg_agv.is_file()
        and "ast_guard_validator" not in sys.modules
    ):
        spec = importlib.util.spec_from_file_location("ast_guard_validator", str(stg_agv))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["ast_guard_validator"] = mod
            spec.loader.exec_module(mod)
            agv = getattr(mod, "ASTGuardValidator", None)
            if agv is not None:
                facade_ns["_LAZY_AST_GUARD_CLS"] = agv
                return agv
    agv_res: Any = None
    try:
        from ast_guard_validator import ASTGuardValidator as _agv

        if not hasattr(_agv, "check_sast_constructs"):
            cand = f_scripts / "ast_guard_validator.py"
            if not cand.exists():
                cand = f_ws / "scripts" / "ast_guard_validator.py"
            if cand.exists():
                spec2 = importlib.util.spec_from_file_location(
                    "ast_guard_validator", str(cand)
                )
                if spec2 and spec2.loader:
                    mod2 = importlib.util.module_from_spec(spec2)
                    sys.modules["ast_guard_validator"] = mod2
                    spec2.loader.exec_module(mod2)
                    _agv = mod2.ASTGuardValidator
        agv_res = _agv
    except ImportError:
        try:
            from scripts.ast_guard_validator import ASTGuardValidator as _agv2

            agv_res = _agv2
        except ImportError:
            agv_res = None
    facade_ns["_LAZY_AST_GUARD_CLS"] = agv_res
    return agv_res


def facade_get_ste100_validator(
    facade_ns: Dict[str, Any], load_ntt_fn: Callable[[], Any]
) -> Callable[..., Dict[str, Any]]:
    """Risolve verify_ste100_compliance sullo stato della facciata."""
    cached = facade_ns.get("_LAZY_STE100_FN")
    if cached is not None:
        return cached
    f_scripts = Path(facade_ns.get("_SCRIPT_DIR", _scripts_dir))
    f_prod = Path(facade_ns.get("_PROD_SCRIPTS", _scripts_dir))
    if (
        f_scripts != f_prod
        and (f_scripts / "nk_transcript_tools.py").is_file()
        and "nk_transcript_tools" not in sys.modules
    ):
        mod_stg = load_ntt_fn()
        if mod_stg is not None and hasattr(mod_stg, "verify_ste100_compliance"):
            facade_ns["_LAZY_STE100_FN"] = mod_stg.verify_ste100_compliance
            return facade_ns["_LAZY_STE100_FN"]
    try:
        from nk_transcript_tools import verify_ste100_compliance as _fn

        facade_ns["_LAZY_STE100_FN"] = _fn
        return _fn
    except ImportError:
        try:
            from scripts.nk_transcript_tools import verify_ste100_compliance as _fn2

            facade_ns["_LAZY_STE100_FN"] = _fn2
            return _fn2
        except ImportError:
            mod = load_ntt_fn()
            if mod is not None and hasattr(mod, "verify_ste100_compliance"):
                facade_ns["_LAZY_STE100_FN"] = mod.verify_ste100_compliance
                return mod.verify_ste100_compliance
            raise RuntimeError(
                "SSOT nk_transcript_tools.verify_ste100_compliance non disponibile."
            )


def facade_get_report_grounding_validator(
    facade_ns: Dict[str, Any], load_ntt_fn: Callable[[], Any]
) -> Optional[Callable[..., Dict[str, Any]]]:
    """Risolve verify_report_grounding sullo stato della facciata."""
    cached = facade_ns.get("_LAZY_GROUNDING_FN")
    if cached is not None:
        return cached
    f_scripts = Path(facade_ns.get("_SCRIPT_DIR", _scripts_dir))
    f_prod = Path(facade_ns.get("_PROD_SCRIPTS", _scripts_dir))
    if (
        f_scripts != f_prod
        and (f_scripts / "nk_transcript_tools.py").is_file()
        and "nk_transcript_tools" not in sys.modules
    ):
        mod_stg = load_ntt_fn()
        if mod_stg is not None and hasattr(mod_stg, "verify_report_grounding"):
            facade_ns["_LAZY_GROUNDING_FN"] = mod_stg.verify_report_grounding
            return facade_ns["_LAZY_GROUNDING_FN"]
    try:
        from nk_transcript_tools import verify_report_grounding as _gfn

        facade_ns["_LAZY_GROUNDING_FN"] = _gfn
    except ImportError:
        try:
            from scripts.nk_transcript_tools import verify_report_grounding as _gfn2

            facade_ns["_LAZY_GROUNDING_FN"] = _gfn2
        except ImportError:
            mod = load_ntt_fn()
            if mod is not None and hasattr(mod, "verify_report_grounding"):
                facade_ns["_LAZY_GROUNDING_FN"] = mod.verify_report_grounding
    return facade_ns.get("_LAZY_GROUNDING_FN")


def get_reconfigure_streams() -> None:
    fn = _HOOKS.get("reconfigure")
    if callable(fn):
        fn()
    else:
        fallback_reconfigure_streams()


def get_healing_snapshot_manager_cls() -> Any:
    fn = _HOOKS.get("hsm")
    if callable(fn):
        return fn()
    if _FALLBACK_STATE["hsm_loaded"]:
        return _FALLBACK_STATE["hsm_cls"]
    _FALLBACK_STATE["hsm_loaded"] = True
    _FALLBACK_STATE["hsm_cls"] = facade_get_healing_snapshot_manager_cls({})
    return _FALLBACK_STATE["hsm_cls"]


def get_ast_guard_validator() -> Any:
    fn = _HOOKS.get("agv")
    if callable(fn):
        return fn()
    if _FALLBACK_STATE["agv_loaded"]:
        return _FALLBACK_STATE["agv_cls"]
    _FALLBACK_STATE["agv_loaded"] = True
    _FALLBACK_STATE["agv_cls"] = facade_get_ast_guard_validator({})
    return _FALLBACK_STATE["agv_cls"]


def get_ste100_validator() -> Callable[..., Dict[str, Any]]:
    fn = _HOOKS.get("ste100")
    if callable(fn):
        return fn()
    if _FALLBACK_STATE["ste100_fn"] is not None:
        return _FALLBACK_STATE["ste100_fn"]
    res = facade_get_ste100_validator({}, fallback_load_ntt_module)
    _FALLBACK_STATE["ste100_fn"] = res
    return res


def get_report_grounding_validator() -> Optional[Callable[..., Dict[str, Any]]]:
    fn = _HOOKS.get("grounding")
    if callable(fn):
        return fn()
    if _FALLBACK_STATE["grounding_fn"] is not None:
        return _FALLBACK_STATE["grounding_fn"]
    res = facade_get_report_grounding_validator({}, fallback_load_ntt_module)
    _FALLBACK_STATE["grounding_fn"] = res
    return res


def facade_ensure_exports_loaded(
    facade_ns: Dict[str, Any],
    export_map: Dict[str, Tuple[str, str]],
    **hook_fns: Any,
) -> Dict[str, Any]:
    """Registra gli hook lazy e popola una volta gli export della facciata."""
    import importlib

    if not facade_ns.get("_HOOKS_REGISTERED"):
        register_lazy_hooks(**hook_fns)
        facade_ns["_HOOKS_REGISTERED"] = True
    if not facade_ns.get("_EXPORTS_LOADED"):
        for exp_name, (mod_path, attr_name) in export_map.items():
            facade_ns[exp_name] = getattr(importlib.import_module(mod_path), attr_name)
        facade_ns["_EXPORTS_LOADED"] = True
    return facade_ns
