"""LabNK API Routers Package.
Nexus Keystone v1.1.0-Universal | Modular REST Endpoints.
"""

from .documents_router import router as documents_router
from .grants_router import router as grants_router
from .health_router import router as health_router
from .search_router import router as search_router
from .sync_router import router as sync_router
from .ui_router import router as ui_router

__all__ = [
    "documents_router",
    "grants_router",
    "health_router",
    "search_router",
    "sync_router",
    "ui_router",
]
