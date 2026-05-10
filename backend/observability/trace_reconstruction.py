"""
Execution trace reconstruction and analysis.

Reconstructs complete execution traces from individual steps,
builds dependency graphs, and enables trace replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from ..schemas.execution import ExecutionTrace, ExecutionStep, ExecutionStepType


@dataclass
class TraceSpan:
    """A span represents a logical operation within a trace."""
    
    id: UUID
    trace_id: UUID
    parent_span_id: Optional[UUID] = None
    
    operation_name: str = ""
    span_type: str = ""
    
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    tags: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        end = self.end_time or datetime.utcnow()
        delta = (end - self.start_time).total_seconds()
        return delta * 1000


@dataclass
class DependencyEdge:
    """Edge in dependency graph between execution steps."""
    
    from_step: int  # step_number
    to_step: int
    edge_type: str  # "sequential", "conditional", "parallel", etc.
    description: str = ""


class DependencyGraph:
    """Tracks dependencies and causality between execution steps."""
    
    def __init__(self):
        self.edges: List[DependencyEdge] = []
        self.step_dependencies: Dict[int, Set[int]] = {}  # step -> set of dependencies
    
    def add_edge(
        self,
        from_step: int,
        to_step: int,
        edge_type: str = "sequential",
        description: str = ""
    ) -> None:
        """Add a dependency edge."""
        edge = DependencyEdge(
            from_step=from_step,
            to_step=to_step,
            edge_type=edge_type,
            description=description,
        )
        self.edges.append(edge)
        
        if to_step not in self.step_dependencies:
            self.step_dependencies[to_step] = set()
        self.step_dependencies[to_step].add(from_step)
    
    def get_dependencies(self, step_number: int) -> Set[int]:
        """Get all steps that must complete before this step."""
        return self.step_dependencies.get(step_number, set())
    
    def is_critical_path_step(self, step_number: int, total_duration_ms: float) -> bool:
        """Check if a step is on the critical path."""
        # A step is critical if reducing its duration would reduce overall duration
        # Simplified: if it has dependents, it's likely critical
        return any(
            edge.to_step == step_number or edge.from_step == step_number
            for edge in self.edges
        )


class TraceCollector:
    """Collects ExecutionStep data and builds complete ExecutionTrace."""
    
    def __init__(self):
        self.steps_by_trace: Dict[UUID, List[ExecutionStep]] = {}
        self.span_by_step: Dict[Tuple[UUID, int], TraceSpan] = {}
        self.dependency_graphs: Dict[UUID, DependencyGraph] = {}
    
    def add_step(self, step: ExecutionStep) -> None:
        """Add an execution step to the trace."""
        trace_id = step.execution_trace_id
        
        if trace_id not in self.steps_by_trace:
            self.steps_by_trace[trace_id] = []
            self.dependency_graphs[trace_id] = DependencyGraph()
        
        self.steps_by_trace[trace_id].append(step)
    
    def build_trace(self, trace: ExecutionTrace) -> ExecutionTrace:
        """Reconstruct complete trace with all steps in order."""
        trace_id = trace.id
        
        if trace_id in self.steps_by_trace:
            # Sort steps by step_number
            steps = sorted(
                self.steps_by_trace[trace_id],
                key=lambda s: s.step_number
            )
            # Update trace with reconstructed steps
            trace.steps = steps
        
        return trace
    
    def add_dependency(
        self,
        trace_id: UUID,
        from_step: int,
        to_step: int,
        edge_type: str = "sequential",
    ) -> None:
        """Record a dependency between steps."""
        if trace_id not in self.dependency_graphs:
            self.dependency_graphs[trace_id] = DependencyGraph()
        
        self.dependency_graphs[trace_id].add_edge(
            from_step, to_step, edge_type
        )
    
    def get_dependency_graph(self, trace_id: UUID) -> DependencyGraph:
        """Get the dependency graph for a trace."""
        return self.dependency_graphs.get(
            trace_id,
            DependencyGraph()
        )
    
    def analyze_critical_path(self, trace: ExecutionTrace) -> List[ExecutionStep]:
        """Find the critical path (slowest sequence of steps)."""
        dep_graph = self.get_dependency_graph(trace.id)
        
        critical_steps = [
            step for step in trace.steps
            if dep_graph.is_critical_path_step(step.step_number, trace.total_duration_ms)
        ]
        
        return sorted(critical_steps, key=lambda s: s.step_number)
    
    def get_slowest_steps(
        self,
        trace: ExecutionTrace,
        limit: int = 10
    ) -> List[ExecutionStep]:
        """Get the N slowest steps by duration."""
        return sorted(
            trace.steps,
            key=lambda s: s.duration_ms,
            reverse=True
        )[:limit]


class TraceAnalyzer:
    """Analyzes traces for insights and metrics."""
    
    @staticmethod
    def get_step_by_type(
        trace: ExecutionTrace,
        step_type: ExecutionStepType
    ) -> List[ExecutionStep]:
        """Get all steps of a specific type."""
        return [s for s in trace.steps if s.step_type == step_type]
    
    @staticmethod
    def get_tool_invocations(trace: ExecutionTrace) -> List[ExecutionStep]:
        """Get all tool call steps."""
        return TraceAnalyzer.get_step_by_type(
            trace, ExecutionStepType.TOOL_CALL
        )
    
    @staticmethod
    def count_tool_calls(trace: ExecutionTrace) -> int:
        """Count total tool invocations."""
        return len(TraceAnalyzer.get_tool_invocations(trace))
    
    @staticmethod
    def get_total_tool_duration(trace: ExecutionTrace) -> float:
        """Sum of all tool execution durations."""
        tool_steps = TraceAnalyzer.get_tool_invocations(trace)
        return sum(s.duration_ms for s in tool_steps)
    
    @staticmethod
    def get_tool_efficiency(trace: ExecutionTrace) -> float:
        """Ratio of tool time to total time."""
        total_tool_ms = TraceAnalyzer.get_total_tool_duration(trace)
        if trace.total_duration_ms == 0:
            return 0
        return total_tool_ms / trace.total_duration_ms
    
    @staticmethod
    def get_failed_steps(trace: ExecutionTrace) -> List[ExecutionStep]:
        """Get all failed execution steps."""
        return [s for s in trace.steps if s.status == "failed"]
    
    @staticmethod
    def has_errors(trace: ExecutionTrace) -> bool:
        """Check if trace has any errors."""
        return len(TraceAnalyzer.get_failed_steps(trace)) > 0
    
    @staticmethod
    def get_error_messages(trace: ExecutionTrace) -> List[str]:
        """Get all error messages."""
        return [
            s.error_message for s in TraceAnalyzer.get_failed_steps(trace)
            if s.error_message
        ]
    
    @staticmethod
    def get_total_cost(trace: ExecutionTrace) -> float:
        """Sum of all costs incurred."""
        return sum(
            s.cost_incurred or 0
            for s in trace.steps
        )
    
    @staticmethod
    def get_expensive_steps(
        trace: ExecutionTrace,
        limit: int = 10
    ) -> List[ExecutionStep]:
        """Get the most expensive steps."""
        return sorted(
            [s for s in trace.steps if s.cost_incurred],
            key=lambda s: s.cost_incurred,
            reverse=True
        )[:limit]
