"""Owned browser refusals; provider and page text never choose their meaning."""

from enum import Enum


class BrowserRefusalReason(Enum):
    UNHEALTHY = ("DEPENDENCY_ERROR", "Browser pool is not healthy")
    CAPACITY = ("RATE_LIMIT_EXCEEDED", "Maximum concurrent browser sessions reached")
    SESSION_MOVED = ("DEPENDENCY_ERROR", "Browser session ownership changed during allocation")
    COORDINATION_UNSUPPORTED = (
        "DEPENDENCY_ERROR",
        "Browser coordination requires Redis hash-field expiry support",
    )
    NAVIGATION_LIMIT = ("RATE_LIMIT_EXCEEDED", "Max navigations per session reached")
    BLOCKED_URL = ("INVALID_INPUT", "URL blocked by the browser security policy")
    NO_PAGE = ("DEPENDENCY_ERROR", "No page is currently open")
    MISSING_ELEMENT = ("NOT_FOUND", "The referenced element was not found on the page")
    BLOCKED_KEY = ("INVALID_INPUT", "This keyboard key is not allowed")

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class BrowserRefusal(ValueError):
    """A refusal raised by our browser layer, with a closed vocabulary."""

    def __init__(self, reason: BrowserRefusalReason) -> None:
        self.reason = reason
        super().__init__(reason.message)
