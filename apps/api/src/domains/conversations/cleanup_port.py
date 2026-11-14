"""Native runtime cleanup is supplied by startup, never imported by the domain."""

from src.domains.conversations.cleanup_contracts import RuntimeCleanupPort

_runtime_cleanup: RuntimeCleanupPort | None = None


def configure_runtime_cleanup(port: RuntimeCleanupPort | None) -> None:
    """Bind or withdraw the process's native cleanup implementation."""
    global _runtime_cleanup
    _runtime_cleanup = port


def runtime_cleanup() -> RuntimeCleanupPort:
    """Refuse an unconfigured worker rather than pretending native cleanup succeeded."""
    if _runtime_cleanup is None:
        raise RuntimeError("Conversation runtime cleanup was not configured at startup")
    return _runtime_cleanup
