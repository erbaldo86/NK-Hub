"""LabNK Service Bootstrap Routines.
Nexus Keystone v1.1.0-Universal | Zero-Mock Engine.
"""

from typing import TYPE_CHECKING
from ..service.bandi_service import LabNKBandiService
from .catalog_loader import load_seed_grants

if TYPE_CHECKING:
    from ..ingestion.orchestrator import IngestionOrchestrator


def bootstrap_demo_service() -> LabNKBandiService:
    """
    Inizializza il servizio LabNK caricando il catalogo seed di 38 bandi CGM autentici.
    Boot deterministico ultra-rapido (<50ms) da file locale seed_grants.json.
    """
    service = LabNKBandiService()
    grants = load_seed_grants()
    service.add_grants(grants)
    return service


async def bootstrap_live_service() -> LabNKBandiService:
    """
    Inizializza il servizio LabNK avviando la scansione e l'aggiornamento live
    da tutte le fonti istituzionali registrate tramite IngestionOrchestrator.
    """
    from ..ingestion.orchestrator import IngestionOrchestrator
    service = LabNKBandiService()
    await IngestionOrchestrator.harvest_all(service)
    return service
