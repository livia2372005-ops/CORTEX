"""CORTEX Claim Provenance and Freshness Detection Engine."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Claim, Evidence


def compute_file_hash(file_path: str | Path) -> Optional[str]:
    """Compute SHA-256 hash of a file on disk."""
    path = Path(file_path)
    if not path.is_file():
        return None
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def get_git_commit(cwd: Optional[str | Path] = None) -> Optional[str]:
    """Retrieve current Git commit SHA-1 if available."""
    work_dir = Path(cwd).resolve() if cwd else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
            return commit if len(commit) >= 7 else None
        return None
    except Exception:
        return None


def evaluate_claim_freshness(
    claim: Claim,
    workspace_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Evaluate whether artifact and evidence supporting a claim remain fresh.
    
    Principles:
    1. artifact changed != claim rejected (marks status: affected).
    2. missing evidence != claim true.
    3. Returns structured empirical report; Agent retains judgment.
    """
    root = Path(workspace_root).resolve() if workspace_root else Path.cwd()

    # Base report envelope
    report: Dict[str, Any] = {
        "id": claim.id,
        "statement": claim.statement,
        "original_status": claim.status,
        "status": claim.status,
        "fresh": False,
        "reason": "unknown",
        "artifact": claim.artifact,
        "evidence": claim.evidence,
        "provenance": claim.provenance,
    }

    # Explicit terminal/non-verified statuses
    if claim.status == "rejected":
        report["status"] = "rejected"
        report["reason"] = "claim_explicitly_rejected"
        report["fresh"] = False
        return report

    if claim.status == "unprovable":
        report["status"] = "unprovable"
        report["reason"] = "claim_unprovable"
        report["fresh"] = False
        return report

    if claim.status == "unverified":
        report["status"] = "unverified"
        report["reason"] = "claim_not_yet_verified"
        report["fresh"] = False
        return report

    # Evaluate Artifact Freshness for verified / affected claims
    if not claim.artifact or not isinstance(claim.artifact, dict):
        report["status"] = "affected"
        report["reason"] = "missing_artifact_reference"
        report["fresh"] = False
        return report

    artifact_rel_path = claim.artifact.get("path")
    expected_hash = claim.artifact.get("content_hash") or claim.artifact.get("hash")

    if not artifact_rel_path or not expected_hash:
        report["status"] = "affected"
        report["reason"] = "malformed_artifact_reference"
        report["fresh"] = False
        return report

    artifact_full_path = root / artifact_rel_path if not Path(artifact_rel_path).is_absolute() else Path(artifact_rel_path)

    if not artifact_full_path.exists():
        report["status"] = "affected"
        report["reason"] = "artifact_missing"
        report["fresh"] = False
        report["artifact"] = {
            "path": artifact_rel_path,
            "expected_hash": expected_hash,
            "current_hash": None,
        }
        return report

    current_hash = compute_file_hash(artifact_full_path)
    report["artifact"] = {
        "path": artifact_rel_path,
        "expected_hash": expected_hash,
        "current_hash": current_hash,
    }

    if current_hash == expected_hash:
        report["status"] = "verified"
        report["reason"] = "artifact_unchanged"
        report["fresh"] = True
    else:
        # Artifact changed -> Marks affected, NOT rejected
        report["status"] = "affected"
        report["reason"] = "artifact_changed"
        report["fresh"] = False

    return report
