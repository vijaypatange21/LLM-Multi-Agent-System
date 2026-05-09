"""
Agent-related schemas for task decomposition and execution.

WHY: Agents need to reason about tasks. These schemas define the structure
of tasks, their dependencies, and decomposition results.

Architecture:
- Task: Unit of work with type, description, dependencies
- TaskGraph: DAG of tasks with explicit dependencies
- DecompositionResult: Output from decomposition agent with ambiguities
- AmbiguityIndicator: Flags uncertain parts of decomposition
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """
    Enumeration of task types.
    
    Enables orchestrator to understand what kind of work each task represents.
    """
    # Information gathering
    SEARCH = "search"                # Search for information
    RETRIEVE = "retrieve"            # Retrieve from database/API
    FETCH = "fetch"                  # Fetch external data
    
    # Processing
    ANALYZE = "analyze"              # Analyze data
    TRANSFORM = "transform"          # Transform format
    AGGREGATE = "aggregate"          # Combine multiple inputs
    FILTER = "filter"                # Filter/subset data
    
    # Generation
    GENERATE = "generate"            # Generate new content
    SYNTHESIZE = "synthesize"        # Combine to create output
    SUMMARIZE = "summarize"          # Create summary
    
    # Reasoning
    REASON = "reason"                # Logical reasoning
    PLAN = "plan"                    # Make a plan
    EVALUATE = "evaluate"            # Assess/score
    
    # Validation
    VALIDATE = "validate"            # Check correctness
    VERIFY = "verify"                # Verify information
    CHECK = "check"                  # Quality check
    
    # Other
    UNKNOWN = "unknown"              # Unknown/ambiguous task type


class TaskStatus(str, Enum):
    """Status of a task in execution."""
    PENDING = "pending"              # Waiting to execute
    BLOCKED = "blocked"              # Blocked by dependencies
    READY = "ready"                  # Ready to execute
    IN_PROGRESS = "in_progress"      # Currently executing
    COMPLETED = "completed"          # Completed successfully
    FAILED = "failed"                # Failed
    SKIPPED = "skipped"              # Skipped (e.g., optional)


class AmbiguityType(str, Enum):
    """Types of ambiguities detected in decomposition."""
    MISSING_INFO = "missing_info"                # Critical info missing
    UNCLEAR_REFERENCE = "unclear_reference"      # Ambiguous reference
    MULTIPLE_INTERPRETATIONS = "multiple_interpretations"  # Polysemous
    UNDEFINED_TERM = "undefined_term"            # Term not defined
    CIRCULAR_DEPENDENCY = "circular_dependency"  # Invalid cycle
    IMPOSSIBLE_CONSTRAINT = "impossible_constraint"  # Conflicting requirements
    OVER_DECOMPOSED = "over_decomposed"          # Too granular
    UNDER_DECOMPOSED = "under_decomposed"        # Too coarse


class AmbiguityIndicator(BaseModel):
    """
    Flags potential ambiguity or missing information in decomposition.
    
    Helps user understand what clarification might be needed.
    """
    id: UUID = Field(default_factory=uuid4)
    ambiguity_type: AmbiguityType
    location: str                          # Which task or dependency
    description: str                       # What's ambiguous
    severity: float = Field(ge=0, le=1)   # 0=minor, 1=critical
    suggested_clarification: Optional[str]  # How to clarify
    
    class Config:
        use_enum_values = False


class TaskDependency(BaseModel):
    """
    Represents a dependency between two tasks.
    
    WHY: Explicit dependencies enable:
    - Topological sorting for valid execution order
    - Blocking management (don't execute until dependencies done)
    - Cycle detection (circular dependencies = invalid)
    - Parallel execution planning
    """
    dependent_task_id: UUID            # Task that depends on other
    dependency_task_id: UUID           # Task that must complete first
    dependency_type: str = Field(       # REQUIRES, OPTIONAL, CONDITIONAL
        default="REQUIRES",
        description="Type of dependency"
    )
    
    def __hash__(self):
        return hash((self.dependent_task_id, self.dependency_task_id))
    
    def __eq__(self, other):
        if not isinstance(other, TaskDependency):
            return False
        return (self.dependent_task_id == other.dependent_task_id and
                self.dependency_task_id == other.dependency_task_id)


class Task(BaseModel):
    """
    Represents a single task in decomposition.
    
    WHY: Breaks complex query into units the orchestrator can execute.
    Each task is:
    - Typed (SEARCH, ANALYZE, AGGREGATE, etc.)
    - Has explicit description
    - Has dependencies on other tasks
    - Can be executed by an agent
    """
    id: UUID = Field(default_factory=uuid4)
    type: TaskType                      # What kind of task
    description: str                    # What needs to be done
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    
    # Execution context
    input_description: str              # What inputs needed
    expected_output: str                # What output should be
    
    # Confidence and ambiguity
    confidence_score: float = Field(    # 0-1 how confident in this task
        default=1.0,
        ge=0,
        le=1,
    )
    ambiguities: List[AmbiguityIndicator] = Field(default_factory=list)
    
    # Metadata
    reasoning: str                      # Why this task exists
    estimated_tokens: int = Field(default=0)  # LLM tokens estimate
    estimated_duration_ms: int = Field(default=0)
    
    # Execution result
    output: Optional[Dict] = None       # Result after execution
    error: Optional[str] = None         # Error if failed
    
    class Config:
        use_enum_values = False


class TaskGraph(BaseModel):
    """
    DAG of tasks with dependencies.
    
    WHY: Enables orchestrator to:
    - Execute tasks in valid order (topological sort)
    - Parallelize independent tasks
    - Block dependent tasks until prerequisites done
    - Detect invalid cycles
    - Replan on failures
    """
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    original_query: str                 # User's original question
    
    # Graph structure
    tasks: List[Task]                   # All tasks
    dependencies: List[TaskDependency]  # All dependencies
    
    # Graph properties
    is_valid: bool = Field(default=True)  # No cycles, well-formed
    execution_order: List[UUID] = Field(   # Topologically sorted
        default_factory=list
    )
    has_cycles: bool = Field(default=False)  # Cycle detection result
    
    # Metrics
    total_tasks: int                    # Number of tasks
    total_dependencies: int             # Number of edges
    depth: int = Field(default=0)       # Maximum path length
    width: int = Field(default=0)       # Maximum parallel tasks
    
    class Config:
        use_enum_values = False
    
    def get_task(self, task_id: UUID) -> Optional[Task]:
        """Get task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_dependencies_for_task(self, task_id: UUID) -> List[TaskDependency]:
        """Get all dependencies for a specific task."""
        return [d for d in self.dependencies if d.dependent_task_id == task_id]
    
    def get_dependents_for_task(self, task_id: UUID) -> List[TaskDependency]:
        """Get all tasks that depend on this task."""
        return [d for d in self.dependencies if d.dependency_task_id == task_id]
    
    def get_tasks_at_level(self, level: int) -> List[Task]:
        """Get all tasks at a specific level (0=roots, higher=deeper)."""
        # Level 0 = tasks with no dependencies
        # Level N = tasks whose all dependencies are at level < N
        levels = self._compute_levels()
        task_ids = [tid for tid, lvl in levels.items() if lvl == level]
        return [self.get_task(tid) for tid in task_ids if self.get_task(tid)]
    
    def _compute_levels(self) -> Dict[UUID, int]:
        """Compute level of each task (longest path from roots)."""
        levels: Dict[UUID, int] = {}
        
        # Find roots (no incoming edges)
        incoming = {task.id: 0 for task in self.tasks}
        for dep in self.dependencies:
            incoming[dep.dependent_task_id] += 1
        
        roots = [tid for tid, count in incoming.items() if count == 0]
        queue = [(root, 0) for root in roots]
        
        while queue:
            task_id, level = queue.pop(0)
            levels[task_id] = max(levels.get(task_id, 0), level)
            
            # Add dependents
            for dep in self.get_dependents_for_task(task_id):
                queue.append((dep.dependent_task_id, level + 1))
        
        return levels


class DecompositionResult(BaseModel):
    """
    Complete result of query decomposition.
    
    WHY: Encapsulates everything the decomposition agent produces so the
    orchestrator knows what to execute and what issues were found.
    """
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    original_query: str
    
    # The actual decomposition
    task_graph: TaskGraph              # DAG of tasks
    
    # Quality metrics
    decomposition_confidence: float = Field(  # Overall confidence 0-1
        default=1.0,
        ge=0,
        le=1,
    )
    total_ambiguities: int              # Number of ambiguities found
    
    # Issues found
    ambiguities: List[AmbiguityIndicator] = Field(  # All ambiguities
        default_factory=list
    )
    missing_information: List[str] = Field(      # What's missing
        default_factory=list
    )
    
    # Reasoning
    decomposition_reasoning: str        # Why this decomposition
    reasoning_steps: List[str] = Field(  # Step-by-step reasoning
        default_factory=list
    )
    
    # Validation
    is_executable: bool = Field(        # Can orchestrator execute it?
        default=True
    )
    execution_issues: List[str] = Field(   # Problems executing this
        default_factory=list
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = Field(default="rule-based")  # Which decomposer
    
    class Config:
        use_enum_values = False
