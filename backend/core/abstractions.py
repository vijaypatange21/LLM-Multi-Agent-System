"""
Core abstractions and base classes for the multi-agent system.

This module defines the interfaces that all agents, tools, and orchestrators
must implement. These abstractions enable:
- Polymorphism: Different agent implementations can be swapped
- Extensibility: New agents/tools can be added without core changes
- Testing: Mocks can implement these interfaces
- Type safety: Type hints for better IDE support and error detection
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..schemas import (
    AgentMessage,
    ExecutionTrace,
    SharedContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


class BaseTool(ABC):
    """
    Abstract base class for all tools.
    
    WHY: Tools are the mechanism by which agents interact with the external
    world. By standardizing the interface, we enable:
    - Runtime tool discovery (agents find available tools dynamically)
    - Automatic validation (tool calls are checked against definitions)
    - Consistent error handling
    - Monitoring and cost tracking
    
    Design principles:
    - Stateless: Tools don't store state between calls
    - Idempotent: If possible, same inputs = same outputs
    - Async-first: All I/O is async (network, database, etc.)
    - Failure modes: Tools can fail; the orchestrator handles retries/fallback
    """
    
    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """
        Return this tool's static definition/schema.
        
        WHY: Agents use this to understand what arguments to pass and what
        output to expect. Definitions are immutable and discoverable at runtime.
        
        Returns:
            ToolDefinition: Schema and metadata for this tool
        """
        pass
    
    @abstractmethod
    async def execute(
        self,
        tool_call: ToolCall,
        context: SharedContext,
    ) -> ToolResult:
        """
        Execute this tool with the given arguments.
        
        WHY: This is where the tool actually does work. The orchestrator
        invokes this after validating the ToolCall against the schema.
        
        Args:
            tool_call: The invocation (arguments, trace info, etc.)
            context: Shared context (facts, constraints, resources)
        
        Returns:
            ToolResult: Outcome (success/failure, output, execution metadata)
        """
        pass


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    
    WHY: Agents are the "thinking" entities. They:
    - Make decisions based on context
    - Invoke tools to gather information or take action
    - Reason through multi-step problems
    - Communicate with users and other agents
    
    By defining a common interface, we enable:
    - Orchestrators to manage agents uniformly
    - Easy testing (mock agents for testing orchestrators)
    - Composition (agents can delegate to other agents)
    - Monitoring (track execution across all agents)
    
    Design principles:
    - Stateless: Agents don't maintain state across invocations
      (state lives in SharedContext and ExecutionTrace)
    - Message-based: Communication happens via AgentMessage
    - Async: All I/O is async (LLM calls, tool invocations, etc.)
    - Introspectable: Agents expose their capabilities and constraints
    """
    
    @property
    @abstractmethod
    def agent_id(self) -> str:
        """
        Unique identifier for this agent.
        
        WHY: Used for logging, monitoring, and agent discovery.
        """
        pass
    
    @property
    @abstractmethod
    def agent_version(self) -> str:
        """
        Semantic version of this agent.
        
        WHY: Agent behavior can change across versions (prompt updates,
        model upgrades, etc.). Version enables reproducibility and rollback.
        """
        pass
    
    @abstractmethod
    def get_available_tools(self) -> List[ToolDefinition]:
        """
        List all tools this agent can use.
        
        WHY: Enables dynamic tool discovery. The orchestrator queries this
        at runtime to understand what tools to make available to the agent.
        """
        pass
    
    @abstractmethod
    async def process_message(
        self,
        message: AgentMessage,
        context: SharedContext,
    ) -> ExecutionTrace:
        """
        Process an incoming message and produce an execution trace.
        
        WHY: This is the core agent logic. Given a message and context,
        the agent reasons through the problem and produces a trace of
        its decisions/actions.
        
        Args:
            message: Input message (user query, tool result, etc.)
            context: Shared context (facts, constraints, resources)
        
        Returns:
            ExecutionTrace: Complete record of the agent's reasoning and actions
        
        Implementation notes:
        - The agent should make tool calls by adding them to the trace
        - The orchestrator will execute those tools and provide results
        - The agent may be called again with tool results for continued reasoning
        """
        pass
    
    @abstractmethod
    async def validate_tool_call(self, tool_call: ToolCall) -> bool:
        """
        Check if a tool call is valid (does it match the tool's schema?).
        
        WHY: Agents might invoke tools incorrectly. This early validation
        prevents wasted execution and provides better error messages.
        
        Args:
            tool_call: The proposed tool call
        
        Returns:
            True if valid, False otherwise
        """
        pass


class ContextManager(ABC):
    """
    Abstract base class for managing shared context.
    
    WHY: Shared context must be stored durably and accessed consistently
    across multiple agents and workers. The context manager abstracts
    the storage layer, enabling:
    - Transactional updates (atomic context changes)
    - Versioning (track context evolution)
    - Concurrency control (prevent race conditions)
    - Audit trails (who changed what, when?)
    - Caching (reduce database queries)
    
    Design principles:
    - Versioned: Each context version is immutable
    - Transactional: Changes are atomic (all-or-nothing)
    - Observable: Changes trigger events for monitoring
    """
    
    @abstractmethod
    async def get_context(
        self,
        conversation_id: UUID,
    ) -> SharedContext:
        """
        Retrieve current shared context for a conversation.
        
        Args:
            conversation_id: Which conversation's context to fetch
        
        Returns:
            SharedContext: Current state
        """
        pass
    
    @abstractmethod
    async def update_context(
        self,
        context: SharedContext,
    ) -> SharedContext:
        """
        Update (or create) shared context.
        
        WHY: Context updates are transactional. This ensures all agents
        see a consistent world view.
        
        Args:
            context: Updated context
        
        Returns:
            SharedContext: The saved context (may have been modified by storage layer)
        
        Raises:
            Exception: If context version conflicts (concurrent update)
        """
        pass
    
    @abstractmethod
    async def get_context_history(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> List[SharedContext]:
        """
        Retrieve historical versions of context.
        
        WHY: For debugging and analysis. We want to see how context evolved.
        
        Args:
            conversation_id: Which conversation
            limit: Max versions to return
        
        Returns:
            List of SharedContext objects, ordered by recency
        """
        pass


class Orchestrator(ABC):
    """
    Abstract orchestrator for managing multi-agent workflows.
    
    WHY: The orchestrator is the conductor. It:
    - Routes messages to appropriate agents
    - Manages tool execution
    - Tracks execution across multiple agents
    - Handles errors and retries
    - Enforces constraints and budgets
    
    By defining the interface, we enable:
    - Different orchestration strategies (sequential, parallel, hierarchical)
    - Testing (mock orchestrators for testing agents)
    - Extension (custom routing logic, novel scheduling strategies)
    
    Design principles:
    - Message-driven: Communication is asynchronous message-passing
    - Stateless: State lives in databases/queues
    - Observable: All decisions are logged and traced
    - Fault-tolerant: Can recover from worker failures
    """
    
    @abstractmethod
    async def execute(
        self,
        conversation_id: UUID,
        initial_message: AgentMessage,
        agents: List[BaseAgent],
    ) -> ExecutionTrace:
        """
        Execute a multi-agent workflow.
        
        WHY: This is the main orchestration logic. Given agents and
        an initial message, execute the workflow to completion.
        
        Args:
            conversation_id: Which conversation this belongs to
            initial_message: Starting message (usually from user)
            agents: Available agents to route to
        
        Returns:
            ExecutionTrace: Complete workflow execution record
        
        Implementation notes:
        - Should handle agent delegation (one agent calls another)
        - Should execute tools and provide results back to agents
        - Should enforce constraints from SharedContext
        - Should track total cost/tokens for budget enforcement
        """
        pass
    
    @abstractmethod
    async def route_message(
        self,
        message: AgentMessage,
        agents: List[BaseAgent],
    ) -> BaseAgent:
        """
        Decide which agent should process a message.
        
        WHY: In multi-agent systems, messages might need to go to
        different agents (routing logic). This abstraction enables
        different strategies:
        - Round-robin
        - Load-based
        - Capability-based (agent matches message type)
        - ML-based (learned routing)
        
        Args:
            message: The message to route
            agents: Available agents
        
        Returns:
            BaseAgent: Which agent should process this
        """
        pass
    
    @abstractmethod
    async def execute_tool(
        self,
        tool_call: ToolCall,
        tools: List[BaseTool],
        context: SharedContext,
    ) -> ToolResult:
        """
        Execute a tool call and return the result.
        
        WHY: This centralizes tool execution, enabling:
        - Validation before execution
        - Cost tracking and budget enforcement
        - Retry logic
        - Monitoring and observability
        
        Args:
            tool_call: What tool to invoke
            tools: Available tools
            context: Shared context
        
        Returns:
            ToolResult: Tool output
        """
        pass
