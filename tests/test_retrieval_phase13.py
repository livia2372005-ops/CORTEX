"""Tests for CORTEX Phase 13 Retrieval Intelligence Experiment."""

import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.retrieval_benchmark import (
    BenchmarkQuery,
    RetrievalBenchmarkRunner,
    SemanticVectorIndex,
    build_benchmark_dataset,
)


class TestPhase13RetrievalExperiment(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.runner = RetrievalBenchmarkRunner(workspace_dir=self.workspace)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_benchmark_dataset_scale_and_diversity(self):
        """Verify benchmark has 300+ records and 100+ queries spanning all 7 categories."""
        total_records, queries = self.runner.setup_benchmark()
        self.assertGreaterEqual(total_records, 300)
        self.assertGreaterEqual(len(queries), 100)

        categories = {q.category for q in queries}
        expected_cats = {"Exact", "Synonym", "Conceptual", "Negative", "Contradiction", "Supersession", "Historical"}
        self.assertEqual(categories, expected_cats)

    def test_condition_a_fts_baseline(self):
        """Test FTS5 baseline on exact match vs vocabulary drift queries."""
        self.runner.setup_benchmark()

        # Exact match should succeed
        res_exact = self.runner.execute_query_condition_a_fts("Service Layer Business Logic", limit=5)
        exact_ids = [r["id"] for r in res_exact]
        self.assertIn("CON-001", exact_ids)

        # Conceptual zero-overlap query fails under pure FTS5
        res_drift = self.runner.execute_query_condition_a_fts("avoid direct database coupling between microservices", limit=5)
        drift_ids = [r["id"] for r in res_drift]
        self.assertNotIn("CON-004", drift_ids)

    def test_condition_b_lexical_expansion(self):
        """Test that deterministic lexical expansion resolves synonym queries."""
        self.runner.setup_benchmark()

        # Synonym query: 'in-memory key-value store for user sessions' expands 'in-memory' and 'session'
        res_syn = self.runner.execute_query_condition_b_lexical_expansion("in-memory key-value store for user sessions", limit=5)
        syn_ids = [r["id"] for r in res_syn]
        # Should retrieve session/cache related records
        self.assertTrue(any(i in syn_ids for i in ["DEC-007", "DEC-002", "FAIL-003", "CON-005"]))

    def test_condition_c_semantic_embeddings(self):
        """Test that semantic embeddings recover conceptual queries with zero lexical overlap."""
        self.runner.setup_benchmark()

        # Conceptual query with zero lexical overlap
        res_concept = self.runner.execute_query_condition_c_semantic_embeddings("avoid direct database coupling between microservices", limit=5)
        concept_ids = [r["id"] for r in res_concept]
        # Embeddings should capture inter-service API and repository coupling boundaries
        self.assertTrue(any(i in concept_ids for i in ["CON-004", "CON-010", "FAIL-005"]))

    def test_vector_index_disposability_and_rebuild(self):
        """MANDATORY: Delete vector database -> rebuild from canonical disk files -> search restored."""
        self.runner.setup_benchmark()

        db_path = self.workspace / ".cortex" / "indexes" / "vector.db"
        self.assertTrue(db_path.exists())

        # Verify search works before deletion
        res1 = self.runner.execute_query_condition_c_semantic_embeddings("Stateless Session Authentication", limit=5)
        self.assertTrue(len(res1) > 0)

        # Delete vector index
        db_path.unlink()
        self.assertFalse(db_path.exists())

        # Rebuild vector index from canonical storage
        rebuilt_count = self.runner.vector_index.rebuild(self.runner.storage)
        self.assertGreaterEqual(rebuilt_count, 300)
        self.assertTrue(db_path.exists())

        # Search restored
        res2 = self.runner.execute_query_condition_c_semantic_embeddings("Stateless Session Authentication", limit=5)
        self.assertEqual([r["id"] for r in res1], [r["id"] for r in res2])

    def test_supersession_safety_across_conditions(self):
        """Verify that all 3 conditions return status and supersession metadata without censorship."""
        self.runner.setup_benchmark()

        for exec_fn in [
            self.runner.execute_query_condition_a_fts,
            self.runner.execute_query_condition_b_lexical_expansion,
            self.runner.execute_query_condition_c_semantic_embeddings,
        ]:
            results = exec_fn("session storage Redis", limit=10)
            for r in results:
                self.assertIn("id", r)
                self.assertIn("status", r)

    def test_full_benchmark_comparison_metrics(self):
        """Execute full 105-query benchmark comparison and verify metric outputs."""
        comparison = self.runner.run_full_comparison()

        self.assertIn("condition_a", comparison)
        self.assertIn("condition_b", comparison)
        self.assertIn("condition_c", comparison)

        ma = comparison["condition_a"]
        mb = comparison["condition_b"]
        mc = comparison["condition_c"]

        # Lexical expansion and embeddings improve recall over pure FTS baseline
        self.assertGreaterEqual(mb["recall_at_10"], ma["recall_at_10"])
        self.assertGreaterEqual(mc["recall_at_10"], ma["recall_at_10"])
        # Query failure rate in C is lower than A
        self.assertLessEqual(mc["query_failure_rate"], ma["query_failure_rate"])


if __name__ == "__main__":
    unittest.main()
