"""Render the document corpus to disk, every fixture in every applicable format.

Usage (from ``apps/api``)::

    .venv/Scripts/python scripts/document_generation/render_corpus.py [--out DIR]

A rendering STEP, never a gate: a test can prove a file opens, not that it is
well composed. The files are for eyes, and for ``measure_office.ps1``, which
asks Word, PowerPoint and Excel what they think of them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.domains.document_generation.context import RenderContext  # noqa: E402
from src.domains.document_generation.renderers import (  # noqa: E402
    DOCUMENT_EXTENSIONS,
    render_document,
)
from src.domains.document_generation.schemas import (  # noqa: E402
    SCHEMA_BY_DOC_TYPE,
    DocumentType,
)

CORPUS = REPO_ROOT / "tests" / "fixtures" / "document_corpus"
DEFAULT_OUT = REPO_ROOT / "data" / "document_corpus_out"


def render_all(out: Path) -> int:
    """Render every fixture; return how many files were written."""
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(CORPUS.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        doc_types = [DocumentType(value) for value in raw["doc_types"]]
        content = SCHEMA_BY_DOC_TYPE[doc_types[0]].model_validate(raw["content"])
        context = RenderContext(
            language=raw.get("language", "en"), structure=raw.get("structure", "auto")
        )
        for doc_type in doc_types:
            target = out / f"{path.stem}.{DOCUMENT_EXTENSIONS[doc_type]}"
            target.write_bytes(render_document(doc_type, content, context))
            written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory.")
    args = parser.parse_args()
    out = Path(args.out)
    written = render_all(out)
    print(f"rendered {written} files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
