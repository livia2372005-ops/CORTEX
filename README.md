# CORTEX — Persistent Project Memory & Evidence Substrate for Coding Agents

CORTEX is a lightweight, inspectable tool for an Agent — not a second autonomous decision authority.

---

## 1. Core Principles

1. **ONE Agent Architecture**: There is ONE coding Agent operating in isolated role modes (`APP`, `MEMORY`, `REVIEW`, `LEARNING`).
2. **Advisory Tool**: The Agent retains full decision-making responsibility, code reasoning, and final judgment. CORTEX does not autonomously reject code or alter project plans.
3. **Canonical Filesystem Truth**: Authoritative records live in human-readable JSON files in `.cortex/knowledge/` and `.cortex/events/`.
4. **Disposable Derived Indexes**: SQLite FTS5 index is purely derived data and is always 100% rebuildable from disk.
5. **No Hallucinated Memory**: Every claim and decision carries provenance tracing back to files, git commits, or tests.

---

## 2. Quickstart

### Installation & Initialization

```bash
# Initialize CORTEX and Antigravity plugin in current workspace
python -m cortex_engine.cli init

# Verify installation health
python -m cortex_engine.cli doctor

# Inspect memory record status
python -m cortex_engine.cli status
```

### Antigravity Integration

CORTEX packages natively as an Antigravity workspace plugin in `.agents/plugins/cortex/`:
- **Rules**: `.agents/plugins/cortex/rules/cortex-awareness.md`
- **Skills**: `cortex-memory`, `cortex-review`, `cortex-learning`
- **MCP Server**: Stdio JSON-RPC 2.0 server (`python -m cortex_engine.mcp_server`)

---

## 3. Agent Tool Surface

- `cortex_search(query, limit)`: Deterministic lexical candidate search via SQLite FTS5.
- `cortex_get(id, category)`: Direct retrieval of canonical record from disk.
- `cortex_compile_context(task, memory_ids, budget_tokens)`: Compiles selected memory items into bounded structured prompt context.
- `cortex_check_claim_freshness(id)`: Verifies claim artifact content hashes against workspace files.
- `cortex_record_knowledge(...)`: Persists architectural decisions, constraints, failures, and lessons.
- `cortex_record_event(...)`: Appends lifecycle audit events.

---

## 4. Documentation Index

- [Architecture Overview](file:///d:/App/CORTEX/docs/architecture.md)
- [Installation Guide](file:///d:/App/CORTEX/docs/installation.md)
- [Agent Usage Guide](file:///d:/App/CORTEX/docs/agent-usage.md)
- [Canonical Memory Model](file:///d:/App/CORTEX/docs/memory-model.md)
- [Troubleshooting & Doctor](file:///d:/App/CORTEX/docs/troubleshooting.md)
