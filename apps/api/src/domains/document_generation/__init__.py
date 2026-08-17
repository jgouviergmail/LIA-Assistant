"""Document generation bounded context (ADR-226).

Turns user instructions (plus optional source data) into downloadable
documents: a dedicated LLM slot writes structured content, pure renderers
produce the file bytes, and the attachments infrastructure stores and purges
the result. Mirrors the ``image_generation`` domain architecture.
"""
