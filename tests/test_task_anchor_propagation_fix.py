"""Regression test suite for TaskAnchor propagation across Antigravity hook processes."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.antigravity_hook import process_hook_payload
from cortex_engine.storage import CortexStorage


class TestTaskAnchorPropagationFix(unittest.TestCase):
    """Verify reliable TaskAnchor propagation into Antigravity tool telemetry across processes."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="cortex_anchor_fix_")
        self.workspace1 = Path(self.temp_dir) / "workspace1"
        self.workspace2 = Path(self.temp_dir) / "workspace2"
        self.workspace1.mkdir(parents=True, exist_ok=True)
        self.workspace2.mkdir(parents=True, exist_ok=True)

        self.api1 = CortexAPI(workspace_root=self.workspace1)
        self.api2 = CortexAPI(workspace_root=self.workspace2)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_process_boundary_simulation(self) -> None:
        """Simulate separate hook subprocess resolving active anchor created via API/CLI."""
        # Process 1: Start task anchor
        task_data = self.api1.start_task(
            task_label="Refactor Database Driver",
            prompt="Implement retry policy",
            conversation_id="conv-proc-001",
            anchor_id="task-proc-001",
        )
        self.assertEqual(task_data["anchor_id"], "task-proc-001")

        # Process 2: Execute actual Antigravity hook command via subprocess CLI
        hook_payload = {
            "conversationId": "conv-proc-001",
            "stepIdx": 1,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/test_db.py"},
            },
        }

        env = os.environ.copy()
        env["PYTHONPATH"] = "d:/App/CORTEX"

        # Pre hook
        proc_pre = subprocess.run(
            [sys.executable, "-m", "cortex_engine.antigravity_hook", "--event", "pre"],
            input=json.dumps(hook_payload),
            cwd=str(self.workspace1),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_pre.returncode, 0)
        self.assertEqual(json.loads(proc_pre.stdout), {"decision": "allow"})

        # Post hook
        hook_payload["error"] = None
        proc_post = subprocess.run(
            [sys.executable, "-m", "cortex_engine.antigravity_hook", "--event", "post"],
            input=json.dumps(hook_payload),
            cwd=str(self.workspace1),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_post.returncode, 0)

        # Verify activity.jsonl on disk
        events = self.api1.list_activity(conversation_id="conv-proc-001")
        # task_start, pre tool_call, post tool_result
        self.assertGreaterEqual(len(events), 3)

        tool_events = [e for e in events if e.get("action_type") in ("tool_call", "tool_result")]
        self.assertEqual(len(tool_events), 2)
        for te in tool_events:
            self.assertEqual(te.get("anchor_id"), "task-proc-001")
            self.assertEqual(te.get("task_id"), "task-proc-001")
            self.assertEqual(te.get("correlation_id"), "step-conv-proc-001-1")

    def test_runtime_restart_anchor_persistence(self) -> None:
        """Persist active anchor, recreate storage instance from scratch, verify hook resolution."""
        self.api1.start_task(
            task_label="Restart Test",
            prompt="Test persistence across restart",
            conversation_id="conv-restart-01",
            anchor_id="task-restart-01",
        )

        # Fresh storage and fresh hook execution
        payload = {
            "conversation_id": "conv-restart-01",
            "step_index": 0,
            "workspace_paths": [str(self.workspace1)],
            "tool_call": {"name": "view_file", "args": {"AbsolutePath": str(self.workspace1 / "config.py")}},
        }
        process_hook_payload("pre", json.dumps(payload))
        process_hook_payload("post", json.dumps(payload))

        fresh_api = CortexAPI(workspace_root=self.workspace1)
        events = fresh_api.list_activity(anchor_id="task-restart-01")
        tool_events = [e for e in events if e.get("action_type") in ("tool_call", "tool_result")]
        self.assertEqual(len(tool_events), 2)
        for te in tool_events:
            self.assertEqual(te.get("anchor_id"), "task-restart-01")

    def test_multiple_concurrent_conversations_isolation(self) -> None:
        """Verify active tasks in different conversations do not cross-pollinate tool events."""
        self.api1.start_task(
            task_label="Task Alpha",
            conversation_id="conv-alpha",
            anchor_id="task-alpha-001",
        )
        self.api1.start_task(
            task_label="Task Beta",
            conversation_id="conv-beta",
            anchor_id="task-beta-002",
        )

        # Event for Conv Alpha
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-alpha",
            "stepIdx": 10,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "git diff"}},
        }))

        # Event for Conv Beta
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-beta",
            "stepIdx": 5,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/beta.py"}},
        }))

        # Event for Conv Gamma (no active task started)
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-gamma",
            "stepIdx": 1,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "grep_search", "args": {"Query": "find_something"}},
        }))

        events_alpha = self.api1.list_activity(conversation_id="conv-alpha")
        tool_alpha = [e for e in events_alpha if e.get("action_type") == "tool_call"]
        self.assertEqual(len(tool_alpha), 1)
        self.assertEqual(tool_alpha[0].get("anchor_id"), "task-alpha-001")

        events_beta = self.api1.list_activity(conversation_id="conv-beta")
        tool_beta = [e for e in events_beta if e.get("action_type") == "tool_call"]
        self.assertEqual(len(tool_beta), 1)
        self.assertEqual(tool_beta[0].get("anchor_id"), "task-beta-002")

        events_gamma = self.api1.list_activity(conversation_id="conv-gamma")
        tool_gamma = [e for e in events_gamma if e.get("action_type") == "tool_call"]
        self.assertEqual(len(tool_gamma), 1)
        self.assertIsNone(tool_gamma[0].get("anchor_id"), "Gamma should have anchor_id=None (strict isolation)")

    def test_multiple_sequential_tasks_in_one_conversation(self) -> None:
        """Verify sequential tasks in the same conversation attach only to the active task."""
        # 1. Start Task A
        self.api1.start_task(task_label="Phase 1", conversation_id="conv-seq", anchor_id="task-seq-A")
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-seq", "stepIdx": 1, "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "step1"}},
        }))

        # 2. End Task A
        self.api1.end_task(anchor_id="task-seq-A", status="completed")

        # 3. Intermediary action with no active task
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-seq", "stepIdx": 2, "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "view_file", "args": {"AbsolutePath": "docs/notes.md"}},
        }))

        # 4. Start Task B
        self.api1.start_task(task_label="Phase 2", conversation_id="conv-seq", anchor_id="task-seq-B")
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-seq", "stepIdx": 3, "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "step2"}},
        }))

        # 5. End Task B
        self.api1.end_task(anchor_id="task-seq-B", status="completed")

        # Verify assignments
        events = self.api1.list_activity(conversation_id="conv-seq")
        tool_events = [e for e in events if e.get("action_type") == "tool_call"]
        self.assertEqual(len(tool_events), 3)

        self.assertEqual(tool_events[0].get("target"), "step1")
        self.assertEqual(tool_events[0].get("anchor_id"), "task-seq-A")

        self.assertEqual(tool_events[1].get("target"), "docs/notes.md")
        self.assertIsNone(tool_events[1].get("anchor_id"), "Intermediary action must have anchor_id=None")

        self.assertEqual(tool_events[2].get("target"), "step2")
        self.assertEqual(tool_events[2].get("anchor_id"), "task-seq-B")

    def test_workspace_isolation_no_cross_association(self) -> None:
        """Verify two independent workspaces do not cross-associate active anchors."""
        self.api1.start_task(task_label="Workspace 1 Task", conversation_id="conv-ws", anchor_id="task-ws1-01")
        self.api2.start_task(task_label="Workspace 2 Task", conversation_id="conv-ws", anchor_id="task-ws2-02")

        # Event targeting workspace 1
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-ws",
            "stepIdx": 0,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest ws1"}},
        }))

        # Event targeting workspace 2
        process_hook_payload("pre", json.dumps({
            "conversationId": "conv-ws",
            "stepIdx": 0,
            "workspacePaths": [str(self.workspace2)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest ws2"}},
        }))

        events1 = self.api1.list_activity(anchor_id="task-ws1-01")
        tool1 = [e for e in events1 if e.get("action_type") == "tool_call"]
        self.assertEqual(len(tool1), 1)
        self.assertEqual(tool1[0].get("target"), "pytest ws1")

        events2 = self.api2.list_activity(anchor_id="task-ws2-02")
        tool2 = [e for e in events2 if e.get("action_type") == "tool_call"]
        self.assertEqual(len(tool2), 1)
        self.assertEqual(tool2[0].get("target"), "pytest ws2")

    def test_end_to_end_complete_trajectory(self) -> None:
        """Verify full trajectory: task_start -> tool_call -> tool_result -> tool_call -> tool_result -> task_end."""
        self.api1.start_task(
            task_label="End-to-End Trajectory Test",
            prompt="Build feature X",
            conversation_id="conv-e2e-001",
            anchor_id="task-e2e-001",
        )

        # Step 1
        payload1 = {
            "conversationId": "conv-e2e-001",
            "stepIdx": 1,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/feature.py"}},
        }
        process_hook_payload("pre", json.dumps(payload1))
        process_hook_payload("post", json.dumps(payload1))

        # Step 2
        payload2 = {
            "conversationId": "conv-e2e-001",
            "stepIdx": 2,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest tests/test_feature.py"}},
        }
        process_hook_payload("pre", json.dumps(payload2))
        process_hook_payload("post", json.dumps(payload2))

        # End task
        self.api1.end_task(anchor_id="task-e2e-001", status="completed")

        # Read back full activity trajectory for task-e2e-001
        events = self.api1.list_activity(anchor_id="task-e2e-001")
        self.assertEqual(len(events), 6)  # task_start, pre1, post1, pre2, post2, task_end

        types = [e.get("action_type") for e in events]
        self.assertEqual(types, ["task_start", "tool_call", "tool_result", "tool_call", "tool_result", "task_end"])

        for e in events:
            self.assertEqual(e.get("anchor_id"), "task-e2e-001", f"Event {e} must have anchor_id=task-e2e-001")
            self.assertEqual(e.get("task_id"), "task-e2e-001")

    def test_no_active_anchor_leaves_anchor_id_none(self) -> None:
        """Verify that when no task is active, activity events retain anchor_id=None without guessing."""
        payload = {
            "conversationId": "conv-idle",
            "stepIdx": 1,
            "workspacePaths": [str(self.workspace1)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "ls -la"}},
        }
        process_hook_payload("pre", json.dumps(payload))
        process_hook_payload("post", json.dumps(payload))

        events = self.api1.list_activity(conversation_id="conv-idle")
        self.assertEqual(len(events), 2)
        for e in events:
            self.assertIsNone(e.get("anchor_id"))
            self.assertIsNone(e.get("task_id"))
            self.assertEqual(e.get("source"), "antigravity_hook")


if __name__ == "__main__":
    unittest.main()
