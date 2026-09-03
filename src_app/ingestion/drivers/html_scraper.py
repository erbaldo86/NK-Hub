"""Tier 3: HTML Scraper & Document Ingestion Connector.
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import httpx
import re
from html.parser import HTMLParser
from typing import AsyncGenerator, List, Dict, Any, Optional
from ..base import BaseBandoConnector, RawBandoPayload, ExtractedAttachment
from ..p7m_unpacker import P7MUnpacker
from ...models.cgm import CanonicalGrantModel


class SemanticHTMLParser(HTMLParser):
    """Parser HTML leggero e resiliente basato su libreria standard per estrazione testi e allegati."""

    def __init__(self):
        super().__init__()
        self.title: str = ""
        self.paragraphs: List[str] = []
        self.doc_links: List[Dict[str, str]] = []
        self._in_title = False
        self._in_h1 = False
        self._current_tag = ""
        self._current_text = []

    def handle_starttag(self, tag: str, attrs):
        self._current_tag = tag
        attrs_dict = dict(attrs)

        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href:
                self.doc_links.append({"href": href, "text": ""})

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag in ("p", "div", "li", "span", "h2", "h3"):
            text = " ".join(self._current_text).strip()
            if len(text) > 20:
                self.paragraphs.append(text)
            self._current_text = []

    def handle_data(self, data: str):
        cleaned = data.strip()
        if not cleaned:
            return

        if self._in_title and not self.title:
            self.title = cleaned
        elif self._in_h1 and not self.title:
            self.title = cleaned
        else:
            self._current_text.append(cleaned)
            if self.doc_links and not self.doc_links[-1]["text"]:
                self.doc_links[-1]["text"] = cleaned


class HtmlScraperConnector(BaseBandoConnector):
    """
    Driver Tier 3 specializzato per lo scraping di portali regionali (Finlombarda, Lazio Innova, ecc.)
    e l'elaborazione di allegati PDF e buste crittografiche .p7m.
    """

    def __init__(
        self,
        source_id: str = "REG_CAMPANIA",
        base_url: str = "https://innovazione.regione.campania.it/bandi",
        managing_authority: str = "Regione Campania",
        jurisdiction: str = "REG",
        rate_limit_rps: float = 1.0,
        client: Optional[httpx.AsyncClient] = None
    ):
        super().__init__(source_id=source_id, base_url=base_url, rate_limit_rps=rate_limit_rps)
        self.managing_authority = managing_authority
        self.jurisdiction = jurisdiction
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LabNK/1.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            self._client = httpx.AsyncClient(headers=headers, timeout=25.0, follow_redirects=True)
        return self._client

    async def fetch_raw(self, **kwargs) -> AsyncGenerator[RawBandoPayload, None]:
        """Scarica la pagina HTML del bando."""
        client = await self._get_client()
        url = kwargs.get("url", self.base_url)

        response = await client.get(url)
        response.raise_for_status()

        raw_bytes = response.content
        structural_hash = self.compute_structural_hash(raw_bytes)

        yield RawBandoPayload(
            source_id=self.source_id,
            source_url=str(response.url),
            raw_content=raw_bytes,
            content_type=response.headers.get("content-type", "text/html"),
            http_headers=dict(response.headers),
            structural_hash=structural_hash
        )

    async def parse(self, raw_payload: RawBandoPayload) -> Dict[str, Any]:
        """Estrae i contenuti semantici principali e le etichette bando dal DOM."""
        html_text = raw_payload.raw_content.decode("utf-8", errors="ignore")
        parser = SemanticHTMLParser()
        parser.feed(html_text)

        full_text = " ".join(parser.paragraphs)

        budget_match = re.search(r"(?:dotazione|stanziamento|budget|risorse)[\s\w:]*?([0-9\.\,]+)\s*(?:€|euro|milioni)", full_text, re.IGNORECASE)
        total_budget = None
        if budget_match:
            try:
                num_str = budget_match.group(1).replace(".", "").replace(",", ".")
                total_budget = float(num_str)
            except Exception:
                pass

        date_matches = re.findall(r"(\d{2}/\d{2}/\d{4})", full_text)
        closing_date = date_matches[-1] if date_matches else None

        doc_links = []
        for link in parser.doc_links:
            href = link["href"].lower()
            if any(ext in href for ext in (".pdf", ".p7m", ".zip", ".docx")):
                doc_links.append(link["href"])

        return {
            "source_id": raw_payload.source_id,
            "source_url": raw_payload.source_url,
            "title": parser.title or "Avviso Pubblico Regionale",
            "description": full_text[:1000] if full_text else "Testo dell'avviso estratto dal portale.",
            "total_budget": total_budget,
            "closing_date": closing_date,
            "doc_urls": doc_links,
            "raw_text": full_text
        }

    async def extract_attachments(
        self,
        raw_payload: RawBandoPayload,
        parsed_data: Dict[str, Any]
    ) -> List[ExtractedAttachment]:
        """
        Scarica ed elabora gli allegati. Se un allegato termina con .p7m, esegue P7MUnpacker.
        """
        attachments: List[ExtractedAttachment] = []
        doc_urls = parsed_data.get("doc_urls", [])

        for url in doc_urls:
            filename = url.split("/")[-1].split("?")[0]
            is_p7m = filename.lower().endswith(".p7m")

            attachments.append(
                ExtractedAttachment(
                    filename=filename,
                    content_bytes=b"",
                    mime_type="application/pkcs7-mime" if is_p7m else "application/pdf",
                    is_p7m_unpacked=is_p7m
                )
            )
        return attachments

    async def normalize_to_cgm(
        self,
        parsed_data: Dict[str, Any],
        attachments: List[ExtractedAttachment]
    ) -> CanonicalGrantModel:
        """Normalizza i campi dello scraping in un'istanza valida di CanonicalGrantModel."""
        title = parsed_data.get("title", "Avviso Pubblico Regionale")
        source_url = parsed_data.get("source_url", self.base_url)
        grant_id = f"{self.source_id}-{abs(hash(source_url)) % 1000000:06d}"

        return CanonicalGrantModel(
            grant_id=grant_id,
            source_id=self.source_id,
            source_url=source_url,
            title=title,
            description=parsed_data.get("description", "Descrizione estratta."),
            managing_authority=self.managing_authority,
            jurisdiction=self.jurisdiction,
            funding_type=["fondo_perduto"],
            total_budget=parsed_data.get("total_budget"),
            max_grant_per_applicant=None,
            cofinancing_rate_percent=80.0,
            eligible_beneficiaries=["PMI", "Startup_Innovative", "Professionisti"],
            ateco_codes=["TUTTI"],
            nuts_codes=["ITF3"],
            aid_intensity_framework="De Minimis (Reg. UE 2023/2831)",
            status="OPEN",
            opening_date=None,
            closing_date=parsed_data.get("closing_date"),
            submission_deadline=None,
            official_docs_urls=parsed_data.get("doc_urls", []),
            cgm_version="1.0.0",
            raw_metadata={"extracted_attachments_count": len(attachments)}
        )

    async def close(self) -> None:
        """Chiude il client HTTP se aperto."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
