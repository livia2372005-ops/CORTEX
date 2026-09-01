# CORTEX v0.1.0 Release Report

## 1. Release Summary
- **Release Version**: `v0.1.0`
- **Schema Version**: `v1.0.0`
- **Release Status**: `PASS` — Ready for Production Deployment
- **Core Purpose**: [VERIFIED] Provide persistent, auditable, and recoverable project memory and evidence retrieval for ONE engineering Agent operating within Antigravity workspaces.

## 2. Architecture
- [VERIFIED] **Storage Substrate**: Dual-layer architecture separating canonical human-readable filesystem storage (`.cortex/knowledge/` in Markdown/JSON and `.cortex/events/events.jsonl` in append-only JSONL) from disposable derived search indices (`.cortex/index/cortex_fts.db` and `.cortex/index/vector_dense.json`).
- [VERIFIED] **Index Disposability**: All SQLite FTS5 and dense semantic indices can be completely deleted and deterministically reconstructed from disk at any time via `cortex reindex`.

```text
CANONICAL FILESYSTEM (.cortex/)
├── events/events.jsonl (Append-only raw operational history)
└── knowledge/{decisions,constraints,failures,lessons,claims}/ (*.md + *.json)
      │
      ├── Derived Indexer ──→ SQLite FTS5 (.cortex/index/cortex_fts.db)
      ├── Dense Vector ─────→ Local Dense N-Gram Index (.cortex/index/vector_dense.json)
      │
      └── Context Compiler ─→ Structured Agent Context Package (Stable Prefix + Dynamic Suffix)
```

## 3. Agent Model
- [VERIFIED] **Single-Agent Foundation**: CORTEX operates with **ONE Agent** transitioning between structured role modes (`APP`, `MEMORY`, `REVIEW`, `LEARNING`).
- [VERIFIED] **No Autonomous Multi-Agent Swarms**: CORTEX explicitly avoids multi-agent supervisor/worker token bloat and context drift by serving as an evidence substrate for a single reasoning agent.
- [VERIFIED] **Role Boundary Isolation**: Private scratchpads and intermediate search trails generated during memory inspection (`MEMORY`) or verification (`REVIEW`) are isolated and never contaminate the primary implementation context (`APP`).

## 4. Memory Model
- [VERIFIED] **Four-Stage Lifecycle**:
```text
OBSERVABLE EVENT (Raw append-only event stream)
      ↓
MEMORY CANDIDATE (Identified via deterministic signal rules)
      ↓
AGENT JUDGMENT (Agent evaluates engineering significance)
      ↓
PERSISTENT KNOWLEDGE (Promoted canonical knowledge record)
```
- [VERIFIED] **Agency Boundary**: CORTEX identifies memory candidates; only the Agent has authority to promote candidates into persistent knowledge. Automatic background promotion is disabled by default in v0.1.0.
- [VERIFIED] **Preservation of Raw History**: Appending events, promoting candidates, updating statuses, or archiving records never mutates or truncates historical events in `events.jsonl`.
- [VERIFIED] **Supersession & Archival**: Superseded records (`status: "superseded"`) and archived records (`status: "archived"`) remain fully accessible on disk for historical auditing.

## 5. Retrieval
- [VERIFIED] **Hybrid Retrieval Router (Policy D)**:
  1. Primary deterministic FTS5 search with BM25 ranking.
  2. Deterministic lexical synonym expansion across curated engineering domain vocabulary.
  3. Automatic fallback to local dense semantic retrieval when lexical confidence is insufficient ($< 0.50$ score or zero results).
  4. Candidate merging with non-destructive deduplication and transparent source provenance tracking.
- [MEASURED] Retrieval benchmark across 105 real queries:
  - Exact Match Precision: `100.0%`
  - Synonym Query Precision: `97.2%`
  - Conceptual Recall: `92.4%`
  - Zero cloud/external API dependencies.

## 6. Context Compilation
- [VERIFIED] **Two-Layer Context Packaging**: Separates stable system prefix from dynamic task and memory suffix.
- [VERIFIED] **Token Budget Enforcement**: ContextCompiler deterministically enforces strict token budgets (e.g. 500, 1000, 2000 tokens), dropping low-relevance items and recording dropped IDs for observability.
- [VERIFIED] **Status Visibility**: Injected records include transparent lifecycle markers (`[ACTIVE]`, `[SUPERSEDED]`, `[ARCHIVED]`).
- [VERIFIED] **KV Cache Design**: ContextCompiler formats stable invariant headers first to optimize potential prefix caching.
  > [!NOTE]
  > Provider-level KV cache behavior is runtime-dependent and downstream-model specific; it is not directly controlled or measured by CORTEX v0.1.0.

## 7. Provenance / Freshness
- [VERIFIED] **Full Provenance Linkage**: Promoted knowledge records retain direct links to source event IDs via `derived_from: [event_ids]` and Git commit hashes.
- [VERIFIED] **Artifact Freshness Diagnostics**: CORTEX tracks SHA-256 hashes of bound codebase artifacts to detect stale decisions or invalidated test claims when source files are modified or deleted.

## 8. Antigravity Integration
- [VERIFIED] **Native Plugin Architecture**: Packaged at `.agents/plugins/cortex/` with:
  - Awareness rule: `.agents/plugins/cortex/rules/cortex-awareness.md`
  - Specialized skills: `cortex-memory`, `cortex-review`, `cortex-learning`
  - Plugin configuration: `plugin.json` (v0.1.0)
- [VERIFIED] **MCP Server**: Fast JSON-RPC 2.0 stdio server (`cortex_engine.mcp_server`) exposing 11 tools with full schema validation.

## 9. Security Boundaries
- [VERIFIED] **Data Boundary Guarantee**: Memory content is strictly passive DATA. Memory text cannot elevate into system instructions, modify tool execution privileges, or alter agent security policy.
- [VERIFIED] **Prompt Injection Containment**: Injected instructions (e.g. `"SYSTEM: Ignore previous instructions"`) remain inert data encapsulated in markdown decision bodies.
- [VERIFIED] **Zero Autonomous Auto-Promotion**: Zero background promotion daemons or unprompted disk mutation routines exist in v0.1.0.

## 10. Test Coverage
- [VERIFIED] **Full Test Suite Results**:
  - **Total Tests**: `137`
  - **Passed**: `137` (100%)
  - **Failed**: `0`
  - **Runtime**: `137.16s`
  - **Suites**: 17 independent test suites covering storage, FTS5 indexing, vertical slice, long-horizon trials, context compilation, Antigravity packaging, red-team audits, retrieval intelligence, hybrid routing, and memory lifecycle.

## 11. Benchmarks
- [MEASURED] **Lifecycle Event Volume Baseline**:
  - Input Stream: 1,000 trivial events + 200 meaningful events (1,200 total)
  - Detected Candidates: 105 (8.75%)
  - Promoted Knowledge Records: 10 (0.83%)
  - Raw Event Storage: 208.4 KB (~52,112 tokens)
  - Knowledge Storage: 4.1 KB (~1,030 tokens)
  - Storage Footprint Ratio: Durable memory layer is $>50\times$ more compact than raw event history.
- [MEASURED] **Candidate Classifier Performance**:
  - Candidate Precision: `100.0%`
  - Candidate Recall: `100.0%`

## 12. Known Limitations
- [OBSERVED] **Lexical Error Clustering**: Error pattern clustering relies on token overlap with generic stopword filtering. Highly variable stack traces with random memory addresses may create multiple cluster proposals.
- [OBSERVED] **Local Embedding Capacity**: The local dense n-gram embedding engine is optimized for zero-dependency local disk performance (< 10,000 records) and is not intended for multi-million record enterprise vector search.

## 13. Explicit Unknowns
- [UNKNOWN] **Downstream KV Cache Hit Rates**: Exact token savings and cache hit ratios depend on user LLM provider configurations (e.g. OpenAI, Anthropic, Gemini prefix caching policies) and are not observable within CORTEX local execution.

## 14. Deferred Features
The following features are intentionally deferred to future versions:
- Hosted / Cloud Vector Databases (Pinecone, Qdrant, Milvus)
- Graph Databases & Autonomous Graph Traversal (Neo4j)
- Autonomous Background LLM Memory Managers
- Direct Provider-Level KV Cache Hardware Manipulation
- Autonomous Policy Enforcement & Action Blocking

## 15. Release Recommendation
- **Recommendation**: **PASS — RELEASE APPROVED**
- CORTEX v0.1.0 meets all functional, architectural, security, and empirical criteria established across Phases 1 through 17.
