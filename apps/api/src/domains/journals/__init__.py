"""
Journals domain — Personal assistant logbooks.

Provides thematic journals where the AI assistant records its own reflections,
observations, analyses and learnings. These notes are written from the assistant's
perspective, colored by its active personality, and influence future responses.

Components:
- models: SQLAlchemy models (JournalEntry + enums)
- schemas: Pydantic request/response schemas
- repository: Data access layer with semantic search
- service: Business logic (CRUD + embedding generation)
- router: FastAPI endpoints
- extraction_service: Background post-conversation extraction
- consolidation_service: Periodic journal maintenance
- context_builder: Prompt injection via semantic relevance
"""
