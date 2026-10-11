"""Only non-secret account security state is model-readable."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class SecurityRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: Literal["overview", "passkeys", "totp"] = "overview"
    cursor: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=50)
