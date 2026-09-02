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
from typing import Any, Dict, List, Optional

from .models import ActivityEvent, utc_now_iso
from .redaction import redact_data, redact_text
from .storage import CortexStorage, normalize_workspace_path


def extract_target(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Intelligently extract the principal target or resource being operated on."""
    if not isinstance(tool_args, dict):
        return tool_name

    if tool_name == "run_command":
        return str(tool_args.get("CommandLine") or tool_args.get("command") or tool_args.get("cmd") or tool_name)
    elif tool_name in {"view_file", "view_symbol", "show_definition"}:
        return str(tool_args.get("AbsolutePath") or tool_args.get("TargetFile") or tool_args.get("file_path") or tool_name)
    elif tool_name in {"replace_file_content", "multi_replace_file_content", "write_to_file"}:
        return str(tool_args.get("TargetFile") or tool_args.get("AbsolutePath") or tool_args.get("file_path") or tool_name)
    elif tool_name in {"grep_search", "find_by_name"}:
        path = tool_args.get("SearchPath") or tool_args.get("path") or ""
        query = tool_args.get("Query") or tool_args.get("query") or ""
        return f"{path} (query: {query})" if path or query else tool_name
    elif tool_name == "read_url_content":
        return str(tool_args.get("Url") or tool_args.get("url") or tool_name)
    elif tool_name in {"list_dir", "list_directory"}:
        return str(tool_args.get("DirectoryPath") or tool_args.get("path") or tool_name)
    elif tool_name.startswith("mcp_") or tool_name.startswith("cortex_"):
        return tool_name

    # Generic fallback: inspect recognizable target arguments
    for key in ("TargetFile", "AbsolutePath", "DirectoryPath", "Url", "CommandLine", "path", "file", "query", "id"):
        if key in tool_args and tool_args[key]:
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


def find_cortex_dir(candidate_paths: List[str | Path]) -> Optional[Path]:
    """Climb path hierarchies of candidate paths to locate active .cortex storage directory."""
    for candidate in candidate_paths:
        if not candidate:
            continue
        try:
            norm = normalize_workspace_path(candidate)
            if not norm:
                continue
            p = Path(norm).resolve()

            # 1. Direct .cortex directory
            if p.name == ".cortex" and p.is_dir():
                return p

            # 2. Candidate workspace root containing .cortex
            cortex_sub = p / ".cortex"
            if cortex_sub.is_dir():
                return cortex_sub

            # 3. Climb up parents if candidate is a subpath or file
            curr = p if p.is_dir() else p.parent
            for parent in [curr] + list(curr.parents):
                cortex_parent = parent / ".cortex"
                if cortex_parent.is_dir():
                    return cortex_parent
        except Exception:
            continue
    return None


def resolve_cortex_storage(data: Dict[str, Any], tool_args: Dict[str, Any]) -> CortexStorage:
    """Resolve storage instance from hook payload metadata, tool file args, or current directory."""
    candidates: List[str | Path] = []

    # 1. Workspace paths passed by Antigravity in various formats
    for key in ("workspacePaths", "workspace_paths", "workspaces"):
        ws_list = data.get(key)
        if isinstance(ws_list, list):
            candidates.extend(ws_list)

    for key in ("workspaceRoot", "workspace_root", "workspace", "workspacePath", "workspace_path", "cwd"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    # 2. File paths from tool arguments (TargetFile, AbsolutePath, etc.)
    for key in ("TargetFile", "AbsolutePath", "DirectoryPath", "SearchPath", "file_path", "path"):
        val = tool_args.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    # 3. Environment variables
    for env_var in ("CORTEX_WORKSPACE", "WORKSPACE_ROOT", "PROJECT_ROOT"):
        val = os.environ.get(env_var)
        if val:
            candidates.append(val)

    # 4. Current working directory
    candidates.append(Path.cwd())

    # Find the nearest valid .cortex directory
    found = find_cortex_dir(candidates)
    if found:
        return CortexStorage(cortex_dir=found)
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
        # Resolve conversation_id across key variations
        conversation_id = (
            data.get("conversationId")
            or data.get("conversation_id")
            or data.get("conversation")
            or data.get("sessionId")
            or data.get("session_id")
            or data.get("session")
            or None
        )

        # Resolve step index across key variations (handle 0 correctly)
        step_idx = None
        for k in ("stepIdx", "step_index", "stepIndex", "step_idx", "step"):
            if k in data and data[k] is not None:
                step_idx = data[k]
                break

        # Resolve tool call and arguments across key variations
        tool_call = data.get("toolCall") or data.get("tool_call") or data.get("call") or {}
        tool_name = (
            tool_call.get("name")
            or data.get("tool_name")
            or data.get("toolName")
            or data.get("name")
            or data.get("tool")
            or "unknown_tool"
        )
        tool_args = (
            tool_call.get("args")
            or data.get("tool_args")
            or data.get("toolArgs")
            or data.get("args")
            or data.get("input")
            or data.get("arguments")
            or data.get("parameters")
            or data.get("tool_input")
            or data.get("toolInput")
            or {}
        )

        # Resolve error value across key variations
        error_val = (
            data.get("error")
            or data.get("error_message")
            or data.get("errorMessage")
            or data.get("error_type")
            or data.get("errorType")
            or None
        )

        # Resolve workspace storage
        storage = resolve_cortex_storage(data, tool_args)
        target = extract_target(tool_name, tool_args)
        correlation_id = f"step-{conversation_id}-{step_idx}" if conversation_id and step_idx is not None else None

        # Resolve active task anchor for this conversation/workspace
        workspace_str = str(storage.workspace_root)
        active_anchor = storage.get_active_task_anchor(conversation_id=conversation_id, workspace=workspace_str)
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
