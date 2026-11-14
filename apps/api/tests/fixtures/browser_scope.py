"""Explicit stable browser identities for session lifecycle and Redis tests."""

from uuid import NAMESPACE_URL, uuid4, uuid5

from src.core.browser_scope import BrowserScope


def browser_scope(label: str | None = None) -> BrowserScope:
    """A historical Main scope; named fixtures keep stable UUIDs across calls."""
    owner = uuid4() if label is None else uuid5(NAMESPACE_URL, f"lia-test-browser:{label}")
    return BrowserScope(owner, owner)
