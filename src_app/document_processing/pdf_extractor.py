"""PDF Document Extractor & Text Sanitizer.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import io
import re
from typing import Tuple, Dict, Any, List
import pypdf


class PdfExtractor:
    """
    Estrattore di testo e metadati da documenti PDF (disciplinari, bandi, allegati)
    con algoritmi di sanitizzazione e rimozione artefatti di impaginazione.
    """

    @classmethod
    def extract_text_and_meta(cls, pdf_bytes: bytes) -> Tuple[str, Dict[str, Any], int]:
        """
        Estrae il testo integrale pulito, i metadati e il numero di pagine da un payload PDF in memoria.

        Ritorna:
            Tuple[str, Dict[str, Any], int]: (testo_pulito, metadati_pdf, numero_pagine)
        """
        if not pdf_bytes:
            return "", {}, 0

        stream = io.BytesIO(pdf_bytes)
        try:
            reader = pypdf.PdfReader(stream)
        except Exception as exc:
            # Se il PDF è corrotto o non leggibile
            return "", {"error": f"PDF parse error: {str(exc)}"}, 0

        page_count = len(reader.pages)
        pages_text: List[str] = []

        for idx, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
                if txt:
                    pages_text.append(txt)
            except Exception:
                continue

        raw_joined = "\n\n".join(pages_text)
        cleaned_text = cls.sanitize_text(raw_joined)

        # Estrazione metadati PDF
        metadata: Dict[str, Any] = {}
        if reader.metadata:
            for k, v in reader.metadata.items():
                clean_key = str(k).lstrip("/").lower()
                metadata[clean_key] = str(v)

        metadata["total_pages"] = page_count

        return cleaned_text, metadata, page_count

    @staticmethod
    def sanitize_text(text: str) -> str:
        """
        Pulisce e normalizza il testo estratto:
        - Ricompone parole spezzate a fine riga (es. 'finanzia- \\nmento' -> 'finanziamento')
        - Normalizza caratteri speciali, spazi multipli e ritorni a capo eccessivi
        - Rimuove intestazioni/piè di pagina frequenti (es. 'Pagina X di Y')
        """
        if not text:
            return ""

        # 1. Ricomposizione parole spezzate con trattino
        cleaned = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)

        # 2. Rimozione pattern di numerazione pagine 'Pagina X di Y' o '- X -'
        cleaned = re.sub(r"(?i)pagina\s+\d+\s+(?:di|\/)\s+\d+", "", cleaned)
        cleaned = re.sub(r"\n\s*[-–—]\s*\d+\s*[-–—]\s*\n", "\n", cleaned)

        # 3. Normalizzazione spazi multipli e tab
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        # 4. Normalizzazione ritorni a capo (massimo due newline consecutivi)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        return cleaned.strip()
