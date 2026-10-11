"""Stream owned audio witnesses in a worker without exposing names or bytes."""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from src.domains.meetings.audio_store import (
    SEGMENT_SUFFIX,
    SEGMENTS_DIR,
    AudioStorageError,
    MeetingAudioStore,
)


@dataclass(frozen=True)
class RetryAudioWitness:
    files: int
    bytes_on_disk: int
    digest: str


def _audio_paths(root: Path, directory: Path, audio_path: str | None) -> list[Path]:
    paths: list[Path] = []
    if audio_path:
        normalized = root / audio_path
        if not normalized.resolve().is_relative_to(directory) or normalized.is_symlink():
            raise AudioStorageError("audio file is not owned")
        if normalized.is_file():
            paths.append(normalized)
    segments = directory / SEGMENTS_DIR
    if segments.is_symlink():
        raise AudioStorageError("audio segment directory is not owned")
    if segments.is_dir():
        paths.extend(
            sorted(
                entry
                for entry in segments.iterdir()
                if entry.suffix == SEGMENT_SUFFIX and entry.stem.isdigit()
            )
        )
    return paths


def _file_witness(path: Path, directory: Path) -> tuple[bytes, int]:
    if path.is_symlink() or not path.resolve().is_relative_to(directory):
        raise AudioStorageError("audio segment is not owned")
    before = path.stat()
    item = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            item.update(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise AudioStorageError("audio changed while observing")
    return item.digest(), after.st_size


def _seal(
    root: Path, owner_id: UUID, meeting_id: UUID, audio_path: str | None
) -> RetryAudioWitness:
    expected = root / str(owner_id) / str(meeting_id)
    directory = expected.resolve()
    if directory != expected:
        raise AudioStorageError("audio directory is not owned")
    paths = _audio_paths(root, directory, audio_path)
    return _paths_witness(paths, directory)


def _paths_witness(paths: list[Path], directory: Path) -> RetryAudioWitness:
    digest, size = hashlib.sha256(), 0
    for path in paths:
        item, item_size = _file_witness(path, directory)
        name = str(path.relative_to(directory)).encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(item)
        size += item_size
    return RetryAudioWitness(len(paths), size, digest.hexdigest())


def _seal_directory(root: Path, owner_id: UUID, meeting_id: UUID) -> RetryAudioWitness:
    directory = root / str(owner_id) / str(meeting_id)
    if directory.resolve() != directory:
        raise AudioStorageError("audio directory is not owned")
    paths: list[Path] = []
    pending = [directory] if directory.exists() else []
    while pending:
        for path in pending.pop().iterdir():
            if path.is_symlink() or path.resolve() != path:
                raise AudioStorageError("audio directory contains an unowned link")
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                paths.append(path)
            else:
                raise AudioStorageError("audio directory contains an unsupported entry")
    return _paths_witness(sorted(paths), directory)


async def seal_meeting_directory(
    store: MeetingAudioStore, owner_id: UUID, meeting_id: UUID
) -> RetryAudioWitness:
    try:
        return await asyncio.to_thread(_seal_directory, store.root, owner_id, meeting_id)
    except OSError:
        raise AudioStorageError("audio witness unavailable") from None


async def seal_retry_audio(
    store: MeetingAudioStore, owner_id: UUID, meeting_id: UUID, audio_path: str | None
) -> RetryAudioWitness:
    try:
        return await asyncio.to_thread(_seal, store.root, owner_id, meeting_id, audio_path)
    except OSError:
        raise AudioStorageError("audio witness unavailable") from None
