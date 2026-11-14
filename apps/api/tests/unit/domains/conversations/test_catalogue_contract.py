"""Published bounds and private creation payloads agree before persistence."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.core.config.conversations import ConversationsSettings
from src.core.constants import CONVERSATION_LIST_SQL_MAX, CONVERSATION_TITLE_MAX_LENGTH
from src.domains.conversations.catalogue_schemas import ConversationCreateRequest

pytestmark = pytest.mark.unit


def test_rollout_settings_are_composed_and_pages_can_be_tuned() -> None:
    """Environment tuning is actually read by the application Settings MRO."""
    assert issubclass(Settings, ConversationsSettings)
    configured = ConversationsSettings(
        secondary_conversations_enabled=True,
        conversation_list_default_limit=7,
        conversation_list_max_limit=11,
    )
    assert configured.secondary_conversations_enabled
    assert configured.conversation_list_default_limit == 7


@pytest.mark.parametrize(
    "default, maximum", [(0, 10), (12, 11), (1, CONVERSATION_LIST_SQL_MAX + 1)]
)
def test_invalid_page_configuration_cannot_start(default: int, maximum: int) -> None:
    with pytest.raises(ValidationError):
        ConversationsSettings(
            conversation_list_default_limit=default, conversation_list_max_limit=maximum
        )


def test_a_full_length_unicode_title_is_preserved_as_plain_text() -> None:
    title = "界" * CONVERSATION_TITLE_MAX_LENGTH
    request = ConversationCreateRequest(title=title, request_id=uuid4())
    assert request.title == title


def test_a_creation_cannot_smuggle_a_role_or_owner() -> None:
    with pytest.raises(ValidationError):
        ConversationCreateRequest.model_validate(
            {
                "title": "Main",
                "request_id": str(uuid4()),
                "kind": "main",
                "user_id": str(uuid4()),
            }
        )


def test_the_title_bound_counts_code_points_after_trimming() -> None:
    """Whitespace around a full-length supplementary Unicode title is not content."""
    title = "🎨" * CONVERSATION_TITLE_MAX_LENGTH
    request = ConversationCreateRequest(title=f" \t{title}\u3000 ", request_id=uuid4())
    assert request.title == title


@pytest.mark.parametrize(
    "title", ["\u200b", "\u2800", "\u0301", "\ufeff \u200d", "\U000e0061", "\ufe0f"]
)
def test_an_invisible_only_title_is_not_a_named_discussion(title: str) -> None:
    """Zero-width controls, blank glyphs and baseless marks cannot name a row."""
    with pytest.raises(ValidationError):
        ConversationCreateRequest(title=title, request_id=uuid4())


@pytest.mark.parametrize(
    "title", ["Projet <b>été</b>", "👩🏽‍💻", "e\u0301", "工程设计", "\u200fمشروع"]
)
def test_visible_titles_keep_their_writing_and_emoji_sequences(title: str) -> None:
    """Validation never rewrites international text, markup-like text or emoji."""
    assert ConversationCreateRequest(title=title, request_id=uuid4()).title == title


def test_a_creation_without_a_title_asks_for_an_automatic_one() -> None:
    """Omitted or null: the discussion takes its title from its first message."""
    assert ConversationCreateRequest(request_id=uuid4()).title is None
    assert (
        ConversationCreateRequest.model_validate({"title": None, "request_id": str(uuid4())}).title
        is None
    )


@pytest.mark.parametrize("title", ["", " \t\n", "\u00a0\u3000"])
def test_a_blank_title_is_not_a_request_for_an_automatic_one(title: str) -> None:
    """A title that was SENT is held to the grammar: only its absence means automatic."""
    with pytest.raises(ValidationError):
        ConversationCreateRequest(title=title, request_id=uuid4())
