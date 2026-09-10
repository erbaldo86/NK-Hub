"""Nightly & Midday Ingestion Scheduler with Liveness Telemetry.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
Protocollo CRV 4.0 | Controlled Autonomous Ingestion Scheduling.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src_app.ingestion.orchestrator import IngestionOrchestrator

if TYPE_CHECKING:
    from src_app.service.bandi_service import LabNKBandiService

logger = logging.getLogger("NightlyIngestionScheduler")

# Definizione delle fonti Tier 1 e Tier 2 prioritarie per la scansione leggera
TIER_1_2_KEYWORDS = {
    "INCENTIVI_GOV_NATIONAL",
    "RNA_AIUTI_STATO",
    "INVITALIA_NATIONAL",
    "MIMIT_NATIONAL",
    "MASE_NATIONAL",
    "MASAF_NATIONAL",
    "MUR_NATIONAL",
    "INAIL_NATIONAL",
    "EU_SEDIA",
    "EU_TED_V3",
    "UNIONCAMERE_PID_NATIONAL",
}


class NightlyIngestionScheduler:
    """
    Scheduler asincrono in background per l'ecosistema LabNK Bandi Intelligence.
    - Deep Scan alle ore 00:01: scansione completa di tutte le 125 fonti istituzionali con paginazione.
    - Light Scan alle ore 14:00: scansione mirata e veloce sulle fonti prioritarie Tier 1 e Tier 2.
    - Telemetria di Liveness continua e heartbeat monitorabile via API.
    """

    def __init__(self, service: Optional["LabNKBandiService"] = None):
        self.service = service
        self._is_running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._total_deep_runs: int = 0
        self._total_light_runs: int = 0
        self._last_run_type: Optional[str] = None
        self._last_run_timestamp: Optional[datetime] = None
        self._last_run_duration_ms: float = 0.0
        self._last_error: Optional[str] = None
        self._next_scheduled_run: Optional[datetime] = None
        self._next_run_type: Optional[str] = None

    @property
    def is_running(self) -> bool:
        """Indica se lo scheduler è in esecuzione."""
        return self._is_running

    def get_status(self) -> Dict[str, Any]:
        """Restituisce lo stato di liveness e la telemetria delle esecuzioni dello scheduler."""
        now = datetime.now(timezone.utc)
        health = "HEALTHY"
        if not self._is_running:
            health = "STOPPED"
        elif self._last_error:
            health = "DEGRADED"

        return {
            "status": health,
            "is_running": self._is_running,
            "total_deep_runs": self._total_deep_runs,
            "total_light_runs": self._total_light_runs,
            "last_run_type": self._last_run_type,
            "last_run_timestamp": self._last_run_timestamp.isoformat() if self._last_run_timestamp else None,
            "last_run_duration_ms": self._last_run_duration_ms,
            "last_error": self._last_error,
            "next_scheduled_run": self._next_scheduled_run.isoformat() if self._next_scheduled_run else None,
            "next_run_type": self._next_run_type,
            "current_time_utc": now.isoformat(),
        }

    @staticmethod
    def get_tier1_tier2_sources() -> List[Dict[str, Any]]:
        """Filtra e restituisce le fonti Tier 1 e Tier 2 (Nazionali, UE e Fondamentali)."""
        all_sources = IngestionOrchestrator.load_sources_registry()
        filtered: List[Dict[str, Any]] = []
        for s in all_sources:
            s_id = s.get("source_id", "")
            jurisdiction = s.get("jurisdiction", "")
            if s_id in TIER_1_2_KEYWORDS or jurisdiction in ("EU", "NAT"):
                filtered.append(s)
        return filtered or all_sources[:25]

    async def trigger_deep_scan(self, service: Optional["LabNKBandiService"] = None) -> Dict[str, Any]:
        """Esegue immediatamente una Deep Scan completa di tutte le fonti registrate."""
        svc = service or self.service
        if not svc:
            raise ValueError("LabNKBandiService instance required for ingestion scan")

        t0 = asyncio.get_event_loop().time()
        logger.info("NightlyScheduler: Inizio Deep Scan (00:01 mode - tutte le 125 fonti)...")
        try:
            report = await IngestionOrchestrator.harvest_all(svc)
            elapsed_ms = round((asyncio.get_event_loop().time() - t0) * 1000, 2)
            self._total_deep_runs += 1
            self._last_run_type = "DEEP_SCAN"
            self._last_run_timestamp = datetime.now(timezone.utc)
            self._last_run_duration_ms = elapsed_ms
            self._last_error = None
            logger.info("NightlyScheduler: Deep Scan completata in %.2f ms", elapsed_ms)
            return report
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("NightlyScheduler: Errore durante Deep Scan: %s", exc)
            raise

    async def trigger_light_scan(self, service: Optional["LabNKBandiService"] = None) -> Dict[str, Any]:
        """Esegue immediatamente una Light Scan sulle fonti prioritarie Tier 1 e Tier 2."""
        svc = service or self.service
        if not svc:
            raise ValueError("LabNKBandiService instance required for ingestion scan")

        t0 = asyncio.get_event_loop().time()
        logger.info("NightlyScheduler: Inizio Light Scan (14:00 mode - Tier 1/2 prioritari)...")
        tier1_sources = self.get_tier1_tier2_sources()
        try:
            report = await IngestionOrchestrator.harvest_all(svc, sources_subset=tier1_sources)
            elapsed_ms = round((asyncio.get_event_loop().time() - t0) * 1000, 2)
            self._total_light_runs += 1
            self._last_run_type = "LIGHT_SCAN"
            self._last_run_timestamp = datetime.now(timezone.utc)
            self._last_run_duration_ms = elapsed_ms
            self._last_error = None
            logger.info("NightlyScheduler: Light Scan completata in %.2f ms (%d fonti)", elapsed_ms, len(tier1_sources))
            return report
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("NightlyScheduler: Errore durante Light Scan: %s", exc)
            raise

    def compute_next_event(self) -> tuple[datetime, str, float]:
        """Calcola il timestamp del prossimo evento pianificato (00:01 o 14:00) e i secondi di attesa."""
        now = datetime.now(timezone.utc)

        # Prossimo 00:01 UTC
        cand_deep = now.replace(hour=0, minute=1, second=0, microsecond=0)
        if cand_deep <= now:
            cand_deep += timedelta(days=1)

        # Prossimo 14:00 UTC
        cand_light = now.replace(hour=14, minute=0, second=0, microsecond=0)
        if cand_light <= now:
            cand_light += timedelta(days=1)

        if cand_deep < cand_light:
            return cand_deep, "DEEP_SCAN", (cand_deep - now).total_seconds()
        else:
            return cand_light, "LIGHT_SCAN", (cand_light - now).total_seconds()

    async def _run_loop(self) -> None:
        """Loop principale asincrono con attesa computata e liveness telemetry."""
        logger.info("NightlyIngestionScheduler avviato con successo in background.")
        while self._is_running:
            try:
                next_dt, event_type, wait_sec = self.compute_next_event()
                self._next_scheduled_run = next_dt
                self._next_run_type = event_type
                logger.info(
                    "NightlyScheduler Liveness Heartbeat: Prossimo evento %s schedulato per %s UTC (tra %.0f sec)",
                    event_type, next_dt.isoformat(), wait_sec
                )

                # Attesa a blocchi di massimo 60 secondi per consentire cancellazione reattiva e heartbeats
                remaining = wait_sec
                while remaining > 0 and self._is_running:
                    step = min(remaining, 60.0)
                    await asyncio.sleep(step)
                    remaining -= step

                if not self._is_running:
                    break

                # Esecuzione dell'evento pianificato
                if event_type == "DEEP_SCAN":
                    await self.trigger_deep_scan()
                else:
                    await self.trigger_light_scan()

            except asyncio.CancelledError:
                logger.info("NightlyIngestionScheduler ricevuto segnale di cancellazione.")
                break
            except Exception as exc:
                self._last_error = str(exc)
                logger.error("NightlyIngestionScheduler eccezione non gestita nel loop: %s", exc)
                await asyncio.sleep(30.0)

        self._is_running = False
        logger.info("NightlyIngestionScheduler arrestato.")

    def start(self, service: Optional["LabNKBandiService"] = None) -> None:
        """Avvia il task asincrono in background se non è già attivo."""
        if self._is_running:
            logger.warning("NightlyIngestionScheduler è già in esecuzione.")
            return

        if service:
            self.service = service

        self._is_running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            self._task = None
        logger.info("NightlyIngestionScheduler avviato.")

    def stop(self) -> None:
        """Arresta lo scheduler in modo pulito."""
        if not self._is_running:
            return

        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("NightlyIngestionScheduler arresto richiesto.")
