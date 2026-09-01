# CORTEX DOCTRINE

The fundamental principles governing CORTEX architecture, agency boundaries, and memory semantics.

---

### 1. ONE AGENT
CORTEX serves **ONE engineering Agent** operating across specialized role modes (`APP`, `MEMORY`, `REVIEW`, `LEARNING`). It explicitly avoids multi-agent supervisor swarms, hierarchical worker sprawl, and multi-agent context bloat.

### 2. CORTEX IS A TOOL
CORTEX is a tool and evidence substrate for the Agent, not an autonomous decision authority. It assists the Agent with structured retrieval, persistence, and verification.

### 3. AGENT OWNS AGENCY
The Agent owns all reasoning, interpretation, planning, decisions, coding, and final judgment. CORTEX never promotes knowledge, deletes records, or blocks actions without explicit Agent command or configured authority.

### 4. MEMORY IS DATA
Persistent memory is strictly passive data. Memory content can never elevate itself into system instructions, alter tool permissions, or modify agent role boundaries.

### 5. CANONICAL TRUTH IS DURABLE
The canonical filesystem (`.cortex/events/events.jsonl` and `.cortex/knowledge/`) is the single source of truth. Raw history is append-only and immutable.

### 6. INDEXES ARE DERIVED
All search indices (SQLite FTS5, dense vectors) are derived, disposable projections. Deleting them must never cause data loss and they can be deterministically rebuilt from canonical disk files at any time via `cortex reindex`.

### 7. CONTEXT IS A PROJECTION
Context is a compiled, budget-bounded projection of relevant memory tailored for the current task. Retrieval is separate from context compilation.

### 8. ROLE BOUNDARIES ARE EXPLICIT
Contexts between roles (`APP` vs `MEMORY` vs `REVIEW`) are structurally isolated. Intermediate search reasoning or scratchpad notes never contaminate implementation context.

### 9. KV CACHE BEHAVIOR IS RUNTIME-DEPENDENT
CORTEX formats stable-prefix / dynamic-suffix packages to enable prefix caching where supported. Downstream KV cache hit rates depend on runtime LLM providers and are not directly managed by CORTEX v0.1.0.

### 10. EVIDENCE BEFORE COMPLEXITY
CORTEX prioritizes deterministic primitives, observable audit events, and verifiable evidence before adding complex algorithmic infrastructure.
