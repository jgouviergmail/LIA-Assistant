"""Closed peer-transfer contracts: source identity is input, authority never is."""

import re
from datetime import datetime
from enum import StrEnum
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.constants import MCP_DEFAULT_TIMEOUT_SECONDS
from src.domains.user_mcp.models import UserMCPAuthType
from src.domains.user_mcp.schemas import UserMCPServerCreate


class CapabilityKind(StrEnum):
    SKILL = "skill"
    MCP = "mcp"
    PLUGIN = "plugin"


class TransferStatus(StrEnum):
    PREPARING = "preparing"
    INSTALLING = "installing"
    INSTALLED = "installed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClosedContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64"
    )


class CapabilityPreviewRequest(ClosedContract):
    connection_id: UUID
    kind: CapabilityKind
    source_id: UUID
    idempotency_key: UUID


class CapabilitySendRequest(ClosedContract):
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PortableMCPConfig(ClosedContract):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    auth_type: UserMCPAuthType = UserMCPAuthType.NONE
    header_name: str | None = Field(default=None, max_length=100)
    domain_description: str | None = Field(default=None, max_length=10000)
    timeout_seconds: int = Field(default=MCP_DEFAULT_TIMEOUT_SECONDS, ge=5, le=300)
    iterative_mode: bool = False
    oauth_scopes: str | None = Field(default=None, max_length=500)
    extra_headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _native_creation_settings(self) -> PortableMCPConfig:
        UserMCPServerCreate(
            name=self.name,
            url=self.url,
            domain_description=self.domain_description,
            timeout_seconds=self.timeout_seconds,
            iterative_mode=self.iterative_mode,
            oauth_scopes=self.oauth_scopes,
        )
        return self

    @field_validator("header_name")
    @classmethod
    def _header_name(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", value) is None:
            raise ValueError("Invalid authentication header name")
        return value

    @field_validator("url")
    @classmethod
    def _portable_url(cls, value: str) -> str:
        # The installer performs the original DNS/SSRF validation separately.
        parsed = urlsplit(value)
        forbidden = {
            "token",
            "accesstoken",
            "apikey",
            "accesskey",
            "clientsecret",
            "refreshtoken",
            "xapikey",
            "key",
            "secret",
            "password",
            "auth",
            "signature",
            "credential",
            "code",
            "jwt",
            "session",
        }
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(
                re.sub(r"[^a-z0-9]", "", key.casefold()) in forbidden
                for key, _ in parse_qsl(parsed.query)
            )
        ):
            raise ValueError("Endpoint cannot be shared with embedded credentials")
        return value


class PortableServer(ClosedContract):
    key: str
    config: PortableMCPConfig


class PortableFile(ClosedContract):
    path: str
    content: bytes


class PackageSnapshot(ClosedContract):
    kind: CapabilityKind
    name: str
    digest: str
    files: tuple[PortableFile, ...]
    omitted: tuple[str, ...] = ()
    servers: tuple[PortableServer, ...] = ()


class CapabilityFileView(ClosedContract):
    path: str
    size: int


class CapabilityComponentView(ClosedContract):
    kind: CapabilityKind
    key: str
    resource_id: UUID | None
    installed: bool
    error_code: str | None = None


class CapabilityTransferView(ClosedContract):
    id: UUID
    kind: CapabilityKind
    name: str
    status: TransferStatus
    digest: str
    files: tuple[CapabilityFileView, ...] = ()
    omitted: tuple[str, ...] = ()
    requires_credentials: bool = False
    created_at: datetime
    transferred_at: datetime | None = None
    components: tuple[CapabilityComponentView, ...] = ()
    error_code: str | None = None
