"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Pydantic v2 Data Schemas & Validation Models
Civil Code Compliance: Art. 2424 & 2425 C.C.
Period-Object Architecture (Soluzione C)
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

class ExtractedValue(BaseModel):
    value: float
    confidence: float
    source_page: int
    source_snippet: str
    suggested_mapping: str = ""
    description: str = ""

class ManualInsertInput(BaseModel):
    label: str
    section: str
    category: str
    year: str = "FY2025"
    amount: float

    @field_validator('year', mode='before')
    def parse_year_string(cls, v):
        if isinstance(v, str) and v.startswith("FY"):
            return v
        if isinstance(v, (int, str)):
            return f"FY{v}"
        return "FY2025"

class ManualOverrideItem(BaseModel):
    account_code: str
    original_value: float
    override_value: float
    modified_by: Optional[str] = "HITL_USER"
    year: Optional[int] = None

class ExceptionItem(BaseModel):
    id: str
    description: str
    suggested_mapping: str
    year: int
    amount: float
    type: str
    confidence: Optional[float] = None
    selected: Optional[bool] = False
    source_file: Optional[str] = None

# --- NEW FILE REGISTRY & MULTI-FILE DELTA MODELS ---

class IngestedFileRecord(BaseModel):
    file_id: str
    filename: str
    file_type: str
    size_bytes: int
    extracted_items_count: int
    confidence_score: float
    upload_timestamp: Optional[str] = None
    detected_years: List[int] = Field(default_factory=list)
    document_type: str = "FULL_BILANCIO"

class FileRegistryState(BaseModel):
    active_files: List[IngestedFileRecord] = Field(default_factory=list)
    max_allowed_files: int = 4
    total_active_count: int = 0

class FileDeltaPayload(BaseModel):
    file_id: str
    filename: str
    detected_years: List[int] = Field(default_factory=list)
    ce_delta: Dict[str, Any] = Field(default_factory=dict)
    sp_delta: Dict[str, Any] = Field(default_factory=dict)
    subitems_delta: List[Dict[str, Any]] = Field(default_factory=list)
    exceptions: List[ExceptionItem] = Field(default_factory=list)

class BoundedHorizonConfig(BaseModel):
    max_visible_years: int = 5
    visible_years: List[int] = Field(default_factory=list)
    all_years: List[int] = Field(default_factory=list)
    has_gaps: bool = False
    gap_years: List[int] = Field(default_factory=list)

class MultiFileBatchResponse(BaseModel):
    is_success: bool = True
    total_files: int = 0
    active_files_count: int = 0
    ingested_files: List[IngestedFileRecord] = Field(default_factory=list)
    cumulative_registry: List[IngestedFileRecord] = Field(default_factory=list)
    exceptions_queue: List[ExceptionItem] = Field(default_factory=list)
    combined_extracted_data: Dict[str, Any] = Field(default_factory=dict)
    detected_years: List[int] = Field(default_factory=list)
    message: str = "Batch ingestion completata con successo"

# --- SINGLE YEAR PERIOD-OBJECT MODELS (SOLUZIONE C) ---

class ContoEconomicoSingleYear(BaseModel):
    ricaviVendite: float = 0.0
    variazRimanenze: float = 0.0
    variazLavoriCorso: float = 0.0
    lavoriInterni: float = 0.0
    altriRicavi: float = 0.0
    costiMaterieHosting: float = 0.0
    costiServiziMarketing: float = 0.0
    costiGodimentoBeni: float = 0.0
    salariStipendi: float = 0.0
    oneriSociali: float = 0.0
    tfrQuota: float = 0.0
    ammImmateriali: float = 0.0
    ammMateriali: float = 0.0
    svalutazioneCrediti: float = 0.0
    oneriDiversi: float = 0.0
    proventiFinanziari: float = 0.0
    oneriFinanziari: float = 0.0
    proventiStraordinari: Optional[float] = Field(default=0.0, description="[LEGACY D.Lgs. 139/2015 DEPRECATED] Area E Soppressa")
    imposteReddito: float = 0.0
    imposteIres: float = 0.0
    imposteIrap: float = 0.0

class StatoPatrimonialeSingleYear(BaseModel):
    capitaleSociale: float = 0.0
    immaterialiLorde: float = 0.0
    materialiLorde: float = 0.0
    finanziarieDepositi: float = 0.0
    rimanenze: float = 0.0
    creditiClienti: float = 0.0
    creditiTributari: float = 0.0
    cassa: float = 0.0
    rateiAttivi: float = 0.0
    patrimonioNetto: float = 0.0
    riservaLegale: float = 0.0
    riserveUtili: float = 0.0
    fondiRischi: float = 0.0
    tfrFondo: float = 0.0
    debBanche: float = 0.0
    debFornitori: float = 0.0
    debTrib: float = 0.0
    debPrev: float = 0.0
    rateiPassivi: float = 0.0

class YearRecord(BaseModel):
    year: int
    data_type: Literal["actual", "forecast", "budget"] = "actual"
    ce: ContoEconomicoSingleYear = Field(default_factory=ContoEconomicoSingleYear)
    sp: StatoPatrimonialeSingleYear = Field(default_factory=StatoPatrimonialeSingleYear)
    source_documents: List[str] = Field(default_factory=list)
    last_modified: Optional[str] = None

class MultiYearModel(BaseModel):
    base_year: int = 2025
    records: Dict[int, YearRecord] = Field(default_factory=dict)
    manualOverrides: Dict[str, ManualOverrideItem] = Field(default_factory=dict)

class ProjectionDrivers(BaseModel):
    revenue_growth_rate: float = 0.05
    ebitda_margin_target: Optional[float] = None
    capex_pct_revenue: float = 0.03

class CorkscrewError(BaseModel):
    year: int
    error_type: str  # "GAP_ANNI_NON_CONSECUTIVI" | "MISMATCH_CHIUSURA_APERTURA" | "WARNING"
    account_name: str
    expected_value: float
    actual_value: float
    delta: float
    message: str

class CorkscrewValidationResult(BaseModel):
    is_valid: bool = True
    errors: List[CorkscrewError] = Field(default_factory=list)

# --- BACKWARD COMPATIBILITY INPUT MODELS (v0.9 ARRAY SUPPORT) ---

class ContoEconomicoInput(BaseModel):
    ricaviVendite: List[float] = Field(default_factory=lambda: [0.0]*5, description="A.1 Ricavi delle vendite")
    altriRicavi: List[float] = Field(default_factory=lambda: [0.0]*5, description="A.5 Altri ricavi e proventi")
    costiMaterieHosting: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.6 Costi per materie prime / hosting SaaS")
    costiServiziMarketing: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.7 Costi per servizi e marketing")
    costiGodimentoBeni: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.8 Costi godimento beni di terzi")
    salariStipendi: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.9.a Salari e stipendi dipendenti")
    oneriSociali: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.9.b Oneri sociali INPS/INAIL")
    tfrQuota: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.9.c Quota TFR maturata d'esercizio OIC")
    ammImmateriali: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.10.a Ammortamento immobilizzazioni immateriali")
    ammMateriali: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.10.b Ammortamento immobilizzazioni materiali")
    svalutazioneCrediti: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.10.c Svalutazione crediti")
    oneriDiversi: List[float] = Field(default_factory=lambda: [0.0]*5, description="B.14 Oneri diversi di gestione")
    proventiFinanziari: List[float] = Field(default_factory=lambda: [0.0]*5, description="C.16 Proventi finanziari")
    oneriFinanziari: List[float] = Field(default_factory=lambda: [0.0]*5, description="C.17 Oneri finanziari / Interessi passivi")

    @field_validator('*', mode='before')
    def ensure_five_length(cls, v):
        if isinstance(v, list):
            if len(v) < 5:
                v = v + [0.0] * (5 - len(v))
            return [float(x) for x in v[:5]]
        return [0.0] * 5

class StatoPatrimonialeInput(BaseModel):
    capitaleSociale: float = Field(default=10000.0, description="Art. 2424 C.C. Passivo A.I Capitale Sociale")
    immaterialiLorde: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo B.I Immobilizzazioni Immateriali")
    materialiLorde: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo B.II Immobilizzazioni Materiali")
    finanziarieDepositi: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo B.III Immobilizzazioni Finanziarie")
    rimanenze: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo C.I Rimanenze")
    creditiClienti: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo C.II.1 Crediti verso Clienti DSO 30g")
    creditiTributari: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo C.II.5 Crediti Tributari IVA/IRES")
    cassa: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo C.IV Disponibilità Liquide / Cassa Banca")
    rateiAttivi: List[float] = Field(default_factory=lambda: [0.0]*5, description="Attivo D Ratei e Risconti Attivi")
    patrimonioNetto: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo A Patrimonio Netto Totale")
    riservaLegale: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo A.IV Riserva Legale")
    riserveUtili: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo A.VI Riserve Utili a nuovo")
    fondiRischi: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo B Fondi per Rischi ed Oneri")
    tfrFondo: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo C Fondo TFR Accumulato Lavoratori")
    debBanche: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo D.4 Debiti verso Banche")
    debFornitori: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo D.7 Debiti verso Fornitori DPO 30-60g")
    debTrib: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo D.12 Debiti Tributari IRES/IRAP")
    debPrev: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo D.13 Debiti verso Istituti Previdenziali")
    rateiPassivi: List[float] = Field(default_factory=lambda: [0.0]*5, description="Passivo E Ratei e Risconti Passivi")

    @field_validator('immaterialiLorde', 'materialiLorde', 'finanziarieDepositi', 'rimanenze', 'creditiClienti', 'creditiTributari', 'cassa', 'rateiAttivi', 'patrimonioNetto', 'riservaLegale', 'riserveUtili', 'fondiRischi', 'tfrFondo', 'debBanche', 'debFornitori', 'debTrib', 'debPrev', 'rateiPassivi', mode='before')
    def ensure_five_length_sp(cls, v):
        if isinstance(v, list):
            if len(v) < 5:
                v = v + [0.0] * (5 - len(v))
            return [float(x) for x in v[:5]]
        return [0.0] * 5

class FullFinancialInput(BaseModel):
    manualOverrides: Dict[str, ManualOverrideItem] = Field(default_factory=dict)
    ce: ContoEconomicoInput = Field(default_factory=ContoEconomicoInput)
    sp: StatoPatrimonialeInput = Field(default_factory=StatoPatrimonialeInput)

# --- OUTPUT MODELS ---

class YearFinancialOutput(BaseModel):
    year: int
    data_type: str = "actual"
    valoreProduzione: float
    costiProduzione: float
    ebitda: float
    ebitdaMarginPct: float
    ammortamentiTotali: float
    ebit: float
    ebt: float
    imposteTotali: float
    utileNetto: float
    cassaFineAnno: float
    patrimonioNetto: float
    totaleAttivo: float
    totalePassivoNetto: float
    isQuadrato: bool
    dscr: float
    solvencyRatio: float

class FullCalculationOutput(BaseModel):
    manualOverrides: Dict[str, ManualOverrideItem] = Field(default_factory=dict)
    isSuccess: bool = True
    message: str = "Calcolo deterministico eseguito con successo"
    years: List[YearFinancialOutput]
    kpis: Dict[str, Any]
    corkscrewValidation: Optional[CorkscrewValidationResult] = None

class ParsingResult(BaseModel):
    manualOverrides: Dict[str, ManualOverrideItem] = Field(default_factory=dict)
    ledger: List[YearFinancialOutput]
    exceptions_queue: List[ExceptionItem]

class IngestedFileMetadata(BaseModel):
    filename: str
    file_type: str
    size_bytes: int
    extracted_items_count: int
    confidence_score: float

class IngestionResult(BaseModel):
    is_success: bool
    ingested_files: List[IngestedFileMetadata]
    exceptions_queue: List[ExceptionItem]
    extracted_data: Dict[str, Any]
    pivot_year: int = 2025
    has_comparative_year: bool = True
    detected_years: List[int] = Field(default_factory=lambda: [2025, 2024])
    extracted_data_previous_year: Optional[Dict[str, Any]] = None
