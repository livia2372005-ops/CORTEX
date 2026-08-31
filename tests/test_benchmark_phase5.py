"""Automated tests for Phase 5 Benchmark Suite and Natural Agent Usage."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.benchmark import BENCHMARK_TASKS, BenchmarkRunner, seed_benchmark_fixture
from cortex_engine.indexer import CortexIndexer
from cortex_engine.storage import CortexStorage


class TestPhase5Benchmark(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.runner = BenchmarkRunner(workspace_dir=self.temp_dir)
        self.runner.setup_fixture()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_benchmark_fixture_seeding(self):
        """Verify the synthetic repository contains required counts: 5 constraints, 8 decisions, 5 failures, 10 noise items."""
        all_knowledge = self.runner.storage.list_knowledge()
        constraints = [k for k in all_knowledge if k.type == "constraint"]
        decisions = [k for k in all_knowledge if k.type == "decision"]
        failures = [k for k in all_knowledge if k.type == "failure"]
        noise_items = [k for k in all_knowledge if k.id.startswith("NOISE")]

        self.assertGreaterEqual(len(constraints), 5)
        self.assertGreaterEqual(len(decisions), 8)
        self.assertGreaterEqual(len(failures), 5)
        self.assertGreaterEqual(len(noise_items), 10)

        # Verify superseded relationships exist
        superseded = [d for d in decisions if d.status == "superseded"]
        self.assertGreaterEqual(len(superseded), 2)
        superseded_ids = [s.id for s in superseded]
        self.assertIn("DEC-002", superseded_ids)
        self.assertIn("DEC-005", superseded_ids)

    def test_benchmark_execution_and_metrics(self):
        """Run the complete 12-task benchmark across Condition A (CORTEX) and Condition B (No-CORTEX)."""
        metrics = self.runner.run_benchmark()

        self.assertEqual(metrics["total_tasks"], 12)
        self.assertEqual(metrics["useful_tasks_count"], 9)
        self.assertEqual(metrics["irrelevant_tasks_count"], 3)

        cond_a = metrics["condition_a"]
        cond_b = metrics["condition_b"]

        # Natural Usage Rate: Useful tasks where CORTEX was used / Total useful tasks
        self.assertEqual(cond_a["natural_usage_rate"], 1.0)  # 9/9
        # Unnecessary Usage Rate: Irrelevant tasks where CORTEX was called / Total irrelevant tasks
        self.assertEqual(cond_a["unnecessary_usage_rate"], 0.0)  # 0/3

        # Recall Rate: Relevant evidence retrieved for useful tasks
        self.assertGreaterEqual(cond_a["recall_rate"], 0.88)
        # Noise Rate: Percentage of tasks that retrieved NOISE items (FTS keyword overlap)
        self.assertLessEqual(cond_a["noise_rate"], 0.25)

        # Architectural Violations: CORTEX available must yield significantly fewer violations than No-CORTEX
        self.assertLess(cond_a["total_architectural_violations"], cond_b["total_architectural_violations"])
        self.assertEqual(cond_a["total_architectural_violations"], 0)
        self.assertGreater(cond_b["total_architectural_violations"], 5)

        # Test Success: Condition A passes more tests than Condition B
        self.assertEqual(cond_a["tests_passed_count"], 12)
        self.assertLess(cond_b["tests_passed_count"], cond_a["tests_passed_count"])

    def test_superseded_decision_detection(self):
        """Test Category E tasks: verify that search for session/notification returns modern superseding records."""
        # Query for Redis session caching
        res_redis = self.runner.api.search("Redis session", limit=5)
        found_ids = [r["id"] for r in res_redis["results"]]
        # DEC-007 (superseding decision rejecting Redis) must be retrieved
        self.assertIn("DEC-007", found_ids)

        # Query for notification architecture
        res_notif = self.runner.api.search("notification", limit=5)
        notif_ids = [r["id"] for r in res_notif["results"]]
        # DEC-008 (superseding decision for async events) must be retrieved
        self.assertIn("DEC-008", notif_ids)

    def test_context_size_and_minimization(self):
        """Verify that returned memory evidence is concise and does not pollute context."""
        search_res = self.runner.api.search("payment fee logic", limit=5)
        serialized_chars = len(json.dumps(search_res))
        # 3 retrieved records: ~1.2 KB json payload (~300 tokens) vs full store (>15 KB / >3500 tokens)
        self.assertLess(serialized_chars, 2000)
        self.assertGreater(serialized_chars, 200)

    def test_deterministic_benchmark_repeatability(self):
        """Verify running benchmark twice produces 100% identical metric outputs."""
        run1 = self.runner.run_benchmark()
        run2 = self.runner.run_benchmark()

        self.assertEqual(run1["condition_a"]["natural_usage_rate"], run2["condition_a"]["natural_usage_rate"])
        self.assertEqual(run1["condition_a"]["total_architectural_violations"], run2["condition_a"]["total_architectural_violations"])
        self.assertEqual(run1["condition_b"]["total_architectural_violations"], run2["condition_b"]["total_architectural_violations"])


if __name__ == "__main__":
    unittest.main()
