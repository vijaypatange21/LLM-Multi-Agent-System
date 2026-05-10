"""
Server-Sent Events (SSE) streaming for real-time observability.

Enables live streaming of:
- Agent status changes
- Tool call visibility  
- Token generation
- Policy violations
- Execution progress
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
import json
from asyncio import Queue

from ..schemas.execution import ExecutionStep, ExecutionStepType


class SSEEventType(str, Enum):
    """Types of SSE events."""
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERRORED = "agent_errored"
    
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    
    TOKEN_GENERATED = "token_generated"
    TOKEN_BATCH = "token_batch"
    
    STATUS_UPDATE = "status_update"
    CONTEXT_UPDATE = "context_update"
    
    POLICY_VIOLATION = "policy_violation"
    BUDGET_CHECK = "budget_check"
    CONTEXT_OVERFLOW = "context_overflow"
    
    EXECUTION_STEP = "execution_step"
    
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class SSEEvent:
    """Single SSE event to stream to client."""
    
    event_type: SSEEventType
    trace_id: UUID
    conversation_id: UUID
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Event-specific data
    agent_id: Optional[str] = None
    tool_name: Optional[str] = None
    step_number: Optional[int] = None
    
    # Core payload
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Metrics
    duration_ms: Optional[float] = None
    token_count: Optional[int] = None
    cost: Optional[float] = None
    
    # Error info
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    # Priority for queuing
    priority: int = field(default=0)  # Higher = more urgent
    
    def to_json(self) -> str:
        """Serialize to JSON for SSE transmission."""
        return json.dumps({
            "event": self.event_type.value,
            "trace_id": str(self.trace_id),
            "conversation_id": str(self.conversation_id),
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "step_number": self.step_number,
            "data": self.data,
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "cost": self.cost,
            "error_message": self.error_message,
            "error_code": self.error_code,
        })
    
    def to_sse_string(self) -> str:
        """Format as SSE-compliant string."""
        json_data = self.to_json()
        return f"event: {self.event_type.value}\ndata: {json_data}\n\n"


class SSEEventQueue:
    """Async queue for SSE events with priority support."""
    
    def __init__(self, max_size: int = 10000):
        self.queue: Queue[SSEEvent] = Queue(maxsize=max_size)
        self.event_count = 0
        self.dropped_events = 0
    
    async def put(self, event: SSEEvent) -> None:
        """Add event to queue."""
        try:
            self.queue.put_nowait(event)
            self.event_count += 1
        except Exception:
            # Queue full - drop low priority events
            self.dropped_events += 1
            if event.priority > 5:
                # High priority - try to drop something else
                try:
                    self.queue.get_nowait()
                    self.queue.put_nowait(event)
                except Exception:
                    pass
    
    async def get(self) -> SSEEvent:
        """Get next event from queue."""
        return await self.queue.get()
    
    def qsize(self) -> int:
        """Current queue size."""
        return self.queue.qsize()
    
    def stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        return {
            "total_events": self.event_count,
            "current_size": self.qsize(),
            "dropped_events": self.dropped_events,
        }


class SSEEmitter:
    """Emits SSE events for streaming to clients."""
    
    def __init__(self):
        self.queues: Dict[str, SSEEventQueue] = {}  # trace_id -> queue
        self.all_events: Dict[str, SSEEvent] = {}  # For replay
    
    def create_stream(self, trace_id: UUID) -> SSEEventQueue:
        """Create a new SSE stream."""
        trace_str = str(trace_id)
        queue = SSEEventQueue()
        self.queues[trace_str] = queue
        return queue
    
    async def emit(self, event: SSEEvent) -> None:
        """Emit event to all subscribed streams."""
        trace_str = str(event.trace_id)
        
        # Store for replay
        self.all_events[f"{trace_str}_{event.timestamp.isoformat()}"] = event
        
        # Send to active subscribers
        if trace_str in self.queues:
            await self.queues[trace_str].put(event)
    
    def get_stream(self, trace_id: UUID) -> Optional[SSEEventQueue]:
        """Get stream for a trace."""
        return self.queues.get(str(trace_id))
    
    def get_events_for_trace(self, trace_id: UUID) -> list[SSEEvent]:
        """Get all events for a trace (for replay)."""
        trace_str = str(trace_id)
        return [
            event for key, event in self.all_events.items()
            if key.startswith(trace_str)
        ]
    
    def stats(self) -> Dict[str, Any]:
        """Get emitter statistics."""
        return {
            "active_streams": len(self.queues),
            "total_stored_events": len(self.all_events),
            "stream_stats": {
                trace_id: queue.stats()
                for trace_id, queue in self.queues.items()
            }
        }


# Global SSE emitter
_sse_emitter: Optional[SSEEmitter] = None


def get_sse_emitter() -> SSEEmitter:
    """Get or create global SSE emitter."""
    global _sse_emitter
    if _sse_emitter is None:
        _sse_emitter = SSEEmitter()
    return _sse_emitter
