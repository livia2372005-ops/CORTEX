# CORTEX Installation & Setup Guide

## Requirements
- Python >= 3.10
- Git version control (recommended)
- Antigravity IDE / AGY CLI

## 1. Direct Workspace Installation (Mode A)

Initialize CORTEX in an existing project workspace:

```bash
# In the target project root
python -m cortex_engine.cli init
```

This non-destructively provisions:
1. Canonical Agent entry point at `CORTEX_USAGE.md`
2. Canonical memory storage directory at `.cortex/`
3. Antigravity plugin manifest at `.agents/plugins/cortex/plugin.json`
4. MCP server definition at `.agents/plugins/cortex/mcp_config.json`
5. Lifecycle hooks at `.agents/plugins/cortex/hooks.json`
6. Awareness rules at `.agents/plugins/cortex/rules/`
7. Retrieval, learning, & usage skills at `.agents/plugins/cortex/skills/`

## 2. Verification

Run the diagnostics doctor:

```bash
python -m cortex_engine.cli doctor
```

Expected output:
```text
=== CORTEX Doctor (v0.3.0) ===
Workspace: /path/to/project
Overall Health: [PASS]

  [PASS] Python Runtime       : Python 3.12.x
  [PASS] Git Repository       : Git repo initialized
  [PASS] Canonical Storage    : .cortex/ structure valid
  [PASS] Derived Index        : SQLite FTS5 index ready
  [PASS] Derived Vector Index : Semantic vector index ready (tfidf_ngram_v1)
  [PASS] Antigravity Plugin   : v0.3.0 plugin complete
```
