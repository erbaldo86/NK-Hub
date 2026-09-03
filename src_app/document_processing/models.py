"""Data models for Document Processing & Intelligence Extraction.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class BandoSectionType(str, Enum):
    """Tipologie semantiche di sezioni all'interno di un disciplinare o avviso di bando."""
    AMMISSIBILITA = "AMMISSIBILITA"
    SPESE_FINANZIABILI = "SPESE_FINANZIABILI"
    AGEVOLAZIONE_INTENSITA = "AGEVOLAZIONE_INTENSITA"
    SCADENZE_PROCEDURA = "SCADENZE_PROCEDURA"
    CRITERI_VALUTAZIONE = "CRITERI_VALUTAZIONE"
    MODALITA_PRESENTAZIONE = "MODALITA_PRESENTAZIONE"
    ALTRO = "ALTRO"


class BandoSection(BaseModel):
    """Rappresentazione strutturata di una specifica sezione estratta dal documento del bando."""
    model_config = {"extra": "forbid"}

    section_type: BandoSectionType = Field(..., description="Tipologia semantica della sezione")
    title: str = Field(..., description="Titolo o intestazione rilevata nel documento")
    content: str = Field(..., description="Testo pulito ed estratto appartenente alla sezione")
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Punteggio di confidenza euristico o semantico dell'attribuzione (0.0 - 1.0)"
    )
    key_entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Entità chiave estratte (importi, percentuali, date, codici ATECO rilevati)"
    )
    page_start: Optional[int] = Field(default=None, description="Pagina iniziale nel documento PDF")
    page_end: Optional[int] = Field(default=None, description="Pagina finale nel documento PDF")


class ProcessedDocumentReport(BaseModel):
    """Report consolidato dell'elaborazione di uno o più documenti/allegati di un bando."""
    model_config = {"extra": "forbid"}

    document_id: str = Field(..., description="ID identificativo deterministico del documento")
    source_filename: str = Field(..., description="Nome originario del file processato")
    mime_type: str = Field(..., description="Tipo MIME del documento originario")
    was_p7m: bool = Field(default=False, description="Flag che indica se il file era originariamente in busta .p7m")
    was_archive: bool = Field(default=False, description="Flag che indica se il file era un archivio .zip")
    extracted_files_count: int = Field(default=1, description="Numero di file estratti ed elaborati nel payload")
    total_pages: int = Field(default=1, description="Numero totale di pagine elaborate (se PDF)")
    total_text_length: int = Field(default=0, description="Lunghezza in caratteri del testo estratto")
    raw_text: str = Field(default="", description="Testo integrale pulito estratto dal documento")
    sections: List[BandoSection] = Field(
        default_factory=list,
        description="Sezioni tematiche identificate e segmentate"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadati del documento (certificati firma, autore PDF, timestamp)"
    )
