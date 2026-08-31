"""CORTEX File-Based Storage Engine."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from .models import Claim, Event, Knowledge


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


class CortexStorage:
    """Manages raw durable file-based storage in .cortex/."""

    def __init__(self, cortex_dir: Optional[str | Path] = None):
        if cortex_dir is None:
            # Default to .cortex in current directory or relative to root
            self.cortex_dir = Path.cwd() / ".cortex"
        else:
            self.cortex_dir = Path(cortex_dir).resolve()

        self.events_dir = self.cortex_dir / "events"
        self.events_file = self.events_dir / "events.jsonl"
        self.knowledge_dir = self.cortex_dir / "knowledge"
        self.state_dir = self.cortex_dir / "state"
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

    def record_event(self, event: Event) -> str:
        """Append an event to the events.jsonl log."""
        self._ensure_directories()
        line = json.dumps(event.to_dict(), ensure_ascii=False)
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return event.id

    def read_events(
        self,
        role: Optional[str] = None,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Read events from the events log with optional filtering."""
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
                    events.append(evt)
                except Exception:
                    continue

        if limit is not None and limit > 0:
            return events[-limit:]
        return events

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
                with open(file_path, "r", encoding="utf-8") as f:
                    return Knowledge.from_dict(json.load(f))
            return None

        # Search all categories if category is not specified
        for cat in set(CATEGORY_MAP.values()):
            file_path = self.knowledge_dir / cat / f"{item_id}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return Knowledge.from_dict(json.load(f))
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
        with open(target_file, "r", encoding="utf-8") as f:
            return Claim.from_dict(json.load(f))

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
