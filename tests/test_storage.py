"""Tests for CORTEX storage engine and file persistence."""

import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.models import Claim, Event, Knowledge
from cortex_engine.storage import CortexStorage


class TestCortexStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CortexStorage(cortex_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_deterministic_filesystem_paths(self):
        """Test that deterministic directory structures are established."""
        self.assertTrue((Path(self.temp_dir) / "events").exists())
        self.assertTrue((Path(self.temp_dir) / "knowledge" / "decisions").exists())
        self.assertTrue((Path(self.temp_dir) / "knowledge" / "constraints").exists())
        self.assertTrue((Path(self.temp_dir) / "knowledge" / "failures").exists())
        self.assertTrue((Path(self.temp_dir) / "knowledge" / "lessons").exists())
        self.assertTrue((Path(self.temp_dir) / "knowledge" / "claims").exists())
        self.assertTrue((Path(self.temp_dir) / "state").exists())
        self.assertTrue((Path(self.temp_dir) / "indexes").exists())
        self.assertTrue((Path(self.temp_dir) / "working").exists())

    def test_event_append_and_read(self):
        """Test event recording, persistence in JSONL, and filtered reading."""
        evt1 = Event(
            id="evt-001",
            type="tool_execution",
            role="APP",
            payload={"tool": "pytest", "exit_code": 0},
            task_id="T-01",
            provenance={"commit": "abc1234"},
        )
        evt2 = Event(
            id="evt-002",
            type="memory_retrieval",
            role="MEMORY",
            payload={"query": "architecture"},
            task_id="T-01",
        )

        self.storage.record_event(evt1)
        self.storage.record_event(evt2)

        events_all = self.storage.read_events()
        self.assertEqual(len(events_all), 2)
        self.assertEqual(events_all[0].id, "evt-001")
        self.assertEqual(events_all[0].role, "APP")
        self.assertEqual(events_all[1].id, "evt-002")

        # Filter by role
        events_app = self.storage.read_events(role="APP")
        self.assertEqual(len(events_app), 1)
        self.assertEqual(events_app[0].id, "evt-001")

        # Filter by limit
        events_limit = self.storage.read_events(limit=1)
        self.assertEqual(len(events_limit), 1)
        self.assertEqual(events_limit[0].id, "evt-002")

    def test_knowledge_write_and_read(self):
        """Test writing and reading knowledge records."""
        item = Knowledge(
            id="DEC-001",
            type="decision",
            title="Use SQLite for Derived Indexes",
            content="SQLite FTS5 will be used for rebuildable indexes.",
            status="active",
            provenance={"author": "Agent"},
            related=["CON-001"],
        )
        persisted_id = self.storage.write_knowledge(item)
        self.assertEqual(persisted_id, "DEC-001")

        read_item = self.storage.read_knowledge("DEC-001", category="decisions")
        self.assertIsNotNone(read_item)
        self.assertEqual(read_item.title, "Use SQLite for Derived Indexes")
        self.assertEqual(read_item.type, "decision")
        self.assertEqual(read_item.related, ["CON-001"])

        all_items = self.storage.list_knowledge()
        self.assertEqual(len(all_items), 1)

    def test_claim_write_and_read(self):
        """Test writing and reading testable claim records."""
        claim = Claim(
            id="CLAIM-001",
            statement="CORTEX storage is purely file-based in v0.1",
            status="verified",
            artifact={"path": "cortex_engine/storage.py"},
            evidence=[{"test": "test_claim_write_and_read"}],
        )
        self.storage.write_claim(claim)

        read_claim = self.storage.read_claim("CLAIM-001")
        self.assertIsNotNone(read_claim)
        self.assertEqual(read_claim.status, "verified")
        self.assertEqual(read_claim.artifact["path"], "cortex_engine/storage.py")

        claims = self.storage.list_claims(status="verified")
        self.assertEqual(len(claims), 1)
        claims_unverified = self.storage.list_claims(status="unverified")
        self.assertEqual(len(claims_unverified), 0)

    def test_git_independent_storage_behavior(self):
        """Verify storage works in pure filesystem mode without Git requirement."""
        # Non-git directory
        self.assertTrue(Path(self.temp_dir).exists())
        self.assertFalse((Path(self.temp_dir) / ".git").exists())

        evt = Event(id="evt-standalone", type="log", role="APP", payload={"msg": "ok"})
        self.storage.record_event(evt)
        records = self.storage.read_events()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, "evt-standalone")


if __name__ == "__main__":
    unittest.main()
