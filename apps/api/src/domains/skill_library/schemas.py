"""The skill library's API shapes (ADR-327) — exactly what the web client reads.

A portal's words (a name, a source) are display text; the identities the API
acts on are the repository, the folder and the COMMIT the preview showed:
installing sends them back, so what is installed is what was read.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.core.constants import SKILL_LIBRARY_QUERY_MAX_CHARS

#: Where an installed skill stands against its source.
UpdateState = Literal["current", "available", "unknown"]
#: Why a previewed skill could not be installed as it is.
Conflict = Literal["none", "installed", "name_taken"]

_SHA_PATTERN = r"^[0-9a-f]{40}$"


class LibrarySearchItem(BaseModel):
    """One skill a portal listed."""

    registry_id: str = Field(..., description="The portal's own identifier of the skill.")
    name: str = Field(..., description="The name the portal shows.")
    source: str = Field(..., description="Where the portal says it lives.")
    skill_id: str = Field(..., description="The skill's identifier inside its source.")
    installs: int = Field(..., ge=0, description="Installs the portal counted.")
    repository: str | None = Field(
        None, description="The GitHub repository (owner/repo); null when the origin is not one."
    )
    supported: bool = Field(..., description="Whether LIA can install it (a GitHub origin).")
    installed: bool = Field(..., description="Whether the caller already installed it.")


class LibrarySearchResponse(BaseModel):
    """A portal's answer to a search."""

    portal: str = Field(..., description="The portal searched.")
    items: list[LibrarySearchItem] = Field(..., description="The skills, as the portal ranks them.")
    query_max_chars: int = Field(
        SKILL_LIBRARY_QUERY_MAX_CHARS, description="The longest search text accepted."
    )


class LibraryAudit(BaseModel):
    """What one audit provider said."""

    provider: str = Field(..., description="The provider's name, as the audit service gives it.")
    risk: str = Field(..., description="safe, low, medium, high, critical or unknown.")
    alerts: int = Field(..., ge=0, description="How many alerts it raised.")


class LibraryFile(BaseModel):
    """One file of the skill's folder."""

    path: str = Field(..., description="Relative to the skill folder.")
    size: int = Field(..., ge=0, description="Bytes.")


class LibraryPreviewResponse(BaseModel):
    """A skill read at one commit, before it is installed."""

    portal: str | None = Field(None, description="The portal it was found on, if any.")
    registry_id: str | None = Field(None, description="The portal's identifier, if any.")
    repository: str = Field(..., description="owner/repo.")
    ref: str = Field(..., description="The ref an update follows (HEAD = the default branch).")
    path: str = Field(..., description="The folder inside the repository ('' = the root).")
    commit_sha: str = Field(..., description="The commit read — what an install installs.")
    tree_sha: str = Field(..., description="The folder's git tree SHA at that commit.")
    name: str = Field(..., description="The skill's name, from its SKILL.md.")
    description: str = Field(..., description="Its description, from its SKILL.md.")
    files: list[LibraryFile] = Field(..., description="Every file it installs.")
    skipped: list[str] = Field(
        default_factory=list, description="Links and submodules, never read."
    )
    has_scripts: bool = Field(..., description="Whether it ships scripts (run in the sandbox).")
    audits: list[LibraryAudit] | None = Field(
        None, description="The audits read; null when the audit service could not be read."
    )
    blocked_by: str | None = Field(
        None, description="The audit risk that refuses the install on this instance, if any."
    )
    conflict: Conflict = Field(..., description="Why it cannot be installed as it is, if so.")


class LibraryFolderChoice(BaseModel):
    """A repository holding several skills: the folders to choose from."""

    repository: str = Field(..., description="owner/repo.")
    ref: str = Field(..., description="The ref read.")
    commit_sha: str = Field(..., description="The commit read.")
    folders: list[str] = Field(..., description="Every folder holding a SKILL.md ('' = the root).")


class LibraryPreviewAnswer(BaseModel):
    """A preview, or the folders to choose from first."""

    preview: LibraryPreviewResponse | None = Field(
        None, description="The skill, when one is named."
    )
    choice: LibraryFolderChoice | None = Field(
        None, description="The folders, when the repository holds several skills."
    )


class LibraryInstallRequest(BaseModel):
    """Install the skill a preview showed, at the commit it showed."""

    repository: str = Field(..., max_length=200, description="owner/repo.")
    path: str = Field("", max_length=500, description="The folder ('' = the root).")
    ref: str = Field("HEAD", max_length=200, description="The ref an update will follow.")
    commit_sha: str = Field(..., pattern=_SHA_PATTERN, description="The commit the preview read.")
    portal: str | None = Field(None, max_length=40, description="The portal it was found on.")
    registry_id: str | None = Field(None, max_length=300, description="The portal's identifier.")
    skill_id: str | None = Field(
        None, max_length=200, description="The skill's identifier on the portal, for its audit."
    )

    @field_validator("path")
    @classmethod
    def _strip_slashes(cls, value: str) -> str:
        return value.strip("/")


class LibraryUpdateRequest(BaseModel):
    """Update an installed skill to the commit its update preview showed."""

    commit_sha: str = Field(..., pattern=_SHA_PATTERN, description="The commit the preview read.")


class LibraryInstallResponse(BaseModel):
    """The skill an install or an update registered."""

    skill_id: UUID = Field(..., description="The installed skill.")
    name: str = Field(..., description="Its name.")
    commit_sha: str = Field(..., description="The commit it was installed at.")


class LibraryInstalledItem(BaseModel):
    """One skill the caller installed from a library, and whether it moved."""

    skill_id: UUID = Field(..., description="The installed skill.")
    name: str = Field(..., description="Its name.")
    portal: str | None = Field(None, description="The portal it was found on.")
    repository: str = Field(..., description="owner/repo.")
    path: str = Field(..., description="The folder ('' = the root).")
    ref: str = Field(..., description="The ref it follows.")
    commit_sha: str = Field(..., description="The commit it was installed at.")
    update: UpdateState = Field(..., description="current, available, or unknown (not checked).")


class LibraryInstalledResponse(BaseModel):
    """Every skill the caller installed from a library."""

    items: list[LibraryInstalledItem] = Field(..., description="By name.")


class LibraryChanges(BaseModel):
    """What an update changes in the skill's folder."""

    added: list[str] = Field(default_factory=list, description="Files it adds.")
    removed: list[str] = Field(default_factory=list, description="Files it removes.")
    modified: list[str] = Field(default_factory=list, description="Files it changes.")


class LibraryUpdatePreviewResponse(BaseModel):
    """The next version of an installed skill, and what it changes."""

    preview: LibraryPreviewResponse = Field(..., description="The version an update installs.")
    changes: LibraryChanges = Field(..., description="The files it changes.")
