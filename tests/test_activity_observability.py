"""Tests for CORTEX Agent Action Observability / Activity Log capability."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cortex_engine import (
    ActivityEvent,
    CortexAPI,
    CortexStorage,
    Knowledge,
)
from cortex_engine.cli import CortexCLI
from cortex_engine.mcp_server import CortexMCPServer
from cortex_engine.redaction import redact_data, redact_text


class TestActivityObservability(unittest.TestCase):
    """Test suite for activity logging, redaction, persistence, MCP, and CLI."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="cortex_activity_test_")
        self.workspace_path = Path(self.temp_dir)
        self.cortex_dir = self.workspace_path / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.api = CortexAPI(storage=self.storage)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Schema Validation & Dataclass Contract
    # -------------------------------------------------------------------------

    def test_activity_event_schema_and_serialization(self) -> None:
        """Verify ActivityEvent schema conforms to versioned canonical contract."""
        event = ActivityEvent(
            event_id="act-test-001",
            timestamp="2026-09-02T12:00:00Z",
            session_id="sess-abc",
            task_id="task-123",
            actor="agent",
            action_type="command_exec",
            source="api",
            target="git status",
            status="success",
            duration_ms=45.2,
            metadata={"exit_code": 0, "lines": 5},
            error_type=None,
            schema_version="1.0.0",
        )
        d = event.to_dict()
        self.assertEqual(d["event_id"], "act-test-001")
        self.assertEqual(d["action_type"], "command_exec")
        self.assertEqual(d["target"], "git status")
        self.assertEqual(d["schema_version"], "1.0.0")

        # Roundtrip deserialization
        restored = ActivityEvent.from_dict(d)
        self.assertEqual(restored.event_id, event.event_id)
        self.assertEqual(restored.timestamp, event.timestamp)
        self.assertEqual(restored.duration_ms, 45.2)
        self.assertEqual(restored.metadata, {"exit_code": 0, "lines": 5})

    # -------------------------------------------------------------------------
    # 2. Append-Only Persistence & Filesystem Source of Truth
    # -------------------------------------------------------------------------

    def test_append_only_persistence(self) -> None:
        """Verify activity events are appended to .cortex/events/activity.jsonl."""
        self.api.record_activity(
            action_type="tool_call",
            target="cortex_search",
            task_id="task-001",
            metadata={"query": "cache policy"},
        )
        self.api.record_activity(
            action_type="file_read",
            target="src/config.py",
            task_id="task-001",
            metadata={"bytes": 1024},
        )

        activity_file = self.cortex_dir / "events" / "activity.jsonl"
        self.assertTrue(activity_file.exists())

        lines = activity_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)

        data0 = json.loads(lines[0])
        data1 = json.loads(lines[1])
        self.assertEqual(data0["target"], "cortex_search")
        self.assertEqual(data1["target"], "src/config.py")

    # -------------------------------------------------------------------------
    # 3. Filtering & Query Capabilities
    # -------------------------------------------------------------------------

    def test_query_and_filtering(self) -> None:
        """Verify activity log querying by task, session, type, status, and slicing."""
        for i in range(10):
            task = "task-A" if i < 5 else "task-B"
            action = "command_exec" if i % 2 == 0 else "file_write"
            status = "success" if i != 3 else "error"
            self.api.record_activity(
                action_type=action,
                target=f"target-{i}",
                task_id=task,
                session_id="sess-1",
                status=status,
                metadata={"index": i},
            )

        # Filter by task
        task_a_events = self.api.list_activity(task_id="task-A")
        self.assertEqual(len(task_a_events), 5)

        # Filter by action_type
        cmd_events = self.api.list_activity(action_type="command_exec")
        self.assertEqual(len(cmd_events), 5)

        # Filter by status
        err_events = self.api.list_activity(status="error")
        self.assertEqual(len(err_events), 1)
        self.assertEqual(err_events[0]["target"], "target-3")

        # Offset and limit
        paged = self.api.list_activity(task_id="task-A", limit=2, offset=1)
        self.assertEqual(len(paged), 2)
        self.assertEqual(paged[0]["target"], "target-1")
        self.assertEqual(paged[1]["target"], "target-2")

        # Get by ID
        first_id = task_a_events[0]["event_id"]
        single = self.api.get_activity(first_id)
        self.assertIsNotNone(single)
        self.assertEqual(single["event_id"], first_id)

    # -------------------------------------------------------------------------
    # 4. Redaction & Secret Protection
    # -------------------------------------------------------------------------

    def test_redaction_layer(self) -> None:
        """Verify secrets (GitHub PAT, OpenAI key, AWS key, passwords) are scrubbed before persistence."""
        sensitive_payload = {
            "token": "ghp_1234567890abcdef1234567890abcdef1234",
            "openai_key": "sk-1234567890abcdef1234567890abcdef",
            "aws_key": "AKIA1234567890ABCDEF",
            "auth_header": "Bearer secret_jwt_payload_123456789",
            "password": "supersecretpassword",
            "nested": {
                "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
                "normal_field": "public_safe_data",
            },
        }

        recorded = self.api.record_activity(
            action_type="command_exec",
            target="curl -H 'Authorization: Bearer my_secret_token_12345' https://api.example.com",
            metadata=sensitive_payload,
        )

        activity_file = self.cortex_dir / "events" / "activity.jsonl"
        raw_log = activity_file.read_text(encoding="utf-8")

        # Assert no sensitive strings leaked into raw file
        self.assertNotIn("ghp_1234567890abcdef1234567890abcdef1234", raw_log)
        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", raw_log)
        self.assertNotIn("AKIA1234567890ABCDEF", raw_log)
        self.assertNotIn("supersecretpassword", raw_log)
        self.assertNotIn("secret_jwt_payload_123456789", raw_log)
        self.assertNotIn("my_secret_token_12345", raw_log)
        self.assertNotIn("BEGIN RSA PRIVATE KEY", raw_log)

        # Assert preserved safe data and redacted markers
        self.assertIn("[REDACTED]", raw_log)
        self.assertIn("public_safe_data", raw_log)

    # -------------------------------------------------------------------------
    # 5. Separation from Memory / Knowledge
    # -------------------------------------------------------------------------

    def test_separation_from_knowledge_and_search(self) -> None:
        """Verify activity logs are completely separate from Knowledge records and memory search."""
        # Record activity
        self.api.record_activity(
            action_type="command_exec",
            target="deploy to production server",
            metadata={"cluster": "prod-east"},
        )

        # Record genuine knowledge
        self.api.record_knowledge(
            id="DEC-PROD-001",
            knowledge_type="decision",
            title="Production Deployment Policy",
            content="Deploy only via staging pipeline verification.",
        )

        # Search should find the knowledge, but NOT the raw activity event
        search_res = self.api.search("production deployment")
        found_ids = [r["id"] for r in search_res.get("results", [])]
        self.assertIn("DEC-PROD-001", found_ids)
        for fid in found_ids:
            self.assertFalse(fid.startswith("act-"))

    # -------------------------------------------------------------------------
    # 6. Restart Persistence & Storage Recovery
    # -------------------------------------------------------------------------

    def test_restart_persistence(self) -> None:
        """Verify activity log survives process / storage restart."""
        self.api.record_activity(
            action_type="git_action",
            target="git commit -m 'feat: implement observability'",
            status="success",
            duration_ms=120.0,
            task_id="task-persist",
        )

        # Re-initialize storage and API from same directory
        new_storage = CortexStorage(cortex_dir=self.cortex_dir)
        new_api = CortexAPI(storage=new_storage)

        activities = new_api.list_activity(task_id="task-persist")
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["action_type"], "git_action")
        self.assertEqual(activities[0]["duration_ms"], 120.0)

    # -------------------------------------------------------------------------
    # 7. Malformed Input and Fault Isolation
    # -------------------------------------------------------------------------

    def test_corrupted_lines_resilience(self) -> None:
        """Verify corrupted JSON lines in activity.jsonl are skipped safely without crashing."""
        self.api.record_activity(action_type="tool_call", target="cortex_search")

        # Inject malformed line
        activity_file = self.cortex_dir / "events" / "activity.jsonl"
        with open(activity_file, "a", encoding="utf-8") as f:
            f.write("MALFORMED JSON LINE{{{ invalid\n")

        self.api.record_activity(action_type="tool_call", target="cortex_get")

        # Read activities should yield 2 valid events and skip corrupted line
        activities = self.api.list_activity()
        self.assertEqual(len(activities), 2)
        self.assertEqual(activities[0]["target"], "cortex_search")
        self.assertEqual(activities[1]["target"], "cortex_get")

    # -------------------------------------------------------------------------
    # 8. MCP Server Integration & Automatic Tool Invocations Tracking
    # -------------------------------------------------------------------------

    def test_mcp_activity_tools_and_automatic_logging(self) -> None:
        """Verify MCP server handles explicit activity tools and automatically logs all tool executions."""
        mcp = CortexMCPServer(api=self.api)

        # 1. Explicit tool call to cortex_record_activity
        rec_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cortex_record_activity",
                "arguments": {
                    "action_type": "command_exec",
                    "target": "pytest tests/",
                    "status": "success",
                    "duration_ms": 320.5,
                    "task_id": "task-mcp-1",
                    "metadata": {"tests_run": 10},
                },
            },
        }
        resp = mcp.handle_request(rec_req)
        self.assertFalse(resp.get("result", {}).get("isError", False))

        # 2. Call a regular MCP tool (cortex_search)
        search_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cortex_search",
                "arguments": {"query": "authentication"},
            },
        }
        mcp.handle_request(search_req)

        # 3. Query activity list via MCP tool cortex_list_activity
        list_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "cortex_list_activity",
                "arguments": {"limit": 10},
            },
        }
        list_resp = mcp.handle_request(list_req)
        content_text = list_resp["result"]["content"][0]["text"]
        list_data = json.loads(content_text)
        activities = list_data.get("activities", [])

        # Both the explicit command_exec and the automatic tool_call (cortex_search) must be recorded!
        targets = [a["target"] for a in activities]
        self.assertIn("pytest tests/", targets)
        self.assertIn("cortex_search", targets)

    # -------------------------------------------------------------------------
    # 9. CLI Activity Subcommand Inspection
    # -------------------------------------------------------------------------

    def test_cli_activity_inspection(self) -> None:
        """Verify CLI 'cortex activity' displays formatted events and outputs JSON."""
        self.api.record_activity(
            action_type="file_write",
            target="src/service.py",
            status="success",
            duration_ms=12.4,
            task_id="task-cli-001",
            metadata={"bytes": 450},
        )

        cli = CortexCLI(workspace_root=self.workspace_path)

        # Test CLI method
        acts = cli.cmd_activity(task_id="task-cli-001")
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["target"], "src/service.py")


if __name__ == "__main__":
    unittest.main()
