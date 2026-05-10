"""
Real-time orchestration visibility.

Tracks:
- Live agent status
- Live tool call visibility
- Agent-to-agent communication
- Context state changes
- Resource utilization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING_TOOL = "executing_tool"
    WAITING_FOR_RESULT = "waiting_for_result"
    PROCESSING_RESULT = "processing_result"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentStatusSnapshot:
    """Snapshot of an agent's current status."""
    
    agent_id: str
    trace_id: UUID
    
    status: AgentStatus
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    current_step_number: int = 0
    total_steps: int = 0
    progress_percent: float = 0.0
    
    # Current operation
    current_operation: Optional[str] = None
    current_tool: Optional[str] = None
    
    # Performance
    elapsed_ms: float = 0.0
    estimated_remaining_ms: float = 0.0
    
    # Resource usage
    tokens_used: int = 0
    tokens_available: int = 0
    
    # State
    agent_state: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for transmission."""
        return {
            "agent_id": self.agent_id,
            "trace_id": str(self.trace_id),
            "status": self.status.value,
            "current_step": self.current_step_number,
            "total_steps": self.total_steps,
            "progress_percent": self.progress_percent,
            "current_operation": self.current_operation,
            "current_tool": self.current_tool,
            "elapsed_ms": self.elapsed_ms,
            "estimated_remaining_ms": self.estimated_remaining_ms,
            "tokens_used": self.tokens_used,
            "tokens_available": self.tokens_available,
        }


@dataclass
class ToolCallTrace:
    """Trace of a tool call execution."""
    
    id: UUID
    agent_id: str
    trace_id: UUID
    
    tool_name: str
    tool_args: Dict[str, Any]
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    duration_ms: float = 0.0
    cost: float = 0.0
    
    # Visibility
    status: str = "pending"  # pending, executing, completed, failed
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for transmission."""
        return {
            "id": str(self.id),
            "agent_id": self.agent_id,
            "trace_id": str(self.trace_id),
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "cost": self.cost,
            "status": self.status,
        }


@dataclass
class ContextStateChange:
    """Record of a context state change."""
    
    timestamp: datetime
    trace_id: UUID
    agent_id: str
    
    change_type: str  # "update", "conflict", "overflow", etc.
    field_name: str
    
    old_value: Any
    new_value: Any
    
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for transmission."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "trace_id": str(self.trace_id),
            "agent_id": self.agent_id,
            "change_type": self.change_type,
            "field_name": self.field_name,
            "old_value": str(self.old_value),
            "new_value": str(self.new_value),
            "reason": self.reason,
        }


class OrchestrationVisibilityTracker:
    """Tracks real-time orchestration visibility."""
    
    def __init__(self):
        # Current status of each agent
        self.agent_status: Dict[str, AgentStatusSnapshot] = {}
        
        # Recent tool calls
        self.recent_tool_calls: List[ToolCallTrace] = []
        self.tool_calls_by_agent: Dict[str, List[ToolCallTrace]] = {}
        
        # Context changes
        self.context_changes: List[ContextStateChange] = []
        self.context_changes_by_trace: Dict[UUID, List[ContextStateChange]] = {}
        
        # Metrics
        self.total_tool_calls: int = 0
        self.total_context_changes: int = 0
    
    def update_agent_status(self, snapshot: AgentStatusSnapshot) -> None:
        """Update agent status snapshot."""
        self.agent_status[snapshot.agent_id] = snapshot
    
    def get_agent_status(self, agent_id: str) -> Optional[AgentStatusSnapshot]:
        """Get current status of an agent."""
        return self.agent_status.get(agent_id)
    
    def get_all_agent_statuses(self) -> Dict[str, AgentStatusSnapshot]:
        """Get status of all agents."""
        return self.agent_status.copy()
    
    def record_tool_call(self, tool_call: ToolCallTrace) -> None:
        """Record a tool call."""
        self.recent_tool_calls.append(tool_call)
        self.total_tool_calls += 1
        
        if tool_call.agent_id not in self.tool_calls_by_agent:
            self.tool_calls_by_agent[tool_call.agent_id] = []
        self.tool_calls_by_agent[tool_call.agent_id].append(tool_call)
        
        # Keep only last 1000
        if len(self.recent_tool_calls) > 1000:
            self.recent_tool_calls = self.recent_tool_calls[-1000:]
    
    def get_recent_tool_calls(self, limit: int = 50) -> List[ToolCallTrace]:
        """Get recent tool calls."""
        return self.recent_tool_calls[-limit:]
    
    def get_agent_tool_calls(
        self,
        agent_id: str,
        limit: int = 50
    ) -> List[ToolCallTrace]:
        """Get tool calls by an agent."""
        calls = self.tool_calls_by_agent.get(agent_id, [])
        return calls[-limit:]
    
    def get_pending_tool_calls(self) -> List[ToolCallTrace]:
        """Get all pending tool calls."""
        return [c for c in self.recent_tool_calls if c.status == "pending"]
    
    def get_in_progress_tool_calls(self) -> List[ToolCallTrace]:
        """Get all in-progress tool calls."""
        return [c for c in self.recent_tool_calls if c.status == "executing"]
    
    def record_context_change(self, change: ContextStateChange) -> None:
        """Record a context state change."""
        self.context_changes.append(change)
        self.total_context_changes += 1
        
        if change.trace_id not in self.context_changes_by_trace:
            self.context_changes_by_trace[change.trace_id] = []
        self.context_changes_by_trace[change.trace_id].append(change)
        
        # Keep only last 10000
        if len(self.context_changes) > 10000:
            self.context_changes = self.context_changes[-10000:]
    
    def get_context_changes_for_trace(self, trace_id: UUID) -> List[ContextStateChange]:
        """Get context changes for a trace."""
        return self.context_changes_by_trace.get(trace_id, [])
    
    def get_recent_context_changes(self, limit: int = 50) -> List[ContextStateChange]:
        """Get recent context changes."""
        return self.context_changes[-limit:]
    
    def get_orchestration_status(self) -> Dict[str, Any]:
        """Get overall orchestration status."""
        return {
            "active_agents": len(self.agent_status),
            "agent_statuses": {
                agent_id: status.to_dict()
                for agent_id, status in self.agent_status.items()
            },
            "pending_tool_calls": len(self.get_pending_tool_calls()),
            "in_progress_tool_calls": len(self.get_in_progress_tool_calls()),
            "total_tool_calls": self.total_tool_calls,
            "total_context_changes": self.total_context_changes,
            "recent_tool_calls": [c.to_dict() for c in self.get_recent_tool_calls(10)],
            "recent_context_changes": [c.to_dict() for c in self.get_recent_context_changes(10)],
        }


# Global visibility tracker
_visibility_tracker: Optional[OrchestrationVisibilityTracker] = None


def get_visibility_tracker() -> OrchestrationVisibilityTracker:
    """Get or create global visibility tracker."""
    global _visibility_tracker
    if _visibility_tracker is None:
        _visibility_tracker = OrchestrationVisibilityTracker()
    return _visibility_tracker
