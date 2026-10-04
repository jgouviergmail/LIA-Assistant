"""Remove model-authored host binding attributes before canonical card injection."""

from html import escape
from html.parser import HTMLParser


class _BindingFilter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, closed: bool) -> None:
        if not any(name == "data-card-ref" for name, _ in attrs):
            self.parts.append(self.get_starttag_text() or "")
            return
        safe = "".join(
            f' {name}="{escape(value, quote=True)}"' if value is not None else f" {name}"
            for name, value in attrs
            if name != "data-card-ref"
        )
        self.parts.append(f'<{tag}{safe}{" /" if closed else ""}>')

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, closed=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, closed=True)

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")


def strip_card_bindings(content: str) -> str:
    if "data-card-ref" not in content.lower():
        return content
    parser = _BindingFilter()
    parser.feed(content)
    parser.close()
    return "".join(parser.parts)
