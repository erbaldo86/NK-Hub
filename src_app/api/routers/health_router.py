"""LabNK Health Check Router.
Endpoints: GET /health.
"""

from typing import Dict
from fastapi import APIRouter

from ...core.config import APP_TITLE, APP_VERSION

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health Check")
def health_check() -> Dict[str, str]:
    """Health check endpoint per monitoraggio e telemetria."""
    return {"status": "ok", "service": APP_TITLE, "version": APP_VERSION}
