"""Strict sealed state and one original write contract for URL or browser-selected packages."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.plugin_read_schemas import PluginReadItem
from src.domains.plugins.package_preview import PluginPackagePreview

PluginPackageCheck = Callable[[AsyncSession], Awaitable[None]]


class PluginImportState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    previous: PluginReadItem | None
    digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    root_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    skills: dict[str, str] = Field(repr=False)
    servers: dict[str, str] = Field(repr=False)


@dataclass(frozen=True)
class PluginPackageWrite:
    content: bytes = field(repr=False)
    package: PluginPackagePreview
    state: PluginImportState
    replace_plugin_id: UUID | None
    value_field: Literal["plugin_url_import", "plugin_file_upload"]
