"""The page speaks the synthesis's contract — every code and field, nothing more (spec 2026-10-30 D5).

The page translates each code the API publishes: a code the API produces that the page
does not know would be shown as a raw key, and a code the page knows that the API never
produces is a translation nobody reads (ADR-303). ``apps/web/src/lib/mcp-behavior.ts``
declares each vocabulary once, ``as const``, and a frontend test holds each code
translated in the six languages.

The payloads are hand-written on both sides too, and a field added on one side only
stays green everywhere else — the break ``test_frontend_contract_guard.py`` was written
for. TypeScript types are erased at run time, so Python reads the interfaces as SOURCE.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.domains.user_mcp.behavior_schemas import (
    BehaviorNote,
    BehaviorPreview,
    BehaviorPreviewRequest,
    Driver,
    ExecutionMode,
    ModeBehavior,
    QuestionFlow,
    QuestionLoss,
    ServerBehavior,
    StrategyPreview,
    ToolBehavior,
    ToolConfirmationRequest,
)
from src.domains.user_mcp.schemas import UserMCPDefaults, UserMCPServerListResponse
from src.infrastructure.mcp.confirmation import ConfirmationReason, ConfirmationSource, ToolChoice

pytestmark = pytest.mark.unit

_WEB = Path(__file__).resolve().parents[5] / "web" / "src"
_VOCABULARY = _WEB / "lib" / "mcp-behavior.ts"
_SERVERS_HOOK = _WEB / "hooks" / "useUserMCPServers.ts"


def _declared(name: str) -> list[str]:
    source = _VOCABULARY.read_text(encoding="utf-8")
    declared = re.search(rf"export const {name} = \[([^\]]*)\] as const", source)
    assert declared is not None, f"{name} moved: update this contract test"
    return re.findall(r"'([a-z_]+)'", declared.group(1))


def _fields(path: Path, interface: str) -> set[str]:
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"export interface {interface}\s*\{{(.*?)\n\}}", source, re.S)
    assert match, f"interface {interface} not found in {path.name}: update this contract test"
    return {m.group(1) for m in re.finditer(r"^\s{2}(\w+)\??:", match.group(1), re.M)}


def _served(schema: type[BaseModel]) -> set[str]:
    return set(schema.model_json_schema(mode="serialization")["properties"])


@pytest.mark.parametrize(
    ("web_name", "vocabulary"),
    [
        ("MCP_CONFIRMATION_REASONS", ConfirmationReason),
        ("MCP_CONFIRMATION_SOURCES", ConfirmationSource),
        ("MCP_QUESTION_FLOWS", QuestionFlow),
        ("MCP_BEHAVIOR_NOTES", BehaviorNote),
        ("MCP_DRIVER_KINDS", Driver),
        ("MCP_EXECUTION_MODES", ExecutionMode),
        ("MCP_TOOL_CHOICES", ToolChoice),
    ],
)
def test_the_web_list_is_the_backend_vocabulary(web_name: str, vocabulary: type[StrEnum]) -> None:
    assert _declared(web_name) == [member.value for member in vocabulary]


@pytest.mark.parametrize(
    ("path", "interface", "schema"),
    [
        (_VOCABULARY, "MCPServerBehavior", ServerBehavior),
        (_VOCABULARY, "MCPModeBehavior", ModeBehavior),
        (_VOCABULARY, "MCPToolBehavior", ToolBehavior),
        (_VOCABULARY, "MCPQuestionLoss", QuestionLoss),
        (_VOCABULARY, "MCPBehaviorPreview", BehaviorPreview),
        (_VOCABULARY, "MCPStrategyPreview", StrategyPreview),
        (_VOCABULARY, "UserMCPDefaults", UserMCPDefaults),
        (_SERVERS_HOOK, "UserMCPServerListResponse", UserMCPServerListResponse),
    ],
)
def test_the_browser_reads_exactly_what_the_api_serves(
    path: Path, interface: str, schema: type[BaseModel]
) -> None:
    assert _fields(path, interface) == _served(schema)


@pytest.mark.parametrize(
    ("interface", "schema"),
    [
        ("MCPBehaviorCandidates", BehaviorPreviewRequest),
        ("MCPToolConfirmationRequest", ToolConfirmationRequest),
    ],
)
def test_the_browser_sends_only_what_the_api_accepts(
    interface: str, schema: type[BaseModel]
) -> None:
    accepted = set(schema.model_json_schema()["properties"])
    assert _fields(_VOCABULARY, interface) <= accepted
