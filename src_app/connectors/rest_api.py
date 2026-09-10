"""REST API Connector for Tier 1 sources (SEDIA EU, TED v3 CQL queries, Open Data).
Nexus Keystone v1.1.0-Universal | Protocollo CRV 4.0.
"""

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
    if isinstance(val, list):
        if not val:
            return None
        val = val[0]
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


def _parse_eu_date(val: Any) -> Optional[datetime]:
    """Converte epoch ms (int, float o stringa numerica) o stringa ISO in datetime timezone-aware UTC."""
    if val is None:
        return None
    if isinstance(val, list):
        if not val:
            return None
        val = val[0]
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val) / 1000.0, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        if cleaned.replace(".", "", 1).isdigit():
            try:
                return datetime.fromtimestamp(float(cleaned) / 1000.0, tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                return None
        try:
            iso_str = cleaned.replace("+0000", "+00:00").replace("Z", "+00:00")
            return datetime.fromisoformat(iso_str)
        except (ValueError, TypeError):
            return None
    return None


class RestApiConnector(BaseBandoConnector):
    """Connector for Tier 1 REST API endpoints (SEDIA EU, TED v3, Socrata Open Data)."""

    def __init__(
        self,
        name: str = "REST_API_Generic",
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
        max_pages: int = 2,
    ):
        super().__init__(
            name=name,
            fonte_tipo=FonteTipo.REST_API,
            rate_limiter=rate_limiter,
            anti_ban=anti_ban,
        )
        self.max_pages = max(1, max_pages)
        self.pages_scanned: int = 0

    async def fetch_raw(
        self,
        url_or_query: str,
        headers: Optional[Dict[str, str]] = None,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
    ) -> RawBandoPayload:
        """Fetch raw JSON payload from REST API endpoint, supporting multi-page POST for TED CQL and SEDIA."""
        req_headers = self.anti_ban.get_headers(headers)
        req_headers["Accept"] = "application/json"

        # Determinazione automatica se effettuare una richiesta POST specializzata (TED v3 o SEDIA API)
        is_ted_search = "ted.europa.eu" in url_or_query and ("search" in url_or_query or "notices" in url_or_query)
        is_sedia_search = "ec.europa.eu" in url_or_query and "search" in url_or_query
        should_post = method.upper() == "POST" or is_ted_search or is_sedia_search

        payload_to_send = json_body
        self.pages_scanned = 0

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            if is_sedia_search:
                req_headers.pop("Content-Type", None)
                base_url = url_or_query.split("?")[0]
                sedia_params = {"apiKey": "SEDIA"}
                query_filter = {
                    "bool": {
                        "must": [
                            {"terms": {"type": ["1", "2"]}},
                            {"terms": {"status": ["31094501", "31094502"]}}
                        ]
                    }
                }
                all_results: List[Dict[str, Any]] = []
                last_status = 200
                last_headers: Dict[str, str] = {}
                pages_fetched = 0

                for page_num in range(1, self.max_pages + 1):
                    files = {
                        "query": ("blob", json.dumps(query_filter), "application/json")
                    }
                    data = {
                        "text": "***",
                        "pageSize": "100",
                        "pageNumber": str(page_num),
                    }
                    response = await client.post(base_url, headers=req_headers, params=sedia_params, data=data, files=files)
                    if response.is_error:
                        if page_num == 1:
                            response.raise_for_status()
                        break

                    last_status = response.status_code
                    last_headers = dict(response.headers)
                    pages_fetched += 1

                    try:
                        page_json = response.json()
                        results = page_json.get("results", [])
                        all_results.extend(results)
                        if len(results) < 100:
                            break
                    except Exception:
                        break

                self.pages_scanned = pages_fetched
                combined_payload = {"results": all_results, "totalResults": len(all_results)}
                return RawBandoPayload(
                    raw_content=json.dumps(combined_payload).encode("utf-8"),
                    content_type="application/json",
                    source_url=url_or_query,
                    headers=last_headers,
                    fetched_at=datetime.now(timezone.utc),
                    status_code=last_status,
                )

            elif is_ted_search:
                req_headers["Content-Type"] = "application/json"
                all_notices: List[Dict[str, Any]] = []
                last_status = 200
                last_headers = {}
                pages_fetched = 0

                for page_num in range(1, self.max_pages + 1):
                    ted_body = json_body.copy() if json_body else {
                        "query": "CY = ITA",
                        "fields": ["publication-number", "notice-title", "buyer-name", "total-value"],
                        "scope": "ACTIVE",
                        "paginationMode": "PAGE_NUMBER",
                        "page": page_num,
                        "limit": 50,
                    }
                    ted_body["page"] = page_num
                    if "limit" not in ted_body:
                        ted_body["limit"] = 50
                    if "fields" in ted_body and isinstance(ted_body["fields"], list):
                        ted_body["fields"] = [
                            f if f != "estimated-value" else "total-value"
                            for f in ted_body["fields"]
                        ]
                        if "total-value" not in ted_body["fields"]:
                            ted_body["fields"].append("total-value")
                    if "scope" not in ted_body:
                        ted_body["scope"] = "ACTIVE"

                    response = await client.post(url_or_query, headers=req_headers, json=ted_body)
                    if response.is_error:
                        if page_num == 1:
                            response.raise_for_status()
                        break

                    last_status = response.status_code
                    last_headers = dict(response.headers)
                    pages_fetched += 1

                    try:
                        page_json = response.json()
                        notices = page_json.get("notices") or page_json.get("results") or []
                        all_notices.extend(notices)
                        if len(notices) < ted_body.get("limit", 50):
                            break
                    except Exception:
                        break

                self.pages_scanned = pages_fetched
                combined_payload = {
                    "notices": all_notices,
                    "results": all_notices,
                    "total": len(all_notices),
                }
                return RawBandoPayload(
                    raw_content=json.dumps(combined_payload).encode("utf-8"),
                    content_type="application/json",
                    source_url=url_or_query,
                    headers=last_headers,
                    fetched_at=datetime.now(timezone.utc),
                    status_code=last_status,
                )

            elif should_post:
                req_headers["Content-Type"] = "application/json"
                response = await client.post(url_or_query, headers=req_headers, json=payload_to_send or {})
                self.pages_scanned = 1
            else:
                response = await client.get(url_or_query, headers=req_headers)
                self.pages_scanned = 1
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

        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
            first = data["results"][0]
            if isinstance(first, dict) and ("frameworkProgramme" in first or "metadata" in first or "callTitle" in first or "identifier" in first):
                return self.parse_sedia_eu_json(data, payload.source_url)
            elif isinstance(first, dict) and ("publication-number" in first or "notice-title" in first):
                return self.parse_ted_v3_cql(data, payload.source_url)

        if isinstance(data, dict) and "notices" in data:
            return self.parse_ted_v3_cql(data, payload.source_url)

        return self.parse_generic_json(data, payload.source_url)

    def parse_sedia_eu_json(self, data: Dict[str, Any], source_url: str) -> List[CanonicalGrantModel]:
        """Parse SEDIA EU Funding & Tenders API response into CGM records with ZERO-MOCK enforcement."""
        records: List[CanonicalGrantModel] = []
        items = data.get("results", [])
        now_utc = datetime.now(timezone.utc)

        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

            ext_id = str(
                meta.get("identifier")
                or item.get("identifier")
                or meta.get("id")
                or item.get("id")
                or meta.get("callIdentifier")
                or item.get("callIdentifier", "")
                or item.get("reference", "")
            ).strip()

            # Estrazione titolo con supporto multilingua e ZERO-MOCK MANDATE
            raw_title = meta.get("title") or item.get("title") or meta.get("callTitle") or item.get("callTitle")
            titolo = _extract_multilingual_text(raw_title)
            if not titolo or not titolo.strip():
                logger.warning("DROP_RECORD: Record scartato per titolo mancante/vuoto (SEDIA ID: %s)", ext_id)
                continue

            raw_ente = _extract_multilingual_text(meta.get("frameworkProgramme") or item.get("frameworkProgramme"))
            if not raw_ente or raw_ente.isdigit() or len(raw_ente) < 3:
                ente = "Commissione Europea / SEDIA"
            else:
                ente = raw_ente

            budget = _parse_float_amount(meta.get("budget") or item.get("budget"))

            # Gestione date aperture e scadenze (epoch ms o ISO)
            raw_start = meta.get("startDate") or item.get("startDate")
            data_apertura = _parse_eu_date(raw_start)

            raw_deadline = meta.get("deadlineDate") or item.get("deadlineDate")
            data_scadenza = _parse_eu_date(raw_deadline)

            # stato: BandoStato.APERTO se data_scadenza is None or data_scadenza > datetime.now(timezone.utc) altrimenti BandoStato.CHIUSO
            if data_scadenza is None or data_scadenza > now_utc:
                stato = BandoStato.APERTO
            else:
                stato = BandoStato.CHIUSO

            url_bando = (
                item.get("url")
                or meta.get("url")
                or (f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ext_id}" if ext_id else source_url)
            )

            bando_id = CanonicalGrantModel.calculate_payload_hash(f"SEDIA:{ext_id or titolo}")

            raw_desc = meta.get("summary") or meta.get("description") or item.get("summary") or item.get("description")
            descrizione = _extract_multilingual_text(raw_desc)

            tipo_agevolazione = meta.get("grantType") or item.get("grantType") or "Grant / Sovereign Support"
            if isinstance(tipo_agevolazione, list) and tipo_agevolazione:
                tipo_agevolazione = str(tipo_agevolazione[0])

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=titolo,
                ente_erogatore=ente,
                descrizione=descrizione,
                tipo_agevolazione=str(tipo_agevolazione),
                budget_totale=budget,
                data_apertura=data_apertura,
                data_scadenza=data_scadenza,
                stato=stato,
                regioni_target=["Tutte"],
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
            raw_title = item.get("notice-title") or item.get("title")
            titolo = _extract_multilingual_text(raw_title)
            if not titolo or not titolo.strip():
                logger.warning("DROP_RECORD: Record scartato per titolo mancante/vuoto (TED ID: %s)", ext_id)
                continue

            ente = _extract_multilingual_text(item.get("buyer-name") or item.get("contracting-authority")) or "Unione Europea - TED"
            budget = _parse_float_amount(item.get("total-value") or item.get("estimated-value"))

            data_pub = _parse_eu_date(item.get("publication-date") or item.get("publicationDate"))
            data_scad = _parse_eu_date(item.get("deadline-date") or item.get("deadlineDate"))

            url_bando = item.get("url") or (f"https://ted.europa.eu/udl?uri=TED:NOTICE:{ext_id}:TEXT:IT:HTML" if ext_id else source_url)
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
                regioni_target=["Tutte"],
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
                    data_apertura = _parse_eu_date(item[date_key])
                    if data_apertura:
                        break

            data_scadenza = None
            for date_key in ("data_scadenza", "data_fine", "deadlineDate", "data_fine_presentazione_domande"):
                if item.get(date_key):
                    data_scadenza = _parse_eu_date(item[date_key])
                    if data_scadenza:
                        break

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
