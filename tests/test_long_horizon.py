"""Tests for CORTEX Phase 7 Long-Horizon Benchmark Experiment."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.long_horizon import LongHorizonRunner, generate_50_task_sequence


class TestLongHorizonExperiment(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.runner = LongHorizonRunner(workspace_dir=self.temp_dir)
        self.runner.setup_environment()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_50_task_sequence_structure(self):
        """Verify the 50-task sequence contains exactly 50 tasks balanced across 5 horizon buckets."""
        tasks = generate_50_task_sequence()
        self.assertEqual(len(tasks), 50)

        buckets = ["1-10", "11-20", "21-30", "31-40", "41-50"]
        for b in buckets:
            b_tasks = [t for t in tasks if t.horizon_bucket == b]
            self.assertEqual(len(b_tasks), 10)

    def test_long_horizon_experiment_execution(self):
        """Run full 50-task long-horizon experiment and verify CORTEX maintains consistent recovery without degradation."""
        results = self.runner.run_experiment()

        self.assertEqual(results["total_tasks"], 50)
        overall = results["overall"]

        # CORTEX vs Vanilla Violations
        self.assertEqual(overall["cortex_total_violations"], 0)
        self.assertGreater(overall["vanilla_total_violations"], 30)

        # Memory Recovery Rate (92.3% in 50-task benchmark vs 0.0% vanilla)
        self.assertGreaterEqual(overall["cortex_recovery_rate"], 0.90)
        self.assertEqual(overall["vanilla_recovery_rate"], 0.0)

        # Unnecessary Retrieval Rate on Trivial Tasks
        self.assertEqual(overall["cortex_unnecessary_rate"], 0.0)

        # Stale Memory Mistakes
        self.assertEqual(overall["cortex_stale_errors"], 0)
        self.assertGreater(overall["vanilla_stale_errors"], 3)

    def test_horizon_degradation_trends(self):
        """Verify horizon degradation metrics: CORTEX retains high performance across early and late horizons."""
        results = self.runner.run_experiment()
        cortex_summary = results["cortex_summary"]
        vanilla_summary = results["vanilla_summary"]

        self.assertEqual(len(cortex_summary), 5)
        self.assertEqual(len(vanilla_summary), 5)

        # Check Horizon 1 (Tasks 1-10) vs Horizon 5 (Tasks 41-50) for CORTEX
        h1_cortex = cortex_summary[0]
        h5_cortex = cortex_summary[4]

        self.assertEqual(h1_cortex.task_success_rate, 1.0)
        self.assertEqual(h5_cortex.task_success_rate, 1.0)
        self.assertEqual(h1_cortex.architecture_violation_count, 0)
        self.assertEqual(h5_cortex.architecture_violation_count, 0)

        # Dynamic memory context remains bounded across early and late horizons
        self.assertLess(h5_cortex.avg_dynamic_context_tokens, 500)
        self.assertGreater(h5_cortex.avg_dynamic_context_tokens, 150)

    def test_role_isolation_ablation(self):
        """Compare isolated role contexts vs non-isolated continuous context."""
        results = self.runner.run_experiment()
        cortex_isolated = results["cortex_summary"]
        cortex_no_isolation = results["no_isolation_summary"]

        # Isolated contexts maintain small, fixed stable prefix (~450 tokens)
        # Non-isolated contexts accumulate continuous instruction overhead (~850 tokens)
        for iso, non_iso in zip(cortex_isolated, cortex_no_isolation):
            self.assertLess(iso.avg_stable_context_tokens, non_iso.avg_stable_context_tokens)
            self.assertEqual(iso.avg_stable_context_tokens, 450)
            self.assertEqual(non_iso.avg_stable_context_tokens, 850)


if __name__ == "__main__":
    unittest.main()
