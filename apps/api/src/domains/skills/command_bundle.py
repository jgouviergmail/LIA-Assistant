"""The tar a skill command receives, and the tar it hands back (ADR-327 lot 2).

A skill command runs in the SEC-001 throwaway container with no mount at all:
the API runs in a container of its own, so a bind path would resolve on the
HOST, and a named volume would hand the sandbox far more than one skill. So
the skill folder and the turn's files travel IN as one tar on stdin, and the
command's output — its text, its exit code and the files it wrote under
``out/`` — travels OUT as one tar on stdout.

What comes back was written by the command, which may be a third party's code,
so :func:`read_output` trusts none of it: regular files only, under ``out/``
only, a bounded count, bounded sizes, plain basenames. A file past a bound is
NAMED with its reason — never dropped in silence.
"""

from __future__ import annotations

import io
import re
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.core.config import settings
from src.core.constants import SKILL_COMMAND_MAX_CHARS, SKILLS_RESOURCE_SKIP_DIRS
from src.domains.skills.sandbox_toolbox import SANDBOX_COMMANDS

__all__ = [
    "COMMAND_DESCRIPTION",
    "HOSTS_DESCRIPTION",
    "INPUT_DIR",
    "BundleTooLarge",
    "CommandOutput",
    "InputFile",
    "OutputFile",
    "OutputLimits",
    "UnreadableOutput",
    "pack_bundle",
    "read_output",
    "safe_file_name",
]

#: Where each half lives in the tar; the container's bootstrap reads the same.
SKILL_PREFIX = "skill"
INPUT_PREFIX = "input"
OUTPUT_PREFIX = "out"
STDOUT_MEMBER = "stdout"
STDERR_MEMBER = "stderr"
EXIT_CODE_MEMBER = "exit_code"

#: Where the turn's files are, seen from the copy the command runs in.
INPUT_DIR = f"../{INPUT_PREFIX}"

#: What the model reads about the command parameter: ONE constant for the
#: manifest the planner reads and the schema the ReAct loop binds.
#: What the model reads of ``command`` — the tool's schema AND the manifest, so the
#: ReAct loop and the planner learn here what only the skill runner's prompt used to
#: say: the commands the image holds (the declaration the image is proven against),
#: and that every call starts from a fresh copy.
COMMAND_DESCRIPTION = (
    "Shell command run with bash in a copy of the skill's folder, offline unless `hosts` "
    f"names what it reaches, at most {SKILL_COMMAND_MAX_CHARS} characters. Available: "
    + ", ".join(command.name for command in SANDBOX_COMMANDS)
    + ". Every call starts from a fresh copy: chain dependent steps in ONE command "
    f"(`a && b`). The files the user attached to this turn are in {INPUT_DIR}/. Write "
    f"every file to hand to the user under {OUTPUT_PREFIX}/."
)

#: What the model reads of ``hosts`` — the tool's schema AND the manifest (ADR-184,
#: ADR-327 lot 3); the bound is the one the egress path enforces.
HOSTS_DESCRIPTION = (
    "Hosts the command reaches over HTTPS, as bare lowercase hostnames (no scheme, "
    "port, path or IP): npm needs registry.npmjs.org, pip needs pypi.org and "
    "files.pythonhosted.org, git needs github.com. Omit for an offline run. At most "
    f"{settings.python_sandbox_max_hosts_per_run}. A host must be permitted — the "
    "operator's list, the person's approval or, for the person's own skills, their "
    "connectors; an unknown host is asked of the person, or refused where nobody can be "
    "asked."
)

#: Why a file the command wrote did not come back.
SKIP_TOO_LARGE = "too_large"
SKIP_TOO_MANY = "too_many"
SKIP_NOT_A_FILE = "not_a_file"
#: The stream the sandbox handed back ended inside this file.
SKIP_INCOMPLETE = "incomplete"

#: Everything in the copy is executable: a shebang script runs as ``./x.sh``.
_FILE_MODE = 0o755
_NAME_MAX_CHARS = 120
_UNSAFE_CHARS = re.compile(r"[^\w.\- ()]+")
_FALLBACK_NAME = "file"
#: More members than this is not a run's output: reading stops.
_MEMBER_CEILING_FACTOR = 4


class BundleTooLarge(Exception):
    """The skill and its input files exceed what one run may carry in."""


class UnreadableOutput(Exception):
    """What the sandbox handed back is not the tar the bootstrap writes."""


@dataclass(frozen=True, slots=True)
class InputFile:
    """One file of the turn, carried into ``input/``.

    Attributes:
        name: Its name inside ``input/`` — already a safe, unique basename.
        path: Where the API reads it.
        size: Its size in bytes, as recorded (checked before anything is read).
    """

    name: str
    path: Path
    size: int


@dataclass(frozen=True, slots=True)
class OutputLimits:
    """What a run may bring back.

    Attributes:
        max_text_bytes: Of stdout, and of stderr.
        max_files: Files under ``out/``.
        max_file_bytes: One file.
        max_total_bytes: All files together.
    """

    max_text_bytes: int
    max_files: int
    max_file_bytes: int
    max_total_bytes: int


@dataclass(frozen=True, slots=True)
class OutputFile:
    """A file the command wrote under ``out/``, under a safe unique basename."""

    name: str
    data: bytes


@dataclass(frozen=True, slots=True)
class CommandOutput:
    """What a run handed back, bounded.

    Attributes:
        exit_code: The command's exit status, or None when it is unreadable.
        stdout: Its standard output, decoded, cut at the bound.
        stderr: Its standard error, decoded, cut at the bound.
        stdout_truncated: The output was longer than what is kept.
        stderr_truncated: The error text was longer than what is kept.
        files: What it wrote under ``out/`` and is within every bound.
        skipped: ``(name, reason)`` for every file it wrote that did not come back.
        incomplete: The stream ended before the tar did — read past a ceiling,
            or cut by the command itself. What came before it is kept.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    files: tuple[OutputFile, ...]
    skipped: tuple[tuple[str, str], ...]
    incomplete: bool = False


def safe_file_name(raw: str, taken: set[str]) -> str:
    """A plain basename for ``raw``, numbered when ``taken`` already holds it.

    Case-insensitive on the clash, because the person's disk may be.

    Args:
        raw: A name somebody else wrote (an upload's name, a path in the tar).
        taken: The names already given, lower-cased; the result is added.

    Returns:
        A basename with no separator, no control character, and no leading dot
        or dash (a command would read ``-x.pdf`` as an option), at most
        ``_NAME_MAX_CHARS`` long with its extension kept.
    """
    base = re.split(r"[\\/]", raw)[-1]
    base = _UNSAFE_CHARS.sub("", base).strip().lstrip(".-").strip()
    stem, dot, extension = base.rpartition(".")
    if not dot or not stem:
        stem, extension = base, ""
    room = _NAME_MAX_CHARS - len(extension) - 1 if extension else _NAME_MAX_CHARS
    stem = stem[: max(room, 1)].strip()
    if not stem.strip("."):
        stem, extension = _FALLBACK_NAME, ""
    name, rank = (f"{stem}.{extension}" if extension else stem), 1
    while name.lower() in taken:
        rank += 1
        name = f"{stem} ({rank}).{extension}" if extension else f"{stem} ({rank})"
    taken.add(name.lower())
    return name


def _skill_files(skill_dir: Path) -> list[tuple[str, Path, int]]:
    """Every regular file of the skill: never a link, never build debris."""
    files = []
    for item in sorted(skill_dir.rglob("*")):
        relative = item.relative_to(skill_dir)
        if any(part in SKILLS_RESOURCE_SKIP_DIRS for part in relative.parts):
            continue
        if item.is_symlink() or not item.is_file():
            continue
        files.append((relative.as_posix(), item, item.stat().st_size))
    return files


def _add(tar: tarfile.TarFile, name: str, path: Path, size: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = _FILE_MODE
    with path.open("rb") as handle:
        tar.addfile(info, handle)


def pack_bundle(skill_dir: Path, inputs: Sequence[InputFile], *, max_bytes: int) -> bytes:
    """The tar the container unpacks: ``skill/…`` and ``input/…``.

    Blocking (it reads files): call it off the event loop.

    Args:
        skill_dir: The skill's folder on the API's disk.
        inputs: The turn's files, already named.
        max_bytes: What the run may carry in, all files together.

    Returns:
        The tar's bytes.

    Raises:
        BundleTooLarge: The recorded sizes exceed ``max_bytes`` — checked
            before a single byte is read.
    """
    skill_files = _skill_files(skill_dir)
    total = sum(size for _, _, size in skill_files) + sum(item.size for item in inputs)
    if total > max_bytes:
        raise BundleTooLarge(total)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for relative, path, size in skill_files:
            _add(tar, f"{SKILL_PREFIX}/{relative}", path, size)
        for item in inputs:
            _add(tar, f"{INPUT_PREFIX}/{item.name}", item.path, item.size)
    return buffer.getvalue()


def _text(tar: tarfile.TarFile, member: tarfile.TarInfo, limit: int) -> tuple[str, bool]:
    handle = tar.extractfile(member)
    raw = handle.read(limit + 1) if handle is not None else b""
    return raw[:limit].decode("utf-8", errors="replace"), len(raw) > limit


def _exit_code(tar: tarfile.TarFile, member: tarfile.TarInfo) -> int | None:
    text, _ = _text(tar, member, 16)
    try:
        return int(text.strip())
    except ValueError:
        return None


def _output_path(name: str) -> PurePosixPath | None:
    """The path of a member under ``out/``, or None when it is anything else."""
    path = PurePosixPath(name.removeprefix("./"))
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        return None
    return path if path.parts[0] == OUTPUT_PREFIX else None


class _Collector:
    """The files of ``out/`` within every bound, and the reason for the others."""

    def __init__(self, limits: OutputLimits) -> None:
        self.limits = limits
        self.files: list[OutputFile] = []
        self.skipped: list[tuple[str, str]] = []
        self.taken: set[str] = set()
        self.total = 0
        #: The file being read when the stream ended, if it did.
        self.reading: str | None = None

    def offer(self, tar: tarfile.TarFile, member: tarfile.TarInfo, path: PurePosixPath) -> None:
        name = safe_file_name(path.name, self.taken)
        if not member.isreg():
            self.skipped.append((name, SKIP_NOT_A_FILE))
        elif len(self.files) >= self.limits.max_files:
            self.skipped.append((name, SKIP_TOO_MANY))
        elif (
            member.size > self.limits.max_file_bytes
            or self.total + member.size > self.limits.max_total_bytes
        ):
            self.skipped.append((name, SKIP_TOO_LARGE))
        else:
            self.reading = name
            handle = tar.extractfile(member)
            data = handle.read(member.size) if handle is not None else b""
            self.reading = None
            self.total += len(data)
            self.files.append(OutputFile(name=name, data=data))


def read_output(data: bytes, limits: OutputLimits) -> CommandOutput:
    """Read the tar the container handed back, trusting nothing in it.

    Args:
        data: What the sandbox wrote on stdout (already bounded by the caller).
        limits: What the run may bring back.

    Returns:
        The bounded output.

    Raises:
        UnreadableOutput: ``data`` is not a tar — not even its first member.
    """
    texts: dict[str, tuple[str, bool]] = {}
    exit_code: int | None = None
    collector = _Collector(limits)
    ceiling = (limits.max_files + 3) * _MEMBER_CEILING_FACTOR
    seen = 0
    incomplete = False
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            for member in tar:
                if seen >= ceiling:
                    # Not a run's output any more: what follows is stated unread.
                    incomplete = True
                    break
                seen += 1
                name = member.name.removeprefix("./")
                if name in (STDOUT_MEMBER, STDERR_MEMBER) and member.isreg():
                    texts[name] = _text(tar, member, limits.max_text_bytes)
                elif name == EXIT_CODE_MEMBER and member.isreg():
                    exit_code = _exit_code(tar, member)
                elif (path := _output_path(name)) is not None and not member.isdir():
                    collector.offer(tar, member, path)
    except tarfile.TarError as exc:
        if not seen:
            raise UnreadableOutput(str(exc)) from exc
        incomplete = True
        if collector.reading is not None:
            collector.skipped.append((collector.reading, SKIP_INCOMPLETE))
    stdout, stdout_cut = texts.get(STDOUT_MEMBER, ("", False))
    stderr, stderr_cut = texts.get(STDERR_MEMBER, ("", False))
    return CommandOutput(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_cut,
        stderr_truncated=stderr_cut,
        files=tuple(collector.files),
        skipped=tuple(collector.skipped),
        incomplete=incomplete,
    )
