"""Tests for CORTEX Phase 11 Native Antigravity Packaging & CLI Diagnostics."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cortex_engine import __version__
from cortex_engine.cli import CortexCLI
from cortex_engine.models import Knowledge


class TestPackagingAndDiagnostics(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.cli = CortexCLI(workspace_root=self.workspace)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_plugin_manifest_validity(self):
        """Verify plugin.json schema, version, and component references."""
        self.cli.cmd_init()
        manifest_p = self.workspace / ".agents" / "plugins" / "cortex" / "plugin.json"
        self.assertTrue(manifest_p.exists())

        with open(manifest_p, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["name"], "cortex")
        self.assertEqual(data["version"], __version__)
        self.assertIn("Persistent project memory", data["description"])
        self.assertIn("rules/cortex-awareness.md", data["components"]["rules"])
        self.assertIn("skills/cortex-memory", data["components"]["skills"])

    def test_plugin_file_discovery(self):
        """Verify all declared plugin rules and skills exist on disk."""
        self.cli.cmd_init()
        plugin_root = self.workspace / ".agents" / "plugins" / "cortex"

        self.assertTrue((plugin_root / "rules" / "cortex-awareness.md").exists())
        self.assertTrue((plugin_root / "skills" / "cortex-memory" / "SKILL.md").exists())
        self.assertTrue((plugin_root / "skills" / "cortex-review" / "SKILL.md").exists())
        self.assertTrue((plugin_root / "skills" / "cortex-learning" / "SKILL.md").exists())
        self.assertTrue((plugin_root / "mcp_config.json").exists())

    def test_mcp_config_validity(self):
        """Verify plugin mcp_config.json points to cortex_engine.mcp_server."""
        self.cli.cmd_init()
        mcp_p = self.workspace / ".agents" / "plugins" / "cortex" / "mcp_config.json"
        with open(mcp_p, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("cortex-mcp", data["mcpServers"])
        server_cfg = data["mcpServers"]["cortex-mcp"]
        self.assertEqual(server_cfg["command"], "python")
        self.assertIn("cortex_engine.mcp_server", server_cfg["args"])

    def test_clean_workspace_installation(self):
        """Verify clean workspace initialization creates canonical and plugin structures."""
        res = self.cli.cmd_init()
        self.assertEqual(res["status"], "initialized")
        self.assertTrue((self.workspace / ".cortex" / "knowledge").exists())
        self.assertTrue((self.workspace / ".cortex" / "events").exists())
        self.assertTrue((self.workspace / ".cortex" / "indexes" / "cortex.db").exists())

    def test_existing_project_installation_preservation(self):
        """Verify init does not overwrite existing non-CORTEX rules/skills in .agents/."""
        custom_rule = self.workspace / ".agents" / "rules" / "my-custom-rule.md"
        custom_rule.parent.mkdir(parents=True, exist_ok=True)
        custom_rule.write_text("Custom user rule content", encoding="utf-8")

        self.cli.cmd_init()

        self.assertTrue(custom_rule.exists())
        self.assertEqual(custom_rule.read_text(encoding="utf-8"), "Custom user rule content")

    def test_version_reporting(self):
        """Verify cortex --version returns correct version string."""
        ver_str = self.cli.cmd_version()
        self.assertIn(__version__, ver_str)
        self.assertIn("CORTEX v", ver_str)

    def test_doctor_command_integrity(self):
        """Verify doctor runs non-mutating checks and passes on clean init."""
        self.cli.cmd_init()
        doc = self.cli.cmd_doctor()
        self.assertIn(doc["overall"], ["PASS", "WARN"])

        checks = {c["name"]: c["status"] for c in doc["checks"]}
        self.assertEqual(checks["Python Runtime"], "PASS")
        self.assertEqual(checks["Canonical Storage"], "PASS")
        self.assertEqual(checks["Derived Index"], "PASS")
        self.assertEqual(checks["Antigravity Plugin"], "PASS")

    def test_status_command_diagnostics(self):
        """Verify status reports accurate record counts and plugin configuration."""
        self.cli.cmd_init()
        self.cli.storage.write_knowledge(
            Knowledge(id="CON-001", type="constraint", title="Title", content="Content", status="active")
        )
        self.cli.indexer.rebuild_from_canonical(self.cli.storage)

        st = self.cli.cmd_status()
        self.assertEqual(st["version"], __version__)
        self.assertEqual(st["record_counts"]["constraints"], 1)
        self.assertEqual(st["total_records"], 1)
        self.assertEqual(st["index_status"], "HEALTHY")
        self.assertTrue(st["antigravity_plugin_configured"])

    def test_missing_or_corrupt_derived_index_diagnostics(self):
        """Verify doctor detects missing index and reindex fixes it."""
        self.cli.cmd_init()
        db_path = self.workspace / ".cortex" / "indexes" / "cortex.db"
        if db_path.exists():
            db_path.unlink()

        doc1 = self.cli.cmd_doctor()
        checks1 = {c["name"]: c["status"] for c in doc1["checks"]}
        self.assertEqual(checks1["Derived Index"], "WARN")

        # Reindex
        self.cli.cmd_reindex()
        doc2 = self.cli.cmd_doctor()
        checks2 = {c["name"]: c["status"] for c in doc2["checks"]}
        self.assertEqual(checks2["Derived Index"], "PASS")

    def test_configuration_conflict_detection(self):
        """Verify doctor detects missing plugin files."""
        self.cli.cmd_init()
        manifest_p = self.workspace / ".agents" / "plugins" / "cortex" / "plugin.json"
        manifest_p.unlink()

        doc = self.cli.cmd_doctor()
        checks = {c["name"]: c["status"] for c in doc["checks"]}
        self.assertEqual(checks["Antigravity Plugin"], "WARN")

    def test_canonical_data_preservation_during_reinit(self):
        """Verify running init again preserves canonical records on disk."""
        self.cli.cmd_init()
        k = Knowledge(id="DEC-001", type="decision", title="Test Dec", content="Statement", status="active")
        self.cli.storage.write_knowledge(k)

        # Re-initialize
        self.cli.cmd_init()

        read_k = self.cli.storage.read_knowledge("DEC-001")
        self.assertIsNotNone(read_k)
        self.assertEqual(read_k.content, "Statement")


if __name__ == "__main__":
    unittest.main()
