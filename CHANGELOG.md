# Changelog

All notable changes to the CORTEX persistent project memory and evidence retrieval substrate are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.1] — 2026-09-02

### Fixed
- **Reliable TaskAnchor Propagation**: Fixed cross-process TaskAnchor resolution in Antigravity lifecycle hooks (`PreToolUse`/`PostToolUse`) so that observable tool telemetry deterministically attaches the active `anchor_id` when a valid workspace/conversation correlation exists.
- **Robust `.cortex` Storage Resolution**: Implemented hierarchical path climbing (`find_cortex_dir`) across payload `workspacePaths`, `workspaceRoot`, `cwd`, and tool target file arguments to reliably locate project `.cortex` storage across separate hook processes.
- **Cross-Platform Path Normalization**: Added `normalize_workspace_path` to handle Windows backward/forward slashes, case variations, and `file:///` URI schemes.
- **Step Index `0` Preservation**: Fixed integer zero falsy evaluation bug where initial step 0 events lost their step indices.
- **Multi-Key Payload Compatibility**: Expanded hook payload parser to seamlessly extract metadata across snake_case, camelCase, and nested `toolCall` payload variants.
- **Strict Conversation Isolation**: Ensured hook events never cross-associate active anchors across differing concurrent conversations or separate workspace boundaries.

---

## [0.3.0] — 2026-09-02

### Added
- **Clean Runtime Packaging**: Strict separation between the CORTEX developer repository and consuming workspace runtime integration. `cortex init` provisions only `.cortex/`, `.agents/plugins/cortex/`, and root `CORTEX_USAGE.md` without polluting application `docs/` or creating `docs/reports/`.
- **Root Agent Entry Point (`CORTEX_USAGE.md`)**: Single, canonical 102-line root-level guide teaching coding Agents the core mental model, decision policy, memory workflow, and workspace authority boundary immediately upon workspace entry.
- **TaskAnchor / Task Boundary Observability**: First-class `TaskAnchor` entity and lifecycle APIs (`start_task`, `end_task`, CLI `cortex task`, MCP `cortex_start_task` / `cortex_end_task`) associating multi-step tool execution trajectories with distinct engineering tasks.
- **Deterministic Prompt Fingerprinting**: Deterministic SHA-256 fingerprinting (`prompt_hash`) for explicitly supplied task prompts without persisting raw user prompts by default or parsing conversation transcripts.
- **General Agent Usage Protocol (`cortex-usage`)**: Standardized Agent skill ([`.agents/skills/cortex-usage/SKILL.md`](.agents/skills/cortex-usage/SKILL.md)) establishing the decision policy ("when to use vs when not to use CORTEX"), the `Retrieved vs Applied vs Not Applied` distinction, and graceful degradation rules.
- **Workspace Authority Boundary Invariants**: Injected awareness rules explicitly declare that the consuming workspace owns its application source, tests, documentation, and reports.

### Security & Privacy Invariants
- **Zero Raw Prompt / Reasoning Storage**: Raw user prompts and private deliberations (chain-of-thought) are strictly excluded from memory persistence.
- **No Transcript Scraping**: Tool execution observability relies on structured native hooks without reading or scraping conversation transcripts.

---

## [0.2.0] — 2026-09-02

### Added
- **Native Antigravity Agent Observability**: Automated, non-intrusive action observability for Antigravity coding agents via native `PreToolUse` and `PostToolUse` lifecycle hooks (`.agents/plugins/cortex/hooks.json` and `cortex_engine.antigravity_hook`).
- **Canonical Activity Log (`.cortex/events/activity.jsonl`)**: Append-only activity log capturing observable tool calls, results, status, durations, error traces, and targets without recording private chain-of-thought or internal prompts.
- **Trajectory Reconstruction & Correlation**: Multi-step action trajectory linking using deterministic `correlation_id` (`step-{conversation_id}-{step_index}`) and `parent_event_id`.
- **Centralized Pre-Persistence Redaction**: Robust secret scrubbing (`cortex_engine.redaction`) redacting GitHub PATs, AI API keys (OpenAI, Anthropic), AWS credentials, Bearer JWTs, private keys, and passwords before storage.
- **Fault-Isolated Hook Architecture**: Resilient hook execution ensuring logging failures never disrupt agent tool operations or emit malformed responses.
- **CLI Trajectory Inspection**: Extended `cortex activity` CLI with `--conversation <id>`, `--step <idx>`, `--source`, `--status`, and `--json` filtering for formatted action timeline inspection.
- **Comprehensive Test Suite**: Added 17 new observability and hook integration tests, bringing full test coverage to 154 passing tests across 19 test modules.

### Security & Privacy Invariants
- **Reasoning Boundary**: CORTEX captures observable tool actions and parameters only; private deliberations, hidden reasoning traces, and conversation transcripts are strictly excluded from storage.

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
