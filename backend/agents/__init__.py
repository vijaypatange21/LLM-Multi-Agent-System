"""
Agent implementations module.

Architecture Overview:
This module contains concrete implementations of BaseAgent. Agents are the
"thinking" components of the system. They:
- Receive messages and context
- Reason about the problem
- Make decisions (including tool calls)
- Return execution traces

Common agent types (to be implemented):
1. LLMAgent: Uses an LLM (GPT-4, Claude, etc.) as the reasoning engine.
   - Reads context and message
   - Constructs a prompt
   - Calls the LLM
   - Parses LLM output for tool calls
   - Returns execution trace

2. HierarchicalAgent: Delegates to sub-agents
   - Breaks down complex tasks
   - Delegates to specialist agents
   - Aggregates results
   - Reports back to parent

3. ReasoningAgent: Multi-step reasoning with explicit planning
   - Thinks through steps before acting
   - Produces interpretable traces
   - Can be traced/debugged

4. RoutingAgent: Dispatches to other agents based on message type
   - Content-based routing
   - Maintains agent registry
   - Transparent passthrough for debugging

Extension points:
- Custom reasoning strategies (chain-of-thought, tree-of-thought, etc.)
- Different LLM backends (OpenAI, Anthropic, local models, etc.)
- Agent-specific tool filtering
- Custom message interpretation

No implementations here yet - only interface definitions and docstrings.
"""
