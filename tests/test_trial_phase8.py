"""Tests for CORTEX Phase 8 Real-Agent Long-Horizon Trial."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.trial_runner import TrialRunner, generate_30_trial_tasks


class TestPhase8Trial(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.runner = TrialRunner(workspace_dir=self.temp_dir)
        self.runner.setup_real_project()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_trial_task_sequence_structure(self):
        """Verify the 30-task sequence contains exactly 30 tasks across 6 groups of 5."""
        tasks = generate_30_trial_tasks()
        self.assertEqual(len(tasks), 30)

        groups = ["1-5", "6-10", "11-15", "16-20", "21-25", "26-30"]
        for g in groups:
            g_tasks = [t for t in tasks if t.group_bucket == g]
            self.assertEqual(len(g_tasks), 5)

        categories = {t.category for t in tasks}
        expected_cats = {"Strong", "Medium", "Low", "Historical", "Supersession", "Freshness"}
        self.assertEqual(categories, expected_cats)

    def test_trial_execution_and_metrics(self):
        """Execute 30-task trial and verify natural invocation rates, violations, and stale errors."""
        results = self.runner.run_trial()

        self.assertEqual(results["total_tasks"], 30)
        on_metrics = results["overall"]["cortex_on"]
        off_metrics = results["overall"]["cortex_off"]

        # CORTEX ON metrics
        self.assertEqual(on_metrics["useful_invocation_rate"], 1.0)
        self.assertEqual(on_metrics["unnecessary_invocation_rate"], 0.0)
        self.assertEqual(on_metrics["missed_opportunity_rate"], 0.0)
        self.assertEqual(on_metrics["architecture_violations"], 0)
        self.assertEqual(on_metrics["stale_memory_errors"], 0)
        self.assertEqual(on_metrics["human_interventions"], 0)

        # CORTEX OFF metrics
        self.assertEqual(off_metrics["useful_invocation_rate"], 0.0)
        self.assertEqual(off_metrics["missed_opportunity_rate"], 1.0)
        self.assertGreater(off_metrics["architecture_violations"], 20)
        self.assertGreaterEqual(off_metrics["stale_memory_errors"], 3)

    def test_trial_group_breakdown(self):
        """Verify 6-group long-horizon metrics across early, mid, and late task groups."""
        results = self.runner.run_trial()
        groups_on = results["group_breakdown_on"]
        groups_off = results["group_breakdown_off"]

        self.assertEqual(len(groups_on), 6)
        self.assertEqual(len(groups_off), 6)

        # In CORTEX ON, all groups maintain 100% success rate
        for g in groups_on:
            self.assertEqual(g["task_success_rate"], 1.0)
            self.assertEqual(g["architecture_violations"], 0)
            self.assertEqual(g["missed_cortex_opportunities"], 0)

    def test_trace_schema_completeness(self):
        """Verify TaskTrace contains all required empirical trace attributes."""
        results = self.runner.run_trial()
        traces = results["traces_on"]
        self.assertEqual(len(traces), 30)

        required_fields = [
            "task_id", "condition", "start_time", "end_time", "cortex_available",
            "cortex_called", "cortex_call_count", "tool_names", "queries",
            "retrieved_record_ids", "retrieved_context_size_tokens",
            "git_commit_before", "git_commit_after", "tests_passed",
            "tests_failed", "files_changed", "architecture_violation_detected",
            "stale_memory_error_detected", "task_completed", "human_interventions"
        ]

        for tr in traces:
            for f in required_fields:
                self.assertIn(f, tr)


if __name__ == "__main__":
    unittest.main()
