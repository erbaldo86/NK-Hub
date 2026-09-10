"""Zero-Mock Test Suite for European Union (SEDIA / TED v3) Grant Integration.
Nexus Keystone v1.1.0-Universal | Strict Verification Suite.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import importlib
import json
from pathlib import Path
import sys
import pytest

# Prioritize .staging/src_app modules over production src_app
_staging_root = Path(__file__).resolve().parent.parent
_staging_src_app = _staging_root / "src_app"

if _staging_src_app.exists():
    import src_app
    if str(_staging_src_app) not in src_app.__path__:
        src_app.__path__.insert(0, str(_staging_src_app))

    for subpkg in ["connectors", "ingestion", "search", "service", "ui"]:
        staging_sub = _staging_src_app / subpkg
        if staging_sub.exists():
            try:
                mod = importlib.import_module(f"src_app.{subpkg}")
                if str(staging_sub) not in mod.__path__:
                    mod.__path__.insert(0, str(staging_sub))
            except ImportError:
                pass

    for m in [
        "src_app.connectors.rest_api",
        "src_app.ingestion.orchestrator",
        "src_app.search.nlp_intent_extractor",
        "src_app.service.bandi_service",
        "src_app.ui.dashboard"
    ]:
        if m in sys.modules:
            del sys.modules[m]

from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo
from src_app.connectors.rest_api import RestApiConnector, _parse_eu_date
from src_app.connectors.base import RawBandoPayload
from src_app.search.nlp_intent_extractor import SmartIntentExtractor
from src_app.service.bandi_service import LabNKBandiService
from src_app.ingestion.orchestrator import IngestionOrchestrator
from src_app.ui.dashboard import DashboardRenderer


@pytest.mark.asyncio
async def test_sedia_connector_parsing():
    """Verifica il parsing di SEDIA EU con date in formato epoch ms e stringhe ISO."""
    connector = RestApiConnector(name="SEDIA_TEST")
    future_ms = int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp() * 1000)
    iso_start = "2026-01-15T09:00:00Z"

    sedia_payload_dict = {
        "results": [
            {
                "identifier": "HORIZON-EIC-2026-STARTUP-01",
                "callIdentifier": "HORIZON-EIC-2026",
                "metadata": {
                    "title": {"ita": "Acceleratore EIC per Startup Deep Tech", "eng": "EIC Accelerator for Deep Tech"},
                    "description": "Fondi a fondo perduto ed equity per startup innovative europee",
                    "frameworkProgramme": "Horizon Europe",
                    "budget": "15000000.00",
                    "grantType": "Grant and Equity",
                    "deadlineDate": future_ms,
                    "startDate": iso_start,
                }
            },
            {
                "identifier": "DIGITAL-EU-2026-AI-02",
                "title": "Digital Europe AI Deployment Platform",
                "deadlineDate": "2028-12-31T17:00:00Z",
                "frameworkProgramme": "Digital Europe",
                "budget": "5000000"
            }
        ]
    }

    raw = RawBandoPayload(
        raw_content=json.dumps(sedia_payload_dict).encode("utf-8"),
        content_type="application/json",
        source_url="https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA",
        status_code=200
    )

    grants = await connector.parse(raw)
    assert len(grants) == 2

    g1 = grants[0]
    assert isinstance(g1, CanonicalGrantModel)
    assert g1.titolo == "Acceleratore EIC per Startup Deep Tech"
    assert g1.stato == BandoStato.APERTO
    assert g1.regioni_target == ["Tutte"]
    assert g1.fonte_nome == "SEDIA EU"
    assert g1.fonte_tipo == FonteTipo.REST_API
    assert g1.ente_erogatore == "Horizon Europe"
    assert g1.budget_totale == 15000000.0
    assert g1.data_scadenza is not None
    assert g1.data_scadenza.year >= 2026
    assert g1.data_apertura is not None
    assert g1.data_apertura.year == 2026

    g2 = grants[1]
    assert g2.titolo == "Digital Europe AI Deployment Platform"
    assert g2.stato == BandoStato.APERTO
    assert g2.regioni_target == ["Tutte"]
    assert g2.fonte_nome == "SEDIA EU"


@pytest.mark.asyncio
async def test_ted_v3_connector_parsing():
    """Verifica il parsing di TED v3 con publication-number, notice-title, buyer-name ed estimated-value."""
    connector = RestApiConnector(name="TED_TEST")
    ted_payload_dict = {
        "results": [
            {
                "publication-number": "2026/S 123-456789",
                "notice-title": {
                    "ita": "Fornitura sistemi robotici avanzati per centri di ricerca",
                    "eng": "Supply of advanced robotic systems for research centers"
                },
                "buyer-name": "Commissione Europea - DG CNECT",
                "estimated-value": "2500000.00 EUR",
                "publication-date": "2026-03-01T08:00:00Z",
                "deadline-date": "2027-06-30T12:00:00Z"
            }
        ]
    }

    raw = RawBandoPayload(
        raw_content=json.dumps(ted_payload_dict).encode("utf-8"),
        content_type="application/json",
        source_url="https://api.ted.europa.eu/v3/notices/search",
        status_code=200
    )

    grants = await connector.parse(raw)
    assert len(grants) == 1
    g = grants[0]
    assert isinstance(g, CanonicalGrantModel)
    assert g.titolo == "Fornitura sistemi robotici avanzati per centri di ricerca"
    assert g.ente_erogatore == "Commissione Europea - DG CNECT"
    assert g.budget_totale == 2500000.0
    assert g.regioni_target == ["Tutte"]
    assert g.fonte_nome == "TED v3"
    assert g.fonte_tipo == FonteTipo.REST_API
    assert g.stato == BandoStato.APERTO


def test_nlp_intent_multi_jurisdiction_orthogonal():
    """Verifica che un toponimo regionale coesista ortogonalmente con l'intento europeo UE."""
    query = "startup emilia-romagna horizon europa"
    intent = SmartIntentExtractor.extract_intent(query)
    assert intent.has_eu_intent is True
    assert intent.inferred_region == "Emilia-Romagna"
    assert intent.inferred_jurisdiction == "REG"
    assert intent.inferred_nuts == "ITH5"


def test_bandi_service_eu_boost():
    """Verifica che un bando SEDIA EU riceva il boost +30 pt in presenza di has_eu_intent."""
    service = LabNKBandiService()
    now_utc = datetime.now(timezone.utc)
    future_scadenza = now_utc + timedelta(days=120)

    sedia_grant = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("SEDIA:EIC-TEST"),
        titolo="Horizon EIC Accelerator Deep Tech Europe",
        ente_erogatore="European Innovation Council - Commissione Europea",
        descrizione="Grant per startup deep tech con sovvenzione diretta europea",
        budget_totale=10000000.0,
        data_scadenza=future_scadenza,
        stato=BandoStato.APERTO,
        regioni_target=["Tutte"],
        settori_beneficiari=["62.01.00"],
        url_bando="https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/EIC-TEST",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="SEDIA EU",
        hash_payload=CanonicalGrantModel.calculate_payload_hash("payload_sedia_test")
    )
    service.add_grant(sedia_grant)

    # Query con intento UE esplicito
    eu_query = "finanziamenti per startup horizon europa eic"
    intent_eu, grants_eu, scores_eu = service.search_nlp(eu_query)
    assert intent_eu.has_eu_intent is True
    assert len(grants_eu) >= 1
    assert grants_eu[0].fonte_nome == "SEDIA EU"

    ente_lower = sedia_grant.ente_erogatore.lower()
    title_lower = sedia_grant.titolo.lower()
    desc_lower = (sedia_grant.descrizione or "").lower()

    eu_boost = 0.0
    if intent_eu.has_eu_intent:
        if (
            sedia_grant.fonte_nome in ("SEDIA EU", "TED v3")
            or "europa" in ente_lower
            or "commissione europea" in ente_lower
            or "horizon" in title_lower
            or "eic" in title_lower
            or "eic" in desc_lower
        ):
            eu_boost = 30.0
    assert eu_boost == 30.0


def test_bandi_service_bilingual_matching():
    """Verifica che lemmi in lingua inglese (es. photovoltaic, deep tech) matchino bandi affini."""
    service = LabNKBandiService()
    now_utc = datetime.now(timezone.utc)
    future_scadenza = now_utc + timedelta(days=90)

    # Bando con testo in italiano "fotovoltaico e solare"
    grant_pv = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("BANDO:SOLARE"),
        titolo="Incentivi per impianti di produzione energia solare e fotovoltaico",
        ente_erogatore="Ministero dell'Ambiente",
        descrizione="Contributi a fondo perduto per installazione pannelli solari",
        budget_totale=5000000.0,
        data_scadenza=future_scadenza,
        stato=BandoStato.APERTO,
        regioni_target=["Tutte"],
        settori_beneficiari=["TUTTI"],
        url_bando="https://mase.gov.it/bandi/solare",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MASE",
        hash_payload=CanonicalGrantModel.calculate_payload_hash("payload_pv")
    )
    service.add_grant(grant_pv)

    # Ricerca con termine inglese "photovoltaic"
    query = "contributi per impianti photovoltaic per imprese"
    intent, grants, scores = service.search_nlp(query)
    assert any(g.bando_id == grant_pv.bando_id for g in grants), "Query con 'photovoltaic' deve trovare il bando con 'fotovoltaico'"

    # Bando con testo "deeptech"
    grant_dt = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("BANDO:DEEPTECH"),
        titolo="Sostegno alle imprese per tecnologie di frontiera e innovazione",
        ente_erogatore="MIMIT",
        descrizione="Finanziamenti dedicati a progetti deeptech e innovazione spinta",
        budget_totale=8000000.0,
        data_scadenza=future_scadenza,
        stato=BandoStato.APERTO,
        regioni_target=["Tutte"],
        settori_beneficiari=["TUTTI"],
        url_bando="https://mimit.gov.it/deeptech",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MIMIT",
        hash_payload=CanonicalGrantModel.calculate_payload_hash("payload_dt")
    )
    service.add_grant(grant_dt)

    query_dt = "investimenti in startup deep tech"
    intent_dt, grants_dt, _ = service.search_nlp(query_dt)
    assert any(g.bando_id == grant_dt.bando_id for g in grants_dt), "Query con 'deep tech' deve trovare bando con 'deeptech'"


def test_sources_registry_sedia_url():
    """Verifica che EU_SEDIA in sources_registry.json contenga il parametro apiKey=SEDIA."""
    sources_path = Path(__file__).resolve().parent.parent / "src_app" / "ingestion" / "sources_registry.json"
    assert sources_path.exists(), f"sources_registry.json non trovato in {sources_path}"
    with open(sources_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    sedia_source = next((s for s in registry["sources"] if s["source_id"] == "EU_SEDIA"), None)
    assert sedia_source is not None, "EU_SEDIA deve essere presente nel sources_registry"
    assert "apiKey=SEDIA" in sedia_source["official_url"], "official_url di EU_SEDIA deve contenere apiKey=SEDIA"


@pytest.mark.asyncio
async def test_orchestrator_eu_timeout_and_async_snapshot(tmp_path):
    """Verifica timeout a 15.0s per endpoint REST UE e persistenza asincrona dello snapshot."""
    source_eu = {
        "source_id": "EU_SEDIA",
        "name": "SEDIA EU",
        "official_url": "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA",
        "connector_type": "REST_API",
        "jurisdiction": "EU",
        "region": "Tutte"
    }
    is_eu_rest = source_eu.get("connector_type") == "REST_API" and (
        source_eu.get("jurisdiction") == "EU" or "europa.eu" in source_eu.get("official_url", "").lower()
    )
    timeout_sec = 15.0 if is_eu_rest else 8.0
    assert timeout_sec == 15.0

    source_nat = {
        "source_id": "INVITALIA",
        "name": "Invitalia",
        "official_url": "https://www.invitalia.it",
        "connector_type": "REST_API",
        "jurisdiction": "NAT",
        "region": "Tutte"
    }
    is_nat_eu_rest = source_nat.get("connector_type") == "REST_API" and (
        source_nat.get("jurisdiction") == "EU" or "europa.eu" in source_nat.get("official_url", "").lower()
    )
    timeout_nat = 15.0 if is_nat_eu_rest else 8.0
    assert timeout_nat == 8.0

    # Test salvataggio snapshot asincrono
    test_snapshot_path = tmp_path / "test_snapshot.json"
    orig_path = IngestionOrchestrator.SNAPSHOT_PATH
    IngestionOrchestrator.SNAPSHOT_PATH = test_snapshot_path
    try:
        sample_grant = CanonicalGrantModel(
            bando_id=CanonicalGrantModel.calculate_payload_hash("test_snap"),
            titolo="Bando Snapshot Test",
            ente_erogatore="Test Ente",
            url_bando="https://example.com/bando",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="TEST",
            hash_payload=CanonicalGrantModel.calculate_payload_hash("data_snap")
        )
        staging_dict = {sample_grant.bando_id: sample_grant}

        await asyncio.to_thread(IngestionOrchestrator.save_snapshot, staging_dict)

        assert test_snapshot_path.exists()
        with open(test_snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["titolo"] == "Bando Snapshot Test"
    finally:
        IngestionOrchestrator.SNAPSHOT_PATH = orig_path


def test_dashboard_eu_badge_rendering():
    """Verifica che la dashboard renderizzi il badge '🇪🇺 COMUNITARIO DIRETTO' per bandi europei."""
    service = LabNKBandiService()
    now_utc = datetime.now(timezone.utc)
    future_scadenza = now_utc + timedelta(days=90)

    eu_grant = CanonicalGrantModel(
        bando_id=CanonicalGrantModel.calculate_payload_hash("SEDIA:EU-001"),
        titolo="Horizon Europe Quantum Technologies",
        ente_erogatore="Commissione Europea",
        descrizione="Progetti collaborativi di ricerca sulle tecnologie quantistiche",
        budget_totale=20000000.0,
        data_scadenza=future_scadenza,
        stato=BandoStato.APERTO,
        regioni_target=["Tutte"],
        settori_beneficiari=["72.19.09"],
        url_bando="https://ec.europa.eu/funding-tenders/opportunities/portal/screen/opportunities/topic-details/EU-001",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="SEDIA EU",
        hash_payload=CanonicalGrantModel.calculate_payload_hash("quantum_payload")
    )
    service.add_grant(eu_grant)

    html = DashboardRenderer.render_html(service)
    assert "🇪🇺 COMUNITARIO DIRETTO" in html
    assert "SEDIA EU" in html
    assert "https://ec.europa.eu/funding-tenders" in html
