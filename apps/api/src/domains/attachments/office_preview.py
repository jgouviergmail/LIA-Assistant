"""Small received Office excerpts. Archive/XML budgets precede every parser."""

import csv
import io
import threading
from importlib import import_module
from xml.etree.ElementTree import Element
from zipfile import BadZipFile, ZipFile

OFFICE_FORMATS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}
_PARTS = {
    "docx": "word/document.xml",
    "pptx": "ppt/slides/slide1.xml",
    "xlsx": "xl/worksheets/sheet1.xml",
}
_OFFICE_SLOTS = threading.BoundedSemaphore(2)


def _xml(archive: ZipFile, name: str) -> Element:
    info = archive.getinfo(name)
    if info.file_size > 1024 * 1024 or info.flag_bits & 1:
        raise ValueError("unavailable")
    # Read a cap too: a forged ZIP directory cannot bypass the actual budget.
    with archive.open(info) as part:
        data = part.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("unavailable")
    return _parse_xml(data)


def _parse_xml(data: bytes) -> Element:
    # The unannotated third-party boundary is checked, never trusted as Any.
    parser: object = import_module("defusedxml.ElementTree").fromstring
    if not callable(parser):
        raise ValueError("unavailable")
    try:
        value: object = parser(data)
    except Exception as exc:
        # XML/DTD/entity errors must never publish source/parser diagnostics.
        raise ValueError("unavailable") from exc
    if not isinstance(value, Element):
        raise ValueError("unavailable")
    return value


def _local(node: Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _paragraphs(root: Element) -> str:
    parts: list[str] = []
    for node in root.iter():
        if _local(node) == "p":
            text = "".join(child.text or "" for child in node.iter() if _local(child) == "t")
            if text:
                parts.append(text)
            if len(parts) >= 24:
                break
    return "\n".join(parts)[:4096]


def _spreadsheet(archive: ZipFile, data: bytes) -> str:
    # openpyxl owns Excel's types/number formats (dates are not serial integers).
    # Preflight every XML part the read-only parser may consult before loading.
    for info in archive.infolist():
        if info.filename.endswith(".xml"):
            _xml(archive, info.filename)
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
    try:
        if not workbook.worksheets:
            return ""
        output = io.StringIO()
        writer = csv.writer(output)
        for row in workbook.worksheets[0].iter_rows(
            min_row=1, max_row=7, min_col=1, max_col=8, values_only=True
        ):
            writer.writerow("" if value is None else str(value)[:256] for value in row)
        return output.getvalue()
    finally:
        workbook.close()


def office_excerpt(data: bytes, mime: str) -> bytes:
    if not _OFFICE_SLOTS.acquire(blocking=False):
        raise ValueError("unavailable")
    try:
        return _read_office(data, mime)
    finally:
        _OFFICE_SLOTS.release()


def _read_office(data: bytes, mime: str) -> bytes:
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 256 or sum(info.file_size for info in infos) > 16 * 1024 * 1024:
                raise ValueError("unavailable")
            kind = OFFICE_FORMATS[mime]
            root = _xml(archive, _PARTS[kind])
            text = _spreadsheet(archive, data) if kind == "xlsx" else _paragraphs(root)
            return text.encode("utf-8")
    except (BadZipFile, KeyError, OSError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("unavailable") from exc
