"""CORTEX Derived Indexing Engine using SQLite FTS5."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Event, Knowledge
from .storage import CortexStorage


def sanitize_fts5_query(raw_query: str) -> str:
    """Sanitize user query for SQLite FTS5 match syntax."""
    # Strip dangerous FTS5 operators and extract clean alphanumeric words
    tokens = re.findall(r"\w+", raw_query, re.UNICODE)
    if not tokens:
        return ""
    # Use prefix matching for each term combined with AND conjunction
    # e.g. "payment service" -> '"payment"* AND "service"*'
    return " AND ".join(f'"{t}"*' for t in tokens)


class CortexIndexer:
    """Manages rebuildable SQLite FTS5 derived index in .cortex/indexes/cortex.db."""

    def __init__(self, db_path: Optional[str | Path] = None, storage: Optional[CortexStorage] = None):
        if db_path is None:
            if storage is not None:
                self.db_path = storage.indexes_dir / "cortex.db"
            else:
                self.db_path = Path.cwd() / ".cortex" / "indexes" / "cortex.db"
        else:
            self.db_path = Path(db_path).resolve()

        self.storage = storage
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection with foreign keys and row factory."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        self._initialize_schema(conn)
        return conn

    def _initialize_schema(self, conn: sqlite3.Connection) -> None:
        """Create derived FTS5 virtual tables if they do not exist."""
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_knowledge USING fts5(
                id UNINDEXED,
                type,
                title,
                content,
                status,
                related,
                affects,
                provenance_text,
                raw_json UNINDEXED,
                tokenize = 'unicode61'
            )
            """
        )

        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_events USING fts5(
                id UNINDEXED,
                type,
                role,
                task_id,
                payload_text,
                provenance_text,
                raw_json UNINDEXED,
                tokenize = 'unicode61'
            )
            """
        )
        conn.commit()

    def index_knowledge_item(self, item: Knowledge, conn: Optional[sqlite3.Connection] = None) -> None:
        """Index a single knowledge record into fts_knowledge."""
        should_close = False
        if conn is None:
            conn = self._get_connection()
            should_close = True

        cursor = conn.cursor()
        # Remove existing index entry for this ID if present
        cursor.execute("DELETE FROM fts_knowledge WHERE id = ?", (item.id,))

        related_text = " ".join(item.related) if item.related else ""
        affects_text = " ".join(item.affects) if item.affects else ""
        prov_text = json.dumps(item.provenance, ensure_ascii=False) if item.provenance else ""
        raw_json = json.dumps(item.to_dict(), ensure_ascii=False)

        cursor.execute(
            """
            INSERT INTO fts_knowledge (id, type, title, content, status, related, affects, provenance_text, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.type,
                item.title,
                item.content,
                item.status,
                related_text,
                affects_text,
                prov_text,
                raw_json,
            ),
        )
        conn.commit()
        if should_close:
            conn.close()

    def index_event(self, event: Event, conn: Optional[sqlite3.Connection] = None) -> None:
        """Index an observable event record into fts_events."""
        should_close = False
        if conn is None:
            conn = self._get_connection()
            should_close = True

        cursor = conn.cursor()
        cursor.execute("DELETE FROM fts_events WHERE id = ?", (event.id,))

        payload_text = json.dumps(event.payload, ensure_ascii=False)
        prov_text = json.dumps(event.provenance, ensure_ascii=False) if event.provenance else ""
        raw_json = json.dumps(event.to_dict(), ensure_ascii=False)

        cursor.execute(
            """
            INSERT INTO fts_events (id, type, role, task_id, payload_text, provenance_text, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.type,
                event.role,
                event.task_id or "",
                payload_text,
                prov_text,
                raw_json,
            ),
        )
        conn.commit()
        if should_close:
            conn.close()

    def search_knowledge(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search fts_knowledge with deterministic rank and ID tie-breaker."""
        if not self.db_path.exists():
            return []

        fts_query = sanitize_fts5_query(query)
        if not fts_query:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if category:
                # Map potential singular to plural or normalized category
                cat_normalized = category.lower().rstrip("s")
                cursor.execute(
                    """
                    SELECT raw_json, rank FROM fts_knowledge
                    WHERE fts_knowledge MATCH ? AND type LIKE ?
                    ORDER BY rank ASC, id ASC
                    LIMIT ?
                    """,
                    (fts_query, f"{cat_normalized}%", limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT raw_json, rank FROM fts_knowledge
                    WHERE fts_knowledge MATCH ?
                    ORDER BY rank ASC, id ASC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                )

            rows = cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                try:
                    results.append(json.loads(row["raw_json"]))
                except Exception:
                    continue
            return results
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def search_events(
        self,
        query: str,
        event_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search fts_events with deterministic rank and ID tie-breaker."""
        if not self.db_path.exists():
            return []

        fts_query = sanitize_fts5_query(query)
        if not fts_query:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if event_type:
                cursor.execute(
                    """
                    SELECT raw_json, rank FROM fts_events
                    WHERE fts_events MATCH ? AND type = ?
                    ORDER BY rank ASC, id ASC
                    LIMIT ?
                    """,
                    (fts_query, event_type, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT raw_json, rank FROM fts_events
                    WHERE fts_events MATCH ?
                    ORDER BY rank ASC, id ASC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                )

            rows = cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                try:
                    results.append(json.loads(row["raw_json"]))
                except Exception:
                    continue
            return results
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def rebuild_from_canonical(self, storage: Optional[CortexStorage] = None) -> Dict[str, int]:
        """Rebuild entire derived FTS index from canonical filesystem files."""
        active_storage = storage or self.storage
        if active_storage is None:
            active_storage = CortexStorage()

        # Delete database file if exists to guarantee complete clean rebuild
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except PermissionError:
                # If file locked, drop tables inside connection
                conn = sqlite3.connect(str(self.db_path))
                conn.execute("DROP TABLE IF EXISTS fts_knowledge")
                conn.execute("DROP TABLE IF EXISTS fts_events")
                conn.execute("DROP TABLE IF EXISTS index_metadata")
                conn.commit()
                conn.close()

        conn = self._get_connection()

        # 1. Index all canonical knowledge records
        knowledge_items = active_storage.list_knowledge()
        for item in knowledge_items:
            self.index_knowledge_item(item, conn=conn)

        # 2. Index all canonical events
        events = active_storage.read_events()
        for evt in events:
            self.index_event(evt, conn=conn)

        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value) VALUES ('last_rebuild', CURRENT_TIMESTAMP)"
        )
        conn.commit()
        conn.close()

        return {
            "indexed_knowledge": len(knowledge_items),
            "indexed_events": len(events),
        }
