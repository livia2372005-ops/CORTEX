"""CORTEX MCP Server for Antigravity Tool Integration."""

from __future__ import annotations

import json
import sys
import time
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
                "policy": {
                    "type": "string",
                    "description": "Retrieval routing policy: 'hybrid' (default), 'fts', 'semantic'.",
                    "default": "hybrid",
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
    {
        "name": "cortex_detect_candidates",
        "description": "Scan observable events and identify candidate memories (e.g. repeated failures, architecture signals) awaiting Agent promotion.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "cortex_promote_memory",
        "description": "Promote candidate memories or raw event IDs directly to persistent knowledge under explicit Agent authority.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Source observable event IDs (e.g., ['evt-100', 'evt-101']).",
                },
                "candidate_id": {
                    "type": "string",
                    "description": "Optional detected candidate ID to promote.",
                },
                "knowledge_type": {
                    "type": "string",
                    "description": "Knowledge type: 'decision', 'constraint', 'failure', 'lesson', 'claim'.",
                },
                "title": {
                    "type": "string",
                    "description": "Durable knowledge title.",
                },
                "content": {
                    "type": "string",
                    "description": "Detailed markdown explanation.",
                },
                "id": {
                    "type": "string",
                    "description": "Optional specific canonical ID (e.g., 'DEC-018'). Auto-assigned if omitted.",
                },
                "status": {
                    "type": "string",
                    "description": "Initial status (default: 'active').",
                    "default": "active",
                },
                "supersedes": {
                    "type": "string",
                    "description": "Optional ID of an older knowledge record that this new record supersedes.",
                },
                "provenance": {
                    "type": "object",
                    "description": "Optional provenance metadata.",
                },
            },
            "required": ["knowledge_type", "title", "content"],
        },
    },
    {
        "name": "cortex_check_duplicates",
        "description": "Check if a proposed knowledge item is similar or duplicate to existing active knowledge without destructive merging.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Proposed knowledge title.",
                },
                "content": {
                    "type": "string",
                    "description": "Proposed knowledge content.",
                },
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold (default: 0.70).",
                    "default": 0.70,
                },
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "cortex_archive_memory",
        "description": "Logically archive a persistent knowledge record without deleting historical files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Knowledge ID to archive (e.g., 'DEC-002').",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for archival.",
                    "default": "manual_archival",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "cortex_record_activity",
        "description": "Record an observable Agent action, command execution, tool result, or file operation to the canonical activity log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "Category of action: 'tool_call', 'tool_result', 'command_exec', 'file_read', 'file_write', 'file_delete', 'git_action', 'cortex_action', 'task_start', 'task_end', 'error'.",
                },
                "target": {
                    "type": "string",
                    "description": "Action resource or target (e.g., 'pytest tests/', 'src/auth.py', 'git commit').",
                },
                "status": {
                    "type": "string",
                    "description": "Status of the action: 'success' (default), 'error', 'pending', 'interrupted'.",
                    "default": "success",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional associated task ID.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID.",
                },
                "duration_ms": {
                    "type": "number",
                    "description": "Optional duration in milliseconds.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Sanitized metadata describing the operation (e.g. exit code, byte count).",
                },
                "error_type": {
                    "type": "string",
                    "description": "Optional sanitized error category.",
                },
            },
            "required": ["action_type", "target"],
        },
    },
    {
        "name": "cortex_list_activity",
        "description": "Query the canonical activity log to inspect real Agent actions and timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Filter by task ID.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Filter by session ID.",
                },
                "action_type": {
                    "type": "string",
                    "description": "Filter by action type (e.g., 'tool_call', 'command_exec').",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status ('success', 'error').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of activity events to return (default: 50).",
                    "default": 50,
                },
            },
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
            start_t = time.perf_counter()
            try:
                result_data = self._execute_tool(tool_name, args)
                duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                # Automatically record observable MCP tool invocation (skip list_activity to avoid noise)
                if tool_name != "cortex_list_activity":
                    try:
                        self.api.record_activity(
                            action_type="tool_call",
                            target=str(tool_name),
                            source="mcp",
                            status="success",
                            duration_ms=duration_ms,
                            metadata={"args_keys": list(args.keys())},
                        )
                    except Exception:
                        pass
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
                duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                try:
                    self.api.record_activity(
                        action_type="tool_call",
                        target=str(tool_name),
                        source="mcp",
                        status="error",
                        duration_ms=duration_ms,
                        error_type="ValueError",
                        metadata={"error": str(ve)},
                    )
                except Exception:
                    pass
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": str(ve)},
                }
            except Exception as e:
                duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                try:
                    self.api.record_activity(
                        action_type="tool_call",
                        target=str(tool_name),
                        source="mcp",
                        status="error",
                        duration_ms=duration_ms,
                        error_type=type(e).__name__,
                        metadata={"error": str(e)},
                    )
                except Exception:
                    pass
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
            policy = args.get("policy", "hybrid")
            return self.api.search(query=query, category=category, limit=limit, role="MEMORY", policy=policy)

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

        elif name == "cortex_detect_candidates":
            return {"candidates": self.api.detect_candidates()}

        elif name == "cortex_promote_memory":
            k_type = args.get("knowledge_type")
            title = args.get("title")
            content = args.get("content")
            if not k_type or not title or not content:
                raise ValueError("Parameters 'knowledge_type', 'title', and 'content' are required for cortex_promote_memory.")
            event_ids = args.get("event_ids") or []
            cand_id = args.get("candidate_id")
            k_id = args.get("id")
            status = args.get("status", "active")
            supersedes = args.get("supersedes")
            provenance = args.get("provenance")

            if cand_id:
                return self.api.promote_candidate(
                    candidate_dict_or_id=cand_id,
                    knowledge_id=k_id,
                    custom_title=title,
                    custom_content=content,
                    status=status,
                    supersedes=supersedes,
                    provenance=provenance,
                )
            else:
                return self.api.promote_memory(
                    event_ids=event_ids,
                    knowledge_type=k_type,
                    title=title,
                    content=content,
                    knowledge_id=k_id,
                    status=status,
                    supersedes=supersedes,
                    provenance=provenance,
                )

        elif name == "cortex_check_duplicates":
            title = args.get("title")
            content = args.get("content")
            if not title or not content:
                raise ValueError("Parameters 'title' and 'content' are required for cortex_check_duplicates.")
            threshold = float(args.get("threshold", 0.70))
            return {"duplicates": self.api.check_duplicates(title=title, content=content, threshold=threshold)}

        elif name == "cortex_archive_memory":
            item_id = args.get("id")
            if not item_id:
                raise ValueError("Parameter 'id' is required for cortex_archive_memory.")
            reason = args.get("reason", "manual_archival")
            archived = self.api.archive_knowledge(knowledge_id=item_id, reason=reason)
            if archived is None:
                return {"found": False, "id": item_id, "message": "Record not found"}
            return {"archived": True, "record": archived}

        elif name == "cortex_record_activity":
            action_type = args.get("action_type")
            target = args.get("target")
            if not action_type or not target:
                raise ValueError("Parameters 'action_type' and 'target' are required for cortex_record_activity.")
            status = args.get("status", "success")
            task_id = args.get("task_id")
            session_id = args.get("session_id")
            duration_ms = float(args["duration_ms"]) if "duration_ms" in args and args["duration_ms"] is not None else None
            metadata = args.get("metadata")
            error_type = args.get("error_type")
            recorded = self.api.record_activity(
                action_type=action_type,
                target=target,
                status=status,
                task_id=task_id,
                session_id=session_id,
                source="mcp",
                duration_ms=duration_ms,
                metadata=metadata,
                error_type=error_type,
            )
            return {"recorded_id": recorded["event_id"], "status": "persisted"}

        elif name == "cortex_list_activity":
            task_id = args.get("task_id")
            session_id = args.get("session_id")
            action_type = args.get("action_type")
            status = args.get("status")
            limit = int(args.get("limit", 50))
            activities = self.api.list_activity(
                task_id=task_id,
                session_id=session_id,
                action_type=action_type,
                status=status,
                limit=limit,
            )
            return {"activities": activities, "count": len(activities)}

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
