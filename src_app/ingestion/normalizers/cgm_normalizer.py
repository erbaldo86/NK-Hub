"""CGM Normalizer: Universal Transformer & Data Sanitizer.
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import re
from typing import Dict, Any, List, Optional
from ...models.cgm import CanonicalGrantModel


class CgmNormalizer:
    """Trasforma, pulisce e normalizza dati eterogenei nel Canonical Grant Model (CGM)."""

    FUNDING_TYPE_MAP = {
        "fondo perduto": "fondo_perduto",
        "sovvenzione": "fondo_perduto",
        "grant": "fondo_perduto",
        "contributo": "fondo_perduto",
        "tasso agevolato": "tasso_agevolato",
        "finanziamento agevolato": "tasso_agevolato",
        "credito imposta": "credito_imposta",
        "tax credit": "credito_imposta",
        "voucher": "voucher",
        "garanzia": "garanzia",
        "garanzia pubblica": "garanzia"
    }

    @classmethod
    def clean_monetary_amount(cls, val: Any) -> Optional[float]:
        """Converte stringhe di valuta (es. '1.500.000,00 €', '250.000 €', '10M') in float standard."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)

        val_str = str(val).strip().lower()
        if not val_str:
            return None

        if "mln" in val_str or "milion" in val_str or "m" in val_str:
            match = re.search(r"([0-9\.\,]+)", val_str)
            if match:
                clean_num = match.group(1).replace(",", ".")
                try:
                    return float(clean_num) * 1_000_000.0
                except ValueError:
                    pass

        cleaned = re.sub(r"[^\d\,\.]", "", val_str)
        if not cleaned:
            return None

        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                cleaned = "".join(parts)

        try:
            return float(cleaned)
        except ValueError:
            return None

    @classmethod
    def clean_percentage(cls, val: Any) -> Optional[float]:
        """Normalizza percentuali (es. '80%', '0.8', '50.5%') in float 0.0 - 100.0."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            num = float(val)
            return num * 100.0 if num <= 1.0 and num > 0 else num

        val_str = str(val).replace("%", "").strip().replace(",", ".")
        try:
            num = float(val_str)
            if 0.0 <= num <= 1.0 and "." in val_str:
                return num * 100.0
            return min(100.0, max(0.0, num))
        except ValueError:
            return None

    @classmethod
    def map_funding_types(cls, raw_types: List[str]) -> List[str]:
        """Mappa tipologie descrittive nelle chiavi standard CGM."""
        mapped = set()
        for t in raw_types:
            t_low = t.strip().lower()
            found = False
            for k, v in cls.FUNDING_TYPE_MAP.items():
                if k in t_low:
                    mapped.add(v)
                    found = True
            if not found and t_low:
                mapped.add("altro")
        return list(mapped) if mapped else ["fondo_perduto"]

    @classmethod
    def to_cgm(cls, raw_data: Dict[str, Any]) -> CanonicalGrantModel:
        """Costruisce e valida un'istanza di CanonicalGrantModel."""
        total_budget = cls.clean_monetary_amount(raw_data.get("total_budget"))
        max_grant = cls.clean_monetary_amount(raw_data.get("max_grant_per_applicant"))
        cofinancing = cls.clean_percentage(raw_data.get("cofinancing_rate_percent"))

        raw_ft = raw_data.get("funding_type", [])
        if isinstance(raw_ft, str):
            raw_ft = [raw_ft]
        funding_types = cls.map_funding_types(raw_ft)

        return CanonicalGrantModel(
            grant_id=str(raw_data.get("grant_id", "GRANT-GEN-001")),
            source_id=str(raw_data.get("source_id", "UNKNOWN")),
            source_url=str(raw_data.get("source_url", "https://labnk.nexus")),
            title=str(raw_data.get("title", "Bando senza titolo")),
            description=str(raw_data.get("description", "Nessuna descrizione.")),
            managing_authority=str(raw_data.get("managing_authority", "Ente Erogatore")),
            jurisdiction=raw_data.get("jurisdiction", "NAT"),
            funding_type=funding_types,
            total_budget=total_budget,
            max_grant_per_applicant=max_grant,
            cofinancing_rate_percent=cofinancing,
            eligible_beneficiaries=raw_data.get("eligible_beneficiaries", ["PMI"]),
            ateco_codes=raw_data.get("ateco_codes", ["TUTTI"]),
            nuts_codes=raw_data.get("nuts_codes", ["IT"]),
            aid_intensity_framework=raw_data.get("aid_intensity_framework"),
            status=raw_data.get("status", "OPEN"),
            opening_date=raw_data.get("opening_date"),
            closing_date=raw_data.get("closing_date"),
            submission_deadline=raw_data.get("submission_deadline"),
            official_docs_urls=raw_data.get("official_docs_urls", []),
            cgm_version="1.0.0",
            raw_metadata=raw_data.get("raw_metadata", {})
        )
