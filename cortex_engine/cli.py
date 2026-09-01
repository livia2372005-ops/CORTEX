"""CORTEX Command Line Interface and Diagnostics Tool."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __schema_version__, __version__
from .api import CortexAPI
from .indexer import CortexIndexer
from .models import Knowledge
from .storage import CortexStorage


def get_workspace_root(override_path: Optional[str] = None) -> Path:
    """Resolve current active workspace directory."""
    if override_path:
        return Path(override_path).resolve()
    return Path.cwd().resolve()


class CortexCLI:
    """CLI handler for CORTEX diagnostics, status, search, and non-destructive initialization."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = get_workspace_root(str(workspace_root) if workspace_root else None)
        self.cortex_dir = self.workspace_root / ".cortex"
        self.storage = CortexStorage(cortex_dir=self.cortex_dir)
        self.indexer = CortexIndexer(storage=self.storage)
        self.api = CortexAPI(storage=self.storage, indexer=self.indexer)

    def cmd_version(self) -> str:
        """Return CORTEX version string."""
        return f"CORTEX v{__version__} (schema v{__schema_version__})"

    def cmd_status(self) -> Dict[str, Any]:
        """Collect and return health and observability metrics."""
        exists = self.cortex_dir.exists()
        knowledge_counts: Dict[str, int] = {
            "decisions": 0,
            "constraints": 0,
            "failures": 0,
            "lessons": 0,
            "claims": 0,
        }

        if exists:
            k_dir = self.cortex_dir / "knowledge"
            for cat in ["decisions", "constraints", "failures", "lessons", "claims"]:
                cat_p = k_dir / cat
                if cat_p.exists():
                    knowledge_counts[cat] = len(list(cat_p.glob("*.json")))

        db_path = self.cortex_dir / "indexes" / "cortex.db"
        index_status = "HEALTHY" if db_path.exists() and db_path.stat().st_size > 0 else "MISSING_OR_EMPTY"

        # Read last event
        last_event_time = None
        evt_file = self.cortex_dir / "events" / "events.jsonl"
        if evt_file.exists() and evt_file.stat().st_size > 0:
            try:
                with open(evt_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_line = json.loads(lines[-1].strip())
                        last_event_time = last_line.get("timestamp")
            except Exception:
                pass

        # Check plugin and MCP config
        plugin_file = self.workspace_root / ".agents" / "plugins" / "cortex" / "plugin.json"
        mcp_file = self.workspace_root / ".agents" / "plugins" / "cortex" / "mcp_config.json"
        mcp_configured = plugin_file.exists() and mcp_file.exists()

        vdb_path = self.cortex_dir / "indexes" / "vector.db"
        vector_status = "HEALTHY" if vdb_path.exists() and vdb_path.stat().st_size > 0 else "MISSING"

        status_data = {
            "version": __version__,
            "schema_version": __schema_version__,
            "workspace": str(self.workspace_root),
            "cortex_initialized": exists,
            "record_counts": knowledge_counts,
            "total_records": sum(knowledge_counts.values()),
            "index_status": index_status,
            "vector_index_status": vector_status,
            "retrieval_policy": "hybrid",
            "vectorizer_version": "tfidf_ngram_v1",
            "last_event_timestamp": last_event_time,
            "antigravity_plugin_configured": mcp_configured,
        }
        return status_data

    def cmd_doctor(self) -> Dict[str, Any]:
        """Perform non-mutating diagnostics and report checks."""
        checks: List[Dict[str, str]] = []

        # 1. Python Runtime Check
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 10):
            checks.append({"name": "Python Runtime", "status": "PASS", "detail": f"Python {py_ver}"})
        else:
            checks.append({"name": "Python Runtime", "status": "FAIL", "detail": f"Python {py_ver} (requires >= 3.10)"})

        # 2. Git Check
        git_dir = self.workspace_root / ".git"
        if git_dir.exists():
            checks.append({"name": "Git Repository", "status": "PASS", "detail": "Git repo initialized"})
        else:
            checks.append({"name": "Git Repository", "status": "WARN", "detail": "No .git directory found"})

        # 3. Canonical .cortex/ Storage
        if self.cortex_dir.exists():
            k_dir = self.cortex_dir / "knowledge"
            e_dir = self.cortex_dir / "events"
            if k_dir.exists() and e_dir.exists():
                checks.append({"name": "Canonical Storage", "status": "PASS", "detail": ".cortex/ structure valid"})
            else:
                checks.append({"name": "Canonical Storage", "status": "WARN", "detail": "Missing knowledge/ or events/ directory"})
        else:
            checks.append({"name": "Canonical Storage", "status": "WARN", "detail": ".cortex/ directory not initialized"})

        # 4. Derived FTS5 Index
        db_path = self.cortex_dir / "indexes" / "cortex.db"
        if db_path.exists() and db_path.stat().st_size > 0:
            checks.append({"name": "Derived Index", "status": "PASS", "detail": "SQLite FTS5 index ready"})
        else:
            checks.append({"name": "Derived Index", "status": "WARN", "detail": "SQLite index missing (run cortex reindex)"})

        # 5. Derived Vector Index
        vdb_path = self.cortex_dir / "indexes" / "vector.db"
        if vdb_path.exists() and vdb_path.stat().st_size > 0:
            checks.append({"name": "Derived Vector Index", "status": "PASS", "detail": "Semantic vector index ready (tfidf_ngram_v1)"})
        else:
            checks.append({"name": "Derived Vector Index", "status": "WARN", "detail": "Semantic vector index missing (run cortex reindex)"})

        # 6. Antigravity Plugin Structure
        plugin_root = self.workspace_root / ".agents" / "plugins" / "cortex"
        manifest = plugin_root / "plugin.json"
        mcp_cfg = plugin_root / "mcp_config.json"
        rules_dir = plugin_root / "rules"
        skills_dir = plugin_root / "skills"

        if manifest.exists() and mcp_cfg.exists() and rules_dir.exists() and skills_dir.exists():
            checks.append({"name": "Antigravity Plugin", "status": "PASS", "detail": f"v{__version__} plugin complete"})
        else:
            checks.append({"name": "Antigravity Plugin", "status": "WARN", "detail": "Incomplete plugin installation"})

        overall_status = "PASS"
        if any(c["status"] == "FAIL" for c in checks):
            overall_status = "FAIL"
        elif any(c["status"] == "WARN" for c in checks):
            overall_status = "WARN"

        return {
            "overall": overall_status,
            "cortex_version": __version__,
            "retrieval_policy": "hybrid",
            "workspace": str(self.workspace_root),
            "checks": checks,
        }

    def cmd_init(self, force: bool = False) -> Dict[str, Any]:
        """Safely initialize CORTEX storage and Antigravity plugin without overwriting existing user assets."""
        # 1. Initialize canonical storage directories
        self.storage._ensure_directories()

        # 2. Setup Antigravity plugin directories
        plugin_dir = self.workspace_root / ".agents" / "plugins" / "cortex"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "rules").mkdir(parents=True, exist_ok=True)
        (plugin_dir / "skills").mkdir(parents=True, exist_ok=True)

        # 3. Create plugin manifest if missing
        manifest_file = plugin_dir / "plugin.json"
        if not manifest_file.exists() or force:
            manifest_data = {
                "name": "cortex",
                "version": __version__,
                "schema_version": __schema_version__,
                "description": "Persistent project memory and evidence retrieval for coding Agents.",
                "rules": ["rules/cortex-awareness.md"],
                "skills": [
                    "skills/cortex-memory",
                    "skills/cortex-review",
                    "skills/cortex-learning",
                ],
                "components": {
                    "rules": ["rules/cortex-awareness.md"],
                    "skills": ["skills/cortex-memory", "skills/cortex-review", "skills/cortex-learning"],
                    "mcp_config": "mcp_config.json",
                    "hooks": "hooks.json",
                },
                "mcp": "mcp_config.json",
                "hooks": "hooks.json",
            }
            manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        # 4. Create mcp_config.json if missing
        mcp_file = plugin_dir / "mcp_config.json"
        if not mcp_file.exists() or force:
            mcp_data = {
                "mcpServers": {
                    "cortex-mcp": {
                        "command": "python",
                        "args": ["-m", "cortex_engine.mcp_server"],
                        "env": {},
                    }
                }
            }
            mcp_file.write_text(json.dumps(mcp_data, indent=2), encoding="utf-8")

        # 5. Create hooks.json if missing
        hooks_file = plugin_dir / "hooks.json"
        if not hooks_file.exists() or force:
            hooks_data = {
                "version": "1.0.0",
                "hooks": {
                    "on_session_start": {
                        "description": "Verify CORTEX index readiness upon workspace session start",
                        "action": "cortex doctor",
                    }
                },
            }
            hooks_file.write_text(json.dumps(hooks_data, indent=2), encoding="utf-8")

        # 6. Create cortex-awareness rule if missing
        rule_file = plugin_dir / "rules" / "cortex-awareness.md"
        if not rule_file.exists() or force:
            rule_content = """# CORTEX Awareness

CORTEX is active in this workspace to provide persistent project memory, event tracking, and evidence retrieval.

- **Agent Responsibility**: You (the Agent) remain fully responsible for reasoning, interpretation, planning, decisions, coding, and final judgment. CORTEX is your tool and evidence substrate, not an autonomous decision authority.
- **Roles & Capabilities**: When helpful, you may transition roles (`APP`, `MEMORY`, `REVIEW`, `LEARNING`) using CORTEX skills and tools to query prior decisions, inspect lessons/constraints, verify claims, or record durable knowledge.
- **Provenance**: Treat retrieved memory as contextual evidence to be verified, not unquestionable ground truth.
"""
            rule_file.write_text(rule_content, encoding="utf-8")

        # 7. Create skills directories and SKILL.md templates if missing
        skill_templates = {
            "cortex-memory": """---
name: cortex-memory
description: Inspect and retrieve project memory, prior decisions, constraints, failures, lessons, and claims from CORTEX storage.
---
# CORTEX Memory Skill
Use cortex_search and cortex_get to inspect persistent memory and retrieve architectural evidence.
""",
            "cortex-review": """---
name: cortex-review
description: Inspect evidence, diffs, test logs, and claims to identify regressions, constraint violations, and verification gaps.
---
# CORTEX Review Skill
Use cortex_check_claim_freshness and cortex_search to inspect constraints and verify claims.
""",
            "cortex-learning": """---
name: cortex-learning
description: Record durable decisions, constraints, failures, lessons, and claims into persistent CORTEX storage.
---
# CORTEX Learning Skill
Use cortex_record_knowledge and cortex_record_event to persist durable engineering knowledge.
""",
        }
        for skill_name, content in skill_templates.items():
            s_dir = plugin_dir / "skills" / skill_name
            s_dir.mkdir(parents=True, exist_ok=True)
            s_file = s_dir / "SKILL.md"
            if not s_file.exists() or force:
                s_file.write_text(content, encoding="utf-8")

        # Build initial indexes
        self.indexer.rebuild_from_canonical(self.storage)
        from .retrieval_benchmark import SemanticVectorIndex
        vindex = SemanticVectorIndex(db_path=self.cortex_dir / "indexes" / "vector.db")
        vindex.rebuild(self.storage)

        return {
            "status": "initialized",
            "workspace": str(self.workspace_root),
            "cortex_dir": str(self.cortex_dir),
            "plugin_dir": str(plugin_dir),
        }

    def cmd_search(self, query: str, limit: int = 10, policy: str = "hybrid") -> Dict[str, Any]:
        """Perform CLI search query using hybrid router."""
        return self.api.search(query=query, limit=limit, role="MEMORY", policy=policy)

    def cmd_reindex(self) -> Dict[str, Any]:
        """Rebuild derived SQLite FTS5 and Semantic Vector indexes from canonical storage."""
        count_fts = self.indexer.rebuild_from_canonical(self.storage)
        from .retrieval_benchmark import SemanticVectorIndex
        vindex = SemanticVectorIndex(db_path=self.cortex_dir / "indexes" / "vector.db")
        count_vec = vindex.rebuild(self.storage)
        return {"status": "reindexed", "indexed_fts": count_fts, "indexed_vector": count_vec}


def main(args: Optional[List[str]] = None) -> int:
    """Entry point for CORTEX CLI commands."""
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="CORTEX: Persistent project memory and evidence retrieval engine for coding Agents.",
    )
    parser.add_argument("--version", action="store_true", help="Show CORTEX version")
    parser.add_argument("--workspace", type=str, default=None, help="Target workspace path")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # cortex status
    subparsers.add_parser("status", help="Show CORTEX workspace status and memory counts")

    # cortex doctor
    subparsers.add_parser("doctor", help="Run non-mutating diagnostics and health checks")

    # cortex init
    init_parser = subparsers.add_parser("init", help="Initialize CORTEX and Antigravity plugin in workspace")
    init_parser.add_argument("--force", action="store_true", help="Force overwrite plugin configuration")

    # cortex search
    search_parser = subparsers.add_parser("search", help="Search memory records via derived index")
    search_parser.add_argument("query", type=str, help="Search query keywords")
    search_parser.add_argument("--limit", type=int, default=10, help="Max results")

    # cortex reindex
    subparsers.add_parser("reindex", help="Rebuild derived SQLite FTS5 index from canonical files")

    parsed = parser.parse_args(args)

    cli = CortexCLI(workspace_root=parsed.workspace)

    if parsed.version:
        print(cli.cmd_version())
        return 0

    if parsed.command == "status":
        st = cli.cmd_status()
        print(f"\n--- CORTEX Status (v{st['version']}) ---")
        print(f"Workspace:          {st['workspace']}")
        print(f"Initialized:        {st['cortex_initialized']}")
        print(f"Total Records:      {st['total_records']} (Decisions: {st['record_counts']['decisions']}, Constraints: {st['record_counts']['constraints']}, Failures: {st['record_counts']['failures']}, Claims: {st['record_counts']['claims']})")
        print(f"Index Status:       {st['index_status']}")
        print(f"Last Event:         {st['last_event_timestamp'] or 'None'}")
        print(f"Antigravity Plugin: {'Configured' if st['antigravity_plugin_configured'] else 'Not configured'}\n")
        return 0

    elif parsed.command == "doctor":
        doc = cli.cmd_doctor()
        print(f"\n=== CORTEX Doctor (v{doc['cortex_version']}) ===")
        print(f"Workspace: {doc['workspace']}")
        print(f"Overall Health: [{doc['overall']}]\n")
        for chk in doc["checks"]:
            print(f"  [{chk['status']:<4}] {chk['name']:<20} : {chk['detail']}")
        print()
        return 0 if doc["overall"] != "FAIL" else 1

    elif parsed.command == "init":
        res = cli.cmd_init(force=parsed.force)
        print(f"CORTEX initialized successfully in {res['workspace']}")
        return 0

    elif parsed.command == "search":
        res = cli.cmd_search(query=parsed.query, limit=parsed.limit)
        print(f"\n--- Search Results for '{parsed.query}' ({len(res['results'])} matches) ---")
        for r in res["results"]:
            print(f"[{r['id']}] ({r.get('type', 'knowledge').upper()}) {r.get('title', '')}")
            if "content" in r:
                print(f"    {r['content']}")
        print()
        return 0

    elif parsed.command == "reindex":
        res = cli.cmd_reindex()
        print(f"Reindexed {res['indexed_records']} canonical records successfully.")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
