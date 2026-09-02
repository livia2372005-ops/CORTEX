"""Tests for CORTEX Native Antigravity Hook Agent Observability."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cortex_engine import (
    ActivityEvent,
    CortexAPI,
    CortexStorage,
)
from cortex_engine.antigravity_hook import (
    extract_target,
    process_hook_payload,
    sanitize_args_metadata,
)
from cortex_engine.cli import CortexCLI


class TestAntigravityHookObservability(unittest.TestCase):
    """Test suite for native Antigravity PreToolUse / PostToolUse hook observation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="cortex_hook_test_")
        self.workspace_path = Path(self.temp_dir)
        self.cortex_dir = self.workspace_path / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.api = CortexAPI(storage=self.storage)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. PreToolUse Payload Handling
    # -------------------------------------------------------------------------

    def test_pre_tool_use_payload_handling(self) -> None:
        """Verify PreToolUse parses tool info, records started event, and returns allow."""
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "git status --short",
                    "Cwd": str(self.workspace_path),
                },
            },
            "stepIdx": 10,
            "conversationId": "conv-test-123",
            "workspacePaths": [str(self.workspace_path)],
        }
        res = process_hook_payload("pre", json.dumps(payload))
        self.assertEqual(res.get("decision"), "allow")

        # Verify activity was appended
        activities = self.storage.read_activity(conversation_id="conv-test-123")
        self.assertEqual(len(activities), 1)
        evt = activities[0]
        self.assertEqual(evt.action_type, "tool_call")
        self.assertEqual(evt.source, "antigravity_hook")
        self.assertEqual(evt.tool_name, "run_command")
        self.assertEqual(evt.target, "git status --short")
        self.assertEqual(evt.status, "started")
        self.assertEqual(evt.step_index, 10)
        self.assertEqual(evt.correlation_id, "step-conv-test-123-10")

    # -------------------------------------------------------------------------
    # 2. PostToolUse Payload Handling & Result Correlation
    # -------------------------------------------------------------------------

    def test_post_tool_use_success_and_correlation(self) -> None:
        """Verify PostToolUse records tool_result event linked to PreToolUse."""
        # 1. Pre event
        pre_payload = {
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/app/service.py"},
            },
            "stepIdx": 1,
            "conversationId": "conv-corr-456",
            "workspacePaths": [str(self.workspace_path)],
        }
        process_hook_payload("pre", json.dumps(pre_payload))

        # 2. Post event
        post_payload = {
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/app/service.py"},
            },
            "stepIdx": 1,
            "conversationId": "conv-corr-456",
            "workspacePaths": [str(self.workspace_path)],
        }
        post_res = process_hook_payload("post", json.dumps(post_payload))
        self.assertEqual(post_res, {})

        activities = self.storage.read_activity(conversation_id="conv-corr-456")
        self.assertEqual(len(activities), 2)

        pre_evt = activities[0]
        post_evt = activities[1]

        self.assertEqual(pre_evt.action_type, "tool_call")
        self.assertEqual(post_evt.action_type, "tool_result")
        self.assertEqual(post_evt.status, "success")
        self.assertEqual(pre_evt.correlation_id, "step-conv-corr-456-1")
        self.assertEqual(post_evt.correlation_id, "step-conv-corr-456-1")

    # -------------------------------------------------------------------------
    # 3. PostToolUse Failure Handling & Error Sanitization
    # -------------------------------------------------------------------------

    def test_post_tool_use_error_handling(self) -> None:
        """Verify PostToolUse captures and sanitizes execution errors without crashing."""
        post_err_payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python non_existent_script.py"},
            },
            "stepIdx": 2,
            "error": "FileNotFoundError: [Errno 2] No such file or directory with secret_token=ghp_1234567890abcdef1234567890abcdef1234",
            "conversationId": "conv-err-789",
            "workspacePaths": [str(self.workspace_path)],
        }
        process_hook_payload("post", json.dumps(post_err_payload))

        activities = self.storage.read_activity(conversation_id="conv-err-789")
        self.assertEqual(len(activities), 1)
        evt = activities[0]
        self.assertEqual(evt.status, "error")
        self.assertIsNotNone(evt.error_type)
        self.assertNotIn("ghp_1234567890abcdef1234567890abcdef1234", evt.error_type)
        self.assertIn("[REDACTED]", evt.error_type)

    # -------------------------------------------------------------------------
    # 4. Multi-Step Trajectory Reconstruction
    # -------------------------------------------------------------------------

    def test_trajectory_reconstruction(self) -> None:
        """Verify complete multi-step tool call sequence reconstruction."""
        conv_id = "conv-traj-001"
        steps = [
            ("view_file", {"AbsolutePath": "/src/models.py"}, None),
            ("run_command", {"CommandLine": "pytest tests/"}, None),
            ("replace_file_content", {"TargetFile": "/src/models.py", "Instruction": "fix typo"}, None),
            ("run_command", {"CommandLine": "pytest tests/"}, "exit status 1"),
        ]

        for idx, (tool, args, err) in enumerate(steps):
            pre_p = {
                "toolCall": {"name": tool, "args": args},
                "stepIdx": idx,
                "conversationId": conv_id,
                "workspacePaths": [str(self.workspace_path)],
            }
            process_hook_payload("pre", json.dumps(pre_p))

            post_p = {
                "toolCall": {"name": tool, "args": args},
                "stepIdx": idx,
                "conversationId": conv_id,
                "workspacePaths": [str(self.workspace_path)],
            }
            if err:
                post_p["error"] = err
            process_hook_payload("post", json.dumps(post_p))

        # Reconstruct trajectory
        events = self.storage.read_activity(conversation_id=conv_id)
        self.assertEqual(len(events), 8)  # 4 steps * (1 call + 1 result)

        for idx in range(4):
            call_evt = events[idx * 2]
            res_evt = events[idx * 2 + 1]

            self.assertEqual(call_evt.step_index, idx)
            self.assertEqual(res_evt.step_index, idx)
            self.assertEqual(call_evt.action_type, "tool_call")
            self.assertEqual(res_evt.action_type, "tool_result")
            self.assertEqual(call_evt.tool_name, steps[idx][0])
            self.assertEqual(res_evt.tool_name, steps[idx][0])

        # Step 3 had error
        self.assertEqual(events[7].status, "error")

    # -------------------------------------------------------------------------
    # 5. Generic Tool Matching & Target Extraction
    # -------------------------------------------------------------------------

    def test_generic_tool_target_extraction(self) -> None:
        """Verify target extraction for standard and arbitrary new tool types."""
        self.assertEqual(extract_target("run_command", {"CommandLine": "cargo build"}), "cargo build")
        self.assertEqual(extract_target("view_file", {"AbsolutePath": "/a/b/c.txt"}), "/a/b/c.txt")
        self.assertEqual(extract_target("replace_file_content", {"TargetFile": "/a/b/c.txt"}), "/a/b/c.txt")
        self.assertEqual(extract_target("read_url_content", {"Url": "https://docs.rs"}), "https://docs.rs")
        self.assertEqual(extract_target("custom_deploy_tool", {"cluster": "us-west"}), "custom_deploy_tool")

    # -------------------------------------------------------------------------
    # 6. Redaction of Sensitive Tool Arguments
    # -------------------------------------------------------------------------

    def test_redaction_in_tool_args(self) -> None:
        """Verify secrets in command line, headers, or parameters are redacted before storage."""
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "curl -H 'Authorization: Bearer sk-1234567890abcdef1234567890abcdef' https://api.openai.com",
                    "password": "secret_db_password",
                },
            },
            "stepIdx": 0,
            "conversationId": "conv-sec-01",
            "workspacePaths": [str(self.workspace_path)],
        }
        process_hook_payload("pre", json.dumps(payload))

        raw_file = self.cortex_dir / "events" / "activity.jsonl"
        content = raw_file.read_text(encoding="utf-8")

        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", content)
        self.assertNotIn("secret_db_password", content)
        self.assertIn("[REDACTED]", content)

    # -------------------------------------------------------------------------
    # 7. Malformed Input & Fault Isolation
    # -------------------------------------------------------------------------

    def test_malformed_input_isolation(self) -> None:
        """Verify malformed JSON or empty stdin never raises unhandled exception and yields valid JSON."""
        # Empty string
        res1 = process_hook_payload("pre", "")
        self.assertEqual(res1.get("decision"), "allow")

        # Invalid JSON
        res2 = process_hook_payload("pre", "{invalid json content...")
        self.assertEqual(res2.get("decision"), "allow")

        res3 = process_hook_payload("post", "{invalid json content...")
        self.assertEqual(res3, {})

        # None / missing fields
        res4 = process_hook_payload("pre", json.dumps({"unexpected": "structure"}))
        self.assertEqual(res4.get("decision"), "allow")

    # -------------------------------------------------------------------------
    # 8. CLI Conversation Trajectory Filtering
    # -------------------------------------------------------------------------

    def test_cli_conversation_filtering(self) -> None:
        """Verify CLI 'cortex activity --conversation <id>' retrieves trajectory events."""
        conv_id = "conv-cli-inspect-01"
        payload = {
            "toolCall": {
                "name": "cortex_search",
                "args": {"query": "authentication caching"},
            },
            "stepIdx": 5,
            "conversationId": conv_id,
            "workspacePaths": [str(self.workspace_path)],
        }
        process_hook_payload("pre", json.dumps(payload))

        cli = CortexCLI(workspace_root=self.workspace_path)
        events = cli.cmd_activity(conversation_id=conv_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["tool_name"], "cortex_search")
        self.assertEqual(events[0]["step_index"], 5)


if __name__ == "__main__":
    unittest.main()
