#!/usr/bin/env python3
"""
Background worker - polls for research tasks and runs them asynchronously.
"""

import sqlite3
import time
from pathlib import Path


def _init_task_table(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thesis_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def run_worker(config: dict, poll_interval: int = 60):
    """
    Run background worker that polls for pending research tasks.

    Tasks can be queued by inserting into pending_research (thesis_id, status='pending').
    Worker processes them and runs research.
    """
    db_path = config.get("db_path", "portrec.db")
    securities_db = config.get("securities_db_path", "portrec_securities.db")
    _init_task_table(db_path)

    print("Background worker started. Polling for research tasks...")
    print("  To queue a task: INSERT INTO pending_research (thesis_id) VALUES ('1');")
    print("  Ctrl+C to stop.\n")

    while True:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, thesis_id FROM pending_research WHERE status = 'pending' LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                task_id, thesis_id = row
                print(f"Processing task {task_id}: thesis {thesis_id}")

                from portrec.thesis_store import ThesisStore
                from portrec.equity_analyst import MultiSourceEquityAnalyst

                store = ThesisStore(db_path=db_path)
                thesis = store.get_thesis(thesis_id)
                if thesis:
                    analyst = MultiSourceEquityAnalyst(
                        db_path=securities_db,
                        enable_massive=config.get("enable_massive"),
                        enable_alpha_vantage=config.get("enable_alpha_vantage"),
                        polygon_api_key=config.get("polygon_api_key") or None,
                        alpha_vantage_api_key=config.get("alpha_vantage_api_key") or None,
                    )
                    analyst.analyze_thesis(thesis, max_securities=20)
                    print(f"  Completed research for {thesis_id}")

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE pending_research SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (task_id,),
                )
                conn.commit()
                conn.close()
            else:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(poll_interval)
