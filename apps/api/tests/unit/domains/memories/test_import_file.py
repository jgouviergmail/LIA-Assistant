"""A memories export reads back as the memories it held — in both formats the export writes.

The oracle is the REAL exporter: every file parsed here is written by
``prepare_management_export_file`` from ``MemoryResponse`` rows, as the export route
does. A hand-written fixture would agree with the parser and with nothing else.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Mapping
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.management_export_file import prepare_management_export_file
from src.domains.memories.import_file import (
    MemoryImportFileError,
    parse_memory_import,
)
from src.domains.memories.management_export import (
    MemoryCSVExportRecord,
    memory_csv_export_record,
)
from src.domains.memories.schemas import MemoryResponse

pytestmark = pytest.mark.unit

_MOMENT = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)


def _memory(content: str, **fields: object) -> MemoryResponse:
    return MemoryResponse.model_validate(
        {
            "id": str(uuid4()),
            "content": content,
            "category": "personal",
            "created_at": _MOMENT,
            "updated_at": _MOMENT,
            **fields,
        }
    )


async def _export(memories: list[MemoryResponse], export_format: str) -> bytes:
    """The file the export route serves for these memories."""

    async def rows() -> AsyncGenerator[Mapping[str, object]]:
        for memory in memories:
            record = memory_csv_export_record(memory) if export_format == "csv" else memory
            yield record.model_dump(mode="json")

    reader = await prepare_management_export_file(
        rows(),
        format=export_format,
        fieldnames=tuple(MemoryCSVExportRecord.model_fields),
        collection="memories",
        metadata={"user_id": str(uuid4()), "exported_at": _MOMENT.isoformat()},
        count_key="total_memories",
        max_bytes=4_000_000,
    )
    try:
        chunks: list[bytes] = []
        while chunk := await reader.read_chunk():
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        await reader.close()


def _fields(parsed_memory: object) -> dict[str, object]:
    data = parsed_memory.data  # type: ignore[attr-defined]
    return {**data.model_dump(), "pinned": parsed_memory.pinned}  # type: ignore[attr-defined]


FORMATS = pytest.mark.parametrize("export_format", ["csv", "json"])


class TestAnExportReadsBackAsWhatItHeld:
    @FORMATS
    async def test_every_field_a_memory_is_created_from_comes_back(
        self, export_format: str
    ) -> None:
        exported = [
            _memory(
                "Je préfère le thé au café — 你好",
                category="preference",
                emotional_weight=-7,
                trigger_topic="boissons",
                usage_nuance="Proposer du thé, jamais de café",
                importance=0.35,
                pinned=True,
            ),
            _memory("A plain fact", category="event"),
        ]

        parsed = parse_memory_import(await _export(exported, export_format), max_memories=10)

        assert parsed.total == 2 and parsed.invalid == 0 and parsed.duplicates == 0
        assert [_fields(memory) for memory in parsed.memories] == [
            {
                "content": "Je préfère le thé au café — 你好",
                "category": "preference",
                "emotional_weight": -7,
                "trigger_topic": "boissons",
                "usage_nuance": "Proposer du thé, jamais de café",
                "importance": 0.35,
                "pinned": True,
            },
            {
                "content": "A plain fact",
                "category": "event",
                "emotional_weight": 0,
                "trigger_topic": "",
                "usage_nuance": "",
                "importance": 0.7,
                "pinned": False,
            },
        ]

    @FORMATS
    @pytest.mark.parametrize(
        "content",
        ["=SUM(1,2) is my favourite formula", "-3 degrees is too cold", "@home on Fridays"],
    )
    async def test_a_text_the_csv_protected_from_a_spreadsheet_comes_back_bare(
        self, export_format: str, content: str
    ) -> None:
        """The CSV export marks a text a spreadsheet would run; the mark is not the text."""
        parsed = parse_memory_import(
            await _export([_memory(content, trigger_topic="+33")], export_format), max_memories=10
        )

        assert parsed.memories[0].data.content == content
        assert parsed.memories[0].data.trigger_topic == "+33"

    @FORMATS
    async def test_an_export_of_nothing_imports_nothing(self, export_format: str) -> None:
        parsed = parse_memory_import(await _export([], export_format), max_memories=10)

        assert (parsed.total, parsed.memories) == (0, ())


class TestWhatAnImportLeavesOut:
    @FORMATS
    async def test_a_memory_the_write_bounds_refuse_is_counted_never_cut(
        self, export_format: str
    ) -> None:
        """An export reads every row whatever its length; a write keeps its bound."""
        too_long = "x" * (settings.memory_content_max_chars + 1)
        exported = [_memory(too_long), _memory("Kept as it is")]

        parsed = parse_memory_import(await _export(exported, export_format), max_memories=10)

        assert (parsed.total, parsed.invalid) == (2, 1)
        assert [memory.data.content for memory in parsed.memories] == ["Kept as it is"]

    @FORMATS
    async def test_the_same_content_twice_is_one_memory(self, export_format: str) -> None:
        exported = [
            _memory("Said twice", category="personal"),
            _memory("Said once"),
            _memory("Said twice", category="event"),
        ]

        parsed = parse_memory_import(await _export(exported, export_format), max_memories=10)

        assert (parsed.total, parsed.duplicates) == (3, 1)
        # The first one read is the one kept.
        assert [(m.data.content, m.data.category) for m in parsed.memories] == [
            ("Said twice", "personal"),
            ("Said once", "personal"),
        ]

    def test_an_entry_of_another_shape_is_counted_invalid(self) -> None:
        document = {
            "memories": [
                {"content": "Valid", "category": "personal"},
                {"content": "Unknown category", "category": "gossip"},
                {"category": "personal"},
                "not an object",
                {"content": "ok", "category": "personal", "importance": "high"},
            ]
        }

        parsed = parse_memory_import(json.dumps(document).encode(), max_memories=10)

        assert (parsed.total, parsed.invalid, len(parsed.memories)) == (5, 4, 1)

    def test_a_json_memory_with_no_pin_keeps_the_creation_default(self) -> None:
        document = {"memories": [{"content": "No pin said", "category": "procedural"}]}

        parsed = parse_memory_import(json.dumps(document).encode(), max_memories=10)

        assert parsed.memories[0].pinned is None


class TestAFileThatIsNotAnExport:
    @FORMATS
    async def test_more_memories_than_one_import_takes_is_refused_whole(
        self, export_format: str
    ) -> None:
        exported = [_memory(f"Fact number {index}") for index in range(4)]

        with pytest.raises(MemoryImportFileError) as refusal:
            parse_memory_import(await _export(exported, export_format), max_memories=3)

        assert refusal.value.code == "too_many"
        assert (refusal.value.found, refusal.value.limit) == (4, 3)

    @pytest.mark.parametrize(
        "content",
        [
            b"",
            b"   \n",
            b"\xff\xfe\x00binary",
            b'{"memories": "not a list"}',
            b'{"interests": []}',
            b"[1, 2, 3]",
            b'{"memories": [',
            b"title,body\nA,B\n",
            b"just a sentence somebody saved as a file",
        ],
    )
    def test_anything_else_is_unreadable_and_says_so(self, content: bytes) -> None:
        with pytest.raises(MemoryImportFileError) as refusal:
            parse_memory_import(content, max_memories=10)

        assert refusal.value.code == "unreadable"

    def test_a_csv_a_spreadsheet_saved_again_is_still_read(self) -> None:
        """Columns in another order, others dropped, CRLF: the header decides, not the layout."""
        content = b"category,content,pinned\r\npreference,Edited in a spreadsheet,True\r\n"

        parsed = parse_memory_import(content, max_memories=10)

        assert _fields(parsed.memories[0]) == {
            "content": "Edited in a spreadsheet",
            "category": "preference",
            "emotional_weight": 0,
            "trigger_topic": "",
            "usage_nuance": "",
            "importance": 0.7,
            "pinned": True,
        }
