"""REST API Connector for Tier 1 sources (SEDIA EU, TED v3 CQL queries, Open Data)."""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from src_app.models.cgm import BandoStato, CanonicalGrantModel, FonteTipo
from src_app.connectors.base import (
    AntiBanPolicy,
    AsyncRateLimiter,
    BaseBandoConnector,
    RawBandoPayload,
)

logger = logging.getLogger("RestApiConnector")


def _extract_multilingual_text(val: Any) -> Optional[str]:
    """Estrae testo multilingua dando priorità all'italiano, poi inglese, poi primo valore disponibile."""
    if val is None:
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, dict):
        for lang_key in ("ita", "it", "IT", "ITA", "eng", "en", "EN", "ENG"):
            if lang_key in val and isinstance(val[lang_key], str) and val[lang_key].strip():
                return val[lang_key].strip()
        for v in val.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
            elif isinstance(v, (list, dict)):
                nested = _extract_multilingual_text(v)
                if nested:
                    return nested
    if isinstance(val, list):
        for item in val:
            extracted = _extract_multilingual_text(item)
            if extracted:
                return extracted
    return None


def _parse_float_amount(val: Any) -> Optional[float]:
    """Pulisce e normalizza importi valuta a float deterministico."""
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
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


class RestApiConnector(BaseBandoConnector):
    """Connector for Tier 1 REST API endpoints (SEDIA EU, TED v3, Socrata Open Data)."""

    def __init__(
        self,
        name: str = "REST_API_Generic",
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
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
    ) -> RawBandoPayload:
        """Fetch raw JSON payload from REST API endpoint, supporting POST for TED CQL and SEDIA."""
        req_headers = self.anti_ban.get_headers(headers)
        req_headers["Accept"] = "application/json"

        # Determinazione automatica se effettuare una richiesta POST (TED v3 o SEDIA API)
        is_ted_search = "ted.europa.eu" in url_or_query and ("search" in url_or_query or "notices" in url_or_query)
        is_sedia_search = "ec.europa.eu" in url_or_query and "search" in url_or_query
        should_post = method.upper() == "POST" or is_ted_search or is_sedia_search

        payload_to_send = json_body
        if should_post and payload_to_send is None:
            if is_ted_search:
                payload_to_send = {
                    "q": "ND = [* TO *]",
                    "page": 1,
                    "limit": 25,
                    "scope": "ACTIVE"
                }
            elif is_sedia_search:
                payload_to_send = {
                    "pageNumber": 1,
                    "pageSize": 25
                }

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            if should_post:
                req_headers["Content-Type"] = "application/json"
                response = await client.post(url_or_query, headers=req_headers, json=payload_to_send)
            else:
                response = await client.get(url_or_query, headers=req_headers)
            response.raise_for_status()

        return RawBandoPayload(
            raw_content=response.content,
            content_type=response.headers.get("content-type", "application/json"),
            source_url=url_or_query,
            headers=dict(response.headers),
            fetched_at=datetime.now(timezone.utc),
            status_code=response.status_code,
        )

    async def parse(self, payload: RawBandoPayload) -> List[CanonicalGrantModel]:
        """Parse raw payload according to source format (SEDIA EU, TED v3, or generic JSON)."""
        content_str = (
            payload.raw_content.decode("utf-8", errors="replace")
            if isinstance(payload.raw_content, bytes)
            else payload.raw_content
        )
        try:
            data = json.loads(content_str)
        except Exception:
            # Fallback graceful: se l'endpoint restituisce HTML invece di JSON, usa lo scraper HTML
            from .html_scraper import HtmlScraperConnector
            scraper = HtmlScraperConnector(name=self.name, rate_limiter=self.rate_limiter, anti_ban=self.anti_ban)
            return await scraper.parse(payload)

        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0 and "frameworkProgramme" in data["results"][0]:
            return self.parse_sedia_eu_json(data, payload.source_url)
        elif isinstance(data, dict) and ("notices" in data or ("results" in data and len(data["results"]) > 0 and "publication-number" in data["results"][0])):
            return self.parse_ted_v3_cql(data, payload.source_url)
        else:
            return self.parse_generic_json(data, payload.source_url)

    def parse_sedia_eu_json(self, data: Dict[str, Any], source_url: str) -> List[CanonicalGrantModel]:
        """Parse SEDIA EU Funding & Tenders API response into CGM records with ZERO-MOCK enforcement."""
        records: List[CanonicalGrantModel] = []
        items = data.get("results", [])

        for item in items:
            if not isinstance(item, dict):
                continue
            ext_id = str(item.get("identifier") or item.get("id") or item.get("callIdentifier", "")).strip()
            
            # Estrazione titolo con supporto multilingua e ZERO-MOCK MANDATE
            raw_title = item.get("title") or item.get("callTitle")
            titolo = _extract_multilingual_text(raw_title)
            if not titolo or not titolo.strip():
                logger.warning("DROP_RECORD: Record scartato per titolo mancante/vuoto (SEDIA ID: %s)", ext_id)
                continue

            ente = item.get("frameworkProgramme") or "Commissione Europea / SEDIA"
            budget = _parse_float_amount(item.get("budget"))

            data_apertura = None
            if item.get("startDate"):
                try:
                    data_apertura = datetime.fromisoformat(item["startDate"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            data_scadenza = None
            if item.get("deadlineDate"):
                try:
                    data_scadenza = datetime.fromisoformat(item["deadlineDate"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            url_bando = item.get("url") or f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ext_id}"
            bando_id = CanonicalGrantModel.calculate_payload_hash(f"SEDIA:{ext_id or titolo}")

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=titolo,
                ente_erogatore=ente,
                descrizione=_extract_multilingual_text(item.get("summary") or item.get("description")),
                tipo_agevolazione=item.get("grantType") or "Grant / Sovereign Support",
                budget_totale=budget,
                data_apertura=data_apertura,
                data_scadenza=data_scadenza,
                stato=BandoStato.APERTO,
                url_bando=url_bando,
                fonte_tipo=FonteTipo.REST_API,
                fonte_nome="SEDIA EU",
                hash_payload=CanonicalGrantModel.calculate_payload_hash(json.dumps(item, sort_keys=True)),
            )
            records.append(cgm)

        return records

    def parse_ted_v3_cql(self, data: Dict[str, Any], source_url: str) -> List[CanonicalGrantModel]:
        """Parse TED v3 CQL query API response into CGM records with multilingual title support and ZERO-MOCK."""
        records: List[CanonicalGrantModel] = []
        items = data.get("notices") or data.get("results") or []

        for item in items:
            if not isinstance(item, dict):
                continue
            ext_id = str(item.get("publication-number") or item.get("notice-id") or item.get("id", "")).strip()

            # Supporto titolo multilingua (ita prioritario) e ZERO-MOCK MANDATE
            raw_title = item.get("title") or item.get("notice-title")
            titolo = _extract_multilingual_text(raw_title)
            if not titolo or not titolo.strip():
                logger.warning("DROP_RECORD: Record scartato per titolo mancante/vuoto (TED ID: %s)", ext_id)
                continue

            ente = _extract_multilingual_text(item.get("buyer-name") or item.get("contracting-authority")) or "Unione Europea - TED"
            budget = _parse_float_amount(item.get("estimated-value") or item.get("total-value"))

            data_pub = None
            if item.get("publication-date"):
                try:
                    data_pub = datetime.fromisoformat(item["publication-date"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            data_scad = None
            if item.get("deadline-date"):
                try:
                    data_scad = datetime.fromisoformat(item["deadline-date"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            url_bando = item.get("url") or f"https://ted.europa.eu/udl?uri=TED:NOTICE:{ext_id}:TEXT:IT:HTML"
            bando_id = CanonicalGrantModel.calculate_payload_hash(f"TED:{ext_id or titolo}")

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=titolo,
                ente_erogatore=ente,
                descrizione=_extract_multilingual_text(item.get("description") or item.get("notice-abstract")),
                budget_totale=budget,
                data_apertura=data_pub,
                data_scadenza=data_scad,
                stato=BandoStato.APERTO,
                url_bando=url_bando,
                fonte_tipo=FonteTipo.REST_API,
                fonte_nome="TED v3",
                hash_payload=CanonicalGrantModel.calculate_payload_hash(json.dumps(item, sort_keys=True)),
            )
            records.append(cgm)

        return records

    def parse_generic_json(self, data: Dict[str, Any] | List[Any], source_url: str) -> List[CanonicalGrantModel]:
        """Generic JSON array/object parser for REST APIs with ZERO-MOCK MANDATE."""
        records: List[CanonicalGrantModel] = []
        items = data if isinstance(data, list) else data.get("items") or data.get("data") or [data]

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            # ZERO-MOCK MANDATE: Estrazione del titolo autentico senza fallback sintetici
            raw_title = (
                item.get("titolo")
                or item.get("title")
                or item.get("titolo_del_bando")
                or item.get("denominazione")
                or item.get("name")
                or item.get("oggetto")
            )
            titolo = _extract_multilingual_text(raw_title)
            if not titolo or not titolo.strip():
                logger.warning("DROP_RECORD: Record scartato per titolo assente o vuoto (Fonte: %s, item #%d)", self.name, i)
                continue

            ext_id = str(item.get("id") or item.get("code") or item.get("identifier") or CanonicalGrantModel.calculate_payload_hash(f"{titolo}:{i}")[:16])
            ente = str(item.get("ente") or item.get("ente_erogatore") or item.get("publisher") or item.get("amministrazione") or self.name)
            url_bando = str(item.get("url") or item.get("link") or item.get("url_bando") or item.get("link_al_bando") or source_url)
            budget = _parse_float_amount(item.get("budget") or item.get("dotazione_finanziaria") or item.get("importo_totale") or item.get("importo"))

            data_apertura = None
            for date_key in ("data_apertura", "data_inizio", "startDate", "data_inizio_presentazione_domande"):
                if item.get(date_key):
                    try:
                        data_apertura = datetime.fromisoformat(str(item[date_key]).replace("Z", "+00:00"))
                        break
                    except (ValueError, TypeError):
                        pass

            data_scadenza = None
            for date_key in ("data_scadenza", "data_fine", "deadlineDate", "data_fine_presentazione_domande"):
                if item.get(date_key):
                    try:
                        data_scadenza = datetime.fromisoformat(str(item[date_key]).replace("Z", "+00:00"))
                        break
                    except (ValueError, TypeError):
                        pass

            bando_id = CanonicalGrantModel.calculate_payload_hash(f"{self.name}:{ext_id}:{titolo}")

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=titolo,
                ente_erogatore=ente,
                descrizione=_extract_multilingual_text(item.get("descrizione") or item.get("description") or item.get("sintesi")),
                budget_totale=budget,
                data_apertura=data_apertura,
                data_scadenza=data_scadenza,
                url_bando=url_bando,
                fonte_tipo=FonteTipo.REST_API,
                fonte_nome=self.name,
                hash_payload=CanonicalGrantModel.calculate_payload_hash(json.dumps(item, sort_keys=True)),
            )
            records.append(cgm)

        return records
