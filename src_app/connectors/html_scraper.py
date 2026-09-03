"""HTML Scraper Connector for Tier 3 sources (Regional Portals, Institutional Scrapers) using BeautifulSoup4."""

from datetime import datetime, timezone
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
import urllib.parse
from bs4 import BeautifulSoup
import httpx

from src_app.models.cgm import BandoStato, CanonicalGrantModel, FonteTipo
from src_app.connectors.base import (
    AntiBanPolicy,
    AsyncRateLimiter,
    BaseBandoConnector,
    DOMDriftDetector,
    RawBandoPayload,
)

logger = logging.getLogger("HtmlScraperConnector")


class HtmlScraperConnector(BaseBandoConnector):
    """Connector for Tier 3 HTML scraping sources with DOM Drift Detection and JSON-LD support."""

    def __init__(
        self,
        name: str = "HTML_Scraper_Generic",
        card_selector: str = ".bando-item, article, tr.bando, .views-row, .card, .node--type-bando, .bando, .item-bando, .views-field, .view-content > div, li.bando, .elenco-bandi .item",
        title_selector: str = ".title, h2, h3, h4, a.bando-link, .card-title, .views-field-title, .field--name-title, .titolo, header a",
        link_selector: str = "a.bando-link, .card-title a, h2 a, h3 a, h4 a, a",
        desc_selector: str = ".description, .summary, p, .card-text, .views-field-body, .field--name-body, .descrizione, .abstract",
        deadline_selector: str = ".deadline, .scadenza, .data-scadenza, .views-field-field-data-scadenza, time, .field--name-field-data-scadenza",
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
    ):
        super().__init__(
            name=name,
            fonte_tipo=FonteTipo.HTML_SCRAPER,
            rate_limiter=rate_limiter,
            anti_ban=anti_ban,
        )
        self.card_selector = card_selector
        self.title_selector = title_selector
        self.link_selector = link_selector
        self.desc_selector = desc_selector
        self.deadline_selector = deadline_selector

    async def fetch_raw(self, url_or_query: str, headers: Optional[Dict[str, str]] = None) -> RawBandoPayload:
        """Fetch raw HTML document from portal endpoint."""
        req_headers = self.anti_ban.get_headers(headers)

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            response = await client.get(url_or_query, headers=req_headers)
            response.raise_for_status()

        return RawBandoPayload(
            raw_content=response.content,
            content_type=response.headers.get("content-type", "text/html"),
            source_url=str(response.url) if response.url else url_or_query,
            headers=dict(response.headers),
            fetched_at=datetime.now(timezone.utc),
            status_code=response.status_code,
        )

    def check_dom_drift(self, previous_hash: str, html_content: str) -> Tuple[bool, str]:
        """Compute current DOM skeleton hash and return whether structure drift occurred."""
        current_hash = DOMDriftDetector.compute_skeleton_hash(html_content)
        has_drifted = DOMDriftDetector.detect_drift(previous_hash, current_hash)
        if has_drifted:
            logger.warning("DOM drift detected for scraper %s! Prev hash: %s, New hash: %s", self.name, previous_hash, current_hash)
        return has_drifted, current_hash

    def _parse_json_ld(self, soup: BeautifulSoup, source_url: str, skeleton_hash: str) -> List[CanonicalGrantModel]:
        """Extract structured grant items from Schema.org JSON-LD scripts."""
        records: List[CanonicalGrantModel] = []
        for script in soup.find_all("script", type="application/ld+json"):
            content = (script.string or script.get_text() or "").strip()
            if not content:
                continue
            try:
                data = json.loads(content)
            except Exception:
                continue

            items: List[Dict[str, Any]] = []
            if isinstance(data, list):
                items.extend([i for i in data if isinstance(i, dict)])
            elif isinstance(data, dict):
                if "@graph" in data and isinstance(data["@graph"], list):
                    items.extend([i for i in data["@graph"] if isinstance(i, dict)])
                elif "itemListElement" in data and isinstance(data["itemListElement"], list):
                    for el in data["itemListElement"]:
                        if isinstance(el, dict):
                            items.append(el.get("item") if isinstance(el.get("item"), dict) else el)
                else:
                    items.append(data)

            for idx, item in enumerate(items):
                title = (
                    item.get("name")
                    or item.get("headline")
                    or item.get("title")
                )
                if not title or not isinstance(title, str) or len(title.strip()) < 4:
                    continue
                title = title.strip()

                raw_url = item.get("url") or item.get("@id") or source_url
                link = urllib.parse.urljoin(source_url, str(raw_url).strip())
                desc = item.get("description") or item.get("abstract") or item.get("articleBody")
                if desc and not isinstance(desc, str):
                    desc = str(desc)

                bando_id = CanonicalGrantModel.calculate_payload_hash(f"{self.name}:jsonld:{link}:{title}")
                cgm = CanonicalGrantModel(
                    bando_id=bando_id,
                    titolo=title,
                    ente_erogatore=self.name,
                    descrizione=desc.strip() if desc else None,
                    stato=BandoStato.APERTO,
                    url_bando=link,
                    fonte_tipo=FonteTipo.HTML_SCRAPER,
                    fonte_nome=self.name,
                    hash_payload=CanonicalGrantModel.calculate_payload_hash(json.dumps(item, sort_keys=True)),
                    dom_skeleton_hash=skeleton_hash,
                )
                records.append(cgm)

        return records

    async def parse(self, payload: RawBandoPayload) -> List[CanonicalGrantModel]:
        """Parse HTML page into CGM records using JSON-LD and CSS selectors with ZERO-MOCK enforcement."""
        html_str = (
            payload.raw_content.decode("utf-8", errors="replace")
            if isinstance(payload.raw_content, bytes)
            else payload.raw_content
        )

        skeleton_hash = DOMDriftDetector.compute_skeleton_hash(html_str)
        soup = BeautifulSoup(html_str, "html.parser")
        records: List[CanonicalGrantModel] = []
        seen_bando_ids = set()

        # 1. Parsing JSON-LD Schema.org strutturato
        json_ld_records = self._parse_json_ld(soup, payload.source_url, skeleton_hash)
        for r in json_ld_records:
            if r.bando_id not in seen_bando_ids:
                seen_bando_ids.add(r.bando_id)
                records.append(r)

        # 2. Parsing visivo tramite selettori CSS (Drupal, Bootstrap, Portali Regionali)
        cards = soup.select(self.card_selector)
        if not cards or len(cards) < 2:
            # Fallback euristico: ricerca link semantici correlati a bandi e agevolazioni
            keywords = ["bando", "avviso", "incentiv", "agevolaz", "finanziament", "contribut", "voucher", "misura", "fondo", "innovazion", "startup", "investiment"]
            found_parents = []
            seen_hrefs = set()
            for elem in soup.find_all("a", href=True):
                txt = elem.get_text(strip=True).lower()
                href = elem.get("href", "")
                if any(kw in txt or kw in href.lower() for kw in keywords) and len(elem.get_text(strip=True)) >= 10:
                    if href not in seen_hrefs:
                        seen_hrefs.add(href)
                        found_parents.append(elem.parent if elem.parent else elem)
            if found_parents:
                cards = found_parents

        for i, card in enumerate(cards):
            # ZERO-MOCK MANDATE: Estrazione del titolo autentico senza mock o fallback sintetici
            title_elem = card.select_one(self.title_selector) or card.find(["h1", "h2", "h3", "h4", "a"])
            raw_title = title_elem.get_text(strip=True) if title_elem else None

            # Scarto immediato del record se il titolo è assente o non valido
            if not raw_title or len(raw_title.strip()) < 4:
                logger.warning("DROP_RECORD: Record scartato per titolo mancante/insufficiente (Fonte: %s, Card #%d)", self.name, i)
                continue
            title = raw_title.strip()

            # Risoluzione sicura dell'URL relativo tramite urllib.parse.urljoin
            link_elem = card.select_one(self.link_selector) or (card if card.name == "a" else card.find("a", href=True))
            href = link_elem.get("href", "").strip() if link_elem and link_elem.has_attr("href") else ""
            if href:
                link = urllib.parse.urljoin(payload.source_url, href)
            else:
                link = payload.source_url

            # Descrizione
            desc_elem = card.select_one(self.desc_selector)
            desc = desc_elem.get_text(strip=True) if desc_elem else None

            # Scadenza euristica
            deadline_elem = card.select_one(self.deadline_selector)
            deadline_text = deadline_elem.get_text(strip=True) if deadline_elem else None

            bando_id = CanonicalGrantModel.calculate_payload_hash(f"{self.name}:{link}:{title}")
            if bando_id in seen_bando_ids:
                continue
            seen_bando_ids.add(bando_id)

            card_raw = str(card)

            cgm = CanonicalGrantModel(
                bando_id=bando_id,
                titolo=title,
                ente_erogatore=self.name,
                descrizione=desc or deadline_text,
                stato=BandoStato.APERTO,
                url_bando=link,
                fonte_tipo=FonteTipo.HTML_SCRAPER,
                fonte_nome=self.name,
                hash_payload=CanonicalGrantModel.calculate_payload_hash(card_raw),
                dom_skeleton_hash=skeleton_hash,
            )
            records.append(cgm)

        return records
