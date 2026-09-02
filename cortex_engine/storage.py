"""CORTEX File-Based Storage Engine."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from .models import ActivityEvent, Claim, Event, Knowledge, TaskAnchor, utc_now_iso
from .redaction import redact_data


CATEGORY_MAP = {
    "decision": "decisions",
    "decisions": "decisions",
    "constraint": "constraints",
    "constraints": "constraints",
    "failure": "failures",
    "failures": "failures",
    "lesson": "lessons",
    "lessons": "lessons",
    "claim": "claims",
    "claims": "claims",
}


def normalize_workspace_path(path_or_uri: Optional[str | Path]) -> str:
    """Normalize workspace paths and URIs for robust cross-platform comparison."""
    if not path_or_uri:
        return ""
    s = str(path_or_uri).strip()
    if s.startswith("file:///"):
        s = s[8:]
    elif s.startswith("file://"):
        s = s[7:]
    try:
        p = Path(s).resolve()
        return str(p)
    except Exception:
        return s.replace("\\", "/").rstrip("/")


class CortexStorage:
    """Manages raw durable file-based storage in .cortex/."""

    def __init__(self, cortex_dir: Optional[str | Path] = None):
        if cortex_dir is None:
            # Default to .cortex in current directory or relative to root
            self.cortex_dir = (Path.cwd() / ".cortex").resolve()
        else:
            self.cortex_dir = Path(cortex_dir).resolve()

        self.workspace_root = self.cortex_dir.parent
        self.events_dir = self.cortex_dir / "events"
        self.events_file = self.events_dir / "events.jsonl"
        self.activity_file = self.events_dir / "activity.jsonl"
        self.knowledge_dir = self.cortex_dir / "knowledge"
        self.state_dir = self.cortex_dir / "state"
        self.anchors_file = self.state_dir / "anchors.jsonl"
        self.indexes_dir = self.cortex_dir / "indexes"
        self.working_dir = self.cortex_dir / "working"

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure standard .cortex directory skeleton exists."""
        self.events_dir.mkdir(parents=True, exist_ok=True)
        for cat in set(CATEGORY_MAP.values()):
            (self.knowledge_dir / cat).mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        self.working_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Events Layer
    # -------------------------------------------------------------------------

    def append_event(self, event: Event) -> str:
        """Append an observable event to the canonical append-only events.jsonl log."""
        self._ensure_directories()
        line = json.dumps(event.to_dict(), ensure_ascii=False)
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return event.id

    record_event = append_event

    def read_events(
        self,
        role: Optional[str] = None,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Read events from the append-only events log with optional filtering."""
        if not self.events_file.exists():
            return []

        events: List[Event] = []
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    evt = Event.from_dict(data)
                    if role and evt.role != role:
                        continue
                    if event_type and evt.type != event_type:
                        continue
                    if task_id and evt.task_id != task_id:
                        continue
                    if source and evt.source != source:
                        continue
                    events.append(evt)
                except Exception:
                    continue

        if limit is not None and limit > 0:
            return events[-limit:]
        return events

    # -------------------------------------------------------------------------
    # Task Anchor Layer
    # -------------------------------------------------------------------------

    def record_task_anchor(self, anchor: TaskAnchor) -> str:
        """Append or update a task boundary anchor in state/anchors.jsonl."""
        self._ensure_directories()
        clean_anchor = TaskAnchor(
            anchor_id=anchor.anchor_id,
            conversation_id=anchor.conversation_id,
            created_at=anchor.created_at,
            ended_at=anchor.ended_at,
            status=anchor.status,
            workspace=str(anchor.workspace or ""),
            source=anchor.source,
            task_label=redact_data(anchor.task_label) if anchor.task_label else None,
            prompt_hash=anchor.prompt_hash,
            metadata=redact_data(anchor.metadata) if anchor.metadata else {},
            schema_version=anchor.schema_version,
        )
        line = json.dumps(clean_anchor.to_dict(), ensure_ascii=False)
        with open(self.anchors_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return clean_anchor.anchor_id

    def get_task_anchor(self, anchor_id: str) -> Optional[TaskAnchor]:
        """Retrieve the latest state of a specific task anchor by ID."""
        if not self.anchors_file.exists():
            return None

        latest_anchor: Optional[TaskAnchor] = None
        with open(self.anchors_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("anchor_id") == anchor_id:
                        latest_anchor = TaskAnchor.from_dict(data)
                except Exception:
                    continue
        return latest_anchor

    def get_active_task_anchor(
        self,
        conversation_id: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> Optional[TaskAnchor]:
        """Retrieve the most recent active task anchor for a conversation or workspace."""
        if not self.anchors_file.exists():
            return None

        anchors_map: dict[str, TaskAnchor] = {}
        with open(self.anchors_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    anc = TaskAnchor.from_dict(data)
                    anchors_map[anc.anchor_id] = anc
                except Exception:
                    continue

        active_anchors = [anc for anc in anchors_map.values() if anc.status == "active"]
        if not active_anchors:
            return None

        def workspace_matches(anc: TaskAnchor) -> bool:
            if not workspace or not anc.workspace:
                return True
            w1 = normalize_workspace_path(anc.workspace).lower()
            w2 = normalize_workspace_path(workspace).lower()
            return w1 == w2 or w1.endswith(w2) or w2.endswith(w1)

        # 1. Exact match on conversation_id (and compatible workspace)
        if conversation_id:
            conv_matches = [
                anc for anc in active_anchors
                if anc.conversation_id == conversation_id and workspace_matches(anc)
            ]
            if conv_matches:
                return conv_matches[-1]

            # 2. If no exact conversation match, match active anchors in same workspace
            # that have no explicit conversation_id bound (e.g. started via CLI in this workspace)
            unbound_matches = [
                anc for anc in active_anchors
                if (not anc.conversation_id) and workspace_matches(anc)
            ]
            if unbound_matches:
                return unbound_matches[-1]

            # Strict isolation: active anchors bound to a DIFFERENT conversation_id are not attached
            return None

        # 3. If no conversation_id supplied, match active anchors for this workspace
        ws_matches = [anc for anc in active_anchors if workspace_matches(anc)]
        if ws_matches:
            return ws_matches[-1]

        return None

    def list_task_anchors(
        self,
        conversation_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = 50,
    ) -> List[TaskAnchor]:
        """List distinct task anchors resolving each anchor to its latest state."""
        if not self.anchors_file.exists():
            return []

        anchors_map: dict[str, TaskAnchor] = {}
        with open(self.anchors_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    anc = TaskAnchor.from_dict(data)
                    anchors_map[anc.anchor_id] = anc
                except Exception:
                    continue

        results: List[TaskAnchor] = []
        for anc in anchors_map.values():
            if conversation_id and anc.conversation_id != conversation_id:
                continue
            if status and anc.status != status:
                continue
            results.append(anc)

        if limit is not None and limit > 0:
            return results[-limit:]
        return results

    def update_task_anchor(
        self,
        anchor_id: str,
        status: str = "completed",
        ended_at: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[TaskAnchor]:
        """Update status and end timestamp of a task anchor."""
        existing = self.get_task_anchor(anchor_id)
        if not existing:
            return None

        updated_meta = dict(existing.metadata)
        if metadata:
            updated_meta.update(metadata)

        updated_anchor = TaskAnchor(
            anchor_id=existing.anchor_id,
            conversation_id=existing.conversation_id,
            created_at=existing.created_at,
            ended_at=ended_at or utc_now_iso(),
            status=status,
            workspace=existing.workspace,
            source=existing.source,
            task_label=existing.task_label,
            prompt_hash=existing.prompt_hash,
            metadata=updated_meta,
            schema_version=existing.schema_version,
        )
        self.record_task_anchor(updated_anchor)
        return updated_anchor

    # -------------------------------------------------------------------------
    # Activity Observability Layer
    # -------------------------------------------------------------------------

    def record_activity(self, activity: ActivityEvent) -> str:
        """Append an activity event to the canonical append-only activity.jsonl log with automatic sanitization."""
        self._ensure_directories()
        # Sanitize metadata, target, and error info
        sanitized_metadata = redact_data(activity.metadata) if activity.metadata else {}
        sanitized_target = redact_data(activity.target) if activity.target else ""
        sanitized_error = redact_data(activity.error_type) if activity.error_type else None
        sanitized_tool = redact_data(activity.tool_name) if activity.tool_name else None

        clean_activity = ActivityEvent(
            event_id=activity.event_id,
            timestamp=activity.timestamp,
            anchor_id=activity.anchor_id,
            session_id=activity.session_id,
            task_id=activity.task_id,
            conversation_id=activity.conversation_id,
            step_index=activity.step_index,
            actor=activity.actor,
            action_type=activity.action_type,
            source=activity.source,
            target=sanitized_target,
            tool_name=sanitized_tool,
            status=activity.status,
            duration_ms=activity.duration_ms,
            parent_event_id=activity.parent_event_id,
            correlation_id=activity.correlation_id,
            metadata=sanitized_metadata,
            error_type=sanitized_error,
            schema_version=activity.schema_version,
        )

        line = json.dumps(clean_activity.to_dict(), ensure_ascii=False)
        with open(self.activity_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return clean_activity.event_id

    def read_activity(
        self,
        task_id: Optional[str] = None,
        anchor_id: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        step_index: Optional[int] = None,
        tool_name: Optional[str] = None,
        action_type: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[ActivityEvent]:
        """Read activity events from the canonical activity log with filtering."""
        if not self.activity_file.exists():
            return []

        # task_id or anchor_id match interchangeably for backward compatibility
        target_anchor = anchor_id or task_id

        activities: List[ActivityEvent] = []
        with open(self.activity_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    act = ActivityEvent.from_dict(data)
                    if target_anchor and act.anchor_id != target_anchor and act.task_id != target_anchor:
                        continue
                    if session_id and act.session_id != session_id:
                        continue
                    if conversation_id and act.conversation_id != conversation_id:
                        continue
                    if step_index is not None and act.step_index != step_index:
                        continue
                    if tool_name and act.tool_name != tool_name:
                        continue
                    if action_type and act.action_type != action_type:
                        continue
                    if source and act.source != source:
                        continue
                    if status and act.status != status:
                        continue
                    if start_time and act.timestamp < start_time:
                        continue
                    if end_time and act.timestamp > end_time:
                        continue
                    activities.append(act)
                except Exception:
                    continue

        if offset > 0:
            activities = activities[offset:]
        if limit is not None and limit > 0:
            return activities[:limit] if offset > 0 else activities[-limit:]
        return activities

    def get_activity(self, event_id: str) -> Optional[ActivityEvent]:
        """Retrieve a specific activity event by its event_id."""
        if not self.activity_file.exists():
            return None

        with open(self.activity_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("event_id") == event_id:
                        return ActivityEvent.from_dict(data)
                except Exception:
                    continue
        return None

    # -------------------------------------------------------------------------
    # Knowledge Layer
    # -------------------------------------------------------------------------

    def write_knowledge(self, item: Knowledge) -> str:
        """Persist a knowledge record as a structured JSON/MD record."""
        self._ensure_directories()
        category = CATEGORY_MAP.get(item.type.lower(), "decisions")
        target_dir = self.knowledge_dir / category
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / f"{item.id}.json"
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)
        return item.id

    def read_knowledge(self, item_id: str, category: Optional[str] = None) -> Optional[Knowledge]:
        """Read a knowledge record by ID."""
        if category:
            cat_dir = CATEGORY_MAP.get(category.lower(), category)
            file_path = self.knowledge_dir / cat_dir / f"{item_id}.json"
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return Knowledge.from_dict(json.load(f))
                except Exception:
                    return None
            return None

        # Search all categories if category is not specified
        for cat in set(CATEGORY_MAP.values()):
            file_path = self.knowledge_dir / cat / f"{item_id}.json"
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return Knowledge.from_dict(json.load(f))
                except Exception:
                    return None
        return None

    def list_knowledge(self, category: Optional[str] = None) -> List[Knowledge]:
        """List all knowledge records in a category or across all categories."""
        categories = [CATEGORY_MAP[category.lower()]] if category else list(set(CATEGORY_MAP.values()))
        results: List[Knowledge] = []

        for cat in categories:
            cat_dir = self.knowledge_dir / cat
            if not cat_dir.exists():
                continue
            for file_path in sorted(cat_dir.glob("*.json")):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        results.append(Knowledge.from_dict(json.load(f)))
                except Exception:
                    continue
        return results

    # -------------------------------------------------------------------------
    # Claims Layer
    # -------------------------------------------------------------------------

    def write_claim(self, claim: Claim) -> str:
        """Persist a claim record."""
        self._ensure_directories()
        claims_dir = self.knowledge_dir / "claims"
        claims_dir.mkdir(parents=True, exist_ok=True)

        target_file = claims_dir / f"{claim.id}.json"
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(claim.to_dict(), f, indent=2, ensure_ascii=False)
        return claim.id

    def read_claim(self, claim_id: str) -> Optional[Claim]:
        """Read a claim record by ID."""
        target_file = self.knowledge_dir / "claims" / f"{claim_id}.json"
        if not target_file.exists():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return Claim.from_dict(json.load(f))
        except Exception:
            return None

    def list_claims(self, status: Optional[str] = None) -> List[Claim]:
        """List all claims with optional status filtering."""
        claims_dir = self.knowledge_dir / "claims"
        if not claims_dir.exists():
            return []

        results: List[Claim] = []
        for file_path in sorted(claims_dir.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    claim = Claim.from_dict(json.load(f))
                    if status and claim.status != status:
                        continue
                    results.append(claim)
            except Exception:
                continue
        return results
