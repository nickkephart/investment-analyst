#!/usr/bin/env python3
"""
Multi-Source Equity Analyst
Uses Yahoo Finance (primary), optional Massive/Polygon, optional Alpha Vantage.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory for existing modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from equity_analyst_autonomous import AutonomousEquityAnalyst


class MultiSourceEquityAnalyst:
    """
    Equity analyst using Yahoo Finance (primary) plus optional Massive and Alpha Vantage.

    Data sources (configurable via env or constructor):
    - yahoo: Always used (yfinance, free)
    - massive: Ticker discovery when POLYGON_API_KEY or MASSIVE_API_KEY set
    - alpha_vantage: Fundamentals when ALPHA_VANTAGE_API_KEY set (25 calls/day free)
    """

    def __init__(
        self,
        db_path: str = "portrec_securities.db",
        enable_massive: bool = None,
        enable_alpha_vantage: bool = None,
        polygon_api_key: str = None,
        alpha_vantage_api_key: str = None,
    ):
        self.analyst = AutonomousEquityAnalyst(db_path=db_path)
        self.db_path = db_path

        polygon_key = (
            polygon_api_key
            or os.environ.get("POLYGON_API_KEY")
            or os.environ.get("MASSIVE_API_KEY")
        )
        av_key = (
            alpha_vantage_api_key
            or os.environ.get("ALPHA_VANTAGE_API_KEY")
        )

        self.enable_massive = enable_massive if enable_massive is not None else True
        self.enable_alpha_vantage = (
            enable_alpha_vantage if enable_alpha_vantage is not None else True
        )

        self._massive_client = None
        self._av_client = None

        if self.enable_massive:
            try:
                from massive_api_client import MassiveAPIClient
                self._massive_client = MassiveAPIClient(use_mcp=False, api_key=polygon_key)
                mode = "Polygon API" if self._massive_client._use_direct_api else "disabled (no API key)"
                print(f"  [OK] Massive/Polygon: {mode}")
            except Exception as e:
                print(f"  [WARN] Massive/Polygon not available: {e}")
                self._massive_client = None

        if self.enable_alpha_vantage and av_key:
            try:
                from alpha_vantage_client import AlphaVantageClient
                self._av_client = AlphaVantageClient(api_key=av_key)
                print(f"  [OK] Alpha Vantage: enabled")
            except Exception as e:
                print(f"  [WARN] Alpha Vantage not available: {e}")
                self._av_client = None
        elif self.enable_alpha_vantage and not av_key:
            print(f"  [WARN] Alpha Vantage: enabled but no API key (set ALPHA_VANTAGE_API_KEY)")

        print(f"  [OK] Yahoo Finance: primary (prices, history, dividends)")

    def _get_discovery_tickers(self, thesis: Dict) -> List[str]:
        """Get ticker list - heuristic + Massive/Polygon when available."""
        keywords = thesis.get("keywords", [])
        search_query = " ".join(keywords[:3]) if keywords else thesis.get("name", "")

        base_tickers = self.analyst._generate_search_tickers(search_query)

        if self._massive_client:
            try:
                for kw in (keywords[:3] or [search_query]):
                    if not kw:
                        continue
                    results = self._massive_client.list_tickers(
                        search=kw, ticker_type="ETF", limit=8
                    )
                    for r in results:
                        t = r.get("ticker") if isinstance(r, dict) else r
                        if t and t not in base_tickers:
                            base_tickers.append(t)
            except Exception as e:
                print(f"  Massive discovery skipped: {e}")

        return list(dict.fromkeys(base_tickers))

    def _enrich_with_massive(self, security: Dict) -> Dict:
        """Enrich security with Massive/Polygon ticker details."""
        if not self._massive_client:
            return security
        symbol = security.get("symbol")
        if not symbol:
            return security
        try:
            details = self._massive_client.get_ticker_details(symbol)
            if details:
                if not security.get("sic_code") and details.get("sic_code"):
                    security["sic_code"] = details.get("sic_code")
                if not security.get("sic_description") and details.get("sic_description"):
                    security["sic_description"] = details.get("sic_description")
                    # Fallback for sector matching when no GICS/asset_class
                    if not security.get("sector"):
                        security["sector"] = details.get("sic_description")
                if not security.get("description") and details.get("description"):
                    security["description"] = details.get("description")
        except Exception:
            pass
        return security

    def _enrich_with_alpha_vantage(self, security: Dict) -> Dict:
        """Optionally enrich security with Alpha Vantage overview."""
        if not self._av_client:
            return security

        symbol = security.get("symbol")
        if not symbol:
            return security

        try:
            overview = self._av_client.get_company_overview(symbol)
            if overview:
                if not security.get("gics_sector") and overview.get("Sector"):
                    security["gics_sector"] = overview.get("Sector")
                    security["sector"] = overview.get("Sector")
                if not security.get("gics_industry") and overview.get("Industry"):
                    security["gics_industry"] = overview.get("Industry")
                    security["industry"] = overview.get("Industry")
                if not security.get("description") and overview.get("Description"):
                    security["description"] = overview.get("Description")
                # Alpha Vantage DividendYield is decimal (0.025 = 2.5%); convert to % if we use it
                if not security.get("dividend_yield") and overview.get("DividendYield") is not None:
                    try:
                        dy = float(overview["DividendYield"])
                        security["dividend_yield"] = dy * 100 if 0 < dy < 0.1 else dy
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass

        return security

    def analyze_thesis(self, thesis: Dict, max_securities: int = 20) -> List[Dict]:
        """
        Analyze an investment thesis and find aligned securities.

        Uses multi-source data: Yahoo (primary), optionally Massive for discovery,
        optionally Alpha Vantage for fundamentals.
        """
        # Ensure thesis has 'name' for compatibility with autonomous analyst
        thesis = dict(thesis)
        if "name" not in thesis and "title" in thesis:
            thesis["name"] = thesis["title"]

        # Get tickers from discovery (heuristic + Massive)
        tickers = self._get_discovery_tickers(thesis)[:max_securities]

        results = []
        for ticker in tickers:
            try:
                security = self.analyst._fetch_security_data(ticker)
                if not security:
                    continue

                # Enrich with Massive/Polygon and Alpha Vantage when available
                security = self._enrich_with_massive(security)
                security = self._enrich_with_alpha_vantage(security)

                self.analyst.save_security(security)
                score, rationale = self.analyst.calculate_alignment_score(security, thesis)
                self.analyst.save_thesis_alignment(
                    thesis_id=thesis.get("id", thesis.get("name", "")),
                    thesis_name=thesis.get("name", thesis.get("title", "")),
                    security=security,
                    alignment_score=score,
                    rationale=rationale,
                )

                results.append({
                    "symbol": security["symbol"],
                    "name": security["name"],
                    "score": score,
                    "rationale": rationale,
                    "current_price": security.get("current_price"),
                    "market_cap": security.get("market_cap"),
                    "pe_ratio": security.get("pe_ratio"),
                    "year_performance": security.get("year_performance"),
                })
            except Exception as e:
                print(f"  Error analyzing {ticker}: {e}")
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def get_thesis_results(self, thesis_id: str, limit: int = 20) -> List[Dict]:
        """Get stored analysis results for a thesis."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, thesis_name, alignment_score, rationale,
                   current_price, market_cap, pe_ratio, dividend_yield,
                   year_performance
            FROM thesis_alignments
            WHERE thesis_id = ?
            ORDER BY alignment_score DESC
            LIMIT ?
        """, (thesis_id, limit))
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "symbol": r[0],
                "thesis_name": r[1],
                "score": r[2],
                "rationale": r[3],
                "current_price": r[4],
                "market_cap": r[5],
                "pe_ratio": r[6],
                "dividend_yield": r[7],
                "year_performance": r[8],
            }
            for r in rows
        ]

    def export_results(self, thesis_id: str, output_file: str):
        """Delegate to autonomous analyst export."""
        self.analyst.export_results(thesis_id=thesis_id, output_file=output_file)
