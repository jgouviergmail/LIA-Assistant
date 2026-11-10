"""A refused request leaves a line in the logs, and never what was submitted.

A 422 is answered before any handler runs, and ordinary access logs stay below the
production level: five refused saves of a memory left no line at all on 2026-11-06,
and only a Prometheus counter could say what had happened. The line names WHICH field
was refused and HOW. The value is a person's own text, so it never appears.
"""

from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from prometheus_client import REGISTRY
from pydantic import BaseModel, ConfigDict, Field, RootModel

import src.main as main_module
from src.main import _validation_exception_handler
from tests._routes import served_routes

pytestmark = pytest.mark.unit

SECRET = "Ma soeur Claire est en soins palliatifs"


class _Body(BaseModel):
    content: str = Field(max_length=5)
    labels: dict[str, int] = Field(default_factory=dict)


class _StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = "ok"


class _Recorder:
    """Keeps what the handler logs; every other level is a no-op."""

    def __init__(self) -> None:
        self.warnings: list[dict[str, Any]] = []

    def warning(self, event: str, **fields: Any) -> None:
        self.warnings.append({"event": event, **fields})

    def __getattr__(self, _name: str) -> Any:
        return lambda *args, **kwargs: None


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorded = _Recorder()
    monkeypatch.setattr(main_module, "logger", recorded)
    return recorded


def _counted(field: str, error_type: str) -> float:
    labels = {"field": field, "error_type": error_type}
    return REGISTRY.get_sample_value("validation_errors_total", labels) or 0.0


def _counted_fields() -> set[str]:
    """Every `field` label the counter holds: each one is a series until retention ends."""
    return {
        sample.labels["field"]
        for family in REGISTRY.collect()
        if family.name == "validation_errors"
        for sample in family.samples
        if sample.name == "validation_errors_total"
    }


async def _submit(
    body: dict[str, Any], path: str = "/things", *, raw: bytes | None = None
) -> httpx.Response:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]

    @app.patch("/things")
    async def update(payload: _Body) -> dict[str, str]:
        return {"content": payload.content}

    @app.patch("/strict")
    async def update_strictly(payload: _StrictBody) -> dict[str, str]:
        return {"content": payload.content}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        if raw is not None:
            headers = {"content-type": "application/json"}
            return await client.patch(path, content=raw, headers=headers)
        return await client.patch(path, json=body)


async def test_a_refused_field_is_named_with_how_it_failed(recorder: _Recorder) -> None:
    response = await _submit({"content": "far too long"})
    assert response.status_code == 422
    assert recorder.warnings == [
        {
            "event": "request_validation_failed",
            "errors": ["content:string_too_long"],
            "error_count": 1,
        }
    ]


async def test_the_submitted_value_never_reaches_the_log(recorder: _Recorder) -> None:
    await _submit({"content": SECRET})
    assert "Claire" not in repr(recorder.warnings)


@pytest.mark.parametrize(
    "key",
    [SECRET, "Claire", "Ma soeur Claire.Dupont", "claire.dupont@example.com"],
)
async def test_a_dict_key_the_client_typed_is_not_printed(recorder: _Recorder, key: str) -> None:
    """A dict's key is the client's text, and `loc` carries it as if it were a field."""
    await _submit({"content": "ok", "labels": {key: "not a number"}})
    assert "laire" not in repr(recorder.warnings) and "Dupont" not in repr(recorder.warnings)
    assert recorder.warnings[0]["errors"] == ["<withheld>:int_parsing"]


async def test_an_unknown_key_of_a_strict_body_is_not_printed(recorder: _Recorder) -> None:
    await _submit({"Cancer_du_sein_Claire": 1}, "/strict")
    assert "Claire" not in repr(recorder.warnings)
    assert recorder.warnings[0]["errors"] == ["<withheld>:extra_forbidden"]


async def test_a_cut_is_stated(recorder: _Recorder) -> None:
    """The line keeps ten errors, and says how many there were."""
    await _submit({"content": "ok", "labels": {f"key{n}": "x" for n in range(12)}})
    assert len(recorder.warnings[0]["errors"]) == 10
    assert recorder.warnings[0]["error_count"] == 12


async def test_the_answer_keeps_its_contract(recorder: _Recorder) -> None:
    """The line is added beside the reply, which stays FastAPI's own 422 body."""
    response = await _submit({"content": "far too long"})
    assert response.json()["detail"][0]["type"] == "string_too_long"
    assert response.json()["detail"][0]["loc"] == ["body", "content"]


async def test_a_refused_field_is_counted_under_its_declared_name(recorder: _Recorder) -> None:
    """The counter keeps what a diagnosis reads: which declared field, and how it failed."""
    before = _counted("content", "string_too_long")
    await _submit({"content": "far too long"})
    assert _counted("content", "string_too_long") == before + 1


@pytest.mark.parametrize(
    "key",
    [SECRET, "Claire", "Ma soeur Claire.Dupont", "claire.dupont@example.com"],
)
async def test_a_dict_key_the_client_typed_is_never_a_label(recorder: _Recorder, key: str) -> None:
    """A label is a series kept for the whole retention: a client's text has no place there."""
    fields, before = _counted_fields(), _counted("<withheld>", "int_parsing")
    await _submit({"content": "ok", "labels": {key: "not a number"}})
    assert _counted_fields() - fields <= {"<withheld>"}
    assert _counted("<withheld>", "int_parsing") == before + 1


async def test_an_unknown_key_of_a_strict_body_is_never_a_label(recorder: _Recorder) -> None:
    fields, before = _counted_fields(), _counted("<withheld>", "extra_forbidden")
    await _submit({"Cancer_du_sein_Claire": 1}, "/strict")
    assert _counted_fields() - fields <= {"<withheld>"}
    assert _counted("<withheld>", "extra_forbidden") == before + 1


async def test_where_a_malformed_body_broke_is_neither_named_nor_counted(
    recorder: _Recorder,
) -> None:
    """`json_invalid` locates the character where parsing stopped: a number the client
    chooses, which would open one series per position."""
    fields, before = _counted_fields(), _counted("<withheld>", "json_invalid")
    response = await _submit({}, raw=b'{"content": "ok", "oops"')
    assert response.status_code == 422
    assert recorder.warnings[0]["errors"] == ["<withheld>:json_invalid"]
    assert _counted_fields() - fields <= {"<withheld>"}
    assert _counted("<withheld>", "json_invalid") == before + 1


def _request_bodies(owner: FastAPI) -> list[tuple[str, object]]:
    """The declared type of every request body the application serves."""
    return [
        (context.path or route.path, route.body_field.field_info.annotation)
        for context in served_routes(owner)
        if isinstance(route := context.original_route, APIRoute) and route.body_field is not None
    ]


def _holds_declared_names(annotation: object) -> bool:
    """A model's first level holds the names its fields declare; a mapping's, a client's."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _holds_declared_names(get_args(annotation)[0])
    if origin in (Union, UnionType):
        members = [member for member in get_args(annotation) if member is not type(None)]
        return all(_holds_declared_names(member) for member in members)
    return (
        isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
        and not issubclass(annotation, RootModel)
    )


def test_every_request_body_holds_declared_names() -> None:
    """The handler names what lies one level under `body`, which only a model makes safe.

    A top-level `dict` or `list` body would put a client's keys or indexes there, in the
    log line and in the counter's labels.
    """
    bodies = _request_bodies(main_module.app)
    assert any(path.endswith("/memories/{memory_id}") for path, _ in bodies)
    assert [path for path, annotation in bodies if not _holds_declared_names(annotation)] == []


def test_the_body_check_refuses_a_mapping_and_a_list() -> None:
    """Proven on the shapes it must refuse, so it cannot pass by checking nothing."""
    app = FastAPI()

    @app.post("/mapping")
    async def mapping(body: dict[str, int]) -> None:
        del body

    @app.post("/items")
    async def items(body: list[int]) -> None:
        del body

    @app.post("/model")
    async def model(body: _Body | None = None) -> None:
        del body

    refused = [
        path for path, annotation in _request_bodies(app) if not _holds_declared_names(annotation)
    ]
    assert refused == ["/mapping", "/items"]
