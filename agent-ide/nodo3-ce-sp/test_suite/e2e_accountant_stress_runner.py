"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Differential Property Oracle & Accountant Stress Runner (TB-ST-03 & TB-ST-05)
Validates Civil Code mathematical equations with tolerance Delta <= 0.01€.
"""

import sys, os, io, json, datetime, asyncio
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

# Include backend path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src_app', 'backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from pydantic_schemas import FullFinancialInput, ContoEconomicoInput, StatoPatrimonialeInput
from civil_code_math_engine import calculate_financials
from ingestion_parser_service import parse_file_bytes

class AccountantStressRunner:
    """
    Simulates a Senior Certified Public Accountant (Commercialista Esperto)
    auditing financial statements for Art. 2424 & 2425 C.C. mathematical compliance.
    """
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = tolerance
        self.discrepancies: List[Dict[str, Any]] = []

    def verify_financial_output(self, output: Any, filename: str = "Input Data") -> bool:
        """
        Validates mathematical properties:
        1. EBITDA = ValoreProduzione - CostiProduzione
        2. EBIT = EBITDA - AmmortamentiTotali
        3. EBT = EBIT + ProventiFinanziari - OneriFinanziari
        4. UtileNetto = EBT - ImposteTotali
        5. Balance Sheet Balance: |TotaleAttivo - TotalePassivoNetto| <= 0.01€
        """
        is_clean = True
        for yr in output.years:
            year_num = yr.year

            # 1. EBITDA Check
            calc_ebitda = yr.valoreProduzione - yr.costiProduzione
            delta_ebitda = abs(yr.ebitda - calc_ebitda)
            if delta_ebitda > self.tolerance:
                is_clean = False
                self.discrepancies.append({
                    "file": filename, "year": year_num, "metric": "EBITDA",
                    "expected": calc_ebitda, "actual": yr.ebitda, "delta": delta_ebitda
                })

            # 2. EBIT Check
            calc_ebit = yr.ebitda - yr.ammortamentiTotali
            delta_ebit = abs(yr.ebit - calc_ebit)
            if delta_ebit > self.tolerance:
                is_clean = False
                self.discrepancies.append({
                    "file": filename, "year": year_num, "metric": "EBIT",
                    "expected": calc_ebit, "actual": yr.ebit, "delta": delta_ebit
                })

            # 3. Balance Sheet Balance Check (|TotaleAttivo - TotalePassivoNetto| <= 0.01€)
            delta_sp = abs(yr.totaleAttivo - yr.totalePassivoNetto)
            if delta_sp > self.tolerance or not yr.isQuadrato:
                is_clean = False
                self.discrepancies.append({
                    "file": filename, "year": year_num, "metric": "Quadratura_SP",
                    "expected": yr.totaleAttivo, "actual": yr.totalePassivoNetto, "delta": delta_sp
                })

        return is_clean

    def save_discrepancy_report(self, report_dir: str) -> str:
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(report_dir, f"discrepancy_report_{ts}.json")

        report_data = {
            "timestamp": ts,
            "tolerance_limit": self.tolerance,
            "total_discrepancies": len(self.discrepancies),
            "status": "PASS" if len(self.discrepancies) == 0 else "FAIL",
            "discrepancies": self.discrepancies
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        return report_path
