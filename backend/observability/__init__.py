"""
Production-grade observability module.

Provides:
- SSE streaming for real-time visibility
- Structured execution tracing
- Queryable logs with filtering
- Latency and token metrics
- Policy violation tracking
- Trace replay and timeline reconstruction
- Real-time orchestration visibility
"""

from .sse_events import (
    SSEEvent,
    SSEEventType,
    SSEEventQueue,
    SSEEmitter,
    get_sse_emitter,
)

from .trace_reconstruction import (
    TraceSpan,
    DependencyEdge,
    DependencyGraph,
    TraceCollector,
    TraceAnalyzer,
)

from .metrics import (
    LatencyMetrics,
    TokenMetrics,
    PolicyViolationMetrics,
    MetricsCollector,
)

from .logs import (
    LogLevel,
    LogEntry,
    LogRepository,
    StructuredLogger,
    LoggerFactory,
    get_log_repository,
    get_logger,
)

from .trace_replay import (
    ReplayFrame,
    TraceTimeline,
    TraceReplayer,
    TimelineBuilder,
    ExecutionComparator,
)

from .orchestration_visibility import (
    AgentStatus,
    AgentStatusSnapshot,
    ToolCallTrace,
    ContextStateChange,
    OrchestrationVisibilityTracker,
    get_visibility_tracker,
)

__all__ = [
    # SSE Events
    "SSEEvent",
    "SSEEventType",
    "SSEEventQueue",
    "SSEEmitter",
    "get_sse_emitter",
    # Trace Reconstruction
    "TraceSpan",
    "DependencyEdge",
    "DependencyGraph",
    "TraceCollector",
    "TraceAnalyzer",
    # Metrics
    "LatencyMetrics",
    "TokenMetrics",
    "PolicyViolationMetrics",
    "MetricsCollector",
    # Logs
    "LogLevel",
    "LogEntry",
    "LogRepository",
    "StructuredLogger",
    "LoggerFactory",
    "get_log_repository",
    "get_logger",
    # Trace Replay
    "ReplayFrame",
    "TraceTimeline",
    "TraceReplayer",
    "TimelineBuilder",
    "ExecutionComparator",
    # Orchestration Visibility
    "AgentStatus",
    "AgentStatusSnapshot",
    "ToolCallTrace",
    "ContextStateChange",
    "OrchestrationVisibilityTracker",
    "get_visibility_tracker",
]
