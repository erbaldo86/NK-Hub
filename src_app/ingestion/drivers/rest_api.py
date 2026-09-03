"""Tier 1: REST API Connector (SEDIA EU F&T Portal & TED v3 API).
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import httpx
import json
from typing import AsyncGenerator, List, Dict, Any, Optional
from ..base import BaseBandoConnector, RawBandoPayload, ExtractedAttachment
from ...models.cgm import CanonicalGrantModel


class RestApiConnector(BaseBandoConnector):
    """
    Driver Tier 1 specializzato per l'acquisizione di bandi e avvisi via API REST
    (es. SEDIA Horizon Europe, Digital Europe, e TED v3 con query CQL).
    """

    def __init__(
        self,
        source_id: str = "EU_SEDIA",
        base_url: str = "https://api.tech.ec.europa.eu/search-api/prod/rest/search",
        api_key: Optional[str] = None,
        rate_limit_rps: float = 3.0,
        client: Optional[httpx.AsyncClient] = None
    ):
        super().__init__(source_id=source_id, base_url=base_url, rate_limit_rps=rate_limit_rps)
        self.api_key = api_key
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": "LabNK-BandiMonitor/1.0 (+https://labnk.nexus)"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(headers=headers, timeout=30.0)
        return self._client

    async def fetch_raw(
        self,
        cql_query: Optional[str] = None,
        program_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        **kwargs
    ) -> AsyncGenerator[RawBandoPayload, None]:
        """Esegue la richiesta HTTP all'API REST e restituisce i payload grezzi."""
        client = await self._get_client()

        params = {"page": page, "pageSize": page_size}
        if cql_query:
            params["q"] = cql_query
        if program_filter:
            params["program"] = program_filter
        params.update(kwargs)

        response = await client.get(self.base_url, params=params)
        response.raise_for_status()

        raw_bytes = response.content
        structural_hash = self.compute_structural_hash(raw_bytes)

        yield RawBandoPayload(
            source_id=self.source_id,
            source_url=str(response.url),
            raw_content=raw_bytes,
            content_type=response.headers.get("content-type", "application/json"),
            http_headers=dict(response.headers),
            structural_hash=structural_hash
        )

    async def parse(self, raw_payload: RawBandoPayload) -> Dict[str, Any]:
        """Estrae e normalizza le chiavi dal payload JSON SEDIA/TED."""
        try:
            data = json.loads(raw_payload.raw_content.decode("utf-8"))
        except Exception:
            data = {}

        items = data.get("results") or data.get("items") or data.get("notices") or []
        if not items and isinstance(data, dict) and "identifier" in data:
            items = [data]

        return {
            "source_id": raw_payload.source_id,
            "source_url": raw_payload.source_url,
            "items_count": len(items),
            "items": items,
            "raw_root": data
        }

    async def extract_attachments(
        self,
        raw_payload: RawBandoPayload,
        parsed_data: Dict[str, Any]
    ) -> List[ExtractedAttachment]:
        """Estrae i riferimenti ai documenti ufficiali associati ai bandi (Call documents, PDF)."""
        attachments: List[ExtractedAttachment] = []
        for item in parsed_data.get("items", []):
            docs = item.get("call_documents") or item.get("documents") or []
            for doc in docs:
                doc_url = doc.get("url") if isinstance(doc, dict) else str(doc)
                doc_name = doc.get("name", "document.pdf") if isinstance(doc, dict) else "document.pdf"
                if doc_url:
                    attachments.append(
                        ExtractedAttachment(
                            filename=doc_name,
                            content_bytes=b"",
                            mime_type="application/pdf"
                        )
                    )
        return attachments

    async def normalize_to_cgm(
        self,
        parsed_data: Dict[str, Any],
        attachments: List[ExtractedAttachment]
    ) -> CanonicalGrantModel:
        """
        Converte il primo elemento del batch in CanonicalGrantModel.
        """
        items = parsed_data.get("items", [])
        item = items[0] if items else {}

        grant_id = str(item.get("identifier") or item.get("id") or item.get("topic_id") or "EU-UNKNOWN-001")
        title = str(item.get("title") or item.get("topic_title") or "Bando Europeo")
        description = str(item.get("description") or item.get("topic_description") or "Descrizione non disponibile")
        managing_authority = str(item.get("managing_authority") or item.get("framework_programme") or "European Commission")

        total_budget = None
        if "budget" in item:
            try:
                total_budget = float(item["budget"])
            except (ValueError, TypeError):
                pass
        elif "total_budget" in item:
            try:
                total_budget = float(item["total_budget"])
            except (ValueError, TypeError):
                pass

        opening_date = item.get("opening_date") or item.get("call_start_date")
        closing_date = item.get("deadline_date") or item.get("call_end_date") or item.get("closing_date")

        doc_urls = [att.filename for att in attachments]

        return CanonicalGrantModel(
            grant_id=grant_id,
            source_id=self.source_id,
            source_url=parsed_data.get("source_url", self.base_url),
            title=title,
            description=description,
            managing_authority=managing_authority,
            jurisdiction="EU",
            funding_type=["fondo_perduto"],
            total_budget=total_budget,
            max_grant_per_applicant=None,
            cofinancing_rate_percent=100.0,
            eligible_beneficiaries=["PMI", "Startup_Innovative", "Enti_Ricerca", "Grandi_Imprese"],
            ateco_codes=["TUTTI"],
            nuts_codes=["IT"],
            aid_intensity_framework="GBER (Reg. UE 651/2014)",
            status="OPEN",
            opening_date=opening_date,
            closing_date=closing_date,
            submission_deadline=None,
            official_docs_urls=doc_urls,
            cgm_version="1.0.0",
            raw_metadata=item
        )

    async def close(self) -> None:
        """Chiude il client HTTP se aperto."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
