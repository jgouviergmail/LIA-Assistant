"""Fixed first-page raster worker, invoked in an isolated Python process."""

import math
import sys


def _resource_limits() -> None:
    if sys.platform == "win32":
        return  # Parent timeout and generated-input gate still apply on Windows.
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))


def first_page_png(data: bytes) -> bytes:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass or not document.page_count:
            raise ValueError("unavailable")
        page = document[0]
        width, height = page.rect.width, page.rect.height
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError("unavailable")
        scale = min(640 / width, 900 / height, 1.5)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=False)
        return bytes(pixmap.tobytes("png"))


def main() -> int:
    try:
        _resource_limits()
        data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
        if not data or len(data) > 10 * 1024 * 1024:
            return 1
        output = first_page_png(data)
        if len(output) > 3 * 1024 * 1024:
            return 1
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        # No parser path, source text or diagnostic may become a response.
        return 1


if __name__ == "__main__":
    sys.exit(main())
