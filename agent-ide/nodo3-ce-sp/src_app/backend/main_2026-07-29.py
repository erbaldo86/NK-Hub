import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationInfo, model_validator

# --- 1. Pydantic v2 Strict Models (Refiner) ---

class BaseStrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')

class InvoiceItem(BaseStrictModel):
    description: str = Field(..., min_length=1)
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    
    @property
    def total_amount(self) -> Decimal:
        return self.quantity * self.unit_price

class Invoice(BaseStrictModel):
    invoice_id: str = Field(..., min_length=1)
    issue_date: date
    due_date: date
    client_name: str = Field(..., min_length=1)
    items: List[InvoiceItem] = Field(default_factory=list)
    total_amount: Decimal = Field(..., ge=0)

    @field_validator('due_date')
    @classmethod
    def check_dates(cls, v: date, info: ValidationInfo) -> date:
        issue_date = info.data.get('issue_date')
        if issue_date and v < issue_date:
            raise ValueError('due_date cannot be earlier than issue_date')
        return v

class Transaction(BaseStrictModel):
    transaction_id: str = Field(..., min_length=1)
    transaction_date: date
    description: str = Field(..., min_length=1)
    amount: Decimal
    currency: str = Field(default="EUR", min_length=3, max_length=3)

class BankStatement(BaseStrictModel):
    account_id: str = Field(..., min_length=1)
    statement_date: date
    transactions: List[Transaction] = Field(default_factory=list)
    starting_balance: Decimal
    ending_balance: Decimal

class APIResponse(BaseStrictModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class BatchIngestRequest(BaseStrictModel):
    document_ids: List[str] = Field(..., min_length=1, description="List of document IDs to process")
    engine_mode: str = Field(default="auto", description="Processing mode: auto, primary, fallback")
    tenant_id: str = Field(..., description="Isolated tenant identifier")

class ExtractedAmounts(BaseStrictModel):
    imponibile: float = Field(..., ge=0.0)
    iva: float = Field(..., ge=0.0)
    totale: float = Field(..., ge=0.0)
    
    @model_validator(mode='after')
    def check_totals(self) -> 'ExtractedAmounts':
        # Tolleranza per arrotondamenti
        if abs((self.imponibile + self.iva) - self.totale) > 0.01:
            raise ValueError("Imponibile + IVA does not match totale")
        return self

class ExtractionResult(BaseStrictModel):
    document_id: str
    amounts: Optional[ExtractedAmounts] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    engine_used: str
    shadow_mapped: bool = False
    error: Optional[str] = None

class BatchIngestResponse(BaseStrictModel):
    batch_id: str
    results: List[ExtractionResult]
    overall_confidence: float

# --- 2. State & Locks (Defender) ---

class AccountingState:
    def __init__(self):
        self.doc_locks: Dict[str, asyncio.Lock] = {}

    def get_lock(self, doc_id: str) -> asyncio.Lock:
        if doc_id not in self.doc_locks:
            self.doc_locks[doc_id] = asyncio.Lock()
        return self.doc_locks[doc_id]

state = AccountingState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    state.doc_locks.clear()

app = FastAPI(
    title="AI-First Accounting Engine 2.0",
    description="Advanced accounting extraction with Dual Fallback Engine, Shadow Mapping & Concurrency Locks",
    version="2.0.0",
    lifespan=lifespan
)

# Strict Anti-Leakage Boundary: Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal System Error. Request cannot be processed securely."},
    )

# --- 3. Business Logic & Services (Architect) ---

class ShadowMappingService:
    async def map_document(self, document_id: str) -> Dict[str, Any]:
        # Simulated async shadow mapping operation
        await asyncio.sleep(0.1)
        return {"mapped": True, "shadow_id": f"shdw_{document_id}"}

class DualFallbackEngine:
    def __init__(self, shadow_mapper: ShadowMappingService):
        self.shadow_mapper = shadow_mapper
        
    async def process_primary(self, doc_id: str) -> ExtractionResult:
        await asyncio.sleep(0.1)
        return ExtractionResult(
            document_id=doc_id,
            amounts=ExtractedAmounts(imponibile=100.0, iva=22.0, totale=122.0),
            confidence_score=0.92,
            engine_used="primary"
        )
        
    async def process_fallback(self, doc_id: str) -> ExtractionResult:
        await asyncio.sleep(0.2)
        return ExtractionResult(
            document_id=doc_id,
            amounts=ExtractedAmounts(imponibile=100.0, iva=22.0, totale=122.0),
            confidence_score=0.75,
            engine_used="fallback",
            shadow_mapped=True
        )

    async def execute_extraction(self, doc_id: str, mode: str) -> ExtractionResult:
        lock = state.get_lock(doc_id)
        async with lock:
            try:
                # Esecuzione protetta dal lock di sistema asincrono
                if mode == "fallback":
                    result = await self.process_fallback(doc_id)
                else:
                    result = await self.process_primary(doc_id)
                    # Primary engine fallback threshold
                    if result.confidence_score < 0.8:
                        result = await self.process_fallback(doc_id)
                        
                if getattr(result, 'shadow_mapped', False) or result.engine_used == "fallback":
                    await self.shadow_mapper.map_document(doc_id)
                    result.shadow_mapped = True
                    
                return result
            except Exception as e:
                return ExtractionResult(
                    document_id=doc_id,
                    confidence_score=0.0,
                    engine_used="none",
                    error=str(e)
                )

def get_shadow_mapper() -> ShadowMappingService:
    return ShadowMappingService()

def get_extraction_engine(mapper: ShadowMappingService = Depends(get_shadow_mapper)) -> DualFallbackEngine:
    return DualFallbackEngine(mapper)

# --- 4. Routes ---

@app.post("/api/v1/ingest/batch", response_model=BatchIngestResponse)
async def ingest_batch(
    request: BatchIngestRequest,
    engine: DualFallbackEngine = Depends(get_extraction_engine)
):
    """
    Endpoint per l'estrazione atomica in batch.
    Esegue la scomposizione imponibile/IVA e calcola il confidenceScore
    usando il Dual Fallback Engine e lo Shadow Mapping.
    """
    try:
        # Wrap the whole batch with wait_for to prevent lock starvation globally
        tasks = [engine.execute_extraction(doc_id, request.engine_mode) for doc_id in request.document_ids]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=45.0)
        
        valid_scores = [r.confidence_score for r in results if r.error is None]
        overall_conf = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
        
        return BatchIngestResponse(
            batch_id=f"batch_{request.tenant_id}",
            results=results,
            overall_confidence=overall_conf
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Batch processing timeout."
        )
