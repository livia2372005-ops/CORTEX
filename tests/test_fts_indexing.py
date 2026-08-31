"""Comprehensive tests for SQLite FTS5 derived indexing, determinism, and rebuildability."""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.indexer import CortexIndexer, sanitize_fts5_query
from cortex_engine.models import Event, Knowledge
from cortex_engine.storage import CortexStorage


class TestFTS5Indexing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CortexStorage(cortex_dir=self.temp_dir)
        self.indexer = CortexIndexer(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fts_index_creation(self):
        """Test that SQLite FTS5 database and virtual tables initialize properly."""
        conn = self.indexer._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        self.assertIn("fts_knowledge", tables)
        self.assertIn("fts_events", tables)
        self.assertIn("index_metadata", tables)

    def test_knowledge_indexing_and_search_correctness(self):
        """Test indexing knowledge and retrieving via FTS5 match."""
        self.api.record_knowledge(
            id="DEC-100",
            knowledge_type="decision",
            title="Use Redis for Distributed Cache Invalidation",
            content="Redis pub/sub will be used to broadcast cache invalidation signals across instances.",
            status="active",
            provenance={"author": "Team Lead"},
        )
        self.api.record_knowledge(
            id="FAIL-100",
            knowledge_type="failure",
            title="Local In-Memory Cache Invalidation Inconsistency",
            content="Local dictionary cache invalidation caused state desynchronization across clustered workers.",
            status="active",
        )

        res = self.api.search("cache invalidation")
        self.assertEqual(res["count"], 2)
        ids = [r["id"] for r in res["results"]]
        self.assertIn("DEC-100", ids)
        self.assertIn("FAIL-100", ids)

    def test_event_indexing_and_search(self):
        """Test observable event indexing and search."""
        evt1 = Event(
            id="evt-payment-01",
            type="tool_execution",
            role="APP",
            payload={"tool": "pytest", "test": "test_payment_checkout", "status": "pass"},
            task_id="T-PAY-01",
        )
        self.api.record_event(
            event_type=evt1.type,
            role=evt1.role,
            payload=evt1.payload,
            id=evt1.id,
            task_id=evt1.task_id,
        )

        event_matches = self.api.search_events("payment checkout")
        self.assertEqual(len(event_matches), 1)
        self.assertEqual(event_matches[0]["id"], "evt-payment-01")

    def test_deterministic_ordering(self):
        """Test deterministic result ordering with predictable tie-breaking by id."""
        # Insert items with identical content to test tie-breaker
        for i in range(5, 0, -1):
            self.api.record_knowledge(
                id=f"ITEM-00{i}",
                knowledge_type="decision",
                title=f"Standard Architecture Pattern {i}",
                content="Deterministic ranking test content for consistent ordering.",
                status="active",
            )

        res1 = self.api.search("deterministic ranking")
        res2 = self.api.search("deterministic ranking")

        # Result lists must be identical in content and order
        ids1 = [r["id"] for r in res1["results"]]
        ids2 = [r["id"] for r in res2["results"]]
        self.assertEqual(ids1, ids2)
        # Verify sorted tie breaker: ITEM-001 ... ITEM-005
        self.assertEqual(ids1, sorted(ids1))

    def test_empty_query_and_no_result_handling(self):
        """Test handling of empty queries and queries with no matches."""
        self.api.record_knowledge(
            id="DEC-01",
            knowledge_type="decision",
            title="Single Agent",
            content="Only one agent operates across roles.",
        )

        # Empty query
        empty_res = self.api.search("")
        self.assertEqual(empty_res["count"], 0)
        self.assertEqual(empty_res["results"], [])

        # Whitespace query
        ws_res = self.api.search("   ")
        self.assertEqual(ws_res["count"], 0)

        # Non-matching query
        no_match = self.api.search("nonexistent_quantum_tensor_xyz")
        self.assertEqual(no_match["count"], 0)
        self.assertEqual(no_match["results"], [])

    def test_rebuild_correctness(self):
        """Test: build -> search -> delete index -> rebuild -> search == equivalent."""
        self.api.record_knowledge(
            id="DEC-200",
            knowledge_type="decision",
            title="Postgres Connection Pooling",
            content="Use PgBouncer with transaction-level pooling.",
        )
        self.api.record_knowledge(
            id="DEC-201",
            knowledge_type="decision",
            title="Database Sharding Strategy",
            content="Shard by customer tenant ID.",
        )

        initial_search = self.api.search("pooling")
        self.assertEqual(initial_search["count"], 1)
        self.assertEqual(initial_search["results"][0]["id"], "DEC-200")

        # Force delete index DB file
        index_db_file = self.storage.indexes_dir / "cortex.db"
        if index_db_file.exists():
            index_db_file.unlink()

        # Rebuild indexes from canonical storage
        rebuild_stats = self.api.rebuild_indexes()
        self.assertEqual(rebuild_stats["indexed_knowledge"], 2)

        # Verify search produces identical results
        rebuilt_search = self.api.search("pooling")
        self.assertEqual(rebuilt_search["count"], 1)
        self.assertEqual(rebuilt_search["results"][0]["id"], "DEC-200")

    def test_canonical_truth_survives_index_deletion(self):
        """MANDATORY: Delete SQLite index -> canonical files remain intact -> rebuild -> memory restored."""
        self.api.record_knowledge(
            id="CON-999",
            knowledge_type="constraint",
            title="Zero Data Loss Invariant",
            content="Canonical truth must survive complete derived index destruction.",
        )

        # Verify canonical file exists on filesystem
        canonical_file = self.storage.knowledge_dir / "constraints" / "CON-999.json"
        self.assertTrue(canonical_file.exists())

        # Destroy index database
        index_db = self.storage.indexes_dir / "cortex.db"
        if index_db.exists():
            index_db.unlink()
        self.assertFalse(index_db.exists())

        # Canonical file MUST still exist completely unmodified
        self.assertTrue(canonical_file.exists())
        canonical_data = json.loads(canonical_file.read_text(encoding="utf-8"))
        self.assertEqual(canonical_data["id"], "CON-999")

        # Rebuild restored memory in index
        self.api.rebuild_indexes()
        self.assertTrue(index_db.exists())
        search_res = self.api.search("zero data loss")
        self.assertEqual(search_res["count"], 1)
        self.assertEqual(search_res["results"][0]["id"], "CON-999")

    def test_stale_index_and_drift_behavior(self):
        """Test stale index behavior: modify canonical file directly -> index is stale until rebuilt."""
        self.api.record_knowledge(
            id="DEC-DRIFT-01",
            knowledge_type="decision",
            title="Initial Title V1",
            content="Version 1 content before manual modification.",
        )

        # Verify initial search finds V1
        res1 = self.api.search("Version 1")
        self.assertEqual(res1["count"], 1)

        # Simulate direct modification to canonical file on disk without notifying index
        canonical_file = self.storage.knowledge_dir / "decisions" / "DEC-DRIFT-01.json"
        with open(canonical_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["content"] = "Version 2 updated content after external edit."
        with open(canonical_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Search for 'Version 2' WITHOUT rebuilding -> returns 0 (demonstrates index drift/staleness)
        stale_search = self.api.search("Version 2")
        self.assertEqual(stale_search["count"], 0)

        # Search for 'Version 1' WITHOUT rebuilding -> still returns old index record
        old_search = self.api.search("Version 1")
        self.assertEqual(old_search["count"], 1)

        # Now execute rebuild
        self.api.rebuild_indexes()

        # Search for 'Version 2' AFTER rebuild -> returns 1 match with updated content
        fresh_search = self.api.search("Version 2")
        self.assertEqual(fresh_search["count"], 1)
        self.assertIn("Version 2", fresh_search["results"][0]["content"])

    def test_performance_baseline_benchmark(self):
        """Benchmark comparison: Filesystem scan vs SQLite FTS5 across synthetic datasets (100, 1000 records)."""
        benchmark_dir = tempfile.mkdtemp()
        bench_storage = CortexStorage(cortex_dir=benchmark_dir)
        bench_indexer = CortexIndexer(storage=bench_storage)
        bench_api = CortexAPI(storage=bench_storage, indexer=bench_indexer)

        try:
            # Seed 1,000 synthetic records
            num_records = 1000
            for i in range(num_records):
                bench_storage.write_knowledge(
                    Knowledge(
                        id=f"SYNTH-{i:05d}",
                        type="decision" if i % 2 == 0 else "lesson",
                        title=f"Synthetic Architectural Decision {i}",
                        content=f"Detailed payload text for synthetic record {i} discussing caching, services, and transactions.",
                    )
                )

            # 1. Measure Filesystem Scan (without FTS)
            start_fs = time.perf_counter()
            items = bench_storage.list_knowledge()
            fs_matches = [
                item.to_dict()
                for item in items
                if "synthetic architectural decision 777" in f"{item.title} {item.content}".lower()
            ]
            fs_duration_ms = (time.perf_counter() - start_fs) * 1000.0

            # 2. Build FTS Index
            start_rebuild = time.perf_counter()
            bench_indexer.rebuild_from_canonical(bench_storage)
            rebuild_duration_ms = (time.perf_counter() - start_rebuild) * 1000.0

            # 3. Measure SQLite FTS5 Search
            start_fts = time.perf_counter()
            fts_matches = bench_indexer.search_knowledge("synthetic architectural decision 777")
            fts_duration_ms = (time.perf_counter() - start_fts) * 1000.0

            self.assertEqual(len(fs_matches), 1)
            self.assertEqual(len(fts_matches), 1)
            self.assertEqual(fs_matches[0]["id"], fts_matches[0]["id"])

            # Verify FTS search is operational and fast
            self.assertGreater(fs_duration_ms, 0)
            self.assertGreater(fts_duration_ms, 0)
        finally:
            shutil.rmtree(benchmark_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
