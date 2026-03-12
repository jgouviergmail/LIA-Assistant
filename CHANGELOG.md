# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-03-13

First public open-source release of LIA.

### Features

- **Multi-Agent Orchestration**: LangGraph-based pipeline with Router, Planner, Orchestrator, and Response nodes
- **16+ Domain Agents**: Contacts, Email, Calendar, Drive, Tasks, Weather, Wikipedia, Perplexity, Brave Search, Web Search, Web Fetch, Places, Routes, Reminders, Context, Query, and dynamic MCP agents
- **Human-in-the-Loop (HITL)**: 6 interaction types — Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review
- **Smart Planner**: LLM-based execution plan generation with dependency graphs and wave-by-wave parallel execution
- **Plan Pattern Learner**: Redis-based Bayesian learning; high-confidence patterns (>=90%) bypass semantic validation
- **Model Context Protocol (MCP)**: Admin MCP (persistent) + Per-User MCP (ephemeral) with OAuth flow support
- **MCP Apps**: Interactive HTML widgets in sandboxed iframes via PostMessage JSON-RPC bridge
- **Excalidraw Integration**: LLM-driven diagram builder with intent-based element generation
- **Skills System**: agentskills.io standard SKILL.md files with per-user toggle and deterministic bypass strategies
- **Multi-Channel Messaging**: Generic abstraction with Telegram as first implementation (webhook, OTP binding, voice)
- **Autonomous Heartbeat**: LLM-driven proactive notifications with two-phase approach (decision + personality-aware rewrite)
- **Voice Mode**: TTS (Edge/OpenAI/Gemini) + STT (Sherpa-onnx Whisper, CPU-only)
- **Multi-Provider LLM**: 6 providers (OpenAI, Anthropic, Gemini, DeepSeek, Perplexity, Ollama) with dynamic config via Admin UI
- **Multi-Provider Connectors**: Google, Apple iCloud, and Microsoft 365 with mutual exclusivity per functional category
- **Scheduled Actions**: User-scheduled deferred task execution
- **Session-based Auth (BFF)**: HTTP-only cookies in Redis, no JWT exposed to frontend
- **Enterprise Observability**: OpenTelemetry traces, Prometheus metrics, Grafana dashboards, Langfuse LLM analytics
- **Internationalization**: 6 languages (fr, en, es, de, it, zh)
- **Multi-arch Docker**: `linux/amd64` + `linux/arm64` builds for Raspberry Pi deployment
- **Comprehensive Test Suite**: 2,300+ tests (unit, integration, e2e, benchmark)

### Infrastructure

- FastAPI 0.128 backend (Python 3.12+) with async SQLAlchemy 2.0 + asyncpg
- Next.js 16 frontend (React 19, TypeScript) with TailwindCSS 4
- PostgreSQL 16 (+ pgvector) for data and vector search
- Redis 7 for sessions, cache, distributed locks, and pattern learning
- APScheduler for 9 background jobs
- Circuit breaker, rate limiting, and distributed locks
- SOPS/Age encryption for secrets management

[Unreleased]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/jgouviergmail/LIA-Assistant/releases/tag/v1.0.0
