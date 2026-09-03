"""Tests for Cortex Interaction Trace Observability.

Validates:
1. Domain and class classification (cortex vs external_tool, agent_memory, task_boundary, maintenance)
2. Automatic capture across Python API and MCP Server
3. Single-trace de-duplication (no double counting between MCP and internal API)
4. Active TaskAnchor propagation and null anchor handling
5. Centralized redaction in queries and metadata
6. Metrics-friendly structured metadata across core operations
7. Legacy backward compatibility (safe None when fields missing)
8. Programmatic API (list_cortex_activity)
9. CLI filtering (--cortex, --agent-memory, --maintenance, --json)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine import (
    ActivityEvent,
    CortexAPI,
    CortexStorage,
    classify_cortex_interaction,
    extract_cortex_interaction_metadata,
)
from cortex_engine.cli import CortexCLI
from cortex_engine.mcp_server import CortexMCPServer
from cortex_engine.antigravity_hook import process_hook_payload


class TestCortexInteractionTrace(unittest.TestCase):
    """Regression test suite for Cortex Interaction Trace."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="cortex_trace_test_")
        self.workspace_path = Path(self.temp_dir).resolve()
        self.cortex_dir = self.workspace_path / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.api = CortexAPI(storage=self.storage, workspace_root=self.workspace_path)
        self.cli = CortexCLI(workspace_root=self.workspace_path)
        self.mcp = CortexMCPServer(api=self.api)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_domain_and_class_classification(self) -> None:
        """Verify deterministic classification of tools and actions into domain and interaction_class."""
        # Agent memory tools
        for tool in [
            "cortex_search", "mcp_cortex_search", "search",
            "cortex_get", "cortex_compile_context", "cortex_record_knowledge",
            "cortex_promote_memory", "cortex_check_claim_freshness",
            "cortex_check_duplicates", "cortex_archive_memory",
        ]:
            domain, i_class = classify_cortex_interaction(tool)
            self.assertEqual(domain, "cortex", f"Expected cortex domain for {tool}")
            self.assertEqual(i_class, "agent_memory", f"Expected agent_memory class for {tool}")

        # Task boundary operations
        for op in ["start_task", "end_task", "cortex_start_task", "cortex_end_task", "get_task", "list_tasks"]:
            domain, i_class = classify_cortex_interaction(op)
            self.assertEqual(domain, "cortex", f"Expected cortex domain for {op}")
            self.assertEqual(i_class, "task_boundary", f"Expected task_boundary class for {op}")

        # Explicit action types
        self.assertEqual(classify_cortex_interaction("any_target", action_type="task_start"), ("cortex", "task_boundary"))
        self.assertEqual(classify_cortex_interaction("any_target", action_type="task_end"), ("cortex", "task_boundary"))

        # Maintenance operations
        for op in ["cortex_doctor", "cortex_reindex", "cortex_status", "cortex_list_activity"]:
            domain, i_class = classify_cortex_interaction(op)
            self.assertEqual(domain, "cortex", f"Expected cortex domain for {op}")
            self.assertEqual(i_class, "maintenance", f"Expected maintenance class for {op}")

        # External tools
        for ext in ["view_file", "write_to_file", "run_command", "grep_search", "browser_subagent"]:
            domain, i_class = classify_cortex_interaction(ext)
            self.assertEqual(domain, "external_tool", f"Expected external_tool for {ext}")
            self.assertIsNone(i_class, f"Expected None interaction_class for {ext}")

    def test_automatic_capture_via_python_api(self) -> None:
        """Verify calling core Python API methods automatically records ActivityEvents with domain and class."""
        # 1. Record knowledge
        self.api.record_knowledge(
            id="DEC-001",
            knowledge_type="decision",
            title="Use SQLite WAL mode",
            content="Enabled WAL mode for concurrent reads.",
        )

        # 2. Search
        search_res = self.api.search(query="SQLite WAL")
        self.assertGreaterEqual(search_res["count"], 1)

        # 3. Get
        get_res = self.api.get("DEC-001")
        self.assertIsNotNone(get_res)

        # 4. Compile context
        compile_res = self.api.compile_context(task="Setup database configuration", memory_ids=["DEC-001"])
        self.assertIsNotNone(compile_res)

        # Inspect canonical activity log
        cortex_events = self.api.list_cortex_activity()
        self.assertGreaterEqual(len(cortex_events), 4)

        for event in cortex_events:
            self.assertEqual(event["activity_domain"], "cortex")
            self.assertEqual(event["interaction_class"], "agent_memory")

        tools = [e["tool_name"] for e in cortex_events]
        self.assertIn("cortex_record_knowledge", tools)
        self.assertIn("cortex_search", tools)
        self.assertIn("cortex_get", tools)
        self.assertIn("cortex_compile_context", tools)

    def test_no_double_counting_between_mcp_and_api(self) -> None:
        """Verify executing CORTEX operations via MCP creates exactly ONE activity event per operation."""
        # First seed knowledge
        self.api.record_knowledge(
            id="CON-001",
            knowledge_type="constraint",
            title="Max file size",
            content="Max file size is 10MB.",
        )

        initial_count = len(self.api.list_activity())

        # Call cortex_search via MCP
        mcp_msg = {
            "jsonrpc": "2.0",
            "id": "req-mcp-01",
            "method": "tools/call",
            "params": {
                "name": "cortex_search",
                "arguments": {"query": "Max file size"},
            },
        }
        res = self.mcp.handle_request(mcp_msg)
        self.assertFalse(res.get("result", {}).get("isError", True))

        # Check total activities recorded: exactly ONE new event!
        all_activities = self.api.list_activity()
        self.assertEqual(len(all_activities), initial_count + 1)

        search_event = all_activities[-1]
        self.assertEqual(search_event["tool_name"], "cortex_search")
        self.assertEqual(search_event["source"], "mcp")
        self.assertEqual(search_event["activity_domain"], "cortex")
        self.assertEqual(search_event["interaction_class"], "agent_memory")
        self.assertEqual(search_event["status"], "success")

    def test_task_anchor_and_conversation_propagation(self) -> None:
        """Verify CORTEX interaction events carry active anchor_id, and null when no task is active."""
        conv_id = "conv-trace-999"

        # 1. Action without active anchor -> anchor_id must be None
        self.api.search(query="initial discovery")
        acts = self.api.list_cortex_activity(limit=1)
        self.assertIsNone(acts[0].get("anchor_id"), "Expected None anchor_id when no task active")

        # 2. Start task anchor
        task = self.api.start_task(
            task_label="Refactor Auth Subsystem",
            conversation_id=conv_id,
        )
        aid = task["anchor_id"]

        # 3. Execute CORTEX memory action in same conversation context
        # (simulate active task anchor lookup for conversation)
        self.api.record_activity(
            action_type="tool_call",
            target="cortex_search(OAuth tokens)",
            tool_name="cortex_search",
            conversation_id=conv_id,
            status="success",
        )

        # 4. End task anchor
        self.api.end_task(anchor_id=aid)

        # Inspect activities for this task
        task_acts = self.api.list_cortex_activity(anchor_id=aid)
        self.assertEqual(len(task_acts), 3)  # task_start, cortex_search, task_end

        self.assertEqual(task_acts[0]["action_type"], "task_start")
        self.assertEqual(task_acts[0]["interaction_class"], "task_boundary")
        self.assertEqual(task_acts[0]["anchor_id"], aid)

        self.assertEqual(task_acts[1]["tool_name"], "cortex_search")
        self.assertEqual(task_acts[1]["interaction_class"], "agent_memory")
        self.assertEqual(task_acts[1]["anchor_id"], aid)

        self.assertEqual(task_acts[2]["action_type"], "task_end")
        self.assertEqual(task_acts[2]["interaction_class"], "task_boundary")
        self.assertEqual(task_acts[2]["anchor_id"], aid)

    def test_centralized_redaction_in_trace_queries(self) -> None:
        """Verify queries and metadata with API keys/tokens are redacted before trace persistence."""
        secret_key = "sk-live-51M1234567890abcdefghijklmnopqrstuv"
        query_with_secret = f"fix payment webhook with token {secret_key}"

        self.api.search(query=query_with_secret)

        latest = self.api.list_cortex_activity(limit=1)[0]
        meta = latest.get("metadata", {})

        # Query in metadata must be redacted
        self.assertIn("[REDACTED]", meta.get("query", ""))
        self.assertNotIn(secret_key, meta.get("query", ""))

        # Raw file check
        act_file = self.cortex_dir / "events" / "activity.jsonl"
        content = act_file.read_text(encoding="utf-8")
        self.assertNotIn(secret_key, content)

    def test_metrics_friendly_metadata_across_operations(self) -> None:
        """Verify structured metrics metadata are recorded accurately for Agent Memory operations."""
        # 1. record_knowledge
        self.api.record_knowledge(
            id="LES-005",
            knowledge_type="lesson",
            title="Batch database writes",
            content="Group SQLite transactions into 50-item batches.",
        )
        rec_act = self.api.list_cortex_activity(limit=1)[0]
        self.assertEqual(rec_act["metadata"].get("record_id"), "LES-005")
        self.assertEqual(rec_act["metadata"].get("knowledge_type"), "lesson")

        # 2. search
        self.api.search(query="Batch database writes", limit=5)
        search_act = self.api.list_cortex_activity(limit=1)[0]
        self.assertEqual(search_act["metadata"].get("query"), "Batch database writes")
        self.assertGreaterEqual(search_act["metadata"].get("candidate_count", 0), 1)
        self.assertIn("policy", search_act["metadata"])

        # 3. get
        self.api.get("LES-005")
        get_act = self.api.list_cortex_activity(limit=1)[0]
        self.assertEqual(get_act["metadata"].get("record_id"), "LES-005")
        self.assertTrue(get_act["metadata"].get("found"))

        # 4. compile_context
        self.api.compile_context(task="Database batching task", memory_ids=["LES-005"])
        compile_act = self.api.list_cortex_activity(limit=1)[0]
        self.assertEqual(compile_act["metadata"].get("task"), "Database batching task")
        self.assertEqual(compile_act["metadata"].get("selected_count"), 1)
        self.assertGreater(compile_act["metadata"].get("char_count", 0), 0)

    def test_legacy_backward_compatibility(self) -> None:
        """Verify legacy activity records without activity_domain or interaction_class load safely."""
        act_file = self.cortex_dir / "events" / "activity.jsonl"
        act_file.parent.mkdir(parents=True, exist_ok=True)

        legacy_event_json = {
            "event_id": "act-legacy-01",
            "timestamp": "2026-09-01T12:00:00Z",
            "action_type": "tool_call",
            "source": "antigravity_hook",
            "target": "cortex_search",
            "status": "success",
            "metadata": {"args_keys": ["query"]},
        }
        with open(act_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(legacy_event_json) + "\n")

        # Read back via storage and API
        loaded = self.api.list_activity(limit=10)
        legacy_obj = [a for a in loaded if a["event_id"] == "act-legacy-01"][0]

        self.assertIsNone(legacy_obj.get("activity_domain"))
        self.assertIsNone(legacy_obj.get("interaction_class"))
        self.assertEqual(legacy_obj["target"], "cortex_search")

        # Serializing to dict should work seamlessly
        event_model = ActivityEvent.from_dict(legacy_obj)
        self.assertIsNone(event_model.activity_domain)
        self.assertIsNone(event_model.interaction_class)

    def test_cli_filtering_and_trace_view(self) -> None:
        """Verify CLI supports --cortex, --agent-memory, --maintenance, and --json."""
        # Seed external tool event via hook simulation
        hook_payload = {
            "toolCall": {"name": "view_file", "args": {"AbsolutePath": "/src/main.py"}},
            "stepIdx": 1,
            "conversationId": "conv-cli-test",
            "workspacePaths": [str(self.workspace_path)],
        }
        process_hook_payload("pre", json.dumps(hook_payload))

        # Seed CORTEX memory event
        self.api.search(query="caching policy")

        # 1. Default activity: includes both external tool and cortex
        all_acts = self.cli.cmd_activity()
        self.assertGreaterEqual(len(all_acts), 2)
        tool_names = [a.get("tool_name") for a in all_acts]
        self.assertIn("view_file", tool_names)
        self.assertIn("cortex_search", tool_names)

        # 2. Filter --cortex: external tool MUST be excluded
        cortex_acts = self.cli.cmd_activity(activity_domain="cortex")
        for a in cortex_acts:
            self.assertEqual(a.get("activity_domain"), "cortex")
            self.assertNotEqual(a.get("tool_name"), "view_file")

        # 3. Filter --agent-memory: only agent memory
        memory_acts = self.cli.cmd_activity(activity_domain="cortex", interaction_class="agent_memory")
        for a in memory_acts:
            self.assertEqual(a.get("interaction_class"), "agent_memory")

        # 4. Filter --maintenance: none found yet
        maint_acts = self.cli.cmd_activity(activity_domain="cortex", interaction_class="maintenance")
        self.assertEqual(len(maint_acts), 0)

        # Seed a maintenance event (status/doctor)
        self.api.record_activity(
            action_type="tool_call",
            target="cortex_doctor",
            tool_name="cortex_doctor",
            status="success",
        )
        maint_acts_after = self.cli.cmd_activity(activity_domain="cortex", interaction_class="maintenance")
        self.assertEqual(len(maint_acts_after), 1)
        self.assertEqual(maint_acts_after[0]["tool_name"], "cortex_doctor")


if __name__ == "__main__":
    unittest.main()
