#!/usr/bin/env python3
"""
One-time cleanup: normalize data formatting in securities table.

1. dividend_yield: store as percentage (Yahoo format). Convert decimal values (< 0.1) to %.
2. currency, exchange: normalize to uppercase.
3. sector/industry split: migrate to gics_sector, gics_industry, sic_code, sic_description, asset_class.
   - sector in (Equity, Bond, Commodity, etc.) -> asset_class
   - sector GICS-style (Technology, Financial Services, etc.) -> gics_sector
   - industry -> gics_industry
   - sector = COALESCE(gics_sector, asset_class) for backward compat
"""

import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "portrec_securities.db"

# ETFDB asset_class values (case-insensitive)
ASSET_CLASS_VALUES = frozenset(
    {"equity", "bond", "commodity", "currency", "multi-asset", "alternatives",
     "real estate", "volatility", "preferred stock"}
)


def ensure_columns(conn: sqlite3.Connection):
    """Ensure new columns exist."""
    for col in ("gics_sector", "gics_industry", "sic_code", "sic_description", "asset_class"):
        try:
            conn.execute(f"ALTER TABLE securities ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass


def cleanup(db_path: str) -> dict:
    """
    Run all one-time corrections. Returns counts: dividend_yield, currency_exchange, sector_split.
    """
    conn = sqlite3.connect(db_path)
    ensure_columns(conn)
    cursor = conn.cursor()

    # 1. dividend_yield: convert decimal (< 0.1) to percentage
    cursor.execute("SELECT symbol, dividend_yield FROM securities WHERE dividend_yield IS NOT NULL")
    dy_updated = 0
    for symbol, dy in cursor.fetchall():
        if dy is not None and 0 < dy < 0.1:
            cursor.execute("UPDATE securities SET dividend_yield = ? WHERE symbol = ?", (dy * 100, symbol))
            dy_updated += 1

    # 2. currency, exchange: uppercase
    cursor.execute("SELECT symbol, currency, exchange FROM securities")
    ce_updated = 0
    for symbol, currency, exchange in cursor.fetchall():
        changes = []
        args = []
        if currency and str(currency).strip() and str(currency) != str(currency).upper():
            changes.append("currency = ?")
            args.append(str(currency).strip().upper())
        if exchange and str(exchange).strip() and str(exchange) != str(exchange).upper():
            changes.append("exchange = ?")
            args.append(str(exchange).strip().upper())
        if changes:
            args.append(symbol)
            cursor.execute(f"UPDATE securities SET {', '.join(changes)} WHERE symbol = ?", args)
            ce_updated += 1

    # 3. sector/industry migration to gics_sector, gics_industry, asset_class
    cursor.execute("SELECT symbol, sector, industry FROM securities")
    sector_updated = 0
    for symbol, sector, industry in cursor.fetchall():
        gics_sector = None
        gics_industry = None
        asset_class = None
        if sector:
            s_lower = str(sector).strip().lower()
            if s_lower in ASSET_CLASS_VALUES:
                asset_class = str(sector).strip().upper()
            else:
                gics_sector = str(sector).strip()
        if industry:
            gics_industry = str(industry).strip()
        # sector for backward compat = gics_sector or asset_class
        derived_sector = gics_sector or asset_class
        cursor.execute(
            """UPDATE securities SET gics_sector = ?, gics_industry = ?, asset_class = ?, sector = ?, industry = ?
               WHERE symbol = ?""",
            (gics_sector, gics_industry, asset_class, derived_sector, gics_industry, symbol)
        )
        if gics_sector or asset_class or gics_industry:
            sector_updated += 1

    conn.commit()
    conn.close()
    return {"dividend_yield": dy_updated, "currency_exchange": ce_updated, "sector_split": sector_updated}


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    if not Path(db).exists():
        print(f"Database not found: {db}")
        sys.exit(1)
    counts = cleanup(db)
    print(f"Updated dividend_yield: {counts['dividend_yield']} rows")
    print(f"Updated currency/exchange: {counts['currency_exchange']} rows")
    print(f"Migrated sector/industry: {counts['sector_split']} rows")


if __name__ == "__main__":
    main()
