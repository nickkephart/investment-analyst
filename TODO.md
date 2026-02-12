# Project TODO

## Backfill / Data Enrichment

- [ ] **Finish constituent enrichment** – Run constituent backfill when Yahoo API is no longer rate-limited. ~910 constituents remain (of 4,247) needing sector/description. Command: `python backfill_etf_full.py --constituents-only --remaining-only`
