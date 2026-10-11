"""The reviewed operation allowlist; route discovery never grants a capability."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User


class OperationKind(str, Enum):
    READ = "read"
    ACTION = "action"
    DEVICE = "device"
    SECURE_HANDOFF = "secure_handoff"


class ApplicationEmptyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ApplicationOperationSpec:
    operation_id: str
    tool_name: str
    sections: tuple[str, ...]
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    kind: OperationKind
    administrative: bool = False
    version: int = 1
    required_capabilities: tuple[PlatformCapability, ...] = ()
    addressed_device: bool = False

    @property
    def interaction_kind(self) -> Literal["secure", "device"] | None:
        """A browser receipt cannot choose its own authentication requirement."""
        if self.kind == OperationKind.SECURE_HANDOFF:
            return "secure"
        if self.kind == OperationKind.DEVICE:
            return "device"
        return None

    def __post_init__(self) -> None:
        if self.addressed_device and self.kind != OperationKind.DEVICE:
            raise ValueError("Only a device action may require an addressed document")
        if not self.operation_id or not self.tool_name or not self.sections:
            raise ValueError("An application operation requires identity and UI coverage")
        if self.version < 1:
            raise ValueError("An application operation requires a positive schema version")


class OperationRegistry:
    """Reviewed declarations with per-request visibility projections."""

    def __init__(self) -> None:
        self._operations: dict[str, ApplicationOperationSpec] = {}
        self._tools: dict[str, ApplicationOperationSpec] = {}

    def register(self, spec: ApplicationOperationSpec) -> None:
        if spec.operation_id in self._operations:
            raise ValueError(f"Duplicate application operation: {spec.operation_id}")
        if spec.tool_name in self._tools:
            raise ValueError(f"Duplicate application tool: {spec.tool_name}")
        self._operations[spec.operation_id] = spec
        self._tools[spec.tool_name] = spec

    def get(self, operation_id: str) -> ApplicationOperationSpec:
        return self._operations[operation_id]

    def get_by_tool_name(self, tool_name: str) -> ApplicationOperationSpec | None:
        return self._tools.get(tool_name)

    def all(self) -> tuple[ApplicationOperationSpec, ...]:
        return tuple(self._operations.values())

    def visible(self, actor: User, *, enabled: bool) -> tuple[ApplicationOperationSpec, ...]:
        if not enabled or not actor.is_active or actor.is_deleted:
            return ()
        return tuple(
            spec
            for spec in self._operations.values()
            if not spec.administrative or actor.is_superuser
        )
