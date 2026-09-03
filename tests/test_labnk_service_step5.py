"""Unit & Integration Tests for LabNK Unified Service & UI Dashboard (Step 5).
Nexus Keystone v1.1.0-Universal | Zero-Mock / CRV 4.0.
"""

import pytest
from datetime import datetime, timezone
import pypdf
import io

from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo
from src_app.service.bandi_service import LabNKBandiService
from src_app.matching.profile_model import CompanyProfile
from src_app.search.parametric_filter import ParametricFilterCriteria
from src_app.ui.dashboard import DashboardRenderer


def create_sample_pdf_bytes(title: str = "Allegato Bando") -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": title, "/Producer": "LabNK Test Engine"})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def populated_service() -> LabNKBandiService:
    service = LabNKBandiService()
    now = datetime.now(timezone.utc)

    g1 = CanonicalGrantModel(
        bando_id="CAMPANIA-AI-2026",
        titolo="Bando Innovazione e Intelligenza Artificiale Campania",
        ente_erogatore="Regione Campania",
        descrizione="Sostegno a progetti di sviluppo software AI per startup e PMI campane.",
        tipo_agevolazione="Contributo a fondo perduto (de minimis)",
        budget_totale=10000000.0,
        importo_massimo_finanziabile=150000.0,
        percentuale_copertura=80.0,
        data_apertura=now,
        stato=BandoStato.APERTO,
        settori_beneficiari=["62.01.00", "72.19.09"],
        tipologia_beneficiari=["PMI", "Startup_Innovative"],
        regioni_target=["Campania"],
        url_bando="https://innovazione.regione.campania.it/ai",
        fonte_tipo=FonteTipo.HTML_SCRAPER,
        fonte_nome="REG_CAMPANIA",
        hash_payload="hash_c1"
    )

    g2 = CanonicalGrantModel(
        bando_id="MIMIT-DIGIT-2026",
        titolo="Voucher Digitalizzazione Nazionale",
        ente_erogatore="MIMIT",
        descrizione="Incentivi nazionali per acquisto software, cloud e cybersecurity.",
        tipo_agevolazione="Voucher a fondo perduto",
        budget_totale=30000000.0,
        importo_massimo_finanziabile=20000.0,
        percentuale_copertura=50.0,
        data_apertura=now,
        stato=BandoStato.APERTO,
        settori_beneficiari=["TUTTI"],
        tipologia_beneficiari=["PMI"],
        regioni_target=["Tutte"],
        url_bando="https://mimit.gov.it/voucher",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MIMIT_REST",
        hash_payload="hash_m1"
    )

    service.add_grants([g1, g2])
    return service


# ---------------------------------------------------------------------------
# 1. TEST LABNK UNIFIED BANDI SERVICE
# ---------------------------------------------------------------------------

def test_service_add_and_get_grant(populated_service):
    """Verifica l'archiviazione e il recupero deterministico di schede bando."""
    grant = populated_service.get_grant("CAMPANIA-AI-2026")
    assert grant is not None
    assert grant.titolo == "Bando Innovazione e Intelligenza Artificiale Campania"
    assert grant.budget_totale == 10000000.0


def test_service_nlp_search_ranking(populated_service):
    """Verifica la ricerca conversazionale NLP con calcolo automatico del Match Score."""
    query = "Cerco fondi a fondo perduto per una startup a Napoli nel settore software e intelligenza artificiale"
    intent, grants, scores = populated_service.search_nlp(query)

    assert intent.inferred_region == "Campania"
    assert len(grants) >= 1
    assert grants[0].bando_id == "CAMPANIA-AI-2026"
    assert scores[0].overall_match_score >= 80.0
    assert scores[0].is_eligible is True


def test_service_parametric_search(populated_service):
    """Verifica la ricerca parametrica tramite il servizio unificato."""
    criteria = ParametricFilterCriteria(
        regioni_target=["Campania"],
        min_percentuale_copertura=75.0,
        stato=BandoStato.APERTO
    )
    results = populated_service.search_parametric(criteria)

    assert len(results) == 1
    assert results[0].bando_id == "CAMPANIA-AI-2026"


def test_service_document_processing_attachment(populated_service):
    """Verifica l'elaborazione e associazione di allegati ufficiali al bando."""
    pdf_data = create_sample_pdf_bytes(title="Disciplinare Bando Campania")
    report = populated_service.process_and_attach_document(
        grant_id="CAMPANIA-AI-2026",
        doc_bytes=pdf_data,
        filename="disciplinare.pdf",
        mime_type="application/pdf"
    )

    assert report is not None
    assert report.source_filename == "disciplinare.pdf"
    assert report.total_pages == 1

    retrieved = populated_service.get_document_report("CAMPANIA-AI-2026")
    assert retrieved is not None
    assert retrieved.document_id == report.document_id


# ---------------------------------------------------------------------------
# 2. TEST DASHBOARD UI RENDERER
# ---------------------------------------------------------------------------

def test_dashboard_renderer_html_generation(populated_service):
    """Verifica la generazione della dashboard HTML con KPI e dati bando coerenti."""
    html = DashboardRenderer.render_html(populated_service)

    assert "<!DOCTYPE html>" in html
    assert "LabNK" in html
    assert "Bando Innovazione e Intelligenza Artificiale Campania" in html
    assert "Voucher Digitalizzazione Nazionale" in html
    assert "10,000,000" in html or "10.000.000" in html or "40,000,000" in html
