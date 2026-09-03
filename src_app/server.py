"""LabNK Bandi Intelligence — Sovereign FastAPI Web Server.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import sys
import io
import uuid
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

# Force UTF-8 on stdout/stderr for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to sys.path if not present
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src_app.models.cgm import CanonicalGrantModel, BandoStato
from src_app.search.nlp_intent_extractor import SearchIntent
from src_app.search.parametric_filter import ParametricFilterCriteria
from src_app.matching.profile_model import CompanyProfile, MatchScoreBreakdown
from src_app.service.bandi_service import LabNKBandiService
from src_app.document_processing.models import ProcessedDocumentReport
from src_app.document_processing.document_pipeline import DocumentPipeline
from src_app.ui.dashboard import DashboardRenderer
from src_app.app import bootstrap_demo_service

logger = logging.getLogger("LabNKServer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB max upload security cap
CHUNK_SIZE = 1024 * 1024            # 1 MB streaming read chunk


# ---------------------------------------------------------------------------
# API REQUEST & RESPONSE MODELS
# ---------------------------------------------------------------------------

class NLPSearchRequest(BaseModel):
    """Richiesta di ricerca in linguaggio naturale."""
    query: str = Field(..., description="Query di ricerca testuale o conversazionale")
    profile: Optional[CompanyProfile] = Field(
        default=None,
        description="Profilo aziendale opzionale per il calcolo avanzato del matching"
    )
    top_k: int = Field(default=20, ge=1, le=100, description="Numero massimo di bandi da restituire")


class MatchResultItem(BaseModel):
    """Coppia Bando-Valutazione nel risultato di ricerca semantica."""
    grant: CanonicalGrantModel
    score: MatchScoreBreakdown


class NLPSearchResponse(BaseModel):
    """Risposta strutturata dell'endpoint di ricerca semantica NLP."""
    intent: SearchIntent
    results: List[MatchResultItem]


class ParametricSearchResponse(BaseModel):
    """Risposta dell'endpoint di ricerca parametrica."""
    results: List[CanonicalGrantModel]
    count: int


class GrantsListResponse(BaseModel):
    """Risposta per l'elenco completo dei bandi CGM."""
    grants: List[CanonicalGrantModel]
    total: int


# ---------------------------------------------------------------------------
# FASTAPI APPLICATION SETUP
# ---------------------------------------------------------------------------

# Global Sovereign Service Instance with real demo dataset
service: LabNKBandiService = bootstrap_demo_service()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestore del ciclo di vita:
    1. Carica lo snapshot offline salvato per boot immediato <50ms.
    2. Avvia in background l'harvesting live reale delle 31 fonti istituzionali.
    3. Gestisce la cancellazione aggraziata con await al teardown.
    """
    from src_app.ingestion.orchestrator import IngestionOrchestrator
    cached_snapshot = IngestionOrchestrator.load_snapshot()
    if cached_snapshot:
        logger.info("[*] Pre-caricamento di %d bandi da snapshot autentico (boot <50ms)...", len(cached_snapshot))
        service.swap_grants_atomic(cached_snapshot)

    logger.info("[*] Avvio harvesting in background delle 31 fonti istituzionali...")
    app.state.harvest_task = asyncio.create_task(IngestionOrchestrator.harvest_all(service))
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
    title="LabNK Bandi Intelligence",
    description="Sovereign AI Grant Intelligence & Semantic Matching Platform — Nexus Keystone v1.1.0-Universal",
    version="1.1.0-Universal",
    lifespan=lifespan,
)

# Hardened CORS policy for stateless API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# ROUTES & ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, summary="Dashboard UI Root")
@app.get("/dashboard", response_class=HTMLResponse, summary="Dashboard UI")
def get_dashboard() -> HTMLResponse:
    """Restituisce l'interfaccia utente HTML interattiva e reattiva della Dashboard LabNK."""
    html_content = DashboardRenderer.render_html(service)
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/health", summary="Health Check")
def health_check() -> Dict[str, str]:
    """Health check endpoint per monitoraggio e telemetria."""
    return {"status": "ok", "service": "LabNK Bandi Intelligence", "version": "1.1.0-Universal"}


@app.post(
    "/api/search/nlp",
    response_model=NLPSearchResponse,
    summary="Ricerca Semantica NLP & Matching Rating"
)
def search_nlp(req: NLPSearchRequest) -> NLPSearchResponse:
    """
    Esegue l'estrazione dell'intento semantico (regione, ATECO, beneficiari, budget),
    il filtraggio dei bandi e il calcolo deterministico del Match Score (0-100%).
    """
    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il parametro 'query' non può essere vuoto."
        )

    try:
        intent, ranked_grants, scores = service.search_nlp(req.query.strip(), profile=req.profile, top_k=req.top_k)
        results = [
            MatchResultItem(grant=g, score=s)
            for g, s in zip(ranked_grants, scores)
        ]
        return NLPSearchResponse(intent=intent, results=results)
    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante search_nlp [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante l'analisi semantica. Codice di riferimento: {error_id}"
        )


@app.post(
    "/api/sync/harvest",
    summary="Sincronizzazione & Harvesting Fonti Ufficiali"
)
@app.get(
    "/api/sync/harvest",
    summary="Sincronizzazione & Harvesting Fonti Ufficiali (GET)"
)
async def sync_harvest(
    wait: bool = Query(default=False, description="Se True esegue await e restituisce il report completo (HTTP 200)")
) -> Any:
    """
    Avvia la scansione e l'aggiornamento automatico dei bandi dalle 31 fonti
    istituzionali registrate nel registro SSOT (sources_registry.json).
    Restituisce HTTP 202 Accepted con job_id se wait=False per non bloccare il client.
    """
    try:
        from src_app.ingestion.orchestrator import IngestionOrchestrator

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
                    "message": "Harvesting già in corso in background."
                }
            )

        job_id = f"job-{uuid.uuid4().hex[:8]}"
        task = asyncio.create_task(IngestionOrchestrator.harvest_all(service))
        app.state.harvest_task = task

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "started",
                "job_id": job_id,
                "message": "Harvesting live avviato in background con successo."
            }
        )

    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante sync_harvest [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante la sincronizzazione delle fonti. Codice di riferimento: {error_id}"
        )


@app.get(
    "/api/sync/status",
    summary="Telemetria e Stato Ultimo Harvesting"
)
def sync_status() -> Dict[str, Any]:
    """Restituisce la telemetria dell'ultimo harvesting e lo stato attuale del motore di ingestion."""
    try:
        from src_app.ingestion.orchestrator import IngestionOrchestrator
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
            detail=f"Errore interno durante il recupero dello stato di sincronizzazione. Codice di riferimento: {error_id}"
        )


@app.post(
    "/api/search/parametric",
    response_model=ParametricSearchResponse,
    summary="Ricerca Parametrica Multi-Dimensionale"
)
def search_parametric(criteria: ParametricFilterCriteria) -> ParametricSearchResponse:
    """Esegue il filtraggio combinatorio per ATECO, Regione, Beneficiari, Agevolazione e Budget."""
    try:
        matched = service.search_parametric(criteria)
        return ParametricSearchResponse(results=matched, count=len(matched))
    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante search_parametric [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante il filtraggio parametrico. Codice di riferimento: {error_id}"
        )


@app.get(
    "/api/grants",
    response_model=GrantsListResponse,
    summary="Catalogo Completo Bandi CGM"
)
def list_grants() -> GrantsListResponse:
    """Restituisce la lista di tutti i bandi canonici indicizzati nel sistema."""
    try:
        all_grants = service.list_all_grants()
        return GrantsListResponse(grants=all_grants, total=len(all_grants))
    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante list_grants [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno durante il recupero del catalogo. Codice di riferimento: {error_id}"
        )


@app.post(
    "/api/documents/extract",
    response_model=ProcessedDocumentReport,
    summary="Elaborazione & Segmentazione Allegato Bando (PDF/P7M/ZIP)"
)
async def extract_document(
    file: UploadFile = File(..., description="File PDF, P7M o archivio ZIP da analizzare"),
    grant_id: Optional[str] = Form(default=None, description="ID bando facoltativo a cui associare il report")
) -> ProcessedDocumentReport:
    """
    Esegue l'unpacking, estrazione del testo e segmentazione semantica delle sezioni
    (Requisiti, Spese Finanziabili, Agevolazione, Scadenze) da allegati di bando.
    Applica streaming chunks e limite rigido di upload a 25 MB.
    """
    try:
        # Stream read with size boundary check to prevent memory exhaustion
        total_read = 0
        chunks = []
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Dimensione del file eccede il limite massimo consentito di {MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
                )
            chunks.append(chunk)

        if not chunks or total_read == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Il payload del file caricato è vuoto."
            )

        content = b"".join(chunks)
        filename = file.filename or "uploaded_document.bin"
        mime_type = file.content_type

        if grant_id:
            report = service.process_and_attach_document(
                grant_id=grant_id,
                doc_bytes=content,
                filename=filename,
                mime_type=mime_type
            )
        else:
            report = DocumentPipeline.process_document(
                raw_bytes=content,
                filename=filename,
                mime_type=mime_type
            )
        return report

    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante l'elaborazione del documento [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno del server durante l'elaborazione del documento. Codice di riferimento: {error_id}"
        )


# ---------------------------------------------------------------------------
# MAIN RUNNER
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("[*] Avvio LabNK Bandi Intelligence Server su http://127.0.0.1:8080")
    uvicorn.run(app, host="127.0.0.1", port=8080)
