"""The Telegram voice PCM conversion chain survives the interpreter migration.

`pydub` imports the stdlib `audioop` module, removed in Python 3.13: on 3.13+ the whole
voice path used to die at import time with no test signal (audited 2026-07-29 — the suite
was green while `import pydub` was broken on the host venv; closed by ADR-241). These
tests exercise the exact audioop-backed operations `_ogg_to_pcm_float`
(src/infrastructure/channels/telegram/voice.py) applies after ffmpeg decoding
(48 kHz stereo → 16 kHz mono 16-bit), hermetically — no ffmpeg, no network.
"""

from __future__ import annotations


def test_pydub_imports_with_audioop() -> None:
    """The historical failure mode: ModuleNotFoundError at pydub import on 3.13+."""
    import audioop
    from pydub import AudioSegment

    assert callable(audioop.ratecv)
    assert AudioSegment is not None


def test_resample_chain_to_stt_format() -> None:
    """48 kHz stereo 16-bit → 16 kHz mono 16-bit, the exact chain of _ogg_to_pcm_float."""
    from pydub import AudioSegment

    # 50 ms of synthetic 48 kHz STEREO 16-bit audio (what Telegram OGG decodes to):
    # frame = 2 channels x 2 bytes; 2400 frames.
    frames = 2400
    seg = AudioSegment(
        data=b"\x00\x10\x00\xf0" * frames, sample_width=2, frame_rate=48000, channels=2
    )

    pcm = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    assert pcm.frame_rate == 16000
    assert pcm.channels == 1
    assert pcm.sample_width == 2
    # ratecv keeps duration: 2400 frames at 48 kHz -> ~800 frames at 16 kHz.
    assert abs(pcm.frame_count() - frames / 3) <= 2
    # raw_data is what the module converts to float samples: 2 bytes per mono frame.
    assert len(pcm.raw_data) == int(pcm.frame_count()) * 2
