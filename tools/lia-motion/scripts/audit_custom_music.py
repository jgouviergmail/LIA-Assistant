"""One independent audio-perception audit; never generates or retries music.

The complete source MP3 is sent inline to a multimodal Flash model. The request
contains no requested musical style, original generation prompt or filename.
Its answer is automated perception, not human audition or a rights guarantee.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import sys
import time

from generate_custom_music import (
    ApiFailure,
    DESTINATION,
    PROJECT,
    audio_blocks,
    credentials,
    request_json,
    write_json,
)

MODEL = "gemini-3.8-flash"
AUDIO_GUIDE = "https://ai.google.dev/gemini-api/docs/audio"
API_REFERENCE = "https://ai.google.dev/api/interactions-api"
PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
PROMPT = """Analyse the complete supplied audio by its audible content alone.
You have no information about the creator's intent, requested genre or intended
instrumentation. Do not infer an instrument from a musical stereotype. State
uncertainty rather than convert a synthetic timbre into a definite acoustic
instrument. Give concise descriptions in French and timestamps in seconds.

Identify the main rhythm, bass and melodic lead instruments and how their
textures change across the piece. Separately assess (a) saxophone, (b) other
brass or woodwind instruments, and (c) human voices, including speech, singing,
humming and sampled/chopped vocals. For each, report present/absent/uncertain,
self-assessed confidence and every relevant time range. Distinguish an audible
realistic wind/reed sound from a synthesizer with a horn-like tone, and say when
the distinction cannot be determined from this mix. If absent, use no detection
intervals; do not invent positions. Also describe the actual structural changes,
rhythmic energy, melodic repetition and the audible ending. The confidence
values are self-assessments, not calibrated probabilities. This is an automatic
audio-perception report and must not claim human listening or legal clearance.
"""

INTERVAL = {
    "type": "object",
    "properties": {
        "startSeconds": {"type": "number"},
        "endSeconds": {"type": "number"},
        "description": {"type": "string"},
    },
    "required": ["startSeconds", "endSeconds", "description"],
}
ASSESSMENT = {
    "type": "object",
    "properties": {
        "presence": {"type": "string", "enum": ["present", "absent", "uncertain"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "intervals": {"type": "array", "items": INTERVAL},
    },
    "required": ["presence", "confidence", "reason", "intervals"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "mainInstruments": {"type": "array", "items": {"type": "string"}},
        "melodicLeads": {"type": "array", "items": INTERVAL},
        "saxophone": ASSESSMENT,
        "otherBrassOrWoodwinds": ASSESSMENT,
        "voices": ASSESSMENT,
        "structure": {"type": "array", "items": INTERVAL},
        "rhythmicEnergy": {"type": "string"},
        "melodicRepetition": {"type": "string"},
        "ending": {"type": "string"},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "mainInstruments",
        "melodicLeads",
        "saxophone",
        "otherBrassOrWoodwinds",
        "voices",
        "structure",
        "rhythmicEnergy",
        "melodicRepetition",
        "ending",
        "limitations",
    ],
}


def main() -> int:
    attempt_path = DESTINATION / "lia-electrofunk-audit-attempt.json"
    report_path = DESTINATION / "lia-electrofunk-audio-audit.json"
    if attempt_path.exists():
        previous = json.loads(attempt_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": "existing_audit_not_repeated",
                    "previousStatus": previous.get("status"),
                }
            )
        )
        return 0

    selected = json.loads((PROJECT / "src/music-film.json").read_text("utf-8"))
    source = PROJECT / "public" / selected["originalAudio"]
    if source.name != "LIA-ElectroFunk.mp3":
        raise RuntimeError("The selected third source is required")
    source_bytes = source.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if source_sha != selected["sourceSha256"]:
        raise RuntimeError("Selected source hash does not match the actual audio")
    generation_metadata = json.loads(
        (PROJECT / "public" / selected["generationMetadata"]).read_text("utf-8")
    )
    _, key = credentials()
    model_inventory, _ = request_json("/v1beta/models?pageSize=1000", key)
    model_listed = any(
        item.get("name") == f"models/{MODEL}"
        for item in model_inventory.get("models", [])
    )
    if not model_listed:
        print(json.dumps({"status": "audit_model_unavailable", "model": MODEL}))
        return 1

    generation_config = {"max_output_tokens": 3500, "thinking_level": "minimal"}
    provenance = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "provider": "Google Gemini API",
        "modelListedByReadOnlyPreflight": model_listed,
        "sourceAudio": source.name,
        "sourceBytes": len(source_bytes),
        "sourceSha256": source_sha,
        "sourceDurationSeconds": generation_metadata["sourceDurationSeconds"],
        "inputMimeType": "audio/mp3",
        "wholeSourceInline": True,
        "generationConfig": generation_config,
        "prompt": PROMPT,
        "responseSchema": SCHEMA,
        "generationPromptProvided": False,
        "filenameProvidedToModel": False,
        "automatedAudioPerception": True,
        "humanAudioAudition": False,
        "musicGenerationRequests": 0,
        "maximumAuditRequests": 1,
        "automaticRetries": 0,
        "credentialPersisted": False,
        "store": False,
        "audioGuide": AUDIO_GUIDE,
        "apiReference": API_REFERENCE,
        "pricingSource": PRICING,
        "publishedInputUsdPerMillionTokens": 0.75,
        "publishedOutputUsdPerMillionTokens": 3.75,
        "pricePeriod": "Standard through 2026-12-31",
        "invoiceVerified": False,
        "qualification": (
            "Automatic perception of the actual MP3, with a neutral prompt. "
            "Instrument identification and confidence can be mistaken; no human "
            "audition, source separation or legal clearance is asserted."
        ),
    }
    write_json(DESTINATION / "lia-electrofunk-audit-request.json", provenance)
    checkpoint = {"status": "requested", **provenance}
    write_json(attempt_path, checkpoint)
    payload = {
        "model": MODEL,
        "input": [
            {"type": "text", "text": PROMPT},
            {
                "type": "audio",
                "data": base64.b64encode(source_bytes).decode("ascii"),
                "mime_type": "audio/mp3",
            },
        ],
        "response_format": SCHEMA,
        "generation_config": generation_config,
        "store": False,
    }
    started = time.monotonic()
    try:
        document, headers = request_json("/v1beta/interactions", key, payload)
        _, texts = audio_blocks(document)
        assessment = json.loads("\n".join(texts))
        usage = document.get("usage", {})
        price = (
            usage.get("total_input_tokens", 0) * 0.75
            + usage.get("total_output_tokens", 0) * 3.75
        ) / 1_000_000
        report = {
            **provenance,
            "status": "audited",
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "providerResponseMetadata": headers,
            "interactionId": document.get("id"),
            "usage": usage,
            "estimatedPriceUsdFromPublishedRate": round(price, 6),
            "assessment": assessment,
        }
        write_json(report_path, report)
        checkpoint.update(
            status="audited", finishedAt=report["finishedAt"], report=report_path.name
        )
        write_json(attempt_path, checkpoint)
        print(
            json.dumps(
                {
                    "status": "audited",
                    "report": report_path.name,
                    "elapsedSeconds": report["elapsedSeconds"],
                    "estimatedPriceUsd": report["estimatedPriceUsdFromPublishedRate"],
                    "assessment": assessment,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:
        # Never print raw exceptions/URLs, response bodies or credential headers.
        checkpoint.update(status="audit_failed", errorType=type(error).__name__)
        if isinstance(error, ApiFailure):
            checkpoint["apiDiagnostic"] = error.diagnostic
        checkpoint.update(
            elapsedSeconds=round(time.monotonic() - started, 3),
            finishedAt=datetime.now(timezone.utc).isoformat(),
            assessment=None,
            qualification=(
                "The sole automatic audio audit was rejected or failed. "
                "No instrument-presence assessment was received. "
                "The generation prompt does not prove the absence of saxophone, "
                "other winds or voices. No automatic retry is permitted."
            ),
        )
        write_json(attempt_path, checkpoint)
        write_json(report_path, checkpoint)
        print(json.dumps({"status": "audit_failed", "errorType": type(error).__name__}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
