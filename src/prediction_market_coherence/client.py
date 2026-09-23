from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests


BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


class KalshiClient:
    """Small public-market-data client for the MVP detector."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "prediction-market-coherence/0.1"})

    def iter_markets(
        self,
        *,
        status: str = "open",
        event_ticker: str | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield markets from GET /markets, following Kalshi cursor pagination."""
        cursor: str | None = None
        pages = 0

        while True:
            params: dict[str, Any] = {"status": status, "limit": 1000, "mve_filter": "exclude"}
            if event_ticker:
                params["event_ticker"] = event_ticker
            if cursor:
                params["cursor"] = cursor

            response = self.session.get(
                f"{self.base_url}/markets",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()

            for market in payload.get("markets", []):
                yield market

            pages += 1
            cursor = payload.get("cursor") or None
            if not cursor or (max_pages is not None and pages >= max_pages):
                break
