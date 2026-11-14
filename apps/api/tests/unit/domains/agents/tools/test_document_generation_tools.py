"""generate_document tool: guard order, honest failures, success path (ADR-226).

Invocation and settings-doubling mirror
``test_image_generation_tools_rate_limit.py`` (the canonical harness for
rate-limited tools): ``tool.coroutine(...)``, module-level settings patch,
in-memory tracker reset between tests.
"""

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from langchain.tools import ToolRuntime

from src.core.document_preferences import (
    DocumentAnimations,
    DocumentIllustrations,
    DocumentPreferences,
)
from src.domains.agents.tools import document_generation_tools as mod
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker
from src.domains.document_generation.illustrations import IllustrationReport
from src.domains.document_generation.service import GeneratedDocumentResult
from src.domains.feature_switches.registry import PlatformCapability
from tests.helpers.runtime_context import make_tool_runtime

SETTINGS_PATCH_PATH = "src.core.config.get_settings"

_USER_ID = "11111111-1111-1111-1111-111111111111"
_CONVERSATION_ID = UUID("22222222-2222-4222-8222-222222222222")
_RUNTIME_ID = UUID("33333333-3333-4333-8333-333333333333")


@pytest.fixture(autouse=True)
def reset_tracker() -> Iterator[None]:
    """Isolate the in-memory sliding-window tracker between tests."""
    _rate_limit_tracker.clear()
    yield
    _rate_limit_tracker.clear()


@pytest.fixture(autouse=True)
def capability_on() -> Iterator[AsyncMock]:
    """The capability is on unless a test switches it off (no settings store read)."""
    with patch.object(mod, "is_capability_enabled", AsyncMock(return_value=True)) as gate:
        yield gate


def _runtime(user_id: str | None = _USER_ID) -> ToolRuntime | MagicMock:
    """A runtime carrying the identity on its typed context (ADR-231).

    ``user_id=None`` models a tool reached with no identity at all, which the
    tool must refuse — so that case keeps a contextless runtime on purpose.
    """
    if user_id is None:
        runtime = MagicMock()
        runtime.config = {"configurable": {"thread_id": "conv1"}}
        runtime.context = None
        return runtime
    return make_tool_runtime(
        user_id=UUID(user_id),
        thread_id=str(_RUNTIME_ID),
        conversation_id=str(_CONVERSATION_ID),
        runtime_id=_RUNTIME_ID,
        conversation_revision=3,
    )


def _fake_settings() -> MagicMock:
    settings = MagicMock()
    settings.document_generation_rate_limit_calls = 10
    settings.document_generation_rate_limit_window = 60
    return settings


def _wrapper_settings() -> MagicMock:
    settings = MagicMock()
    settings.rate_limit_enabled = True
    return settings


def _user() -> MagicMock:
    user = MagicMock()
    user.language = "fr"
    return user


def _success_result() -> GeneratedDocumentResult:
    return GeneratedDocumentResult(
        attachment_id=str(uuid.uuid4()),
        url="/api/v1/attachments/x",
        filename="a.csv",
        doc_type="csv",
        size_bytes=10,
        expires_at_iso=None,
        truncated_source=False,
    )


@pytest.mark.unit
class TestGenerateDocumentGuards:
    """Guard order mirrors generate_image; each failure is explicit."""

    async def test_missing_user_id_fails_auth(self) -> None:
        with patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type="csv", runtime=_runtime(user_id=None)
            )
        assert result.success is False
        assert result.error_code == "AUTH_ERROR"

    async def test_a_switched_off_capability_fails(self, capability_on: AsyncMock) -> None:
        # The EFFECTIVE state, not the deployment flag: an administrator's
        # switch used to be ignored here, so the tool ran in ReAct mode.
        capability_on.return_value = False
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "generate_document_for_user", AsyncMock()) as generate,
        ):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type="csv", runtime=_runtime()
            )
        assert result.success is False
        # Not available on this instance (ADR-307's code), never a tool failure.
        assert result.error_code == "CONFIGURATION_ERROR"
        assert "disabled" in result.message
        capability_on.assert_awaited_once_with(PlatformCapability.DOCUMENT_GENERATION)
        generate.assert_not_awaited()

    async def test_invalid_doc_type_lists_valid_values(self) -> None:
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
        ):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type="exe", runtime=_runtime()
            )
        assert result.success is False
        # The enforced bound is published to the caller (ADR-184).
        for value in ("csv", "xlsx", "docx", "pptx", "pdf", "md", "txt"):
            assert value in result.message

    async def test_doc_type_is_normalized(self) -> None:
        """' .PDF ' and 'pdf' are the same intent — repaired, not rejected."""
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(
                mod, "generate_document_for_user", AsyncMock(return_value=_success_result())
            ) as service_mock,
        ):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type=" .PDF ", runtime=_runtime()
            )
        assert result.success is True
        assert service_mock.call_args.kwargs["doc_type"].value == "pdf"

    async def test_user_not_found_fails(self) -> None:
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=None)),
        ):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type="csv", runtime=_runtime()
            )
        assert result.success is False


@pytest.mark.unit
class TestGenerateDocumentOutcomes:
    """After the guards: honest failure, honest success."""

    async def test_a_truncated_document_names_the_budget_and_produces_no_card(self) -> None:
        """ADR-275: the caller is told WHY and what to do, not just « it failed »."""
        from src.domains.document_generation.service import DocumentOutputTruncatedError

        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(
                mod,
                "generate_document_for_user",
                AsyncMock(side_effect=DocumentOutputTruncatedError(16000)),
            ),
        ):
            result = await mod.generate_document.coroutine(
                instructions="a very long report", doc_type="docx", runtime=_runtime()
            )
        assert result.success is False
        assert result.error_code == "TOOL_ERROR"
        assert "16000" in result.message
        assert "No document was produced" in result.message
        assert "shorter" in result.message  # actionable, not just a refusal

    async def test_service_failure_is_honest(self) -> None:
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(
                mod,
                "generate_document_for_user",
                AsyncMock(side_effect=RuntimeError("render boom")),
            ),
        ):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type="csv", runtime=_runtime()
            )
        assert result.success is False  # tokens may be spent, but no phantom card
        assert "No document was produced" in result.message

    async def test_success_returns_action_success(self) -> None:
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(
                mod, "generate_document_for_user", AsyncMock(return_value=_success_result())
            ),
        ):
            result = await mod.generate_document.coroutine(
                instructions="liste", doc_type="csv", runtime=_runtime()
            )
        assert result.success is True
        assert result.structured_data["document_url"] == "/api/v1/attachments/x"
        assert result.structured_data["filename"] == "a.csv"
        assert "Do NOT include any markdown link" in result.message

    async def test_truncation_is_reported_in_message(self) -> None:
        outcome = _success_result()
        outcome.truncated_source = True
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(mod, "generate_document_for_user", AsyncMock(return_value=outcome)),
        ):
            result = await mod.generate_document.coroutine(
                instructions="liste", doc_type="csv", runtime=_runtime()
            )
        assert result.success is True
        assert "truncated" in result.message

    async def test_service_receives_user_language_and_context(self) -> None:
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(
                mod, "generate_document_for_user", AsyncMock(return_value=_success_result())
            ) as service_mock,
        ):
            await mod.generate_document.coroutine(
                instructions="liste",
                doc_type="csv",
                source_data="données",
                filename="mon-fichier",
                runtime=_runtime(),
            )
        kwargs = service_mock.call_args.kwargs
        assert kwargs["language"] == "fr"
        assert kwargs["conversation_id"] == str(_CONVERSATION_ID)
        assert kwargs["delivery_runtime_id"] == str(_RUNTIME_ID)
        assert kwargs["source_data"] == "données"
        assert kwargs["requested_filename"] == "mon-fichier"


@pytest.mark.unit
class TestTheDocumentPreferencesReachTheService:
    """The person's choices, read once per generation; images need BOTH switches."""

    @staticmethod
    def _account(*, illustrations: str | None, animations: str | None, images: bool) -> MagicMock:
        user = _user()
        user.document_illustrations = illustrations
        user.document_animations = animations
        user.image_generation_enabled = images
        user.image_generation_default_quality = "medium"
        user.image_generation_default_size = "1536x1024"
        return user

    async def _preferences(self, user: MagicMock) -> DocumentPreferences:
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=user)),
            patch.object(
                mod, "generate_document_for_user", AsyncMock(return_value=_success_result())
            ) as service_mock,
        ):
            invoke = mod.generate_document.coroutine
            assert invoke is not None
            await invoke(instructions="liste", doc_type="pptx", runtime=_runtime())
        preferences = service_mock.call_args.kwargs["preferences"]
        assert isinstance(preferences, DocumentPreferences)
        return preferences

    async def test_the_stored_choices_reach_the_service(self) -> None:
        user = self._account(illustrations="never", animations="always", images=True)

        assert await self._preferences(user) == DocumentPreferences(
            illustrations=DocumentIllustrations.NEVER,
            animations=DocumentAnimations.ALWAYS,
            images_allowed=True,
            image_quality="medium",
            image_size="1536x1024",
        )

    async def test_choices_nobody_made_read_as_the_owners_defaults(self) -> None:
        user = self._account(illustrations=None, animations="weekly", images=True)

        preferences = await self._preferences(user)

        assert preferences.illustrations is DocumentIllustrations.AUTO
        assert preferences.animations is DocumentAnimations.PRESENTED

    async def test_an_instance_without_image_generation_allows_no_illustration(
        self, capability_on: AsyncMock
    ) -> None:
        capability_on.side_effect = lambda capability: (
            capability is not PlatformCapability.IMAGE_GENERATION
        )
        user = self._account(illustrations="auto", animations=None, images=True)

        assert (await self._preferences(user)).images_allowed is False

    async def test_a_person_without_image_generation_allows_no_illustration(
        self, capability_on: AsyncMock
    ) -> None:
        user = self._account(illustrations="auto", animations=None, images=False)

        assert (await self._preferences(user)).images_allowed is False
        # The person's own switch decides first: the instance is not even asked.
        asked = [call.args[0] for call in capability_on.await_args_list]
        assert PlatformCapability.IMAGE_GENERATION not in asked


@pytest.mark.unit
class TestWhatBecameOfThePicturesIsTold:
    """A picture that was not drawn is said, by its facts, never left for the model to guess."""

    @pytest.mark.parametrize(
        ("report", "said"),
        [
            (IllustrationReport(), None),
            (IllustrationReport(requested=3, drawn=3), "It carries 3 illustration(s)."),
            (
                IllustrationReport(requested=3, drawn=1, failures=("rate_limited", "refused")),
                "1 of 3 illustrations were drawn; the others failed (rate_limited, refused)",
            ),
            (
                IllustrationReport(requested=2, skipped="usage_limit"),
                "were not drawn: the usage limit is reached",
            ),
            (
                IllustrationReport(requested=2, skipped="model_not_served"),
                "were not drawn: no image model is available",
            ),
        ],
    )
    async def test_the_message_says_it(self, report: IllustrationReport, said: str | None) -> None:
        result = _success_result()
        result.illustrations = report
        with (
            patch.object(mod, "settings", _fake_settings()),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
            patch.object(mod, "_load_user", AsyncMock(return_value=_user())),
            patch.object(mod, "generate_document_for_user", AsyncMock(return_value=result)),
        ):
            invoke = mod.generate_document.coroutine
            assert invoke is not None
            output = await invoke(instructions="deck", doc_type="pptx", runtime=_runtime())

        assert output.success is True
        if said is None:
            assert "illustration" not in output.message
        else:
            assert said in output.message
        assert output.structured_data["illustrations"] == {
            "requested": report.requested,
            "drawn": report.drawn,
            "failures": list(report.failures),
            "skipped": report.skipped,
        }
