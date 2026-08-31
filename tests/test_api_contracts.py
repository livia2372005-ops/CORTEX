"""Tests for CORTEX API, role context contracts, and boundary serialization."""

import shutil
import tempfile
import unittest

from cortex_engine.api import CortexAPI
from cortex_engine.models import ContextPackage, RoleContext, RoleResult
from cortex_engine.storage import CortexStorage


class TestCortexAPIContracts(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CortexStorage(cortex_dir=self.temp_dir)
        self.api = CortexAPI(storage=self.storage)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_context_package_creation(self):
        """Test creating layered ContextPackage separating stable and dynamic context."""
        pkg = self.api.create_context_package(
            stable={"role": "APP", "rules": ["protocol-v1"]},
            dynamic={"task": "implement feature", "diff": "+ def foo(): pass"},
        )
        self.assertIsInstance(pkg, ContextPackage)
        pkg_dict = pkg.to_dict()
        self.assertIn("stable", pkg_dict)
        self.assertIn("dynamic", pkg_dict)
        self.assertEqual(pkg_dict["stable"]["role"], "APP")
        self.assertEqual(pkg_dict["dynamic"]["task"], "implement feature")

    def test_role_context_creation(self):
        """Test RoleContext model and its transformation into a ContextPackage."""
        ctx = self.api.create_role_context(
            role="MEMORY",
            stable_context="Stable memory instructions",
            dynamic_context={"query": "find constraints"},
            available_tools=["cortex.search", "cortex.get"],
            task_id="TASK-42",
        )
        self.assertIsInstance(ctx, RoleContext)
        self.assertEqual(ctx.role, "MEMORY")
        self.assertIn("cortex.search", ctx.available_tools)

        pkg = ctx.to_package()
        self.assertEqual(pkg.stable, "Stable memory instructions")
        self.assertEqual(pkg.dynamic, {"query": "find constraints"})

    def test_role_boundary_serialization(self):
        """Test that RoleResult transfers only structured outcomes without leaking private reasoning."""
        res_dict = self.api.serialize_role_result(
            source_role="MEMORY",
            result_type="memory_evidence",
            items=[{"id": "CON-001", "text": "No external heavy DBs"}],
            provenance=[{"source": ".cortex/knowledge/constraints/CON-001.json"}],
        )
        self.assertEqual(res_dict["source_role"], "MEMORY")
        self.assertEqual(res_dict["result_type"], "memory_evidence")
        self.assertEqual(len(res_dict["items"]), 1)
        self.assertEqual(len(res_dict["provenance"]), 1)
        # Verify round-trip parsing
        parsed = RoleResult.from_dict(res_dict)
        self.assertEqual(parsed.source_role, "MEMORY")
        self.assertEqual(parsed.items[0]["id"], "CON-001")

    def test_api_record_and_search(self):
        """Test high level API recording and search over persistent knowledge."""
        self.api.record_knowledge(
            id="LESSON-01",
            knowledge_type="lesson",
            title="Isolate Role Contexts",
            content="Prevent reasoning leakage by passing only structured result objects.",
        )
        self.api.record_knowledge(
            id="DEC-02",
            knowledge_type="decision",
            title="Single Agent Architecture",
            content="Use one Agent operating across distinct role modes.",
        )

        matches = self.api.search("reasoning leakage")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["id"], "LESSON-01")

        retrieved = self.api.get("DEC-02", category="decisions")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["title"], "Single Agent Architecture")

    def test_claim_recording_via_api(self):
        """Test recording and retrieving claims via API."""
        self.api.record_claim(
            id="CLAIM-002",
            statement="Role switches do not leak private thoughts.",
            status="unverified",
        )
        retrieved = self.api.get_claim("CLAIM-002")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
