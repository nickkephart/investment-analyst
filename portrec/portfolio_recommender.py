#!/usr/bin/env python3
"""
Portfolio Recommender - Produces add/remove recommendations based on
portfolio holdings vs thesis-aligned securities.
"""

import csv
from pathlib import Path
from typing import Dict, List, Optional


def load_portfolio_csv(csv_path: str) -> List[Dict]:
    """
    Load portfolio from Fidelity-style CSV.

    Expected columns: Symbol, Description, Qty, Mkt Val, Security Type
    Skips cash, totals, and non-position rows.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {csv_path}")

    positions = []
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read()
    # Fidelity CSV may have a title row before headers; find the header row
    lines = content.strip().split("\n")
    header_idx = 0
    for i, line in enumerate(lines):
        if "Symbol" in line and "Description" in line:
            header_idx = i
            break
    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
            symbol = (row.get("Symbol") or "").strip()
            if not symbol:
                continue
            # Skip header/total rows
            if symbol in ("Account Total", "Cash & Cash Investments", "--"):
                continue
            # Skip cash tickers (e.g. SWVXX)
            sec_type = (row.get("Security Type") or "").lower()
            if "cash" in sec_type or "money market" in sec_type:
                continue

            try:
                qty = float((row.get("Qty (Quantity)") or "0").replace(",", ""))
            except ValueError:
                qty = 0

            mkt_val_str = (row.get("Mkt Val (Market Value)") or "0").replace("$", "").replace(",", "")
            try:
                mkt_val = float(mkt_val_str)
            except ValueError:
                mkt_val = 0

            positions.append({
                "symbol": symbol.upper(),
                "description": row.get("Description", ""),
                "quantity": qty,
                "market_value": mkt_val,
                "security_type": sec_type,
            })

    return positions


def generate_recommendations(
    portfolio: List[Dict],
    thesis_results: Dict[str, List[Dict]],
    add_threshold: float = 50.0,
    top_n_adds: int = 5,
    consider_removals: bool = False,
    removal_threshold: float = 30.0,
) -> Dict:
    """
    Generate add/remove recommendations.

    Args:
        portfolio: List of portfolio positions from load_portfolio_csv
        thesis_results: Dict mapping thesis_id -> list of {symbol, score, rationale, ...}
        add_threshold: Minimum score to recommend adding
        top_n_adds: Max number of add recommendations per thesis
        consider_removals: Whether to suggest removals
        removal_threshold: Holdings scoring below this (vs any thesis) may be flagged

    Returns:
        {
            "add": [{"symbol", "name", "score", "rationale", "thesis_id", "thesis_name"}, ...],
            "remove": [{"symbol", "rationale"}, ...],  # if consider_removals
            "hold": [{"symbol", "score", "rationale"}, ...]  # existing holdings with good alignment
        }
    """
    portfolio_symbols = {p["symbol"] for p in portfolio}

    adds = []
    seen_adds = set()

    for thesis_id, results in thesis_results.items():
        thesis_name = results[0]["thesis_name"] if results else thesis_id
        for r in results[:top_n_adds]:
            symbol = r.get("symbol", "").upper()
            score = r.get("score", 0)
            if symbol in portfolio_symbols or symbol in seen_adds:
                continue
            if score < add_threshold:
                continue
            seen_adds.add(symbol)
            adds.append({
                "symbol": symbol,
                "name": r.get("name", symbol),
                "score": score,
                "rationale": r.get("rationale", ""),
                "thesis_id": thesis_id,
                "thesis_name": thesis_name,
                "current_price": r.get("current_price"),
                "market_cap": r.get("market_cap"),
            })

    # Sort adds by score desc
    adds.sort(key=lambda x: x["score"], reverse=True)

    removals = []
    holds = []

    if consider_removals or True:  # Always compute holds for context
        # Build symbol -> best score across theses
        symbol_scores = {}
        for thesis_id, results in thesis_results.items():
            thesis_name = results[0]["thesis_name"] if results else thesis_id
            for r in results:
                symbol = r.get("symbol", "").upper()
                score = r.get("score", 0)
                if symbol not in symbol_scores or score > symbol_scores[symbol]["score"]:
                    symbol_scores[symbol] = {
                        "score": score,
                        "rationale": r.get("rationale", ""),
                        "thesis_name": thesis_name,
                    }

        for pos in portfolio:
            symbol = pos["symbol"]
            info = symbol_scores.get(symbol, {"score": 0, "rationale": "No thesis alignment", "thesis_name": ""})
            if info["score"] >= add_threshold:
                holds.append({
                    "symbol": symbol,
                    "description": pos["description"],
                    "score": info["score"],
                    "rationale": info["rationale"],
                })
            elif consider_removals and info["score"] < removal_threshold:
                removals.append({
                    "symbol": symbol,
                    "description": pos["description"],
                    "rationale": f"Low alignment ({info['score']:.0f}) with selected theses; {info['rationale']}",
                })

    return {
        "add": adds,
        "remove": removals,
        "hold": holds,
    }
