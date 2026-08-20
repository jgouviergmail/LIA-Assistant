"""PAD → ElevenLabs voice_settings modulation (Lot 4-D4, ADR-237).

Pure math: arousal drives expressiveness (style up, stability down),
inside hard [0, 1] bounds, with a neutral dead-band so a flat mood never
jitters the voice. The admin's configured settings stay the BASE — the
mood bends them, it never replaces them.
"""

import pytest

from src.domains.voice.prosody import modulate_voice_settings


@pytest.mark.unit
class TestModulateVoiceSettings:
    def test_neutral_mood_returns_base_untouched(self):
        base = {"stability": 0.5, "style": 0.2}

        result = modulate_voice_settings(base, pleasure=0.05, arousal=0.05)

        assert result == base

    def test_high_arousal_raises_style_and_lowers_stability(self):
        base = {"stability": 0.5, "style": 0.2}

        result = modulate_voice_settings(base, pleasure=0.3, arousal=0.8)

        assert result["style"] > 0.2
        assert result["stability"] < 0.5

    def test_low_arousal_calms_the_voice(self):
        base = {"stability": 0.5, "style": 0.4}

        result = modulate_voice_settings(base, pleasure=-0.2, arousal=-0.8)

        assert result["style"] < 0.4
        assert result["stability"] > 0.5

    def test_outputs_stay_inside_hard_bounds(self):
        base = {"stability": 0.95, "style": 0.95}

        calm = modulate_voice_settings(base, pleasure=0.0, arousal=-1.0)
        excited = modulate_voice_settings(base, pleasure=0.0, arousal=1.0)

        for result in (calm, excited):
            assert 0.0 <= result["stability"] <= 1.0
            assert 0.0 <= result["style"] <= 1.0

    def test_unknown_base_keys_are_preserved(self):
        base = {"stability": 0.5, "style": 0.0, "similarity_boost": 0.9}

        result = modulate_voice_settings(base, pleasure=0.0, arousal=0.6)

        assert result["similarity_boost"] == 0.9

    def test_missing_base_keys_use_provider_defaults(self):
        result = modulate_voice_settings({}, pleasure=0.0, arousal=0.9)

        assert 0.0 <= result["stability"] <= 1.0
        assert result["style"] > 0.0

    def test_base_dict_is_never_mutated(self):
        base = {"stability": 0.5, "style": 0.2}

        modulate_voice_settings(base, pleasure=0.0, arousal=0.9)

        assert base == {"stability": 0.5, "style": 0.2}
