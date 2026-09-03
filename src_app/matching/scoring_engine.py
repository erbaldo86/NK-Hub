"""Deterministic Match Scoring & Compatibility Engine.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

from typing import List, Dict, Any, Tuple
from ..models.cgm import CanonicalGrantModel, BandoStato
from .profile_model import CompanyProfile, MatchScoreBreakdown
from ..search.ateco_tree import AtecoTree


class MatchScoringEngine:
    """
    Motore deterministico di calcolo compatibilità (0 - 100%) tra profilo aziendale
    e bando di finanziamento con spiegazione trasparente di criteri, blocchi e premialità.
    """

    DE_MINIMIS_MAX_CAP_3YR = 300_000.0  # Regolamento UE 2023/2831

    @classmethod
    def calculate_match(
        cls,
        grant: CanonicalGrantModel,
        profile: CompanyProfile
    ) -> MatchScoreBreakdown:
        """Calcola l'indice di affinità e verifica l'eleggibilità del profilo rispetto al bando."""
        blocking_failures: List[str] = []
        criteria_scores: Dict[str, float] = {}
        bonus_points: List[str] = []
        recommended_actions: List[str] = []

        # 1. Condizioni Bloccanti
        if grant.stato == BandoStato.CHIUSO:
            blocking_failures.append("Il bando risulta formalmente CHIUSO per scadenza termini.")

        bando_sectors = grant.settori_beneficiari or ["TUTTI"]
        is_profile_all_ateco = not profile.ateco_codes or any(c.upper() in ("TUTTI", "*", "ALL") for c in profile.ateco_codes)
        ateco_compat = is_profile_all_ateco or AtecoTree.is_code_compatible(bando_sectors, profile.ateco_codes)
        if not ateco_compat:
            blocking_failures.append(
                f"Nessun codice ATECO aziendale {profile.ateco_codes} rientra nei settori ammessi {grant.settori_beneficiari}."
            )

        bando_regioni = [r.lower() for r in (grant.regioni_target or ["Tutte"])]
        is_bando_all = any(r in ("tutte", "italia", "nazionale", "all") for r in bando_regioni)
        is_profile_all = profile.operational_region.lower() in ("tutte", "italia", "nazionale", "all")

        # Se l'utente non ha specificato una regione (operational_region == "Tutte"),
        # TUTTI i bandi (nazionali o regionali) sono considerati compatibili a livello esplorativo!
        territory_compat = is_bando_all or is_profile_all or (profile.operational_region.lower() in bando_regioni)
        if not territory_compat:
            blocking_failures.append(
                f"La sede aziendale ({profile.operational_region}) non rientra nelle regioni ammissibili ({grant.regioni_target})."
            )

        is_de_minimis = grant.tipo_agevolazione and "de minimis" in grant.tipo_agevolazione.lower()
        if is_de_minimis and profile.de_minimis_accumulated_3yr >= cls.DE_MINIMIS_MAX_CAP_3YR:
            blocking_failures.append(
                f"Plafond De Minimis triennale (€{profile.de_minimis_accumulated_3yr:,.2f}) saturo rispetto al limite di legge (€300.000,00)."
            )

        # 2. Punteggi Parziali
        if not ateco_compat:
            score_ateco = 0.0
        elif "TUTTI" in [c.upper() for c in bando_sectors] or is_profile_all_ateco:
            score_ateco = 22.0
        else:
            score_ateco = 30.0
        criteria_scores["ateco_affinity"] = score_ateco

        if not territory_compat:
            score_territory = 0.0
        elif is_profile_all:
            # Se la ricerca è esplorativa/nazionale, assegna punteggio neutro bilanciato
            score_territory = 20.0 if is_bando_all else 18.0
        elif not is_bando_all:
            score_territory = 25.0
        else:
            score_territory = 20.0
        criteria_scores["territory_fit"] = score_territory

        b_types = [b.lower() for b in (grant.tipologia_beneficiari or ["PMI"])]
        if profile.company_size.lower() in b_types or "pmi" in b_types:
            score_beneficiary = 20.0
        elif profile.legal_form == "Startup_Innovativa" and "startup_innovative" in b_types:
            score_beneficiary = 20.0
        else:
            score_beneficiary = 10.0
        criteria_scores["beneficiary_size_fit"] = score_beneficiary

        score_intensity = 15.0
        if grant.percentuale_copertura:
            score_intensity = min(25.0, (grant.percentuale_copertura / 100.0) * 25.0)
        criteria_scores["aid_intensity"] = round(score_intensity, 1)

        # 3. Premialità & Bonus
        total_score = sum(criteria_scores.values())

        if profile.youth_ownership:
            total_score += 5.0
            bonus_points.append("Premialità Imprenditoria Giovanile (+5%)")
        if profile.female_ownership:
            total_score += 5.0
            bonus_points.append("Premialità Imprenditoria Femminile (+5%)")
        if profile.legal_form == "Startup_Innovativa":
            total_score += 5.0
            bonus_points.append("Bonus Status Startup Innovativa (+5%)")

        final_score = min(100.0, max(0.0, total_score)) if not blocking_failures else min(35.0, total_score * 0.3)

        # 4. Azioni Consigliate
        if not blocking_failures:
            recommended_actions.append("Predisporre il business plan e il quadro economico degli investimenti.")
            if is_de_minimis:
                recommended_actions.append("Verificare la capienza residua sul Registro Nazionale Aiuti (RNA).")
        else:
            recommended_actions.append("Risolvere i vincoli bloccanti o valutare misure alternative a livello nazionale.")

        return MatchScoreBreakdown(
            grant_id=grant.bando_id,
            grant_title=grant.titolo,
            overall_match_score=round(final_score, 1),
            is_eligible=len(blocking_failures) == 0,
            blocking_failures=blocking_failures,
            criteria_scores=criteria_scores,
            bonus_points=bonus_points,
            recommended_actions=recommended_actions
        )
