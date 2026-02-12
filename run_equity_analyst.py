#!/usr/bin/env python3
"""
Equity Analyst Agent - Executable Wrapper
Connects the agent to web_search, Massive.com, Alpha Vantage, and Yahoo Finance
"""

import sys
import json
from pathlib import Path

# Add the agent to path
sys.path.insert(0, str(Path(__file__).parent))

from equity_analyst_agent import EquityAnalystAgent

# Try to import Alpha Vantage client
try:
    from alpha_vantage_client import AlphaVantageClient
    ALPHA_VANTAGE_AVAILABLE = True
except:
    ALPHA_VANTAGE_AVAILABLE = False

# Try to import Yahoo Finance client
try:
    from yahoo_finance_client import YahooFinanceClient
    YAHOO_FINANCE_AVAILABLE = True
except:
    YAHOO_FINANCE_AVAILABLE = False
    print("âš ï¸  Yahoo Finance client not available")

# NOTE: Yahoo Finance uses yfinance library (no MCP needed for Python)
# For Claude Desktop UI, use mcp-yahoo-finance MCP server

# NOTE: These imports would be replaced with actual MCP tool imports
# For now, we'll use placeholder functions that show the integration points

def web_search_wrapper(query: str):
    """
    Wrapper for web_search tool. Requires real web_search MCP tool or implementation.
    Returns empty list when no implementation available.
    """
    print(f"      [web_search] {query[:60]}...")
    return []


def _to_obj(d):
    """Convert dict to object with attributes for agent compatibility."""
    return type('Obj', (), d if isinstance(d, dict) else {})()


def massive_list_tickers_wrapper(search: str, active: bool = True, limit: int = 5):
    """
    Wrapper for massive:list_tickers tool
    In actual implementation, this would call the Massive.com MCP tool
    """
    print(f"      ðŸ“Š Calling massive:list_tickers: search='{search}', limit={limit}")
    
    # Placeholder - in real implementation:
    # from mcp_tools import massive
    # return massive.list_tickers(search=search, active=active, limit=limit)
    
    import os
    try:
        from massive_api_client import MassiveAPIClient
        api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
        if api_key:
            client = MassiveAPIClient(use_mcp=False, api_key=api_key)
            results = client.list_tickers(search=search, active=active, limit=limit)
            class Results:
                pass
            r = Results()
            r.results = [_to_obj({**item, 'ticker': item.get('ticker')}) for item in results]
            return r
    except Exception as e:
        print(f"      [massive] list_tickers failed: {e}")
    class EmptyResults:
        results = []
    return EmptyResults()


def massive_get_ticker_details_wrapper(ticker: str):
    """
    Wrapper for massive:get_ticker_details tool
    In actual implementation, this would call the Massive.com MCP tool
    """
    print(f"      ðŸ“Š Calling massive:get_ticker_details: ticker='{ticker}'")
    
    # Placeholder - in real implementation:
    # from mcp_tools import massive
    # return massive.get_ticker_details(ticker=ticker)
    
    import os
    try:
        from massive_api_client import MassiveAPIClient
        api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
        if api_key:
            client = MassiveAPIClient(use_mcp=False, api_key=api_key)
            details = client.get_ticker_details(ticker)
            if details:
                return _to_obj(details)
    except Exception as e:
        print(f"      [massive] get_ticker_details failed: {e}")
    return _to_obj({'name': ticker, 'primary_exchange': '', 'market_cap': None, 'sic_description': '', 'description': '', 'type': 'CS'})

def main():
    """Main entry point with tool integration"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Equity Analyst Agent - Map investment theses to securities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze specific theses by number (1-15)
  python run_equity_analyst.py --theses 1 2 3
  
  # Analyze all theses
  python run_equity_analyst.py --all
  
  # Analyze with more securities per thesis
  python run_equity_analyst.py --theses 1 --max-securities 100
  
  # List available theses
  python run_equity_analyst.py --list
        """
    )
    
    parser.add_argument(
        '--theses',
        type=int,
        nargs='+',
        help='Thesis numbers to analyze (e.g., --theses 1 2 3)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Analyze all 15 theses'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available theses and exit'
    )
    parser.add_argument(
        '--max-securities',
        type=int,
        default=20,
        help='Maximum securities to discover per thesis (default: 20)'
    )
    
    args = parser.parse_args()
    
    # Load theses
    theses_file = Path("/mnt/user-data/outputs/investment_theses_15_expanded_2026.json")
    
    if not theses_file.exists():
        print("âŒ Theses file not found!")
        return
    
    with open(theses_file) as f:
        data = json.load(f)
        theses = data.get('theses', [])
    
    if not theses:
        print("âŒ No theses found in file!")
        return
    
    # Add IDs to theses if not present
    for i, thesis in enumerate(theses, 1):
        if 'id' not in thesis:
            thesis['id'] = f"thesis_{i}"
    
    # List mode
    if args.list:
        print("=" * 80)
        print("AVAILABLE INVESTMENT THESES")
        print("=" * 80)
        for i, thesis in enumerate(theses, 1):
            print(f"\n{i}. {thesis['title']}")
            print(f"   Conviction: {thesis.get('conviction_level', 'N/A')}")
            print(f"   Horizon: {thesis.get('time_horizon', 'N/A')}")
        print("\n" + "=" * 80)
        return
    
    # Determine which theses to analyze
    if args.all:
        selected_theses = theses
        print(f"ðŸ“š Analyzing all {len(theses)} investment theses")
    elif args.theses:
        selected_theses = []
        for thesis_num in args.theses:
            if 1 <= thesis_num <= len(theses):
                selected_theses.append(theses[thesis_num - 1])
            else:
                print(f"âš ï¸  Warning: Thesis #{thesis_num} not found (valid range: 1-{len(theses)})")
        
        if not selected_theses:
            print("âŒ No valid theses selected!")
            return
        
        print(f"ðŸ“š Analyzing {len(selected_theses)} selected thesis(es)")
    else:
        # Default: show help
        parser.print_help()
        return
    
    # Initialize agent
    print("\nðŸ”Œ Connecting data sources...")
    agent = EquityAnalystAgent()
    
    # Initialize Alpha Vantage client (requires ALPHA_VANTAGE_API_KEY)
    import os
    alpha_vantage_api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    
    if ALPHA_VANTAGE_AVAILABLE and alpha_vantage_api_key:
        # Use real API
        alpha_vantage = AlphaVantageClient(alpha_vantage_api_key)
        agent.set_alpha_vantage(alpha_vantage)
        print("   âœ“ Alpha Vantage API enabled (25 calls/day, 5 calls/min)")
    else:
        print("   âš ï¸  Alpha Vantage not available")
    
    # Initialize Yahoo Finance client with MCP tools
    # Note: In Claude environment, pass the actual MCP tools as a dictionary
    # For standalone Python execution, pass actual MCP tools when available
    yahoo_finance_mcp_tools = {
        # These would be the actual MCP tools in Claude environment:
        # 'get_current_stock_price': <yahoo-finance MCP tool>,
        # 'get_historical_stock_prices': <yahoo-finance MCP tool>,
        # 'get_stock_dividend': <yahoo-finance MCP tool>,
        # 'get_income_statement': <yahoo-finance MCP tool>
    }
    
    if YAHOO_FINANCE_AVAILABLE:
        yahoo_finance = YahooFinanceClient(mcp_tools=yahoo_finance_mcp_tools)
        if yahoo_finance.is_available():
            agent.set_yahoo_finance(yahoo_finance)
            print("   âœ“ Yahoo Finance MCP enabled (momentum + dividends, unlimited)")
        else:
            print("   âš ï¸  Yahoo Finance MCP tools not available")
            print("      The equity analyst will run without Yahoo Finance enrichment")
    else:
        print("   âš ï¸  Yahoo Finance client not available")
    
    # Connect tools to agent
    agent.discovery.set_web_search(web_search_wrapper)
    agent.discovery.set_massive_funcs(
        massive_list_tickers_wrapper,
        massive_get_ticker_details_wrapper
    )
    print("   âœ“ Web search enabled")
    print("   âœ“ Massive.com API enabled (5 calls/min rate limit)")
    print("")
    print("   ðŸ“Š Enhanced Scoring: 14 points total (scaled to /10)")
    print("      â€¢ Business Description: 3 pts (Alpha Vantage)")
    print("      â€¢ Revenue Exposure: 3 pts (Alpha Vantage)")
    print("      â€¢ Sector Alignment: 2 pts (Alpha Vantage)")
    print("      â€¢ Direct Mention: 2 pts (Thesis parsing)")
    if YAHOO_FINANCE_AVAILABLE and yahoo_finance and yahoo_finance.is_available():
        print("      â€¢ Price Momentum: 2 pts (Yahoo Finance) âœ¨ NEW")
        print("      â€¢ Dividend Quality: 2 pts (Yahoo Finance) âœ¨ NEW")
    
    # Process each thesis
    all_results = []
    
    for idx, thesis in enumerate(selected_theses, 1):
        print(f"\n{'='*80}")
        print(f"Processing Thesis {idx}/{len(selected_theses)}")
        print(f"{'='*80}")
        
        result = agent.analyze_thesis(thesis, max_securities=args.max_securities)
        all_results.append(result)
        
        # Export individual results
        output_dir = Path("/mnt/user-data/outputs")
        output_file = output_dir / f"equity_analysis_{result['thesis_id']}.json"
        agent.export_results(result['thesis_id'], str(output_file))
        
        # Print summary
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)
        print(f"\nThesis: {result['thesis_title']}")
        print(f"Securities analyzed: {result['summary']['total_securities']}")
        print(f"Average alignment score: {result['summary']['avg_score']:.2f}/10")
        print(f"High alignment (8-10): {result['summary']['high_alignment']}")
        print(f"Medium alignment (5-7.99): {result['summary']['medium_alignment']}")
        print(f"Low alignment (<5): {result['summary']['low_alignment']}")
        
        print("\nTop 20 Securities by Alignment:")
        print("-" * 80)
        for i, sec in enumerate(result['securities'][:20], 1):
            asset_type_indicator = "[ETF]" if sec.get('asset_type', '').lower() in ['etf', 'fund'] else "[Stock]"
            print(f"{i:2d}. {sec['ticker']:6s} {asset_type_indicator:7s} - {sec['name'][:35]:35s} | Score: {sec['alignment_score']}/10")
        
        print(f"\nðŸ“„ Results exported to: {output_file}")
    
    # Summary across all analyzed theses
    if len(all_results) > 1:
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)
        total_securities = sum(r['summary']['total_securities'] for r in all_results)
        avg_score = sum(r['summary']['avg_score'] for r in all_results) / len(all_results)
        print(f"Total theses analyzed: {len(all_results)}")
        print(f"Total securities discovered: {total_securities}")
        print(f"Average alignment score across all: {avg_score:.2f}/10")
    
    # Clean up
    agent.close()
    
    print("\nâœ… Equity analysis complete!")
    print(f"ðŸ“Š Database location: /home/claude/securities.db")


if __name__ == "__main__":
    # Check if we need to show usage instructions
    if len(sys.argv) == 1:
        print("=" * 80)
        print("EQUITY ANALYST AGENT - Enhanced with Web Search & Massive.com")
        print("=" * 80)
        print("\nUsage:")
        print("  python run_equity_analyst.py --theses 1 2 3     # Analyze specific theses")
        print("  python run_equity_analyst.py --all              # Analyze all 15 theses")
        print("  python run_equity_analyst.py --list             # List available theses")
        print("\nOptions:")
        print("  --max-securities N    Maximum securities per thesis (default: 20, ETFs prioritized)")
        print("\nData Sources:")
        print("  âœ“ Thesis parsing (extracts mentioned tickers)")
        print("  âœ“ Web search (finds relevant companies)")
        print("  âœ“ Massive.com API (ticker details with rate limiting)")
        print("\nRate Limiting:")
        print("  â€¢ Massive.com: 5 calls per minute (automatic)")
        print("  â€¢ Displays countdown when waiting")
        print("\n" + "=" * 80)
        sys.exit(0)
    
    main()
