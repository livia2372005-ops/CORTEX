# CORTEX Phase Report — Agent Entry Point (`CORTEX_USAGE.md`)

**Phase**: Agent Entry Point (`CORTEX_USAGE.md`)  
**Date**: 2026-09-02  
**Test Suite Status**: **173 / 173 Passing (100%) across 23 test modules**  

---

## 1. Executive Summary & Objective

In this phase, we established a single, canonical, root-level Agent entry point:

[`CORTEX_USAGE.md`](file:///d:/App/CORTEX/CORTEX_USAGE.md)

When CORTEX is installed into any consuming application workspace, `CORTEX_USAGE.md` serves as the primary document an Agent reads. It provides a concise (102 lines), direct, and action-oriented usage contract that defines the core mental model, workspace documentation boundaries, decision policies, memory workflows, context compilation, and safety invariants without requiring the Agent to explore CORTEX's internal engine implementation.

---

## 2. Problem & Previous Ambiguity

Before this phase:
- Agents joining a consuming workspace containing CORTEX had to discover CORTEX capabilities either through scattered skill definitions or by inspecting CORTEX engine source files.
- Without a top-level root document, Agents were prone to misidentifying CORTEX developer reports (`docs/reports/`) as the consuming application's reporting directory.
- Having multiple independent usage documents created the risk of documentation drift.

---

## 3. Canonical-Source Strategy & File Structure

### Single Canonical Source
- Canonical file: [`d:/App/CORTEX/CORTEX_USAGE.md`](file:///d:/App/CORTEX/CORTEX_USAGE.md) at the repository root.
- Targeted length: 102 lines (within 50–125 line range).
- **Runtime Installation Behavior**: `cortex init` automatically provisions `CORTEX_USAGE.md` at the **root** of the consuming project:

```text
consuming-project/
├── CORTEX_USAGE.md          ← Canonical Agent entry point
├── .cortex/                 ← Local project memory & events
├── .agents/
│   ├── plugins/cortex/      ← Plugin integration & hooks
│   └── hooks.json           ← Lifecycle hook registry
├── src/                     ← Application source (Authoritative)
├── tests/                   ← Application tests (Authoritative)
└── docs/                    ← Application documentation (Authoritative)
    └── reports/             ← Application deliverables (Authoritative)
```

`CORTEX_USAGE.md` is strictly kept at the workspace root and is **never** placed under `docs/` or `docs/reports/` to prevent polluting the consuming application's documentation namespace.

---

## 4. Key Rules & Contracts Established

1. **Mental Model**:
   ```text
   CORTEX = memory + evidence + context + observability substrate
   Agent  = reasoning + planning + decision + implementation + judgment
   ```
2. **Workspace Authority Invariant**:
   - CORTEX is infrastructure for the consuming project.
   - The consuming workspace owns its application source, tests, documentation, and reports.
   - The Agent must never write application reports or design documents into CORTEX developer directories.
3. **Decision Policy**:
   - Use CORTEX when historical or cross-session knowledge is plausibly useful (architectural continuity, constraints, recurring failures, durable lessons).
   - Skip CORTEX on trivial, self-contained edits.
   - Rejects the anti-pattern: `"Always use CORTEX"`.
4. **Retrieved vs Applied vs Not Applied**:
   - *Retrieved*: Returned as candidate evidence.
   - *Applied*: Actually utilized in implementation or validation.
   - *Not Applied*: Reviewed and discarded.
5. **Privacy & Security**:
   - Never persist chain-of-thought, private reasoning, or secret keys.
   - Never scrape conversation transcripts.

---

## 5. Relationship to Specialized Skills

```text
CORTEX_USAGE.md (Root Entry Point & General Protocol)
    ├── cortex-memory (Specialized memory retrieval & queries)
    ├── cortex-review (Specialized claim freshness & evidence verification)
    └── cortex-learning (Specialized durable knowledge promotion)
```

The root entry point points the Agent to specialized skills when deeper operations are required, maintaining a clean single-source hierarchy.

---

## 6. Verification & Test Evidence

A dedicated unit test suite [`tests/test_cortex_usage_entrypoint.py`](file:///d:/App/CORTEX/tests/test_cortex_usage_entrypoint.py) was built and executed:
- `test_canonical_cortex_usage_exists_and_concise`: PASS (102 lines)
- `test_canonical_cortex_usage_content_invariants`: PASS
- `test_cortex_init_installs_cortex_usage_at_workspace_root`: PASS
- `test_cortex_init_idempotency_and_preservation`: PASS

### Full Test Suite Execution
- **Total Test Modules**: 23 modules
- **Test Pass Rate**: **173 / 173 (100% PASS)**
