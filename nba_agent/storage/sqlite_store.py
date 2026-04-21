from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from nba_agent.models import CollectedItem


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collected_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    content_excerpt TEXT NOT NULL,
                    author TEXT NOT NULL,
                    publish_time TEXT,
                    tags_json TEXT NOT NULL,
                    matched_keywords_json TEXT NOT NULL,
                    matched_categories_json TEXT NOT NULL DEFAULT '[]',
                    matched_groups_json TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    agent_score INTEGER,
                    agent_reason TEXT NOT NULL DEFAULT '',
                    raw_payload TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(
                conn,
                table_name="collected_items",
                column_name="matched_categories_json",
                column_definition="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                conn,
                table_name="collected_items",
                column_name="agent_score",
                column_definition="INTEGER",
            )
            self._ensure_column(
                conn,
                table_name="collected_items",
                column_name="agent_reason",
                column_definition="TEXT NOT NULL DEFAULT ''",
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_collected_items_source_url
                ON collected_items(source, url)
                """
            )

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        *,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {row[1] for row in rows}
        if column_name in existing_columns:
            return
        try:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    def save_items(self, items: list[CollectedItem]) -> int:
        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            for item in items:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO collected_items (
                        source,
                        title,
                        url,
                        content_excerpt,
                        author,
                        publish_time,
                        tags_json,
                        matched_keywords_json,
                        matched_categories_json,
                        matched_groups_json,
                        score,
                        agent_score,
                        agent_reason,
                        raw_payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.source,
                        item.title,
                        item.url,
                        item.content_excerpt,
                        item.author,
                        item.publish_time.isoformat() if item.publish_time else None,
                        json.dumps(item.tags, ensure_ascii=False),
                        json.dumps(item.matched_keywords, ensure_ascii=False),
                        json.dumps(item.matched_categories, ensure_ascii=False),
                        json.dumps(item.matched_groups, ensure_ascii=False),
                        item.score,
                        item.agent_score,
                        item.agent_reason,
                        item.raw_payload,
                    ),
                )
                inserted += cursor.rowcount
        return inserted
