"""generate_document tool: guard order, honest failures, success path (ADR-226).

Invocation and settings-doubling mirror
``test_image_generation_tools_rate_limit.py`` (the canonical harness for
rate-limited tools): ``tool.coroutine(...)``, module-level settings patch,
in-memory tracker reset between tests.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.tools import document_generation_tools as mod
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker
from src.domains.document_generation.service import GeneratedDocumentResult

SETTINGS_PATCH_PATH = "src.core.config.get_settings"

_USER_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def reset_tracker():
    """Isolate the in-memory sliding-window tracker between tests."""
    _rate_limit_tracker.clear()
    yield
    _rate_limit_tracker.clear()


def _runtime(user_id: str | None = _USER_ID) -> MagicMock:
    runtime = MagicMock()
    runtime.config = {"configurable": {"user_id": user_id, "thread_id": "conv1"}}
    return runtime


def _fake_settings(enabled: bool = True) -> MagicMock:
    settings = MagicMock()
    settings.document_generation_enabled = enabled
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

    async def test_global_flag_off_fails(self) -> None:
        with (
            patch.object(mod, "settings", _fake_settings(enabled=False)),
            patch(SETTINGS_PATCH_PATH, return_value=_wrapper_settings()),
        ):
            result = await mod.generate_document.coroutine(
                instructions="x", doc_type="csv", runtime=_runtime()
            )
        assert result.success is False
        assert "disabled" in result.message

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
        assert kwargs["conversation_id"] == "conv1"
        assert kwargs["source_data"] == "données"
        assert kwargs["requested_filename"] == "mon-fichier"
