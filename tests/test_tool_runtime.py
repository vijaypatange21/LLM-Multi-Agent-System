"""Tests for the tool runtime, validators, and standard stub tools."""

import asyncio
from uuid import uuid4

import pytest

from backend.core import BaseTool
from backend.schemas import (
    ContextMetadata,
    MessageRole,
    SharedContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
    ToolType,
)
from backend.tools import (
    InMemoryToolExecutionStore,
    RetryManager,
    ToolExecutor,
    ToolRegistry,
    ToolResultValidator,
    WebSearchStubTool,
    PythonSandboxExecutor,
    NLToSQLDatabaseTool,
    SelfReflectionTool,
)


def _context() -> SharedContext:
    return SharedContext(
        conversation_id=uuid4(),
        user_intent="test tool runtime",
        metadata=ContextMetadata(last_modified_by="test"),
    )


def _tool_call(tool_id: str, arguments: dict, trace_id=None, agent_id: str = "agent_1") -> ToolCall:
    return ToolCall(
        id=uuid4(),
        tool_id=tool_id,
        tool_version="1.0.0",
        arguments=arguments,
        execution_trace_id=trace_id or uuid4(),
        agent_id=agent_id,
    )


class FlakyTool(BaseTool):
    def __init__(self, *, tool_id: str, fail_times: int, timeout_seconds: int = 1, fallback_tool_ids=None):
        self.fail_times = fail_times
        self.calls = 0
        self._definition = ToolDefinition(
            id=tool_id,
            name=tool_id,
            description="flaky test tool",
            version="1.0.0",
            tool_type=ToolType.COMPUTE,
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
            },
            output_schema={
                "type": "object",
                "required": ["attempt", "value"],
                "properties": {"attempt": {"type": "integer"}, "value": {"type": "integer"}},
            },
            timeout_seconds=timeout_seconds,
            fallback_tool_ids=fallback_tool_ids or [],
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary unavailable")
        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={"attempt": self.calls, "value": tool_call.arguments["value"]},
            execution_time_ms=5.0,
            execution_metadata={"calls": self.calls},
        )


class InvalidOutputTool(BaseTool):
    def __init__(self):
        self._definition = ToolDefinition(
            id="invalid_output_tool",
            name="invalid_output_tool",
            description="returns schema-invalid output",
            version="1.0.0",
            tool_type=ToolType.COMPUTE,
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
            },
            output_schema={
                "type": "object",
                "required": ["expected"],
                "properties": {"expected": {"type": "string"}},
            },
            timeout_seconds=1,
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={"wrong": True},
            execution_time_ms=1.0,
        )


@pytest.mark.asyncio
class TestToolRuntime:
    async def test_retry_logs_each_attempt_and_returns_success(self):
        store = InMemoryToolExecutionStore()
        executor = ToolExecutor(
            tools=[FlakyTool(tool_id="flaky", fail_times=2)],
            store=store,
            retry_manager=RetryManager(max_attempts=3, base_delay_seconds=0.0, jitter=0.0),
        )
        call = _tool_call("flaky", {"value": 7})

        result = await executor.execute_tool(call, _context())
        trace = await store.get_trace(call.id)

        assert result.status == ToolResultStatus.SUCCESS
        assert result.output["attempt"] == 3
        assert trace is not None
        assert trace.total_attempts == 3
        assert len(trace.attempts) == 3
        assert trace.attempts[0].structured_log["attempt_number"] == 1
        assert trace.attempts[1].structured_log["attempt_number"] == 2
        assert trace.attempts[2].structured_log["attempt_number"] == 3

    async def test_malformed_input_is_rejected_before_execution(self):
        store = InMemoryToolExecutionStore()
        executor = ToolExecutor(
            tools=[FlakyTool(tool_id="flaky", fail_times=0)],
            store=store,
            retry_manager=RetryManager(max_attempts=3, base_delay_seconds=0.0, jitter=0.0),
        )
        call = _tool_call("flaky", {})

        result = await executor.execute_tool(call, _context())
        trace = await store.get_trace(call.id)

        assert result.status == ToolResultStatus.FAILED
        assert result.execution_metadata["accepted"] is False
        assert trace is not None
        assert trace.accepted is False
        assert trace.rejected_reason
        assert len(trace.attempts) == 1
        assert trace.attempts[0].decision.value == "rejected"

    async def test_timeout_falls_back_to_secondary_tool(self):
        primary = FlakyTool(tool_id="primary", fail_times=0, timeout_seconds=1, fallback_tool_ids=["fallback"])

        class SlowPrimaryTool(FlakyTool):
            async def execute(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
                await asyncio.sleep(1.1)
                return await super().execute(tool_call, context)

        slow_primary = SlowPrimaryTool(tool_id="primary", fail_times=0, timeout_seconds=1, fallback_tool_ids=["fallback"])
        fallback = FlakyTool(tool_id="fallback", fail_times=0, timeout_seconds=1)
        executor = ToolExecutor(
            tools=[slow_primary, fallback],
            store=InMemoryToolExecutionStore(),
            retry_manager=RetryManager(max_attempts=1, base_delay_seconds=0.0, jitter=0.0),
        )
        call = _tool_call("primary", {"value": 11})

        result = await executor.execute_tool(call, _context())
        trace = await executor.store.get_trace(call.id)

        assert result.status == ToolResultStatus.SUCCESS
        assert result.output["attempt"] == 1
        assert trace is not None
        assert len(trace.attempts) == 2
        assert trace.attempts[0].status == ToolResultStatus.TIMEOUT
        assert trace.attempts[1].structured_log["fallback_index"] == 2

    async def test_invalid_output_is_rejected(self):
        executor = ToolExecutor(
            tools=[InvalidOutputTool()],
            store=InMemoryToolExecutionStore(),
            retry_manager=RetryManager(max_attempts=1, base_delay_seconds=0.0, jitter=0.0),
        )
        call = _tool_call("invalid_output_tool", {"value": 5})

        result = await executor.execute_tool(call, _context())
        trace = await executor.store.get_trace(call.id)

        assert result.status == ToolResultStatus.FAILED
        assert "validation" in (result.error_message or "").lower()
        assert trace is not None
        assert trace.final_result_status == ToolResultStatus.FAILED

    async def test_standard_tools_smoke(self):
        registry = ToolRegistry()
        tools = [WebSearchStubTool(), PythonSandboxExecutor(), NLToSQLDatabaseTool(), SelfReflectionTool()]
        for tool in tools:
            registry.register(tool)

        assert {tool.get_definition().id for tool in registry.list()} == {
            "web_search_stub",
            "python_sandbox_executor",
            "nl_to_sql_database_tool",
            "self_reflection_tool",
        }
