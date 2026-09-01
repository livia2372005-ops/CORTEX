"""CORTEX MCP Server for Antigravity Tool Integration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api import CortexAPI
from .storage import CortexStorage


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "cortex_search",
        "description": "Search CORTEX persistent knowledge base for historical decisions, constraints, failures, and lessons. Returns structured evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query keywords (e.g., 'payment validation', 'cache invalidation').",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter: 'decisions', 'constraints', 'failures', 'lessons', 'claims'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of evidence records to return (default: 10).",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "cortex_get",
        "description": "Retrieve an authoritative canonical knowledge record by its unique ID (e.g., 'DEC-001', 'FAIL-001').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Unique identifier of the knowledge record.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category where the record resides.",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "cortex_record_event",
        "description": "Append an observable lifecycle event to CORTEX event log. Never persists private thoughts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "Observable event type (e.g. 'role_transition', 'tool_execution', 'task_completed').",
                },
                "role": {
                    "type": "string",
                    "description": "Active agent role: 'APP', 'MEMORY', 'REVIEW', 'LEARNING'.",
                },
                "payload": {
                    "type": "object",
                    "description": "Structured event payload.",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional active task ID.",
                },
                "provenance": {
                    "type": "object",
                    "description": "Optional provenance metadata.",
                },
            },
            "required": ["event_type", "role", "payload"],
        },
    },
    {
        "name": "cortex_record_knowledge",
        "description": "Persist a durable knowledge item (decision, constraint, failure, lesson) to canonical storage and index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Unique identifier (e.g. 'DEC-002', 'CON-003', 'FAIL-002').",
                },
                "knowledge_type": {
                    "type": "string",
                    "description": "Type of knowledge: 'decision', 'constraint', 'failure', 'lesson', 'claim'.",
                },
                "title": {
                    "type": "string",
                    "description": "Concise descriptive title.",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown or structured text content.",
                },
                "status": {
                    "type": "string",
                    "description": "Status (default: 'active').",
                    "default": "active",
                },
                "provenance": {
                    "type": "object",
                    "description": "Optional author, commit, or incident provenance.",
                },
                "related": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of related knowledge IDs.",
                },
                "affects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of affected files or modules.",
                },
            },
            "required": ["id", "knowledge_type", "title", "content"],
        },
    },
    {
        "name": "cortex_check_claim_freshness",
        "description": "Evaluate empirical claim freshness by verifying supporting artifact content hashes against current workspace files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Claim ID to verify (e.g., 'CLAIM-001').",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "cortex_compile_context",
        "description": "Compile selected CORTEX memory IDs into a structured, bounded context for the active engineering task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Active task description.",
                },
                "memory_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit list of knowledge/claim IDs chosen by the Agent (e.g., ['CON-001', 'DEC-007']).",
                },
                "budget_tokens": {
                    "type": "integer",
                    "description": "Optional token budget for injected memory (default: 500).",
                    "default": 500,
                },
                "role": {
                    "type": "string",
                    "description": "Active role mode (default: 'APP').",
                    "default": "APP",
                },
            },
            "required": ["task", "memory_ids"],
        },
    },
]


class CortexMCPServer:
    """Local JSON-RPC 2.0 / MCP Server exposing CORTEX tools."""

    def __init__(self, api: Optional[CortexAPI] = None):
        self.api = api or CortexAPI()

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC / MCP request dictionary."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: method missing"},
            }

        # Lifecycle methods
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "cortex-mcp",
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {},
                    },
                },
            }

        if method == "notifications/initialized":
            return None  # Notifications do not return a response

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # Tools catalog
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOL_SCHEMAS,
                },
            }

        # Tool execution
        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            try:
                result_data = self._execute_tool(tool_name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2, ensure_ascii=False),
                            }
                        ],
                        "isError": False,
                    },
                }
            except ValueError as ve:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": str(ve)},
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": f"Internal tool error: {str(e)}"},
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Route tool invocation to CORTEX API."""
        if name == "cortex_search":
            query = args.get("query")
            if not query:
                raise ValueError("Parameter 'query' is required for cortex_search.")
            category = args.get("category")
            limit = int(args.get("limit", 10))
            return self.api.search(query=query, category=category, limit=limit, role="MEMORY")

        elif name == "cortex_get":
            item_id = args.get("id")
            if not item_id:
                raise ValueError("Parameter 'id' is required for cortex_get.")
            category = args.get("category")
            item = self.api.get(id=item_id, category=category, role="MEMORY")
            if item is None:
                return {"found": False, "id": item_id, "message": "Record not found"}
            return item

        elif name == "cortex_record_event":
            event_type = args.get("event_type")
            role = args.get("role")
            payload = args.get("payload")
            if not event_type or not role or payload is None:
                raise ValueError("Parameters 'event_type', 'role', and 'payload' are required for cortex_record_event.")
            task_id = args.get("task_id")
            provenance = args.get("provenance")
            persisted_id = self.api.record_event(
                event_type=event_type,
                role=role,
                payload=payload,
                task_id=task_id,
                provenance=provenance,
            )
            return {"recorded_id": persisted_id, "status": "persisted"}

        elif name == "cortex_record_knowledge":
            item_id = args.get("id")
            k_type = args.get("knowledge_type")
            title = args.get("title")
            content = args.get("content")
            if not item_id or not k_type or not title or not content:
                raise ValueError("Parameters 'id', 'knowledge_type', 'title', and 'content' are required for cortex_record_knowledge.")
            status = args.get("status", "active")
            provenance = args.get("provenance")
            related = args.get("related")
            affects = args.get("affects")
            persisted_id = self.api.record_knowledge(
                id=item_id,
                knowledge_type=k_type,
                title=title,
                content=content,
                status=status,
                provenance=provenance,
                related=related,
                affects=affects,
            )
            return {"persisted_id": persisted_id, "status": "persisted"}

        elif name == "cortex_check_claim_freshness":
            claim_id = args.get("id")
            if not claim_id:
                raise ValueError("Parameter 'id' is required for cortex_check_claim_freshness.")
            report = self.api.check_claim_freshness(id=claim_id, role="REVIEW")
            if report is None:
                return {"found": False, "id": claim_id, "message": "Claim not found"}
            return report

        elif name == "cortex_compile_context":
            task = args.get("task")
            memory_ids = args.get("memory_ids")
            if not task or memory_ids is None:
                raise ValueError("Parameters 'task' and 'memory_ids' are required for cortex_compile_context.")
            budget = int(args.get("budget_tokens", 500))
            role = args.get("role", "APP")
            return self.api.compile_context(task=task, memory_ids=memory_ids, budget_tokens=budget, role=role)

        else:
            raise ValueError(f"Unknown tool name: {name}")

    def run_stdio(self) -> None:
        """Run standard STDIO transport loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error: invalid JSON"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def main() -> None:
    server = CortexMCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
