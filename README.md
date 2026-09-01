# CORTEX — Persistent Project Memory & Evidence Substrate for Coding Agents

**CORTEX** is an inspectable, deterministic persistent memory and evidence retrieval substrate designed for **ONE** engineering Agent operating in modern AI coding environments (such as Google Antigravity).

---

## 1. Core Principles

1. **ONE Agent Model**: CORTEX serves a single engineering agent operating across specialized role modes (`APP`, `MEMORY`, `REVIEW`, `LEARNING`). It explicitly avoids multi-agent supervisor swarms and worker token explosion.
2. **Tool & Evidence Substrate**: CORTEX provides structured evidence, retrieval, persistence, and freshness diagnostics. The Agent retains full ownership of reasoning, planning, implementation, and final judgment.
3. **Canonical Filesystem Truth**: Authoritative records live in human-readable Markdown/JSON files in `.cortex/knowledge/` and an append-only event log in `.cortex/events/events.jsonl`.
4. **Disposable Derived Indexes**: SQLite FTS5 and local dense semantic indices are purely derived data and are always 100% rebuildable from disk via `cortex reindex`.
5. **Memory is Data**: Persistent memory is strictly passive data. It cannot elevate into system instructions or alter tool privileges.
6. **Explicit Promotion Authority**: Candidates are proposed from observed patterns; only the Agent has authority to promote candidates into persistent knowledge.

---

## 2. Architecture & Memory Lifecycle

```text
OBSERVABLE EVENT (Append-only operational history in events.jsonl)
      ↓
MEMORY CANDIDATE (Identified via deterministic signal rules)
      ↓
AGENT JUDGMENT (Agent evaluates engineering significance)
      ↓
PERSISTENT KNOWLEDGE (Canonical records in .cortex/knowledge/)
      │
      ├── Derived Indexer ──→ SQLite FTS5 + Local Dense Semantic Vectors
      │
      └── Context Compiler ─→ Structured Agent Context Package (Stable Prefix + Dynamic Suffix)
```

---

## 3. Quickstart

### Installation & Initialization

```bash
# Initialize CORTEX and Antigravity plugin in the current workspace
python -m cortex_engine.cli init

# Verify workspace health and index readiness
python -m cortex_engine.cli doctor

# Inspect memory record counts and configuration
python -m cortex_engine.cli status
```

### Antigravity Integration

CORTEX integrates natively as an Antigravity workspace plugin at `.agents/plugins/cortex/`:
- **Awareness Rule**: `.agents/plugins/cortex/rules/cortex-awareness.md`
- **Agent Skills**: `cortex-memory`, `cortex-review`, `cortex-learning`
- **MCP Server**: Fast JSON-RPC 2.0 stdio server (`python -m cortex_engine.mcp_server`)

---

## 4. Agent Tool Surface (MCP)

| Tool Name | Description |
|---|---|
| `cortex_search` | Adaptive hybrid search (FTS5 + lexical expansion + semantic fallback) |
| `cortex_get` | Direct retrieval of canonical record by ID |
| `cortex_compile_context` | Compiles selected memory items into bounded structured context |
| `cortex_record_knowledge` | Persists decisions, constraints, failures, lessons, and claims |
| `cortex_record_event` | Appends observable lifecycle events to append-only log |
| `cortex_detect_candidates` | Inspects recent events for memory candidate proposals |
| `cortex_promote_memory` | Explicitly promotes events to durable knowledge with provenance |
| `cortex_check_duplicates` | Non-destructively identifies conceptual duplicates |
| `cortex_archive_memory` | Logically archives retired knowledge records |
| `cortex_check_claim_freshness`| Verifies bound code artifact SHA-256 hashes against disk |
| `cortex_status` / `cortex_doctor` | Workspace diagnostics and health checks |

---

## 5. Context Compilation & KV Cache Design

CORTEX features a dedicated **Context Compiler Layer** that transforms retrieved records into structured, budget-bounded agent context:
- Formats context into a **stable prefix** (invariant guidelines) and **dynamic suffix** (task and selected memories).
- Enforces token budgets (e.g. 500, 1000 tokens) with deterministic budget shedding.
- Embeds transparent lifecycle status markers (`[ACTIVE]`, `[SUPERSEDED]`, `[ARCHIVED]`).

> [!NOTE]
> Provider-level KV cache behavior is runtime-dependent and downstream LLM provider specific. CORTEX formats stable-prefix context to enable prefix caching where supported, but does not directly control hardware KV cache slots.

---

## 6. Known Limitations

- **Lexical Pattern Clustering**: Failure clustering operates on lexical token overlap with stopword filtering; highly dynamic stack traces with randomized variable names may produce multiple candidate proposals.
- **Local Embedding Scale**: The embedded dense n-gram vector engine is tailored for local zero-dependency workspaces (< 10,000 records) rather than massive hosted enterprise clusters.

---

## 7. Documentation Index

- [CORTEX Doctrine](docs/CORTEX_DOCTRINE.md) — Core architectural and agency principles
- [Architecture Overview](docs/architecture.md) — Dual-layer storage and indexing design
- [Installation Guide](docs/installation.md) — Setup and Antigravity configuration
- [Agent Usage Guide](docs/agent-usage.md) — Role transitions and MCP workflows
- [Canonical Memory Model](docs/memory-model.md) — Knowledge schemas and status lifecycles
- [Troubleshooting & Doctor](docs/troubleshooting.md) — Diagnostic and repair procedures
- [Changelog](CHANGELOG.md) — Release notes and version history
- [v0.1.0 Release Report](docs/reports/RELEASE-0.1.0.md) — Release audit and benchmark evidence
