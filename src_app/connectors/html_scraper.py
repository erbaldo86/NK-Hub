"""HTML Scraper Connector for Tier 3 sources (Regional Portals, Institutional Scrapers) using BeautifulSoup4.
Nexus Keystone v1.1.0-Universal | Protocollo CRV 4.0.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
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

# Selettori CSS ottimizzati per Drupal 10, Elementor WordPress e portali regionali italiani
DEFAULT_CARD_SELECTOR = (
    ".bando-item, article, tr.bando, .views-row, .card, .node--type-bando, .bando, "
    ".item-bando, .views-field, .view-content > div, li.bando, .elenco-bandi .item, "
    ".elementor-post, .elementor-grid-item, .elementor-card, .node--view-mode-teaser, "
    ".card-bando, .box-bando, .scheda-bando, .list-item-bando, .entry-bando, "
    ".cmp-card, .it-card, .table-bandi tbody tr, .bandi-table tr, .views-element-container .views-row, "
    ".teaser-bando, .c-bando, .bando-box, .bandi-list__item"
)

DEFAULT_TITLE_SELECTOR = (
    ".title, h2, h3, h4, a.bando-link, .card-title, .views-field-title, .field--name-title, "
    ".titolo, header a, .elementor-post__title, .elementor-post__title a, .bando-title, "
    ".titolo-bando, .entry-title, .entry-title a, .c-bando__title, .cmp-card__title, "
    ".views-field-title a, .field--name-title a, .it-card-title, h2.title, h3.title"
)

DEFAULT_LINK_SELECTOR = (
    "a.bando-link, .card-title a, h2 a, h3 a, h4 a, .elementor-post__title a, "
    ".entry-title a, .c-bando__link, .cmp-card__link, a.read-more, a.btn-bando, a"
)

DEFAULT_DESC_SELECTOR = (
    ".description, .summary, p, .card-text, .views-field-body, .field--name-body, "
    ".descrizione, .abstract, .elementor-post__excerpt, .sommario, .c-bando__desc, "
    ".entry-content, .field--name-field-descrizione, .it-card-text"
)

DEFAULT_DEADLINE_SELECTOR = (
    ".deadline, .scadenza, .data-scadenza, .views-field-field-data-scadenza, time, "
    ".field--name-field-data-scadenza, .bando-scadenza, .date-scadenza, .badge-scadenza, "
    ".field--name-field-scadenza"
)


class HtmlScraperConnector(BaseBandoConnector):
    """Connector for Tier 3 HTML scraping sources with controlled multi-page pagination, DOM Drift Detection and JSON-LD support."""

    def __init__(
        self,
        name: str = "HTML_Scraper_Generic",
        card_selector: str = DEFAULT_CARD_SELECTOR,
        title_selector: str = DEFAULT_TITLE_SELECTOR,
        link_selector: str = DEFAULT_LINK_SELECTOR,
        desc_selector: str = DEFAULT_DESC_SELECTOR,
        deadline_selector: str = DEFAULT_DEADLINE_SELECTOR,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
        max_pages: int = 3,
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
        self.max_pages = max(1, max_pages)
        self.pages_scanned: int = 0

    async def fetch_raw(
        self,
        url_or_query: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> RawBandoPayload:
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

    def find_next_page_url(
        self,
        html_content: str,
        current_url: str,
        current_page: int = 1,
    ) -> Optional[str]:
        """
        Riconosce i pattern di paginazione nei portali regionali:
        1. Selettori CSS per link successivi (Drupal 10, Elementor, Bootstrap):
           'li.pager__item--next a', '.pagination a', 'a[rel=next]', '.elementor-pagination a.next'.
        2. Testo del link corrispondente alla pagina target (es. "2", "3").
        3. Riconoscimento parametri query (?page=, &p=, start=).
        """
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, "html.parser")
        target_page = current_page + 1

        # 1. Selettori prioritari per link esplicito "Successivo / Next"
        next_selectors = [
            "li.pager__item--next a",
            ".pager__item--next a",
            "li.pager-next a",
            "a[rel='next']",
            ".pagination a.next",
            ".pagination li.next a",
            "a.page-numbers.next",
            ".elementor-pagination a.next",
            ".elementor-pagination a[class*='next']",
            "a.next-page",
            "a.next",
            ".pager__link--next",
            "a[aria-label*='Next' i]",
            "a[aria-label*='Successiv' i]",
            "a[aria-label*='Avanti' i]",
        ]
        for sel in next_selectors:
            elem = soup.select_one(sel)
            if elem and elem.has_attr("href"):
                href = elem["href"].strip()
                if href and href != "#" and not href.startswith("javascript:"):
                    return urllib.parse.urljoin(current_url, href)

        # 2. Ricerca del numero di pagina target all'interno dei contenitori di paginazione
        target_str = str(target_page)
        pagination_container_selectors = [
            ".pagination a",
            "ul.pager a",
            "nav.pagination a",
            ".elementor-pagination a",
            "a.page-numbers",
            ".pagination-container a",
            ".pager a",
            ".pagination-wrapper a",
            "ul.page-numbers a",
        ]
        for container_sel in pagination_container_selectors:
            for a in soup.select(container_sel):
                txt = a.get_text(strip=True)
                if txt == target_str and a.has_attr("href"):
                    href = a["href"].strip()
                    if href and href != "#" and not href.startswith("javascript:"):
                        return urllib.parse.urljoin(current_url, href)

        # 3. Analisi della query string dell'URL corrente per pattern ?page=, &p=, start=
        parsed = urllib.parse.urlparse(current_url)
        qs = urllib.parse.parse_qs(parsed.query)

        has_pagination_markup = bool(
            soup.select(".pagination, .pager, .elementor-pagination, .page-numbers, li.pager__item, nav[aria-label*='paginat' i]")
        )

        for param_name in ("page", "p", "pg", "page_number"):
            if param_name in qs:
                try:
                    curr = int(qs[param_name][0])
                    qs[param_name] = [str(curr + 1)]
                    new_query = urllib.parse.urlencode(qs, doseq=True)
                    return urllib.parse.urlunparse(parsed._replace(query=new_query))
                except (ValueError, IndexError):
                    pass

        if "start" in qs:
            try:
                curr = int(qs["start"][0])
                qs["start"] = [str(curr + 10)]
                new_query = urllib.parse.urlencode(qs, doseq=True)
                return urllib.parse.urlunparse(parsed._replace(query=new_query))
            except (ValueError, IndexError):
                pass

        # Se il markup presenta paginazione ma i link sono generati o non catturati:
        if has_pagination_markup and target_page <= 50:
            qs["page"] = [str(target_page)]
            new_query = urllib.parse.urlencode(qs, doseq=True)
            return urllib.parse.urlunparse(parsed._replace(query=new_query))

        return None

    async def fetch_and_parse(
        self,
        url_or_query: str,
        max_pages: Optional[int] = None,
    ) -> List[CanonicalGrantModel]:
        """
        Esegue l'acquisizione multi-pagina adattiva data-driven (Hash-Stop).
        Rimuove il limite fisso max_pages e arresta lo sfoglio quando:
        1. Tutti i bandi dell'ultima pagina sono duplicati (hash già visti).
        2. Tutti i bandi dell'ultima pagina sono chiusi (BandoStato.CHIUSO).
        3. Non ci sono più bandi o pagine successive da esplorare.
        """
        safety_ceiling = max_pages if max_pages is not None else 50
        all_records: List[CanonicalGrantModel] = []
        seen_bando_ids: Set[str] = set()
        seen_hashes: Set[str] = set()
        visited_urls: Set[str] = set()

        current_url = url_or_query
        pages_fetched = 0

        for page_idx in range(1, safety_ceiling + 1):
            if current_url in visited_urls:
                break
            visited_urls.add(current_url)

            await self.rate_limiter.acquire()
            try:
                payload = await self.fetch_raw(current_url)
                pages_fetched += 1
            except Exception as exc:
                if page_idx == 1:
                    raise
                logger.warning("Errore fetch pagina %d (%s): %s", page_idx, current_url, exc)
                break

            records = await self.parse(payload)
            if not records:
                logger.debug("[%s] Hash-Stop: Nessun record estratto a pagina %d.", self.name, page_idx)
                break

            new_records = [
                r for r in records
                if r.bando_id not in seen_bando_ids and r.hash_payload not in seen_hashes
            ]

            # Condizione Hash-Stop 1: tutti i record estratti sono duplicati/già visti
            if not new_records:
                logger.info(
                    "[%s] Hash-Stop attivato: tutti i bandi a pagina %d sono duplicati/noti, arresto sfoglio.",
                    self.name, page_idx,
                )
                break

            # Condizione Hash-Stop 2: tutti i bandi della pagina sono CHIUSI
            all_closed = len(records) > 0 and all(r.stato == BandoStato.CHIUSO for r in records)
            if all_closed:
                logger.info(
                    "[%s] Hash-Stop attivato: tutti i bandi a pagina %d sono CHIUSI, arresto sfoglio storico.",
                    self.name, page_idx,
                )
                for r in new_records:
                    seen_bando_ids.add(r.bando_id)
                    seen_hashes.add(r.hash_payload)
                    all_records.append(r)
                break

            for r in new_records:
                seen_bando_ids.add(r.bando_id)
                seen_hashes.add(r.hash_payload)
                all_records.append(r)

            # Cerca l'URL della pagina successiva
            html_text = (
                payload.raw_content.decode("utf-8", errors="replace")
                if isinstance(payload.raw_content, bytes)
                else str(payload.raw_content)
            )
            next_url = self.find_next_page_url(html_text, current_url, current_page=page_idx)
            if not next_url or next_url in visited_urls:
                break
            current_url = next_url

        self.pages_scanned = pages_fetched
        return all_records

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
        seen_bando_ids: Set[str] = set()

        # 1. Parsing JSON-LD Schema.org strutturato
        json_ld_records = self._parse_json_ld(soup, payload.source_url, skeleton_hash)
        for r in json_ld_records:
            if r.bando_id not in seen_bando_ids:
                seen_bando_ids.add(r.bando_id)
                records.append(r)

        # 2. Parsing visivo tramite selettori CSS (Drupal, Bootstrap, Elementor, Portali Regionali)
        cards = soup.select(self.card_selector)
        if not cards or len(cards) < 2:
            # Fallback euristico: ricerca link semantici correlati a bandi e agevolazioni
            keywords = [
                "bando", "avviso", "incentiv", "agevolaz", "finanziament",
                "contribut", "voucher", "misura", "fondo", "innovazion", "startup", "investiment"
            ]
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
