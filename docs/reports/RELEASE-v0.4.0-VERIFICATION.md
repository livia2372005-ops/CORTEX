# CORTEX v0.4.0 Remote Release Verification Report

**Release**: CORTEX v0.4.0 — Cortex Interaction Trace  
**Release Type**: Minor Release  
**Date**: 2026-09-03  
**Repository**: `https://github.com/livia2372005-ops/CORTEX.git`  
**Publication Status**: **Published on GitHub**  

---

## 1. Release Identification & Git Lineage

| Parameter | Value | Status |
| :--- | :--- | :--- |
| **Previous Version** | `v0.3.1` (`e2302c7b463f51cfd82fed377d0c1184e5406157`) | Established |
| **New Version** | `v0.4.0` | **Verified** |
| **Release Commit SHA** | `1293a95932005556db21e0252c76f15a4012bbed` | **Verified** |
| **Annotated Tag Object SHA** | `9d440db30e0d3d1bf977671ae47f4d64df6b4685` | **Verified** |
| **Peeled Tag Target Commit** | `1293a95932005556db21e0252c76f15a4012bbed` | **Matches HEAD** |
| **Schema Version** | `1.0.0` (Backward-compatible additions; no breaking schema change) | **Preserved** |
| **GitHub Release URL** | `https://github.com/livia2372005-ops/CORTEX/releases/tag/v0.4.0` | **Published** |

---

## 2. Remote State Verification

Remote reference verification executed via `git ls-remote origin`:
```text
1293a95932005556db21e0252c76f15a4012bbed	HEAD
1293a95932005556db21e0252c76f15a4012bbed	refs/heads/master
9d440db30e0d3d1bf977671ae47f4d64df6b4685	refs/tags/v0.4.0
1293a95932005556db21e0252c76f15a4012bbed	refs/tags/v0.4.0^{}
```

The remote `master` branch and annotated tag `v0.4.0` point to the exact release commit `1293a95932005556db21e0252c76f15a4012bbed`.

---

## 3. Test Suite & Verification Results

### Comprehensive Regression Test Suite
- **Total Test Modules**: 25 modules
- **Total Tests Executed**: 188 tests
- **Result**: **188 / 188 PASS (100% PASS, 0 failures, 0 errors in 131.958s)**

### Core Verification Dimensions Tested
1. **Interaction Trace Classification** (`tests/test_cortex_interaction_trace.py`):
   - Deterministic categorization of operations into `activity_domain` (`cortex`, `external_tool`, `system`) and `interaction_class` (`agent_memory`, `task_boundary`, `maintenance`).
   - Core API auto-capture without manual secondary logging.
   - MCP/API single-trace de-duplication (`_in_mcp_call` context flag).
   - TaskAnchor propagation across CORTEX interactions.
   - Centralized pre-persistence redaction of sensitive query parameters.
   - Metrics-friendly metadata recording across search, get, compile_context, and knowledge lifecycle ops.
   - Full backward compatibility for legacy ActivityEvents lacking new fields.
   - CLI trace filtering (`--cortex`, `--agent-memory`, `--maintenance`, `--json`).
2. **TaskAnchor Propagation Across Processes** (`tests/test_task_anchor_propagation_fix.py`):
   - Process boundary simulation, restart persistence, conversation isolation, sequential tasks, and full trajectories.
3. **Packaging Boundaries** (`tests/test_packaging_boundaries.py`):
   - Injected awareness rule invariants, idempotent initialization, and isolation from developer docs/reports.
4. **Context Isolation & Retrieval Router** (`tests/test_router_phase14.py`, `tests/test_vertical_slice.py`):
   - Hybrid retrieval Pareto benchmarks, role isolation contracts, and deterministic context packaging.

---

## 4. Clean-Clone Verification

An isolated trial was executed cloning directly from GitHub:
```bash
git clone --branch v0.4.0 --single-branch https://github.com/livia2372005-ops/CORTEX.git <clean-dir>
```
Verification findings:
- **Cloned Commit SHA**: `1293a95932005556db21e0252c76f15a4012bbed`
- **Checked-out Tag**: `v0.4.0`
- **Working Tree**: Completely clean (0 uncommitted or untracked files)
- **Version Reporting**:
  - `python -m cortex_engine.cli --version` $\rightarrow$ `CORTEX v0.4.0 (schema v1.0.0)`
  - `plugin.json` $\rightarrow$ `"version": "0.4.0"`, `"schema_version": "1.0.0"`
- **Clean Clone Unit Tests**: Executed `test_cortex_interaction_trace.py` and `test_packaging_boundaries.py` $\rightarrow$ **12 / 12 PASS**.

---

## 5. Clean Consuming Workspace Verification

A fresh consuming application workspace (`sample-app/`) was initialized using the clean clone CLI:
```bash
python -m cortex_engine.cli --workspace <sample-app> init
```

### Workspace Structure Invariants
```text
sample-app/
├── CORTEX_USAGE.md                 # Root Agent entry point installed
├── .agents/
│   └── plugins/
│       └── cortex/
│           ├── plugin.json         # v0.4.0 plugin manifest
│           ├── hooks.json          # Antigravity lifecycle hooks
│           └── rules/
│               └── cortex-awareness.md
├── .cortex/                        # Runtime storage initialized clean
├── src/
│   └── main.py                     # Unaltered application source
├── tests/
│   └── test_main.py                # Unaltered application tests
└── docs/
    └── user_guide.md               # Unaltered application documentation
```

### Invariant Checks
- **Application docs untouched**: `docs/user_guide.md` was preserved intact.
- **Zero developer report pollution**: No `docs/reports/` directory was created or copied into `sample-app/`.
- **Root Entry Point**: `CORTEX_USAGE.md` installed at root, containing the 113-line concise Agent contract.

---

## 6. Real Cortex Interaction Trace Smoke Test

In the clean consuming workspace, a real multi-step task was executed through the native API/MCP substrate:
1. **TaskAnchor Started**: `Refactor Payment Service` (`aid = task-f4279346`, conversation: `conv-release-smoke-40`).
2. **Record Knowledge**: `DEC-PAY-01` (`"Use Stripe idempotent tokens with 5m TTL"`).
3. **Search Memory**: `query="Stripe idempotent tokens"` (returned candidate `DEC-PAY-01` via `policy_d_hybrid_expand_fallback`).
4. **Get Record**: `id="DEC-PAY-01"` (returned `found: True`).
5. **Compile Context**: `task="Payment idempotency token caching"` (compiled 408 characters, token estimate `~102 tokens`).
6. **TaskAnchor Ended**: Status `completed`.

### Raw Telemetry Verification (`.cortex/events/activity.jsonl`)
The resulting log contained **exactly 6 events**:
```text
- Event 0: action=task_start, domain=cortex, class=task_boundary, anchor=task-f4279346
- Event 1: action=tool_call,  domain=cortex, class=agent_memory,  anchor=task-f4279346, tool=cortex_record_knowledge
- Event 2: action=tool_call,  domain=cortex, class=agent_memory,  anchor=task-f4279346, tool=cortex_search
- Event 3: action=tool_call,  domain=cortex, class=agent_memory,  anchor=task-f4279346, tool=cortex_get
- Event 4: action=tool_call,  domain=cortex, class=agent_memory,  anchor=task-f4279346, tool=cortex_compile_context
- Event 5: action=task_end,   domain=cortex, class=task_boundary, anchor=task-f4279346
```
- **Single-trace de-duplication**: No double-counting; exactly 1 event per operation.
- **Domain & Class**: All events had `activity_domain = "cortex"`; memory ops had `interaction_class = "agent_memory"`; task boundaries had `interaction_class = "task_boundary"`.
- **Anchor Attachment**: All 6 events carried `anchor_id = "task-f4279346"`.
- **Structured Metadata**: Candidate counts, retrieval status, and token estimates were accurately captured and unredacted.

---

## 7. CLI Verification

Verified all filtering and inspection modes on the consuming workspace:

### A. All CORTEX Interactions (`cortex activity --cortex`)
```text
=== CORTEX Interaction Trace (6 events) ===
[TASK START] Refactor Payment Service (anchor: task-f4279346)
  ↓
[CORTEX RECORD] record: DEC-PAY-01 (type: decision) (7.17ms)
  ↓
[CORTEX SEARCH] query: "Stripe idempotent tokens" | 1 candidates (policy_d_hybrid_expand_fallback) (10.41ms)
  ↓
[CORTEX GET] record: DEC-PAY-01 (found: True) (0.26ms)
  ↓
[CORTEX COMPILE] task: "Payment idempotency token caching" | 1 records (~102 tokens) (0.37ms)
  ↓
[TASK END] status: completed (anchor: task-f4279346)
=== End of CORTEX Interaction Trace ===
```

### B. Filter by TaskAnchor (`cortex activity --cortex --task task-f4279346`)
Renders the complete 6-event flow specifically bounded to `task-f4279346`.

### C. Filter by Interaction Class (`cortex activity --cortex --agent-memory`)
```text
=== CORTEX Interaction Trace (4 events) for agent_memory only ===
[CORTEX RECORD] record: DEC-PAY-01 (type: decision) (7.17ms)
  ↓
[CORTEX SEARCH] query: "Stripe idempotent tokens" | 1 candidates (policy_d_hybrid_expand_fallback) (10.41ms)
  ↓
[CORTEX GET] record: DEC-PAY-01 (found: True) (0.26ms)
  ↓
[CORTEX COMPILE] task: "Payment idempotency token caching" | 1 records (~102 tokens) (0.37ms)
=== End of CORTEX Interaction Trace ===
```
*Notice: Task start and end boundaries are cleanly excluded.*

### D. Filter Maintenance (`cortex activity --cortex --maintenance`)
```text
=== CORTEX Interaction Trace (0 events) for maintenance only ===
No CORTEX interaction records found.
=== End of CORTEX Interaction Trace ===
```

### E. Machine-Readable JSON (`cortex activity --cortex --json`)
Outputs valid JSON array of 6 activity event dictionaries, verifying programmatic consumption capability.

---

## 8. Security, Privacy & Data-Minimization Audit

- **Tracked Files Clean**: No `.env`, secret tokens, credentials, or private keys exist in the repository tree.
- **Pre-Persistence Scrubbing**: `redact_data` sanitizes input parameters before activity events are appended to disk.
- **Exclusion of Sensitive Internal Deliberations**: Raw user prompts, hidden instructions, conversation transcripts, and private reasoning (chain-of-thought) are strictly excluded from logging.
- **Data Minimization**:
  - Search queries and compile task strings are bounded in length.
  - Only structured summary metrics (counts, record IDs, duration) are persisted rather than raw model context dumps.
  - Explicit metrics (`token_estimate`, `total_tokens_estimate`) are preserved via `SAFE_METRIC_KEYS` without exposing auth tokens.

---

## 9. Evidence Classification

### Directly Verified (Observed during this release process)
- Local and remote version bumped to `0.4.0` across package, CLI, MCP server metadata, and plugin manifest.
- Complete unit test suite: **188 / 188 PASS** across 25 modules in 131.96s.
- Release commit `1293a95932005556db21e0252c76f15a4012bbed` pushed to remote `master`.
- Annotated tag `v0.4.0` (`9d440db30e0d3d1bf977671ae47f4d64df6b4685`) pushed to remote and verified via `git ls-remote`.
- GitHub Release published at `https://github.com/livia2372005-ops/CORTEX/releases/tag/v0.4.0`.
- Clean-clone test execution from remote at tag `v0.4.0` passing 100%.
- Consuming workspace initialization invariant verification (`sample-app/`).
- Real consuming workspace smoke test demonstrating exact 6-event CORTEX interaction trace with correct metadata and CLI rendering.

### Previously Established (Inherited from earlier releases/phases)
- Clean Runtime Packaging separation (`cortex init` provisions only runtime assets).
- Cross-process TaskAnchor resolution and path normalization.
- Hybrid Retrieval router policies (Policy D Lexical Expansion + Semantic Fallback).
- Context Compiler role isolation contracts (`APP`, `MEMORY`, `REVIEW`, `LEARNING`).
- Invariant that historical Activity records are never retroactively rewritten.

---

## 10. Known Limitations

- **Interaction Trace Boundary**: The interaction trace provides objective evidence of observable CORTEX operations performed during a task. It does not prove cognitive causality (whether retrieved memory caused a specific implementation decision).
- **Scope of Telemetry**: Unhooked OS commands executed outside Antigravity or direct CORTEX APIs are not tracked.
- **Unbounded Operations**: Operations executed without an active TaskAnchor carry `anchor_id = null`. CORTEX intentionally avoids guessing task associations.
