"""LabNK Live Harvesting & Sync Router.
Endpoints: POST/GET /api/sync/harvest, GET /api/sync/status.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from ...ingestion.orchestrator import IngestionOrchestrator
from ...service.bandi_service import LabNKBandiService
from ..deps import get_service

logger = logging.getLogger("SyncRouter")

router = APIRouter(prefix="/api/sync", tags=["Sync"])


@router.post(
    "/harvest",
    summary="Sincronizzazione & Harvesting Fonti Ufficiali",
)
@router.get(
    "/harvest",
    summary="Sincronizzazione & Harvesting Fonti Ufficiali (GET)",
)
async def sync_harvest(
    request: Request,
    wait: bool = Query(
        default=False,
        description="Se True esegue await e restituisce il report completo (HTTP 200)",
    ),
    service: LabNKBandiService = Depends(get_service),
) -> Any:
    """
    Avvia la scansione e l'aggiornamento automatico dei bandi dalle 31 fonti
    istituzionali registrate nel registro SSOT (sources_registry.json).
    Restituisce HTTP 202 Accepted con job_id se wait=False per non bloccare il client.
    """
    try:
        if wait:
            # Esecuzione sincrona attesa dal client (HTTP 200)
            result = await IngestionOrchestrator.harvest_all(service)
            return JSONResponse(status_code=status.HTTP_200_OK, content=result)

        # Esecuzione asincrona (HTTP 202 Accepted)
        if IngestionOrchestrator.is_harvesting():
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "in_progress",
                    "job_id": IngestionOrchestrator.get_current_job_id(),
                    "message": "Harvesting già in corso in background.",
                },
            )

        job_id = f"job-{uuid.uuid4().hex[:8]}"
        task = asyncio.create_task(IngestionOrchestrator.harvest_all(service))
        request.app.state.harvest_task = task

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "started",
                "job_id": job_id,
                "message": "Harvesting live avviato in background con successo.",
            },
        )

    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante sync_harvest [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante la sincronizzazione delle fonti. Codice di riferimento: {error_id}",
        )


@router.get(
    "/status",
    summary="Telemetria e Stato Ultimo Harvesting",
)
def sync_status(
    service: LabNKBandiService = Depends(get_service),
) -> Dict[str, Any]:
    """Restituisce la telemetria dell'ultimo harvesting e lo stato attuale del motore di ingestion."""
    try:
        last_report = IngestionOrchestrator.get_last_telemetry()
        is_running = IngestionOrchestrator.is_harvesting()
        job_id = IngestionOrchestrator.get_current_job_id()

        return {
            "status": "running" if is_running else ("idle" if not last_report else "completed"),
            "is_running": is_running,
            "current_job_id": job_id,
            "total_grants_in_service": len(service.list_all_grants()),
            "last_harvest": last_report if last_report else None,
        }
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante sync_status [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante il recupero dello stato di sincronizzazione. Codice di riferimento: {error_id}",
        )
