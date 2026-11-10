"""Transport-only source proofs beside strict native download queries.

The router's dependency verifies the proof. It is excluded from serialization
and removed before the unchanged provider-facing model reaches a service.
"""

from pydantic import BaseModel, Field

from src.domains.workbench.card_targets import CARD_TOKEN_MAX_CHARS
from src.domains.workbench.schemas.files import DownloadQuery
from src.domains.workbench.schemas.mail import AttachmentRequest


class _SourceQuery(BaseModel):
    """The optional proof browsers need when opening a native download link."""

    card_source: str | None = Field(
        default=None,
        max_length=CARD_TOKEN_MAX_CHARS,
        exclude=True,
        repr=False,
        description="Account-bound source proof; verified by the request dependency.",
    )


class FileDownloadQuery(DownloadQuery, _SourceQuery):
    """A strict file query plus its optional transport proof."""

    def provider_query(self) -> DownloadQuery:
        """Keep the provider contract free of the source proof."""
        return DownloadQuery.model_validate(self.model_dump())


class MailAttachmentQuery(AttachmentRequest, _SourceQuery):
    """A strict attachment query plus its optional transport proof."""

    def provider_query(self) -> AttachmentRequest:
        """Keep the provider contract free of the source proof."""
        return AttachmentRequest.model_validate(self.model_dump())
