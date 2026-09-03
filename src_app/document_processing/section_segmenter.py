"""Section Segmenter & Key Entity Intelligence Extractor.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from .models import BandoSection, BandoSectionType


class SectionSegmenter:
    """
    Segmentatore euristico e semantico per l'individuazione di sezioni istituzionali
    (Ammissibilità, Spese, Agevolazione, Scadenze, Criteri) ed estrazione di entità chiave.
    """

    SECTION_PATTERNS = {
        BandoSectionType.AMMISSIBILITA: [
            r"(?i)\b(soggetti\s+beneficiari|soggetti\s+ammissibili|requisiti\s+di\s+ammissibilit[aà]|chi\s+pu[oò]\s+partecipare|beneficiari\s+ammessi|destinatari\s+dell['\s]intervento)\b",
            r"(?i)\b(forma\s+giuridica|dimensione\s+d['\s]impresa|codici\s+ateco|settori\s+di\s+attivit[aà])\b"
        ],
        BandoSectionType.AGEVOLAZIONE_INTENSITA: [
            r"(?i)\b(dotazione\s+finanziaria|risorse\s+disponibili|natura\s+dell['\s]agevolazione|entit[aà]\s+dell['\s]aiuto|forma\s+e\s+intensit[aà]|contributo\s+a\s+fondo\s+perduto)\b",
            r"(?i)\b(de\s+minimis|regolamento\s+gber|finanziamento\s+a\s+tasso\s+agevolato|massimale\s+di\s+contributo)\b"
        ],
        BandoSectionType.SPESE_FINANZIABILI: [
            r"(?i)\b(spese\s+ammissibili|interventi\s+ammissibili|progetti\s+finanziabili|voci\s+di\s+spesa|costi\s+ammissibili|spese\s+eleggibili)\b",
            r"(?i)\b(beni\s+strumentali|attrezzature|consulenze\s+specialistiche|spese\s+del\s+personale|sviluppo\s+software)\b"
        ],
        BandoSectionType.SCADENZE_PROCEDURA: [
            r"(?i)\b(termini\s+di\s+presentazione|modalit[aà]\s+di\s+presentazione|apertura\s+dello\s+sportello|chiusura\s+dello\s+sportello|scadenza\s+domande|termini\s+e\s+scadenze)\b",
            r"(?i)\b(click\s*day|procedura\s+a\s+sportello|valutazione\s+a\s+graduatoria)\b"
        ],
        BandoSectionType.CRITERI_VALUTAZIONE: [
            r"(?i)\b(criteri\s+di\s+valutazione|griglia\s+di\s+valutazione|punteggio\s+minimo|criteri\s+di\s+selezione|premialit[aà]|graduatoria\s+di\s+merito)\b"
        ],
        BandoSectionType.MODALITA_PRESENTAZIONE: [
            r"(?i)\b(piattaforma\s+telematica|invio\s+della\s+domanda|firma\s+digitale|accesso\s+tramite\s+spid|indirizzo\s+pec|documentazione\s+da\s+allegare)\b"
        ]
    }

    @classmethod
    def segment_text(cls, full_text: str) -> List[BandoSection]:
        """
        Analizza il testo integrale ed individua le sezioni tematiche principali.
        """
        if not full_text:
            return []

        blocks = cls._split_into_structural_blocks(full_text)
        sections: List[BandoSection] = []

        for block in blocks:
            detected_type, detected_title = cls._classify_block_header(block)
            sec_type = detected_type or BandoSectionType.ALTRO
            sec_title = detected_title or sec_type.value

            entities = cls.extract_key_entities(block)
            sections.append(
                BandoSection(
                    section_type=sec_type,
                    title=sec_title,
                    content=block,
                    confidence_score=0.95 if detected_type else 0.5,
                    key_entities=entities
                )
            )

        return sections

    @classmethod
    def _split_into_structural_blocks(cls, text: str) -> List[str]:
        """Suddivide il testo in corrispondenza di articoli, paragrafi o capitoli."""
        article_pattern = re.compile(
            r"(?:\n|^)\s*(?=art(?:icolo|\.)?\s+\d+|sezione\s+\d+|capo\s+[ivxlcdm]+|\d+\.\s+[A-Z])",
            re.IGNORECASE
        )
        splits = article_pattern.split(text)
        valid_splits = [s.strip() for s in splits if s.strip()]
        if len(valid_splits) > 1:
            return valid_splits

        # Fallback su doppi ritorni a capo
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    @classmethod
    def _classify_block_header(cls, block: str) -> Tuple[Optional[BandoSectionType], Optional[str]]:
        """Esamina prioritariamente la prima riga del blocco, poi il corpo iniziale."""
        first_line = block.splitlines()[0].strip()

        # 1. Matching prioritario sulla riga di intestazione
        for sec_type, patterns in cls.SECTION_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, first_line):
                    return sec_type, first_line

        # 2. Matching sul corpo iniziale del blocco
        header_text = block[:300]
        for sec_type, patterns in cls.SECTION_PATTERNS.items():
            for pat in patterns:
                match = re.search(pat, header_text)
                if match:
                    title = first_line if len(first_line) < 120 else match.group(0).capitalize()
                    return sec_type, title

        return None, first_line

    @classmethod
    def extract_key_entities(cls, text: str) -> Dict[str, Any]:
        """Estrae importi finanziari, percentuali, date e codici ATECO dal testo."""
        entities: Dict[str, Any] = {
            "monetary_amounts": [],
            "percentages": [],
            "dates": [],
            "ateco_codes": [],
            "de_minimis_mentioned": False,
            "click_day_mentioned": False
        }

        currency_matches = re.findall(
            r"(?:€|euro|eur)\s*([0-9\.\,]+)|([0-9\.\,]+)\s*(?:€|euro|eur|milioni|mln|mila)",
            text,
            re.IGNORECASE
        )
        for m in currency_matches:
            raw_num = m[0] or m[1]
            if raw_num:
                clean = raw_num.replace(".", "").replace(",", ".")
                try:
                    val = float(clean)
                    entities["monetary_amounts"].append(val)
                except ValueError:
                    pass

        percentages = re.findall(r"(\d+(?:[\,\.]\d+)?)\s*%", text)
        for p in percentages:
            try:
                val = float(p.replace(",", "."))
                if 0.0 <= val <= 100.0:
                    entities["percentages"].append(val)
            except ValueError:
                pass

        dates = re.findall(r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b", text)
        entities["dates"] = list(set(dates))

        ateco = re.findall(r"\b(\d{2}\.\d{2}(?:\.\d{2})?)\b", text)
        entities["ateco_codes"] = list(set(ateco))

        if re.search(r"(?i)\bde\s+minimis\b", text):
            entities["de_minimis_mentioned"] = True
        if re.search(r"(?i)\bclick\s*day\b", text):
            entities["click_day_mentioned"] = True

        return entities
