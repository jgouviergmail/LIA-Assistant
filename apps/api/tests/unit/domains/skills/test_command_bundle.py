"""What travels into a skill command's sandbox, and what may come back (ADR-327 lot 2).

The skill folder and the turn's files go in as ONE tar on stdin; the command's
output comes back as ONE tar on stdout. Everything read back was written by the
command — code a third party may have written — so the reader trusts nothing:
it bounds the count, the sizes and the names, and keeps regular files only.
"""

from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

import pytest

from src.domains.skills.command_bundle import (
    BundleTooLarge,
    InputFile,
    OutputLimits,
    UnreadableOutput,
    pack_bundle,
    read_output,
    safe_file_name,
)

pytestmark = pytest.mark.unit

_LIMITS = OutputLimits(max_text_bytes=16, max_files=2, max_file_bytes=10, max_total_bytes=14)


def _skill(tmp_path: Path) -> Path:
    folder = tmp_path / "pdf"
    (folder / "scripts").mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: pdf\n---\nbody", encoding="utf-8")
    (folder / "scripts" / "fill.py").write_text("print('x')", encoding="utf-8")
    return folder


def _members(data: bytes) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return {m.name: m for m in tar.getmembers()}


def _output(files: dict[str, bytes], *, extra: list[tarfile.TarInfo] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info in extra or []:
            tar.addfile(info)
    return buffer.getvalue()


class TestPackBundle:
    def test_the_skill_folder_and_the_inputs_travel_as_one_tar(self, tmp_path: Path) -> None:
        upload = tmp_path / "stored-uuid.pdf"
        upload.write_bytes(b"%PDF-1.7")
        data = pack_bundle(
            _skill(tmp_path),
            [InputFile(name="form.pdf", path=upload, size=8)],
            max_bytes=1_000,
        )
        members = _members(data)
        assert set(members) >= {"skill/SKILL.md", "skill/scripts/fill.py", "input/form.pdf"}
        # Executable, so a shebang script runs as `./scripts/x.sh` in the copy.
        assert members["skill/scripts/fill.py"].mode == 0o755
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            extracted = tar.extractfile("input/form.pdf")
            assert extracted is not None
            assert extracted.read() == b"%PDF-1.7"

    def test_links_and_build_debris_never_travel(self, tmp_path: Path) -> None:
        folder = _skill(tmp_path)
        (folder / "__pycache__").mkdir()
        (folder / "__pycache__" / "x.pyc").write_bytes(b"\0")
        secret = tmp_path / "outside.txt"
        secret.write_text("host file", encoding="utf-8")
        try:
            os.symlink(secret, folder / "link.txt")
        except OSError:
            pytest.skip("symlinks need a privilege this host does not grant")
        members = _members(pack_bundle(folder, [], max_bytes=1_000))
        assert "skill/link.txt" not in members
        assert not any("__pycache__" in name for name in members)

    def test_a_bundle_over_its_budget_is_refused_before_anything_is_read(
        self, tmp_path: Path
    ) -> None:
        upload = tmp_path / "big.bin"
        upload.write_bytes(b"x" * 64)
        with pytest.raises(BundleTooLarge):
            pack_bundle(
                _skill(tmp_path), [InputFile(name="big.bin", path=upload, size=64)], max_bytes=50
            )


class TestSafeFileName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("../../etc/passwd", "passwd"),
            ("C:\\Users\\me\\report.pdf", "report.pdf"),
            (".hidden", "hidden"),
            ("a b\x00c.txt", "a bc.txt"),
            ("", "file"),
            ("..", "file"),
        ],
    )
    def test_a_name_is_a_plain_basename(self, raw: str, expected: str) -> None:
        assert safe_file_name(raw, set()) == expected

    def test_a_long_name_keeps_its_extension(self) -> None:
        name = safe_file_name("x" * 300 + ".pdf", set())
        assert name.endswith(".pdf") and len(name) <= 120

    def test_a_name_never_reads_as_an_option(self) -> None:
        assert safe_file_name("--help.pdf", set()) == "help.pdf"

    def test_a_second_file_of_the_same_name_is_numbered(self) -> None:
        taken: set[str] = set()
        assert safe_file_name("a.pdf", taken) == "a.pdf"
        assert safe_file_name("a.pdf", taken) == "a (2).pdf"
        assert safe_file_name("A.PDF", taken) == "A (3).PDF"


class TestReadOutput:
    def test_text_exit_code_and_files_are_read(self) -> None:
        output = read_output(
            _output(
                {
                    "stdout": b"done",
                    "stderr": b"",
                    "exit_code": b"0\n",
                    "out/report.pdf": b"%PDF",
                }
            ),
            _LIMITS,
        )
        assert (output.exit_code, output.stdout, output.stderr) == (0, "done", "")
        assert [(f.name, f.data) for f in output.files] == [("report.pdf", b"%PDF")]
        assert output.skipped == ()

    def test_text_past_its_bound_is_cut_and_says_so(self) -> None:
        output = read_output(_output({"stdout": b"x" * 40, "exit_code": b"1"}), _LIMITS)
        assert len(output.stdout) == _LIMITS.max_text_bytes
        assert output.stdout_truncated

    def test_every_file_past_a_bound_is_named_never_dropped_in_silence(self) -> None:
        output = read_output(
            _output(
                {
                    "exit_code": b"0",
                    "out/a.txt": b"12345",
                    # Past the per-file bound.
                    "out/big.bin": b"x" * 11,
                    # Within it, but past what the run may bring back in all.
                    "out/b.txt": b"x" * 10,
                    "out/c.txt": b"x" * 9,
                    # Past the count.
                    "out/d.txt": b"1",
                }
            ),
            _LIMITS,
        )
        assert [f.name for f in output.files] == ["a.txt", "c.txt"]
        assert dict(output.skipped) == {
            "big.bin": "too_large",
            "b.txt": "too_large",
            "d.txt": "too_many",
        }

    def test_only_regular_files_under_out_come_back(self) -> None:
        link = tarfile.TarInfo("out/secret")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        output = read_output(
            _output(
                {"exit_code": b"0", "../escape": b"x", "/abs": b"x", "elsewhere": b"x"},
                extra=[link],
            ),
            _LIMITS,
        )
        assert output.files == ()
        assert dict(output.skipped) == {"secret": "not_a_file"}

    def test_a_nested_file_keeps_its_basename_numbered_on_a_clash(self) -> None:
        output = read_output(
            _output({"exit_code": b"0", "out/a/c.txt": b"1", "out/b/c.txt": b"2"}), _LIMITS
        )
        assert [f.name for f in output.files] == ["c.txt", "c (2).txt"]

    def test_a_missing_or_unreadable_exit_code_is_none(self) -> None:
        assert read_output(_output({"stdout": b""}), _LIMITS).exit_code is None
        assert read_output(_output({"exit_code": b"zero"}), _LIMITS).exit_code is None

    def test_bytes_that_are_not_a_tar_are_refused(self) -> None:
        with pytest.raises(UnreadableOutput):
            read_output(b"not a tar at all" * 64, _LIMITS)

    def test_a_cut_stream_keeps_what_was_read_and_names_what_was_not(self) -> None:
        # The sandbox's output is read under a ceiling: past it, the stream
        # ends mid-member. What came before stays; the rest is stated.
        whole = _output({"stdout": b"ok", "exit_code": b"0", "out/big.txt": b"y" * 9})
        cut = whole[: whole.index(b"y" * 9) + 3]
        output = read_output(cut, _LIMITS)
        assert (output.stdout, output.exit_code, output.incomplete) == ("ok", 0, True)
        assert output.files == ()
        assert dict(output.skipped) == {"big.txt": "incomplete"}

    def test_members_past_the_ceiling_are_stated_as_unread(self) -> None:
        # A run writing thousands of files is not read to its end: the output
        # says what followed was not read, rather than falling silent.
        files = {f"out/f{i}.txt": b"1" for i in range(200)}
        output = read_output(_output({"exit_code": b"0", **files}), _LIMITS)
        assert output.incomplete
        assert len(output.files) == _LIMITS.max_files

    def test_a_whole_stream_is_complete(self) -> None:
        assert not read_output(_output({"exit_code": b"0"}), _LIMITS).incomplete
