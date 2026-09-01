# CORTEX Architecture Overview

## 1. System Philosophy

CORTEX operates as an inspectable memory and evidence substrate for a single coding Agent.

```text
CANONICAL STORAGE (.cortex/)
  ├── knowledge/ (decisions, constraints, failures, lessons, claims)
  └── events/    (append-only events.jsonl)
        │
        ▼
DERIVED INDEX (.cortex/indexes/cortex.db)
  └── SQLite FTS5 (BM25 deterministic ranking)
        │
        ▼
CORTEX TOOLS (Local stdio MCP Server)
  ├── cortex_search
  ├── cortex_get
  ├── cortex_compile_context
  └── cortex_check_claim_freshness
        │
        ▼
ONE ANTIGRAVITY AGENT
  ├── APP Mode      (Code synthesis & refactoring)
  ├── MEMORY Mode   (Evidence retrieval & candidate selection)
  ├── REVIEW Mode   (Constraint verification & freshness checking)
  └── LEARNING Mode (Knowledge recording & durable takeaways)
```

## 2. Key Components

- **CortexStorage** (`cortex_engine/storage.py`): Pure filesystem manager writing deterministic JSON and JSONL records.
- **CortexIndexer** (`cortex_engine/indexer.py`): Derived FTS5 virtual tables enforcing the Canonical Read Rule (FTS matches candidate IDs $\rightarrow$ loads full record from disk).
- **ContextCompiler** (`cortex_engine/compiler.py`): Formats, deduplicates, and bounds selected memory records into structured sections.
- **CortexAPI** (`cortex_engine/api.py`): Unified programmatic Python API.
- **CortexMCPServer** (`cortex_engine/mcp_server.py`): JSON-RPC 2.0 stdio MCP server for Antigravity integration.
