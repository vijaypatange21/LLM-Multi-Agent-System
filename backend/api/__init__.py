"""
FastAPI REST API module.

Architecture Overview:
This module defines REST endpoints for the multi-agent system. The API
is the entry point for users/clients. It handles:
- User authentication
- Request validation
- Orchestration
- Streaming responses
- Error handling

API Endpoints:

1. Conversations
   POST /api/conversations
   - Start new conversation
   - Request: {user_id, initial_message, agent_ids?, context?}
   - Response: {conversation_id, agents, initial_context}
   
   GET /api/conversations/{conversation_id}
   - Retrieve conversation metadata
   - Response: {conversation_id, user_id, created_at, status, ...}

2. Messages
   POST /api/conversations/{conversation_id}/messages
   - Send message to agents
   - Request: {content, agent_id?}
   - Response: {message_id, received_at}
   - Triggers orchestration
   
   GET /api/conversations/{conversation_id}/messages
   - Retrieve conversation history
   - Query params: ?limit=100&offset=0
   - Response: {messages, total_count}

3. Streaming
   GET /api/conversations/{conversation_id}/stream
   - SSE stream of execution updates
   - Response: Server-sent events
   - Keep-alive heartbeats
   - Automatic reconnection support

4. ExecutionTraces
   GET /api/conversations/{conversation_id}/traces
   - List execution traces for conversation
   - Query: ?agent_id=X&status=Y
   - Response: {traces, count}
   
   GET /api/traces/{trace_id}
   - Get detailed trace with all steps
   - Response: ExecutionTrace (with steps)

5. Evaluations
   GET /api/traces/{trace_id}/evaluation
   - Get evaluation for a trace
   - Response: EvalResult (if evaluated)
   
   GET /api/evaluations?agent_id=X&date_range=...
   - Analytics: evaluation metrics over time
   - Response: {metrics, trends, comparisons}

6. Prompts
   GET /api/prompts/{prompt_id}
   - Get active prompt version
   - Response: PromptVersion
   
   GET /api/prompts/{prompt_id}/versions
   - List all versions
   - Response: [PromptVersion, ...]
   
   POST /api/prompts
   - Create new prompt version
   - Request: {prompt_id, content, config, ...}
   - Response: PromptVersion
   
   PATCH /api/prompts/{prompt_id}/activate
   - Activate specific version
   - Request: {version_number}
   - Response: PromptVersion (now active)

7. Tools
   GET /api/tools
   - List available tools
   - Query: ?agent_id=X
   - Response: [ToolDefinition, ...]
   
   GET /api/tools/{tool_id}
   - Get tool definition
   - Response: ToolDefinition

8. Context
   GET /api/conversations/{conversation_id}/context
   - Get shared context
   - Response: SharedContext
   
   PATCH /api/conversations/{conversation_id}/context
   - Update context (constraints, facts)
   - Request: {facts?, constraints?, resources?}
   - Response: SharedContext (updated)

9. Analytics
   GET /api/analytics/agents
   - Agent performance metrics
   - Response: {avg_latency, success_rate, cost, ...}
   
   GET /api/analytics/tools
   - Tool usage and performance
   - Response: {usage_count, success_rate, avg_latency, ...}
   
   GET /api/analytics/conversations
   - Conversation trends
   - Response: {total, by_status, by_date, ...}

Request/Response patterns:

Pagination:
- Query: ?limit=50&offset=100
- Response includes: total_count, next_offset
- Default limit: 50, max: 500

Filtering:
- Query: ?agent_id=X&status=Y&date_from=ISO8601&date_to=ISO8601
- Support filtering on common fields

Sorting:
- Query: ?sort_by=created_at&sort_order=desc
- Default: sort by created_at descending

Error responses:
{
  "status_code": 400,
  "error_code": "INVALID_REQUEST",
  "message": "User-friendly error message",
  "details": {
    "field": "conversation_id",
    "reason": "not found"
  }
}

Authentication:
- Bearer token in Authorization header
- Verify token against auth service
- Include user_id in all requests
- Enforce permissions (user owns conversation?)

Rate limiting:
- Per-user limits (e.g., 100 requests/minute)
- Per-endpoint limits
- Return 429 Too Many Requests if exceeded

Validation:
- Request body validation (Pydantic)
- Query parameter validation
- Return 400 Bad Request with details if invalid

Async handling:
- All endpoints are async (async def)
- Use FastAPI background tasks for heavy work
- Return immediately, work happens in background

CORS:
- Enable CORS for frontend
- Restrict to known origins
- Allow credentials for authentication

Documentation:
- Auto-generated OpenAPI (Swagger)
- Available at /docs
- Response schema examples
- Error code documentation

Performance:
- Database query optimization (indexes, selective loading)
- Caching where appropriate (Redis)
- Connection pooling
- Pagination to limit result size

Security:
- HTTPS only
- Input sanitization
- SQL injection prevention (ORM)
- XSS prevention (content type)
- CSRF protection

No implementations yet - only API design and structure.
"""
