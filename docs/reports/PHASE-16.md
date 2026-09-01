# CORTEX Development Report — Phase 16

## 1. Objective
- [VERIFIED] **Goal**: Design and implement the memory lifecycle and promotion layer for CORTEX. Establish a clear boundary where raw observable events remain append-only, candidate memories are deterministically identified from patterns, and persistent knowledge is created strictly under explicit Agent judgment and authority.

## 2. Lifecycle Model
- [IMPLEMENTED] The four-stage lifecycle model:
```text
OBSERVABLE EVENT (Raw append-only event stream)
      ↓
MEMORY CANDIDATE (Identified via deterministic signal rules)
      ↓
AGENT JUDGMENT (Agent evaluates significance)
      ↓
PERSISTENT KNOWLEDGE (Promoted canonical knowledge record)
```
- [VERIFIED] Raw events are never deleted or rewritten during candidate creation, promotion, supersession, or archival.

## 3. Candidate Memory
- [IMPLEMENTED] Structured candidate schema (`MemoryCandidate`):
```json
{
  "id": "cand-dec-a1b2c3d4",
  "event_ids": ["evt-100", "evt-101"],
  "candidate_type": "decision",
  "summary": "Reject Redis; Use Stateless JWTs",
  "reason": "architectural_decision_signal",
  "evidence": [{"event_id": "evt-100", "type": "architecture_decision"}],
  "suggested_title": "Stateless JWT Authentication",
  "suggested_content": "Reject Redis sessions in favor of stateless JWT tokens."
}
```

## 4. Promotion Signals
- [IMPLEMENTED] Deterministic, rule-based signal detectors:
  1. **Trivial Events**: Filtered out (`file_opened`, `file_read`, `grep_executed`, `test_passed`, `formatting_changed`, `variable_renamed`, `linter_run`, `tool_invoked`).
  2. **Architectural Decisions**: Events with type `architecture_decision` or payload containing `decision`/`architectural_choice` $\rightarrow$ candidate of type `decision`.
  3. **New Invariants / Constraints**: Events with type `constraint_added` or payload containing `invariant`/`security_boundary` $\rightarrow$ candidate of type `constraint`.
  4. **Incident Postmortems / Lessons**: Events with type `incident_postmortem` or `lesson_learned` $\rightarrow$ candidate of type `lesson`.
  5. **Repeated Failures**: Error clustering on content words with stopword filtering; 2+ occurrences $\rightarrow$ candidate of type `failure`.

## 5. Promotion API
- [IMPLEMENTED] Explicit promotion endpoints across Python API, CLI, and MCP:
  - `cortex.promote_candidate(...)`: Promotes a candidate identified from events.
  - `cortex.promote_memory(event_ids, ...)` / `cortex.record_knowledge(...)`: Direct promotion upon explicit Agent command.
  - Exposes `cortex_detect_candidates` and `cortex_promote_memory` MCP tools.
- [VERIFIED] CORTEX never auto-promotes records without explicit Agent command or configured policy.

## 6. Provenance
- [IMPLEMENTED] Promoted knowledge records retain direct links to source event IDs via `derived_from: ["evt-100", "evt-101"]` and structured `provenance` metadata.
- [VERIFIED] Provenance remains traceable from knowledge back to disk events and commits.

## 7. Status Lifecycle
- [IMPLEMENTED] Knowledge status lifecycle:
  - `candidate`: In-memory candidate awaiting promotion.
  - `active`: Normal active engineering knowledge.
  - `superseded`: Historical knowledge replaced by newer decisions.
  - `affected`: Knowledge or claims flagged due to artifact modification/invalidation.
  - `archived`: Logically retired knowledge retained for historical auditing.

## 8. Supersession
- [IMPLEMENTED] Non-destructive supersession:
  - When new knowledge specifies `supersedes: "DEC-009"`, the old record's status is updated to `superseded` and `provenance.superseded_by = "DEC-017"`.
  - The superseded canonical file is never deleted.

## 9. Duplicate Handling
- [IMPLEMENTED] Non-destructive duplicate detection (`detect_duplicates`):
  - Computes harmonic token overlap (Jaccard + containment) against active records.
  - Returns similarity scores and match types (`exact_or_near_duplicate`, `high_conceptual_similarity`).
  - [VERIFIED] Identified duplicates are reported to the Agent for inspection; records are never automatically merged or overwritten.

## 10. Retrieval Interaction
- [VERIFIED] Search queries return canonical records with their active lifecycle `status` intact (`active`, `superseded`, `affected`, `archived`).
- [VERIFIED] Historical and superseded records remain searchable rather than silently suppressed.

## 11. Context Compiler Interaction
- [VERIFIED] ContextCompiler formats status markers:
  - `- **DEC-030** [ACTIVE]: Postgres Relational DB`
  - `- **DEC-010** [SUPERSEDED]: MySQL Relational DB`
- [VERIFIED] Prompts and budget management prioritize active knowledge while maintaining transparent status visibility.

## 12. Raw Event Preservation
- [VERIFIED] Appending events, promoting candidates, modifying statuses, superseding, or archiving records never modifies or removes previous entries in `.cortex/events/events.jsonl`. Raw event history remains strictly append-only.

## 13. Real Agent Experiment
- [REAL AGENT / OBSERVED] Evaluated natural Agent behavior across unprompted engineering tasks:
  - In normal editing tasks (e.g. refactoring helper functions), the Agent generated routine observable events (`file_opened`, `grep_executed`, `test_passed`) without polluting persistent knowledge.
  - When encountering architectural changes, the Agent executed explicit `cortex_record_knowledge` / `promote` calls with full event provenance.
- [OBSERVED] Natural promotion rate matches engineering intent: durable memory grows selectively while raw operational logs remain high-volume.

## 14. Event Volume Baseline
- [MEASURED] Evaluated a synthetic event stream with 100 trivial events + 20 meaningful events:
  - Total Raw Events: `120`
  - Detected Candidates: `12` (10 decisions + 2 failure clusters)
  - Promoted Knowledge Records: `5`
  - Promotion Ratio: `4.17%` (5 / 120)
  - [VERIFIED] Durable knowledge is $>20\times$ more compact than raw history, eliminating context bloat while preserving historical completeness.

## 15. Tests
- [VERIFIED] All 122 tests across 16 test suites pass with 100% success rate:
  - `test_trivial_event_remains_event`: PASS
  - `test_explicit_memory_request_creates_knowledge`: PASS
  - `test_candidate_creation_and_promotion`: PASS
  - `test_repeated_failure_pattern_candidate`: PASS
  - `test_duplicate_knowledge_detection_without_destructive_merge`: PASS
  - `test_supersession_lifecycle`: PASS
  - `test_archival_lifecycle`: PASS
  - `test_retrieval_respects_lifecycle_status`: PASS
  - `test_context_compiler_respects_lifecycle_status`: PASS
  - `test_raw_event_history_preservation`: PASS
  - `test_event_volume_baseline_ratio`: PASS
  - All regression suites (Phases 1–15): PASS

## 16. Failures / Surprises
- [OBSERVED] Naive error message tokenization clustered distinct errors when both contained common developer words (`during`, `execution`, `error`). Adding a generic stopword filter resolved pattern grouping.
- [OBSERVED] Short titles in duplicate detection benefited from combining Jaccard and containment metrics.

## 17. What Was NOT Implemented
- [DEFERRED] Autonomous background LLM agents that summarize or delete memories without user consent.
- [DEFERRED] Destructive automatic record merging or fuzzy deduplication deletion.
- [DEFERRED] Complex graph databases for event-to-knowledge traces.

## 18. Evidence
- Full Test Discovery Output:
```text
Ran 122 tests in 147.077s
OK
```
- CLI Command Diagnostic:
```text
--- Detected Memory Candidates (2) ---
[cand-dec-1] (DECISION) Reason: architectural_decision_signal
  Summary: Repository pattern decoupling
  Events:  evt-1
```

## 19. Limitations
- [ASSUMED] Error pattern clustering operates on lexical token overlap and does not perform deep stack trace AST parsing.

## 20. Recommended Next Step
- Finalize production release v0.1.0 with comprehensive documentation and user guides.
