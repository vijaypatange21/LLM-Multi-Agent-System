"""
Docker and container orchestration module.

Architecture Overview:
This directory contains Dockerfiles and docker-compose configuration for
containerizing the multi-agent system. Containerization enables:
- Reproducible environments (same in dev, test, prod)
- Isolation (services don't interfere)
- Scalability (orchestrators like Kubernetes manage containers)
- DevOps automation (CI/CD pipelines)

Services:

1. API Service
   - FastAPI application
   - Handles REST requests
   - Streams SSE responses
   - Stateless (scale horizontally)
   - Dependencies: PostgreSQL, Redis

2. AgentWorker Service
   - Processes agent tasks
   - Scales based on queue depth
   - Dependencies: PostgreSQL, Redis, LLM APIs

3. ToolWorker Service
   - Executes tools
   - May have external dependencies (APIs, databases)
   - Resource-intensive (may need GPU)
   - Dependencies: PostgreSQL, Redis

4. EvalWorker Service
   - Runs evaluations
   - Compute-intensive
   - Scales independently
   - Dependencies: PostgreSQL, Redis

5. PostgreSQL
   - Data persistence
   - Volume mount for data
   - Environment variables for config

6. Redis
   - Message queue
   - Session cache
   - Pub/Sub
   - Volume mount for persistence

7. Nginx (reverse proxy)
   - Load balancing
   - SSL/TLS termination
   - Static file serving
   - Rate limiting

Docker image structure:

Base image:
- python:3.11-slim
- Lightweight, security-focused
- Alpine considered but may lack system deps

Layers:
1. System dependencies
   - apt-get update/install
   - Minimal tooling

2. Python dependencies
   - COPY requirements.txt
   - pip install
   - Large layer, cached

3. Application code
   - COPY backend/
   - Frequently changed, invalidates cache

4. Entrypoint
   - ENTRYPOINT with health checks
   - Signal handling (SIGTERM)

Multi-stage builds:
- Build stage: compile/prepare
- Runtime stage: minimal runtime image
- Reduces final image size

Docker Compose (development):

Services:
- api: main application
- postgres: database
- redis: message queue
- agent_worker: agent processing
- tool_worker: tool execution

Networking:
- All services on same network
- Service discovery via DNS (service name)
- Expose API on port 8000

Volumes:
- Database persistence
- Redis persistence (optional)
- Code volume for development (live reload)

Environment:
- DATABASE_URL: postgresql://postgres:password@postgres:5432/app
- REDIS_URL: redis://redis:6379/0
- LOG_LEVEL: DEBUG (for development)

Health checks:
- API: curl /health
- Database: pg_isready
- Redis: redis-cli ping

Production considerations:

Image optimization:
- Minimize layer size
- Remove build artifacts
- Scan for vulnerabilities
- Sign images

Registry:
- Push to private registry
- Version tags (v1.0.0, latest)
- Image metadata (labels, annotations)

Orchestration:
- Kubernetes or Docker Swarm
- Auto-scaling based on metrics
- Rolling updates
- Resource limits

Security:
- Run as non-root user
- Read-only root filesystem (where possible)
- No secrets in images
- Network policies (restrict traffic)
- Pod security policies

Monitoring:
- Container logs
- Resource usage (CPU, memory)
- Health checks
- Service mesh (Istio, Linkerd) for observability

No implementations yet - only architecture and structure.
"""
