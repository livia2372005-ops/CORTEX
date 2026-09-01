# CORTEX Troubleshooting & Diagnostics

## Common Issues & Resolutions

### 1. Doctor reports `[WARN] Derived Index : SQLite index missing`
- **Cause**: Index has not been initialized or was manually deleted.
- **Fix**: Run `python -m cortex_engine.cli reindex` to rebuild the index from canonical files.

### 2. Doctor reports `[WARN] Antigravity Plugin : Incomplete plugin installation`
- **Cause**: Missing `plugin.json` or skill files in `.agents/plugins/cortex/`.
- **Fix**: Run `python -m cortex_engine.cli init --force` to repair plugin files.

### 3. Claim reports `status: affected`
- **Cause**: The file referenced by the claim has changed its content hash.
- **Resolution**: Review the changes against the claim statement and update or re-verify the claim using `cortex_record_knowledge`.
