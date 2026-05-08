"""
SharedContext schema.

WHY: Agents in a multi-agent system need access to shared state that persists
across multiple reasoning steps and agent invocations. SharedContext provides
a single source of truth for facts, constraints, and resources, avoiding
inconsistency and enabling coordinated behavior.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContextMetadata(BaseModel):
    """
    Metadata about the context itself.
    
    WHY: Production systems need to understand the lineage and validity of data.
    Metadata enables cache invalidation, versioning, and audit trails.
    """
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1, description="Context version for consistency checks")
    
    # WHO changed it and WHY
    last_modified_by: str = Field(description="Agent or system that last modified this context")
    modification_reason: Optional[str] = Field(
        default=None,
        description="Why was this context changed (for audit/debugging)"
    )


class ContextConstraint(BaseModel):
    """
    Explicit constraints that guide agent behavior.
    
    WHY: Constraints are distinct from facts. They represent operational rules
    (e.g., "budget < $1000", "only use approved services") that agents must
    consider during decision-making. Separating them enables:
    - Declarative rule enforcement
    - Easy constraint updates without code changes
    - Observability: which constraints agents violated
    """
    
    name: str = Field(description="Constraint identifier")
    description: str = Field(description="Human-readable constraint statement")
    constraint_type: str = Field(
        description="Type for validation logic (e.g., 'budget', 'rate_limit', 'approval')"
    )
    value: Any = Field(description="Constraint value (varies by type)")
    enforceable: bool = Field(
        default=True,
        description="Can the system enforce this, or only warn?"
    )


class SharedContext(BaseModel):
    """
    Immutable context shared across all agents in a conversation.
    
    WHY: This is the "ground truth" for a session. All agents read from here
    to ensure consistent world view. Changes are atomic and versioned to support:
    - Consistency checks and conflict detection
    - Rollback if agents make invalid decisions
    - Multi-agent coordination without race conditions
    
    Design considerations:
    - conversation_id: Ties context to a specific conversation/session.
    - user_intent: The original user request. Referenced by agents to validate
      their outputs against the initial goal (drift detection).
    - facts: Observable truths extracted from sources. Distinct from derived
      conclusions (stored in agent memory/logs).
    - constraints: Operational rules agents must follow.
    - resources: External service/data dependencies. Enables agents to discover
      available tools/APIs at runtime (dynamic tool discovery).
    - metadata: For tracking who modified context, when, and why (audit trail).
    """
    
    conversation_id: UUID = Field(
        description="Links context to a specific multi-agent conversation"
    )
    
    user_intent: str = Field(
        description="Original user request. Used for goal validation and drift detection."
    )
    
    # Observable facts extracted/synthesized from external sources
    facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Ground truths: extracted data, verified information, query results"
    )
    
    # Operational constraints that guide agent behavior
    constraints: List[ContextConstraint] = Field(
        default_factory=list,
        description="Rules agents must follow: budgets, rate limits, approvals, etc."
    )
    
    # External resources agents can leverage
    resources: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description={
            "description": "Available tools, APIs, databases, services",
            "example": {
                "search_api": {"type": "tool", "endpoint": "https://...", "rate_limit": 100},
                "database": {"type": "resource", "connection_string": "..."}
            }
        }
    )
    
    # User information and preferences
    user_id: Optional[str] = Field(default=None, description="User making the request")
    user_preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="User settings: language, formatting, privacy preferences, etc."
    )
    
    # Context-level metadata
    metadata: ContextMetadata = Field(default_factory=ContextMetadata)
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
                    "user_intent": "Find the cheapest flights from NYC to LA next week",
                    "facts": {
                        "departure_city": "New York",
                        "arrival_city": "Los Angeles",
                        "date_range": "2026-05-16 to 2026-05-23"
                    },
                    "constraints": [
                        {
                            "name": "budget",
                            "description": "Total flight cost must be under $500",
                            "constraint_type": "budget",
                            "value": 500,
                            "enforceable": True
                        }
                    ],
                    "resources": {
                        "flight_search_api": {
                            "type": "tool",
                            "endpoint": "https://api.flights.com/search",
                            "rate_limit": 100
                        }
                    },
                    "user_id": "user_123",
                    "user_preferences": {"currency": "USD", "language": "en"}
                }
            ]
        }
