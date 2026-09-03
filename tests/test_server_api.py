"""Unit & Integration Tests for LabNK FastAPI Web Server & REST Endpoints.
Nexus Keystone v1.1.0-Universal | Zero-Mock / CRV 4.0.
"""

import pytest
import io
import pypdf
from fastapi.testclient import TestClient

from src_app.server import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Fixture che inizializza il TestClient di FastAPI."""
    return TestClient(app)


def create_sample_pdf_bytes(title: str = "Bando Innovazione Test") -> bytes:
    """Crea un file PDF sintetico in memoria per i test di estrazione documentale."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": title, "/Producer": "LabNK Test Engine"})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. TEST DASHBOARD HTML ENDPOINTS
# ---------------------------------------------------------------------------

def test_get_root_dashboard_html(client: TestClient):
    """Verifica che GET / e GET /dashboard restituiscano la dashboard HTML reattiva."""
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert "text/html" in resp_root.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in resp_root.text
    assert "LabNK" in resp_root.text
    assert "Startup AI Napoli" in resp_root.text

    resp_dash = client.get("/dashboard")
    assert resp_dash.status_code == 200
    assert "<!DOCTYPE html>" in resp_dash.text
    assert "Voucher PMI Lombardia" in resp_dash.text


# ---------------------------------------------------------------------------
# 2. TEST NLP SEMANTIC SEARCH ENDPOINT
# ---------------------------------------------------------------------------

def test_post_api_search_nlp_success(client: TestClient):
    """Verifica l'elaborazione dell'intento NLP e il calcolo del ranking di matching."""
    payload = {
        "query": "Cerco finanziamenti a fondo perduto per una startup a Napoli per sviluppo software AI"
    }
    resp = client.post("/api/search/nlp", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert "intent" in data
    assert "results" in data

    # Verifica Intent
    intent = data["intent"]
    assert intent["inferred_region"] == "Campania"
    assert "62.01.00" in intent["inferred_ateco_codes"]
    assert "Startup_Innovative" in intent["inferred_beneficiary_types"]

    # Verifica Results e Match Score
    results = data["results"]
    assert len(results) >= 1
    top_grant = results[0]["grant"]
    top_score = results[0]["score"]

    assert top_grant["bando_id"] == "CAMPANIA-AI-2026"
    assert top_score["overall_match_score"] >= 80.0
    assert top_score["is_eligible"] is True
    assert "ateco_affinity" in top_score["criteria_scores"]


def test_post_api_search_nlp_empty_query_fails(client: TestClient):
    """Verifica che una query vuota sollevi un errore 400."""
    resp = client.post("/api/search/nlp", json={"query": "   "})
    assert resp.status_code == 400


def test_post_api_search_nlp_top_k(client: TestClient):
    """Verifica che se viene passato top_k=5, vengano restituiti massimo 5 bandi."""
    payload = {
        "query": "innovazione digitale software e intelligenza artificiale",
        "top_k": 5
    }
    resp = client.post("/api/search/nlp", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert 0 < len(data["results"]) <= 5


# ---------------------------------------------------------------------------
# 3. TEST PARAMETRIC FILTER ENDPOINT
# ---------------------------------------------------------------------------

def test_post_api_search_parametric(client: TestClient):
    """Verifica il filtraggio multi-criterio dei bandi CGM."""
    criteria = {
        "regioni_target": ["Campania"],
        "min_percentuale_copertura": 70.0,
        "stato": "APERTO"
    }
    resp = client.post("/api/search/parametric", json=criteria)
    assert resp.status_code == 200

    data = resp.json()
    assert "results" in data
    assert "count" in data
    assert data["count"] >= 1
    grant_ids = [g["bando_id"] for g in data["results"]]
    assert "CAMPANIA-AI-2026" in grant_ids


# ---------------------------------------------------------------------------
# 4. TEST GRANTS CATALOG ENDPOINT
# ---------------------------------------------------------------------------

def test_get_api_grants_catalog(client: TestClient):
    """Verifica il recupero dell'intero catalogo CGM."""
    resp = client.get("/api/grants")
    assert resp.status_code == 200

    data = resp.json()
    assert "grants" in data
    assert "total" in data
    assert data["total"] >= 4
    assert any(g["bando_id"] == "MIMIT-TRANS-5-0" for g in data["grants"])
    assert any(g["bando_id"] == "EU-HORIZON-EIC-ACCEL" for g in data["grants"])


# ---------------------------------------------------------------------------
# 5. TEST DOCUMENT PROCESSING EXTRACTION ENDPOINT
# ---------------------------------------------------------------------------

def test_post_api_documents_extract(client: TestClient):
    """Verifica l'upload e l'elaborazione documentale tramite FastAPI."""
    pdf_bytes = create_sample_pdf_bytes(title="Disciplinare EIC Accelerator")

    files = {
        "file": ("disciplinare_eic.pdf", pdf_bytes, "application/pdf")
    }
    data = {
        "grant_id": "EU-HORIZON-EIC-ACCEL"
    }

    resp = client.post("/api/documents/extract", files=files, data=data)
    assert resp.status_code == 200

    report = resp.json()
    assert report["source_filename"] == "disciplinare_eic.pdf"
    assert report["total_pages"] == 1
    assert "document_id" in report


# ---------------------------------------------------------------------------
# 6. TEST LIVE HARVESTING SYNC & STATUS ENDPOINTS
# ---------------------------------------------------------------------------

def test_post_api_sync_harvest(client: TestClient):
    """Verifica l'endpoint POST /api/sync/harvest (supporta sia 200 OK che 202 Accepted)."""
    resp = client.post("/api/sync/harvest")
    assert resp.status_code in (200, 202)

    data = resp.json()
    assert "status" in data
    if resp.status_code == 200:
        assert data["status"] == "completed"
        assert "grants_harvested_live" in data
        assert isinstance(data["grants_harvested_live"], int)
        assert data["grants_harvested_live"] >= 50
        assert "sources_scanned" in data
        assert data["sources_scanned"] == 31
    else:
        assert data["status"] in ("started", "in_progress")
        assert "job_id" in data


def test_get_api_sync_status(client: TestClient):
    """Verifica l'endpoint GET /api/sync/status per telemetria e stato del motore di ingestion."""
    resp = client.get("/api/sync/status")
    assert resp.status_code == 200

    data = resp.json()
    assert "status" in data
    assert "is_running" in data
    assert "total_grants_in_service" in data
    assert data["total_grants_in_service"] >= 4
    assert "last_harvest" in data
