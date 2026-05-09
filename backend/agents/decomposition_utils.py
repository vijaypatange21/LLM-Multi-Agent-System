"""
Utilities for task decomposition.

WHY: Provides reusable functions for:
- Parsing queries into tasks
- Generating dependency DAGs
- Detecting ambiguities
- Validating task graphs
- Topological sorting
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from .schemas import (
    AmbiguityIndicator,
    AmbiguityType,
    Task,
    TaskDependency,
    TaskGraph,
    TaskType,
)


class DAGValidator:
    """Validates task graphs for cycles and structure."""
    
    @staticmethod
    def has_cycles(tasks: List[Task], dependencies: List[TaskDependency]) -> bool:
        """
        Detect cycles using DFS.
        
        Returns True if graph has cycles, False if DAG.
        """
        # Build adjacency list
        graph: Dict[UUID, List[UUID]] = {task.id: [] for task in tasks}
        for dep in dependencies:
            graph[dep.dependent_task_id].append(dep.dependency_task_id)
        
        # DFS to detect cycles
        visited: Set[UUID] = set()
        rec_stack: Set[UUID] = set()
        
        def has_cycle_dfs(node: UUID) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph[node]:
                if neighbor not in visited:
                    if has_cycle_dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        # Check each component
        for task_id in graph:
            if task_id not in visited:
                if has_cycle_dfs(task_id):
                    return True
        
        return False
    
    @staticmethod
    def topological_sort(
        tasks: List[Task],
        dependencies: List[TaskDependency]
    ) -> Tuple[List[UUID], bool]:
        """
        Topologically sort tasks.
        
        Returns (sorted_task_ids, is_valid).
        is_valid=False if cycle detected.
        """
        if DAGValidator.has_cycles(tasks, dependencies):
            return ([], False)
        
        # Build graph
        graph: Dict[UUID, List[UUID]] = {task.id: [] for task in tasks}
        in_degree: Dict[UUID, int] = {task.id: 0 for task in tasks}
        
        for dep in dependencies:
            graph[dep.dependency_task_id].append(dep.dependent_task_id)
            in_degree[dep.dependent_task_id] += 1
        
        # Kahn's algorithm
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        sorted_tasks = []
        
        while queue:
            task_id = queue.pop(0)
            sorted_tasks.append(task_id)
            
            for neighbor in graph[task_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # All tasks should be included
        if len(sorted_tasks) != len(tasks):
            return ([], False)  # Cycle exists
        
        return (sorted_tasks, True)
    
    @staticmethod
    def compute_graph_metrics(
        tasks: List[Task],
        dependencies: List[TaskDependency]
    ) -> Dict:
        """Compute metrics: depth, width, etc."""
        if not tasks:
            return {"depth": 0, "width": 0, "total_tasks": 0}
        
        # Compute level of each task
        levels: Dict[UUID, int] = {}
        incoming: Dict[UUID, int] = {task.id: 0 for task in tasks}
        graph: Dict[UUID, List[UUID]] = {task.id: [] for task in tasks}
        
        for dep in dependencies:
            graph[dep.dependency_task_id].append(dep.dependent_task_id)
            incoming[dep.dependent_task_id] += 1
        
        queue = [tid for tid, count in incoming.items() if count == 0]
        while queue:
            task_id = queue.pop(0)
            max_prev_level = max(
                [levels.get(dep.dependency_task_id, -1) for dep in dependencies
                 if dep.dependent_task_id == task_id],
                default=-1
            )
            levels[task_id] = max_prev_level + 1
            
            for dependent_id in graph[task_id]:
                queue.append(dependent_id)
        
        depth = max(levels.values()) if levels else 0
        
        # Compute width (max parallel tasks at any level)
        level_counts: Dict[int, int] = {}
        for level in levels.values():
            level_counts[level] = level_counts.get(level, 0) + 1
        width = max(level_counts.values()) if level_counts else 0
        
        return {
            "depth": depth,
            "width": width,
            "total_tasks": len(tasks),
            "total_dependencies": len(dependencies),
        }


class AmbiguityDetector:
    """Detects ambiguities in task decomposition."""
    
    VAGUE_TERMS = {
        "some", "several", "many", "various", "different",
        "etc", "et cetera", "and so on", "and so forth",
        "maybe", "perhaps", "sort of", "kind of",
        "somehow", "someway", "apparently"
    }
    
    UNCLEAR_PRONOUNS = {
        "it", "this", "that", "these", "those",
        "he", "she", "they", "them"
    }
    
    @staticmethod
    def detect_missing_information(
        query: str,
        tasks: List[Task]
    ) -> List[str]:
        """
        Detect missing information that might affect decomposition.
        
        Returns list of missing info indicators.
        """
        missing = []
        
        # Check for temporal info
        temporal_words = ["when", "after", "before", "during", "last", "next"]
        if not any(word in query.lower() for word in temporal_words):
            if any("schedule" in t.description.lower() or "time" in t.description.lower()
                   for t in tasks):
                missing.append("No temporal information (when should this happen?)")
        
        # Check for scope/boundaries
        scope_words = ["all", "each", "every", "within", "between", "from", "to"]
        if not any(word in query.lower() for word in scope_words):
            if any("filter" in t.description.lower() or "range" in t.description.lower()
                   for t in tasks):
                missing.append("No scope/boundaries defined")
        
        # Check for constraints
        constraint_words = ["must", "must not", "should", "cannot", "limit", "maximum", "minimum"]
        if not any(word in query.lower() for word in constraint_words):
            missing.append("No explicit constraints mentioned")
        
        # Check for prioritization
        priority_words = ["first", "most important", "urgent", "critical"]
        if not any(word in query.lower() for word in priority_words):
            missing.append("No priority/importance indicated")
        
        return missing
    
    @staticmethod
    def detect_vague_language(text: str) -> List[Tuple[str, str]]:
        """
        Detect vague language in text.
        
        Returns list of (vague_term, context).
        """
        vague_words = []
        words = text.lower().split()
        
        for i, word in enumerate(words):
            # Check if word is vague
            if word in AmbiguityDetector.VAGUE_TERMS:
                context_start = max(0, i - 2)
                context_end = min(len(words), i + 3)
                context = " ".join(words[context_start:context_end])
                vague_words.append((word, context))
        
        return vague_words
    
    @staticmethod
    def detect_ambiguities_in_graph(
        query: str,
        tasks: List[Task],
        dependencies: List[TaskDependency]
    ) -> List[AmbiguityIndicator]:
        """
        Detect all ambiguities in decomposition.
        
        Checks for:
        - Missing information
        - Vague language
        - Circular dependencies
        - Unclear task definitions
        - Over/under decomposition
        """
        ambiguities: List[AmbiguityIndicator] = []
        
        # Check for cycles (circular dependencies)
        if DAGValidator.has_cycles(tasks, dependencies):
            ambiguities.append(
                AmbiguityIndicator(
                    ambiguity_type=AmbiguityType.CIRCULAR_DEPENDENCY,
                    location="task_graph",
                    description="Circular dependencies detected in task graph",
                    severity=1.0,
                    suggested_clarification="Reorder tasks to break cycle"
                )
            )
        
        # Check for vague language in query
        vague_terms = AmbiguityDetector.detect_vague_language(query)
        for vague_term, context in vague_terms:
            ambiguities.append(
                AmbiguityIndicator(
                    ambiguity_type=AmbiguityType.UNDEFINED_TERM,
                    location="query",
                    description=f"Vague term '{vague_term}' in context: {context}",
                    severity=0.5,
                    suggested_clarification=f"Clarify what '{vague_term}' means"
                )
            )
        
        # Check for missing information
        missing_info = AmbiguityDetector.detect_missing_information(query, tasks)
        for missing in missing_info:
            ambiguities.append(
                AmbiguityIndicator(
                    ambiguity_type=AmbiguityType.MISSING_INFO,
                    location="query",
                    description=missing,
                    severity=0.6,
                    suggested_clarification=missing.replace("No ", "Provide ") + " information"
                )
            )
        
        # Check for over-decomposition (too many tiny tasks)
        if len(tasks) > 20:
            ambiguities.append(
                AmbiguityIndicator(
                    ambiguity_type=AmbiguityType.OVER_DECOMPOSED,
                    location="task_graph",
                    description=f"Many tasks ({len(tasks)}) - might be over-decomposed",
                    severity=0.3,
                    suggested_clarification="Consider combining similar tasks"
                )
            )
        
        # Check for under-decomposition (task descriptions too complex)
        for task in tasks:
            if len(task.description.split()) > 20:
                ambiguities.append(
                    AmbiguityIndicator(
                        ambiguity_type=AmbiguityType.UNDER_DECOMPOSED,
                        location=f"task_{task.id}",
                        description=f"Task description is very complex: {task.description[:50]}...",
                        severity=0.4,
                        suggested_clarification="Break this task into smaller subtasks"
                    )
                )
        
        # Check for unclear task descriptions
        unclear_markers = ["and", "or", "etc", "such as"]
        for task in tasks:
            if any(marker in task.description.lower() for marker in unclear_markers):
                ambiguities.append(
                    AmbiguityIndicator(
                        ambiguity_type=AmbiguityType.MULTIPLE_INTERPRETATIONS,
                        location=f"task_{task.id}",
                        description=f"Task can be interpreted multiple ways: {task.description}",
                        severity=0.5,
                        suggested_clarification="Clarify exactly what this task should do"
                    )
                )
        
        return ambiguities


class QueryParser:
    """Parses natural language queries into tasks."""
    
    # Keyword to task type mapping
    ACTION_TO_TASK_TYPE = {
        "search": TaskType.SEARCH,
        "find": TaskType.SEARCH,
        "look for": TaskType.SEARCH,
        "retrieve": TaskType.RETRIEVE,
        "fetch": TaskType.FETCH,
        "get": TaskType.RETRIEVE,
        "analyze": TaskType.ANALYZE,
        "examine": TaskType.ANALYZE,
        "study": TaskType.ANALYZE,
        "investigate": TaskType.ANALYZE,
        "aggregate": TaskType.AGGREGATE,
        "combine": TaskType.AGGREGATE,
        "merge": TaskType.AGGREGATE,
        "summarize": TaskType.SUMMARIZE,
        "sum up": TaskType.SUMMARIZE,
        "review": TaskType.SUMMARIZE,
        "generate": TaskType.GENERATE,
        "create": TaskType.GENERATE,
        "write": TaskType.GENERATE,
        "produce": TaskType.GENERATE,
        "reason": TaskType.REASON,
        "think about": TaskType.REASON,
        "figure out": TaskType.REASON,
        "validate": TaskType.VALIDATE,
        "check": TaskType.CHECK,
        "verify": TaskType.VERIFY,
        "transform": TaskType.TRANSFORM,
        "convert": TaskType.TRANSFORM,
        "synthesize": TaskType.SYNTHESIZE,
        "evaluate": TaskType.EVALUATE,
        "assess": TaskType.EVALUATE,
        "rate": TaskType.EVALUATE,
        "plan": TaskType.PLAN,
        "filter": TaskType.FILTER,
    }
    
    @staticmethod
    def parse_simple_query(query: str) -> List[Task]:
        """
        Parse simple queries into tasks using keyword matching.
        
        Returns list of tasks.
        
        Examples:
        - "Search for AI papers" → [Task(SEARCH, "Search for AI papers")]
        - "Analyze sentiment and summarize" → [Task(ANALYZE), Task(SUMMARIZE)]
        - "Search for A and search for B and search for C" → [Task(SEARCH), Task(SEARCH), Task(SEARCH)]
        """
        tasks: List[Task] = []
        normalized_query = re.sub(r"\s+", " ", query.strip())

        # Find all action occurrences and preserve order by position.
        candidates: List[Tuple[int, int, str, TaskType]] = []
        for action_keyword, task_type in QueryParser.ACTION_TO_TASK_TYPE.items():
            pattern = re.compile(r"\b" + re.escape(action_keyword) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(normalized_query):
                candidates.append((match.start(), match.end(), action_keyword, task_type))

        # Sort by position, and prefer longer keyword on exact start collision.
        candidates.sort(key=lambda x: (x[0], -(x[1] - x[0])))

        filtered: List[Tuple[int, int, str, TaskType]] = []
        last_end = -1
        for candidate in candidates:
            start, end, action_keyword, task_type = candidate
            if start < last_end:
                continue
            filtered.append((start, end, action_keyword, task_type))
            last_end = end

        for index, (start, end, action_keyword, task_type) in enumerate(filtered):
            next_start = filtered[index + 1][0] if index + 1 < len(filtered) else len(normalized_query)
            after_action = normalized_query[end:next_start].strip(" ,.;:-")
            after_action = re.sub(r"^(and|to|for)\s+", "", after_action, flags=re.IGNORECASE).strip()

            description = f"{action_keyword.title()} {after_action}".strip()
            if not after_action:
                description = action_keyword.title()

            task = Task(
                type=task_type,
                description=description,
                input_description="Query results from previous task",
                expected_output=f"Results of {action_keyword}ing",
                reasoning=f"Query contains '{action_keyword}' action",
            )

            if not any(t.description == task.description and t.type == task.type for t in tasks):
                tasks.append(task)
        
        # If no tasks found, create generic one
        if not tasks:
            tasks.append(
                Task(
                    type=TaskType.UNKNOWN,
                    description=query,
                    input_description="User query",
                    expected_output="Results matching query",
                    reasoning="Could not parse specific task type",
                    confidence_score=0.3,
                )
            )
        
        return tasks
    
    @staticmethod
    def infer_dependencies(tasks: List[Task], query: str) -> List[TaskDependency]:
        """
        Infer dependencies between tasks.
        
        Heuristics:
        - SEARCH before ANALYZE (get data first)
        - ANALYZE before AGGREGATE (process before combining)
        - AGGREGATE before SUMMARIZE (combine before summing)
        - Basic topological dependencies
        """
        dependencies: List[TaskDependency] = []
        
        # Build a simple dependency structure
        # Rule 1: SEARCH should come before most other tasks
        search_tasks = [t for t in tasks if t.type == TaskType.SEARCH]
        other_tasks = [t for t in tasks if t.type != TaskType.SEARCH]
        
        for other_task in other_tasks:
            for search_task in search_tasks:
                # Search often feeds into analysis
                if other_task.type in [
                    TaskType.ANALYZE, TaskType.AGGREGATE,
                    TaskType.SYNTHESIZE, TaskType.EVALUATE
                ]:
                    dep = TaskDependency(
                        dependent_task_id=other_task.id,
                        dependency_task_id=search_task.id,
                        dependency_type="REQUIRES"
                    )
                    if dep not in dependencies:
                        dependencies.append(dep)
        
        # Rule 2: ANALYZE before AGGREGATE/SUMMARIZE
        analyze_tasks = [t for t in tasks if t.type == TaskType.ANALYZE]
        combine_tasks = [
            t for t in tasks
            if t.type in [TaskType.AGGREGATE, TaskType.SYNTHESIZE]
        ]
        
        for combine_task in combine_tasks:
            for analyze_task in analyze_tasks:
                dep = TaskDependency(
                    dependent_task_id=combine_task.id,
                    dependency_task_id=analyze_task.id,
                    dependency_type="REQUIRES"
                )
                if dep not in dependencies:
                    dependencies.append(dep)
        
        # Rule 3: Aggregate/Synthesize before Summarize
        agg_syn_tasks = [
            t for t in tasks
            if t.type in [TaskType.AGGREGATE, TaskType.SYNTHESIZE]
        ]
        summarize_tasks = [t for t in tasks if t.type == TaskType.SUMMARIZE]
        
        for summarize_task in summarize_tasks:
            for agg_task in agg_syn_tasks:
                dep = TaskDependency(
                    dependent_task_id=summarize_task.id,
                    dependency_task_id=agg_task.id,
                    dependency_type="REQUIRES"
                )
                if dep not in dependencies:
                    dependencies.append(dep)
        
        return dependencies
    
    @staticmethod
    def build_task_graph(
        query: str,
        tasks: Optional[List[Task]] = None
    ) -> TaskGraph:
        """
        Build complete task graph from query.
        
        Steps:
        1. Parse query into tasks
        2. Infer dependencies
        3. Validate (check for cycles)
        4. Compute metrics
        5. Return graph
        """
        from uuid import uuid4
        
        if tasks is None:
            tasks = QueryParser.parse_simple_query(query)
        
        # Infer dependencies
        dependencies = QueryParser.infer_dependencies(tasks, query)
        
        # Check validity
        has_cycles = DAGValidator.has_cycles(tasks, dependencies)
        sorted_order, is_valid = DAGValidator.topological_sort(tasks, dependencies)
        
        # Compute metrics
        metrics = DAGValidator.compute_graph_metrics(tasks, dependencies)
        
        # Compute confidence
        confidence = 1.0 - (len([a for a in AmbiguityDetector.detect_ambiguities_in_graph(
            query, tasks, dependencies
        ) if a.severity > 0.5]) * 0.1)
        confidence = max(0.1, min(1.0, confidence))
        
        # Build graph
        graph = TaskGraph(
            conversation_id=uuid4(),
            original_query=query,
            tasks=tasks,
            dependencies=dependencies,
            is_valid=is_valid,
            execution_order=sorted_order,
            has_cycles=has_cycles,
            total_tasks=metrics["total_tasks"],
            total_dependencies=metrics["total_dependencies"],
            depth=metrics["depth"],
            width=metrics["width"],
        )
        
        return graph
