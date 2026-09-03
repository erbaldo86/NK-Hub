"""Base Abstract Connector for Bandi Ingestion Pipeline.
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any, Optional
from pydantic import BaseModel, Field
import hashlib
import datetime


class RawBandoPayload(BaseModel):
    """Contenitore per il payload grezzo acquisito da una fonte remota."""
    model_config = {"extra": "forbid"}

    source_id: str = Field(..., description="ID univoco della fonte (es. 'EU_SEDIA', 'REG_LOMBARDIA')")
    source_url: str = Field(..., description="URL specifico da cui è stato scaricato il payload")
    raw_content: bytes = Field(..., description="Contenuto binario o testuale grezzo")
    content_type: str = Field(default="text/html", description="MIME type restituito dal server")
    http_headers: Dict[str, str] = Field(default_factory=dict, description="Header HTTP della risposta")
    structural_hash: str = Field(..., description="Hash SHA-256 della struttura del documento")
    fetched_at_utc: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(),
        description="Timestamp ISO 8601 di acquisizione"
    )


class ExtractedAttachment(BaseModel):
    """Rappresentazione di un allegato associato al bando (Disciplinare, Modulistica, ecc.)."""
    model_config = {"extra": "forbid"}

    filename: str = Field(..., description="Nome del file (es. 'bando_disciplinare.pdf')")
    content_bytes: bytes = Field(..., description="Contenuto binario dell'allegato")
    mime_type: str = Field(default="application/pdf", description="Tipo MIME del file")
    is_p7m_unpacked: bool = Field(default=False, description="Flag che indica se il file è stato estratto da .p7m")
    original_signature_valid: Optional[bool] = Field(
        default=None,
        description="Esito della verifica di integrità crittografica della firma CAdES/PKCS#7"
    )
    signer_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Dettagli del firmatario e del certificato estratto"
    )


class BaseBandoConnector(ABC):
    """
    Classe base astratta per tutti i connettori di acquisizione bandi.
    Definisce il ciclo di vita standard: fetch_raw -> parse -> extract_attachments -> normalize_to_cgm.
    """

    def __init__(self, source_id: str, base_url: str, rate_limit_rps: float = 2.0):
        self.source_id = source_id
        self.base_url = base_url
        self.rate_limit_rps = rate_limit_rps
        self._last_structural_hash: Optional[str] = None

    @abstractmethod
    async def fetch_raw(self, **kwargs) -> AsyncGenerator[RawBandoPayload, None]:
        """
        Esegue l'acquisizione a basso livello (HTTP GET/POST/API stream).
        Restituisce un generatore asincrono di RawBandoPayload.
        """
        pass

    @abstractmethod
    async def parse(self, raw_payload: RawBandoPayload) -> Dict[str, Any]:
        """
        Estrae le informazioni strutturate grezze dal payload (JSON dict o campi DOM).
        """
        pass

    @abstractmethod
    async def extract_attachments(
        self,
        raw_payload: RawBandoPayload,
        parsed_data: Dict[str, Any]
    ) -> List[ExtractedAttachment]:
        """
        Scarica ed elabora gli allegati associati al bando (PDF, P7M, ZIP).
        """
        pass

    @abstractmethod
    async def normalize_to_cgm(
        self,
        parsed_data: Dict[str, Any],
        attachments: List[ExtractedAttachment]
    ) -> Any:
        """
        Mappa e valida i dati estratti nel Canonical Grant Model (CanonicalGrantModel).
        """
        pass

    def compute_structural_hash(self, content: bytes) -> str:
        """
        Calcola l'hash SHA-256 della struttura del documento per rilevare il DOM o schema drift.
        """
        return hashlib.sha256(content).hexdigest()

    async def run_pipeline(self, **kwargs) -> AsyncGenerator[Any, None]:
        """
        Esegue l'intera pipeline di acquisizione, parsing, estrazione allegati e normalizzazione.
        """
        async for raw in self.fetch_raw(**kwargs):
            current_hash = self.compute_structural_hash(raw.raw_content)
            self._last_structural_hash = current_hash

            parsed_data = await self.parse(raw)
            attachments = await self.extract_attachments(raw, parsed_data)
            cgm_grant = await self.normalize_to_cgm(parsed_data, attachments)
            yield cgm_grant
