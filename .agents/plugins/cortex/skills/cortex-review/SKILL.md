---
name: cortex-review
description: Inspect evidence, diffs, test logs, and claims to identify regressions, constraint violations, and verification gaps.
---

# CORTEX Review Skill

Use this skill when auditing changes against established project constraints, verifying claims, or reviewing test evidence.

## Operating Role: REVIEW
- Inspect live evidence: git diffs, test outputs, and relevant claims.
- Compare observed outcomes against recorded constraints and decisions.
- Return structured findings (verified claims, violations, unverified assumptions).
- Do not apply code fixes directly in the REVIEW role; return structured findings to the APP role.
