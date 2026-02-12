# Investment Analyst

Autonomous equity analyst using direct APIs. No MCP, no Claude API—pure Python with yfinance and SQLite.

## Quick Start

```bash
pip install -r requirements.txt
python equity_analyst_autonomous.py
```

## What It Does

- Analyzes investment theses against securities
- Uses Yahoo Finance (yfinance) for prices, fundamentals, ETF holdings
- Stores results in SQLite (securities, thesis alignments, ETF holdings)
- Exports to CSV
- Can run on cron/scheduler for automated analysis

**Cost:** $0/month

## Installation

```bash
pip install yfinance pandas requests
# Or:
pip install -r requirements.txt
```

## Usage

```python
from equity_analyst_autonomous import AutonomousEquityAnalyst

analyst = AutonomousEquityAnalyst(db_path="my_analysis.db")

thesis = {
    'id': 1,
    'name': 'Tech Growth 2026',
    'description': 'Technology stocks with strong growth potential',
    'keywords': ['technology', 'AI', 'cloud', 'growth'],
    'sectors': ['Technology', 'Communication Services']
}

results = analyst.analyze_thesis(thesis, max_securities=20)
analyst.export_results(thesis_id=1, output_file="tech_growth_analysis.csv")
```

## How It Works

### 1. Security Discovery

Uses ticker generation based on keywords (e.g. "small cap growth" → IWM, IJR, SCHA, VB). Built-in mappings for small/mid/large cap, sectors, dividend/income, value/growth, international, REITs.

### 2. Data Fetching

For each security, fetches via yfinance:
- Basic info (name, exchange, sector)
- Market data (price, market cap, volume)
- Performance (1-year return, beta)
- Valuation (P/E ratio)
- Income (dividend yield)

### 3. Alignment Scoring (0–100)

| Criteria      | Max Points | How It's Calculated                    |
|---------------|------------|----------------------------------------|
| Sector Match  | 30         | Sector matches thesis sectors          |
| Keyword Match | 25         | Keywords in name/description           |
| Market Cap Fit| 15         | Matches small/mid/large cap criteria   |
| Performance   | 15         | Growth/value performance alignment     |
| Dividend Yield| 15         | Income-focused thesis alignment         |

### 4. Database

SQLite tables: `securities`, `thesis_alignments`, `etf_holdings`. See `equity_analyst_autonomous.py` for schema.

## Project Structure

| Path | Purpose |
|------|---------|
| `equity_analyst_autonomous.py` | Main analyst (yfinance, SQLite) |
| `portrec/` | Portfolio recommender with multi-source analyst |
| `massive_api_client.py` | Polygon/Massive API (optional) |
| `alpha_vantage_client.py` | Alpha Vantage fundamentals (optional) |
| `etfdb_scraper.py` | ETFDB screener for securities |
| `backfill_etf_full.py` | Full ETF + constituent backfill |
| `backfill_etf_sample.py` | Sample backfill (first 10 ETFs) |
| `check_backfill_status.py` | Constituent enrichment status |

## Data Sources

- **Yahoo Finance** (yfinance) – Primary: prices, fundamentals, ETF holdings
- **ETFDB** – ETF listing scraper for securities discovery
- **Massive/Polygon** – Optional ticker discovery (POLYGON_API_KEY)
- **Alpha Vantage** – Optional fundamentals (ALPHA_VANTAGE_API_KEY, 25 calls/day free)

## Quick Commands

```bash
# Run autonomous analyst
python equity_analyst_autonomous.py

# Run portfolio recommender
python -m portrec

# Backfill ETFs (constituents only)
python backfill_etf_full.py --constituents-only --remaining-only

# Check backfill status
python check_backfill_status.py
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and set paths and API keys. Database paths default to `portrec_securities.db` and `portrec.db`.

## Advanced Usage

### Batch Processing Multiple Theses

```python
theses = [
    {'id': 1, 'name': 'Tech Growth', 'keywords': ['technology'], 'sectors': ['Technology']},
    {'id': 2, 'name': 'Value Recovery', 'keywords': ['value'], 'sectors': ['Financial Services']},
]

for thesis in theses:
    analyst.analyze_thesis(thesis)
    analyst.export_results(thesis['id'], f"thesis_{thesis['id']}_results.csv")
```

### ETF Holdings

ETF top holdings are stored in `etf_holdings`. Yahoo provides 10 holdings per ETF (Alpha Vantage ~10; Polygon ETF Global up to 5,000).

**Schema:**

| Column | Type | Description |
|--------|------|-------------|
| etf_symbol | TEXT | FK -> securities(symbol) |
| constituent_symbol | TEXT | FK -> securities(symbol) |
| holding_percent | REAL | Allocation as % (e.g. 7.83) |
| holding_rank | INTEGER | 1 = largest holding |
| source | TEXT | 'yahoo', 'alpha_vantage', etc. |
| last_updated | TIMESTAMP | When fetched |

Primary key: (etf_symbol, constituent_symbol). Constituents missing from `securities` are inserted with symbol and name only.

**Usage:**

```python
holdings = analyst.fetch_etf_holdings("SPY")  # Returns list of dicts
if holdings:
    analyst.save_etf_holdings("SPY", holdings, source="yahoo")
```

## Production & Limitations

**Speed:** ~2–3 seconds per ticker (first run); ~0.5–1 s with cache.

**Rate limits:** yfinance has no official limit; ~2000 requests/hour recommended. Add delays for heavy usage.

**Discovery:** Built-in heuristic covers 100+ common ETFs. For broader coverage, use ETFDB scraper or Polygon.

**Data delay:** yfinance is ~15 min delayed. For real-time, use Polygon or Alpha Vantage.

## Troubleshooting

**"No module named 'yfinance'"** → `pip install yfinance`

**"Ticker not found"** → Check symbol on Yahoo Finance (e.g. BRK-B vs BRK.B)

**Slow** → Reduce `max_securities`; add caching; use parallel fetch (ThreadPoolExecutor)

**Missing data** → Not all securities have all metrics; code handles None gracefully
