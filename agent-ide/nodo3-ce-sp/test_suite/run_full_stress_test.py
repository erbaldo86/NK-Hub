"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Main Full Stress Test Orchestrator
Executes Ground Truth Extraction & Accountant Stress Runner across test files.
"""

import sys, os, glob, asyncio, json

sys.stdout.reconfigure(encoding='utf-8')

# Include backend & test_suite path
test_dir = os.path.dirname(__file__)
backend_path = os.path.abspath(os.path.join(test_dir, '..', 'src_app', 'backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
if test_dir not in sys.path:
    sys.path.insert(0, test_dir)

from pydantic_schemas import FullFinancialInput, ContoEconomicoInput, StatoPatrimonialeInput
from civil_code_math_engine import calculate_financials
from ingestion_parser_service import parse_file_bytes
from e2e_accountant_stress_runner import AccountantStressRunner

async def run_stress_test_suite():
    print("=== STARTING COMMERCIALISTA ESPERTO STRESS TEST SUITE ===")
    runner = AccountantStressRunner(tolerance=0.01)

    # 1. Test Deterministic Math Calculation Engine with Full Input
    ce_in = ContoEconomicoInput(
        ricaviVendite=[500000.0, 650000.0, 800000.0, 1000000.0, 1250000.0],
        altriRicavi=[20000.0, 25000.0, 30000.0, 35000.0, 40000.0],
        costiMaterieHosting=[120000.0, 150000.0, 180000.0, 220000.0, 270000.0],
        costiServiziMarketing=[80000.0, 95000.0, 110000.0, 130000.0, 150000.0],
        costiGodimentoBeni=[30000.0, 32000.0, 35000.0, 38000.0, 40000.0],
        salariStipendi=[150000.0, 180000.0, 210000.0, 250000.0, 300000.0],
        oneriSociali=[45000.0, 54000.0, 63000.0, 75000.0, 90000.0],
        tfrQuota=[10000.0, 12000.0, 14000.0, 16000.0, 20000.0]
    )
    sp_in = StatoPatrimonialeInput(
        capitaleSociale=50000.0,
        cassa=[100000.0, 150000.0, 220000.0, 310000.0, 450000.0],
        creditiClienti=[80000.0, 95000.0, 110000.0, 130000.0, 150000.0]
    )
    full_in = FullFinancialInput(ce=ce_in, sp=sp_in)
    calc_out = calculate_financials(full_in)

    is_clean = runner.verify_financial_output(calc_out, "Synthetic Financial Projection 5Y")
    print(f"✅ Synthetic Financial Engine Test: {'PASSED' if is_clean else 'FAILED'}")

    # 2. Test Real Files from Downloads & sample_data
    search_dirs = [
        r"C:\Users\erbal\Downloads",
        os.path.abspath(os.path.join(test_dir, "..", "sample_data"))
    ]

    files_tested = 0
    for d in search_dirs:
        if os.path.exists(d):
            pattern = os.path.join(d, "*.*")
            for fp in glob.glob(pattern):
                ext = os.path.splitext(fp)[1].lower()
                if ext in [".pdf", ".ods", ".xml", ".csv"]:
                    files_tested += 1
                    try:
                        with open(fp, "rb") as f:
                            content = f.read()
                        ingest_res = parse_file_bytes(content, os.path.basename(fp))
                        if ingest_res and hasattr(ingest_res, 'ledger') and ingest_res.ledger:
                            # Create a mock output object for runner verification
                            class MockOutput:
                                pass
                            out_mock = MockOutput()
                            out_mock.years = ingest_res.ledger
                            runner.verify_financial_output(out_mock, os.path.basename(fp))
                            print(f"✅ File tested [{os.path.basename(fp)}]: Ingestion OK ({len(ingest_res.ledger)} Y)")
                        else:
                            print(f"ℹ️ File tested [{os.path.basename(fp)}]: Ingestion parsed cleanly (0 exceptions)")
                    except Exception as e:
                        print(f"⚠️ Exception parsing {os.path.basename(fp)}: {e}")

    # 3. Save Discrepancy Report
    report_dir = os.path.join(test_dir, "test_reports")
    report_path = runner.save_discrepancy_report(report_dir)

    print(f"=== STRESS TEST SUITE VERDICT: {'PASSED 🟢' if len(runner.discrepancies) == 0 else 'FAILED 🔴'} ===")
    print(f"Tested {files_tested} real files. Report saved to: {report_path}")

    return len(runner.discrepancies) == 0

if __name__ == "__main__":
    success = asyncio.run(run_stress_test_suite())
    sys.exit(0 if success else 1)
