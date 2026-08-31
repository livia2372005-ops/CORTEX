"""Comprehensive unit and integration tests for CORTEX MCP Server and Antigravity Tool Integration."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.indexer import CortexIndexer
from cortex_engine.mcp_server import CortexMCPServer, TOOL_SCHEMAS
from cortex_engine.models import Knowledge
from cortex_engine.storage import CortexStorage


class TestMCPIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CortexStorage(cortex_dir=self.temp_dir)
        self.indexer = CortexIndexer(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer)
        self.mcp = CortexMCPServer(api=self.api)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mcp_initialize_and_lifecycle(self):
        """Test standard MCP initialize handshake and ping."""
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        init_res = self.mcp.handle_request(init_req)
        self.assertEqual(init_res["id"], 1)
        self.assertEqual(init_res["result"]["serverInfo"]["name"], "cortex-mcp")
        self.assertIn("tools", init_res["result"]["capabilities"])

        # Initialized notification
        notif_req = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        notif_res = self.mcp.handle_request(notif_req)
        self.assertIsNone(notif_res)

        # Ping
        ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
        ping_res = self.mcp.handle_request(ping_req)
        self.assertEqual(ping_res["id"], 2)
        self.assertEqual(ping_res["result"], {})

    def test_mcp_tools_list_schema(self):
        """Test tools/list returns valid tool declarations."""
        req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
        res = self.mcp.handle_request(req)
        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        self.assertIn("cortex_search", tool_names)
        self.assertIn("cortex_get", tool_names)
        self.assertIn("cortex_record_event", tool_names)
        self.assertIn("cortex_record_knowledge", tool_names)

        # Validate inputSchema structure for cortex_search
        search_tool = next(t for t in tools if t["name"] == "cortex_search")
        self.assertIn("query", search_tool["inputSchema"]["properties"])
        self.assertIn("query", search_tool["inputSchema"]["required"])

    def test_mcp_cortex_record_and_search(self):
        """Test recording knowledge and searching through MCP tools/call."""
        # 1. Record knowledge via MCP
        rec_req = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "cortex_record_knowledge",
                "arguments": {
                    "id": "DEC-MCP-01",
                    "knowledge_type": "decision",
                    "title": "Use MCP stdio for Antigravity Tools",
                    "content": "MCP provides two-way native tool execution over JSON-RPC 2.0 stdio transport.",
                    "status": "active",
                    "provenance": {"author": "Agent"},
                },
            },
        }
        rec_res = self.mcp.handle_request(rec_req)
        self.assertFalse(rec_res["result"]["isError"])
        rec_data = json.loads(rec_res["result"]["content"][0]["text"])
        self.assertEqual(rec_data["persisted_id"], "DEC-MCP-01")

        # 2. Search knowledge via MCP
        search_req = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "cortex_search",
                "arguments": {
                    "query": "stdio transport",
                },
            },
        }
        search_res = self.mcp.handle_request(search_req)
        search_data = json.loads(search_res["result"]["content"][0]["text"])
        self.assertEqual(search_data["count"], 1)
        self.assertEqual(search_data["results"][0]["id"], "DEC-MCP-01")
        self.assertEqual(search_data["results"][0]["type"], "decision")

    def test_mcp_cortex_get_canonical_read(self):
        """Test cortex_get retrieves authoritative canonical record directly from disk."""
        # Write canonical file directly to disk
        self.storage.write_knowledge(
            Knowledge(
                id="CON-AUTH-01",
                type="constraint",
                title="Authoritative Source Invariant",
                content="Filesystem records are canonical truth, not SQLite FTS snapshots.",
            )
        )

        get_req = {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "cortex_get",
                "arguments": {"id": "CON-AUTH-01"},
            },
        }
        get_res = self.mcp.handle_request(get_req)
        get_data = json.loads(get_res["result"]["content"][0]["text"])
        self.assertEqual(get_data["id"], "CON-AUTH-01")
        self.assertEqual(get_data["type"], "constraint")

    def test_mcp_cortex_record_event(self):
        """Test recording lifecycle events through MCP."""
        evt_req = {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "cortex_record_event",
                "arguments": {
                    "event_type": "tool_execution",
                    "role": "APP",
                    "payload": {"command": "npm test", "exit_code": 0},
                    "task_id": "T-TEST-99",
                },
            },
        }
        evt_res = self.mcp.handle_request(evt_req)
        evt_data = json.loads(evt_res["result"]["content"][0]["text"])
        self.assertEqual(evt_data["status"], "persisted")

        # Verify event persisted in JSONL
        events = self.storage.read_events(task_id="T-TEST-99")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["command"], "npm test")

    def test_mcp_failure_handling_and_no_hallucination(self):
        """Test error conditions: missing records, invalid queries, malformed input."""
        # 1. Missing record -> returns found: False, does not fabricate
        get_missing = {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {"name": "cortex_get", "arguments": {"id": "NONEXISTENT-999"}},
        }
        res_missing = self.mcp.handle_request(get_missing)
        data_missing = json.loads(res_missing["result"]["content"][0]["text"])
        self.assertFalse(data_missing["found"])
        self.assertEqual(data_missing["id"], "NONEXISTENT-999")

        # 2. Missing required parameters -> JSON-RPC error -32602
        bad_call = {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "cortex_search", "arguments": {}},
        }
        res_bad = self.mcp.handle_request(bad_call)
        self.assertIn("error", res_bad)
        self.assertEqual(res_bad["error"]["code"], -32602)

        # 3. Unknown method -> JSON-RPC error -32601
        bad_method = {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "unknown_rpc_method",
        }
        res_method = self.mcp.handle_request(bad_method)
        self.assertIn("error", res_method)
        self.assertEqual(res_method["error"]["code"], -32601)

        # 4. Unknown tool name -> JSON-RPC error -32602
        bad_tool = {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        res_tool = self.mcp.handle_request(bad_tool)
        self.assertIn("error", res_tool)
        self.assertEqual(res_tool["error"]["code"], -32602)

    def test_real_antigravity_task_simulation(self):
        """Simulate real Antigravity Agent interaction:
        1. Seed historical knowledge (DEC-001, FAIL-001, CON-001).
        2. Agent queries cortex_search for 'payment fee calculation'.
        3. Agent receives structured evidence (220 tokens projection).
        4. Agent verifies canonical record via cortex_get.
        5. Agent decides implementation cleanly.
        """
        # 1. Seed knowledge
        self.api.record_knowledge(
            id="DEC-001",
            knowledge_type="decision",
            title="Business Logic in Service Layer",
            content="Fee calculations and business validation belong exclusively in Service classes.",
        )
        self.api.record_knowledge(
            id="FAIL-001",
            knowledge_type="failure",
            title="Fee Logic in PaymentRepository Regression",
            content="Putting fee calculation logic in PaymentRepository caused database migration and test mock failures.",
        )
        self.api.record_knowledge(
            id="CON-001",
            knowledge_type="constraint",
            title="Repository Boundary Invariant",
            content="Repositories must remain pure data-access layers without business calculations.",
        )

        # 2. Agent searches for payment fee guidance
        search_req = {
            "jsonrpc": "2.0",
            "id": 30,
            "method": "tools/call",
            "params": {
                "name": "cortex_search",
                "arguments": {"query": "fee logic Service"},
            },
        }
        search_res = self.mcp.handle_request(search_req)
        search_data = json.loads(search_res["result"]["content"][0]["text"])

        self.assertGreaterEqual(search_data["count"], 1)
        found_ids = [r["id"] for r in search_data["results"]]
        self.assertIn("DEC-001", found_ids)

        # 3. Agent retrieves full canonical record for DEC-001
        get_req = {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "cortex_get",
                "arguments": {"id": "DEC-001"},
            },
        }
        get_res = self.mcp.handle_request(get_req)
        get_data = json.loads(get_res["result"]["content"][0]["text"])
        self.assertEqual(get_data["title"], "Business Logic in Service Layer")


if __name__ == "__main__":
    unittest.main()
