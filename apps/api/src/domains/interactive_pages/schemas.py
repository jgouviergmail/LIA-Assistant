"""The vocabulary of interactive pages (ADR-370)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


class PageMode(str, Enum):
    """What a call asks of the tool. Published to the planner as a closed enum."""

    #: A new page, written from the instructions.
    CREATE = "create"
    #: A page of this conversation, changed as the instructions say.
    REVISE = "revise"
    #: A page or HTML code that already exists, shown as it is: no writer.
    SHOW = "show"
    #: The source of a page that already exists: no writer, no file.
    CODE = "code"


class PageContent(BaseModel):
    """What the writer returns."""

    filename_stem: str = Field(description="Suggested filename, without extension.")
    title: str = Field(description="Short name of the page, as a person would call it.")
    html: str = Field(description="The complete HTML document, from doctype to closing tag.")


@dataclass(frozen=True, slots=True)
class PageSource:
    """A page that already exists, as a mode works from it.

    Attributes:
        html: The page as written, without the policy or the runtime.
        title: Its title, empty when it has none.
    """

    html: str
    title: str
