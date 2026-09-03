"""Verification script for the 60 Benchmark Queries (30 NLP + 30 Parametric).
Nexus Keystone v1.1.0-Universal | While-Clean Loop Validation.
"""

import sys
import re
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src_app.app import bootstrap_demo_service
from src_app.search.parametric_filter import ParametricFilterCriteria

GROUND_TRUTH_FILE = Path(r"C:\Users\erbal\.gemini\antigravity\brain\97794ea2-8907-43d5-b082-f5dd3a56bdf3\test_queries_ground_truth.txt")


def run_benchmark():
    service = bootstrap_demo_service()
    grants = service.list_all_grants()
    print(f"[+] Loaded {len(grants)} grants into demo service.")

    # Mappa bando_id -> bando
    grant_map = {g.bando_id: g for g in grants}

    # -------------------------------------------------------------
    # 30 NLP QUERIES
    # -------------------------------------------------------------
    nlp_cases = [
        ("NLP_01", "Contributi a fondo perduto per installazione pannelli solari e fotovoltaico aziendale", ["SICILIA-SOLAR-GREEN", "MIMIT-TRANS-5-0"]),
        ("NLP_02", "Finanziamento agevolato per startup innovativa intelligenza artificiale a Napoli", ["CAMPANIA-AI-2026", "INVITALIA-SMART-START-2026"]),
        ("NLP_03", "Voucher digitalizzazione PMI per acquisto software e cybersecurity a Milano", ["LOMBARDIA-DIGIT-2026"]),
        ("NLP_04", "Incentivi transizione 5.0 per efficienza energetica macchinari industriali", ["MIMIT-TRANS-5-0"]),
        ("NLP_05", "Bando ISI INAIL bonifica amianto e miglioramento sicurezza reparti produttivi", ["INAIL-ISI-2026"]),
        ("NLP_06", "Finanziamento a tasso agevolato per macchine utensili e robotica industriale a Bologna", ["EMILIA-MECCANICA-4-0"]),
        ("NLP_07", "Contributo a fondo perduto per agritech droni e sensoristica agricoltura a Bari", ["PUGLIA-AGRITECH-PRECISION"]),
        ("NLP_08", "Voucher per temporary export manager e fiere internazionali all'estero per consorzi veneti", ["VENETO-CONSORZI-EXPORT"]),
        ("NLP_09", "Bando per ricerca e sviluppo biotech sperimentazione clinica e dispositivi medici a Firenze", ["TOSCANA-BIOTECH-PHARMA"]),
        ("NLP_10", "Finanziamenti a fondo perduto per riconversione automotive verso componentistica elettrica e idrogeno a Torino", ["PIEMONTE-AUTOMOTIVE-EV"]),
        ("NLP_11", "Incentivi per riqualificazione energetica alberghi strutture ricettive e turismo sostenibile", ["VENETO-TURISMO-2026"]),
        ("NLP_12", "Agevolazioni per macchinari lavorazione e packaging conserve alimentari in Abruzzo", ["ABRUZZO-FOOD-PROCESSING"]),
        ("NLP_13", "Bando innovazione filiera legno e arredo design sostenibile a Udine", ["FRIULI-MANIFATTURA-LEGNO"]),
        ("NLP_14", "Horizon Europe EIC Accelerator finanziamento grant ed equity per deep tech", ["EU-HORIZON-EIC-ACCEL"]),
        ("NLP_15", "Voucher per audit di sicurezza informatica cloud migration e crittografia dati a Roma", ["LAZIO-CYBER-SECURITY"]),
        ("NLP_16", "Contributi per apertura ristorante tipico o laboratorio di street food a Palermo", ["RESTO-AL-SUD-2-0"]),
        ("NLP_17", "Agevolazioni brevetti marchi e valorizzazione titoli di proprietà industriale PMI", ["MIMIT-BREVETTI-PLUS"]),
        ("NLP_18", "Fondo perduto per imprenditoria femminile nuove imprese guidate da donne a Cagliari", ["SARDEGNA-IMPRESA-FEMMINILE"]),
        ("NLP_19", "Incentivi per acquisto veicoli commerciali elettrici e logistica green a Genova", ["LIGURIA-LOGISTICA-GREEN"]),
        ("NLP_20", "Contributi per digitalizzazione laboratori odontoiatrici e diagnostica biomedicale ad Ancona", ["MARCHE-BIOMEDICALE"]),
        ("NLP_21", "Finanziamenti per economia circolare riciclo materie plastiche e riduzione scarti a Perugia", ["UMBRIA-CIRCOLARE"]),
        ("NLP_22", "Fondo di rotazione per investimenti innovativi e artigianato alpino ad Aosta", ["VALLE-AOSTA-ROTAZIONE"]),
        ("NLP_23", "Agevolazioni per cantieristica navale nautica da diporto e blue economy a Taranto", ["PUGLIA-BLUE-ECONOMY"]),
        ("NLP_24", "Bando per attrazione investimenti e nuove unita produttive nelle aree ZES Unica Mezzogiorno", ["CAMPANIA-ZES-UNICA"]),
        ("NLP_25", "Contributi a fondo perduto per microimprese dell'artigianato artistico e ceramica a Faenza", ["EMILIA-ARTIGIANATO-CERAMICA"]),
        ("NLP_26", "Incentivi per efficientamento idrico e riutilizzo acque reflue in aziende agricole a Foggia", ["PUGLIA-IDRICO-AGRICOLTURA"]),
        ("NLP_27", "Finanziamenti per startup aerospaziali droni e tecnologie satellitari a Napoli", ["CAMPANIA-AEROSPAZIO-DRONI"]),
        ("NLP_28", "Voucher per transizione ecologica tessile biologico e moda sostenibile a Prato", ["TOSCANA-MODA-TESSILE"]),
        ("NLP_29", "Bando sostegno alle filiere cinematografiche produzione audiovisiva e gaming in Piemonte", ["PIEMONTE-FILM-FUND"]),
        ("NLP_30", "Contributi per creazione hub logistici e magazzini refrigerati per la catena del freddo a Verona", ["VENETO-LOGISTICA-FREDDO"]),
    ]

    print("\n" + "=" * 80)
    print("VALIDAZIONE 30 QUERY NLP")
    print("=" * 80)

    nlp_passed = 0
    for q_id, query, expected_ids in nlp_cases:
        intent, ranked, scores = service.search_nlp(query)
        retrieved_ids = [g.bando_id for g in ranked]
        match_found = any(exp in retrieved_ids for exp in expected_ids)
        top1_match = len(retrieved_ids) > 0 and retrieved_ids[0] in expected_ids

        if match_found:
            nlp_passed += 1
            status = "PASS (TOP-1)" if top1_match else "PASS (FOUND)"
            print(f"[{status}] {q_id}: Top match '{retrieved_ids[0] if retrieved_ids else 'None'}' in {retrieved_ids[:3]}")
        else:
            print(f"[FAIL] {q_id}: '{query}' -> Expected one of {expected_ids}, got {retrieved_ids}")

    print(f"\nNLP Score: {nlp_passed}/30 ({nlp_passed/30*100:.1f}%)")

    # -------------------------------------------------------------
    # 30 PARAMETRIC QUERIES
    # -------------------------------------------------------------
    param_cases = [
        ("PARAM_01", "35.11.00", "Sicilia", "PMI", "Fondo perduto", 50.0, "fotovoltaico", "SICILIA-SOLAR-GREEN"),
        ("PARAM_02", "62.01.00", "Campania", "Startup_Innovative", "Fondo perduto", 70.0, "intelligenza artificiale", "CAMPANIA-AI-2026"),
        ("PARAM_03", "62.02.00", "Lombardia", "PMI", "Voucher digitalizzazione", 40.0, "software", "LOMBARDIA-DIGIT-2026"),
        ("PARAM_04", "28.00.00", "Tutte", "PMI", "Credito d'imposta", 40.0, "transizione", "MIMIT-TRANS-5-0"),
        ("PARAM_05", "43.99.01", "Tutte", "PMI", "Fondo perduto", 60.0, "amianto", "INAIL-ISI-2026"),
        ("PARAM_06", "28.41.00", "Emilia-Romagna", "PMI", None, 40.0, "meccanica", "EMILIA-MECCANICA-4-0"),
        ("PARAM_07", "01.11.00", "Puglia", "PMI", "Fondo perduto", 60.0, "agritech", "PUGLIA-AGRITECH-PRECISION"),
        ("PARAM_08", "70.22.09", "Veneto", "PMI", "Voucher", 50.0, "export", "VENETO-CONSORZI-EXPORT"),
        ("PARAM_09", "72.11.00", "Toscana", "PMI", "Fondo perduto", 50.0, "biotech", "TOSCANA-BIOTECH-PHARMA"),
        ("PARAM_10", "29.10.00", "Piemonte", "PMI", "Fondo perduto", 40.0, "automotive", "PIEMONTE-AUTOMOTIVE-EV"),
        ("PARAM_11", "55.10.00", "Veneto", "PMI", "Fondo perduto", 30.0, "turismo", "VENETO-TURISMO-2026"),
        ("PARAM_12", "10.39.00", "Abruzzo", "PMI", "Fondo perduto", 40.0, "agroalimentare", "ABRUZZO-FOOD-PROCESSING"),
        ("PARAM_13", "31.09.00", "Friuli-Venezia Giulia", "PMI", "Fondo perduto", 50.0, "legno", "FRIULI-MANIFATTURA-LEGNO"),
        ("PARAM_14", "72.19.09", "Tutte", "Startup_Innovative", "Grant ed equity", 60.0, "accelerator", "EU-HORIZON-EIC-ACCEL"),
        ("PARAM_15", "62.09.09", "Lazio", "PMI", "Voucher", 50.0, "cyber", "LAZIO-CYBER-SECURITY"),
        ("PARAM_16", "56.10.11", "Campania", "Micro", "Fondo perduto", 70.0, "resto al sud", "RESTO-AL-SUD-2-0"),
        ("PARAM_17", "72.19.09", "Tutte", "PMI", "Fondo perduto", 70.0, "brevetti", "MIMIT-BREVETTI-PLUS"),
        ("PARAM_18", "62.01.00", "Tutte", "Startup_Innovative", "Finanziamento agevolato", 70.0, "smart", "INVITALIA-SMART-START-2026"),
        ("PARAM_19", "49.41.00", "Liguria", "PMI", None, 30.0, "mobilita", "LIGURIA-LOGISTICA-GREEN"),
        ("PARAM_20", "32.50.13", "Marche", "PMI", "Fondo perduto", 40.0, "digitale", "MARCHE-BIOMEDICALE"),
        ("PARAM_21", "38.32.20", "Umbria", "PMI", "Fondo perduto", 40.0, "circolare", "UMBRIA-CIRCOLARE"),
        ("PARAM_22", "16.29.19", "Valle d'Aosta", "PMI", "Finanziamento agevolato", 50.0, "rotazione", "VALLE-AOSTA-ROTAZIONE"),
        ("PARAM_23", "30.11.02", "Puglia", "PMI", None, 40.0, "nautica", "PUGLIA-BLUE-ECONOMY"),
        ("PARAM_24", "25.00.00", "Campania", "PMI", "Credito d'imposta", 40.0, "zes", "CAMPANIA-ZES-UNICA"),
        ("PARAM_25", "23.41.00", "Emilia-Romagna", "Micro", "Fondo perduto", 40.0, "artigianato", "EMILIA-ARTIGIANATO-CERAMICA"),
        ("PARAM_26", "01.61.00", "Puglia", "PMI", "Fondo perduto", 50.0, "idrico", "PUGLIA-IDRICO-AGRICOLTURA"),
        ("PARAM_27", "30.30.09", "Campania", "Startup_Innovative", "Fondo perduto", 70.0, "aerospazio", "CAMPANIA-AEROSPAZIO-DRONI"),
        ("PARAM_28", "13.20.00", "Toscana", "PMI", "Fondo perduto", 40.0, "tessile", "TOSCANA-MODA-TESSILE"),
        ("PARAM_29", "59.11.00", "Piemonte", "PMI", "Fondo perduto", 40.0, "film", "PIEMONTE-FILM-FUND"),
        ("PARAM_30", "52.10.10", "Veneto", "PMI", "Fondo perduto", 40.0, "logistica", "VENETO-LOGISTICA-FREDDO"),
    ]

    print("\n" + "=" * 80)
    print("VALIDAZIONE 30 QUERY PARAMETRICHE")
    print("=" * 80)

    param_passed = 0
    for q_id, ateco, reg, ben, aid, min_cov, text, expected_id in param_cases:
        criteria = ParametricFilterCriteria(
            ateco_codes=[ateco] if ateco else [],
            regioni_target=[reg] if reg and reg != "Tutte" else [],
            tipologia_beneficiari=[ben] if ben else [],
            tipo_agevolazione=aid,
            min_percentuale_copertura=min_cov,
            search_text=text
        )
        res = service.search_parametric(criteria)
        matched_ids = [g.bando_id for g in res]
        if expected_id in matched_ids:
            param_passed += 1
            print(f"[PASS] {q_id}: Found '{expected_id}' in {matched_ids}")
        else:
            print(f"[FAIL] {q_id}: Expected '{expected_id}', got {matched_ids}")

    print(f"\nParametric Score: {param_passed}/30 ({param_passed/30*100:.1f}%)")

    # -------------------------------------------------------------
    # LINK AUDIT (URL VALIDATION)
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("VALIDAZIONE LINK E URL REALI")
    print("=" * 80)
    url_errors = []
    for g in grants:
        if not g.url_bando or not (g.url_bando.startswith("http://") or g.url_bando.startswith("https://")):
            url_errors.append((g.bando_id, g.url_bando, "Invalid protocol"))
        if "transizione5-0" in g.url_bando:
            url_errors.append((g.bando_id, g.url_bando, "404 path found (expected transizione-5-0)"))

    if url_errors:
        print(f"[FAIL] URL errors detected: {url_errors}")
    else:
        print(f"[PASS] Tutti i {len(grants)} bandi hanno URL validi e path 404 corretti!")

    total_passed = nlp_passed + param_passed
    print("\n" + "=" * 80)
    print(f"BENCHMARK COMPLESSIVO: {total_passed}/60 ({total_passed/60*100:.1f}%)")
    print("=" * 80)
    return total_passed == 60 and len(url_errors) == 0


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
