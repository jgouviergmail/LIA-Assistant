"""Phone payload boundaries preserve accounting without leaking private input."""

import json

import pytest

from src.domains.ingestion.parser import IngestionBodyError, parse_body

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value",
    [
        {"sender": "Alice", "date": "2026-10-19T12:00:00Z", "body": "Bonjour", "o": "iphone"},
        {"sender": "银行", "body": "明天见 👋\nDeuxième ligne", "date": "2026-10-19T12:00:00Z"},
    ],
)
def test_single_message_preserves_literal_content(value: dict[str, str]) -> None:
    parsed = parse_body(json.dumps(value, ensure_ascii=False).encode())
    assert parsed.items == (value,)
    assert parsed.single is True


@pytest.mark.parametrize("wrapped", [False, True])
def test_batch_keeps_invalid_entries_at_their_original_indices(wrapped: bool) -> None:
    entries = [{"body": "one"}, 42, None, {"body": "two"}]
    value = {"data": entries} if wrapped else entries
    parsed = parse_body(json.dumps(value).encode())
    assert parsed.items == tuple(entries)
    assert parsed.single is False


def test_ndjson_and_shortcuts_wrapping_keep_every_entry() -> None:
    source = '{"body":"a"}\nnull\n{"body":"b"}\n'
    for body in (source.encode(), json.dumps({source: {}}).encode()):
        parsed = parse_body(body)
        assert parsed.items == ({"body": "a"}, None, {"body": "b"})
        assert parsed.single is False


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"  \n ",
        b"42",
        b'{"body":"secret","body":"replacement"}',
        b'{"private":"do-not-echo",',
        b'{"body":NaN}',
        b'{"body":Infinity}',
        b"\xff",
    ],
)
def test_malformed_payload_diagnostics_never_echo_private_input(body: bytes) -> None:
    with pytest.raises(IngestionBodyError) as failure:
        parse_body(body)
    assert all(
        value not in str(failure.value) for value in ("secret", "do-not-echo", "replacement")
    )


def test_byte_limit_is_checked_before_decoding() -> None:
    with pytest.raises(IngestionBodyError, match="body_too_large"):
        parse_body(b"\xff" * 11, max_bytes=10)


def test_invalid_ndjson_reports_index_without_content() -> None:
    with pytest.raises(IngestionBodyError) as failure:
        parse_body(b'{"body":"ok"}\nsecret is not JSON')
    assert failure.value.line == 2
    assert "secret" not in str(failure.value)


def test_health_compatibility_filters_primitives_and_requires_its_singleton_fields() -> None:
    fields = frozenset({"date_start", "date_end"})
    result = parse_body(b'[{"date_start":"a"},false,{"date_end":"b"}]', legacy_fields=fields)
    assert result.items == ({"date_start": "a"}, {"date_end": "b"})
    with pytest.raises(IngestionBodyError, match="unsupported payload shape"):
        parse_body(b'{"body":"sms"}', legacy_fields=fields)


def test_deeply_nested_payload_has_a_bounded_diagnostic() -> None:
    with pytest.raises(IngestionBodyError):
        parse_body(b'{"body":' + b"[" * 1200 + b"0" + b"]" * 1200 + b"}")


async def test_chunked_body_stops_before_consuming_following_chunks() -> None:
    from src.domains.ingestion.parser import read_bounded_body

    consumed = []

    async def chunks():
        for chunk in (b"12345", b"67890", b"never-read"):
            consumed.append(chunk)
            yield chunk

    with pytest.raises(IngestionBodyError, match="body_too_large"):
        await read_bounded_body(chunks(), max_bytes=9)
    assert consumed == [b"12345", b"67890"]


def test_sms_envelope_cannot_hide_a_singleton_or_unknown_fields() -> None:
    with pytest.raises(IngestionBodyError):
        parse_body(b'{"data":[{"body":"nested"}],"body":"outer"}')
    legacy = parse_body(
        b'{"data":[{"date_start":"a"}],"extra":true}',
        legacy_fields=frozenset({"date_start", "date_end"}),
    )
    assert legacy.items == ({"date_start": "a"},)
