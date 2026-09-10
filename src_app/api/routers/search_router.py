"""LabNK Search Router.
Endpoints: POST /api/search/nlp, POST /api/search/parametric.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ...matching.profile_model import MatchScoreBreakdown
from ...models.cgm import CanonicalGrantModel
from ...search.parametric_filter import ParametricFilterCriteria
from ...service.bandi_service import LabNKBandiService
from ..deps import get_service
from ..schemas import MatchResultItem, NLPSearchRequest, NLPSearchResponse, ParametricSearchResponse

logger = logging.getLogger("SearchRouter")

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.post(
    "/nlp",
    response_model=NLPSearchResponse,
    summary="Ricerca Semantica NLP & Matching Rating",
)
def search_nlp(
    req: NLPSearchRequest,
    service: LabNKBandiService = Depends(get_service),
) -> NLPSearchResponse:
    """
    Esegue l'estrazione dell'intento semantico (regione, ATECO, beneficiari, budget),
    il filtraggio dei bandi e il calcolo deterministico del Match Score (0-100%).
    """
    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il parametro 'query' non può essere vuoto.",
        )

    try:
        intent, ranked_grants, scores = service.search_nlp(
            req.query.strip(),
            profile=req.profile,
            top_k=req.top_k,
        )
        results = [
            MatchResultItem(grant=g, score=s)
            for g, s in zip(ranked_grants, scores)
        ]
        intent_data = intent.model_dump() if hasattr(intent, "model_dump") else intent
        return NLPSearchResponse(intent=intent_data, results=results)
    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante search_nlp [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante l'analisi semantica. Codice di riferimento: {error_id}",
        )


@router.post(
    "/parametric",
    response_model=ParametricSearchResponse,
    summary="Ricerca Parametrica Multi-Dimensionale",
)
def search_parametric(
    criteria: ParametricFilterCriteria,
    service: LabNKBandiService = Depends(get_service),
) -> ParametricSearchResponse:
    """Esegue il filtraggio combinatorio per ATECO, Regione, Beneficiari, Agevolazione e Budget."""
    try:
        matched: List[CanonicalGrantModel] = service.search_parametric(criteria)
        return ParametricSearchResponse(results=matched, count=len(matched))
    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante search_parametric [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante il filtraggio parametrico. Codice di riferimento: {error_id}",
        )
