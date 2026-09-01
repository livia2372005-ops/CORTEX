# CORTEX Memory Model & Invariants

## 1. Canonical Storage Structure

```text
.cortex/
├── events/
│   └── events.jsonl
├── knowledge/
│   ├── constraints/   # CON-*.json
│   ├── decisions/     # DEC-*.json
│   ├── failures/      # FAIL-*.json
│   ├── lessons/       # LES-*.json / NOISE-*.json
│   └── claims/        # CLAIM-*.json
└── indexes/
    └── cortex.db      # Disposable SQLite FTS5 index
```

## 2. Core Invariants

1. **Canonical Read Rule**: FTS index tables return record IDs; full content is always loaded from disk files.
2. **Deterministic Rebuild Rule**: Deleting `.cortex/indexes/cortex.db` never loses data. `cortex reindex` restores the entire index from disk files.
3. **Non-Destructive Supersession**: Superseded decisions are marked `status: superseded` and reference their replacement (`supersedes: DEC-002`). They are never deleted.
4. **Empirical Freshness**: Modifying a source artifact marks associated claims as `status: affected` (`reason: artifact_changed`). CORTEX never autonomously rejects code.
