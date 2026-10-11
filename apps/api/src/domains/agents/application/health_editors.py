"""The finite health family shares the existing exact-approval editor dispatcher."""

from src.domains.agents.application.health_removal_editing import rebuild_health_removal_draft
from src.domains.agents.application.health_token_editing import (
    rebuild_health_token_creation_draft,
    rebuild_health_token_draft,
)

HEALTH_EDITORS = {
    "health_token.revoke": rebuild_health_token_draft,
    "health_token.create": rebuild_health_token_creation_draft,
    "health_samples.delete": rebuild_health_removal_draft,
}
