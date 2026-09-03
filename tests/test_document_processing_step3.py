"""Unit & Integration Tests for Document Processing Pipeline (Step 3).
Nexus Keystone v1.1.0-Universal | Zero-Mock / CRV 4.0.
"""

import pytest
import io
import zipfile
import pypdf
from typing import Dict, Any

from src_app.document_processing.models import (
    BandoSection,
    BandoSectionType,
    ProcessedDocumentReport
)
from src_app.document_processing.pdf_extractor import PdfExtractor
from src_app.document_processing.zip_unpacker import ZipUnpacker
from src_app.document_processing.section_segmenter import SectionSegmenter
from src_app.document_processing.document_pipeline import DocumentPipeline
from src_app.ingestion.p7m_unpacker import P7MUnpacker


# Helper per generare PDF sintetico valido con metadati
def create_sample_pdf(title: str = "Disciplinare di Gara", author: str = "Regione Campania") -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({
        "/Title": title,
        "/Author": author,
        "/Producer": "LabNK Document Engine"
    })
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# Helper per creare archivio ZIP
def create_sample_zip(files_dict: Dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, data in files_dict.items():
            zf.writestr(fname, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. TEST PDF EXTRACTOR & TEXT SANITIZER
# ---------------------------------------------------------------------------

def test_pdf_extractor_metadata_and_pages():
    """Verifica l'estrazione corretta di metadati e conteggio pagine da PDF."""
    pdf_bytes = create_sample_pdf(title="Avviso Pubblico PMI", author="MIMIT")
    text, metadata, pages = PdfExtractor.extract_text_and_meta(pdf_bytes)

    assert pages == 1
    assert metadata.get("title") == "Avviso Pubblico PMI"
    assert metadata.get("author") == "MIMIT"
    assert metadata.get("producer") == "LabNK Document Engine"


def test_pdf_text_sanitizer_rules():
    """Verifica la rimozione di cesure di riga, numeri di pagina e spazi duplicati."""
    messy_text = (
        "Articolo 1 - Finanzia-\nmento alle imprese.\n\n"
        "Pagina 1 di 10\n\n"
        "Le   risorse   stanziate   ammontano   a   5.000.000,00 €.\n\n\n\n"
        "- 1 -\n\n"
        "La scadenza è fissata al 31/12/2026."
    )
    cleaned = PdfExtractor.sanitize_text(messy_text)

    assert "Finanziamento" in cleaned
    assert "Pagina 1 di 10" not in cleaned
    assert "- 1 -" not in cleaned
    assert "   " not in cleaned
    assert "\n\n\n" not in cleaned


# ---------------------------------------------------------------------------
# 2. TEST ZIP UNPACKER & SECURITY GATES
# ---------------------------------------------------------------------------

def test_zip_unpacker_valid_extraction():
    """Verifica l'estrazione corretta dei file ammessi in un archivio ZIP."""
    pdf_bytes = create_sample_pdf()
    txt_bytes = b"Testo integrativo del bando"
    zip_bytes = create_sample_zip({
        "disciplinare.pdf": pdf_bytes,
        "allegato_1.txt": txt_bytes
    })

    extracted = ZipUnpacker.extract_files(zip_bytes)
    assert len(extracted) == 2
    names = [item[0] for item in extracted]
    assert "disciplinare.pdf" in names
    assert "allegato_1.txt" in names

    mime_map = {item[0]: item[2] for item in extracted}
    assert mime_map["disciplinare.pdf"] == "application/pdf"
    assert mime_map["allegato_1.txt"] == "text/plain"


def test_zip_unpacker_path_traversal_mitigation():
    """Verifica la neutralizzazione di tentativi di path traversal (Zip Slip)."""
    zip_bytes = create_sample_zip({
        "../../etc/passwd.txt": b"illegal content",
        "subfolder/normale.pdf": create_sample_pdf()
    })

    extracted = ZipUnpacker.extract_files(zip_bytes)
    extracted_names = [item[0] for item in extracted]

    assert "passwd.txt" in extracted_names
    assert "normale.pdf" in extracted_names
    for name in extracted_names:
        assert "/" not in name and "\\" not in name and ".." not in name


def test_zip_unpacker_bomb_protection():
    """Verifica il blocco di archivi con decompressione superiore alla soglia."""
    large_payload = b"A" * 5000
    zip_bytes = create_sample_zip({"large.txt": large_payload})

    with pytest.raises(ValueError, match=r"(?i)dimensione decompressa.*supera il limite"):
        ZipUnpacker.extract_files(zip_bytes, max_bytes=1000)


# ---------------------------------------------------------------------------
# 3. TEST SECTION SEGMENTER & KEY ENTITY EXTRACTION
# ---------------------------------------------------------------------------

def test_section_segmenter_classification_and_entities():
    """Verifica la classificazione accurata delle sezioni istituzionali ed entità chiave."""
    sample_bando_text = """
    Articolo 1 - Soggetti Beneficiari e Requisiti di Ammissibilità
    Possono presentare domanda le PMI e Startup Innovative iscritte nel registro delle imprese con codice ATECO 62.01.00 o 72.19.09 aventi sede operativa nel territorio regionale.
    
    Articolo 2 - Spese Ammissibili e Interventi Finanziabili
    Sono ammesse ad agevolazione le spese per acquisto di beni strumentali, sviluppo software, licenze cloud e consulenze specialistiche fino a 150.000 € per beneficiario.
    
    Articolo 3 - Dotazione Finanziaria e Natura dell'Agevolazione
    La dotazione complessiva è pari a 10.000.000,00 €. Il contributo a fondo perduto è concesso nella misura dell'80% delle spese ammissibili in regime de minimis.
    
    Articolo 4 - Termini e Modalità di Presentazione delle Domande
    Le domande possono essere trasmesse a partire dal 15/10/2026 fino alla data di scadenza del 30/11/2026 tramite procedura a sportello click day.
    
    Articolo 5 - Criteri di Valutazione e Graduatoria
    Le domande saranno valutate secondo la griglia di valutazione con attribuzione di premialità del 10% per le imprese a conduzione femminile o giovanile.
    """

    sections = SectionSegmenter.segment_text(sample_bando_text)
    assert len(sections) >= 5

    section_types = [s.section_type for s in sections]
    assert BandoSectionType.AMMISSIBILITA in section_types
    assert BandoSectionType.SPESE_FINANZIABILI in section_types
    assert BandoSectionType.AGEVOLAZIONE_INTENSITA in section_types
    assert BandoSectionType.SCADENZE_PROCEDURA in section_types
    assert BandoSectionType.CRITERI_VALUTAZIONE in section_types

    agevolazione_sec = next(s for s in sections if s.section_type == BandoSectionType.AGEVOLAZIONE_INTENSITA)
    assert agevolazione_sec.key_entities["de_minimis_mentioned"] is True
    assert 80.0 in agevolazione_sec.key_entities["percentages"]
    assert 10000000.0 in agevolazione_sec.key_entities["monetary_amounts"]

    scadenze_sec = next(s for s in sections if s.section_type == BandoSectionType.SCADENZE_PROCEDURA)
    assert scadenze_sec.key_entities["click_day_mentioned"] is True
    assert "15/10/2026" in scadenze_sec.key_entities["dates"] or "30/11/2026" in scadenze_sec.key_entities["dates"]

    amm_sec = next(s for s in sections if s.section_type == BandoSectionType.AMMISSIBILITA)
    assert "62.01.00" in amm_sec.key_entities["ateco_codes"] or "72.19.09" in amm_sec.key_entities["ateco_codes"]


# ---------------------------------------------------------------------------
# 4. TEST END-TO-END DOCUMENT PIPELINE
# ---------------------------------------------------------------------------

def test_document_pipeline_direct_text_and_sections():
    """Verifica l'elaborazione end-to-end di un documento di testo con segmentazione."""
    doc_content = (
        "Articolo 1 - Soggetti Beneficiari\nPMI con sede in Italia e codice ATECO 62.01.\n\n"
        "Articolo 2 - Natura dell'Agevolazione\nContributo a fondo perduto fino al 70% in regime de minimis.\n\n"
        "Articolo 3 - Termini di Presentazione\nScadenza fissata al 20/12/2026."
    ).encode("utf-8")

    report = DocumentPipeline.process_document(
        raw_bytes=doc_content,
        filename="disciplinare.txt",
        mime_type="text/plain"
    )

    assert isinstance(report, ProcessedDocumentReport)
    assert report.source_filename == "disciplinare.txt"
    assert report.total_text_length > 0
    assert len(report.sections) >= 3
    assert report.was_p7m is False
    assert report.was_archive is False


def test_document_pipeline_with_p7m_and_zip():
    """Verifica l'elaborazione di un archivio ZIP contenente disciplinare e allegati."""
    sample_text = b"Articolo 1 - Soggetti Ammissibili\nStartup innovative.\n\nArticolo 2 - Spese Ammissibili\nCosti di personale e brevetti."
    zip_bytes = create_sample_zip({
        "bando_completo.txt": sample_text,
        "allegato_scheda.pdf": create_sample_pdf()
    })

    report = DocumentPipeline.process_document(
        raw_bytes=zip_bytes,
        filename="pacchetto_bando.zip",
        mime_type="application/zip"
    )

    assert report.was_archive is True
    assert report.extracted_files_count == 2
    assert "Startup innovative" in report.raw_text
    assert len(report.sections) >= 1
