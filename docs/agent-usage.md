# CORTEX Natural Agent Usage Guide

## 1. Natural Workflow

When CORTEX is installed in a workspace, the developer interacts naturally without special invocations:

```text
User: "Refactor the payment fee calculation in PaymentService."
```

### Agent Workflow:
1. **Recognition**: Agent notices the task touches payment calculations.
2. **Search**: Agent invokes `cortex_search(query="payment fee")`.
3. **Selection**: Agent inspects candidate IDs (`CON-001`, `DEC-001`, `FAIL-001`) and identifies relevant constraints.
4. **Context Compilation**: Agent invokes `cortex_compile_context(task=..., memory_ids=['CON-001', 'DEC-001'])`.
5. **Synthesis**: Agent writes the refactored code adhering to service layer boundaries.

## 2. Preferred Tool Interaction Protocol

```text
Agent
  ↓
cortex_search
  ↓
candidate records
  ↓
Agent selects relevant IDs
  ↓
cortex_compile_context
  ↓
Agent executes task
```
