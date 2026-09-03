"""Live Web Ingestion Verification & Harvesting Audit Script.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence | Live Harvesting.
"""

import sys
import io
import time
import asyncio
from pathlib import Path
from typing import Dict, Any

# Force UTF-8 on stdout/stderr for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src_app.models.cgm import CanonicalGrantModel
from src_app.service.bandi_service import LabNKBandiService
from src_app.ingestion.orchestrator import IngestionOrchestrator


def is_valid_sha256_hex(val: Any) -> bool:
    """Verifica se la stringa è un hash SHA-256 esadecimale valido a 64 caratteri."""
    return bool(
        val
        and isinstance(val, str)
        and len(val) == 64
        and all(c in "0123456789abcdefABCDEF" for c in val)
    )


async def verify_live_harvesting() -> Dict[str, Any]:
    """Esegue l'harvesting live dalle 31 fonti istituzionali e valida le metriche di volume, latenza e integrità CGM."""
    service = LabNKBandiService()

    print("=" * 85)
    print("🌐 LABNK BANDI INTELLIGENCE — LIVE WEB HARVESTING & INGESTION VERIFIER")
    print("   Protocollo CRV 4.0 | Zero-Mock | Connessione Asincrona alle 31 Fonti SSOT")
    print("=" * 85)

    print("\n[*] Avvio scansione asincrona e parsing live delle 31 fonti istituzionali...")
    t0 = time.perf_counter()
    report = await IngestionOrchestrator.harvest_all(service)
    elapsed_total_ms = (time.perf_counter() - t0) * 1000

    print(f"[+] Scansione completata in {elapsed_total_ms:.2f} ms ({report['duration_ms']:.2f} ms interni)")
    print(f"[+] Fonti Istituzionali Contattate: {report['sources_scanned']}")
    print(f"[+] Bandi Live Scaricati dal Web:  {report['grants_harvested_live']}")
    print(f"[+] Totale Bandi nel Catalogo:      {report['grants_total_in_service']}")

    # 1. Stampa tabella riassuntiva delle fonti e dei conteggi
    print("\n" + "=" * 85)
    print("📋 DETTAGLIO FONTI ISTITUZIONALI SCANSIONATE")
    print("=" * 85)
    print(f"{'Fonte ID':<26} | {'Giurisdizione':<13} | {'Connettore':<13} | {'Bandi':<7} | {'Stato / Diagnostica'}")
    print("-" * 85)

    healthy_count = 0
    for s in report.get("sources_details", []):
        s_id = s.get("source_id", "N/A")
        juris = s.get("jurisdiction", "NAT")
        conn = s.get("connector", "N/A")
        cnt = s.get("grants_found", 0)
        st = s.get("status", "N/A")
        if "HEALTHY" in st or cnt > 0:
            healthy_count += 1
        print(f"{s_id:<26} | {juris:<13} | {conn:<13} | {cnt:>5} | {st}")

    print("-" * 85)
    print(f"📊 Fonti Attive / Sincronizzate: {healthy_count}/{report['sources_scanned']}")

    # 2. Campione bandi
    all_grants = service.list_all_grants()
    print("\n" + "=" * 85)
    print("🔍 CAMPIONE BANDI LIVE CARICATI NEL CATALOGO")
    print("=" * 85)
    for g in all_grants[:10]:
        print(f"  • [{g.bando_id[:12]}] {g.titolo[:55]:<55} | Ente: {g.ente_erogatore[:20]} | Regioni: {g.regioni_target}")

    # 3. Asserzione fonti scansionate: 31 fonti SSOT registrate
    assert report["sources_scanned"] == 31, f"FAIL: Fonti registrate inattese ({report['sources_scanned']} != 31)"

    # 4. Asserzione di volume: grants_harvested_live >= 50 (con target > 100)
    live_count = report.get("grants_harvested_live", 0)
    assert live_count >= 50, f"FAIL: Bandi live estratti insufficienti ({live_count} < 50 soglia minima)"
    if live_count > 100:
        print(f"\n🎯 [TARGET SUPERATO] Bandi live estratti: {live_count} > 100 target ottimale")
    else:
        print(f"\n✅ [SOGLIA SUPERATA] Bandi live estratti: {live_count} >= 50 soglia minima")

    # 5. Asserzioni di integrità del modello CGM e ZERO-MOCK MANDATE
    assert len(all_grants) > 0, "FAIL: Il catalogo del servizio è vuoto"
    for g in all_grants:
        assert isinstance(g, CanonicalGrantModel), f"FAIL: Oggetto non istanza di CanonicalGrantModel: {type(g)}"
        assert g is not None, "FAIL: Rilevato bando nullo nel catalogo"
        assert g.titolo and g.titolo.strip(), f"FAIL: Bando {g.bando_id} ha titolo assente o vuoto"
        assert is_valid_sha256_hex(g.hash_payload), (
            f"FAIL: Bando {g.bando_id} ha hash_payload non valido: '{g.hash_payload}' (attesi 64 char hex)"
        )
        # ZERO-MOCK MANDATE ENFORCEMENT: Nessun titolo sintetico ammesso nel catalogo SSOT
        assert "Scraped" not in g.titolo, f"ZERO-MOCK VIOLATION: Rilevato titolo sintetico in {g.bando_id}: '{g.titolo}'"
        assert "API gen_" not in g.titolo, f"ZERO-MOCK VIOLATION: Rilevato titolo sintetico in {g.bando_id}: '{g.titolo}'"
        assert not g.titolo.startswith("Bando API "), f"ZERO-MOCK VIOLATION: Rilevato titolo sintetico in {g.bando_id}: '{g.titolo}'"

    print("\n" + "=" * 85)
    print(f"✅ TUTTE LE ASSERZIONI SUPERATE: {len(all_grants)} BANDI CONVALIDATI NEL CATALOGO SSOT (31 FONTI)!")
    print("=" * 85)
    return report


def main():
    try:
        report = asyncio.run(verify_live_harvesting())
        if report.get("grants_harvested_live", 0) >= 50:
            sys.exit(0)
        else:
            sys.exit(1)
    except AssertionError as ae:
        print(f"\n❌ ERRORE DI ASSERZIONE: {ae}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ ERRORE CRITICO DURANTE L'HARVESTING: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
