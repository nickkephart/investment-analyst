#!/usr/bin/env python3
"""
Polygon.io (Massive) Direct API Client for ticker search.
Uses REST API when POLYGON_API_KEY or MASSIVE_API_KEY is set.
"""

import os
import time
from typing import List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class PolygonDirectClient:
    """Direct API client for Polygon.io ticker reference."""

    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
        if not self.api_key:
            raise ValueError("Polygon API key required")
        self._last_call = 0
        self._min_interval = 0.2  # Rate limit friendly

    def _request(self, path: str, params: dict = None) -> dict:
        if not HAS_REQUESTS:
            return {}
        params = params or {}
        params["apiKey"] = self.api_key
        url = f"{self.BASE_URL}{path}"
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Polygon API error: {e}")
            return {}

    def search_tickers(
        self,
        search: str,
        ticker_type: str = None,
        market: str = "stocks",
        limit: int = 10,
    ) -> List[str]:
        """
        Search for tickers by term.

        Returns:
            List of ticker symbols (e.g. ['XLE', 'VDE', ...])
        """
        params = {
            "search": search,
            "market": market,
            "active": "true",
            "limit": min(limit, 100),
        }
        if ticker_type:
            params["type"] = ticker_type

        data = self._request("/v3/reference/tickers", params)
        results = data.get("results", [])
        return [r["ticker"] for r in results if r.get("ticker")]
