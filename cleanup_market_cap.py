#!/usr/bin/env python3
"""
One-time cleanup: normalize market_cap to dollars in securities table.

Values < 1e6 are assumed to be in millions (ETFDB format) and are multiplied by 1e6.
Values >= 1e6 are assumed already in dollars (Yahoo, etc.) and are left as-is.
"""

import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "portrec_securities.db"


def cleanup(db_path: str) -> int:
    """Normalize market_cap column. Returns number of rows updated."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, market_cap FROM securities WHERE market_cap IS NOT NULL")
    rows = cursor.fetchall()
    updated = 0
    for symbol, mc in rows:
        if mc is None or mc <= 0:
            continue
        if mc < 1e6:
            # Treat as millions (ETFDB format) - convert to dollars
            new_mc = mc * 1e6
            cursor.execute("UPDATE securities SET market_cap = ? WHERE symbol = ?", (new_mc, symbol))
            updated += 1
    conn.commit()
    conn.close()
    return updated


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    if not Path(db).exists():
        print(f"Database not found: {db}")
        sys.exit(1)
    n = cleanup(db)
    print(f"Updated {n} market_cap values to dollars")


if __name__ == "__main__":
    main()
