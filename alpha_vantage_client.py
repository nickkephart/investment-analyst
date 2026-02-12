#!/usr/bin/env python3
"""
Alpha Vantage Integration Module
Provides company fundamentals and financial data with proper rate limiting.

Rate Limits:
- Free tier: 25 API calls per day
- 5 calls per minute
"""

import time
import json
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, Optional, List
import requests


class AlphaVantageRateLimiter:
    """
    Rate limiter specifically for Alpha Vantage API
    Free tier: 25 calls/day, 5 calls/minute
    """
    
    def __init__(self, calls_per_minute: int = 5, calls_per_day: int = 25):
        self.calls_per_minute = calls_per_minute
        self.calls_per_day = calls_per_day
        
        # Track calls in last minute
        self.minute_calls = deque()
        
        # Track calls today
        self.daily_calls = []
        self.current_date = datetime.now().date()
    
    def wait_if_needed(self):
        """Wait if rate limits would be exceeded"""
        now = time.time()
        current_date = datetime.now().date()
        
        # Reset daily counter if new day
        if current_date != self.current_date:
            self.daily_calls = []
            self.current_date = current_date
            print(f"   ðŸ“… New day - daily call counter reset")
        
        # Check daily limit
        if len(self.daily_calls) >= self.calls_per_day:
            # Calculate time until midnight
            tomorrow = datetime.combine(current_date, datetime.min.time()) + timedelta(days=1)
            wait_seconds = (tomorrow - datetime.now()).total_seconds()
            hours = int(wait_seconds // 3600)
            minutes = int((wait_seconds % 3600) // 60)
            
            print(f"   âš ï¸  Daily limit reached ({self.calls_per_day} calls)")
            print(f"   â°  Resets in {hours}h {minutes}m")
            raise Exception(f"Alpha Vantage daily limit reached. Resets in {hours}h {minutes}m")
        
        # Clean old calls from minute window
        cutoff = now - 60
        while self.minute_calls and self.minute_calls[0] < cutoff:
            self.minute_calls.popleft()
        
        # Check minute limit
        if len(self.minute_calls) >= self.calls_per_minute:
            # Need to wait
            oldest_call = self.minute_calls[0]
            wait_time = 60 - (now - oldest_call) + 1  # +1 for safety margin
            
            print(f"   â³ Alpha Vantage rate limit: waiting {wait_time:.1f}s before next call...")
            print(f"   ðŸ“Š Usage: {len(self.minute_calls)}/{self.calls_per_minute} calls/min, {len(self.daily_calls)}/{self.calls_per_day} calls/day")
            
            time.sleep(wait_time)
            
            # Clean again after waiting
            cutoff = time.time() - 60
            while self.minute_calls and self.minute_calls[0] < cutoff:
                self.minute_calls.popleft()
        
        # Record this call
        self.minute_calls.append(now)
        self.daily_calls.append(now)
    
    def get_usage_stats(self) -> Dict:
        """Get current usage statistics"""
        now = time.time()
        cutoff = now - 60
        
        # Clean old minute calls
        while self.minute_calls and self.minute_calls[0] < cutoff:
            self.minute_calls.popleft()
        
        return {
            'calls_last_minute': len(self.minute_calls),
            'calls_today': len(self.daily_calls),
            'minute_limit': self.calls_per_minute,
            'daily_limit': self.calls_per_day,
            'minute_remaining': self.calls_per_minute - len(self.minute_calls),
            'daily_remaining': self.calls_per_day - len(self.daily_calls)
        }


class AlphaVantageClient:
    """Client for Alpha Vantage API with rate limiting"""
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self, api_key: str, web_fetch_fn=None):
        """
        Initialize Alpha Vantage client
        
        Args:
            api_key: Alpha Vantage API key
            web_fetch_fn: Optional web_fetch function (for Claude environment)
                         If not provided, will try to use requests library
        """
        self.api_key = api_key
        self.rate_limiter = AlphaVantageRateLimiter()
        self.web_fetch_fn = web_fetch_fn
        
        # Only create session if we're not using web_fetch
        if not self.web_fetch_fn:
            self.session = requests.Session()
    
    def _make_request(self, params: Dict) -> Dict:
        """Make API request with rate limiting"""
        # Add API key to params
        params['apikey'] = self.api_key
        
        # Wait if needed for rate limits
        self.rate_limiter.wait_if_needed()
        
        # Build URL
        from urllib.parse import urlencode
        url = f"{self.BASE_URL}?{urlencode(params)}"
        
        # Make request using web_fetch or requests
        if self.web_fetch_fn:
            # Use web_fetch (Claude environment)
            result = self.web_fetch_fn(url)
            # Parse JSON from result
            if isinstance(result, str):
                data = json.loads(result)
            elif isinstance(result, dict):
                data = result
            else:
                raise Exception(f"Unexpected web_fetch result type: {type(result)}")
        else:
            # Use requests library (standalone Python)
            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        
        # Check for API errors
        if 'Error Message' in data:
            raise Exception(f"Alpha Vantage API Error: {data['Error Message']}")
        
        if 'Note' in data:
            # Rate limit message
            raise Exception(f"Alpha Vantage Rate Limit: {data['Note']}")
        
        return data
    
    def get_company_overview(self, symbol: str) -> Optional[Dict]:
        """
        Get company overview including business description, sector, industry, etc.
        
        Returns dict with fields:
        - Symbol, Name, Description, Exchange, Sector, Industry
        - MarketCapitalization, PERatio, DividendYield
        - 52WeekHigh, 52WeekLow
        - And many more...
        """
        print(f"   ðŸ“Š Alpha Vantage: Getting company overview for {symbol}")
        
        try:
            params = {
                'function': 'OVERVIEW',
                'symbol': symbol
            }
            
            data = self._make_request(params)
            
            # Check if we got data
            if not data or 'Symbol' not in data:
                print(f"   âš ï¸  No overview data found for {symbol}")
                return None
            
            return data
            
        except Exception as e:
            print(f"   âŒ Error getting overview for {symbol}: {e}")
            return None
    
    def get_income_statement(self, symbol: str, quarterly: bool = False) -> Optional[Dict]:
        """
        Get income statement (annual or quarterly)
        
        Returns dict with:
        - annualReports or quarterlyReports (list of reports)
        - Each report has: fiscalDateEnding, totalRevenue, costOfRevenue, 
          grossProfit, operatingIncome, netIncome, etc.
        """
        print(f"   ðŸ“Š Alpha Vantage: Getting income statement for {symbol}")
        
        try:
            params = {
                'function': 'INCOME_STATEMENT',
                'symbol': symbol
            }
            
            data = self._make_request(params)
            
            # Check if we got data
            report_key = 'quarterlyReports' if quarterly else 'annualReports'
            if not data or report_key not in data:
                print(f"   âš ï¸  No income statement data found for {symbol}")
                return None
            
            return data
            
        except Exception as e:
            print(f"   âŒ Error getting income statement for {symbol}: {e}")
            return None
    
    def get_balance_sheet(self, symbol: str, quarterly: bool = False) -> Optional[Dict]:
        """Get balance sheet (annual or quarterly)"""
        print(f"   ðŸ“Š Alpha Vantage: Getting balance sheet for {symbol}")
        
        try:
            params = {
                'function': 'BALANCE_SHEET',
                'symbol': symbol
            }
            
            data = self._make_request(params)
            
            report_key = 'quarterlyReports' if quarterly else 'annualReports'
            if not data or report_key not in data:
                print(f"   âš ï¸  No balance sheet data found for {symbol}")
                return None
            
            return data
            
        except Exception as e:
            print(f"   âŒ Error getting balance sheet for {symbol}: {e}")
            return None
    
    def get_cash_flow(self, symbol: str, quarterly: bool = False) -> Optional[Dict]:
        """Get cash flow statement (annual or quarterly)"""
        print(f"   ðŸ“Š Alpha Vantage: Getting cash flow for {symbol}")
        
        try:
            params = {
                'function': 'CASH_FLOW',
                'symbol': symbol
            }
            
            data = self._make_request(params)
            
            report_key = 'quarterlyReports' if quarterly else 'annualReports'
            if not data or report_key not in data:
                print(f"   âš ï¸  No cash flow data found for {symbol}")
                return None
            
            return data
            
        except Exception as e:
            print(f"   âŒ Error getting cash flow for {symbol}: {e}")
            return None
    
    def get_earnings(self, symbol: str) -> Optional[Dict]:
        """
        Get earnings data (annual and quarterly)
        
        Returns:
        - annualEarnings: List of {fiscalDateEnding, reportedEPS}
        - quarterlyEarnings: List of same
        """
        print(f"   ðŸ“Š Alpha Vantage: Getting earnings for {symbol}")
        
        try:
            params = {
                'function': 'EARNINGS',
                'symbol': symbol
            }
            
            data = self._make_request(params)
            
            if not data or 'annualEarnings' not in data:
                print(f"   âš ï¸  No earnings data found for {symbol}")
                return None
            
            return data
            
        except Exception as e:
            print(f"   âŒ Error getting earnings for {symbol}: {e}")
            return None
    
    def get_usage_stats(self) -> Dict:
        """Get current API usage statistics"""
        return self.rate_limiter.get_usage_stats()


# Test function
def test_alpha_vantage():
    """Test Alpha Vantage integration"""
    import os
    
    # Use API key from environment or parameter
    api_key = "IBOQYCMYZYBISLL5"
    
    print("=" * 80)
    print("TESTING ALPHA VANTAGE INTEGRATION")
    print("=" * 80)
    
    client = AlphaVantageClient(api_key)
    
    # Test with NVDA
    print("\n1. Testing Company Overview (NVDA)")
    print("-" * 80)
    overview = client.get_company_overview("NVDA")
    
    if overview:
        print(f"\nSymbol: {overview.get('Symbol')}")
        print(f"Name: {overview.get('Name')}")
        print(f"Sector: {overview.get('Sector')}")
        print(f"Industry: {overview.get('Industry')}")
        print(f"Market Cap: ${float(overview.get('MarketCapitalization', 0))/1e9:.1f}B")
        print(f"\nDescription (first 200 chars):")
        print(overview.get('Description', 'N/A')[:200] + "...")
    
    # Test with MSFT
    print("\n\n2. Testing Company Overview (MSFT)")
    print("-" * 80)
    overview2 = client.get_company_overview("MSFT")
    
    if overview2:
        print(f"\nSymbol: {overview2.get('Symbol')}")
        print(f"Name: {overview2.get('Name')}")
        print(f"Sector: {overview2.get('Sector')}")
        print(f"Description (first 200 chars):")
        print(overview2.get('Description', 'N/A')[:200] + "...")
    
    # Show usage stats
    print("\n\n3. API Usage Statistics")
    print("-" * 80)
    stats = client.get_usage_stats()
    print(f"Calls in last minute: {stats['calls_last_minute']}/{stats['minute_limit']}")
    print(f"Calls today: {stats['calls_today']}/{stats['daily_limit']}")
    print(f"Remaining today: {stats['daily_remaining']}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_alpha_vantage()
