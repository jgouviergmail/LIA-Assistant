"""A layout delta retains the previously proposed grid before source replacement validation."""

from src.domains.agents.application.draft_models import ApplicationActionDraftContent


def _revision_intent(old: ApplicationActionDraftContent, intent: object) -> object:
    if old.operation_id != "layout_preferences.update" or not isinstance(intent, dict):
        return intent
    previous = old.intent.get("briefing_preferences")
    grid = intent.get("briefing_preferences")
    if isinstance(previous, dict) and isinstance(grid, dict):
        # A modifier emits a delta; materialize it against the existing proposal
        # before the full-replacement UI schema can introduce default values.
        return {**intent, "briefing_preferences": {**previous, **grid}}
    return intent
