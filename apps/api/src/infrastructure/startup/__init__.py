"""Application startup and shutdown step modules (ADR-123).

Each module groups the ``src.main.lifespan`` steps of one subsystem and
exposes one typed function per *contiguous* segment of the historical
startup sequence:

- ``registries`` — eager model imports, fail-fast boot validations, tool schemas
- ``observability`` — Prometheus metrics server, Langfuse, lifetime metrics task
- ``caches`` — Redis, pricing/config caches, cross-worker invalidation (ADR-063)
- ``agents`` — checkpointer, AgentRegistry, semantic tool selector, agent graph
- ``integrations`` — MCP, Telegram, currency rates sync, system RAG indexing
- ``schedulers`` — background job registration + leader election
- ``shutdown`` — the full shutdown sequence (drain first, Redis last — ADR-117)

The lifespan in ``src/main.py`` remains the SINGLE orchestration point: it
calls these functions in the exact historical order and is the only place
where ordering is decided. Bodies were extracted verbatim — same structlog
events, same exception handling, same feature-flag guards. When adding a new
startup step, add a function to the matching module here AND a call in the
lifespan (the CLAUDE.md "Startup initialization" checklist still applies).
"""
