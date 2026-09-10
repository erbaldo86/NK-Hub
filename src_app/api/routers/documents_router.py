"""LabNK Documents Extraction Router.
Endpoints: POST /api/documents/extract.
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ...core.config import CHUNK_SIZE, MAX_UPLOAD_SIZE
from ...document_processing.document_pipeline import DocumentPipeline
from ...document_processing.models import ProcessedDocumentReport
from ...service.bandi_service import LabNKBandiService
from ..deps import get_service

logger = logging.getLogger("DocumentsRouter")

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post(
    "/extract",
    response_model=ProcessedDocumentReport,
    summary="Elaborazione & Segmentazione Allegato Bando (PDF/P7M/ZIP)",
)
async def extract_document(
    file: UploadFile = File(..., description="File PDF, P7M o archivio ZIP da analizzare"),
    grant_id: Optional[str] = Form(default=None, description="ID bando facoltativo a cui associare il report"),
    service: LabNKBandiService = Depends(get_service),
) -> ProcessedDocumentReport:
    """
    Esegue l'unpacking, estrazione del testo e segmentazione semantica delle sezioni
    (Requisiti, Spese Finanziabili, Agevolazione, Scadenze) da allegati di bando.
    Applica streaming chunks e limite rigido di upload a 25 MB.
    """
    try:
        total_read = 0
        chunks: List[bytes] = []
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Dimensione del file eccede il limite massimo consentito di {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
                )
            chunks.append(chunk)

        if not chunks or total_read == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Il payload del file caricato è vuoto.",
            )

        content = b"".join(chunks)
        filename = file.filename or "uploaded_document.bin"
        mime_type = file.content_type

        if grant_id:
            report = service.process_and_attach_document(
                grant_id=grant_id,
                doc_bytes=content,
                filename=filename,
                mime_type=mime_type,
            )
        else:
            report = DocumentPipeline.process_document(
                raw_bytes=content,
                filename=filename,
                mime_type=mime_type,
            )
        return report

    except HTTPException:
        raise
    except Exception as exc:
        error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        logger.exception("Errore interno durante l'elaborazione del documento [%s]: %s", error_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore interno del server durante l'elaborazione del documento. Codice di riferimento: {error_id}",
        )
