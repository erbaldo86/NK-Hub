"""Parametric Multidimensional Search Filter for Consultants.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import re
import unicodedata
from typing import List, Optional
from pydantic import BaseModel, Field
from ..models.cgm import CanonicalGrantModel, BandoStato
from .ateco_tree import AtecoTree


def strip_accents(text: str) -> str:
    """Rimuove accenti e diacritici per comparazioni flessibili e resilienti."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def match_token(tok: str, text: str) -> bool:
    """Helper di matching morfologico flesso per italiano (singolari/plurali e accenti)."""
    t_clean = strip_accents(tok.lower().strip())
    text_clean = strip_accents(text.lower())
    if not t_clean:
        return True
    if t_clean in text_clean:
        return True
    if len(t_clean) >= 5:
        # Rimuove desinenza singolare/plurale o/a/e/i (es. fotovoltaico/fotovoltaici -> fotovoltaic)
        stem = t_clean[:-1]
        if stem in text_clean:
            return True
        if (t_clean.endswith("ico") or t_clean.endswith("ica") or t_clean.endswith("ici") or t_clean.endswith("iche")) and len(t_clean) >= 6:
            if t_clean[:-3] + "ic" in text_clean:
                return True
    # Controllo per singole parole del testo
    words = re.findall(r"\b\w+\b", text_clean)
    for w in words:
        if len(w) >= 5 and len(t_clean) >= 5:
            if w[:-1] == t_clean[:-1]:
                return True
    return False


def matches_tipo_agevolazione(requested: str, actual: Optional[str]) -> bool:
    """Matching normalizzato e flessibile per tipologia di agevolazione."""
    if not actual:
        return False
    req = requested.lower().strip()
    act = actual.lower().strip()

    if req in act:
        return True
    if "voucher" in req and "voucher" in act:
        return True
    if "finanziamento agevolato" in req or "tasso agevolato" in req:
        if any(term in act for term in ["finanziamento", "tasso zero", "tasso agevolato", "agevolato"]):
            return True
    if "grant ed equity" in req or "grant e equity" in req or "equity" in req:
        if "equity" in act or ("grant" in act and "equity" in act) or "blended" in act:
            return True
    if "fondo perduto" in req and "fondo perduto" in act:
        return True
    if "credito d'imposta" in req or "credito imposta" in req:
        if "credito d'imposta" in act or "credito imposta" in act:
            return True
    return False


from pydantic import BaseModel, Field, model_validator


class ParametricFilterCriteria(BaseModel):
    """Criteri di filtro parametrico avanzato per consulenti e commercialisti."""
    model_config = {"extra": "ignore"}

    ateco_codes: List[str] = Field(default_factory=list, description="Elenco codici ATECO da verificare")
    regioni_target: List[str] = Field(default_factory=list, description="Regioni ammesse")
    tipologia_beneficiari: List[str] = Field(default_factory=list, description="Tipologie beneficiari (es. ['PMI', 'Startup_Innovative'])")
    tipo_agevolazione: Optional[str] = Field(default=None, description="Tipologia agevolazione (es. 'fondo_perduto')")
    min_budget: Optional[float] = Field(default=None, ge=0.0, description="Dotazione minima complessiva del bando in Euro")
    max_budget: Optional[float] = Field(default=None, ge=0.0, description="Dotazione massima")
    min_percentuale_copertura: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="% minima a fondo perduto")
    stato: Optional[BandoStato] = Field(default=BandoStato.APERTO, description="Stato operativo del bando")
    search_text: Optional[str] = Field(default=None, description="Testo di ricerca libera in titolo o descrizione")

    @model_validator(mode="before")
    @classmethod
    def map_convenience_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # ateco_code -> ateco_codes
            if "ateco_code" in data and data["ateco_code"] and "ateco_codes" not in data:
                data["ateco_codes"] = [data["ateco_code"]] if isinstance(data["ateco_code"], str) else data["ateco_code"]
            # region -> regioni_target
            if "region" in data and data["region"] and "regioni_target" not in data:
                reg_val = data["region"]
                if reg_val and str(reg_val).lower() != "tutte":
                    data["regioni_target"] = [reg_val] if isinstance(reg_val, str) else reg_val
            # beneficiary -> tipologia_beneficiari
            if "beneficiary" in data and data["beneficiary"] and "tipologia_beneficiari" not in data:
                data["tipologia_beneficiari"] = [data["beneficiary"]] if isinstance(data["beneficiary"], str) else data["beneficiary"]
            # aid_type -> tipo_agevolazione
            if "aid_type" in data and data["aid_type"] is not None and "tipo_agevolazione" not in data:
                data["tipo_agevolazione"] = data["aid_type"]
            # min_coverage -> min_percentuale_copertura
            if "min_coverage" in data and data["min_coverage"] is not None and "min_percentuale_copertura" not in data:
                data["min_percentuale_copertura"] = data["min_coverage"]
        return data


class ParametricFilter:
    """Motore di filtraggio combinatorio e multi-dimensionale su oggetti CanonicalGrantModel."""

    @classmethod
    def filter_grants(
        cls,
        grants: List[CanonicalGrantModel],
        criteria: ParametricFilterCriteria
    ) -> List[CanonicalGrantModel]:
        """Applica la combinazione di tutti i filtri parametrici e restituisce i bandi compatibili."""
        matched: List[CanonicalGrantModel] = []

        for g in grants:
            # 1. Filtro Stato
            if criteria.stato and g.stato != criteria.stato:
                continue

            # 2. Filtro ATECO / Settori (compatibilità gerarchica a livello foglia e divisione 2 cifre)
            if criteria.ateco_codes:
                bando_sectors = g.settori_beneficiari or ["TUTTI"]
                matched_ateco = AtecoTree.is_code_compatible(bando_sectors, criteria.ateco_codes)
                if not matched_ateco:
                    div_criteria = [c.split('.')[0] for c in criteria.ateco_codes if '.' in c]
                    div_bando = [s.split('.')[0] for s in bando_sectors if '.' in s]
                    if div_criteria and any(dc in div_bando for dc in div_criteria):
                        matched_ateco = True
                    elif div_criteria and AtecoTree.is_code_compatible(bando_sectors, div_criteria):
                        matched_ateco = True
                if not matched_ateco:
                    continue

            # 3. Filtro Territoriale (Regioni)
            if criteria.regioni_target:
                bando_regioni = [r.lower() for r in g.regioni_target]
                if "tutte" not in bando_regioni and "italia" not in bando_regioni and "nazionale" not in bando_regioni:
                    req_regioni = [r.lower() for r in criteria.regioni_target]
                    if not any(r in bando_regioni for r in req_regioni):
                        continue

            # 4. Filtro Beneficiari
            if criteria.tipologia_beneficiari:
                b_types = [b.lower() for b in g.tipologia_beneficiari]
                req_types = [t.lower() for t in criteria.tipologia_beneficiari]
                if not (set(b_types) & set(req_types)) and "pmi" not in b_types:
                    continue

            # 5. Filtro Tipologia Agevolazione (matching flessibile)
            if criteria.tipo_agevolazione:
                if not matches_tipo_agevolazione(criteria.tipo_agevolazione, g.tipo_agevolazione):
                    continue

            # 6. Filtro Budget Totale
            if criteria.min_budget is not None and g.budget_totale is not None:
                if g.budget_totale < criteria.min_budget:
                    continue
            if criteria.max_budget is not None and g.budget_totale is not None:
                if g.budget_totale > criteria.max_budget:
                    continue

            # 7. Filtro % Copertura
            if criteria.min_percentuale_copertura is not None and g.percentuale_copertura is not None:
                if g.percentuale_copertura < criteria.min_percentuale_copertura:
                    continue

            # 8. Filtro Testo Libero (matching morfologico flesso con stem e accenti)
            if criteria.search_text:
                terms = [w.lower() for w in criteria.search_text.strip().split() if len(w) > 2]
                if terms:
                    text_blob = f"{g.titolo} {g.ente_erogatore} {g.descrizione or ''} {g.tipo_agevolazione or ''}"
                    if not any(match_token(t, text_blob) for t in terms):
                        continue

            matched.append(g)

        return matched
