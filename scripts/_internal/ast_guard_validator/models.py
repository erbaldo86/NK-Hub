"""Contratti dati Pydantic e normalizzazione AST dei tipi per ast_guard_validator."""

from __future__ import annotations

import ast
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


PROTECTED_SECURITY_ANCHORS: Set[str] = {
    "_handle_write_gate",
    "_verify_quality_baseline_ratchet",
}


class ViolationType(str, Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SIGNATURE_MUTATION = "SIGNATURE_MUTATION"
    UNAUTHORIZED_DELETION = "UNAUTHORIZED_DELETION"
    UNDEFINED_NAME = "UNDEFINED_NAME"
    MALFORMED_IMPORT = "MALFORMED_IMPORT"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    SAST_VIOLATION = "SAST_VIOLATION"


class GuardViolation(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    violation_type: ViolationType = Field(description="Categoria della violazione AST")
    symbol_name: Optional[str] = Field(
        default=None, description="Nome del simbolo coinvolto"
    )
    line_number: Optional[int] = Field(
        default=None, description="Numero di riga (1-indexed)"
    )
    column: Optional[int] = Field(
        default=None, description="Offset di colonna (0-indexed)"
    )
    message: str = Field(description="Diagnosi esplicativa dell'errore")
    diff_context: Optional[str] = Field(
        default=None, description="Frammento diff o contesto della riga"
    )
    severity: str = Field(
        default="CRITICAL", description="Livello di gravita della violazione"
    )


class FunctionSignatureSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    name: str = Field(description="Nome della funzione o del metodo")
    is_async: bool = Field(description="Indica se la funzione e asincrona")
    posonly_args: List[str] = Field(
        default_factory=list, description="Argomenti solo posizionali"
    )
    pos_args: List[str] = Field(
        default_factory=list, description="Argomenti posizionali standard"
    )
    vararg: Optional[str] = Field(default=None, description="Nome *args se presente")
    kwonly_args: List[str] = Field(
        default_factory=list, description="Argomenti solo keyword"
    )
    kwarg: Optional[str] = Field(default=None, description="Nome **kwargs se presente")
    defaults_count: int = Field(
        default=0, description="Numero di valori di default posizionali"
    )
    kw_defaults_count: int = Field(
        default=0, description="Numero di valori di default keyword non-None"
    )
    kwonly_with_defaults: List[str] = Field(
        default_factory=list,
        description="Argomenti keyword-only dotati di valore di default",
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Mappa argomento -> stringa annotazione"
    )
    return_annotation: Optional[str] = Field(
        default=None, description="Stringa annotazione tipo di ritorno"
    )
    parent_class: Optional[str] = Field(
        default=None, description="Nome della classe contenitore"
    )


_PEP585_TYPE_ALIASES: Dict[str, str] = {
    "List": "list",
    "Dict": "dict",
    "Set": "set",
    "Tuple": "tuple",
    "FrozenSet": "frozenset",
    "Type": "type",
}


def _normalize_type_ast_node(node: ast.AST) -> str:
    """Normalizza ricorsivamente un nodo AST di annotazione di tipo."""
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        if isinstance(node.value, str):
            try:
                parsed_inner = ast.parse(node.value, mode="eval").body
                return _normalize_type_ast_node(parsed_inner)
            except Exception:
                return repr(node.value)
        return repr(node.value)
    if isinstance(node, ast.Name):
        if node.id == "NoneType":
            return "None"
        return _PEP585_TYPE_ALIASES.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id in (
            "typing",
            "typing_extensions",
            "builtins",
        ):
            return _PEP585_TYPE_ALIASES.get(node.attr, node.attr)
        return f"{_normalize_type_ast_node(node.value)}.{node.attr}"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts = _collect_union_parts(node.left) + _collect_union_parts(node.right)
        return _format_canonical_union(parts)
    if isinstance(node, ast.Subscript):
        base_str = _normalize_type_ast_node(node.value)
        if base_str == "Optional":
            parts = _collect_union_parts(node.slice) + ["None"]
            return _format_canonical_union(parts)
        if base_str == "Union":
            if isinstance(node.slice, ast.Tuple):
                parts = []
                for elt in node.slice.elts:
                    parts.extend(_collect_union_parts(elt))
            else:
                parts = _collect_union_parts(node.slice)
            return _format_canonical_union(parts)
        if isinstance(node.slice, ast.Tuple):
            inner = ", ".join(_normalize_type_ast_node(e) for e in node.slice.elts)
        else:
            inner = _normalize_type_ast_node(node.slice)
        return f"{base_str}[{inner}]"
    return ast.unparse(node)


def _collect_union_parts(node: ast.AST) -> List[str]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _collect_union_parts(node.left) + _collect_union_parts(node.right)
    if isinstance(node, ast.Subscript):
        base_str = _normalize_type_ast_node(node.value)
        if base_str == "Optional":
            return _collect_union_parts(node.slice) + ["None"]
        if base_str == "Union":
            if isinstance(node.slice, ast.Tuple):
                out: List[str] = []
                for elt in node.slice.elts:
                    out.extend(_collect_union_parts(elt))
                return out
            return _collect_union_parts(node.slice)
    return [_normalize_type_ast_node(node)]


def _format_canonical_union(parts: List[str]) -> str:
    has_none = False
    non_none: List[str] = []
    for p in parts:
        if p == "None":
            has_none = True
        elif p not in non_none:
            non_none.append(p)
    non_none.sort()
    if has_none:
        non_none.append("None")
    return " | ".join(non_none) if non_none else "None"


def _normalize_type_annotation(ann: Optional[str]) -> Optional[str]:
    """Normalizza annotazioni equivalenti (Optional[T] <-> T | None <-> Union[T, None])."""
    if ann is None:
        return None
    raw = ann.strip()
    if not raw:
        return raw
    try:
        tree = ast.parse(raw, mode="eval")
        return _normalize_type_ast_node(tree.body)
    except Exception:
        return raw


class ValidationReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    is_valid: bool = Field(description="True se non ci sono violazioni critiche")
    pre_symbol_count: int = Field(description="Totale simboli nell'AST pre-modifica")
    post_symbol_count: int = Field(description="Totale simboli nell'AST post-modifica")
    violations: List[GuardViolation] = Field(
        default_factory=list, description="Lista delle violazioni rilevate"
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Metriche dettagliate di validazione"
    )
