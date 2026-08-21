"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Test Suite: Hard File Limiter Guard & File Size Security E2E
Validates:
  1. Upload of 5 files in single batch -> HTTP 422 (Hard File Limiter Guard)
  2. Upload of 3 files (success), followed by 2 files with active count -> HTTP 422 (Cumulative Limiter Guard)
  3. Upload of file > 50MB -> HTTP 413 (Payload Too Large / Size Guard)
"""

import sys
import os
import io

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(ROOT_DIR, 'src_app', 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient
from main_api_server import app, MAX_FILE_SIZE_BYTES

client = TestClient(app)

def create_dummy_csv_content(name: str, revenue: float = 10000.0) -> bytes:
    csv_str = f"Codice;Descrizione;2025;2024\n"
    csv_str += f"A.1;Ricavi delle vendite;{revenue};{revenue*0.9}\n"
    csv_str += f"B.6;Materie prime;{revenue*0.3};{revenue*0.25}\n"
    csv_str += f"SP_B.II;Immobilizzazioni materiali;{revenue*0.5};{revenue*0.4}\n"
    csv_str += f"SP_PASS_A.I;Capitale sociale;10000;10000\n"
    return csv_str.encode('utf-8')

def test_1_single_batch_over_limit():
    """Test 1: Upload di 5 file in un unico batch -> verifica che riceva HTTP 422."""
    files = [
        ('files', (f'file_{i}.csv', create_dummy_csv_content(f'f{i}', 10000.0 + i*1000), 'text/csv'))
        for i in range(5)
    ]
    response = client.post(
        "/api/v1/ingest/multi_file",
        files=files,
        data={"year": 2025, "current_active_count": 0}
    )
    assert response.status_code == 422, f"Expected HTTP 422, got {response.status_code}: {response.text}"
    detail = response.json().get("detail", "")
    assert "Hard File Limiter Guard" in detail, f"Expected guard message in detail, got: {detail}"
    print("✓ Test 1 Passed: Upload di 5 file in unico batch bloccato con HTTP 422.")

def test_2_cumulative_batch_over_limit():
    """Test 2: Upload di 3 file (successo), successivo upload di 2 file con current_active_count=3 -> HTTP 422."""
    # Step A: 3 files upload
    files_batch_1 = [
        ('files', (f'initial_{i}.csv', create_dummy_csv_content(f'init_{i}', 20000.0 + i*5000), 'text/csv'))
        for i in range(3)
    ]
    res1 = client.post(
        "/api/v1/ingest/multi_file",
        files=files_batch_1,
        data={"year": 2025, "current_active_count": 0}
    )
    assert res1.status_code == 200, f"Expected HTTP 200 for 3 files, got {res1.status_code}: {res1.text}"
    json1 = res1.json()
    assert json1["is_success"] is True
    assert len(json1["ingested_files"]) == 3
    assert json1["active_files_count"] == 3

    # Step B: 2 more files with current_active_count=3 -> Total 5 > 4 -> HTTP 422
    files_batch_2 = [
        ('files', (f'second_{i}.csv', create_dummy_csv_content(f'sec_{i}', 15000.0), 'text/csv'))
        for i in range(2)
    ]
    res2 = client.post(
        "/api/v1/ingest/multi_file",
        files=files_batch_2,
        data={"year": 2025, "current_active_count": 3}
    )
    assert res2.status_code == 422, f"Expected HTTP 422 for cumulative limit breach, got {res2.status_code}: {res2.text}"
    detail = res2.json().get("detail", "")
    assert "Hard File Limiter Guard" in detail, f"Expected guard message in detail, got: {detail}"
    print("✓ Test 2 Passed: Limiter cumulativo ha bloccato 3+2 file con HTTP 422.")

def test_3_file_size_exceeded():
    """Test 3: Upload di file > 50MB -> verifica che riceva HTTP 413 o 422."""
    # Create an in-memory stream exceeding 50MB (e.g. 50MB + 1KB)
    large_size = MAX_FILE_SIZE_BYTES + 1024
    large_content = b'A' * large_size

    files = [
        ('files', ('oversized_file.csv', large_content, 'text/csv'))
    ]
    response = client.post(
        "/api/v1/ingest/multi_file",
        files=files,
        data={"year": 2025, "current_active_count": 0}
    )
    assert response.status_code in (413, 422), f"Expected HTTP 413 or 422 for oversized file, got {response.status_code}: {response.text}"
    print(f"✓ Test 3 Passed: Upload di file >50MB ({large_size} bytes) bloccato con HTTP {response.status_code}.")

if __name__ == "__main__":
    print("--- INIZIO TEST HARD FILE LIMITER E2E ---")
    test_1_single_batch_over_limit()
    test_2_cumulative_batch_over_limit()
    test_3_file_size_exceeded()
    print("--- TUTTI I TEST HARD FILE LIMITER E2E SUPERATI CON SUCCESSO! ---")
