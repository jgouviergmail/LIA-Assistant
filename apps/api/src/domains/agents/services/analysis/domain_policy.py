"""The published domain menu is the boundary for every analyzer selection."""

from collections.abc import Collection, Iterable


def retain_available_domains(
    primary_domain: str | None,
    secondary_domains: Iterable[str],
    available: Collection[str],
) -> tuple[str | None, list[str]]:
    """Unavailable names never become executable through a model's output."""
    primary = primary_domain if not primary_domain or primary_domain in available else None
    return primary, [domain for domain in secondary_domains if domain in available]
