# Autonomous Equity Analyst - Direct API Implementation

## Overview

**NO MCP. NO CLAUDE API. PURE PYTHON.**

This is a completely autonomous equity analyst that:
- ✅ Runs without Claude or Anthropic API
- ✅ Uses yfinance for all financial data (FREE)
- ✅ Stores results in SQLite database
- ✅ Exports to CSV
- ✅ Can run on cron/scheduler for automated analysis

## Installation

```bash
# Install dependencies
pip install yfinance pandas requests

# Or use requirements file
pip install -r requirements_autonomous.txt
```

## Quick Start

```python
from equity_analyst_autonomous import AutonomousEquityAnalyst

# Initialize
analyst = AutonomousEquityAnalyst(db_path="my_analysis.db")

# Define your investment thesis
thesis = {
    'id': 1,
    'name': 'Tech Growth 2026',
    'description': 'Technology stocks with strong growth potential',
    'keywords': ['technology', 'AI', 'cloud', 'growth'],
    'sectors': ['Technology', 'Communication Services']
}

# Run analysis
results = analyst.analyze_thesis(thesis, max_securities=20)

# Export to CSV
analyst.export_results(thesis_id=1, output_file="tech_growth_analysis.csv")
```

## How It Works

### 1. Security Discovery

The system uses intelligent ticker generation based on keywords:

```python
# Example: "small cap growth" → searches IWM, IJR, SCHA, VB, etc.
securities = analyst.search_securities("small cap growth", max_results=20)
```

Built-in ticker mappings for:
- Small/Mid/Large cap
- Technology, Energy, Healthcare, Financials
- Dividend/Income stocks
- Value/Growth strategies
- International/Emerging markets
- Real Estate/REITs

### 2. Data Fetching with yfinance

For each security, fetches:
- Basic info (name, exchange, sector)
- Market data (price, market cap, volume)
- Performance metrics (1-year return, beta)
- Valuation (P/E ratio)
- Income (dividend yield)

```python
import yfinance as yf

# Simple example
stock = yf.Ticker("AAPL")
info = stock.info  # All company data
hist = stock.history(period="1y")  # Price history
```

### 3. Alignment Scoring Algorithm

Scores securities 0-100 based on:

| Criteria | Max Points | How It's Calculated |
|----------|------------|---------------------|
| Sector Match | 30 | Does sector match thesis sectors? |
| Keyword Match | 25 | Keywords in name/description |
| Market Cap Fit | 15 | Matches small/mid/large cap criteria |
| Performance | 15 | Growth/value performance alignment |
| Dividend Yield | 15 | Income-focused thesis alignment |

Example:
```python
score, rationale = analyst.calculate_alignment_score(security, thesis)
# Returns: (85.0, "Sector match: Technology; Keywords matched: AI, cloud; Strong growth: 23.4%")
```

### 4. Database Storage

SQLite schema:

```sql
-- Securities table
CREATE TABLE securities (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    asset_type TEXT,
    market_cap REAL,
    sector TEXT,
    industry TEXT,
    description TEXT,
    exchange TEXT,
    currency TEXT,
    last_updated TIMESTAMP
);

-- Analysis results table
CREATE TABLE thesis_alignments (
    id INTEGER PRIMARY KEY,
    thesis_id INTEGER,
    thesis_name TEXT,
    symbol TEXT,
    alignment_score REAL,
    rationale TEXT,
    current_price REAL,
    market_cap REAL,
    pe_ratio REAL,
    dividend_yield REAL,
    year_performance REAL,
    analysis_date TIMESTAMP
);
```

### 5. CSV Export

Output format:
```csv
Symbol,Thesis,Score,Rationale,Price,Market Cap,P/E Ratio,Div Yield %,YTD %,Date
IWM,Small & Mid-Cap Revival,85.00,"Sector match: Technology; Small-cap fit; Strong growth: 18.5%",$234.56,"$45,000,000,000",18.50,1.25%,18.50%,2026-02-06
```

## Advanced Usage

### Custom Thesis Analysis

```python
# Energy sector thesis
energy_thesis = {
    'id': 2,
    'name': 'Energy Transition 2026',
    'description': 'Clean energy and traditional energy companies benefiting from transition',
    'keywords': ['energy', 'renewable', 'clean', 'solar', 'wind'],
    'sectors': ['Energy', 'Utilities']
}

results = analyst.analyze_thesis(energy_thesis, max_securities=25)
```

### Batch Processing Multiple Theses

```python
theses = [
    {'id': 1, 'name': 'Tech Growth', ...},
    {'id': 2, 'name': 'Value Recovery', ...},
    {'id': 3, 'name': 'Dividend Income', ...}
]

for thesis in theses:
    print(f"\nAnalyzing: {thesis['name']}")
    results = analyst.analyze_thesis(thesis)
    analyst.export_results(thesis['id'], f"thesis_{thesis['id']}_results.csv")
```

### Querying Historical Results

```python
import sqlite3

conn = sqlite3.connect("securities_autonomous.db")
cursor = conn.cursor()

# Get top performers across all theses
cursor.execute("""
    SELECT symbol, thesis_name, alignment_score, rationale
    FROM thesis_alignments
    WHERE alignment_score > 70
    ORDER BY alignment_score DESC
    LIMIT 10
""")

for row in cursor.fetchall():
    print(f"{row[0]}: Score {row[2]}/100 - {row[3]}")
```

## Comparison: MCP vs Direct API

### With MCP (Option 2):
```python
# Python calls Claude API
# Claude calls MCP tools
# MCP calls Yahoo Finance API
# Results flow back through all layers

Python → Claude API ($) → MCP → Yahoo Finance API
```

### Direct API (This Implementation):
```python
# Python calls Yahoo Finance directly
import yfinance as yf
stock = yf.Ticker("AAPL")
data = stock.info  # Done!

Python → Yahoo Finance API (FREE)
```

**Direct API wins:**
- ✅ Faster (no intermediate layers)
- ✅ Free (no API costs)
- ✅ Simpler (pure Python)
- ✅ More reliable (fewer failure points)

## Performance Notes

### Speed
- First run: ~2-3 seconds per ticker (downloads data)
- Subsequent runs: ~0.5-1 second per ticker (cached)
- 20 securities: ~20-40 seconds total

### Rate Limits
yfinance uses Yahoo Finance's public API:
- No official rate limits
- Recommended: 2000 requests/hour to be safe
- For heavy usage: Add delays between requests

```python
import time

for ticker in tickers:
    data = analyst._fetch_security_data(ticker)
    time.sleep(0.5)  # Be nice to Yahoo's servers
```

## Limitations & Solutions

### Limitation 1: Ticker Discovery
**Problem:** Need to know ticker symbols in advance
**Solution:** Built-in heuristic mapping (covers 100+ common ETFs)
**Better Solution:** Use a ticker database like `yfinance.search()` (experimental)

### Limitation 2: No Real-Time Quotes
**Problem:** yfinance data is ~15 min delayed
**Solution:** For real-time, upgrade to paid API (Polygon.io, Alpha Vantage)

### Limitation 3: Limited Fundamental Data
**Problem:** Some metrics not available for all securities
**Solution:** Graceful handling of missing data; use available metrics

## Production Deployment

### Scheduled Analysis

```python
# cron job: Run daily at 6 PM
# 0 18 * * * cd /path/to/analyst && python run_daily_analysis.py

import schedule
import time

def daily_analysis():
    analyst = AutonomousEquityAnalyst()
    # Load theses from config file
    theses = load_theses_from_config()
    for thesis in theses:
        analyst.analyze_thesis(thesis)

schedule.every().day.at("18:00").do(daily_analysis)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Error Handling & Logging

```python
import logging

logging.basicConfig(
    filename='analyst.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    results = analyst.analyze_thesis(thesis)
    logging.info(f"Analysis complete: {len(results)} securities")
except Exception as e:
    logging.error(f"Analysis failed: {e}")
    # Send alert email
```

### Scaling Up

For analyzing 1000+ securities:

```python
from concurrent.futures import ThreadPoolExecutor

def fetch_parallel(tickers):
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(analyst._fetch_security_data, t) 
                  for t in tickers]
        for future in futures:
            results.append(future.result())
    return results
```

## Cost Comparison

| Approach | Monthly Cost | Pros | Cons |
|----------|--------------|------|------|
| **Direct API (yfinance)** | $0 | Free, fast, simple | 15-min delay, limited tickers |
| **MCP + Claude API** | $10-50 | Intelligent search | Costs money, slower, complex |
| **Polygon.io Pro** | $200 | Real-time, comprehensive | Expensive |
| **Alpha Vantage Free** | $0 | Real-time option | 500 calls/day limit |

## Next Steps

1. **Run the demo:**
   ```bash
   python equity_analyst_autonomous.py
   ```

2. **Customize theses:**
   Edit the thesis dictionaries to match your investment strategy

3. **Integrate with your portfolio:**
   Query the database to track which securities match your theses

4. **Automate:**
   Set up scheduled runs to continuously update your analysis

5. **Enhance scoring:**
   Adjust the `calculate_alignment_score()` method for your criteria

## Troubleshooting

**Error: "No module named 'yfinance'"**
```bash
pip install yfinance
```

**Error: "Ticker not found"**
- Check ticker symbol is valid on Yahoo Finance
- Some tickers may have different symbols (e.g., BRK.B vs BRK-B)

**Slow performance:**
- Add caching
- Use parallel fetching (ThreadPoolExecutor)
- Reduce `max_securities` parameter

**Missing data:**
- Not all securities have all metrics
- Code handles None values gracefully
- Check yfinance documentation for available fields

## Support

For issues or questions:
1. Check yfinance documentation: https://pypi.org/project/yfinance/
2. Review the code comments
3. Test with known tickers (AAPL, MSFT, SPY) first

---

**You now have a completely autonomous equity analyst that requires ZERO external services beyond the free Yahoo Finance API.**
