"""CORTEX: Persistent project memory and evidence retrieval engine for coding Agents."""

__version__ = "0.2.0"
__schema_version__ = "1.0.0"

from .api import CortexAPI
from .compiler import CompiledContext, ContextCompiler
from .indexer import CortexIndexer
from .models import ActivityEvent, Claim, ContextPackage, Event, Evidence, Knowledge, RoleContext, RoleResult
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
    "RoleContext",
    "RoleResult",
    "ContextPackage",
]
