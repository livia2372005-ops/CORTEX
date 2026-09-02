# CORTEX Phase Report — Reliable TaskAnchor Propagation Across Antigravity Hook Processes

**Phase**: Reliable TaskAnchor Propagation Fix  
**Date**: 2026-09-02  
**Test Suite Status**: **180 / 180 Passing (100%) across 24 test modules**  

---

## 1. Executive Summary

In consuming workspaces, `task_start` and `task_end` events successfully created and updated `TaskAnchor` entities, but intermediate Antigravity tool actions executed via lifecycle hooks (`PreToolUse`/`PostToolUse`) did not reliably receive the active `anchor_id`.

This phase resolved the root causes across process boundaries, path representations, and multi-key JSON payload variations. All tool telemetry now deterministically attaches the active `anchor_id` across independent Python hook processes, multiple concurrent conversations, and sequential task boundaries.

---

## 2. Problem Diagnosis & Root Cause Analysis

### Observed Failure
When an Agent executed a task:
1. `cortex task start` created an active TaskAnchor in `.cortex/state/anchors.jsonl`.
2. Real Antigravity tool calls (`view_file`, `write_to_file`, `run_command`) triggered the `PreToolUse` and `PostToolUse` hooks.
3. Activity events were appended to `.cortex/events/activity.jsonl` with `anchor_id = null`.
4. `cortex task end` closed the TaskAnchor.

### Rejected Hypotheses
- *Hypothesis 1 (Rejected)*: In-memory state loss. (Anchors were already written to disk JSONL, but hook processes failed during disk lookup).
- *Hypothesis 2 (Rejected)*: Hook failure / unhandled exception. (Hooks were returning `{"decision": "allow"}` successfully).

### Confirmed Root Causes
1. **Workspace Storage Resolution Gap**: When Antigravity executed the hook subprocess, candidate workspace paths were passed in various keys (`workspacePaths`, `workspace_paths`, `workspaceRoot`, `cwd`), and paths often used differing Windows/URI formatting (`d:\App\...` vs `d:/App/...` vs `file:///d:/App/...`). Hook processes could default to `Path.cwd() / ".cortex"`, looking in the IDE directory rather than the project workspace.
2. **Anchor Matching Falsy Conversation Handling**: When CLI `task start` was invoked without an explicit `--conversation` flag, `anchor.conversation_id` was `None`. When Antigravity hook passed its runtime `conversationId`, strict equality `anc.conversation_id == conversation_id` failed and fell back incorrectly if other active anchors existed.
3. **Integer Zero Falsy Evaluation**: In `step_idx = data.get("stepIdx") or data.get("step_index")`, step index `0` was evaluated as falsy in Python (`0 or None` $\rightarrow$ `None`), causing step 0 events to lose their step index.

---

## 3. Architectural & Implementation Changes

### 1. Robust Path Hierarchy Resolution (`cortex_engine.antigravity_hook`)
Implemented `find_cortex_dir` and `resolve_cortex_storage`:
- Climbs the filesystem hierarchy from candidate paths, workspace roots, and tool target file arguments to find the nearest valid `.cortex` directory.
- Implemented `normalize_workspace_path` across `storage.py` and `antigravity_hook.py` to handle forward/backward slashes and `file:///` URI schemes seamlessly on Windows and POSIX.

### 2. Deterministic TaskAnchor Resolution (`cortex_engine.storage.CortexStorage`)
Refactored `get_active_task_anchor(conversation_id, workspace)` with strict priority:
1. **Exact Match**: Match active anchor where `anc.conversation_id == conversation_id` and workspace matches.
2. **Unbound Match**: If no exact conversation match exists, match active anchor in the same workspace that has `anc.conversation_id is None` (e.g. started via CLI `cortex task start`).
3. **Strict Isolation**: If an active anchor is bound to a *different* conversation ID, return `None` rather than cross-contaminating.
4. **No Guessing**: If no active anchor is valid for the workspace, return `None` (`anchor_id = null`).

### 3. Payload Key Extraction & Step 0 Fix
- Iterates over all key variations (`stepIdx`, `step_index`, `stepIndex`, `step_idx`, `step`) checking `is not None` so step `0` is never lost.
- Extracts `tool_name`, `tool_args`, `conversation_id`, and `error` across both camelCase and snake_case formats.

---

## 4. Telemetry Comparison (Before vs. After)

### Before (Broken Propagation)
```json
{"event_id": "act-start-01", "action_type": "task_start", "anchor_id": "task-live-01", "status": "started"}
{"event_id": "act-pre-7d260295", "action_type": "tool_call", "anchor_id": null, "tool_name": "view_file", "status": "started"}
{"event_id": "act-post-4c5ea2ca", "action_type": "tool_result", "anchor_id": null, "tool_name": "view_file", "status": "success"}
{"event_id": "act-end-01", "action_type": "task_end", "anchor_id": "task-live-01", "status": "completed"}
```

### After (Reliable Propagation Across Processes)
```json
{"event_id": "act-start-01", "action_type": "task_start", "anchor_id": "task-smoke-live-02", "status": "started"}
{"event_id": "act-pre-e7edc64c", "action_type": "tool_call", "anchor_id": "task-smoke-live-02", "step_index": 0, "tool_name": "view_file", "correlation_id": "step-conv-live-02-0", "status": "started"}
{"event_id": "act-post-1da6f27c", "action_type": "tool_result", "anchor_id": "task-smoke-live-02", "step_index": 0, "tool_name": "view_file", "correlation_id": "step-conv-live-02-0", "status": "success"}
{"event_id": "act-end-01", "action_type": "task_end", "anchor_id": "task-smoke-live-02", "status": "completed"}
```

---

## 5. Verification & Regression Test Suite

Added dedicated regression suite [`tests/test_task_anchor_propagation_fix.py`](file:///d:/App/CORTEX/tests/test_task_anchor_propagation_fix.py):
1. `test_process_boundary_simulation`: Spawns separate subprocess executing `python -m cortex_engine.antigravity_hook` and asserts `anchor_id` attaches. (PASS)
2. `test_runtime_restart_anchor_persistence`: Recreates storage and API from clean state and asserts active anchor resolves. (PASS)
3. `test_multiple_concurrent_conversations_isolation`: Verifies tasks in `conv-alpha` and `conv-beta` do not cross-pollinate tool events. (PASS)
4. `test_multiple_sequential_tasks_in_one_conversation`: Verifies sequential tasks A and B in the same conversation attach cleanly to active boundaries, with intermediary actions receiving `anchor_id = None`. (PASS)
5. `test_no_active_anchor_leaves_anchor_id_none`: Verifies idle actions record `anchor_id = None` without guessing. (PASS)
6. `test_workspace_isolation_no_cross_association`: Verifies independent workspaces cannot attach each other's anchors. (PASS)
7. `test_end_to_end_complete_trajectory`: Verifies 6-event lifecycle (`task_start` $\rightarrow$ `tool_call` $\rightarrow$ `tool_result` $\rightarrow$ `tool_call` $\rightarrow$ `tool_result` $\rightarrow$ `task_end`) all carry the exact same `anchor_id`. (PASS)

### Full Test Suite
- **Total Test Modules**: 24 modules
- **Test Pass Rate**: **180 / 180 (100% PASS)**

---

## 6. Historical Data Notes

- **Bootstrap Contamination (`task-bf2fba1e`)**: A previous runtime bootstrap task executed under anchor `task-bf2fba1e`. In accordance with CORTEX invariants, its historical activity records are preserved in the raw activity log, but `task-bf2fba1e` is classified as bootstrap infrastructure validation and is excluded from benchmark measurements.
- **Task 01 Telemetry Classification**: Historical Task 01 activity lacking `anchor_id` is classified as *unresolved / incomplete telemetry*. No historical records have been retroactively modified or fabricated.

---

## 7. Known Limitations

- **Lifecycle Hook Scope**: Only Antigravity tool calls executed through configured lifecycle hooks (`PreToolUse`/`PostToolUse`) or explicit `record_activity` API calls are recorded. Uninstrumented OS processes executed directly outside the agent environment are not captured.
- **Prompt Hash Proof**: The SHA-256 `prompt_hash` provides cryptographic proof that the identical normalized prompt was supplied; it does not reconstruct semantic intent.
