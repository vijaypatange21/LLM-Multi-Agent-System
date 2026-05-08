"""
Server-Sent Events (SSE) streaming module.

Architecture Overview:
This module enables real-time streaming of agent execution updates to
connected clients. Users see agent progress in real-time.

Why streaming?
- User experience: see results as they arrive (not wait for completion)
- Transparency: understand what agent is doing
- Responsiveness: feel like natural conversation
- Interactivity: user can interrupt/redirect if needed

Streaming Architecture:

1. Client (Browser)
   - Opens EventSource connection to /api/stream/{conversation_id}
   - Receives SSE events
   - Updates UI in real-time

2. API Server (FastAPI)
   - Accepts streaming connection
   - Subscribes to Redis pub/sub for conversation
   - Yields SSE events to client
   - Handles disconnection gracefully

3. Workers (Agent/Tool executors)
   - Perform work
   - Publish updates to Redis: channel="stream:{conversation_id}"
   - Updates are queued for all subscribers

Event types:

1. ExecutionStarted
   {
     "type": "execution_started",
     "agent_id": "search_agent",
     "timestamp": "2026-05-09T10:00:00Z"
   }

2. ExecutionStep
   {
     "type": "execution_step",
     "step_type": "tool_call",
     "step_number": 1,
     "description": "Calling web_search with query: climate change",
     "timestamp": "2026-05-09T10:00:01Z"
   }

3. ToolInvoked
   {
     "type": "tool_invoked",
     "tool_id": "web_search",
     "arguments": {"query": "climate change", "num_results": 10},
     "timestamp": "2026-05-09T10:00:02Z"
   }

4. ToolResult
   {
     "type": "tool_result",
     "tool_id": "web_search",
     "status": "success",
     "result_summary": "Found 10 articles about climate change",
     "timestamp": "2026-05-09T10:00:05Z"
   }

5. TokenUsage
   {
     "type": "token_usage",
     "prompt_tokens": 150,
     "completion_tokens": 87,
     "total_tokens": 237,
     "timestamp": "2026-05-09T10:00:06Z"
   }

6. ExecutionCompleted
   {
     "type": "execution_completed",
     "status": "success",
     "final_output": {...},
     "total_duration_ms": 6000,
     "total_cost": 0.15,
     "timestamp": "2026-05-09T10:00:06Z"
   }

7. Error
   {
     "type": "error",
     "error_message": "Tool timeout after 30 seconds",
     "agent_id": "search_agent",
     "timestamp": "2026-05-09T10:00:35Z"
   }

Implementation details:

Connection management:
- Keep-alive heartbeats every 30 seconds (keep connection alive through proxies)
- Timeout disconnection if client not reading (prevent resource leak)
- Graceful shutdown (send final event before closing)

Redis pub/sub pattern:
- Channel: "stream:{conversation_id}"
- Workers publish events
- API subscribes on behalf of each connected client
- Redis persistence: events not persisted (fire-and-forget)

Error handling:
- Client disconnects: stop publishing, clean up
- Worker crashes: partial trace in database, client gets error event
- Network error: client reconnects, queries database for state

Backpressure:
- If many clients connected, don't overwhelm them
- Batch events if needed
- Drop non-critical events if rate-limited

Security:
- Authenticate before subscribing (check user owns conversation)
- Filter events by user permissions
- Rate-limit streaming to prevent abuse

Performance:
- Async I/O (don't block request threads)
- Redis pub/sub (efficient fan-out)
- Event compression (gzip if large)
- Connection pooling (reuse connections)

No implementations yet - only architecture and event definitions.
"""
