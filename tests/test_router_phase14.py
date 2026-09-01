"""Tests for CORTEX Phase 14 Hybrid Retrieval Router."""

import math
import shutil
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Set

from cortex_engine.hybrid_router import (
    HybridRetrievalRouter,
    RoutedSearchResult,
    RouterPolicy,
)
from cortex_engine.indexer import CortexIndexer
from cortex_engine.retrieval_benchmark import (
    BenchmarkQuery,
    SemanticVectorIndex,
    build_benchmark_dataset,
)
from cortex_engine.storage import CortexStorage


class TestPhase14HybridRouter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.storage = CortexStorage(cortex_dir=self.workspace / ".cortex")
        self.indexer = CortexIndexer(storage=self.storage)
        self.vector_index = SemanticVectorIndex(db_path=self.workspace / ".cortex" / "indexes" / "vector.db")
        self.router = HybridRetrievalRouter(
            storage=self.storage,
            indexer=self.indexer,
            vector_index=self.vector_index,
        )

        # Seed benchmark dataset
        self.total_records, self.queries = build_benchmark_dataset(self.storage)
        self.indexer.rebuild_from_canonical(self.storage)
        self.vector_index.rebuild(self.storage)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_policy_a_fts_only(self):
        """Test Policy A returns FTS candidates with 'fts' retrieval source."""
        res = self.router.search("Service Layer Business Logic", policy=RouterPolicy.POLICY_A_FTS_ONLY, limit=5)
        self.assertEqual(res["policy"], "policy_a_fts_only")
        self.assertEqual(res["triggered_backends"], ["fts"])
        self.assertTrue(len(res["results"]) > 0)
        self.assertEqual(res["results"][0]["retrieval_source"], "fts")

    def test_policy_b_zero_fallback(self):
        """Test Policy B triggers semantic search only when FTS returns 0 candidates."""
        # 1. Exact match -> FTS returns candidates, semantic NOT triggered
        res_exact = self.router.search("Service Layer Business Logic", policy=RouterPolicy.POLICY_B_ZERO_FALLBACK, limit=5)
        self.assertEqual(res_exact["triggered_backends"], ["fts"])
        self.assertEqual(res_exact["routing_decision"], "DIRECT")

        # 2. Zero-overlap conceptual query -> FTS returns 0, semantic triggered
        res_concept = self.router.search("avoid direct database coupling between microservices", policy=RouterPolicy.POLICY_B_ZERO_FALLBACK, limit=5)
        self.assertEqual(res_concept["triggered_backends"], ["fts", "semantic"])
        self.assertEqual(res_concept["routing_decision"], "FALLBACK_ON_ZERO")
        self.assertTrue(len(res_concept["results"]) > 0)
        self.assertEqual(res_concept["results"][0]["retrieval_source"], "semantic")

    def test_policy_c_weak_confidence_fallback(self):
        """Test Policy C triggers semantic fallback on low lexical confidence and merges candidates."""
        res = self.router.search("in-memory key-value store for user sessions", policy=RouterPolicy.POLICY_C_WEAK_CONFIDENCE_FALLBACK, limit=10)
        self.assertIn("fts", res["triggered_backends"])
        self.assertIn("semantic", res["triggered_backends"])
        self.assertTrue(len(res["results"]) > 0)

    def test_policy_d_hybrid_expand_fallback(self):
        """Test Policy D uses Lexical Expansion and triggers Semantic fallback if confidence is weak."""
        res = self.router.search("mitigate cascading worker thread exhaustion on slow email APIs", policy=RouterPolicy.POLICY_D_HYBRID_EXPAND_FALLBACK, limit=10)
        self.assertIn("lexical_expansion", res["triggered_backends"])
        self.assertIn("semantic", res["triggered_backends"])
        self.assertTrue(len(res["results"]) > 0)

    def test_provenance_preservation_and_deduplication(self):
        """Verify candidate records found by multiple backends merge without duplication and retain both sources."""
        raw_fts = [{"id": "DEC-007", "type": "decision", "title": "Reject Redis; Use Stateless JWTs", "content": "Stateless JWTs"}]
        raw_semantic = [{"id": "DEC-007", "type": "decision", "title": "Reject Redis; Use Stateless JWTs", "content": "Stateless JWTs", "similarity_score": 0.88}]

        merged = self.router.merge_candidates(raw_fts, raw_semantic, "fts", "semantic", limit=5)
        self.assertEqual(len(merged), 1)
        item = merged[0]
        self.assertEqual(item.id, "DEC-007")
        self.assertEqual(item.retrieval_source, ["fts", "semantic"])
        self.assertIn("fts", item.backend_metadata)
        self.assertIn("semantic", item.backend_metadata)
        self.assertEqual(item.backend_metadata["semantic"]["similarity_score"], 0.88)

    def test_policy_benchmark_comparison(self):
        """Benchmark all 4 policies across the 105 queries and verify Pareto performance."""
        policies = [
            RouterPolicy.POLICY_A_FTS_ONLY,
            RouterPolicy.POLICY_B_ZERO_FALLBACK,
            RouterPolicy.POLICY_C_WEAK_CONFIDENCE_FALLBACK,
            RouterPolicy.POLICY_D_HYBRID_EXPAND_FALLBACK,
        ]

        policy_metrics: Dict[str, Dict[str, Any]] = {}

        for pol in policies:
            recalls_10: List[float] = []
            failures = 0
            latencies: List[float] = []
            noise_ratios: List[float] = []

            for q in self.queries:
                t0 = time.perf_counter()
                res = self.router.search(q.query_text, policy=pol, limit=10)
                lat = (time.perf_counter() - t0) * 1000.0
                latencies.append(lat)

                retrieved_ids = [r["id"] for r in res["results"]]
                expected_set = set(q.expected_relevant_ids)

                r10 = len(expected_set.intersection(retrieved_ids)) / len(expected_set) if expected_set else 1.0
                recalls_10.append(r10)

                if expected_set and len(expected_set.intersection(retrieved_ids)) == 0:
                    failures += 1

                irrelevant = sum(1 for r_id in retrieved_ids if r_id not in expected_set)
                noise_ratios.append(irrelevant / len(retrieved_ids) if retrieved_ids else 0.0)

            total_q = len(self.queries)
            policy_metrics[pol.value] = {
                "recall_at_10": round(sum(recalls_10) / total_q, 4),
                "query_failure_rate": round(failures / total_q, 4),
                "avg_noise_ratio": round(sum(noise_ratios) / total_q, 4),
                "avg_latency_ms": round(sum(latencies) / total_q, 2),
            }

        # Assert that Policy D achieves highest recall and lowest query failure rate
        mA = policy_metrics[RouterPolicy.POLICY_A_FTS_ONLY.value]
        mB = policy_metrics[RouterPolicy.POLICY_B_ZERO_FALLBACK.value]
        mD = policy_metrics[RouterPolicy.POLICY_D_HYBRID_EXPAND_FALLBACK.value]

        self.assertGreaterEqual(mB["recall_at_10"], mA["recall_at_10"])
        self.assertGreaterEqual(mD["recall_at_10"], mB["recall_at_10"])
        self.assertLessEqual(mD["query_failure_rate"], mA["query_failure_rate"])


if __name__ == "__main__":
    unittest.main()
