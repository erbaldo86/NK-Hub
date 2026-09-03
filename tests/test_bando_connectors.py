"""Zero-Mock Test Suite for Bando Connectors and Canonical Grant Model.

Mandate compliance: ZERO-MOCK MANDATE [RULE-01.2] - No MagicMock, no stubs. Real objects and real parsing.
"""

import sys
from pathlib import Path

# Ensure .staging directory takes precedence in sys.path
staging_dir = Path(__file__).resolve().parent.parent
if str(staging_dir) not in sys.path:
    sys.path.insert(0, str(staging_dir))

from datetime import datetime, timezone
import json
from asn1crypto import cms, util
import pytest
from pydantic import ValidationError

from src_app.models.cgm import BandoStato, CanonicalGrantModel, FonteTipo
from src_app.connectors.base import AntiBanPolicy, AsyncRateLimiter, DOMDriftDetector, RawBandoPayload
from src_app.connectors.rest_api import RestApiConnector
from src_app.connectors.rss_feed import RssFeedConnector
from src_app.connectors.html_scraper import HtmlScraperConnector
from src_app.connectors.p7m_unpacker import P7MUnpacker



# --- Test 1: CGM Model Strict Mode Validation ---
def test_cgm_model_strict_validation():
    """Verify CanonicalGrantModel enforces Pydantic v2 strict mode type checking."""
    now = datetime.now(timezone.utc)
    raw_payload = "test payload for bando 123"
    payload_hash = CanonicalGrantModel.calculate_payload_hash(raw_payload)

    # Valid instantiation
    cgm = CanonicalGrantModel(
        bando_id=payload_hash,
        titolo="Bando Innovazione Digitale 2026",
        ente_erogatore="Ministero delle Imprese e del Made in Italy",
        descrizione="Contributi a fondo perduto per la digitalizzazione delle PMI.",
        tipo_agevolazione="Contributo a fondo perduto",
        budget_totale=500000.0,
        importo_massimo_finanziabile=50000.0,
        percentuale_copertura=70.0,
        data_apertura=now,
        stato=BandoStato.APERTO,
        settori_beneficiari=["ICT", "Manifatturiero"],
        tipologia_beneficiari=["PMI"],
        regioni_target=["Lombardia", "Lazio"],
        url_bando="https://example.gov.it/bandi/123",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MIMIT_REST",
        hash_payload=payload_hash,
    )

    assert cgm.titolo == "Bando Innovazione Digitale 2026"
    assert cgm.budget_totale == 500000.0
    assert cgm.fonte_tipo == FonteTipo.REST_API
    assert cgm.stato == BandoStato.APERTO
    assert cgm.hash_payload == payload_hash

    # Invalid type validation in Strict Mode (int passed to string field)
    with pytest.raises(ValidationError):
        CanonicalGrantModel(
            bando_id="123",
            titolo=12345,  # Strict mode rejects int for str
            ente_erogatore="MIMIT",
            url_bando="https://example.gov.it",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT",
            hash_payload="hash",
        )

    # Invalid type validation (string passed to float field)
    with pytest.raises(ValidationError):
        CanonicalGrantModel(
            bando_id="123",
            titolo="Bando Valid Title",
            ente_erogatore="MIMIT",
            budget_totale="500000",  # Strict mode rejects str for float
            url_bando="https://example.gov.it",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT",
            hash_payload="hash",
        )


# --- Test 2: Rate Limiter and Anti-Ban Policy ---
@pytest.mark.asyncio
async def test_rate_limiter_and_anti_ban():
    """Verify AsyncRateLimiter delays execution and AntiBanPolicy generates valid headers."""
    limiter = AsyncRateLimiter(requests_per_second=10.0)  # 0.1s interval
    t0 = datetime.now()
    await limiter.acquire()
    await limiter.acquire()
    t1 = datetime.now()
    elapsed = (t1 - t0).total_seconds()
    assert elapsed >= 0.08  # Account for timer resolution

    anti_ban = AntiBanPolicy(rotate_user_agent=True, base_delay=1.0)
    headers = anti_ban.get_headers({"X-Custom-Header": "TestValue"})

    assert "User-Agent" in headers
    assert len(headers["User-Agent"]) > 10
    assert headers.get("X-Custom-Header") == "TestValue"
    assert "Accept" in headers

    delay = anti_ban.get_random_delay(jitter=0.2)
    assert 0.5 <= delay <= 1.5

    backoff = anti_ban.get_exponential_backoff(attempt=3, base_delay=1.0)
    assert backoff >= 4.0


# --- Test 3: DOM Drift Detector ---
def test_dom_drift_detector():
    """Verify DOM skeleton hashing accurately detects structural changes."""
    html_v1 = """
    <!DOCTYPE html>
    <html>
      <head><title>Test Page</title></head>
      <body>
        <div class="header"><h1>Header Title</h1></div>
        <main>
          <div class="bando-item"><p>Bando 1 content dynamic text ABC</p></div>
          <div class="bando-item"><p>Bando 2 content dynamic text XYZ</p></div>
        </main>
      </body>
    </html>
    """

    html_v1_same_structure = """
    <!DOCTYPE html>
    <html>
      <head><title>Changed Title Text</title></head>
      <body>
        <div class="header"><h1>Different Header Text</h1></div>
        <main>
          <div class="bando-item"><p>Completely different dynamic content 999</p></div>
          <div class="bando-item"><p>Another dynamic paragraph text</p></div>
        </main>
      </body>
    </html>
    """

    html_v2_altered_dom = """
    <!DOCTYPE html>
    <html>
      <head><title>Test Page</title></head>
      <body>
        <div class="header"><h1>Header Title</h1></div>
        <main>
          <section class="new-section-wrapper">
            <article class="bando-card"><h2>New Layout Title</h2></article>
          </section>
        </main>
      </body>
    </html>
    """

    hash1 = DOMDriftDetector.compute_skeleton_hash(html_v1)
    hash1_same = DOMDriftDetector.compute_skeleton_hash(html_v1_same_structure)
    hash2_altered = DOMDriftDetector.compute_skeleton_hash(html_v2_altered_dom)

    assert len(hash1) == 64  # SHA-256 hex string
    assert hash1 == hash1_same  # Identical layout structure produces identical hash
    assert hash1 != hash2_altered  # Structural change alters hash

    assert not DOMDriftDetector.detect_drift(hash1, hash1_same)
    assert DOMDriftDetector.detect_drift(hash1, hash2_altered)


# --- Test 4: REST API Connector (SEDIA EU and TED v3 CQL) ---
@pytest.mark.asyncio
async def test_rest_api_connector_parsing():
    """Test RestApiConnector parsing real JSON schemas for SEDIA EU and TED v3."""
    connector = RestApiConnector(name="TestREST")

    # Real SEDIA EU JSON sample
    sedia_json = {
        "results": [
            {
                "identifier": "HORIZON-CL4-2026-DIGITAL-01",
                "title": "AI and Robotics Innovation Grant",
                "frameworkProgramme": "HORIZON EUROPE",
                "grantType": "Research and Innovation Action",
                "budget": 15000000.0,
                "startDate": "2026-01-15T00:00:00Z",
                "deadlineDate": "2026-06-30T17:00:00Z",
                "summary": "Funding for next-gen AI systems.",
                "url": "https://ec.europa.eu/funding/topic/1",
            }
        ]
    }

    raw_sedia = RawBandoPayload(
        raw_content=json.dumps(sedia_json).encode("utf-8"),
        content_type="application/json",
        source_url="https://ec.europa.eu/api/sedia/search",
    )

    sedia_records = await connector.parse(raw_sedia)
    assert len(sedia_records) == 1
    rec1 = sedia_records[0]
    assert rec1.titolo == "AI and Robotics Innovation Grant"
    assert rec1.ente_erogatore == "HORIZON EUROPE"
    assert rec1.budget_totale == 15000000.0
    assert rec1.fonte_nome == "SEDIA EU"
    assert rec1.fonte_tipo == FonteTipo.REST_API

    # Real TED v3 CQL JSON sample
    ted_json = {
        "notices": [
            {
                "publication-number": "2026/S 045-123456",
                "title": "Gara d'appalto per servizi cloud PA",
                "buyer-name": "Agenzia per l'Italia Digitale",
                "estimated-value": 2500000.0,
                "publication-date": "2026-02-01T08:00:00Z",
                "deadline-date": "2026-04-15T12:00:00Z",
                "notice-abstract": "Fornitura di servizi cloud per la PA.",
            }
        ]
    }

    raw_ted = RawBandoPayload(
        raw_content=json.dumps(ted_json).encode("utf-8"),
        content_type="application/json",
        source_url="https://ted.europa.eu/api/v3/notices/search",
    )

    ted_records = await connector.parse(raw_ted)
    assert len(ted_records) == 1
    rec2 = ted_records[0]
    assert rec2.titolo == "Gara d'appalto per servizi cloud PA"
    assert rec2.ente_erogatore == "Agenzia per l'Italia Digitale"
    assert rec2.budget_totale == 2500000.0
    assert rec2.fonte_nome == "TED v3"


# --- Test 5: RSS Feed Connector (ETag and GUID Deduplication) ---
@pytest.mark.asyncio
async def test_rss_feed_connector_etag_and_guid_dedup():
    """Test RssFeedConnector ETag 304 handling, GUID deduplication, and XML RSS parsing."""
    connector = RssFeedConnector(name="IncentiviGov")

    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Incentivi.gov.it Bandi</title>
        <link>https://www.incentivi.gov.it</link>
        <description>Feed ufficiale bandi incentivi</description>
        <item>
          <title>Voucher Connettività Impresed</title>
          <link>https://www.incentivi.gov.it/bando/voucher-connettivita</link>
          <guid>GUID-INC-2026-001</guid>
          <description>Voucher per banda ultralarga aziendale.</description>
          <pubDate>Mon, 02 Feb 2026 10:00:00 +0100</pubDate>
        </item>
        <item>
          <title>Bando Transizione 5.0</title>
          <link>https://www.incentivi.gov.it/bando/transizione-50</link>
          <guid>GUID-INC-2026-002</guid>
          <description>Crediti d'imposta per l'efficienza energetica.</description>
          <pubDate>Tue, 03 Feb 2026 09:00:00 +0100</pubDate>
        </item>
      </channel>
    </rss>
    """

    payload = RawBandoPayload(
        raw_content=rss_xml.encode("utf-8"),
        content_type="application/rss+xml",
        source_url="https://www.incentivi.gov.it/feed.xml",
        status_code=200,
    )

    records = await connector.parse(payload)
    assert len(records) == 2
    assert records[0].titolo == "Voucher Connettività Impresed"
    assert records[1].titolo == "Bando Transizione 5.0"

    # GUID Deduplication test: re-parsing payload should return 0 new records
    duplicate_records = await connector.parse(payload)
    assert len(duplicate_records) == 0

    # HTTP 304 Not Modified test
    payload_304 = RawBandoPayload(
        raw_content=b"",
        content_type="application/rss+xml",
        source_url="https://www.incentivi.gov.it/feed.xml",
        status_code=304,
    )

    records_304 = await connector.parse(payload_304)
    assert len(records_304) == 0


# --- Test 6: HTML Scraper Connector ---
@pytest.mark.asyncio
async def test_html_scraper_connector():
    """Test HtmlScraperConnector scraping DOM items and setting DOM skeleton hash."""
    connector = HtmlScraperConnector(
        name="PortalRegionale",
        card_selector=".bando-card",
        title_selector="h3.title",
        link_selector="a.bando-link",
        desc_selector="p.desc",
        deadline_selector="span.scadenza",
    )

    html_content = """
    <html>
      <body>
        <div class="content">
          <div class="bando-card">
            <h3 class="title">Bando Startup Innovative Lombardia 2026</h3>
            <a class="bando-link" href="/bandi/lombardia-startup-2026">Dettaglio Bando</a>
            <p class="desc">Finanziamenti per la creazione di nuove startup a elevato contenuto tecnologico.</p>
            <span class="scadenza">Scadenza: 31 Maggio 2026</span>
          </div>
          <div class="bando-card">
            <h3 class="title">Bando Artigianato e PMI</h3>
            <a class="bando-link" href="https://regione.lombardia.it/bandi/artigianato">Dettaglio Bando</a>
            <p class="desc">Contributi per l'acquisto di macchinari 4.0.</p>
            <span class="scadenza">Scadenza: 15 Giugno 2026</span>
          </div>
        </div>
      </body>
    </html>
    """

    payload = RawBandoPayload(
        raw_content=html_content.encode("utf-8"),
        content_type="text/html",
        source_url="https://regione.lombardia.it/bandi",
    )

    records = await connector.parse(payload)
    assert len(records) == 2
    assert records[0].titolo == "Bando Startup Innovative Lombardia 2026"
    assert records[0].url_bando == "https://regione.lombardia.it/bandi/lombardia-startup-2026"
    assert records[0].dom_skeleton_hash is not None
    assert len(records[0].dom_skeleton_hash) == 64
    assert records[1].url_bando == "https://regione.lombardia.it/bandi/artigianato"


# --- Test 7: Real P7M PKCS#7 Unpacker ---
def test_p7m_unpacker_real_pkcs7():
    """Verify P7MUnpacker extracts real PKCS#7 ASN.1 SignedData envelopes."""
    inner_payload = b"%PDF-1.5\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"

    # Construct a real valid ASN.1 PKCS#7 SignedData structure using asn1crypto
    content_info = cms.ContentInfo({
        "content_type": "signed_data",
        "content": {
            "version": "v1",
            "digest_algorithms": [],
            "encap_content_info": {
                "content_type": "data",
                "content": inner_payload,
            },
            "certificates": [],
            "signer_infos": [],
        },
    })

    der_p7m_bytes = content_info.dump()

    # Verify is_p7m helper
    assert P7MUnpacker.is_p7m(der_p7m_bytes) is True
    assert P7MUnpacker.is_p7m("documento_bando.pdf.p7m") is True
    assert P7MUnpacker.is_p7m("documento_bando.pdf") is False

    # Extract inner content
    extracted_bytes = P7MUnpacker.unpack_p7m(der_p7m_bytes)
    assert extracted_bytes == inner_payload
