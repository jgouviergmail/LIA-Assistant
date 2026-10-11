"""No session credential or claimed current device is accepted from a model."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.core.constants import SESSION_DISPLAY_ID_LENGTH


class DeviceSessionsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cursor: str | None = Field(default=None, pattern=rf"^[0-9a-f]{{{SESSION_DISPLAY_ID_LENGTH}}}$")
    limit: StrictInt = Field(default=25, ge=1, le=50)
