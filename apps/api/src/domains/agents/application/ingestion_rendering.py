"""The existing health and SMS families share the exact native preview dispatcher."""

from src.domains.agents.application.health_removal import canonical_health_removal
from src.domains.agents.application.health_removal_rendering import health_removal_preview
from src.domains.agents.application.health_token_creation import canonical_health_token_creation
from src.domains.agents.application.health_token_rendering import (
    health_token_creation_preview,
    health_token_preview,
)
from src.domains.agents.application.health_token_revocation import canonical_health_token_revocation
from src.domains.agents.application.sms_rendering import SMS_CANONICAL, SMS_PREVIEWS

INGESTION_CANONICAL = {
    "health_token.revoke": canonical_health_token_revocation,
    "health_token.create": canonical_health_token_creation,
    "health_samples.delete": canonical_health_removal,
    **SMS_CANONICAL,
}
INGESTION_PREVIEWS = {
    "health_token.revoke": health_token_preview,
    "health_token.create": health_token_creation_preview,
    "health_samples.delete": health_removal_preview,
    **SMS_PREVIEWS,
}
