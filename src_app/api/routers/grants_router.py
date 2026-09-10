"""LabNK Grants Catalog Router.
Endpoints: GET /api/grants.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ...models.cgm import CanonicalGrantModel
from ...service.bandi_service import LabNKBandiService
from ..deps import get_service
from ..schemas import GrantsListResponse

logger = logging.getLogger("GrantsRouter")

router = APIRouter(prefix="/api/grants", tags=["Grants"])


@router.get(
    "",
    response_model=GrantsListResponse,
    summary="Catalogo Completo Bandi CGM",
)
def list_grants(
    service: LabNKBandiService = Depends(get_service),
) -> GrantsListResponse:
    """Restituisce la lista di tutti i bandi canonici indicizzati nel sistema."""
    try:
        all_grants: List[CanonicalGrantModel] = service.list_all_grants()
        return GrantsListResponse(grants=all_grants, total=len(all_grants))
    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante list_grants [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante il recupero del catalogo. Codice di riferimento: {error_id}",
        )
