# CORTEX Phase Report — Clean Runtime Packaging & Task Boundary Observability

**Phase**: Clean Runtime Packaging + Task Boundary Observability  
**Date**: 2026-09-02  
**Test Suite Status**: **166 / 166 Passing (100%) across 21 test modules**  

---

## 1. Executive Summary

This phase accomplishes two key objectives:
1. **Clean Runtime Packaging**: Explicitly separates the CORTEX developer repository (source, tests, benchmarks, internal engineering reports) from the runtime integration installed into consuming application workspaces. CORTEX initialization never pollutes or touches application documentation or creates `docs/reports/` in consuming projects.
2. **Task Boundary / Activity Anchors**: Establishes first-class `TaskAnchor` entities and lifecycle APIs (`start_task`, `end_task`, CLI `cortex task`, MCP `cortex_start_task` / `cortex_end_task`) that bind multi-step tool trajectories to distinct engineering tasks using deterministic prompt fingerprints, without parsing conversation transcripts, storing raw private prompts by default, or requiring Agent self-reporting.

---

## 2. Repository Classification & Boundaries Audit

| Directory / File | Category | In Consuming Workspace Runtime? | Description / Boundary Rule |
| :--- | :--- | :--- | :--- |
| `cortex_engine/` | **Runtime** | Yes (via package / Python path) | Core engine, storage, indexer, API, CLI, hooks, and MCP server. |
| `.agents/plugins/cortex/` | **Plugin Integration** | Yes (installed into workspace) | Plugin manifest, MCP config, hooks, skills, and awareness rules. |
| `.agents/hooks.json` | **Plugin Integration** | Yes (installed into workspace) | Workspace root hook declaration for tool observability. |
| `.cortex/` | **Runtime State** | Yes (local project storage) | Canonical knowledge, events, state, and derived SQLite indexes. |
| `docs/reports/` | **Developer / Historical** | **NO (Isolated to Dev Repo)** | CORTEX phase reports and release reports. Must NEVER be copied to user projects. |
| `docs/architecture.md`, etc. | **Developer Documentation**| **NO (Isolated to Dev Repo)** | Developer documentation for CORTEX maintainers. |
| `tests/` | **Tests** | **NO (Isolated to Dev Repo)** | Comprehensive unit and benchmark test suites. |
| `benchmark_datasets/` | **Experimental / Benchmarks** | **NO (Isolated to Dev Repo)** | Retrieval datasets for offline Pareto validation. |
| `CHANGELOG.md`, `README.md` | **Release Metadata** | CORTEX Repo Only | Repository documentation. |

---

## 3. Runtime vs Developer Structure & `cortex init`

### The Problem
Previously, when users cloned or initialized CORTEX inside an application workspace, an Agent could confuse CORTEX's internal `docs/reports/` with the application's documentation directory, creating application reports inside CORTEX's internal report directory.

### The Solution: Explicit Project Authority Boundary
- **Consuming Application Authority**: The consuming workspace remains 100% authoritative for its own source code, documentation, tests, and reports.
- **`cortex init` Invariant**: `cortex init` provisions only:
  - `.cortex/` (`knowledge/`, `events/`, `state/`, `indexes/`)
  - `.agents/plugins/cortex/` (`plugin.json`, `mcp_config.json`, `hooks.json`, `rules/cortex-awareness.md`, `skills/`)
  - `.agents/hooks.json`
- **Zero Pollution**: `cortex init` never creates `docs/reports/` or touches existing files in the consuming workspace's `docs/` folder.
- **Injected Awareness Rule**: Explicitly informs the Agent:
  > *"CORTEX integration is infrastructure for the current project. The current application workspace remains authoritative for application source, documentation, tests, and reports. Never write application reports into CORTEX's internal directories."*

---

## 4. Task Boundary & TaskAnchor Schema

### TaskAnchor Model (`cortex_engine/models.py`)
```python
@dataclass
class TaskAnchor:
    anchor_id: str
    conversation_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    status: str = "active"  # active, completed, failed, aborted
    workspace: str = ""
    source: str = "api"     # api, cli, mcp, hook, system
    task_label: Optional[str] = None
    prompt_hash: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0.0"
```

### Storage Location
Task anchors are stored in `.cortex/state/anchors.jsonl` (append/update model with deduplication on read).

---

## 5. Prompt Fingerprint Semantics vs Raw Prompt Capture

### What Antigravity Exposes vs Does Not Expose
- **Exposed by Lifecycle Hooks**: `toolCall.name`, `toolCall.args`, `stepIdx`, `conversationId`, `workspacePaths`, execution status, error payloads.
- **NOT Exposed by Lifecycle Hooks**: The raw user prompt is not directly present in `PreToolUse` or `PostToolUse` event payloads.
- **Platform Invariant**: CORTEX **does NOT parse `transcriptPath`**, does NOT scrape conversation transcripts, and does NOT capture private reasoning traces.

### Deterministic Fingerprinting
When a user prompt is explicitly provided to `start_task(...)`:
1. It is sanitized via `cortex_engine.redaction`.
2. It is deterministically normalized (`normalize_prompt`: strip, collapse whitespace, lowercase).
3. A SHA-256 hash is computed (`compute_prompt_hash`).
4. **Only the hash is persisted** (`prompt_hash`). The raw prompt is **NEVER** stored by default.

This enables cryptographic proof that two task executions correspond to the same user intent without retaining private prompt contents in project memory.

---

## 6. Activity Propagation & Trajectory Correlation

When tools execute, the Antigravity hook handler (`cortex_engine.antigravity_hook`):
1. Resolves the currently active `TaskAnchor` for the matching `conversation_id`.
2. Sets `act_event.anchor_id = active_anchor.anchor_id` and `act_event.task_id = active_anchor.anchor_id`.
3. Records `tool_call` and `tool_result` events tied directly to the task anchor.

### Trajectory Example
```text
TaskAnchor: task-01 (Label: "DB Connection Pool Retry", Hash: e165857...)
├── [task_start]   status: started (anchor: task-01)
├── [step 1] [tool_call]   run_command (CommandLine: pytest tests/) (anchor: task-01)
├── [step 1] [tool_result] run_command (status: success, duration: 420ms) (anchor: task-01)
├── [step 2] [tool_call]   write_to_file (Target: src/db.py) (anchor: task-01)
├── [step 2] [tool_result] write_to_file (status: success, duration: 35ms) (anchor: task-01)
└── [task_end]     status: completed (anchor: task-01)
```

---

## 7. CLI and MCP Surface

### CLI Task Commands
- `cortex task start [--label <label>] [--prompt <prompt>] [--conversation <id>] [--id <id>]`
- `cortex task end <anchor_id> [--status <status>]`
- `cortex task list [--conversation <id>] [--status <status>]`
- `cortex task get <anchor_id>`
- `cortex activity --task <anchor_id>` (or `--anchor <id>`)
- `cortex activity --task <anchor_id> --json`

### MCP Tools Added
- `cortex_start_task`
- `cortex_end_task`
- `cortex_get_task`
- `cortex_list_tasks`

---

## 8. Migration & Backward Compatibility

- **Historical Events**: Existing `ActivityEvent` records without `anchor_id` deserialize cleanly with `anchor_id=None`.
- **Query Flexibility**: `cortex activity --task <id>` filters against both `anchor_id` and legacy `task_id` interchangeably.
- **Non-Destructive Storage**: No legacy activity log files are rewritten or mutated.

---

## 9. Verification & Test Evidence

### New Test Suites
1. [`tests/test_packaging_boundaries.py`](file:///d:/App/CORTEX/tests/test_packaging_boundaries.py):
   - `test_cortex_init_does_not_create_reports_or_pollute_app_docs`: PASS
   - `test_awareness_rule_declares_workspace_authority_and_doc_boundary`: PASS
   - `test_cortex_init_is_idempotent_and_preserves_user_files`: PASS
   - `test_clean_runtime_mode_independent_of_dev_repo`: PASS
2. [`tests/test_task_anchors.py`](file:///d:/App/CORTEX/tests/test_task_anchors.py):
   - `test_prompt_normalization_and_deterministic_hashing`: PASS
   - `test_task_start_and_end_lifecycle`: PASS
   - `test_active_anchor_resolution_and_hook_propagation`: PASS
   - `test_multiple_tasks_in_one_conversation`: PASS
   - `test_restart_persistence`: PASS
   - `test_backward_compatibility_with_missing_anchor_id`: PASS
   - `test_cli_task_and_activity_commands`: PASS
   - `test_mcp_task_tools`: PASS

### Full Test Suite Execution
```text
Ran 166 tests in 125.953s
OK (166 / 166 PASS across 21 test modules)
```
