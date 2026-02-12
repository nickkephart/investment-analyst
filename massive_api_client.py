"""
Massive.com / Polygon.io Integration

Supports:
1. Direct Polygon REST API (when api_key provided)
2. MCP protocol (when use_mcp=True, for Claude Desktop)

Requires POLYGON_API_KEY or MASSIVE_API_KEY for direct API. No mock data.
"""

import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class MassiveAPIClient:
    """
    Client for Massive.com / Polygon.io data:
    - Direct API: when api_key is provided
    - MCP: when use_mcp=True (Claude Desktop)

    Requires API key for direct API. Returns empty results when unavailable.
    """
    
    POLYGON_BASE = "https://api.polygon.io"

    def __init__(self, use_mcp: bool = False, api_key: Optional[str] = None):
        """
        Initialize client

        Args:
            use_mcp: If True, use MCP protocol (for Claude Desktop)
            api_key: Polygon.io API key for direct REST API. If not set, uses
                     POLYGON_API_KEY or MASSIVE_API_KEY env var.
        """
        self.use_mcp = use_mcp
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
        self._use_direct_api = bool(self.api_key and HAS_REQUESTS)
        self._last_polygon_call = 0
        
    def list_tickers(self, 
                     search: Optional[str] = None,
                     ticker_type: Optional[str] = None,
                     market: Optional[str] = None,
                     active: bool = True,
                     limit: int = 100) -> List[Dict]:
        """
        Search for tickers via Polygon API. Returns empty list when no API key.
        """
        if self.use_mcp:
            raise NotImplementedError("MCP server communication not yet implemented for standalone mode")

        if self._use_direct_api:
            return self._polygon_list_tickers(search, ticker_type, market, active, limit) or []

        return []
    
    def get_ticker_details(self, ticker: str) -> Dict:
        """
        Get ticker details via Polygon API. Returns empty dict when no API key.
        """
        if self.use_mcp:
            raise NotImplementedError("MCP server communication not yet implemented")

        if self._use_direct_api:
            result = self._polygon_get_ticker_details(ticker)
            return result or {}

        return {}
    
    def get_previous_close(self, ticker: str) -> Dict:
        """
        Get previous day close data. Returns empty dict when no API key.
        MCP call: massive:get_previous_close_agg(ticker=...)
        """
        if self.use_mcp:
            raise NotImplementedError("MCP server communication not yet implemented")
        if not self._use_direct_api:
            return {}
        # Polygon has prev close via /v2/aggs/ticker/{ticker}/prev - not implemented here
        return {}
    
    def get_historical_data(self, 
                           ticker: str,
                           from_date: str,
                           to_date: str,
                           timespan: str = "day",
                           multiplier: int = 1) -> List[Dict]:
        """
        Get historical aggregate data. Returns empty list when no API key.
        MCP call: massive:get_aggs(ticker=..., from_=..., to=..., timespan=..., multiplier=...)
        """
        if self.use_mcp:
            raise NotImplementedError("MCP server communication not yet implemented")
        if not self._use_direct_api:
            return []
        # Polygon has aggs via /v2/aggs/ticker/{ticker}/range - not implemented here
        return []
    
    def get_ticker_news(self, ticker: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """
        Get recent news
        
        MCP call: massive:list_ticker_news(ticker=..., limit=...)
        """
        if self.use_mcp:
            raise NotImplementedError("MCP server communication not yet implemented")
        
        return []
    
    def _polygon_request(self, path: str, params: dict = None) -> dict:
        """Make rate-limited Polygon REST API request."""
        if not HAS_REQUESTS or not self.api_key:
            return {}
        params = dict(params or {})
        params["apiKey"] = self.api_key
        now = time.time()
        if now - self._last_polygon_call < 0.2:
            time.sleep(0.2 - (now - self._last_polygon_call))
        self._last_polygon_call = time.time()
        try:
            r = requests.get(f"{self.POLYGON_BASE}{path}", params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Polygon API error: {e}")
            return {}

    def _polygon_list_tickers(
        self,
        search: Optional[str],
        ticker_type: Optional[str],
        market: Optional[str],
        active: bool,
        limit: int,
    ) -> List[Dict]:
        """Fetch tickers from Polygon /v3/reference/tickers."""
        params = {
            "search": search or "",
            "market": market or "stocks",
            "active": str(active).lower(),
            "limit": min(limit, 100),
        }
        if ticker_type:
            params["type"] = ticker_type
        data = self._polygon_request("/v3/reference/tickers", params)
        results = data.get("results", [])
        return [
            {
                "ticker": r.get("ticker", ""),
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "market": r.get("market", "stocks"),
                "exchange": r.get("primary_exchange", ""),
                "active": r.get("active", True),
            }
            for r in results if r.get("ticker")
        ]

    def _polygon_get_ticker_details(self, ticker: str) -> Optional[Dict]:
        """Fetch ticker details from Polygon /v3/reference/tickers/{ticker}."""
        data = self._polygon_request(f"/v3/reference/tickers/{ticker.upper()}")
        r = data.get("results")
        if not r:
            return None
        # Results can be a single object or list
        if isinstance(r, list):
            r = r[0] if r else {}
        return {
            "ticker": r.get("ticker", ticker),
            "name": r.get("name", ticker),
            "type": r.get("type", "CS"),
            "market": r.get("market", "stocks"),
            "locale": r.get("locale", "us"),
            "primary_exchange": r.get("primary_exchange", ""),
            "currency_name": r.get("currency_name", "usd"),
            "active": r.get("active", True),
            "description": r.get("description", ""),
            "sic_code": r.get("sic_code"),
            "sic_description": r.get("sic_description", ""),
        }

    def calculate_returns(self, historical_data: List[Dict]) -> Dict:
        """Calculate returns from historical data"""
        if len(historical_data) < 2:
            return {'error': 'Insufficient data'}
        
        first_close = historical_data[0]['close']
        last_close = historical_data[-1]['close']
        
        total_return = (last_close - first_close) / first_close
        
        # Calculate volatility (simplified)
        daily_returns = []
        for i in range(1, len(historical_data)):
            prev_close = historical_data[i-1]['close']
            curr_close = historical_data[i]['close']
            daily_return = (curr_close - prev_close) / prev_close
            daily_returns.append(daily_return)
        
        import statistics
        volatility = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
        
        return {
            'total_return': total_return,
            'annualized_return': total_return * (252 / len(historical_data)),
            'volatility': volatility,
            'sharpe_ratio': (total_return / volatility) if volatility > 0 else 0
        }


# Example usage (requires API key)
if __name__ == "__main__":
    import sys
    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Set POLYGON_API_KEY or MASSIVE_API_KEY to run")
        sys.exit(1)
    client = MassiveAPIClient(use_mcp=False, api_key=api_key)
    
    print("ðŸ” Searching for energy ETFs...")
    tickers = client.list_tickers(search="energy", ticker_type="ETF", limit=5)
    for t in tickers:
        print(f"  {t.get('ticker')}: {t.get('name')}")
