# CORTEX Phase Report — Agent Action Observability

## 1. Implementation Summary

This phase introduces a first-class **Agent Action Observability / Activity Log** subsystem into CORTEX. It enables empirical, deterministic tracking of what the Agent actually does during engineering tasks—such as tool calls, shell command executions, file modifications, git operations, and CORTEX interactions—**without requiring the Agent to manually write self-reported narratives**.

Crucially, the activity log captures **observable external actions only** and strictly does **NOT** capture or reconstruct private reasoning, internal chain-of-thought (CoT), or hidden prompt deliberations.

---

## 2. Architecture & Design Principles

```text
┌────────────────────────────────────────────────────────────┐
│                    AGENT ACTION STREAM                     │
│  (MCP tool calls, CLI runs, shell commands, file changes)  │
└──────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│                 CENTRALIZED REDACTION LAYER                │
│   (Patterns: PATs, OpenAI/AWS keys, Bearer tokens, PEMs)   │
└──────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│                  CANONICAL ACTIVITY LOG                    │
│           .cortex/events/activity.jsonl (Append-Only)      │
│  - Separate from Knowledge & Claims                        │
│  - Single source of truth (Disks/JSONL, not DB/FTS)        │
│  - No auto-promotion to persistent memory                  │
└────────────────────────────────────────────────────────────┘
```

### Core Invariants Preserved
1. **ONE Agent Responsibility**: The Agent owns reasoning, planning, implementation, and judgment. CORTEX provides the observable activity and memory substrate.
2. **Canonical Append-Only Storage**: All activity events are recorded in `.cortex/events/activity.jsonl`. No destructive history rewriting.
3. **Strict Separation from Knowledge**: Activity logs are **NOT** knowledge records and are never returned in default `cortex.search` knowledge queries. The promotion path remains explicit: `Event → Candidate → Agent Judgment → Persistent Knowledge`.
4. **Zero CoT / Zero Private Reasoning**: Only observable actions (`target`, `action_type`, `status`, `duration_ms`, sanitized `metadata`) are captured.

---

## 3. Canonical Activity Event Schema

Versioned canonical contract (`ActivityEvent` with schema v1.0.0):

| Field | Type | Description |
| :--- | :--- | :--- |
| `event_id` | `str` | Unique canonical event identifier (e.g. `act-0ca9dbeae1`) |
| `timestamp` | `str` | ISO-8601 UTC timestamp |
| `session_id` | `Optional[str]` | Optional session correlation identifier |
| `task_id` | `Optional[str]` | Optional task correlation identifier |
| `actor` | `str` | Active actor (`agent`, `system`, `user`) |
| `action_type` | `str` | Action category (see table below) |
| `source` | `str` | Ingress channel (`mcp`, `cli`, `api`, `agent_hook`) |
| `target` | `str` | Resource or operation target (e.g., `pytest tests/`, `cortex_search`) |
| `status` | `str` | Execution status (`success`, `error`, `pending`, `interrupted`) |
| `duration_ms` | `Optional[float]` | Measured duration in milliseconds |
| `metadata` | `dict[str, Any]` | Sanitized structured operation metadata (e.g. exit code, byte count) |
| `error_type` | `Optional[str]` | Sanitized error classification if status is `error` |
| `schema_version`| `str` | Schema version (`1.0.0`) |

### Supported Observable Action Types
- `tool_call`: MCP or external tool invocation
- `tool_result`: Tool completion result
- `command_exec`: Shell / terminal command execution
- `file_read`: File read operation
- `file_write`: File write or creation operation
- `file_delete`: File deletion operation
- `git_action`: Version control commit, push, or branch operation
- `cortex_action`: Internal CORTEX memory or indexing operation
- `task_start`: Task initiation lifecycle marker
- `task_end`: Task completion lifecycle marker
- `error`: Uncaught runtime error

---

## 4. Automatic vs. Manual Capture

### Automatic MCP Tool Instrumentation
When any tool is invoked via the CORTEX MCP server (`cortex_engine/mcp_server.py`), the request is automatically wrapped:
- Execution time is measured with high precision (`time.perf_counter()`).
- An `ActivityEvent` with `action_type="tool_call"`, `source="mcp"`, `target=<tool_name>`, `duration_ms`, `status="success"|"error"`, and sanitized input keys is recorded to `.cortex/events/activity.jsonl`.
- `cortex_list_activity` calls are exempted from self-logging to prevent recursive log explosion.

### Explicit API & Tool Capture
- **Python API**: `cortex.record_activity(action_type=..., target=..., status=..., task_id=..., metadata=...)`
- **MCP Tool**: `cortex_record_activity` (allows recording external shell executions, file updates, and test runs)
- **MCP Query Tool**: `cortex_list_activity` (query activity events with task/session/type/status filtering)

---

## 5. Security & Redaction Layer

Centralized redaction in `cortex_engine/redaction.py` ensures that sensitive values never reach disk:
- **GitHub PATs** (`ghp_...`, `github_pat_...`) $\rightarrow$ `[REDACTED]`
- **AI Keys** (`sk-...`) $\rightarrow$ `[REDACTED]`
- **AWS Keys** (`AKIA...`) $\rightarrow$ `[REDACTED]`
- **Bearer Tokens** (`Bearer ...`) $\rightarrow$ `Bearer [REDACTED]`
- **Private Keys** (`-----BEGIN ... PRIVATE KEY-----`) $\rightarrow$ `[REDACTED]`
- **Password / Key Assignments** (`password=...`, `token=...`) $\rightarrow$ `[REDACTED]`
- Recursive traversal of all dictionaries, lists, and string fields.

---

## 6. CLI Inspection Capability

Added `cortex activity` subcommand to inspect activity directly from the terminal:

```bash
# Formatted activity log
cortex activity --last 10

# Filtered by task
cortex activity --task task-001

# Filtered by action type
cortex activity --type command_exec

# Output machine-readable JSON
cortex activity --task task-001 --json
```

---

## 7. Sample Canonical Activity Events

### Raw JSONL Record
```json
{"event_id": "act-0ca9dbeae1", "timestamp": "2026-09-02T05:15:50.431773+00:00", "task_id": "task-smoke-01", "actor": "agent", "action_type": "command_exec", "source": "api", "target": "pytest tests/", "status": "success", "duration_ms": 250.0, "metadata": {"exit_code": 0, "tests_run": 146}, "schema_version": "1.0.0"}
{"event_id": "act-4d16378bff", "timestamp": "2026-09-02T05:15:50.433312+00:00", "task_id": "task-smoke-01", "actor": "agent", "action_type": "tool_call", "source": "api", "target": "cortex_search", "status": "success", "duration_ms": 15.4, "metadata": {"query": "sqlite fts"}, "schema_version": "1.0.0"}
```

### Formatted CLI Output
```text
--- Recent Agent Activity (2 events) ---
2026-09-02T05:15:50.431773+00:00 [SUCCESS] command_exec   via api  target: pytest tests/ (250.0ms)
   meta: {"exit_code": 0, "tests_run": 146}
2026-09-02T05:15:50.433312+00:00 [SUCCESS] tool_call      via api  target: cortex_search (15.4ms)
   meta: {"query": "sqlite fts"}
```

---

## 8. Files Changed

| File | Change Type | Description |
| :--- | :--- | :--- |
| `cortex_engine/redaction.py` | `NEW` | Centralized redaction and secret sanitization engine |
| `tests/test_activity_observability.py` | `NEW` | Full 9-case test suite for activity observability |
| `docs/reports/PHASE-ACTIVITY-OBSERVABILITY.md` | `NEW` | Phase report and architecture specifications |
| `cortex_engine/models.py` | `MODIFIED` | Added `ActivityEvent` canonical dataclass |
| `cortex_engine/storage.py` | `MODIFIED` | Added `record_activity`, `read_activity`, and `get_activity` |
| `cortex_engine/api.py` | `MODIFIED` | Added public `record_activity`, `list_activity`, and `get_activity` |
| `cortex_engine/mcp_server.py` | `MODIFIED` | Added `cortex_record_activity`, `cortex_list_activity`, and auto tool wrapping |
| `cortex_engine/cli.py` | `MODIFIED` | Added `cortex activity` subcommand and formatted output |
| `cortex_engine/__init__.py` | `MODIFIED` | Exported `ActivityEvent` |

---

## 9. Test Verification

- **Activity Observability Suite**: 9/9 tests passed in 0.28s (`tests/test_activity_observability.py`).
- **Full Regression Test Suite**: 146/146 tests passed in 135.71s across 18 test suites.
- **Pass Rate**: 100%. Zero regressions.

---

## 10. Known Observability Gaps

- **External Interactive Terminals**: Commands typed interactively into external user terminal windows without invoking CORTEX CLI, MCP, or API wrappers cannot be intercepted passively. Such external operations should be recorded via explicit `cortex_record_activity` calls or wrapper scripts.
- **In-Memory Volatile Variables**: Python runtime local variables inside test execution processes are not monitored, preserving performance and memory isolation.

---

## 11. Security & Privacy Boundary Confirmation

- **No Private Deliberations Captured**: Confirmed that zero chain-of-thought, system prompts, or hidden agent thought tokens are recorded.
- **No Secret Leakage**: Confirmed via regex scanner that `.env` tokens, API keys, and credential headers are redacted before appending to `.cortex/events/activity.jsonl`.
- **Durable Disk Recovery**: Confirmed that activity records survive process restart and corrupted line injections without data loss.
