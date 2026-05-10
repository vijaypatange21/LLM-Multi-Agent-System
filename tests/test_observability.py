"""
Tests for production-grade observability module.
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime

from backend.observability import (
    SSEEvent,
    SSEEventType,
    SSEEventQueue,
    SSEEmitter,
    TraceCollector,
    TraceAnalyzer,
    LatencyMetrics,
    TokenMetrics,
    PolicyViolationMetrics,
    MetricsCollector,
    LogLevel,
    LogEntry,
    LogRepository,
    StructuredLogger,
    get_logger,
    TraceReplayer,
    TimelineBuilder,
    ExecutionComparator,
    AgentStatus,
    AgentStatusSnapshot,
    ToolCallTrace,
    OrchestrationVisibilityTracker,
    get_visibility_tracker,
)
from backend.schemas.execution import ExecutionTrace, ExecutionStep, ExecutionStepType


class TestSSEEvents:
    """Test SSE event streaming."""
    
    def test_create_sse_event(self):
        """Create an SSE event."""
        trace_id = uuid4()
        conv_id = uuid4()
        
        event = SSEEvent(
            event_type=SSEEventType.AGENT_STARTED,
            trace_id=trace_id,
            conversation_id=conv_id,
            agent_id="test_agent",
        )
        
        assert event.event_type == SSEEventType.AGENT_STARTED
        assert event.agent_id == "test_agent"
    
    def test_sse_event_serialization(self):
        """Serialize SSE event to JSON."""
        trace_id = uuid4()
        conv_id = uuid4()
        
        event = SSEEvent(
            event_type=SSEEventType.TOOL_CALL,
            trace_id=trace_id,
            conversation_id=conv_id,
            tool_name="search",
            data={"query": "test"},
        )
        
        json_str = event.to_json()
        assert "tool_call" in json_str
        assert "search" in json_str
    
    @pytest.mark.asyncio
    async def test_sse_event_queue(self):
        """Test async SSE event queue."""
        queue = SSEEventQueue()
        
        trace_id = uuid4()
        event = SSEEvent(
            event_type=SSEEventType.AGENT_COMPLETED,
            trace_id=trace_id,
            conversation_id=uuid4(),
        )
        
        await queue.put(event)
        
        retrieved = await queue.get()
        assert retrieved.event_type == SSEEventType.AGENT_COMPLETED
        
        assert queue.stats()["total_events"] == 1
    
    @pytest.mark.asyncio
    async def test_sse_emitter(self):
        """Test SSE emitter."""
        emitter = SSEEmitter()
        
        trace_id = uuid4()
        conv_id = uuid4()
        
        # Create stream
        stream = emitter.create_stream(trace_id)
        assert stream is not None
        
        # Emit event
        event = SSEEvent(
            event_type=SSEEventType.TOKEN_GENERATED,
            trace_id=trace_id,
            conversation_id=conv_id,
            token_count=100,
        )
        
        await emitter.emit(event)
        
        # Retrieve from stream
        retrieved = await stream.get()
        assert retrieved.token_count == 100
        
        # Get for replay
        events = emitter.get_events_for_trace(trace_id)
        assert len(events) > 0


class TestTraceReconstruction:
    """Test trace collection and reconstruction."""
    
    def test_trace_collector(self):
        """Collect execution steps."""
        collector = TraceCollector()
        
        trace_id = uuid4()
        step = ExecutionStep(
            execution_trace_id=trace_id,
            step_type=ExecutionStepType.PLANNING,
            step_number=1,
            description="Plan the approach",
            duration_ms=100,
        )
        
        collector.add_step(step)
        
        assert trace_id in collector.steps_by_trace
        assert len(collector.steps_by_trace[trace_id]) == 1
    
    def test_dependency_graph(self):
        """Build dependency graph."""
        from backend.observability import DependencyGraph
        
        graph = DependencyGraph()
        
        # Add dependencies: step 2 depends on 1, step 3 depends on 2
        graph.add_edge(1, 2, "sequential")
        graph.add_edge(2, 3, "sequential")
        
        assert 1 in graph.get_dependencies(2)
        assert 2 in graph.get_dependencies(3)


class TestMetrics:
    """Test metrics collection."""
    
    def test_latency_metrics(self):
        """Collect and calculate latency metrics."""
        metrics = LatencyMetrics()
        
        metrics.add_sample(100)
        metrics.add_sample(200)
        metrics.add_sample(150)
        
        assert metrics.count == 3
        assert metrics.mean_ms == pytest.approx(150)
        assert metrics.min_ms == 100
        assert metrics.max_ms == 200
    
    def test_token_metrics(self):
        """Collect token metrics."""
        metrics = TokenMetrics()
        
        metrics.add_tokens(100, 50, cost=0.01)
        metrics.add_tokens(150, 75, cost=0.015)
        
        assert metrics.total_tokens == 375
        assert metrics.sample_count == 2
        assert metrics.total_cost == pytest.approx(0.025)
    
    def test_policy_violation_metrics(self):
        """Track policy violations."""
        metrics = PolicyViolationMetrics()
        
        metrics.add_violation("budget_exceeded", "agent1")
        metrics.add_violation("budget_exceeded", "agent2")
        metrics.add_violation("context_overflow", "agent1")
        
        assert metrics.total_violations == 3
        assert metrics.violations_by_type["budget_exceeded"] == 2
        assert metrics.violations_by_agent["agent1"] == 2


class TestLogs:
    """Test structured logging."""
    
    def test_log_entry_creation(self):
        """Create a log entry."""
        trace_id = uuid4()
        conv_id = uuid4()
        
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.INFO,
            logger="test.module",
            message="Test message",
            trace_id=trace_id,
            conversation_id=conv_id,
            agent_id="test_agent",
        )
        
        assert entry.level == LogLevel.INFO
        assert entry.message == "Test message"
    
    def test_log_repository(self):
        """Store and query logs."""
        repo = LogRepository()
        
        trace_id = uuid4()
        conv_id = uuid4()
        
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.WARNING,
            logger="test",
            message="Warning message",
            trace_id=trace_id,
            conversation_id=conv_id,
        )
        
        repo.add(entry)
        
        # Query by trace
        results = repo.get_by_trace(trace_id)
        assert len(results) == 1
        assert results[0].level == LogLevel.WARNING
    
    def test_structured_logger(self):
        """Use structured logger."""
        repo = LogRepository()
        logger = StructuredLogger("test", repo)
        
        trace_id = uuid4()
        conv_id = uuid4()
        
        logger.info(
            "Test info",
            trace_id=trace_id,
            conversation_id=conv_id,
            agent_id="agent1",
            custom_field="value",
        )
        
        results = repo.get_by_trace(trace_id)
        assert len(results) == 1
        assert results[0].fields["custom_field"] == "value"
    
    def test_log_search(self):
        """Search logs with filters."""
        repo = LogRepository()
        
        trace1 = uuid4()
        trace2 = uuid4()
        conv_id = uuid4()
        
        for i in range(5):
            repo.add(LogEntry(
                timestamp=datetime.utcnow(),
                level=LogLevel.INFO,
                logger="test",
                message=f"Message {i}",
                trace_id=trace1,
                conversation_id=conv_id,
            ))
        
        # Search by trace
        results = repo.search("Message 2", trace_id=trace1)
        assert len(results) >= 1
        
        # Get errors (none exist)
        errors = repo.get_errors_and_warnings()
        assert len(errors) == 0


class TestTraceReplay:
    """Test trace replay and timeline."""
    
    def _create_test_trace(self) -> ExecutionTrace:
        """Create a test trace."""
        trace = ExecutionTrace(
            id=uuid4(),
            conversation_id=uuid4(),
            agent_id="test_agent",
            total_duration_ms=300,
        )
        
        for i in range(3):
            step = ExecutionStep(
                execution_trace_id=trace.id,
                step_type=ExecutionStepType.REASONING,
                step_number=i + 1,
                description=f"Step {i + 1}",
                duration_ms=100 * (i + 1),
            )
            trace.steps.append(step)
        
        trace.total_duration_ms = sum(s.duration_ms for s in trace.steps)
        return trace
    
    def test_trace_replayer(self):
        """Replay a trace step-by-step."""
        trace = self._create_test_trace()
        replayer = TraceReplayer(trace)
        
        frame1 = replayer.step_forward()
        assert frame1 is not None
        assert frame1.step_number == 1
        
        frame2 = replayer.step_forward()
        assert frame2.step_number == 2
    
    def test_trace_analyzer(self):
        """Analyze trace metrics."""
        trace = self._create_test_trace()
        
        # Add a tool call
        tool_step = ExecutionStep(
            execution_trace_id=trace.id,
            step_type=ExecutionStepType.TOOL_CALL,
            step_number=4,
            description="Call tool",
            duration_ms=500,
            input_data={"tool_name": "search"},
        )
        trace.steps.append(tool_step)
        trace.total_duration_ms += 500
        
        analyzer = TraceAnalyzer()
        tool_calls = analyzer.get_tool_invocations(trace)
        assert len(tool_calls) == 1
    
    def test_execution_comparator(self):
        """Compare two traces."""
        trace1 = self._create_test_trace()
        
        trace2 = self._create_test_trace()
        # Make it faster
        for step in trace2.steps:
            step.duration_ms = step.duration_ms * 0.5
        trace2.total_duration_ms = sum(s.duration_ms for s in trace2.steps)
        
        comparison = ExecutionComparator.compare(trace1, trace2)
        
        assert "deltas" in comparison
        assert comparison["deltas"]["duration_delta_ms"] < 0  # Faster


class TestOrchestrationVisibility:
    """Test real-time orchestration visibility."""
    
    def test_agent_status_snapshot(self):
        """Create agent status snapshot."""
        trace_id = uuid4()
        
        status = AgentStatusSnapshot(
            agent_id="agent1",
            trace_id=trace_id,
            status=AgentStatus.EXECUTING_TOOL,
            current_step_number=2,
            total_steps=5,
            current_tool="search",
        )
        
        assert status.status == AgentStatus.EXECUTING_TOOL
        assert status.current_tool == "search"
    
    def test_tool_call_trace(self):
        """Record a tool call."""
        trace_id = uuid4()
        
        tool_call = ToolCallTrace(
            id=uuid4(),
            agent_id="agent1",
            trace_id=trace_id,
            tool_name="search",
            tool_args={"query": "test"},
        )
        
        assert tool_call.tool_name == "search"
        assert tool_call.status == "pending"
    
    def test_visibility_tracker(self):
        """Track real-time orchestration."""
        tracker = OrchestrationVisibilityTracker()
        
        trace_id = uuid4()
        
        # Update agent status
        status = AgentStatusSnapshot(
            agent_id="agent1",
            trace_id=trace_id,
            status=AgentStatus.EXECUTING_TOOL,
        )
        tracker.update_agent_status(status)
        
        retrieved = tracker.get_agent_status("agent1")
        assert retrieved.status == AgentStatus.EXECUTING_TOOL
        
        # Record tool call
        tool_call = ToolCallTrace(
            id=uuid4(),
            agent_id="agent1",
            trace_id=trace_id,
            tool_name="search",
            tool_args={},
        )
        tracker.record_tool_call(tool_call)
        
        assert tracker.total_tool_calls == 1
        
        # Get orchestration status
        status = tracker.get_orchestration_status()
        assert status["active_agents"] == 1
        assert status["total_tool_calls"] == 1
