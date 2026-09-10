"""Smart NLP Intent Extractor for Conversational Grant Search.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from .ateco_tree import AtecoTree


class SearchIntent(BaseModel):
    """Rappresentazione strutturata dell'intento di ricerca estratto da un prompt conversazionale."""
    model_config = {"extra": "forbid"}

    raw_query: str
    inferred_ateco_codes: List[str] = Field(default_factory=list)
    inferred_jurisdiction: Optional[str] = None
    inferred_region: Optional[str] = None
    inferred_nuts: Optional[str] = None
    inferred_beneficiary_types: List[str] = Field(default_factory=list)
    inferred_funding_types: List[str] = Field(default_factory=list)
    inferred_budget: Optional[float] = None
    extracted_keywords: List[str] = Field(default_factory=list)
    has_eu_intent: bool = False


class SmartIntentExtractor:
    """
    Estrattore di intenti in linguaggio naturale che trasforma le richieste delle startup
    e delle PMI in query strutturate e parametri di matching.
    """

    LOCATION_MAP: Dict[str, Tuple[str, str]] = {
        "lombardia": ("Lombardia", "ITC4"),
        "milano": ("Lombardia", "ITC4C"),
        "campania": ("Campania", "ITF3"),
        "napoli": ("Campania", "ITF33"),
        "salerno": ("Campania", "ITF35"),
        "lazio": ("Lazio", "ITI4"),
        "roma": ("Lazio", "ITI43"),
        "piemonte": ("Piemonte", "ITC1"),
        "torino": ("Piemonte", "ITC11"),
        "veneto": ("Veneto", "ITH3"),
        "venezia": ("Veneto", "ITH35"),
        "verona": ("Veneto", "ITH31"),
        "belluno": ("Veneto", "ITH33"),
        "emilia-romagna": ("Emilia-Romagna", "ITH5"),
        "emilia romagna": ("Emilia-Romagna", "ITH5"),
        "emilia": ("Emilia-Romagna", "ITH5"),
        "romagna": ("Emilia-Romagna", "ITH5"),
        "bologna": ("Emilia-Romagna", "ITH55"),
        "faenza": ("Emilia-Romagna", "ITH57"),
        "toscana": ("Toscana", "ITI1"),
        "firenze": ("Toscana", "ITI14"),
        "prato": ("Toscana", "ITI15"),
        "puglia": ("Puglia", "ITF4"),
        "bari": ("Puglia", "ITF47"),
        "taranto": ("Puglia", "ITF43"),
        "foggia": ("Puglia", "ITF46"),
        "sicilia": ("Sicilia", "ITG1"),
        "palermo": ("Sicilia", "ITG12"),
        "calabria": ("Calabria", "ITF6"),
        "sardegna": ("Sardegna", "ITG2"),
        "cagliari": ("Sardegna", "ITG27"),
        "liguria": ("Liguria", "ITC3"),
        "genova": ("Liguria", "ITC33"),
        "marche": ("Marche", "ITI3"),
        "ancona": ("Marche", "ITI32"),
        "abruzzo": ("Abruzzo", "ITF1"),
        "friuli-venezia giulia": ("Friuli-Venezia Giulia", "ITH4"),
        "friuli venezia giulia": ("Friuli-Venezia Giulia", "ITH4"),
        "friuli": ("Friuli-Venezia Giulia", "ITH4"),
        "udine": ("Friuli-Venezia Giulia", "ITH42"),
        "trieste": ("Friuli-Venezia Giulia", "ITH44"),
        "trentino-alto adige": ("Trentino-Alto Adige", "ITH2"),
        "trentino alto adige": ("Trentino-Alto Adige", "ITH2"),
        "trentino": ("Trentino-Alto Adige", "ITH2"),
        "umbria": ("Umbria", "ITI2"),
        "perugia": ("Umbria", "ITI21"),
        "foligno": ("Umbria", "ITI22"),
        "basilicata": ("Basilicata", "ITF5"),
        "molise": ("Molise", "ITF2"),
        "valle d'aosta": ("Valle d'Aosta", "ITC2"),
        "valle daosta": ("Valle d'Aosta", "ITC2"),
        "aosta": ("Valle d'Aosta", "ITC20"),
        "mezzogiorno": ("Campania", "ITF"),
        "sud": ("Campania", "ITF")
    }

    BENEFICIARY_MAP: Dict[str, str] = {
        "startup": "Startup_Innovative",
        "startup innovativa": "Startup_Innovative",
        "spin-off": "Enti_Ricerca",
        "spinoff": "Enti_Ricerca",
        "pmi": "PMI",
        "piccola impresa": "PMI",
        "media impresa": "PMI",
        "microimpresa": "PMI",
        "industria": "PMI",
        "grande impresa": "Grandi_Imprese",
        "ente di ricerca": "Enti_Ricerca",
        "università": "Enti_Ricerca",
        "professionista": "Professionisti",
        "freelance": "Professionisti"
    }

    FUNDING_MAP: Dict[str, str] = {
        "fondo perduto": "fondo_perduto",
        "contributo": "fondo_perduto",
        "voucher": "voucher",
        "grant": "fondo_perduto",
        "incentivi": "fondo_perduto",
        "credito imposta": "credito_imposta",
        "credito d'imposta": "credito_imposta",
        "tax credit": "credito_imposta",
        "tasso agevolato": "tasso_agevolato",
        "finanziamento": "tasso_agevolato",
        "garanzia": "garanzia"
    }

    @classmethod
    def extract_intent(cls, user_prompt: str) -> SearchIntent:
        """Estrae i parametri strutturati dal prompt in linguaggio naturale."""
        if not user_prompt:
            return SearchIntent(raw_query="")

        low_prompt = user_prompt.lower()

        ateco_codes = AtecoTree.infer_ateco_from_text(user_prompt)

        inferred_region = None
        inferred_nuts = None
        inferred_jurisdiction = None

        for loc_name, (region_name, nuts_code) in cls.LOCATION_MAP.items():
            if re.search(r"\b" + re.escape(loc_name) + r"\b", low_prompt):
                inferred_region = region_name
                inferred_nuts = nuts_code
                inferred_jurisdiction = "REG"
                break

        eu_pattern = r"\b(europa|europeo|europei|ue|horizon|eic|comunitario|bruxelles)\b"
        has_eu_intent = bool(re.search(eu_pattern, low_prompt))

        if not inferred_region:
            if has_eu_intent:
                inferred_jurisdiction = "EU"
                inferred_nuts = "EU"
            elif "italia" in low_prompt or "nazionale" in low_prompt or "ministero" in low_prompt or "mimit" in low_prompt:
                inferred_jurisdiction = "NAT"
                inferred_nuts = "IT"

        beneficiaries = set()
        for k, v in cls.BENEFICIARY_MAP.items():
            if re.search(r"\b" + re.escape(k) + r"\b", low_prompt):
                beneficiaries.add(v)
        if not beneficiaries:
            beneficiaries.add("PMI")

        funding_types = set()
        for k, v in cls.FUNDING_MAP.items():
            if re.search(r"\b" + re.escape(k) + r"\b", low_prompt):
                funding_types.add(v)
        if not funding_types:
            funding_types.add("fondo_perduto")

        inferred_budget = None
        budget_match = re.search(r"(\d+(?:[\.\,]\d+)?)\s*(?:k|mila|mila euro|€|euro|milioni)", low_prompt)
        if budget_match:
            raw_val = budget_match.group(1).replace(",", ".")
            try:
                base_num = float(raw_val)
                if "k" in low_prompt or "mila" in low_prompt:
                    inferred_budget = base_num * 1000.0
                elif "milion" in low_prompt:
                    inferred_budget = base_num * 1000000.0
                else:
                    inferred_budget = base_num
            except ValueError:
                pass

        clean_words = re.findall(r"\b[A-Za-z]{3,}\b", low_prompt)
        stopwords = {"cerco", "fondi", "bando", "bandi", "per", "una", "uno", "con", "nel", "nella", "del", "della", "fare", "aprire"}
        keywords = [w for w in clean_words if w not in stopwords]

        return SearchIntent(
            raw_query=user_prompt,
            inferred_ateco_codes=ateco_codes,
            inferred_jurisdiction=inferred_jurisdiction,
            inferred_region=inferred_region,
            inferred_nuts=inferred_nuts,
            inferred_beneficiary_types=list(beneficiaries),
            inferred_funding_types=list(funding_types),
            inferred_budget=inferred_budget,
            extracted_keywords=keywords,
            has_eu_intent=has_eu_intent
        )
