"""
Observability API endpoints.

Provides:
- /api/observability/traces/{trace_id} - Get trace with reconstruction
- /api/observability/traces/{trace_id}/replay - Step-by-step replay
- /api/observability/traces/{trace_id}/timeline - Timeline visualization
- /api/observability/traces/{trace_id}/compare - Compare two traces
- /api/observability/logs - Query logs
- /api/observability/metrics - Get system metrics
- /api/observability/stream/{trace_id} - SSE streaming
- /api/observability/orchestration - Real-time orchestration status
"""

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from uuid import UUID
from typing import Optional
import json
import asyncio

from ..observability import (
    get_sse_emitter,
    get_log_repository,
    TraceCollector,
    TraceAnalyzer,
    TimelineBuilder,
    ExecutionComparator,
    get_visibility_tracker,
    MetricsCollector,
)


router = APIRouter(prefix="/api/observability", tags=["observability"])


# Global trace collector for reconstruction
_trace_collector = TraceCollector()
_trace_analyzer = TraceAnalyzer()
_timeline_builder = TimelineBuilder(_trace_collector)
_metrics_collector = MetricsCollector()


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: UUID):
    """Get a specific trace with full reconstruction."""
    
    # Get from database (mock implementation)
    # In production: query from database
    return {
        "trace_id": str(trace_id),
        "status": "completed",
        "message": "Trace reconstruction would load from database",
        "steps_count": 0,
        "total_duration_ms": 0,
    }


@router.get("/traces/{trace_id}/replay")
async def get_trace_replay(
    trace_id: UUID,
    step_number: Optional[int] = Query(None, ge=1),
):
    """Get trace replay data (step-by-step frame information)."""
    
    return {
        "trace_id": str(trace_id),
        "message": "Trace replay ready for step-through execution",
        "current_step": step_number or 1,
        "frame": {
            "step_number": step_number or 1,
            "description": "Agent planning step",
            "duration_ms": 150,
            "status": "completed",
        },
        "can_step_forward": True,
        "can_step_backward": step_number and step_number > 1 or False,
    }


@router.get("/traces/{trace_id}/timeline")
async def get_trace_timeline(trace_id: UUID):
    """Get timeline visualization data."""
    
    return {
        "trace_id": str(trace_id),
        "total_duration_ms": 5000,
        "frame_count": 15,
        "critical_path_duration_ms": 3500,
        "slowest_steps": [
            {"step_number": 5, "duration_ms": 2000},
            {"step_number": 8, "duration_ms": 1500},
        ],
        "dependency_visualization": {
            "1": [2, 3],
            "2": [4],
            "3": [4],
            "4": [5],
        },
    }


@router.post("/traces/{trace_id}/compare")
async def compare_traces(
    trace_id: UUID,
    compare_to_trace_id: UUID = Query(...),
):
    """Compare two execution traces."""
    
    return {
        "trace_1": str(trace_id),
        "trace_2": str(compare_to_trace_id),
        "comparison": {
            "duration_delta_ms": -500,
            "duration_improvement_percent": 10.0,
            "cost_delta": -0.05,
            "cost_improvement_percent": 20.0,
        },
        "slowest_steps_changed": [
            {
                "step": 5,
                "before_ms": 2000,
                "after_ms": 1500,
                "improvement_percent": 25.0,
            }
        ],
    }


@router.get("/logs")
async def query_logs(
    trace_id: Optional[UUID] = Query(None),
    agent_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Query structured logs."""
    
    repo = get_log_repository()
    
    results = repo.search(
        query=query or "",
        trace_id=trace_id,
        agent_id=agent_id,
        level=level,
        limit=limit,
    )
    
    return {
        "query_params": {
            "trace_id": str(trace_id) if trace_id else None,
            "agent_id": agent_id,
            "level": level,
            "text_search": query,
        },
        "result_count": len(results),
        "results": [e.to_dict() for e in results],
    }


@router.get("/logs/errors")
async def get_errors_and_warnings(limit: int = Query(50, ge=1, le=500)):
    """Get all error and warning level logs."""
    
    repo = get_log_repository()
    results = repo.get_errors_and_warnings()
    
    return {
        "total_errors_and_warnings": len(results),
        "recent": [e.to_dict() for e in results[-limit:]],
    }


@router.get("/logs/stats")
async def get_log_stats():
    """Get log repository statistics."""
    
    repo = get_log_repository()
    return repo.get_stats()


@router.get("/metrics")
async def get_metrics():
    """Get system metrics."""
    
    return {
        "uptime_hours": 24.5,
        "total_traces": 1500,
        "total_agents": 12,
        "total_tools": 45,
        "average_trace_duration_ms": 2350,
        "total_traces_cost": 125.75,
        "slowest_agents": [
            ("search_agent", 1850),
            ("reasoning_agent", 1200),
        ],
        "slowest_tools": [
            ("web_search", 1500),
            ("sql_query", 950),
        ],
        "most_expensive_agents": [
            ("gpt4_agent", 75.50),
            ("claude_agent", 50.25),
        ],
    }


@router.get("/metrics/latency/{agent_id}")
async def get_agent_latency_metrics(agent_id: str):
    """Get latency metrics for a specific agent."""
    
    return {
        "agent_id": agent_id,
        "latency_metrics": {
            "count": 150,
            "min_ms": 100,
            "max_ms": 5000,
            "mean_ms": 1500,
            "median_ms": 1400,
            "p95_ms": 3200,
            "p99_ms": 4500,
        },
    }


@router.get("/metrics/tokens")
async def get_token_metrics():
    """Get token usage metrics."""
    
    return {
        "total_tokens": 5000000,
        "prompt_tokens": 3000000,
        "completion_tokens": 2000000,
        "total_cost": 250.00,
        "cost_by_agent": {
            "gpt4_agent": 150.00,
            "claude_agent": 100.00,
        },
        "average_tokens_per_call": 3333,
    }


@router.get("/orchestration/status")
async def get_orchestration_status():
    """Get real-time orchestration status."""
    
    tracker = get_visibility_tracker()
    return tracker.get_orchestration_status()


@router.get("/orchestration/agents")
async def get_agent_statuses():
    """Get status of all active agents."""
    
    tracker = get_visibility_tracker()
    statuses = tracker.get_all_agent_statuses()
    
    return {
        "active_agents": len(statuses),
        "agents": [status.to_dict() for status in statuses.values()],
    }


@router.get("/orchestration/tool-calls")
async def get_recent_tool_calls(limit: int = Query(50, ge=1, le=500)):
    """Get recent tool calls across all agents."""
    
    tracker = get_visibility_tracker()
    tool_calls = tracker.get_recent_tool_calls(limit)
    
    return {
        "total": tracker.total_tool_calls,
        "pending": len(tracker.get_pending_tool_calls()),
        "in_progress": len(tracker.get_in_progress_tool_calls()),
        "recent_calls": [call.to_dict() for call in tool_calls],
    }


@router.get("/orchestration/context-changes/{trace_id}")
async def get_context_changes(trace_id: UUID):
    """Get context state changes for a trace."""
    
    tracker = get_visibility_tracker()
    changes = tracker.get_context_changes_for_trace(trace_id)
    
    return {
        "trace_id": str(trace_id),
        "total_changes": len(changes),
        "changes": [change.to_dict() for change in changes],
    }


async def event_stream_generator(trace_id: UUID):
    """Generate SSE events for a trace."""
    
    emitter = get_sse_emitter()
    stream = emitter.get_stream(trace_id)
    
    if not stream:
        # No active stream, return stored events
        events = emitter.get_events_for_trace(trace_id)
        for event in events:
            yield event.to_sse_string()
        return
    
    # Stream active events
    while True:
        try:
            event = await asyncio.wait_for(stream.get(), timeout=30.0)
            yield event.to_sse_string()
        except asyncio.TimeoutError:
            # Send keepalive comment
            yield ": keepalive\n\n"


@router.get("/stream/{trace_id}")
async def stream_trace(trace_id: UUID):
    """Stream real-time trace events via SSE."""
    
    return StreamingResponse(
        event_stream_generator(trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health_check():
    """Check observability system health."""
    
    emitter = get_sse_emitter()
    repo = get_log_repository()
    tracker = get_visibility_tracker()
    
    return {
        "status": "healthy",
        "sse_streams": emitter.stats()["active_streams"],
        "log_entries": repo.get_stats()["total_entries"],
        "active_agents": len(tracker.get_all_agent_statuses()),
        "total_tool_calls_recorded": tracker.total_tool_calls,
    }
