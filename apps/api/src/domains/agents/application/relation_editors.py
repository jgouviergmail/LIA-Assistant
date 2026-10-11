"""Relations actions reuse the existing exact-approval editor dispatcher."""

from src.domains.agents.application.relation_context_refresh_editing import (
    rebuild_relation_context_refresh_draft,
)
from src.domains.agents.application.relation_debrief_build_editing import (
    rebuild_relation_debrief_build_draft,
)
from src.domains.agents.application.relation_favorite_editing import rebuild_relation_favorite_draft
from src.domains.agents.application.relation_grouping_editing import rebuild_relation_grouping_draft
from src.domains.agents.application.relation_settings_editing import rebuild_relation_settings_draft

RELATION_EDITORS = {
    "relation_context.refresh": rebuild_relation_context_refresh_draft,
    "relation_debrief.build": rebuild_relation_debrief_build_draft,
    "relation_grouping.update": rebuild_relation_grouping_draft,
    "relation_settings.update": rebuild_relation_settings_draft,
    "relation_favorite.update": rebuild_relation_favorite_draft,
}
