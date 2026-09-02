"""Unit tests for CORTEX Task Boundary / Activity Anchors."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.antigravity_hook import process_hook_payload
from cortex_engine.api import CortexAPI
from cortex_engine.cli import CortexCLI
from cortex_engine.mcp_server import CortexMCPServer
from cortex_engine.models import ActivityEvent, TaskAnchor
from cortex_engine.redaction import compute_prompt_hash, normalize_prompt
from cortex_engine.storage import CortexStorage


class TestTaskAnchors(unittest.TestCase):
    """Verify task boundary anchors, prompt hashing, correlation, and activity propagation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.cortex_dir = Path(self.temp_dir) / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.api = CortexAPI(storage=self.storage)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_prompt_normalization_and_deterministic_hashing(self) -> None:
        """Verify prompt normalization and SHA-256 fingerprinting."""
        p1 = "  Refactor auth middleware to prevent token leaks.  \n"
        p2 = "refactor  auth middleware   to prevent token leaks."
        p3 = "Different prompt content entirely."

        self.assertEqual(normalize_prompt(p1), "refactor auth middleware to prevent token leaks.")
        self.assertEqual(normalize_prompt(p2), "refactor auth middleware to prevent token leaks.")
        
        h1 = compute_prompt_hash(p1)
        h2 = compute_prompt_hash(p2)
        h3 = compute_prompt_hash(p3)

        self.assertIsNotNone(h1)
        self.assertEqual(h1, h2, "Normalized identical prompts must yield identical prompt hashes")
        self.assertNotEqual(h1, h3, "Different prompts must yield different hashes")
        self.assertIsNone(compute_prompt_hash(None))
        self.assertIsNone(compute_prompt_hash("   "))

    def test_task_start_and_end_lifecycle(self) -> None:
        """Verify task start, persistence, activity event recording, and task end."""
        prompt = "Add database connection pool retry logic"
        task = self.api.start_task(
            task_label="DB Pool Retry",
            prompt=prompt,
            conversation_id="conv-1234",
            metadata={"priority": "high", "secret_key": "ghp_123456789012345678901234567890"},
        )

        anchor_id = task["anchor_id"]
        self.assertTrue(anchor_id.startswith("task-"))
        self.assertEqual(task["status"], "active")
        self.assertEqual(task["task_label"], "DB Pool Retry")
        self.assertEqual(task["conversation_id"], "conv-1234")
        self.assertEqual(task["prompt_hash"], compute_prompt_hash(prompt))
        self.assertEqual(task["metadata"]["secret_key"], "[REDACTED]")
        # Raw prompt must NEVER be stored
        self.assertNotIn("prompt", task)

        # Verify activity stream recorded task_start event
        acts = self.api.list_activity(anchor_id=anchor_id)
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["action_type"], "task_start")
        self.assertEqual(acts[0]["anchor_id"], anchor_id)
        self.assertEqual(acts[0]["status"], "started")

        # End the task
        ended = self.api.end_task(anchor_id=anchor_id, status="completed", metadata={"summary": "retry added"})
        self.assertIsNotNone(ended)
        self.assertEqual(ended["status"], "completed")
        self.assertIsNotNone(ended["ended_at"])

        # Verify activity stream recorded task_end event
        acts_after = self.api.list_activity(anchor_id=anchor_id)
        self.assertEqual(len(acts_after), 2)
        self.assertEqual(acts_after[1]["action_type"], "task_end")
        self.assertEqual(acts_after[1]["status"], "completed")

    def test_active_anchor_resolution_and_hook_propagation(self) -> None:
        """Verify Antigravity hook automatically resolves active task anchor for the conversation."""
        task = self.api.start_task(
            task_label="Observability Hook Task",
            conversation_id="conv-hook-test",
            anchor_id="task-custom-anchor-01",
        )
        self.assertEqual(task["anchor_id"], "task-custom-anchor-01")

        # Simulate Antigravity PreToolUse hook payload
        pre_payload = json.dumps({
            "conversationId": "conv-hook-test",
            "stepIdx": 1,
            "workspacePaths": [self.temp_dir],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/ -v"},
            },
        })
        resp_pre = process_hook_payload("pre", pre_payload)
        self.assertEqual(resp_pre, {"decision": "allow"})

        # Simulate PostToolUse hook payload
        post_payload = json.dumps({
            "conversationId": "conv-hook-test",
            "stepIdx": 1,
            "workspacePaths": [self.temp_dir],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/ -v"},
            },
            "error": None,
        })
        resp_post = process_hook_payload("post", post_payload)
        self.assertEqual(resp_post, {})

        # Verify all recorded tool events are anchored to task-custom-anchor-01
        events = self.api.list_activity(anchor_id="task-custom-anchor-01")
        # 1 task_start + 1 pre-tool + 1 post-tool = 3
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["action_type"], "task_start")
        self.assertEqual(events[1]["action_type"], "tool_call")
        self.assertEqual(events[1]["anchor_id"], "task-custom-anchor-01")
        self.assertEqual(events[2]["action_type"], "tool_result")
        self.assertEqual(events[2]["anchor_id"], "task-custom-anchor-01")

    def test_multiple_tasks_in_one_conversation(self) -> None:
        """Verify sequential tasks within the same conversation have distinct boundaries."""
        t1 = self.api.start_task(task_label="Task 1", conversation_id="conv-multi", anchor_id="task-01")
        self.api.record_activity(action_type="file_read", target="src/a.py", conversation_id="conv-multi")
        self.api.end_task(anchor_id="task-01", status="completed")

        t2 = self.api.start_task(task_label="Task 2", conversation_id="conv-multi", anchor_id="task-02")
        self.api.record_activity(action_type="file_write", target="src/b.py", conversation_id="conv-multi")
        self.api.end_task(anchor_id="task-02", status="completed")

        acts_t1 = self.api.list_activity(anchor_id="task-01")
        acts_t2 = self.api.list_activity(anchor_id="task-02")

        # t1 should contain task_start, file_read, task_end
        self.assertEqual(len(acts_t1), 3)
        self.assertTrue(all(a["anchor_id"] == "task-01" for a in acts_t1))

        # t2 should contain task_start, file_write, task_end
        self.assertEqual(len(acts_t2), 3)
        self.assertTrue(all(a["anchor_id"] == "task-02" for a in acts_t2))

    def test_restart_persistence(self) -> None:
        """Verify task anchors and activity events survive process/storage reload."""
        self.api.start_task(task_label="Persistent Task", anchor_id="task-restart-01", prompt="Prompt test")
        self.api.record_activity(action_type="tool_call", target="cortex_search", anchor_id="task-restart-01")

        # Reload storage
        new_storage = CortexStorage(cortex_dir=self.cortex_dir)
        new_api = CortexAPI(storage=new_storage)

        anc = new_api.get_task("task-restart-01")
        self.assertIsNotNone(anc)
        self.assertEqual(anc["task_label"], "Persistent Task")
        self.assertEqual(anc["status"], "active")

        acts = new_api.list_activity(anchor_id="task-restart-01")
        self.assertEqual(len(acts), 2)

    def test_backward_compatibility_with_missing_anchor_id(self) -> None:
        """Verify legacy activity records without anchor_id load safely with anchor_id=None."""
        legacy_line = json.dumps({
            "event_id": "act-legacy-001",
            "timestamp": "2026-09-01T10:00:00Z",
            "actor": "agent",
            "action_type": "tool_call",
            "source": "mcp",
            "target": "cortex_search",
            "status": "success",
            "schema_version": "1.0.0"
        })
        with open(self.storage.activity_file, "a", encoding="utf-8") as f:
            f.write(legacy_line + "\n")

        acts = self.api.list_activity()
        legacy_act = [a for a in acts if a["event_id"] == "act-legacy-001"][0]
        self.assertIsNone(legacy_act.get("anchor_id"))
        self.assertEqual(legacy_act["action_type"], "tool_call")

    def test_cli_task_and_activity_commands(self) -> None:
        """Verify CLI task commands (start, end, list, get) and activity filtering by task."""
        cli = CortexCLI(workspace_root=Path(self.temp_dir))
        
        # 1. Start task
        t = cli.cmd_task_start(label="CLI Task", prompt="CLI prompt", anchor_id="task-cli-01")
        self.assertEqual(t["anchor_id"], "task-cli-01")
        self.assertEqual(t["task_label"], "CLI Task")

        # 2. Get task
        t_get = cli.cmd_task_get("task-cli-01")
        self.assertEqual(t_get["anchor_id"], "task-cli-01")

        # 3. List tasks
        t_list = cli.cmd_task_list()
        self.assertEqual(len(t_list), 1)
        self.assertEqual(t_list[0]["anchor_id"], "task-cli-01")

        # 4. Filter activity by task
        acts = cli.cmd_activity(task_id="task-cli-01")
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["action_type"], "task_start")

        # 5. End task
        t_end = cli.cmd_task_end("task-cli-01", status="completed")
        self.assertEqual(t_end["status"], "completed")

    def test_mcp_task_tools(self) -> None:
        """Verify MCP server handles cortex_start_task, cortex_end_task, cortex_get_task, cortex_list_tasks."""
        server = CortexMCPServer(api=self.api)

        def parse_mcp_result(resp):
            self.assertIn("result", resp)
            self.assertFalse(resp["result"].get("isError", False))
            text_content = resp["result"]["content"][0]["text"]
            return json.loads(text_content)

        # 1. Start task via MCP
        req_start = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cortex_start_task",
                "arguments": {
                    "task_label": "MCP Task",
                    "anchor_id": "task-mcp-01",
                },
            },
        }
        resp_start = parse_mcp_result(server.handle_request(req_start))
        self.assertIn("task", resp_start)
        self.assertEqual(resp_start["task"]["anchor_id"], "task-mcp-01")

        # 2. Get task via MCP
        req_get = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cortex_get_task",
                "arguments": {"anchor_id": "task-mcp-01"},
            },
        }
        resp_get = parse_mcp_result(server.handle_request(req_get))
        self.assertTrue(resp_get["found"])

        # 3. List tasks via MCP
        req_list = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "cortex_list_tasks",
                "arguments": {},
            },
        }
        resp_list = parse_mcp_result(server.handle_request(req_list))
        self.assertEqual(resp_list["count"], 1)

        # 4. End task via MCP
        req_end = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "cortex_end_task",
                "arguments": {"anchor_id": "task-mcp-01", "status": "completed"},
            },
        }
        resp_end = parse_mcp_result(server.handle_request(req_end))
        self.assertEqual(resp_end["task"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
