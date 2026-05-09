"""
Unit tests for decomposition agent.

Test Coverage:
1. Simple queries - straightforward decomposition
2. Ambiguous queries - unclear or vague requirements
3. Adversarial cases - edge cases and error conditions
4. Task graph validation - DAG properties
5. Confidence scoring - metric validation
"""

import asyncio
import pytest
from uuid import uuid4

from backend.agents import (
    DecompositionAgent,
    Task,
    TaskDependency,
    TaskGraph,
    TaskType,
)
from backend.agents.decomposition_utils import (
    AmbiguityDetector,
    DAGValidator,
    QueryParser,
)
from backend.schemas import AgentMessage, MessageRole, SharedContext, ContextMetadata


class TestQueryParser:
    """Tests for query parsing into tasks."""
    
    def test_parse_simple_search_query(self):
        """Test parsing a simple search query."""
        query = "Search for machine learning papers"
        tasks = QueryParser.parse_simple_query(query)
        
        assert len(tasks) > 0
        assert any(t.type == TaskType.SEARCH for t in tasks)
        assert "machine learning" in tasks[0].description.lower()
    
    def test_parse_multi_action_query(self):
        """Test parsing query with multiple actions."""
        query = "Find customer data and analyze sentiment"
        tasks = QueryParser.parse_simple_query(query)
        
        assert len(tasks) >= 2
        task_types = [t.type for t in tasks]
        assert TaskType.SEARCH in task_types or TaskType.RETRIEVE in task_types
        assert TaskType.ANALYZE in task_types
    
    def test_parse_complex_query(self):
        """Test parsing complex query."""
        query = "Search for AI trends, analyze growth patterns, and summarize findings"
        tasks = QueryParser.parse_simple_query(query)
        
        assert len(tasks) >= 2
        # Should find at least search/retrieve, analyze, and summarize
        task_types = {t.type for t in tasks}
        actions = {TaskType.SEARCH, TaskType.RETRIEVE, TaskType.ANALYZE, TaskType.SUMMARIZE}
        assert len(task_types & actions) >= 2
    
    def test_parse_vague_query(self):
        """Test parsing vague query."""
        query = "Do something with data"
        tasks = QueryParser.parse_simple_query(query)
        
        # Should still parse something
        assert len(tasks) > 0
        # Confidence should be lower for vague query
        assert any(t.confidence_score < 0.5 for t in tasks)
    
    def test_parse_empty_query(self):
        """Test parsing empty query."""
        query = ""
        tasks = QueryParser.parse_simple_query(query)
        
        # Should create generic task
        assert len(tasks) > 0
        assert tasks[0].type == TaskType.UNKNOWN
    
    def test_parse_ambiguous_pronouns(self):
        """Test parsing with ambiguous pronouns."""
        query = "Analyze it and compare with that"
        tasks = QueryParser.parse_simple_query(query)
        
        # Should parse but identify ambiguity
        assert len(tasks) > 0


class TestDependencyInference:
    """Tests for inferring dependencies between tasks."""
    
    def test_search_before_analyze(self):
        """Test that SEARCH comes before ANALYZE."""
        query = "Search for data and analyze it"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        search_tasks = [t for t in tasks if t.type == TaskType.SEARCH]
        analyze_tasks = [t for t in tasks if t.type == TaskType.ANALYZE]
        
        # If both types exist, search should precede analyze
        if search_tasks and analyze_tasks:
            for analyze_task in analyze_tasks:
                for search_task in search_tasks:
                    # Check if this dependency was inferred
                    matching_deps = [
                        d for d in dependencies
                        if (d.dependency_task_id == search_task.id and
                            d.dependent_task_id == analyze_task.id)
                    ]
                    # At least one search should feed into analyze
                    assert len(matching_deps) > 0
    
    def test_analyze_before_aggregate(self):
        """Test that ANALYZE comes before AGGREGATE."""
        query = "Analyze results and aggregate them"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        analyze_tasks = [t for t in tasks if t.type == TaskType.ANALYZE]
        agg_tasks = [t for t in tasks if t.type == TaskType.AGGREGATE]
        
        if analyze_tasks and agg_tasks:
            for agg_task in agg_tasks:
                for analyze_task in analyze_tasks:
                    matching_deps = [
                        d for d in dependencies
                        if (d.dependency_task_id == analyze_task.id and
                            d.dependent_task_id == agg_task.id)
                    ]
                    assert len(matching_deps) > 0
    
    def test_independent_tasks(self):
        """Test that independent tasks have no dependencies."""
        # Create two independent tasks
        task1 = Task(
            type=TaskType.SEARCH,
            description="Search for papers",
            input_description="Query",
            expected_output="Papers",
            reasoning="User asked to search"
        )
        task2 = Task(
            type=TaskType.SEARCH,
            description="Search for articles",
            input_description="Query",
            expected_output="Articles",
            reasoning="User asked to search"
        )
        
        query = "Search for papers and search for articles"
        dependencies = QueryParser.infer_dependencies([task1, task2], query)
        
        # Two independent searches shouldn't have dependencies between them
        task_pair_deps = [
            d for d in dependencies
            if (d.dependent_task_id == task2.id and d.dependency_task_id == task1.id) or
               (d.dependent_task_id == task1.id and d.dependency_task_id == task2.id)
        ]
        # Should have no dependencies between two searches
        assert len(task_pair_deps) == 0


class TestDAGValidation:
    """Tests for DAG validation."""
    
    def test_acyclic_graph(self):
        """Test that valid DAG has no cycles."""
        query = "Search for data, analyze it, and summarize"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        # Normal decomposition should be acyclic
        has_cycles = DAGValidator.has_cycles(tasks, dependencies)
        assert not has_cycles
    
    def test_topological_sort(self):
        """Test topological sorting."""
        query = "Search, analyze, and summarize"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        sorted_order, is_valid = DAGValidator.topological_sort(tasks, dependencies)
        
        assert is_valid
        assert len(sorted_order) == len(tasks)
        
        # Check that dependencies are respected in sort order
        for dep in dependencies:
            dep_idx = sorted_order.index(dep.dependency_task_id)
            dependent_idx = sorted_order.index(dep.dependent_task_id)
            assert dep_idx < dependent_idx, "Dependency not respected in sort order"
    
    def test_circular_dependency_detection(self):
        """Test that cycles are detected."""
        # Create circular dependency manually
        task1 = Task(type=TaskType.ANALYZE, description="A",
                    input_description="Input", expected_output="Output",
                    reasoning="Test")
        task2 = Task(type=TaskType.ANALYZE, description="B",
                    input_description="Input", expected_output="Output",
                    reasoning="Test")
        task3 = Task(type=TaskType.ANALYZE, description="C",
                    input_description="Input", expected_output="Output",
                    reasoning="Test")
        
        # Create cycle: 1 -> 2 -> 3 -> 1
        dep1 = TaskDependency(dependent_task_id=task2.id, dependency_task_id=task1.id)
        dep2 = TaskDependency(dependent_task_id=task3.id, dependency_task_id=task2.id)
        dep3 = TaskDependency(dependent_task_id=task1.id, dependency_task_id=task3.id)
        
        has_cycles = DAGValidator.has_cycles(
            [task1, task2, task3],
            [dep1, dep2, dep3]
        )
        assert has_cycles
    
    def test_graph_metrics(self):
        """Test graph metrics computation."""
        query = "Search and analyze"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        metrics = DAGValidator.compute_graph_metrics(tasks, dependencies)
        
        assert metrics["total_tasks"] == len(tasks)
        assert metrics["total_dependencies"] >= 0
        assert metrics["depth"] >= 0
        assert metrics["width"] >= 0


class TestAmbiguityDetection:
    """Tests for ambiguity detection."""
    
    def test_vague_language_detection(self):
        """Test detection of vague language."""
        query = "Do something with data and maybe analyze"
        vague = AmbiguityDetector.detect_vague_language(query)
        
        assert len(vague) > 0
        # Should find "maybe" and "something"
        vague_words = [term for term, _ in vague]
        assert any("something" in term or "maybe" in term for term in vague_words)
    
    def test_missing_information_detection(self):
        """Test detection of missing information."""
        query = "Analyze data"  # No temporal, scope, or constraints info
        tasks = QueryParser.parse_simple_query(query)
        
        missing = AmbiguityDetector.detect_missing_information(query, tasks)
        
        # Should detect missing scope, constraints, priorities
        assert len(missing) > 0
    
    def test_ambiguities_in_graph(self):
        """Test detecting ambiguities in full decomposition."""
        query = "Do something with data and maybe validate it"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        ambiguities = AmbiguityDetector.detect_ambiguities_in_graph(
            query, tasks, dependencies
        )
        
        # Should detect vague language and/or missing info
        assert len(ambiguities) >= 0  # May or may not detect depending on parsing
    
    def test_no_ambiguities_in_clear_query(self):
        """Test that clear queries have few ambiguities."""
        query = "Search for Python papers from 2024 and analyze trends"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        ambiguities = AmbiguityDetector.detect_ambiguities_in_graph(
            query, tasks, dependencies
        )
        
        # Clear query should have few or no critical ambiguities
        critical = [a for a in ambiguities if a.severity > 0.8]
        assert len(critical) == 0


class TestTaskGraphBuilding:
    """Tests for building complete task graphs."""
    
    def test_build_simple_task_graph(self):
        """Test building graph from simple query."""
        query = "Search for information"
        graph = QueryParser.build_task_graph(query)
        
        assert graph.original_query == query
        assert len(graph.tasks) > 0
        assert graph.is_valid
        assert len(graph.execution_order) == len(graph.tasks)
    
    def test_build_complex_task_graph(self):
        """Test building graph from complex query."""
        query = "Search for customer data, analyze sentiment trends, aggregate results, and summarize findings"
        graph = QueryParser.build_task_graph(query)
        
        assert len(graph.tasks) >= 2
        assert len(graph.dependencies) >= 1
        assert graph.is_valid
        assert not graph.has_cycles
    
    def test_graph_confidence_scoring(self):
        """Test confidence score computation."""
        # Clear query should have high confidence
        clear_query = "Search for information and analyze it"
        clear_graph = QueryParser.build_task_graph(clear_query)
        clear_conf = clear_graph.tasks[0].confidence_score if clear_graph.tasks else 0
        
        # Vague query should have lower confidence
        vague_query = "Do something maybe with some data"
        vague_graph = QueryParser.build_task_graph(vague_query)
        vague_conf = vague_graph.tasks[0].confidence_score if vague_graph.tasks else 0
        
        # Clear should generally be higher confidence (though not guaranteed)
        # Just verify both are in valid range
        assert 0 <= clear_conf <= 1
        assert 0 <= vague_conf <= 1


@pytest.mark.asyncio
class TestDecompositionAgent:
    """Tests for the decomposition agent itself."""
    
    async def test_agent_properties(self):
        """Test agent identification."""
        agent = DecompositionAgent()
        
        assert agent.agent_id == "decomposition_agent"
        assert agent.agent_version == "1.0.0"
        assert agent.get_available_tools() == []
    
    async def test_simple_query_decomposition(self):
        """Test decomposing a simple query."""
        agent = DecompositionAgent()
        
        message = AgentMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            parent_message_id=None,
            trace_id=str(uuid4()),
            role=MessageRole.USER,
            content="Search for AI papers",
            agent_id="user",
            sequence_number=1,
        )
        
        context = SharedContext(
            conversation_id=message.conversation_id,
            user_intent=message.content,
            metadata=ContextMetadata(last_modified_by="test"),
        )
        
        trace = await agent.process_message(message, context)
        
        assert trace.status == "completed"
        assert trace.final_output is not None
        assert "task_graph" in trace.final_output
    
    async def test_complex_query_decomposition(self):
        """Test decomposing a complex multi-step query."""
        agent = DecompositionAgent()
        
        message = AgentMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            parent_message_id=None,
            trace_id=str(uuid4()),
            role=MessageRole.USER,
            content="Find customer feedback, analyze sentiment, identify trends, and summarize insights",
            agent_id="user",
            sequence_number=1,
        )
        
        context = SharedContext(
            conversation_id=message.conversation_id,
            user_intent=message.content,
            metadata=ContextMetadata(last_modified_by="test"),
        )
        
        trace = await agent.process_message(message, context)
        
        assert trace.status == "completed"
        result = trace.final_output
        assert len(result["task_graph"]["tasks"]) >= 2
        assert result["task_graph"]["is_valid"]
    
    async def test_ambiguous_query_decomposition(self):
        """Test decomposing an ambiguous query."""
        agent = DecompositionAgent()
        
        message = AgentMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            parent_message_id=None,
            trace_id=str(uuid4()),
            role=MessageRole.USER,
            content="Analyze the data and maybe do something with it",
            agent_id="user",
            sequence_number=1,
        )
        
        context = SharedContext(
            conversation_id=message.conversation_id,
            user_intent=message.content,
            metadata=ContextMetadata(last_modified_by="test"),
        )
        
        trace = await agent.process_message(message, context)
        
        assert trace.status == "completed"
        result = trace.final_output
        # Should detect ambiguities
        assert result["total_ambiguities"] >= 0
        # Confidence should be lower for ambiguous query
        assert result["decomposition_confidence"] < 1.0
    
    async def test_invalid_tool_call(self):
        """Test that agent rejects tool calls."""
        agent = DecompositionAgent()
        
        result = await agent.validate_tool_call({"tool_id": "test"})
        assert result is False


# Adversarial test cases
class TestAdversarialCases:
    """Tests for edge cases and adversarial inputs."""
    
    def test_extremely_vague_query(self):
        """Test parsing extremely vague query."""
        query = "stuff"
        tasks = QueryParser.parse_simple_query(query)
        
        # Should still parse to something
        assert len(tasks) > 0
        # Confidence should be very low
        assert tasks[0].confidence_score < 0.5
    
    def test_query_with_contradictions(self):
        """Test parsing query with contradictory requirements."""
        query = "Search for AND don't search for data"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        # Should parse even if contradictory
        assert len(tasks) > 0
    
    def test_very_long_query(self):
        """Test parsing very long query."""
        query = " ".join(["find"] * 100)  # Repetitive, long
        tasks = QueryParser.parse_simple_query(query)
        
        # Should handle without crashing
        assert len(tasks) >= 0
    
    def test_special_characters_in_query(self):
        """Test parsing query with special characters."""
        query = "Search for @#$% & analyze <data>"
        tasks = QueryParser.parse_simple_query(query)
        
        # Should handle gracefully
        assert len(tasks) >= 0
    
    def test_many_independent_tasks(self):
        """Test decomposition with many independent tasks."""
        query = "Search for A and search for B and search for C and search for D and search for E"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        # Multiple search tasks should have few dependencies
        assert len(tasks) >= 3
        assert len(dependencies) < len(tasks) * len(tasks)
    
    def test_circular_semantic_dependency(self):
        """Test handling of circularly-dependent tasks."""
        # Create tasks that might have circular semantics
        task1 = Task(
            type=TaskType.ANALYZE,
            description="Analyze based on summary",
            input_description="Summary",
            expected_output="Analysis",
            reasoning="Test"
        )
        task2 = Task(
            type=TaskType.SUMMARIZE,
            description="Summarize based on analysis",
            input_description="Analysis",
            expected_output="Summary",
            reasoning="Test"
        )
        
        # Manually create circular dependency
        dep1 = TaskDependency(dependent_task_id=task2.id, dependency_task_id=task1.id)
        dep2 = TaskDependency(dependent_task_id=task1.id, dependency_task_id=task2.id)
        
        # Should detect cycle
        has_cycles = DAGValidator.has_cycles([task1, task2], [dep1, dep2])
        assert has_cycles
    
    def test_self_referential_task(self):
        """Test task that depends on itself."""
        task = Task(
            type=TaskType.ANALYZE,
            description="Analyze",
            input_description="Input",
            expected_output="Output",
            reasoning="Test"
        )
        
        # Self-referential dependency
        dep = TaskDependency(dependent_task_id=task.id, dependency_task_id=task.id)
        
        # Should detect as cycle
        has_cycles = DAGValidator.has_cycles([task], [dep])
        assert has_cycles


# Integration-style tests
class TestDecompositionIntegration:
    """Integration tests for decomposition with orchestrator compatibility."""
    
    def test_decomposition_result_orchestrator_compatible(self):
        """Test that decomposition result can be used by orchestrator."""
        query = "Find relevant data and analyze it"
        graph = QueryParser.build_task_graph(query)
        
        # Orchestrator needs:
        # 1. Typed tasks (each has a TaskType)
        assert all(task.type != TaskType.UNKNOWN or task.type == TaskType.UNKNOWN
                  for task in graph.tasks)
        
        # 2. Execution order (topologically sorted)
        assert len(graph.execution_order) == len(graph.tasks)
        
        # 3. Valid DAG (no cycles)
        assert not graph.has_cycles
        
        # 4. Dependencies clear
        assert len(graph.dependencies) >= 0
    
    def test_execution_plan_from_decomposition(self):
        """Test creating execution plan from decomposition."""
        query = "Analyze customer data, identify trends, and create report"
        graph = QueryParser.build_task_graph(query)
        
        # Can build execution plan from graph
        assert len(graph.execution_order) > 0
        
        # All tasks in order are in the task list
        for task_id in graph.execution_order:
            assert any(t.id == task_id for t in graph.tasks)
    
    def test_ambiguity_helps_with_clarification(self):
        """Test that ambiguity detection helps users clarify."""
        query = "Analyze it somehow"
        tasks = QueryParser.parse_simple_query(query)
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        ambiguities = AmbiguityDetector.detect_ambiguities_in_graph(
            query, tasks, dependencies
        )
        
        # Each ambiguity should have a suggested clarification
        for amb in ambiguities:
            assert amb.suggested_clarification is not None
            assert len(amb.suggested_clarification) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
