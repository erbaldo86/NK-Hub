"""Canonical Grant Model (CGM) definition.

Pydantic v2 Strict Mode data model representing normalized grant data across all sources.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
import hashlib

from pydantic import BaseModel, ConfigDict, Field


class FonteTipo(str, Enum):
    REST_API = "REST_API"
    RSS_FEED = "RSS_FEED"
    HTML_SCRAPER = "HTML_SCRAPER"


class BandoStato(str, Enum):
    APERTO = "APERTO"
    IN_SCADENZA = "IN_SCADENZA"
    CHIUSO = "CHIUSO"
    PIANIFICATO = "PIANIFICATO"


class CanonicalGrantModel(BaseModel):
    """Canonical Grant Model (CGM) enforcing strict type validation."""

    model_config = ConfigDict(
        strict=True,
        frozen=False,
        validate_assignment=True,
        use_enum_values=False,
        extra="forbid",
    )

    bando_id: str
    titolo: str
    ente_erogatore: str
    descrizione: Optional[str] = None
    tipo_agevolazione: Optional[str] = None
    budget_totale: Optional[float] = None
    importo_massimo_finanziabile: Optional[float] = None
    percentuale_copertura: Optional[float] = None
    data_apertura: Optional[datetime] = None
    data_scadenza: Optional[datetime] = None
    stato: BandoStato = BandoStato.APERTO
    settori_beneficiari: List[str] = Field(default_factory=list)
    tipologia_beneficiari: List[str] = Field(default_factory=list)
    regioni_target: List[str] = Field(default_factory=list)
    url_bando: str
    url_documenti: List[str] = Field(default_factory=list)
    codice_cup: Optional[str] = None
    fonte_tipo: FonteTipo
    fonte_nome: str
    hash_payload: str
    dom_skeleton_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def calculate_payload_hash(raw_data: str | bytes) -> str:
        """Calculate SHA-256 hash for raw payload for duplicate/change detection."""
        if isinstance(raw_data, str):
            raw_bytes = raw_data.encode("utf-8")
        else:
            raw_bytes = raw_data
        return hashlib.sha256(raw_bytes).hexdigest()
