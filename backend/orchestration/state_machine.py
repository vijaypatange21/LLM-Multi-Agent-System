"""
Orchestration state machine and event logging.

The state machine tracks the execution flow:
PLANNING -> VALIDATION -> SCHEDULING -> EXECUTING -> COLLECTING -> AGGREGATING -> COMPLETED

Event logger provides structured, queryable logs of all orchestration decisions.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from .schemas import (
    ExecutionStep,
    OrchestrationEvent,
    OrchestrationEventType,
    OrchestrationTrace,
    PolicyViolation,
)


class OrchestrationStateMachine:
    """
    Manages orchestration execution flow and state transitions.
    
    WHY: Explicit state machine:
    - Prevents invalid transitions (e.g., can't execute before planning)
    - Makes state visible for monitoring
    - Enables step-by-step execution and pausing
    - Helps with debugging (know exactly what stage failed)
    """
    
    # Valid state transitions
    TRANSITIONS = {
        ExecutionStep.PLANNING: [ExecutionStep.VALIDATION],
        ExecutionStep.VALIDATION: [ExecutionStep.PLANNING, ExecutionStep.SCHEDULING],
        ExecutionStep.SCHEDULING: [ExecutionStep.EXECUTING],
        ExecutionStep.EXECUTING: [ExecutionStep.COLLECTING_RESULTS],
        ExecutionStep.COLLECTING_RESULTS: [ExecutionStep.AGGREGATING],
        ExecutionStep.AGGREGATING: [ExecutionStep.COMPLETED],
        ExecutionStep.COMPLETED: [],
    }
    
    def __init__(self):
        self.current_state = ExecutionStep.PLANNING
        self.state_entered_at: Dict[ExecutionStep, datetime] = {}
        self.state_durations: Dict[ExecutionStep, float] = {}
        self._mark_state_entry()
    
    def _mark_state_entry(self):
        """Record when we entered current state."""
        self.state_entered_at[self.current_state] = datetime.utcnow()
    
    def _record_state_duration(self):
        """Record time spent in current state."""
        if self.current_state in self.state_entered_at:
            entered = self.state_entered_at[self.current_state]
            duration_ms = (datetime.utcnow() - entered).total_seconds() * 1000
            self.state_durations[self.current_state] = duration_ms
    
    def can_transition_to(self, new_state: ExecutionStep) -> bool:
        """Check if transition is valid."""
        valid_next_states = self.TRANSITIONS.get(self.current_state, [])
        return new_state in valid_next_states
    
    def transition_to(self, new_state: ExecutionStep) -> bool:
        """
        Attempt to transition to new state.
        
        Returns:
            True if transition succeeded, False if invalid
        """
        if not self.can_transition_to(new_state):
            return False
        
        self._record_state_duration()
        self.current_state = new_state
        self._mark_state_entry()
        return True
    
    def get_state_duration_ms(self, state: ExecutionStep) -> float:
        """Get time spent in a state."""
        return self.state_durations.get(state, 0.0)


class StructuredOrchestrationLogger:
    """
    Structured event logger for orchestration.
    
    WHY: Structured logging enables:
    - Aggregation: search logs by event type, agent, etc.
    - Analytics: query patterns, routing patterns
    - Monitoring: alerts on rare events
    - Debugging: replay execution step-by-step
    - Compliance: audit trail of decisions
    
    Events are structured JSON for machine parsing.
    """
    
    def __init__(
        self,
        orchestration_trace: OrchestrationTrace,
        base_logger: Optional[logging.Logger] = None,
    ):
        self.trace = orchestration_trace
        self.base_logger = base_logger or logging.getLogger(__name__)
        self.state_machine = OrchestrationStateMachine()
        self.started_at = datetime.utcnow()
    
    def _elapsed_ms(self) -> float:
        """Time since orchestration started."""
        return (datetime.utcnow() - self.started_at).total_seconds() * 1000
    
    def log_event(
        self,
        event_type: OrchestrationEventType,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        decision_explanation: Optional[str] = None,
    ) -> OrchestrationEvent:
        """
        Log a structured orchestration event.
        
        Args:
            event_type: Type of event
            message: Human-readable description
            details: Event-specific details
            decision_explanation: For decision events, why was this chosen?
        
        Returns:
            The created event
        """
        event = OrchestrationEvent(
            orchestration_trace_id=self.trace.id,
            conversation_id=self.trace.conversation_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            message=message,
            details=details or {},
            current_stage=self.state_machine.current_state,
            elapsed_time_ms=self._elapsed_ms(),
            cost_incurred_this_event=details.get("cost", 0.0) if details else 0.0,
            cumulative_cost=self.trace.total_cost,
            decision_explanation=decision_explanation,
        )
        
        # Add to trace
        self.trace.events.append(event)
        
        # Also log to structured JSON logger
        log_data = {
            "event_type": event_type.value,
            "message": message,
            "stage": self.state_machine.current_state.value,
            "elapsed_ms": event.elapsed_time_ms,
            "trace_id": str(self.trace.id),
            "conversation_id": str(self.trace.conversation_id),
        }
        
        if details:
            log_data["details"] = details
        
        if decision_explanation:
            log_data["decision_explanation"] = decision_explanation
        
        # Log to Python logger
        self.base_logger.info(
            f"ORCHESTRATION_EVENT: {event_type.value}",
            extra={"structured": log_data}
        )
        
        return event
    
    def log_query_received(self, query: str) -> OrchestrationEvent:
        """Log that a query was received."""
        return self.log_event(
            OrchestrationEventType.QUERY_RECEIVED,
            f"Received query: {query[:100]}...",
            details={"query": query},
        )
    
    def log_analysis_started(self) -> OrchestrationEvent:
        """Log that query analysis is starting."""
        return self.log_event(
            OrchestrationEventType.ANALYSIS_STARTED,
            "Starting query analysis to determine required agents",
        )
    
    def log_routing_decision(
        self,
        agent_id: str,
        decided_to_select: bool,
        reasoning: str,
        score: float,
    ) -> OrchestrationEvent:
        """Log a routing decision."""
        decision = "SELECTED" if decided_to_select else "REJECTED"
        return self.log_event(
            OrchestrationEventType.ROUTING_DECISION,
            f"{decision} agent {agent_id}",
            details={
                "agent_id": agent_id,
                "decision": decision,
                "score": score,
            },
            decision_explanation=reasoning,
        )
    
    def log_plan_created(
        self,
        planned_agents: list,
        estimated_cost: float,
        estimated_time_ms: float,
    ) -> OrchestrationEvent:
        """Log that execution plan was created."""
        return self.log_event(
            OrchestrationEventType.PLAN_CREATED,
            f"Created execution plan with {len(planned_agents)} agents",
            details={
                "agents": planned_agents,
                "estimated_cost": estimated_cost,
                "estimated_time_ms": estimated_time_ms,
            },
            decision_explanation=f"Selected agents to handle query: {', '.join(planned_agents)}",
        )
    
    def log_agent_started(self, agent_id: str) -> OrchestrationEvent:
        """Log that agent execution started."""
        return self.log_event(
            OrchestrationEventType.AGENT_STARTED,
            f"Started executing agent: {agent_id}",
            details={"agent_id": agent_id},
        )
    
    def log_agent_completed(
        self,
        agent_id: str,
        cost: float,
        tokens_used: int,
    ) -> OrchestrationEvent:
        """Log that agent completed successfully."""
        return self.log_event(
            OrchestrationEventType.AGENT_COMPLETED,
            f"Agent {agent_id} completed successfully",
            details={
                "agent_id": agent_id,
                "cost": cost,
                "tokens_used": tokens_used,
            },
        )
    
    def log_agent_failed(
        self,
        agent_id: str,
        error: str,
        retry_count: int = 0,
    ) -> OrchestrationEvent:
        """Log that agent failed."""
        event_type = (
            OrchestrationEventType.RETRY_ATTEMPT
            if retry_count > 0
            else OrchestrationEventType.AGENT_FAILED
        )
        
        return self.log_event(
            event_type,
            f"Agent {agent_id} failed: {error}",
            details={
                "agent_id": agent_id,
                "error": error,
                "retry_count": retry_count,
            },
            decision_explanation=f"Failed with: {error}",
        )
    
    def log_budget_constraint(
        self,
        current_cost: float,
        budget_limit: float,
        agent_rejected: str,
    ) -> OrchestrationEvent:
        """Log budget constraint violation."""
        return self.log_event(
            OrchestrationEventType.BUDGET_CONSTRAINT,
            f"Budget constraint: {current_cost} / {budget_limit}",
            details={
                "current_cost": current_cost,
                "budget_limit": budget_limit,
                "agent_rejected": agent_rejected,
            },
            decision_explanation=f"Rejected {agent_rejected} due to budget constraint",
        )

    def log_policy_violation(
        self,
        violation: PolicyViolation,
    ) -> OrchestrationEvent:
        """Log a structured policy violation."""
        self.trace.policy_violations.append(violation)
        return self.log_event(
            OrchestrationEventType.POLICY_VIOLATION,
            violation.message,
            details={
                "violation_type": violation.violation_type.value,
                "agent_id": violation.agent_id,
                "severity": violation.severity,
                **violation.details,
            },
            decision_explanation=violation.message,
        )

    def log_context_updated(self, updates: Dict[str, Any]) -> OrchestrationEvent:
        """Log that shared context was updated."""
        return self.log_event(
            OrchestrationEventType.CONTEXT_UPDATED,
            "Shared context updated with new facts/constraints",
            details={"updates": updates},
        )
    
    def log_result_aggregated(
        self,
        aggregated_result: Dict[str, Any],
    ) -> OrchestrationEvent:
        """Log that results were aggregated."""
        return self.log_event(
            OrchestrationEventType.RESULT_AGGREGATED,
            "Aggregated results from all agents",
            details={"result_summary": str(aggregated_result)[:200]},
        )
    
    def log_orchestration_completed(
        self,
        final_output: Dict[str, Any],
        total_cost: float,
        total_tokens: int,
    ) -> OrchestrationEvent:
        """Log successful orchestration completion."""
        self.trace.final_output = final_output
        self.trace.total_cost = total_cost
        self.trace.status = "completed"
        
        return self.log_event(
            OrchestrationEventType.ORCHESTRATION_COMPLETED,
            "Orchestration completed successfully",
            details={
                "total_cost": total_cost,
                "total_tokens": total_tokens,
            },
        )
    
    def log_orchestration_failed(
        self,
        error: str,
        failed_agent: Optional[str] = None,
    ) -> OrchestrationEvent:
        """Log orchestration failure."""
        self.trace.error_message = error
        self.trace.status = "failed"
        
        return self.log_event(
            OrchestrationEventType.ORCHESTRATION_FAILED,
            f"Orchestration failed: {error}",
            details={
                "error": error,
                "failed_agent": failed_agent,
            },
            decision_explanation=f"Fatal error in orchestration: {error}",
        )
    
    def transition_state(self, new_state: ExecutionStep) -> bool:
        """Transition to new execution state and log it."""
        if not self.state_machine.can_transition_to(new_state):
            self.base_logger.warning(
                f"Invalid state transition: {self.state_machine.current_state} -> {new_state}"
            )
            return False
        
        old_state = self.state_machine.current_state
        self.state_machine.transition_to(new_state)
        
        self.base_logger.info(
            f"State transition: {old_state.value} -> {new_state.value}",
            extra={
                "structured": {
                    "event_type": "state_transition",
                    "from_state": old_state.value,
                    "to_state": new_state.value,
                    "trace_id": str(self.trace.id),
                }
            }
        )
        
        return True
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of orchestration so far."""
        return {
            "events_count": len(self.trace.events),
            "agents_executed": len(self.trace.agent_execution_order),
            "current_stage": self.state_machine.current_state.value,
            "total_cost": self.trace.total_cost,
            "elapsed_ms": self._elapsed_ms(),
            "stage_durations": {
                state.value: self.state_machine.get_state_duration_ms(state)
                for state in ExecutionStep
            },
        }
