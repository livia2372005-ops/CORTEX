---
name: cortex-learning
description: Record durable decisions, constraints, failures, lessons, and claims into persistent CORTEX storage.
---

# CORTEX Learning & Knowledge Recording Skill

Use this skill at the conclusion of tasks or milestones to persist durable knowledge and verified outcomes.

## Operating Role: LEARNING
- Identify if the completed work produced:
  - An architectural or design decision (`decisions/`)
  - A project or environment constraint (`constraints/`)
  - A notable failure/regression and root cause (`failures/`)
  - An operational takeaway/rule (`lessons/`)
  - An empirical claim requiring future verification (`claims/`)
- Record the knowledge item using `cortex.record_knowledge` or `cortex.record_event`.
- Do not persist raw internal reasoning traces or temporary scratch data; record only structured, durable findings.
