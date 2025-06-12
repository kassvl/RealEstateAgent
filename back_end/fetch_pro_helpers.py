"""Lightweight helper around `requests` to provide:
- Rate limiting (simple sleep between calls)
- Automatic retries with exponential back-off for transient HTTP errors
- Optional proxy rotation (round-robin)

Example:
    fetcher = ProFetcher(rate_limit=0.5, proxies=["http://user:pass@1.2.3.4:8080"])
    resp = fetcher.get("https://example.com")
"""
from __future__ import annotations

import random
import time
import logging
from itertools import cycle
from typing import Dict, List, Optional, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from metrics import SCRAPE_ERRORS
import os
from vault_client import get_secret

logger = logging.getLogger(__name__)


class ProFetcher:
    def __init__(
        self,
        rate_limit: float = 0.5,
        proxies: Optional[Sequence[str]] = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        status_forcelist: Optional[Sequence[int]] = None,
    ) -> None:
        """Create a ProFetcher.

        Args:
            rate_limit: Minimum number of **seconds** between consecutive requests.
            proxies: Optional list of proxy URLs (``http://user:pass@host:port``). If provided, each request
                will pick the next proxy in round-robin manner.
            max_retries: Total retry attempts for idempotent requests.
            backoff_factor: Exponential back-off factor between retries.
            status_forcelist: HTTP status codes that trigger a retry.
        """
        self.rate_limit = max(rate_limit, 0.0)
        self._last_request_ts: float = 0.0

        _proxy_secret = get_secret("PROXY_LIST") or os.getenv("PROXY_LIST")
        PROXY_LIST = _proxy_secret.split(",") if _proxy_secret else []
        self.proxies_cycle = cycle(PROXY_LIST) if PROXY_LIST else None

        # Prepare a requests.Session with retry logic.
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist or (500, 502, 503, 504, 429),
            allowed_methods=(
                "HEAD",
                "GET",
                "OPTIONS",
                "POST",
                "PUT",
                "DELETE",
                "PATCH",
            ),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ----------------- Internal helpers -----------------
    def _rate_limit_sleep(self):
        """Sleep if last request was sooner than rate_limit allows."""
        elapsed = time.time() - self._last_request_ts
        wait = self.rate_limit - elapsed
        if wait > 0:
            time.sleep(wait)

    def _choose_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies_cycle:
            return None
        proxy_url = next(self.proxies_cycle)
        return {"http": proxy_url, "https": proxy_url}

    def _request(self, method: str, url: str, **kwargs):
        self._rate_limit_sleep()
        kwargs.setdefault("timeout", 15)
        # Attach proxy if configured
        proxy_dict = self._choose_proxy()
        if proxy_dict:
            kwargs.setdefault("proxies", proxy_dict)
            logger.debug("Using proxy %s for %s", proxy_dict.get('http') or proxy_dict.get('https'), url)
        try:
            resp = self.session.request(method, url, **kwargs)
        finally:
            # Mark time regardless of success/failure so we still rate-limit
            self._last_request_ts = time.time()
        return resp

    # ----------------- Public helpers -----------------
    def get(self, url: str, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self._request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self._request("DELETE", url, **kwargs)

    # For convenience
    def __getattr__(self, item):
        # Delegate unknown attrs to underlying session (e.g., headers)
        return getattr(self.session, item)
