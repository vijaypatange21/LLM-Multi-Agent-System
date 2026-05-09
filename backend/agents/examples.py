"""
Decomposition Agent Examples

Shows how to use the decomposition agent in various scenarios:
- Simple queries
- Complex multi-step queries
- Ambiguous queries
- Adversarial inputs
- Integration with orchestrator
"""

import asyncio
import logging
from uuid import uuid4

from backend.agents import DecompositionAgent
from backend.agents.decomposition_utils import (
    AmbiguityDetector,
    DAGValidator,
    QueryParser,
)
from backend.schemas import AgentMessage, MessageRole, SharedContext


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """Pretty print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_task_graph(graph):
    """Pretty print a task graph."""
    print(f"\n📊 TASK GRAPH")
    print(f"  Tasks: {graph.total_tasks}")
    print(f"  Dependencies: {graph.total_dependencies}")
    print(f"  Depth (longest path): {graph.depth}")
    print(f"  Width (max parallel): {graph.width}")
    print(f"  Valid (no cycles): {'✓' if graph.is_valid else '✗'}")
    
    print(f"\n  TASKS:")
    for i, task in enumerate(graph.tasks, 1):
        print(f"    {i}. [{task.type.value.upper()}] {task.description}")
        print(f"       Input: {task.input_description}")
        print(f"       Output: {task.expected_output}")
        print(f"       Confidence: {task.confidence_score:.0%}")
    
    if graph.dependencies:
        print(f"\n  DEPENDENCIES:")
        for dep in graph.dependencies:
            from_task = graph.get_task(dep.dependency_task_id)
            to_task = graph.get_task(dep.dependent_task_id)
            if from_task and to_task:
                print(f"    {from_task.type.value} → {to_task.type.value}")
    
    print(f"\n  EXECUTION ORDER:")
    if graph.execution_order:
        for i, task_id in enumerate(graph.execution_order, 1):
            task = graph.get_task(task_id)
            if task:
                print(f"    {i}. {task.type.value} - {task.description}")
    else:
        print("    No execution order")


def print_decomposition_result(result):
    """Pretty print decomposition result."""
    print(f"\n🎯 DECOMPOSITION RESULT")
    print(f"  Confidence: {result['decomposition_confidence']:.0%}")
    print(f"  Executable: {'✓' if result['is_executable'] else '✗'}")
    print(f"  Total Ambiguities: {result['total_ambiguities']}")
    
    if result['ambiguities']:
        print(f"\n  AMBIGUITIES:")
        for amb in result['ambiguities'][:5]:  # Show first 5
            severity = "🔴" if amb['severity'] > 0.8 else "🟡" if amb['severity'] > 0.5 else "🟢"
            print(f"    {severity} {amb['ambiguity_type']}")
            print(f"       Issue: {amb['description']}")
            print(f"       Fix: {amb['suggested_clarification']}")
    
    if result['execution_issues']:
        print(f"\n  EXECUTION ISSUES:")
        for issue in result['execution_issues']:
            print(f"    • {issue}")
    
    if result['missing_information']:
        print(f"\n  MISSING INFORMATION:")
        for missing in result['missing_information']:
            print(f"    • {missing}")


async def example_simple_query():
    """Example 1: Simple, clear query."""
    print_section("EXAMPLE 1: Simple Query")
    
    query = "Search for machine learning papers"
    print(f"Query: {query}\n")
    
    # Method 1: Direct query parser
    print("METHOD 1: Query Parser")
    graph = QueryParser.build_task_graph(query)
    print_task_graph(graph)
    
    # Method 2: Via decomposition agent
    print("\n" + "-" * 80)
    print("METHOD 2: Decomposition Agent")
    
    agent = DecompositionAgent(logger=logger)
    message = AgentMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        parent_message_id=None,
        trace_id=uuid4(),
        role=MessageRole.USER,
        content=query,
        agent_id="user",
        sequence_number=1,
    )
    context = SharedContext(
        conversation_id=message.conversation_id,
        user_intent=query,
    )
    
    trace = await agent.process_message(message, context)
    
    if trace.status == "completed":
        result = trace.final_output
        print_decomposition_result(result)
    else:
        print(f"ERROR: {trace.error_message}")


async def example_complex_query():
    """Example 2: Complex multi-step query."""
    print_section("EXAMPLE 2: Complex Multi-Step Query")
    
    query = "Find recent customer feedback, analyze sentiment trends, identify key insights, and summarize recommendations"
    print(f"Query: {query}\n")
    
    graph = QueryParser.build_task_graph(query)
    print_task_graph(graph)
    
    # Analyze dependencies
    print(f"\n🔗 DEPENDENCY STRUCTURE:")
    for i, task_id in enumerate(graph.execution_order, 1):
        task = graph.get_task(task_id)
        if task:
            deps = graph.get_dependencies_for_task(task_id)
            if deps:
                print(f"  {i}. {task.type.value}")
                for dep in deps:
                    dep_task = graph.get_task(dep.dependency_task_id)
                    if dep_task:
                        print(f"     ↓ depends on: {dep_task.type.value}")
            else:
                print(f"  {i}. {task.type.value} (no dependencies)")


async def example_ambiguous_query():
    """Example 3: Ambiguous query with missing information."""
    print_section("EXAMPLE 3: Ambiguous Query")
    
    query = "Analyze it somehow with data"
    print(f"Query: {query}\n")
    
    agent = DecompositionAgent(logger=logger)
    message = AgentMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        parent_message_id=None,
        trace_id=uuid4(),
        role=MessageRole.USER,
        content=query,
        agent_id="user",
        sequence_number=1,
    )
    context = SharedContext(
        conversation_id=message.conversation_id,
        user_intent=query,
    )
    
    trace = await agent.process_message(message, context)
    result = trace.final_output
    
    print_decomposition_result(result)
    
    # Show reasoning
    if result['reasoning_steps']:
        print(f"\n💭 REASONING STEPS:")
        for step in result['reasoning_steps']:
            print(f"  • {step}")


async def example_vague_language():
    """Example 4: Detecting vague language."""
    print_section("EXAMPLE 4: Vague Language Detection")
    
    query = "Do something with data, maybe analyze it, and sort of summarize"
    print(f"Query: {query}\n")
    
    # Detect vague words
    vague_words = AmbiguityDetector.detect_vague_language(query)
    print(f"🔍 VAGUE WORDS DETECTED ({len(vague_words)}):")
    for word, context in vague_words:
        print(f"  '{word}' in: ...{context}...")
    
    # Full decomposition
    print("\n" + "-" * 80)
    graph = QueryParser.build_task_graph(query)
    print_task_graph(graph)
    
    # Show ambiguities
    ambiguities = AmbiguityDetector.detect_ambiguities_in_graph(
        query, graph.tasks, graph.dependencies
    )
    if ambiguities:
        print(f"\n⚠️  AMBIGUITIES ({len(ambiguities)}):")
        for amb in ambiguities:
            print(f"  • {amb.description}")
            print(f"    → {amb.suggested_clarification}")


async def example_dependency_inference():
    """Example 5: Understanding dependency inference."""
    print_section("EXAMPLE 5: Dependency Inference Patterns")
    
    test_cases = [
        ("Search for papers", "Single task, no dependencies"),
        ("Search and analyze", "SEARCH → ANALYZE (data before analysis)"),
        ("Analyze and aggregate", "ANALYZE → AGGREGATE (process before combine)"),
        ("Aggregate and summarize", "AGGREGATE → SUMMARIZE (combine before sum)"),
        ("Search, analyze, and summarize", "Chain: SEARCH → ANALYZE → SUMMARIZE"),
    ]
    
    for query, expected_pattern in test_cases:
        print(f"\nQuery: {query}")
        print(f"Expected: {expected_pattern}")
        
        graph = QueryParser.build_task_graph(query)
        
        print(f"Result: {graph.total_tasks} tasks, {graph.total_dependencies} deps")
        if graph.dependencies:
            for dep in graph.dependencies:
                from_task = graph.get_task(dep.dependency_task_id)
                to_task = graph.get_task(dep.dependent_task_id)
                if from_task and to_task:
                    print(f"  {from_task.type.value} → {to_task.type.value}")


async def example_cycle_detection():
    """Example 6: Cycle detection (invalid decomposition)."""
    print_section("EXAMPLE 6: Cycle Detection")
    
    from backend.agents.schemas import Task, TaskDependency, TaskType
    
    # Create circular dependency manually
    print("Creating circular dependency: A → B → C → A\n")
    
    task_a = Task(
        type=TaskType.ANALYZE,
        description="Task A",
        input_description="Input",
        expected_output="Output",
        reasoning="Test"
    )
    task_b = Task(
        type=TaskType.ANALYZE,
        description="Task B",
        input_description="Input",
        expected_output="Output",
        reasoning="Test"
    )
    task_c = Task(
        type=TaskType.ANALYZE,
        description="Task C",
        input_description="Input",
        expected_output="Output",
        reasoning="Test"
    )
    
    # Create cycle
    dep1 = TaskDependency(dependent_task_id=task_b.id, dependency_task_id=task_a.id)
    dep2 = TaskDependency(dependent_task_id=task_c.id, dependency_task_id=task_b.id)
    dep3 = TaskDependency(dependent_task_id=task_a.id, dependency_task_id=task_c.id)
    
    # Check for cycles
    has_cycles = DAGValidator.has_cycles([task_a, task_b, task_c], [dep1, dep2, dep3])
    print(f"Has cycles: {has_cycles} {'✗ INVALID' if has_cycles else '✓ VALID'}")
    
    # Try topological sort
    sorted_order, is_valid = DAGValidator.topological_sort(
        [task_a, task_b, task_c], [dep1, dep2, dep3]
    )
    print(f"Topological sort valid: {is_valid}")
    print(f"Sorted order: {sorted_order if sorted_order else 'INVALID (cycle detected)'}")


async def example_confidence_scoring():
    """Example 7: Understanding confidence scores."""
    print_section("EXAMPLE 7: Confidence Scoring")
    
    test_queries = [
        ("Search for papers", "Clear, specific"),
        ("Find and analyze data", "Clear actions"),
        ("Maybe do something", "Vague, uncertain"),
        ("Do stuff", "Very vague"),
        ("Analyze it with that", "Ambiguous references"),
    ]
    
    print("Decomposing various queries to show confidence scoring:\n")
    
    for query, description in test_queries:
        print(f"Query: {query}")
        print(f"  ({description})")
        
        graph = QueryParser.build_task_graph(query)
        
        if graph.tasks:
            avg_confidence = sum(t.confidence_score for t in graph.tasks) / len(graph.tasks)
            print(f"  Average task confidence: {avg_confidence:.0%}")
        
        print()


async def example_orchestrator_integration():
    """Example 8: Integration with orchestrator workflow."""
    print_section("EXAMPLE 8: Orchestrator Integration")
    
    query = "Find customer feedback from last month and analyze satisfaction levels"
    print(f"Original query: {query}\n")
    
    # Step 1: Decompose
    print("STEP 1: DecompositionAgent processes query")
    print("-" * 80)
    
    graph = QueryParser.build_task_graph(query)
    print_task_graph(graph)
    
    # Step 2: What orchestrator sees
    print("\n" + "-" * 80)
    print("STEP 2: What DynamicOrchestrator receives")
    print("-" * 80)
    
    print(f"\nExecution Plan:")
    print(f"  Total tasks: {graph.total_tasks}")
    print(f"  Execution order: {[graph.get_task(tid).type.value for tid in graph.execution_order]}")
    print(f"  Constraints: {graph.total_dependencies} dependencies")
    
    print(f"\nOrchestrator's routing decisions:")
    for i, task_id in enumerate(graph.execution_order, 1):
        task = graph.get_task(task_id)
        print(f"  {i}. {task.type.value}")
        print(f"     ↳ Agent selection: Select agent matching {task.type.value.upper()} capability")
        print(f"     ↳ Blocked until: Dependencies complete")
        print(f"     ↳ Confidence: {task.confidence_score:.0%}")
    
    print(f"\nResult aggregation:")
    print(f"  Combine outputs from {graph.total_tasks} agents")
    print(f"  Return to user with tracing")


async def main():
    """Run all examples."""
    try:
        await example_simple_query()
        await example_complex_query()
        await example_ambiguous_query()
        await example_vague_language()
        await example_dependency_inference()
        await example_cycle_detection()
        await example_confidence_scoring()
        await example_orchestrator_integration()
        
        print_section("✅ ALL EXAMPLES COMPLETED SUCCESSFULLY")
    
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
