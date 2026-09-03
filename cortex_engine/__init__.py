"""CORTEX: Persistent project memory and evidence retrieval engine for coding Agents."""

__version__ = "0.4.0"
__schema_version__ = "1.0.0"

from .api import CortexAPI
from .compiler import CompiledContext, ContextCompiler
from .indexer import CortexIndexer
from .models import (
    ActivityEvent,
    Claim,
    ContextPackage,
    Event,
    Evidence,
    Knowledge,
    RoleContext,
    RoleResult,
    TaskAnchor,
    classify_cortex_interaction,
    extract_cortex_interaction_metadata,
)
from .storage import CortexStorage

__all__ = [
    "__version__",
    "__schema_version__",
    "CortexAPI",
    "CortexStorage",
    "CortexIndexer",
    "ContextCompiler",
    "CompiledContext",
    "Knowledge",
    "Claim",
    "Evidence",
    "Event",
    "ActivityEvent",
    "TaskAnchor",
    "RoleContext",
    "RoleResult",
    "ContextPackage",
    "classify_cortex_interaction",
    "extract_cortex_interaction_metadata",
]
