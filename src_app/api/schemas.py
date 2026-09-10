"""LabNK API Request & Response Schemas.
Nexus Keystone v1.1.0-Universal | Strict DTO Contracts.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

from ..matching.profile_model import CompanyProfile, MatchScoreBreakdown
from ..models.cgm import CanonicalGrantModel
from ..search.nlp_intent_extractor import SearchIntent


class NLPSearchRequest(BaseModel):
    """Richiesta di ricerca in linguaggio naturale."""

    query: str = Field(..., description="Query di ricerca testuale o conversazionale")
    profile: Optional[CompanyProfile] = Field(
        default=None,
        description="Profilo aziendale opzionale per il calcolo avanzato del matching",
    )
    top_k: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Numero massimo di bandi da restituire",
    )


class MatchResultItem(BaseModel):
    """Coppia Bando-Valutazione nel risultato di ricerca semantica."""

    grant: CanonicalGrantModel
    score: MatchScoreBreakdown


class NLPSearchResponse(BaseModel):
    """Risposta strutturata dell'endpoint di ricerca semantica NLP."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    intent: SearchIntent
    results: List[MatchResultItem]


class ParametricSearchResponse(BaseModel):
    """Risposta dell'endpoint di ricerca parametrica."""

    results: List[CanonicalGrantModel]
    count: int


class GrantsListResponse(BaseModel):
    """Risposta per l'elenco completo dei bandi CGM."""

    grants: List[CanonicalGrantModel]
    total: int


__all__ = [
    "NLPSearchRequest",
    "MatchResultItem",
    "NLPSearchResponse",
    "ParametricSearchResponse",
    "GrantsListResponse",
]
