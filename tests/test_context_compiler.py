"""Tests for CORTEX Phase 10 Context Compiler & Injection API."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.compiler import ContextCompiler
from cortex_engine.indexer import CortexIndexer
from cortex_engine.mcp_server import CortexMCPServer
from cortex_engine.models import Claim, Evidence, Knowledge
from cortex_engine.storage import CortexStorage
from cortex_engine.trial_runner import generate_30_trial_tasks


class TestContextCompiler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cortex_dir = Path(self.temp_dir) / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.indexer = CortexIndexer(storage=self.storage)
        self.compiler = ContextCompiler(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer, compiler=self.compiler)
        self.mcp_server = CortexMCPServer(api=self.api)

        # Seed knowledge records
        self.con1 = Knowledge(
            id="CON-001",
            type="constraint",
            title="Service Layer Business Logic",
            content="Business logic belongs in Service classes, never in Repositories.",
            status="active",
        )
        self.con2 = Knowledge(
            id="CON-003",
            type="constraint",
            title="No Payment Storage",
            content="Raw payment card details must never be stored in persistent storage.",
            status="active",
        )
        self.dec1 = Knowledge(
            id="DEC-007",
            type="decision",
            title="Stateless JWT Sessions",
            content="Use stateless signed JWTs for session auth.",
            status="active",
            supersedes="DEC-002",
        )
        self.dec2 = Knowledge(
            id="DEC-008",
            type="decision",
            title="Async Event Queue",
            content="Use async message queue for notifications.",
            status="active",
            supersedes="DEC-005",
        )
        self.fail1 = Knowledge(
            id="FAIL-001",
            type="failure",
            title="Fee Logic in Repo",
            content="Putting fee calculation in Repository caused schema migration lockups.",
            status="active",
        )
        self.noise1 = Knowledge(
            id="NOISE-001",
            type="lesson",
            title="Guideline 1",
            content="General coding style guidelines.",
            status="active",
        )

        for k in [self.con1, self.con2, self.dec1, self.dec2, self.fail1, self.noise1]:
            self.storage.write_knowledge(k)

        self.storage.write_claim(
            Claim(
                id="CLAIM-001",
                statement="Payment fee calculation is placed in PaymentService",
                status="verified",
                artifact={"path": "src/payment/service.py", "content_hash": "abc123"},
            )
        )
        self.indexer.rebuild_from_canonical(self.storage)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compile_selected_records(self):
        """Test compiling explicit subset of memory IDs."""
        result = self.api.compile_context(
            task="Implement refund calculation in PaymentService.",
            memory_ids=["CON-001", "DEC-007", "FAIL-001"],
            budget_tokens=500,
            role="APP",
        )

        self.assertEqual(result["selected_ids"], ["CON-001", "DEC-007", "FAIL-001"])
        self.assertEqual(result["included_ids"], ["CON-001", "DEC-007", "FAIL-001"])
        self.assertEqual(result["dropped_ids_budget"], [])
        self.assertIn("=== CRITICAL CONSTRAINTS ===", result["compiled_text"])
        self.assertIn("=== ACTIVE DECISIONS ===", result["compiled_text"])
        self.assertIn("=== RELEVANT FAILURES ===", result["compiled_text"])
        self.assertIn("SUPERSEDES: DEC-002", result["compiled_text"])

    def test_section_partitioning_and_omission_of_empty_sections(self):
        """Verify only populated sections appear in compiled context."""
        # Compile only constraint CON-001
        result = self.api.compile_context(
            task="Check service class constraints.",
            memory_ids=["CON-001"],
            budget_tokens=300,
        )

        self.assertIn("CRITICAL CONSTRAINTS", result["sections_present"])
        self.assertNotIn("ACTIVE DECISIONS", result["sections_present"])
        self.assertNotIn("RELEVANT FAILURES", result["sections_present"])
        self.assertNotIn("EVIDENCE", result["sections_present"])
        self.assertNotIn("HISTORICAL CONTEXT", result["sections_present"])

    def test_budget_enforcement_and_prioritization(self):
        """Verify that under tight budgets, constraints are prioritized over decisions and lessons."""
        # Tight budget: 40 tokens (only ~1-2 items can fit)
        result = self.api.compile_context(
            task="Refactor payments.",
            memory_ids=["CON-001", "DEC-007", "FAIL-001", "NOISE-001"],
            budget_tokens=40,
        )

        # Constraint CON-001 must be preserved
        self.assertIn("CON-001", result["included_ids"])
        # Lower priority items dropped due to budget
        self.assertTrue(len(result["dropped_ids_budget"]) > 0)
        self.assertIn("NOISE-001", result["dropped_ids_budget"])

    def test_deduplication(self):
        """Verify identical statements are deduplicated without losing IDs."""
        dup_k = Knowledge(
            id="CON-099",
            type="constraint",
            title="Duplicate Constraint",
            content="Business logic belongs in Service classes, never in Repositories.",
            status="active",
        )
        self.storage.write_knowledge(dup_k)

        result = self.api.compile_context(
            task="Check repo constraints.",
            memory_ids=["CON-001", "CON-099"],
            budget_tokens=500,
        )

        # Only one instance of the text should be present
        count_occurrences = result["compiled_text"].count("never in Repositories")
        self.assertEqual(count_occurrences, 1)

    def test_provenance_attachment(self):
        """Verify provenance metadata (source path, status, supersession) is attached."""
        result = self.api.compile_context(
            task="Verify auth sessions.",
            memory_ids=["DEC-007", "CLAIM-001"],
            budget_tokens=500,
        )

        prov = result["provenance"]
        self.assertEqual(len(prov), 2)
        dec_prov = next(p for p in prov if p["id"] == "DEC-007")
        self.assertEqual(dec_prov["source_path"], ".cortex/knowledge/decisions/DEC-007.json")
        self.assertEqual(dec_prov["supersedes"], "DEC-002")

        claim_prov = next(p for p in prov if p["id"] == "CLAIM-001")
        self.assertEqual(claim_prov["source_path"], ".cortex/knowledge/claims/CLAIM-001.json")

    def test_layout_configurations(self):
        """Verify layout generation for Layout 1, 2, 3, and default Layout 4."""
        for l_name in ["layout_1", "layout_2", "layout_3", "layout_4"]:
            res = self.api.compile_context(
                task="Test layout",
                memory_ids=["CON-001", "DEC-007"],
                layout=l_name,
            )
            self.assertIn("=== SYSTEM STABLE", res["compiled_text"])
            self.assertIn("=== CURRENT TASK ===", res["compiled_text"])

    def test_convenience_retrieve_context(self):
        """Verify retrieve_context executes search, selection, and compilation."""
        res = self.api.retrieve_context(query="payment fee", budget_tokens=500)
        self.assertIn("compiled_text", res)
        self.assertIn("included_ids", res)

    def test_mcp_tool_compile_context(self):
        """Verify MCP server successfully handles cortex_compile_context."""
        req = {
            "jsonrpc": "2.0",
            "id": "req-comp-1",
            "method": "tools/call",
            "params": {
                "name": "cortex_compile_context",
                "arguments": {
                    "task": "Add card preview feature",
                    "memory_ids": ["CON-003", "DEC-007"],
                    "budget_tokens": 400,
                    "role": "APP",
                },
            },
        }
        resp = self.mcp_server.handle_request(req)
        self.assertEqual(resp["id"], "req-comp-1")
        content_obj = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("compiled_text", content_obj)
        self.assertIn("CON-003", content_obj["included_ids"])

    def test_long_horizon_compilation_comparison(self):
        """Compare raw retrieval token size vs compiled context across 30 tasks."""
        tasks = generate_30_trial_tasks()
        raw_token_total = 0
        compiled_token_total = 0

        for t in tasks:
            if not t.materially_useful:
                continue
            # Raw retrieval
            s_res = self.api.search(query=t.user_prompt, limit=10)
            raw_tokens = len(json.dumps(s_res)) // 4
            raw_token_total += raw_tokens

            # Compiled context
            c_res = self.api.compile_context(
                task=t.user_prompt,
                memory_ids=t.expected_relevant_ids,
                budget_tokens=300,
            )
            compiled_token_total += c_res["memory_tokens_estimate"]

        self.assertLess(compiled_token_total, raw_token_total)


if __name__ == "__main__":
    unittest.main()
