"""One bounded, credential-safe generation of the original LIA film score.

Run `preflight` to inspect model availability without generation. Run `generate`
only after the human has requested paid music generation. A checkpoint prevents
an ambiguous or failed request from being repeated. No credentials are persisted.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

from dotenv import dotenv_values

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
DESTINATION = PROJECT / "public/audio/v5"
MODEL = "lyria-3.5"
API_ORIGIN = "https://generativelanguage.googleapis.com"
PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"
TERMS_URL = "https://ai.google.dev/gemini-api/terms"
GUIDE_URL = "https://ai.google.dev/gemini-api/docs/music-generation"

PROMPT = """Compose one complete ORIGINAL instrumental soundtrack for LIA, a warm,
capable personal AI assistant with a friendly little robot mascot named BIP.
This is a premium product film, graceful and human, optimistic without hype.
Duration: exactly 2 minutes 40 seconds (160 seconds). One continuous composed
piece, not a short loop repeated. Instrumental ONLY: absolutely no singing,
spoken voice, lyrics, humming, vocal chops or choir at any point.

Musical direction: elegant contemporary pop with a light soulful funk groove,
118 BPM, steady 4/4, warm major-key harmony with tasteful sixths and ninths.
A genuinely memorable, singable melodic theme played by warm piano and Rhodes,
clean electric guitar answers, round electric bass with small syncopated fills,
organic soft kick and rounded snare, restrained smooth closed hi-hat. A brief
three-note piano motif introduces BIP, returns only at meaningful story beats
and develops into a fresh longer melody. Human musical phrasing, breathing
space, satisfying chord movement, melody carried across instruments. Modern,
polished stereo production with clean low end and comfortable upper mids.
The listener should enjoy the whole piece independently of the images.

Keep momentum and a clearly audible pulse for motion editing, but no incessant
staccato ostinato, shrill percussion, hard claps, metallic clicks, ukulele,
pizzicato marimba loop, EDM riser, aggressive sidechain, dramatic anxiety,
glitch effects, logo sound effects or overbearing synthetic lead. No loud
crashes or mechanical ticking. Do not imitate or quote any artist or song.
Give the theme melodic variations, contrasting sections and real harmonic
development. Avoid repeating an eight-bar riff throughout. Maintain the same
tempo and an audible beat across changes; avoid silence before the ending.

[0:00 - 0:04] Opening: immediately welcoming piano pickup, short BIP motif,
round bass and a soft groove entering by the second bar. An assured beginning.
[0:04 - 0:14] Animated companions: playful clean guitar conversation with the
piano melody, small warm bass response; delightful but tasteful.
[0:14 - 0:21] Personal display: open the texture, smooth Rhodes counter-melody,
steady restrained drums. A graceful breathing space, no loss of momentum.
[0:21 - 0:44] The daily flow: warm full band, first complete lyrical piano
theme, attractive bass groove and guitar answers. Develop a fresh phrase in
the second half instead of repeating the same pattern.
[0:44 - 1:19] Prepare a meeting and work together: a contrasting B melody,
guitar carrying the tune then handing it to piano; richer harmony and gentle
drum fills at phrase ends. Calm confidence, purposeful forward motion.
[1:19 - 2:04] Move projects and knowledge forward: a melodic bridge with
Rhodes and piano interplay, then return to the main theme with new voicing
and a fuller bass line. Gradual, musical rise; never frantic or crowded.
[2:04 - 2:16] Administration and platform health: slightly leaner arrangement,
clean rhythmic pocket, lower piano register and a reassuring melody variation.
[2:16 - 2:26] Retain control: warm harmonic lift, full elegant melody returning,
steady bass and drums, clear and trustworthy rather than epic or suspenseful.
[2:26 - 2:30] Brand resolution: joyful, concise main-theme cadence with the
BIP piano motif as a musical answer, naturally resolving by 2:30.
[2:30 - 2:40] Usable musical tail: continue the gentle groove with a short
new melodic answer, then end with a clean resolved piano/Rhodes chord and
natural resonance. No abrupt cut. End the complete piece at 2:40.
"""

FUNK_PROMPT = """Compose a complete ORIGINAL instrumental nu-funk / modern live
disco-funk track, exactly 2 minutes 40 seconds (160 seconds), for the high-energy
LIA product film. This is compelling FOREGROUND music, a confident real-band
groove that is enjoyable on its own. Not corporate background music. Not lounge
or elevator music. Immediate momentum and rhythmic personality, danceable but
classy. Instrumental ONLY: no voice, singing, humming, chants, lyrics, speech,
vocal samples, chopped vocals, whistle, choir or wordless vocal at any moment.

Tempo 134 BPM throughout, 4/4. Put a deep rounded syncopated electric bass line
up front as the engine of the piece: lively fingerstyle groove, tasteful octave
responses, little melodic bass fills and strong warm low end. Punchy organic
acoustic drums with a tight kick, decisive rounded snare on 2 and 4, crisp but
non-harsh controlled sixteenth hi-hat. Clean electric guitar plays syncopated
muted funk strums, percussive rhythmic chords and soulful melodic answers.
Rhodes is SUPPORT ONLY: warm occasional chord stabs, never a piano-led lounge
melody or noodling smooth-jazz solo. Lead melody is a warm singing clean-guitar
line: short memorable phrases, then fresh answers and variation. No shrill
brass/sax repetition. A brief three-note guitar motif suggests friendly robot
mascot BIP, used sparingly as punctuation, never an incessant hook.

Cool minor / Dorian harmony opening, confident rhythmic tension without anxiety,
then a warmly uplifting major-key turn in later sections. Real melodic and
harmonic development, changing phrasing every eight bars, rhythmic breaks and
exciting band re-entries around sixteen-bar boundaries. Alternate guitar lead,
bass-led passages and fuller band answers. Do not repeat an eight-bar stock
riff throughout. Clear forward pulse remains audible in the leaner passages.
Tasteful melodic space: the melody should be enjoyable, not nagging, overly
bright, over-busy or continuously repeated. Modern polished stereo production,
solid bass, energetic transients, comfortable mids, natural dynamic contrast.
No elevator/lounge/smooth jazz, corporate piano bed, ukulele, marimba loop,
ticking percussion, strident hats, EDM drops, risers, aggressive distortion,
big synth wall, anxiety or trailer bombast. No artist imitation or song quote.

One uninterrupted coherent composition with five distinct musical movements
and seamless composed transitions. No copy/paste loop. Exact total 160 seconds.
[0:00 - 0:04] Start immediately with tight DRUMS AND UPFRONT BASS, then muted
guitar reply. Strong rhythm from the first second, not a soft piano introduction.
[0:04 - 0:21] Meet the animated companions and personal display: lively bass
groove, guitar motif then a different melodic answer, cheeky tasteful band fills.
[0:21 - 0:44] Daily flow: first complete soulful guitar melody over a confident
full-band pocket. Change the bass and melodic phrase in the second half.
[0:44 - 1:19] Meeting and teamwork movement: brief rhythmic break then clean
re-entry, contrasting guitar melody and new chord movement, energetic drums,
bass-led response around 1:00. Funk attitude, no smooth-jazz detour.
[1:19 - 2:04] Projects and knowledge movement: lean bass-and-guitar bridge with
a new rhythmic pattern, then a fuller major-key lift and a developed new melody.
One or two well-placed band stops/re-entries, never an EDM build. Keep groove.
[2:04 - 2:16] Administration: tight confident bass-led pocket, reduced lead
density, quick new guitar response. Keep the drums punchy and tempo constant.
[2:16 - 2:26] Retain control: warm major-key full-band reprise with DIFFERENT
melodic phrasing, joyful confidence and strong low end, not epic or anxious.
[2:26 - 2:30] LIA brand resolution: a concise satisfying cadence, short BIP
guitar motif answering the bass, musically resolved by 2:30.
[2:30 - 2:40] Continue an enjoyable new bass/guitar phrase as a usable musical
tail, then a clean composed band ending with natural resonance at exactly 2:40.
"""

ELECTRO_PROMPT = """STRICT INSTRUMENT PALETTE: SYNTHESIZERS, SYNTH BASS, ELECTRONIC
DRUM MACHINE and quiet MUTED RHYTHM GUITAR ONLY. NO SAXOPHONE whatsoever.
NO sax-like or breathy reed lead, NO brass, NO horns, NO trumpets, NO trombones,
NO woodwinds, NO flute, NO clarinet, NO wind instruments. NO vocals, singing,
humming, vocal samples, chopped voices, chants, speech or choir anywhere.
All lead melodies must be plainly ELECTRONIC ANALOG POLYSYNTH tones, with a
rounded low-pass sound in the comfortable middle register. This restriction
applies to the ENTIRE 160-second composition, including fills and the outro.

Create one complete ORIGINAL instrumental ELECTRO-FUNK track for LIA, exactly
2 minutes 40 seconds. Confident modern rhythmic character, warm but energetic,
compelling foreground music that is enjoyable on its own. Keep the attitude
and momentum of a punchy funk groove, now with genuinely ELECTRONIC production.
134 BPM, steady 4/4. Modern tight drum-machine kick and snare drive a decisive
funk backbeat. Controlled sixteenth closed hi-hats, a restrained soft clap,
occasional small electronic tom fills. No harsh treble or metallic ticking.

UPFRONT warm rounded analog SYNTH BASS carries the groove: deep punchy attack,
syncopated short and held notes, octave answers, tasteful melodic bass fills.
Strong clean low end and clear rhythmic momentum from the first second.
The melody comes ONLY from a warm rounded ANALOG POLYSYNTH lead: soft square,
triangle and low-pass saw-wave character, understated portamento, expressive
electronic envelopes, never a sampled horn or sax timbre. Gently syncopated
electronic chord stabs and a small synth-clav texture support the rhythm.
Muted clean guitar contributes discreet percussive chops, never a lead solo.

Musically rich but uncluttered: short melodic phrases with fresh answers,
varying voicing and harmony every eight bars, contrasting bass-led and synth-
led passages, deliberate tight breaks and band re-entry every sixteen bars.
The melody develops instead of a constant nagging hook. A tiny three-note
synth motif for robot mascot BIP returns sparingly, with different endings.
Cool minor / Dorian harmony opens the track; later sections turn to a warm
major uplift, self-assured and playful. Comfortable mids, clean stereo mix,
modern precise transients, solid bass, some genuine dynamic contrast.

This is ELECTRO-FUNK, NOT jazz, jazz-funk, smooth lounge, elevator music,
muzak, corporate piano, acoustic disco or a soft background bed. NO piano,
no lounge Rhodes lead, no ukulele, marimba, harp or shrill repetitive ostinato.
No EDM festival drops, huge synth wall, harsh distortion, aggressive risers,
anxiety, epic trailer build or clichéd corporate finale. No artist imitation,
no song quotation. The piece must sound modern, rhythmic, funky and melodic.

One continuous coherent composed track, no copied eight-bar loop. Five distinct
movements connected seamlessly. SYNTH LEAD ONLY throughout. NO SAX / WINDS.
[0:00 - 0:04] Immediately punchy ELECTRONIC DRUMS and prominent SYNTH BASS;
short muted-guitar rhythmic reply and the compact BIP synth motif.
[0:04 - 0:21] Lively bass-led electro-funk pocket, first warm synth melody,
then a fresh contrasting phrase; playful drum-machine fills kept restrained.
[0:21 - 0:44] Fuller synth-and-bass groove, melody developing in new phrases,
cool harmonic turn, clean muted guitar chops underneath, no repeating hook.
[0:44 - 1:19] Tight rhythmic stop and re-entry, contrasting analog synth melody,
then a lean bass-led middle section with electronic chord-stab answers.
[1:19 - 2:04] New rhythmic pattern and developed synth lead, major-key lift,
fuller electronic groove, small deliberate breaks and satisfying re-entries.
[2:04 - 2:16] Bass-led pocket with less lead density, new synth chord voicing,
same solid electronic backbeat, confident clear rhythmic energy.
[2:16 - 2:26] Warm uplifting reprise with NEW melodic phrasing and bass fills,
never repetitive or overbearing; distinct analog synth tone, no horn timbre.
[2:26 - 2:30] Concise composed brand cadence, short BIP synth motif answering
the bass, satisfying harmonic resolution at 2:30 without stopping the groove.
[2:30 - 2:40] Usable tail: a new short synth/bass phrase, then a clean electronic
band ending with natural synth resonance at exactly 2:40. No voice or wind.
"""


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def credentials() -> tuple[str, str]:
    values = dotenv_values(ROOT / ".env")
    for name in ("GOOGLE_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = values.get(name)
        if key:
            return name, key
    raise RuntimeError("No existing Google API credential is configured")


def request_json(
    endpoint: str, key: str, payload: object | None = None
) -> tuple[dict, dict]:
    encoded = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_ORIGIN + endpoint,
        data=encoded,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            document = json.loads(response.read())
            headers = {
                name: response.headers.get(name)
                for name in ("x-request-id", "x-goog-request-id", "date")
                if response.headers.get(name)
            }
            return document, headers
    except urllib.error.HTTPError as error:
        # API diagnostics are intentionally reduced; never echo a URL, key,
        # request headers, raw response body or account identifiers.
        diagnostic = {"httpStatus": error.code}
        try:
            body = json.loads(error.read())
            diagnostic["apiStatus"] = body.get("error", {}).get("status")
        except (ValueError, AttributeError):
            pass
        raise ApiFailure(diagnostic) from None


class ApiFailure(Exception):
    def __init__(self, diagnostic: dict):
        super().__init__("Provider rejected the music request")
        self.diagnostic = diagnostic


def audio_blocks(document: dict) -> tuple[list[dict], list[str]]:
    audio, text = [], []
    for step in document.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "audio" and block.get("data"):
                audio.append(block)
            elif block.get("type") == "text":
                text.append(block.get("text", ""))
    return audio, text


def preflight(key: str) -> dict:
    document, _ = request_json("/v1beta/models?pageSize=1000", key)
    models = [
        model["name"]
        for model in document.get("models", [])
        if "lyria" in model.get("name", "").lower()
    ]
    return {
        "credentialPresent": True,
        "musicModelsListed": models,
        "requestedModel": MODEL,
        "publishedGenerationPriceUsd": 0.08,
        "pricingSource": PRICING_URL,
        "paidGenerationRequests": 0,
    }


def generate(
    key: str, funk_revision: bool = False, electro_revision: bool = False
) -> None:
    prefix = (
        "lia-electrofunk"
        if electro_revision
        else "lia-funk" if funk_revision else "lia-custom"
    )
    title = (
        "LIA — ElectroFunk"
        if electro_revision
        else (
            "LIA — Le groove en mouvement"
            if funk_revision
            else "LIA — Une journée en harmonie"
        )
    )
    attempt = DESTINATION / f"{prefix}-generation-attempt.json"
    if attempt.exists():
        checkpoint = json.loads(attempt.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": "existing_attempt_not_repeated",
                    "previousStatus": checkpoint.get("status"),
                    "checkpoint": str(attempt.relative_to(ROOT)),
                }
            )
        )
        return
    DESTINATION.mkdir(parents=True, exist_ok=True)
    if funk_revision or electro_revision:
        # Every revision is a separately human-requested take, not a retry.
        # Earlier audio, mixes, requests and evidence keep their unique names.
        previous_take = 2 if electro_revision else 1
        for source, target in (
            (
                PROJECT / "src/music-v5.json",
                f"take{previous_take}-selected-record.json",
            ),
            (PROJECT / "src/music-film.json", f"take{previous_take}-music-film.json"),
            (DESTINATION / "LICENSE.md", f"take{previous_take}-LICENSE.md"),
        ):
            destination = DESTINATION / target
            if source.exists() and not destination.exists():
                destination.write_bytes(source.read_bytes())
    payload = {
        "model": MODEL,
        "input": (
            ELECTRO_PROMPT
            if electro_revision
            else FUNK_PROMPT if funk_revision else PROMPT
        ),
        "response_format": {"type": "audio"},
        "store": False,
    }
    write_json(DESTINATION / f"{prefix}-composition-request.json", payload)
    started = datetime.now(timezone.utc).isoformat()
    checkpoint = {
        "status": "dispatched",
        "startedAt": started,
        "provider": "Google Gemini API",
        "model": MODEL,
        "publishedGenerationPriceUsd": 0.08,
        "invoiceVerified": False,
        "pricingSource": PRICING_URL,
        "paidGenerationAttempts": 1,
        "humanRequestedTake": 3 if electro_revision else 2 if funk_revision else 1,
        "automaticRetries": 0,
        "credentialPersisted": False,
    }
    write_json(attempt, checkpoint)
    print(
        json.dumps({"status": "generating", "model": MODEL, "attempts": 1}), flush=True
    )
    timer = time.monotonic()
    try:
        response, headers = request_json("/v1beta/interactions", key, payload)
    except ApiFailure as error:
        checkpoint.update(status="rejected", **error.diagnostic)
        write_json(attempt, checkpoint)
        print(json.dumps(checkpoint), flush=True)
        return
    except Exception as error:
        checkpoint.update(status="outcome_unknown", errorType=type(error).__name__)
        write_json(attempt, checkpoint)
        print(json.dumps(checkpoint), flush=True)
        return
    blocks, structural_text = audio_blocks(response)
    if len(blocks) != 1:
        checkpoint.update(
            status="response_without_single_audio",
            responseStatus=response.get("status"),
            audioBlockCount=len(blocks),
            interactionId=response.get("id"),
        )
        write_json(attempt, checkpoint)
        print(json.dumps(checkpoint), flush=True)
        return
    generated = base64.b64decode(blocks[0]["data"], validate=True)
    mime = blocks[0].get("mime_type", "")
    extension = ".wav" if generated[:4] == b"RIFF" else ".mp3"
    original = DESTINATION / (
        f"LIA-ElectroFunk{extension}"
        if electro_revision
        else f"{prefix}-original{extension}"
    )
    original.write_bytes(generated)
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(original),
            ],
            text=True,
        )
    )
    streams = [item for item in probe["streams"] if item.get("codec_type") == "audio"]
    if len(streams) != 1:
        raise RuntimeError("The provider output is not one valid audio stream")
    native = streams[0]
    source_duration = float(probe["format"]["duration"])
    source_sha = hashlib.sha256(generated).hexdigest()
    metadata = {
        **checkpoint,
        "status": "generated",
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "elapsedSeconds": round(time.monotonic() - timer, 3),
        "interactionId": response.get("id"),
        "requestHeaders": headers,
        "usage": response.get("usage"),
        "providerRequestIdentifierAvailable": bool(
            response.get("id")
            or headers.get("x-request-id")
            or headers.get("x-goog-request-id")
        ),
        "reportedMimeType": mime,
        "sourceAudio": original.name,
        "sourceBytes": len(generated),
        "sourceSha256": source_sha,
        "sourceAudioFormat": {
            key: native.get(key)
            for key in (
                "codec_name",
                "sample_fmt",
                "sample_rate",
                "channels",
                "bits_per_sample",
                "bit_rate",
            )
        },
        "sourceDurationSeconds": source_duration,
        "generationGuide": GUIDE_URL,
        "termsSource": TERMS_URL,
        "termsQualification": "Google does not claim ownership of generated content; API terms apply. No Creative Commons licence or exclusive copyright is asserted.",
        "instrumentalRequested": True,
        "humanAudioAudition": False,
        "structuralText": structural_text,
        "generationMode": "single-turn original composition; audio remix/editing is not supported by Lyria 3.5",
        "forbiddenInstrumentsRequested": (
            ["saxophone", "sax-like lead", "brass", "woodwinds", "voice"]
            if electro_revision
            else ["voice"]
        ),
    }
    write_json(DESTINATION / f"{prefix}-generation.json", metadata)
    checkpoint.update(
        status="generated", interactionId=response.get("id"), sourceSha256=source_sha
    )
    write_json(attempt, checkpoint)
    if source_duration < 150:
        print(
            json.dumps(
                {
                    "status": "generated_too_short_for_film",
                    "durationSeconds": source_duration,
                }
            ),
            flush=True,
        )
        return
    selected_path = PROJECT / "src/music-v5.json"
    if selected_path.exists():
        previous = json.loads(selected_path.read_text(encoding="utf-8"))
        if previous.get("id") != "lia-original-score":
            write_json(DESTINATION / "previous-selected-record.json", previous)
    duration = min(160.0, int(source_duration * 1000) / 1000)
    selected = {
        "id": "lia-original-score",
        "title": title,
        "artist": "Composition originale LIA · Google Lyria",
        "provider": "Google Gemini API",
        "model": MODEL,
        "source": GUIDE_URL,
        "sourceSha256": source_sha,
        "publishedTempoBpm": 134 if funk_revision or electro_revision else 118,
        "tempoIsPromptTarget": True,
        "attribution": f"{title} · composition sur mesure générée avec Google Lyria 3.5",
        "styleSource": (
            "Original electro-funk: upfront analog synth bass, tight electronic drums, rounded middle-register analog polysynth lead, discreet muted rhythm guitar; sax/brass/woodwinds/voice forbidden in the prompt. Continuous 160-second composition requested."
            if electro_revision
            else (
                "Original high-energy nu-funk/disco-funk with upfront syncopated bass, punchy live drums, clean funk guitar and developed non-repetitive melody; continuous 160-second composition requested."
                if funk_revision
                else "Original instrumental piano/Rhodes, clean guitar, warm bass and restrained organic pop/funk drums; continuous 160-second composition requested."
            )
        ),
        "license": "Google Gemini API generated-content terms",
        "licenseUrl": TERMS_URL,
        "sourceFormat": metadata["sourceAudioFormat"],
        "originalAudio": f"audio/v5/{original.name}",
        "workingAudio": (
            "audio/v5/LIA-ElectroFunk-film.wav"
            if electro_revision
            else f"audio/v5/{prefix}-film.wav"
        ),
        "allowanceSeconds": duration,
        "generationMetadata": f"audio/v5/{prefix}-generation.json",
        "compositionRequest": f"audio/v5/{prefix}-composition-request.json",
    }
    write_json(selected_path, selected)
    print(
        json.dumps(
            {
                "status": "selected",
                "durationSeconds": duration,
                "nativeFormat": metadata["sourceAudioFormat"],
                "sourceSha256": source_sha,
            }
        ),
        flush=True,
    )


def preserve_public_evidence() -> None:
    """Snapshot the provider's public terms and prices without credentials."""
    DESTINATION.mkdir(parents=True, exist_ok=True)
    evidence = []
    for label, url in (
        ("google-gemini-terms", TERMS_URL),
        ("google-lyria-pricing", PRICING_URL),
        ("google-lyria-guide", GUIDE_URL),
    ):
        request = urllib.request.Request(
            url, headers={"User-Agent": "LIA production evidence"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
        path = DESTINATION / f"{label}.html"
        path.write_bytes(content)
        evidence.append(
            {
                "source": url,
                "file": path.name,
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    write_json(DESTINATION / "lia-custom-provider-evidence.json", evidence)
    print(
        json.dumps(
            {"publicEvidenceSaved": len(evidence), "credentialSentToPublicPages": False}
        ),
        flush=True,
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "preflight"
    if mode not in {
        "preflight",
        "generate",
        "generate-funk",
        "generate-electro",
        "evidence",
    }:
        raise ValueError(
            "Use preflight, generate, generate-funk, generate-electro or evidence"
        )
    if mode == "evidence":
        preserve_public_evidence()
        return
    _, key = credentials()
    if mode == "preflight":
        print(json.dumps(preflight(key)), flush=True)
    else:
        generate(
            key,
            funk_revision=mode == "generate-funk",
            electro_revision=mode == "generate-electro",
        )


if __name__ == "__main__":
    try:
        main()
    except ApiFailure as error:
        print(json.dumps({"status": "preflight_rejected", **error.diagnostic}))
        sys.exit(1)
    except Exception as error:
        # Never include exception text: networking libraries may repeat URLs
        # and credentials. Original audio and attempt records remain intact.
        print(json.dumps({"status": "stopped", "errorType": type(error).__name__}))
        sys.exit(1)
