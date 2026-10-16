"""Fish Audio: speech synthesis, transcription and the voice library (ADR-345).

One vendor, several surfaces, one account allowance: every request any module
here sends takes a slot of :mod:`src.domains.voice.provider_capacity`'s
``fishaudio`` pool, because the vendor counts synthesis, transcription and
voice design against the same concurrency limit.
"""
