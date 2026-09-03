"""Tier 2: RSS / Atom Feed Connector (Incentivi.gov.it & Gazzetta Ufficiale).
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import httpx
import xml.etree.ElementTree as ET
from typing import AsyncGenerator, List, Dict, Any, Optional
from ..base import BaseBandoConnector, RawBandoPayload, ExtractedAttachment
from ...models.cgm import CanonicalGrantModel


class RssFeedConnector(BaseBandoConnector):
    """
    Driver Tier 2 specializzato nel monitoraggio continuo a basso impatto di feed RSS/Atom.
    Supporta delta check tramite ETag / If-Modified-Since.
    """

    def __init__(
        self,
        source_id: str = "NAT_INCENTIVI",
        base_url: str = "https://www.incentivi.gov.it/it/notizie/feed",
        rate_limit_rps: float = 2.0,
        client: Optional[httpx.AsyncClient] = None
    ):
        super().__init__(source_id=source_id, base_url=base_url, rate_limit_rps=rate_limit_rps)
        self.cached_etag: Optional[str] = None
        self.cached_last_modified: Optional[str] = None
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": "LabNK-BandiMonitor/1.0 (+https://labnk.nexus)"}
            self._client = httpx.AsyncClient(headers=headers, timeout=20.0)
        return self._client

    async def fetch_raw(self, **kwargs) -> AsyncGenerator[RawBandoPayload, None]:
        """Esegue una GET condizionale del feed RSS."""
        client = await self._get_client()

        headers = {}
        if self.cached_etag:
            headers["If-None-Match"] = self.cached_etag
        if self.cached_last_modified:
            headers["If-Modified-Since"] = self.cached_last_modified

        response = await client.get(self.base_url, headers=headers)

        if response.status_code == 304:
            return

        response.raise_for_status()

        self.cached_etag = response.headers.get("etag")
        self.cached_last_modified = response.headers.get("last-modified")

        raw_bytes = response.content
        structural_hash = self.compute_structural_hash(raw_bytes)

        yield RawBandoPayload(
            source_id=self.source_id,
            source_url=str(response.url),
            raw_content=raw_bytes,
            content_type=response.headers.get("content-type", "application/xml"),
            http_headers=dict(response.headers),
            structural_hash=structural_hash
        )

    async def parse(self, raw_payload: RawBandoPayload) -> Dict[str, Any]:
        """Esegue il parsing XML del feed RSS 2.0 o Atom."""
        items: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(raw_payload.raw_content)

            channel = root.find("channel")
            if channel is not None:
                for item_node in channel.findall("item"):
                    title = item_node.findtext("title", "").strip()
                    link = item_node.findtext("link", "").strip()
                    desc = item_node.findtext("description", "").strip()
                    pub_date = item_node.findtext("pubDate", "").strip()
                    guid = item_node.findtext("guid", link).strip()
                    category = item_node.findtext("category", "").strip()

                    items.append({
                        "guid": guid,
                        "title": title,
                        "link": link,
                        "description": desc,
                        "pub_date": pub_date,
                        "category": category
                    })
            else:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry_node in root.findall("atom:entry", ns) or root.findall("entry"):
                    title = entry_node.findtext("atom:title", entry_node.findtext("title", "")).strip()
                    desc = entry_node.findtext("atom:summary", entry_node.findtext("summary", "")).strip()
                    updated = entry_node.findtext("atom:updated", entry_node.findtext("updated", "")).strip()
                    guid = entry_node.findtext("atom:id", entry_node.findtext("id", "")).strip()

                    link_elem = entry_node.find("atom:link", ns) or entry_node.find("link")
                    link = link_elem.attrib.get("href", "") if link_elem is not None else ""

                    items.append({
                        "guid": guid,
                        "title": title,
                        "link": link,
                        "description": desc,
                        "pub_date": updated,
                        "category": ""
                    })

        except Exception as exc:
            return {"error": str(exc), "items": []}

        return {
            "source_id": raw_payload.source_id,
            "source_url": raw_payload.source_url,
            "items_count": len(items),
            "items": items
        }

    async def extract_attachments(
        self,
        raw_payload: RawBandoPayload,
        parsed_data: Dict[str, Any]
    ) -> List[ExtractedAttachment]:
        """I feed RSS raramente contengono file binari diretti; restituisce elenco vuoto o link."""
        return []

    async def normalize_to_cgm(
        self,
        parsed_data: Dict[str, Any],
        attachments: List[ExtractedAttachment]
    ) -> CanonicalGrantModel:
        """Mappa un elemento del feed RSS in CanonicalGrantModel."""
        items = parsed_data.get("items", [])
        item = items[0] if items else {}

        guid = item.get("guid") or item.get("link") or "NAT-INCENTIVI-001"
        title = item.get("title") or "Incentivo Nazionale"
        description = item.get("description") or "Nessuna descrizione disponibile"
        link = item.get("link") or parsed_data.get("source_url", self.base_url)

        return CanonicalGrantModel(
            grant_id=f"NAT-INC-{abs(hash(guid)) % 1000000:06d}",
            source_id=self.source_id,
            source_url=link,
            title=title,
            description=description,
            managing_authority="Ministero delle Imprese e del Made in Italy (MIMIT)",
            jurisdiction="NAT",
            funding_type=["fondo_perduto", "credito_imposta"],
            total_budget=None,
            max_grant_per_applicant=None,
            cofinancing_rate_percent=50.0,
            eligible_beneficiaries=["PMI", "Startup_Innovative"],
            ateco_codes=["TUTTI"],
            nuts_codes=["IT"],
            aid_intensity_framework="De Minimis (Reg. UE 2023/2831)",
            status="OPEN",
            opening_date=None,
            closing_date=None,
            submission_deadline=None,
            official_docs_urls=[link] if link else [],
            cgm_version="1.0.0",
            raw_metadata=item
        )

    async def close(self) -> None:
        """Chiude il client HTTP se aperto."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
