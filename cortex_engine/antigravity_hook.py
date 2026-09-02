"""CORTEX Native Antigravity Lifecycle Hook Handler.

Intercepts Antigravity agent lifecycle events (PreToolUse, PostToolUse) to provide
automatic, non-intrusive, privacy-preserving action observability without
capturing private reasoning or requiring manual self-reporting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ActivityEvent, utc_now_iso
from .redaction import redact_data, redact_text
from .storage import CortexStorage


def extract_target(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Intelligently extract the principal target or resource being operated on."""
    if not isinstance(tool_args, dict):
        return tool_name

    if tool_name == "run_command":
        return str(tool_args.get("CommandLine", tool_name))
    elif tool_name in {"view_file", "view_symbol", "show_definition"}:
        return str(tool_args.get("AbsolutePath", tool_args.get("TargetFile", tool_name)))
    elif tool_name in {"replace_file_content", "multi_replace_file_content", "write_to_file"}:
        return str(tool_args.get("TargetFile", tool_args.get("AbsolutePath", tool_name)))
    elif tool_name in {"grep_search", "find_by_name"}:
        path = tool_args.get("SearchPath", "")
        query = tool_args.get("Query", "")
        return f"{path} (query: {query})" if path or query else tool_name
    elif tool_name == "read_url_content":
        return str(tool_args.get("Url", tool_name))
    elif tool_name.startswith("mcp_") or tool_name.startswith("cortex_"):
        return tool_name

    # Generic: pick first recognizable path or name argument
    for key in ("TargetFile", "AbsolutePath", "DirectoryPath", "Url", "CommandLine", "query", "id"):
        if key in tool_args:
            return str(tool_args[key])
    return tool_name


def sanitize_args_metadata(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a high-level, sanitized summary of arguments without dumping sensitive payloads."""
    if not isinstance(tool_args, dict):
        return {}

    summary: Dict[str, Any] = {}
    for k, v in tool_args.items():
        if isinstance(v, (int, float, bool)):
            summary[k] = v
        elif isinstance(v, str):
            # If string is short, store sanitized version; if long, store length
            if len(v) <= 150:
                summary[k] = redact_text(v)
            else:
                summary[k] = f"[str_length={len(v)}]"
        elif isinstance(v, (list, tuple)):
            summary[k] = f"[items_count={len(v)}]"
        elif isinstance(v, dict):
            summary[k] = f"[keys={list(v.keys())}]"
        else:
            summary[k] = f"[{type(v).__name__}]"

    return redact_data(summary)


def resolve_cortex_storage(workspace_paths: Optional[list[str]] = None) -> CortexStorage:
    """Resolve storage instance from workspace paths or current directory."""
    if workspace_paths:
        for wp in workspace_paths:
            p = Path(wp) / ".cortex"
            if p.exists() or p.parent.exists():
                return CortexStorage(cortex_dir=p)
    return CortexStorage()


def process_hook_payload(event_type: str, payload_str: str) -> Dict[str, Any]:
    """Process incoming JSON payload and record sanitized ActivityEvent."""
    event_type = event_type.lower()
    default_response: Dict[str, Any] = {"decision": "allow"} if event_type == "pre" else {}

    if not payload_str or not payload_str.strip():
        return default_response

    try:
        data = json.loads(payload_str)
    except Exception:
        return default_response

    try:
        conversation_id = data.get("conversationId", data.get("conversation_id"))
        step_idx = data.get("stepIdx", data.get("step_index"))
        workspace_paths = data.get("workspacePaths", [])
        tool_call = data.get("toolCall", {})
        tool_name = tool_call.get("name") or data.get("tool_name") or data.get("name") or "unknown_tool"
        tool_args = tool_call.get("args") or data.get("args") or {}
        error_val = data.get("error")

        storage = resolve_cortex_storage(workspace_paths)
        target = extract_target(tool_name, tool_args)
        correlation_id = f"step-{conversation_id}-{step_idx}" if conversation_id and step_idx is not None else None

        active_anchor = storage.get_active_task_anchor(conversation_id=conversation_id)
        anchor_id = active_anchor.anchor_id if active_anchor else None

        if event_type == "pre":
            event_id = f"act-pre-{uuid.uuid4().hex[:8]}"
            act_event = ActivityEvent(
                event_id=event_id,
                timestamp=utc_now_iso(),
                anchor_id=anchor_id,
                task_id=anchor_id,
                conversation_id=conversation_id,
                step_index=int(step_idx) if step_idx is not None else None,
                actor="agent",
                action_type="tool_call",
                source="antigravity_hook",
                target=target,
                tool_name=tool_name,
                status="started",
                correlation_id=correlation_id,
                metadata=sanitize_args_metadata(tool_args),
            )
            storage.record_activity(act_event)
            return {"decision": "allow"}

        elif event_type == "post":
            event_id = f"act-post-{uuid.uuid4().hex[:8]}"
            status = "error" if error_val else "success"
            error_type = redact_text(str(error_val)) if error_val else None

            meta = sanitize_args_metadata(tool_args)
            if error_val:
                meta["error"] = redact_text(str(error_val))

            act_event = ActivityEvent(
                event_id=event_id,
                timestamp=utc_now_iso(),
                anchor_id=anchor_id,
                task_id=anchor_id,
                conversation_id=conversation_id,
                step_index=int(step_idx) if step_idx is not None else None,
                actor="agent",
                action_type="tool_result",
                source="antigravity_hook",
                target=target,
                tool_name=tool_name,
                status=status,
                correlation_id=correlation_id,
                parent_event_id=f"act-pre-{correlation_id}" if correlation_id else None,
                metadata=meta,
                error_type=error_type,
            )
            storage.record_activity(act_event)
            return {}

        else:
            return {}

    except Exception:
        # Failure isolation: logging error must never break the Agent tool call
        return default_response


def main() -> None:
    """CLI entrypoint for Antigravity hook command execution."""
    parser = argparse.ArgumentParser(description="CORTEX Antigravity Hook Handler")
    parser.add_argument("--event", type=str, default="pre", choices=["pre", "post", "pre_invocation", "post_invocation", "stop"], help="Hook event type")
    args = parser.parse_args()

    try:
        input_data = sys.stdin.read()
    except Exception:
        input_data = ""

    response = process_hook_payload(args.event, input_data)
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
