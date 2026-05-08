"""
Example usage and integration guide for DynamicOrchestrator.

This module demonstrates how to use the dynamic orchestrator in practice.
"""

import asyncio
import logging
from typing import List
from uuid import UUID, uuid4

from backend.core import BaseAgent
from backend.orchestration import (
    DynamicOrchestrator,
    RuleBasedRoutingPolicy,
)
from backend.schemas import AgentMessage, MessageRole, SharedContext, ToolDefinition


# Configure logging with structured output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExampleSearchAgent(BaseAgent):
    """Example agent that performs searches."""
    
    @property
    def agent_id(self) -> str:
        return "search_agent"
    
    @property
    def agent_version(self) -> str:
        return "1.0.0"
    
    def get_available_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                id="web_search",
                name="Web Search",
                description="Search the web for information",
                version="1.0.0",
                tool_type="search",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}}
                },
                output_schema={
                    "type": "object",
                    "properties": {"results": {"type": "array"}}
                },
            )
        ]
    
    async def process_message(self, message, context):
        """Simulate search agent processing."""
        # Create a basic execution trace
        from backend.schemas import ExecutionTrace, ExecutionStep
        
        trace = ExecutionTrace(
            conversation_id=message.conversation_id,
            agent_id=self.agent_id,
            status="completed",
            final_output={"search_results": ["result 1", "result 2"]},
            total_cost=0.05,
        )
        return trace
    
    async def validate_tool_call(self, tool_call):
        return True


class ExampleAnalyzerAgent(BaseAgent):
    """Example agent that analyzes information."""
    
    @property
    def agent_id(self) -> str:
        return "analyzer_agent"
    
    @property
    def agent_version(self) -> str:
        return "1.0.0"
    
    def get_available_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                id="analyze",
                name="Analyze",
                description="Analyze information",
                version="1.0.0",
                tool_type="analyze",
                input_schema={
                    "type": "object",
                    "properties": {"data": {"type": "string"}}
                },
                output_schema={
                    "type": "object",
                    "properties": {"analysis": {"type": "string"}}
                },
            )
        ]
    
    async def process_message(self, message, context):
        """Simulate analyzer agent processing."""
        from backend.schemas import ExecutionTrace
        
        trace = ExecutionTrace(
            conversation_id=message.conversation_id,
            agent_id=self.agent_id,
            status="completed",
            final_output={"analysis": "Analyzed data shows pattern X"},
            total_cost=0.1,
        )
        return trace
    
    async def validate_tool_call(self, tool_call):
        return True


async def example_orchestration():
    """
    Example: Running dynamic orchestration.
    
    Shows:
    1. Creating orchestrator
    2. Setting up agents
    3. Running orchestration
    4. Analyzing results
    """
    
    logger.info("=" * 80)
    logger.info("EXAMPLE: Dynamic Multi-Agent Orchestration")
    logger.info("=" * 80)
    
    # 1. Create orchestrator with rule-based routing policy
    orchestrator = DynamicOrchestrator(
        routing_policy=RuleBasedRoutingPolicy(),
        max_retries=2,
        logger=logger,
    )
    
    logger.info("Created DynamicOrchestrator with RuleBasedRoutingPolicy")
    
    # 2. Create example agents
    agents = [
        ExampleSearchAgent(),
        ExampleAnalyzerAgent(),
    ]
    
    logger.info(f"Registered {len(agents)} agents")
    
    # 3. Create user query and context
    conversation_id = uuid4()
    user_query = "Find information about machine learning and analyze the trends"
    
    initial_message = AgentMessage(
        id=uuid4(),
        conversation_id=conversation_id,
        parent_message_id=None,
        trace_id="trace-001",
        role=MessageRole.USER,
        content=user_query,
        agent_id="user",
        sequence_number=1,
    )
    
    logger.info(f"User query: {user_query}")
    
    # 4. Execute orchestration
    logger.info("Starting orchestration...")
    
    orchestration_trace = await orchestrator.execute(
        conversation_id=conversation_id,
        initial_message=initial_message,
        agents=agents,
    )
    
    # 5. Analyze results
    logger.info("=" * 80)
    logger.info("ORCHESTRATION COMPLETE")
    logger.info("=" * 80)
    
    logger.info(f"Status: {orchestration_trace.status}")
    logger.info(f"Agents executed: {orchestration_trace.agent_execution_order}")
    logger.info(f"Total cost: ${orchestration_trace.total_cost:.2f}")
    logger.info(f"Duration: {orchestration_trace.total_duration_ms:.0f}ms")
    
    logger.info(f"\nRouting decisions made:")
    for decision in orchestration_trace.routing_decisions:
        logger.info(f"  - {decision.agent_id}: {decision.decision} ({decision.reason.value})")
        logger.info(f"    Explanation: {decision.explanation}")
        logger.info(f"    Score: {decision.score:.2f}")
    
    logger.info(f"\nExecution events ({len(orchestration_trace.events)} total):")
    for event in orchestration_trace.events[:10]:  # Show first 10
        logger.info(f"  - [{event.event_type.value}] {event.message}")
    
    logger.info(f"\nAgent results:")
    for agent_id, result in orchestration_trace.agent_results.items():
        logger.info(f"  - {agent_id}: status={result['status']}")
    
    if orchestration_trace.final_output:
        logger.info(f"\nFinal aggregated output:")
        logger.info(f"  Agents: {orchestration_trace.final_output.get('agents_executed')}")
    
    if orchestration_trace.error_message:
        logger.error(f"\nError: {orchestration_trace.error_message}")
    
    return orchestration_trace


async def example_complex_query():
    """
    Example: Complex query that triggers multiple agents.
    """
    
    logger.info("=" * 80)
    logger.info("EXAMPLE: Complex Multi-Step Query")
    logger.info("=" * 80)
    
    orchestrator = DynamicOrchestrator(
        routing_policy=RuleBasedRoutingPolicy(),
        max_retries=3,
        logger=logger,
    )
    
    agents = [
        ExampleSearchAgent(),
        ExampleAnalyzerAgent(),
    ]
    
    conversation_id = uuid4()
    
    # Complex query that requires both search and analysis
    complex_query = """
    I need to understand the impact of recent AI developments on software engineering.
    Please search for the latest information, analyze emerging trends, and summarize
    the key implications for development teams.
    """
    
    initial_message = AgentMessage(
        id=uuid4(),
        conversation_id=conversation_id,
        parent_message_id=None,
        trace_id="trace-complex",
        role=MessageRole.USER,
        content=complex_query,
        agent_id="user",
        sequence_number=1,
    )
    
    logger.info(f"Complex query:\n{complex_query}")
    
    trace = await orchestrator.execute(
        conversation_id=conversation_id,
        initial_message=initial_message,
        agents=agents,
    )
    
    logger.info(f"\n✅ Orchestration completed successfully")
    logger.info(f"   Status: {trace.status}")
    logger.info(f"   Agents selected: {len(trace.agent_execution_order)}")
    logger.info(f"   Total execution time: {trace.total_duration_ms:.0f}ms")
    logger.info(f"   Total cost: ${trace.total_cost:.2f}")
    
    return trace


async def example_budget_constraint():
    """
    Example: Query with budget constraints affecting agent selection.
    """
    
    logger.info("=" * 80)
    logger.info("EXAMPLE: Budget-Aware Agent Selection")
    logger.info("=" * 80)
    
    orchestrator = DynamicOrchestrator(
        routing_policy=RuleBasedRoutingPolicy(),
        logger=logger,
    )
    
    agents = [
        ExampleSearchAgent(),
        ExampleAnalyzerAgent(),
    ]
    
    conversation_id = uuid4()
    query = "Analyze market trends and competitive landscape"
    
    initial_message = AgentMessage(
        id=uuid4(),
        conversation_id=conversation_id,
        parent_message_id=None,
        trace_id="trace-budget",
        role=MessageRole.USER,
        content=query,
        agent_id="user",
        sequence_number=1,
    )
    
    logger.info(f"Query: {query}")
    logger.info(f"Budget constraint: Limited budget available")
    
    trace = await orchestrator.execute(
        conversation_id=conversation_id,
        initial_message=initial_message,
        agents=agents,
    )
    
    logger.info(f"\n✅ Orchestration completed")
    logger.info(f"   Agents selected: {trace.agent_execution_order}")
    logger.info(f"   Total cost: ${trace.total_cost:.2f}")
    
    # Show how budget affected routing decisions
    logger.info(f"\n   Routing decisions influenced by budget:")
    for decision in trace.routing_decisions:
        if not decision.budget_available:
            logger.info(f"   - {decision.agent_id} rejected due to budget constraint")
    
    return trace


async def main():
    """Run all examples."""
    
    try:
        # Example 1: Basic orchestration
        await example_orchestration()
        
        print("\n" * 3)
        
        # Example 2: Complex query
        await example_complex_query()
        
        print("\n" * 3)
        
        # Example 3: Budget constraints
        await example_budget_constraint()
        
        logger.info("\n" + "=" * 80)
        logger.info("ALL EXAMPLES COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
    
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
