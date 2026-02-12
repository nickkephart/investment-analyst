#!/usr/bin/env python3
"""
Run Equity Analyst on a Thesis
Complete workflow: Discovery → Enrichment → Analysis
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from equity_analyst_agent import discover_tickers_for_thesis, batch_analyze_thesis


def run_thesis_analysis(thesis_number: int):
    """
    Run complete analysis for a thesis
    
    Workflow:
    1. Load thesis from JSON
    2. Generate discovery strategy (MCP calls Claude should make)
    3. WAIT FOR CLAUDE to execute MCP calls and pass results
    4. Run batch analysis with enriched data
    
    Args:
        thesis_number: Which thesis (1-15)
    """
    
    # Load thesis
    theses_file = Path(__file__).parent / 'investment_theses_15_expanded_2026.json'
    with open(theses_file) as f:
        theses = json.load(f)['theses']
    
    if thesis_number < 1 or thesis_number > len(theses):
        raise ValueError(f'Invalid thesis number. Must be 1-{len(theses)}')
    
    thesis = theses[thesis_number - 1]
    thesis['id'] = f'thesis_{thesis_number}'
    
    print("=" * 80)
    print(f"EQUITY ANALYST - THESIS #{thesis_number}")
    print("=" * 80)
    print(f"\nTitle: {thesis['title']}")
    print()
    
    # Generate discovery strategy
    strategy = discover_tickers_for_thesis(thesis)
    
    print("DISCOVERY STRATEGY:")
    print("-" * 80)
    print(f"Web searches: {len(strategy['web_search_queries'])}")
    for q in strategy['web_search_queries']:
        print(f"  - web_search('{q}')")
    
    print(f"\nMassive searches: {len(strategy['massive_searches'])}")
    for s in strategy['massive_searches']:
        params = ', '.join(f"{k}='{v}'" if isinstance(v, str) else f"{k}={v}" 
                          for k, v in s.items())
        print(f"  - massive:list_tickers({params})")
    
    print(f"\nEstimated tickers to discover: {strategy['estimated_tickers']}")
    print()
    
    print("=" * 80)
    print("NEXT STEP: Claude must execute discovery MCP calls")
    print("=" * 80)
    print("\nClaude should:")
    print("1. Execute ALL web_search and massive:list_tickers calls IN PARALLEL")
    print("2. Extract unique ticker symbols from results")
    print("3. For each ticker, execute IN PARALLEL:")
    print("   - massive:get_ticker_details(ticker)")
    print("   - yahoo-finance:get_current_stock_price(symbol)")
    print("   - yahoo-finance:get_historical_stock_prices(symbol, period='1y')")
    print("   - yahoo-finance:get_dividends(symbol)")
    print("4. Call batch_analyze_thesis(thesis_number, mcp_data)")
    print()
    print("This script cannot proceed further without Claude's MCP orchestration.")
    print("=" * 80)
    
    return strategy


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run equity analyst on a thesis')
    parser.add_argument('thesis_number', type=int, help='Thesis number (1-15)')
    
    args = parser.parse_args()
    
    strategy = run_thesis_analysis(args.thesis_number)
