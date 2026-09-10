"""Incentivi.gov.it & Registro Nazionale Aiuti (RNA) Connector.
Nexus Keystone v1.1.0-Universal | Protocollo CRV 4.0.
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from src_app.connectors.base import (
    AntiBanPolicy,
    AsyncRateLimiter,
    BaseBandoConnector,
    RawBandoPayload,
)
from src_app.core.config import DE_MINIMIS_THRESHOLD
from src_app.models.cgm import (
    BandoStato,
    CanonicalGrantModel,
    FonteTipo,
    MacroCategoria,
)

logger = logging.getLogger("IncentiviGovConnector")


def _parse_italian_date(val: Any) -> Optional[datetime]:
    """Parse dates in ISO format, DD/MM/YYYY, or epoch ms."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val) / 1000.0, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        # Try DD/MM/YYYY or DD-MM-YYYY
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt = datetime.strptime(cleaned.split(".")[0].replace("Z", ""), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        try:
            iso_str = cleaned.replace("+0000", "+00:00").replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return None


def _clean_amount(val: Any) -> Optional[float]:
    """Extract float amount from number or string."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d,\.]", "", val).strip()
        if not cleaned:
            return None
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "." in cleaned:
            # Se formattato come 50.000 o 1.000.000 (separatore migliaia italiano senza virgola decimale)
            parts = cleaned.split(".")
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                cleaned = "".join(parts)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


class IncentiviGovConnector(BaseBandoConnector):
    """
    Connettore sovereign per il portale nazionale Incentivi.gov.it e
    il Registro Nazionale degli Aiuti di Stato (RNA).
    Estrae e normalizza CAR (Codice Aiuto Registro), CUP, date, regione e soglia De Minimis.
    """

    DEFAULT_ENDPOINT = "https://www.incentivi.gov.it/api/v1/incentivi"

    def __init__(
        self,
        name: str = "INCENTIVI_GOV_RNA",
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
    ):
        super().__init__(
            name=name,
            fonte_tipo=FonteTipo.REST_API,
            rate_limiter=rate_limiter,
            anti_ban=anti_ban,
        )

    async def fetch_raw(
        self,
        url_or_query: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> RawBandoPayload:
        """Esegue la richiesta HTTP verso il portale Incentivi.gov.it o RNA con rate limiting e anti-ban."""
        endpoint = url_or_query if url_or_query.startswith("http") else self.DEFAULT_ENDPOINT
        req_headers = self.anti_ban.get_headers(headers)
        req_headers["Accept"] = "application/json, text/html;q=0.9"

        await self.rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            response = await client.get(endpoint, headers=req_headers, params=params)
            response.raise_for_status()

        return RawBandoPayload(
            raw_content=response.content,
            content_type=response.headers.get("content-type", "application/json"),
            source_url=str(response.url) if response.url else endpoint,
            headers=dict(response.headers),
            fetched_at=datetime.now(timezone.utc),
            status_code=response.status_code,
        )

    async def parse(self, payload: RawBandoPayload) -> List[CanonicalGrantModel]:
        """Estrae i record dal payload JSON o HTML di Incentivi.gov.it / RNA."""
        content_str = (
            payload.raw_content.decode("utf-8", errors="replace")
            if isinstance(payload.raw_content, bytes)
            else payload.raw_content
        )

        try:
            data = json.loads(content_str)
        except Exception:
            logger.warning("Payload non JSON per %s, tentativo fallback", payload.source_url)
            return []

        records: List[CanonicalGrantModel] = []
        items = data if isinstance(data, list) else data.get("incentivi") or data.get("results") or data.get("items") or [data]

        for item in items:
            if not isinstance(item, dict):
                continue
            grant = self.parse_single_record(item, payload.source_url)
            if grant:
                records.append(grant)

        logger.info("IncentiviGovConnector estratte %d misure da %s", len(records), payload.source_url)
        return records

    def parse_single_record(self, item: Dict[str, Any], source_url: str) -> Optional[CanonicalGrantModel]:
        """Normalizza un singolo record da Incentivi.gov o RNA nel Canonical Grant Model."""
        titolo = (
            item.get("titolo")
            or item.get("denominazioneMisura")
            or item.get("titoloMisura")
            or item.get("name")
            or ""
        ).strip()
        if not titolo:
            return None

        # Identificativi: CAR (Codice Aiuto Registro) e CUP
        ext_id = str(
            item.get("id")
            or item.get("codiceMisura")
            or item.get("car")
            or item.get("codiceAiuto")
            or ""
        ).strip()

        car_code = (
            item.get("car")
            or item.get("codiceAiutoRna")
            or item.get("codiceMisura")
        )
        if car_code:
            car_code = str(car_code).strip()

        cup_code = item.get("cup") or item.get("codiceCup")
        if cup_code:
            cup_code = str(cup_code).strip()

        # Ente erogatore
        ente = (
            item.get("soggettoConcedente")
            or item.get("enteErogatore")
            or item.get("amministrazioneCompetente")
            or item.get("ministero")
            or "Incentivi.gov.it / MIMIT"
        ).strip()

        # Descrizione
        desc = item.get("descrizione") or item.get("finalita") or item.get("sintesi") or ""

        # Date
        data_apertura = _parse_italian_date(item.get("dataApertura") or item.get("dataInizio") or item.get("dataPubblicazione"))
        data_scadenza = _parse_italian_date(item.get("dataScadenza") or item.get("dataChiusura") or item.get("dataFine"))

        # Stato bando
        now_utc = datetime.now(timezone.utc)
        if data_scadenza and data_scadenza < now_utc:
            stato = BandoStato.CHIUSO
        else:
            raw_stato = str(item.get("stato") or item.get("status") or "").upper()
            if "CHIUS" in raw_stato:
                stato = BandoStato.CHIUSO
            elif "SCADENZA" in raw_stato:
                stato = BandoStato.IN_SCADENZA
            elif "FUTUR" in raw_stato or "PIANIF" in raw_stato:
                stato = BandoStato.PIANIFICATO
            else:
                stato = BandoStato.APERTO

        # Aspetti finanziari e De Minimis
        budget = _clean_amount(item.get("dotazioneFinanziaria") or item.get("budgetTotale") or item.get("stanziamento"))
        massimale = _clean_amount(item.get("importoMassimo") or item.get("contributoMassimo") or item.get("massimale"))
        copertura = _clean_amount(item.get("percentualeCopertura") or item.get("intensitaAiuto"))

        # Riconoscimento applicabilità De Minimis
        desc_lower = (desc + " " + titolo + " " + str(item.get("tipoAiuto", ""))).lower()
        is_de_minimis = (
            "de minimis" in desc_lower
            or "1407/2013" in desc_lower
            or "2831/2023" in desc_lower
            or bool(massimale and massimale <= DE_MINIMIS_THRESHOLD and "fondo perduto" in desc_lower)
        )

        tipo_agev = item.get("tipoAgevolazione") or item.get("formaAiuto") or ("Contributo a fondo perduto (de minimis)" if is_de_minimis else "Agevolazione pubblica")

        # Territorio / Regione
        regioni_raw = item.get("regioni") or item.get("regione") or item.get("territorio")
        regioni: List[str] = []
        if isinstance(regioni_raw, list):
            regioni = [str(r).strip() for r in regioni_raw if r]
        elif isinstance(regioni_raw, str):
            if regioni_raw.strip().lower() in ("nazionale", "tutte", "italia", "tutto il territorio nazionale"):
                regioni = ["Tutte"]
            else:
                regioni = [r.strip() for r in regioni_raw.split(",") if r.strip()]
        if not regioni:
            regioni = ["Tutte"]

        # Beneficiari e ATECO
        beneficiari_raw = item.get("beneficiari") or item.get("tipologiaBeneficiari") or ["PMI"]
        beneficiari = [str(b).strip() for b in beneficiari_raw] if isinstance(beneficiari_raw, list) else [str(beneficiari_raw)]

        settori_raw = item.get("settoriAteco") or item.get("settori") or ["TUTTI"]
        settori = [str(s).strip() for s in settori_raw] if isinstance(settori_raw, list) else [str(settori_raw)]

        url_bando = item.get("url") or item.get("linkBando") or item.get("urlScheda") or source_url
        bando_id = CanonicalGrantModel.calculate_payload_hash(f"INCENTIVIGOV:{ext_id or titolo}")

        return CanonicalGrantModel(
            bando_id=bando_id,
            titolo=titolo,
            ente_erogatore=ente,
            descrizione=desc if desc else None,
            tipo_agevolazione=tipo_agev,
            budget_totale=budget,
            importo_massimo_finanziabile=massimale,
            percentuale_copertura=copertura,
            data_apertura=data_apertura,
            data_scadenza=data_scadenza,
            stato=stato,
            settori_beneficiari=settori,
            tipologia_beneficiari=beneficiari,
            regioni_target=regioni,
            url_bando=url_bando,
            codice_cup=cup_code,
            macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA,
            car_codice_misura=car_code,
            de_minimis_applicabile=is_de_minimis,
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome="Incentivi.gov.it & RNA",
            hash_payload=CanonicalGrantModel.calculate_payload_hash(json.dumps(item, sort_keys=True, default=str)),
        )
