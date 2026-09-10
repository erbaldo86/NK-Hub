"""LabNK Sovereign FastAPI Application Factory.
Nexus Keystone v1.1.0-Universal | API Gateway Factory.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core.bootstrap import bootstrap_demo_service
from ..core.config import APP_DESCRIPTION, APP_TITLE, APP_VERSION
from ..ingestion.orchestrator import IngestionOrchestrator
from ..service.bandi_service import LabNKBandiService
from .routers import (
    documents_router,
    grants_router,
    health_router,
    search_router,
    sync_router,
    ui_router,
)

logger = logging.getLogger("AppFactory")


def create_app(service: Optional[LabNKBandiService] = None) -> FastAPI:
    """
    Costruisce e configura l'applicazione sovereign FastAPI di LabNK Bandi Intelligence:
    - Gestione del ciclo di vita (Lifespan con pre-caricamento snapshot e background harvesting)
    - Policy CORS hardening per API stateless
    - Inclusione modulare di tutti i router REST (Search, Grants, Sync, Documents, UI, Health)
    """
    target_service = service if service is not None else bootstrap_demo_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Gestore del ciclo di vita:
        1. Carica lo snapshot offline salvato per boot immediato <50ms.
        2. Avvia in background l'harvesting live reale delle 31 fonti istituzionali.
        3. Gestisce la cancellazione aggraziata con await al teardown.
        """
        cached_snapshot = IngestionOrchestrator.load_snapshot()
        if cached_snapshot:
            logger.info("[*] Pre-caricamento di %d bandi da snapshot autentico (boot <50ms)...", len(cached_snapshot))
            target_service.swap_grants_atomic(cached_snapshot)

        logger.info("[*] Avvio harvesting in background delle 31 fonti istituzionali...")
        app.state.harvest_task = asyncio.create_task(IngestionOrchestrator.harvest_all(target_service))
        try:
            yield
        finally:
            if hasattr(app.state, "harvest_task") and app.state.harvest_task:
                logger.info("[*] Cancellazione e chiusura del task di harvesting in background...")
                app.state.harvest_task.cancel()
                try:
                    await app.state.harvest_task
                except (asyncio.CancelledError, Exception):
                    pass

    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
    )

    # Attach service to app state for dependency injection
    app.state.service = target_service

    # Hardened CORS policy for stateless API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register modular REST routers
    app.include_router(ui_router)
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(grants_router)
    app.include_router(sync_router)
    app.include_router(documents_router)

    return app
