"""Helper di verifica classi/firme, lookup controparte e persistenza JSON atomica."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from _internal.ast_guard_validator.models import (
    PROTECTED_SECURITY_ANCHORS,
    FunctionSignatureSnapshot,
    GuardViolation,
    ViolationType,
    _normalize_type_annotation,
)
from _internal.nk_common.io import atomic_write_json


def verify_classes_impl(
    pre_class_bases: Dict[str, List[str]],
    post_class_bases: Dict[str, List[str]],
    allowed_mutations: Set[str],
    violations: List[GuardViolation],
    target_file: str = "<target>",
) -> None:
    target_basename = (
        str(target_file).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if target_file
        else ""
    )
    for cls_key, pre_bases in pre_class_bases.items():
        short_name = cls_key.split(".")[-1]
        if cls_key in allowed_mutations or short_name in allowed_mutations:
            continue
        if (
            short_name == "SignatureDriftDetector"
            and target_basename == "ast_guard_validator.py"
        ):
            continue
        is_dunder = short_name.startswith("__") and short_name.endswith("__")
        is_protected = (
            short_name in PROTECTED_SECURITY_ANCHORS
            or cls_key in PROTECTED_SECURITY_ANCHORS
        )
        if short_name.startswith("_") and not is_dunder and not is_protected:
            continue

        if cls_key not in post_class_bases:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.UNAUTHORIZED_DELETION,
                    symbol_name=cls_key,
                    message=(
                        f"Public class '{cls_key}' was deleted without explicit "
                        "authorization in allowed_mutations."
                    ),
                )
            )
            continue

        post_bases = post_class_bases[cls_key]
        pre_effective = [
            b for b in pre_bases if b != "object" and b != f"_Core{short_name}"
        ]
        post_effective = [b for b in post_bases if b != "object"]
        missing_bases = [b for b in pre_effective if b not in post_effective]
        if missing_bases:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SIGNATURE_MUTATION,
                    symbol_name=cls_key,
                    message=(
                        f"Base class(es) {missing_bases} removed or altered for class "
                        f"'{cls_key}'. Expected {pre_bases}, got {post_bases}"
                    ),
                )
            )


def verify_signatures_impl(
    pre_sigs: Dict[str, FunctionSignatureSnapshot],
    post_sigs: Dict[str, FunctionSignatureSnapshot],
    allowed_mutations: Set[str],
    violations: List[GuardViolation],
) -> None:
    for name, pre_sig in pre_sigs.items():
        if name in allowed_mutations or name.split(".")[-1] in allowed_mutations:
            continue

        func_name = pre_sig.name
        is_dunder = func_name.startswith("__") and func_name.endswith("__")
        is_protected_anchor = (
            func_name in PROTECTED_SECURITY_ANCHORS
            or name in PROTECTED_SECURITY_ANCHORS
        )
        if func_name.startswith("_") and not is_dunder and not is_protected_anchor:
            continue

        if name not in post_sigs:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.UNAUTHORIZED_DELETION,
                    symbol_name=name,
                    message=f"Function/Method '{name}' was deleted without explicit authorization in allowed_mutations.",
                )
            )
            continue

        post_sig = post_sigs[name]

        if pre_sig.is_async != post_sig.is_async:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SIGNATURE_MUTATION,
                    symbol_name=name,
                    message=f"Async modifier altered for '{name}'. Pre: is_async={pre_sig.is_async}, Post: is_async={post_sig.is_async}",
                )
            )

        if pre_sig.posonly_args != post_sig.posonly_args:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SIGNATURE_MUTATION,
                    symbol_name=name,
                    message=f"Positional-only arguments changed for '{name}'. Expected {pre_sig.posonly_args}, got {post_sig.posonly_args}",
                )
            )

        pre_n = len(pre_sig.pos_args)
        post_n = len(post_sig.pos_args)
        pre_req = pre_n - pre_sig.defaults_count
        post_req = post_n - post_sig.defaults_count

        is_backward_compatible_extension = (
            post_n >= pre_n
            and post_sig.pos_args[:pre_n] == pre_sig.pos_args
            and post_req <= pre_req
            and post_sig.defaults_count >= pre_sig.defaults_count
        )

        if not is_backward_compatible_extension:
            if pre_sig.pos_args != post_sig.pos_args:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Positional arguments changed for '{name}'. Expected {pre_sig.pos_args}, got {post_sig.pos_args}",
                    )
                )
            elif pre_sig.defaults_count != post_sig.defaults_count:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Default parameter count changed for '{name}'. Expected {pre_sig.defaults_count}, got {post_sig.defaults_count}",
                    )
                )

        if pre_sig.vararg != post_sig.vararg:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SIGNATURE_MUTATION,
                    symbol_name=name,
                    message=f"Variadic positional (*args) changed for '{name}'. Expected {pre_sig.vararg!r}, got {post_sig.vararg!r}",
                )
            )

        pre_kw_set = set(pre_sig.kwonly_args)
        post_kw_set = set(post_sig.kwonly_args)
        new_kw = post_kw_set - pre_kw_set
        post_kw_def_set = set(post_sig.kwonly_with_defaults)
        pre_kw_def_set = set(pre_sig.kwonly_with_defaults)
        is_kwonly_compatible = (
            pre_kw_set.issubset(post_kw_set)
            and pre_kw_def_set.issubset(post_kw_def_set)
            and new_kw.issubset(post_kw_def_set)
            and post_sig.kw_defaults_count >= pre_sig.kw_defaults_count
        )
        if not is_kwonly_compatible:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SIGNATURE_MUTATION,
                    symbol_name=name,
                    message=f"Keyword-only arguments changed for '{name}'. Expected {pre_sig.kwonly_args}, got {post_sig.kwonly_args}",
                )
            )

        if pre_sig.kwarg != post_sig.kwarg:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SIGNATURE_MUTATION,
                    symbol_name=name,
                    message=f"Variadic keyword (**kwargs) changed for '{name}'. Expected {pre_sig.kwarg!r}, got {post_sig.kwarg!r}",
                )
            )

        for arg_name, pre_ann in pre_sig.annotations.items():
            post_ann = post_sig.annotations.get(arg_name)
            if _normalize_type_annotation(post_ann) != _normalize_type_annotation(
                pre_ann
            ):
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.TYPE_MISMATCH,
                        symbol_name=f"{name}:{arg_name}",
                        message=f"Type annotation for parameter '{arg_name}' altered in '{name}'. Expected '{pre_ann}', got '{post_ann}'",
                    )
                )

        if (
            pre_sig.return_annotation is not None
            and _normalize_type_annotation(pre_sig.return_annotation)
            != _normalize_type_annotation(post_sig.return_annotation)
        ):
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.TYPE_MISMATCH,
                    symbol_name=f"{name}:return",
                    message=f"Return type annotation altered for '{name}'. Expected '{pre_sig.return_annotation}', got '{post_sig.return_annotation}'",
                )
            )


def _resolve_production_counterpart(
    py_file: Path, workspace_root: Path
) -> Optional[Path]:
    """Individua il file di produzione corrispondente se py_file si trova in .staging/."""
    resolved = py_file.resolve()
    parts = list(resolved.parts)
    if ".staging" in parts:
        idx = parts.index(".staging")
        rel_parts = parts[idx + 1 :]
        if rel_parts:
            effective_root = Path(*parts[:idx]) if idx > 0 else workspace_root
            prod_cand = effective_root.joinpath(*rel_parts)
            if prod_cand.exists() and prod_cand.is_file() and prod_cand != resolved:
                return prod_cand
            fallback_cand = workspace_root.joinpath(*rel_parts)
            if (
                fallback_cand.exists()
                and fallback_cand.is_file()
                and fallback_cand != resolved
            ):
                return fallback_cand
    return None


def _write_json_atomic(out_path: Path, payload: Dict[str, Any]) -> None:
    """Persiste atomicamente il report JSON delegando a nk_common.io.atomic_write_json."""
    ok, err = atomic_write_json(
        out_path,
        payload,
        indent=2,
        ensure_ascii=False,
        ensure_parent=True,
    )
    if not ok:
        raise OSError(err or f"Atomic JSON write failed for {out_path}")
