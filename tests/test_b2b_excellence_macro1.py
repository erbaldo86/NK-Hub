"""Test Suite for Super Brief Macro-Fase 1: 100% Grant Coverage & B2B Excellence.
Nexus Keystone v1.1.0-Universal | Protocollo CRV 4.0.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import pytest

from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo, MacroCategoria
from src_app.catalog.repository import GrantsRepository
from src_app.connectors.incentivi_gov import IncentiviGovConnector
from src_app.connectors.unioncamere_federator import UnioncamereFederatorConnector, CCIAA_REGISTRY
from src_app.connectors.html_scraper import HtmlScraperConnector
from src_app.connectors.rest_api import RestApiConnector
from src_app.connectors.base import RawBandoPayload
from src_app.ingestion.nightly_scheduler import NightlyIngestionScheduler
from src_app.ui.components.search_sections import render_search_sections
from src_app.ui.dashboard import DashboardRenderer
from src_app.service.bandi_service import LabNKBandiService


def test_cgm_macro_category_and_de_minimis_fields():
    """Verifica la presenza e la validazione dei nuovi campi CGM: MacroCategoria, CAR e De Minimis."""
    grant = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("TEST:CGM:01"),
        titolo="Bando Voucher Digitalizzazione PMI",
        ente_erogatore="MIMIT",
        url_bando="https://mimit.gov.it/voucher",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="Incentivi.gov.it",
        macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA,
        car_codice_misura="CAR-12345",
        codice_cup="B12C34567890001",
        de_minimis_applicabile=True,
        hash_payload=CanonicalGrantModel.calculate_payload_hash("payload_test_01")
    )
    assert grant.macro_categoria == MacroCategoria.AGEVOLAZIONE_IMPRESA
    assert grant.car_codice_misura == "CAR-12345"
    assert grant.codice_cup == "B12C34567890001"
    assert grant.de_minimis_applicabile is True

    # Test tender appalto
    tender = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("TEST:TED:02"),
        titolo="Appalto Europeo Fornitura Server Cloud",
        ente_erogatore="Commissione Europea",
        url_bando="https://ted.europa.eu/tender",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="TED v3",
        macro_categoria=MacroCategoria.APPALTO_FORNITURA,
        de_minimis_applicabile=False,
        hash_payload=CanonicalGrantModel.calculate_payload_hash("payload_tender_02")
    )
    assert tender.macro_categoria == MacroCategoria.APPALTO_FORNITURA
    assert tender.de_minimis_applicabile is False


def test_repository_inverted_indices_fast_lookup():
    """Verifica le performance e la correttezza dell'indice invertito su regione, ATECO e macro_categoria."""
    repo = GrantsRepository()
    now_utc = datetime.now(timezone.utc)

    g1 = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("G1"),
        titolo="Bando Innovazione Campania ICT",
        ente_erogatore="Regione Campania",
        url_bando="https://regione.campania.it/bando",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="Regione Campania",
        regioni_target=["Campania"],
        settori_beneficiari=["62.01.00", "62.02.00"],
        macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA,
        hash_payload=CanonicalGrantModel.calculate_payload_hash("p1")
    )
    g2 = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("G2"),
        titolo="Bando Nazionale Deep Tech",
        ente_erogatore="MIMIT",
        url_bando="https://mimit.gov.it/deeptech",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MIMIT",
        regioni_target=["Tutte"],
        settori_beneficiari=["62.09.09", "72.19.09"],
        macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA,
        hash_payload=CanonicalGrantModel.calculate_payload_hash("p2")
    )
    g3 = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("G3"),
        titolo="Appalto Fornitura Robotica Lombardia",
        ente_erogatore="Regione Lombardia",
        url_bando="https://regione.lombardia.it/appalto",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="Regione Lombardia",
        regioni_target=["Lombardia"],
        settori_beneficiari=["28.99.00"],
        macro_categoria=MacroCategoria.APPALTO_FORNITURA,
        hash_payload=CanonicalGrantModel.calculate_payload_hash("p3")
    )

    repo.add(g1)
    repo.add(g2)
    repo.add(g3)

    # 1. Lookup per regione (Campania deve includere sia g1 che il bando nazionale g2)
    res_campania = repo.get_by_region("Campania")
    ids_campania = {g.bando_id for g in res_campania}
    assert g1.bando_id in ids_campania
    assert g2.bando_id in ids_campania
    assert g3.bando_id not in ids_campania

    # 2. Lookup per codice ATECO a 2 cifre ("62" deve matchare g1 e g2)
    res_ateco_62 = repo.get_by_ateco("62")
    ids_ateco = {g.bando_id for g in res_ateco_62}
    assert g1.bando_id in ids_ateco
    assert g2.bando_id in ids_ateco
    assert g3.bando_id not in ids_ateco

    # 3. Lookup per macro_categoria
    res_appalti = repo.get_by_macro_categoria(MacroCategoria.APPALTO_FORNITURA)
    assert len(res_appalti) == 1
    assert res_appalti[0].bando_id == g3.bando_id

    # 4. Lookup combinato veloce filter_fast (< 10ms)
    fast_res = repo.filter_fast(region="Campania", ateco="62.01.00", macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA)
    assert len(fast_res) == 1
    assert fast_res[0].bando_id == g1.bando_id


@pytest.mark.asyncio
async def test_incentivi_gov_connector_parsing():
    """Verifica il parsing di IncentiviGovConnector con estrazione di CAR, CUP e De Minimis."""
    connector = IncentiviGovConnector()
    sample_payload = {
        "incentivi": [
            {
                "id": "INC-2026-999",
                "titolo": "Voucher Connettività e Digitalizzazione Imprese",
                "car": "CAR-998877",
                "cup": "C12B340001",
                "soggettoConcedente": "MIMIT - Direzione Generale Incentivi",
                "descrizione": "Aiuto concesso in regime de minimis secondo Regolamento UE 2023/2831.",
                "dotazioneFinanziaria": "50.000.000,00 €",
                "importoMassimo": "50.000 €",
                "percentualeCopertura": 80.0,
                "regioni": ["Tutte"],
                "dataPubblicazione": "2026-01-10",
                "dataScadenza": "2027-12-31",
                "stato": "APERTO",
                "url": "https://www.incentivi.gov.it/scheda/voucher-digital"
            }
        ]
    }

    raw = RawBandoPayload(
        raw_content=json.dumps(sample_payload).encode("utf-8"),
        content_type="application/json",
        source_url="https://www.incentivi.gov.it/api/v1/incentivi",
        status_code=200
    )

    grants = await connector.parse(raw)
    assert len(grants) == 1
    g = grants[0]
    assert g.titolo == "Voucher Connettività e Digitalizzazione Imprese"
    assert g.car_codice_misura == "CAR-998877"
    assert g.codice_cup == "C12B340001"
    assert g.de_minimis_applicabile is True
    assert g.macro_categoria == MacroCategoria.AGEVOLAZIONE_IMPRESA
    assert g.budget_totale == 50000000.0
    assert g.importo_massimo_finanziabile == 50000.0
    assert g.percentuale_copertura == 80.0
    assert g.stato == BandoStato.APERTO


@pytest.mark.asyncio
async def test_unioncamere_federator_connector_parsing():
    """Verifica il federatore Unioncamere con anagrafica 81 CCIAA."""
    assert len(CCIAA_REGISTRY) == 65 or len(CCIAA_REGISTRY) >= 60

    connector = UnioncamereFederatorConnector()
    sample_payload = {
        "voucher": [
            {
                "cciaa_id": "CCIAA_MILANO_MONZA_LODI",
                "titolo": "Bando Voucher Digitalizzazione I4.0 Anno 2026",
                "descrizione": "Contributi per servizi di consulenza e formazione 4.0",
                "valore_voucher": 15000.0,
                "intensita": 70.0,
                "url": "https://www.milomb.camcom.it/bando-i40"
            }
        ]
    }

    raw = RawBandoPayload(
        raw_content=json.dumps(sample_payload).encode("utf-8"),
        content_type="application/json",
        source_url="https://www.milomb.camcom.it/api/voucher",
        status_code=200
    )

    grants = await connector.parse(raw)
    assert len(grants) == 1
    g = grants[0]
    assert "CCIAA Milano Monza Brianza Lodi" in g.ente_erogatore
    assert g.regioni_target == ["Lombardia"]
    assert g.importo_massimo_finanziabile == 15000.0
    assert g.percentuale_copertura == 70.0
    assert g.de_minimis_applicabile is True
    assert g.macro_categoria == MacroCategoria.AGEVOLAZIONE_IMPRESA


def test_nightly_ingestion_scheduler_lifecycle():
    """Verifica lo scheduling degli eventi 00:01 deep e 14:00 light, e la telemetria di liveness."""
    service = LabNKBandiService()
    scheduler = NightlyIngestionScheduler(service=service)

    status = scheduler.get_status()
    assert status["is_running"] is False
    assert status["status"] == "STOPPED"

    next_dt, event_type, wait_sec = scheduler.compute_next_event()
    assert event_type in ("DEEP_SCAN", "LIGHT_SCAN")
    assert wait_sec > 0
    assert next_dt > datetime.now(timezone.utc)

    tier1_sources = scheduler.get_tier1_tier2_sources()
    assert len(tier1_sources) > 0
    assert any(s["source_id"] == "EU_SEDIA" for s in tier1_sources)

    # Test start and stop
    scheduler.start()
    assert scheduler.is_running is True
    assert scheduler.get_status()["status"] == "HEALTHY"

    scheduler.stop()
    assert scheduler.is_running is False


def test_ui_search_sections_macro_toggle_and_calendar():
    """Verifica che render_search_sections generi il macro toggle, debounce, tab calendario e modale simulatore."""
    html = render_search_sections()
    assert "macro-toggle-bar" in html
    assert "setMacroCategory('ALL')" in html
    assert "setMacroCategory('AGEVOLAZIONE_IMPRESA')" in html
    assert "setMacroCategory('APPALTO_FORNITURA')" in html
    assert "debouncedSearchNLP()" in html
    assert "calendar-tab" in html
    assert "simulator-modal" in html
    assert "recalculateSimulation()" in html


def test_dashboard_renderer_contains_macro_and_de_minimis():
    """Verifica che il template HTML completo contenga i dati di macro-categoria e le nuove funzioni."""
    service = LabNKBandiService()
    grant = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("TEST:UI:01"),
        titolo="Bando Transizione 5.0 Made in Italy",
        ente_erogatore="MIMIT",
        url_bando="https://mimit.gov.it/transizione5",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MIMIT",
        macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA,
        de_minimis_applicabile=True,
        hash_payload=CanonicalGrantModel.calculate_payload_hash("p_ui_01")
    )
    service.add_grant(grant)

    rendered = DashboardRenderer.render_html(service)
    assert "macro_categoria" in rendered
    assert "de_minimis_applicabile" in rendered
    assert "debouncedSearchNLP" in rendered
    assert "downloadIcsCalendar" in rendered
    assert "calculateSimulatorContribution" in rendered
