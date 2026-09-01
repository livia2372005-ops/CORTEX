"""CORTEX Phase 16: Memory Lifecycle & Promotion Test Suite.

Verifies:
1. Trivial event remains event
2. Explicit memory request creates knowledge with provenance
3. Candidate memory creation
4. Candidate promotion under Agent authority
5. Promotion provenance links to source event IDs
6. Repeated failure pattern candidate detection
7. Architectural decision candidate detection
8. Duplicate knowledge detection without destructive merge
9. Supersession lifecycle (preserves old record with status=superseded)
10. Archival lifecycle (status=archived without deletion)
11. Retrieval respects lifecycle status
12. Context compiler respects active/affected/superseded status tags
13. Raw event history remains append-only and intact
14. Event volume baseline: 100 trivial events + 20 meaningful events
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.compiler import ContextCompiler
from cortex_engine.indexer import CortexIndexer
from cortex_engine.lifecycle import MemoryLifecycleManager, compute_text_similarity
from cortex_engine.models import Event, Knowledge, MemoryCandidate
from cortex_engine.storage import CortexStorage


class TestPhase16MemoryLifecycle(unittest.TestCase):
    """Phase 16 Lifecycle and Promotion Unit & Integration Tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cortex_phase16_")
        self.cortex_dir = Path(self.temp_dir) / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.indexer = CortexIndexer(storage=self.storage)
        self.compiler = ContextCompiler(storage=self.storage)
        self.api = CortexAPI(
            storage=self.storage,
            indexer=self.indexer,
            compiler=self.compiler,
        )
        self.lifecycle = self.api.lifecycle

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_trivial_event_remains_event(self):
        """Verify trivial events (file opened, grep executed, formatting) remain events and are not candidates."""
        e1 = Event(id="evt-1", type="file_opened", role="APP", payload={"path": "main.py"})
        e2 = Event(id="evt-2", type="grep_executed", role="APP", payload={"query": "import redis"})
        e3 = Event(id="evt-3", type="formatting_changed", role="APP", payload={"file": "test.py"})
        e4 = Event(id="evt-4", type="test_passed", role="APP", payload={"test": "test_unit.py"})

        self.storage.record_event(e1)
        self.storage.record_event(e2)
        self.storage.record_event(e3)
        self.storage.record_event(e4)

        candidates = self.lifecycle.detect_candidates()
        self.assertEqual(len(candidates), 0)

        # Raw events are stored in append-only log
        all_events = self.storage.read_events()
        self.assertEqual(len(all_events), 4)

        # Knowledge records are not created
        self.assertEqual(len(self.storage.list_knowledge()), 0)

    def test_explicit_memory_request_creates_knowledge(self):
        """Verify explicit Agent memory request promotes events to persistent knowledge with provenance."""
        e1 = Event(id="evt-10", type="decision_made", role="LEARNING", payload={"summary": "Use Redis for rate limiting"})
        self.storage.record_event(e1)

        promoted = self.api.promote_memory(
            event_ids=["evt-10"],
            knowledge_type="decision",
            title="Redis Rate Limiting Architecture",
            content="We use Redis with sliding-window counters for rate limiting.",
            knowledge_id="DEC-050",
            status="active",
            provenance={"author": "lead_engineer", "ticket": "ENG-101"},
        )

        self.assertEqual(promoted["id"], "DEC-050")
        self.assertEqual(promoted["status"], "active")
        self.assertEqual(promoted["derived_from"], ["evt-10"])
        self.assertTrue(promoted["provenance"]["explicit_agent_request"])

        # Check canonical file persisted
        stored = self.storage.read_knowledge("DEC-050")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.title, "Redis Rate Limiting Architecture")
        self.assertEqual(stored.derived_from, ["evt-10"])

    def test_candidate_creation_and_promotion(self):
        """Verify candidate creation from architectural event and promotion under explicit Agent command."""
        e1 = Event(
            id="evt-dec-1",
            type="architecture_decision",
            role="LEARNING",
            payload={"decision": "Enforce Repository pattern", "rationale": "Decouple persistence from business logic"},
        )
        self.storage.record_event(e1)

        candidates = self.lifecycle.detect_candidates()
        self.assertEqual(len(candidates), 1)
        cand = candidates[0]
        self.assertEqual(cand.candidate_type, "decision")
        self.assertEqual(cand.reason, "architectural_decision_signal")
        self.assertIn("evt-dec-1", cand.event_ids)

        # Promote candidate
        promoted = self.api.promote_candidate(
            candidate_dict_or_id=cand.id,
            knowledge_id="DEC-080",
            custom_title="Repository Pattern Decoupling",
            custom_content="All domain logic must access storage exclusively via Repository interfaces.",
        )

        self.assertEqual(promoted["id"], "DEC-080")
        self.assertEqual(promoted["title"], "Repository Pattern Decoupling")
        self.assertEqual(promoted["derived_from"], ["evt-dec-1"])

        # Observable memory_promoted event recorded
        events = self.storage.read_events(event_type="memory_promoted")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["knowledge_id"], "DEC-080")

    def test_repeated_failure_pattern_candidate(self):
        """Verify 2+ matching failure events generate a failure memory candidate."""
        f1 = Event(
            id="evt-f1",
            type="test_failure",
            role="APP",
            payload={"error": "Database connection timeout during pool exhaustion", "status": "error"},
        )
        f2 = Event(
            id="evt-f2",
            type="test_failure",
            role="APP",
            payload={"error": "Database connection timeout in replica node", "status": "error"},
        )
        self.storage.record_event(f1)
        self.storage.record_event(f2)

        candidates = self.lifecycle.detect_candidates()
        self.assertEqual(len(candidates), 1)
        cand = candidates[0]
        self.assertEqual(cand.candidate_type, "failure")
        self.assertEqual(cand.reason, "repeated_failure_pattern")
        self.assertEqual(set(cand.event_ids), {"evt-f1", "evt-f2"})

    def test_duplicate_knowledge_detection_without_destructive_merge(self):
        """Verify duplicate knowledge check identifies high conceptual similarity without modifying records."""
        k1 = Knowledge(
            id="CON-001",
            type="constraint",
            title="Repository Persistence Isolation",
            content="Repository classes must only handle database persistence and never contain business rules.",
            status="active",
        )
        self.storage.write_knowledge(k1)

        proposed_title = "Repository persistence handling"
        proposed_content = "Repository classes should only handle persistence and database operations."

        duplicates = self.lifecycle.detect_duplicates(title=proposed_title, content=proposed_content, threshold=0.50)
        self.assertGreaterEqual(len(duplicates), 1)
        match = duplicates[0]
        self.assertEqual(match["id"], "CON-001")
        self.assertGreaterEqual(match["similarity"], 0.50)

        # Verify original record CON-001 is completely untouched
        original = self.storage.read_knowledge("CON-001")
        self.assertEqual(original.title, "Repository Persistence Isolation")

    def test_supersession_lifecycle(self):
        """Verify supersession updates old record status to 'superseded' while preserving old file."""
        old_k = Knowledge(
            id="DEC-009",
            type="decision",
            title="Use Redis for Session Storage",
            content="Sessions are stored in Redis cluster with 24h TTL.",
            status="active",
        )
        self.storage.write_knowledge(old_k)

        # Promote new decision that explicitly supersedes DEC-009
        new_promoted = self.api.promote_memory(
            event_ids=["evt-new-jwt"],
            knowledge_type="decision",
            title="Stateless JWT Session Storage",
            content="Reject Redis session store; use signed stateless JWT cookies.",
            knowledge_id="DEC-017",
            supersedes="DEC-009",
        )

        self.assertEqual(new_promoted["id"], "DEC-017")
        self.assertEqual(new_promoted["supersedes"], "DEC-009")

        # Verify old record is preserved on disk with status='superseded'
        old_record = self.storage.read_knowledge("DEC-009")
        self.assertIsNotNone(old_record)
        self.assertEqual(old_record.status, "superseded")
        self.assertEqual(old_record.provenance.get("superseded_by"), "DEC-017")

        # Verify new record is active
        new_record = self.storage.read_knowledge("DEC-017")
        self.assertEqual(new_record.status, "active")

    def test_archival_lifecycle(self):
        """Verify archiving a record updates its status to 'archived' without deleting canonical file."""
        k = Knowledge(
            id="LES-005",
            type="lesson",
            title="Legacy migration checkpoint",
            content="Historical note on Python 2 to 3 migration.",
            status="active",
        )
        self.storage.write_knowledge(k)

        archived = self.api.archive_knowledge("LES-005", reason="legacy_deprecated")
        self.assertIsNotNone(archived)
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["provenance"]["archival_reason"], "legacy_deprecated")

        # File is still present on disk
        persisted = self.storage.read_knowledge("LES-005")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, "archived")

    def test_retrieval_respects_lifecycle_status(self):
        """Verify search results expose status and do not hide historical/superseded records."""
        k_active = Knowledge(
            id="DEC-020",
            type="decision",
            title="Use PostgreSQL for primary store",
            content="Primary relational store is PostgreSQL 16.",
            status="active",
        )
        k_superseded = Knowledge(
            id="DEC-001",
            type="decision",
            title="Use SQLite for primary store",
            content="Initial relational store was SQLite.",
            status="superseded",
            supersedes=None,
        )
        self.storage.write_knowledge(k_active)
        self.storage.write_knowledge(k_superseded)
        self.indexer.rebuild_from_canonical(self.storage)

        results = self.api.search("relational store", policy="fts")["results"]
        ids = [r["id"] for r in results]
        self.assertIn("DEC-020", ids)
        self.assertIn("DEC-001", ids)

        # Check status field is intact
        for r in results:
            if r["id"] == "DEC-020":
                self.assertEqual(r["status"], "active")
            elif r["id"] == "DEC-001":
                self.assertEqual(r["status"], "superseded")

    def test_context_compiler_respects_lifecycle_status(self):
        """Verify ContextCompiler embeds [ACTIVE] and [SUPERSEDED] status tags in compiled markdown."""
        k_active = Knowledge(
            id="DEC-030",
            type="decision",
            title="Postgres Relational DB",
            content="Active database decision.",
            status="active",
        )
        k_sup = Knowledge(
            id="DEC-010",
            type="decision",
            title="MySQL Relational DB",
            content="Superseded database decision.",
            status="superseded",
            supersedes=None,
        )
        self.storage.write_knowledge(k_active)
        self.storage.write_knowledge(k_sup)

        compiled = self.api.compile_context(
            task="Design database adapter",
            memory_ids=["DEC-030", "DEC-010"],
            budget_tokens=500,
        )

        md = compiled["compiled_text"]
        self.assertIn("**DEC-030** [ACTIVE]", md)
        self.assertIn("**DEC-010** [SUPERSEDED]", md)

    def test_raw_event_history_preservation(self):
        """Verify raw events are never deleted or modified when candidates are promoted, superseded, or archived."""
        # 1. Write events
        for i in range(10):
            self.storage.record_event(
                Event(
                    id=f"evt-{i}",
                    type="task_step",
                    role="APP",
                    payload={"step": i, "status": "ok"},
                )
            )

        # 2. Promote one event
        self.api.promote_memory(
            event_ids=["evt-5"],
            knowledge_type="lesson",
            title="Step 5 Lesson",
            content="Key takeaway from step 5.",
            knowledge_id="LES-001",
        )

        # 3. Archive the lesson
        self.api.archive_knowledge("LES-001")

        # 4. Check all 10 original events + observable promotion/archival events are present
        events = self.storage.read_events()
        original_event_ids = {e.id for e in events}
        for i in range(10):
            self.assertIn(f"evt-{i}", original_event_ids)

    def test_event_volume_baseline_ratio(self):
        """Verify event volume baseline: 100 trivial events + 20 meaningful events results in a compact durable memory layer."""
        # Inject 100 trivial events
        for i in range(100):
            self.storage.record_event(
                Event(
                    id=f"triv-{i}",
                    type="grep_executed" if i % 2 == 0 else "file_opened",
                    role="APP",
                    payload={"idx": i, "file": f"module_{i % 5}.py"},
                )
            )

        # Inject 20 meaningful events (10 architecture decisions, 10 failures in 2 clusters)
        for i in range(10):
            self.storage.record_event(
                Event(
                    id=f"arch-{i}",
                    type="architecture_decision",
                    role="LEARNING",
                    payload={"summary": f"Decided on API design pattern {i}", "rationale": "Scalability"},
                )
            )
        for i in range(10):
            cluster = "Redis Connection Error" if i < 5 else "Postgres Lock Timeout"
            self.storage.record_event(
                Event(
                    id=f"fail-{i}",
                    type="test_failure",
                    role="APP",
                    payload={"error": f"{cluster} during execution {i}", "status": "error"},
                )
            )

        total_raw_events = len(self.storage.read_events())
        self.assertEqual(total_raw_events, 120)

        # Detect candidates
        candidates = self.lifecycle.detect_candidates()
        # 10 architecture decisions + 2 failure clusters = 12 candidates
        self.assertEqual(len(candidates), 12)

        # Agent voluntarily promotes 5 key candidates
        for c in candidates[:5]:
            self.api.promote_candidate(c.id)

        promoted_count = len(self.storage.list_knowledge())
        self.assertEqual(promoted_count, 5)

        promotion_ratio = promoted_count / total_raw_events
        # Durable knowledge is ~4.1% of raw event history
        self.assertLessEqual(promotion_ratio, 0.10)
        self.assertGreater(promotion_ratio, 0.0)


if __name__ == "__main__":
    unittest.main()
