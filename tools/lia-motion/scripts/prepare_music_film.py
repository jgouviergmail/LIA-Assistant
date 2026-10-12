"""Prepare the selected generated or licensed score without looping it."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path.insert(0, str(ROOT))
from scripts.assets.encode_landing_video import (  # noqa: E402
    BEAT_ANALYSIS_VERSION,
    ONSET_LEAD_MS,
    beat_map,
)

selected = json.loads((PROJECT / "src/music-v5.json").read_text(encoding="utf-8"))
duration = selected["allowanceSeconds"]
original = PROJECT / "public" / selected["originalAudio"]
if hashlib.sha256(original.read_bytes()).hexdigest() != selected["sourceSha256"]:
    raise ValueError("Selected source recording fingerprint changed")
audio = PROJECT / "public" / selected["workingAudio"]
destination = audio.parent
destination.mkdir(parents=True, exist_ok=True)
subprocess.run(
    [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(original),
        "-af",
        f"atrim=start=0:end={duration},asetpts=PTS-STARTPTS,volume=-6dB",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s24le",
        str(audio),
    ],
    check=True,
)
probe = json.loads(
    subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio),
        ],
        text=True,
    )
)
if abs(float(probe["format"]["duration"]) - duration) > 0.001:
    raise ValueError("Soundtrack excerpt is shorter than the film allowance")
beats, analysis = beat_map(audio)
if not beats or analysis["onset_hit_rate"] < 0.9:
    raise ValueError("The soundtrack does not have reliable measured pulses")
if any(not 0 <= entry[0] < duration * 1000 for entry in beats):
    raise ValueError("A measured accent falls outside the soundtrack")
record = {
    **selected,
    "audio": selected["workingAudio"],
    "durationSeconds": duration,
    "audioSha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
    "edit": {
        "trimFrom": 0,
        "trimTo": duration,
        "repetitions": 0,
        "decodeHeadroomDb": 6,
    },
    "beats": [round(ms / 1000, 3) for ms, _, _ in beats],
    "beatEntries": beats,
    "analysisVersion": BEAT_ANALYSIS_VERSION,
    "onsetLeadMs": ONSET_LEAD_MS,
    "analysis": analysis,
}
(PROJECT / "src/music-film.json").write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
license_path = destination / "LICENSE.md"
previous_license = destination / "lookin-up-LICENSE.md"
if (
    selected["id"] == "lia-original-score"
    and license_path.exists()
    and not previous_license.exists()
):
    previous_license.write_text(license_path.read_text(encoding="utf-8"), encoding="utf-8")
source_format = selected.get("sourceFormat", "See original source and generation metadata")
license_path.write_text(
    "# Musique du film LIA\n\n"
    f"{selected['attribution']}\n\n"
    f"Source : {selected['source']}\n\nLicence : {selected['licenseUrl']}\n\n"
    f"Extrait continu de {duration} secondes, sans boucle. "
    "La source originale et les éléments de provenance sont conservés dans audio/v5. "
    "Le WAV de travail est décodé/rééchantillonné en PCM 24 bits à 48 kHz ; "
    "ce format de travail ne prétend pas améliorer la fidélité de la source.\n\n"
    f"Format de la source : {source_format}\n\n"
    + (
        "Composition originale demandée via Google Lyria 3.5. Le prompt, le payload "
        "sans clé, les métadonnées disponibles, le coût publié et le format natif mesuré "
        f"figurent dans {Path(selected['generationMetadata']).name}. Aucune licence Creative Commons "
        "et aucune exclusivité de copyright ne sont revendiquées. Les conditions "
        "Gemini API indiquent que Google ne revendique pas la propriété du contenu "
        "généré ; l’utilisation reste soumise à ces conditions et au droit applicable.\n"
        if selected["id"] == "lia-original-score"
        else "La licence de la source et les preuves correspondantes sont conservées ici.\n"
    ),
    encoding="utf-8",
)
print(
    f"Film soundtrack: {duration}s, {len(beats)} pulses, {analysis['onset_hit_rate']:.1%} onset alignment"
)
