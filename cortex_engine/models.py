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
class ActivityEvent:
    """Canonical schema for observable Agent activity and actions."""
    event_id: str
    timestamp: str = field(default_factory=utc_now_iso)
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    actor: str = "agent"  # agent, system, user
    action_type: str = "tool_call"  # tool_call, tool_result, command_exec, file_read, file_write, file_delete, git_action, cortex_action, task_start, task_end, error
    source: str = "mcp"  # mcp, cli, api, agent_hook
    target: str = ""  # resource or target e.g. "cortex_search", "src/auth.py", "git commit"
    status: str = "success"  # success, error, pending, interrupted
    duration_ms: Optional[float] = None
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
            session_id=data.get("session_id"),
            task_id=data.get("task_id"),
            actor=data.get("actor", "agent"),
            action_type=data.get("action_type", "tool_call"),
            source=data.get("source", "mcp"),
            target=data.get("target", ""),
            status=data.get("status", "success"),
            duration_ms=data.get("duration_ms"),
            metadata=data.get("metadata", {}),
            error_type=data.get("error_type"),
            schema_version=data.get("schema_version", "1.0.0"),
        )
