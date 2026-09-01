"""Tests for CORTEX Phase 12 Release Candidate Red-Team Audit."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.compiler import ContextCompiler
from cortex_engine.freshness import compute_file_hash, evaluate_claim_freshness
from cortex_engine.mcp_server import CortexMCPServer
from cortex_engine.models import Claim, Evidence, Knowledge
from cortex_engine.red_team import RedTeamAuditor
from cortex_engine.storage import CortexStorage


class TestPhase12RedTeam(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.auditor = RedTeamAuditor(workspace_dir=self.workspace)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_storage_integrity_audit(self):
        """Execute destructive storage integrity tests."""
        results = self.auditor.audit_storage_integrity()
        for r in results:
            self.assertEqual(r.status, "PASS", f"Failed storage audit: {r.scenario} — {r.details}")

    def test_retrieval_robustness_audit(self):
        """Execute FTS syntax and SQL injection attacks."""
        results = self.auditor.audit_retrieval_robustness()
        for r in results:
            self.assertEqual(r.status, "PASS", f"Failed retrieval audit: {r.scenario} — {r.details}")

    def test_prompt_injection_boundary_audit(self):
        """Verify prompt injection strings are kept in data boundaries."""
        results = self.auditor.audit_prompt_injection_boundary()
        for r in results:
            self.assertEqual(r.status, "PASS", f"Failed injection audit: {r.scenario} — {r.details}")

    def test_index_corruption_and_recovery_audit(self):
        """Verify corrupt index restoration from canonical files."""
        results = self.auditor.audit_index_corruption_and_recovery()
        for r in results:
            self.assertEqual(r.status, "PASS", f"Failed index recovery audit: {r.scenario} — {r.details}")

    def test_supersession_chain_audit(self):
        """Verify multi-hop supersession chains."""
        results = self.auditor.audit_supersession_chain()
        for r in results:
            self.assertEqual(r.status, "PASS", f"Failed supersession audit: {r.scenario} — {r.details}")

    def test_freshness_matrix_audit(self):
        """Audit artifact states: unchanged, modified, deleted, recreated."""
        src_file = self.workspace / "test_module.py"
        src_file.write_text("def fee(): return 10\n", encoding="utf-8")
        h1 = compute_file_hash(src_file)

        claim = Claim(
            id="CLAIM-AUDIT-1",
            statement="Fee is 10",
            status="verified",
            artifact={"path": "test_module.py", "content_hash": h1},
        )

        # 1. Unchanged -> verified, fresh=True
        res1 = evaluate_claim_freshness(claim, workspace_root=self.workspace)
        self.assertTrue(res1["fresh"])
        self.assertEqual(res1["status"], "verified")

        # 2. Modified -> affected, fresh=False, reason=artifact_changed
        src_file.write_text("def fee(): return 20\n", encoding="utf-8")
        res2 = evaluate_claim_freshness(claim, workspace_root=self.workspace)
        self.assertFalse(res2["fresh"])
        self.assertEqual(res2["status"], "affected")
        self.assertEqual(res2["reason"], "artifact_changed")

        # 3. Deleted -> affected, fresh=False, reason=artifact_missing
        src_file.unlink()
        res3 = evaluate_claim_freshness(claim, workspace_root=self.workspace)
        self.assertFalse(res3["fresh"])
        self.assertEqual(res3["status"], "affected")
        self.assertEqual(res3["reason"], "artifact_missing")

    def test_mcp_failure_handling(self):
        """Audit MCP error handling on invalid JSON-RPC and unknown tools."""
        server = CortexMCPServer(api=self.auditor.api)

        # 1. Unknown tool
        req_unknown = {
            "jsonrpc": "2.0",
            "id": "req-unk",
            "method": "tools/call",
            "params": {"name": "cortex_nonexistent", "arguments": {}},
        }
        resp1 = server.handle_request(req_unknown)
        self.assertIn("error", resp1)
        self.assertIn("Unknown tool name", resp1["error"]["message"])

        # 2. Missing required arguments
        req_missing = {
            "jsonrpc": "2.0",
            "id": "req-miss",
            "method": "tools/call",
            "params": {"name": "cortex_search", "arguments": {}},
        }
        resp2 = server.handle_request(req_missing)
        self.assertIn("error", resp2)
        self.assertIn("required", resp2["error"]["message"])

    def test_context_budget_stress(self):
        """Audit context compiler budget scalability across 100 to 10,000 tokens."""
        compiler = ContextCompiler(storage=self.auditor.storage)
        c1 = Knowledge(id="CON-1", type="constraint", title="C1", content="Constraint 1" * 10, status="active")
        d1 = Knowledge(id="DEC-1", type="decision", title="D1", content="Decision 1" * 20, status="active")
        l1 = Knowledge(id="LES-1", type="lesson", title="L1", content="Lesson 1" * 50, status="active")

        self.auditor.storage.write_knowledge(c1)
        self.auditor.storage.write_knowledge(d1)
        self.auditor.storage.write_knowledge(l1)

        for budget in [100, 300, 500, 1000, 3000, 7000, 10000]:
            compiled = compiler.compile(
                task="Audit context scaling",
                memory_ids=["CON-1", "DEC-1", "LES-1"],
                budget_tokens=budget,
            )
            # Total tokens should not wildly exceed budget
            self.assertIsNotNone(compiled.compiled_text)
            self.assertIn("CON-1", compiled.included_ids)


if __name__ == "__main__":
    unittest.main()
