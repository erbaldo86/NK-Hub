"""LabNK Bandi Intelligence — Sovereign FastAPI Web Server Facade.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import uvicorn
from .api.app_factory import create_app
from .api.schemas import (
    GrantsListResponse,
    MatchResultItem,
    NLPSearchRequest,
    NLPSearchResponse,
    ParametricSearchResponse,
)
from .core.bootstrap import bootstrap_demo_service
from .core.config import CHUNK_SIZE, DEFAULT_HOST, DEFAULT_PORT, MAX_UPLOAD_SIZE
from .service.bandi_service import LabNKBandiService

# Global Sovereign Service & FastAPI App instances
service: LabNKBandiService = bootstrap_demo_service()
app = create_app(service=service)

__all__ = [
    "app",
    "service",
    "create_app",
    "bootstrap_demo_service",
    "NLPSearchRequest",
    "MatchResultItem",
    "NLPSearchResponse",
    "ParametricSearchResponse",
    "GrantsListResponse",
    "MAX_UPLOAD_SIZE",
    "CHUNK_SIZE",
]

if __name__ == "__main__":
    print(f"[*] Avvio LabNK Bandi Intelligence Server su http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
