"""
Agent Middleware.

Custom middleware implementations for LangGraph agents (LangChain v1.0).
Provides extensible hooks for managing message history, validation, and more.
"""

from src.domains.agents.middleware.message_history import MessageHistoryMiddleware

__all__ = ["MessageHistoryMiddleware"]
