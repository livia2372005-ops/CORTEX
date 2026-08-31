"""Tests for CORTEX Phase 9 Context Engineering & Memory Injection Experiments."""

import unittest

from cortex_engine.context_engineering import ContextEngineeringStudy
from cortex_engine.models import Claim, Evidence, Knowledge


class TestContextEngineering(unittest.TestCase):
    def setUp(self):
        self.study = ContextEngineeringStudy()
        self.con = Knowledge(
            id="CON-001",
            type="constraint",
            title="Service Layer Business Logic",
            content="Business logic belongs in Service classes, never in Repositories.",
            status="active",
        )
        self.dec_active = Knowledge(
            id="DEC-007",
            type="decision",
            title="Stateless JWT Sessions",
            content="Use stateless signed JWTs for session auth.",
            status="active",
            supersedes="DEC-002",
        )
        self.dec_old = Knowledge(
            id="DEC-002",
            type="decision",
            title="Redis Sessions",
            content="Use Redis cluster for session storage.",
            status="superseded",
        )
        self.fail_item = Knowledge(
            id="FAIL-001",
            type="failure",
            title="Fee Logic in Repo",
            content="Putting fee calculation in Repository caused migration lockups.",
            status="active",
        )
        self.noise_item = Knowledge(
            id="NOISE-009",
            type="lesson",
            title="CLI Markdown Format",
            content="Use bullet lists when printing help menus.",
            status="active",
        )
        self.evid_item = Evidence(
            id="EVID-001",
            type="artifact",
            path="src/payment/service.py",
            content_hash="abc12345def",
            commit="f4a56b7",
        )
        self.claim_item = Claim(
            id="CLAIM-001",
            statement="Payment fee calculation is placed in PaymentService",
            status="verified",
            artifact={"path": "src/payment/service.py", "content_hash": "abc12345def"},
        )

    def test_context_layout_variations(self):
        """Verify generation and token structure of 4 distinct context layouts."""
        task = "Implement refund fee calculation."
        items = [self.con, self.dec_active]
        evids = [self.evid_item]

        l1 = self.study.build_layout_1(task, items)
        l2 = self.study.build_layout_2(task, items)
        l3 = self.study.build_layout_3(task, items, evids)
        l4 = self.study.build_layout_4(task, items, evids)

        self.assertIn("=== SYSTEM STABLE ===", l1)
        self.assertIn("=== CURRENT TASK ===", l1)
        self.assertIn("=== CRITICAL CONSTRAINTS ===", l3)
        self.assertIn("=== CRITICAL CONSTRAINTS ===", l4)
        self.assertIn("=== EVIDENCE ===", l4)

        # In Layout 4, CRITICAL CONSTRAINTS precedes CURRENT TASK
        pos_con = l4.find("=== CRITICAL CONSTRAINTS ===")
        pos_task = l4.find("=== CURRENT TASK ===")
        self.assertLess(pos_con, pos_task)

    def test_structured_section_partitioning(self):
        """Test Condition D: partitioning into TASK, CONSTRAINTS, DECISIONS, FAILURES, EVIDENCE, and HISTORICAL CONTEXT."""
        task = "Evaluate session authentication architecture."
        items = [self.con, self.dec_active, self.fail_item, self.noise_item]
        claims = [self.claim_item]
        evids = [self.evid_item]

        prompt = self.study.build_structured_sections(task, items, claims, evids)

        self.assertIn("### TASK", prompt)
        self.assertIn("### CRITICAL CONSTRAINTS", prompt)
        self.assertIn("### ACTIVE DECISIONS", prompt)
        self.assertIn("### RELEVANT FAILURES", prompt)
        self.assertIn("### CLAIMS & FRESHNESS", prompt)
        self.assertIn("### EVIDENCE", prompt)
        self.assertIn("### HISTORICAL CONTEXT", prompt)

    def test_memory_contamination_experiment(self):
        """Verify contamination evaluation: relevant vs weak vs irrelevant noise."""
        task = "Implement payment fee calculation in service layer."
        result = self.study.evaluate_memory_contamination(
            task=task,
            relevant_item=self.dec_active,
            weak_item=self.fail_item,
            irrelevant_item=self.noise_item,
        )

        self.assertTrue(result["correct_decision"])
        self.assertTrue(result["ignored_irrelevant_memory"])
        self.assertFalse(result["interference_detected"])
        self.assertEqual(result["behavior"], "adhered_to_relevant_ignored_irrelevant")

    def test_memory_overload_experiment(self):
        """Verify overload across 100, 300, 1000, 3000, and 7000 token targets."""
        task = "Refactor payment checkout flow."
        results = self.study.evaluate_memory_overload(task, self.con)

        self.assertEqual(len(results), 5)
        # Small memory budgets (100, 300, 1000) have 0.0 distraction
        self.assertEqual(results[0].distraction_score, 0.0)
        self.assertEqual(results[1].distraction_score, 0.0)
        self.assertEqual(results[2].distraction_score, 0.0)

        # Large memory budget (7000) shows interference and high distraction
        self.assertTrue(results[4].interference_detected)
        self.assertEqual(results[4].distraction_score, 0.40)

    def test_structured_vs_prose_formatting(self):
        """Verify that structured formatters include explicit IDs, status, provenance, and supersession."""
        # 1. Constraint
        c_prose = self.study.format_constraint_prose(self.con)
        c_struct = self.study.format_constraint_structured(self.con)
        self.assertIn("Previously, the engineering team", c_prose)
        self.assertIn("CONSTRAINT: [CON-001]", c_struct)
        self.assertIn("STATUS: ACTIVE", c_struct)

        # 2. Decision
        d_prose = self.study.format_decision_prose(self.dec_active)
        d_struct = self.study.format_decision_structured(self.dec_active)
        self.assertIn("SUPERSEDES: DEC-002", d_struct)
        self.assertIn("DECISION: [DEC-007]", d_struct)

        # 3. Evidence
        e_prose = self.study.format_evidence_prose(self.evid_item)
        e_struct = self.study.format_evidence_structured(self.evid_item)
        self.assertIn("The previous implementation had failures", e_prose)
        self.assertIn("EVIDENCE: [EVID-001]", e_struct)
        self.assertIn("HASH: abc12345def", e_struct)


if __name__ == "__main__":
    unittest.main()
