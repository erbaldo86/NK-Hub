"""LabNK API Dependencies.
Nexus Keystone v1.1.0-Universal | FastAPI Dependency Injection.
"""

from fastapi import Request
from ..service.bandi_service import LabNKBandiService


def get_service(request: Request) -> LabNKBandiService:
    """Restituisce l'istanza globale del servizio LabNKBandiService associata all'applicazione."""
    return request.app.state.service
