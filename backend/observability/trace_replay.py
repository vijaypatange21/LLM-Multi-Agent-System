"""
Trace replay and timeline visualization.

Enables:
- Step-by-step execution replay
- Timeline visualization
- State snapshots at each step
- Dependency visualization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..schemas.execution import ExecutionTrace, ExecutionStep, ExecutionStepType
from .trace_reconstruction import TraceCollector, TraceAnalyzer, DependencyGraph


@dataclass
class ReplayFrame:
    """A single frame in trace replay."""
    
    step_number: int
    step_type: ExecutionStepType
    
    description: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    
    timestamp: datetime
    duration_ms: float
    status: str
    
    # State at this point
    agent_state: Dict[str, Any] = field(default_factory=dict)
    context_state: Dict[str, Any] = field(default_factory=dict)
    
    # Error info
    error_message: Optional[str] = None
    
    # Navigation
    can_step_forward: bool = True
    can_step_backward: bool = True


@dataclass
class TraceTimeline:
    """Timeline view of a trace for visualization."""
    
    trace_id: UUID
    conversation_id: UUID
    
    total_duration_ms: float
    frame_count: int
    
    # Timeline events
    frames: List[ReplayFrame] = field(default_factory=list)
    
    # Dependency graph
    dependencies: Dict[int, List[int]] = field(default_factory=dict)
    
    # Critical path
    critical_steps: List[int] = field(default_factory=list)
    
    # Performance hotspots
    slowest_steps: List[tuple[int, float]] = field(default_factory=list)
    
    def get_frame(self, step_number: int) -> Optional[ReplayFrame]:
        """Get a specific frame."""
        for frame in self.frames:
            if frame.step_number == step_number:
                return frame
        return None
    
    def get_step_percentage(self, step_number: int) -> float:
        """Get percentage of trace completed at this step."""
        if self.total_duration_ms == 0:
            return 0
        
        frame = self.get_frame(step_number)
        if not frame:
            return 0
        
        # Approximate based on frame time relative to total
        return min(100.0, (frame.timestamp.timestamp() / self.total_duration_ms) * 100)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON transmission."""
        return {
            "trace_id": str(self.trace_id),
            "conversation_id": str(self.conversation_id),
            "total_duration_ms": self.total_duration_ms,
            "frame_count": self.frame_count,
            "frames": [
                {
                    "step_number": f.step_number,
                    "step_type": f.step_type.value,
                    "description": f.description,
                    "duration_ms": f.duration_ms,
                    "status": f.status,
                    "error_message": f.error_message,
                }
                for f in self.frames
            ],
            "critical_steps": self.critical_steps,
            "slowest_steps": self.slowest_steps,
        }


class TraceReplayer:
    """Replays execution traces step-by-step."""
    
    def __init__(self, trace: ExecutionTrace):
        self.trace = trace
        self.current_step = 0
        self.states: Dict[int, Dict[str, Any]] = {}
    
    def reset(self) -> None:
        """Reset replay to beginning."""
        self.current_step = 0
        self.states.clear()
    
    def step_forward(self) -> Optional[ReplayFrame]:
        """Move to next step."""
        if self.current_step >= len(self.trace.steps):
            return None
        
        step = self.trace.steps[self.current_step]
        frame = self._step_to_frame(step)
        
        self.current_step += 1
        return frame
    
    def step_backward(self) -> Optional[ReplayFrame]:
        """Move to previous step."""
        if self.current_step <= 0:
            return None
        
        self.current_step -= 1
        step = self.trace.steps[self.current_step]
        return self._step_to_frame(step)
    
    def jump_to_step(self, step_number: int) -> Optional[ReplayFrame]:
        """Jump to a specific step."""
        if step_number < 0 or step_number >= len(self.trace.steps):
            return None
        
        self.current_step = step_number
        step = self.trace.steps[step_number]
        return self._step_to_frame(step)
    
    def get_current_frame(self) -> Optional[ReplayFrame]:
        """Get current frame without advancing."""
        if self.current_step >= len(self.trace.steps):
            return None
        
        step = self.trace.steps[self.current_step]
        return self._step_to_frame(step)
    
    def _step_to_frame(self, step: ExecutionStep) -> ReplayFrame:
        """Convert ExecutionStep to ReplayFrame."""
        return ReplayFrame(
            step_number=step.step_number,
            step_type=step.step_type,
            description=step.description,
            input_data=step.input_data or {},
            output_data=step.output_data,
            timestamp=step.started_at,
            duration_ms=step.duration_ms,
            status=step.status,
            error_message=step.error_message,
            agent_state=self.states.get(step.step_number, {}),
        )
    
    def get_all_frames(self) -> List[ReplayFrame]:
        """Get all frames for the trace."""
        frames = []
        for step in self.trace.steps:
            frame = self._step_to_frame(step)
            frames.append(frame)
        return frames


class TimelineBuilder:
    """Builds timeline views from traces."""
    
    def __init__(self, collector: TraceCollector):
        self.collector = collector
        self.analyzer = TraceAnalyzer()
    
    def build_timeline(self, trace: ExecutionTrace) -> TraceTimeline:
        """Build a timeline for a trace."""
        replayer = TraceReplayer(trace)
        frames = replayer.get_all_frames()
        
        # Get dependency graph
        dep_graph = self.collector.get_dependency_graph(trace.id)
        
        # Find critical path
        critical_steps = [
            s.step_number for s in self.analyzer.analyze_critical_path(trace)
        ]
        
        # Find slowest steps
        slowest = self.analyzer.get_slowest_steps(trace, limit=10)
        slowest_steps = [(s.step_number, s.duration_ms) for s in slowest]
        
        # Build timeline
        timeline = TraceTimeline(
            trace_id=trace.id,
            conversation_id=trace.conversation_id,
            total_duration_ms=trace.total_duration_ms,
            frame_count=len(frames),
            frames=frames,
            critical_steps=critical_steps,
            slowest_steps=slowest_steps,
        )
        
        # Add dependencies
        for edge in dep_graph.edges:
            if edge.from_step not in timeline.dependencies:
                timeline.dependencies[edge.from_step] = []
            timeline.dependencies[edge.from_step].append(edge.to_step)
        
        return timeline


class ExecutionComparator:
    """Compares two execution traces."""
    
    @staticmethod
    def compare(trace1: ExecutionTrace, trace2: ExecutionTrace) -> Dict[str, Any]:
        """Compare two traces and return differences."""
        
        analyzer = TraceAnalyzer()
        
        stats1 = {
            "duration_ms": trace1.total_duration_ms,
            "steps": len(trace1.steps),
            "tool_calls": analyzer.count_tool_calls(trace1),
            "total_cost": analyzer.get_total_cost(trace1),
            "errors": len(analyzer.get_failed_steps(trace1)),
        }
        
        stats2 = {
            "duration_ms": trace2.total_duration_ms,
            "steps": len(trace2.steps),
            "tool_calls": analyzer.count_tool_calls(trace2),
            "total_cost": analyzer.get_total_cost(trace2),
            "errors": len(analyzer.get_failed_steps(trace2)),
        }
        
        return {
            "trace1": stats1,
            "trace2": stats2,
            "deltas": {
                "duration_delta_ms": trace2.total_duration_ms - trace1.total_duration_ms,
                "duration_improvement_percent": (
                    (1 - trace2.total_duration_ms / trace1.total_duration_ms) * 100
                    if trace1.total_duration_ms > 0 else 0
                ),
                "cost_delta": stats2["total_cost"] - stats1["total_cost"],
                "cost_improvement_percent": (
                    (1 - stats2["total_cost"] / stats1["total_cost"]) * 100
                    if stats1["total_cost"] > 0 else 0
                ),
            }
        }
