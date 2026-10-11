"""Compatibility imports for the shared SSRF validator and DNS-pinned transport.

The infrastructure owner is shared by web fetch and the skill library. This
facade preserves the historical DNS seam used by the agent's callers/tests.
"""

import asyncio

from src.infrastructure.utils.url_validation import (
    UrlValidationResult as UrlValidationResult,
)
from src.infrastructure.utils.url_validation import (
    _resolve_dns_sync as _resolve_dns_sync,
)
from src.infrastructure.utils.url_validation import (
    check_ip_safety as check_ip_safety,
)
from src.infrastructure.utils.url_validation import (
    pinned_request_parts as pinned_request_parts,
)
from src.infrastructure.utils.url_validation import (
    pinned_stream as pinned_stream,
)
from src.infrastructure.utils.url_validation import validate_url as _validate_url

__all__ = [
    "UrlValidationResult",
    "check_ip_safety",
    "pinned_request_parts",
    "pinned_stream",
    "validate_url",
    "asyncio",
]


async def validate_url(url: str) -> UrlValidationResult:
    return await _validate_url(url, dns_resolver=_resolve_dns_sync)
