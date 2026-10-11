"""The actual dialog bounds constrain native recipient lookups too."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from src.core.constants import EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS
from src.domains.email_share.schemas import EmailShareOptions, RecipientSuggestionsResponse


class EmailShareReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    recipient_query: str | None = Field(
        default=None, max_length=EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS
    )


class EmailShareReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: AwareDatetime
    options: EmailShareOptions
    recipients: RecipientSuggestionsResponse | None = None
