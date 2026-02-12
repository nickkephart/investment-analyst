# ETF Holdings - Data Sources & Schema

## Holdings Count by Source

| Source | Holdings per ETF | Notes |
|--------|------------------|-------|
| **Yahoo Finance (yfinance)** | **10** | Fixed; top 10 only |
| **Alpha Vantage** | ~10 (likely) | ETF_PROFILE: exact count not documented |
| **Polygon ETF Global** | 100 default, up to 5,000 | Partnership tier; not in standard Polygon |
| **ETFDB** | Varies | Scraping; paginated per ETF page |
| **yahooquery** | ~10 | Same underlying Yahoo data |

**Conclusion:** Sources differ. Yahoo gives exactly 10. Polygon ETF Global offers the most when available.

## Schema

### etf_holdings

| Column | Type | Description |
|--------|------|-------------|
| etf_symbol | TEXT | FK -> securities(symbol) |
| constituent_symbol | TEXT | FK -> securities(symbol) |
| holding_percent | REAL | Allocation as percentage (e.g. 7.83) |
| holding_rank | INTEGER | 1 = largest holding |
| source | TEXT | 'yahoo', 'alpha_vantage', etc. |
| last_updated | TIMESTAMP | When data was fetched |

Primary key: (etf_symbol, constituent_symbol)

### Constituent Insertion

When saving holdings, if a constituent symbol is not in `securities`, a minimal row is inserted:
- symbol, name (from holding)
- asset_type left NULL (we don't have type info from holdings; Yahoo/Alpha Vantage will set it when the constituent is fetched)

## Usage

```python
from equity_analyst_autonomous import AutonomousEquityAnalyst

analyst = AutonomousEquityAnalyst(db_path="portrec_securities.db")
holdings = analyst.fetch_etf_holdings("SPY")  # Returns list of dicts
if holdings:
    analyst.save_etf_holdings("SPY", holdings, source="yahoo")
```
