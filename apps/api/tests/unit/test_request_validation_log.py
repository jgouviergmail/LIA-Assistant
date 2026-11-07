"""A refused request leaves a line in the logs, and never what was submitted.

A 422 is answered before any handler runs, and ordinary access logs stay below the
production level: five refused saves of a memory left no line at all on 2026-11-06,
and only a Prometheus counter could say what had happened. The line names WHICH field
was refused and HOW. The value is a person's own text, so it never appears.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

import src.main as main_module
from src.main import _validation_exception_handler

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


async def _submit(body: dict[str, Any], path: str = "/things") -> httpx.Response:
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
