"""LabNK Bandi Ingestion Orchestrator.
Nexus Keystone v1.1.0-Universal | Live Institutional Sources Harvester.
Protocollo CRV 4.0 | Controlled Multi-Page Pagination & Enriched Telemetry.
"""

from __future__ import annotations

import json
import time
import asyncio
import logging
import uuid
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime, timezone

from src_app.models.cgm import CanonicalGrantModel, BandoStato, FonteTipo
if TYPE_CHECKING:
    from src_app.service.bandi_service import LabNKBandiService
from src_app.search.ateco_tree import AtecoTree
from src_app.connectors.rest_api import RestApiConnector
from src_app.connectors.rss_feed import RssFeedConnector
from src_app.connectors.html_scraper import HtmlScraperConnector
from src_app.connectors.incentivi_gov import IncentiviGovConnector
from src_app.connectors.unioncamere_federator import UnioncamereFederatorConnector
from src_app.connectors.base import AsyncRateLimiter, AntiBanPolicy
from src_app.core.catalog_loader import load_seed_grants

logger = logging.getLogger("IngestionOrchestrator")


def _is_valid_sha256(val: Optional[str]) -> bool:
    """Verifica se la stringa è un hash SHA-256 esadecimale valido a 64 caratteri."""
    return bool(
        val
        and isinstance(val, str)
        and len(val) == 64
        and all(c in "0123456789abcdefABCDEF" for c in val)
    )


def _find_snapshot_path() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        cand = parent / "data" / "snapshots" / "catalog_snapshot.json"
        if cand.exists():
            return cand
    for parent in p.parents:
        if (parent / "src_app").exists() or (parent / ".staging").exists():
            return parent / "data" / "snapshots" / "catalog_snapshot.json"
    return p.parent.parent.parent / "data" / "snapshots" / "catalog_snapshot.json"


class IngestionOrchestrator:
    """
    Orchestratore centrale di Ingestion che carica il registro SSOT delle fonti (sources_registry.json),
    scansiona i portali istituzionali reali (Nazionali, 20 Regioni, Fonti Camerali, CSR/PSR, UE),
    supporta la paginazione multi-pagina (max_pages controllata), normalizza i record
    nel Canonical Grant Model (CGM) e popola il repository con Double-Buffered Atomic Swap,
    concorrenza limitata per-host, circuit breaker, telemetria granulare e persistenza offline-first.
    """

    SOURCES_REGISTRY_PATH = Path(__file__).resolve().parent / "sources_registry.json"
    SNAPSHOT_PATH = _find_snapshot_path()

    _is_harvesting: bool = False
    _current_job_id: Optional[str] = None
    _last_telemetry: Dict[str, Any] = {}
    _harvest_lock: asyncio.Lock = asyncio.Lock()

    _host_semaphores: Dict[str, asyncio.Semaphore] = {}
    _circuit_failures: Dict[str, int] = {}
    _circuit_open_until: Dict[str, float] = {}
    _source_telemetry: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def is_harvesting(cls) -> bool:
        """Indica se un harvesting è attualmente in esecuzione."""
        return cls._is_harvesting

    @classmethod
    def get_current_job_id(cls) -> Optional[str]:
        """Restituisce il job_id dell'harvesting in corso."""
        return cls._current_job_id

    @classmethod
    def get_last_telemetry(cls) -> Dict[str, Any]:
        """Restituisce l'ultima telemetria registrata."""
        return cls._last_telemetry

    @classmethod
    def is_circuit_open(cls, source_id: str) -> bool:
        """Verifica se il Circuit Breaker per una fonte è attualmente aperto (in cooldown)."""
        return time.time() < cls._circuit_open_until.get(source_id, 0.0)

    @classmethod
    def record_failure(cls, source_id: str) -> None:
        """Registra un fallimento per il Circuit Breaker; apre il circuito dopo 3 fallimenti consecutivi."""
        cls._circuit_failures[source_id] = cls._circuit_failures.get(source_id, 0) + 1
        if cls._circuit_failures[source_id] >= 3:
            cls._circuit_open_until[source_id] = time.time() + 60.0
            logger.warning("CIRCUIT_BREAKER_TRIPPED: Fonte %s in cooldown per 60s", source_id)

    @classmethod
    def record_success(cls, source_id: str) -> None:
        """Resetta i fallimenti del Circuit Breaker al successo."""
        cls._circuit_failures[source_id] = 0

    @classmethod
    def _get_host_semaphore(cls, host: str) -> asyncio.Semaphore:
        """Restituisce il semaforo con cap massimo di 2 richieste contemporanee per dominio host."""
        if host not in cls._host_semaphores:
            cls._host_semaphores[host] = asyncio.Semaphore(2)
        return cls._host_semaphores[host]

    @classmethod
    def save_snapshot(cls, grants: Dict[str, CanonicalGrantModel]) -> None:
        """Persiste lo snapshot reale dei bandi autentici su data/snapshots/catalog_snapshot.json in modo atomico."""
        try:
            cls.SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            serialized = [g.model_dump(mode="json") for g in grants.values()]
            temp_path = cls.SNAPSHOT_PATH.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False, indent=2)
            temp_path.replace(cls.SNAPSHOT_PATH)
            logger.info("Snapshot persistito con successo in %s (%d bandi)", cls.SNAPSHOT_PATH, len(grants))
        except Exception as exc:
            logger.error("Errore durante la scrittura dello snapshot su %s: %s", cls.SNAPSHOT_PATH, exc)

    @classmethod
    def load_snapshot(cls) -> Dict[str, CanonicalGrantModel]:
        """Carica lo snapshot offline autentico precedentemente persistito (Offline-First)."""
        if not cls.SNAPSHOT_PATH.exists():
            return {}
        try:
            with open(cls.SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                loaded = {}
                for item in data:
                    try:
                        cgm = CanonicalGrantModel.model_validate(item, strict=False)
                        loaded[cgm.bando_id] = cgm
                    except Exception as e:
                        logger.warning("Salto record snapshot invalido: %s", e)
                logger.info("Caricati %d bandi autentici dallo snapshot %s", len(loaded), cls.SNAPSHOT_PATH)
                return loaded
        except Exception as exc:
            logger.warning("Impossibile caricare snapshot da %s: %s", cls.SNAPSHOT_PATH, exc)
            return {}

    @classmethod
    def load_sources_registry(cls) -> List[Dict[str, Any]]:
        """Carica l'elenco dei portali ufficiali registrati in sources_registry.json."""
        if not cls.SOURCES_REGISTRY_PATH.exists():
            logger.warning(f"File {cls.SOURCES_REGISTRY_PATH} non trovato.")
            return []
        try:
            with open(cls.SOURCES_REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("sources", [])
        except Exception as e:
            logger.error(f"Errore durante il parsing di sources_registry.json: {e}")
            return []

    @classmethod
    async def harvest_single_source(
        cls,
        source: Dict[str, Any],
        global_semaphore: asyncio.Semaphore
    ) -> Tuple[str, List[CanonicalGrantModel], str]:
        """
        Esegue l'harvesting asincrono di una singola fonte con supporto paginazione,
        Circuit Breaker, limite per-host e telemetria arricchita.
        """
        source_id = source.get("source_id", "UNKNOWN")
        source_name = source.get("name", source_id)
        url = source.get("official_url")
        connector_type = source.get("connector_type", "HTML_SCRAPER")
        region = source.get("region", "Tutte")
        jurisdiction = source.get("jurisdiction", "NAT")

        if not url:
            cls._source_telemetry[source_id] = {
                "pages_scanned": 0,
                "duration_ms": 0.0,
                "grants_found": 0,
                "yield_status": "SKIPPED",
            }
            return source_id, [], "SKIPPED_NO_URL"

        # Controllo Circuit Breaker
        if cls.is_circuit_open(source_id):
            logger.warning("Fonte %s esclusa temporaneamente per Circuit Breaker aperto", source_id)
            cls._source_telemetry[source_id] = {
                "pages_scanned": 0,
                "duration_ms": 0.0,
                "grants_found": 0,
                "yield_status": "CIRCUIT_BREAKER_OPEN",
            }
            return source_id, [], "CIRCUIT_BREAKER_OPEN"

        # Concurrency limit per-host (max 2 richieste contemporanee per host)
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.netloc.lower() or "unknown_host"
        host_semaphore = cls._get_host_semaphore(host)

        async with global_semaphore:
            async with host_semaphore:
                t0 = time.perf_counter()
                try:
                    rate_limiter = AsyncRateLimiter(requests_per_second=5.0)
                    anti_ban = AntiBanPolicy(rotate_user_agent=True, base_delay=0.1)

                    if connector_type in ("INCENTIVI_GOV_RNA", "INCENTIVI_GOV") or source_id in ("INCENTIVI_GOV_NATIONAL", "RNA_AIUTI_STATO"):
                        connector = IncentiviGovConnector(
                            name=source_name,
                            rate_limiter=rate_limiter,
                            anti_ban=anti_ban,
                        )
                    elif connector_type == "UNIONCAMERE_FEDERATOR" or source_id == "UNIONCAMERE_PID_NATIONAL" or "CCIAA_" in source_id:
                        connector = UnioncamereFederatorConnector(
                            name=source_name,
                            rate_limiter=rate_limiter,
                            anti_ban=anti_ban,
                        )
                    elif connector_type == "REST_API":
                        connector = RestApiConnector(
                            name=source_name,
                            rate_limiter=rate_limiter,
                            anti_ban=anti_ban,
                            max_pages=2,
                        )
                    elif connector_type == "RSS_FEED":
                        connector = RssFeedConnector(
                            name=source_name,
                            rate_limiter=rate_limiter,
                            anti_ban=anti_ban,
                        )
                    else:
                        connector = HtmlScraperConnector(
                            name=source_name,
                            rate_limiter=rate_limiter,
                            anti_ban=anti_ban,
                            max_pages=3,
                        )

                    # Timeout differenziato a 15.0s per fonti REST UE, timeout 10.0s per le altre con paginazione
                    is_eu_rest = connector_type == "REST_API" and (jurisdiction == "EU" or "europa.eu" in (url or "").lower())
                    timeout_sec = 15.0 if is_eu_rest else 10.0

                    # Invisible Self-Healing Loop for HTTP 403 / 429 with backoff 1s -> 2s -> 4s & UA rotation
                    backoff_delays = [1.0, 2.0, 4.0]
                    max_attempts = 3
                    grants = []
                    last_exc = None

                    for attempt in range(max_attempts):
                        try:
                            grants = await asyncio.wait_for(connector.fetch_and_parse(url), timeout=timeout_sec)
                            last_exc = None
                            break
                        except Exception as exc:
                            last_exc = exc
                            status_code = getattr(getattr(exc, "response", None), "status_code", None)
                            err_msg = str(exc)
                            is_ban_or_rate = (
                                status_code in (403, 429)
                                or "403" in err_msg
                                or "429" in err_msg
                                or "rate limit" in err_msg.lower()
                                or "too many requests" in err_msg.lower()
                                or "forbidden" in err_msg.lower()
                            )
                            if is_ban_or_rate and attempt < max_attempts - 1:
                                delay = backoff_delays[attempt]
                                logger.warning(
                                    "Invisible Self-Healing Loop: HTTP 403/429 rilevato per %s (tentativo %d/%d). "
                                    "Rotazione User-Agent e backoff di %.1fs...",
                                    source_id, attempt + 1, max_attempts, delay
                                )
                                anti_ban.base_delay += delay
                                await asyncio.sleep(delay)
                                continue
                            raise exc

                    fetch_duration_ms = round((time.perf_counter() - t0) * 1000, 2)
                    pages_scanned = getattr(connector, "pages_scanned", 1) or 1

                    # Post-process & enrich parsed records
                    enriched_grants = []
                    for idx, g in enumerate(grants):
                        # Imposta regioni_target = ["Tutte"] se EU; [region] se REG; altrimenti ["Tutte"]
                        if jurisdiction == "EU":
                            g.regioni_target = ["Tutte"]
                        elif jurisdiction == "REG" and region and region.strip() and region.strip() != "Tutte":
                            g.regioni_target = [region.strip()]
                        else:
                            g.regioni_target = ["Tutte"]

                        # Se settori_beneficiari e' assente o ["TUTTI"], applica AtecoTree.infer_ateco_from_text
                        if not g.settori_beneficiari or g.settori_beneficiari == ["TUTTI"]:
                            inferred_ateco = AtecoTree.infer_ateco_from_text(f"{g.titolo} {g.descrizione or ''}")
                            g.settori_beneficiari = inferred_ateco if inferred_ateco else ["TUTTI"]

                        # Assicurati che ente_erogatore sia valorizzato con il nome della fonte se vuoto
                        if not g.ente_erogatore or not g.ente_erogatore.strip():
                            g.ente_erogatore = source_name

                        # Assicurati che bando_id e hash_payload siano hash SHA-256 univoci calcolati correttamente
                        if not _is_valid_sha256(g.bando_id):
                            g.bando_id = CanonicalGrantModel.calculate_payload_hash(
                                f"{source_id}:{g.url_bando}:{g.titolo}:{idx}"
                            )

                        if not _is_valid_sha256(g.hash_payload):
                            raw_sig = f"{g.titolo}|{g.url_bando}|{g.ente_erogatore}|{g.descrizione or ''}"
                            g.hash_payload = CanonicalGrantModel.calculate_payload_hash(raw_sig)

                        enriched_grants.append(g)

                    cls.record_success(source_id)
                    yield_status = "HIGH" if len(enriched_grants) >= 10 else ("MEDIUM" if len(enriched_grants) > 0 else "EMPTY")
                    cls._source_telemetry[source_id] = {
                        "pages_scanned": pages_scanned,
                        "duration_ms": fetch_duration_ms,
                        "grants_found": len(enriched_grants),
                        "yield_status": yield_status,
                    }

                    status = f"HEALTHY_LIVE_HARVESTED ({len(enriched_grants)} bandi, {pages_scanned} pag, {fetch_duration_ms:.0f}ms)"
                    return source_id, enriched_grants, status

                except Exception as exc:
                    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                    cls.record_failure(source_id)
                    cls._source_telemetry[source_id] = {
                        "pages_scanned": 0,
                        "duration_ms": elapsed_ms,
                        "grants_found": 0,
                        "yield_status": "OFFLINE",
                    }
                    logger.warning(f"Errore durante harvest live di {source_id} ({url}): {exc}")
                    return source_id, [], f"OFFLINE_FALLBACK ({type(exc).__name__})"

    @classmethod
    async def harvest_all(
        cls,
        service: LabNKBandiService,
        sources_subset: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Esegue la scansione completa di tutte le fonti istituzionali registrate con:
        - Re-entrancy protection
        - Double-Buffered Atomic Swap
        - Offline-First snapshot fallback
        - Deduplicazione globale rigorosa su grant.hash_payload
        - Supporto paginazione e telemetria granulare per fonte
        - Concorrenza limitata globale e per-host
        """
        async with cls._harvest_lock:
            if cls._is_harvesting:
                logger.info("Harvesting già in corso (Job: %s). Invocazione ignorata.", cls._current_job_id)
                return cls._last_telemetry or {
                    "status": "in_progress",
                    "job_id": cls._current_job_id,
                    "message": "Harvesting already in progress",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            cls._is_harvesting = True
            cls._current_job_id = f"job-{uuid.uuid4().hex[:8]}"

        try:
            start_time = time.perf_counter()
            sources = sources_subset if sources_subset is not None else cls.load_sources_registry()
            sources_count = len(sources)

            # Staging dictionary per il Double-Buffered Swap con deduplicazione su hash_payload
            staging_grants: Dict[str, CanonicalGrantModel] = {}
            seen_hashes: set[str] = set()

            # 1. Carica il catalogo base curato (38 bandi di riferimento con hash validi)
            for grant in load_seed_grants():
                if not _is_valid_sha256(grant.hash_payload):
                    grant.hash_payload = CanonicalGrantModel.calculate_payload_hash(f"{grant.bando_id}:{grant.titolo}")
                if grant.hash_payload not in seen_hashes:
                    seen_hashes.add(grant.hash_payload)
                    staging_grants[grant.bando_id] = grant

            # 2. Supporto Offline-First: carica snapshot autentico salvato precedentemente (ZERO-MOCK)
            cached_snapshot = cls.load_snapshot()
            for g_id, g in cached_snapshot.items():
                if not _is_valid_sha256(g.hash_payload):
                    g.hash_payload = CanonicalGrantModel.calculate_payload_hash(f"{g.bando_id}:{g.titolo}")
                if g.hash_payload not in seen_hashes:
                    seen_hashes.add(g.hash_payload)
                    staging_grants[g.bando_id] = g

            # 3. Concurrency limitata globale a 8 richieste parallele (e 2 per-host)
            active_sources = [s for s in sources if s.get("active", True)]
            global_semaphore = asyncio.Semaphore(8)
            tasks = [
                cls.harvest_single_source(s, global_semaphore)
                for s in active_sources
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_live_harvested = 0
            sources_details = []

            for idx, res in enumerate(results):
                source_meta = active_sources[idx] if idx < len(active_sources) else {}
                if isinstance(res, tuple):
                    s_id, grants, status_desc = res
                    for g in grants:
                        if not _is_valid_sha256(g.hash_payload):
                            g.hash_payload = CanonicalGrantModel.calculate_payload_hash(f"{g.bando_id}:{g.titolo}")
                        if g.hash_payload not in seen_hashes:
                            seen_hashes.add(g.hash_payload)
                            staging_grants[g.bando_id] = g
                            total_live_harvested += 1

                    tel = cls._source_telemetry.get(s_id, {})
                    sources_details.append({
                        "source_id": s_id,
                        "name": source_meta.get("name", s_id),
                        "jurisdiction": source_meta.get("jurisdiction", "NAT"),
                        "region": source_meta.get("region", "Tutte"),
                        "connector": source_meta.get("connector_type", "HTML_SCRAPER"),
                        "grants_found": len(grants),
                        "pages_scanned": tel.get("pages_scanned", 1),
                        "duration_ms": tel.get("duration_ms", 0.0),
                        "yield_status": tel.get("yield_status", "UNKNOWN"),
                        "status": status_desc,
                    })
                else:
                    sources_details.append({
                        "source_id": source_meta.get("source_id", f"SOURCE_{idx}"),
                        "name": source_meta.get("name", "Unknown"),
                        "jurisdiction": source_meta.get("jurisdiction", "NAT"),
                        "region": source_meta.get("region", "Tutte"),
                        "connector": source_meta.get("connector_type", "UNKNOWN"),
                        "grants_found": 0,
                        "pages_scanned": 0,
                        "duration_ms": 0.0,
                        "yield_status": "ERROR",
                        "status": f"ERROR ({str(res)})",
                    })

            # 4. Double-Buffered Atomic Swap nel servizio centrale in-memory
            service.swap_grants_atomic(staging_grants)

            # 5. Persistenza dello snapshot reale su disco in modo asincrono
            await asyncio.to_thread(cls.save_snapshot, staging_grants)

            total_grants_in_service = len(service.list_all_grants())
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            total_pages_scanned = sum(s.get("pages_scanned", 1) for s in sources_details)

            report = {
                "status": "completed",
                "job_id": cls._current_job_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sources_scanned": sources_count,
                "sources_active": len([s for s in sources_details if s.get("grants_found", 0) > 0]),
                "total_pages_scanned": total_pages_scanned,
                "grants_harvested_live": total_live_harvested,
                "grants_total_in_service": total_grants_in_service,
                "duration_ms": elapsed_ms,
                "sources_details": sources_details,
            }
            cls._last_telemetry = report
            logger.info(
                "Live Harvesting completato: %d fonti scansionate (%d pagine), %d bandi live scaricati, %d bandi totali in %.2f ms",
                sources_count, total_pages_scanned, total_live_harvested, total_grants_in_service, elapsed_ms
            )
            return report

        finally:
            cls._is_harvesting = False
            cls._current_job_id = None
