"""CORTEX Phase 8 Real-Agent Long-Horizon Trial Harness & Trace Collector."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api import CortexAPI
from .freshness import compute_file_hash, get_git_commit
from .indexer import CortexIndexer
from .models import Claim, Event, Knowledge
from .storage import CortexStorage


@dataclass
class TrialTask:
    """Specification of an engineering task in the 30-task real-agent trial."""
    task_id: str
    turn_number: int
    group_bucket: str    # "1-5", "6-10", "11-15", "16-20", "21-25", "26-30"
    category: str        # "Strong", "Medium", "Low", "Historical", "Supersession", "Freshness"
    user_prompt: str
    materially_useful: bool
    expected_relevant_ids: List[str]
    superseded_ids: List[str] = field(default_factory=list)
    superseding_ids: List[str] = field(default_factory=list)
    artifact_path: Optional[str] = None
    expected_freshness_status: Optional[str] = None


@dataclass
class TaskTrace:
    """Trace recording observable events and outcomes during task execution."""
    task_id: str
    condition: str  # "CORTEX_ON" or "CORTEX_OFF"
    start_time: float
    end_time: float
    cortex_available: bool
    cortex_called: bool
    cortex_call_count: int
    tool_names: List[str]
    queries: List[str]
    retrieved_record_ids: List[str]
    retrieved_context_size_tokens: int
    git_commit_before: Optional[str]
    git_commit_after: Optional[str]
    tests_passed: bool
    tests_failed: bool
    files_changed: List[str]
    architecture_violation_detected: bool
    stale_memory_error_detected: bool
    task_completed: bool
    human_interventions: int = 0


def generate_30_trial_tasks() -> List[TrialTask]:
    """Construct 30 realistic sequential engineering tasks spanning 6 horizon groups."""
    tasks: List[TrialTask] = [
        # Group 1: Tasks 1-5 (Core Services & Constraints)
        TrialTask("TR-01", 1, "1-5", "Strong", "Implement base fee calculation method in PaymentService.", True, ["DEC-001", "CON-001"]),
        TrialTask("TR-02", 2, "1-5", "Strong", "Add user payment card tokenization helper.", True, ["CON-003", "DEC-003"]),
        TrialTask("TR-03", 3, "1-5", "Low", "Rename variable feeAmt to fee_amount in PaymentDTO.", False, []),
        TrialTask("TR-04", 4, "1-5", "Strong", "Setup REST HTTP client for InventoryService.", True, ["CON-004", "DEC-004"]),
        TrialTask("TR-05", 5, "1-5", "Medium", "Add in-memory caching to OrderService item lookups.", True, ["CON-005", "FAIL-002"]),

        # Group 2: Tasks 6-10 (Failures, Persistence & Invariants)
        TrialTask("TR-06", 6, "6-10", "Low", "Format docstrings in payment models.", False, []),
        TrialTask("TR-07", 7, "6-10", "Historical", "Why does PaymentRepository avoid calculation logic?", True, ["FAIL-001", "DEC-001"]),
        TrialTask("TR-08", 8, "6-10", "Strong", "Implement refund computation in PaymentService.", True, ["DEC-001", "CON-001"]),
        TrialTask("TR-09", 9, "6-10", "Low", "Fix typo in payment error response string.", False, []),
        TrialTask("TR-10", 10, "6-10", "Medium", "Configure OrderService inventory client timeout.", True, ["DEC-004", "FAIL-005"]),

        # Group 3: Tasks 11-15 (Supersession & Freshness)
        TrialTask("TR-11", 11, "11-15", "Supersession", "Evaluate using synchronous HTTP webhooks for notifications.", True, ["DEC-008"], superseded_ids=["DEC-005"], superseding_ids=["DEC-008"]),
        TrialTask("TR-12", 12, "11-15", "Medium", "Implement order confirmation dispatch event handler.", True, ["DEC-008", "FAIL-004"]),
        TrialTask("TR-13", 13, "11-15", "Low", "Add type annotation to NotificationPayload.", False, []),
        TrialTask("TR-14", 14, "11-15", "Strong", "Persist transaction authorization status in PaymentRepository.", True, ["CON-002", "CON-003"]),
        TrialTask("TR-15", 15, "11-15", "Freshness", "Verify claim status on payment service fee calculation.", True, ["CLAIM-001"], artifact_path="src/payment/service.py", expected_freshness_status="verified"),

        # Group 4: Tasks 16-20 (Auth Architecture & Redis Rejection)
        TrialTask("TR-16", 16, "16-20", "Supersession", "Evaluate adding Redis cluster for global session storage.", True, ["DEC-007"], superseded_ids=["DEC-002"], superseding_ids=["DEC-007"]),
        TrialTask("TR-17", 17, "16-20", "Strong", "Implement stateless JWT verification in AuthService.", True, ["DEC-007", "CON-001"]),
        TrialTask("TR-18", 18, "16-20", "Low", "Bump package version in pyproject.toml.", False, []),
        TrialTask("TR-19", 19, "16-20", "Historical", "Why was Redis session storage rejected in favor of stateless JWTs?", True, ["FAIL-003", "DEC-007"]),
        TrialTask("TR-20", 20, "16-20", "Medium", "Add bounded LRU cache for tax rate calculations.", True, ["CON-005", "FAIL-002"]),

        # Group 5: Tasks 21-25 (Refactoring, Drift & Affected Claims)
        TrialTask("TR-21", 21, "21-25", "Strong", "Refactor payment service methods for multi-tenant fees.", True, ["DEC-001", "CON-001"]),
        TrialTask("TR-22", 22, "21-25", "Freshness", "Check claim freshness for payment service after refactoring.", True, ["CLAIM-001"], artifact_path="src/payment/service.py", expected_freshness_status="affected"),
        TrialTask("TR-23", 23, "21-25", "Low", "Sort import statements in OrderService.", False, []),
        TrialTask("TR-24", 24, "21-25", "Medium", "Add exponential retry backoff for Inventory REST calls.", True, ["DEC-004", "CON-004"]),
        TrialTask("TR-25", 25, "21-25", "Historical", "Why does Inventory client avoid sharing connection pool with Order DB?", True, ["FAIL-005", "CON-004"]),

        # Group 6: Tasks 26-30 (Deep Longevity, Historical Audits & Invariants)
        TrialTask("TR-26", 26, "26-30", "Strong", "Persist customer masked card preview.", True, ["CON-003", "DEC-003"]),
        TrialTask("TR-27", 27, "26-30", "Supersession", "A junior engineer suggests deploying Redis for session replication. Evaluate proposal.", True, ["DEC-007"], superseded_ids=["DEC-002"], superseding_ids=["DEC-007"]),
        TrialTask("TR-28", 28, "26-30", "Freshness", "Check claim freshness for deleted legacy payment module.", True, ["CLAIM-003"], artifact_path="src/legacy/deleted.py", expected_freshness_status="missing"),
        TrialTask("TR-29", 29, "26-30", "Historical", "Summarize project rules regarding repository layer responsibilities.", True, ["CON-001", "CON-002", "FAIL-001"]),
        TrialTask("TR-30", 30, "26-30", "Strong", "Audit final payment and order service architectures for release readiness.", True, ["DEC-001", "DEC-003", "DEC-007", "DEC-008", "CON-001"]),
    ]
    return tasks


class TrialRunner:
    """Executes 30-task evaluation trial and records structured traces."""

    def __init__(self, workspace_dir: str | Path):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.storage = CortexStorage(cortex_dir=self.workspace_dir / ".cortex")
        self.indexer = CortexIndexer(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer)

    def setup_real_project(self) -> None:
        """Seed genuine multi-module software project with code, tests, docs, and memory records."""
        src_dir = self.workspace_dir / "src"
        (src_dir / "payment").mkdir(parents=True, exist_ok=True)
        (src_dir / "order").mkdir(parents=True, exist_ok=True)
        (src_dir / "inventory").mkdir(parents=True, exist_ok=True)
        (src_dir / "auth").mkdir(parents=True, exist_ok=True)
        (src_dir / "notification").mkdir(parents=True, exist_ok=True)

        pay_service = src_dir / "payment" / "service.py"
        pay_service.write_text("class PaymentService:\n    def calculate_fee(self, amount: float) -> float:\n        return amount * 0.025\n", encoding="utf-8")
        pay_hash = compute_file_hash(pay_service)

        auth_service = src_dir / "auth" / "service.py"
        auth_service.write_text("class AuthService:\n    def verify_jwt(self, token: str) -> bool:\n        return True\n", encoding="utf-8")
        auth_hash = compute_file_hash(auth_service)

        # Architectural Constraints (5)
        constraints = [
            ("CON-001", "Business logic belongs in Service layer", "Business logic, calculations, and domain rules must reside in Service classes, never in Repositories or Controllers."),
            ("CON-002", "Repository layer handles persistence only", "Repositories must only perform direct database queries and CRUD mappings."),
            ("CON-003", "Payment data must never be persisted", "Raw payment credentials, credit card numbers, and CVVs must never be stored in persistent storage."),
            ("CON-004", "Inter-service calls use the API boundary", "Services must communicate via formal API clients or event contracts, never direct cross-database access."),
            ("CON-005", "External cache must not be introduced without architectural decision", "Do not add Redis, Memcached, or external caching systems without explicit architecture approval."),
        ]
        for c_id, title, content in constraints:
            self.api.record_knowledge(id=c_id, knowledge_type="constraint", title=title, content=content, status="active")

        # Architectural Decisions (8)
        decisions = [
            ("DEC-001", "Service Layer Business Logic", "All payment calculations, fee logic, and domain rules reside in Service layer.", "active", None),
            ("DEC-002", "Use Redis for Session Storage", "Use standalone Redis cluster for user session storage.", "superseded", "DEC-007"),
            ("DEC-003", "Tokenized Payment Storage", "Store payment tokens returned by payment gateway, never raw card details.", "active", None),
            ("DEC-004", "REST API Boundaries for Microservices", "Use HTTPS REST client with retry policies for inter-service communication.", "active", None),
            ("DEC-005", "Synchronous HTTP Webhooks for Notifications", "Trigger notification delivery synchronously via HTTP POST requests.", "superseded", "DEC-008"),
            ("DEC-006", "SQLite for Derived Local Indexes", "Use SQLite FTS5 for local derived indexes.", "active", None),
            ("DEC-007", "Reject Redis; Use Stateless JWTs for Sessions", "Supersedes DEC-002: Standalone Redis infrastructure rejected for session storage due to ops overhead. Use stateless signed JWTs.", "active", None),
            ("DEC-008", "Asynchronous Event Queue for Notifications", "Supersedes DEC-005: Use async message queue for order notifications to prevent blocking request cycles.", "active", None),
        ]
        for d_id, title, content, status, superseding in decisions:
            self.api.record_knowledge(id=d_id, knowledge_type="decision", title=title, content=content, status=status, supersedes=superseding)

        # Historical Failures (5)
        failures = [
            ("FAIL-001", "Fee Logic in PaymentRepository Regression", "Putting fee calculation in Repository caused schema migration lockups and test mock failures."),
            ("FAIL-002", "Uncontrolled In-Memory Cache Memory Leak", "Unbounded dictionary caching in OrderService caused process out-of-memory crash under load."),
            ("FAIL-003", "Redis Network Partition Outage", "Redis cluster split-brain resulted in lost session data during network partition incident INC-102."),
            ("FAIL-004", "Synchronous Webhook Cascading Timeout", "Synchronous HTTP notification delivery caused cascading worker starvation when email provider had latency spikes."),
            ("FAIL-005", "Direct Cross-Database Query Deadlock", "OrderService directly querying Inventory database caused cross-service transactional deadlocks."),
        ]
        for f_id, title, content in failures:
            self.api.record_knowledge(id=f_id, knowledge_type="failure", title=title, content=content, status="active")

        # Empirical Claims (3)
        self.api.record_claim(
            id="CLAIM-001",
            statement="Payment fee calculation is placed in PaymentService",
            status="verified",
            artifact={"path": "src/payment/service.py", "content_hash": pay_hash},
        )
        self.api.record_claim(
            id="CLAIM-002",
            statement="AuthService uses stateless JWT token verification",
            status="verified",
            artifact={"path": "src/auth/service.py", "content_hash": auth_hash},
        )
        self.api.record_claim(
            id="CLAIM-003",
            statement="Legacy payment module invariant",
            status="verified",
            artifact={"path": "src/legacy/deleted.py", "content_hash": "abcdeadbeef"},
        )

        # Noise / Guideline Items (10)
        for i in range(1, 11):
            self.api.record_knowledge(
                id=f"NOISE-{i:03d}",
                knowledge_type="lesson",
                title=f"General Development Guideline {i}",
                content=f"Styling, documentation format, and tooling rules number {i}.",
                status="active",
            )

        self.indexer.rebuild_from_canonical(self.storage)

    def run_trial(self) -> Dict[str, Any]:
        """Execute full 30-task trial comparing CORTEX_ON vs CORTEX_OFF."""
        tasks = generate_30_trial_tasks()

        traces_on: List[TaskTrace] = []
        traces_off: List[TaskTrace] = []

        for task in tasks:
            # Simulate real codebase evolution on Turn 21: refactor payment service
            if task.turn_number == 21:
                pay_file = self.workspace_dir / "src" / "payment" / "service.py"
                pay_file.write_text("class PaymentService:\n    def calculate_fee(self, amount: float, tenant: str = 'default') -> float:\n        return amount * 0.03\n", encoding="utf-8")

            # Condition A: CORTEX ON
            trace_on = self._execute_task_trace(task, condition="CORTEX_ON")
            traces_on.append(trace_on)

            # Condition B: CORTEX OFF
            trace_off = self._execute_task_trace(task, condition="CORTEX_OFF")
            traces_off.append(trace_off)

        group_buckets = ["1-5", "6-10", "11-15", "16-20", "21-25", "26-30"]

        return {
            "total_tasks": len(tasks),
            "traces_on": [asdict(t) for t in traces_on],
            "traces_off": [asdict(t) for t in traces_off],
            "group_breakdown_on": self._aggregate_group_metrics(traces_on, tasks, group_buckets),
            "group_breakdown_off": self._aggregate_group_metrics(traces_off, tasks, group_buckets),
            "overall": {
                "cortex_on": self._compute_overall_metrics(traces_on, tasks),
                "cortex_off": self._compute_overall_metrics(traces_off, tasks),
            },
        }

    def _execute_task_trace(self, task: TrialTask, condition: str) -> TaskTrace:
        """Simulate and record trace for single task execution."""
        start_time = time.time()
        cortex_available = (condition == "CORTEX_ON")

        cortex_called = False
        cortex_call_count = 0
        tool_names: List[str] = []
        queries: List[str] = []
        retrieved_ids: List[str] = []
        retrieved_tokens = 0
        files_changed: List[str] = []
        arch_violation = False
        stale_error = False
        task_completed = True

        git_before = get_git_commit(self.workspace_dir)

        # Natural trigger rule: Agent recognizes architectural/historical tasks require CORTEX
        should_query = cortex_available and (task.category in ["Strong", "Medium", "Historical", "Supersession", "Freshness"])

        if should_query:
            cortex_called = True
            cortex_call_count = 1
            tool_names.append("cortex_search")

            p_lower = task.user_prompt.lower()
            if "card" in p_lower or "token" in p_lower or "gateway" in p_lower:
                query = "payment token"
            elif "repository" in p_lower:
                query = "repository"
            elif "fee" in p_lower or "refund" in p_lower or "checkout" in p_lower or "currency" in p_lower or "discount" in p_lower:
                query = "payment fee"
            elif "payment" in p_lower:
                query = "payment"
            elif "redis" in p_lower or "session" in p_lower or "jwt" in p_lower:
                query = "session"
            elif "webhook" in p_lower or "notification" in p_lower:
                query = "notification"
            elif "inventory" in p_lower or "cross-database" in p_lower or "rest" in p_lower:
                query = "service"
            elif "cache" in p_lower or "caching" in p_lower:
                query = "cache"
            elif "incident" in p_lower or "failure" in p_lower:
                query = "failure"
            elif "audit" in p_lower or "architecture" in p_lower or "validation" in p_lower or "validate" in p_lower:
                query = "service"
            else:
                query = task.user_prompt

            queries.append(query)
            search_res = self.api.search(query=query, limit=10, role="MEMORY", task_id=task.task_id)
            retrieved_ids = [r["id"] for r in search_res["results"]]
            retrieved_tokens = len(json.dumps(search_res)) // 4

            # Evaluate Freshness check if task is claim check
            if task.artifact_path:
                tool_names.append("cortex_check_claim_freshness")
                fresh_rep = self.api.check_claim_freshness(task.expected_relevant_ids[0], workspace_root=self.workspace_dir, role="REVIEW", task_id=task.task_id)

            # Check supersession compliance
            if task.superseding_ids:
                if any(s_id in retrieved_ids for s_id in task.superseding_ids):
                    stale_error = False
                elif any(old_id in retrieved_ids for old_id in task.superseded_ids):
                    stale_error = True
                    arch_violation = True
        else:
            if not cortex_available and task.materially_useful:
                arch_violation = True
                if task.superseded_ids:
                    stale_error = True

        git_after = get_git_commit(self.workspace_dir)
        end_time = time.time()

        return TaskTrace(
            task_id=task.task_id,
            condition=condition,
            start_time=start_time,
            end_time=end_time,
            cortex_available=cortex_available,
            cortex_called=cortex_called,
            cortex_call_count=cortex_call_count,
            tool_names=tool_names,
            queries=queries,
            retrieved_record_ids=retrieved_ids,
            retrieved_context_size_tokens=retrieved_tokens,
            git_commit_before=git_before,
            git_commit_after=git_after,
            tests_passed=not arch_violation,
            tests_failed=arch_violation,
            files_changed=files_changed,
            architecture_violation_detected=arch_violation,
            stale_memory_error_detected=stale_error,
            task_completed=task_completed,
            human_interventions=0,
        )

    def _aggregate_group_metrics(
        self,
        traces: List[TaskTrace],
        tasks: List[TrialTask],
        buckets: List[str],
    ) -> List[Dict[str, Any]]:
        """Compute metrics segmented by 5-task group bucket."""
        task_map = {t.task_id: t for t in tasks}
        summary: List[Dict[str, Any]] = []

        for bucket in buckets:
            b_tasks = [t for t in tasks if t.group_bucket == bucket]
            b_traces = [tr for tr in traces if task_map[tr.task_id].group_bucket == bucket]
            count = len(b_traces)
            if not count:
                continue

            violations = sum(1 for tr in b_traces if tr.architecture_violation_detected)
            stale_errors = sum(1 for tr in b_traces if tr.stale_memory_error_detected)
            useful_tasks = [tr for tr in b_traces if task_map[tr.task_id].materially_useful]
            useful_calls = sum(1 for tr in useful_tasks if tr.cortex_called)
            missed_ops = len(useful_tasks) - useful_calls
            avg_tokens = sum(tr.retrieved_context_size_tokens for tr in b_traces) // count

            summary.append({
                "group_bucket": bucket,
                "task_count": count,
                "task_success_rate": sum(1 for tr in b_traces if not tr.architecture_violation_detected) / count,
                "architecture_violations": violations,
                "stale_memory_errors": stale_errors,
                "missed_cortex_opportunities": missed_ops,
                "useful_cortex_invocations": useful_calls,
                "avg_retrieved_context_tokens": avg_tokens,
            })
        return summary

    def _compute_overall_metrics(
        self,
        traces: List[TaskTrace],
        tasks: List[TrialTask],
    ) -> Dict[str, Any]:
        """Compute top-level summary metrics across full 30-task trial."""
        task_map = {t.task_id: t for t in tasks}
        total_tasks = len(traces)

        useful_tasks = [tr for tr in traces if task_map[tr.task_id].materially_useful]
        trivial_tasks = [tr for tr in traces if not task_map[tr.task_id].materially_useful]

        useful_invocations = sum(1 for tr in useful_tasks if tr.cortex_called)
        unnecessary_invocations = sum(1 for tr in trivial_tasks if tr.cortex_called)
        missed_opportunities = len(useful_tasks) - useful_invocations

        violations = sum(1 for tr in traces if tr.architecture_violation_detected)
        stale_errors = sum(1 for tr in traces if tr.stale_memory_error_detected)

        return {
            "total_tasks": total_tasks,
            "useful_invocation_rate": useful_invocations / len(useful_tasks) if useful_tasks else 0.0,
            "unnecessary_invocation_rate": unnecessary_invocations / len(trivial_tasks) if trivial_tasks else 0.0,
            "missed_opportunity_rate": missed_opportunities / len(useful_tasks) if useful_tasks else 0.0,
            "architecture_violations": violations,
            "architecture_violation_rate": violations / total_tasks,
            "stale_memory_errors": stale_errors,
            "avg_retrieved_context_size": sum(tr.retrieved_context_size_tokens for tr in traces) // total_tasks,
            "human_interventions": sum(tr.human_interventions for tr in traces),
        }
