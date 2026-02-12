# Data Formatting & Consistency Analysis

## Securities Table Columns

| Column | Yahoo | Massive/Polygon | Alpha Vantage | ETFDB | Issues? |
|--------|-------|-----------------|---------------|-------|---------|
| symbol | uppercase | ticker | Symbol | symbol | OK |
| name | longName/shortName | name | Name | name | OK |
| asset_type | quoteType | type | - | ETF | OK |
| market_cap | marketCap (dollars) | - | MarketCapitalization (dollars) | assets (millions) | **FIXED** - normalized to dollars |
| sector | sector | sic_description | Sector | asset_class | **Different taxonomies** (GICS vs SIC) |
| industry | industry | - | Industry | - | OK |
| description | longBusinessSummary | description | Description | - | OK |
| exchange | exchange | primary_exchange | Exchange | - | **Case** (PCX vs pcx) |
| currency | currency | currency_name | - | USD | **Case** (usd vs USD) |
| current_price | currentPrice | - | - | - | OK |
| pe_ratio | trailingPE | - | PERatio | - | OK |
| dividend_yield | dividendYield | - | DividendYield | - | **Units differ**: Yahoo=%, AV=decimal |
| year_performance | calculated | - | - | ytd | OK (both %) |
| fifty_two_week_high | fiftyTwoWeekHigh | - | 52WeekHigh | - | OK |
| fifty_two_week_low | fiftyTwoWeekLow | - | 52WeekLow | - | OK |
| beta | beta | - | Beta | - | OK |
| volume | volume | - | - | - | OK |
| avg_volume | averageVolume | - | - | average_volume | OK |
| expense_ratio | netExpenseRatio | - | - | - | OK (Yahoo only) |

## Issues Requiring Cleanup

### 1. dividend_yield - UNIT INCONSISTENCY
- **Yahoo**: Percentage points (1.05 = 1.05%)
- **Alpha Vantage**: Decimal (0.025 = 2.5%)
- **Standard**: Store as percentage points (matches Yahoo, alignment logic uses `> 0.02`)
- **Action**: When enriching from Alpha Vantage, multiply DividendYield by 100 if we add it

### 2. currency - CASE
- **Massive**: currency_name = "usd" (lowercase)
- **Yahoo**: "USD" (uppercase)
- **Action**: Normalize to uppercase (USD)

### 3. exchange - CASE
- **Yahoo**: "PCX", "NMS", etc.
- **Massive**: primary_exchange may vary
- **Action**: Normalize to uppercase for consistency

### 4. sector/industry - TAXONOMY MIX
- **Yahoo/Alpha Vantage**: GICS (e.g. "Technology", "Financial Services")
- **Massive**: SIC (sic_description, e.g. "ESTABLISHED PHYSICAL COMMODITY CONTRACTS")
- **ETFDB**: asset_class (e.g. "Bond", "Equity", "Currency")
- **Action**: Accept mixed - they fill gaps. No normalization needed unless we want strict GICS.

### 5. market_cap - DONE
- Already normalized to dollars. ETFDB millions converted. Cleanup script run.

## Current Data Flow (portrec)

- **Primary**: Yahoo (_fetch_security_data)
- **Enrichment**: Massive fills sector, description when missing
- **Enrichment**: Alpha Vantage fills sector, industry, description when missing
- **ETFDB**: Seeds symbols, market_cap, sector, year_performance

Alpha Vantage and Massive do NOT currently set dividend_yield or market_cap in the portrec flow. So dividend_yield unit inconsistency would only matter if we start using Alpha Vantage for it.

## Recommendations (IMPLEMENTED)

1. **currency**: Normalize to uppercase when saving - DONE
2. **exchange**: Normalize to uppercase when saving - DONE
3. **dividend_yield**: Store as percentage (Yahoo format). Convert decimal (< 0.1) to % when enriching from Alpha Vantage - DONE
4. **sector/industry**: Split into gics_sector, gics_industry, sic_code, sic_description, asset_class - DONE
5. **One-time cleanup**: Run `python cleanup_data_formatting.py portrec_securities.db`

## Schema: Sector/Industry Split

| Column | Source | Description |
|--------|--------|-------------|
| sector | derived | COALESCE(gics_sector, asset_class) - for backward compat / thesis matching |
| industry | derived | Usually gics_industry |
| gics_sector | Yahoo, Alpha Vantage | GICS sector (Technology, Financial Services, etc.) |
| gics_industry | Yahoo, Alpha Vantage | GICS industry (e.g. Semiconductors) |
| sic_code | Massive/Polygon | SIC code |
| sic_description | Massive/Polygon | SIC description |
| asset_class | ETFDB | Industry-standard concept (Equity, Bond, Commodity, Currency, etc.). ETFDB uses its own mapping. |
