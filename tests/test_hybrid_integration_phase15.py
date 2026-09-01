"""CORTEX Phase 15 Hybrid Retrieval Integration & Observability Test Suite."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from cortex_engine.api import CortexAPI
from cortex_engine.cli import CortexCLI
from cortex_engine.compiler import ContextCompiler
from cortex_engine.hybrid_router import (
    HybridRetrievalRouter,
    RouterPolicy,
    RoutedSearchResult,
    parse_policy,
)
from cortex_engine.indexer import CortexIndexer
from cortex_engine.models import Knowledge
from cortex_engine.retrieval_benchmark import (
    SemanticVectorIndex,
    build_benchmark_dataset,
)
from cortex_engine.storage import CortexStorage


class TestPhase15HybridIntegration(unittest.TestCase):
    """Automated integration tests for Phase 15 Hybrid Retrieval Integration."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace_root = Path(self.temp_dir)
        self.storage = CortexStorage(cortex_dir=self.workspace_root / ".cortex")
        self.indexer = CortexIndexer(storage=self.storage)
        self.vector_index = SemanticVectorIndex(db_path=self.storage.indexes_dir / "vector.db")
        self.compiler = ContextCompiler(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer, compiler=self.compiler)

        # Seed minimal canonical knowledge
        self.sample_records = [
            Knowledge(
                id="DEC-001",
                type="decision",
                title="Use PostgreSQL for Primary Relational Storage",
                content="Decision to standardize on PostgreSQL relational persistence across backend microservices.",
                status="active",
            ),
            Knowledge(
                id="DEC-007",
                type="decision",
                title="Reject Redis; Use Stateless JWTs",
                content="Decision to reject Redis session storage in favor of cryptographically signed stateless JWT authorization tokens.",
                status="active",
            ),
            Knowledge(
                id="CON-002",
                type="constraint",
                title="Repository Persistence Isolation",
                content="Architecture requires repository layer isolation to avoid direct database coupling between domain services.",
                status="active",
            ),
        ]
        for rec in self.sample_records:
            self.storage.write_knowledge(rec)

        self.indexer.rebuild_from_canonical(self.storage)
        self.vector_index.rebuild(self.storage)

    def tearDown(self):
        # Explicit cleanup to avoid Windows file locks
        if hasattr(self.indexer, "close"):
            self.indexer.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_policy_is_hybrid(self):
        """Verify default search policy is 'hybrid' and triggers appropriate router logic."""
        res = self.api.search("PostgreSQL relational storage")
        self.assertEqual(res["policy"], "policy_d_hybrid_expand_fallback")
        self.assertIn("results", res)
        self.assertIn("routing_trace", res)
        self.assertEqual(res["routing_trace"]["policy"], "policy_d_hybrid_expand_fallback")
        self.assertTrue(res["count"] > 0)
        self.assertEqual(res["results"][0]["id"], "DEC-001")

    def test_explicit_policy_overrides(self):
        """Verify explicit policy overrides for fts, hybrid, and semantic modes."""
        # 1. FTS mode
        res_fts = self.api.search("PostgreSQL", policy="fts")
        self.assertEqual(res_fts["policy"], "policy_a_fts_only")
        self.assertEqual(res_fts["routing_trace"]["primary_backend"], "fts")
        self.assertFalse(res_fts["routing_trace"]["fallback_triggered"])

        # 2. Semantic mode
        res_sem = self.api.search("stateless token authentication", policy="semantic")
        self.assertEqual(res_sem["policy"], "semantic")
        self.assertEqual(res_sem["routing_trace"]["primary_backend"], "semantic")
        self.assertTrue(len(res_sem["results"]) > 0)
        self.assertEqual(res_sem["results"][0]["id"], "DEC-007")

        # 3. Hybrid mode
        res_hyb = self.api.search("avoid direct coupling", policy="hybrid")
        self.assertEqual(res_hyb["policy"], "policy_d_hybrid_expand_fallback")

    def test_hybrid_fallback_on_weak_confidence(self):
        """Verify hybrid search falls back to semantic on conceptual queries and preserves dual provenance."""
        # Conceptual query with zero exact token overlap
        query = "mitigate cascading worker thread exhaustion on slow email APIs"
        res = self.api.search(query, policy="hybrid")
        trace = res["routing_trace"]
        self.assertTrue(trace["fallback_triggered"])
        self.assertEqual(trace["primary_backend"], "lexical_expansion")
        self.assertEqual(trace["secondary_backend"], "semantic")

    def test_semantic_index_unavailable_graceful_degradation(self):
        """Verify search gracefully degrades to lexical when vector.db is deleted/missing."""
        # Delete derived vector index
        vec_db = self.storage.indexes_dir / "vector.db"
        if vec_db.exists():
            vec_db.unlink()

        res = self.api.search("PostgreSQL relational storage", policy="hybrid")
        self.assertTrue(res["count"] > 0)
        self.assertEqual(res["results"][0]["id"], "DEC-001")
        self.assertEqual(res["results"][0]["retrieval_source"], "lexical_expansion")

    def test_semantic_index_corrupt_graceful_degradation(self):
        """Verify search gracefully degrades to lexical when vector.db is corrupt."""
        vec_db = self.storage.indexes_dir / "vector.db"
        vec_db.write_text("CORRUPTED_NON_SQLITE_DATA", encoding="utf-8")

        res = self.api.search("PostgreSQL relational storage", policy="hybrid")
        self.assertTrue(res["count"] > 0)
        self.assertEqual(res["results"][0]["id"], "DEC-001")

    def test_candidate_merging_and_provenance(self):
        """Verify candidate records found by multiple backends merge without duplicating IDs and retain scores."""
        raw_lex = [{"id": "DEC-007", "type": "decision", "title": "Reject Redis", "content": "JWTs"}]
        raw_sem = [
            {"id": "DEC-007", "type": "decision", "title": "Reject Redis", "content": "JWTs", "similarity_score": 0.88},
            {"id": "CON-002", "type": "constraint", "title": "Persistence", "content": "DB", "similarity_score": 0.72},
        ]
        router = HybridRetrievalRouter(storage=self.storage, indexer=self.indexer, vector_index=self.vector_index)
        merged = router.merge_candidates(raw_lex, raw_sem, primary_source="lexical_expansion", fallback_source="semantic")

        self.assertEqual(len(merged), 2)
        dec7 = next(r for r in merged if r.id == "DEC-007")
        self.assertIn("lexical_expansion", dec7.retrieval_source)
        self.assertIn("semantic", dec7.retrieval_source)
        self.assertEqual(dec7.scores["lexical_expansion_rank"], 1)
        self.assertEqual(dec7.scores["semantic_score"], 0.88)

    def test_routing_trace_and_event_observability(self):
        """Verify search logs observable memory_retrieval event with routing trace to events.jsonl."""
        res = self.api.search("PostgreSQL storage", task_id="task-smoke-01")
        self.assertIn("routing_trace", res)

        events = self.storage.read_events(event_type="memory_retrieval")
        self.assertTrue(len(events) > 0)
        last_evt = events[-1]
        self.assertEqual(last_evt.task_id, "task-smoke-01")
        self.assertIn("routing_trace", last_evt.payload)
        self.assertIn("policy", last_evt.payload)

    def test_context_compiler_compatibility(self):
        """Verify context compiler compiles search results seamlessly into Agent-facing context."""
        search_res = self.api.search("PostgreSQL")
        retrieved_ids = [r["id"] for r in search_res["results"]]

        ctx_pkg = self.api.compile_context(
            task="Design the user storage schema",
            memory_ids=retrieved_ids,
            budget_tokens=400,
            role="APP",
        )
        self.assertIn("DEC-001", ctx_pkg["compiled_text"])
        self.assertIn("DEC-001", ctx_pkg["included_ids"])
        self.assertTrue(ctx_pkg["total_tokens_estimate"] <= 400)

    def test_cli_diagnostics_and_reindex(self):
        """Verify CLI doctor, status, and reindex display hybrid retrieval state and vector index health."""
        cli = CortexCLI(workspace_root=self.workspace_root)
        
        # 1. Status
        status = cli.cmd_status()
        self.assertEqual(status["retrieval_policy"], "hybrid")
        self.assertEqual(status["vector_index_status"], "HEALTHY")

        # 2. Doctor
        doc = cli.cmd_doctor()
        self.assertEqual(doc["retrieval_policy"], "hybrid")
        check_names = [c["name"] for c in doc["checks"]]
        self.assertIn("Derived Vector Index", check_names)

        # 3. Reindex
        reindex_res = cli.cmd_reindex()
        self.assertEqual(reindex_res["status"], "reindexed")
        self.assertTrue(isinstance(reindex_res["indexed_fts"], dict))
        self.assertTrue(reindex_res["indexed_vector"] > 0)


if __name__ == "__main__":
    unittest.main()
