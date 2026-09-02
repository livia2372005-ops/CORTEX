# CORTEX Phase Report — Native Antigravity Agent Observability

**Status**: Implemented & Formally Verified  
**Date**: 2026-09-02  
**Component**: `cortex_engine.antigravity_hook`, `.agents/plugins/cortex/hooks.json`, `.agents/hooks.json`  
**Test Suite**: 154 / 154 Passing (100%) across 19 test suites  

---

## 1. Executive Summary & Objective

In this phase, CORTEX transitioned from requiring explicit Agent/MCP self-reporting of actions to **automatic, transparent observation of the Agent's actual tool execution trajectory** via native Antigravity lifecycle hooks (`PreToolUse` and `PostToolUse`).

### Core Principle
- **CORTEX is an observation and memory substrate**, not an autonomous decision-maker or supervisor.
- **The Agent remains solely responsible** for reasoning, planning, judgment, and code modifications.
- **Strict Privacy Invariant**: CORTEX captures observable tool invocations, parameters, outcomes, durations, and errors. It **never captures private reasoning, chain-of-thought traces, or internal prompts**, and does **not parse conversation transcripts**.

---

## 2. Architecture & Lifecycle Hook Design

```text
               +--------------------------------------+
               |          Antigravity Agent           |
               +--------------------------------------+
                                  |
                                  | (1) Tool Decision
                                  v
+-----------------------------------------------------------------------------+
|                               PreToolUse Hook                               |
| - Intercepts tool call payload: name, args, stepIdx, conversationId         |
| - Extracts resource target & sanitizes metadata                             |
| - Writes ActivityEvent(action_type="tool_call", status="started")           |
| - Emits {"decision": "allow"} to standard output                            |
+-----------------------------------------------------------------------------+
                                  |
                                  | (2) Tool Executes in Workspace
                                  v
+-----------------------------------------------------------------------------+
|                              Tool Execution Engine                          |
| (run_command, view_file, replace_file_content, write_to_file, cortex_*)     |
+-----------------------------------------------------------------------------+
                                  |
                                  | (3) Tool Result / Exit Status
                                  v
+-----------------------------------------------------------------------------+
|                              PostToolUse Hook                               |
| - Intercepts completion payload: stepIdx, conversationId, error             |
| - Correlates with parent PreToolUse event via correlation_id                |
| - Writes ActivityEvent(action_type="tool_result", status="success"|"error") |
| - Emits {} to standard output                                               |
+-----------------------------------------------------------------------------+
                                  |
                                  v
               +--------------------------------------+
               |    .cortex/events/activity.jsonl     |
               |      (Canonical Append-Only Log)     |
               +--------------------------------------+
```

### Event Correlation
Each lifecycle step is correlated deterministically:
- `correlation_id`: `step-{conversation_id}-{step_index}`
- `parent_event_id`: Links the `tool_result` event directly to its corresponding `tool_call` start event.

---

## 3. Taxonomy of Observable Actions

| Category | Event Source | Automatically Observed? | Examples |
| :--- | :--- | :--- | :--- |
| **Tool Invocations** | `antigravity_hook` (`PreToolUse`) | **Yes** | `view_file`, `replace_file_content`, `run_command`, `write_to_file` |
| **Tool Completions** | `antigravity_hook` (`PostToolUse`) | **Yes** | Success exit, command errors, exit status codes |
| **CORTEX API / MCP Actions** | `mcp`, `python_api` | **Yes** | `cortex_search`, `cortex_promote`, `cortex_archive` |
| **CLI Invocations** | `cli` | **Yes** | `cortex activity`, `cortex reindex`, `cortex doctor` |
| **Private Deliberations / CoT** | N/A | **NO (Out of Scope)** | Agent internal chain-of-thought, reasoning steps |
| **Raw Transcript Text** | N/A | **NO (Forbidden)** | Conversation JSONL transcript content parsing |

---

## 4. Privacy, Security & Secret Redaction

Before any activity event is written to `.cortex/events/activity.jsonl`, all tool arguments, command lines, targets, metadata, and error strings pass through the centralized `cortex_engine.redaction` layer:

1. **GitHub PATs**: `ghp_...`, `github_pat_...` $\rightarrow$ `[REDACTED]`
2. **AI Provider API Keys**: `sk-proj-...`, `sk-ant-...`, `sk-...` $\rightarrow$ `[REDACTED]`
3. **AWS Keys**: `AKIA...` $\rightarrow$ `[REDACTED]`
4. **JWT & Bearer Tokens**: `Bearer eyJ...` $\rightarrow$ `[REDACTED]`
5. **Private Keys & Passwords**: `-----BEGIN PRIVATE KEY-----`, password fields $\rightarrow$ `[REDACTED]`

---

## 5. Fault Isolation & Non-Blocking Execution

To guarantee that CORTEX never interferes with or halts the Agent:
1. **Hook Handlers are Isolated**: All hook operations are wrapped in safe exception handling.
2. **Deterministic Fallbacks**:
   - `PreToolUse` always emits `{"decision": "allow"}`.
   - `PostToolUse` always emits `{}`.
   - Script always returns exit code `0`.
3. **Zero Tool Disruption**: Even if file I/O fails or the `.cortex` folder is read-only, the tool call proceeds without error.

---

## 6. CLI Trajectory Inspection

The CLI has been extended with full conversation trajectory support:

```bash
# Formatted trajectory log for a specific conversation
cortex activity --conversation <conversation_id>

# Raw JSON trajectory for automated analysis
cortex activity --conversation <conversation_id> --json

# Filter by step index or status
cortex activity --conversation <conversation_id> --step 2 --status error
```

### Sample Trajectory Output:
```text
--- Agent Action Observability Log (10 events) for conversation 'conv-real-smoke-test-01' ---
2026-09-02T05:32:12.715555+00:00 [step 0] [STARTED] tool_call      via antigravity_hook [view_file] target: d:/App/CORTEX/pyproject.toml
   corr: step-conv-real-smoke-test-01-0
   meta: {"AbsolutePath": "[REDACTED]"}
2026-09-02T05:32:12.828083+00:00 [step 0] [SUCCESS] tool_result    via antigravity_hook [view_file] target: d:/App/CORTEX/pyproject.toml
   corr: step-conv-real-smoke-test-01-0
   meta: {"AbsolutePath": "[REDACTED]"}
2026-09-02T05:32:12.932678+00:00 [step 1] [STARTED] tool_call      via antigravity_hook [run_command] target: git status
   corr: step-conv-real-smoke-test-01-1
   meta: {"CommandLine": "git status"}
2026-09-02T05:32:13.043103+00:00 [step 1] [SUCCESS] tool_result    via antigravity_hook [run_command] target: git status
   corr: step-conv-real-smoke-test-01-1
   meta: {"CommandLine": "git status"}
2026-09-02T05:32:13.586881+00:00 [step 4] [STARTED] tool_call      via antigravity_hook [cortex_search] target: cortex_search
   corr: step-conv-real-smoke-test-01-4
   meta: {"query": "hybrid retrieval"}
2026-09-02T05:32:13.690188+00:00 [step 4] [SUCCESS] tool_result    via antigravity_hook [cortex_search] target: cortex_search
   corr: step-conv-real-smoke-test-01-4
   meta: {"query": "hybrid retrieval"}
```

---

## 7. Verification & Test Summary

| Test Module | Coverage | Status |
| :--- | :--- | :--- |
| `tests/test_antigravity_hook_observability.py` | PreToolUse, PostToolUse, Correlation, Trajectory, Redaction, Fault Isolation, CLI | **8 / 8 PASS** |
| `tests/test_activity_observability.py` | Redaction engine, JSONL append, API, MCP tools, CLI filters | **9 / 9 PASS** |
| Full CORTEX Regression Suite | All 19 test modules across storage, FTS, vectors, hybrid routing, lifecycle, packaging | **154 / 154 PASS (100%)** |
| Live Multi-Step Smoke Test | 5-step sequence across `view_file`, `run_command`, `write_to_file`, `cortex_search` | **VERIFIED** |

---

## 8. Conclusion

Native Antigravity Agent Observability is active, robust, and verified. CORTEX automatically records the Agent's empirical actions without invading private reasoning, without manual self-reporting, and without compromising agent performance or safety.
