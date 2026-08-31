"""CORTEX Local Tool and API Interface."""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from .indexer import CortexIndexer
from .models import (
    Claim,
    ContextPackage,
    Event,
    Knowledge,
    RoleContext,
    RoleResult,
    utc_now_iso,
)
from .storage import CortexStorage


class CortexAPI:
    """Standard callable API for CORTEX tools with SQLite FTS5 acceleration."""

    def __init__(
        self,
        storage: Optional[CortexStorage] = None,
        indexer: Optional[CortexIndexer] = None,
    ):
        self.storage = storage or CortexStorage()
        self.indexer = indexer or CortexIndexer(storage=self.storage)

    def record_event(
        self,
        event_type: str,
        role: str,
        payload: dict[str, Any],
        id: Optional[str] = None,
        task_id: Optional[str] = None,
        provenance: Optional[dict[str, Any]] = None,
    ) -> str:
        """Record an observable event in append-only log and derived index."""
        event_id = id or f"evt-{uuid.uuid4().hex[:8]}"
        event = Event(
            id=event_id,
            type=event_type,
            role=role,
            payload=payload,
            task_id=task_id,
            provenance=provenance,
        )
        persisted_id = self.storage.record_event(event)
        try:
            self.indexer.index_event(event)
        except Exception:
            pass  # Indexing error must never break canonical storage write
        return persisted_id

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
        task_id: Optional[str] = None,
    ) -> str:
        """Record a persistent knowledge item in canonical files and derived index."""
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
        persisted_id = self.storage.write_knowledge(item)
        try:
            self.indexer.index_knowledge_item(item)
        except Exception:
            pass  # Indexing error must never break canonical write

        # Record observable knowledge capture event
        self.record_event(
            event_type="knowledge_recorded",
            role="LEARNING",
            payload={"knowledge_id": id, "type": knowledge_type, "title": title},
            task_id=task_id,
            provenance=provenance,
        )
        return persisted_id

    def record_claim(
        self,
        id: str,
        statement: str,
        status: str = "unverified",
        artifact: Optional[dict[str, Any]] = None,
        evidence: Optional[List[dict[str, Any]]] = None,
        provenance: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
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
        persisted_id = self.storage.write_claim(claim)

        # Record observable claim capture event
        self.record_event(
            event_type="claim_recorded",
            role="LEARNING",
            payload={"claim_id": id, "statement": statement, "status": status},
            task_id=task_id,
            provenance=provenance,
        )
        return persisted_id

    def get(
        self,
        id: str,
        category: Optional[str] = None,
        task_id: Optional[str] = None,
        role: str = "MEMORY",
    ) -> Optional[dict[str, Any]]:
        """Retrieve a specific knowledge record by ID."""
        item = self.storage.read_knowledge(id, category)
        if item is not None:
            self.record_event(
                event_type="memory_get",
                role=role,
                payload={"id": id, "found": True, "type": item.type},
                task_id=task_id,
            )
            return item.to_dict()
        else:
            self.record_event(
                event_type="memory_get",
                role=role,
                payload={"id": id, "found": False},
                task_id=task_id,
            )
            return None

    def get_claim(self, id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific claim record by ID."""
        claim = self.storage.read_claim(id)
        return claim.to_dict() if claim else None

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        task_id: Optional[str] = None,
        role: str = "MEMORY",
    ) -> dict[str, Any]:
        """Search knowledge using fast SQLite FTS5 with fallback to canonical storage scan."""
        matched_items = self.indexer.search_knowledge(query, category=category, limit=limit)

        # Fallback to filesystem scan if FTS index was not yet populated / query empty
        if not matched_items and not self.indexer.db_path.exists():
            items = self.storage.list_knowledge(category)
            query_lower = query.lower()
            for item in items:
                searchable_text = f"{item.id} {item.title} {item.content} {item.type}".lower()
                if query_lower in searchable_text:
                    matched_items.append(item.to_dict())
                    if len(matched_items) >= limit:
                        break

        result_payload = {
            "query": query,
            "results": matched_items,
            "count": len(matched_items),
        }

        # Record observable memory retrieval event
        self.record_event(
            event_type="memory_retrieval",
            role=role,
            payload={
                "query": query,
                "result_ids": [r["id"] for r in matched_items],
                "count": len(matched_items),
            },
            task_id=task_id,
        )

        return result_payload

    def search_events(
        self,
        query: str,
        event_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict[str, Any]]:
        """Search indexed events via SQLite FTS5."""
        return self.indexer.search_events(query, event_type=event_type, limit=limit)

    def rebuild_indexes(self) -> dict[str, int]:
        """Rebuild entire derived index from canonical filesystem storage."""
        stats = self.indexer.rebuild_from_canonical(self.storage)
        self.record_event(
            event_type="index_rebuilt",
            role="APP",
            payload=stats,
        )
        return stats

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
        role: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> ContextPackage:
        """Construct a two-layer ContextPackage."""
        return ContextPackage(
            stable=stable,
            dynamic=dynamic,
            role=role,
            task_id=task_id,
        )

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

    def transition_role(
        self,
        from_context: RoleContext,
        to_role: str,
        to_stable_context: dict[str, Any] | str,
        to_tools: List[str],
        transfer_payload: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> RoleContext:
        """Transition ONE Agent from one role to another with context isolation."""
        active_task_id = task_id or from_context.task_id
        new_dynamic_context = transfer_payload or {}

        new_context = RoleContext(
            role=to_role,
            stable_context=to_stable_context,
            dynamic_context=new_dynamic_context,
            available_tools=to_tools,
            task_id=active_task_id,
        )

        self.record_event(
            event_type="role_transition",
            role=to_role,
            payload={
                "from_role": from_context.role,
                "to_role": to_role,
                "transferred_keys": list(new_dynamic_context.keys()) if isinstance(new_dynamic_context, dict) else ["raw"],
            },
            task_id=active_task_id,
        )

        return new_context
