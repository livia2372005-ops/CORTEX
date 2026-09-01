# Changelog

All notable changes to the CORTEX persistent project memory and evidence retrieval substrate are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-09-01

### Added
- **Append-Only Event Stream**: Deterministic recording of observable lifecycle events in `.cortex/events/events.jsonl` with strict append-only semantics.
- **Canonical Storage Architecture**: Markdown (`.md`) and JSON (`.json`) canonical filesystem storage for persistent knowledge (`decisions`, `constraints`, `failures`, `lessons`, `claims`, `evidence`).
- **Deterministic FTS5 Indexing**: SQLite FTS5 derived indexing for fast full-text lexical search and ranking.
- **Local Dense Semantic Retrieval**: Disposability-first local dense n-gram character/word embedding engine for recall-oriented retrieval with zero cloud dependency.
- **Deterministic Lexical Expansion**: Pre-computed synonym/domain vocabulary expansion dictionary for handling vocabulary drift without LLM hallucination.
- **Hybrid Retrieval Router (Policy D)**: Adaptive hybrid search routing that evaluates lexical FTS confidence, falls back to local semantic retrieval on weak confidence, and merges deduplicated candidates.
- **Context Compiler Layer**: Structured compilation layer supporting stable-prefix / dynamic-suffix formatting, token budget enforcement, status tags, and provenance attachment.
- **Memory Lifecycle & Promotion Layer**: Deterministic pattern clustering for candidate memory proposal with strict Agent-authorized promotion (`cortex.promote_candidate`, `cortex.promote_memory`).
- **Non-Destructive Supersession**: Explicit supersession tracking (`supersedes` / `superseded_by`) preserving full historical records without physical deletion.
- **Non-Destructive Duplicate Detection**: Heuristic token-overlap similarity scoring flagging duplicates for Agent review without automated destructive merging.
- **Antigravity Packaging & Plugin**: Native Antigravity workspace integration at `.agents/plugins/cortex` with awareness rules (`cortex-awareness.md`) and specialized skills (`cortex-memory`, `cortex-review`, `cortex-learning`).
- **Model Context Protocol (MCP) Server**: JSON-RPC 2.0 MCP server exposing tools (`cortex_search`, `cortex_get`, `cortex_compile_context`, `cortex_record_event`, `cortex_record_knowledge`, `cortex_detect_candidates`, `cortex_promote_memory`, `cortex_check_duplicates`, `cortex_archive_memory`, `cortex_status`, `cortex_doctor`).
- **CLI Subcommands**: Command-line interface supporting `init`, `status`, `doctor`, `reindex`, `search`, `get`, `compile`, `candidates`, `promote`, `archive`, `duplicates`.

### Architecture & Agent Model
- **Single-Agent Model**: ONE engineering agent operating across specialized role modes (`APP`, `MEMORY`, `REVIEW`, `LEARNING`) with structured context packages, avoiding multi-agent supervisor/swarm overhead.
- **Agency Boundary**: CORTEX provides evidence, retrieval, persistence, and diagnostics. The Agent retains full ownership of reasoning, interpretation, planning, decisions, and code execution.
- **KV Cache Design**: Stable-prefix context separation. Explicitly documents that runtime provider KV cache hit rates depend on downstream LLM providers and are not directly managed by CORTEX.

### Deferred to Future Releases
- **Provider-Level KV Cache Control**: Direct control over provider-specific KV cache slotting or attention masks.
- **Hosted / Cloud Vector Databases**: Hosted vector infra (e.g. Pinecone, Milvus, Qdrant). Local SQLite FTS5 + local dense embeddings are prioritized for zero-dependency reliability.
- **Graph Databases**: Autonomous graph traversal or Neo4j infrastructure.
- **Autonomous Memory Agents / LLM Managers**: Autonomous background daemons or scheduled LLM agents that synthesize, merge, or delete memories without user consent.
- **Autonomous Policy Enforcement**: Autonomous hard blocking of developer actions.
