#!/usr/bin/env python3
"""
ETFDB.com - Source for securities database

Uses the ETFDB screener API (POST https://etfdb.com/api/screener/) for full pagination.
Each page is a deterministic request: page=N in the JSON body.

Writes to the securities table. Merges with existing data: only fills in null fields
so Yahoo/Alpha Vantage data is preserved when present.

Logs pages scraped, securities recorded, and failed attempts to etfdb_scraper.log.
"""

import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Log file in same directory as script
LOG_FILE = Path(__file__).parent / "etfdb_scraper.log"

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

# Default DB path - use config.yaml securities_db_path in production
DEFAULT_DB_PATH = "portrec_securities.db"
API_URL = "https://etfdb.com/api/screener/"
COOKIE_URL = "https://etfdb.com/alpha/A/"  # Visit first to get Cloudflare cookies
REQUEST_DELAY = 1.0  # Be polite to the server
PER_PAGE = 25


def _setup_logging(log_path: Path = LOG_FILE) -> logging.Logger:
    """Configure file logger for scraper run."""
    logger = logging.getLogger("etfdb_scraper")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)
    return logger


def _parse_assets(value) -> Optional[float]:
    """
    Parse ETFDB assets string to dollars (float).
    ETFDB returns values in millions when no K/M/B suffix (e.g. '$3,079' = $3.079B).
    Strips $, commas. Returns value in dollars for consistency with Yahoo.
    """
    if value is None:
        return None
    orig = str(value).strip().upper()
    s = orig.replace("$", "").replace(",", "").replace(" ", "")
    if not s or s == "N/A":
        return None
    has_suffix = any(x in orig for x in ("K", "M", "B"))
    s = s.replace("K", "e3").replace("M", "e6").replace("B", "e9")
    try:
        raw = float(s)
        # ETFDB plain numbers (no K/M/B) are in millions - convert to dollars
        if not has_suffix:
            raw = raw * 1e6
        return raw
    except ValueError:
        return None


def _parse_pct(value) -> Optional[float]:
    """Parse '1.25%' or '-0.50%' to float."""
    if value is None:
        return None
    s = str(value).strip().replace("%", "").replace(",", "").strip()
    if not s or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _create_session():
    if HAS_CLOUDSCRAPER:
        return cloudscraper.create_scraper()
    import requests
    return requests.Session()


def fetch_api_page(session, page: int, logger: Optional[logging.Logger] = None) -> Optional[dict]:
    """Fetch a single page from ETFDB screener API. Returns parsed JSON or None."""
    body = {
        "page": page,
        "per_page": PER_PAGE,
        "sort_by": "symbol",
        "sort_direction": "asc",
        "only": ["meta", "data"],
    }
    try:
        resp = session.post(API_URL, json=body, headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        if "Just a moment" in resp.text or resp.status_code == 403:
            msg = f"Page {page}: Cloudflare/403 blocked"
            if logger:
                logger.warning(msg)
            return None
        return resp.json()
    except Exception as e:
        msg = f"Page {page}: FAILED - {e}"
        if logger:
            logger.error(msg)
        return None


def parse_api_row(item: dict) -> Optional[Dict]:
    """Convert API response item to securities schema."""
    symbol = item.get("symbol")
    if isinstance(symbol, dict):
        symbol = symbol.get("text")
    if not symbol:
        return None
    name = item.get("name")
    if isinstance(name, dict):
        name = name.get("text", "")
    ac = (item.get("asset_class") or "").strip() or None
    # ETFDB asset_class: Equity, Bond, Commodity, Currency, etc. Normalize to uppercase.
    if ac:
        ac = ac.upper()
    return {
        "symbol": symbol,
        "name": name or None,
        "asset_type": "ETF",
        "market_cap": _parse_assets(item.get("assets")),
        "gics_sector": None,
        "gics_industry": None,
        "sic_code": None,
        "sic_description": None,
        "asset_class": ac,
        "sector": ac,  # for backward compat / matching
        "industry": None,
        "description": None,
        "exchange": None,
        "currency": "USD",
        "current_price": None,
        "pe_ratio": None,
        "dividend_yield": None,
        "year_performance": _parse_pct(item.get("ytd")),
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "beta": None,
        "volume": None,
        "avg_volume": None,
        "expense_ratio": None,  # ETFDB API does not provide; Yahoo Finance is source
    }


def save_to_securities(conn: sqlite3.Connection, securities: List[Dict]):
    """
    Upsert into securities table. Merges with existing: only fills null columns
    so Yahoo/Alpha Vantage data is preserved.
    """
    for s in securities:
        symbol = s["symbol"]
        currency = (s.get("currency") or "USD").strip().upper()
        conn.execute("""
            INSERT INTO securities (
                symbol, name, asset_type, market_cap, sector, industry, gics_sector, gics_industry,
                sic_code, sic_description, asset_class, description, exchange, currency,
                current_price, pe_ratio, dividend_yield, year_performance,
                fifty_two_week_high, fifty_two_week_low, beta, volume, avg_volume, expense_ratio, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(symbol) DO UPDATE SET
                name = COALESCE(excluded.name, name),
                asset_type = COALESCE(excluded.asset_type, asset_type),
                market_cap = COALESCE(excluded.market_cap, market_cap),
                sector = COALESCE(excluded.sector, sector),
                industry = COALESCE(excluded.industry, industry),
                gics_sector = COALESCE(excluded.gics_sector, gics_sector),
                gics_industry = COALESCE(excluded.gics_industry, gics_industry),
                sic_code = COALESCE(excluded.sic_code, sic_code),
                sic_description = COALESCE(excluded.sic_description, sic_description),
                asset_class = COALESCE(excluded.asset_class, asset_class),
                description = COALESCE(excluded.description, description),
                exchange = COALESCE(excluded.exchange, exchange),
                currency = COALESCE(excluded.currency, currency),
                current_price = COALESCE(excluded.current_price, current_price),
                pe_ratio = COALESCE(excluded.pe_ratio, pe_ratio),
                dividend_yield = COALESCE(excluded.dividend_yield, dividend_yield),
                year_performance = COALESCE(excluded.year_performance, year_performance),
                fifty_two_week_high = COALESCE(excluded.fifty_two_week_high, fifty_two_week_high),
                fifty_two_week_low = COALESCE(excluded.fifty_two_week_low, fifty_two_week_low),
                beta = COALESCE(excluded.beta, beta),
                volume = COALESCE(excluded.volume, volume),
                avg_volume = COALESCE(excluded.avg_volume, avg_volume),
                expense_ratio = COALESCE(excluded.expense_ratio, expense_ratio),
                last_updated = datetime('now')
        """, (
            symbol,
            s["name"],
            s["asset_type"],
            s["market_cap"],
            s["sector"],
            s["industry"],
            s.get("gics_sector"),
            s.get("gics_industry"),
            s.get("sic_code"),
            s.get("sic_description"),
            s.get("asset_class"),
            s["description"],
            ((s.get("exchange") or "").strip().upper() or None),
            currency,
            s["current_price"],
            s["pe_ratio"],
            s["dividend_yield"],
            s["year_performance"],
            s["fifty_two_week_high"],
            s["fifty_two_week_low"],
            s["beta"],
            s["volume"],
            s["avg_volume"],
            s["expense_ratio"],
        ))


def ensure_securities_schema(conn: sqlite3.Connection):
    """Ensure securities table exists with full schema (idempotent)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS securities (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            asset_type TEXT,
            market_cap REAL,
            sector TEXT,
            industry TEXT,
            gics_sector TEXT,
            gics_industry TEXT,
            sic_code TEXT,
            sic_description TEXT,
            asset_class TEXT,
            description TEXT,
            exchange TEXT,
            currency TEXT,
            current_price REAL,
            pe_ratio REAL,
            dividend_yield REAL,
            year_performance REAL,
            fifty_two_week_high REAL,
            fifty_two_week_low REAL,
            beta REAL,
            volume REAL,
            avg_volume REAL,
            expense_ratio REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col in ("current_price", "pe_ratio", "dividend_yield", "year_performance",
                "fifty_two_week_high", "fifty_two_week_low", "beta", "volume", "avg_volume", "expense_ratio"):
        try:
            conn.execute(f"ALTER TABLE securities ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    for col in ("gics_sector", "gics_industry", "sic_code", "sic_description", "asset_class"):
        try:
            conn.execute(f"ALTER TABLE securities ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass


def run_scraper(
    db_path: str = DEFAULT_DB_PATH,
    max_pages: Optional[int] = None,
    letter: Optional[str] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    log_path: Optional[Path] = None,
) -> int:
    """
    Scrape ETFDB screener API and write to securities table.
    If letter is set (e.g. "A"), stop when first symbol no longer starts with that letter.
    If start_page/end_page are set, scrape only that page range (e.g. 11-20).
    Returns total ETFs saved.
    """
    if not HAS_CLOUDSCRAPER:
        print("[ERR] Install cloudscraper: pip install cloudscraper")
        return 0

    logger = _setup_logging(log_path or LOG_FILE)
    logger.info("=" * 60)
    logger.info(f"Scraper run started at {datetime.now().isoformat()}")
    logger.info(f"db={db_path}, max_pages={max_pages}, letter={letter}, start_page={start_page}, end_page={end_page}")

    session = _create_session()
    print("Establishing session...")
    session.get(COOKIE_URL, timeout=30)

    data = fetch_api_page(session, 1, logger)
    if not data:
        logger.error("Initial API request failed - cannot determine total pages")
        return 0

    meta = data.get("meta", {})
    total_pages = meta.get("total_pages", 0)
    total_records = meta.get("total_records", 0)

    if start_page is not None and end_page is not None:
        page_range = range(start_page, end_page + 1)
    else:
        if max_pages:
            total_pages = min(total_pages, max_pages)
        page_range = range(1, total_pages + 1)

    target_letter = letter.upper() if letter else None
    print(f"Fetching pages {page_range[0]}-{page_range[-1]} -> securities table...")

    conn = sqlite3.connect(db_path)
    ensure_securities_schema(conn)
    conn.commit()
    total = 0

    for page in page_range:
        if page > 1:
            data = fetch_api_page(session, page, logger)
            if not data:
                logger.warning(f"Stopping: page {page} fetch failed")
                break
        rows = [parse_api_row(item) for item in data.get("data", [])]
        rows = [r for r in rows if r]
        if not rows:
            logger.info(f"Page {page}: no securities (empty)")
            break
        # Stop if letter filter (and not using explicit page range) and we've passed it
        if target_letter and start_page is None:
            first_sym = rows[0].get("symbol", "") or ""
            if not first_sym.upper().startswith(target_letter):
                logger.info(f"Page {page}: first symbol {first_sym} does not start with {target_letter} - stopping")
                break
        save_to_securities(conn, rows)
        total += len(rows)
        conn.commit()
        logger.info(f"Page {page}: scraped OK, {len(rows)} securities")
        for r in rows:
            logger.info(f"  Recorded: {r['symbol']} | {r.get('name', '')[:50]}")
        print(f"  Page {page}: {len(rows)} ETFs (total: {total})")
        if page < page_range[-1]:
            time.sleep(REQUEST_DELAY)

    conn.close()
    logger.info(f"Run complete. Total securities recorded: {total}")
    logger.info("=" * 60)
    return total


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Scrape ETFDB into securities database",
        epilog="Writes to securities table. Logs to etfdb_scraper.log.",
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Securities database path")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages (default: all)")
    parser.add_argument("--letter", type=str, default=None, help="Only ETFs starting with this letter (e.g. A)")
    parser.add_argument("--start-page", type=int, default=None, help="First page to scrape (use with --end-page)")
    parser.add_argument("--end-page", type=int, default=None, help="Last page to scrape (use with --start-page)")
    parser.add_argument("--log", type=str, default=None, help="Log file path (default: etfdb_scraper.log)")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else None
    print(f"ETFDB Scraper - db: {args.db}")
    if args.start_page is not None and args.end_page is not None:
        print(f"Pages: {args.start_page}-{args.end_page}")
    elif args.letter:
        print(f"Letter: {args.letter}")
    print(f"Log: {log_path or LOG_FILE}")
    total = run_scraper(
        db_path=args.db,
        max_pages=args.max_pages,
        letter=args.letter,
        start_page=args.start_page,
        end_page=args.end_page,
        log_path=log_path,
    )
    print(f"\nDone. Total ETFs in securities: {total}")


if __name__ == "__main__":
    main()
