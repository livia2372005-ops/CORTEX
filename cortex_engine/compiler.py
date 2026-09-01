"""CORTEX Context Compiler Layer (Transforms retrieved memory into structured Agent-facing context)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .models import Claim, Evidence, Knowledge
from .storage import CortexStorage


@dataclass
class CompiledContext:
    """Structured result of context compilation."""
    task: str
    compiled_text: str
    total_tokens_estimate: int
    memory_tokens_estimate: int
    selected_ids: List[str]
    included_ids: List[str]
    dropped_ids_budget: List[str]
    sections_present: List[str]
    provenance: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "compiled_text": self.compiled_text,
            "total_tokens_estimate": self.total_tokens_estimate,
            "memory_tokens_estimate": self.memory_tokens_estimate,
            "selected_ids": self.selected_ids,
            "included_ids": self.included_ids,
            "dropped_ids_budget": self.dropped_ids_budget,
            "sections_present": self.sections_present,
            "provenance": self.provenance,
        }


class ContextCompiler:
    """Compiles selected memory records and evidence into structured, bounded Agent context."""

    def __init__(self, storage: Optional[CortexStorage] = None):
        self.storage = storage or CortexStorage()
        self.stable_prefix = (
            "You are ONE engineering agent operating in an isolated role mode.\n"
            "Follow project constraints, inspect evidence, and maintain architectural invariants."
        )

    def compile(
        self,
        task: str,
        memory_ids: List[str],
        budget_tokens: int = 500,
        role: str = "APP",
        task_id: Optional[str] = None,
        layout: str = "layout_4",
        extra_evidence: Optional[List[Evidence]] = None,
    ) -> CompiledContext:
        """Compile selected knowledge records into structured context enforcing token budget."""
        # 1. Fetch records from canonical storage
        records: List[Knowledge] = []
        claims: List[Claim] = []
        provenance_list: List[Dict[str, Any]] = []

        for m_id in memory_ids:
            # Check claim records first
            c = self.storage.read_claim(m_id)
            if c is not None:
                claims.append(c)
                provenance_list.append({
                    "id": c.id,
                    "type": "claim",
                    "source_path": f".cortex/knowledge/claims/{c.id}.json",
                    "status": c.status,
                    "artifact": c.artifact,
                })
                continue

            # Check knowledge records
            k = self.storage.read_knowledge(m_id)
            if k is not None:
                records.append(k)
                category = k.type.lower() + ("s" if not k.type.endswith("s") else "")
                provenance_list.append({
                    "id": k.id,
                    "type": k.type,
                    "source_path": f".cortex/knowledge/{category}/{k.id}.json",
                    "status": k.status,
                    "supersedes": k.supersedes,
                })
                continue

        # 2. Deduplicate while preserving IDs and distinct statements
        deduped_records = self._deduplicate_records(records)

        # 3. Categorize into sections
        constraints = [r for r in deduped_records if r.type == "constraint"]
        decisions = [r for r in deduped_records if r.type == "decision"]
        failures = [r for r in deduped_records if r.type == "failure"]
        lessons = [r for r in deduped_records if r.type in ["lesson", "general"]]

        # 4. Budget prioritization: Constraints > Decisions > Failures > Claims > Evidence > Lessons
        included_ids: List[str] = []
        dropped_ids: List[str] = []
        accumulated_chars = 0
        char_budget = budget_tokens * 4  # heuristic: 4 chars per token

        active_constraints: List[Knowledge] = []
        active_decisions: List[Knowledge] = []
        active_failures: List[Knowledge] = []
        active_claims: List[Claim] = []
        active_evidence: List[Evidence] = []
        active_lessons: List[Knowledge] = []

        # Priority 1: Constraints
        for c in constraints:
            chunk = f"CONSTRAINT [{c.id}] ({c.status.upper()}): {c.content}\n"
            if accumulated_chars + len(chunk) <= char_budget or not active_constraints:
                active_constraints.append(c)
                included_ids.append(c.id)
                accumulated_chars += len(chunk)
            else:
                dropped_ids.append(c.id)

        # Priority 2: Decisions
        for d in decisions:
            sup = f" (SUPERSEDES: {d.supersedes})" if d.supersedes else ""
            chunk = f"DECISION [{d.id}] [{d.status.upper()}]{sup}: {d.title} — {d.content}\n"
            if accumulated_chars + len(chunk) <= char_budget:
                active_decisions.append(d)
                included_ids.append(d.id)
                accumulated_chars += len(chunk)
            else:
                dropped_ids.append(d.id)

        # Priority 3: Failures
        for f in failures:
            chunk = f"FAILURE [{f.id}]: {f.title} — {f.content}\n"
            if accumulated_chars + len(chunk) <= char_budget:
                active_failures.append(f)
                included_ids.append(f.id)
                accumulated_chars += len(chunk)
            else:
                dropped_ids.append(f.id)

        # Priority 4: Claims
        for cl in claims:
            path_ref = cl.artifact.get("path") if cl.artifact else "none"
            chunk = f"CLAIM [{cl.id}] [{cl.status.upper()}]: {cl.statement} (artifact: {path_ref})\n"
            if accumulated_chars + len(chunk) <= char_budget:
                active_claims.append(cl)
                included_ids.append(cl.id)
                accumulated_chars += len(chunk)
            else:
                dropped_ids.append(cl.id)

        # Priority 5: Evidence
        if extra_evidence:
            for ev in extra_evidence:
                chunk = f"EVIDENCE [{ev.id}] ({ev.type.upper()}): path={ev.path or 'n/a'} commit={ev.commit or 'HEAD'}\n"
                if accumulated_chars + len(chunk) <= char_budget:
                    active_evidence.append(ev)
                    accumulated_chars += len(chunk)

        # Priority 6: Lessons
        for l in lessons:
            chunk = f"LESSON [{l.id}]: {l.title} — {l.content}\n"
            if accumulated_chars + len(chunk) <= char_budget:
                active_lessons.append(l)
                included_ids.append(l.id)
                accumulated_chars += len(chunk)
            else:
                dropped_ids.append(l.id)

        # 5. Format into sections (Omit empty sections)
        sections_present: List[str] = ["TASK"]
        section_blocks: Dict[str, str] = {}

        if active_constraints:
            sections_present.append("CRITICAL CONSTRAINTS")
            section_blocks["CRITICAL CONSTRAINTS"] = "\n".join(
                f"- **{c.id}** [STATUS: {c.status.upper()}]: {c.content}" for c in active_constraints
            )

        if active_decisions:
            sections_present.append("ACTIVE DECISIONS")
            dec_strs = []
            for d in active_decisions:
                sup_str = f"\n  SUPERSEDES: {d.supersedes}" if d.supersedes else ""
                dec_strs.append(f"- **{d.id}** [{d.status.upper()}]: {d.title}\n  STATEMENT: {d.content}{sup_str}")
            section_blocks["ACTIVE DECISIONS"] = "\n".join(dec_strs)

        if active_failures:
            sections_present.append("RELEVANT FAILURES")
            section_blocks["RELEVANT FAILURES"] = "\n".join(
                f"- **{f.id}**: {f.title}\n  IMPACT: {f.content}" for f in active_failures
            )

        if active_claims:
            sections_present.append("CLAIMS & FRESHNESS")
            section_blocks["CLAIMS & FRESHNESS"] = "\n".join(
                f"- **{cl.id}** [STATUS: {cl.status.upper()}]: {cl.statement}\n  ARTIFACT: {cl.artifact.get('path') if cl.artifact else 'N/A'}"
                for cl in active_claims
            )

        if active_evidence:
            sections_present.append("EVIDENCE")
            section_blocks["EVIDENCE"] = "\n".join(
                f"- **{e.id}** [{e.type.upper()}]: path={e.path or 'N/A'} commit={e.commit or 'HEAD'}"
                for e in active_evidence
            )

        if active_lessons:
            sections_present.append("HISTORICAL CONTEXT")
            section_blocks["HISTORICAL CONTEXT"] = "\n".join(
                f"- **{l.id}**: {l.title} — {l.content}" for l in active_lessons
            )

        # 6. Assemble according to layout (Default: Layout 4)
        compiled_text = self._assemble_layout(
            layout=layout,
            task=task,
            section_blocks=section_blocks,
            role=role,
        )

        total_tokens = len(compiled_text) // 4
        memory_tokens = accumulated_chars // 4

        return CompiledContext(
            task=task,
            compiled_text=compiled_text,
            total_tokens_estimate=total_tokens,
            memory_tokens_estimate=memory_tokens,
            selected_ids=memory_ids,
            included_ids=included_ids,
            dropped_ids_budget=dropped_ids,
            sections_present=sections_present,
            provenance=[p for p in provenance_list if p["id"] in included_ids],
        )

    def _deduplicate_records(self, records: List[Knowledge]) -> List[Knowledge]:
        """Deduplicate records with verbatim identical statements while retaining distinct records."""
        seen_statements: Set[str] = set()
        deduped: List[Knowledge] = []

        for r in records:
            stmt = r.content.strip().lower()
            if stmt in seen_statements:
                continue
            seen_statements.add(stmt)
            deduped.append(r)

        return deduped

    def _assemble_layout(
        self,
        layout: str,
        task: str,
        section_blocks: Dict[str, str],
        role: str,
    ) -> str:
        """Assemble layout blocks (Default: Layout 4)."""
        header = f"=== SYSTEM STABLE (ROLE: {role.upper()}) ===\n{self.stable_prefix}"
        task_block = f"=== CURRENT TASK ===\n{task}"

        if layout == "layout_1":
            # STABLE -> MEMORY -> TASK
            mem_parts = [f"=== {name} ===\n{content}" for name, content in section_blocks.items()]
            return f"{header}\n\n" + "\n\n".join(mem_parts) + f"\n\n{task_block}"

        elif layout == "layout_2":
            # STABLE -> TASK -> MEMORY
            mem_parts = [f"=== {name} ===\n{content}" for name, content in section_blocks.items()]
            return f"{header}\n\n{task_block}\n\n" + "\n\n".join(mem_parts)

        elif layout == "layout_3":
            # STABLE -> TASK -> CONSTRAINTS -> MEMORY -> EVIDENCE
            parts = [header, task_block]
            if "CRITICAL CONSTRAINTS" in section_blocks:
                parts.append(f"=== CRITICAL CONSTRAINTS ===\n{section_blocks['CRITICAL CONSTRAINTS']}")
            for name, content in section_blocks.items():
                if name not in ["CRITICAL CONSTRAINTS", "EVIDENCE"]:
                    parts.append(f"=== {name} ===\n{content}")
            if "EVIDENCE" in section_blocks:
                parts.append(f"=== EVIDENCE ===\n{section_blocks['EVIDENCE']}")
            return "\n\n".join(parts)

        else:
            # Default Layout 4: STABLE -> CRITICAL CONSTRAINTS -> TASK -> RELEVANT MEMORY -> EVIDENCE
            parts = [header]
            if "CRITICAL CONSTRAINTS" in section_blocks:
                parts.append(f"=== CRITICAL CONSTRAINTS ===\n{section_blocks['CRITICAL CONSTRAINTS']}")
            parts.append(task_block)
            for name, content in section_blocks.items():
                if name not in ["CRITICAL CONSTRAINTS", "EVIDENCE"]:
                    parts.append(f"=== {name} ===\n{content}")
            if "EVIDENCE" in section_blocks:
                parts.append(f"=== EVIDENCE ===\n{section_blocks['EVIDENCE']}")
            return "\n\n".join(parts)
