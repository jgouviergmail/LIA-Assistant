"""Gmail settings tools (lot I, 2026-08).

Two capabilities on the ``gmail.settings.basic`` scope:

- **Read**: vacation responder state, filters and sendAs aliases in one call —
  the mailbox's standing behavior, previously invisible to LIA.
- **Write**: the vacation responder, behind the full HITL draft flow. The
  auto-reply is sent verbatim to every correspondent, so the user confirms the
  exact wording before anything is written.

Filter creation joined at lot completion (HITL draft — a filter rewrites how
every future matching email is handled). sendAs writes stay out of scope.
Gmail-only by nature: the tools target the GOOGLE_GMAIL connector directly,
no functional-category resolution.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool, with_user_preferences
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.google_gmail_settings_client import (
    GoogleGmailSettingsClient,
)
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

_ISO_DATE_FORMAT = "%Y-%m-%d"


class VacationResponderDraftInput(BaseModel):
    """Content of a VACATION_RESPONDER draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    enable: bool = Field(description="Turn the auto-reply on (True) or off (False)")
    subject: str = Field(default="", description="Auto-reply subject")
    body: str = Field(default="", description="Auto-reply plain-text body")
    start_date: str = Field(default="", description="First active day (YYYY-MM-DD, optional)")
    end_date: str = Field(default="", description="Last active day inclusive (YYYY-MM-DD)")
    user_timezone: str = Field(default="UTC", description="IANA timezone for the date bounds")
    user_language: str = Field(default="fr", description="User language for result messages")


# ============================================================================
# READ: mailbox settings overview
# ============================================================================


def _normalize_vacation(vacation: dict[str, Any]) -> dict[str, Any]:
    """Compact vacation payload for the LLM (Gmail's camelCase stays at the API)."""
    return {
        "enabled": bool(vacation.get("enableAutoReply", False)),
        "subject": vacation.get("responseSubject", ""),
        "body": vacation.get("responseBodyPlainText", ""),
        "start_time_ms": vacation.get("startTime"),
        "end_time_ms": vacation.get("endTime"),
    }


def _normalize_filters(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact filter list — criteria and action, no raw internals."""
    return [
        {
            "id": item.get("id", ""),
            "criteria": item.get("criteria", {}),
            "action": item.get("action", {}),
        }
        for item in filters.get("filter", [])
    ]


def _normalize_send_as(send_as: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact sendAs aliases — address, display name and default flags."""
    return [
        {
            "email": alias.get("sendAsEmail", ""),
            "display_name": alias.get("displayName", ""),
            "is_default": bool(alias.get("isDefault", False)),
            "is_primary": bool(alias.get("isPrimary", False)),
        }
        for alias in send_as.get("sendAs", [])
    ]


class GetGmailSettingsTool(ToolOutputMixin, ConnectorTool[GoogleGmailSettingsClient]):
    """Read the mailbox's standing behavior: vacation, filters, sendAs."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailSettingsClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize Gmail settings read tool."""
        super().__init__(tool_name="get_gmail_settings_tool", operation="details")

    async def execute_api_call(
        self,
        client: GoogleGmailSettingsClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch the three settings surfaces (small sequential GETs)."""
        vacation = _normalize_vacation(await client.get_vacation())
        filters = _normalize_filters(await client.list_filters())
        send_as = _normalize_send_as(await client.list_send_as())

        logger.info(
            "gmail_settings_read",
            user_id=str(user_id),
            vacation_enabled=vacation["enabled"],
            filter_count=len(filters),
            send_as_count=len(send_as),
        )
        # The filters/sendAs endpoints return the WHOLE set (no pagination),
        # so len() here is the exact total, not a page-derived claim.
        return {
            "success": True,
            "vacation_responder": vacation,
            "filters": filters,
            "filter_count": len(filters),
            "send_as": send_as,
            "send_as_count": len(send_as),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Settings are a short structured snapshot — no registry items needed."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Gmail settings request failed"),
                error_code=result.get("error"),
            )
        enabled = result["vacation_responder"]["enabled"]
        return UnifiedToolOutput.data_success(
            message=(
                f"vacation responder {'on' if enabled else 'off'}, "
                f"{result['filter_count']} filters, {result['send_as_count']} aliases"
            ),
            structured_data={
                "vacation_responder": result["vacation_responder"],
                "filters": result["filters"],
                "filter_count": result["filter_count"],
                "send_as": result["send_as"],
                "send_as_count": result["send_as_count"],
            },
        )


_get_gmail_settings_instance = GetGmailSettingsTool()


@connector_tool(
    name="get_gmail_settings",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="read",
)
async def get_gmail_settings_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Read the Gmail mailbox settings: vacation responder, filters, send-as aliases.

    Use to answer "is my auto-reply on?", "what filters do I have?" or before
    changing the vacation responder. Gmail only.

    Returns:
        UnifiedToolOutput with the vacation responder state, the exact filter
        list and the sendAs aliases.
    """
    return await _get_gmail_settings_instance.execute(runtime=runtime)


# ============================================================================
# WRITE: vacation responder (HITL draft)
# ============================================================================


def _validate_vacation_request(
    enable: bool, body: str, start_date: str, end_date: str
) -> str | None:
    """Return a machine-readable error code, or None when the request is valid.

    Mechanically repairable issues do not exist here: a missing body or a
    malformed/inverted date range cannot be repaired without inventing intent,
    so they stay real errors the LLM must resolve with the user.
    """
    if not enable:
        return None
    if not body.strip():
        return "vacation_body_required"
    parsed: dict[str, date] = {}
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value:
            try:
                parsed[name] = date.fromisoformat(value)
            except ValueError:
                return "invalid_date_format"
    if (
        "start_date" in parsed
        and "end_date" in parsed
        and parsed["end_date"] < parsed["start_date"]
    ):
        return "end_before_start"
    return None


@connector_tool(
    name="set_vacation_responder",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
@with_user_preferences
async def set_vacation_responder_tool(
    enable: Annotated[bool, "True to turn the auto-reply on, False to turn it off"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
    subject: Annotated[str, "Auto-reply subject (when enabling)"] = "",
    body: Annotated[str, "Auto-reply message body, sent verbatim (required when enabling)"] = "",
    start_date: Annotated[str, "First active day, YYYY-MM-DD (optional)"] = "",
    end_date: Annotated[str, "Last active day INCLUSIVE, YYYY-MM-DD (optional)"] = "",
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Set or disable the Gmail vacation responder (returns a confirmation draft).

    The auto-reply is sent to every correspondent, so nothing is written until
    the user confirms the exact wording and dates in the HITL flow. Gmail only.

    Args:
        enable: Turn the auto-reply on or off.
        runtime: LangChain tool runtime.
        subject: Auto-reply subject.
        body: Auto-reply plain-text body (required when enabling).
        start_date: Optional first active day (user timezone).
        end_date: Optional last active day, inclusive (user timezone).
        user_timezone: User timezone (injected by @with_user_preferences).
        locale: User language (injected by @with_user_preferences).

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True),
        or a validation failure the LLM can relay.
    """
    config = validate_runtime_config(runtime, "set_vacation_responder_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    error_code = _validate_vacation_request(enable, body, start_date, end_date)
    if error_code is not None:
        return UnifiedToolOutput.failure(
            message=error_code.replace("_", " "),
            error_code=error_code,
        )

    draft_input = VacationResponderDraftInput(
        enable=enable,
        subject=subject,
        body=body,
        start_date=start_date,
        end_date=end_date,
        user_timezone=user_timezone,
        user_language=locale,
    )
    return DraftService().create_draft(
        draft_type=DraftType.VACATION_RESPONDER,
        content=draft_input.model_dump(),
        related_registry_ids=[],
        source_tool="set_vacation_responder_tool",
        user_language=locale,
    )


def _date_bounds_ms(
    start_date: str, end_date: str, timezone_name: str
) -> tuple[int | None, int | None]:
    """Convert the draft's YYYY-MM-DD bounds to Gmail epoch milliseconds.

    The user states an INCLUSIVE last day; Gmail's ``endTime`` is exclusive,
    so the end bound is midnight AFTER that day, in the user's timezone.
    """
    try:
        tz = ZoneInfo(timezone_name)
    except KeyError, ValueError:
        tz = ZoneInfo("UTC")
    start_ms: int | None = None
    end_ms: int | None = None
    if start_date:
        start = datetime.strptime(start_date, _ISO_DATE_FORMAT).replace(tzinfo=tz)
        start_ms = int(start.timestamp() * 1000)
    if end_date:
        end = datetime.strptime(end_date, _ISO_DATE_FORMAT).replace(tzinfo=tz) + timedelta(days=1)
        end_ms = int(end.timestamp() * 1000)
    return start_ms, end_ms


async def execute_vacation_responder_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed VACATION_RESPONDER draft: write the Gmail setting.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.

    Args:
        draft_content: VACATION_RESPONDER draft content (VacationResponderDraftInput).
        user_id: Draft owner.
        deps: ToolDependencies (Gmail credentials come through it).

    Returns:
        {"success", "enabled"} on write; {"success": False, "error"} otherwise.
    """
    connector_service = await deps.get_connector_service()
    credentials = await connector_service.get_connector_credentials(
        user_id, ConnectorType.GOOGLE_GMAIL
    )
    if credentials is None:
        return {"success": False, "error": "connector_not_activated"}

    client = GoogleGmailSettingsClient(user_id, credentials, connector_service)
    enable = bool(draft_content.get("enable", False))

    if enable:
        start_ms, end_ms = _date_bounds_ms(
            draft_content.get("start_date", ""),
            draft_content.get("end_date", ""),
            draft_content.get("user_timezone") or "UTC",
        )
        await client.update_vacation(
            enable=True,
            subject=draft_content.get("subject", ""),
            body=draft_content.get("body", ""),
            start_time_ms=start_ms,
            end_time_ms=end_ms,
        )
    else:
        await client.update_vacation(enable=False)

    logger.info(
        "vacation_responder_draft_executed",
        user_id=str(user_id),
        enabled=enable,
    )
    return {"success": True, "enabled": enable}


# ============================================================================
# WRITE: filter creation (HITL draft)
# ============================================================================


class EmailFilterDraftInput(BaseModel):
    """Content of an EMAIL_FILTER draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    criteria: dict[str, str] = Field(description="Gmail criteria (from/subject/query)")
    label_id: str = Field(default="", description="Resolved Gmail label id to apply")
    label_name: str = Field(default="", description="Label display name (preview)")
    archive: bool = Field(default=False, description="Skip the inbox (archive)")
    mark_as_read: bool = Field(default=False, description="Mark matching mail as read")
    filter_summary: str = Field(default="", description="Compact one-line summary (card)")
    user_language: str = Field(default="fr", description="User language for messages")


def _filter_summary(criteria: dict[str, str], label_name: str, archive: bool) -> str:
    """Compact neutral one-line summary for the draft card label."""
    parts = [f"{key}:{value}" for key, value in criteria.items() if value]
    target = label_name or ("archive" if archive else "")
    joined = " ".join(parts)
    return f"{joined} → {target}" if target else joined


class CreateEmailFilterTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """Create a Gmail filter (label / archive / mark-read) via HITL draft."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize create email filter tool."""
        super().__init__(tool_name="create_email_filter_tool", operation="write")

    @staticmethod
    def _collect_criteria(kwargs: dict[str, Any]) -> dict[str, str]:
        """Non-empty Gmail criteria from the tool parameters."""
        pairs = (("from", "from_sender"), ("subject", "subject_contains"), ("query", "query"))
        return {
            key: value for key, param in pairs if (value := str(kwargs.get(param) or "").strip())
        }

    @staticmethod
    async def _resolve_label(client: GoogleGmailClient, label_name: str) -> dict[str, Any]:
        """Resolve a label name to its id, or a label_not_found error dict."""
        labels = await client.list_labels()
        wanted = label_name.casefold()
        match = next(
            ((lid, name) for lid, name in labels.items() if str(name).casefold() == wanted),
            None,
        )
        if match is None:
            return {
                "success": False,
                "error": "label_not_found",
                "available_labels": sorted(str(name) for name in labels.values()),
            }
        return {"success": True, "label_id": match[0], "label_name": str(match[1])}

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Validate criteria/actions and resolve the label BEFORE drafting.

        Resolving at draft time gives immediate feedback on an unknown label
        (with the available names) instead of a failure after confirmation.
        """
        criteria = self._collect_criteria(kwargs)
        label_name: str = str(kwargs.get("label_name") or "").strip()
        archive = bool(kwargs.get("archive", False))
        mark_as_read = bool(kwargs.get("mark_as_read", False))

        # Unrepairable without inventing intent: a filter needs something to
        # match and something to do.
        if not criteria:
            return {"success": False, "error": "criteria_required"}
        if not label_name and not archive and not mark_as_read:
            return {"success": False, "error": "action_required"}

        label_id = ""
        if label_name:
            resolved = await self._resolve_label(client, label_name)
            if not resolved["success"]:
                return resolved
            label_id, label_name = resolved["label_id"], resolved["label_name"]

        return {
            "success": True,
            "criteria": criteria,
            "label_id": label_id,
            "label_name": label_name,
            "archive": archive,
            "mark_as_read": mark_as_read,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create the EMAIL_FILTER draft (requires confirmation)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=str(result.get("error", "filter creation failed")).replace("_", " "),
                error_code=result.get("error"),
                metadata={"available_labels": result.get("available_labels", [])},
            )
        draft_input = EmailFilterDraftInput(
            criteria=result["criteria"],
            label_id=result["label_id"],
            label_name=result["label_name"],
            archive=result["archive"],
            mark_as_read=result["mark_as_read"],
            filter_summary=_filter_summary(
                result["criteria"], result["label_name"], result["archive"]
            ),
            user_language=self.get_user_language(),
        )
        return DraftService().create_draft(
            draft_type=DraftType.EMAIL_FILTER,
            content=draft_input.model_dump(),
            related_registry_ids=[],
            source_tool="create_email_filter_tool",
            user_language=draft_input.user_language,
        )


_create_email_filter_instance = CreateEmailFilterTool()


@connector_tool(
    name="create_email_filter",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def create_email_filter_tool(
    from_sender: Annotated[str, "Match mail from this sender (address or domain)"] = "",
    subject_contains: Annotated[str, "Match mail whose subject contains this text"] = "",
    query: Annotated[str, "Gmail query criteria (e.g. 'has:attachment larger:5M')"] = "",
    label_name: Annotated[
        str, "Existing label to apply (matched case-insensitively). Create it first if needed."
    ] = "",
    archive: Annotated[bool, "Skip the inbox for matching mail (archive)"] = False,
    mark_as_read: Annotated[bool, "Mark matching mail as read"] = False,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Create a Gmail filter ("label every mail from X as Newsletters and archive it").

    Needs at least one criterion (sender, subject, query) and one action
    (label, archive, mark as read). Returns a confirmation draft: a filter
    rewrites how every future matching email is handled, so nothing is
    created until the user approves. Gmail only.

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True).
    """
    return await _create_email_filter_instance.execute(
        runtime=runtime,
        from_sender=from_sender,
        subject_contains=subject_contains,
        query=query,
        label_name=label_name,
        archive=archive,
        mark_as_read=mark_as_read,
    )


async def execute_email_filter_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed EMAIL_FILTER draft: create the Gmail filter.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.

    Args:
        draft_content: EmailFilterDraftInput content.
        user_id: Draft owner.
        deps: ToolDependencies (Gmail credentials come through it).

    Returns:
        {"success", "filter_id"} on creation; typed failure otherwise.
    """
    connector_service = await deps.get_connector_service()
    credentials = await connector_service.get_connector_credentials(
        user_id, ConnectorType.GOOGLE_GMAIL
    )
    if credentials is None:
        return {"success": False, "error": "connector_not_activated"}

    action: dict[str, Any] = {}
    if draft_content.get("label_id"):
        action["addLabelIds"] = [draft_content["label_id"]]
    remove_ids = []
    if draft_content.get("archive"):
        remove_ids.append("INBOX")
    if draft_content.get("mark_as_read"):
        remove_ids.append("UNREAD")
    if remove_ids:
        action["removeLabelIds"] = remove_ids

    client = GoogleGmailSettingsClient(user_id, credentials, connector_service)
    response = await client.create_filter(
        criteria=draft_content.get("criteria") or {}, action=action
    )

    logger.info(
        "email_filter_draft_executed",
        user_id=str(user_id),
        filter_id=response.get("id"),
    )
    return {"success": True, "filter_id": response.get("id")}
