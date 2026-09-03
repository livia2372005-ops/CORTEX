# CORTEX Phase Report — Cortex Interaction Trace

**Phase**: Cortex Interaction Trace  
**Date**: 2026-09-03  
**Test Suite Status**: **188 / 188 Passing (100%) across 25 test modules**  

---

## 1. Executive Summary

Prior to this phase, CORTEX Activity Observability logged all observed tool invocations in a flat event structure. While external tool telemetry (`view_file`, `write_to_file`, `run_command`) was captured, experiments studying Agent memory dynamics faced high noise: identifying what the Agent actually did with CORTEX required ad-hoc parsing of tool names, CORTEX operations were mixed with external tools, diagnostic commands were conflated with memory lookups, and rich execution metrics (queries, candidate counts, compiled token budgets, records retrieved) were not systematically recorded.

This phase introduces **Cortex Interaction Trace** as a first-class semantic category within canonical Activity Observability (`.cortex/events/activity.jsonl`). It establishes:
1. Deterministic categorization into `activity_domain` (`cortex`, `external_tool`, `system`) and `interaction_class` (`agent_memory`, `task_boundary`, `maintenance`).
2. Automatic trace generation directly from native CORTEX MCP and Python API operations without requiring second-pass Agent logging.
3. Single-trace de-duplication semantics that prevent double-counting when MCP instruments an operation that calls internal APIs.
4. Metrics-friendly structured metadata across `search`, `get`, `compile_context`, `record_knowledge`, `promote_memory`, and `check_claim_freshness`.
5. Experiment-oriented CLI flow visualization via `cortex activity --cortex` showing the step-by-step memory lifecycle free of external tool noise.

---

## 2. Classification Architecture

ActivityEvent is extended with two backward-compatible semantic fields:
- `activity_domain: Optional[str]`
- `interaction_class: Optional[str]`

### Activity Domains
| Domain | Scope | Examples |
|---|---|---|
| `cortex` | Interactions with CORTEX storage, memory, task boundaries, or diagnostics | `cortex_search`, `cortex_get`, `cortex_compile_context`, `task_start` |
| `external_tool` | Actions executed on external system/workspace tools via Antigravity hooks | `view_file`, `write_to_file`, `run_command`, `grep_search` |
| `system` | Process lifecycle, system hooks, or engine daemon events | System startup, workspace reload |

### Interaction Classes (CORTEX Domain)
| Interaction Class | Operations / Tools | Semantic Purpose |
|---|---|---|
| `agent_memory` | `cortex_search`, `cortex_get`, `cortex_compile_context`, `cortex_record_knowledge`, `cortex_promote_memory`, `cortex_check_claim_freshness`, `cortex_check_duplicates`, `cortex_archive_memory` | Core Agent memory consumption, retrieval, and durable knowledge lifecycle |
| `task_boundary` | `start_task`, `end_task`, `cortex_start_task`, `cortex_end_task`, `get_task`, `list_tasks` | Independent engineering task boundaries (TaskAnchors) |
| `maintenance` | `cortex_doctor`, `cortex_reindex`, `cortex_status`, `cortex_list_activity`, `cortex_record_activity` | Diagnostic, index rebuild, and administrative health inspection |

External tools (`activity_domain = "external_tool"`) have `interaction_class = None`, cleanly separating application work from memory dynamics.

---

## 3. Single-Trace De-Duplication Semantics

A critical design requirement is preventing double-counting when:
- An Agent invokes a CORTEX tool through MCP (`tools/call`), AND
- The MCP server implementation delegates to internal API methods (`self.api.search`, `self.api.get`, etc.) which also possess instrumentation.

### Chosen Semantics & Mechanism
1. **MCP Context Flag (`_in_mcp_call`)**:
   `CortexAPI` maintains an internal runtime flag `self._in_mcp_call`. When `CortexMCPServer` receives a tool call:
   ```python
   self.api._in_mcp_call = True
   try:
       result_data = self._execute_tool(tool_name, args)
   finally:
       self.api._in_mcp_call = False
   ```
2. **API Delegation Suppression**:
   Inside core API methods (`search`, `get`, `compile_context`, `record_knowledge`, `promote_memory`, `check_claim_freshness`), activity trace logging only fires when `record_trace and not self._in_mcp_call`. When called inside MCP, the API methods skip logging.
3. **Authoritative MCP Recording**:
   `CortexMCPServer` records the single authoritative event with source `"mcp"`, the exact end-to-end execution duration (`duration_ms`), status (`success` or `error`), and extracted metrics metadata.
4. **Task Boundary Non-Duplication**:
   `api.start_task` and `api.end_task` record canonical `task_start` and `task_end` events. When invoked via MCP tools (`cortex_start_task` / `cortex_end_task`), the MCP server detects the task boundary tools and skips emitting a redundant `tool_call` event.
5. **Direct Python API Invocations**:
   When tests, scripts, or embedded runtimes call `api.search(...)` directly outside of MCP, `self._in_mcp_call` is `False`. The API method records the single authoritative interaction event directly.

Result: **Exactly one coherent interaction event is recorded for every CORTEX operation.**

---

## 4. TaskAnchor Propagation Across CORTEX Interactions

When an active `TaskAnchor` exists for a workspace/conversation:
- Automatic CORTEX interaction events inherit the active `anchor_id`.
- The trace links seamlessly: `task_start` $\rightarrow$ `cortex_search` $\rightarrow$ `cortex_get` $\rightarrow$ `cortex_compile_context` $\rightarrow$ `cortex_record_knowledge` $\rightarrow$ `task_end`.
- When no active anchor exists: `anchor_id = None`. CORTEX never invents or guesses an anchor.
- Legacy records without `anchor_id`, `activity_domain`, or `interaction_class` deserialize safely with `None` values.

---

## 5. Metrics-Friendly Structured Metadata

Each CORTEX interaction records sanitized, queryable metadata:

| Operation | Structured Metadata Fields |
|---|---|
| `cortex_search` | `query` (sanitized), `candidate_count`, `policy`, `category` (optional) |
| `cortex_get` | `record_id`, `found` (`true`/`false`) |
| `cortex_compile_context` | `task` (sanitized prefix), `selected_count`, `char_count`, `token_estimate` |
| `cortex_record_knowledge` | `record_id`, `knowledge_type` |
| `cortex_promote_memory` | `candidate_id`, `resulting_record_id` |
| `cortex_check_claim_freshness` | `claim_id`, `classification` (`fresh`, `stale`, `affected`) |
| `cortex_check_duplicates` | `title` (sanitized), `match_count` |
| `cortex_archive_memory` | `record_id`, `reason` |

### Privacy & Redaction Guarantees
- All queries and user-facing parameters pass through the centralized `redact_data` / `redact_text` layer before entering `.cortex/events/activity.jsonl`.
- API keys (`sk-...`, `ghp_...`, AWS access keys, Bearer tokens, private keys) are replaced with `[REDACTED]`.
- Prompt hashes (`prompt_hash`) use SHA-256 fingerprinting. Raw user prompts and hidden system prompts are never persisted.
- Metric counts (`token_estimate`, `total_tokens_estimate`) are explicitly protected from false-positive auth token redaction via `SAFE_METRIC_KEYS`.

---

## 6. CLI Analysis & Experiment Flow View

### Command Usage
```bash
# Filter strictly for CORTEX interaction events (excludes view_file, run_command, etc.)
cortex activity --cortex

# Filter by active task anchor
cortex activity --cortex --task <anchor_id>

# Filter by conversation
cortex activity --cortex --conversation <conversation_id>

# Filter by interaction class
cortex activity --cortex --agent-memory
cortex activity --cortex --maintenance

# Machine-readable JSON output
cortex activity --cortex --json
```

### Flow Visualization Output
When `--cortex` is passed without `--json`, the CLI renders an intuitive step-by-step transition trace:
```text
=== CORTEX Interaction Trace (6 events) for task 'task-cc8838d9' ===
[TASK START] Implement Authentication Cache (anchor: task-cc8838d9)
  ↓
[CORTEX RECORD] record: DEC-AUTH-01 (type: decision) (27.23ms)
  ↓
[CORTEX SEARCH] query: "JWT validation caching" | 1 candidates (policy_d_hybrid_expand_fallback) (20.53ms)
  ↓
[CORTEX GET] record: DEC-AUTH-01 (found: True) (0.46ms)
  ↓
[CORTEX COMPILE] task: "Implement Redis JWT token caching" | 1 records (~99 tokens) (0.69ms)
  ↓
[TASK END] status: completed (anchor: task-cc8838d9)
=== End of CORTEX Interaction Trace ===
```

---

## 7. Programmatic API

Applications and evaluation harnesses query CORTEX interaction traces using `CortexAPI.list_cortex_activity`:

```python
events = api.list_cortex_activity(
    task_id="task-01",              # Filter by TaskAnchor
    conversation_id="conv-123",     # Filter by conversation
    interaction_class="agent_memory",# Filter: agent_memory | task_boundary | maintenance
    status="success",               # Filter: success | error | started
    limit=50,
)
```

`CortexStorage` provides `read_cortex_activity` and `read_activity` supporting `activity_domain` and `interaction_class` filters.

---

## 8. Real Consuming Workspace Smoke Test

A real smoke test was executed in an isolated temporary workspace (`scratch/smoke_test_cortex_interaction_trace.py`):
1. Initialized real `CortexStorage` and `CortexAPI`.
2. Created an active `TaskAnchor` (`Implement Authentication Cache`).
3. Executed real operations:
   - `record_knowledge` (`DEC-AUTH-01`)
   - `search` (`"JWT validation caching"`)
   - `get` (`"DEC-AUTH-01"`)
   - `compile_context` (`"Implement Redis JWT token caching"`)
4. Closed `TaskAnchor`.
5. Inspected raw `.cortex/events/activity.jsonl` and verified:
   - Exactly 6 events recorded.
   - All events carry `activity_domain = "cortex"`.
   - All events share the identical active `anchor_id`.
   - Agent memory events carry `interaction_class = "agent_memory"`.
   - Task boundary events carry `interaction_class = "task_boundary"`.
   - Query and token metadata are populated and unredacted.
6. Invoked CLI `cortex activity --cortex --task <aid>` via subprocess and verified clean execution and output.

---

## 9. Verification & Test Results

### Dedicated Test Module
`tests/test_cortex_interaction_trace.py` validates:
- `test_domain_and_class_classification`: Deterministic mapping across all tool and op names.
- `test_automatic_capture_via_python_api`: Core API methods auto-record traces.
- `test_no_double_counting_between_mcp_and_api`: Exactly 1 event recorded per MCP tool call.
- `test_task_anchor_and_conversation_propagation`: Anchor propagation and null anchor handling.
- `test_centralized_redaction_in_trace_queries`: API keys redacted from queries.
- `test_metrics_friendly_metadata_across_operations`: Verification of metadata schemas across ops.
- `test_legacy_backward_compatibility`: Historical events without new fields load safely.
- `test_cli_filtering_and_trace_view`: CLI `--cortex`, `--agent-memory`, `--maintenance`, and `--json`.

### Full Test Suite
```text
Ran 188 tests in 179.093s

OK
```
All 188 unit, integration, and benchmark tests across 25 test modules passed with 100% success.
