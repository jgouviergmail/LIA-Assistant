"""One owned document and source-sealed file identity, under explicit browser confirmation."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.rag_spaces.download_schemas import DocumentDownloadSnapshot


class DocumentDownloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID
    document_id: UUID


class DocumentDownloadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_to_download: DocumentDownloadSnapshot


def canonical_document_download(draft: ApplicationActionDraftContent) -> bool:
    selected = DocumentDownloadPatch.model_validate(draft.intent).document_to_download
    return draft.before == {"document_to_download": None} and draft.after == {
        "document_to_download": selected.public_scope()
    }
