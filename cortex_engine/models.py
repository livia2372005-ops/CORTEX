"""CORTEX Core Contracts and Data Models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional


def utc_now_iso() -> str:
    """Return current UTC ISO-8601 timestamp string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
    """Raw append-only event schema."""
    id: str
    type: str
    role: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=utc_now_iso)
    task_id: Optional[str] = None
    provenance: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            id=data["id"],
            type=data["type"],
            role=data["role"],
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", utc_now_iso()),
            task_id=data.get("task_id"),
            provenance=data.get("provenance"),
        )


@dataclass
class Knowledge:
    """Persistent knowledge record contract."""
    id: str
    type: str  # decision, constraint, failure, lesson, claim
    title: str
    content: str
    status: str = "active"  # active, superseded, deprecated
    created_at: str = field(default_factory=utc_now_iso)
    provenance: Optional[dict[str, Any]] = None
    supersedes: Optional[str] = None
    derived_from: Optional[List[str]] = None
    related: Optional[List[str]] = None
    affects: Optional[List[str]] = None
    evidence: Optional[List[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Knowledge:
        content = data.get("content") or data.get("statement", "")
        title = data.get("title") or (content[:60] if content else "")
        return cls(
            id=data["id"],
            type=data.get("type", "knowledge"),
            title=title,
            content=content,
            status=data.get("status", "active"),
            created_at=data.get("created_at", utc_now_iso()),
            provenance=data.get("provenance"),
            supersedes=data.get("supersedes"),
            derived_from=data.get("derived_from"),
            related=data.get("related"),
            affects=data.get("affects"),
            evidence=data.get("evidence"),
        )


@dataclass
class MemoryCandidate:
    """Potential knowledge item detected from observable events awaiting Agent judgment."""
    id: str
    event_ids: List[str]
    candidate_type: str  # decision, constraint, failure, lesson, claim
    summary: str
    reason: str  # e.g., 'repeated_failure_pattern', 'architectural_decision_signal', 'constraint_added'
    evidence: List[dict[str, Any]] = field(default_factory=list)
    suggested_title: str = ""
    suggested_content: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryCandidate:
        return cls(
            id=data["id"],
            event_ids=data.get("event_ids", []),
            candidate_type=data.get("candidate_type", "knowledge"),
            summary=data.get("summary", ""),
            reason=data.get("reason", "unknown"),
            evidence=data.get("evidence", []),
            suggested_title=data.get("suggested_title", ""),
            suggested_content=data.get("suggested_content", ""),
            created_at=data.get("created_at", utc_now_iso()),
        )


@dataclass
class Evidence:
    """Explicit, inspectable evidence reference."""
    id: str
    type: str  # artifact, test, git_commit, source_document
    path: Optional[str] = None
    content_hash: Optional[str] = None
    commit: Optional[str] = None
    test_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        return cls(
            id=data["id"],
            type=data["type"],
            path=data.get("path"),
            content_hash=data.get("content_hash"),
            commit=data.get("commit"),
            test_id=data.get("test_id"),
            details=data.get("details"),
        )


@dataclass
class Claim:
    """Claim contract for tracking empirical assertions and verification state."""
    id: str
    statement: str
    type: str = "claim"
    status: str = "unverified"  # unverified, verified, affected, rejected, unprovable
    created_at: str = field(default_factory=utc_now_iso)
    artifact: Optional[dict[str, Any]] = None  # e.g., {"path": "...", "content_hash": "...", "commit": "..."}
    evidence: Optional[List[dict[str, Any]]] = None
    provenance: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        return cls(
            id=data["id"],
            statement=data.get("statement", ""),
            type=data.get("type", "claim"),
            status=data.get("status", "unverified"),
            created_at=data.get("created_at", utc_now_iso()),
            artifact=data.get("artifact"),
            evidence=data.get("evidence"),
            provenance=data.get("provenance"),
        )


@dataclass
class ContextPackage:
    """Layered context package separating stable prefix from dynamic suffix."""
    stable: dict[str, Any] | str
    dynamic: dict[str, Any] | str
    role: Optional[str] = None
    task_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "stable": self.stable,
            "dynamic": self.dynamic,
        }
        if self.role is not None:
            data["role"] = self.role
        if self.task_id is not None:
            data["task_id"] = self.task_id
        return data


@dataclass
class RoleContext:
    """Working context contract for one Agent in an isolated role mode."""
    role: str  # APP, MEMORY, REVIEW, LEARNING
    stable_context: dict[str, Any] | str
    dynamic_context: dict[str, Any] | str
    available_tools: List[str]
    task_id: Optional[str] = None

    def to_package(self) -> ContextPackage:
        return ContextPackage(
            stable=self.stable_context,
            dynamic=self.dynamic_context,
            role=self.role,
            task_id=self.task_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "stable_context": self.stable_context,
            "dynamic_context": self.dynamic_context,
            "available_tools": self.available_tools,
            "task_id": self.task_id,
        }


@dataclass
class RoleResult:
    """Structured boundary transfer envelope across role transitions."""
    source_role: str
    result_type: str
    items: List[Any] = field(default_factory=list)
    provenance: List[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoleResult:
        return cls(
            source_role=data["source_role"],
            result_type=data["result_type"],
            items=data.get("items", []),
            provenance=data.get("provenance", []),
        )


@dataclass
class TaskAnchor:
    """Canonical representation of an explicit engineering task boundary."""
    anchor_id: str
    conversation_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    status: str = "active"  # active, completed, failed, aborted
    workspace: str = ""
    source: str = "api"  # api, cli, mcp, hook, system
    task_label: Optional[str] = None
    prompt_hash: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskAnchor:
        return cls(
            anchor_id=data["anchor_id"],
            conversation_id=data.get("conversation_id"),
            created_at=data.get("created_at", utc_now_iso()),
            ended_at=data.get("ended_at"),
            status=data.get("status", "active"),
            workspace=data.get("workspace", ""),
            source=data.get("source", "api"),
            task_label=data.get("task_label"),
            prompt_hash=data.get("prompt_hash"),
            metadata=data.get("metadata", {}),
            schema_version=data.get("schema_version", "1.0.0"),
        )


@dataclass
class ActivityEvent:
    """Canonical schema for observable Agent activity and actions."""
    event_id: str
    timestamp: str = field(default_factory=utc_now_iso)
    anchor_id: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    step_index: Optional[int] = None
    actor: str = "agent"  # agent, system, user
    action_type: str = "tool_call"  # tool_call, tool_result, command_exec, file_read, file_write, file_delete, git_action, cortex_action, task_start, task_end, error
    source: str = "antigravity_hook"  # antigravity_hook, mcp, cli, python_api, system
    target: str = ""  # resource or target e.g. "cortex_search", "src/auth.py", "git commit"
    tool_name: Optional[str] = None
    status: str = "success"  # success, error, pending, started, interrupted
    activity_domain: Optional[str] = None  # cortex, external_tool, system
    interaction_class: Optional[str] = None  # agent_memory, task_boundary, maintenance
    duration_ms: Optional[float] = None
    parent_event_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_type: Optional[str] = None
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActivityEvent:
        return cls(
            event_id=data["event_id"],
            timestamp=data.get("timestamp", utc_now_iso()),
            anchor_id=data.get("anchor_id"),
            session_id=data.get("session_id"),
            task_id=data.get("task_id"),
            conversation_id=data.get("conversation_id"),
            step_index=data.get("step_index"),
            actor=data.get("actor", "agent"),
            action_type=data.get("action_type", "tool_call"),
            source=data.get("source", "mcp"),
            target=data.get("target", ""),
            tool_name=data.get("tool_name"),
            status=data.get("status", "success"),
            activity_domain=data.get("activity_domain"),
            interaction_class=data.get("interaction_class"),
            duration_ms=data.get("duration_ms"),
            parent_event_id=data.get("parent_event_id"),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata", {}),
            error_type=data.get("error_type"),
            schema_version=data.get("schema_version", "1.0.0"),
        )


def classify_cortex_interaction(tool_or_op_name: str, action_type: str = "tool_call") -> tuple[str, Optional[str]]:
    """Determine activity_domain and interaction_class for an operation or tool call.

    Returns:
        (activity_domain, interaction_class) where:
        - activity_domain: "cortex", "external_tool", or "system"
        - interaction_class: "agent_memory", "task_boundary", "maintenance", or None
    """
    raw_name = (tool_or_op_name or "").strip().lower()

    # Check explicit task boundary action types first
    if action_type in ("task_start", "task_end"):
        return "cortex", "task_boundary"

    # Normalize tool name by stripping standard prefixes
    name = raw_name
    for prefix in ("mcp_cortex_", "mcp_cortex.", "cortex_", "cortex."):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    agent_memory_ops = {
        "search", "get", "compile_context", "record_knowledge",
        "promote_memory", "check_claim_freshness", "check_duplicates",
        "archive_memory", "detect_candidates", "record_event",
    }
    task_boundary_ops = {
        "start_task", "end_task", "task_start", "task_end",
        "get_task", "list_tasks",
    }
    maintenance_ops = {
        "status", "doctor", "reindex", "list_activity", "record_activity",
    }

    if name in agent_memory_ops:
        return "cortex", "agent_memory"
    elif name in task_boundary_ops:
        return "cortex", "task_boundary"
    elif name in maintenance_ops:
        return "cortex", "maintenance"
    elif raw_name.startswith("cortex") or "cortex" in raw_name:
        return "cortex", "maintenance"
    elif action_type == "system" or raw_name.startswith("system"):
        return "system", None
    else:
        return "external_tool", None


def extract_cortex_interaction_metadata(
    tool_or_op_name: str,
    args: dict[str, Any],
    result: Any = None,
) -> dict[str, Any]:
    """Extract metrics-friendly, sanitized metadata for a CORTEX operation."""
    from .redaction import redact_data, redact_text

    norm_name = (tool_or_op_name or "").lower()
    for prefix in ("mcp_cortex_", "mcp_cortex.", "cortex_", "cortex."):
        if norm_name.startswith(prefix):
            norm_name = norm_name[len(prefix):]
            break

    meta: dict[str, Any] = {}

    if norm_name == "search":
        if "query" in args and args["query"]:
            meta["query"] = redact_text(str(args["query"]))
        if isinstance(result, dict):
            meta["candidate_count"] = result.get("count", len(result.get("results", [])))
            if "policy" in result:
                meta["policy"] = result["policy"]
        elif isinstance(result, list):
            meta["candidate_count"] = len(result)
        if "category" in args and args["category"]:
            meta["category"] = args["category"]

    elif norm_name == "get":
        if "id" in args and args["id"]:
            meta["record_id"] = args["id"]
        if isinstance(result, dict):
            meta["found"] = result.get("found", True) if "found" in result else (result.get("id") is not None)
        elif result is None:
            meta["found"] = False

    elif norm_name == "compile_context":
        if "task" in args and args["task"]:
            meta["task"] = redact_text(str(args["task"])[:100])
        if isinstance(result, dict):
            items = result.get("included_ids") or result.get("items") or []
            meta["selected_count"] = len(items) if isinstance(items, list) else result.get("item_count")
            ctx_text = result.get("compiled_text") or result.get("context") or ""
            if isinstance(ctx_text, str) and ctx_text:
                meta["char_count"] = len(ctx_text)
                meta["token_estimate"] = result.get("total_tokens_estimate") or len(ctx_text.split())
        elif "memory_ids" in args and isinstance(args["memory_ids"], list):
            meta["selected_count"] = len(args["memory_ids"])

    elif norm_name == "record_knowledge":
        if "id" in args and args["id"]:
            meta["record_id"] = args["id"]
        elif isinstance(result, dict) and "persisted_id" in result:
            meta["record_id"] = result["persisted_id"]
        if "knowledge_type" in args:
            meta["knowledge_type"] = args["knowledge_type"]

    elif norm_name == "promote_memory":
        candidate_id = args.get("candidate_id") or args.get("id")
        if candidate_id:
            meta["candidate_id"] = candidate_id
        if isinstance(result, dict):
            promoted_id = result.get("promoted_id") or result.get("id")
            if promoted_id:
                meta["resulting_record_id"] = promoted_id

    elif norm_name == "check_claim_freshness":
        if "id" in args and args["id"]:
            meta["claim_id"] = args["id"]
        if isinstance(result, dict):
            meta["classification"] = result.get("status") or result.get("freshness") or result.get("result")

    elif norm_name == "check_duplicates":
        if "title" in args and args["title"]:
            meta["title"] = redact_text(str(args["title"]))
        if isinstance(result, list):
            meta["match_count"] = len(result)

    elif norm_name == "archive_memory":
        if "id" in args and args["id"]:
            meta["record_id"] = args["id"]
        if "reason" in args and args["reason"]:
            meta["reason"] = redact_text(str(args["reason"]))

    elif norm_name in ("start_task", "task_start"):
        if "label" in args or "task_label" in args:
            meta["task_label"] = redact_text(str(args.get("label") or args.get("task_label")))
        if isinstance(result, dict) and "anchor_id" in result:
            meta["anchor_id"] = result["anchor_id"]

    elif norm_name in ("end_task", "task_end"):
        if "anchor_id" in args:
            meta["anchor_id"] = args["anchor_id"]
        if "status" in args:
            meta["task_status"] = args["status"]

    return redact_data(meta)
