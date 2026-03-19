"""
SQLAlchemy model registry.

Imports all domain models to ensure SQLAlchemy mappers are configured
before any database operation. Required for standalone scripts that
don't go through FastAPI app startup (which loads models via routes).

Usage:
    from src.infrastructure.database.registry import import_all_models
    import_all_models()
"""

_models_imported = False


def import_all_models() -> None:
    """Import all SQLAlchemy domain models to register mappers.

    Idempotent: safe to call multiple times.
    """
    global _models_imported
    if _models_imported:
        return

    import src.domains.attachments.models  # noqa: F401
    import src.domains.auth.models  # noqa: F401
    import src.domains.channels.models  # noqa: F401
    import src.domains.connectors.models  # noqa: F401
    import src.domains.conversations.models  # noqa: F401
    import src.domains.google_api.models  # noqa: F401
    import src.domains.heartbeat.models  # noqa: F401
    import src.domains.interests.models  # noqa: F401
    import src.domains.llm_config.models  # noqa: F401
    import src.domains.notifications.models  # noqa: F401
    import src.domains.personalities.models  # noqa: F401
    import src.domains.rag_spaces.models  # noqa: F401
    import src.domains.reminders.models  # noqa: F401
    import src.domains.scheduled_actions.models  # noqa: F401
    import src.domains.skills.models  # noqa: F401
    import src.domains.sub_agents.models  # noqa: F401
    import src.domains.system_settings.models  # noqa: F401
    import src.domains.user_mcp.models  # noqa: F401
    import src.domains.users.models  # noqa: F401

    _models_imported = True
