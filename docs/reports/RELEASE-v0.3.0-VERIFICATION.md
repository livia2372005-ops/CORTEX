# CORTEX v0.3.0 — Remote Release Verification Report

**Release Version**: `v0.3.0`  
**Date**: 2026-09-02  
**Target Tag**: `v0.3.0`  
**Repository Remote**: `https://github.com/livia2372005-ops/CORTEX.git`  
**Verification Status**: **100% VERIFIED & PUBLISHED**  

---

## 1. Executive Summary

CORTEX v0.3.0 establishes **Clean Runtime Packaging**, the root Agent entry point **`CORTEX_USAGE.md`**, first-class **`TaskAnchor` Task Boundary Observability**, and the standardized **General Agent Usage Protocol (`cortex-usage`)**, alongside existing Native Antigravity Action Observability and persistent memory retrieval.

This report independently verifies the local Git state, remote Git state on GitHub, the published GitHub Release, and isolated clean-clone reproduction in an independent consuming application workspace.

---

## 2. Git & Release Metadata Verification

| Check | Expected | Observed | Status |
| :--- | :--- | :--- | :--- |
| **Release Version** | `0.3.0` | `0.3.0` (`cortex_engine.__version__`) | Verified |
| **Schema Version** | `1.0.0` | `1.0.0` (`__schema_version__`) | Verified |
| **Plugin Version** | `0.3.0` | `0.3.0` (`plugin.json`) | Verified |
| **MCP Version** | `0.3.0` | `0.3.0` (`mcp_server.py`) | Verified |
| **Release Commit SHA** | `88ee8ea...` | `88ee8ea20532f92adb7b4f3719d82cd59bf813fd` | Verified |
| **Annotated Tag SHA** | Tag Object | `c44e7092d03dab6718223728d4f58be047ef3f23` | Verified |
| **Local Tag Target** | `88ee8ea...` | `88ee8ea20532f92adb7b4f3719d82cd59bf813fd` | Verified |
| **Working Tree State** | Clean | `nothing to commit, working tree clean` | Verified |

---

## 3. Remote Git State Verification (`git ls-remote origin`)

```text
88ee8ea20532f92adb7b4f3719d82cd59bf813fd	HEAD
88ee8ea20532f92adb7b4f3719d82cd59bf813fd	refs/heads/master
c44e7092d03dab6718223728d4f58be047ef3f23	refs/tags/v0.3.0
88ee8ea20532f92adb7b4f3719d82cd59bf813fd	refs/tags/v0.3.0^{}
```

- **Remote `master`**: Matches release commit `88ee8ea20532f92adb7b4f3719d82cd59bf813fd`.
- **Remote `v0.3.0` Tag**: Points to tag object `c44e7092d03dab6718223728d4f58be047ef3f23`.
- **Peeled Target (`refs/tags/v0.3.0^{}`)**: Matches release commit `88ee8ea20532f92adb7b4f3719d82cd59bf813fd`.

---

## 4. GitHub Release Publication Verification

Direct query to GitHub Releases API:
- **Tag Name**: `v0.3.0`
- **Release Title**: `CORTEX v0.3.0 — Clean Runtime + Agent Entry Point`
- **Publication Status**: Published (`draft: false`, `prerelease: false`)
- **Release URL**: [https://github.com/livia2372005-ops/CORTEX/releases/tag/v0.3.0](https://github.com/livia2372005-ops/CORTEX/releases/tag/v0.3.0)

---

## 5. Security & Secret Protection Audit

Tracked repository files were audited via `git ls-files` and pattern matching:
- **Zero Credentials**: No `.env`, API keys, PATs, bearer tokens, or private keys tracked.
- **Zero Local State**: No `.cortex/state/*.jsonl`, `.cortex/events/*.jsonl`, `.cortex/index/`, or `.sqlite` files committed.
- **Zero Transcripts**: No conversation transcript files or private reasoning logs stored.

---

## 6. Automated Test Suite Results

```text
Ran 173 tests in 128.498s
OK (100% PASS across 23 test modules)
```

### Coverage by Component:
- `test_storage.py` (5 tests): Canonical dual-layer filesystem storage.
- `test_fts_indexing.py` (4 tests): Derived SQLite FTS5 lexical indexing.
- `test_context_compiler.py` (8 tests): Stable prefix / dynamic suffix context compilation.
- `test_mcp_integration.py` (7 tests): MCP JSON-RPC tool server & lifecycles.
- `test_red_team_phase12.py` (6 tests): Adversarial prompt injection & FTS syntax robustness.
- `test_retrieval_phase13.py` (7 tests): Lexical expansion & dense vector benchmarks.
- `test_router_phase14.py` (6 tests): Hybrid routing policies (Policy A/B/C/D).
- `test_lifecycle_phase16.py` (8 tests): Memory candidate detection & promotion.
- `test_release_gate_phase17.py` (10 tests): Agency boundaries & promotion invariant audit.
- `test_activity_observability.py` (9 tests): Activity logging, correlation, & redaction.
- `test_antigravity_hooks.py` (8 tests): PreToolUse & PostToolUse lifecycle hook integration.
- `test_packaging_boundaries.py` (4 tests): Runtime isolation and documentation boundaries.
- `test_task_anchors.py` (8 tests): TaskAnchor boundaries, prompt hashing, hook propagation, MCP tools.
- `test_cortex_usage_skill.py` (3 tests): General Agent usage skill invariants.
- `test_cortex_usage_entrypoint.py` (4 tests): Root `CORTEX_USAGE.md` invariants & consuming workspace placement.
- *Additional modules*: `test_cli.py`, `test_models.py`, `test_vertical_slice.py`, `test_supersession.py`, `test_freshness.py`, `test_duplicate_detection.py`, `test_trial_phase8.py`.

---

## 7. Isolated Clean-Clone & Consuming-Project Verification

An isolated reproduction trial was executed from a fresh temporary directory:
1. **GitHub Clone**: `git clone --branch v0.3.0 --single-branch https://github.com/livia2372005-ops/CORTEX.git`
2. **Version Verification**: `python -m cortex_engine.cli --version` $\rightarrow$ `CORTEX v0.3.0 (schema v1.0.0)`.
3. **Consuming Workspace Setup**: Initialized an independent application workspace (`sample-app/`) containing pre-existing `docs/reports/Q3_AUDIT.md` and `src/main.py`.
4. **CORTEX Initialization**: Executed `cortex --workspace sample-app init`.
5. **Boundary Audit Results**:
   - `[PASS]` `sample-app/CORTEX_USAGE.md` placed directly at project root.
   - `[PASS]` `sample-app/docs/reports/Q3_AUDIT.md` completely untouched and preserved.
   - `[PASS]` Zero CORTEX developer reports placed into `sample-app/docs/`.
   - `[PASS]` Plugin manifest registered at `sample-app/.agents/plugins/cortex/plugin.json`.
6. **Agent Smoke Test Results**:
   - Started task anchor `smoke-task-1` (Prompt: "Implement greeter", Hash: `df8967b...`).
   - Inspected root `CORTEX_USAGE.md` for core usage protocol.
   - Recorded tool action and completed task anchor.
   - `cortex activity --task smoke-task-1 --json` verified all events correlated cleanly with `anchor_id = "smoke-task-1"`.

---

## 8. Directly Verified vs. Previously Reported Facts

### Directly Verified in this Audit:
- Git commit `88ee8ea20532f92adb7b4f3719d82cd59bf813fd` and tag `v0.3.0` match across local repository and GitHub remote.
- GitHub Release `v0.3.0` is published and publicly accessible.
- Clean clone from GitHub remote successfully initializes independent consuming workspaces with `CORTEX_USAGE.md` at root.
- Consuming workspace documentation (`docs/reports/`) is 100% isolated and never polluted by CORTEX initialization.
- Full automated test suite passes with 173 / 173 tests.
- TaskAnchor prompt hashing produces deterministic SHA-256 fingerprints without storing raw prompts.

### Previously Reported Facts (Inherited Context):
- FTS5 and TF-IDF n-gram vector benchmark recall metrics across 105-query evaluation suite (Phase 13 / 14).
- 30-task long-horizon trial metrics (Phase 8).

---

## 9. Known Limitations

- **Observability Scope**: Observes tool executions through configured Antigravity hooks and MCP calls; does not monitor uninstrumented external OS processes outside the workspace.
- **Prompt Hash Semantics**: Prompt hashes provide cryptographic proof of identical normalized prompt inputs; they do not reconstruct semantic intent.
- **Vector Index Scale**: Local dense n-gram semantic vector index is optimized for repository-scale memories (< 10,000 records).
