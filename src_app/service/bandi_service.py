"""LabNK Unified Bandi Service & Central Intelligence Orchestrator.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import collections
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from ..catalog.repository import GrantsRepository
from ..core.config import DEFAULT_TOP_K, MAX_LRU_DOCUMENTS
from ..document_processing.models import ProcessedDocumentReport
from ..matching.profile_model import CompanyProfile, MatchScoreBreakdown
from ..matching.scoring_engine import MatchScoringEngine
from ..models.cgm import BandoStato, CanonicalGrantModel
from ..search.ateco_tree import AtecoTree
from ..search.linguistics import (
    BILINGUAL_LEMMAS,
    SHORT_RELEVANT_TOKENS,
    _get_text_tokens_and_stems,
    match_token,
    match_token_fast,
    strip_accents,
)
from ..search.nlp_intent_extractor import SearchIntent, SmartIntentExtractor
from ..search.parametric_filter import ParametricFilter, ParametricFilterCriteria

# Re-export linguistic symbols for 100% backwards compatibility
__all__ = [
    "BILINGUAL_LEMMAS",
    "SHORT_RELEVANT_TOKENS",
    "strip_accents",
    "_get_text_tokens_and_stems",
    "match_token_fast",
    "match_token",
    "LabNKBandiService",
]


class LabNKBandiService:
    """
    Servizio unificato sovrano per la gestione dell'intelligence bandi:
    archiviazione CGM thread-safe tramite GrantsRepository (Double-Buffered Atomic Swap),
    ricerca conversazionale NLP ad altissima efficienza (<20ms),
    ricerca parametrica, scoring di matching aziendale ed elaborazione
    documentale con bounded LRU cache.
    """

    MAX_LRU_DOCUMENTS: int = MAX_LRU_DOCUMENTS

    def __init__(self) -> None:
        self._repo = GrantsRepository()
        self._lock = threading.Lock()
        self._documents: collections.OrderedDict[str, ProcessedDocumentReport] = collections.OrderedDict()

    @property
    def _grants(self) -> Dict[str, CanonicalGrantModel]:
        """Accesso trasparente al dizionario dei bandi per retrocompatibilità."""
        return self._repo._grants

    @_grants.setter
    def _grants(self, value: Dict[str, CanonicalGrantModel]) -> None:
        self._repo._grants = value

    def add_grant(self, grant: CanonicalGrantModel) -> None:
        """Registra o aggiorna un bando nel repository centrale (thread-safe)."""
        self._repo.add_grant(grant)

    def add_grants(self, grants: List[CanonicalGrantModel]) -> None:
        """Registra un batch di bandi (thread-safe)."""
        self._repo.add_grants(grants)

    def get_grant(self, grant_id: str) -> Optional[CanonicalGrantModel]:
        """Recupera la scheda bando per ID (thread-safe)."""
        return self._repo.get_grant(grant_id)

    def list_all_grants(self) -> List[CanonicalGrantModel]:
        """Restituisce una copia snapshot dell'elenco completo dei bandi indicizzati (thread-safe)."""
        return self._repo.list_all_grants()

    def swap_grants_atomic(self, new_grants: Dict[str, CanonicalGrantModel]) -> None:
        """
        Sostituisce atomicamente l'intero dizionario dei bandi con una nuova versione validata.
        Implementa il pattern Double-Buffered Swap (Copy-On-Write) per garantire letture
        concorrenti non bloccate e consistenza transazionale.
        """
        self._repo.swap_grants_atomic(new_grants)

    def search_nlp(
        self,
        query: str,
        profile: Optional[CompanyProfile] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> Tuple[SearchIntent, List[CanonicalGrantModel], List[MatchScoreBreakdown]]:
        """
        Esegue una ricerca conversazionale NLP ad altissima velocità (<20ms):
        1. Estrae l'intento strutturato dal prompt.
        2. Calcola l'indice di compatibilità e verifica l'idoneità con MatchScoringEngine.
        3. Applica lo Strict Relevance Filter su token, n-grammi ed espansione bilingue tramite set e cache O(1).
        4. Calcola lo score ibrido con boost regionale ed EU Direct Boost e restituisce i top_k ordinati.
        """
        intent = SmartIntentExtractor.extract_intent(query)
        all_grants = self.list_all_grants()

        # Profilo sintetico dedotto dall'intento se non specificato
        allowed_sizes = {"Micro", "Piccola", "Media", "Grande", "Startup_Innovative", "Ente_Ricerca", "Professionista", "PMI"}
        inferred_size = "Piccola"
        inferred_legal_form = "SRL"
        if intent.inferred_beneficiary_types:
            for b in intent.inferred_beneficiary_types:
                if b in allowed_sizes:
                    inferred_size = b
                    if b == "Startup_Innovative":
                        inferred_legal_form = "Startup_Innovativa"
                    break

        target_profile = profile or CompanyProfile(
            company_name="Richiedente NLP",
            legal_form=inferred_legal_form,
            company_size=inferred_size,
            ateco_codes=intent.inferred_ateco_codes,
            operational_region=intent.inferred_region or "Tutte",
            target_investment_amount=intent.inferred_budget,
        )

        open_grants = [g for g in all_grants if g.stato == BandoStato.APERTO]

        stopwords = {
            "cerco", "fondi", "bando", "bandi", "per", "una", "uno", "con", "nel", "nella",
            "del", "della", "delle", "dei", "degli", "fare", "aprire", "alle", "agli", "allo",
            "settore", "settori", "ambito", "ambiti", "linea", "linee", "misura", "misure",
            "imprese", "impresa", "aziende", "azienda", "società", "societa", "ditta", "ditte",
            "pmi", "progetto", "progetti", "attività", "attivita", "servizio", "servizi",
            "supporto", "agevolazione", "agevolazioni", "contributo", "contributi",
            "fondo", "perduto", "aiuto", "aiuti", "avviso", "avvisi", "concessione", "erogazione",
        }

        query_lower = query.lower()
        all_found = re.findall(r"\b[A-Za-z0-9\.\+\-]{2,}\b", query_lower)
        raw_words = [w for w in all_found if len(w) >= 3 or w in SHORT_RELEVANT_TOKENS]
        query_tokens = set([w for w in raw_words if w not in stopwords])
        if intent.extracted_keywords:
            query_tokens.update([kw.lower() for kw in intent.extracted_keywords if kw.lower() not in stopwords])

        # Estrazione n-grammi e locuzioni composte (bi-grammi e tri-grammi)
        words_list = [w for w in raw_words if w not in stopwords]
        phrases: List[str] = []
        for i in range(len(words_list) - 1):
            phrases.append(f"{words_list[i]} {words_list[i+1]}")
        for i in range(len(words_list) - 2):
            phrases.append(f"{words_list[i]} {words_list[i+1]} {words_list[i+2]}")
        phrases = list(set(phrases))

        # Espansione bilingue tramite BILINGUAL_LEMMAS
        for lemma_key, synonyms in BILINGUAL_LEMMAS.items():
            variants = [lemma_key] + synonyms
            matched = False
            for v in variants:
                if " " in v:
                    if v in query_lower:
                        matched = True
                        break
                else:
                    if v in query_tokens or re.search(r"\b" + re.escape(v) + r"\b", query_lower):
                        matched = True
                        break
            if matched:
                for v in variants:
                    if " " in v:
                        phrases.append(v)
                    else:
                        query_tokens.add(v)

        has_intent_specific_ateco = bool(
            intent.inferred_ateco_codes and "TUTTI" not in [c.upper() for c in intent.inferred_ateco_codes]
        )

        # Pre-processa token puliti per query
        clean_tokens = [strip_accents(tok.lower().strip()) for tok in query_tokens]

        scored_pairs: List[Tuple[CanonicalGrantModel, MatchScoreBreakdown, float, float]] = []

        for g in open_grants:
            breakdown = MatchScoringEngine.calculate_match(g, target_profile)
            if not breakdown.is_eligible:
                continue

            # Recupero testi e indici memorizzati in cache per evitare scansioni e allocazioni multiple
            t_clean, t_words, t_stems = _get_text_tokens_and_stems(g.titolo)
            d_clean, d_words, d_stems = _get_text_tokens_and_stems(g.descrizione or "")
            e_clean, e_words, e_stems = _get_text_tokens_and_stems(g.ente_erogatore)

            title_hits = sum(1 for tok in clean_tokens if match_token_fast(tok, t_clean, t_words, t_stems))
            desc_hits = sum(1 for tok in clean_tokens if match_token_fast(tok, d_clean, d_words, d_stems))
            ente_hits = sum(1 for tok in clean_tokens if match_token_fast(tok, e_clean, e_words, e_stems))

            phrase_title_hits = sum(1 for p in phrases if p in t_clean)
            phrase_desc_hits = sum(1 for p in phrases if p in d_clean)
            phrase_points = (phrase_title_hits * 40.0) + (phrase_desc_hits * 25.0)

            lexical_points = (title_hits * 25.0) + (desc_hits * 15.0) + (ente_hits * 5.0) + phrase_points

            bando_has_specific_ateco = bool(
                g.settori_beneficiari and "TUTTI" not in [s.upper() for s in g.settori_beneficiari]
            )
            has_specific_ateco_match = False
            if has_intent_specific_ateco and bando_has_specific_ateco:
                has_specific_ateco_match = AtecoTree.is_code_compatible(
                    g.settori_beneficiari, intent.inferred_ateco_codes
                )

            # Strict Relevance Filter:
            # Se query_tokens è presente, richiedi obbligatoriamente che lexical_points >= 15.0
            if query_tokens:
                if lexical_points < 15.0:
                    continue
            elif phrases or has_intent_specific_ateco:
                if not (lexical_points > 0 or has_specific_ateco_match):
                    continue

            region_boost = 0.0
            if intent.inferred_region:
                if intent.inferred_region in g.regioni_target:
                    region_boost = 30.0 if "Tutte" not in g.regioni_target else 5.0

            # EU Direct Boost (+30 pt)
            eu_boost = 0.0
            if intent.has_eu_intent:
                if (
                    g.fonte_nome in ("SEDIA EU", "TED v3")
                    or "europa" in e_clean
                    or "commissione europea" in e_clean
                    or "horizon" in t_clean
                    or "eic" in t_clean
                    or "eic" in d_clean
                ):
                    eu_boost = 30.0
            elif intent.inferred_jurisdiction == "EU":
                if "europa" in e_clean or "EU" in (g.fonte_nome or ""):
                    eu_boost = 30.0

            sector_boost = 0.0
            if has_intent_specific_ateco and bando_has_specific_ateco:
                sector_boost = 25.0

            hybrid_score = breakdown.overall_match_score + lexical_points + region_boost + sector_boost + eu_boost

            relevance_boost = min(30.0, lexical_points)
            final_display_score = round(min(100.0, (breakdown.overall_match_score * 0.7) + relevance_boost), 1)

            # Aggiorna overall_match_score nel breakdown
            updated_breakdown = breakdown.model_copy(update={"overall_match_score": final_display_score})
            scored_pairs.append((g, updated_breakdown, hybrid_score, lexical_points))

        scored_pairs.sort(key=lambda p: (p[2], p[3]), reverse=True)
        if scored_pairs:
            is_generic = not bool(query_tokens or phrases)
            if not is_generic:
                max_score = max(p[2] for p in scored_pairs)
                cutoff = max_score * 0.55
                scored_pairs = [p for p in scored_pairs if p[2] >= cutoff]
                scored_pairs = scored_pairs[: min(top_k, 10)]
            else:
                scored_pairs = scored_pairs[:top_k]

        sorted_grants = [p[0] for p in scored_pairs]
        sorted_scores = [p[1] for p in scored_pairs]

        return intent, sorted_grants, sorted_scores

    def search_parametric(self, criteria: ParametricFilterCriteria) -> List[CanonicalGrantModel]:
        """Esegue una ricerca parametrica avanzata per consulenti."""
        return ParametricFilter.filter_grants(self.list_all_grants(), criteria)

    def calculate_match_for_grant(
        self,
        grant_id: str,
        profile: CompanyProfile,
    ) -> Optional[MatchScoreBreakdown]:
        """Calcola la compatibilità di un profilo con uno specifico bando."""
        grant = self.get_grant(grant_id)
        if not grant:
            return None
        return MatchScoringEngine.calculate_match(grant, profile)

    def process_and_attach_document(
        self,
        grant_id: str,
        doc_bytes: bytes,
        filename: str,
        mime_type: Optional[str] = None,
    ) -> ProcessedDocumentReport:
        """
        Elabora un allegato ufficiale (P7M/ZIP/PDF) tramite DocumentPipeline
        e lo associa al bando corrispondente all'interno della cache LRU (max 50 report).
        """
        from ..document_processing.document_pipeline import DocumentPipeline
        report = DocumentPipeline.process_document(doc_bytes, filename, mime_type)
        with self._lock:
            if grant_id in self._documents:
                self._documents.move_to_end(grant_id)
            self._documents[grant_id] = report
            if len(self._documents) > self.MAX_LRU_DOCUMENTS:
                self._documents.popitem(last=False)
        return report

    def get_document_report(self, grant_id: str) -> Optional[ProcessedDocumentReport]:
        """Recupera il report documentale associato a un bando aggiornando la priorità LRU."""
        with self._lock:
            if grant_id in self._documents:
                self._documents.move_to_end(grant_id)
                return self._documents[grant_id]
            return None
