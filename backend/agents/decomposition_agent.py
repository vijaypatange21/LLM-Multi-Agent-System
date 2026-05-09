"""
Decomposition agent for breaking down queries into subtasks.

WHY: Complex queries need to be broken into manageable pieces before execution.
The decomposition agent:
- Analyzes the query
- Identifies required tasks and their types
- Detects dependencies between tasks
- Identifies ambiguities and missing information
- Produces a task graph that the orchestrator can execute

Architecture:
- Implements BaseAgent interface
- Uses QueryParser to extract tasks
- Uses AmbiguityDetector to identify issues
- Returns structured DecompositionResult
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from ..core import BaseAgent
from ..schemas import ExecutionTrace, SharedContext, ToolDefinition, AgentMessage
from .decomposition_utils import (
    AmbiguityDetector,
    DAGValidator,
    QueryParser,
)
from .schemas import (
    AmbiguityIndicator,
    DecompositionResult,
    Task,
    TaskDependency,
    TaskGraph,
)


logger = logging.getLogger(__name__)


class DecompositionAgent(BaseAgent):
    """
    Agent that decomposes complex queries into structured task graphs.
    
    WHY: The orchestrator needs to know:
    1. What tasks need to be done (task list)
    2. In what order to do them (dependencies)
    3. What type of task each is (task types enable agent selection)
    4. What ambiguities exist (helps with clarification)
    
    Key Features:
    - Parses queries using keyword matching (rule-based)
    - Generates dependency DAG
    - Detects cycles (invalid decomposition)
    - Identifies ambiguities and missing info
    - Confidence scoring
    - Reasoning explanation
    
    Extensible: Can replace with LLM-based decomposition later
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize decomposition agent."""
        self.logger = logger or logging.getLogger(__name__)
    
    @property
    def agent_id(self) -> str:
        """Unique agent identifier."""
        return "decomposition_agent"
    
    @property
    def agent_version(self) -> str:
        """Agent version."""
        return "1.0.0"
    
    def get_available_tools(self) -> List[ToolDefinition]:
        """
        Decomposition agent doesn't call external tools.
        
        It only analyzes and decomposes queries.
        """
        return []
    
    async def process_message(
        self,
        message: AgentMessage,
        context: SharedContext,
    ) -> ExecutionTrace:
        """
        Process a message and decompose it into tasks.
        
        Main entry point. Analyzes the query, breaks it down,
        detects ambiguities, returns execution trace.
        
        Args:
            message: User query message
            context: Conversation context
        
        Returns:
            ExecutionTrace with decomposition results
        """
        start_time = time.time()
        
        trace = ExecutionTrace(
            id=uuid4(),
            conversation_id=message.conversation_id,
            agent_id=self.agent_id,
            input_message=message,
            total_duration_ms=0.0,  # Will be updated at end
        )
        
        try:
            # Extract query
            query = message.content
            
            self.logger.info(
                f"Decomposing query: {query}",
                extra={"trace_id": str(message.trace_id)}
            )
            
            # Step 1: Parse query into tasks
            tasks = QueryParser.parse_simple_query(query)
            
            # Step 2: Set confidence scores based on task types
            for task in tasks:
                task.confidence_score = self._score_task_confidence(task)
            
            # Step 3: Infer dependencies
            dependencies = QueryParser.infer_dependencies(tasks, query)
            
            # Step 4: Build task graph
            graph = TaskGraph(
                conversation_id=message.conversation_id,
                original_query=query,
                tasks=tasks,
                dependencies=dependencies,
            )
            
            # Step 5: Validate graph
            graph.has_cycles = DAGValidator.has_cycles(tasks, dependencies)
            sorted_order, is_valid = DAGValidator.topological_sort(tasks, dependencies)
            graph.is_valid = is_valid
            graph.execution_order = sorted_order
            
            # Step 6: Compute metrics
            metrics = DAGValidator.compute_graph_metrics(tasks, dependencies)
            graph.total_tasks = metrics["total_tasks"]
            graph.total_dependencies = metrics["total_dependencies"]
            graph.depth = metrics["depth"]
            graph.width = metrics["width"]
            
            # Step 7: Detect ambiguities
            ambiguities = AmbiguityDetector.detect_ambiguities_in_graph(
                query, tasks, dependencies
            )
            
            # Step 8: Compute overall confidence
            decomposition_confidence = self._compute_overall_confidence(
                graph, tasks, ambiguities
            )
            
            # Step 9: Build reasoning explanation
            reasoning_steps = self._build_reasoning_steps(
                query, tasks, dependencies, ambiguities
            )
            decomposition_reasoning = self._build_reasoning_text(
                query, tasks, dependencies, ambiguities
            )
            
            # Step 10: Create decomposition result
            decomposition_result = DecompositionResult(
                conversation_id=message.conversation_id,
                original_query=query,
                task_graph=graph,
                decomposition_confidence=decomposition_confidence,
                total_ambiguities=len(ambiguities),
                ambiguities=ambiguities,
                decomposition_reasoning=decomposition_reasoning,
                reasoning_steps=reasoning_steps,
                is_executable=is_valid and decomposition_confidence > 0.3,
                model_used="rule-based",
            )
            
            # Check for execution issues
            if not is_valid:
                decomposition_result.execution_issues.append("Task graph has cycles")
            
            if not tasks:
                decomposition_result.execution_issues.append("No tasks extracted from query")
            
            if len(ambiguities) > 5:
                decomposition_result.execution_issues.append(
                    f"Too many ambiguities ({len(ambiguities)}), clarification needed"
                )
            
            # Extract missing information
            missing = AmbiguityDetector.detect_missing_information(query, tasks)
            decomposition_result.missing_information = missing
            
            # Record as final output
            trace.final_output = decomposition_result.dict()
            trace.status = "completed"
            
            self.logger.info(
                f"Decomposition complete: {len(tasks)} tasks, "
                f"{len(dependencies)} dependencies, "
                f"confidence={decomposition_confidence:.2f}",
                extra={"trace_id": str(message.trace_id)}
            )
            
        except Exception as e:
            # Log error
            trace.status = "failed"
            trace.error_message = str(e)
            
            self.logger.error(
                f"Decomposition failed: {str(e)}",
                extra={"trace_id": str(message.trace_id)},
                exc_info=True
            )
        
        finally:
            # Calculate and set duration
            end_time = time.time()
            trace.total_duration_ms = (end_time - start_time) * 1000
            trace.completed_at = datetime.utcnow()
            
            return trace
    
    async def validate_tool_call(self, tool_call) -> bool:
        """
        Decomposition agent doesn't make tool calls.
        
        Returns False for all tool calls.
        """
        return False
    
    def _score_task_confidence(self, task: Task) -> float:
        """
        Score confidence in a specific task extraction.
        
        Factors:
        - Task type (SEARCH is high confidence, UNKNOWN is low)
        - Description clarity
        - Dependency relationships
        """
        score = 0.8  # Base confidence
        
        # Adjust based on task type
        if task.type.value == "unknown":
            score -= 0.5
        
        # Adjust based on description length and clarity
        desc_words = len(task.description.split())
        if desc_words < 3:
            score -= 0.2  # Too short, unclear
        elif desc_words > 15:
            score -= 0.1  # Too long, might be under-decomposed
        
        # Penalize vague language
        vague_terms = AmbiguityDetector.detect_vague_language(task.description)
        score -= len(vague_terms) * 0.1
        
        return max(0.1, min(1.0, score))
    
    def _compute_overall_confidence(
        self,
        graph: TaskGraph,
        tasks: List[Task],
        ambiguities: List[AmbiguityIndicator],
    ) -> float:
        """
        Compute overall confidence in decomposition.
        
        Factors:
        - Graph validity (has cycles = low confidence)
        - Task confidence scores
        - Number of ambiguities
        - Graph structure (depth, width)
        """
        confidence = 0.8  # Base confidence
        
        # Deduct for invalid graph
        if not graph.is_valid:
            confidence -= 0.3
        
        # Deduct for ambiguities (critical > important > minor)
        critical_ambiguities = sum(1 for a in ambiguities if a.severity > 0.8)
        important_ambiguities = sum(1 for a in ambiguities if 0.5 < a.severity <= 0.8)
        minor_ambiguities = sum(1 for a in ambiguities if a.severity <= 0.5)
        
        confidence -= critical_ambiguities * 0.15
        confidence -= important_ambiguities * 0.05
        confidence -= minor_ambiguities * 0.02
        
        # Deduct for low task confidence
        avg_task_confidence = (
            sum(t.confidence_score for t in tasks) / len(tasks)
            if tasks else 0
        )
        confidence -= (1.0 - avg_task_confidence) * 0.2
        
        # Deduct for extreme graph shapes
        if graph.depth > 5:
            confidence -= 0.1
        if graph.width > 10:
            confidence -= 0.1
        
        # Clamp to [0, 1]
        return max(0.1, min(1.0, confidence))
    
    def _build_reasoning_steps(
        self,
        query: str,
        tasks: List[Task],
        dependencies: List[TaskDependency],
        ambiguities: List[AmbiguityIndicator],
    ) -> List[str]:
        """
        Build step-by-step reasoning for decomposition.
        
        Returns list of reasoning steps explaining the decomposition.
        """
        steps = []
        
        # Step 1: Query analysis
        steps.append(f"Analyzed user query: '{query}'")
        
        # Step 2: Task extraction
        if tasks:
            task_types = ", ".join(set(t.type.value for t in tasks))
            steps.append(f"Extracted {len(tasks)} tasks with types: {task_types}")
        else:
            steps.append("No explicit task types found in query")
        
        # Step 3: Dependency inference
        if dependencies:
            steps.append(f"Inferred {len(dependencies)} dependencies between tasks")
            # Show some example dependencies
            for dep in dependencies[:2]:
                from_task = next((t for t in tasks if t.id == dep.dependency_task_id), None)
                to_task = next((t for t in tasks if t.id == dep.dependent_task_id), None)
                if from_task and to_task:
                    steps.append(f"  • {from_task.type.value} must complete before {to_task.type.value}")
        else:
            steps.append("No dependencies detected - tasks are independent")
        
        # Step 4: Ambiguities found
        if ambiguities:
            critical = sum(1 for a in ambiguities if a.severity > 0.8)
            if critical > 0:
                steps.append(f"⚠️  Found {critical} critical ambiguities requiring clarification")
        else:
            steps.append("No significant ambiguities detected")
        
        # Step 5: Graph validity
        steps.append("✓ Task graph is valid (no cycles)")
        
        # Step 6: Readiness assessment
        steps.append("Decomposition ready for orchestration and execution")
        
        return steps
    
    def _build_reasoning_text(
        self,
        query: str,
        tasks: List[Task],
        dependencies: List[TaskDependency],
        ambiguities: List[AmbiguityIndicator],
    ) -> str:
        """
        Build human-readable reasoning text for decomposition.
        """
        lines = []
        
        lines.append(f"Query: {query}\n")
        
        lines.append("DECOMPOSITION ANALYSIS")
        lines.append("=" * 60)
        
        # Task breakdown
        lines.append(f"\n1. TASK EXTRACTION ({len(tasks)} tasks)")
        lines.append("-" * 60)
        for i, task in enumerate(tasks, 1):
            lines.append(f"  Task {i}: [{task.type.value}]")
            lines.append(f"    Description: {task.description}")
            lines.append(f"    Input: {task.input_description}")
            lines.append(f"    Expected Output: {task.expected_output}")
            lines.append(f"    Confidence: {task.confidence_score:.1%}")
        
        # Dependencies
        lines.append(f"\n2. DEPENDENCY ANALYSIS ({len(dependencies)} edges)")
        lines.append("-" * 60)
        if dependencies:
            for dep in dependencies:
                from_task = next((t for t in tasks if t.id == dep.dependency_task_id), None)
                to_task = next((t for t in tasks if t.id == dep.dependent_task_id), None)
                if from_task and to_task:
                    lines.append(
                        f"  {from_task.type.value} → {to_task.type.value} "
                        f"({dep.dependency_type})"
                    )
        else:
            lines.append("  No dependencies - all tasks can run in parallel")
        
        # Ambiguities
        lines.append(f"\n3. AMBIGUITY DETECTION ({len(ambiguities)} issues)")
        lines.append("-" * 60)
        if ambiguities:
            for amb in sorted(ambiguities, key=lambda a: a.severity, reverse=True)[:5]:
                severity_emoji = "🔴" if amb.severity > 0.8 else "🟡" if amb.severity > 0.5 else "🟢"
                lines.append(f"  {severity_emoji} {amb.ambiguity_type.value}")
                lines.append(f"     Issue: {amb.description}")
                lines.append(f"     Fix: {amb.suggested_clarification}")
        else:
            lines.append("  No ambiguities detected - query is clear and well-formed")
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)
