"""ATECO Hierarchical Tree & Semantic Code Resolver.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import re
from typing import List, Dict, Optional, Set, Tuple


class AtecoTree:
    """
    Gestore gerarchico dell'albero codici ATECO 2007/2025 con risoluzione di prefisso,
    compatibilità multilivello e associazione semantica da parole chiave.
    """

    # Mappatura semantica parole chiave -> Codici ATECO / Divisioni
    KEYWORD_TO_ATECO: Dict[str, List[str]] = {
        "software": ["62.01.00", "62.02.00", "58.29.00", "63.11.00", "72.19.09"],
        "sviluppo software": ["62.01.00", "62.02.00", "58.29.00", "63.11.00", "72.19.09"],
        "informatica": ["62.01.00", "62.02.00", "63.11.00"],
        "ict": ["62.01.00", "62.09.09", "63.11.00"],
        "intelligenza artificiale": ["62.01.00", "72.19.09", "63.11.00", "62.09.09"],
        "ai": ["62.01.00", "72.19.09", "63.11.00"],
        "cloud": ["62.03.00", "63.11.00"],
        "cybersecurity": ["62.02.00", "62.09.09"],
        "e-commerce": ["47.91.10", "62.01.00"],
        "ecommerce": ["47.91.10", "62.01.00"],
        "commercio": ["47.91.10", "46.90.00"],
        "retail": ["47.91.10"],
        "digitale": ["62.01.00", "62.02.00", "63.11.00"],
        "digitalizzazione": ["62.01.00", "62.02.00"],
        "ricerca": ["72.19.09", "72.11.00"],
        "r&d": ["72.19.09", "72.11.00"],
        "biotecnologie": ["72.11.00", "21.20.00"],
        "biotecnologia": ["72.11.00", "21.20.00"],
        "biotech": ["72.11.00", "21.20.00"],
        "pharma": ["21.20.00", "72.11.00"],
        "farmaceutica": ["21.20.00"],
        "manifattura": ["25.00.00", "28.00.00", "30.00.00"],
        "manifatturiera": ["25.00.00", "28.00.00", "30.00.00"],
        "manifatturiero": ["25.00.00", "28.00.00", "30.00.00"],
        "industria 4.0": ["28.00.00", "25.00.00", "62.01.00"],
        "robotica": ["28.99.00", "28.00.00"],
        "meccanica": ["28.11.00", "28.99.00", "25.62.00"],
        "energia": ["35.11.00", "35.14.00", "71.12.10"],
        "energetico": ["35.11.00", "71.12.10"],
        "green": ["38.21.00", "39.00.00", "35.11.00"],
        "fotovoltaico": ["35.11.00", "43.21.01", "71.12.10"],
        "fotovoltaici": ["35.11.00", "43.21.01", "71.12.10"],
        "solare": ["35.11.00", "43.21.01", "71.12.10"],
        "inverter": ["35.11.00", "43.21.01", "71.12.10"],
        "pannelli solari": ["35.11.00", "43.21.01", "71.12.10"],
        "autoproduzione": ["35.11.00", "43.21.01", "71.12.10"],
        "rinnovabili": ["35.11.00", "43.21.01", "71.12.10"],
        "accumulo": ["35.11.00", "43.21.01"],
        "transizione energetica": ["35.11.00", "71.12.10"],
        "amianto": ["39.00.00", "43.99.09", "71.20.00"],
        "asbesto": ["39.00.00", "43.99.09", "71.20.00"],
        "bonifica": ["39.00.00", "43.99.09", "71.20.00"],
        "decontaminazione": ["39.00.00", "43.99.09", "71.20.00"],
        "rimozione amianto": ["39.00.00", "43.99.09", "71.20.00"],
        "coperture": ["43.99.09", "39.00.00"],
        "turismo": ["55.10.00", "55.20.51", "79.11.00"],
        "turistica": ["55.10.00", "55.20.51"],
        "alberghiera": ["55.10.00"],
        "ristorazione": ["56.10.11", "56.10.12"],
        "ristorante": ["56.10.11"],
        "agricoltura": ["01.11.00", "01.21.00", "01.50.00"],
        "agricola": ["01.11.00", "01.21.00"],
        "agritech": ["01.11.00", "01.21.00", "62.01.00"],
        "agroalimentare": ["10.39.00", "10.89.09"],
        "alimentare": ["10.39.00", "10.89.09"],
        "consulenza": ["70.22.09", "71.12.10", "69.20.10"],
        "ingegneria": ["71.12.10"],
        "artigianato": ["13.99.00", "14.13.00", "16.29.00", "23.70.00", "31.09.00", "32.12.00"],
        "artigianale": ["13.99.00", "14.13.00", "16.29.00", "23.70.00", "31.09.00"],
        "moda": ["13.10.00", "13.20.00", "14.13.00", "15.12.00"],
        "tessile": ["13.10.00", "13.20.00", "13.99.00"],
        "abbigliamento": ["14.13.00", "14.19.00"],
        "sicurezza": ["71.20.00", "84.30.00"],
        "inail": ["71.20.00", "84.30.00", "25.00.00"],
        "isi inail": ["71.20.00", "84.30.00", "25.00.00"],
        "automotive": ["29.10.00", "28.11.00", "25.62.00"],
        "aerospazio": ["30.30.00", "28.00.00"],
        "legno": ["16.29.00", "31.09.00"],
        "arredo": ["31.09.00", "16.29.00"],
        "arredamento": ["31.09.00", "16.29.00"],
        "medtech": ["32.50.11", "72.11.00", "21.20.00"],
        "salute": ["32.50.11", "72.11.00", "21.20.00"],
        "dispositivi medici": ["32.50.11", "72.11.00", "21.20.00"],
        "scienze della vita": ["72.11.00", "21.20.00", "72.19.09"],
        "sperimentazione clinica": ["72.11.00", "21.20.00"],
        "temporary export manager": ["70.22.09", "46.90.00", "73.11.00"],
        "tem": ["70.22.09", "46.90.00", "73.11.00"],
        "export": ["70.22.09", "46.90.00", "73.11.00"],
        "fiere estere": ["73.11.00", "70.22.09", "46.90.00"],
        "internazionalizzazione": ["70.22.09", "46.90.00", "73.11.00"],
        "consorzi export": ["70.22.09", "46.90.00", "73.11.00"],
        "idrogeno": ["29.10.00", "28.11.00", "25.62.00"],
        "veicoli elettrici": ["29.10.00", "28.11.00", "25.62.00"],
        "componenti auto": ["29.10.00", "28.11.00", "25.62.00"],
        "alberghi": ["55.10.00", "55.20.51", "79.11.00"],
        "strutture ricettive": ["55.10.00", "55.20.51", "79.11.00"],
        "hotel": ["55.10.00", "55.20.51", "79.11.00"],
        "packaging sostenibile": ["10.39.00", "10.89.09", "38.21.00"],
        "agroalimentare tipico": ["10.39.00", "10.89.09"],
        "food processing": ["10.39.00", "10.89.09", "10.51.00"],
        "arredo design": ["16.29.00", "31.09.00", "28.11.00"],
        "filiera legno": ["16.29.00", "31.09.00", "28.11.00"],
        "legno arredo": ["16.29.00", "31.09.00", "28.11.00"],
        "blended finance": ["TUTTI", "62.01.00", "72.19.09"],
        "equity": ["TUTTI", "62.01.00", "72.19.09"],
        "deep tech": ["TUTTI", "62.01.00", "72.19.09"],
        "audit infrastrutturale": ["62.01.00", "62.02.00", "62.03.00", "62.09.09"],
        "migrazione cloud": ["62.01.00", "62.02.00", "62.03.00", "62.09.09"],
        "sicurezza informatica": ["62.01.00", "62.02.00", "62.03.00", "62.09.09"],
        "brevetti": ["72.19.09", "71.12.10"],
        "proprietà intellettuale": ["72.19.09", "71.12.10", "70.22.09"],
        "marchi": ["72.19.09", "71.12.10"],
        "alimentari": ["10.39.00", "10.89.09"],
        "conserve": ["10.39.00", "10.89.09"],
        "packaging": ["10.39.00", "10.89.09"],
        "logistica": ["49.41.00", "52.10.10", "52.29.00"],
        "logistici": ["49.41.00", "52.10.10", "52.29.00"],
        "veicoli commerciali": ["49.41.00"],
        "circolare": ["38.32.20", "38.21.00"],
        "economia circolare": ["38.32.20", "38.21.00"],
        "riciclo": ["38.32.20", "38.21.00"],
        "plastica": ["38.32.20"],
        "plastiche": ["38.32.20"],
        "scarti": ["38.32.20", "38.21.00"],
        "nautica": ["30.11.02", "30.12.00"],
        "navale": ["30.11.02", "30.12.00"],
        "cantieristica": ["30.11.02", "30.12.00"],
        "blue economy": ["30.11.02", "30.12.00"],
        "idrico": ["01.61.00"],
        "idrica": ["01.61.00"],
        "acque": ["01.61.00"],
        "acque reflue": ["01.61.00"],
        "irrigazione": ["01.61.00"],
        "agricole": ["01.11.00", "01.61.00"],
        "aerospaziali": ["30.30.09", "30.30.00"],
        "aerospaziale": ["30.30.09", "30.30.00"],
        "droni": ["30.30.09", "30.30.00"],
        "satellitari": ["30.30.09"],
        "cinema": ["59.11.00", "59.12.00"],
        "cinematografiche": ["59.11.00", "59.12.00"],
        "audiovisiva": ["59.11.00", "59.12.00"],
        "audiovisivo": ["59.11.00", "59.12.00"],
        "gaming": ["59.11.00", "62.01.00"],
        "film": ["59.11.00", "59.12.00"],
        "freddo": ["52.10.10"],
        "refrigerati": ["52.10.10"],
        "magazzini": ["52.10.10"],
        "ceramica": ["23.41.00"],
        "odontoiatrici": ["32.50.13"],
        "biomedicale": ["32.50.13", "72.11.00"]
    }

    @classmethod
    def normalize_code(cls, code: str) -> str:
        """Pulisce e normalizza un codice ATECO nel formato standard con punti (es. 62.01.00)."""
        c = code.strip().upper()
        if c in ("TUTTI", "ALL", "*"):
            return "TUTTI"

        digits = re.sub(r"\D", "", c)
        if len(digits) == 6:
            return f"{digits[0:2]}.{digits[2:4]}.{digits[4:6]}"
        elif len(digits) == 4:
            return f"{digits[0:2]}.{digits[2:4]}"
        elif len(digits) == 2:
            return digits
        return c

    @classmethod
    def is_code_compatible(cls, bando_codes: List[str], company_codes: List[str]) -> bool:
        """
        Verifica se almeno uno dei codici ATECO aziendali è ammesso dal bando.
        Supporta corrispondenza a livello di Sezione, Divisione (2 cifre), Gruppo (4 cifre) o Sottocategoria (6 cifre).
        """
        if not bando_codes or "TUTTI" in [c.upper() for c in bando_codes]:
            return True

        if not company_codes:
            return False

        norm_bando = [cls.normalize_code(c) for c in bando_codes]
        norm_company = [cls.normalize_code(c) for c in company_codes]

        for comp_code in norm_company:
            for b_code in norm_bando:
                if b_code == "TUTTI":
                    return True
                # Match esatto o per prefisso gerarchico (es. bando '62', '62.01' o '28.00.00' ammette '28.11.00')
                comp_clean = re.sub(r"(\.00)+$", "", comp_code)
                b_clean = re.sub(r"(\.00)+$", "", b_code)
                if (
                    comp_code == b_code
                    or comp_code.startswith(b_code)
                    or b_code.startswith(comp_code)
                    or comp_code.startswith(b_clean)
                    or comp_clean.startswith(b_clean)
                    or b_code.startswith(comp_clean)
                ):
                    return True

        return False

    @classmethod
    def infer_ateco_from_text(cls, text: str) -> List[str]:
        """Estrae codici ATECO associabili semanticamente a partire da una descrizione in linguaggio naturale."""
        inferred: Set[str] = set()
        low_text = text.lower()

        # 1. Ricerca codici ATECO espliciti (es. '62.01.00')
        explicit = re.findall(r"\b(\d{2}\.\d{2}(?:\.\d{2})?)\b", text)
        for code in explicit:
            inferred.add(cls.normalize_code(code))

        # 2. Ricerca semantica da dizionario parole chiave
        for kw, codes in cls.KEYWORD_TO_ATECO.items():
            if re.search(r"\b" + re.escape(kw) + r"\b", low_text):
                inferred.update(codes)

        return list(inferred) if inferred else ["TUTTI"]
