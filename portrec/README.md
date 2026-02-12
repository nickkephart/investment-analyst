# Portfolio Recommendation Service (portrec)

Recommends changes to your retirement portfolio based on investment theses. Uses Yahoo Finance (primary), optional Massive/Polygon, and optional Alpha Vantage.

## Setup

```powershell
cd "c:\Users\nick_\Investment Analyst"
pip install -r requirements.txt
```

## Theses Format

Provide theses as JSON:

```json
{
  "theses": [
    {
      "id": "1",
      "name": "Thesis Title",
      "description": "Description of the investment theme",
      "keywords": ["keyword1", "keyword2"],
      "sectors": ["Technology", "Healthcare"]
    }
  ]
}
```

## Commands

```powershell
# Import theses from JSON
python -m portrec import-theses theses_example.json

# List theses
python -m portrec list-theses

# Select theses for research
python -m portrec select 1
python -m portrec deselect 1
python -m portrec set-priority 1 0

# Run equity research (blocking)
python -m portrec research

# Generate add/remove recommendations
python -m portrec recommend

# Run background worker (async research)
python -m portrec run-background
```

## Config

Edit `config.yaml` to set:

- `portfolio_csv`: Path to Fidelity-style portfolio CSV
- `db_path`, `securities_db_path`: Database paths
- `enable_massive`, `enable_alpha_vantage`: Toggle data sources
- `add_threshold`, `top_n_adds_per_thesis`: Recommendation thresholds

## Data Sources

| Source | Config / Env | Use |
|--------|--------------|-----|
| Yahoo Finance | (always on) | Prices, history, dividends - primary |
| Massive/Polygon | polygon_api_key in config, or POLYGON_API_KEY env | Ticker discovery + details (sector, description) |
| Alpha Vantage | alpha_vantage_api_key in config, or ALPHA_VANTAGE_API_KEY env | Fundamentals (sector, industry) - 25 calls/day free |

Without API keys: Massive returns no tickers; Alpha Vantage is skipped.
