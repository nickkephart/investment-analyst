#!/usr/bin/env python3
"""
Performance Data Fetcher
Uses web_search to gather price performance metrics for securities
"""

import re
from typing import Dict, Optional


class PerformanceDataFetcher:
    """Fetch historical performance data via web search"""
    
    def __init__(self, web_search_fn=None):
        """
        Initialize fetcher
        
        Args:
            web_search_fn: Web search function (from MCP or other)
        """
        self.web_search = web_search_fn
    
    def fetch_performance_metrics(self, ticker: str) -> Dict:
        """
        Fetch performance metrics for a security
        
        Returns dict with:
        - current_price
        - week_52_high
        - week_52_low
        - pct_from_52w_high
        - pct_from_52w_low
        - return_1y
        - return_3m (if available)
        - return_1m (if available)
        - return_ytd (if available)
        - dividend_yield
        - market_cap
        - pe_ratio
        - avg_volume
        """
        
        if not self.web_search:
            return {}
        
        print(f"      ðŸ“ˆ Fetching performance data for {ticker}...")
        
        try:
            # Search for stock price and performance data
            query = f"{ticker} stock price 52 week high low return performance"
            results = self.web_search(query)
            
            # Parse search results
            metrics = self._parse_search_results(results, ticker)
            
            return metrics
            
        except Exception as e:
            print(f"      âš ï¸  Error fetching performance data: {e}")
            return {}
    
    def _parse_search_results(self, results, ticker: str) -> Dict:
        """Parse search results to extract metrics"""
        
        metrics = {}
        
        # Combine all result text
        full_text = ""
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict):
                    full_text += result.get('content', '') + " "
                    full_text += result.get('title', '') + " "
        
        # Extract 52-week high/low
        high_match = re.search(r'52[- ]?week high[^\d]*(\d+\.?\d*)', full_text, re.IGNORECASE)
        low_match = re.search(r'52[- ]?week low[^\d]*(\d+\.?\d*)', full_text, re.IGNORECASE)
        
        if high_match:
            metrics['week_52_high'] = float(high_match.group(1))
        if low_match:
            metrics['week_52_low'] = float(low_match.group(1))
        
        # Extract current price
        price_match = re.search(r'(?:current price|trading at|stock price)[^\d]*\$?(\d+\.?\d*)', full_text, re.IGNORECASE)
        if price_match:
            metrics['current_price'] = float(price_match.group(1))
        
        # Extract 1-year return
        return_match = re.search(r'(?:1[- ]?year|annual|52[- ]?week).*?return[^\d\-]*([+\-]?\d+\.?\d*)%', full_text, re.IGNORECASE)
        if return_match:
            metrics['return_1y'] = float(return_match.group(1))
        
        # Extract market cap
        mcap_match = re.search(r'market cap[^\d]*(\d+\.?\d*)\s*([TBM])', full_text, re.IGNORECASE)
        if mcap_match:
            value = float(mcap_match.group(1))
            unit = mcap_match.group(2).upper()
            if unit == 'T':
                metrics['market_cap'] = f"{value}T"
            elif unit == 'B':
                metrics['market_cap'] = f"{value}B"
            elif unit == 'M':
                metrics['market_cap'] = f"{value}M"
        
        # Extract P/E ratio
        pe_match = re.search(r'p/?e ratio[^\d]*(\d+\.?\d*)', full_text, re.IGNORECASE)
        if pe_match:
            metrics['pe_ratio'] = float(pe_match.group(1))
        
        # Extract dividend yield
        div_match = re.search(r'dividend yield[^\d]*(\d+\.?\d*)%', full_text, re.IGNORECASE)
        if div_match:
            metrics['dividend_yield'] = float(div_match.group(1))
        
        # Calculate percentage from 52-week high/low
        if 'current_price' in metrics and 'week_52_high' in metrics:
            metrics['pct_from_52w_high'] = round(
                ((metrics['current_price'] - metrics['week_52_high']) / metrics['week_52_high']) * 100, 
                1
            )
        
        if 'current_price' in metrics and 'week_52_low' in metrics:
            metrics['pct_from_52w_low'] = round(
                ((metrics['current_price'] - metrics['week_52_low']) / metrics['week_52_low']) * 100,
                1
            )
        
        return metrics


if __name__ == '__main__':
    print("PerformanceDataFetcher requires a real web_search_fn. Use from caller with actual web search.")
