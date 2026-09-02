"""Unit tests for CORTEX Clean Runtime Packaging and Workspace Boundary Invariants."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine.cli import CortexCLI
from cortex_engine.storage import CortexStorage


class TestPackagingBoundaries(unittest.TestCase):
    """Verify runtime initialization isolation and non-pollution of consuming projects."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        # Simulate a consuming application workspace
        self.app_docs = self.workspace / "docs"
        self.app_docs.mkdir(parents=True, exist_ok=True)
        (self.app_docs / "app_architecture.md").write_text("# App Architecture\nAuthoritative app spec.", encoding="utf-8")
        
        self.app_src = self.workspace / "src"
        self.app_src.mkdir(parents=True, exist_ok=True)
        (self.app_src / "main.py").write_text("print('App running')", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cortex_init_does_not_create_reports_or_pollute_app_docs(self) -> None:
        """Verify cortex init creates .cortex/ and .agents/ without touching docs/ or creating docs/reports/."""
        cli = CortexCLI(workspace_root=self.workspace)
        res = cli.cmd_init()

        self.assertEqual(res["status"], "initialized")
        
        # 1. Check that docs/reports was NEVER created
        cortex_reports = self.workspace / "docs" / "reports"
        self.assertFalse(cortex_reports.exists(), "cortex init must NOT create docs/reports/")

        # 2. Check that application docs remain intact
        app_doc_file = self.app_docs / "app_architecture.md"
        self.assertTrue(app_doc_file.exists())
        self.assertEqual(app_doc_file.read_text(encoding="utf-8"), "# App Architecture\nAuthoritative app spec.")

        # 3. Check that .cortex and .agents/plugins/cortex exist
        self.assertTrue((self.workspace / ".cortex").exists())
        self.assertTrue((self.workspace / ".cortex" / "knowledge").exists())
        self.assertTrue((self.workspace / ".cortex" / "events").exists())
        self.assertTrue((self.workspace / ".cortex" / "state").exists())
        self.assertTrue((self.workspace / ".agents" / "plugins" / "cortex" / "plugin.json").exists())
        self.assertTrue((self.workspace / ".agents" / "plugins" / "cortex" / "hooks.json").exists())
        self.assertTrue((self.workspace / ".agents" / "hooks.json").exists())

    def test_awareness_rule_declares_workspace_authority_and_doc_boundary(self) -> None:
        """Verify injected awareness rule explicitly prevents writing application reports into CORTEX."""
        cli = CortexCLI(workspace_root=self.workspace)
        cli.cmd_init()

        rule_path = self.workspace / ".agents" / "plugins" / "cortex" / "rules" / "cortex-awareness.md"
        self.assertTrue(rule_path.exists())
        content = rule_path.read_text(encoding="utf-8")

        self.assertIn("Workspace Authority", content)
        self.assertIn("Documentation Boundary", content)
        self.assertIn("authoritative for application source, documentation, tests, and reports", content)

    def test_cortex_init_is_idempotent_and_preserves_user_files(self) -> None:
        """Verify repeated cortex init does not overwrite modified user assets without --force."""
        cli = CortexCLI(workspace_root=self.workspace)
        cli.cmd_init()

        # User customizes plugin manifest
        manifest_path = self.workspace / ".agents" / "plugins" / "cortex" / "plugin.json"
        custom_data = {"name": "cortex", "version": "0.2.0", "custom_key": "user_preserved_value"}
        manifest_path.write_text(json.dumps(custom_data), encoding="utf-8")

        # Run init again without force
        cli.cmd_init(force=False)
        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded.get("custom_key"), "user_preserved_value", "idempotent init must preserve user edits")

        # Run init with force=True
        cli.cmd_init(force=True)
        reloaded_force = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("custom_key", reloaded_force, "force init resets template")

    def test_clean_runtime_mode_independent_of_dev_repo(self) -> None:
        """Verify clean runtime storage operates fully without CORTEX test suites or dev docs."""
        cli = CortexCLI(workspace_root=self.workspace)
        cli.cmd_init()

        # Confirm tests directory does NOT exist in consuming workspace
        self.assertFalse((self.workspace / "tests").exists())
        self.assertFalse((self.workspace / "docs" / "reports").exists())

        # Storage and Doctor can run cleanly
        doc = cli.cmd_doctor()
        self.assertTrue(doc["healthy"])


if __name__ == "__main__":
    unittest.main()
