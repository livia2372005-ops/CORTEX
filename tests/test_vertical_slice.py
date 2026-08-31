"""Integration and vertical slice tests demonstrating ONE Agent CORTEX workflows."""

import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.api import CortexAPI
from cortex_engine.models import ContextPackage, RoleContext, RoleResult
from cortex_engine.storage import CortexStorage


class TestVerticalSliceAndContextIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CortexStorage(cortex_dir=self.temp_dir)
        self.api = CortexAPI(storage=self.storage)

        # Seed historical knowledge into the fixture
        self.api.record_knowledge(
            id="DEC-001",
            knowledge_type="decision",
            title="Layered Architecture: Business Logic in Services",
            content="All business logic, fee computations, and validation must reside in the Service layer, not in Repository.",
            status="active",
            provenance={"commit": "init_arch", "doc": "architecture.md"},
            task_id="INIT",
        )
        self.api.record_knowledge(
            id="FAIL-001",
            knowledge_type="failure",
            title="Business Logic in Repository Failure",
            content="Placing currency conversion logic inside PaymentRepository broke database migrations and unit test mocking.",
            status="active",
            provenance={"incident_id": "INC-889"},
            task_id="INIT",
        )
        self.api.record_knowledge(
            id="CON-001",
            knowledge_type="constraint",
            title="Repository Boundary Invariant",
            content="Repositories must only execute direct persistence operations and return data models.",
            status="active",
            provenance={"rule_id": "ARCH-01"},
            task_id="INIT",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_structured_search_result_contract(self):
        """Verify cortex.search returns structured evidence and observable events, not generated instructions."""
        search_res = self.api.search("business logic", task_id="T-100", role="MEMORY")

        self.assertIn("query", search_res)
        self.assertIn("results", search_res)
        self.assertIn("count", search_res)
        self.assertEqual(search_res["query"], "business logic")
        self.assertGreaterEqual(search_res["count"], 2)

        # Verify results contain raw evidence properties
        first_result = search_res["results"][0]
        self.assertIn("id", first_result)
        self.assertIn("type", first_result)
        self.assertIn("title", first_result)
        self.assertIn("content", first_result)
        self.assertIn("provenance", first_result)

        # Verify search does NOT synthesize directive instructions
        for res in search_res["results"]:
            self.assertFalse(res["content"].lower().startswith("you must"))

        # Verify observable event was recorded
        events = self.storage.read_events(event_type="memory_retrieval")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].role, "MEMORY")
        self.assertEqual(events[0].payload["query"], "business logic")
        self.assertIn("DEC-001", events[0].payload["result_ids"])

    def test_cortex_get_and_observable_event(self):
        """Verify cortex.get retrieves structured record and logs observable access event."""
        item = self.api.get("DEC-001", task_id="T-101", role="MEMORY")
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "DEC-001")
        self.assertEqual(item["type"], "decision")

        events = self.storage.read_events(event_type="memory_get")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["id"], "DEC-001")
        self.assertTrue(events[0].payload["found"])

    def test_role_context_isolation_and_no_leakage(self):
        """Test that switching APP -> MEMORY -> APP maintains strict context boundaries.
        
        Working variables and private reasoning from MEMORY must NOT leak into APP context.
        """
        # Step 1: Initial APP context
        app_stable = {"role": "APP", "instructions": "Write clean Python code adhering to project architecture."}
        app_dynamic = {
            "task": "Refactor payment processing",
            "active_file": "services/payment.py",
            "private_scratch": "Initial thought: where should validation go?",
        }
        app_ctx = self.api.create_role_context(
            role="APP",
            stable_context=app_stable,
            dynamic_context=app_dynamic,
            available_tools=["edit_file", "run_test"],
            task_id="TASK-REF-01",
        )

        # Step 2: Transition to MEMORY role (clean context)
        mem_stable = {"role": "MEMORY", "instructions": "Retrieve relevant historical constraints and evidence."}
        mem_ctx = self.api.transition_role(
            from_context=app_ctx,
            to_role="MEMORY",
            to_stable_context=mem_stable,
            to_tools=["cortex.search", "cortex.get"],
            transfer_payload={"search_target": "payment business logic architecture"},
        )

        # Verify MEMORY role context does NOT have app private scratch
        self.assertEqual(mem_ctx.role, "MEMORY")
        self.assertEqual(mem_ctx.available_tools, ["cortex.search", "cortex.get"])
        self.assertNotIn("private_scratch", mem_ctx.dynamic_context)
        self.assertNotIn("active_file", mem_ctx.dynamic_context)

        # Step 3: MEMORY role performs search
        search_res = self.api.search("business logic", task_id="TASK-REF-01", role="MEMORY")
        
        # Structure findings as a RoleResult
        role_result = self.api.serialize_role_result(
            source_role="MEMORY",
            result_type="memory_evidence",
            items=search_res["results"],
            provenance=[{"source": "local_knowledge"}],
        )

        # Step 4: Transition back to APP role with ONLY the structured result
        app_ctx_resumed = self.api.transition_role(
            from_context=mem_ctx,
            to_role="APP",
            to_stable_context=app_stable,
            to_tools=["edit_file", "run_test"],
            transfer_payload={
                "task": "Refactor payment processing",
                "active_file": "services/payment.py",
                "retrieved_evidence": role_result,
            },
        )

        # Verify APP context contains structured evidence but NO unexported MEMORY working state
        self.assertEqual(app_ctx_resumed.role, "APP")
        self.assertIn("retrieved_evidence", app_ctx_resumed.dynamic_context)
        self.assertEqual(app_ctx_resumed.dynamic_context["retrieved_evidence"]["source_role"], "MEMORY")
        self.assertEqual(len(app_ctx_resumed.dynamic_context["retrieved_evidence"]["items"]), search_res["count"])

        # Check recorded role_transition events
        trans_events = self.storage.read_events(event_type="role_transition")
        self.assertEqual(len(trans_events), 2)
        self.assertEqual(trans_events[0].payload["from_role"], "APP")
        self.assertEqual(trans_events[0].payload["to_role"], "MEMORY")
        self.assertEqual(trans_events[1].payload["from_role"], "MEMORY")
        self.assertEqual(trans_events[1].payload["to_role"], "APP")

    def test_context_package_role_separation(self):
        """Verify ContextPackage cleanly formats stable prefix and dynamic suffix per role."""
        app_pkg = self.api.create_context_package(
            stable={"role": "APP", "guidelines": "Layered services"},
            dynamic={"task": "Refactor payment"},
            role="APP",
            task_id="TASK-1",
        )
        mem_pkg = self.api.create_context_package(
            stable={"role": "MEMORY", "guidelines": "Search evidence"},
            dynamic={"query": "business logic"},
            role="MEMORY",
            task_id="TASK-1",
        )

        self.assertEqual(app_pkg.role, "APP")
        self.assertEqual(mem_pkg.role, "MEMORY")
        self.assertNotEqual(app_pkg.stable, mem_pkg.stable)
        self.assertNotEqual(app_pkg.dynamic, mem_pkg.dynamic)

    def test_end_to_end_deterministic_workflow_simulation(self):
        """End-to-end vertical slice:
        Task: Refactor payment module.
        Agent inspects CORTEX evidence -> discovers DEC-001 and FAIL-001 -> places validation in Service.
        """
        task_id = "TASK-PAYMENT-REFACTOR"

        # 1. User assigns task: "Refactor payment functionality to compute processing fees"
        # 2. Agent initializes in APP role
        app_context = self.api.create_role_context(
            role="APP",
            stable_context={"guidelines": "Standard Python service architecture"},
            dynamic_context={"task_prompt": "Refactor payment functionality to compute processing fees"},
            available_tools=["cortex.search", "write_file", "run_test"],
            task_id=task_id,
        )

        # 3. Agent queries CORTEX memory for architectural decisions regarding business logic & payments
        search_evidence = self.api.search("business logic", task_id=task_id, role="MEMORY")
        retrieved_ids = [item["id"] for item in search_evidence["results"]]
        self.assertIn("DEC-001", retrieved_ids)
        self.assertIn("FAIL-001", retrieved_ids)

        # 4. Agent independently reasons over evidence:
        # DEC-001 specifies fee computations belong in Service layer.
        # FAIL-001 warns against placing logic in Repository.
        chosen_implementation_layer = "Service"  # Agent decision based on evidence
        self.assertEqual(chosen_implementation_layer, "Service")

        # 5. Agent writes service code in demo directory
        demo_service_path = Path(self.temp_dir) / "payment_service.py"
        demo_service_code = (
            "class PaymentService:\n"
            "    def calculate_fee(self, amount: float) -> float:\n"
            "        # Business logic strictly placed in Service layer per DEC-001\n"
            "        return amount * 0.025\n"
        )
        demo_service_path.write_text(demo_service_code, encoding="utf-8")

        # 6. Agent records task completion event
        self.api.record_event(
            event_type="task_completed",
            role="APP",
            payload={
                "task_id": task_id,
                "adhered_decisions": ["DEC-001"],
                "target_file": str(demo_service_path),
            },
            task_id=task_id,
        )

        # 7. Verify observable event stream completeness
        all_events = self.storage.read_events(task_id=task_id)
        event_types = [e.type for e in all_events]
        self.assertIn("memory_retrieval", event_types)
        self.assertIn("task_completed", event_types)


if __name__ == "__main__":
    unittest.main()
