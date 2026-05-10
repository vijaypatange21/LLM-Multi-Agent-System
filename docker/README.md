"""
Docker and container orchestration module.

Architecture Overview:
This directory contains the current Docker Compose stack and production Dockerfiles
for containerizing the multi-agent system. Containerization enables:
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

7. Grafana
   - Log and metrics dashboard
   - Connects to Loki for log exploration

8. Loki
   - Log aggregation backend
   - Stores application and container logs

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
- worker: background worker runtime
- postgres: database
- redis: message queue
- grafana: log viewer/dashboard
- loki: log aggregation backend

Networking:
- All services on same network
- Service discovery via DNS (service name)
- Expose API on port 8000

Volumes:
- Database persistence
- Redis persistence (optional)
- Code volume for development (live reload)

Environment:
- POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB: database credentials
- REDIS_URL: redis://redis:6379/0
- SECRET_KEY: application secret
- GRAFANA_ADMIN_PASSWORD: Grafana admin password

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

This document now matches the repository's current Docker entrypoints and compose stack.
"""
