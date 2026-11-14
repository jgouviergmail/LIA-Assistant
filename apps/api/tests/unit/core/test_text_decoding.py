"""What the bytes of a text file say (``core.text_decoding``).

A text file names no encoding. Read as UTF-8 with replacement, a spreadsheet
export from a French Windows desktop lost every accent to U+FFFD — in a
knowledge space's index and in a chat attachment's text alike. The door reads
UTF-8 when the bytes are UTF-8, Windows' own letters when they are not, and
never trades a whole text for one damaged byte.
"""

from __future__ import annotations

import codecs

import pytest

from src.core.text_decoding import decode_text

pytestmark = pytest.mark.unit

REPLACEMENT = "�"


class TestUtf8IsReadAsUtf8:
    def test_a_utf8_text_keeps_its_letters(self) -> None:
        assert decode_text("déjà vu — 您好 😀".encode()) == "déjà vu — 您好 😀"

    def test_plain_ascii_is_itself(self) -> None:
        assert decode_text(b"name,age\nAda,36\n") == "name,age\nAda,36\n"

    def test_nothing_reads_as_nothing(self) -> None:
        assert decode_text(b"") == ""

    def test_a_mark_is_no_letter(self) -> None:
        assert decode_text(codecs.BOM_UTF8 + b"hello") == "hello"


class TestAWindowsTextKeepsItsLetters:
    def test_a_french_export_keeps_its_accents(self) -> None:
        text = "prénom;âge;ville\nZoé;36;Besançon\n"

        assert decode_text(text.encode("cp1252")) == text

    def test_the_letters_windows_adds_to_latin1_are_read(self) -> None:
        # Curly quotes, the euro sign and the ellipsis live in the block Latin-1
        # leaves to control codes: reading it as Latin-1 would lose them.
        text = "« L’été » coûte 12 € … “vraiment”"

        assert decode_text(text.encode("cp1252")) == text

    def test_a_byte_windows_does_not_define_costs_one_letter_not_the_text(self) -> None:
        read = decode_text(b"caf\xe9 \x81 cr\xe8me")

        assert read == f"café {REPLACEMENT} crème"

    def test_a_single_accent_is_enough_to_tell(self) -> None:
        assert decode_text(b"Besan\xe7on") == "Besançon"


class TestATextMarkedAsUtf16:
    @pytest.mark.parametrize(
        ("mark", "encoding"),
        [(codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")],
    )
    def test_it_is_read_as_it_says(self, mark: bytes, encoding: str) -> None:
        assert decode_text(mark + "déjà vu".encode(encoding)) == "déjà vu"


class TestADamagedUtf8TextStaysUtf8:
    def test_one_stray_byte_never_turns_every_accent_into_two_wrong_letters(self) -> None:
        # Read as Windows' letters, every « é » of a UTF-8 text becomes « Ã© »:
        # one damaged byte must cost one letter, never the whole text.
        damaged = "été, forêt, garçon ".encode() + b"\xff" + " où ça ?".encode()

        read = decode_text(damaged)

        assert read == f"été, forêt, garçon {REPLACEMENT} où ça ?"

    def test_a_whole_file_that_ends_inside_a_letter_keeps_the_others(self) -> None:
        whole = "créé à Besançon, relu à Orléans".encode() + "é".encode()[:1]

        read = decode_text(whole)

        assert read == f"créé à Besançon, relu à Orléans{REPLACEMENT}"


class TestABeginningCutAtAByteBound:
    def test_a_letter_the_bound_cut_is_withheld(self) -> None:
        beginning = b"a" + "é".encode() * 3 + "é".encode()[:1]

        assert decode_text(beginning, cut=True) == "aééé"

    def test_the_cut_never_turns_the_text_into_another(self) -> None:
        beginning = ("é" * 1000).encode()[:-1]

        assert set(decode_text(beginning, cut=True)) == {"é"}

    def test_a_utf16_letter_the_bound_cut_is_withheld(self) -> None:
        beginning = (codecs.BOM_UTF16_LE + "😀😀".encode("utf-16-le"))[:-2]

        assert decode_text(beginning, cut=True) == "😀"

    def test_a_cut_windows_text_is_still_read(self) -> None:
        assert decode_text("déjà vu".encode("cp1252"), cut=True) == "déjà vu"
