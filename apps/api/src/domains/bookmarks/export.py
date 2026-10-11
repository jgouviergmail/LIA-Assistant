"""One complete localized Markdown export shared by native download and original email sending."""

from dataclasses import dataclass
from hashlib import sha256

from src.core.i18n import normalize_language
from src.core.time_utils import resolve_user_timezone
from src.domains.bookmarks.indexing import render_bookmark
from src.domains.bookmarks.models import MessageBookmark
from src.domains.users.models import User


@dataclass(frozen=True, slots=True)
class BookmarkExport:
    base_name: str
    text: str

    @property
    def filename(self) -> str:
        return f"{self.base_name}.md"

    @property
    def data(self) -> bytes:
        return self.text.encode("utf-8")

    @property
    def digest(self) -> str:
        return sha256(self.data).hexdigest()


def export_bookmark(row: MessageBookmark, actor: User) -> BookmarkExport:
    return BookmarkExport(
        base_name=f"lia-answer-{row.answered_at.strftime('%Y-%m-%d-%H-%M')}",
        text=render_bookmark(
            row,
            language=normalize_language(actor.language),
            timezone=resolve_user_timezone(actor).key,
        ),
    )
