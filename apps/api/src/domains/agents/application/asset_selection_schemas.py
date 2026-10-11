"""Exact bounded generated-file selections are shared by native mutations."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.attachments.schemas import GENERATED_ASSET_SELECTION_MAX


class AssetSelectionInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ids: tuple[UUID, ...] = Field(min_length=1, max_length=GENERATED_ASSET_SELECTION_MAX)

    @model_validator(mode="after")
    def distinct_files(self) -> Self:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Select each generated file once")
        return self
