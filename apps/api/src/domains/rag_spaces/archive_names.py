"""Portable ZIP member names: one flat namespace, including the missing-file report."""

import os
import re

from src.core.constants import RAG_SPACES_ARCHIVE_MISSING_MEMBER

_UNSAFE = re.compile(r'[\x00-\x1f\x7f<>:"|?*]')
_DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


def unique_archive_name(original: str, taken: set[str]) -> str:
    """Keep readable basenames while preventing extraction paths and overwrites."""
    name = _UNSAFE.sub("_", original.replace("\\", "/").rsplit("/", 1)[-1]).strip(" .")
    name = name or "document"
    if _DEVICE.match(name):
        name = f"_{name}"
    stem, suffix = os.path.splitext(name)
    counter = 2
    candidate = name
    while candidate.casefold() in taken:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    taken.add(candidate.casefold())
    return candidate


def archive_name_reservations() -> set[str]:
    return {RAG_SPACES_ARCHIVE_MISSING_MEMBER.casefold()}
