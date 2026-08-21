"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Test Suite: Delta Ledger Replay & Deterministic State Reconstruction (INV-03 Zero Ghost Residues)
Validates:
  1. Sequential ingestion of 4 distinct files -> deltaLedger has 4 items, coherent financial state
  2. Eviction of 1 file -> replay resets and calculates only 3 remaining files with zero ghost residues and SP balance |Δ| < 0.01€
  3. Eviction of all files -> virgin base state (€0)
"""

import sys
import os
import io
import json
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(ROOT_DIR, 'src_app', 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from pydantic_schemas import (
    IngestedFileRecord, FileDeltaPayload, MultiYearModel, YearRecord,
    ContoEconomicoSingleYear, StatoPatrimonialeSingleYear, FullCalculationOutput
)
from civil_code_math_engine import calculate_multi_year

class PythonDeltaLedgerStore:
    """Python reference implementation mirroring frontend state.js Delta Ledger Replay engine."""
    def __init__(self, pivot_year: int = 2025):
        self.pivot_year = pivot_year
        self.delta_ledger: Dict[str, Dict[str, Any]] = {}
        self.records: Dict[int, YearRecord] = {}
        self.active_file_count: int = 0
        self.detailed_subitems: List[Dict[str, Any]] = []

    def add_file_delta(self, file_record: IngestedFileRecord, delta_data: Dict[str, Any]):
        self.delta_ledger[file_record.file_id] = {
            "file_record": file_record,
            "delta_data": delta_data
        }
        self.replay_delta_ledger()

    def remove_file_delta(self, file_id: str):
        if file_id in self.delta_ledger:
            del self.delta_ledger[file_id]
        self.replay_delta_ledger()

    def replay_delta_ledger(self):
        # 1. Reset records to virgin zero state (€0)
        self.records = {}
        self.detailed_subitems = []
        for i in range(5):
            yr = self.pivot_year + i
            self.records[yr] = YearRecord(
                year=yr,
                data_type="actual" if i == 0 else "forecast",
                ce=ContoEconomicoSingleYear(),
                sp=StatoPatrimonialeSingleYear()
            )

        # 2. Sequential Replay of all registered delta payloads
        for file_id, entry in self.delta_ledger.items():
            delta = entry["delta_data"]
            ce_delta = delta.get("ce", {})
            sp_delta = delta.get("sp", {})
            subitems = delta.get("detailedSubitems", [])

            # Apply CE
            for yr, rec in self.records.items():
                idx = yr - self.pivot_year
                for field in ContoEconomicoSingleYear.model_fields.keys():
                    if field in ce_delta:
                        val = ce_delta[field]
                        if isinstance(val, list) and idx < len(val):
                            curr = getattr(rec.ce, field)
                            setattr(rec.ce, field, curr + float(val[idx]))
                        elif isinstance(val, (int, float)) and idx == 0:
                            curr = getattr(rec.ce, field)
                            setattr(rec.ce, field, curr + float(val))

            # Apply SP
            for yr, rec in self.records.items():
                idx = yr - self.pivot_year
                for field in StatoPatrimonialeSingleYear.model_fields.keys():
                    if field in sp_delta:
                        val = sp_delta[field]
                        if field == 'capitaleSociale':
                            rec.sp.capitaleSociale = max(rec.sp.capitaleSociale, float(val) if isinstance(val, (int, float)) else 0.0)
                        elif isinstance(val, list) and idx < len(val):
                            curr = getattr(rec.sp, field)
                            setattr(rec.sp, field, curr + float(val[idx]))
                        elif isinstance(val, (int, float)) and idx == 0:
                            curr = getattr(rec.sp, field)
                            setattr(rec.sp, field, curr + float(val))

            # Apply subitems
            for sub in subitems:
                sub_copy = dict(sub)
                sub_copy["file_id"] = file_id
                self.detailed_subitems.append(sub_copy)

        self.active_file_count = len(self.delta_ledger)

    def compute_financials(self) -> FullCalculationOutput:
        model = MultiYearModel(base_year=self.pivot_year, records=self.records)
        return calculate_multi_year(model)


def test_1_sequential_ingestion_4_files():
    """Test 1: Ingestione sequenziale di 4 file distinti (ODS/XML/CSV). Verifica coerenza deltaLedger."""
    store = PythonDeltaLedgerStore(pivot_year=2025)

    # File 1: CSV Bilancio Generale (Ricavi 100k, Costi 40k)
    f1 = IngestedFileRecord(
        file_id="f1_csv", filename="bilancio_2025.csv", file_type="CSV",
        size_bytes=1024, extracted_items_count=10, confidence_score=0.99,
        detected_years=[2025]
    )
    store.add_file_delta(f1, {
        "ce": {"ricaviVendite": [100000.0, 0, 0, 0, 0], "costiMaterieHosting": [40000.0, 0, 0, 0, 0]},
        "sp": {"capitaleSociale": 10000.0, "cassa": [60000.0, 0, 0, 0, 0]},
        "detailedSubitems": [{"label": "Vendite SaaS", "value": 100000.0, "section": "ricavi"}]
    })

    # File 2: ODS Fatture Fornitori (Costi Servizi 25k, Debiti 25k)
    f2 = IngestedFileRecord(
        file_id="f2_ods", filename="fornitori_2025.ods", file_type="ODS",
        size_bytes=2048, extracted_items_count=8, confidence_score=0.98,
        detected_years=[2025]
    )
    store.add_file_delta(f2, {
        "ce": {"costiServiziMarketing": [25000.0, 0, 0, 0, 0]},
        "sp": {"debFornitori": [25000.0, 0, 0, 0, 0]},
        "detailedSubitems": [{"label": "Consulenze Cloud", "value": 25000.0, "section": "opex"}]
    })

    # File 3: XML FatturaPA (Altri Ricavi 15k, Crediti 15k)
    f3 = IngestedFileRecord(
        file_id="f3_xml", filename="fatturapa_2025.xml", file_type="XML",
        size_bytes=1500, extracted_items_count=5, confidence_score=0.99,
        detected_years=[2025]
    )
    store.add_file_delta(f3, {
        "ce": {"altriRicavi": [15000.0, 0, 0, 0, 0]},
        "sp": {"creditiClienti": [15000.0, 0, 0, 0, 0]},
        "detailedSubitems": [{"label": "Contributo R&S", "value": 15000.0, "section": "ricavi"}]
    })

    # File 4: ODS Asset Immobilizzazioni (Immob Materiali 50k, Amm 5k, Cassa -5k)
    f4 = IngestedFileRecord(
        file_id="f4_asset", filename="cespiti_2025.ods", file_type="ODS",
        size_bytes=3000, extracted_items_count=12, confidence_score=0.97,
        detected_years=[2025]
    )
    store.add_file_delta(f4, {
        "ce": {"ammMateriali": [5000.0, 0, 0, 0, 0]},
        "sp": {"materialiLorde": [50000.0, 0, 0, 0, 0]},
        "detailedSubitems": [{"label": "Server Farm", "value": 50000.0, "section": "materiali"}]
    })

    assert store.active_file_count == 4
    assert len(store.delta_ledger) == 4
    assert len(store.detailed_subitems) == 4

    out = store.compute_financials()
    y2025 = out.years[0]
    # Ricavi: 100k + 15k = 115k
    assert y2025.valoreProduzione == 115000.0, f"Expected 115000.0, got {y2025.valoreProduzione}"
    # Costi op: 40k + 25k = 65k
    assert y2025.costiProduzione == 65000.0, f"Expected 65000.0, got {y2025.costiProduzione}"
    # EBITDA: 115k - 65k = 50k
    assert y2025.ebitda == 50000.0, f"Expected 50000.0, got {y2025.ebitda}"
    # Ammortamenti: 5k -> EBIT: 45k
    assert y2025.ebit == 45000.0, f"Expected 45000.0, got {y2025.ebit}"
    # SP Quadrature Check
    assert y2025.isQuadrato is True, f"Expected isQuadrato True, got {y2025.isQuadrato}"
    assert abs(y2025.totaleAttivo - y2025.totalePassivoNetto) < 0.01, f"Balance discrepancy: {y2025.totaleAttivo} vs {y2025.totalePassivoNetto}"
    print("✓ Test 1 Passed: 4 file sequenziali ingestiti con quadratura esatta (|Δ| < 0.01€).")
    return store

def test_2_eviction_of_1_file(store: PythonDeltaLedgerStore):
    """Test 2: Eviction di 1 file (f2_ods). Verifica replay pulito, zero residui fantasma (INV-03) e quadratura SP perfetta."""
    store.remove_file_delta("f2_ods")

    assert store.active_file_count == 3
    assert "f2_ods" not in store.delta_ledger
    assert len(store.detailed_subitems) == 3

    out = store.compute_financials()
    y2025 = out.years[0]

    # Without f2 (25k costi servizi), Costi op should be exactly 40k (f1 materie), with zero ghost residues
    assert y2025.costiProduzione == 40000.0, f"Expected 40000.0, got {y2025.costiProduzione}"
    # EBITDA: 115k - 40k = 75k
    assert y2025.ebitda == 75000.0, f"Expected 75000.0, got {y2025.ebitda}"
    # Debiti: 0 (f2 removed debFornitori 25k)
    assert store.records[2025].sp.debFornitori == 0.0, f"Ghost residue detected in debFornitori: {store.records[2025].sp.debFornitori}"
    # SP Balance must be exact
    assert y2025.isQuadrato is True
    assert abs(y2025.totaleAttivo - y2025.totalePassivoNetto) < 0.01, f"Discrepancy: {y2025.totaleAttivo} vs {y2025.totalePassivoNetto}"
    print("✓ Test 2 Passed: Rimozione di 1 file (f2_ods) eseguita. Zero residui fantasma (INV-03), quadratura SP perfetta.")

def test_3_eviction_of_all_files(store: PythonDeltaLedgerStore):
    """Test 3: Rimozione di tutti i file rimasti -> stato torna a base vergine (€0)."""
    for file_id in list(store.delta_ledger.keys()):
        store.remove_file_delta(file_id)

    assert store.active_file_count == 0
    assert len(store.delta_ledger) == 0
    assert len(store.detailed_subitems) == 0

    out = store.compute_financials()
    for y in out.years:
        assert y.valoreProduzione == 0.0, f"Expected 0.0, got {y.valoreProduzione}"
        assert y.costiProduzione == 0.0, f"Expected 0.0, got {y.costiProduzione}"
        assert y.ebitda == 0.0, f"Expected 0.0, got {y.ebitda}"
        assert y.utileNetto == 0.0, f"Expected 0.0, got {y.utileNetto}"
        assert y.isQuadrato is True

    print("✓ Test 3 Passed: Rimozione totale file -> stato tornato a base vergine (€0.00).")

if __name__ == "__main__":
    print("--- INIZIO TEST DELTA LEDGER REPLAY & INVARIANTE INV-03 ---")
    store = test_1_sequential_ingestion_4_files()
    test_2_eviction_of_1_file(store)
    test_3_eviction_of_all_files(store)
    print("--- TUTTI I TEST DELTA LEDGER REPLAY SUPERATI CON SUCCESSO! ---")
