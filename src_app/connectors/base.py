"""Base classes, Rate Limiter, DOM Drift Detector, and Anti-Ban Policy for Bando Connectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import random
import re
from typing import Dict, List, Optional, Any
import asyncio

from bs4 import BeautifulSoup

from src_app.models.cgm import CanonicalGrantModel, FonteTipo


@dataclass
class RawBandoPayload:
    """Raw payload received from a data source."""
    raw_content: str | bytes
    content_type: str
    source_url: str
    headers: Dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    status_code: int = 200


@dataclass
class ParsedBandoRecord:
    """Intermediate parsed record prior to CGM normalization."""
    external_id: str
    titolo: str
    ente_erogatore: str
    url_bando: str
    descrizione: Optional[str] = None
    tipo_agevolazione: Optional[str] = None
    budget_totale: Optional[float] = None
    importo_massimo: Optional[float] = None
    data_apertura: Optional[datetime] = None
    data_scadenza: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


class AsyncRateLimiter:
    """Asynchronous rate limiter ensuring polite request intervals."""

    def __init__(self, requests_per_second: float = 2.0):
        self.min_interval = 1.0 / max(requests_per_second, 0.001)
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait if necessary to observe rate limits."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_call
            wait_time = self.min_interval - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_call = asyncio.get_event_loop().time()


class DOMDriftDetector:
    """Detector for HTML layout structure changes using SHA-256 DOM skeleton hashing."""

    @staticmethod
    def extract_skeleton(html_content: str) -> str:
        """Extract a structural skeleton of HTML tags, ignoring text, attributes, scripts, and styles."""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove non-structural tags
        for element in soup(["script", "style", "meta", "link", "svg", "noscript"]):
            element.decompose()
        
        tags: List[str] = []
        for elem in soup.find_all(True):
            tags.append(elem.name)
        
        return ">".join(tags)

    @classmethod
    def compute_skeleton_hash(cls, html_content: str) -> str:
        """Compute SHA-256 skeleton hash of HTML document structure."""
        skeleton = cls.extract_skeleton(html_content)
        return hashlib.sha256(skeleton.encode("utf-8")).hexdigest()

    @classmethod
    def detect_drift(cls, previous_hash: str, current_hash: str) -> bool:
        """Return True if DOM structure hash has changed."""
        if not previous_hash or not current_hash:
            return False
        return previous_hash != current_hash


class AntiBanPolicy:
    """Anti-ban policy providing User-Agent rotation, delay randomization, and backoff logic."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ]

    def __init__(self, rotate_user_agent: bool = True, base_delay: float = 1.0):
        self.rotate_user_agent = rotate_user_agent
        self.base_delay = base_delay

    def get_headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Generate request headers with rotated User-Agent and standard browser headers."""
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS) if self.rotate_user_agent else self.USER_AGENTS[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,json;q=0.8,*/*;q=0.7",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def get_random_delay(self, jitter: float = 0.5) -> float:
        """Return base delay plus randomized jitter."""
        return max(0.1, self.base_delay + random.uniform(-jitter, jitter))

    @staticmethod
    def get_exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
        """Calculate exponential backoff time for retry attempts."""
        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
        jitter = random.uniform(0, 0.5 * delay)
        return delay + jitter


class BaseBandoConnector(ABC):
    """Abstract base class for all Bando connectors."""

    def __init__(
        self,
        name: str,
        fonte_tipo: FonteTipo,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
    ):
        self.name = name
        self.fonte_tipo = fonte_tipo
        self.rate_limiter = rate_limiter or AsyncRateLimiter(requests_per_second=2.0)
        self.anti_ban = anti_ban or AntiBanPolicy()

    @abstractmethod
    async def fetch_raw(self, url_or_query: str, headers: Optional[Dict[str, str]] = None) -> RawBandoPayload:
        """Fetch raw payload from external data source."""
        pass

    @abstractmethod
    async def parse(self, payload: RawBandoPayload) -> List[CanonicalGrantModel]:
        """Parse raw payload into Canonical Grant Model records."""
        pass

    async def fetch_and_parse(self, url_or_query: str) -> List[CanonicalGrantModel]:
        """Fetch raw payload and parse into CGM records."""
        await self.rate_limiter.acquire()
        payload = await self.fetch_raw(url_or_query)
        return await self.parse(payload)
