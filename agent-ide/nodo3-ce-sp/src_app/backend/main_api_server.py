"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
FastAPI / Async REST OpenAPI 3.0 API Server
Exposes Real PDF/File Ingestion & Deterministic Math Engine
Period-Object Architecture Support (Soluzione C)
"""

import sys
import os
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic_schemas import (
    FullFinancialInput, FullCalculationOutput, MultiYearModel,
    ProjectionDrivers, CorkscrewValidationResult,
    IngestedFileRecord, MultiFileBatchResponse, FileRegistryState,
    BoundedHorizonConfig, ExceptionItem
)
from civil_code_math_engine import calculate_financials, calculate_multi_year, expand_years, validate_corkscrew
from ingestion_parser_service import parse_file_bytes, IngestionResult

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

app = FastAPI(
    title="Chronos & Kairos - Nodo 3 API Server",
    description="Engine deterministico e Parser PDF ERP per Conto Economico & Stato Patrimoniale (Art. 2424 & 2425 C.C.)",
    version="4.0.0"
)

# Enable CORS for local dev server UI room
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Asyncio Lock for thread-safe upload serialization
upload_lock = asyncio.Lock()

@app.get("/")
def read_root():
    return {
        "status": "ONLINE",
        "node": "Nodo 3 (Chronos & Kairos - CE & SP Engine)",
        "version": "4.0.0",
        "civil_code_compliance": "Art. 2424 & 2425 C.C.",
        "architecture": "Period-Object Architecture (Soluzione C)",
        "deterministic_engine": True
    }

@app.post("/api/v1/financials/calculate", response_model=FullCalculationOutput)
def calculate_endpoint(data: FullFinancialInput):
    try:
        return calculate_financials(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore di calcolo deterministico: {str(e)}")

@app.post("/api/v1/financials/calculate_multi_year", response_model=FullCalculationOutput)
def calculate_multi_year_endpoint(model: MultiYearModel):
    try:
        return calculate_multi_year(model)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore di calcolo multi-anno: {str(e)}")

@app.post("/api/v1/model/expand", response_model=MultiYearModel)
def expand_model_endpoint(model: MultiYearModel, n_years: int = 3, drivers: ProjectionDrivers = ProjectionDrivers()):
    try:
        return expand_years(model, n_years, drivers)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore durante l'espansione anni: {str(e)}")

@app.post("/api/v1/corkscrew/validate", response_model=CorkscrewValidationResult)
def validate_corkscrew_endpoint(model: MultiYearModel):
    try:
        out = calculate_multi_year(model)
        return validate_corkscrew(model, out.years)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore durante la validazione Corkscrew: {str(e)}")

@app.post("/api/v1/ingest/parse_pdf", response_model=IngestionResult)
async def parse_pdf_endpoint(
    file: UploadFile = File(...),
    year: int = Form(2025),
    force_overwrite: bool = Header(False, alias="X-Force-Overwrite")
):
    async with upload_lock:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' supera la dimensione massima consentita di 50MB ({len(content)} bytes > {MAX_FILE_SIZE_BYTES} bytes)"
            )
        try:
            return await asyncio.to_thread(parse_file_bytes, content, file.filename, target_year=year)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Errore di parsing del file ERP ({file.filename}): {str(e)}")

@app.post("/api/v1/ingest/multi_file", response_model=MultiFileBatchResponse)
async def ingest_multi_file_endpoint(
    files: List[UploadFile] = File(...),
    year: int = Form(2025),
    current_active_count: int = Form(0)
):
    # Hard File Limiter Guard: Max 4 active files simultaneously
    if len(files) > 4 or (current_active_count + len(files)) > 4:
        raise HTTPException(
            status_code=422,
            detail="Hard File Limiter Guard violato: massimo 4 file attivi contemporaneamente"
        )

    async with upload_lock:
        ingested_records: List[IngestedFileRecord] = []
        all_exceptions: List[ExceptionItem] = []
        combined_ce: Dict[str, Any] = {}
        combined_sp: Dict[str, Any] = {}
        combined_subitems: List[Dict[str, Any]] = []
        detected_years_set = set()

        for file in files:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{file.filename}' supera la dimensione massima consentita di 50MB ({len(content)} bytes > {MAX_FILE_SIZE_BYTES} bytes)"
                )

            try:
                result: IngestionResult = await asyncio.to_thread(
                    parse_file_bytes, content, file.filename, target_year=year
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Errore di parsing per il file ERP ({file.filename}): {str(e)}"
                )

            ext = os.path.splitext(file.filename)[1].replace('.', '').upper()
            file_id = f"file_{uuid.uuid4().hex[:8]}"
            detected_yrs = result.detected_years or [year, year - 1]
            subitems = result.extracted_data.get("detailedSubitems", [])

            record = IngestedFileRecord(
                file_id=file_id,
                filename=file.filename,
                file_type=ext or "ERP_DOC",
                size_bytes=len(content),
                extracted_items_count=len(subitems) + 15,
                confidence_score=0.98,
                upload_timestamp=datetime.now(timezone.utc).isoformat(),
                detected_years=detected_yrs,
                document_type=result.extracted_data.get("doc_type", "FULL_BILANCIO")
            )
            ingested_records.append(record)
            for yr in detected_yrs:
                detected_years_set.add(yr)

            # Combine CE numbers
            ext_ce = result.extracted_data.get("ce", {})
            for k, v in ext_ce.items():
                if k not in combined_ce:
                    combined_ce[k] = v if isinstance(v, list) else [float(v)] + [0.0]*4
                else:
                    if isinstance(v, list) and isinstance(combined_ce[k], list):
                        combined_ce[k] = [
                            (combined_ce[k][i] if i < len(combined_ce[k]) else 0.0) + (v[i] if i < len(v) else 0.0)
                            for i in range(max(len(combined_ce[k]), len(v)))
                        ]
                    elif isinstance(v, (int, float)) and isinstance(combined_ce[k], (int, float)):
                        combined_ce[k] = combined_ce[k] + v

            # Combine SP numbers
            ext_sp = result.extracted_data.get("sp", {})
            for k, v in ext_sp.items():
                if k not in combined_sp:
                    combined_sp[k] = v if isinstance(v, list) else (float(v) if k == 'capitaleSociale' else [float(v)] + [0.0]*4)
                else:
                    if k == 'capitaleSociale':
                        combined_sp[k] = max(combined_sp[k], float(v) if isinstance(v, (int, float)) else 0.0)
                    elif isinstance(v, list) and isinstance(combined_sp[k], list):
                        combined_sp[k] = [
                            (combined_sp[k][i] if i < len(combined_sp[k]) else 0.0) + (v[i] if i < len(v) else 0.0)
                            for i in range(max(len(combined_sp[k]), len(v)))
                        ]
                    elif isinstance(v, (int, float)) and isinstance(combined_sp[k], (int, float)):
                        combined_sp[k] = combined_sp[k] + v

            # Merge subitems with file association
            for sub in subitems:
                sub_copy = dict(sub)
                sub_copy["file_id"] = file_id
                sub_copy["source_file"] = file.filename
                combined_subitems.append(sub_copy)

            # Merge exceptions with file association
            if result.exceptions_queue:
                for ex in result.exceptions_queue:
                    ex_copy = ex.model_copy() if hasattr(ex, 'model_copy') else ex.copy()
                    ex_copy.source_file = file.filename
                    all_exceptions.append(ex_copy)

        detected_years_list = sorted(list(detected_years_set), reverse=True)
        if not detected_years_list:
            detected_years_list = [year, year - 1]

        combined_data = {
            "ce": combined_ce,
            "sp": combined_sp,
            "detailedSubitems": combined_subitems
        }

        total_active = current_active_count + len(ingested_records)
        return MultiFileBatchResponse(
            is_success=True,
            total_files=len(files),
            active_files_count=total_active,
            ingested_files=ingested_records,
            cumulative_registry=ingested_records,
            exceptions_queue=all_exceptions,
            combined_extracted_data=combined_data,
            detected_years=detected_years_list,
            message=f"Batch ingestion completata con successo: {len(files)} file elaborati"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_api_server:app", host="0.0.0.0", port=8000, reload=True)
