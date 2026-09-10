"""LabNK Dashboard UI Router.
Endpoints: GET /, GET /dashboard.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...service.bandi_service import LabNKBandiService
from ...ui.dashboard import DashboardRenderer
from ..deps import get_service

router = APIRouter(tags=["UI"])


@router.get("/", response_class=HTMLResponse, summary="Dashboard UI Root")
@router.get("/dashboard", response_class=HTMLResponse, summary="Dashboard UI")
def get_dashboard(
    service: LabNKBandiService = Depends(get_service),
) -> HTMLResponse:
    """Restituisce l'interfaccia utente HTML interattiva e reattiva della Dashboard LabNK."""
    html_content = DashboardRenderer.render_html(service)
    return HTMLResponse(content=html_content, status_code=200)
