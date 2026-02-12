#!/usr/bin/env python3
"""
Autonomous Equity Analyst Agent - Direct API Version
No MCP, no Claude API - pure Python with yfinance

This version uses:
- yfinance for all financial data
- SQLite for persistence
- Your existing scoring logic
- No external dependencies on Claude or MCP
"""

import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re


# Price/performance data older than this is considered stale and will be refetched
STALENESS_DAYS = 7


def _normalize_dividend_yield(val) -> Optional[float]:
    """Store dividend yield as percentage (Yahoo format). Convert decimal (e.g. 0.025) to % if needed."""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    # Values < 0.1 are likely decimal (0.025 = 2.5%); convert to percentage
    if 0 < v < 0.1:
        return v * 100
    return v


def _normalize_currency(val) -> Optional[str]:
    """Return uppercase currency code or None."""
    if val is None or not str(val).strip():
        return None
    return str(val).strip().upper()


def _normalize_exchange(val) -> Optional[str]:
    """Return uppercase exchange code or None."""
    if val is None or not str(val).strip():
        return None
    return str(val).strip().upper()


def _derived_sector(gics_sector: Optional[str], asset_class: Optional[str]) -> Optional[str]:
    """Sector for display/matching: GICS when available, else asset_class."""
    return gics_sector or asset_class


class AutonomousEquityAnalyst:
    """Fully autonomous equity analyst using direct APIs."""
    
    def __init__(self, db_path: str = "securities.db"):
        """Initialize the analyst with database connection."""
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with required schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create securities table
        cursor.execute("""
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
        # Migration: add columns if they don't exist (older DBs)
        for col in ("current_price", "pe_ratio", "dividend_yield", "year_performance",
                    "fifty_two_week_high", "fifty_two_week_low", "beta", "volume", "avg_volume",
                    "expense_ratio"):
            try:
                cursor.execute(f"ALTER TABLE securities ADD COLUMN {col} REAL")
            except sqlite3.OperationalError:
                pass  # Column already exists
        for col in ("gics_sector", "gics_industry", "sic_code", "sic_description", "asset_class"):
            try:
                cursor.execute(f"ALTER TABLE securities ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        # Create etf_holdings table (ETF -> constituent allocation)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS etf_holdings (
                etf_symbol TEXT NOT NULL,
                constituent_symbol TEXT NOT NULL,
                holding_percent REAL NOT NULL,
                holding_rank INTEGER,
                source TEXT DEFAULT 'yahoo',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (etf_symbol, constituent_symbol),
                FOREIGN KEY (etf_symbol) REFERENCES securities(symbol),
                FOREIGN KEY (constituent_symbol) REFERENCES securities(symbol)
            )
        """)

        # Create thesis_alignments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thesis_alignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES securities(symbol)
            )
        """)
        
        conn.commit()
        conn.close()
        print(f"[OK] Database initialized: {self.db_path}")
    
    def search_securities(self, query: str, max_results: int = 20) -> List[Dict]:
        """
        Search for securities using yfinance.
        
        Args:
            query: Search query (keywords for ETFs, stocks, etc.)
            max_results: Maximum number of results to return
            
        Returns:
            List of security dictionaries
        """
        print(f"\nSearching for securities matching: '{query}'")
        
        # Common ETF ticker patterns based on query
        etf_searches = self._generate_search_tickers(query)
        
        results = []
        for ticker in etf_searches[:max_results]:
            try:
                security_data = self._fetch_security_data(ticker)
                if security_data:
                    results.append(security_data)
                    print(f"  [OK] Found: {ticker} - {security_data.get('name', 'N/A')}")
            except Exception as e:
                print(f"  [ERR] Error fetching {ticker}: {e}")
                continue
        
        print(f"[OK] Found {len(results)} securities")
        return results
    
    def _generate_search_tickers(self, query: str) -> List[str]:
        """
        Generate likely ticker symbols based on search query.
        
        This is a heuristic approach - in production you'd want a proper
        ticker search API or database.
        """
        query_lower = query.lower()
        tickers = []
        
        # Common ETF prefixes/patterns
        if 'small' in query_lower and 'cap' in query_lower:
            tickers.extend(['IWM', 'IJR', 'SCHA', 'VB', 'SLYG', 'SLYV', 'VBR', 'VBK'])
        
        if 'mid' in query_lower and 'cap' in query_lower:
            tickers.extend(['IJH', 'MDY', 'VO', 'SCHM', 'IWR', 'VXF'])
        
        if 'tech' in query_lower or 'technology' in query_lower:
            tickers.extend(['XLK', 'VGT', 'QQQ', 'QTEC', 'SOXX', 'IGV', 'FDN'])
        
        if 'energy' in query_lower:
            tickers.extend(['XLE', 'VDE', 'IYE', 'FENY', 'IXC', 'PXE'])
        
        if 'health' in query_lower or 'healthcare' in query_lower:
            tickers.extend(['XLV', 'VHT', 'IYH', 'FHLC', 'IBB', 'XBI'])
        
        if 'financial' in query_lower or 'bank' in query_lower:
            tickers.extend(['XLF', 'VFH', 'IYF', 'KBE', 'KRE', 'IAT'])
        
        if 'dividend' in query_lower or 'income' in query_lower:
            tickers.extend(['VYM', 'DVY', 'SCHD', 'HDV', 'SDY', 'DGRO', 'VIG'])
        
        if 'value' in query_lower:
            tickers.extend(['VTV', 'IVE', 'VOOV', 'SCHV', 'IWD', 'VBR'])
        
        if 'growth' in query_lower:
            tickers.extend(['VUG', 'IVW', 'VOOG', 'SCHG', 'IWF', 'VBK'])
        
        if 'international' in query_lower or 'emerging' in query_lower:
            tickers.extend(['VEA', 'IEFA', 'VWO', 'IEMG', 'EEM', 'VEU', 'IXUS'])
        
        if 'real estate' in query_lower or 'reit' in query_lower:
            tickers.extend(['VNQ', 'IYR', 'SCHH', 'XLRE', 'RWR', 'USRT'])
        
        # Default broad market ETFs if no specific match
        if not tickers:
            tickers.extend(['SPY', 'VOO', 'VTI', 'IVV', 'QQQ', 'DIA'])
        
        return list(dict.fromkeys(tickers))  # Remove duplicates while preserving order
    
    def _load_security_from_db(self, ticker: str) -> Optional[Dict]:
        """
        Load cached security from DB if price/performance data is fresh (< 7 days).
        Returns None if not found or stale (sector/description are not refetched; only price/performance).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT symbol, name, asset_type, market_cap, sector, industry, gics_sector, gics_industry, "
            "sic_code, sic_description, asset_class, description, exchange, currency, "
            "current_price, pe_ratio, dividend_yield, year_performance, "
            "fifty_two_week_high, fifty_two_week_low, beta, volume, avg_volume, expense_ratio, last_updated "
            "FROM securities WHERE symbol = ?",
            (ticker.upper(),),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        (symbol, name, asset_type, market_cap, sector, industry, gics_sector, gics_industry,
         sic_code, sic_description, asset_class, description, exchange, currency,
         current_price, pe_ratio, dividend_yield, year_performance,
         fifty_two_week_high, fifty_two_week_low, beta, volume, avg_volume, expense_ratio, last_updated_str) = row
        if not last_updated_str:
            return None
        s = last_updated_str.strip().replace("T", " ")[:19]
        try:
            last_updated = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                last_updated = datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return None
        if last_updated.tzinfo:
            last_updated = last_updated.replace(tzinfo=None)
        if datetime.now() - last_updated > timedelta(days=STALENESS_DAYS):
            return None  # Stale
        # Require at least some price/performance data to use cache
        if current_price is None and year_performance is None:
            return None
        return {
            "symbol": symbol,
            "name": name or symbol,
            "asset_type": asset_type,
            "market_cap": market_cap,
            "sector": sector,
            "industry": industry,
            "description": description or "",
            "exchange": exchange,
            "currency": currency or "USD",
            "current_price": current_price,
            "pe_ratio": pe_ratio,
            "dividend_yield": dividend_yield,
            "year_performance": year_performance,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
            "beta": beta,
            "volume": volume,
            "avg_volume": avg_volume,
            "expense_ratio": expense_ratio,
        }
    
    def _fetch_security_data(self, ticker: str) -> Optional[Dict]:
        """
        Fetch detailed data for a security using yfinance.
        Uses cached price/performance if less than 7 days old.
        Does not refetch sector/description when cache is fresh.
        
        Args:
            ticker: Stock/ETF ticker symbol
            
        Returns:
            Dictionary with security data or None if not found
        """
        ticker_upper = ticker.upper()
        cached = self._load_security_from_db(ticker_upper)
        if cached:
            return cached
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Basic validation - check if we got real data
            if not info or 'symbol' not in info:
                return None
            
            # Extract relevant data (Yahoo sector/industry are GICS)
            gics_sector = info.get('sector')
            gics_industry = info.get('industry')
            security_data = {
                'symbol': ticker.upper(),
                'name': info.get('longName') or info.get('shortName', ticker),
                'asset_type': info.get('quoteType', 'EQUITY'),
                'market_cap': info.get('marketCap'),
                'gics_sector': gics_sector,
                'gics_industry': gics_industry,
                'sic_code': None,
                'sic_description': None,
                'asset_class': None,
                'sector': _derived_sector(gics_sector, None),
                'industry': gics_industry,
                'description': info.get('longBusinessSummary', ''),
                'exchange': _normalize_exchange(info.get('exchange')),
                'currency': _normalize_currency(info.get('currency')) or 'USD',
                'current_price': info.get('currentPrice') or info.get('regularMarketPrice'),
                'pe_ratio': info.get('trailingPE') or info.get('forwardPE'),
                'dividend_yield': _normalize_dividend_yield(info.get('dividendYield')),
                'expense_ratio': info.get('netExpenseRatio'),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
                'beta': info.get('beta'),
                'volume': info.get('volume'),
                'avg_volume': info.get('averageVolume'),
            }
            
            # Calculate year performance if possible
            try:
                hist = stock.history(period="1y")
                if len(hist) > 0:
                    year_start = hist.iloc[0]['Close']
                    year_end = hist.iloc[-1]['Close']
                    security_data['year_performance'] = ((year_end - year_start) / year_start) * 100
            except:
                security_data['year_performance'] = None
            
            return security_data
            
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")
            return None
    
    def save_security(self, security: Dict):
        """Save or update security in database, including price/performance for staleness cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Normalize before save
        currency = _normalize_currency(security.get('currency')) or 'USD'
        exchange = _normalize_exchange(security.get('exchange'))
        div_yield = _normalize_dividend_yield(security.get('dividend_yield'))
        gics_sector = security.get('gics_sector')
        gics_industry = security.get('gics_industry')
        sic_code = security.get('sic_code')
        sic_description = security.get('sic_description')
        asset_class = security.get('asset_class')
        sector = security.get('sector') or _derived_sector(gics_sector, asset_class)
        industry = security.get('industry') or gics_industry
        cursor.execute("""
            INSERT OR REPLACE INTO securities 
            (symbol, name, asset_type, market_cap, sector, industry, gics_sector, gics_industry,
             sic_code, sic_description, asset_class, description, exchange, currency,
             current_price, pe_ratio, dividend_yield, year_performance,
             fifty_two_week_high, fifty_two_week_low, beta, volume, avg_volume, expense_ratio, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            security['symbol'],
            security['name'],
            security.get('asset_type'),
            security.get('market_cap'),
            sector,
            industry,
            gics_sector,
            gics_industry,
            sic_code,
            sic_description,
            asset_class,
            security.get('description'),
            exchange,
            currency,
            security.get('current_price'),
            security.get('pe_ratio'),
            div_yield,
            security.get('year_performance'),
            security.get('fifty_two_week_high'),
            security.get('fifty_two_week_low'),
            security.get('beta'),
            security.get('volume'),
            security.get('avg_volume'),
            security.get('expense_ratio'),
        ))
        
        conn.commit()
        conn.close()

    def fetch_etf_holdings(self, ticker: str) -> Optional[List[Dict]]:
        """
        Fetch top holdings for an ETF from Yahoo Finance (yfinance).
        Returns list of {symbol, name, holding_percent} or None if not available.
        Yahoo provides exactly 10 top holdings.
        """
        try:
            stock = yf.Ticker(ticker)
            fd = stock.funds_data
            if not fd or not hasattr(fd, 'top_holdings') or fd.top_holdings is None:
                return None
            df = fd.top_holdings
            if df.empty:
                return None
            holdings = []
            for rank, (symbol, row) in enumerate(df.iterrows(), 1):
                name = row.get('Name', '')
                pct = row.get('Holding Percent', 0)
                try:
                    pct_val = float(pct) * 100 if pct is not None else 0  # Store as percentage
                except (TypeError, ValueError):
                    pct_val = 0
                symbol_str = str(symbol).strip().upper() if symbol else None
                if symbol_str:
                    holdings.append({
                        'symbol': symbol_str,
                        'name': str(name).strip() if name else symbol_str,
                        'holding_percent': pct_val,
                        'holding_rank': rank,
                    })
            return holdings if holdings else None
        except Exception as e:
            print(f"  Error fetching ETF holdings for {ticker}: {e}")
            return None

    def save_etf_holdings(self, etf_symbol: str, holdings: List[Dict], source: str = 'yahoo'):
        """
        Save ETF holdings to database. Ensures each constituent exists in securities
        (inserts minimal row if missing) before inserting into etf_holdings.
        """
        if not holdings:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        etf_sym = etf_symbol.upper()
        for h in holdings:
            const_sym = (h.get('symbol') or '').strip().upper()
            if not const_sym:
                continue
            pct = h.get('holding_percent')
            rank = h.get('holding_rank')
            name = (h.get('name') or const_sym).strip()
            # Ensure constituent exists in securities
            cursor.execute("SELECT 1 FROM securities WHERE symbol = ?", (const_sym,))
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT OR IGNORE INTO securities (symbol, name, last_updated)
                    VALUES (?, ?, datetime('now'))
                """, (const_sym, name))
            # Upsert holding
            cursor.execute("""
                INSERT OR REPLACE INTO etf_holdings
                (etf_symbol, constituent_symbol, holding_percent, holding_rank, source, last_updated)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (etf_sym, const_sym, pct, rank, source))
        conn.commit()
        conn.close()

    def calculate_alignment_score(
        self, 
        security: Dict, 
        thesis: Dict
    ) -> Tuple[float, str]:
        """
        Calculate how well a security aligns with an investment thesis.
        
        Args:
            security: Security data dictionary
            thesis: Investment thesis dictionary
            
        Returns:
            Tuple of (score 0-100, rationale text)
        """
        score = 0.0
        rationale_parts = []
        
        # Extract thesis criteria
        thesis_keywords = thesis.get('keywords', [])
        thesis_sectors = thesis.get('sectors', [])
        thesis_description = thesis.get('description', '').lower()
        
        # 1. Sector/Industry Match (30 points)
        security_sector = (security.get('sector') or '').lower()
        security_industry = (security.get('industry') or '').lower()
        
        sector_match = any(s.lower() in security_sector or s.lower() in security_industry 
                          for s in thesis_sectors)
        if sector_match:
            score += 30
            rationale_parts.append(f"Sector match: {security.get('sector')}")
        
        # 2. Keyword Match in Name/Description (25 points)
        security_text = f"{security.get('name', '')} {security.get('description', '')}".lower()
        
        keyword_matches = [kw for kw in thesis_keywords if kw.lower() in security_text]
        if keyword_matches:
            keyword_score = min(25, len(keyword_matches) * 8)
            score += keyword_score
            rationale_parts.append(f"Keywords matched: {', '.join(keyword_matches[:3])}")
        
        # 3. Market Cap Fit (15 points)
        market_cap = security.get('market_cap')
        if market_cap:
            if 'small cap' in thesis_description or 'small-cap' in thesis_description:
                if market_cap < 2_000_000_000:  # < $2B
                    score += 15
                    rationale_parts.append("Small-cap fit")
            elif 'mid cap' in thesis_description or 'mid-cap' in thesis_description:
                if 2_000_000_000 <= market_cap <= 10_000_000_000:  # $2B-$10B
                    score += 15
                    rationale_parts.append("Mid-cap fit")
            elif 'large cap' in thesis_description or 'large-cap' in thesis_description:
                if market_cap > 10_000_000_000:  # > $10B
                    score += 15
                    rationale_parts.append("Large-cap fit")
        
        # 4. Performance Metrics (15 points)
        year_perf = security.get('year_performance')
        if year_perf is not None:
            if 'growth' in thesis_description and year_perf > 15:
                score += 10
                rationale_parts.append(f"Strong growth: {year_perf:.1f}%")
            elif 'value' in thesis_description and year_perf < 5:
                score += 10
                rationale_parts.append(f"Value opportunity: {year_perf:.1f}%")
        
        # 5. Dividend Yield (15 points)
        div_yield = security.get('dividend_yield')
        if div_yield:
            if ('dividend' in thesis_description or 'income' in thesis_description) and div_yield > 0.02:
                score += 15
                rationale_parts.append(f"Dividend yield: {div_yield*100:.2f}%")
        
        # Generate rationale
        rationale = "; ".join(rationale_parts) if rationale_parts else "Limited alignment detected"
        
        return round(score, 2), rationale
    
    def save_thesis_alignment(
        self,
        thesis_id: int,
        thesis_name: str,
        security: Dict,
        alignment_score: float,
        rationale: str
    ):
        """Save thesis alignment analysis to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO thesis_alignments 
            (thesis_id, thesis_name, symbol, alignment_score, rationale, 
             current_price, market_cap, pe_ratio, dividend_yield, year_performance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            thesis_id,
            thesis_name,
            security['symbol'],
            alignment_score,
            rationale,
            security.get('current_price'),
            security.get('market_cap'),
            security.get('pe_ratio'),
            security.get('dividend_yield'),
            security.get('year_performance')
        ))
        
        conn.commit()
        conn.close()
    
    def analyze_thesis(self, thesis: Dict, max_securities: int = 20) -> List[Dict]:
        """
        Analyze an investment thesis and find aligned securities.
        
        Args:
            thesis: Investment thesis dictionary with keys:
                - id: Thesis ID
                - name: Thesis name
                - description: Detailed description
                - keywords: List of relevant keywords
                - sectors: List of relevant sectors
            max_securities: Maximum securities to analyze
            
        Returns:
            List of analyzed securities with scores
        """
        print(f"\n{'='*60}")
        print(f"Analyzing Thesis: {thesis['name']}")
        print(f"{'='*60}")
        
        # Generate search query from thesis
        search_query = " ".join(thesis.get('keywords', [])[:3])
        
        # Search for securities
        securities = self.search_securities(search_query, max_results=max_securities)
        
        # Analyze each security
        results = []
        for security in securities:
            # Save security to database
            self.save_security(security)
            
            # Calculate alignment score
            score, rationale = self.calculate_alignment_score(security, thesis)
            
            # Save alignment
            self.save_thesis_alignment(
                thesis_id=thesis['id'],
                thesis_name=thesis['name'],
                security=security,
                alignment_score=score,
                rationale=rationale
            )
            
            # Add to results
            result = {
                'symbol': security['symbol'],
                'name': security['name'],
                'score': score,
                'rationale': rationale,
                'current_price': security.get('current_price'),
                'market_cap': security.get('market_cap'),
                'pe_ratio': security.get('pe_ratio'),
                'year_performance': security.get('year_performance')
            }
            results.append(result)
            
            print(f"\n  {security['symbol']}: {security['name']}")
            print(f"    Score: {score}/100")
            print(f"    Rationale: {rationale}")
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"\n{'='*60}")
        print(f"Analysis Complete - Top 5 Matches:")
        print(f"{'='*60}")
        for i, result in enumerate(results[:5], 1):
            print(f"{i}. {result['symbol']} - Score: {result['score']}/100")
        
        return results
    
    def export_results(self, thesis_id: int, output_file: str = "thesis_analysis.csv"):
        """Export analysis results to CSV."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                symbol, thesis_name, alignment_score, rationale,
                current_price, market_cap, pe_ratio, dividend_yield,
                year_performance, analysis_date
            FROM thesis_alignments
            WHERE thesis_id = ?
            ORDER BY alignment_score DESC
        """, (thesis_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print(f"No results found for thesis_id {thesis_id}")
            return
        
        # Write CSV
        import csv
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Symbol', 'Thesis', 'Score', 'Rationale', 'Price', 
                'Market Cap', 'P/E Ratio', 'Div Yield %', 'YTD %', 'Date'
            ])
            
            for row in rows:
                # Format numeric values
                formatted_row = [
                    row[0],  # symbol
                    row[1],  # thesis_name
                    f"{row[2]:.2f}",  # score
                    row[3],  # rationale
                    f"${row[4]:.2f}" if row[4] else 'N/A',  # price
                    f"${row[5]:,.0f}" if row[5] else 'N/A',  # market_cap
                    f"{row[6]:.2f}" if row[6] else 'N/A',  # pe_ratio
                    f"{row[7]*100:.2f}%" if row[7] else 'N/A',  # div_yield
                    f"{row[8]:.2f}%" if row[8] else 'N/A',  # year_perf
                    row[9]  # date
                ]
                writer.writerow(formatted_row)
        
        print(f"\n[OK] Results exported to: {output_file}")


def main():
    """Demo of autonomous equity analyst."""
    
    # Initialize analyst
    analyst = AutonomousEquityAnalyst(db_path="securities_autonomous.db")
    
    # Example investment thesis
    thesis = {
        'id': 1,
        'name': 'Small & Mid-Cap Revival',
        'description': 'Small and mid-cap stocks positioned for growth as interest rates stabilize',
        'keywords': ['small cap', 'mid cap', 'growth', 'value'],
        'sectors': ['Technology', 'Healthcare', 'Financial Services']
    }
    
    # Analyze thesis
    results = analyst.analyze_thesis(thesis, max_securities=15)
    
    # Export results
    analyst.export_results(thesis_id=1, output_file="autonomous_analysis.csv")
    
    print("\n" + "="*60)
    print("[OK] Autonomous analysis complete!")
    print("="*60)


if __name__ == "__main__":
    main()
