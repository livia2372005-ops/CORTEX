"""CORTEX Local Tool and API Interface."""

from __future__ import annotations

from typing import Any, List, Optional

from .models import Claim, ContextPackage, Event, Knowledge, RoleContext, RoleResult
from .storage import CortexStorage


class CortexAPI:
    """Standard callable API for CORTEX tools."""

    def __init__(self, storage: Optional[CortexStorage] = None):
        self.storage = storage or CortexStorage()

    def record_event(
        self,
        id: str,
        event_type: str,
        role: str,
        payload: dict[str, Any],
        task_id: Optional[str] = None,
        provenance: Optional[dict[str, Any]] = None,
    ) -> str:
        """Record an observable event in append-only log."""
        event = Event(
            id=id,
            type=event_type,
            role=role,
            payload=payload,
            task_id=task_id,
            provenance=provenance,
        )
        return self.storage.record_event(event)

    def record_knowledge(
        self,
        id: str,
        knowledge_type: str,
        title: str,
        content: str,
        status: str = "active",
        provenance: Optional[dict[str, Any]] = None,
        supersedes: Optional[str] = None,
        related: Optional[List[str]] = None,
        affects: Optional[List[str]] = None,
        evidence: Optional[List[dict[str, Any]]] = None,
    ) -> str:
        """Record a persistent knowledge item (decision, constraint, failure, lesson)."""
        item = Knowledge(
            id=id,
            type=knowledge_type,
            title=title,
            content=content,
            status=status,
            provenance=provenance,
            supersedes=supersedes,
            related=related,
            affects=affects,
            evidence=evidence,
        )
        return self.storage.write_knowledge(item)

    def record_claim(
        self,
        id: str,
        statement: str,
        status: str = "unverified",
        artifact: Optional[dict[str, Any]] = None,
        evidence: Optional[List[dict[str, Any]]] = None,
        provenance: Optional[dict[str, Any]] = None,
    ) -> str:
        """Record a testable claim with verification status."""
        claim = Claim(
            id=id,
            statement=statement,
            status=status,
            artifact=artifact,
            evidence=evidence,
            provenance=provenance,
        )
        return self.storage.write_claim(claim)

    def get(self, id: str, category: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Retrieve a specific knowledge record by ID."""
        item = self.storage.read_knowledge(id, category)
        return item.to_dict() if item else None

    def get_claim(self, id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific claim record by ID."""
        claim = self.storage.read_claim(id)
        return claim.to_dict() if claim else None

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict[str, Any]]:
        """Simple deterministic substring search over local knowledge files."""
        items = self.storage.list_knowledge(category)
        query_lower = query.lower()
        matches = []

        for item in items:
            searchable_text = f"{item.id} {item.title} {item.content} {item.type}".lower()
            if query_lower in searchable_text:
                matches.append(item.to_dict())
                if len(matches) >= limit:
                    break

        return matches

    def create_role_context(
        self,
        role: str,
        stable_context: dict[str, Any] | str,
        dynamic_context: dict[str, Any] | str,
        available_tools: List[str],
        task_id: Optional[str] = None,
    ) -> RoleContext:
        """Construct an isolated role working context."""
        return RoleContext(
            role=role,
            stable_context=stable_context,
            dynamic_context=dynamic_context,
            available_tools=available_tools,
            task_id=task_id,
        )

    def create_context_package(
        self,
        stable: dict[str, Any] | str,
        dynamic: dict[str, Any] | str,
    ) -> ContextPackage:
        """Construct a two-layer ContextPackage."""
        return ContextPackage(stable=stable, dynamic=dynamic)

    def serialize_role_result(
        self,
        source_role: str,
        result_type: str,
        items: List[Any],
        provenance: List[Any],
    ) -> dict[str, Any]:
        """Serialize a role boundary outcome without leaking private reasoning."""
        res = RoleResult(
            source_role=source_role,
            result_type=result_type,
            items=items,
            provenance=provenance,
        )
        return res.to_dict()
