"""Standard stub tools used by the tool runtime."""

import ast
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core import BaseTool
from ..schemas import SharedContext, ToolCall, ToolDefinition, ToolResult, ToolResultStatus, ToolType


def _tool_definition(
    tool_id: str,
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    output_schema: Dict[str, Any],
    tool_type: ToolType,
    timeout_seconds: int = 10,
) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        name=name,
        description=description,
        tool_type=tool_type,
        timeout_seconds=timeout_seconds,
        input_schema=input_schema,
        output_schema=output_schema,
    )


class WebSearchStubTool(BaseTool):
    """Deterministic web search stub that returns synthetic search results."""

    def __init__(self):
        self._definition = _tool_definition(
            tool_id="web_search_stub",
            name="Web Search Stub",
            description="Deterministic search stub for web-style lookups",
            tool_type=ToolType.SEARCH,
            timeout_seconds=5,
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["results"],
                "properties": {
                    "results": {"type": "array"},
                    "query": {"type": "string"},
                },
            },
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        query = str(tool_call.arguments.get("query", ""))
        top_k = int(tool_call.arguments.get("top_k", 3) or 3)
        normalized_query = query.lower().strip()
        seed_terms = [term for term in normalized_query.split() if term]
        results: List[Dict[str, Any]] = []
        for index in range(top_k):
            term = seed_terms[index % len(seed_terms)] if seed_terms else "topic"
            results.append(
                {
                    "title": f"Stub result for {term}",
                    "url": f"https://example.com/{term}/{index + 1}",
                    "snippet": f"Synthetic web result about {term} for query '{query}'.",
                    "rank": index + 1,
                }
            )

        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={"query": query, "results": results, "source": "stub"},
            execution_time_ms=1.0,
            execution_metadata={"tool_name": self._definition.name, "conversation_id": str(context.conversation_id)},
        )


class PythonSandboxExecutor(BaseTool):
    """Restricted Python expression evaluator used as a sandbox stub."""

    def __init__(self):
        self._definition = _tool_definition(
            tool_id="python_sandbox_executor",
            name="Python Sandbox Executor",
            description="Restricted evaluator for simple Python expressions",
            tool_type=ToolType.COMPUTE,
            timeout_seconds=3,
            input_schema={
                "type": "object",
                "required": ["expression"],
                "properties": {"expression": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["result"],
                "properties": {"result": {}, "locals": {"type": "object"}},
            },
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        expression = str(tool_call.arguments.get("expression", ""))
        result = self._safe_eval(expression)
        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={"expression": expression, "result": result, "locals": {}},
            execution_time_ms=1.0,
            execution_metadata={"tool_name": self._definition.name, "conversation_id": str(context.conversation_id)},
        )

    def _safe_eval(self, expression: str) -> Any:
        tree = ast.parse(expression, mode="eval")

        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Pow,
            ast.Mod,
            ast.USub,
            ast.UAdd,
            ast.Constant,
            ast.List,
            ast.Tuple,
            ast.Dict,
            ast.Load,
            ast.Name,
            ast.Call,
            ast.Attribute,
        )

        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise ValueError(f"Unsupported syntax: {type(node).__name__}")
            if isinstance(node, ast.Call):
                raise ValueError("Function calls are not allowed in the sandbox stub")
            if isinstance(node, ast.Name) and node.id not in {"math"}:
                raise ValueError(f"Name not allowed: {node.id}")
            if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "math"):
                raise ValueError("Only math.<fn> attribute access is allowed")

        safe_globals = {"__builtins__": {}, "math": math}
        return eval(compile(tree, filename="<sandbox>", mode="eval"), safe_globals, {})


class NLToSQLDatabaseTool(BaseTool):
    """Deterministic natural-language-to-SQL stub."""

    def __init__(self):
        self._definition = _tool_definition(
            tool_id="nl_to_sql_database_tool",
            name="NL-to-SQL Database Tool",
            description="Convert a natural language request into SQL",
            tool_type=ToolType.DATABASE,
            timeout_seconds=5,
            input_schema={
                "type": "object",
                "required": ["question"],
                "properties": {
                    "question": {"type": "string"},
                    "table_name": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["sql"],
                "properties": {
                    "sql": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        question = str(tool_call.arguments.get("question", ""))
        table_name = str(tool_call.arguments.get("table_name", "records"))
        lowered = question.lower()
        if "count" in lowered:
            sql = f"SELECT COUNT(*) AS count FROM {table_name};"
            confidence = 0.86
        elif "average" in lowered or "avg" in lowered:
            sql = f"SELECT AVG(value) AS average_value FROM {table_name};"
            confidence = 0.82
        elif "list" in lowered or "show" in lowered or "find" in lowered:
            sql = f"SELECT * FROM {table_name} LIMIT 10;"
            confidence = 0.7
        else:
            sql = f"SELECT * FROM {table_name} WHERE summary LIKE '%' || ? || '%';"
            confidence = 0.55

        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={
                "question": question,
                "table_name": table_name,
                "sql": sql,
                "confidence": confidence,
                "source": "stub",
            },
            execution_time_ms=1.0,
            execution_metadata={"tool_name": self._definition.name, "conversation_id": str(context.conversation_id)},
        )


class SelfReflectionTool(BaseTool):
    """Structured self-reflection stub for an agent's own output."""

    def __init__(self):
        self._definition = _tool_definition(
            tool_id="self_reflection_tool",
            name="Self Reflection Tool",
            description="Generate a structured self-review of a draft answer",
            tool_type=ToolType.COMPUTE,
            timeout_seconds=4,
            input_schema={
                "type": "object",
                "required": ["draft_answer"],
                "properties": {
                    "draft_answer": {"type": "string"},
                    "goal": {"type": "string"},
                    "critique": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {
                    "summary": {"type": "string"},
                    "strengths": {"type": "array"},
                    "weaknesses": {"type": "array"},
                    "next_steps": {"type": "array"},
                },
            },
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        draft_answer = str(tool_call.arguments.get("draft_answer", ""))
        critique = str(tool_call.arguments.get("critique", ""))
        goal = str(tool_call.arguments.get("goal", "improve the answer"))
        strengths = ["clear intent", "structured response"] if draft_answer else ["responds to prompt"]
        weaknesses = []
        if len(draft_answer) < 40:
            weaknesses.append("response is too terse for robust evaluation")
        if critique:
            weaknesses.append("incorporates critique feedback")
        next_steps = ["clarify assumptions", "add supporting evidence", "tighten wording"]

        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={
                "goal": goal,
                "summary": f"Reflection completed for goal: {goal}",
                "strengths": strengths,
                "weaknesses": weaknesses,
                "next_steps": next_steps,
                "draft_answer_preview": draft_answer[:120],
                "critique_preview": critique[:120],
            },
            execution_time_ms=1.0,
            execution_metadata={"tool_name": self._definition.name, "conversation_id": str(context.conversation_id)},
        )
