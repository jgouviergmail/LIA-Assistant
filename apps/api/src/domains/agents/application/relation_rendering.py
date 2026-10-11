"""Relation-family preview declarations share the existing generic draft renderer."""

from src.domains.agents.application.relation_context_refresh import (
    canonical_relation_context_refresh,
)
from src.domains.agents.application.relation_debrief_build import canonical_relation_debrief_build
from src.domains.agents.application.relation_favorite import canonical_relation_favorite
from src.domains.agents.application.relation_grouping import canonical_relation_grouping

RELATION_PREVIEW_NOTES = {
    "relation_context.refresh": "application_relation_context_refresh_note",
    "relation_settings.update": "application_relation_settings_note",
    "relation_favorite.update": "application_relation_favorite_note",
    "relation_grouping.update": "application_relation_grouping_note",
    "relation_debrief.build": "application_relation_debrief_build_note",
}
RELATION_CANONICAL = {
    "relation_context.refresh": canonical_relation_context_refresh,
    "relation_favorite.update": canonical_relation_favorite,
    "relation_grouping.update": canonical_relation_grouping,
    "relation_debrief.build": canonical_relation_debrief_build,
}
