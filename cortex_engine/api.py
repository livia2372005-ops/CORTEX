"""CORTEX Local Tool and API Interface."""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from .compiler import CompiledContext, ContextCompiler
from .hybrid_router import HybridRetrievalRouter, RouterPolicy
from .indexer import CortexIndexer
from .lifecycle import MemoryLifecycleManager
from .models import (
    ActivityEvent,
    Claim,
    ContextPackage,
    Event,
    Knowledge,
    MemoryCandidate,
    RoleContext,
    RoleResult,
    utc_now_iso,
)
from .storage import CortexStorage


class CortexAPI:
    """Standard callable API for CORTEX tools with deterministic Hybrid Retrieval acceleration."""

    def __init__(
        self,
        storage: Optional[CortexStorage] = None,
        indexer: Optional[CortexIndexer] = None,
        compiler: Optional[ContextCompiler] = None,
        router: Optional[HybridRetrievalRouter] = None,
        lifecycle: Optional[MemoryLifecycleManager] = None,
    ):
        self.storage = storage or CortexStorage()
        self.indexer = indexer or CortexIndexer(storage=self.storage)
        self.compiler = compiler or ContextCompiler(storage=self.storage)
        self.router = router or HybridRetrievalRouter(storage=self.storage, indexer=self.indexer)
        self.lifecycle = lifecycle or MemoryLifecycleManager(storage=self.storage, indexer=self.indexer)

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
        try:
            self.indexer.index_knowledge_item(Knowledge(
                id=claim.id,
                type="claim",
                title=claim.statement[:60],
                content=claim.statement,
                status=claim.status,
                provenance=claim.provenance,
                evidence=claim.evidence,
            ))
        except Exception:
            pass  # Indexing error must never break canonical storage write

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

    def check_claim_freshness(
        self,
        id: str,
        workspace_root: Optional[str | Path] = None,
        role: str = "REVIEW",
        task_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Evaluate freshness of a claim against current codebase artifacts."""
        claim = self.storage.read_claim(id)
        if claim is None:
            return None

        from .freshness import evaluate_claim_freshness
        root_dir = workspace_root or self.storage.cortex_dir.parent
        report = evaluate_claim_freshness(claim, workspace_root=root_dir)

        # Update stored claim status if changed (e.g. verified -> affected)
        if report["status"] != claim.status:
            claim.status = report["status"]
            self.storage.write_claim(claim)
            try:
                self.indexer.index_knowledge_item(Knowledge(
                    id=claim.id,
                    type=claim.type,
                    title=claim.statement[:60],
                    content=claim.statement,
                    status=claim.status,
                    provenance=claim.provenance,
                    evidence=claim.evidence,
                ))
            except Exception:
                pass

        # Record observable freshness check event
        self.record_event(
            event_type="claim_freshness_checked",
            role=role,
            payload={
                "claim_id": id,
                "fresh": report["fresh"],
                "status": report["status"],
                "reason": report["reason"],
            },
            task_id=task_id,
        )
        return report

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        task_id: Optional[str] = None,
        role: str = "MEMORY",
        policy: str = "hybrid",
    ) -> dict[str, Any]:
        """Search knowledge using deterministic Hybrid Retrieval (FTS + Lexical + Semantic fallback)."""
        routed_data = self.router.search(query=query, policy=policy, limit=limit)
        matched_items = routed_data.get("results", [])

        # Optional category filter
        if category:
            matched_items = [
                r for r in matched_items
                if r.get("type") == category or category.lower() in r.get("id", "").lower()
            ]

        # Fallback to filesystem scan if derived index was not yet populated / query empty
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
            "policy": routed_data.get("policy", policy),
            "count": len(matched_items),
            "results": matched_items,
            "routing_trace": routed_data.get("routing_trace", {}),
        }

        # Record observable memory retrieval event
        self.record_event(
            event_type="memory_retrieval",
            role=role,
            payload={
                "query": query,
                "policy": routed_data.get("policy", policy),
                "result_ids": [r["id"] for r in matched_items],
                "count": len(matched_items),
                "routing_trace": routed_data.get("routing_trace", {}),
            },
            task_id=task_id,
        )

        return result_payload

    def compile_context(
        self,
        task: str,
        memory_ids: List[str],
        budget_tokens: int = 500,
        role: str = "APP",
        task_id: Optional[str] = None,
        layout: str = "layout_4",
    ) -> Dict[str, Any]:
        """Compile selected memory records into a structured, bounded context for the Agent."""
        compiled = self.compiler.compile(
            task=task,
            memory_ids=memory_ids,
            budget_tokens=budget_tokens,
            role=role,
            task_id=task_id,
            layout=layout,
        )

        # Record observable context compilation event
        self.record_event(
            event_type="context_compiled",
            role=role,
            payload={
                "task": task[:60],
                "selected_ids": memory_ids,
                "included_ids": compiled.included_ids,
                "dropped_ids": compiled.dropped_ids_budget,
                "memory_tokens": compiled.memory_tokens_estimate,
                "total_tokens": compiled.total_tokens_estimate,
            },
            task_id=task_id,
        )
        return compiled.to_dict()

    def retrieve_context(
        self,
        query: str,
        budget_tokens: int = 500,
        role: str = "APP",
        task_id: Optional[str] = None,
        layout: str = "layout_4",
    ) -> Dict[str, Any]:
        """Convenience API: Search candidates, select top matching IDs, and compile context."""
        search_res = self.search(query=query, limit=10, role="MEMORY", task_id=task_id)
        candidate_ids = [r["id"] for r in search_res["results"]]
        return self.compile_context(
            task=query,
            memory_ids=candidate_ids,
            budget_tokens=budget_tokens,
            role=role,
            task_id=task_id,
            layout=layout,
        )

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

    def detect_candidates(self, events: Optional[List[Event]] = None) -> List[dict[str, Any]]:
        """Detect candidate memories from observable events."""
        candidates = self.lifecycle.detect_candidates(events=events)
        return [c.to_dict() for c in candidates]

    def promote_candidate(
        self,
        candidate_dict_or_id: str | dict[str, Any],
        knowledge_id: Optional[str] = None,
        custom_title: Optional[str] = None,
        custom_content: Optional[str] = None,
        status: str = "active",
        supersedes: Optional[str] = None,
        provenance: Optional[dict[str, Any]] = None,
        related: Optional[List[str]] = None,
        affects: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Promote a memory candidate into persistent knowledge."""
        if isinstance(candidate_dict_or_id, str):
            # Lookup candidate from current event log
            candidates = self.lifecycle.detect_candidates()
            matching = [c for c in candidates if c.id == candidate_dict_or_id]
            if not matching:
                raise ValueError(f"Candidate '{candidate_dict_or_id}' not found in observable event stream.")
            candidate = matching[0]
        else:
            candidate = MemoryCandidate.from_dict(candidate_dict_or_id)

        promoted = self.lifecycle.promote_candidate(
            candidate=candidate,
            knowledge_id=knowledge_id,
            custom_title=custom_title,
            custom_content=custom_content,
            status=status,
            supersedes=supersedes,
            provenance=provenance,
            related=related,
            affects=affects,
        )
        return promoted.to_dict()

    def promote_memory(
        self,
        event_ids: List[str],
        knowledge_type: str,
        title: str,
        content: str,
        knowledge_id: Optional[str] = None,
        status: str = "active",
        supersedes: Optional[str] = None,
        provenance: Optional[dict[str, Any]] = None,
        related: Optional[List[str]] = None,
        affects: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Directly promote raw observable events to persistent knowledge upon explicit Agent command."""
        promoted = self.lifecycle.promote_events(
            event_ids=event_ids,
            knowledge_type=knowledge_type,
            title=title,
            content=content,
            knowledge_id=knowledge_id,
            status=status,
            supersedes=supersedes,
            provenance=provenance,
            related=related,
            affects=affects,
        )
        return promoted.to_dict()

    def check_duplicates(
        self,
        title: str,
        content: str,
        threshold: float = 0.70,
    ) -> List[dict[str, Any]]:
        """Identify potentially duplicate or highly similar active knowledge without destructive merging."""
        return self.lifecycle.detect_duplicates(title=title, content=content, threshold=threshold)

    def archive_knowledge(
        self,
        knowledge_id: str,
        reason: str = "manual_archival",
    ) -> Optional[dict[str, Any]]:
        """Logically archive a persistent knowledge record without deleting history."""
        archived = self.lifecycle.archive_knowledge(knowledge_id=knowledge_id, reason=reason)
        return archived.to_dict() if archived else None

    # -------------------------------------------------------------------------
    # Activity Observability API
    # -------------------------------------------------------------------------

    def record_activity(
        self,
        action_type: str,
        target: str,
        status: str = "success",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        step_index: Optional[int] = None,
        actor: str = "agent",
        source: str = "python_api",
        tool_name: Optional[str] = None,
        duration_ms: Optional[float] = None,
        parent_event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        error_type: Optional[str] = None,
        id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Explicitly record an observable action or event in the canonical activity log."""
        event_id = id or f"act-{uuid.uuid4().hex[:10]}"
        act_event = ActivityEvent(
            event_id=event_id,
            timestamp=utc_now_iso(),
            session_id=session_id,
            task_id=task_id,
            conversation_id=conversation_id,
            step_index=step_index,
            actor=actor,
            action_type=action_type,
            source=source,
            target=target,
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms,
            parent_event_id=parent_event_id,
            correlation_id=correlation_id,
            metadata=metadata or {},
            error_type=error_type,
        )
        self.storage.record_activity(act_event)
        return act_event.to_dict()

    def list_activity(
        self,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        step_index: Optional[int] = None,
        tool_name: Optional[str] = None,
        action_type: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 50,
        offset: int = 0,
    ) -> List[dict[str, Any]]:
        """Query observable activity events from canonical storage with filtering."""
        events = self.storage.read_activity(
            task_id=task_id,
            session_id=session_id,
            conversation_id=conversation_id,
            step_index=step_index,
            tool_name=tool_name,
            action_type=action_type,
            source=source,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return [e.to_dict() for e in events]

    def get_activity(self, event_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific activity event by its unique event_id."""
        act = self.storage.get_activity(event_id)
        return act.to_dict() if act else None
