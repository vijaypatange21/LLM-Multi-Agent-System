"""
Core abstractions and foundational components.

This module defines the interfaces and base classes that form the foundation
of the multi-agent orchestration system.
"""

from .abstractions import (
    BaseAgent,
    BaseTool,
    ContextManager,
    Orchestrator,
)

__all__ = [
    "BaseAgent",
    "BaseTool",
    "ContextManager",
    "Orchestrator",
]
