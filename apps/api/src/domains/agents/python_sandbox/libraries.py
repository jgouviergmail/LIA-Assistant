"""The libraries a sandbox script may import — declared once, promised once.

The ``<Computation>`` block and the tool's manifest both name what a script
can rely on beyond the standard library. That list is a PROMISE the model
acts on, so it lives in one table whose two properties are guarded:

- every distribution is a DIRECT entry of ``requirements.txt`` (ADR-112) —
  the sandbox runs on the API image, and a name that only rides a transitive
  dependency dies on somebody else's upgrade;
- every import name imports, on the lockfile CI installs
  (``tests/unit/domains/agents/python_sandbox/test_libraries.py``) and in the
  built image (``task sandbox:libraries:check``).

Names are IMPORT names: the model writes ``import bs4``, never
``import beautifulsoup4``. Deliberately absent: what a run cannot use (no
DNS of its own, so no ``dnspython``; text out only, so no plotting) and what
the standard library already covers (``re``, ``json``, ``hashlib``, ``hmac``).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass

#: Group headings, in rendering order.
LIBRARY_GROUPS: tuple[str, ...] = (
    "HTTP and parsing",
    "Data and tables",
    "Dates and calendars",
    "Documents",
    "Text and formats",
)


@dataclass(frozen=True, slots=True)
class SandboxLibrary:
    """One library the sandbox promises.

    Attributes:
        import_name: What the script writes after ``import``.
        distribution: The PyPI name pinned in ``requirements.txt``.
        use: One word or two on what it is for (rendered nowhere yet — kept
            with the declaration so a reviewer can refuse a library nobody
            can name a use for).
        group: One of :data:`LIBRARY_GROUPS`.
    """

    import_name: str
    distribution: str
    use: str
    group: str


PYTHON_SANDBOX_LIBRARIES: tuple[SandboxLibrary, ...] = (
    SandboxLibrary("requests", "requests", "HTTP client", "HTTP and parsing"),
    SandboxLibrary("httpx", "httpx", "HTTP client", "HTTP and parsing"),
    SandboxLibrary("aiohttp", "aiohttp", "async HTTP client", "HTTP and parsing"),
    SandboxLibrary("bs4", "beautifulsoup4", "HTML parsing", "HTTP and parsing"),
    SandboxLibrary("lxml", "lxml", "XML/HTML parsing", "HTTP and parsing"),
    SandboxLibrary("xmltodict", "xmltodict", "XML to dict", "HTTP and parsing"),
    SandboxLibrary("feedparser", "feedparser", "RSS/Atom", "HTTP and parsing"),
    SandboxLibrary("numpy", "numpy", "arrays", "Data and tables"),
    SandboxLibrary("pandas", "pandas", "tables, joins", "Data and tables"),
    SandboxLibrary("openpyxl", "openpyxl", "XLSX read/write", "Data and tables"),
    SandboxLibrary("tabulate", "tabulate", "text tables", "Data and tables"),
    SandboxLibrary("dateutil", "python-dateutil", "date parsing", "Dates and calendars"),
    SandboxLibrary("pytz", "pytz", "timezones", "Dates and calendars"),
    SandboxLibrary("icalendar", "icalendar", "ICS parsing", "Dates and calendars"),
    SandboxLibrary("fitz", "PyMuPDF", "PDF text", "Documents"),
    SandboxLibrary("docx", "python-docx", "DOCX text", "Documents"),
    SandboxLibrary("markdownify", "markdownify", "HTML to Markdown", "Documents"),
    SandboxLibrary("yaml", "pyyaml", "YAML", "Text and formats"),
    SandboxLibrary("chardet", "chardet", "encoding detection", "Text and formats"),
    SandboxLibrary("unidecode", "unidecode", "accent stripping", "Text and formats"),
    SandboxLibrary("pycountry", "pycountry", "countries, currencies", "Text and formats"),
    SandboxLibrary("phonenumbers", "phonenumbers", "phone numbers", "Text and formats"),
)


def render_libraries() -> str:
    """One line per group — ``Group: name, name, …`` — in declaration order."""
    lines = []
    for group in LIBRARY_GROUPS:
        names = [lib.import_name for lib in PYTHON_SANDBOX_LIBRARIES if lib.group == group]
        lines.append(f"{group}: {', '.join(names)}")
    return "\n".join(lines)


def missing_libraries(
    importer: Callable[[str], object] = importlib.import_module,
) -> tuple[str, ...]:
    """The import names that do NOT import here, in declaration order.

    Args:
        importer: How to import a name — the real import by default, a
            substitute in tests.

    Returns:
        The names whose import raised; empty when the promise holds.
    """
    missing: list[str] = []
    for lib in PYTHON_SANDBOX_LIBRARIES:
        try:
            importer(lib.import_name)
        except Exception:  # noqa: BLE001 — any import failure is « missing »
            missing.append(lib.import_name)
    return tuple(missing)


__all__ = [
    "LIBRARY_GROUPS",
    "PYTHON_SANDBOX_LIBRARIES",
    "SandboxLibrary",
    "missing_libraries",
    "render_libraries",
]
