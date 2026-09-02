# CORTEX Phase Report — General Agent Usage Skill

**Phase**: General Agent Usage Skill (`cortex-usage`)  
**Date**: 2026-09-02  
**Test Suite Status**: **169 / 169 Passing (100%) across 22 test modules**  

---

## 1. Executive Summary & Objective

In this phase, we added a first-class, general-purpose Agent skill ([`.agents/skills/cortex-usage/SKILL.md`](file:///d:/App/CORTEX/.agents/skills/cortex-usage/SKILL.md) and [`.agents/plugins/cortex/skills/cortex-usage/SKILL.md`](file:///d:/App/CORTEX/.agents/plugins/cortex/skills/cortex-usage/SKILL.md)) that teaches coding Agents how to use CORTEX effectively and responsibly in consuming application workspaces.

Instead of requiring Agents to discover CORTEX protocols via trial and error or memorizing internal storage implementation details, `cortex-usage` provides an action-oriented protocol for decision-making, context compilation, retrieval evaluation, knowledge lifecycle, and strict workspace documentation boundaries.

---

## 2. Core Mental Model

```text
CORTEX = memory + evidence + context + observability substrate
Agent  = reasoning + planning + decision + implementation + judgment
```

- **Agency Invariant**: CORTEX is an evidence and storage substrate; the Agent retains 100% authority and responsibility for planning, coding, and decision-making.
- **Data vs Instructions**: Memory records are contextual data/evidence to be critically evaluated, not executable instructions or commands.
- **Code Authority**: Verified current workspace code, tests, and runtime state strictly supersede historical memory assumptions.

---

## 3. Workspace Ownership & Documentation Boundary

The skill explicitly establishes that:
- **CORTEX is infrastructure for the consuming project.**
- The consuming workspace owns its application source code (`src/`, `app/`), tests (`tests/`), documentation (`docs/`), reports (`docs/reports/` or custom reporting paths), and build configurations.
- **Boundary Rule**: The Agent must **never** write application reports, design documents, or task deliverables into CORTEX's internal directories.
- Consuming projects containing their own `docs/` or `docs/reports/` namespaces remain 100% authoritative and unpolluted by CORTEX initialization.

---

## 4. Decision Policy (When to Use vs When NOT to Use)

- **Use CORTEX when**:
  - Resuming work on an established architectural subsystem.
  - Verifying known project constraints, security rules, or cross-session design invariants.
  - Investigating recurring errors to check for prior solutions.
  - Retrieving durable lessons learned from earlier iterations.
- **Do NOT use CORTEX when**:
  - The task is trivial or self-contained (e.g., renaming a local variable, fixing a minor typo).
  - The solution is completely determined by current visible code.
  - Retrieval would introduce irrelevant noise.
- **Explicit Anti-Pattern**: Avoid unconditional "always search memory" mandates.

---

## 5. Canonical Workflow & Applied vs Retrieved Distinction

```text
Task → Historical Context Plausibly Matters? → Search CORTEX → Inspect Candidates → Select Relevant Records → Compile Context → Apply & Verify
```

### Critical Triad:
1. **Retrieved**: Returned as candidate evidence in query results.
2. **Applied**: Actually utilized in reasoning, design, implementation, or testing.
3. **Not Applied**: Evaluated and discarded as outdated, superseded, or irrelevant.

The Agent must never claim a historical record influenced an outcome unless it was actually applied.

---

## 6. TaskAnchors & Privacy Invariants

- **TaskAnchor**: Identifies an explicit engineering task boundary without capturing raw user prompts (stores only deterministic SHA-256 fingerprint `prompt_hash`).
- **Activity Log**: Appends observable tool executions for auditable trajectory tracking; distinct from durable project knowledge.
- **Privacy Rules**: Never persist chain-of-thought, private internal deliberations, hidden system prompts, passwords, or API keys. Never scrape conversation transcripts.

---

## 7. Skill Hierarchy & Relationship to Specialized Skills

```text
cortex-usage (General Entry Point & Decision Protocol)
    ├── cortex-memory (Specialized memory queries & search filters)
    ├── cortex-review (Specialized claim freshness & evidence verification)
    └── cortex-learning (Specialized durable knowledge promotion & candidate review)
```

`cortex-usage` acts as the primary entry point, guiding the Agent on *when* and *how* to engage CORTEX. Specialized skills remain focused on specific operational mechanics without duplicate guidance.

---

## 8. Verification & Test Evidence

A dedicated test suite [`tests/test_cortex_usage_skill.py`](file:///d:/App/CORTEX/tests/test_cortex_usage_skill.py) was added:
- `test_cortex_usage_skill_files_exist`: PASS
- `test_cortex_usage_skill_content_invariants`: PASS
- `test_cortex_init_installs_cortex_usage_skill_and_manifest`: PASS

### Full Test Suite Execution
- **Total Test Modules**: 22 modules
- **Test Pass Rate**: **169 / 169 (100% PASS)**
