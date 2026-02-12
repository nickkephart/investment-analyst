#!/usr/bin/env python3
"""Quick check of backfill status in DB."""
import sqlite3

conn = sqlite3.connect("portrec_securities.db")
c = conn.cursor()

# All constituents
c.execute("SELECT DISTINCT constituent_symbol FROM etf_holdings ORDER BY constituent_symbol")
all_const = [row[0] for row in c.fetchall()]

# Constituents with sector/description (enriched)
c.execute("""
    SELECT s.symbol FROM securities s
    WHERE s.symbol IN (SELECT DISTINCT constituent_symbol FROM etf_holdings)
    AND ((s.sector IS NOT NULL AND TRIM(s.sector) != '')
         OR (s.gics_sector IS NOT NULL AND TRIM(s.gics_sector) != '')
         OR (s.description IS NOT NULL AND TRIM(s.description) != ''))
""")
enriched_set = set(row[0] for row in c.fetchall())

remaining = [s for s in all_const if s not in enriched_set]
total = len(all_const)
enriched_count = len(enriched_set)

print("Constituent backfill status")
print("-" * 50)
print(f"Total constituents: {total}")
print(f"Enriched (have sector/description): {enriched_count}")
print(f"Remaining to enrich: {len(remaining)}")
print(f"Progress: {100 * enriched_count / total:.1f}%")
print()
if remaining:
    print("Sample of remaining (first 10):", remaining[:10])
conn.close()
