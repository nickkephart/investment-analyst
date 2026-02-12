#!/usr/bin/env python3
"""
Yahoo Finance MCP Client Wrapper
Uses Yahoo Finance MCP server tools for stock data
"""

from typing import Dict, Optional, List, Callable
from datetime import datetime, timedelta


class YahooFinanceClient:
    """
    Wrapper for Yahoo Finance MCP server
    
    This client uses the yahoo-finance MCP tools that must be available
    in the environment. The tools are passed in as callable functions.
    
    Features:
    - Current stock prices
    - Historical price data
    - Dividend data
    - Income statements
    
    No API key required
    No rate limits
    """
    
    def __init__(self, mcp_tools: Optional[Dict[str, Callable]] = None):
        """
        Initialize Yahoo Finance MCP client
        
        Args:
            mcp_tools: Dictionary of MCP tool functions:
                - 'get_current_stock_price'
                - 'get_stock_historical_prices'
                - 'get_stock_dividend'
                - 'get_income_statement'
        """
        self.mcp_tools = mcp_tools or {}
        self.available = len(self.mcp_tools) > 0
        
        if self.available:
            print("   âœ“ Yahoo Finance MCP client initialized")
        else:
            print("   âš ï¸  Yahoo Finance MCP tools not available")
    
    def is_available(self) -> bool:
        """Check if Yahoo Finance MCP tools are available"""
        return self.available
    
    def get_current_stock_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current stock price
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            
        Returns:
            {
                'symbol': 'AAPL',
                'price': 276.49,
                'currency': 'USD',
                'timestamp': '2026-02-04 16:00:00'
            }
        """
        if not self.available or 'get_current_stock_price' not in self.mcp_tools:
            return None
        
        try:
            tool = self.mcp_tools['get_current_stock_price']
            result = tool(symbol=symbol)
            
            # MCP returns just the price as a float
            if isinstance(result, (int, float)):
                return {
                    'symbol': symbol,
                    'price': float(result),
                    'currency': 'USD',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            
            return None
            
        except Exception as e:
            print(f"   âš ï¸  Error getting current price for {symbol}: {e}")
            return None
    
    def get_stock_historical_prices(
        self, 
        symbol: str, 
        period: str = '1y',
        interval: str = '1d'
    ) -> Optional[List[Dict]]:
        """
        Get historical stock prices
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            period: Time period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            interval: Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
            
        Returns:
            [
                {
                    'date': '2025-02-04',
                    'open': 275.50,
                    'high': 277.00,
                    'low': 274.00,
                    'close': 276.49,
                    'volume': 50000000
                },
                ...
            ]
        """
        if not self.available or 'get_historical_stock_prices' not in self.mcp_tools:
            return None
        
        try:
            tool = self.mcp_tools['get_historical_stock_prices']
            result = tool(symbol=symbol, period=period, interval=interval)
            
            # Parse the result - format depends on MCP implementation
            # This is a placeholder - actual parsing depends on return format
            if isinstance(result, list):
                return result
            
            return None
            
        except Exception as e:
            print(f"   âš ï¸  Error getting historical prices for {symbol}: {e}")
            return None
    
    def get_stock_dividend(self, symbol: str) -> Optional[Dict]:
        """
        Get dividend information
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            
        Returns:
            {
                'symbol': 'AAPL',
                'dividend_yield': 0.0052,  # 0.52%
                'annual_dividend': 0.96,
                'payout_frequency': 'Quarterly',
                'dividend_count_12m': 4,
                'dividends': [
                    {'date': '2025-11-14', 'dividend': 0.24},
                    {'date': '2025-08-15', 'dividend': 0.24},
                    ...
                ]
            }
        """
        if not self.available or 'get_stock_dividend' not in self.mcp_tools:
            return None
        
        try:
            tool = self.mcp_tools['get_stock_dividend']
            result = tool(symbol=symbol)
            
            # Parse dividend data
            if isinstance(result, dict):
                return result
            
            return None
            
        except Exception as e:
            print(f"   âš ï¸  Error getting dividend data for {symbol}: {e}")
            return None
    
    def get_income_statement(
        self, 
        symbol: str, 
        quarterly: bool = False
    ) -> Optional[Dict]:
        """
        Get income statement
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            quarterly: If True, return quarterly data; if False, return annual
            
        Returns:
            {
                'symbol': 'AAPL',
                'total_revenue': 383285000000,
                'cost_of_revenue': 214137000000,
                'gross_profit': 169148000000,
                'operating_income': 114301000000,
                'net_income': 93736000000,
                'ebitda': 123456000000,
                'period': 'Annual'
            }
        """
        if not self.available or 'get_income_statement' not in self.mcp_tools:
            return None
        
        try:
            tool = self.mcp_tools['get_income_statement']
            result = tool(symbol=symbol, quarterly=quarterly)
            
            # Parse income statement
            if isinstance(result, dict):
                return result
            
            return None
            
        except Exception as e:
            print(f"   âš ï¸  Error getting income statement for {symbol}: {e}")
            return None
    
    def calculate_52_week_high_low(self, symbol: str) -> Optional[Dict]:
        """
        Calculate 52-week high and low from historical data
        
        Args:
            symbol: Stock ticker
            
        Returns:
            {
                'high_52week': 145.20,
                'low_52week': 47.32,
                'current_price': 139.50,
                'pct_from_high': 0.94  # 94% of 52-week range
            }
        """
        if not self.available:
            return None
        
        try:
            # Get 1 year of daily data
            historical = self.get_stock_historical_prices(symbol, period='1y', interval='1d')
            if not historical or len(historical) == 0:
                return None
            
            # Get current price
            current = self.get_current_stock_price(symbol)
            if not current:
                return None
            
            current_price = current['price']
            
            # Find high and low
            high_52week = max(bar['high'] for bar in historical)
            low_52week = min(bar['low'] for bar in historical)
            
            # Calculate position in range
            price_range = high_52week - low_52week
            if price_range > 0:
                pct_from_low = (current_price - low_52week) / price_range
            else:
                pct_from_low = 0.5
            
            return {
                'high_52week': high_52week,
                'low_52week': low_52week,
                'current_price': current_price,
                'pct_from_low': pct_from_low
            }
            
        except Exception as e:
            print(f"   âš ï¸  Error calculating 52-week range for {symbol}: {e}")
            return None
    
    def calculate_moving_averages(self, symbol: str) -> Optional[Dict]:
        """
        Calculate 50-day and 200-day moving averages
        
        Args:
            symbol: Stock ticker
            
        Returns:
            {
                'ma_50': 137.20,
                'ma_200': 115.30,
                'current_price': 139.50,
                'ma_50_above_200': True,
                'pct_diff': 0.19  # 50-day is 19% above 200-day
            }
        """
        if not self.available:
            return None
        
        try:
            # Get 1 year of daily data (more than 200 days)
            historical = self.get_stock_historical_prices(symbol, period='1y', interval='1d')
            if not historical or len(historical) < 200:
                return None
            
            # Get current price
            current = self.get_current_stock_price(symbol)
            if not current:
                return None
            
            # Calculate moving averages
            closes = [bar['close'] for bar in historical]
            
            ma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
            ma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
            
            if not ma_50 or not ma_200:
                return None
            
            pct_diff = (ma_50 - ma_200) / ma_200
            
            return {
                'ma_50': ma_50,
                'ma_200': ma_200,
                'current_price': current['price'],
                'ma_50_above_200': ma_50 > ma_200,
                'pct_diff': pct_diff
            }
            
        except Exception as e:
            print(f"   âš ï¸  Error calculating moving averages for {symbol}: {e}")
            return None


if __name__ == '__main__':
    print("YahooFinanceClient requires MCP tools. Use from caller with actual MCP tool functions.")
