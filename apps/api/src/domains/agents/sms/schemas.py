"""One strict source contract for tool schemas and catalogue manifests."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.core.config import settings
from src.domains.sms.read_schemas import SmsQuery

SMS_TOOL_TOKEN_BUDGET = 1500
SMS_TOOL_MAX_PAGE = 3


class SmsListRequest(SmsQuery):
    limit: StrictInt = Field(default=1, ge=1, le=SMS_TOOL_MAX_PAGE)
    query: None = None


class SmsSearchRequest(SmsQuery):
    limit: StrictInt = Field(default=1, ge=1, le=SMS_TOOL_MAX_PAGE)
    query: str = Field(min_length=1, max_length=256)


class SmsGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    message_id: UUID = Field(json_schema_extra={"x-semantic-type": "sms_message_id"})
    body_offset: StrictInt = Field(default=0, ge=0, le=settings.sms_max_body_chars)


SMS_TOOL_MODELS: dict[str, type[BaseModel]] = {
    "list_sms_tool": SmsListRequest,
    "search_sms_tool": SmsSearchRequest,
    "get_sms_tool": SmsGetRequest,
}
