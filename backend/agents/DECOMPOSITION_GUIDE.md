# Decomposition Agent Implementation Guide

## Overview

The **DecompositionAgent** converts ambiguous natural language queries into structured, typed task graphs with explicit dependencies. It's the first stage of query processing before orchestration.

### Key Features

✅ **Query Parsing** - Extracts actions and converts to typed tasks  
✅ **Dependency Inference** - Builds DAG from task relationships  
✅ **Cycle Detection** - Ensures execution is valid (no circular dependencies)  
✅ **Ambiguity Detection** - Identifies unclear requirements and missing information  
✅ **Confidence Scoring** - Quantifies decomposition quality (0-1)  
✅ **Structured Output** - Task graphs ready for orchestrator execution  

## Architecture

### Components

#### 1. Task Type System (`TaskType` enum)

Defines the semantic type of each task:

```python
class TaskType(str, Enum):
    SEARCH = "search"           # Information retrieval
    ANALYZE = "analyze"         # Data analysis
    AGGREGATE = "aggregate"     # Combine multiple inputs
    GENERATE = "generate"       # Create new content
    SYNTHESIZE = "synthesize"   # Combine to create output
    SUMMARIZE = "summarize"     # Create summary
    REASON = "reason"           # Logical reasoning
    VALIDATE = "validate"       # Correctness checking
    # ... etc
```

**WHY**: Task types enable the orchestrator to:
- Select appropriate agents for each task
- Infer execution dependencies
- Estimate costs and tokens
- Parallelize independent tasks
- Provide fallbacks for task failures

#### 2. Task Graph (DAG)

Represents:
- **Nodes**: Individual tasks with descriptions and confidence scores
- **Edges**: Dependencies between tasks  
- **Properties**: Execution order, depth, width, validity

```
Query: "Find papers, analyze results, summarize findings"
       ↓
    ┌─────┐
    │Search│ (root task, no dependencies)
    └──┬──┘
       │
    ┌──▼──────┐
    │Analyze  │ (depends on Search)
    └──┬──────┘
       │
    ┌──▼────────┐
    │Summarize  │ (depends on Analyze)
    └───────────┘
```

#### 3. Query Parser

Converts natural language to tasks:

```python
QueryParser.parse_simple_query(query)
# Returns: List[Task] with types, descriptions, I/O specs

QueryParser.infer_dependencies(tasks, query)
# Returns: List[TaskDependency] with dependency relationships

QueryParser.build_task_graph(query)
# Returns: TaskGraph with validation and metrics
```

#### 4. Ambiguity Detector

Identifies issues:

```python
AmbiguityDetector.detect_vague_language(text)
# Returns: [(vague_word, context), ...]

AmbiguityDetector.detect_missing_information(query, tasks)
# Returns: [missing_info_description, ...]

AmbiguityDetector.detect_ambiguities_in_graph(query, tasks, deps)
# Returns: [AmbiguityIndicator, ...] with severity levels
```

#### 5. DAG Validator

Ensures graph validity:

```python
DAGValidator.has_cycles(tasks, dependencies)
# Returns: bool - True if cycle detected

DAGValidator.topological_sort(tasks, dependencies)
# Returns: (sorted_task_ids, is_valid)

DAGValidator.compute_graph_metrics(tasks, dependencies)
# Returns: {depth, width, total_tasks, total_dependencies}
```

## Data Model

### Task

```python
class Task(BaseModel):
    id: UUID                        # Unique ID
    type: TaskType                  # Semantic type (SEARCH, ANALYZE, etc.)
    description: str                # What needs to be done
    
    input_description: str          # What inputs are needed
    expected_output: str            # What output should be
    
    confidence_score: float         # 0-1, how confident in extraction
    ambiguities: List[AmbiguityIndicator]  # Issues with this task
    
    reasoning: str                  # Why this task exists
    
    status: TaskStatus = PENDING    # Current state
    output: Optional[Dict]          # Result after execution
```

### TaskDependency

```python
class TaskDependency(BaseModel):
    dependent_task_id: UUID         # Task that depends on other
    dependency_task_id: UUID        # Task that must complete first
    dependency_type: str            # REQUIRES, OPTIONAL, CONDITIONAL
```

**WHY**: Explicit types enable different handling:
- `REQUIRES`: Must complete before dependent can start
- `OPTIONAL`: Preferred but not required
- `CONDITIONAL`: Only needed if certain conditions met

### TaskGraph

```python
class TaskGraph(BaseModel):
    id: UUID
    conversation_id: UUID
    original_query: str
    
    tasks: List[Task]               # All tasks
    dependencies: List[TaskDependency]  # All edges
    
    is_valid: bool                  # No cycles, well-formed
    execution_order: List[UUID]     # Topologically sorted
    has_cycles: bool                # Cycle detection result
    
    total_tasks: int
    total_dependencies: int
    depth: int                      # Longest path
    width: int                      # Max parallel tasks
```

### DecompositionResult

```python
class DecompositionResult(BaseModel):
    task_graph: TaskGraph           # The actual decomposition
    
    decomposition_confidence: float # Overall 0-1 confidence
    total_ambiguities: int          # Number of issues found
    ambiguities: List[AmbiguityIndicator]  # All issues
    
    is_executable: bool             # Can orchestrator execute it?
    execution_issues: List[str]     # Problems (if any)
    
    decomposition_reasoning: str    # Explanation
    reasoning_steps: List[str]      # Step-by-step reasoning
```

## Usage Examples

### Basic Usage

```python
from backend.agents import DecompositionAgent
from backend.schemas import AgentMessage, MessageRole, SharedContext
from uuid import uuid4

# Create agent
agent = DecompositionAgent()

# Create message
message = AgentMessage(
    conversation_id=uuid4(),
    role=MessageRole.USER,
    content="Find customer trends and analyze sentiment",
    agent_id="user",
    sequence_number=1,
)

# Create context
context = SharedContext(
    conversation_id=message.conversation_id,
    user_intent=message.content,
)

# Decompose
trace = await agent.process_message(message, context)

# Extract result
result = trace.final_output
print(f"Tasks: {len(result['task_graph']['tasks'])}")
print(f"Dependencies: {len(result['task_graph']['dependencies'])}")
print(f"Confidence: {result['decomposition_confidence']:.1%}")
print(f"Executable: {result['is_executable']}")
```

### Query Parsing Only

```python
from backend.agents.decomposition_utils import QueryParser

# Simple parse
tasks = QueryParser.parse_simple_query("Search for papers and analyze them")
# Returns: [Task(SEARCH, ...), Task(ANALYZE, ...)]

# Full graph
graph = QueryParser.build_task_graph(
    "Find data, analyze trends, summarize results"
)
# Returns: TaskGraph with validation, metrics, execution order
```

### Ambiguity Analysis

```python
from backend.agents.decomposition_utils import AmbiguityDetector

query = "Analyze it somehow with data"

# Vague language
vague = AmbiguityDetector.detect_vague_language(query)
# Returns: [("somehow", "analyze it somehow with"), ("it", "Analyze it")]

# Missing info
missing = AmbiguityDetector.detect_missing_information(query, tasks)
# Returns: ["No temporal information...", "No scope/boundaries..."]

# Complete analysis
ambiguities = AmbiguityDetector.detect_ambiguities_in_graph(
    query, tasks, dependencies
)
# Returns: [AmbiguityIndicator(type=UNDEFINED_TERM, severity=0.5), ...]
```

### DAG Validation

```python
from backend.agents.decomposition_utils import DAGValidator

# Check cycles
has_cycles = DAGValidator.has_cycles(tasks, dependencies)

# Topological sort
sorted_order, is_valid = DAGValidator.topological_sort(tasks, dependencies)

# Metrics
metrics = DAGValidator.compute_graph_metrics(tasks, dependencies)
# Returns: {depth: 3, width: 2, total_tasks: 5, total_dependencies: 4}
```

## Decomposition Process

### Step-by-Step Flow

```
1. PARSE QUERY
   Input: "Find papers, analyze sentiment, summarize trends"
   ↓
   Extract action keywords: find, analyze, summarize

2. EXTRACT TASKS
   ↓
   Task 1: [SEARCH] Find papers on {topic}
   Task 2: [ANALYZE] Analyze sentiment
   Task 3: [SUMMARIZE] Summarize trends

3. INFER DEPENDENCIES
   ↓
   SEARCH → ANALYZE (analyze needs search results)
   ANALYZE → SUMMARIZE (summarize needs analysis)

4. BUILD GRAPH
   ↓
   Create TaskGraph with tasks, dependencies, execution order

5. VALIDATE
   ↓
   Check cycles: ✓ No cycles
   Topological sort: [SEARCH, ANALYZE, SUMMARIZE]
   Compute metrics: depth=2, width=1

6. DETECT AMBIGUITIES
   ↓
   Check vague language, missing info, unclear references
   Results: No critical issues

7. SCORE CONFIDENCE
   ↓
   Task confidence: 0.8 (clear action) + 0.85 (specific domain) + 0.75 (generic)
   Graph confidence: 0.85 (valid DAG, few ambiguities)
   Overall: 0.83 (83% confidence)

8. RETURN RESULT
   ↓
   DecompositionResult with task_graph, confidence, ambiguities, reasoning
```

## Routing Rules

### Task Type Dependencies

| From | To | Rule | Reason |
|------|-----|------|--------|
| SEARCH | ANALYZE | Always | Need data before analysis |
| SEARCH | AGGREGATE | Common | Combine search results |
| ANALYZE | AGGREGATE | Usually | Process before combining |
| ANALYZE | SUMMARIZE | Common | Analyze before summarizing |
| AGGREGATE | SYNTHESIZE | Often | Combine before synthesis |
| * | VALIDATE | Optional | Can validate any output |

### Inference Algorithm

1. **Identify all task types** in query
2. **Build implicit graph** based on rules above
3. **Prune unnecessary edges** (don't add SEARCH → SUMMARIZE if ANALYZE is between)
4. **Validate DAG** (topological sort, cycle detection)
5. **Return execution order** (topologically sorted)

## Ambiguity Types

| Type | Severity | Example | Clarification |
|------|----------|---------|---------------|
| MISSING_INFO | Medium | "Analyze data" (which data?) | Specify data source |
| VAGUE_LANGUAGE | Low | "Maybe do something" | Be specific |
| UNCLEAR_REFERENCE | Medium | "Analyze it" (it = ?) | Clarify reference |
| MULTIPLE_INTERPRETATIONS | Medium | "Analyze and report" | Exact steps? |
| UNDEFINED_TERM | Low | Unknown domain term | Define term |
| CIRCULAR_DEPENDENCY | Critical | Tasks depend on each other | Reorder tasks |
| IMPOSSIBLE_CONSTRAINT | Critical | Conflicting requirements | Resolve conflict |
| OVER_DECOMPOSED | Low | 50+ tiny tasks | Combine tasks |
| UNDER_DECOMPOSED | Low | One giant task | Break into steps |

## Confidence Scoring

**Formula**: Base 0.8 - Deductions

**Deductions**:
- Invalid graph (has cycles): -0.3
- Per critical ambiguity: -0.15
- Per important ambiguity: -0.05
- Per minor ambiguity: -0.02
- Low task confidence: -0.2 × (1 - avg_confidence)
- Extreme depth (>5): -0.1
- Extreme width (>10): -0.1

**Result**: Clamped to [0.1, 1.0]

**Interpretation**:
- `0.9-1.0`: Clear, well-defined decomposition
- `0.7-0.9`: Good decomposition, minor issues
- `0.5-0.7`: Acceptable, some ambiguities
- `0.3-0.5`: Poor, significant clarification needed
- `<0.3`: Very unclear, not executable

## Orchestrator Integration

### DecompositionAgent in Workflow

```
User Query
    ↓
┌─────────────────────────────┐
│  DecompositionAgent         │ ← HERE
│  - Parse query              │
│  - Extract tasks            │
│  - Infer dependencies       │
│  - Detect ambiguities       │
│  - Return DecompositionResult│
└────────────┬────────────────┘
             ↓
┌─────────────────────────────┐
│  DynamicOrchestrator        │
│  - Analyze task graph       │
│  - Route to agents          │
│  - Execute in order         │
│  - Aggregate results        │
└─────────────────────────────┘
```

### Output → Input

**DecompositionAgent Output**:
```python
DecompositionResult(
    task_graph=TaskGraph(
        tasks=[Task(...), Task(...), ...],
        dependencies=[TaskDependency(...), ...],
        execution_order=[task_id1, task_id2, ...]
    ),
    decomposition_confidence=0.85,
    is_executable=True,
    reasoning_steps=[...]
)
```

**DynamicOrchestrator Input**:
- Takes task_graph.execution_order
- For each task, selects agent based on TaskType
- Respects dependencies (blocks until predecessors done)
- Logs orchestration decisions

### Error Handling

**If decomposition fails**:
- `is_executable = False`
- `execution_issues = ["Cannot parse query", ...]`
- Orchestrator requests clarification
- User provides additional context
- Decomposition retried

## Testing

### Test Categories

**1. Simple Queries**
```python
"Search for papers"
→ [Task(SEARCH, ...)]
→ Confidence: 0.9+
```

**2. Complex Queries**
```python
"Find data, analyze trends, identify patterns, summarize insights"
→ [Task(SEARCH), Task(ANALYZE), Task(ANALYZE), Task(SUMMARIZE)]
→ Dependencies: Search → Analyze → Summarize
→ Confidence: 0.85+
```

**3. Ambiguous Queries**
```python
"Do something with data"
→ [Task(UNKNOWN, ...)]
→ Ambiguities: ["No action specified", "No data source"]
→ Confidence: <0.5
```

**4. Adversarial Cases**
- Circular logic ("Analyze it based on summary, summarize based on analysis")
- Contradictions ("Search for AND don't search for")
- Extremely vague input ("stuff")
- Special characters ("@#$% & <data>")
- Self-references ("Task depends on itself")

## Implementation Details

### Keyword Matching Strategy

**ACTION_TO_TASK_TYPE mapping**:
```python
"search" → SEARCH
"find" → SEARCH
"analyze" → ANALYZE
"synthesize" → SYNTHESIZE
"aggregate" → AGGREGATE
"summarize" → SUMMARIZE
# ... etc (30+ mappings)
```

**Algorithm**:
1. Convert query to lowercase
2. Check each keyword in order
3. Extract text after keyword
4. Create task with that description
5. Score confidence based on keyword clarity

### Dependency Inference Heuristics

```
IF query contains (SEARCH + ANALYZE)
  THEN SEARCH → ANALYZE
    (data must be retrieved before analysis)

IF query contains (ANALYZE + AGGREGATE)
  THEN ANALYZE → AGGREGATE
    (process before combining)

IF query contains (AGGREGATE + SUMMARIZE)
  THEN AGGREGATE → SUMMARIZE
    (combine before summarizing)
```

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Parse query | <10ms | Regex + keyword matching |
| Infer dependencies | <5ms | Heuristic-based |
| Validate DAG | <20ms | Topological sort (O(V+E)) |
| Detect ambiguities | <10ms | Pattern matching |
| Total | <50ms | End-to-end |

## Future Enhancements

1. **LLM-Based Decomposition**
   - Replace keyword matching with LLM
   - Extract arbitrary task types
   - More natural parsing

2. **Learning from Feedback**
   - Track decomposition accuracy
   - Learn common query patterns
   - Improve confidence scoring

3. **Task Merging**
   - Detect redundant tasks
   - Combine sequential tasks
   - Optimize execution plan

4. **Constraint-Aware Decomposition**
   - Budget constraints
   - Time constraints
   - Resource constraints

5. **Multi-Language Support**
   - Translate to English
   - Language-specific keywords
   - Localized ambiguity detection

---

## See Also

- [ORCHESTRATOR_GUIDE.md](../orchestration/ORCHESTRATOR_GUIDE.md) - How orchestrator uses task graphs
- [test_decomposition_agent.py](../../tests/test_decomposition_agent.py) - Comprehensive tests
- [examples.py](./examples.py) - Usage examples
