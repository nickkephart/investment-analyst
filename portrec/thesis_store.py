#!/usr/bin/env python3
"""
Thesis Store - SQLite persistence for investment theses and selection/priority.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ThesisStore:
    """Persist theses and record selection/priority for research."""

    def __init__(self, db_path: str = "portrec.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with theses table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS theses (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                keywords TEXT,
                sectors TEXT,
                priority INTEGER DEFAULT 0,
                selected INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def import_from_json(self, json_path: str) -> int:
        """
        Load theses from JSON file into store.

        Expected JSON format:
        {
            "theses": [
                {
                    "id": "1",
                    "name": "Thesis Title",
                    "description": "...",
                    "keywords": ["keyword1", "keyword2"],
                    "sectors": ["Technology", "Healthcare"]
                }
            ]
        }
        Or a list directly: [{...}, {...}]

        Returns:
            Number of theses imported.
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Theses file not found: {json_path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        theses = data.get("theses", data) if isinstance(data, dict) else data
        if not isinstance(theses, list):
            raise ValueError("JSON must contain 'theses' array or be an array of theses")

        count = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for t in theses:
            thesis_id = str(t.get("id", t.get("name", "")))
            title = t.get("name", t.get("title", thesis_id))
            description = t.get("description", "")
            keywords = json.dumps(t.get("keywords", []))
            sectors = json.dumps(t.get("sectors", []))

            cursor.execute("SELECT priority, selected, created_at FROM theses WHERE id = ?",
                           (thesis_id,))
            existing = cursor.fetchone()
            if existing:
                priority, selected, created_at = existing
            else:
                priority, selected, created_at = 0, 0, datetime.now().isoformat()

            cursor.execute("""
                INSERT OR REPLACE INTO theses
                (id, title, description, keywords, sectors, priority, selected, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (thesis_id, title, description, keywords, sectors,
                  priority, selected, created_at))

            count += 1

        conn.commit()
        conn.close()
        return count

    def list_theses(self, selected_only: bool = False) -> List[Dict]:
        """List all theses with selection and priority."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if selected_only:
            cursor.execute(
                "SELECT * FROM theses WHERE selected = 1 ORDER BY priority ASC, id ASC"
            )
        else:
            cursor.execute("SELECT * FROM theses ORDER BY priority ASC, id ASC")

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "keywords": json.loads(r["keywords"] or "[]"),
                "sectors": json.loads(r["sectors"] or "[]"),
                "priority": r["priority"],
                "selected": bool(r["selected"]),
            }
            for r in rows
        ]

    def get_thesis(self, thesis_id: str) -> Optional[Dict]:
        """Get a single thesis by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "id": row["id"],
            "name": row["title"],
            "title": row["title"],
            "description": row["description"],
            "keywords": json.loads(row["keywords"] or "[]"),
            "sectors": json.loads(row["sectors"] or "[]"),
            "priority": row["priority"],
            "selected": bool(row["selected"]),
        }

    def get_selected_theses(self) -> List[Dict]:
        """Get theses that are selected for research (in analyst format)."""
        return self.list_theses(selected_only=True)

    def select(self, thesis_id: str) -> bool:
        """Mark a thesis as selected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE theses SET selected = 1 WHERE id = ?", (thesis_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def deselect(self, thesis_id: str) -> bool:
        """Mark a thesis as not selected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE theses SET selected = 0 WHERE id = ?", (thesis_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def set_priority(self, thesis_id: str, priority: int) -> bool:
        """Set priority for a thesis (lower = higher priority)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE theses SET priority = ? WHERE id = ?", (priority, thesis_id))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed
