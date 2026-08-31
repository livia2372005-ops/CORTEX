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
    status: str = "active"
    created_at: str = field(default_factory=utc_now_iso)
    provenance: Optional[dict[str, Any]] = None
    supersedes: Optional[str] = None
    related: Optional[List[str]] = None
    affects: Optional[List[str]] = None
    evidence: Optional[List[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Knowledge:
        return cls(
            id=data["id"],
            type=data["type"],
            title=data.get("title", ""),
            content=data.get("content", ""),
            status=data.get("status", "active"),
            created_at=data.get("created_at", utc_now_iso()),
            provenance=data.get("provenance"),
            supersedes=data.get("supersedes"),
            related=data.get("related"),
            affects=data.get("affects"),
            evidence=data.get("evidence"),
        )


@dataclass
class Claim:
    """Claim contract for tracking empirical assertions and verification state."""
    id: str
    statement: str
    type: str = "claim"
    status: str = "unverified"  # unverified, verified, affected, rejected
    created_at: str = field(default_factory=utc_now_iso)
    artifact: Optional[dict[str, Any]] = None  # e.g., {"path": "...", "hash": "..."}
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
