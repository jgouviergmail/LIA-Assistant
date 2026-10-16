"""A vendor's refusal leaves a voice client as its facts, never its words (ADR-317, ADR-345)."""

from __future__ import annotations

import httpx
import pytest

from src.domains.voice.vendor_refusal import (
    ELEVENLABS_CODE_PATHS,
    OPENAI_CODE_PATHS,
    Refusal,
    body_code,
    bounded_code,
    payload_shape,
    refusal_from_body,
    retry_after_of,
)

pytestmark = pytest.mark.unit

#: A refused body quoting the request: these words must never travel.
SENTINEL = "the words of the person, quoted back"


def _refused(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, json=body)


class TestBoundedCode:
    @pytest.mark.parametrize("code", ["invalid_api_key", "quota_exceeded", "a", "x" * 64])
    def test_keeps_an_identifier(self, code: str) -> None:
        assert bounded_code(code) == code

    @pytest.mark.parametrize(
        "value", [SENTINEL, "Invalid API key", "x" * 65, "1st", "", None, 401, ["code"]]
    )
    def test_refuses_prose_and_everything_else(self, value: object) -> None:
        assert bounded_code(value) is None


class TestBodyCode:
    def test_the_first_path_naming_a_code_wins(self) -> None:
        response = _refused(400, {"detail": {"code": "new_name", "status": "legacy_name"}})
        assert body_code(response, *ELEVENLABS_CODE_PATHS) == "new_name"

    def test_a_later_path_answers_when_the_first_names_nothing(self) -> None:
        # The key-ID refusal measured on 2026-09-02 carried the legacy field alone.
        body = {"detail": {"status": "api_key_id_used_as_api_key", "message": SENTINEL}}
        assert body_code(_refused(400, body), *ELEVENLABS_CODE_PATHS) == (
            "api_key_id_used_as_api_key"
        )

    def test_a_prose_code_is_skipped_for_the_next_path(self) -> None:
        response = _refused(400, {"detail": {"code": SENTINEL, "status": "voice_not_found"}})
        assert body_code(response, *ELEVENLABS_CODE_PATHS) == "voice_not_found"

    @pytest.mark.parametrize(
        "body", [{"detail": SENTINEL}, {"detail": [{"msg": SENTINEL}]}, [SENTINEL], {}]
    )
    def test_a_path_that_leads_nowhere_names_nothing(self, body: object) -> None:
        assert body_code(_refused(422, body), *ELEVENLABS_CODE_PATHS) is None

    def test_a_body_that_is_no_json_names_nothing(self) -> None:
        assert body_code(httpx.Response(503, text=SENTINEL), *OPENAI_CODE_PATHS) is None


def test_a_refusal_is_its_status_and_its_code() -> None:
    body = {"error": {"code": "insufficient_quota", "message": SENTINEL}}
    refusal = refusal_from_body(_refused(429, body), *OPENAI_CODE_PATHS)
    assert refusal == Refusal(status=429, vendor_code="insufficient_quota")
    assert refusal.details() == {"status_code": 429, "vendor_code": "insufficient_quota"}


@pytest.mark.parametrize(
    ("header", "seconds"),
    [("12", 12.0), ("0.5", 0.5), ("0", 0.0), (None, None), ("", None)],
)
def test_retry_after_reads_a_stated_delay(header: str | None, seconds: float | None) -> None:
    headers = {} if header is None else {"Retry-After": header}
    assert retry_after_of(httpx.Response(429, headers=headers)) == seconds


@pytest.mark.parametrize("header", ["Wed, 21 Oct 2026 07:28:00 GMT", "-5", "nan", "inf"])
def test_retry_after_states_no_delay_it_cannot_wait(header: str) -> None:
    assert retry_after_of(httpx.Response(429, headers={"Retry-After": header})) is None


class TestPayloadShape:
    def test_names_the_keys_never_the_values(self) -> None:
        shape = payload_shape({"text": SENTINEL, "language_code": "fr"})
        assert shape == {"keys": ["language_code", "text"]}
        assert SENTINEL not in repr(shape)

    def test_names_at_most_sixteen_keys(self) -> None:
        shape = payload_shape({f"k{index:02d}": index for index in range(40)})
        assert shape["keys"] == [f"k{index:02d}" for index in range(16)]

    def test_an_answer_that_is_no_object_is_named_by_its_type(self) -> None:
        assert payload_shape([SENTINEL]) == {"type": "list"}
