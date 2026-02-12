#!/usr/bin/env python3
"""
Backfill first 10 ETFs from DB with full Yahoo Finance data + holdings.
Then enrich constituent securities from those holdings.
Display updated data for review.
"""

import sqlite3
import yaml
from pathlib import Path

from equity_analyst_autonomous import AutonomousEquityAnalyst


def main():
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    db_path = cfg.get("securities_db_path", "portrec_securities.db")

    analyst = AutonomousEquityAnalyst(db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT symbol, name FROM securities
        WHERE UPPER(COALESCE(asset_type, '')) = 'ETF'
        ORDER BY symbol
        LIMIT 10
    """)
    etfs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not etfs:
        print("No ETFs found in database.")
        return

    print(f"Backfilling {len(etfs)} ETFs: {[e['symbol'] for e in etfs]}")
    print()

    all_constituents = set()

    print("=" * 60)
    print("STEP 1: Fetch and save full ETF data + holdings")
    print("=" * 60)
    for etf in etfs:
        sym = etf["symbol"]
        print(f"\n  {sym}...")
        data = analyst._fetch_security_data(sym)
        if data:
            analyst.save_security(data)
            print(f"    Saved: {data.get('name', 'N/A')[:50]}")
        else:
            print(f"    No data from Yahoo")
        holdings = analyst.fetch_etf_holdings(sym)
        if holdings:
            analyst.save_etf_holdings(sym, holdings, source="yahoo")
            for h in holdings:
                all_constituents.add(h["symbol"])
            print(f"    Holdings: {len(holdings)} saved")
        else:
            print(f"    No holdings")

    print()
    print("=" * 60)
    print("STEP 2: Enrich constituent securities from holdings")
    print("=" * 60)
    constituents = sorted(all_constituents)
    print(f"\n  Unique constituents: {len(constituents)}")
    for sym in constituents:
        print(f"  {sym}...", end=" ")
        data = analyst._fetch_security_data(sym)
        if data:
            analyst.save_security(data)
            print(f"OK ({data.get('name', '')[:35]})")
        else:
            print("No data")

    print()
    print("=" * 60)
    print("UPDATED DATA FOR REVIEW")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n--- ETFs (backfilled) ---")
    cursor.execute("""
        SELECT symbol, name, asset_type, market_cap, sector, current_price,
               pe_ratio, dividend_yield, year_performance, expense_ratio, last_updated
        FROM securities
        WHERE symbol IN ({})
        ORDER BY symbol
    """.format(",".join("?" * len([e["symbol"] for e in etfs]))), [e["symbol"] for e in etfs])
    for row in cursor.fetchall():
        r = dict(row)
        print(f"  {r['symbol']:6} | {str(r['name'] or '')[:40]:40} | "
              f"cap={r['market_cap']} | price={r['current_price']} | "
              f"PE={r['pe_ratio']} | div={r['dividend_yield']}% | "
              f"1Y={r['year_performance']}% | exp={r['expense_ratio']} | "
              f"updated={r['last_updated']}")

    # Show holdings for first ETF that has them
    etf_with_holdings = None
    for e in etfs:
        cursor.execute("SELECT 1 FROM etf_holdings WHERE etf_symbol = ? LIMIT 1", (e["symbol"],))
        if cursor.fetchone():
            etf_with_holdings = e["symbol"]
            break
    print(f"\n--- ETF Holdings (sample: {etf_with_holdings or 'N/A'}) ---")
    if etf_with_holdings:
        cursor.execute("""
            SELECT h.etf_symbol, h.constituent_symbol, h.holding_percent, h.holding_rank,
                   s.name as constituent_name, s.asset_type, s.current_price, s.sector
            FROM etf_holdings h
            JOIN securities s ON s.symbol = h.constituent_symbol
            WHERE h.etf_symbol = ?
            ORDER BY h.holding_rank
        """, (etf_with_holdings,))
        for row in cursor.fetchall():
            r = dict(row)
            print(f"  {r['holding_rank']:2}. {r['constituent_symbol']:6} {r['holding_percent']:5.2f}% | "
                  f"{str(r['constituent_name'] or '')[:30]:30} | "
                  f"type={r['asset_type'] or 'NULL'} | price={r['current_price']} | sector={r['sector'] or 'NULL'}")

    print("\n--- Constituents (enriched) ---")
    cursor.execute("""
        SELECT symbol, name, asset_type, market_cap, sector, industry, current_price,
               pe_ratio, dividend_yield, last_updated
        FROM securities
        WHERE symbol IN ({})
        ORDER BY symbol
    """.format(",".join("?" * len(constituents))), constituents)
    for row in cursor.fetchall():
        r = dict(row)
        print(f"  {r['symbol']:6} | {str(r['name'] or '')[:35]:35} | "
              f"type={r['asset_type'] or 'NULL'} | cap={r['market_cap']} | "
              f"sector={r['sector'] or 'NULL'} | price={r['current_price']} | "
              f"PE={r['pe_ratio']} | div={r['dividend_yield']}% | updated={r['last_updated']}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
