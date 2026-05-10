"""
Prompt optimization module with mandatory human approval.

This module implements a self-improving loop that:
1. Analyzes failed evaluations
2. Identifies prompt weaknesses
3. Generates improved versions
4. Creates structured diffs
5. REQUIRES human approval before deployment
6. Tracks performance improvements
7. Maintains version history

Key design principle: NO AUTO-APPLY.
All prompt changes must be explicitly approved by humans.
"""

from .prompt_optimizer import (
    ApprovalStatus,
    PromptOrigin,
    ApprovalRequest,
    FailedEval,
    MetaAgent,
    PerformanceDelta,
    PromptDiff,
    PromptOptimizer,
    PromptRecommendation,
    PromptVersion,
    PromptWeakness,
)

__all__ = [
    # Enums
    "ApprovalStatus",
    "PromptOrigin",
    # Models
    "ApprovalRequest",
    "FailedEval",
    "PerformanceDelta",
    "PromptDiff",
    "PromptRecommendation",
    "PromptVersion",
    "PromptWeakness",
    # Agents
    "MetaAgent",
    "PromptOptimizer",
]
