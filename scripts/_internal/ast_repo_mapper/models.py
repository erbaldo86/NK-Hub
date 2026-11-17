"""Modelli Pydantic v2, enum, costanti e stima token per AST Repo-Map Engine."""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

CACHE_SCHEMA_VERSION: str = "1.0.0-Generation"

DEFAULT_EXCLUDED_DIRS: Set[str] = {
    ".venv",
    ".git",
    "__pycache__",
    "node_modules",
    ".staging",
    ".pytest_cache",
    ".wal",
    "NK_External_Projects",
    "NK_Hub",
    "01_Agenti_Skill_e_Regole",
    "nk_docs_and_setup",
    "google-docs-mcp",
    "Output Business Keystone",
    "Antigravity model",
    "fonti",
    "scratch",
    "test_scratch",
    "System_Documentation",
}


class SymbolType(str, Enum):
    MODULE = "MODULE"
    CLASS = "CLASS"
    METHOD = "METHOD"
    FUNCTION = "FUNCTION"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    CONSTANT = "CONSTANT"
    IMPORT = "IMPORT"
    TYPE_ALIAS = "TYPE_ALIAS"
    JS_COMPONENT = "JS_COMPONENT"
    CSS_RULE = "CSS_RULE"


class EdgeType(str, Enum):
    CALL = "CALL"
    INHERITANCE = "INHERITANCE"
    TYPE_REFERENCE = "TYPE_REFERENCE"
    IMPORT_USAGE = "IMPORT_USAGE"
    CONTAINMENT = "CONTAINMENT"
    ATTRIBUTE_ACCESS = "ATTRIBUTE_ACCESS"


class SymbolNode(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    id: str = Field(description="Identificatore univoco qualificato del simbolo")
    name: str = Field(description="Nome breve del simbolo")
    symbol_type: SymbolType = Field(description="Categoria del simbolo di codice")
    module_path: str = Field(description="Percorso relativo del modulo o file")
    parent_id: Optional[str] = Field(default=None, description="ID del contenitore padre")
    line_start: int = Field(ge=1, description="Riga iniziale (1-indexed)")
    line_end: int = Field(ge=1, description="Riga finale (1-indexed)")
    signature: Optional[str] = Field(default=None, description="Rappresentazione completa della firma")
    docstring: Optional[str] = Field(default=None, description="Docstring estratta")
    return_type: Optional[str] = Field(default=None, description="Annotazione del tipo di ritorno")
    is_async: bool = Field(default=False, description="Indica se la funzione risulta asincrona")
    raw_source: Optional[str] = Field(default=None, description="Frammento di codice sorgente originale")

    @field_validator("symbol_type", mode="before")
    @classmethod
    def _coerce_symbol_type(cls, val: Any) -> Any:
        """Converte le chiavi o i valori str JSON in SymbolType preservando strict=True."""
        if isinstance(val, SymbolType):
            return val
        if isinstance(val, str):
            try:
                return SymbolType(val)
            except ValueError:
                if val in SymbolType.__members__:
                    return SymbolType[val]
        return val


class SymbolEdge(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    source_id: str = Field(description="ID del simbolo sorgente")
    target_id: str = Field(description="ID del simbolo destinazione")
    edge_type: EdgeType = Field(description="Categoria della relazione")
    weight: float = Field(default=1.0, ge=0.0, description="Peso dell'arco per PageRank")

    @field_validator("edge_type", mode="before")
    @classmethod
    def _coerce_edge_type(cls, val: Any) -> Any:
        """Converte le chiavi o i valori str JSON in EdgeType preservando strict=True."""
        if isinstance(val, EdgeType):
            return val
        if isinstance(val, str):
            try:
                return EdgeType(val)
            except ValueError:
                if val in EdgeType.__members__:
                    return EdgeType[val]
        return val


class SymbolGraph(BaseModel):
    model_config = ConfigDict(strict=True)

    nodes: Dict[str, SymbolNode] = Field(default_factory=dict, description="Mappa dei nodi per ID")
    edges: List[SymbolEdge] = Field(default_factory=list, description="Archi diretti tra simboli")
    adjacency_out: Dict[str, List[Tuple[str, float]]] = Field(
        default_factory=dict, description="Lista di adiacenza in uscita"
    )
    adjacency_in: Dict[str, List[Tuple[str, float]]] = Field(
        default_factory=dict, description="Lista di adiacenza in ingresso"
    )

    def add_node(self, node: SymbolNode) -> None:
        self.nodes[node.id] = node
        if node.id not in self.adjacency_out:
            self.adjacency_out[node.id] = []
        if node.id not in self.adjacency_in:
            self.adjacency_in[node.id] = []

    def add_edge(self, edge: SymbolEdge) -> None:
        self.edges.append(edge)
        if edge.source_id not in self.adjacency_out:
            self.adjacency_out[edge.source_id] = []
        if edge.target_id not in self.adjacency_in:
            self.adjacency_in[edge.target_id] = []
        self.adjacency_out[edge.source_id].append((edge.target_id, edge.weight))
        self.adjacency_in[edge.target_id].append((edge.source_id, edge.weight))


class PageRankResult(BaseModel):
    model_config = ConfigDict(strict=True)

    scores: Dict[str, float] = Field(description="Mappa ID simbolo e punteggio PageRank")
    ranked_symbols: List[Tuple[str, float]] = Field(description="Lista ordinata decrescente")
    iterations: int = Field(description="Numero di iterazioni fino a convergenza")
    converged: bool = Field(description="Indica se la convergenza sotto epsilon risulta raggiunta")


class SliceResult(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    sliced_code: str = Field(description="Codice sorgente ridotto chirurgicamente")
    token_count: int = Field(description="Stima dei token")
    focal_symbols: List[str] = Field(description="ID dei simboli focali preservati per intero")
    collapsed_symbols: List[str] = Field(description="ID dei simboli compressi in firme scheletro")
    omitted_symbols: List[str] = Field(description="ID dei simboli a bassa rilevanza omessi")
    compression_ratio: float = Field(description="Rapporto tra caratteri ridotti e originali")


class RepoMapConfig(BaseModel):
    model_config = ConfigDict(strict=True)

    max_tokens: int = Field(default=1024, ge=128, le=4096, description="Tetto massimo del budget token")
    mode: str = Field(default="auto", description="Modalita esecuzione: auto, mode_c, mode_b, mode_a")
    cache_enabled: bool = Field(default=True, description="Abilita la cache atomica su disco")
    cache_dir: Optional[str] = Field(default=None, description="Directory personalizzata per la cache")
    polyglot: bool = Field(default=True, description="Include contratti frontend JS/TS/CSS/HTML")
    focal_files: List[str] = Field(default_factory=list, description="Percorsi dei file focali target")
    focal_symbols: List[str] = Field(default_factory=list, description="Nomi dei simboli focali target")


class RepoMapResult(BaseModel):
    model_config = ConfigDict(strict=True)

    content: str = Field(description="Contenuto Markdown della Repo-Map")
    token_count: int = Field(description="Conteggio stimato dei token <= max_tokens")
    files_scanned: int = Field(description="Totale dei file analizzati o letti da cache")
    cached_hits: int = Field(description="Conteggio dei file serviti dalla cache incrementale")
    elapsed_ms: float = Field(description="Tempo totale di generazione in millisecondi")
    focal_files: List[str] = Field(default_factory=list, description="File focali prioritizzati")


def estimate_tokens(text: str) -> int:
    """
    Stima il numero di token in modo deterministico compatibile con BPE.
    Combina la frammentazione lessicale con la lunghezza in caratteri.
    """
    if not text:
        return 0
    pattern = re.compile(r"\w+|[^\w\s]", re.UNICODE)
    tokens = pattern.findall(text)
    char_estimate = int(math.ceil(len(text) / 3.5))
    return max(len(tokens), char_estimate)
