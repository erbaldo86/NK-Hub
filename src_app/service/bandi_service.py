"""LabNK Unified Bandi Service & Central Intelligence Orchestrator.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import collections
import re
import threading
from typing import List, Dict, Any, Optional, Tuple
from ..models.cgm import CanonicalGrantModel, BandoStato
from ..search.nlp_intent_extractor import SmartIntentExtractor, SearchIntent
from ..search.parametric_filter import ParametricFilter, ParametricFilterCriteria
from ..matching.profile_model import CompanyProfile, MatchScoreBreakdown
from ..matching.scoring_engine import MatchScoringEngine
from ..search.ateco_tree import AtecoTree
from ..document_processing.document_pipeline import DocumentPipeline
from ..document_processing.models import ProcessedDocumentReport
def strip_accents(text: str) -> str:
    """Rimuove accenti e diacritici per comparazioni resilienti."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def match_token(tok: str, text: str) -> bool:
    """Helper di matching morfologico flesso per italiano (singolari/plurali e accenti)."""
    t_clean = strip_accents(tok.lower().strip())
    text_clean = strip_accents(text.lower())
    if not t_clean:
        return True
    if t_clean in text_clean:
        return True
    if len(t_clean) >= 5:
        # Rimuove desinenza singolare/plurale o/a/e/i (es. fotovoltaico/fotovoltaici -> fotovoltaic)
        stem = t_clean[:-1]
        if stem in text_clean:
            return True
        if (t_clean.endswith("ico") or t_clean.endswith("ica") or t_clean.endswith("ici") or t_clean.endswith("iche")) and len(t_clean) >= 6:
            if t_clean[:-3] + "ic" in text_clean:
                return True
    words = re.findall(r"\b\w+\b", text_clean)
    for w in words:
        if len(w) >= 5 and len(t_clean) >= 5:
            if w[:-1] == t_clean[:-1]:
                return True
    return False


class LabNKBandiService:
    """
    Servizio unificato sovrano per la gestione dell'intelligence bandi:
    archiviazione CGM thread-safe con Double-Buffered Atomic Swap,
    ricerca conversazionale NLP, ricerca parametrica, scoring di matching
    aziendale ed elaborazione documentale con bounded LRU cache.
    """

    MAX_LRU_DOCUMENTS = 50

    def __init__(self):
        self._lock = threading.Lock()
        self._grants: Dict[str, CanonicalGrantModel] = {}
        self._documents: collections.OrderedDict[str, ProcessedDocumentReport] = collections.OrderedDict()

    def add_grant(self, grant: CanonicalGrantModel) -> None:
        """Registra o aggiorna un bando nel repository centrale (thread-safe)."""
        with self._lock:
            self._grants[grant.bando_id] = grant

    def add_grants(self, grants: List[CanonicalGrantModel]) -> None:
        """Registra un batch di bandi (thread-safe)."""
        with self._lock:
            for g in grants:
                self._grants[g.bando_id] = g

    def get_grant(self, grant_id: str) -> Optional[CanonicalGrantModel]:
        """Recupera la scheda bando per ID (thread-safe)."""
        with self._lock:
            return self._grants.get(grant_id)

    def list_all_grants(self) -> List[CanonicalGrantModel]:
        """Restituisce una copia snapshot dell'elenco completo dei bandi indicizzati (thread-safe)."""
        with self._lock:
            return list(self._grants.values())

    def swap_grants_atomic(self, new_grants: Dict[str, CanonicalGrantModel]) -> None:
        """
        Sostituisce atomicamente l'intero dizionario dei bandi con una nuova versione validata.
        Implementa il pattern Double-Buffered Swap (Copy-On-Write) per garantire letture
        concorrenti non bloccate e consistenza transazionale.
        """
        with self._lock:
            self._grants = dict(new_grants)

    def search_nlp(
        self,
        query: str,
        profile: Optional[CompanyProfile] = None,
        top_k: int = 20
    ) -> Tuple[SearchIntent, List[CanonicalGrantModel], List[MatchScoreBreakdown]]:
        """
        Esegue una ricerca conversazionale NLP:
        1. Estrae l'intento strutturato dal prompt.
        2. Calcola l'indice di compatibilità e verifica l'idoneità con MatchScoringEngine.
        3. Applica lo Strict Relevance Filter su token, n-grammi e affinità ATECO.
        4. Calcola lo score ibrido con boost e restituisce i top_k bandi ordinati.
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
            target_investment_amount=intent.inferred_budget
        )

        open_grants = [g for g in all_grants if g.stato == BandoStato.APERTO]

        stopwords = {
            "cerco", "fondi", "bando", "bandi", "per", "una", "uno", "con", "nel", "nella",
            "del", "della", "delle", "dei", "degli", "fare", "aprire", "alle", "agli", "allo",
            "settore", "settori", "ambito", "ambiti", "linea", "linee", "misura", "misure",
            "imprese", "impresa", "aziende", "azienda", "società", "societa", "ditta", "ditte",
            "pmi", "progetto", "progetti", "attività", "attivita", "servizio", "servizi",
            "supporto", "agevolazione", "agevolazioni", "contributo", "contributi",
            "fondo", "perduto", "aiuto", "aiuti", "avviso", "avvisi", "concessione", "erogazione"
        }

        raw_words = re.findall(r"\b[A-Za-z0-9\.\+\-]{3,}\b", query.lower())
        query_tokens = set([w for w in raw_words if w not in stopwords])
        if intent.extracted_keywords:
            query_tokens.update([kw.lower() for kw in intent.extracted_keywords if kw.lower() not in stopwords])

        # Estrazione n-grammi e locuzioni composte (bi-grammi e tri-grammi)
        words_list = [w for w in raw_words if w not in stopwords]
        phrases = []
        for i in range(len(words_list) - 1):
            phrases.append(f"{words_list[i]} {words_list[i+1]}")
        for i in range(len(words_list) - 2):
            phrases.append(f"{words_list[i]} {words_list[i+1]} {words_list[i+2]}")
        phrases = list(set(phrases))

        has_intent_specific_ateco = bool(intent.inferred_ateco_codes and "TUTTI" not in [c.upper() for c in intent.inferred_ateco_codes])

        scored_pairs: List[Tuple[CanonicalGrantModel, MatchScoreBreakdown, float, float]] = []

        for g in open_grants:
            breakdown = MatchScoringEngine.calculate_match(g, target_profile)
            if not breakdown.is_eligible:
                continue

            title_lower = g.titolo.lower()
            desc_lower = (g.descrizione or "").lower()
            ente_lower = g.ente_erogatore.lower()

            title_hits = sum(1 for tok in query_tokens if match_token(tok, title_lower))
            desc_hits = sum(1 for tok in query_tokens if match_token(tok, desc_lower))
            ente_hits = sum(1 for tok in query_tokens if match_token(tok, ente_lower))

            phrase_title_hits = sum(1 for p in phrases if p in title_lower)
            phrase_desc_hits = sum(1 for p in phrases if p in desc_lower)
            phrase_points = (phrase_title_hits * 40.0) + (phrase_desc_hits * 25.0)

            lexical_points = (title_hits * 25.0) + (desc_hits * 15.0) + (ente_hits * 5.0) + phrase_points

            bando_has_specific_ateco = bool(g.settori_beneficiari and "TUTTI" not in [s.upper() for s in g.settori_beneficiari])
            has_specific_ateco_match = False
            if has_intent_specific_ateco and bando_has_specific_ateco:
                has_specific_ateco_match = AtecoTree.is_code_compatible(g.settori_beneficiari, intent.inferred_ateco_codes)

            # Strict Relevance Filter:
            # Se query_tokens è presente, richiedi obbligatoriamente che lexical_points >= 15.0
            # (eliminando la coda di bandi non pertinenti ammessi solo per ATECO generico).
            # Rilevanza: ogni bando restituito deve avere un lexical_points > 0 correlato alla query.
            if query_tokens:
                if lexical_points < 15.0:
                    continue
            elif (phrases or has_intent_specific_ateco):
                if not (lexical_points > 0 or has_specific_ateco_match):
                    continue

            region_boost = 0.0
            if intent.inferred_region:
                if intent.inferred_region in g.regioni_target:
                    region_boost = 30.0 if "Tutte" not in g.regioni_target else 5.0
            elif intent.inferred_jurisdiction == "EU":
                if "europa" in ente_lower or "eic" in g.bando_id.lower() or "EU" in (g.fonte_nome or ""):
                    region_boost = 30.0

            sector_boost = 0.0
            if has_intent_specific_ateco and bando_has_specific_ateco:
                sector_boost = 25.0

            hybrid_score = breakdown.overall_match_score + lexical_points + region_boost + sector_boost

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
                scored_pairs = scored_pairs[:min(top_k, 10)]
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
        profile: CompanyProfile
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
        mime_type: Optional[str] = None
    ) -> ProcessedDocumentReport:
        """
        Elabora un allegato ufficiale (P7M/ZIP/PDF) tramite DocumentPipeline
        e lo associa al bando corrispondente all'interno della cache LRU (max 50 report).
        """
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
