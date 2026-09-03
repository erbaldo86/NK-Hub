"""Company Profile & Applicant Requirement Models for Grant Matching.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """Profilo aziendale per il calcolo del matching con i bandi."""
    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
        "validate_default": True
    }

    company_name: str = Field(..., description="Ragione sociale dell'impresa")
    legal_form: str = Field(default="SRL", description="Forma giuridica (SRL, SPA, SAS, Ditta_Individuale, Startup_Innovativa)")
    company_size: Literal["Micro", "Piccola", "Media", "Grande", "Startup_Innovative", "Ente_Ricerca", "Professionista", "PMI"] = Field(
        default="Piccola",
        description="Dimensione d'impresa secondo classificazione UE"
    )
    ateco_codes: List[str] = Field(
        default_factory=list,
        description="Codici ATECO primari e secondari (es. ['62.01.00', '72.19.09'])"
    )
    headquarters_nuts: str = Field(
        default="IT",
        description="Codice NUTS della sede legale/operativa (es. 'ITC4' per Lombardia, 'ITF3' per Campania)"
    )
    operational_region: str = Field(default="Tutte", description="Regione italiana prevalente")
    female_ownership: bool = Field(default=False, description="Impresa a prevalente partecipazione femminile")
    youth_ownership: bool = Field(default=False, description="Impresa a prevalente partecipazione giovanile (under 35)")
    de_minimis_accumulated_3yr: float = Field(
        default=0.0,
        ge=0.0,
        description="Totale aiuti in regime de minimis percepiti negli ultimi 3 anni fiscali in Euro"
    )
    target_investment_amount: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Budget preventivato per il progetto di investimento in Euro"
    )
    investment_categories: List[str] = Field(
        default_factory=list,
        description="Voci di investimento previste: beni_strumentali, software_ai, consulenza, r_and_d, sostenibilita_green"
    )


class MatchScoreBreakdown(BaseModel):
    """Dettaglio trasparente del calcolo di compatibilità tra profilo aziendale e bando."""
    model_config = {"extra": "forbid"}

    grant_id: str
    grant_title: str
    overall_match_score: float = Field(..., ge=0.0, le=100.0, description="Punteggio finale di idoneità (0 - 100%)")
    is_eligible: bool = Field(..., description="Flag che indica se l'impresa rispetta tutti i requisiti bloccanti")
    blocking_failures: List[str] = Field(default_factory=list, description="Motivazioni di ineleggibilità (es. ATECO non ammesso, De Minimis ecceduto)")
    criteria_scores: Dict[str, float] = Field(default_factory=dict, description="Punteggi parziali per criterio (ATECO, Territorialità, Dimensione, Budget)")
    bonus_points: List[str] = Field(default_factory=list, description="Premialità applicabili (es. Giovanile +10%, Transizione Green +5%)")
    recommended_actions: List[str] = Field(default_factory=list, description="Azioni consigliate per la candidatura")
