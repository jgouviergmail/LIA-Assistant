"""Contract tests for the router/service error taxonomy migration (ADR-124).

Phase 2 of ADR-114 (rule #18 alignment). The connector CLIENT layer was
migrated to the ``BaseAPIException`` taxonomy by ADR-114; ADR-124 covers the
remaining raw ``raise HTTPException`` sites in routers, services and
validation modules (inventory 2026-07-10: 33 raise sites across 13 files).

Method (same as ``tests/unit/connectors/test_connector_client_error_contract.py``):

1. **Pin / mapping** — every site was first pinned against the PRE-migration
   behavior (status code, detail payload, headers) targeting the base
   ``fastapi.HTTPException``; after the migration the same assertions were
   strengthened to the typed exception per site. Because ``BaseAPIException``
   IS-A ``HTTPException`` (ADR-002), status/detail/headers assertions carried
   over unchanged — proving the external API contract is byte-identical.
2. **Edge parity** — each NEW exception class is rendered against its
   raw-HTTPException twin via ``TestClient``: same status, same JSON body,
   same headers.

Contract change (the ONLY one, user-approved 2026-07-10): the heartbeat
"min > max" 422 used to be swallowed into a generic 500 by the endpoint's
``except Exception``; the migration added ``except HTTPException: raise`` so
the 422 now reaches the client as intended — and its detail is now localized
through ``APIMessages`` (6 languages).

The ``agents/api/router.py`` HITL 429 lives inside the SSE
``event_generator``: its REAL contract is an SSE ``error`` event (never an
HTTP 429) — pinned end-to-end through the actual generator, plus a
classification-parity proof against the legacy raw raise (see
``TestHitlRateLimitContract``).
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.constants import (
    HEALTH_METRICS_RATE_LIMIT_WINDOW_SECONDS,
    HEALTH_METRICS_TOKEN_PREFIX,
    HITL_RATE_LIMIT_REQUESTS,
    HITL_RATE_LIMIT_WINDOW_SECONDS,
)
from src.core.exceptions import (
    AuthenticationError,
    BadGatewayError,
    ForbiddenError,
    GoneError,
    InternalServerError,
    PayloadTooLargeError,
    RateLimitError,
    ResourceConflictError,
    ResourceNotFoundError,
    StructuredValidationError,
    UnprocessableEntityError,
    ValidationError,
    raise_bearer_auth_failed,
    raise_payload_too_large,
    raise_rate_limit_exceeded,
    raise_run_in_progress,
    raise_structured_validation_error,
    raise_unprocessable_entity,
)
from src.core.i18n_api_messages import APIMessages
from src.core.reasoning_types import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
)

# =============================================================================
# 1. llm_config/reasoning_validation.py — 7 sites (422, structured detail)
# =============================================================================


def _caps(
    widget: str,
    enum_values: list[str] | None = None,
    budget_range: dict | None = None,
) -> SimpleNamespace:
    """Duck-typed _CapsLike fake (same shape the module's Protocol documents)."""
    return SimpleNamespace(
        model_id="model-x",
        reasoning_widget=widget,
        reasoning_enum_values=enum_values,
        reasoning_budget_range=budget_range,
    )


class TestReasoningValidationContract:
    """Pins reasoning_validation.py sites (7 structured 422s)."""

    def _validate(self, caps, value):
        from src.domains.llm_config.reasoning_validation import validate_reasoning_effort

        with pytest.raises(StructuredValidationError) as exc_info:
            validate_reasoning_effort(caps, value)
        assert isinstance(exc_info.value, HTTPException)  # external contract preserved
        return exc_info.value

    def test_widget_none_rejects_any_value(self):
        """Site 1: widget 'none' + non-null value -> 422 reasoning_not_supported."""
        value = ReasoningEffortEnum(effort="low")
        exc = self._validate(_caps("none"), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "reasoning_not_supported",
            "loc": ["body", "reasoning_effort"],
            "msg": (
                "Model model-x does not accept reasoning_effort. " "Set reasoning_effort to null."
            ),
            "input": {"effort": "low"},
            "ctx": {"model": "model-x", "widget": "none"},
        }

    def test_widget_enum_rejects_wrong_shape(self):
        """Site 2: widget 'enum' + budget shape -> 422 wrong_reasoning_effort_shape."""
        value = ReasoningEffortBudget(budget=1024)
        exc = self._validate(_caps("enum", enum_values=["low", "high"]), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "wrong_reasoning_effort_shape",
            "loc": ["body", "reasoning_effort"],
            "msg": 'Model model-x expects an enum value (shape: {"effort": "<string>"}).',
            "input": {"budget": 1024},
            "ctx": {
                "model": "model-x",
                "widget": "enum",
                "expected_shape": {"effort": "<str>"},
            },
        }

    def test_widget_enum_rejects_unknown_effort(self):
        """Site 3: widget 'enum' + effort not in allowed -> 422 invalid_reasoning_effort."""
        value = ReasoningEffortEnum(effort="xhigh")
        exc = self._validate(_caps("enum", enum_values=["low", "medium", "high"]), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "invalid_reasoning_effort",
            "loc": ["body", "reasoning_effort"],
            "msg": (
                "Reasoning effort 'xhigh' is not supported by model-x. "
                "Allowed values: low, medium, high."
            ),
            "input": "xhigh",
            "ctx": {
                "model": "model-x",
                "provided": "xhigh",
                "allowed": ["low", "medium", "high"],
                "widget": "enum",
            },
        }

    def test_widget_budget_int_rejects_wrong_shape(self):
        """Site 4: widget 'budget_int' + enum shape -> 422 wrong_reasoning_effort_shape."""
        value = ReasoningEffortEnum(effort="low")
        rng = {"min": 1024, "max": 8192}
        exc = self._validate(_caps("budget_int", budget_range=rng), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "wrong_reasoning_effort_shape",
            "loc": ["body", "reasoning_effort"],
            "msg": 'Model model-x expects a numeric budget (shape: {"budget": <int>}).',
            "input": {"effort": "low"},
            "ctx": {
                "model": "model-x",
                "widget": "budget_int",
                "expected_shape": {"budget": "<int>"},
            },
        }

    def test_widget_budget_int_rejects_out_of_range(self):
        """Site 5: budget out of [min, max] and not a sentinel -> 422."""
        value = ReasoningEffortBudget(budget=9000)
        rng = {"min": 1024, "max": 8192, "off_sentinel": 0, "dynamic_sentinel": -1}
        exc = self._validate(_caps("budget_int", budget_range=rng), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "invalid_reasoning_budget",
            "loc": ["body", "reasoning_effort"],
            "msg": (
                "Reasoning budget 9000 for model-x is out of range [1024, 8192] "
                "and not a sentinel."
            ),
            "input": 9000,
            "ctx": {
                "model": "model-x",
                "provided": 9000,
                "range": {"min": 1024, "max": 8192},
                "sentinels": [-1, 0],
                "widget": "budget_int",
            },
        }

    def test_widget_toggle_budget_rejects_wrong_shape(self):
        """Site 6: widget 'toggle_budget' + enum shape -> 422."""
        value = ReasoningEffortEnum(effort="low")
        exc = self._validate(_caps("toggle_budget"), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "wrong_reasoning_effort_shape",
            "loc": ["body", "reasoning_effort"],
            "msg": (
                "Model model-x expects a toggle+budget "
                '(shape: {"enabled": <bool>, "budget": <int|null>}).'
            ),
            "input": {"effort": "low"},
            "ctx": {
                "model": "model-x",
                "widget": "toggle_budget",
                "expected_shape": {"enabled": "<bool>", "budget": "<int|null>"},
            },
        }

    def test_widget_toggle_budget_rejects_out_of_range(self):
        """Site 7: enabled toggle with budget out of range -> 422."""
        value = ReasoningEffortToggleBudget(enabled=True, budget=99999)
        rng = {"min": 0, "max": 8192}
        exc = self._validate(_caps("toggle_budget", budget_range=rng), value)

        assert exc.status_code == 422
        assert exc.detail == {
            "type": "invalid_reasoning_budget",
            "loc": ["body", "reasoning_effort"],
            "msg": "Reasoning budget 99999 for model-x is out of range [0, 8192].",
            "input": 99999,
            "ctx": {
                "model": "model-x",
                "provided": 99999,
                "range": {"min": 0, "max": 8192},
                "widget": "toggle_budget",
            },
        }

    def test_non_raising_twin_still_reconciles(self):
        """reasoning_effort_matches_widget keeps catching the typed 422."""
        from src.domains.llm_config.reasoning_validation import (
            reasoning_effort_matches_widget,
        )

        assert reasoning_effort_matches_widget(_caps("none"), None) is True
        assert (
            reasoning_effort_matches_widget(_caps("none"), ReasoningEffortEnum(effort="low"))
            is False
        )


# =============================================================================
# 2. llm_config/service.py — 2 sites (422, structured detail)
# =============================================================================


class TestLLMConfigServiceContract:
    """Pins the two structured 422s of LLMConfigService.update_config."""

    @pytest.mark.asyncio
    async def test_unknown_model_rejected_with_structured_422(self):
        """Site: model absent from the capabilities catalogue -> 422 unknown_model."""
        from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
        from src.domains.llm_config.schemas import LLMTypeConfigUpdate
        from src.domains.llm_config.service import LLMConfigService

        llm_type = next(iter(LLM_TYPES_REGISTRY))
        update = LLMTypeConfigUpdate(
            model="ghost-model",
            reasoning_effort=ReasoningEffortEnum(effort="low"),
        )
        service = LLMConfigService(db=Mock())

        with patch(
            "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
            return_value=None,
        ):
            with pytest.raises(StructuredValidationError) as exc_info:
                await service.update_config(llm_type, update, uuid4(), Mock())

        exc = exc_info.value
        assert exc.status_code == 422
        assert exc.detail == {
            "type": "unknown_model",
            "loc": ["body", "model"],
            "msg": "Model 'ghost-model' is not in the catalogue.",
            "input": "ghost-model",
            "ctx": {"model": "ghost-model"},
        }

    @pytest.mark.asyncio
    async def test_invalid_effort_rejected_with_structured_422(self):
        """Site: effort not in the model's effort_values -> 422 invalid_effort."""
        from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
        from src.domains.llm_config.schemas import LLMTypeConfigUpdate
        from src.domains.llm_config.service import LLMConfigService

        llm_type = next(iter(LLM_TYPES_REGISTRY))
        update = LLMTypeConfigUpdate(model="model-x", effort="max")
        service = LLMConfigService(db=Mock())

        with patch(
            "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
            return_value=SimpleNamespace(effort_values=None),
        ):
            with pytest.raises(StructuredValidationError) as exc_info:
                await service.update_config(llm_type, update, uuid4(), Mock())

        exc = exc_info.value
        assert exc.status_code == 422
        assert exc.detail == {
            "type": "invalid_effort",
            "loc": ["body", "effort"],
            "msg": "Effort 'max' is not supported by model-x. Allowed: none.",
            "input": "max",
            "ctx": {"model": "model-x", "provided": "max", "allowed": []},
        }


# =============================================================================
# 3. llm_config/router.py — 5 sites (ValueError -> 400/404, detail=str(e))
# =============================================================================


class TestLLMConfigRouterContract:
    """Pins the ValueError->typed-exception edge mapping of the admin router."""

    def _patched_service(self, method: str) -> Mock:
        instance = Mock()
        setattr(instance, method, AsyncMock(side_effect=ValueError("boom")))
        return instance

    @pytest.mark.asyncio
    async def test_update_provider_key_maps_value_error_to_400(self):
        """Site: PUT /providers/{provider} -> ValidationError 400, detail=str(e)."""
        from src.domains.llm_config.router import update_provider_key
        from src.domains.llm_config.schemas import ProviderKeyUpdate

        with patch("src.domains.llm_config.router.LLMConfigService") as service_cls:
            service_cls.return_value = self._patched_service("update_provider_key")
            with pytest.raises(ValidationError) as exc_info:
                await update_provider_key(
                    provider="openai",
                    body=ProviderKeyUpdate(key="sk-x"),
                    request=Mock(),
                    current_user=Mock(),
                    db=Mock(),
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "boom"

    @pytest.mark.asyncio
    async def test_delete_provider_key_maps_value_error_to_400(self):
        """Site: DELETE /providers/{provider} -> ValidationError 400, detail=str(e)."""
        from src.domains.llm_config.router import delete_provider_key

        with patch("src.domains.llm_config.router.LLMConfigService") as service_cls:
            service_cls.return_value = self._patched_service("delete_provider_key")
            with pytest.raises(ValidationError) as exc_info:
                await delete_provider_key(
                    provider="openai", request=Mock(), current_user=Mock(), db=Mock()
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "boom"

    @pytest.mark.asyncio
    async def test_get_type_maps_value_error_to_404(self):
        """Site: GET /types/{llm_type} -> ResourceNotFoundError 404, detail=str(e)."""
        from src.domains.llm_config.router import get_type

        with patch("src.domains.llm_config.router.LLMConfigService") as service_cls:
            service_cls.return_value = self._patched_service("get_config")
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await get_type(llm_type="ghost", current_user=Mock(), db=Mock())

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "boom"

    @pytest.mark.asyncio
    async def test_update_type_maps_value_error_to_400(self):
        """Site: PUT /types/{llm_type} -> ValidationError 400, detail=str(e)."""
        from src.domains.llm_config.router import update_type
        from src.domains.llm_config.schemas import LLMTypeConfigUpdate

        with patch("src.domains.llm_config.router.LLMConfigService") as service_cls:
            service_cls.return_value = self._patched_service("update_config")
            with pytest.raises(ValidationError) as exc_info:
                await update_type(
                    llm_type="ghost",
                    body=LLMTypeConfigUpdate(),
                    request=Mock(),
                    current_user=Mock(),
                    db=Mock(),
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "boom"

    @pytest.mark.asyncio
    async def test_reset_type_maps_value_error_to_400(self):
        """Site: POST /types/{llm_type}/reset -> ValidationError 400, detail=str(e)."""
        from src.domains.llm_config.router import reset_type

        with patch("src.domains.llm_config.router.LLMConfigService") as service_cls:
            service_cls.return_value = self._patched_service("reset_config")
            with pytest.raises(ValidationError) as exc_info:
                await reset_type(llm_type="ghost", request=Mock(), current_user=Mock(), db=Mock())

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "boom"


# =============================================================================
# 4. health_metrics/ingest_router.py — 5 sites (401 x2, 429, 400, 413)
# =============================================================================


class TestHealthIngestContract:
    """Pins the ingestion edge: Bearer auth, rate limit, body guards."""

    @pytest.mark.asyncio
    async def test_missing_token_401_with_www_authenticate(self):
        """Site: absent/malformed Authorization -> 401 + WWW-Authenticate."""
        from src.domains.health_metrics.ingest_router import _authenticate

        with pytest.raises(AuthenticationError) as exc_info:
            await _authenticate(authorization=None, db=Mock())

        exc = exc_info.value
        assert isinstance(exc, HTTPException)  # external contract preserved
        assert exc.status_code == 401
        assert exc.detail == "Missing or malformed ingestion token."
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.asyncio
    async def test_unknown_token_401_with_www_authenticate(self):
        """Site: unknown/revoked token -> 401 + WWW-Authenticate."""
        from src.domains.health_metrics.ingest_router import _authenticate

        with patch("src.domains.health_metrics.ingest_router.HealthMetricsService") as service_cls:
            service_cls.return_value.authenticate_token = AsyncMock(return_value=None)
            with pytest.raises(AuthenticationError) as exc_info:
                await _authenticate(
                    authorization=f"Bearer {HEALTH_METRICS_TOKEN_PREFIX}abc", db=Mock()
                )

        exc = exc_info.value
        assert exc.status_code == 401
        assert exc.detail == "Invalid ingestion token."
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.asyncio
    async def test_rate_limit_429_with_retry_after(self):
        """Site: sliding-window hit -> 429, dict detail + Retry-After."""
        from src.domains.health_metrics.ingest_router import _rate_limit_by_token

        limiter = Mock()
        limiter.acquire = AsyncMock(return_value=False)
        token = SimpleNamespace(id=uuid4(), user_id=uuid4())

        with patch(
            "src.domains.health_metrics.ingest_router.get_rate_limiter",
            new=AsyncMock(return_value=limiter),
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await _rate_limit_by_token(token=token)

        exc = exc_info.value
        window = HEALTH_METRICS_RATE_LIMIT_WINDOW_SECONDS
        assert exc.status_code == 429
        assert exc.detail == {
            "error": "rate_limit_exceeded",
            "message": "Too many ingestion requests. Please slow down.",
            "retry_after_seconds": window,
        }
        assert exc.headers == {"Retry-After": str(window)}

    @pytest.mark.asyncio
    async def test_malformed_body_400(self):
        """Site: unparsable body -> 400, detail embeds the parser message."""
        from src.domains.health_metrics.ingest_router import _parse_and_guard_body
        from src.domains.health_metrics.parser import (
            HealthSamplesBodyParseError,
            parse_samples_body,
        )

        raw = b"\x00not-a-body"
        with pytest.raises(HealthSamplesBodyParseError) as parser_exc:
            parse_samples_body(raw)
        expected_detail = f"Malformed request body: {parser_exc.value}"

        request = Mock()
        request.body = AsyncMock(return_value=raw)
        with pytest.raises(ValidationError) as exc_info:
            await _parse_and_guard_body(request)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == expected_detail

    @pytest.mark.asyncio
    async def test_batch_too_large_413(self):
        """Site: batch above the settings cap -> 413 (threshold from settings)."""
        from src.domains.health_metrics.ingest_router import _parse_and_guard_body

        max_samples = settings.health_metrics_max_samples_per_request
        oversized = max_samples + 1
        sample = {"date_start": "2026-07-10T00:00:00Z", "date_end": "2026-07-10T01:00:00Z"}
        raw = json.dumps([sample] * oversized).encode()

        request = Mock()
        request.body = AsyncMock(return_value=raw)
        with pytest.raises(PayloadTooLargeError) as exc_info:
            await _parse_and_guard_body(request)

        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == (
            f"Batch too large: {oversized} samples (max {max_samples} per request)."
        )


# =============================================================================
# 5. user_mcp/admin_router.py — 3 sites (404, same detail)
# =============================================================================


class TestUserMcpAdminRouterContract:
    """Pins the 'Admin MCP server not found' 404 on toggle + the 2 app proxies."""

    @pytest.mark.asyncio
    async def test_toggle_unknown_server_404(self):
        """Site: PATCH /{server_key}/toggle with unknown key -> 404."""
        from src.domains.user_mcp.admin_router import toggle_admin_server

        user = SimpleNamespace(id=uuid4(), admin_mcp_disabled_servers=[])
        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=None,
        ):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await toggle_admin_server(server_key="ghost", user=user, db=Mock())

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Admin MCP server 'ghost' not found"

    @pytest.mark.asyncio
    async def test_app_proxy_call_tool_unknown_server_404(self):
        """Site: POST /{server_key}/app/call-tool with unknown key -> 404."""
        from src.domains.user_mcp.admin_router import admin_app_proxy_call_tool

        user = SimpleNamespace(id=uuid4(), admin_mcp_disabled_servers=[])
        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=None,
        ):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await admin_app_proxy_call_tool(server_key="ghost", request=Mock(), user=user)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Admin MCP server 'ghost' not found"

    @pytest.mark.asyncio
    async def test_app_proxy_read_resource_unknown_server_404(self):
        """Site: POST /{server_key}/app/read-resource with unknown key -> 404."""
        from src.domains.user_mcp.admin_router import admin_app_proxy_read_resource

        user = SimpleNamespace(id=uuid4(), admin_mcp_disabled_servers=[])
        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=None,
        ):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await admin_app_proxy_read_resource(server_key="ghost", request=Mock(), user=user)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Admin MCP server 'ghost' not found"


# =============================================================================
# 6. heartbeat/router.py — 3 sites (422 restored, 500, 404)
# =============================================================================


def _heartbeat_user(language: str = "en") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        language=language,
        heartbeat_enabled=True,
        heartbeat_min_per_day=1,
        heartbeat_max_per_day=3,
        heartbeat_push_enabled=True,
        heartbeat_notify_start_hour=9,
        heartbeat_notify_end_hour=21,
    )


class TestHeartbeatRouterContract:
    """Pins the heartbeat settings/feedback error edge.

    Contract change (approved 2026-07-10, ADR-124): the 422 'min > max' guard
    used to be swallowed by the endpoint's ``except Exception`` and degraded
    to a generic 500. The migration added ``except HTTPException: raise`` so
    the 422 now reaches the client as originally intended — and, being now
    user-visible, its detail goes through ``APIMessages`` (6 languages, the
    English wording keeping the endpoint's historical text).
    """

    @pytest.mark.asyncio
    async def test_min_gt_max_returns_422(self):
        """Site: inconsistent min/max -> 422 (no longer degraded to 500)."""
        from src.domains.heartbeat.router import update_heartbeat_settings
        from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate

        db = AsyncMock()
        with pytest.raises(UnprocessableEntityError) as exc_info:
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_min_per_day=5, heartbeat_max_per_day=2),
                user=_heartbeat_user(language="en"),
                db=db,
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "heartbeat_min_per_day must be <= heartbeat_max_per_day"
        # The guard fires before any write: nothing to roll back.
        db.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("language", ["fr", "zh", "zh-CN"])
    async def test_min_gt_max_detail_is_localized(self, language):
        """The 422 detail follows user.language through the normalize chokepoint
        (raw 'zh' and canonical 'zh-CN' both reach the zh-CN table)."""
        from src.core.i18n import normalize_language
        from src.domains.heartbeat.router import update_heartbeat_settings
        from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate

        with pytest.raises(UnprocessableEntityError) as exc_info:
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_min_per_day=5, heartbeat_max_per_day=2),
                user=_heartbeat_user(language=language),
                db=AsyncMock(),
            )

        expected = APIMessages.heartbeat_min_max_invalid(normalize_language(language))
        assert exc_info.value.detail == expected
        assert exc_info.value.detail != APIMessages.heartbeat_min_max_invalid("en")

    @pytest.mark.asyncio
    async def test_db_failure_maps_to_500(self):
        """Site: any update failure -> 500 with the fixed detail."""
        from src.domains.heartbeat.router import update_heartbeat_settings
        from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate

        db = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("db down"))
        with pytest.raises(InternalServerError) as exc_info:
            await update_heartbeat_settings(
                data=HeartbeatSettingsUpdate(heartbeat_min_per_day=1, heartbeat_max_per_day=2),
                user=_heartbeat_user(),
                db=db,
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to update heartbeat settings"
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_feedback_unknown_notification_404(self):
        """Site: feedback on a notification not owned/found -> 404."""
        from src.domains.heartbeat.router import submit_heartbeat_feedback
        from src.domains.heartbeat.schemas import HeartbeatFeedbackRequest

        with patch("src.domains.heartbeat.router.HeartbeatNotificationRepository") as repo_cls:
            repo_cls.return_value.update_feedback = AsyncMock(return_value=None)
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await submit_heartbeat_feedback(
                    notification_id=uuid4(),
                    data=HeartbeatFeedbackRequest(feedback="thumbs_up"),
                    user=_heartbeat_user(),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Notification not found"


# =============================================================================
# 7. agents/api/router.py — 2 sites (409 run lock, 429 HITL in SSE generator)
# =============================================================================


class TestAgentsRunLockContract:
    """Pins the ADR-117 active-run lock 409 (raised BEFORE the SSE stream)."""

    @pytest.mark.asyncio
    async def test_run_lock_conflict_409_with_active_run_payload(self, monkeypatch):
        """Site: second run on a locked conversation -> 409 + active_run dict."""
        from src.domains.agents.api.router import stream_chat
        from src.domains.agents.api.schemas import ChatRequest

        user_id = uuid4()
        request = ChatRequest(message="hello", user_id=user_id, session_id="s-1")
        current_user = SimpleNamespace(id=user_id)
        active = {"run_id": "r-0", "stream_id": "s-0"}

        monkeypatch.setattr(settings, "usage_limits_enabled", False, raising=False)
        monkeypatch.setattr(settings, "background_runs_enabled", True, raising=False)

        with (
            patch(
                "src.infrastructure.cache.get_conversation_id_cached",
                new=AsyncMock(return_value="conv-1"),
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new=AsyncMock(return_value=Mock()),
            ),
            patch(
                "src.infrastructure.streaming.run_stream_broker.register_active_run",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "src.infrastructure.streaming.run_stream_broker.get_active_run",
                new=AsyncMock(return_value=active),
            ),
        ):
            with pytest.raises(ResourceConflictError) as exc_info:
                await stream_chat(
                    http_request=Mock(),
                    request=request,
                    current_user=current_user,
                    accept_language=None,
                )

        exc = exc_info.value
        assert isinstance(exc, HTTPException)  # external contract preserved
        assert exc.status_code == 409
        assert exc.detail == {"error": "run_in_progress", "active_run": active}


def _hitl_429_detail() -> dict:
    """Exact payload literal of the HITL rate-limit site (kept in sync)."""
    return {
        "error": "rate_limit_exceeded",
        "message": APIMessages.hitl_rate_limit_exceeded(),
        "retry_after": HITL_RATE_LIMIT_WINDOW_SECONDS,
        "limit": HITL_RATE_LIMIT_REQUESTS,
        "window_seconds": HITL_RATE_LIMIT_WINDOW_SECONDS,
    }


class TestHitlRateLimitContract:
    """Pins the HITL rate-limit site's REAL contract.

    The raise lives inside the SSE ``event_generator``, AFTER the response has
    started — so it has never reached the client as an HTTP 429: the
    generator's ``except Exception`` converts it into an SSE ``error`` event
    (message from ``SSEErrorMessages.stream_error``, classified "transient")
    followed by a ``done`` chunk. The tests below pin (1) that real SSE
    contract end-to-end through the actual generator, and (2) that the
    classification driving the SSE message is identical for the legacy raw
    ``HTTPException`` and the migrated ``RateLimitError`` (same ``str(e)`` by
    Starlette ``__str__`` inheritance; the typed name is additionally a
    transient type itself).
    """

    @pytest.mark.asyncio
    async def test_hitl_rate_limit_emits_transient_sse_error_through_real_generator(
        self, monkeypatch
    ):
        """Real path: pending HITL + exhausted counter -> SSE error + done."""
        from src.domains.agents.api.error_messages import SSEErrorMessages
        from src.domains.agents.api.router import stream_chat
        from src.domains.agents.api.schemas import ChatRequest

        user_id = uuid4()
        request = ChatRequest(message="ok", user_id=user_id, session_id="s-1")
        current_user = SimpleNamespace(id=user_id, language="en", timezone="UTC")

        monkeypatch.setattr(settings, "usage_limits_enabled", False, raising=False)
        monkeypatch.setattr(settings, "background_runs_enabled", False, raising=False)

        pending_hitl = {
            "interrupt_ts": "2026-07-10T20:00:00Z",  # freshness handled below
            "action_requests": [{"action": "send_email"}],
        }
        # Keep the pending interrupt fresh regardless of wall clock.
        monkeypatch.setattr(settings, "hitl_pending_data_ttl_seconds", 10**9, raising=False)

        redis = Mock()
        redis.incr = AsyncMock(return_value=HITL_RATE_LIMIT_REQUESTS + 1)
        redis.expire = AsyncMock()

        with (
            patch(
                "src.infrastructure.cache.get_conversation_id_cached",
                new=AsyncMock(return_value="conv-1"),
            ),
            patch(
                "src.domains.agents.api.router._check_pending_hitl",
                new=AsyncMock(return_value=pending_hitl),
            ),
            patch("src.domains.agents.api.router.get_agent_service", return_value=Mock()),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new=AsyncMock(return_value=redis),
            ),
        ):
            response = await stream_chat(
                http_request=Mock(),
                request=request,
                current_user=current_user,
                accept_language=None,
            )
            chunks = [chunk async for chunk in response.body_iterator]

        assert chunks[0] == "retry: 5000\n\n"
        events = [json.loads(c.removeprefix("data: ")) for c in chunks[1:] if c.strip()]
        assert [e["type"] for e in events] == ["error", "done"]

        # The SSE error message is the classifier's output for the raised
        # exception — capture the exact exception the migrated site raises.
        with pytest.raises(RateLimitError) as exc_info:
            raise_rate_limit_exceeded(
                limit=HITL_RATE_LIMIT_REQUESTS,
                window_seconds=HITL_RATE_LIMIT_WINDOW_SECONDS,
                retry_after=HITL_RATE_LIMIT_WINDOW_SECONDS,
                detail=_hitl_429_detail(),
                headers={"Retry-After": str(HITL_RATE_LIMIT_WINDOW_SECONDS)},
            )
        assert events[0]["content"] == SSEErrorMessages.stream_error(exc_info.value, language="en")
        assert events[1]["metadata"]["error"] is True

    def test_sse_classification_identical_to_legacy_raw_raise(self):
        """stream_error yields the SAME message for the legacy raw
        HTTPException literal and the migrated RateLimitError (both classify
        as "transient": same str(e), and the typed name is itself transient)."""
        from src.domains.agents.api.error_messages import SSEErrorMessages

        legacy = HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_hitl_429_detail(),
            headers={"Retry-After": str(HITL_RATE_LIMIT_WINDOW_SECONDS)},
        )
        with pytest.raises(RateLimitError) as exc_info:
            raise_rate_limit_exceeded(
                limit=HITL_RATE_LIMIT_REQUESTS,
                window_seconds=HITL_RATE_LIMIT_WINDOW_SECONDS,
                retry_after=HITL_RATE_LIMIT_WINDOW_SECONDS,
                detail=_hitl_429_detail(),
                headers={"Retry-After": str(HITL_RATE_LIMIT_WINDOW_SECONDS)},
            )
        typed = exc_info.value

        assert str(typed) == str(legacy)  # Starlette __str__ inherited
        for language in ("fr", "en", "es", "de", "it", "zh-CN"):
            assert SSEErrorMessages.stream_error(
                typed, language=language
            ) == SSEErrorMessages.stream_error(legacy, language=language)

    def test_hitl_429_typed_raiser_renders_like_legacy_raw_raise_at_http_edge(self):
        """Edge parity kept for completeness: IF a RateLimitError with this
        payload reached the FastAPI edge (it does not on this site), it would
        render byte-identically to the legacy raw raise."""
        app = FastAPI()
        expected_detail = _hitl_429_detail()

        @app.get("/legacy")
        async def legacy():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=expected_detail,
                headers={"Retry-After": str(HITL_RATE_LIMIT_WINDOW_SECONDS)},
            )

        @app.get("/typed")
        async def typed():
            raise_rate_limit_exceeded(
                limit=HITL_RATE_LIMIT_REQUESTS,
                window_seconds=HITL_RATE_LIMIT_WINDOW_SECONDS,
                retry_after=HITL_RATE_LIMIT_WINDOW_SECONDS,
                detail=expected_detail,
                headers={"Retry-After": str(HITL_RATE_LIMIT_WINDOW_SECONDS)},
            )

        client = TestClient(app, raise_server_exceptions=False)
        legacy_resp = client.get("/legacy")
        typed_resp = client.get("/typed")

        assert typed_resp.status_code == legacy_resp.status_code == 429
        assert typed_resp.json() == legacy_resp.json() == {"detail": expected_detail}
        assert (
            typed_resp.headers["Retry-After"]
            == legacy_resp.headers["Retry-After"]
            == str(HITL_RATE_LIMIT_WINDOW_SECONDS)
        )


# =============================================================================
# 8. user_mcp/router.py — 1 site (502 OAuth initiate)
# =============================================================================


class TestUserMcpOAuthContract:
    @pytest.mark.asyncio
    async def test_oauth_initiate_failure_maps_to_502(self):
        """Site: any initiate_flow failure -> 502 with the fixed detail."""
        from src.domains.user_mcp.models import UserMCPAuthType
        from src.domains.user_mcp.router import oauth_authorize

        server = SimpleNamespace(
            id=uuid4(),
            auth_type=UserMCPAuthType.OAUTH2.value,
            url="https://mcp.example.test",
            oauth_metadata={},
        )
        handler = Mock()
        handler.initiate_flow = AsyncMock(side_effect=RuntimeError("unreachable"))
        handler_cm = Mock()
        handler_cm.__aenter__ = AsyncMock(return_value=handler)
        handler_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.domains.user_mcp.router.UserMCPServerService") as service_cls,
            patch("src.domains.user_mcp.router.MCPOAuthFlowHandler", return_value=handler_cm),
        ):
            service = service_cls.return_value
            service.get_with_ownership_check = AsyncMock(return_value=server)
            service.get_decrypted_credentials = Mock(return_value=None)
            with pytest.raises(BadGatewayError) as exc_info:
                await oauth_authorize(
                    server_id=server.id,
                    user=SimpleNamespace(id=uuid4()),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == (
            "Failed to initiate OAuth flow. The MCP server may be unreachable " "or misconfigured."
        )


# =============================================================================
# 9. auth/router.py + auth/dependencies.py — 2 sites (410 tombstone, 429)
# =============================================================================


class TestAuthContract:
    @pytest.mark.asyncio
    async def test_refresh_tombstone_410_with_migration_payload(self):
        """Site auth/router.py: /auth/refresh always -> 410 Gone."""
        from src.domains.auth.router import refresh_token

        with pytest.raises(GoneError) as exc_info:
            await refresh_token(data=Mock())

        exc = exc_info.value
        assert isinstance(exc, HTTPException)  # external contract preserved
        assert exc.status_code == 410
        assert exc.detail == {
            "error": "endpoint_permanently_removed",
            "message": "Token refresh is no longer needed with BFF Pattern. "
            "Sessions are automatically refreshed on authenticated requests.",
            "migration_guide": "/docs#bff-authentication",
            "alternative": "Use session-based authentication via /auth/login",
            "deprecated_since": "v0.2.0",
            "removed_in": "v0.3.0",
            "learn_more": "https://datatracker.ietf.org/doc/html/rfc7235#section-3.1",
        }

    @pytest.mark.asyncio
    async def test_auth_rate_limiter_429_with_retry_after(self):
        """Site auth/dependencies.py: window hit -> 429 dict + Retry-After.

        Also pins the surrounding ``except HTTPException: raise`` fail-open
        structure: the typed 429 must escape (not be swallowed by the
        fail-open arm) — inheritance keeps that catch working.
        """
        from src.domains.auth.dependencies import create_auth_rate_limiter

        dependency = create_auth_rate_limiter("login", max_calls=3, window_seconds=60)
        limiter = Mock()
        limiter.acquire = AsyncMock(return_value=False)
        request = Mock()
        request.client = Mock(host="203.0.113.7")

        with patch(
            "src.domains.auth.dependencies.get_rate_limiter",
            new=AsyncMock(return_value=limiter),
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await dependency(request)

        exc = exc_info.value
        assert exc.status_code == 429
        assert exc.detail == {
            "error": "rate_limit_exceeded",
            "message": "Too many login attempts. Please try again later.",
            "retry_after_seconds": 60,
        }
        assert exc.headers == {"Retry-After": "60"}


# =============================================================================
# 10. connectors / scheduled_actions / channels — 3 single sites
# =============================================================================


class TestSingleSiteContracts:
    @pytest.mark.asyncio
    async def test_places_photo_invalid_name_400(self):
        """Site connectors/router.py: malformed photo resource name -> 400."""
        from src.domains.connectors.router import proxy_places_photo

        with pytest.raises(ValidationError) as exc_info:
            await proxy_places_photo(
                photo_name="../not/a/photo",
                max_height=400,
                max_width=400,
                current_user=SimpleNamespace(id=uuid4()),
                db=Mock(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid photo resource name format"

    @pytest.mark.asyncio
    async def test_scheduled_action_already_executing_409(self):
        """Site scheduled_actions/router.py: EXECUTING action -> 409."""
        from src.domains.scheduled_actions.models import ScheduledActionStatus
        from src.domains.scheduled_actions.router import execute_scheduled_action

        action = SimpleNamespace(id=uuid4(), status=ScheduledActionStatus.EXECUTING.value)
        with patch("src.domains.scheduled_actions.router.ScheduledActionService") as service_cls:
            service_cls.return_value.get_with_ownership_check = AsyncMock(return_value=action)
            with pytest.raises(ResourceConflictError) as exc_info:
                await execute_scheduled_action(
                    action_id=action.id,
                    user=SimpleNamespace(id=uuid4()),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "Action is already executing"

    @pytest.mark.asyncio
    async def test_telegram_webhook_bad_signature_403(self):
        """Site channels/router.py: invalid webhook signature -> 403."""
        from src.domains.channels.router import telegram_webhook

        request = Mock()
        request.body = AsyncMock(return_value=b"{}")
        request.headers = {"X-Telegram-Bot-Api-Secret-Token": "bad"}

        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.TelegramWebhookHandler"
        ) as handler_cls:
            handler_cls.return_value.validate_signature = AsyncMock(return_value=False)
            with pytest.raises(ForbiddenError) as exc_info:
                await telegram_webhook(request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Invalid webhook signature"


# =============================================================================
# 11. Edge parity — new classes render exactly like raw HTTPException twins
# =============================================================================


def _build_parity_app() -> FastAPI:
    """One route per NEW typed exception, plus its raw-HTTPException twin."""
    app = FastAPI()
    structured_detail = {
        "type": "invalid_reasoning_effort",
        "loc": ["body", "reasoning_effort"],
        "msg": "Reasoning effort 'xhigh' is not supported by model-x.",
        "input": "xhigh",
        "ctx": {"model": "model-x"},
    }
    gone_detail = {"error": "endpoint_permanently_removed", "migration_guide": "/docs"}
    conflict_detail = {"error": "run_in_progress", "active_run": {"stream_id": "s-0"}}
    rate_detail = {"error": "rate_limit_exceeded", "retry_after_seconds": 60}

    @app.get("/typed/structured-422")
    async def typed_structured():
        raise_structured_validation_error(
            error_type=structured_detail["type"],
            loc=structured_detail["loc"],
            msg=structured_detail["msg"],
            input_value=structured_detail["input"],
            ctx=structured_detail["ctx"],
        )

    @app.get("/legacy/structured-422")
    async def legacy_structured():
        raise HTTPException(status_code=422, detail=structured_detail)

    @app.get("/typed/unprocessable")
    async def typed_unprocessable():
        raise_unprocessable_entity("min must be <= max")

    @app.get("/legacy/unprocessable")
    async def legacy_unprocessable():
        raise HTTPException(status_code=422, detail="min must be <= max")

    @app.get("/typed/too-large")
    async def typed_too_large():
        raise_payload_too_large("Batch too large: 1001 samples (max 1000 per request).")

    @app.get("/legacy/too-large")
    async def legacy_too_large():
        raise HTTPException(
            status_code=413,
            detail="Batch too large: 1001 samples (max 1000 per request).",
        )

    @app.get("/typed/gone")
    async def typed_gone():
        raise GoneError(detail=gone_detail)

    @app.get("/legacy/gone")
    async def legacy_gone():
        raise HTTPException(status_code=410, detail=gone_detail)

    @app.get("/typed/bad-gateway")
    async def typed_bad_gateway():
        raise BadGatewayError(detail="Failed to initiate OAuth flow.")

    @app.get("/legacy/bad-gateway")
    async def legacy_bad_gateway():
        raise HTTPException(status_code=502, detail="Failed to initiate OAuth flow.")

    @app.get("/typed/conflict-dict")
    async def typed_conflict():
        raise_run_in_progress(conflict_detail["active_run"])

    @app.get("/legacy/conflict-dict")
    async def legacy_conflict():
        raise HTTPException(status_code=409, detail=conflict_detail)

    @app.get("/typed/rate-dict")
    async def typed_rate():
        raise_rate_limit_exceeded(
            limit=3,
            window_seconds=60,
            retry_after=60,
            detail=rate_detail,
            headers={"Retry-After": "60"},
        )

    @app.get("/legacy/rate-dict")
    async def legacy_rate():
        raise HTTPException(status_code=429, detail=rate_detail, headers={"Retry-After": "60"})

    @app.get("/typed/bearer-401")
    async def typed_bearer():
        raise_bearer_auth_failed("Invalid ingestion token.")

    @app.get("/legacy/bearer-401")
    async def legacy_bearer():
        raise HTTPException(
            status_code=401,
            detail="Invalid ingestion token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return app


class TestEdgeContractParity:
    """FastAPI renders every new typed exception exactly like its raw twin."""

    @pytest.mark.parametrize(
        ("path", "expected_status", "expected_headers"),
        [
            ("structured-422", 422, {}),
            ("unprocessable", 422, {}),
            ("too-large", 413, {}),
            ("gone", 410, {}),
            ("bad-gateway", 502, {}),
            ("conflict-dict", 409, {}),
            ("rate-dict", 429, {"Retry-After": "60"}),
            ("bearer-401", 401, {"WWW-Authenticate": "Bearer"}),
        ],
    )
    def test_typed_exception_renders_identically_to_raw_http_exception(
        self, path, expected_status, expected_headers
    ):
        """Same status, same JSON payload, same headers as the legacy raise."""
        client = TestClient(_build_parity_app(), raise_server_exceptions=False)

        typed = client.get(f"/typed/{path}")
        legacy = client.get(f"/legacy/{path}")

        assert typed.status_code == expected_status
        assert typed.status_code == legacy.status_code
        assert typed.json() == legacy.json()
        assert set(typed.json().keys()) == {"detail"}
        for header_name, header_value in expected_headers.items():
            assert typed.headers[header_name] == header_value
            assert legacy.headers[header_name] == header_value
