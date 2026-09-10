"""Parametric Multidimensional Search Filter for Consultants.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Set
from pydantic import BaseModel, Field, model_validator
from ..models.cgm import CanonicalGrantModel, BandoStato
from .ateco_tree import AtecoTree


ALLOWED_SHORT_TOKENS: Set[str] = {
    "ted", "ai", "ue", "ia", "5g", "3d", "4.0", "5.0", "h2", "eu", "ip", "it", "ict", "esg", "pmi", "zes"
}


def strip_accents(text: str) -> str:
    """Rimuove accenti e diacritici per comparazioni flessibili e resilienti."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


@lru_cache(maxsize=2048)
def _get_words_and_stems(text_clean: str) -> Tuple[frozenset, frozenset]:
    """Estrae e memorizza in cache le parole e gli stem per il matching morfologico."""
    words = frozenset(re.findall(r"\b\w+\b", text_clean))
    stems = frozenset(w[:-1] for w in words if len(w) >= 5)
    return words, stems


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
    # Caching e word boundary lookup
    words, stems = _get_words_and_stems(text_clean)
    if len(t_clean) >= 5:
        stem = t_clean[:-1]
        if stem in stems:
            return True
        if (t_clean.endswith("ico") or t_clean.endswith("ica") or t_clean.endswith("ici") or t_clean.endswith("iche")) and len(t_clean) >= 6:
            ic_stem = t_clean[:-3] + "ic"
            if any(w.startswith(ic_stem) for w in words):
                return True
    return False


def normalize_ateco_code_str(code: str) -> str:
    """Rimuove prefissi di sezione alfabetici e punti iniziali (es. 'C.28' -> '28', 'J.62' -> '62')."""
    if not code:
        return ""
    c = code.strip()
    if re.match(r"^[A-Za-z]\.?[0-9]", c):
        c = re.sub(r"^[A-Za-z]\.?", "", c)
    return c


def _normalize_tipo_text(text: Optional[str]) -> str:
    """Normalizza testo per matching tipologia agevolazione: rimozione accenti, snake_case e apostrofi."""
    if not text:
        return ""
    t = strip_accents(text.lower().replace("_", " ").strip())
    # Normalizza 'credito d'imposta' o 'credito d imposta' -> 'credito imposta'
    t = re.sub(r"\bd['’\s]?imposta\b", "imposta", t)
    t = re.sub(r"['’]", " ", t)
    return " ".join(t.split())


def matches_tipo_agevolazione(
    requested: str,
    actual: Optional[str],
    context_text: Optional[str] = None
) -> bool:
    """
    Matching normalizzato e flessibile per tipologia di agevolazione:
    - Normalizza snake_case ('_') e spazi.
    - Gestisce apostrofi e accenti ('credito d'imposta' <-> 'credito imposta').
    - Mappa 'fondo perduto' <-> 'grant', 'blended finance', 'blended equity', 'contributo', 'sovvenzione'.
    - Mappa 'voucher' <-> 'voucher', 'ticket', e consenti match se context_text contiene 'brevetti', 'proprietà intellettuale' o 'voucher'.
    - Mappa 'finanziamento agevolato' <-> 'finanziamento', 'tasso zero', 'tasso agevolato', 'rotazione', 'fondo rotativo'.
    - Mappa 'credito imposta' <-> 'credito d'imposta', 'iperammortamento', 'superammortamento', 'tax credit'.
    - Mappa 'grant ed equity' / 'blended'.
    """
    req = _normalize_tipo_text(requested)
    act = _normalize_tipo_text(actual)

    # 1. Mappa 'voucher' / 'ticket' e Brevetti Plus
    if any(term in req for term in ["voucher", "ticket"]):
        if any(term in act for term in ["voucher", "ticket"]):
            return True
        if "brevetti" in act:
            return True
        if context_text:
            ctx_norm = strip_accents(context_text.lower()).replace("'", " ").replace("’", " ")
            if any(term in ctx_norm for term in ["brevetti", "proprieta intellettuale", "voucher", "ticket"]):
                return True

    if not act:
        return False

    # 2. Match diretto substring (dopo normalizzazione snake_case e apostrofi)
    if req in act or act in req:
        return True

    # 3. Mappa 'grant ed equity' / 'blended'
    if any(term in req for term in ["grant ed equity", "grant e equity", "equity", "blended"]):
        if any(term in act for term in ["equity", "blended"]) or ("grant" in act and "equity" in act):
            return True

    # 4. Mappa 'credito imposta' <-> 'credito d\'imposta', 'iperammortamento'
    if any(term in req for term in ["credito imposta", "iperammortamento", "superammortamento", "tax credit"]):
        if any(term in act for term in ["credito imposta", "iperammortamento", "superammortamento", "tax credit"]):
            return True

    # 5. Mappa 'finanziamento agevolato' <-> 'finanziamento', 'tasso zero', 'tasso agevolato', 'rotazione'
    if any(term in req for term in ["finanziamento agevolato", "finanziamento", "tasso zero", "tasso agevolato", "rotazione", "agevolato"]):
        if any(term in act for term in ["finanziamento", "tasso zero", "tasso agevolato", "agevolato", "rotazione", "fondo rotativo", "rotativo"]):
            return True

    # 6. Mappa 'fondo perduto' <-> 'grant', 'blended finance', 'blended equity', 'contributo', 'sovvenzione'
    if any(term in req for term in ["fondo perduto", "grant", "blended finance", "blended equity", "blended", "contributo", "sovvenzione"]):
        if any(term in act for term in ["fondo perduto", "grant", "blended finance", "blended equity", "blended", "contributo", "sovvenzione"]):
            return True

    return False


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
            # normalizza ateco_codes se presenti (es. 'C.28' -> '28')
            if "ateco_codes" in data and isinstance(data["ateco_codes"], list):
                data["ateco_codes"] = [normalize_ateco_code_str(c) for c in data["ateco_codes"] if c]
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
            # normalizza tipo_agevolazione se presente (snake_case -> spazio)
            if "tipo_agevolazione" in data and isinstance(data["tipo_agevolazione"], str):
                data["tipo_agevolazione"] = data["tipo_agevolazione"].replace("_", " ").strip()
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
                clean_criteria_codes = [normalize_ateco_code_str(c) for c in criteria.ateco_codes if c]
                bando_sectors = g.settori_beneficiari or ["TUTTI"]
                matched_ateco = AtecoTree.is_code_compatible(bando_sectors, clean_criteria_codes)
                if not matched_ateco:
                    div_criteria = []
                    for c in clean_criteria_codes:
                        if '.' in c:
                            div_criteria.append(c.split('.')[0])
                        elif len(c) == 2 and c.isdigit():
                            div_criteria.append(c)
                    div_bando = []
                    for s in bando_sectors:
                        if '.' in s:
                            div_bando.append(s.split('.')[0])
                        elif len(s) == 2 and s.isdigit():
                            div_bando.append(s)
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

            # 5. Filtro Tipologia Agevolazione (matching flessibile con context_text)
            if criteria.tipo_agevolazione:
                context_info = f"{g.titolo} {g.descrizione or ''}"
                if not matches_tipo_agevolazione(
                    criteria.tipo_agevolazione,
                    g.tipo_agevolazione,
                    context_text=context_info
                ):
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

            # 8. Filtro Testo Libero (matching morfologico flesso con stem, accenti e token brevi)
            if criteria.search_text:
                raw_words = criteria.search_text.strip().split()
                terms = [
                    w.lower().strip() for w in raw_words
                    if len(w.strip()) > 2 or w.lower().strip() in ALLOWED_SHORT_TOKENS or len(w.strip()) >= 2
                ]
                if terms:
                    text_blob = f"{g.titolo} {g.ente_erogatore} {g.descrizione or ''} {g.tipo_agevolazione or ''} {g.fonte_nome or ''} {g.bando_id or ''}"
                    if not any(match_token(t, text_blob) for t in terms):
                        continue

            matched.append(g)

        return matched
