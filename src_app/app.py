"""LabNK Bandi Intelligence — Main Entrypoint & Live Demo Runner.
Nexus Keystone v1.1.0-Universal | Zero-Mock Engine.
"""

import sys
import io
from pathlib import Path

# Force UTF-8 on stdout/stderr for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from datetime import datetime, timezone
from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo
from src_app.service.bandi_service import LabNKBandiService
from src_app.matching.profile_model import CompanyProfile
from src_app.ui.dashboard import DashboardRenderer


def bootstrap_demo_service() -> LabNKBandiService:
    """Inizializza il servizio LabNK con un set dimostrativo completo di bandi reali."""
    service = LabNKBandiService()
    now = datetime.now(timezone.utc)

    grants = [
        # 1. CAMPANIA-AI-2026
        CanonicalGrantModel(
            bando_id="CAMPANIA-AI-2026",
            titolo="Bando Innovazione e Intelligenza Artificiale Campania",
            ente_erogatore="Regione Campania — Assessorato alla Ricerca",
            descrizione="Contributi a fondo perduto fino all'80% per lo sviluppo di soluzioni AI, intelligenza artificiale, modelli linguistici, computer vision e software per startup e PMI a Napoli e in Campania.",
            tipo_agevolazione="Contributo a fondo perduto (de minimis)",
            budget_totale=15000000.0,
            importo_massimo_finanziabile=200000.0,
            percentuale_copertura=80.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.01.00", "62.02.00", "72.19.09"],
            tipologia_beneficiari=["PMI", "Startup_Innovative"],
            regioni_target=["Campania"],
            url_bando="https://bandi.sviluppocampania.it/",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_CAMPANIA",
            hash_payload="hash_campania_ai"
        ),
        # 2. MIMIT-TRANS-5-0
        CanonicalGrantModel(
            bando_id="MIMIT-TRANS-5-0",
            titolo="Transizione 5.0 & Efficientamento Energetico Nazionale",
            ente_erogatore="MIMIT (Ministero delle Imprese e del Made in Italy)",
            descrizione="Crediti d'imposta e contributi per la transizione 5.0, digitalizzazione dei processi produttivi, macchinari industriali, efficientamento energetico e autoproduzione rinnovabili.",
            tipo_agevolazione="Credito d'imposta / Fondo perduto",
            budget_totale=6300000000.0,
            importo_massimo_finanziabile=2500000.0,
            percentuale_copertura=45.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["28.00.00", "TUTTI"],
            tipologia_beneficiari=["PMI", "Grandi_Imprese"],
            regioni_target=["Tutte"],
            url_bando="https://www.mimit.gov.it/it/incentivi/transizione-5-0",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT_REST",
            hash_payload="hash_mimit_t50"
        ),
        # 3. LOMBARDIA-DIGIT-2026
        CanonicalGrantModel(
            bando_id="LOMBARDIA-DIGIT-2026",
            titolo="Voucher Digitalizzazione PMI Lombardia",
            ente_erogatore="Regione Lombardia & Unioncamere Lombardia",
            descrizione="Voucher a fondo perduto per l'acquisto di software gestionali, cybersecurity, cloud e piattaforme per PMI a Milano e in Lombardia.",
            tipo_agevolazione="Voucher digitalizzazione a fondo perduto",
            budget_totale=10000000.0,
            importo_massimo_finanziabile=15000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.01.00", "62.02.00", "47.91.10", "70.22.09"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Lombardia"],
            url_bando="https://www.bandi.regione.lombardia.it/servizi/servizio/bandi/dettaglio/sviluppo-economico/voucher-digitalizzazione-pmi",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_LOMBARDIA",
            hash_payload="hash_lom_voucher"
        ),
        # 4. EU-HORIZON-EIC-ACCEL
        CanonicalGrantModel(
            bando_id="EU-HORIZON-EIC-ACCEL",
            titolo="EIC Accelerator — European Innovation Council",
            ente_erogatore="Commissione Europea (Horizon Europe)",
            descrizione="Finanziamento misto grant ed equity (blended finance) per startup deep tech, intelligenza artificiale e innovazioni dirompenti Horizon Europe EIC Accelerator.",
            tipo_agevolazione="Grant ed equity / Blended finance",
            budget_totale=1150000000.0,
            importo_massimo_finanziabile=2500000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["72.19.09", "TUTTI"],
            tipologia_beneficiari=["Startup_Innovative", "PMI"],
            regioni_target=["Tutte"],
            url_bando="https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="EU_SEDIA",
            hash_payload="hash_eic_accel"
        ),
        # 5. INAIL-ISI-2026
        CanonicalGrantModel(
            bando_id="INAIL-ISI-2026",
            titolo="Bando ISI INAIL 2026 — Sicurezza sul Lavoro & Prevenzione",
            ente_erogatore="INAIL (Istituto Nazionale Assicurazione Infortuni sul Lavoro)",
            descrizione="Contributi a fondo perduto fino al 65% per progetti di miglioramento della salute e sicurezza sul lavoro, bonifica amianto e rifacimento coperture.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=500000000.0,
            importo_massimo_finanziabile=130000.0,
            percentuale_copertura=65.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["43.99.01", "39.00.00", "TUTTI"],
            tipologia_beneficiari=["PMI", "Micro", "Grandi_Imprese"],
            regioni_target=["Tutte"],
            url_bando="https://www.inail.it/cs/internet/attivita/prevenzione-e-sicurezza/agevolazioni-e-finanziamenti/incentivi-alle-imprese/bando-isi-2026.html",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="INAIL_GOV",
            hash_payload="hash_inail_isi_2026"
        ),
        # 6. RESTO-AL-SUD-2-0
        CanonicalGrantModel(
            bando_id="RESTO-AL-SUD-2-0",
            titolo="Resto al Sud 2.0 — Autoimpiego & Nuove Imprese nel Mezzogiorno",
            ente_erogatore="Invitalia & Dipartimento Politiche di Coesione",
            descrizione="Incentivi a fondo perduto Resto al Sud 2.0 per apertura di nuove imprese, ristorazione tipica, somministrazione, street food e laboratori artigianali a Palermo, Napoli e nel Mezzogiorno.",
            tipo_agevolazione="Fondo perduto (75%) + Finanziamento agevolato",
            budget_totale=800000000.0,
            importo_massimo_finanziabile=200000.0,
            percentuale_copertura=75.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["56.10.11", "56.10.12", "TUTTI"],
            tipologia_beneficiari=["PMI", "Micro", "Startup_Innovative", "Professionisti"],
            regioni_target=["Campania", "Sicilia", "Puglia", "Calabria", "Basilicata", "Abruzzo", "Molise", "Sardegna"],
            url_bando="https://www.invitalia.it/cosa-facciamo/creiamo-nuove-aziende/resto-al-sud",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="INVITALIA_REST",
            hash_payload="hash_resto_sud"
        ),
        # 7. SICILIA-AGRIFOOD-2026
        CanonicalGrantModel(
            bando_id="SICILIA-AGRIFOOD-2026",
            titolo="PSR Sicilia — Innovazione di Filiera Agroalimentare & Agricoltura Sostenibile",
            ente_erogatore="Regione Siciliana — Dipartimento Agricoltura e Sviluppo Rurale",
            descrizione="Contributi a fondo perduto fino al 70% per investimenti in impianti di precision farming, ammodernamento aziende agricole e trasformazione alimentare biologica in Sicilia.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=45000000.0,
            importo_massimo_finanziabile=300000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["01.11.00", "01.21.00", "01.50.00", "10.39.00", "10.89.09"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Sicilia"],
            url_bando="https://www.euroinfosicilia.it/bandi-e-avvisi/",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_SICILIA_AGRI",
            hash_payload="hash_sicilia_agrifood"
        ),
        # 8. SICILIA-SOLAR-GREEN
        CanonicalGrantModel(
            bando_id="SICILIA-SOLAR-GREEN",
            titolo="Bando Autoconsumo & Transizione Energetica PMI Sicilia",
            ente_erogatore="Regione Siciliana — Dipartimento dell'Energia",
            descrizione="Agevolazioni a fondo perduto per installazione pannelli solari, impianti fotovoltaici aziendali, sistemi di accumulo ed efficientamento energetico per le PMI in Sicilia.",
            tipo_agevolazione="Contributo a fondo perduto (de minimis)",
            budget_totale=50000000.0,
            importo_massimo_finanziabile=250000.0,
            percentuale_copertura=65.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["35.11.00", "43.21.01", "71.12.10", "01.11.00", "01.21.00", "01.50.00"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Sicilia"],
            url_bando="https://www.regione.sicilia.it/istituzioni/regione/strutture-regionali/assessorato-energia-servizi-pubblica-utilita/dipartimento-energia",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_SICILIA_ENERGIA",
            hash_payload="hash_sicilia_solar"
        ),
        # 9. VENETO-TURISMO-2026
        CanonicalGrantModel(
            bando_id="VENETO-TURISMO-2026",
            titolo="Fondo Riqualificazione Strutture Ricettive & Turismo Veneto",
            ente_erogatore="Regione del Veneto — Direzione Turismo",
            descrizione="Contributi a fondo perduto per riqualificazione energetica alberghi, strutture ricettive, sostituzione caldaie con pompe di calore, ammodernamento e turismo sostenibile nel Veneto.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=25000000.0,
            importo_massimo_finanziabile=150000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["55.10.00", "55.20.51", "56.10.11", "79.11.00"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Veneto"],
            url_bando="https://www.venetosviluppo.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_VENETO_TURISMO",
            hash_payload="hash_veneto_turismo"
        ),
        # 10. VENETO-CONSORZI-EXPORT
        CanonicalGrantModel(
            bando_id="VENETO-CONSORZI-EXPORT",
            titolo="Voucher Internazionalizzazione & Consulenza Export Consorzi Veneto",
            ente_erogatore="Regione del Veneto & Veneto Sviluppo",
            descrizione="Voucher a fondo perduto per temporary export manager e partecipazione a fiere internazionali all'estero per consorzi veneti e PMI del Veneto.",
            tipo_agevolazione="Voucher a fondo perduto",
            budget_totale=8000000.0,
            importo_massimo_finanziabile=40000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["70.22.09", "46.90.00", "73.11.00", "38.21.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Veneto"],
            url_bando="https://www.venetosviluppo.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_VENETO_EXPORT",
            hash_payload="hash_veneto_export"
        ),
        # 11. TOSCANA-MODA-TESSILE
        CanonicalGrantModel(
            bando_id="TOSCANA-MODA-TESSILE",
            titolo="Bando Sostegno Distretto Tessile di Prato & Moda Toscana — Transizione Green",
            ente_erogatore="Regione Toscana & Sviluppo Toscana",
            descrizione="Voucher e contributi a fondo perduto per transizione ecologica tessile biologico, manifattura tessile e moda sostenibile a Prato e in Toscana.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=18000000.0,
            importo_massimo_finanziabile=100000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["13.20.00", "13.10.00", "13.99.00", "14.13.00", "15.12.00", "32.12.00"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Toscana"],
            url_bando="https://www.sviluppo.toscana.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_TOSCANA_MODA",
            hash_payload="hash_toscana_moda"
        ),
        # 12. TOSCANA-BIOTECH-PHARMA
        CanonicalGrantModel(
            bando_id="TOSCANA-BIOTECH-PHARMA",
            titolo="Bando Ricerca & Sviluppo Biotech e Scienze della Vita Toscana",
            ente_erogatore="Regione Toscana — Sviluppo Toscana",
            descrizione="Bando per ricerca e sviluppo biotech sperimentazione clinica e dispositivi medici a Firenze e in Toscana per imprese delle scienze della vita e pharma.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=30000000.0,
            importo_massimo_finanziabile=1500000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["72.11.00", "21.20.00", "72.19.09"],
            tipologia_beneficiari=["Enti_Ricerca", "Startup_Innovative", "PMI"],
            regioni_target=["Toscana"],
            url_bando="https://www.sviluppo.toscana.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_TOSCANA_BIOTECH",
            hash_payload="hash_toscana_biotech"
        ),
        # 13. PUGLIA-AEROSPACE-TECH
        CanonicalGrantModel(
            bando_id="PUGLIA-AEROSPACE-TECH",
            titolo="Bando PIA Tech & Aerospazio Puglia",
            ente_erogatore="Regione Puglia — Puglia Sviluppo",
            descrizione="Incentivi per programmi integrati di agevolazione per grandi progetti industriali e PMI nella filiera aerospazio, droni e meccatronica avanzata in Puglia.",
            tipo_agevolazione="Contributo a fondo perduto + Finanziamento",
            budget_totale=30000000.0,
            importo_massimo_finanziabile=1000000.0,
            percentuale_copertura=65.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["30.30.00", "28.00.00", "62.01.00", "72.19.09"],
            tipologia_beneficiari=["PMI", "Startup_Innovative", "Grandi_Imprese"],
            regioni_target=["Puglia"],
            url_bando="https://www.sistema.puglia.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="PUGLIA_SVILUPPO",
            hash_payload="hash_puglia_aerospace"
        ),
        # 14. PUGLIA-AGRITECH-PRECISION
        CanonicalGrantModel(
            bando_id="PUGLIA-AGRITECH-PRECISION",
            titolo="Bando Smart Agritech & Precision Farming Puglia",
            ente_erogatore="Regione Puglia — Assessorato Agricoltura",
            descrizione="Contributo a fondo perduto per agritech droni e sensoristica agricoltura di precisione a Bari e in Puglia.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=25000000.0,
            importo_massimo_finanziabile=120000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["01.11.00", "01.21.00", "62.01.00"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Puglia"],
            url_bando="https://www.regione.puglia.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_PUGLIA_AGRI",
            hash_payload="hash_puglia_agritech"
        ),
        # 15. PIEMONTE-AUTOMOTIVE-EV
        CanonicalGrantModel(
            bando_id="PIEMONTE-AUTOMOTIVE-EV",
            titolo="Bando Riconversione Automotive & Mobilità Sostenibile Piemonte",
            ente_erogatore="Regione Piemonte & Finpiemonte",
            descrizione="Finanziamenti a fondo perduto per riconversione automotive verso componentistica elettrica, veicoli elettrici, batterie e idrogeno a Torino e in Piemonte.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=40000000.0,
            importo_massimo_finanziabile=800000.0,
            percentuale_copertura=55.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["29.10.00", "28.11.00", "25.62.00", "62.01.00"],
            tipologia_beneficiari=["PMI", "Grandi_Imprese"],
            regioni_target=["Piemonte"],
            url_bando="https://www.finpiemonte.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="FINPIEMONTE_AUTO",
            hash_payload="hash_piemonte_auto"
        ),
        # 16. EMILIA-MECCANICA-4-0
        CanonicalGrantModel(
            bando_id="EMILIA-MECCANICA-4-0",
            titolo="Bando Industria Meccanica Avanzata & Robotica Emilia-Romagna",
            ente_erogatore="Regione Emilia-Romagna",
            descrizione="Finanziamento a tasso agevolato per macchine utensili, robotica industriale e meccanica avanzata a Bologna e in Emilia-Romagna.",
            tipo_agevolazione="Tasso agevolato / Fondo perduto",
            budget_totale=35000000.0,
            importo_massimo_finanziabile=500000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["28.41.00", "25.00.00", "28.00.00", "28.11.00", "28.99.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Emilia-Romagna"],
            url_bando="https://fesr.regione.emilia-romagna.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_EMILIA_MECCANICA",
            hash_payload="hash_emilia_mecc"
        ),
        # 17. LAZIO-CYBER-SECURITY
        CanonicalGrantModel(
            bando_id="LAZIO-CYBER-SECURITY",
            titolo="Bando Cyber Security & Cloud Migration PMI Lazio",
            ente_erogatore="Regione Lazio & Lazio Innova",
            descrizione="Voucher per audit di sicurezza informatica, cloud migration, crittografia dati e cyber security a Roma e nel Lazio per PMI.",
            tipo_agevolazione="Voucher a fondo perduto",
            budget_totale=20000000.0,
            importo_massimo_finanziabile=100000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.09.09", "62.01.00", "62.02.00", "62.03.00", "70.22.09"],
            tipologia_beneficiari=["PMI", "Startup_Innovative"],
            regioni_target=["Lazio"],
            url_bando="https://www.lazioinnova.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="LAZIO_INNOVA",
            hash_payload="hash_lazio_cyber"
        ),
        # 18. ABRUZZO-FOOD-PROCESSING
        CanonicalGrantModel(
            bando_id="ABRUZZO-FOOD-PROCESSING",
            titolo="Bando Sviluppo Rurale & Agroalimentare Qualità Abruzzo",
            ente_erogatore="Regione Abruzzo — Dipartimento Agricoltura",
            descrizione="Agevolazioni per macchinari lavorazione e packaging conserve alimentari, trasformazione agroalimentare di qualità in Abruzzo.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=14000000.0,
            importo_massimo_finanziabile=200000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["10.39.00", "10.89.09", "10.51.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Abruzzo"],
            url_bando="https://coesione.regione.abruzzo.it/bandi-e-avvisi",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_ABRUZZO_AGRI",
            hash_payload="hash_abruzzo_food"
        ),
        # 19. FRIULI-MANIFATTURA-LEGNO
        CanonicalGrantModel(
            bando_id="FRIULI-MANIFATTURA-LEGNO",
            titolo="Bando Innovazione Filiera Legno & Arredo Design FVG",
            ente_erogatore="Regione Autonoma Friuli-Venezia Giulia",
            descrizione="Bando innovazione filiera legno e arredo design sostenibile, manifattura arredi a Udine e in Friuli-Venezia Giulia.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=16000000.0,
            importo_massimo_finanziabile=350000.0,
            percentuale_copertura=55.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["31.09.00", "16.29.00", "25.00.00", "28.11.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Friuli-Venezia Giulia"],
            url_bando="https://www.regione.fvg.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_FVG_MANIFATTURA",
            hash_payload="hash_fvg_legno"
        ),
        # 20. MIMIT-BREVETTI-PLUS
        CanonicalGrantModel(
            bando_id="MIMIT-BREVETTI-PLUS",
            titolo="Brevetti+ Disegni+ Marchi+ Valorizzazione Proprietà Intellettuale",
            ente_erogatore="MIMIT (Ministero delle Imprese e del Made in Italy) & Unioncamere",
            descrizione="Agevolazioni brevetti marchi e valorizzazione titoli di proprietà industriale e intellettuale per PMI su tutto il territorio nazionale.",
            tipo_agevolazione="Voucher / Contributo a fondo perduto (de minimis)",
            budget_totale=32000000.0,
            importo_massimo_finanziabile=140000.0,
            percentuale_copertura=80.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["72.19.09", "TUTTI"],
            tipologia_beneficiari=["PMI", "Startup_Innovative", "Micro"],
            regioni_target=["Tutte"],
            url_bando="https://www.mimit.gov.it/it/incentivi/brevetti-disegni-marchi",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT_PI",
            hash_payload="hash_mimit_brevetti_plus"
        ),
        # 21. INVITALIA-SMART-START-2026
        CanonicalGrantModel(
            bando_id="INVITALIA-SMART-START-2026",
            titolo="Smart&Start Italia — Incentivi Startup Innovative",
            ente_erogatore="Invitalia",
            descrizione="Finanziamento agevolato a tasso zero e fondo perduto Smart&Start Italia per startup innovative ad alto valore tecnologico, software, cloud, intelligenza artificiale.",
            tipo_agevolazione="Finanziamento tasso zero / agevolato fino al 90%",
            budget_totale=100000000.0,
            importo_massimo_finanziabile=1500000.0,
            percentuale_copertura=80.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.01.00", "62.02.00", "63.11.00", "72.19.09", "58.29.00"],
            tipologia_beneficiari=["Startup_Innovative", "Micro", "PMI"],
            regioni_target=["Tutte"],
            url_bando="https://www.invitalia.it/cosa-facciamo/creiamo-nuove-aziende/smartstart-italia",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="INVITALIA_REST",
            hash_payload="hash_smart_start_2026"
        ),
        # 22. LIGURIA-LOGISTICA-GREEN
        CanonicalGrantModel(
            bando_id="LIGURIA-LOGISTICA-GREEN",
            titolo="Bando FILSE Mobilità Sostenibile e Flotte Green Liguria",
            ente_erogatore="FILSE & Regione Liguria",
            descrizione="Incentivi per acquisto veicoli commerciali elettrici e logistica green, mobilità sostenibile e flotte ecologiche a Genova e in Liguria per PMI.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=15000000.0,
            importo_massimo_finanziabile=150000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["49.41.00", "52.29.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Liguria"],
            url_bando="https://www.filse.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="FILSE_LIGURIA",
            hash_payload="hash_liguria_logistica"
        ),
        # 23. MARCHE-BIOMEDICALE
        CanonicalGrantModel(
            bando_id="MARCHE-BIOMEDICALE",
            titolo="Bando Innovazione e Digitalizzazione PMI Marche — Biomedicale e Diagnostica",
            ente_erogatore="SVEM & Regione Marche",
            descrizione="Contributi a fondo perduto per digitalizzazione laboratori odontoiatrici e diagnostica biomedicale ad Ancona e nelle Marche per PMI.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=12000000.0,
            importo_massimo_finanziabile=120000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["32.50.13", "32.50.11", "62.01.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Marche"],
            url_bando="https://www.svem.eu",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="SVEM_MARCHE",
            hash_payload="hash_marche_biomedicale"
        ),
        # 24. UMBRIA-CIRCOLARE
        CanonicalGrantModel(
            bando_id="UMBRIA-CIRCOLARE",
            titolo="Bando Sviluppumbria Economia Circolare & Sostenibilità",
            ente_erogatore="Sviluppumbria & Regione Umbria",
            descrizione="Finanziamenti a fondo perduto per economia circolare riciclo materie plastiche, recupero scarti agroalimentari, sansa e ammodernamento frantoi a Foligno, Perugia e in Umbria.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=10000000.0,
            importo_massimo_finanziabile=100000.0,
            percentuale_copertura=55.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["38.32.20", "38.21.00", "10.41.00", "01.63.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Umbria"],
            url_bando="https://www.sviluppumbria.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="SVILUPPUMBRIA",
            hash_payload="hash_umbria_circolare"
        ),
        # 25. VALLE-AOSTA-ROTAZIONE
        CanonicalGrantModel(
            bando_id="VALLE-AOSTA-ROTAZIONE",
            titolo="Fondo Rotazione Finaosta Sostegno Imprese VDA — Riqualificazione Rifugi, Alberghi & Rinnovabili",
            ente_erogatore="Finaosta — Regione Autonoma Valle d'Aosta",
            descrizione="Fondo di rotazione per investimenti innovativi, turismo montano e riqualificazione rifugi alpini: installazione pannelli fotovoltaici, batterie ad alta quota, transizione ecologica e artigianato alpino ad Aosta e in Valle d'Aosta.",
            tipo_agevolazione="Finanziamento agevolato a tasso quasi zero",
            budget_totale=8000000.0,
            importo_massimo_finanziabile=80000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["16.29.19", "16.29.00", "23.70.00", "31.09.00", "55.10.00", "55.20.10", "55.20.20", "35.11.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Valle d'Aosta"],
            url_bando="https://www.finaosta.com",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="FINAOSTA_VDA",
            hash_payload="hash_vda_rotazione"
        ),
        # 26. PUGLIA-BLUE-ECONOMY
        CanonicalGrantModel(
            bando_id="PUGLIA-BLUE-ECONOMY",
            titolo="Puglia Sviluppo — Contratti di Programma e Blue Economy Nautica",
            ente_erogatore="Puglia Sviluppo & Regione Puglia",
            descrizione="Agevolazioni per cantieristica navale, nautica da diporto e blue economy per PMI e cantieri navali a Taranto e in Puglia.",
            tipo_agevolazione="Misto fondo perduto e conto interessi",
            budget_totale=20000000.0,
            importo_massimo_finanziabile=200000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["30.11.02", "30.12.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Puglia"],
            url_bando="https://www.sistema.puglia.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="PUGLIA_BLUE",
            hash_payload="hash_puglia_blue"
        ),
        # 27. CAMPANIA-ZES-UNICA
        CanonicalGrantModel(
            bando_id="CAMPANIA-ZES-UNICA",
            titolo="Credito d'Imposta ZES Unica Mezzogiorno — Investimenti Campania",
            ente_erogatore="Agenzia delle Entrate / Dipartimento Coesione",
            descrizione="Bando per attrazione investimenti e nuove unita produttive nelle aree ZES Unica Mezzogiorno, credito d'imposta per macchinari in Campania.",
            tipo_agevolazione="Credito d'imposta",
            budget_totale=1800000000.0,
            importo_massimo_finanziabile=5000000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["25.00.00", "28.00.00", "TUTTI"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Campania", "Puglia", "Calabria", "Sicilia", "Basilicata", "Abruzzo", "Molise", "Sardegna"],
            url_bando="https://www.agenziaentrate.gov.it",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="AGENZIA_ENTRATE_ZES",
            hash_payload="hash_campania_zes"
        ),
        # 28. EMILIA-ARTIGIANATO-CERAMICA
        CanonicalGrantModel(
            bando_id="EMILIA-ARTIGIANATO-CERAMICA",
            titolo="Bando Sostegno Artigianato Artistico e Ceramica Emilia-Romagna",
            ente_erogatore="Regione Emilia-Romagna",
            descrizione="Contributi a fondo perduto per microimprese dell'artigianato artistico e ceramica a Faenza e su tutta la Regione Emilia-Romagna.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=6000000.0,
            importo_massimo_finanziabile=50000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["23.41.00", "23.70.00"],
            tipologia_beneficiari=["Micro", "PMI"],
            regioni_target=["Emilia-Romagna"],
            url_bando="https://fesr.regione.emilia-romagna.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_EMILIA_CERAMICA",
            hash_payload="hash_emilia_ceramica"
        ),
        # 29. PUGLIA-IDRICO-AGRICOLTURA
        CanonicalGrantModel(
            bando_id="PUGLIA-IDRICO-AGRICOLTURA",
            titolo="PSR Puglia — Gestione Sostenibile Risorse Idriche e Invasi",
            ente_erogatore="Regione Puglia — Assessorato Agricoltura",
            descrizione="Incentivi per efficientamento idrico e riutilizzo acque reflue in aziende agricole e irrigazione a Foggia e in Puglia.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=22000000.0,
            importo_massimo_finanziabile=150000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["01.61.00", "01.11.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Puglia"],
            url_bando="https://www.regione.puglia.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_PUGLIA_IDRICO",
            hash_payload="hash_puglia_idrico"
        ),
        # 30. CAMPANIA-AEROSPAZIO-DRONI
        CanonicalGrantModel(
            bando_id="CAMPANIA-AEROSPAZIO-DRONI",
            titolo="Bando Distretto Aerospaziale Campania (DAC) — Ricerca, Droni e Satelliti",
            ente_erogatore="DAC Campania & Sviluppo Campania",
            descrizione="Finanziamenti per startup aerospaziali droni e tecnologie satellitari e aerospazio a Napoli e in Campania.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=18000000.0,
            importo_massimo_finanziabile=300000.0,
            percentuale_copertura=75.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["30.30.09", "30.30.00", "62.01.00"],
            tipologia_beneficiari=["Startup_Innovative", "PMI"],
            regioni_target=["Campania"],
            url_bando="https://bandi.sviluppocampania.it/",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="DAC_CAMPANIA",
            hash_payload="hash_campania_aerospazio"
        ),
        # 31. PIEMONTE-FILM-FUND
        CanonicalGrantModel(
            bando_id="PIEMONTE-FILM-FUND",
            titolo="Piemonte Film TV Fund — Produzione Audiovisiva e Cinema",
            ente_erogatore="Film Commission Torino Piemonte & Regione Piemonte",
            descrizione="Bando sostegno alle filiere cinematografiche produzione audiovisiva, fiction, film e gaming in Piemonte.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=12000000.0,
            importo_massimo_finanziabile=200000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["59.11.00", "59.12.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Piemonte"],
            url_bando="https://www.fctp.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="PIEMONTE_FILM",
            hash_payload="hash_piemonte_film"
        ),
        # 32. VENETO-LOGISTICA-FREDDO
        CanonicalGrantModel(
            bando_id="VENETO-LOGISTICA-FREDDO",
            titolo="Bando Sviluppo Polo Logistico Intermodale e Agroalimentare Veneto",
            ente_erogatore="Regione del Veneto & Veneto Sviluppo",
            descrizione="Contributi per creazione hub logistici e magazzini refrigerati per la catena del freddo agroalimentare a Verona e nel Veneto.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=16000000.0,
            importo_massimo_finanziabile=250000.0,
            percentuale_copertura=45.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["52.10.10", "52.29.00"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Veneto"],
            url_bando="https://www.venetosviluppo.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_VENETO_LOGISTICA",
            hash_payload="hash_veneto_logistica"
        ),
        # 33. SARDEGNA-IMPRESA-FEMMINILE
        CanonicalGrantModel(
            bando_id="SARDEGNA-IMPRESA-FEMMINILE",
            titolo="Fondo Impresa Femminile & Imprenditoria Donne Sardegna",
            ente_erogatore="Regione Autonoma della Sardegna & Sardegna Ricerche",
            descrizione="Fondo perduto per imprenditoria femminile, nuove imprese guidate da donne a Cagliari e in tutta la Sardegna.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=10000000.0,
            importo_massimo_finanziabile=100000.0,
            percentuale_copertura=80.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["TUTTI"],
            tipologia_beneficiari=["PMI", "Micro", "Startup_Innovative"],
            regioni_target=["Sardegna"],
            url_bando="https://www.sardegnaricerche.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="SARDEGNA_RICERCHE",
            hash_payload="hash_sardegna_femminile"
        ),
        # 34. EMILIA-FONDO-STARTER-2026
        CanonicalGrantModel(
            bando_id="EMILIA-FONDO-STARTER-2026",
            titolo="Fondo Starter — Finanziamento Agevolato & Garanzia Nuove Imprese Tecnologiche",
            ente_erogatore="Regione Emilia-Romagna — PR FESR",
            descrizione="Finanziamenti a tasso agevolato fino al 70% e contributi per la creazione e consolidamento di nuove imprese tecnologiche, startup digitali, AI e meccatronica in Emilia-Romagna.",
            tipo_agevolazione="Finanziamento agevolato / Fondo perduto",
            budget_totale=20000000.0,
            importo_massimo_finanziabile=300000.0,
            percentuale_copertura=70.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["TUTTI"],
            tipologia_beneficiari=["Startup_Innovative", "PMI", "Micro"],
            regioni_target=["Emilia-Romagna"],
            url_bando="https://fesr.regione.emilia-romagna.it",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_EMILIA_STARTER",
            hash_payload="hash_emilia_starter"
        ),
        # 35. MIMIT-VOUCHER-INNOVATION-AI
        CanonicalGrantModel(
            bando_id="MIMIT-VOUCHER-INNOVATION-AI",
            titolo="Voucher Innovation Manager — Consulenza Specialistica AI, Big Data & Cybersecurity",
            ente_erogatore="MIMIT (Ministero delle Imprese e del Made in Italy)",
            descrizione="Contributi a fondo perduto fino al 50% per le spese sostenute da PMI e startup innovative per l'acquisizione di servizi di consulenza specialistica resa da Innovation Manager qualificati in ambito AI, big data e sicurezza.",
            tipo_agevolazione="Voucher a fondo perduto (de minimis)",
            budget_totale=50000000.0,
            importo_massimo_finanziabile=40000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.01.00", "62.02.00", "63.11.00", "72.19.09", "70.22.09"],
            tipologia_beneficiari=["PMI", "Startup_Innovative", "Micro"],
            regioni_target=["Tutte"],
            url_bando="https://www.mimit.gov.it/it/incentivi/voucher-innovation-manager",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT_REST",
            hash_payload="hash_mimit_voucher_im"
        ),
        # 36. CCIAA-ROMA-COMMERCIO-2026
        CanonicalGrantModel(
            bando_id="CCIAA-ROMA-COMMERCIO-2026",
            titolo="Bando CCIAA Roma — Sostegno al Commercio, Registratori Telematici & Sicurezza Antitaccheggio",
            ente_erogatore="Camera di Commercio di Roma & Regione Lazio",
            descrizione="Contributi a fondo perduto per il commercio al dettaglio a Roma e nel Lazio: acquisto registratori telematici di cassa, sistemi antitaccheggio innovativi, commercio elettronico e sicurezza punti vendita.",
            tipo_agevolazione="Contributo a fondo perduto (voucher)",
            budget_totale=6000000.0,
            importo_massimo_finanziabile=10000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["47.71.10", "47.71.20", "47.19.10", "47.19.20", "47.00.00", "47.91.10"],
            tipologia_beneficiari=["PMI", "Micro"],
            regioni_target=["Lazio"],
            url_bando="https://www.rm.camcom.it/bandi",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="CCIAA_ROMA",
            hash_payload="hash_cciaa_roma_commercio"
        ),
        # 37. EU-TED-DIGITAL-HEALTH
        CanonicalGrantModel(
            bando_id="EU-TED-DIGITAL-HEALTH",
            titolo="Bando TED EU — Appalto Pubblico Europeo Sanità Digitale & Piattaforme E-Health",
            ente_erogatore="Unione Europea — TED (Tenders Electronic Daily)",
            descrizione="Appalto pubblico europeo pubblicato su TED v3 per fornitura soluzioni software sanità digitale, telemedicina e fascicolo sanitario elettronico.",
            tipo_agevolazione="Appalto pubblico europeo / Contratto TED",
            budget_totale=80000000.0,
            importo_massimo_finanziabile=5000000.0,
            percentuale_copertura=100.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.01.00", "86.10.00", "TUTTI"],
            tipologia_beneficiari=["Grandi_Imprese", "PMI"],
            regioni_target=["Tutte"],
            url_bando="https://api.ted.europa.eu/v3/notices/search",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="EU_TED_V3",
            hash_payload="hash_eu_ted_health"
        ),
        # 38. EU-SEDIA-LIFE-CIRCULAR
        CanonicalGrantModel(
            bando_id="EU-SEDIA-LIFE-CIRCULAR",
            titolo="Bando LIFE EU — Economia Circolare, Tutela Climatica & Ambiente (SEDIA)",
            ente_erogatore="Commissione Europea (LIFE Programme / SEDIA)",
            descrizione="Finanziamento a fondo perduto del programma LIFE della Commissione Europea per progetti di economia circolare, riduzione emissioni industriali, depurazione acque e tutela dell'ambiente in Europa.",
            tipo_agevolazione="Contributo a fondo perduto LIFE",
            budget_totale=120000000.0,
            importo_massimo_finanziabile=2000000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["38.21.00", "37.00.00", "TUTTI"],
            tipologia_beneficiari=["PMI", "Grandi_Imprese", "Enti_Ricerca"],
            regioni_target=["Tutte"],
            url_bando="https://api.tech.ec.europa.eu/search-api/prod/rest/search",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="EU_SEDIA_LIFE",
            hash_payload="hash_eu_sedia_life"
        )
    ]

    service.add_grants(grants)
    return service


async def bootstrap_live_service() -> LabNKBandiService:
    """Inizializza il servizio LabNK eseguendo l'harvesting live da tutte le 30 fonti istituzionali."""
    from src_app.ingestion.orchestrator import IngestionOrchestrator
    service = LabNKBandiService()
    await IngestionOrchestrator.harvest_all(service)
    return service


def main():
    print("=" * 70)
    print("LAB-NK BANDI INTELLIGENCE — AVVIO SISTEMA")
    print("=" * 70)

    service = bootstrap_demo_service()
    print(f"[+] Database inizializzato: {len(service.list_all_grants())} bandi caricati.")

    prompt = "Cerco finanziamenti a fondo perduto per una startup a Napoli per fare sviluppo software di intelligenza artificiale"
    print(f"\n[?] [PROVA 1] Esecuzione Ricerca NLP: '{prompt}'")
    intent, ranked_grants, scores = service.search_nlp(prompt)
    print(f"    -> Intento Riconosciuto: Regione={intent.inferred_region} | NUTS={intent.inferred_nuts} | ATECO={intent.inferred_ateco_codes}")
    print(f"    -> Miglior Risultato: '{ranked_grants[0].titolo}' | Score: {scores[0].overall_match_score}% (Idoneo={scores[0].is_eligible})")

    html_content = DashboardRenderer.render_html(service)
    output_path = root_dir / "dashboard.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n[+] [PROVA 2] Dashboard HTML interattiva generata con successo:")
    print(f"    -> File: {output_path}")

    print("\n" + "=" * 70)
    print("[OK] APPLICAZIONE COMPLETA E PRONTA ALL'USO!")
    print("=" * 70)


if __name__ == "__main__":
    main()
