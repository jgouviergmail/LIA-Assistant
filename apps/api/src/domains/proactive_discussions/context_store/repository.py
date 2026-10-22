"""Public repository facade; short database operations do not call sources or models."""

from src.domains.proactive_discussions.context_store.updater import ContextUpdater


class ContextRepository(ContextUpdater):
    """Owner-scoped read, control and atomic generation publication interface."""
