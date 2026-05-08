"""
AgentMessage schema.

WHY: Messages are the primary communication unit in the multi-agent system.
They carry agent decisions, tool calls, and results. Strong typing ensures
protocol compliance and simplifies distributed tracing/logging.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """
    Defines who/what is sending the message.
    
    WHY: Different consumers interpret the same action differently. The role
    disambiguates whether the message is from the user, an agent, a tool,
    or the system itself (e.g., error messages).
    """
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"


class AgentMessage(BaseModel):
    """
    Core message structure for agent-to-agent and agent-to-system communication.
    
    WHY: This is the lingua franca of the orchestration system. Every significant
    action (decision, tool invocation, result) flows through messages. Immutability
    and versioning allow for audit trails and distributed consistency.
    
    Design considerations:
    - conversation_id: Links related messages across multiple agent invocations.
      Enables conversation history retrieval and multi-turn reasoning.
    - parent_message_id: Enables building directed acyclic graphs (DAGs) of
      reasoning steps for complex workflows (e.g., hierarchical agents).
    - trace_id: OpenTelemetry-compatible distributed tracing. Critical for
      debugging async operations across multiple services/workers.
    - metadata: Extensible dict for agent-specific context (model version,
      temperature, sampling strategy, etc.) without schema changes.
    """
    
    # Identifiers
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Unique message ID")
    conversation_id: UUID = Field(description="Links messages in a conversation")
    parent_message_id: Optional[UUID] = Field(
        default=None,
        description="Enables DAG reasoning: sub-tasks can reference parent context"
    )
    trace_id: str = Field(description="Distributed trace ID for observability")
    
    # Core content
    role: MessageRole = Field(description="Who is sending this message")
    content: str = Field(description="Primary message content (text)")
    
    # Agent-specific fields
    agent_id: str = Field(description="Identifier of the agent that created this message")
    agent_version: Optional[str] = Field(
        default=None,
        description="Agent version for reproducibility and rollback"
    )
    
    # Timing and ordering
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sequence_number: int = Field(
        description="Logical clock for ordering messages in causally-related operations"
    )
    
    # Tool integration
    tool_calls: List["AgentMessage"] = Field(
        default_factory=list,
        description="Nested tool invocations this message triggers"
    )
    
    # Extensibility
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific context: model params, sampling strategy, etc."
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
                    "parent_message_id": None,
                    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                    "role": "agent",
                    "content": "I need to search for information about climate change.",
                    "agent_id": "researcher_agent",
                    "agent_version": "v1.0.0",
                    "timestamp": "2026-05-09T10:00:00Z",
                    "sequence_number": 1,
                    "tool_calls": [],
                    "metadata": {"temperature": 0.7, "max_tokens": 2048}
                }
            ]
        }
