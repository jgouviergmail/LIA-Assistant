"""
Psyche domain — Dynamic psychological state engine for the AI assistant.

Provides a multi-layered emotional and personality system:
- Big Five personality traits with PAD mood space
- Discrete emotions with temporal decay
- Relationship tracking (4 stages)
- Self-efficacy per domain (Bayesian updates)
- Expression profile compilation for prompt injection

Components:
- models: SQLAlchemy models (PsycheState, PsycheHistory)
- engine: Pure computation engine (stateless, no DB/LLM)
- repository: Data access layer
- service: Business logic (orchestration, cache, persistence)
- router: FastAPI endpoints
- schemas: Pydantic request/response schemas
- constants: Domain constants (emotions, stages, PAD vectors)

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""
