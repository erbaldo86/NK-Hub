"""Asynchronous Rate Limiter & Resilient Backoff Manager.
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import asyncio
import time
import random
from typing import Dict, Optional, Callable, Any


class TokenBucket:
    """Implementazione thread-safe / coroutine-safe del Token Bucket algorithm."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate  # Tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_updated
                self.last_updated = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                needed = tokens - self.tokens
                wait_time = needed / self.rate
                await asyncio.sleep(wait_time)


class AsyncRateLimiter:
    """
    Gestore di limitazione delle richieste per sorgente/dominio e wrapper di resilienza
    con exponential backoff e jitter anti-ban.
    """

    def __init__(self, default_rps: float = 2.0, default_burst: float = 5.0):
        self.default_rps = default_rps
        self.default_burst = default_burst
        self._buckets: Dict[str, TokenBucket] = {}
        self._global_lock = asyncio.Lock()

    async def _get_bucket(self, key: str, rps: Optional[float] = None) -> TokenBucket:
        async with self._global_lock:
            if key not in self._buckets:
                rate = rps if rps is not None else self.default_rps
                capacity = max(rate, self.default_burst)
                self._buckets[key] = TokenBucket(rate=rate, capacity=capacity)
            return self._buckets[key]

    async def throttle(self, key: str = "default", rps: Optional[float] = None) -> None:
        """Blocca l'esecuzione finché non è disponibile un token per il dominio specificato."""
        bucket = await self._get_bucket(key, rps)
        await bucket.acquire(1.0)

    async def execute_with_backoff(
        self,
        coro_func: Callable[..., Any],
        *args,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retry_exceptions: tuple = (Exception,),
        **kwargs
    ) -> Any:
        """
        Esegue una funzione asincrona applicando exponential backoff con jitter casuale in caso di errore.
        """
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return await coro_func(*args, **kwargs)
            except retry_exceptions as exc:
                last_exception = exc
                if attempt == max_retries:
                    raise exc

                jitter = random.uniform(0.8, 1.2)
                delay = min(max_delay, (base_delay * (2 ** attempt)) * jitter)
                await asyncio.sleep(delay)

        raise last_exception
