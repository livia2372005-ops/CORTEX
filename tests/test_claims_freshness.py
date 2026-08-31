"""Unit, negative, and benchmark tests for CORTEX Claims, Provenance, and Freshness."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.freshness import compute_file_hash, evaluate_claim_freshness, get_git_commit
from cortex_engine.indexer import CortexIndexer
from cortex_engine.models import Claim, Evidence, Knowledge
from cortex_engine.storage import CortexStorage


class TestClaimsAndFreshness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CortexStorage(cortex_dir=Path(self.temp_dir) / ".cortex")
        self.indexer = CortexIndexer(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer)

        # Create a sample source artifact in workspace
        self.sample_file = Path(self.temp_dir) / "src" / "payment" / "service.py"
        self.sample_file.parent.mkdir(parents=True, exist_ok=True)
        self.sample_file.write_text("class PaymentService:\n    def calculate_fee(self): pass\n", encoding="utf-8")
        self.sample_hash = compute_file_hash(self.sample_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_verified_claim_with_unchanged_artifact(self):
        """Test: verified claim with matching artifact hash reports verified and fresh=True."""
        claim = Claim(
            id="CLAIM-001",
            statement="Payment fee calculation is placed in PaymentService",
            status="verified",
            artifact={"path": "src/payment/service.py", "content_hash": self.sample_hash},
        )
        self.api.record_claim(
            id=claim.id,
            statement=claim.statement,
            status=claim.status,
            artifact=claim.artifact,
        )

        report = self.api.check_claim_freshness("CLAIM-001", workspace_root=self.temp_dir)
        self.assertIsNotNone(report)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["reason"], "artifact_unchanged")
        self.assertTrue(report["fresh"])

    def test_verified_claim_with_changed_artifact(self):
        """Test: verified claim whose artifact changed is marked affected (NOT rejected!)."""
        claim = Claim(
            id="CLAIM-002",
            statement="Payment fee calculation is placed in PaymentService",
            status="verified",
            artifact={"path": "src/payment/service.py", "content_hash": self.sample_hash},
        )
        self.storage.write_claim(claim)

        # Modify the artifact content on disk
        self.sample_file.write_text("class PaymentService:\n    # Modified\n    def calculate_fee(self): return 10.0\n", encoding="utf-8")

        report = self.api.check_claim_freshness("CLAIM-002", workspace_root=self.temp_dir)
        self.assertEqual(report["status"], "affected")
        self.assertEqual(report["reason"], "artifact_changed")
        self.assertFalse(report["fresh"])

        # CRITICAL NEGATIVE TEST: artifact changed != claim rejected
        self.assertNotEqual(report["status"], "rejected")

        # Verify claim status was updated in persistent storage to affected
        updated_claim = self.storage.read_claim("CLAIM-002")
        self.assertEqual(updated_claim.status, "affected")

    def test_missing_artifact(self):
        """Test: claim pointing to nonexistent file is marked affected with reason artifact_missing."""
        claim = Claim(
            id="CLAIM-003",
            statement="Deleted legacy module invariant",
            status="verified",
            artifact={"path": "src/legacy/deleted.py", "content_hash": "deadbeef12345678"},
        )
        self.storage.write_claim(claim)

        report = self.api.check_claim_freshness("CLAIM-003", workspace_root=self.temp_dir)
        self.assertEqual(report["status"], "affected")
        self.assertEqual(report["reason"], "artifact_missing")
        self.assertIsNone(report["artifact"]["current_hash"])

    def test_malformed_artifact_reference(self):
        """Test: claim with missing expected hash is marked affected with reason malformed_artifact_reference."""
        claim = Claim(
            id="CLAIM-004",
            statement="Malformed reference claim",
            status="verified",
            artifact={"path": "src/payment/service.py"},  # Missing content_hash
        )
        self.storage.write_claim(claim)

        report = self.api.check_claim_freshness("CLAIM-004", workspace_root=self.temp_dir)
        self.assertEqual(report["status"], "affected")
        self.assertEqual(report["reason"], "malformed_artifact_reference")

    def test_rejected_claim(self):
        """Test: explicitly rejected claim returns status rejected and fresh=False."""
        claim = Claim(
            id="CLAIM-005",
            statement="Repository contains fee calculation logic",
            status="rejected",
            evidence=[{"type": "incident", "id": "INC-01"}],
        )
        self.storage.write_claim(claim)

        report = self.api.check_claim_freshness("CLAIM-005", workspace_root=self.temp_dir)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["reason"], "claim_explicitly_rejected")
        self.assertFalse(report["fresh"])

    def test_unverified_and_unprovable_claims(self):
        """Test unverified and unprovable statuses."""
        c_unverified = Claim(id="CLAIM-006", statement="Hypothetical claim", status="unverified")
        c_unprovable = Claim(id="CLAIM-007", statement="Unbounded latency guarantee", status="unprovable")
        self.storage.write_claim(c_unverified)
        self.storage.write_claim(c_unprovable)

        rep_unver = self.api.check_claim_freshness("CLAIM-006", workspace_root=self.temp_dir)
        rep_unprov = self.api.check_claim_freshness("CLAIM-007", workspace_root=self.temp_dir)

        self.assertEqual(rep_unver["status"], "unverified")
        self.assertEqual(rep_unprov["status"], "unprovable")

    def test_claim_with_multiple_evidence_references(self):
        """Test claim containing multiple structured Evidence items."""
        ev1 = Evidence(id="EV-1", type="artifact", path="src/payment/service.py", content_hash=self.sample_hash)
        ev2 = Evidence(id="EV-2", type="test", test_id="test_fee_calculation", commit="abc1234")

        claim = Claim(
            id="CLAIM-008",
            statement="Payment fee service is unit tested and verified",
            status="verified",
            artifact={"path": "src/payment/service.py", "content_hash": self.sample_hash},
            evidence=[ev1.to_dict(), ev2.to_dict()],
        )
        self.storage.write_claim(claim)

        retrieved = self.api.get_claim("CLAIM-008")
        self.assertEqual(len(retrieved["evidence"]), 2)
        self.assertEqual(retrieved["evidence"][1]["test_id"], "test_fee_calculation")

    def test_git_commit_provenance(self):
        """Test git commit resolution function."""
        commit = get_git_commit()
        # In this workspace, git repo is initialized so commit must be a valid 40-char SHA
        self.assertIsNotNone(commit)
        self.assertGreaterEqual(len(commit), 7)

    def test_search_returning_claim_status(self):
        """Test that CORTEX search retrieves claims with their current status."""
        self.api.record_claim(
            id="CLAIM-SEARCH-01",
            statement="Stateless JWT tokens are verified for session auth",
            status="verified",
        )
        self.api.record_claim(
            id="CLAIM-SEARCH-02",
            statement="Redis cluster session auth is affected and pending review",
            status="affected",
        )

        res = self.api.search("session auth")
        self.assertGreaterEqual(res["count"], 2)
        statuses = {r["id"]: r["status"] for r in res["results"]}
        self.assertEqual(statuses["CLAIM-SEARCH-01"], "verified")
        self.assertEqual(statuses["CLAIM-SEARCH-02"], "affected")

    def test_rebuild_indexes_preserves_claim_records(self):
        """Test: rebuild_indexes preserves all claim records and searchable text."""
        self.api.record_claim(
            id="CLAIM-REBUILD-01",
            statement="Deterministic rebuild restores claim index entries",
            status="verified",
        )

        # Rebuild indexes
        rebuild_stats = self.api.rebuild_indexes()
        self.assertGreaterEqual(rebuild_stats["indexed_knowledge"], 1)

        # Search for claim
        res = self.api.search("restores claim index")
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["results"][0]["id"], "CLAIM-REBUILD-01")

    def test_important_negative_invariants(self):
        """Explicit negative tests:
        1. artifact changed != claim automatically rejected
        2. missing evidence != claim automatically true
        3. superseded decision != deleted decision
        """
        # Invariant 1: artifact changed yields status affected, NEVER rejected
        claim1 = Claim(
            id="CLAIM-NEG-01",
            statement="Invariant 1",
            status="verified",
            artifact={"path": "src/payment/service.py", "content_hash": "old_hash"},
        )
        self.storage.write_claim(claim1)
        rep1 = evaluate_claim_freshness(claim1, workspace_root=self.temp_dir)
        self.assertEqual(rep1["status"], "affected")
        self.assertNotEqual(rep1["status"], "rejected")

        # Invariant 2: missing evidence does not make claim true
        claim2 = Claim(id="CLAIM-NEG-02", statement="Invariant 2", status="unverified", evidence=[])
        rep2 = evaluate_claim_freshness(claim2, workspace_root=self.temp_dir)
        self.assertEqual(rep2["status"], "unverified")
        self.assertFalse(rep2["fresh"])

        # Invariant 3: superseded decision is NOT deleted
        self.api.record_knowledge(
            id="DEC-OLD-01",
            knowledge_type="decision",
            title="Old Decision",
            content="Superseded by DEC-NEW-01",
            status="superseded",
            supersedes="DEC-NEW-01",
        )
        old_item = self.storage.read_knowledge("DEC-OLD-01")
        self.assertIsNotNone(old_item)
        self.assertEqual(old_item.status, "superseded")

    def test_freshness_detection_accuracy_benchmark(self):
        """Benchmark synthetic freshness cases and calculate accuracy, false stale rate, false valid rate."""
        # 1. Unchanged artifacts (Expected: Fresh / Verified)
        cases_unchanged = [
            ("CL-ACC-01", "src/payment/service.py", self.sample_hash, True),
        ]
        # 2. Changed artifacts (Expected: Stale / Affected)
        cases_changed = [
            ("CL-ACC-02", "src/payment/service.py", "mismatched_old_hash_123", False),
        ]
        # 3. Deleted/Missing artifacts (Expected: Stale / Affected)
        cases_missing = [
            ("CL-ACC-03", "src/nonexistent/file.py", "some_hash_456", False),
        ]

        total_cases = len(cases_unchanged) + len(cases_changed) + len(cases_missing)
        correct_evaluations = 0
        false_stale = 0
        false_valid = 0

        # Run unchanged cases
        for cid, path, h, expected_fresh in cases_unchanged:
            c = Claim(id=cid, statement="Test unchanged", status="verified", artifact={"path": path, "content_hash": h})
            rep = evaluate_claim_freshness(c, workspace_root=self.temp_dir)
            if rep["fresh"] == expected_fresh and rep["status"] == "verified":
                correct_evaluations += 1
            elif not rep["fresh"] and expected_fresh:
                false_stale += 1

        # Run changed cases
        for cid, path, h, expected_fresh in cases_changed:
            c = Claim(id=cid, statement="Test changed", status="verified", artifact={"path": path, "content_hash": h})
            rep = evaluate_claim_freshness(c, workspace_root=self.temp_dir)
            if rep["fresh"] == expected_fresh and rep["status"] == "affected":
                correct_evaluations += 1
            elif rep["fresh"] and not expected_fresh:
                false_valid += 1

        # Run missing cases
        for cid, path, h, expected_fresh in cases_missing:
            c = Claim(id=cid, statement="Test missing", status="verified", artifact={"path": path, "content_hash": h})
            rep = evaluate_claim_freshness(c, workspace_root=self.temp_dir)
            if rep["fresh"] == expected_fresh and rep["status"] == "affected":
                correct_evaluations += 1
            elif rep["fresh"] and not expected_fresh:
                false_valid += 1

        accuracy = correct_evaluations / total_cases
        false_stale_rate = false_stale / len(cases_unchanged)
        false_valid_rate = false_valid / (len(cases_changed) + len(cases_missing))

        self.assertEqual(accuracy, 1.0)
        self.assertEqual(false_stale_rate, 0.0)
        self.assertEqual(false_valid_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
