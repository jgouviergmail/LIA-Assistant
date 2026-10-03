"""Native email rendering and host projection shared with browser journeys."""

from copy import deepcopy
from uuid import UUID

from langchain_core.messages import AIMessage

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display.card_actions import with_card_actions
from src.domains.agents.display.config import DisplayConfig
from src.domains.agents.display.html_renderer import HtmlRenderer
from tests.helpers.card_reference_cases import REFERENCE_DOMAINS


def composition_references() -> list[dict[str, object]]:
    cases = []
    payload = deepcopy(REFERENCE_DOMAINS["emails"]["emails"][0])
    payload["_lia_card_ref"] = "email_reference"
    payload["id"] = "canonical-email"
    payload["_provider"] = "google"
    item = RegistryItem(
        id="email_reference",
        type=RegistryItemType.EMAIL,
        payload=payload,
        meta=RegistryItemMeta(source="gmail", display={"_lia_email_account": str(UUID(int=4))}),
    )
    projection = with_card_actions(
        AIMessage(content="Final answer"), {item.id: item}, run_id="source-run", enabled=True
    ).additional_kwargs
    for language in ("fr", "en"):
        cases.append(
            {
                "language": language,
                "html": HtmlRenderer().render(
                    "emails", {"emails": [payload]}, DisplayConfig(language=language)
                ),
                "metadata": {"run_id": "source-run", **projection},
            }
        )
    return cases
