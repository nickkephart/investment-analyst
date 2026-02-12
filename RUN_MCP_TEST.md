# Standalone MCP Client Test

This script demonstrates **Option 3**: Using Python to connect directly to MCP servers WITHOUT using Claude/Anthropic API.

## What This Proves

- ✅ You CAN connect to MCP servers from pure Python
- ✅ You CAN call MCP tools programmatically  
- ✅ You DO NOT need Claude or Anthropic API
- ✅ This is a completely autonomous Python solution

## Prerequisites

1. **Python 3.10+** installed
2. **uv** package manager installed (for running MCP servers)
3. Network access (to download MCP servers on first run)

## Installation

```bash
# Install the MCP Python SDK
pip install mcp --break-system-packages

# Or if you're using a virtual environment:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install mcp
```

## Running the Test

```bash
# Basic test (Yahoo Finance only - no API key needed)
python test_standalone_mcp.py

# Test with Massive.com (requires API key)
export MASSIVE_API_KEY="your_api_key_here"
python test_standalone_mcp.py
```

## What the Script Does

### Test 1: Yahoo Finance MCP Server

1. Connects to Yahoo Finance MCP server via `uvx mcp-yahoo-finance`
2. Lists all available tools
3. Calls `get_current_stock_price` for AAPL
4. Calls `get_historical_stock_prices` for AAPL (5 days)
5. Parses and displays the results

### Test 2: Massive.com MCP Server (optional)

1. Connects to Massive.com MCP server via `uvx mcp_massive`
2. Lists available tools
3. Calls `get_snapshot_ticker` for AAPL
4. Displays results

## Expected Output

```
████████████████████████████████████████████████████████████
  STANDALONE MCP CLIENT TEST
  No Claude API Required - Pure Python MCP Client
████████████████████████████████████████████████████████████

============================================================
Testing Standalone MCP Client - Yahoo Finance
============================================================

[1] Connecting to Yahoo Finance MCP server...
[2] Creating client session...
[3] Initializing connection...
    Server name: mcp-yahoo-finance
    Server version: 0.1.0

[4] Listing available tools...
    Found 8 tools:
    - get_current_stock_price: Get current stock price
    - get_historical_stock_prices: Get historical prices
    ...

[5] Testing tool call: get_current_stock_price
    Fetching AAPL stock price...
    
    Parsed data:
    Symbol: AAPL
    Price: $234.56
    Currency: USD

[6] Testing tool call: get_historical_stock_prices
    Fetching AAPL 5-day history...
    Historical data: [...]

============================================================
SUCCESS! Standalone MCP client works!
============================================================
```

## How This Relates to Your Equity Analyst

You can use this same pattern to build your equity analyst agent:

```python
# Your equity analyst would look like this:
async def analyze_thesis(thesis: str):
    # Connect to MCP servers
    async with create_mcp_client("yahoo-finance") as yf_client:
        async with create_mcp_client("massive") as massive_client:
            
            # Your logic determines which tools to call
            etfs = await find_etfs_for_thesis(thesis, yf_client)
            
            for etf in etfs:
                price_data = await yf_client.call_tool(
                    "get_current_stock_price",
                    {"symbol": etf}
                )
                
                # Score and store results
                score = calculate_alignment_score(etf, thesis, price_data)
                save_to_database(etf, score, price_data)
```

## Key Differences from Current Approach

**Current (Hybrid):**
- Claude orchestrates MCP tool calls
- Python handles database/scoring
- Claude decides which tools to call

**Option 3 (This Script):**
- Python connects to MCP servers directly
- Python calls tools programmatically
- You write the logic for which tools to call
- No Claude needed

## Performance Notes

- First run is slow (downloads MCP server packages)
- Subsequent runs are fast (packages are cached)
- Each tool call is ~100-500ms depending on the API

## Troubleshooting

**Error: "uvx: command not found"**
```bash
pip install uv
```

**Error: "Could not connect to MCP server"**
- Make sure `uvx` is in your PATH
- Try running `uvx mcp-yahoo-finance` manually to see errors

**Error: Network connection issues**
- The MCP servers need internet access to function
- Yahoo Finance and Massive.com APIs require network connectivity
