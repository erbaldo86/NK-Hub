"""Unit & Integration Tests for Dual Search & Match Scoring Engine (Step 4).
Nexus Keystone v1.1.0-Universal | Zero-Mock / CRV 4.0.
"""

import pytest
from datetime import datetime, timezone
from typing import List

from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo
from src_app.search.ateco_tree import AtecoTree
from src_app.search.nlp_intent_extractor import SmartIntentExtractor, SearchIntent
from src_app.search.parametric_filter import ParametricFilter, ParametricFilterCriteria
from src_app.matching.profile_model import CompanyProfile, MatchScoreBreakdown
from src_app.matching.scoring_engine import MatchScoringEngine
from src_app.service.bandi_service import LabNKBandiService


@pytest.fixture
def sample_grants() -> List[CanonicalGrantModel]:
    now = datetime.now(timezone.utc)
    return [
        CanonicalGrantModel(
            bando_id="REG-CAMP-AI-01",
            titolo="Bando Campania AI & Big Data",
            ente_erogatore="Regione Campania",
            descrizione="Agevolazioni a fondo perduto per l'adozione di soluzioni AI nelle PMI campane.",
            tipo_agevolazione="Contributo a fondo perduto (de minimis)",
            budget_totale=15000000.0,
            importo_massimo_finanziabile=200000.0,
            percentuale_copertura=80.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["62.01.00", "62.02.00", "72.19.09"],
            tipologia_beneficiari=["PMI", "Startup_Innovative"],
            regioni_target=["Campania"],
            url_bando="https://innovazione.regione.campania.it/ai-pmi",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_CAMPANIA",
            hash_payload="hash_campania_01"
        ),
        CanonicalGrantModel(
            bando_id="NAT-MIMIT-GREEN-02",
            titolo="Transizione Green & Fotovoltaico Nazionale",
            ente_erogatore="MIMIT",
            descrizione="Incentivi nazionali per efficientamento energetico e impianti solari.",
            tipo_agevolazione="Contributo a fondo perduto",
            budget_totale=50000000.0,
            importo_massimo_finanziabile=500000.0,
            percentuale_copertura=50.0,
            data_apertura=now,
            stato=BandoStato.APERTO,
            settori_beneficiari=["TUTTI"],
            tipologia_beneficiari=["PMI", "Grandi_Imprese"],
            regioni_target=["Tutte"],
            url_bando="https://mimit.gov.it/green-investments",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT_REST",
            hash_payload="hash_mimit_02"
        ),
        CanonicalGrantModel(
            bando_id="REG-LOM-CLOSED-03",
            titolo="Innovazione Digitale Lombardia (Scaduto)",
            ente_erogatore="Regione Lombardia",
            descrizione="Misure per il commercio elettronico scadute.",
            tipo_agevolazione="Voucher digitalizzazione",
            budget_totale=5000000.0,
            importo_massimo_finanziabile=10000.0,
            percentuale_copertura=60.0,
            data_apertura=now,
            stato=BandoStato.CHIUSO,
            settori_beneficiari=["47.91.10"],
            tipologia_beneficiari=["PMI"],
            regioni_target=["Lombardia"],
            url_bando="https://regione.lombardia.it/bando-chiuso",
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            fonte_nome="REG_LOMBARDIA",
            hash_payload="hash_lom_03"
        )
    ]


# ---------------------------------------------------------------------------
# 1. TEST ATECO TREE & HIERARCHICAL RESOLVER
# ---------------------------------------------------------------------------

def test_ateco_normalization_and_hierarchy():
    """Verifica la normalizzazione dei codici ATECO e la compatibilità per prefisso."""
    assert AtecoTree.normalize_code("620100") == "62.01.00"
    assert AtecoTree.normalize_code("6201") == "62.01"
    assert AtecoTree.normalize_code("62") == "62"
    assert AtecoTree.normalize_code("TUTTI") == "TUTTI"

    assert AtecoTree.is_code_compatible(["62"], ["62.01.00"]) is True
    assert AtecoTree.is_code_compatible(["62.01"], ["62.01.00"]) is True
    assert AtecoTree.is_code_compatible(["47.91.10"], ["62.01.00"]) is False
    assert AtecoTree.is_code_compatible(["TUTTI"], ["99.99.99"]) is True


def test_ateco_inference_from_text():
    """Verifica l'inferenza di codici ATECO da testo semantico."""
    inferred_ai = AtecoTree.infer_ateco_from_text("Sviluppo di modelli di intelligenza artificiale e software cloud")
    assert "62.01.00" in inferred_ai
    assert "72.19.09" in inferred_ai or "62.03.00" in inferred_ai


# ---------------------------------------------------------------------------
# 2. TEST SMART NLP INTENT EXTRACTOR
# ---------------------------------------------------------------------------

def test_nlp_intent_extractor_startup_query():
    """Verifica l'estrazione accurata dei parametri di ricerca da prompt in linguaggio naturale."""
    query = "Cerco fondi a fondo perduto per una startup innovativa a Napoli per fare software di intelligenza artificiale con budget di 80 mila euro"
    intent = SmartIntentExtractor.extract_intent(query)

    assert isinstance(intent, SearchIntent)
    assert intent.inferred_region == "Campania"
    assert intent.inferred_nuts == "ITF33"
    assert "Startup_Innovative" in intent.inferred_beneficiary_types
    assert "fondo_perduto" in intent.inferred_funding_types
    assert intent.inferred_budget == 80000.0
    assert "62.01.00" in intent.inferred_ateco_codes


# ---------------------------------------------------------------------------
# 3. TEST PARAMETRIC FILTER
# ---------------------------------------------------------------------------

def test_parametric_filter_ateco_and_region(sample_grants):
    """Verifica il filtraggio multi-dimensionale combinatorio."""
    criteria_1 = ParametricFilterCriteria(
        ateco_codes=["62.01.00"],
        regioni_target=["Campania"],
        stato=BandoStato.APERTO
    )
    res_1 = ParametricFilter.filter_grants(sample_grants, criteria_1)
    assert len(res_1) == 2
    ids_1 = [g.bando_id for g in res_1]
    assert "REG-CAMP-AI-01" in ids_1
    assert "NAT-MIMIT-GREEN-02" in ids_1
    assert "REG-LOM-CLOSED-03" not in ids_1

    criteria_2 = ParametricFilterCriteria(
        min_percentuale_copertura=70.0,
        stato=BandoStato.APERTO
    )
    res_2 = ParametricFilter.filter_grants(sample_grants, criteria_2)
    assert len(res_2) == 1
    assert res_2[0].bando_id == "REG-CAMP-AI-01"


# ---------------------------------------------------------------------------
# 4. TEST MATCH SCORING ENGINE (COMPATIBILITY & BLOCKING GATES)
# ---------------------------------------------------------------------------

def test_match_scoring_eligible_startup(sample_grants):
    """Verifica l'assegnazione di un punteggio elevato e l'eleggibilità di una startup compatibile."""
    bando_campania = sample_grants[0]

    profile = CompanyProfile(
        company_name="Nexus AI Lab SRL",
        legal_form="Startup_Innovativa",
        company_size="Startup_Innovative",
        ateco_codes=["62.01.00"],
        headquarters_nuts="ITF3",
        operational_region="Campania",
        youth_ownership=True,
        female_ownership=True,
        de_minimis_accumulated_3yr=50000.0,
        target_investment_amount=150000.0
    )

    breakdown = MatchScoringEngine.calculate_match(bando_campania, profile)

    assert breakdown.is_eligible is True
    assert len(breakdown.blocking_failures) == 0
    assert breakdown.overall_match_score >= 85.0
    assert len(breakdown.bonus_points) >= 2


def test_match_scoring_blocking_failure_ateco(sample_grants):
    """Verifica il blocco categorico di un'azienda con codice ATECO non ammesso."""
    bando_campania = sample_grants[0]

    profile_ineligible = CompanyProfile(
        company_name="Ristorante Tipico SRL",
        legal_form="SRL",
        company_size="Micro",
        ateco_codes=["56.10.11"],
        headquarters_nuts="ITF3",
        operational_region="Campania"
    )

    breakdown = MatchScoringEngine.calculate_match(bando_campania, profile_ineligible)

    assert breakdown.is_eligible is False
    assert any("ATECO" in fail for fail in breakdown.blocking_failures)
    assert breakdown.overall_match_score <= 35.0


def test_match_scoring_blocking_failure_closed_bando(sample_grants):
    """Verifica il blocco di un bando chiuso per decorrenza termini."""
    bando_chiuso = sample_grants[2]

    profile = CompanyProfile(
        company_name="Ecommerce Milano SRL",
        legal_form="SRL",
        company_size="Piccola",
        ateco_codes=["47.91.10"],
        headquarters_nuts="ITC4",
        operational_region="Lombardia"
    )

    breakdown = MatchScoringEngine.calculate_match(bando_chiuso, profile)

    assert breakdown.is_eligible is False
    assert any("CHIUSO" in fail for fail in breakdown.blocking_failures)


# ---------------------------------------------------------------------------
# 5. TEST SEMANTIC BOOST & VERTICAL DISAMBIGUATION (AMIANTO & FOTOVOLTAICO)
# ---------------------------------------------------------------------------

def test_ateco_inference_amianto_and_fotovoltaico():
    """Verifica che query su amianto e fotovoltaico inferiscano codici ATECO precisi e non TUTTI."""
    inferred_amianto = AtecoTree.infer_ateco_from_text("Progetto per bonifica amianto e rifacimento coperture")
    assert "39.00.00" in inferred_amianto or "43.99.09" in inferred_amianto
    assert "TUTTI" not in inferred_amianto

    inferred_solar = AtecoTree.infer_ateco_from_text("Installazione impianti fotovoltaici e pannelli solari per autoproduzione")
    assert "35.11.00" in inferred_solar or "43.21.01" in inferred_solar
    assert "TUTTI" not in inferred_solar


def test_semantic_boost_ranking_vertical_vs_generic():
    """Verifica che il ranking con boost semantico premi i bandi verticali rispetto a quelli generici."""
    now = datetime.now(timezone.utc)
    service = LabNKBandiService()

    # Bando specifico verticale amianto
    bando_inail = CanonicalGrantModel(
        bando_id="INAIL-ISI-SPECIFIC",
        titolo="Bando ISI INAIL — Bonifica Amianto e Sicurezza",
        ente_erogatore="INAIL",
        descrizione="Contributi a fondo perduto per la rimozione e bonifica amianto nelle strutture aziendali.",
        tipo_agevolazione="Fondo perduto",
        budget_totale=100000000.0,
        importo_massimo_finanziabile=130000.0,
        percentuale_copertura=65.0,
        data_apertura=now,
        stato=BandoStato.APERTO,
        settori_beneficiari=["TUTTI"],
        tipologia_beneficiari=["PMI"],
        regioni_target=["Tutte"],
        url_bando="https://inail.it/isi",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="INAIL",
        hash_payload="hash_inail_spec"
    )

    # Bando orizzontale generico senza menzione di amianto
    bando_generico = CanonicalGrantModel(
        bando_id="GENERICO-HORIZON",
        titolo="Bando Orizzontale Innovazione Nazionale",
        ente_erogatore="Ministero Sviluppo",
        descrizione="Agevolazioni generiche per investimenti industriali e digitali.",
        tipo_agevolazione="Fondo perduto",
        budget_totale=500000000.0,
        importo_massimo_finanziabile=500000.0,
        percentuale_copertura=75.0,
        data_apertura=now,
        stato=BandoStato.APERTO,
        settori_beneficiari=["TUTTI"],
        tipologia_beneficiari=["PMI"],
        regioni_target=["Tutte"],
        url_bando="https://ministero.gov.it/generico",
        fonte_tipo=FonteTipo.REST_API,
        fonte_nome="MINISTERO",
        hash_payload="hash_gen_spec"
    )

    service.add_grants([bando_generico, bando_inail])

    intent, ranked_grants, scores = service.search_nlp("Cerco contributi per bonifica amianto")
    assert len(ranked_grants) >= 1
    assert ranked_grants[0].bando_id == "INAIL-ISI-SPECIFIC"
    assert scores[0].is_eligible is True


def test_semantic_boost_batch2_domains():
    """Verifica l'accuratezza di ranking per i domini complessi del Batch 2 (Biotech, TEM, Automotive, Deep Tech)."""
    from src_app.app import bootstrap_demo_service
    service = bootstrap_demo_service()

    # 1. Biotech & Pharma Toscana
    _, g_biotech, _ = service.search_nlp("scienze della vita biotech e sperimentazione clinica toscana")
    assert len(g_biotech) >= 1
    assert g_biotech[0].bando_id == "TOSCANA-BIOTECH-PHARMA"

    # 2. TEM & Consulenza Export Veneto
    _, g_tem, _ = service.search_nlp("temporary export manager e consulenza fiere veneto")
    assert len(g_tem) >= 1
    assert g_tem[0].bando_id == "VENETO-CONSORZI-EXPORT"

    # 3. Automotive & Mobilità Elettrica Piemonte
    _, g_auto, _ = service.search_nlp("riconversione automotive idrogeno e veicoli elettrici piemonte")
    assert len(g_auto) >= 1
    assert g_auto[0].bando_id == "PIEMONTE-AUTOMOTIVE-EV"

    # 4. Deep Tech Horizon Europe EIC Accelerator
    _, g_eu, _ = service.search_nlp("deep tech horizon europe blended finance ed equity startup")
    assert len(g_eu) >= 1
    assert g_eu[0].bando_id == "EU-HORIZON-EIC-ACCEL"


def test_search_nlp_semantic_relevance_filtering():
    """Verifica che lo Strict Relevance Filter escluda bandi non pertinenti e mantenga quelli verticali."""
    from src_app.app import bootstrap_demo_service
    service = bootstrap_demo_service()

    intent, ranked_grants, scores = service.search_nlp("fotovoltaico")

    # Asserzioni su lunghezza e pertinenza semantica
    assert len(ranked_grants) > 0
    assert len(ranked_grants) <= 15

    # Il bando primario deve essere incentrato su solare/energia
    assert ranked_grants[0].bando_id in ("SICILIA-SOLAR-GREEN", "MIMIT-TRANS-5-0")

    # Nessun bando non pertinente su moda, calzaturiero o agroalimentare deve essere presente
    retrieved_ids = [g.bando_id for g in ranked_grants]
    assert "TOSCANA-MODA-TESSILE" not in retrieved_ids
    assert "SICILIA-AGRIFOOD-2026" not in retrieved_ids
    assert "ABRUZZO-FOOD-PROCESSING" not in retrieved_ids



