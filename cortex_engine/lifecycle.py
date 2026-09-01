"""CORTEX Memory Lifecycle & Promotion Manager.

Preserves raw event history as append-only. Identifies candidate memories from
observable events and provides deterministic promotion APIs under explicit Agent authority.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .models import Event, Knowledge, MemoryCandidate, utc_now_iso
from .storage import CortexStorage
from .indexer import CortexIndexer


TRIVIAL_EVENT_TYPES = {
    "file_opened",
    "file_read",
    "grep_executed",
    "test_passed",
    "formatting_changed",
    "variable_renamed",
    "linter_run",
    "tool_invoked",
    "command_executed",
}

VALID_KNOWLEDGE_STATUSES = {
    "candidate",
    "active",
    "superseded",
    "affected",
    "archived",
}


def compute_text_similarity(a: str, b: str) -> float:
    """Compute token overlap similarity (harmonic combination of Jaccard and containment)."""
    tokens_a = set(re.findall(r"\b\w{3,}\b", a.lower()))
    tokens_b = set(re.findall(r"\b\w{3,}\b", b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    jaccard = intersection / len(tokens_a | tokens_b)
    containment = intersection / min(len(tokens_a), len(tokens_b))
    return (jaccard + containment) / 2.0


class MemoryLifecycleManager:
    """Manages detection of candidate memories, explicit promotion, status lifecycle, and duplicate identification."""

    def __init__(self, storage: CortexStorage, indexer: Optional[CortexIndexer] = None):
        self.storage = storage
        self.indexer = indexer

    def detect_candidates(self, events: Optional[List[Event]] = None) -> List[MemoryCandidate]:
        """Deterministically scan observable events and identify potential memory candidates."""
        if events is None:
            raw_events = self.storage.read_events()
        else:
            raw_events = events

        candidates: List[MemoryCandidate] = []
        failure_events: List[Event] = []
        seen_cand_keys: set[str] = set()

        for evt in raw_events:
            evt_type = evt.type.lower()
            payload = evt.payload or {}

            # 1. Skip trivial events
            if evt_type in TRIVIAL_EVENT_TYPES and payload.get("status") != "error":
                continue

            # 2. Architectural Decision Signal
            if (
                evt_type in ("architecture_decision", "decision_made", "design_choice")
                or "decision" in payload
                or "architectural_choice" in payload
            ):
                summary = payload.get("summary") or payload.get("decision") or payload.get("title") or "Architectural decision recorded"
                details = payload.get("rationale") or payload.get("content") or str(payload)
                cand_id = f"cand-dec-{evt.id}"
                if cand_id not in seen_cand_keys:
                    seen_cand_keys.add(cand_id)
                    candidates.append(
                        MemoryCandidate(
                            id=cand_id,
                            event_ids=[evt.id],
                            candidate_type="decision",
                            summary=summary,
                            reason="architectural_decision_signal",
                            evidence=[{"event_id": evt.id, "type": evt.type, "payload": payload}],
                            suggested_title=summary[:60],
                            suggested_content=f"{summary}\n\nContext & Rationale:\n{details}",
                        )
                    )

            # 3. New Project Constraint / Invariant Signal
            elif (
                evt_type in ("constraint_added", "policy_defined", "security_boundary")
                or "invariant" in payload
                or "security_boundary" in payload
                or "hard_rule" in payload
            ):
                summary = payload.get("summary") or payload.get("constraint") or payload.get("rule") or "Project constraint detected"
                details = payload.get("rationale") or payload.get("content") or str(payload)
                cand_id = f"cand-con-{evt.id}"
                if cand_id not in seen_cand_keys:
                    seen_cand_keys.add(cand_id)
                    candidates.append(
                        MemoryCandidate(
                            id=cand_id,
                            event_ids=[evt.id],
                            candidate_type="constraint",
                            summary=summary,
                            reason="new_project_constraint",
                            evidence=[{"event_id": evt.id, "type": evt.type, "payload": payload}],
                            suggested_title=summary[:60],
                            suggested_content=f"{summary}\n\nEnforcement:\n{details}",
                        )
                    )

            # 4. Incident Postmortem / Verified Lesson
            elif evt_type in ("incident_postmortem", "lesson_learned", "root_cause_analysis"):
                summary = payload.get("summary") or payload.get("lesson") or "Incident lesson identified"
                details = payload.get("root_cause") or payload.get("content") or str(payload)
                cand_id = f"cand-les-{evt.id}"
                if cand_id not in seen_cand_keys:
                    seen_cand_keys.add(cand_id)
                    candidates.append(
                        MemoryCandidate(
                            id=cand_id,
                            event_ids=[evt.id],
                            candidate_type="lesson",
                            summary=summary,
                            reason="verified_lesson",
                            evidence=[{"event_id": evt.id, "type": evt.type, "payload": payload}],
                            suggested_title=summary[:60],
                            suggested_content=f"{summary}\n\nRoot Cause & Remediation:\n{details}",
                        )
                    )

            # Collect failure events for pattern clustering
            if (
                evt_type in ("test_failure", "task_failed", "build_error", "execution_error")
                or payload.get("status") == "error"
            ):
                failure_events.append(evt)

        # 5. Cluster repeated failures (2+ matching error patterns)
        generic_stopwords = {"during", "execution", "error", "test", "failed", "step", "task", "with", "from", "this", "that", "after", "before", "node", "pool"}
        clusters: Dict[str, List[Event]] = {}
        for fevt in failure_events:
            err_msg = fevt.payload.get("error") or fevt.payload.get("message") or fevt.payload.get("summary") or fevt.type
            raw_words = set(re.findall(r"\b[a-zA-Z_]{4,}\b", err_msg.lower()))
            words = raw_words - generic_stopwords
            if not words:
                words = raw_words
            # Find matching cluster
            matched_key = None
            for key in clusters:
                key_raw = set(re.findall(r"\b[a-zA-Z_]{4,}\b", key.lower()))
                key_words = key_raw - generic_stopwords or key_raw
                if len(words & key_words) >= 2 or (len(words) == 1 and words == key_words):
                    matched_key = key
                    break
            if matched_key:
                clusters[matched_key].append(fevt)
            else:
                clusters[err_msg] = [fevt]

        for err_pattern, evts in clusters.items():
            if len(evts) >= 2:
                evt_ids = [e.id for e in evts]
                cand_id = f"cand-fail-{uuid.uuid5(uuid.NAMESPACE_DNS, err_pattern).hex[:8]}"
                if cand_id not in seen_cand_keys:
                    seen_cand_keys.add(cand_id)
                    candidates.append(
                        MemoryCandidate(
                            id=cand_id,
                            event_ids=evt_ids,
                            candidate_type="failure",
                            summary=f"Repeated failure pattern: {err_pattern[:80]}",
                            reason="repeated_failure_pattern",
                            evidence=[{"event_id": e.id, "type": e.type, "payload": e.payload} for e in evts],
                            suggested_title=f"Recurring Failure: {err_pattern[:50]}",
                            suggested_content=f"Observed repeated failures across {len(evts)} occurrences.\n\nPattern: {err_pattern}\n\nEvent IDs: {', '.join(evt_ids)}",
                        )
                    )

        return candidates

    def promote_candidate(
        self,
        candidate: MemoryCandidate,
        knowledge_id: Optional[str] = None,
        custom_title: Optional[str] = None,
        custom_content: Optional[str] = None,
        status: str = "active",
        supersedes: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        related: Optional[List[str]] = None,
        affects: Optional[List[str]] = None,
    ) -> Knowledge:
        """Promote a memory candidate into persistent knowledge under explicit Agent authority."""
        if status not in VALID_KNOWLEDGE_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_KNOWLEDGE_STATUSES}")

        # Determine knowledge ID prefix
        type_prefix_map = {
            "decision": "DEC",
            "constraint": "CON",
            "failure": "FAIL",
            "lesson": "LES",
            "claim": "CLM",
        }
        # Idempotency check: if candidate was already promoted, return existing record
        for item in self.storage.list_knowledge(category=candidate.candidate_type):
            if item.provenance and item.provenance.get("promoted_from_candidate") == candidate.id:
                return item

        prefix = type_prefix_map.get(candidate.candidate_type, "KNW")
        if not knowledge_id:
            existing = self.storage.list_knowledge(category=candidate.candidate_type)
            next_idx = len(existing) + 1
            knowledge_id = f"{prefix}-{next_idx:03d}"

        title = custom_title or candidate.suggested_title or candidate.summary
        content = custom_content or candidate.suggested_content or candidate.summary

        prov = provenance or {}
        prov.update({
            "promoted_from_candidate": candidate.id,
            "promoted_at": utc_now_iso(),
            "reason": candidate.reason,
        })

        # Handle supersession if specified
        if supersedes:
            self._apply_supersession(superseded_id=supersedes, new_id=knowledge_id)

        record = Knowledge(
            id=knowledge_id,
            type=candidate.candidate_type,
            title=title,
            content=content,
            status=status,
            created_at=utc_now_iso(),
            provenance=prov,
            supersedes=supersedes,
            derived_from=list(candidate.event_ids),
            related=related or [],
            affects=affects or [],
            evidence=candidate.evidence,
        )

        # 1. Persist canonical record
        self.storage.write_knowledge(record)

        # 2. Update index if available
        if self.indexer:
            self.indexer.index_knowledge_item(record)

        # 3. Record observable memory_promoted event
        self.storage.record_event(
            Event(
                id=f"evt-prom-{uuid.uuid4().hex[:8]}",
                type="memory_promoted",
                role="MEMORY",
                payload={
                    "knowledge_id": record.id,
                    "type": record.type,
                    "title": record.title,
                    "status": record.status,
                    "derived_from": record.derived_from,
                    "supersedes": record.supersedes,
                    "candidate_id": candidate.id,
                },
                provenance=prov,
            )
        )

        return record

    def promote_events(
        self,
        event_ids: List[str],
        knowledge_type: str,
        title: str,
        content: str,
        knowledge_id: Optional[str] = None,
        status: str = "active",
        supersedes: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        related: Optional[List[str]] = None,
        affects: Optional[List[str]] = None,
    ) -> Knowledge:
        """Promote raw observable events directly to persistent knowledge upon explicit Agent command."""
        if status not in VALID_KNOWLEDGE_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_KNOWLEDGE_STATUSES}")

        type_prefix_map = {
            "decision": "DEC",
            "constraint": "CON",
            "failure": "FAIL",
            "lesson": "LES",
            "claim": "CLM",
        }
        # Idempotency check: if exact same events and title were already promoted
        for item in self.storage.list_knowledge(category=knowledge_type):
            if item.derived_from == list(event_ids) and item.title == title:
                return item

        prefix = type_prefix_map.get(knowledge_type, "KNW")
        if not knowledge_id:
            existing = self.storage.list_knowledge(category=knowledge_type)
            next_idx = len(existing) + 1
            knowledge_id = f"{prefix}-{next_idx:03d}"

        prov = provenance or {}
        prov.update({
            "promoted_at": utc_now_iso(),
            "explicit_agent_request": True,
        })

        if supersedes:
            self._apply_supersession(superseded_id=supersedes, new_id=knowledge_id)

        record = Knowledge(
            id=knowledge_id,
            type=knowledge_type,
            title=title,
            content=content,
            status=status,
            created_at=utc_now_iso(),
            provenance=prov,
            supersedes=supersedes,
            derived_from=list(event_ids),
            related=related or [],
            affects=affects or [],
            evidence=[{"event_id": eid} for eid in event_ids],
        )

        self.storage.write_knowledge(record)
        if self.indexer:
            self.indexer.index_knowledge_item(record)

        self.storage.record_event(
            Event(
                id=f"evt-prom-{uuid.uuid4().hex[:8]}",
                type="memory_promoted",
                role="MEMORY",
                payload={
                    "knowledge_id": record.id,
                    "type": record.type,
                    "title": record.title,
                    "status": record.status,
                    "derived_from": record.derived_from,
                    "supersedes": record.supersedes,
                },
                provenance=prov,
            )
        )

        return record

    def _apply_supersession(self, superseded_id: str, new_id: str) -> None:
        """Mark existing knowledge record as superseded without deleting raw file or history."""
        old_record = self.storage.read_knowledge(superseded_id)
        if old_record:
            old_record.status = "superseded"
            old_prov = old_record.provenance or {}
            old_prov["superseded_by"] = new_id
            old_prov["superseded_at"] = utc_now_iso()
            old_record.provenance = old_prov
            self.storage.write_knowledge(old_record)
            if self.indexer:
                self.indexer.index_knowledge_item(old_record)

            self.storage.record_event(
                Event(
                    id=f"evt-sup-{uuid.uuid4().hex[:8]}",
                    type="knowledge_superseded",
                    role="MEMORY",
                    payload={
                        "old_id": superseded_id,
                        "new_id": new_id,
                        "status": "superseded",
                    },
                )
            )

    def detect_duplicates(
        self,
        title: str,
        content: str,
        threshold: float = 0.70,
    ) -> List[Dict[str, Any]]:
        """Identify potentially duplicate/similar active knowledge without destructively merging records."""
        query_text = f"{title} {content}"
        active_records = self.storage.list_knowledge()
        duplicates: List[Dict[str, Any]] = []

        for item in active_records:
            item_text = f"{item.title} {item.content}"
            sim = compute_text_similarity(query_text, item_text)
            if sim >= threshold:
                duplicates.append({
                    "id": item.id,
                    "type": item.type,
                    "title": item.title,
                    "status": item.status,
                    "similarity": round(sim, 3),
                    "match_type": "exact_or_near_duplicate" if sim > 0.9 else "high_conceptual_similarity",
                })

        # Sort duplicates by descending similarity
        duplicates.sort(key=lambda x: x["similarity"], reverse=True)
        return duplicates

    def archive_knowledge(self, knowledge_id: str, reason: str = "manual_archival") -> Optional[Knowledge]:
        """Logically mark a knowledge record as archived without physical deletion."""
        record = self.storage.read_knowledge(knowledge_id)
        if not record:
            return None

        record.status = "archived"
        prov = record.provenance or {}
        prov["archived_at"] = utc_now_iso()
        prov["archival_reason"] = reason
        record.provenance = prov

        self.storage.write_knowledge(record)
        if self.indexer:
            self.indexer.index_knowledge_item(record)

        self.storage.record_event(
            Event(
                id=f"evt-arch-{uuid.uuid4().hex[:8]}",
                type="knowledge_archived",
                role="MEMORY",
                payload={"knowledge_id": record.id, "reason": reason, "status": "archived"},
            )
        )
        return record
