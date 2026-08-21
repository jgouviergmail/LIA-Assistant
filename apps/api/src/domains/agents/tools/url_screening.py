"""Shared Web Risk gate for URL-consuming tools (lot D, 2026-08).

One implementation for every tool that is about to load an external URL
(web_fetch, browser navigation): a flagged URL yields a localized failure
output, anything else lets the caller proceed. Fail-open by design — the
screening being disabled or unavailable never blocks browsing.
"""

from typing import Any

import structlog

from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.security.web_risk import check_url_threat

logger = structlog.get_logger(__name__)


async def web_risk_gate(url: str, runtime: Any) -> UnifiedToolOutput | None:
    """Return a localized failure when Web Risk flags the URL (None = proceed).

    Args:
        url: Absolute URL about to be fetched or browsed.
        runtime: Tool runtime (used to resolve the user's language).

    Returns:
        A failure UnifiedToolOutput when the URL is flagged, None otherwise.
    """
    verdict = await check_url_threat(url)
    if not verdict.blocked:
        return None

    from src.core.i18n import normalize_language
    from src.core.i18n_api_messages import APIMessages
    from src.domains.agents.tools.runtime_helpers import get_user_language_safe

    language = normalize_language(await get_user_language_safe(runtime))
    # Threat types only — never the URL at warning level (may embed tokens/PII).
    logger.warning("web_risk_url_blocked", threat_types=list(verdict.threat_types))
    return UnifiedToolOutput.failure(
        message=APIMessages.unsafe_url_blocked(language),
        error_code="FORBIDDEN",
        metadata={"threat_types": list(verdict.threat_types)},
    )
