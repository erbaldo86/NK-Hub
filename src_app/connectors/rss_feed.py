"""RSS and Atom Feed Connector for Tier 2 sources (Incentivi.gov.it, Gazzetta Ufficiale)."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import logging
from typing import Dict, List, Optional, Set
import xml.etree.ElementTree as ET
import httpx

from src_app.models.cgm import BandoStato, CanonicalGrantModel, FonteTipo
from src_app.connectors.base import (
    AntiBanPolicy,
    AsyncRateLimiter,
    BaseBandoConnector,
    RawBandoPayload,
)

logger = logging.getLogger(__name__)


class RssFeedConnector(BaseBandoConnector):
    """Connector for Tier 2 RSS/Atom feed sources with ETag support and GUID deduplication."""

    def __init__(
        self,
        name: str = "RSS_Feed_Generic",
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
    ):
        super().__init__(
            name=name,
            fonte_tipo=FonteTipo.RSS_FEED,
            rate_limiter=rate_limiter,
            anti_ban=anti_ban,
        )
        self.cached_etags: Dict[str, str] = {}
        self.cached_last_modified: Dict[str, str] = {}
        self.seen_guids: Set[str] = set()

    def clear_cache(self) -> None:
        """Clear cached ETags and GUID history."""
        self.cached_etags.clear()
        self.cached_last_modified.clear()
        self.seen_guids.clear()

    async def fetch_raw(self, url_or_query: str, headers: Optional[Dict[str, str]] = None) -> RawBandoPayload:
        """Fetch RSS payload, supplying ETag / If-Modified-Since headers if available."""
        req_headers = self.anti_ban.get_headers(headers)
        req_headers["Accept"] = "application/rss+xml, application/xml, text/xml, application/atom+xml;q=0.9"

        if url_or_query in self.cached_etags:
            req_headers["If-None-Match"] = self.cached_etags[url_or_query]
        if url_or_query in self.cached_last_modified:
            req_headers["If-Modified-Since"] = self.cached_last_modified[url_or_query]

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            response = await client.get(url_or_query, headers=req_headers)

        if response.status_code == 304:
            logger.info("HTTP 304 Not Modified received for %s", url_or_query)
            return RawBandoPayload(
                raw_content=b"",
                content_type="application/xml",
                source_url=url_or_query,
                headers=dict(response.headers),
                fetched_at=datetime.now(timezone.utc),
                status_code=304,
            )

        response.raise_for_status()

        if "etag" in response.headers:
            self.cached_etags[url_or_query] = response.headers["etag"]
        if "last-modified" in response.headers:
            self.cached_last_modified[url_or_query] = response.headers["last-modified"]

        return RawBandoPayload(
            raw_content=response.content,
            content_type=response.headers.get("content-type", "application/xml"),
            source_url=url_or_query,
            headers=dict(response.headers),
            fetched_at=datetime.now(timezone.utc),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            status_code=response.status_code,
        )

    async def parse(self, payload: RawBandoPayload) -> List[CanonicalGrantModel]:
        """Parse RSS/Atom XML payload into CGM records, enforcing GUID deduplication."""
        if payload.status_code == 304 or not payload.raw_content:
            return []

        content_bytes = (
            payload.raw_content.encode("utf-8")
            if isinstance(payload.raw_content, str)
            else payload.raw_content
        )

        try:
            root = ET.fromstring(content_bytes)
        except ET.ParseError:
            # Fallback graceful su HTML scraper
            try:
                from .html_scraper import HtmlScraperConnector
                scraper = HtmlScraperConnector(name=self.name, rate_limiter=self.rate_limiter, anti_ban=self.anti_ban)
                return await scraper.parse(payload)
            except Exception:
                return []

        records: List[CanonicalGrantModel] = []
        
        # Check RSS vs Atom root
        tag_name = root.tag.lower()
        if tag_name.endswith("rss") or root.find("channel") is not None:
            records = self._parse_rss(root, payload.source_url)
        elif tag_name.endswith("feed"):
            records = self._parse_atom(root, payload.source_url)
        else:
            # Fallback: try parsing all <item> or <entry> tags regardless of namespace
            items = root.findall(".//item")
            if items:
                records = self._parse_rss_items(items, payload.source_url)
            else:
                entries = root.findall(".//entry")
                records = self._parse_atom_entries(entries, payload.source_url)

        return records

    def _parse_rss(self, root: ET.Element, source_url: str) -> List[CanonicalGrantModel]:
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(".//item")
        return self._parse_rss_items(items, source_url)

    def _parse_rss_items(self, items: List[ET.Element], source_url: str) -> List[CanonicalGrantModel]:
        records: List[CanonicalGrantModel] = []

        for item in items:
            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            guid_elem = item.find("guid")
            pub_date_elem = item.find("pubDate")
            if pub_date_elem is None:
                pub_date_elem = item.find("date")

            title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Senza Titolo"
            link = link_elem.text.strip() if link_elem is not None and link_elem.text else source_url
            guid = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else link
            desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None

            if guid in self.seen_guids:
                continue
            self.seen_guids.add(guid)

            pub_date = None
            if pub_date_elem is not None and pub_date_elem.text:
                try:
                    pub_date = parsedate_to_datetime(pub_date_elem.text.strip())
                except Exception:
                    pass

            bando_id = CanonicalGrantModel.calculate_payload_hash(f"{self.name}:{guid}")
            item_raw = f"{title}|{link}|{guid}|{desc}"

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=title,
                ente_erogatore=self.name,
                descrizione=desc,
                data_apertura=pub_date,
                stato=BandoStato.APERTO,
                url_bando=link,
                fonte_tipo=FonteTipo.RSS_FEED,
                fonte_nome=self.name,
                hash_payload=CanonicalGrantModel.calculate_payload_hash(item_raw),
            )
            records.append(cgm)

        return records

    def _parse_atom(self, root: ET.Element, source_url: str) -> List[CanonicalGrantModel]:
        # Atom elements may use default namespaces
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns) or root.findall(".//entry")
        return self._parse_atom_entries(entries, source_url, ns)

    def _parse_atom_entries(
        self, entries: List[ET.Element], source_url: str, ns: Optional[Dict[str, str]] = None
    ) -> List[CanonicalGrantModel]:
        records: List[CanonicalGrantModel] = []

        for entry in entries:
            title_elem = entry.find("atom:title", ns) if ns else entry.find("title")
            if title_elem is None:
                title_elem = entry.find("title")

            id_elem = entry.find("atom:id", ns) if ns else entry.find("id")
            if id_elem is None:
                id_elem = entry.find("id")

            summary_elem = entry.find("atom:summary", ns) or entry.find("atom:content", ns) if ns else entry.find("summary") or entry.find("content")
            if summary_elem is None:
                summary_elem = entry.find("summary") or entry.find("content")

            link_elem = entry.find("atom:link", ns) if ns else entry.find("link")
            if link_elem is None:
                link_elem = entry.find("link")

            updated_elem = entry.find("atom:updated", ns) or entry.find("atom:published", ns) if ns else entry.find("updated") or entry.find("published")
            if updated_elem is None:
                updated_elem = entry.find("updated") or entry.find("published")

            title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Senza Titolo"
            guid = id_elem.text.strip() if id_elem is not None and id_elem.text else title
            desc = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else None
            
            link = source_url
            if link_elem is not None:
                link = link_elem.attrib.get("href") or link_elem.text or source_url

            if guid in self.seen_guids:
                continue
            self.seen_guids.add(guid)

            pub_date = None
            if updated_elem is not None and updated_elem.text:
                try:
                    pub_date = datetime.fromisoformat(updated_elem.text.strip().replace("Z", "+00:00"))
                except ValueError:
                    pass

            bando_id = CanonicalGrantModel.calculate_payload_hash(f"{self.name}:{guid}")
            entry_raw = f"{title}|{link}|{guid}|{desc}"

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=title,
                ente_erogatore=self.name,
                descrizione=desc,
                data_apertura=pub_date,
                stato=BandoStato.APERTO,
                url_bando=link,
                fonte_tipo=FonteTipo.RSS_FEED,
                fonte_nome=self.name,
                hash_payload=CanonicalGrantModel.calculate_payload_hash(entry_raw),
            )
            records.append(cgm)

        return records
