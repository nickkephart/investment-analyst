#!/usr/bin/env python3
"""
Equity/Security Analyst Agent
Maps investment theses to relevant equities and ETFs, then ranks them by thesis alignment.

Features:
- Rate-limited API calls (5 calls/min for Massive.com)
- Persistent database of securities by thesis
- Multi-source discovery: web search, Massive.com, ticker databases
- Alignment scoring for thesis relevance
- Incremental updates (doesn't restart from scratch)
"""

import json
import time
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field, asdict
from collections import deque
import sqlite3


# === DATA STRUCTURES ===

@dataclass
class Security:
    """Represents an equity or ETF"""
    ticker: str
    name: str
    asset_type: str  # 'stock' or 'etf'
    exchange: str = ""
    market_cap: Optional[float] = None
    sector: str = ""
    industry: str = ""
    description: str = ""
    discovered_via: str = ""  # 'web_search', 'massive', 'manual', etc.
    discovered_date: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Performance metrics
    current_price: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    pct_from_52w_high: Optional[float] = None
    pct_from_52w_low: Optional[float] = None
    return_1y: Optional[float] = None
    return_3m: Optional[float] = None
    return_1m: Optional[float] = None
    return_ytd: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    avg_volume: Optional[float] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ThesisAlignment:
    """Represents how well a security aligns with a thesis"""
    thesis_id: str
    thesis_title: str
    ticker: str
    alignment_score: float  # 0-10 scale
    alignment_rationale: str
    key_exposure_factors: List[str] = field(default_factory=list)
    revenue_exposure_pct: Optional[float] = None  # Estimated % of revenue from thesis theme
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self):
        return asdict(self)


# === RATE LIMITER ===

class RateLimiter:
    """Rate limiter for API calls - 5 calls per minute for Massive.com"""
    
    def __init__(self, max_calls: int = 5, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window  # seconds
        self.call_times = deque()
    
    def wait_if_needed(self):
        """Block if rate limit would be exceeded"""
        now = time.time()
        
        # Remove calls outside the time window
        while self.call_times and self.call_times[0] < now - self.time_window:
            self.call_times.popleft()
        
        # If at limit, wait until oldest call expires
        if len(self.call_times) >= self.max_calls:
            sleep_time = self.time_window - (now - self.call_times[0]) + 1
            if sleep_time > 0:
                print(f"â³ Rate limit: waiting {sleep_time:.1f}s before next call...")
                time.sleep(sleep_time)
                # Clean up after waiting
                now = time.time()
                while self.call_times and self.call_times[0] < now - self.time_window:
                    self.call_times.popleft()
        
        # Record this call
        self.call_times.append(time.time())


# === DATABASE MANAGER ===

class SecurityDatabase:
    """SQLite database for persistent storage of securities and alignments"""
    
    def __init__(self, db_path: str = "/home/claude/securities.db"):
        self.db_path = db_path
        self.conn = None
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Securities table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS securities (
                ticker TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                exchange TEXT,
                market_cap REAL,
                sector TEXT,
                industry TEXT,
                description TEXT,
                discovered_via TEXT,
                discovered_date TEXT,
                last_updated TEXT,
                current_price REAL,
                week_52_high REAL,
                week_52_low REAL,
                pct_from_52w_high REAL,
                pct_from_52w_low REAL,
                return_1y REAL,
                return_3m REAL,
                return_1m REAL,
                return_ytd REAL,
                pe_ratio REAL,
                dividend_yield REAL,
                avg_volume REAL
            )
        """)
        
        # Thesis alignments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thesis_alignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thesis_id TEXT NOT NULL,
                thesis_title TEXT NOT NULL,
                ticker TEXT NOT NULL,
                alignment_score REAL NOT NULL,
                alignment_rationale TEXT,
                key_exposure_factors TEXT,
                revenue_exposure_pct REAL,
                last_updated TEXT,
                FOREIGN KEY (ticker) REFERENCES securities(ticker),
                UNIQUE(thesis_id, ticker)
            )
        """)
        
        # Discovery queue table (for tracking what needs analysis)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discovery_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thesis_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                added_date TEXT,
                UNIQUE(thesis_id, ticker)
            )
        """)
        
        self.conn.commit()
    
    def add_security(self, security: Security):
        """Add or update a security"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO securities 
            (ticker, name, asset_type, exchange, market_cap, sector, industry, 
             description, discovered_via, discovered_date, last_updated,
             current_price, week_52_high, week_52_low, pct_from_52w_high, pct_from_52w_low,
             return_1y, return_3m, return_1m, return_ytd, pe_ratio, dividend_yield, avg_volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            security.ticker, security.name, security.asset_type, security.exchange,
            security.market_cap, security.sector, security.industry, security.description,
            security.discovered_via, security.discovered_date, datetime.now().isoformat(),
            security.current_price, security.week_52_high, security.week_52_low,
            security.pct_from_52w_high, security.pct_from_52w_low,
            security.return_1y, security.return_3m, security.return_1m, security.return_ytd,
            security.pe_ratio, security.dividend_yield, security.avg_volume
        ))
        self.conn.commit()
    
    def add_alignment(self, alignment: ThesisAlignment):
        """Add or update a thesis alignment"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO thesis_alignments 
            (thesis_id, thesis_title, ticker, alignment_score, alignment_rationale,
             key_exposure_factors, revenue_exposure_pct, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alignment.thesis_id, alignment.thesis_title, alignment.ticker,
            alignment.alignment_score, alignment.alignment_rationale,
            json.dumps(alignment.key_exposure_factors), alignment.revenue_exposure_pct,
            alignment.last_updated
        ))
        self.conn.commit()
    
    def get_securities_for_thesis(self, thesis_id: str) -> List[Dict]:
        """Get all securities aligned with a thesis"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT s.*, ta.alignment_score, ta.alignment_rationale, 
                   ta.key_exposure_factors, ta.revenue_exposure_pct
            FROM securities s
            JOIN thesis_alignments ta ON s.ticker = ta.ticker
            WHERE ta.thesis_id = ?
            ORDER BY ta.alignment_score DESC
        """, (thesis_id,))
        
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result['key_exposure_factors'] = json.loads(result['key_exposure_factors']) if result['key_exposure_factors'] else []
            results.append(result)
        return results
    
    def get_thesis_summary(self, thesis_id: str) -> Dict:
        """Get summary statistics for a thesis"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_securities,
                AVG(alignment_score) as avg_score,
                COUNT(CASE WHEN alignment_score >= 8 THEN 1 END) as high_alignment,
                COUNT(CASE WHEN alignment_score BETWEEN 5 AND 7.99 THEN 1 END) as medium_alignment,
                COUNT(CASE WHEN alignment_score < 5 THEN 1 END) as low_alignment
            FROM thesis_alignments
            WHERE thesis_id = ?
        """, (thesis_id,))
        return dict(cursor.fetchone())
    
    def security_exists(self, ticker: str) -> bool:
        """Check if security already in database"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM securities WHERE ticker = ?", (ticker,))
        return cursor.fetchone() is not None
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


# === SECURITY DISCOVERY ENGINE ===

class SecurityDiscovery:
    """Discovers securities relevant to a thesis using multiple sources"""
    
    def __init__(self, rate_limiter: RateLimiter, db: SecurityDatabase):
        self.rate_limiter = rate_limiter
        self.db = db
        self.discovered_tickers: Set[str] = set()
        self.web_search_func = None
        self.massive_funcs = None
    
    def set_web_search(self, func):
        """Set the web search function"""
        self.web_search_func = func
    
    def set_massive_funcs(self, list_tickers_func, get_details_func):
        """Set the Massive.com API functions"""
        self.massive_funcs = {
            'list_tickers': list_tickers_func,
            'get_ticker_details': get_details_func
        }
    
    def discover_from_web_search(self, thesis: Dict) -> List[Security]:
        """Discover securities via web search"""
        securities = []
        
        if not self.web_search_func:
            print(f"\nðŸ” Web search disabled (no function provided)")
            return securities
        
        # Build search queries based on thesis
        queries = self._build_search_queries(thesis)
        
        print(f"\nðŸ” Web search for thesis: {thesis['title']}")
        print(f"   Queries: {len(queries)}")
        
        for i, query in enumerate(queries[:3], 1):  # Limit to 3 searches
            print(f"   [{i}/3] Searching: {query[:60]}...")
            
            try:
                # Call web search
                results = self.web_search_func(query=query)
                
                tickers_found = []
                
                # Parse results for ticker mentions and company names
                for result in results:
                    # Get text content from result
                    text = ""
                    if isinstance(result, dict):
                        text = result.get('content', '') + ' ' + result.get('title', '')
                    elif hasattr(result, 'content'):
                        text = result.content
                    
                    # Extract tickers from text
                    tickers = self._extract_tickers_from_text(text)
                    
                    for ticker in tickers:
                        if ticker not in self.discovered_tickers:
                            securities.append(Security(
                                ticker=ticker,
                                name=self._extract_company_name(text, ticker),
                                asset_type='stock',
                                discovered_via='web_search',
                                description=text[:200]  # Store snippet
                            ))
                            self.discovered_tickers.add(ticker)
                            tickers_found.append(ticker)
                
                print(f"      Found {len(tickers_found)} tickers: {', '.join(tickers_found[:5])}")
                
            except Exception as e:
                print(f"      âš ï¸  Search error: {e}")
                continue
        
        return securities
    
    def discover_from_massive(self, thesis: Dict) -> List[Security]:
        """Discover securities using Massive.com ticker search and market data"""
        securities = []
        
        if not self.massive_funcs:
            print(f"\nðŸ“Š Massive.com search disabled (no functions provided)")
            return securities
        
        # Extract key terms from thesis for ticker search
        search_terms = self._extract_search_terms(thesis)
        
        print(f"\nðŸ“Š Massive.com search for thesis: {thesis['title']}")
        print(f"   Search terms: {', '.join(search_terms[:5])}")
        
        list_tickers = self.massive_funcs.get('list_tickers')
        get_details = self.massive_funcs.get('get_ticker_details')
        
        if not list_tickers or not get_details:
            print("   âš ï¸  Massive.com functions not properly configured")
            return securities
        
        for i, term in enumerate(search_terms[:10], 1):  # Limit searches
            self.rate_limiter.wait_if_needed()
            
            print(f"   [{i}/10] Searching tickers for: {term}")
            
            try:
                # Search for tickers matching term
                results = list_tickers(
                    search=term,
                    active=True,
                    limit=5
                )
                
                if not results or not hasattr(results, 'results'):
                    print(f"      No results found")
                    continue
                
                ticker_list = results.results if hasattr(results, 'results') else results
                print(f"      Found {len(ticker_list)} tickers")
                
                # Get details for each ticker
                for ticker_data in ticker_list[:3]:  # Limit to top 3 per search
                    ticker = ticker_data.ticker if hasattr(ticker_data, 'ticker') else ticker_data.get('ticker')
                    
                    if not ticker or ticker in self.discovered_tickers:
                        continue
                    
                    # Get detailed information
                    self.rate_limiter.wait_if_needed()
                    
                    try:
                        details = get_details(ticker=ticker)
                        
                        securities.append(Security(
                            ticker=ticker,
                            name=details.name if hasattr(details, 'name') else details.get('name', ticker),
                            asset_type='stock',
                            exchange=details.primary_exchange if hasattr(details, 'primary_exchange') else details.get('primary_exchange', ''),
                            market_cap=details.market_cap if hasattr(details, 'market_cap') else details.get('market_cap'),
                            sector=details.sic_description if hasattr(details, 'sic_description') else details.get('sic_description', ''),
                            description=details.description if hasattr(details, 'description') else details.get('description', ''),
                            discovered_via='massive'
                        ))
                        self.discovered_tickers.add(ticker)
                        
                    except Exception as e:
                        print(f"      âš ï¸  Error getting details for {ticker}: {e}")
                        continue
                
            except Exception as e:
                print(f"      âš ï¸  Search error: {e}")
                continue
        
        return securities
    
    def discover_from_thesis_examples(self, thesis: Dict) -> List[Security]:
        """Extract securities mentioned in thesis sub-theses"""
        securities = []
        
        print(f"\nðŸ“ Extracting mentioned securities from thesis: {thesis['title']}")
        
        # Parse sub_theses for mentioned companies/tickers
        if 'sub_theses' in thesis:
            for sub_thesis in thesis['sub_theses']:
                if 'specific_opportunities' in sub_thesis:
                    for opp in sub_thesis['specific_opportunities']:
                        # Extract tickers/company names
                        tickers = self._extract_tickers_from_text(opp)
                        for ticker in tickers:
                            if ticker not in self.discovered_tickers:
                                securities.append(Security(
                                    ticker=ticker,
                                    name=self._extract_company_name(opp, ticker),
                                    asset_type='stock',  # Default, will refine
                                    discovered_via='thesis_mention'
                                ))
                                self.discovered_tickers.add(ticker)
        
        print(f"   Found {len(securities)} securities mentioned in thesis")
        return securities
    
    def _build_search_queries(self, thesis: Dict) -> List[str]:
        """Build search queries from thesis"""
        queries = []
        title = thesis['title'].split(':', 1)[-1].strip()
        
        queries.append(f"top stocks ETFs {title} 2026")
        queries.append(f"best companies investing {title}")
        queries.append(f"publicly traded {title} exposure")
        
        return queries
    
    def _extract_search_terms(self, thesis: Dict) -> List[str]:
        """Extract key terms for Massive.com ticker search"""
        terms = []
        
        # Extract from title
        title_words = thesis['title'].split()
        terms.extend([w for w in title_words if len(w) > 4 and w.isalpha()])
        
        # Extract from sub-thesis asset classes
        if 'sub_theses' in thesis:
            for sub in thesis['sub_theses']:
                if 'asset_class' in sub:
                    terms.extend(sub['asset_class'].split())
        
        return list(set(terms))[:20]  # Dedupe and limit
    
    def _extract_tickers_from_text(self, text: str) -> List[str]:
        """Extract potential ticker symbols from text"""
        import re
        
        # Common patterns for ticker mentions
        # "Microsoft (MSFT)", "NVDA", "Alphabet (GOOGL)"
        tickers = []
        
        # Pattern 1: Parentheses pattern - Company (TICK)
        pattern1 = r'\(([A-Z]{1,5})\)'
        matches1 = re.findall(pattern1, text)
        tickers.extend(matches1)
        
        # Pattern 2: Standalone tickers (2-5 uppercase letters)
        # But be careful not to match acronyms like "AI", "US", "CEO"
        pattern2 = r'\b([A-Z]{3,5})\b'
        matches2 = re.findall(pattern2, text)
        # Filter common acronyms
        exclude = {'AI', 'US', 'CEO', 'CFO', 'CTO', 'GDP', 'EPS', 'FCF', 'ROI', 'ROE', 'ETF', 'REIT', 'IPO', 'M&A'}
        tickers.extend([m for m in matches2 if m not in exclude])
        
        return list(set(tickers))
    
    def _extract_company_name(self, text: str, ticker: str) -> str:
        """Extract company name from text near ticker"""
        import re
        
        # Look for name before ticker in parentheses
        pattern = r'([A-Z][a-zA-Z\s&]+)\s*\(' + re.escape(ticker) + r'\)'
        match = re.search(pattern, text)
        
        if match:
            return match.group(1).strip()
        
        return ticker  # Fallback to ticker


# === ALIGNMENT SCORER ===

class AlignmentScorer:
    """Scores how well securities align with a thesis"""
    
    def __init__(self, rate_limiter: RateLimiter, alpha_vantage_client=None, yahoo_finance_client=None):
        self.rate_limiter = rate_limiter
        self.alpha_vantage = alpha_vantage_client
        self.yahoo_finance = yahoo_finance_client
    
    def score_alignment(self, security: Security, thesis: Dict) -> ThesisAlignment:
        """Score a security's alignment with a thesis"""
        
        print(f"   Scoring {security.ticker} for thesis alignment...")
        
        # Get company details from security object
        company_details = self._get_company_details(security.ticker, security)
        
        # Calculate alignment score based on multiple factors
        score = 0.0
        rationale_parts = []
        exposure_factors = []
        
        # Factor 1: Direct mention in thesis (2 points)
        if self._mentioned_in_thesis(security, thesis):
            score += 2.0
            rationale_parts.append("Explicitly mentioned in thesis")
            exposure_factors.append("Direct thesis mention")
        
        # Factor 2: Business description alignment (3 points)
        business_score, business_rationale = self._score_business_description(
            company_details, thesis
        )
        score += business_score
        if business_rationale:
            rationale_parts.append(business_rationale)
            if business_score > 0:
                exposure_factors.append("Business model alignment")
        
        # Factor 3: Revenue exposure (3 points)
        revenue_score, revenue_pct = self._estimate_revenue_exposure(
            company_details, thesis
        )
        score += revenue_score
        if revenue_score > 0:
            rationale_parts.append(f"~{revenue_pct:.0f}% revenue exposure estimated")
            exposure_factors.append(f"Revenue exposure: {revenue_pct:.0f}%")
        
        # Factor 4: Industry/sector alignment (2 points)
        sector_score = self._score_sector_alignment(company_details, thesis)
        score += sector_score
        if sector_score > 0:
            rationale_parts.append("Industry sector alignment")
            exposure_factors.append("Sector classification match")
        
        # Factor 5: Price momentum (2 points) - NEW with Yahoo Finance
        if self.yahoo_finance and self.yahoo_finance.is_available():
            momentum_score, momentum_rationale = self._calculate_momentum_score(security.ticker)
            score += momentum_score
            if momentum_score > 0 and momentum_rationale:
                rationale_parts.append(momentum_rationale)
                exposure_factors.append("Price momentum")
        
        # Factor 6: Dividend quality (2 points) - NEW with Yahoo Finance (income theses only)
        if self.yahoo_finance and self.yahoo_finance.is_available():
            dividend_score, dividend_rationale = self._score_dividend_quality(security.ticker, thesis)
            score += dividend_score
            if dividend_score > 0 and dividend_rationale:
                rationale_parts.append(dividend_rationale)
                exposure_factors.append("Dividend quality")
        
        # Total possible: 14 points (2 + 3 + 3 + 2 + 2 + 2)
        # Scale to 10 points for consistency
        max_possible_score = 14.0
        scaled_score = (score / max_possible_score) * 10.0
        
        # Create alignment object
        alignment = ThesisAlignment(
            thesis_id=thesis.get('id', thesis['title']),
            thesis_title=thesis['title'],
            ticker=security.ticker,
            alignment_score=round(scaled_score, 2),
            alignment_rationale="; ".join(rationale_parts) if rationale_parts else "Limited alignment found",
            key_exposure_factors=exposure_factors,
            revenue_exposure_pct=revenue_pct if revenue_score > 0 else None
        )
        
        return alignment
    
    def _get_company_details(self, ticker: str, security: Security = None) -> Dict:
        """Get company details from Alpha Vantage or security object"""
        
        # Try Alpha Vantage first if available
        if self.alpha_vantage:
            try:
                print(f"      ðŸ” Fetching from Alpha Vantage...")
                overview = self.alpha_vantage.get_company_overview(ticker)
                
                if overview:
                    return {
                        'ticker': overview.get('Symbol', ticker),
                        'name': overview.get('Name', ticker),
                        'description': overview.get('Description', ''),
                        'sector': overview.get('Sector', ''),
                        'industry': overview.get('Industry', ''),
                        'market_cap': float(overview.get('MarketCapitalization', 0)) if overview.get('MarketCapitalization') else None,
                        'exchange': overview.get('Exchange', '')
                    }
            except Exception as e:
                print(f"      âš ï¸  Alpha Vantage error: {e}")
                print(f"      ðŸ“ Falling back to security object data...")
        
        # Fall back to security object if provided
        if security:
            return {
                'ticker': security.ticker,
                'name': security.name,
                'description': security.description,
                'sector': security.sector,
                'industry': security.industry,
                'market_cap': security.market_cap,
                'exchange': security.exchange
            }
        
        # Otherwise return minimal info
        return {
            'ticker': ticker,
            'name': ticker,
            'description': '',
            'sector': '',
            'industry': '',
            'market_cap': None,
            'exchange': ''
        }
    
    def _mentioned_in_thesis(self, security: Security, thesis: Dict) -> bool:
        """Check if security explicitly mentioned in thesis"""
        thesis_text = json.dumps(thesis).upper()
        return security.ticker.upper() in thesis_text
    
    def _score_business_description(self, details: Dict, thesis: Dict) -> tuple:
        """Score based on business description alignment (0-3 points)"""
        
        # If no description available, return low score
        if not details.get('description'):
            return 0.5, "Limited business information available"
        
        # Build analysis prompt for LLM
        company_info = f"""
Company: {details.get('name', details.get('ticker', 'Unknown'))}
Ticker: {details.get('ticker')}
Sector: {details.get('sector', 'Unknown')}
Industry: {details.get('industry', 'Unknown')}
Description: {details['description'][:500]}
"""
        
        thesis_info = f"""
Thesis Title: {thesis.get('title', 'Unknown')}
Summary: {thesis.get('summary', '')[:300]}
"""
        
        # Use simple keyword matching as fallback if LLM not available
        # Extract key themes from thesis
        thesis_text = (thesis.get('title', '') + ' ' + thesis.get('summary', '')).lower()
        description = details['description'].lower()
        
        # Count keyword matches
        keywords = []
        if 'ai' in thesis_text or 'artificial intelligence' in thesis_text:
            keywords.extend(['ai', 'artificial intelligence', 'machine learning', 'gpu', 'data center', 'cloud', 'neural'])
        if 'semiconductor' in thesis_text or 'chip' in thesis_text:
            keywords.extend(['semiconductor', 'chip', 'processor', 'fabrication', 'wafer'])
        if 'infrastructure' in thesis_text:
            keywords.extend(['infrastructure', 'data center', 'colocation', 'hosting', 'connectivity'])
        if 'power' in thesis_text or 'energy' in thesis_text or 'utility' in thesis_text:
            keywords.extend(['power', 'energy', 'utility', 'electric', 'generation', 'transmission'])
        if 'defense' in thesis_text or 'military' in thesis_text:
            keywords.extend(['defense', 'military', 'aerospace', 'weapons', 'combat'])
        if 'china' in thesis_text:
            keywords.extend(['china', 'chinese', 'asia', 'export'])
        if 'inflation' in thesis_text or 'commodity' in thesis_text:
            keywords.extend(['commodity', 'gold', 'copper', 'lithium', 'mining', 'resources'])
        if 'housing' in thesis_text or 'real estate' in thesis_text:
            keywords.extend(['housing', 'residential', 'apartment', 'reit', 'multifamily', 'rental'])
        
        # Score based on keyword density
        matches = sum(1 for kw in keywords if kw in description)
        keyword_density = matches / max(len(keywords), 1) if keywords else 0
        
        # Scoring rubric
        if keyword_density >= 0.4:  # 40%+ keywords match
            score = 3.0
            rationale = "Strong business model alignment - core business directly addresses thesis"
        elif keyword_density >= 0.25:  # 25-40% keywords match
            score = 2.5
            rationale = "High business model alignment - significant operations in thesis area"
        elif keyword_density >= 0.15:  # 15-25% keywords match
            score = 2.0
            rationale = "Meaningful business model alignment - substantial exposure to thesis theme"
        elif keyword_density >= 0.08:  # 8-15% keywords match
            score = 1.5
            rationale = "Moderate business model alignment - some operations related to thesis"
        elif keyword_density >= 0.04:  # 4-8% keywords match
            score = 1.0
            rationale = "Limited business model alignment - tangential exposure to thesis"
        else:
            score = 0.5
            rationale = "Minimal business model alignment - limited relevance to thesis"
        
        return score, rationale
    
    def _estimate_revenue_exposure(self, details: Dict, thesis: Dict) -> tuple:
        """Estimate revenue exposure percentage (0-3 points, 0-100% exposure)"""
        
        # Extract key information
        company_desc = details.get('description', '').lower()
        company_name = details.get('name', '').lower()
        sector = details.get('sector', '').lower()
        thesis_text = (thesis.get('title', '') + ' ' + thesis.get('summary', '')).lower()
        
        # Default estimates based on context clues
        exposure_pct = 0.0
        
        # Analyze thesis theme
        theme_keywords = {
            'ai_infrastructure': ['ai', 'artificial intelligence', 'data center', 'gpu'],
            'semiconductor': ['semiconductor', 'chip'],
            'power': ['power', 'utility', 'energy', 'electric'],
            'defense': ['defense', 'military', 'aerospace'],
            'real_estate': ['real estate', 'reit', 'housing'],
            'china': ['china', 'chinese'],
            'commodities': ['commodity', 'mining', 'copper', 'lithium', 'gold']
        }
        
        # Detect primary thesis theme
        primary_theme = None
        for theme, keywords in theme_keywords.items():
            if any(kw in thesis_text for kw in keywords):
                primary_theme = theme
                break
        
        if not primary_theme:
            return 1.0, 20.0  # Default for unrecognized themes
        
        # Estimate exposure based on company type and theme
        
        # AI Infrastructure theme
        if primary_theme == 'ai_infrastructure':
            if 'nvidia' in company_name or 'nvda' in company_desc:
                exposure_pct = 85.0  # Data center + gaming GPUs
            elif 'amd' in company_name or ('advanced micro' in company_name):
                exposure_pct = 60.0  # MI series + EPYC
            elif 'data center' in company_desc and 'reit' in sector:
                exposure_pct = 75.0  # Data center REITs
            elif 'semiconductor' in sector and any(kw in company_desc for kw in ['gpu', 'ai', 'accelerator']):
                exposure_pct = 70.0  # AI-focused semiconductor
            elif 'semiconductor' in sector:
                exposure_pct = 40.0  # General semiconductor
            elif 'cloud' in company_desc or 'azure' in company_desc:
                exposure_pct = 35.0  # Cloud providers
            elif 'utility' in sector and 'data center' in company_desc:
                exposure_pct = 25.0  # Utilities serving data centers
            elif 'utility' in sector:
                exposure_pct = 8.0  # General utilities
            else:
                exposure_pct = 15.0  # Default
        
        # Semiconductor theme
        elif primary_theme == 'semiconductor':
            if 'fabrication' in company_desc or 'foundry' in company_desc:
                exposure_pct = 90.0  # Pure play foundries
            elif 'lithography' in company_desc or 'asml' in company_name:
                exposure_pct = 95.0  # Lithography equipment
            elif 'semiconductor' in sector:
                exposure_pct = 80.0  # Semiconductor companies
            elif 'equipment' in company_desc and 'semiconductor' in company_desc:
                exposure_pct = 85.0  # Semiconductor equipment
            else:
                exposure_pct = 20.0
        
        # Defense theme
        elif primary_theme == 'defense':
            if 'defense' in sector or 'aerospace' in sector:
                exposure_pct = 70.0
            elif 'military' in company_desc:
                exposure_pct = 60.0
            elif 'government' in company_desc and 'contractor' in company_desc:
                exposure_pct = 50.0
            else:
                exposure_pct = 15.0
        
        # Power/Utility theme
        elif primary_theme == 'power':
            if 'renewable' in company_desc or 'clean energy' in company_desc:
                exposure_pct = 80.0
            elif 'utility' in sector or 'electric' in sector:
                exposure_pct = 90.0
            elif 'power generation' in company_desc:
                exposure_pct = 85.0
            elif 'natural gas' in company_desc and 'lng' in company_desc:
                exposure_pct = 75.0
            else:
                exposure_pct = 30.0
        
        # Real Estate/Housing theme
        elif primary_theme == 'real_estate':
            if 'reit' in sector:
                exposure_pct = 95.0
            elif 'residential' in company_desc or 'multifamily' in company_desc:
                exposure_pct = 85.0
            elif 'homebuilder' in company_desc or 'housing' in company_desc:
                exposure_pct = 90.0
            else:
                exposure_pct = 25.0
        
        # China theme
        elif primary_theme == 'china':
            if 'china' in company_desc or 'chinese' in company_desc:
                exposure_pct = 80.0
            elif 'asia' in company_desc or 'hong kong' in company_desc:
                exposure_pct = 60.0
            else:
                exposure_pct = 20.0
        
        # Commodities theme
        elif primary_theme == 'commodities':
            if 'mining' in company_desc or 'miner' in company_desc:
                exposure_pct = 90.0
            elif any(metal in company_desc for metal in ['copper', 'lithium', 'gold', 'silver']):
                exposure_pct = 85.0
            elif 'resources' in company_desc or 'materials' in sector:
                exposure_pct = 70.0
            else:
                exposure_pct = 15.0
        
        # Convert exposure percentage to score (0-3 points)
        # 90%+ = 3.0, 70-89% = 2.5, 50-69% = 2.0, 30-49% = 1.5, 10-29% = 1.0, <10% = 0.5
        if exposure_pct >= 90:
            score = 3.0
        elif exposure_pct >= 70:
            score = 2.5
        elif exposure_pct >= 50:
            score = 2.0
        elif exposure_pct >= 30:
            score = 1.5
        elif exposure_pct >= 10:
            score = 1.0
        else:
            score = 0.5
        
        return score, exposure_pct
    
    def _score_sector_alignment(self, details: Dict, thesis: Dict) -> float:
        """Score sector/industry alignment (0-2 points)"""
        
        sector = details.get('sector', '').lower()
        industry = details.get('industry', '').lower()
        thesis_text = (thesis.get('title', '') + ' ' + thesis.get('summary', '')).lower()
        
        # Define sector mappings for common thesis themes
        sector_matches = {
            'ai_infrastructure': {
                'perfect': ['semiconductors', 'semiconductor', 'technology hardware', 'data centers', 'reits'],
                'good': ['software', 'technology', 'electric utilities', 'utilities'],
                'related': ['communications', 'telecommunications']
            },
            'semiconductor': {
                'perfect': ['semiconductors', 'semiconductor', 'semiconductor equipment'],
                'good': ['technology hardware', 'electronics'],
                'related': ['materials', 'industrial']
            },
            'power_energy': {
                'perfect': ['electric utilities', 'utilities', 'renewable energy', 'independent power'],
                'good': ['oil & gas', 'energy', 'power generation'],
                'related': ['industrial', 'infrastructure']
            },
            'defense': {
                'perfect': ['aerospace & defense', 'defense', 'military'],
                'good': ['industrial', 'aerospace'],
                'related': ['technology', 'communications']
            },
            'real_estate': {
                'perfect': ['reits', 'real estate', 'residential', 'homebuilders'],
                'good': ['construction', 'building materials'],
                'related': ['financial', 'mortgage']
            },
            'financial': {
                'perfect': ['banks', 'financial services', 'insurance', 'asset management'],
                'good': ['credit', 'lending', 'investment'],
                'related': ['real estate', 'fintech']
            },
            'china_tech': {
                'perfect': ['technology', 'internet', 'e-commerce', 'software'],
                'good': ['telecommunications', 'media', 'semiconductors'],
                'related': ['consumer', 'automotive']
            },
            'commodities': {
                'perfect': ['mining', 'metals & mining', 'gold', 'materials'],
                'good': ['basic materials', 'resources', 'oil & gas'],
                'related': ['energy', 'industrial']
            }
        }
        
        # Detect thesis theme
        thesis_theme = None
        if any(kw in thesis_text for kw in ['ai', 'data center', 'gpu', 'semiconductor']):
            thesis_theme = 'ai_infrastructure'
        elif 'semiconductor' in thesis_text or 'chip' in thesis_text:
            thesis_theme = 'semiconductor'
        elif any(kw in thesis_text for kw in ['power', 'utility', 'energy', 'electric']):
            thesis_theme = 'power_energy'
        elif 'defense' in thesis_text or 'military' in thesis_text:
            thesis_theme = 'defense'
        elif 'real estate' in thesis_text or 'housing' in thesis_text or 'reit' in thesis_text:
            thesis_theme = 'real_estate'
        elif any(kw in thesis_text for kw in ['bank', 'financial', 'credit', 'private equity']):
            thesis_theme = 'financial'
        elif 'china' in thesis_text or 'chinese' in thesis_text:
            thesis_theme = 'china_tech'
        elif any(kw in thesis_text for kw in ['commodity', 'mining', 'copper', 'lithium', 'gold']):
            thesis_theme = 'commodities'
        
        if not thesis_theme:
            return 1.0  # Default when theme unclear
        
        # Check sector alignment
        theme_sectors = sector_matches.get(thesis_theme, {})
        
        # Perfect match (2.0 points)
        for perfect_sector in theme_sectors.get('perfect', []):
            if perfect_sector in sector or perfect_sector in industry:
                return 2.0
        
        # Good match (1.5 points)
        for good_sector in theme_sectors.get('good', []):
            if good_sector in sector or good_sector in industry:
                return 1.5
        
        # Related match (1.0 point)
        for related_sector in theme_sectors.get('related', []):
            if related_sector in sector or related_sector in industry:
                return 1.0
        
        # No meaningful match
        return 0.3
    
    def _calculate_momentum_score(self, ticker: str) -> tuple:
        """
        Calculate price momentum score using Yahoo Finance historical data
        Returns (score 0-2 pts, rationale string)
        
        Analyzes:
        - Position relative to 52-week high/low
        - Trend strength (50-day vs 200-day moving average)
        """
        if not self.yahoo_finance or not self.yahoo_finance.is_available():
            return 0.0, "Momentum data unavailable"
        
        try:
            # Get 1-year historical data
            hist_data = self.yahoo_finance.get_stock_historical_prices(
                symbol=ticker,
                period="1y",
                interval="1d"
            )
            
            if not hist_data or len(hist_data['data']) < 50:
                return 0.0, "Insufficient price history"
            
            prices = [d['close'] for d in hist_data['data']]
            current_price = prices[-1]
            
            # Calculate 52-week high/low
            high_52w = max(prices)
            low_52w = min(prices)
            price_range = high_52w - low_52w
            
            if price_range == 0:
                return 0.0, "No price movement"
            
            # Position score (0-1 pt)
            # How close to 52-week high vs low
            position = (current_price - low_52w) / price_range
            position_score = position  # 1.0 if at highs, 0.0 if at lows
            
            # Trend score (0-1 pt)
            # Compare 50-day moving average to 200-day moving average
            if len(prices) >= 200:
                avg_50d = sum(prices[-50:]) / 50
                avg_200d = sum(prices) / len(prices)
                
                if avg_50d > avg_200d * 1.02:  # 2% above = strong uptrend
                    trend_score = 1.0
                elif avg_50d > avg_200d:  # Above = uptrend
                    trend_score = 0.75
                elif avg_50d > avg_200d * 0.98:  # Near = consolidation
                    trend_score = 0.5
                else:  # Below = downtrend
                    trend_score = 0.25
            else:
                trend_score = 0.5  # Not enough data for trend
            
            total_score = position_score + trend_score
            
            # Build rationale
            position_pct = position * 100
            if position > 0.90:
                position_desc = f"near 52-week high ({position_pct:.0f}% of range)"
            elif position > 0.70:
                position_desc = f"in upper range ({position_pct:.0f}% of 52-week range)"
            elif position > 0.50:
                position_desc = f"mid-range ({position_pct:.0f}% of 52-week range)"
            elif position > 0.30:
                position_desc = f"in lower range ({position_pct:.0f}% of 52-week range)"
            else:
                position_desc = f"near 52-week low ({position_pct:.0f}% of range)"
            
            if trend_score >= 0.75:
                trend_desc = "strong uptrend"
            elif trend_score >= 0.5:
                trend_desc = "uptrending"
            else:
                trend_desc = "downtrending"
            
            rationale = f"Price momentum: {position_desc}, {trend_desc}"
            
            return round(total_score, 2), rationale
            
        except Exception as e:
            print(f"      âš ï¸  Error calculating momentum for {ticker}: {e}")
            return 0.0, "Momentum calculation error"
    
    def _score_dividend_quality(self, ticker: str, thesis: Dict) -> tuple:
        """
        Score dividend quality for income-focused theses
        Returns (score 0-2 pts, rationale string)
        
        Only applies to income/dividend theses
        Analyzes:
        - Dividend yield
        - Dividend growth rate
        - Payment consistency
        """
        if not self.yahoo_finance or not self.yahoo_finance.is_available():
            return 0.0, ""
        
        # Check if thesis is income-focused
        income_keywords = ['dividend', 'income', 'yield', 'payout', 'distribution', 'cash flow']
        thesis_text = (thesis.get('title', '') + ' ' + thesis.get('summary', '')).lower()
        
        is_income_thesis = any(kw in thesis_text for kw in income_keywords)
        
        if not is_income_thesis:
            return 0.0, ""  # Not relevant for growth theses
        
        try:
            # Get dividend data
            div_data = self.yahoo_finance.get_stock_dividend(ticker)
            
            if not div_data or not div_data.get('dividends'):
                return 0.0, "No dividend payments"
            
            dividend_yield = div_data.get('dividend_yield', 0)
            dividends = div_data['dividends']
            annual_dividend = div_data.get('annual_dividend', 0)
            
            # Yield score (0-1 pt)
            if dividend_yield > 0.04:  # >4% excellent
                yield_score = 1.0
                yield_desc = f"excellent {dividend_yield*100:.1f}% yield"
            elif dividend_yield > 0.03:  # 3-4% good
                yield_score = 0.75
                yield_desc = f"good {dividend_yield*100:.1f}% yield"
            elif dividend_yield > 0.02:  # 2-3% moderate
                yield_score = 0.5
                yield_desc = f"moderate {dividend_yield*100:.1f}% yield"
            elif dividend_yield > 0:  # <2% low
                yield_score = 0.25
                yield_desc = f"low {dividend_yield*100:.1f}% yield"
            else:
                yield_score = 0.0
                yield_desc = "no yield"
            
            # Growth score (0-1 pt)
            if len(dividends) >= 8:  # Need 2 years for growth calculation
                oldest_div = dividends[-1]['dividend']
                newest_div = dividends[0]['dividend']
                
                if oldest_div > 0:
                    growth_rate = (newest_div - oldest_div) / oldest_div
                    
                    if growth_rate > 0.10:  # >10% growth excellent
                        growth_score = 1.0
                        growth_desc = f"{growth_rate*100:.0f}% growth"
                    elif growth_rate > 0.05:  # 5-10% growth good
                        growth_score = 0.75
                        growth_desc = f"{growth_rate*100:.0f}% growth"
                    elif growth_rate > 0:  # Positive growth
                        growth_score = 0.5
                        growth_desc = f"{growth_rate*100:.0f}% growth"
                    else:  # Flat or declining
                        growth_score = 0.0
                        growth_desc = "declining"
                else:
                    growth_score = 0.0
                    growth_desc = "no growth data"
            else:
                growth_score = 0.0
                growth_desc = "limited history"
            
            total_score = yield_score + growth_score
            rationale = f"Dividend quality: {yield_desc}, {growth_desc}"
            
            return round(total_score, 2), rationale
            
        except Exception as e:
            print(f"      âš ï¸  Error scoring dividends for {ticker}: {e}")
            return 0.0, ""


# === MAIN ANALYST AGENT ===

class EquityAnalystAgent:
    """Main agent coordinating security discovery and alignment scoring"""
    
    def __init__(self, db_path: str = "/home/claude/securities.db", 
                 alpha_vantage_client=None,
                 yahoo_finance_client=None):
        self.db = SecurityDatabase(db_path)
        self.rate_limiter = RateLimiter(max_calls=5, time_window=60)
        self.discovery = SecurityDiscovery(self.rate_limiter, self.db)
        self.scorer = AlignmentScorer(self.rate_limiter, alpha_vantage_client, yahoo_finance_client)
        self.alpha_vantage = alpha_vantage_client
        self.yahoo_finance = yahoo_finance_client
    
    def set_alpha_vantage(self, client):
        """Set Alpha Vantage client for enhanced data"""
        self.alpha_vantage = client
        self.scorer.alpha_vantage = client
    
    def set_yahoo_finance(self, client):
        """Set Yahoo Finance client for momentum and dividend data"""
        self.yahoo_finance = client
        self.scorer.yahoo_finance = client
    
    def analyze_thesis(self, thesis: Dict, max_securities: int = 20, 
                      enable_web_search: bool = True, 
                      enable_massive: bool = True) -> Dict:
        """Analyze a thesis and discover/score relevant securities"""
        
        thesis_id = thesis.get('id', thesis['title'])
        
        print("=" * 80)
        print(f"EQUITY ANALYSIS FOR THESIS: {thesis['title']}")
        print("=" * 80)
        
        # Check if already analyzed
        existing = self.db.get_securities_for_thesis(thesis_id)
        if existing:
            print(f"\nâœ“ Found {len(existing)} existing securities for this thesis")
            print(f"  Continuing incremental analysis...")
        
        # Phase 1: Security Discovery
        print("\n" + "=" * 80)
        print("PHASE 1: SECURITY DISCOVERY")
        print("=" * 80)
        
        all_securities = []
        
        # Source 1: Thesis mentions (no API calls)
        securities_mentioned = self.discovery.discover_from_thesis_examples(thesis)
        all_securities.extend(securities_mentioned)
        
        # Source 2: Web search (if enabled)
        if enable_web_search:
            securities_web = self.discovery.discover_from_web_search(thesis)
            all_securities.extend(securities_web)
        
        # Source 3: Massive.com (if enabled)
        if enable_massive:
            securities_massive = self.discovery.discover_from_massive(thesis)
            all_securities.extend(securities_massive)
        
        # Deduplicate
        unique_securities = {s.ticker: s for s in all_securities}
        
        # Prioritize ETFs over individual stocks
        etfs = [s for s in unique_securities.values() if s.asset_type.lower() in ['etf', 'fund']]
        stocks = [s for s in unique_securities.values() if s.asset_type.lower() not in ['etf', 'fund']]
        
        # Combine with ETFs first, then limit
        securities_to_analyze = (etfs + stocks)[:max_securities]
        
        print(f"\nâœ“ Discovered {len(unique_securities)} unique securities ({len(etfs)} ETFs, {len(stocks)} stocks)")
        print(f"âœ“ Analyzing {len(securities_to_analyze)} securities (ETFs prioritized)")
        
        # Phase 2: Alignment Scoring
        print("\n" + "=" * 80)
        print("PHASE 2: ALIGNMENT SCORING")
        print("=" * 80)
        
        for i, security in enumerate(securities_to_analyze, 1):
            print(f"\n[{i}/{len(securities_to_analyze)}] Analyzing {security.ticker}...")
            
            # Save security to database
            self.db.add_security(security)
            
            # Score alignment
            alignment = self.scorer.score_alignment(security, thesis)
            self.db.add_alignment(alignment)
            
            print(f"   âœ“ Alignment score: {alignment.alignment_score}/10")
        
        # Generate summary
        summary = self.db.get_thesis_summary(thesis_id)
        securities = self.db.get_securities_for_thesis(thesis_id)
        
        result = {
            'thesis_id': thesis_id,
            'thesis_title': thesis['title'],
            'analysis_date': datetime.now().isoformat(),
            'summary': summary,
            'securities': securities[:20]  # Top 20 securities
        }
        
        return result
    
    def export_results(self, thesis_id: str, output_path: str):
        """Export analysis results to file"""
        securities = self.db.get_securities_for_thesis(thesis_id)
        summary = self.db.get_thesis_summary(thesis_id)
        
        output = {
            'thesis_id': thesis_id,
            'exported': datetime.now().isoformat(),
            'summary': summary,
            'securities': securities
        }
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nâœ“ Exported results to {output_path}")
    
    def close(self):
        """Clean up resources"""
        self.db.close()


# === BATCH PROCESSING FUNCTIONS FOR CLAUDE ===

"""
BATCH EQUITY ANALYST WORKFLOW:

Phase 1: DISCOVERY (Claude discovers all tickers)
--------------------------------------------------
Claude uses web_search and massive:list_tickers to discover ALL tickers upfront.
Returns: ['IWM', 'VTWO', 'VIOO', 'AVUV', 'SCHA', ...]

Phase 2: BATCH MCP ENRICHMENT (Claude makes ALL MCP calls in parallel)
-----------------------------------------------------------------------
For the list of tickers, Claude calls MCP tools for ALL tickers:
- massive:get_ticker_details(ticker) for each ticker
- yahoo-finance:get_current_stock_price(ticker) for each ticker
- yahoo-finance:get_historical_stock_prices(ticker, period='1y') for each ticker
- yahoo-finance:get_dividends(ticker) for each ticker

Returns: List of dicts with all MCP data combined

Phase 3: BATCH PROCESSING (Python processes everything at once)
----------------------------------------------------------------
Claude passes ALL enriched data to Python in ONE function call:
- batch_analyze_thesis(thesis_id, enriched_securities_data)
- Python processes all securities in one batch
- Generates complete output

This is 10-100x faster than sequential processing!
"""

def discover_tickers_for_thesis(thesis: Dict) -> Dict[str, Any]:
    """
    Generate discovery strategy for a thesis
    
    Analyzes thesis and returns MCP tool calls Claude should make.
    
    Args:
        thesis: Thesis dict with title, summary, key_themes
    
    Returns:
        {
            'web_search_queries': [...],
            'massive_searches': [...],
            'estimated_tickers': 15-25
        }
    """
    title = thesis.get('title', '')
    summary = thesis.get('summary', '')
    key_themes = thesis.get('key_themes', '')
    
    text = f"{title} {summary} {key_themes}".lower()
    
    web_queries = []
    massive_searches = []
    
    # Detect investment themes
    if 'small cap' in text or 'small-cap' in text or 'russell 2000' in text:
        web_queries.append('Russell 2000 ETF small cap')
        massive_searches.append({'search': 'Russell 2000', 'limit': 10, 'type': 'ETF'})
        massive_searches.append({'search': 'small cap', 'limit': 10, 'type': 'ETF'})
    
    if 'mid cap' in text or 'mid-cap' in text:
        web_queries.append('mid cap ETF S&P 400')
        massive_searches.append({'search': 'mid cap', 'limit': 10, 'type': 'ETF'})
    
    if 'value' in text:
        massive_searches.append({'search': 'value', 'limit': 8, 'type': 'ETF'})
    
    if 'growth' in text:
        massive_searches.append({'search': 'growth', 'limit': 8, 'type': 'ETF'})
    
    if 'dividend' in text or 'income' in text:
        web_queries.append('dividend ETF high yield')
        massive_searches.append({'search': 'dividend', 'limit': 10, 'type': 'ETF'})
    
    if 'international' in text or 'emerging' in text:
        massive_searches.append({'search': 'international', 'limit': 10, 'type': 'ETF'})
    
    # Fallback
    if not massive_searches:
        web_queries.append(f"ETF {title.split(':')[0][:40]}")
        massive_searches.append({'search': 'ETF', 'limit': 15, 'type': 'ETF'})
    
    return {
        'web_search_queries': web_queries[:2],
        'massive_searches': massive_searches[:4],
        'estimated_tickers': min(20, len(massive_searches) * 8)
    }


def create_analyst(db_path: str = "/mnt/project/securities.db"):
    """
    Create an equity analyst instance
    
    Args:
        db_path: Path to SQLite database
    
    Returns:
        EquityAnalystAgent instance
    """
    return EquityAnalystAgent(db_path=db_path)


def batch_analyze_thesis(
    thesis_number: int,
    mcp_data: Dict[str, Dict],
    db_path: str = "/mnt/project/securities.db"
) -> Dict:
    """
    Batch analyze securities for a thesis (MAIN ENTRY POINT)
    
    This is called by Claude after making ALL MCP calls in parallel.
    
    Args:
        thesis_number: Which thesis (1-15)
        mcp_data: Dictionary mapping ticker -> MCP results:
            {
                'IWM': {
                    'massive_details': {...},      # From massive:get_ticker_details
                    'yahoo_price': float,          # From yahoo-finance:get_current_stock_price
                    'yahoo_historical': {...},     # From yahoo-finance:get_historical_stock_prices
                    'yahoo_dividends': {...}       # From yahoo-finance:get_dividends
                },
                'VTWO': { ... },
                ...
            }
        db_path: Database path
    
    Returns:
        Analysis results dict with summary and output file path
    """
    
    # Load thesis
    theses_file = Path("/mnt/project/investment_theses_15_expanded_2026.json")
    with open(theses_file) as f:
        theses = json.load(f)['theses']
    
    if thesis_number < 1 or thesis_number > len(theses):
        raise ValueError(f'Invalid thesis number. Must be 1-{len(theses)}')
    
    thesis = theses[thesis_number - 1]
    thesis['id'] = f'thesis_{thesis_number}'
    
    print("=" * 80)
    print(f"BATCH EQUITY ANALYSIS - THESIS #{thesis_number}")
    print("=" * 80)
    print(f"\nTitle: {thesis['title']}")
    print(f"Securities to analyze: {len(mcp_data)}")
    print()
    
    # Create analyst with fresh database
    analyst = create_analyst(db_path)
    
    # Process all securities in batch
    securities_processed = 0
    
    for ticker, data in mcp_data.items():
        try:
            # Enrich with MCP data
            enriched = enrich_security_with_mcp_data(
                ticker=ticker,
                massive_details=data.get('massive_details'),
                yahoo_price=data.get('yahoo_price'),
                yahoo_historical=data.get('yahoo_historical'),
                yahoo_dividends=data.get('yahoo_dividends')
            )
            
            # Add to database
            security = Security(**enriched)
            analyst.db.add_security(security)
            
            # Score alignment
            alignment = analyst.scorer.score_alignment(security, thesis)
            analyst.db.add_alignment(alignment)
            
            securities_processed += 1
            print(f"  [{securities_processed:2d}] {ticker:6s} - Score: {alignment.alignment_score:.2f}/10 - {security.name[:50]}")
            
        except Exception as e:
            print(f"  [ERROR] {ticker}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Get results
    summary = analyst.db.get_thesis_summary(thesis['id'])
    securities = analyst.db.get_securities_for_thesis(thesis['id'])
    
    # Export to CSV
    output_path = f"/mnt/project/thesis_{thesis_number}_analysis.csv"
    _export_results(analyst, thesis['id'], output_path)
    
    analyst.db.close()
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"Securities analyzed: {securities_processed}")
    print(f"Average score: {summary.get('avg_score', 0):.2f}/10")
    print(f"High alignment (8-10): {summary.get('high_alignment', 0)}")
    print(f"Medium alignment (5-7.99): {summary.get('medium_alignment', 0)}")
    print(f"Low alignment (<5): {summary.get('low_alignment', 0)}")
    print(f"\nOutput: {output_path}")
    
    return {
        'thesis_id': thesis['id'],
        'thesis_title': thesis['title'],
        'securities_analyzed': securities_processed,
        'summary': summary,
        'top_securities': securities[:10],
        'output_file': output_path
    }


def _export_results(analyst: EquityAnalystAgent, thesis_id: str, output_path: str):
    """Export analysis results to CSV"""
    securities = analyst.db.get_securities_for_thesis(thesis_id)
    
    if not securities:
        print("No securities to export")
        return
    
    with open(output_path, 'w', newline='') as f:
        fieldnames = [
            'ticker', 'name', 'asset_type', 'exchange', 'sector',
            'current_price', 'market_cap', 'pe_ratio', 'dividend_yield',
            'week_52_high', 'week_52_low', 'return_1y', 'return_3m', 'return_1m',
            'pct_from_52w_high', 'pct_from_52w_low', 'avg_volume',
            'alignment_score', 'alignment_rationale', 'discovered_via'
        ]
        
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for sec in securities:
            # Handle both Security objects and dicts
            if hasattr(sec, '_asdict'):
                row = sec._asdict()
            elif isinstance(sec, dict):
                row = sec
            else:
                # Convert object to dict
                row = {k: getattr(sec, k, None) for k in fieldnames}
            
            writer.writerow(row)
    
    print(f"✓ Exported {len(securities)} securities to {output_path}")


def enrich_security_with_mcp_data(
    ticker: str,
    massive_details: Dict = None,
    yahoo_price: Any = None,  # Can be float or dict
    yahoo_historical: Any = None,  # Can be dict or list
    yahoo_dividends: Dict = None
) -> Dict:
    """
    Enrich a ticker with data from MCP tools
    
    Args:
        ticker: Stock ticker symbol
        massive_details: Result from massive:get_ticker_details
        yahoo_price: Result from yahoo-finance:get_current_stock_price (float or dict)
        yahoo_historical: Result from yahoo-finance:get_historical_stock_prices (dict or list)
        yahoo_dividends: Result from yahoo-finance:get_dividends
    
    Returns:
        Dict ready to pass to Security constructor
    """
    security_data = {
        'ticker': ticker,
        'name': '',
        'asset_type': 'stock',
        'exchange': '',
        'discovered_via': 'mcp_enrichment'
    }
    
    # Enrich from Massive.com details
    if massive_details:
        security_data['name'] = massive_details.get('name', ticker)
        security_data['asset_type'] = massive_details.get('type', 'stock').upper()
        security_data['exchange'] = massive_details.get('primary_exchange', '')
        security_data['market_cap'] = massive_details.get('market_cap')
        security_data['sector'] = massive_details.get('sic_description', '')
        security_data['description'] = massive_details.get('description', '')
    
    # Enrich from Yahoo Finance current price
    if yahoo_price is not None:
        # Handle both float (direct price) and dict (full quote)
        if isinstance(yahoo_price, (int, float)):
            security_data['current_price'] = float(yahoo_price)
        elif isinstance(yahoo_price, dict):
            security_data['current_price'] = yahoo_price.get('regularMarketPrice')
            security_data['pe_ratio'] = yahoo_price.get('trailingPE')
            security_data['avg_volume'] = yahoo_price.get('averageVolume')
            if 'marketCap' in yahoo_price and not security_data.get('market_cap'):
                security_data['market_cap'] = yahoo_price['marketCap']
    
    # Enrich from Yahoo Finance historical data
    if yahoo_historical:
        # Handle both dict format (date -> price) and list format
        prices = []
        if isinstance(yahoo_historical, dict):
            # Dict format: {'2025-01-01': 100.0, '2025-01-02': 101.0, ...}
            prices = [float(p) for p in yahoo_historical.values() if p is not None]
        elif isinstance(yahoo_historical, list):
            # List format: [{'close': 100.0}, {'close': 101.0}, ...]
            prices = [p['close'] for p in yahoo_historical if 'close' in p]
        
        if prices:
            security_data['week_52_high'] = max(prices)
            security_data['week_52_low'] = min(prices)
            
            # Calculate returns
            if len(prices) >= 2:
                current = prices[-1]
                year_ago = prices[0]
                security_data['return_1y'] = ((current - year_ago) / year_ago) * 100
                
                # Calculate percentage from 52w high/low
                if security_data.get('week_52_high'):
                    security_data['pct_from_52w_high'] = ((current - security_data['week_52_high']) / security_data['week_52_high']) * 100
                if security_data.get('week_52_low'):
                    security_data['pct_from_52w_low'] = ((current - security_data['week_52_low']) / security_data['week_52_low']) * 100
                
                # 3-month return (last 63 trading days)
                if len(prices) >= 63:
                    three_mo_ago = prices[-63]
                    security_data['return_3m'] = ((current - three_mo_ago) / three_mo_ago) * 100
                
                # 1-month return (last 21 trading days)
                if len(prices) >= 21:
                    one_mo_ago = prices[-21]
                    security_data['return_1m'] = ((current - one_mo_ago) / one_mo_ago) * 100
    
    # Enrich from Yahoo Finance dividends
    if yahoo_dividends:
        dividends_dict = yahoo_dividends
        # Handle different formats
        if isinstance(yahoo_dividends, dict) and 'dividends' in yahoo_dividends:
            dividends_dict = yahoo_dividends['dividends']
        
        if dividends_dict:
            # Calculate annual dividend yield
            annual_dividend = sum(float(d) for d in dividends_dict.values())
            if security_data.get('current_price') and security_data['current_price'] > 0:
                security_data['dividend_yield'] = (annual_dividend / security_data['current_price']) * 100
    
    return security_data
    return security_data


def add_discovered_security(analyst: EquityAnalystAgent, security_data: Dict) -> Security:
    """
    Add a security discovered by Claude's MCP tools
    
    Args:
        analyst: EquityAnalystAgent instance
        security_data: Dict with ticker, name, asset_type, etc.
    
    Returns:
        Security object
    """
    security = Security(**security_data)
    analyst.db.add_security(security)
    return security


def score_security_alignment(analyst: EquityAnalystAgent, security: Security, thesis: Dict) -> ThesisAlignment:
    """
    Score a security's alignment with a thesis
    
    Args:
        analyst: EquityAnalystAgent instance
        security: Security object
        thesis: Thesis dict
    
    Returns:
        ThesisAlignment object
    """
    alignment = analyst.scorer.score_alignment(security, thesis)
    analyst.db.add_alignment(alignment)
    return alignment


def get_analysis_results(analyst: EquityAnalystAgent, thesis_id: str, limit: int = 20) -> Dict:
    """Get analysis results for a thesis"""
    securities = analyst.db.get_securities_for_thesis(thesis_id)
    summary = analyst.db.get_thesis_summary(thesis_id)
    
    return {
        'thesis_id': thesis_id,
        'analysis_date': datetime.now().isoformat(),
        'summary': summary,
        'securities': securities[:limit]
    }


def batch_enrich_securities(
    analyst: EquityAnalystAgent,
    thesis: Dict,
    tickers_with_mcp_data: List[Dict]
) -> List[Security]:
    """
    Batch enrich and score multiple securities at once
    
    Args:
        analyst: EquityAnalystAgent instance
        thesis: Thesis dict
        tickers_with_mcp_data: List of dicts with structure:
            {
                'ticker': 'IWM',
                'massive_details': {...},  # From massive:get_ticker_details
                'yahoo_price': {...},       # From yahoo-finance:get_current_stock_price
                'yahoo_historical': [...],  # From yahoo-finance:get_historical_stock_prices
                'yahoo_dividends': {...}    # From yahoo-finance:get_dividends
            }
    
    Returns:
        List of Security objects with alignment scores
    """
    securities = []
    
    print(f"\nBatch enriching {len(tickers_with_mcp_data)} securities...")
    
    for i, ticker_data in enumerate(tickers_with_mcp_data, 1):
        ticker = ticker_data['ticker']
        print(f"  [{i}/{len(tickers_with_mcp_data)}] Processing {ticker}...")
        
        # Enrich with MCP data
        enriched = enrich_security_with_mcp_data(
            ticker=ticker,
            massive_details=ticker_data.get('massive_details'),
            yahoo_price=ticker_data.get('yahoo_price'),
            yahoo_historical=ticker_data.get('yahoo_historical'),
            yahoo_dividends=ticker_data.get('yahoo_dividends')
        )
        
        # Add to database
        security = add_discovered_security(analyst, enriched)
        
        # Score alignment
        alignment = score_security_alignment(analyst, security, thesis)
        
        print(f"      ✓ Score: {alignment.alignment_score}/10")
        
        securities.append(security)
    
    return securities


def export_to_csv(analyst: EquityAnalystAgent, thesis_id: str, output_path: str):
    """Export analysis results to CSV"""
    import csv
    
    securities = analyst.db.get_securities_for_thesis(thesis_id)
    
    if not securities:
        print(f"No securities found for thesis {thesis_id}")
        return None
    
    with open(output_path, 'w', newline='') as f:
        # Get all field names
        fieldnames = list(securities[0].keys())
        
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for sec in securities:
            writer.writerow(sec)
    
    return output_path


# === MAIN EXECUTION ===

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Equity Analyst Agent - Map investment theses to securities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze specific theses by number (1-15)
  python equity_analyst_agent.py --theses 1 2 3
  
  # Analyze all theses
  python equity_analyst_agent.py --all
  
  # Analyze with more securities per thesis
  python equity_analyst_agent.py --theses 1 --max-securities 100
  
  # List available theses
  python equity_analyst_agent.py --list
        """
    )
    
    parser.add_argument(
        '--theses',
        type=int,
        nargs='+',
        help='Thesis numbers to analyze (e.g., --theses 1 2 3)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Analyze all 15 theses'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available theses and exit'
    )
    parser.add_argument(
        '--max-securities',
        type=int,
        default=50,
        help='Maximum securities to discover per thesis (default: 50)'
    )
    
    args = parser.parse_args()
    
    # Load theses
    theses_file = Path("/mnt/user-data/outputs/investment_theses_15_expanded_2026.json")
    
    if not theses_file.exists():
        print("âŒ Theses file not found!")
        return
    
    with open(theses_file) as f:
        data = json.load(f)
        theses = data.get('theses', [])
    
    if not theses:
        print("âŒ No theses found in file!")
        return
    
    # Add IDs to theses if not present
    for i, thesis in enumerate(theses, 1):
        if 'id' not in thesis:
            thesis['id'] = f"thesis_{i}"
    
    # List mode
    if args.list:
        print("=" * 80)
        print("AVAILABLE INVESTMENT THESES")
        print("=" * 80)
        for i, thesis in enumerate(theses, 1):
            print(f"\n{i}. {thesis['title']}")
            print(f"   Conviction: {thesis.get('conviction_level', 'N/A')}")
            print(f"   Horizon: {thesis.get('time_horizon', 'N/A')}")
        print("\n" + "=" * 80)
        return
    
    # Determine which theses to analyze
    if args.all:
        selected_theses = theses
        print(f"ðŸ“š Analyzing all {len(theses)} investment theses")
    elif args.theses:
        selected_theses = []
        for thesis_num in args.theses:
            if 1 <= thesis_num <= len(theses):
                selected_theses.append(theses[thesis_num - 1])
            else:
                print(f"âš ï¸  Warning: Thesis #{thesis_num} not found (valid range: 1-{len(theses)})")
        
        if not selected_theses:
            print("âŒ No valid theses selected!")
            return
        
        print(f"ðŸ“š Analyzing {len(selected_theses)} selected thesis(es)")
    else:
        # Default: show help
        parser.print_help()
        return
    
    # Initialize agent
    agent = EquityAnalystAgent()
    
    # Process each thesis
    all_results = []
    
    for idx, thesis in enumerate(selected_theses, 1):
        print(f"\n{'='*80}")
        print(f"Processing Thesis {idx}/{len(selected_theses)}")
        print(f"{'='*80}")
        
        result = agent.analyze_thesis(thesis, max_securities=args.max_securities)
        all_results.append(result)
        
        # Export individual results
        output_dir = Path("/mnt/user-data/outputs")
        output_file = output_dir / f"equity_analysis_{result['thesis_id']}.json"
        agent.export_results(result['thesis_id'], str(output_file))
        
        # Print summary
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)
        print(f"\nThesis: {result['thesis_title']}")
        print(f"Securities analyzed: {result['summary']['total_securities']}")
        print(f"Average alignment score: {result['summary']['avg_score']:.2f}/10")
        print(f"High alignment (8-10): {result['summary']['high_alignment']}")
        print(f"Medium alignment (5-7.99): {result['summary']['medium_alignment']}")
        print(f"Low alignment (<5): {result['summary']['low_alignment']}")
        
        print("\nTop 10 Securities by Alignment:")
        print("-" * 80)
        for i, sec in enumerate(result['securities'][:10], 1):
            print(f"{i:2d}. {sec['ticker']:6s} - {sec['name'][:40]:40s} | Score: {sec['alignment_score']}/10")
        
        print(f"\nðŸ“„ Results exported to: {output_file}")
    
    # Summary across all analyzed theses
    if len(all_results) > 1:
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)
        total_securities = sum(r['summary']['total_securities'] for r in all_results)
        avg_score = sum(r['summary']['avg_score'] for r in all_results) / len(all_results)
        print(f"Total theses analyzed: {len(all_results)}")
        print(f"Total securities discovered: {total_securities}")
        print(f"Average alignment score across all: {avg_score:.2f}/10")
    
    # Clean up
    agent.close()
    
    print("\nâœ… Equity analysis complete!")
    print(f"ðŸ“Š Database location: /home/claude/securities.db")


if __name__ == "__main__":
    main()
