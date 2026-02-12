#!/usr/bin/env python3
"""
Full backfill: all ETFs in DB with Yahoo Finance data + holdings.
Enriches constituent securities. Avoids duplicate fetches within run
(never fetches the same symbol twice in a single run).
"""

import sqlite3
import time
import yaml
from pathlib import Path

from equity_analyst_autonomous import AutonomousEquityAnalyst

# Delay between Yahoo requests to avoid rate limiting
REQUEST_DELAY_SEC = 0.3


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Full ETF backfill from Yahoo Finance")
    parser.add_argument("--start", type=int, default=0, help="Start at ETF index (0-based)")
    parser.add_argument("--limit", type=int, default=None, help="Max ETFs to process (default: all)")
    parser.add_argument("--constituents-only", action="store_true", help="Skip ETF step; only enrich constituents from etf_holdings")
    parser.add_argument("--constituent-start", type=int, default=0, help="Start at constituent index (for --constituents-only)")
    parser.add_argument("--constituent-limit", type=int, default=None, help="Max constituents to process (for --constituents-only)")
    parser.add_argument("--remaining-only", action="store_true", help="Only fetch constituents lacking sector/description (skip already enriched)")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path("config.yaml").read_text())
    db_path = cfg.get("securities_db_path", "portrec_securities.db")

    analyst = AutonomousEquityAnalyst(db_path=db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT constituent_symbol FROM etf_holdings ORDER BY constituent_symbol")
    all_constituents = sorted(row[0] for row in cursor.fetchall())
    conn.close()

    if args.constituents_only:
        constituents = all_constituents[args.constituent_start:]
        if args.constituent_limit:
            constituents = constituents[: args.constituent_limit]
        if args.remaining_only:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol FROM securities
                WHERE (sector IS NOT NULL AND TRIM(sector) != '')
                   OR (gics_sector IS NOT NULL AND TRIM(gics_sector) != '')
                   OR (description IS NOT NULL AND TRIM(description) != '')
            """)
            already_enriched = set(row[0] for row in cursor.fetchall())
            conn.close()
            constituents = [c for c in constituents if c not in already_enriched]
            print(f"Constituent enrichment (remaining only): {len(constituents)} to fetch (skipping {len(already_enriched)} already enriched)")
        else:
            print(f"Constituent enrichment only: {len(constituents)} constituents (start={args.constituent_start}, of {len(all_constituents)})")
        print("Deduplication: each symbol fetched at most once per run")
        print()
        fetched_this_run = set()
        stats = {"etfs_fetched": 0, "holdings_saved": 0, "constituents_fetched": 0}
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, name FROM securities
            WHERE UPPER(COALESCE(asset_type, '')) = 'ETF'
            ORDER BY symbol
        """)
        all_etfs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        etfs = all_etfs[args.start:]
        if args.limit:
            etfs = etfs[: args.limit]
        if args.start or args.limit:
            print(f"Batch: ETFs {args.start} to {args.start + len(etfs) - 1} (of {len(all_etfs)})")
        if not etfs:
            print("No ETFs found in database.")
            return

        print(f"Full backfill: {len(etfs)} ETFs")
        print("Deduplication: each symbol fetched at most once per run")
        print()

        fetched_this_run = set()
        all_constituents_set = set()
        stats = {"etfs_fetched": 0, "holdings_saved": 0, "constituents_fetched": 0}

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print("=" * 60)
        print("STEP 1: Fetch and save ETF data + holdings")
        print("=" * 60)
        for i, etf in enumerate(etfs):
            sym = etf["symbol"]
            if (i + 1) % 100 == 0 or i == 0:
                print(f"  Progress: {i + 1}/{len(etfs)} ETFs...")
            if sym in fetched_this_run:
                continue
            data = analyst._fetch_security_data(sym)
            if data:
                analyst.save_security(data)
                fetched_this_run.add(sym)
                stats["etfs_fetched"] += 1
            time.sleep(REQUEST_DELAY_SEC)
            holdings = analyst.fetch_etf_holdings(sym)
            if holdings:
                analyst.save_etf_holdings(sym, holdings, source="yahoo")
                stats["holdings_saved"] += 1
                for h in holdings:
                    all_constituents_set.add(h["symbol"])
            time.sleep(REQUEST_DELAY_SEC)

        cursor.execute("SELECT DISTINCT constituent_symbol FROM etf_holdings")
        for row in cursor.fetchall():
            all_constituents_set.add(row[0])
        conn.close()

        constituents = sorted(all_constituents_set)
    print(f"\n  Unique constituents from holdings: {len(constituents)}")
    print()
    print("=" * 60)
    print("STEP 2: Enrich constituent securities")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for i, sym in enumerate(constituents):
        if (i + 1) % 200 == 0 or (i < 5 and i >= 0):
            print(f"  Progress: {i + 1}/{len(constituents)} constituents...")
        if sym in fetched_this_run:
            continue
        data = analyst._fetch_security_data(sym)
        if data:
            analyst.save_security(data)
            fetched_this_run.add(sym)
            stats["constituents_fetched"] += 1
        time.sleep(REQUEST_DELAY_SEC)
    conn.close()

    print()
    print("=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"  ETFs fetched: {stats['etfs_fetched']}")
    print(f"  Holdings saved: {stats['holdings_saved']} ETFs")
    print(f"  Constituents fetched: {stats['constituents_fetched']}")
    print()


if __name__ == "__main__":
    main()
