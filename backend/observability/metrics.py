"""
Metrics collection and aggregation for observability.

Tracks:
- Latency metrics (P50, P95, P99, mean, max)
- Token metrics (usage, costs)
- Policy violation metrics
- Per-agent and per-trace metrics
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median, quantiles
from typing import Dict, List, Optional
from uuid import UUID

from ..schemas.execution import ExecutionTrace, ExecutionStep


@dataclass
class LatencyMetrics:
    """Latency statistics for operations."""
    
    count: int = 0
    min_ms: float = 0
    max_ms: float = 0
    mean_ms: float = 0
    median_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    
    total_ms: float = 0
    samples: List[float] = field(default_factory=list)
    
    def add_sample(self, duration_ms: float) -> None:
        """Add a duration sample."""
        self.samples.append(duration_ms)
        self.total_ms += duration_ms
        self.count += 1
        self._recalculate()
    
    def _recalculate(self) -> None:
        """Recalculate metrics from samples."""
        if not self.samples:
            return
        
        sorted_samples = sorted(self.samples)
        self.min_ms = sorted_samples[0]
        self.max_ms = sorted_samples[-1]
        self.mean_ms = self.total_ms / len(self.samples)
        self.median_ms = median(sorted_samples)
        
        if len(sorted_samples) >= 100:
            quantiles_list = quantiles(sorted_samples, n=100)
            self.p95_ms = quantiles_list[94]  # 95th percentile
            self.p99_ms = quantiles_list[98]  # 99th percentile
        elif len(sorted_samples) > 1:
            # Simplified for small samples
            self.p95_ms = sorted_samples[int(len(sorted_samples) * 0.95)]
            self.p99_ms = sorted_samples[int(len(sorted_samples) * 0.99)]
        else:
            self.p95_ms = self.p99_ms = self.mean_ms


@dataclass
class TokenMetrics:
    """Token usage and cost metrics."""
    
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    
    total_cost: float = 0
    cost_by_agent: Dict[str, float] = field(default_factory=dict)
    
    sample_count: int = 0
    samples: List[int] = field(default_factory=list)
    
    def add_tokens(self, prompt: int, completion: int, cost: float = 0) -> None:
        """Record token usage."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.total_cost += cost
        self.sample_count += 1
        self.samples.append(prompt + completion)
    
    def add_agent_cost(self, agent_id: str, cost: float) -> None:
        """Add cost for a specific agent."""
        if agent_id not in self.cost_by_agent:
            self.cost_by_agent[agent_id] = 0
        self.cost_by_agent[agent_id] += cost
    
    def avg_tokens_per_call(self) -> float:
        """Average tokens per call."""
        if self.sample_count == 0:
            return 0
        return self.total_tokens / self.sample_count


@dataclass
class PolicyViolationMetrics:
    """Tracking of policy violations."""
    
    total_violations: int = 0
    violations_by_type: Dict[str, int] = field(default_factory=dict)
    violations_by_agent: Dict[str, int] = field(default_factory=dict)
    
    def add_violation(self, violation_type: str, agent_id: str) -> None:
        """Record a policy violation."""
        self.total_violations += 1
        
        if violation_type not in self.violations_by_type:
            self.violations_by_type[violation_type] = 0
        self.violations_by_type[violation_type] += 1
        
        if agent_id not in self.violations_by_agent:
            self.violations_by_agent[agent_id] = 0
        self.violations_by_agent[agent_id] += 1


class MetricsCollector:
    """Collects and aggregates metrics across traces."""
    
    def __init__(self):
        # Per-agent latency metrics
        self.latency_by_agent: Dict[str, LatencyMetrics] = defaultdict(LatencyMetrics)
        
        # Per-agent token metrics
        self.tokens_by_agent: Dict[str, TokenMetrics] = defaultdict(TokenMetrics)
        
        # Per-trace metrics
        self.trace_latencies: Dict[UUID, float] = {}
        self.trace_tokens: Dict[UUID, int] = {}
        self.trace_costs: Dict[UUID, float] = {}
        
        # Tool metrics
        self.tool_latencies: Dict[str, LatencyMetrics] = defaultdict(LatencyMetrics)
        
        # Policy violations
        self.policy_violations = PolicyViolationMetrics()
        
        # Overall metrics
        self.total_traces: int = 0
        self.total_agents: int = 0
        self.start_time: datetime = datetime.utcnow()
    
    def collect_trace(self, trace: ExecutionTrace) -> None:
        """Collect metrics from a completed trace."""
        self.total_traces += 1
        trace_id = trace.id
        
        # Record trace-level metrics
        self.trace_latencies[trace_id] = trace.total_duration_ms
        
        # Process each step
        for step in trace.steps:
            agent_id = trace.agent_id or "unknown"
            
            if agent_id not in self.latency_by_agent:
                self.total_agents += 1
            
            # Latency for this step
            self.latency_by_agent[agent_id].add_sample(step.duration_ms)
            
            # Cost for this step
            if step.cost_incurred:
                self.trace_costs[trace_id] = self.trace_costs.get(trace_id, 0) + step.cost_incurred
                self.tokens_by_agent[agent_id].total_cost += step.cost_incurred
            
            # Tool-specific metrics
            if step.step_type.value == "tool_call":
                tool_name = step.input_data.get("tool_name", "unknown")
                self.tool_latencies[tool_name].add_sample(step.duration_ms)
    
    def get_agent_latency_metrics(self, agent_id: str) -> LatencyMetrics:
        """Get latency metrics for an agent."""
        return self.latency_by_agent[agent_id]
    
    def get_agent_token_metrics(self, agent_id: str) -> TokenMetrics:
        """Get token metrics for an agent."""
        return self.tokens_by_agent[agent_id]
    
    def get_tool_latency_metrics(self, tool_name: str) -> LatencyMetrics:
        """Get latency metrics for a tool."""
        return self.tool_latencies[tool_name]
    
    def get_slowest_agents(self, limit: int = 10) -> List[tuple[str, float]]:
        """Get agents ranked by mean latency."""
        agents = [
            (agent_id, metrics.mean_ms)
            for agent_id, metrics in self.latency_by_agent.items()
        ]
        return sorted(agents, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_slowest_tools(self, limit: int = 10) -> List[tuple[str, float]]:
        """Get tools ranked by mean latency."""
        tools = [
            (tool_name, metrics.mean_ms)
            for tool_name, metrics in self.tool_latencies.items()
        ]
        return sorted(tools, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_most_expensive_agents(self, limit: int = 10) -> List[tuple[str, float]]:
        """Get agents ranked by total cost."""
        agents = [
            (agent_id, metrics.total_cost)
            for agent_id, metrics in self.tokens_by_agent.items()
        ]
        return sorted(agents, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_summary(self) -> Dict:
        """Get summary metrics."""
        uptime = (datetime.utcnow() - self.start_time).total_seconds() / 3600
        
        return {
            "uptime_hours": uptime,
            "total_traces": self.total_traces,
            "total_agents": self.total_agents,
            "total_tools": len(self.tool_latencies),
            
            "average_trace_duration_ms": sum(self.trace_latencies.values()) / max(1, len(self.trace_latencies)),
            "total_traces_cost": sum(self.trace_costs.values()),
            
            "slowest_agents": self.get_slowest_agents(5),
            "slowest_tools": self.get_slowest_tools(5),
            "most_expensive_agents": self.get_most_expensive_agents(5),
            
            "policy_violations": self.policy_violations,
        }
