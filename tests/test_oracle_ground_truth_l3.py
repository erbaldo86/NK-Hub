"""Integration & Ground Truth Oracle Tests for LabNK Bandi Intelligence.
Nexus Keystone v1.1.0-Universal | Deterministic Oracle L3.
"""

import pytest
from datetime import datetime, timezone
from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo
from src_app.search.ateco_tree import AtecoTree
from src_app.search.nlp_intent_extractor import SmartIntentExtractor, SearchIntent
from src_app.search.parametric_filter import ParametricFilter, ParametricFilterCriteria
from src_app.matching.profile_model import CompanyProfile, MatchScoreBreakdown
from src_app.matching.scoring_engine import MatchScoringEngine
from src_app.service.bandi_service import LabNKBandiService
from src_app.ui.dashboard import DashboardRenderer
from src_app.app import bootstrap_demo_service


class TestOracleGroundTruthL3:
    """Suite di validazione formale oracolo deterministico L3."""

    def test_ateco_and_nuts_territorial_coverage(self):
        """Verifica che tutte le 20 regioni e le divisioni ATECO siano coperte in modo accurato."""
        regions = [
            ("lombardia", "Lombardia", "ITC4"),
            ("campania", "Campania", "ITF3"),
            ("lazio", "Lazio", "ITI4"),
            ("piemonte", "Piemonte", "ITC1"),
            ("veneto", "Veneto", "ITH3"),
            ("emilia-romagna", "Emilia-Romagna", "ITH5"),
            ("toscana", "Toscana", "ITI1"),
            ("puglia", "Puglia", "ITF4"),
            ("sicilia", "Sicilia", "ITG1"),
            ("calabria", "Calabria", "ITF6"),
            ("sardegna", "Sardegna", "ITG2"),
            ("liguria", "Liguria", "ITC3"),
            ("marche", "Marche", "ITI3"),
            ("abruzzo", "Abruzzo", "ITF1"),
            ("friuli", "Friuli-Venezia Giulia", "ITH4"),
            ("trentino", "Trentino-Alto Adige", "ITH2"),
            ("umbria", "Umbria", "ITI2"),
            ("basilicata", "Basilicata", "ITF5"),
            ("molise", "Molise", "ITF2"),
            ("valle d'aosta", "Valle d'Aosta", "ITC2")
        ]
        for key, reg, nuts in regions:
            assert key in SmartIntentExtractor.LOCATION_MAP
            m_reg, m_nuts = SmartIntentExtractor.LOCATION_MAP[key]
            assert m_reg == reg
            assert m_nuts == nuts

    def test_ateco_zero_padding_hierarchical_matching(self):
        """Verifica compatibilità gerarchica con codici divisione/gruppo sia padded che unpadded."""
        assert AtecoTree.is_code_compatible(["28.00.00"], ["28.11.00"]) is True
        assert AtecoTree.is_code_compatible(["62.00.00"], ["62.01.00"]) is True
        assert AtecoTree.is_code_compatible(["62.01"], ["62.01.00"]) is True
        assert AtecoTree.is_code_compatible(["47.91.10"], ["62.01.00"]) is False

    @pytest.mark.parametrize("query,exp_reg,exp_nuts,exp_ben,exp_fund,exp_budget", [
        (
            "Startup innovativa agritech a Bari cerca voucher a fondo perduto di 50 mila euro per sensoristica IoT e droni in agricoltura",
            "Puglia", "ITF47", "Startup_Innovative", "fondo_perduto", 50000.0
        ),
        (
            "PMI manifatturiera a Bologna richiede finanziamento a tasso agevolato di 500k per macchinari industria 4.0 e robotica meccanica",
            "Emilia-Romagna", "ITH55", "PMI", "tasso_agevolato", 500000.0
        ),
        (
            "Ente di ricerca e spin-off biotecnologie a Firenze cerca contributo a fondo perduto per r&d su farmaci oncologici con budget 1.5 milioni euro",
            "Toscana", "ITI14", "Enti_Ricerca", "fondo_perduto", 1500000.0
        ),
        (
            "Piccola impresa commercio a Milano cerca voucher digitalizzazione ed e-commerce da 15 mila euro",
            "Lombardia", "ITC4C", "PMI", "voucher", 15000.0
        ),
        (
            "PMI software e cloud a Torino cerca credito imposta e contributi per transizione digitale e cybersecurity da 120k euro",
            "Piemonte", "ITC11", "PMI", "credito_imposta", 120000.0
        ),
        (
            "PMI green a Palermo cerca fondo perduto per impianti fotovoltaici ed efficientamento energetico da 250k euro",
            "Sicilia", "ITG12", "PMI", "fondo_perduto", 250000.0
        ),
        (
            "Microimpresa turismo e ristorazione a Salerno cerca contributo a fondo perduto per riqualificazione alberghiera 100 mila euro",
            "Campania", "ITF35", "PMI", "fondo_perduto", 100000.0
        ),
        (
            "Startup cybersecurity a Roma cerca finanziamento a tasso agevolato da 80k per sicurezza cloud e consulenza",
            "Lazio", "ITI43", "Startup_Innovative", "tasso_agevolato", 80000.0
        ),
    ])
    def test_nlp_smart_intent_precision(self, query, exp_reg, exp_nuts, exp_ben, exp_fund, exp_budget):
        """Valuta l'estrazione semantica corretta su scenari complessi."""
        intent = SmartIntentExtractor.extract_intent(query)
        assert intent.inferred_region == exp_reg
        assert intent.inferred_nuts == exp_nuts
        assert exp_ben in intent.inferred_beneficiary_types
        assert exp_fund in intent.inferred_funding_types
        assert intent.inferred_budget == exp_budget

    def test_de_minimis_cap_ue_regulation(self):
        """Verifica applicazione rigorosa del tetto De Minimis UE 2023/2831 a €300.000,00."""
        now = datetime.now(timezone.utc)
        grant = CanonicalGrantModel(
            bando_id="DM-TEST",
            titolo="Bando De Minimis",
            ente_erogatore="MIMIT",
            tipo_agevolazione="Contributo a fondo perduto (de minimis)",
            budget_totale=1000000.0,
            percentuale_copertura=50.0,
            stato=BandoStato.APERTO,
            settori_beneficiari=["TUTTI"],
            regioni_target=["Tutte"],
            url_bando="https://mimit.gov.it",
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="MIMIT",
            hash_payload="h1"
        )
        # 1. Saturo
        p_sat = CompanyProfile(
            company_name="Saturo SRL",
            ateco_codes=["62.01.00"],
            de_minimis_accumulated_3yr=300000.0
        )
        score_sat = MatchScoringEngine.calculate_match(grant, p_sat)
        assert score_sat.is_eligible is False
        assert any("De Minimis" in f for f in score_sat.blocking_failures)

        # 2. Capiente
        p_cap = CompanyProfile(
            company_name="Capiente SRL",
            ateco_codes=["62.01.00"],
            de_minimis_accumulated_3yr=250000.0
        )
        score_cap = MatchScoringEngine.calculate_match(grant, p_cap)
        assert score_cap.is_eligible is True

    def test_dashboard_renderer_dom_elements(self):
        """Verifica integrità DOM e presenza di tutti i nodi UI interattivi."""
        service = bootstrap_demo_service()
        html = DashboardRenderer.render_html(service)
        assert "<!DOCTYPE html>" in html
        assert "LabNK — Monitoraggio & Intelligence Bandi" in html
        assert "presets-container" in html
        assert "intent-card" in html
        assert "filterGrantsNLP" in html
        assert "filterGrantsParametric" in html
