"""
Dynamic orchestrator implementation.

The orchestrator is the conductor of multi-agent execution. It:
1. Analyzes incoming queries
2. Dynamically selects agents based on capabilities
3. Determines execution order
4. Executes agents with error handling and retries
5. Aggregates results
6. Logs all decisions with reasoning

Key features:
- No hardcoded chains
- Budget-aware execution
- Context mediation between agents
- Retry handling
- Comprehensive error handling
- Structured logging
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ..core import BaseAgent, BaseTool, Orchestrator
from ..schemas import AgentMessage, ExecutionTrace, MessageRole, SharedContext
from .context_window import ContextWindowManager
from .routing import RuleBasedRoutingPolicy, RoutingPolicy
from .schemas import (
    ExecutionPlan,
    ExecutionStep,
    OrchestrationTrace,
)
from .state_machine import StructuredOrchestrationLogger


class DynamicOrchestrator(Orchestrator):
    """
    Production-grade dynamic orchestrator for multi-agent systems.
    
    WHY: Unlike hardcoded orchestrators (Agent A -> Agent B -> Agent C),
    this orchestrator:
    - Analyzes queries to determine which agents are needed
    - Selects agents dynamically at runtime
    - Adapts to different query types
    - Handles failures gracefully
    - Tracks all decisions and costs
    
    Architecture:
    1. Receive query
    2. Analyze to extract intent and requirements
    3. Rank agents by suitability
    4. Select agents respecting budget and constraints
    5. Create execution plan
    6. Execute selected agents
    7. Handle failures with retries
    8. Aggregate results
    9. Return to user
    """
    
    def __init__(
        self,
        routing_policy: Optional[RoutingPolicy] = None,
        max_retries: int = 2,
        default_token_budget: int = 8192,
        default_agent_token_budget: int = 2048,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize orchestrator.
        
        Args:
            routing_policy: Policy for agent selection (defaults to RuleBasedRoutingPolicy)
            max_retries: Max retries per agent on failure
            default_token_budget: Default total context window budget in tokens
            default_agent_token_budget: Default per-agent budget in tokens
            logger: Python logger for structured logging
        """
        self.routing_policy = routing_policy or RuleBasedRoutingPolicy()
        self.max_retries = max_retries
        self.default_token_budget = default_token_budget
        self.default_agent_token_budget = default_agent_token_budget
        self.logger = logger or logging.getLogger(__name__)
    
    async def execute(
        self,
        conversation_id: UUID,
        initial_message: AgentMessage,
        agents: List[BaseAgent],
    ) -> ExecutionTrace:
        """
        Execute multi-agent orchestration.
        
        Main entry point. Analyzes query, selects agents, executes them,
        and returns the execution record.
        
        Args:
            conversation_id: Conversation ID
            initial_message: User's initial message
            agents: Available agents to choose from
        
        Returns:
            ExecutionTrace with full execution record
        """
        # Create orchestration trace
        trace = OrchestrationTrace(
            id=uuid4(),
            conversation_id=conversation_id,
            initial_query=initial_message.content,
        )
        
        # Create structured logger
        event_logger = StructuredOrchestrationLogger(trace, self.logger)
        
        try:
            # Log query received
            event_logger.log_query_received(initial_message.content)
            
            # Dummy shared context for now (would come from database)
            context = SharedContext(
                conversation_id=conversation_id,
                user_intent=initial_message.content,
            )
            token_budget = int(context.user_preferences.get("token_budget", self.default_token_budget))
            token_window = ContextWindowManager(
                total_budget_tokens=token_budget,
                default_agent_budget_tokens=int(
                    context.user_preferences.get("agent_token_budget", self.default_agent_token_budget)
                ),
            )
            
            # Transition to planning stage
            event_logger.transition_state(ExecutionStep.PLANNING)
            
            # 1. Analyze query
            event_logger.log_analysis_started()
            query_analysis = await self.routing_policy.analyze_query(
                initial_message.content,
                context,
            )
            self.logger.debug(
                f"Query analysis: {query_analysis}",
                extra={"trace_id": str(conversation_id)}
            )
            
            # Transition to validation
            event_logger.transition_state(ExecutionStep.VALIDATION)
            
            # 2. Rank agents by suitability
            ranked_agents = await self.routing_policy.rank_agents(
                initial_message.content,
                agents,
                query_analysis,
                context,
            )
            
            # Log each ranking decision
            for agent, score, reasoning in ranked_agents:
                event_logger.log_routing_decision(
                    agent_id=agent.agent_id,
                    decided_to_select=False,  # Not selected yet, just ranked
                    reasoning=reasoning,
                    score=score,
                )
            
            # 3. Select agents respecting budget and constraints
            budget = context.user_preferences.get("budget", 1000.0)  # Default budget
            selected_agents, routing_decisions = await self.routing_policy.select_agents(
                ranked_agents,
                context,
                budget,
            )
            
            # Log selection decisions
            for decision in routing_decisions:
                if decision.decision == "SELECTED":
                    event_logger.log_routing_decision(
                        agent_id=decision.agent_id,
                        decided_to_select=True,
                        reasoning=decision.explanation,
                        score=decision.score,
                    )
            
            trace.routing_decisions.extend(routing_decisions)
            
            if not selected_agents:
                raise Exception("No agents selected for query")
            
            # Transition to scheduling
            event_logger.transition_state(ExecutionStep.SCHEDULING)
            
            # 4. Create execution plan
            execution_plan = ExecutionPlan(
                conversation_id=conversation_id,
                execution_stage=ExecutionStep.SCHEDULING,
                planned_agents=[a.agent_id for a in selected_agents],
                planned_order=list(range(len(selected_agents))),
                total_budget=budget,
                budget_allocated={
                    a.agent_id: float(token_budget / len(selected_agents)) for a in selected_agents
                },
                estimated_total_cost=sum(
                    decision.estimated_cost or 0.0
                    for decision in routing_decisions
                    if decision.decision == "SELECTED"
                ),
                estimated_total_time_ms=5000.0,  # Placeholder
            )
            
            trace.execution_plan = execution_plan
            
            event_logger.log_plan_created(
                planned_agents=[a.agent_id for a in selected_agents],
                estimated_cost=execution_plan.estimated_total_cost,
                estimated_time_ms=execution_plan.estimated_total_time_ms,
            )
            
            # Transition to executing
            event_logger.transition_state(ExecutionStep.EXECUTING)
            
            # 5. Execute agents sequentially
            for i, agent in enumerate(selected_agents):
                try:
                    # Log start
                    event_logger.log_agent_started(agent.agent_id)
                    execution_plan.execution_stage = ExecutionStep.EXECUTING

                    prepared = token_window.prepare_agent_input(
                        agent.agent_id,
                        initial_message,
                        context,
                        token_budget=int(
                            execution_plan.budget_allocated.get(
                                agent.agent_id,
                                token_window.budget_manager.default_agent_budget_tokens,
                            )
                        ),
                    )

                    if not prepared.budget_check.allowed:
                        if prepared.budget_check.policy_violation is not None:
                            event_logger.log_policy_violation(prepared.budget_check.policy_violation)
                        execution_plan.failed_agents.append(agent.agent_id)
                        event_logger.log_agent_failed(
                            agent_id=agent.agent_id,
                            error=prepared.budget_check.reason,
                            retry_count=0,
                        )
                        break

                    # Execute agent with retries
                    agent_trace = await self._execute_agent_with_retries(
                        agent,
                        prepared.message,
                        prepared.context,
                        event_logger,
                    )

                    # Record result
                    trace.agent_execution_order.append(agent.agent_id)
                    trace.agent_results[agent.agent_id] = {
                        "output": agent_trace.final_output,
                        "status": agent_trace.status,
                        "tokens": agent_trace.tokens_used or {},
                    }
                    trace.agent_execution_traces[agent.agent_id] = agent_trace.id
                    trace.agent_token_usage[agent.agent_id] = agent_trace.tokens_used or {}

                    # Update costs
                    trace.total_cost += agent_trace.total_cost
                    execution_plan.completed_agents.append(agent.agent_id)

                    actual_tokens = agent_trace.tokens_used or {}
                    prompt_tokens = int(actual_tokens.get("prompt", actual_tokens.get("prompt_tokens", 0)))
                    completion_tokens = int(actual_tokens.get("completion", actual_tokens.get("completion_tokens", 0)))
                    recorded_tokens = token_window.budget_manager.record_usage(
                        agent.agent_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                    trace.total_tokens_used = {
                        "prompt": trace.total_tokens_used.get("prompt", 0) + recorded_tokens["prompt"],
                        "completion": trace.total_tokens_used.get("completion", 0) + recorded_tokens["completion"],
                        "total": trace.total_tokens_used.get("total", 0) + recorded_tokens["total"],
                    }

                    # Log completion
                    event_logger.log_agent_completed(
                        agent_id=agent.agent_id,
                        cost=agent_trace.total_cost,
                        tokens_used=recorded_tokens["total"],
                    )

                    # Check budget
                    if trace.total_cost > budget:
                        event_logger.log_budget_constraint(
                            current_cost=trace.total_cost,
                            budget_limit=budget,
                            agent_rejected=selected_agents[i + 1].agent_id if i + 1 < len(selected_agents) else "N/A",
                        )
                        break

                except Exception as e:
                    # Log failure
                    execution_plan.failed_agents.append(agent.agent_id)
                    event_logger.log_agent_failed(
                        agent_id=agent.agent_id,
                        error=str(e),
                        retry_count=0,
                    )

                    self.logger.error(
                        f"Agent {agent.agent_id} failed: {str(e)}",
                        extra={"trace_id": str(conversation_id)},
                        exc_info=True,
                    )
            
            # Transition to collecting results
            event_logger.transition_state(ExecutionStep.COLLECTING_RESULTS)
            
            # 6. Aggregate results
            event_logger.transition_state(ExecutionStep.AGGREGATING)
            final_output = await self._aggregate_results(
                trace.agent_results,
                event_logger,
            )
            
            trace.final_output = final_output
            
            # Transition to completed
            event_logger.transition_state(ExecutionStep.COMPLETED)
            
            # Log completion
            event_logger.log_orchestration_completed(
                final_output=final_output,
                total_cost=trace.total_cost,
                total_tokens=trace.total_tokens_used.get("total", 0),
            )
            
            trace.completed_at = datetime.utcnow()
            trace.total_duration_ms = (
                trace.completed_at - trace.started_at
            ).total_seconds() * 1000
            
            return trace
        
        except Exception as e:
            # Log fatal error
            event_logger.log_orchestration_failed(
                error=str(e),
            )
            
            trace.error_message = str(e)
            trace.status = "failed"
            trace.completed_at = datetime.utcnow()
            trace.total_duration_ms = (
                trace.completed_at - trace.started_at
            ).total_seconds() * 1000
            
            self.logger.error(
                f"Orchestration failed: {str(e)}",
                extra={"trace_id": str(conversation_id)},
                exc_info=True,
            )
            
            return trace
    
    async def _execute_agent_with_retries(
        self,
        agent: BaseAgent,
        message: AgentMessage,
        context: SharedContext,
        event_logger: StructuredOrchestrationLogger,
    ) -> ExecutionTrace:
        """
        Execute agent with retry logic.
        
        Handles transient failures with exponential backoff.
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # Execute agent
                agent_message = AgentMessage(
                    conversation_id=message.conversation_id,
                    role=MessageRole.AGENT,
                    content=message.content,
                    agent_id=agent.agent_id,
                    sequence_number=1,
                    trace_id=message.trace_id,
                )
                
                trace = await agent.process_message(agent_message, context)
                return trace
            
            except Exception as e:
                last_error = e
                
                if attempt < self.max_retries:
                    # Log retry
                    event_logger.log_agent_failed(
                        agent_id=agent.agent_id,
                        error=str(e),
                        retry_count=attempt + 1,
                    )
                    
                    # Exponential backoff: 1s, 2s, 4s
                    backoff_seconds = 2 ** attempt
                    self.logger.info(
                        f"Retrying agent {agent.agent_id} after {backoff_seconds}s"
                    )
                    await asyncio.sleep(backoff_seconds)
                else:
                    raise
        
        raise last_error
    
    async def route_message(
        self,
        message: AgentMessage,
        agents: List[BaseAgent],
    ) -> BaseAgent:
        """
        Route message to appropriate agent.
        
        For single agent, just returns it. Multi-agent routing
        handled in execute() method.
        """
        if not agents:
            raise Exception("No agents available for routing")
        
        # Simple routing: return first agent
        # Production: would implement more sophisticated routing
        return agents[0]
    
    async def execute_tool(
        self,
        tool_call,
        tools: List[BaseTool],
        context: SharedContext,
    ):
        """
        Execute a tool invocation.
        
        Validates tool call, executes, tracks cost.
        """
        # Find tool
        tool = None
        for t in tools:
            if t.get_definition().id == tool_call.tool_id:
                tool = t
                break
        
        if not tool:
            raise Exception(f"Tool {tool_call.tool_id} not found")
        
        # Execute tool
        result = await tool.execute(tool_call, context)
        return result
    
    async def _aggregate_results(
        self,
        agent_results: Dict[str, Any],
        event_logger: StructuredOrchestrationLogger,
    ) -> Dict[str, Any]:
        """
        Aggregate results from multiple agents into final output.
        
        Simple implementation: combine all results.
        Production: would implement sophisticated aggregation strategies.
        """
        aggregated = {
            "agents_executed": list(agent_results.keys()),
            "agent_outputs": agent_results,
        }
        
        event_logger.log_result_aggregated(aggregated)
        
        return aggregated
