"""Write a language's model, the shared stages and the manifest to the repository (ADR-329).

Layout under ``apps/web/public/models/wake/``:

    v1/shared/melspectrogram-<sha>.onnx
    v1/shared/embedding_model-<sha>.onnx
    v1/<lang>/classifier-<sha>.onnx
    v1/<lang>/stop-classifier-<sha>.onnx
    v1/<lang>/manifest.json

Every model file is named after the first characters of its SHA-256, so it is
served as immutable: a retrained model is a new URL, and a browser never runs a
cached classifier of the previous training under the new manifest. Only the
manifest keeps its name (it is revalidated). ``v1`` is the contract between
the manifest and the browser's engine (``WAKE_MODEL_VERSION``). The manifest
names every file with its SHA-256 and size (the browser refuses a file that
does not match), the policy the browser applies (threshold, patience,
refractory, warm-up), the measured figures, and the provenance of every input,
with its licence.

A spoken command (``--keyword stop``) is exported INTO the language's manifest,
under ``commands``: its word, its policy, its classifier and its own measured
figures — the phrase's export must come first, and a later export of the phrase
keeps the commands it finds. The voices and corpora are the language's, so the
provenance is written once.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import metadata
from pathlib import Path
from typing import Any

from wakeword.features import CHUNK, REFRACTORY_CHUNKS, WARMUP_CHUNKS
from wakeword.languages import LanguageSpec
from wakeword.measure import bench_path
from wakeword.paths import OUT_DIR, language_dir
from wakeword.sources import (
    LOCK_PATH,
    VOXCPM_REPOSITORY,
    VOXCPM_REVISION,
    feature_models,
    fetch,
    fleurs_remotes,
    musan_remote,
    read_lock,
)

MODEL_VERSION = "v1"


#: How many hex characters of a file's SHA-256 name it.
_NAME_DIGEST = 12


def _addressed(source: Path, directory: Path, stem: str) -> dict[str, Any]:
    """Copy ``source`` as ``<stem>-<sha>.onnx``, drop the stem's other copies, describe it."""
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    target = directory / f"{stem}-{digest[:_NAME_DIGEST]}.onnx"
    for stale in directory.glob(f"{stem}-*.onnx"):
        if stale != target:
            stale.unlink()
    if not target.exists():
        target.write_bytes(data)
    url = f"/models/wake/{MODEL_VERSION}/{directory.name}/{target.name}"
    return {"url": url, "sha256": digest, "bytes": len(data)}


def _synthesisers(clip_banks: dict[str, list[str]]) -> list[str]:
    """The synthesisers of the clip banks the model learnt from (the training report's)."""
    names = {name for banks in clip_banks.values() for name in banks}
    piper = metadata("piper-tts")
    synthesisers = [
        f"Piper (piper-tts {piper['Version']}, {piper['License']}; run as a tool, never shipped; "
        "voices above)"
    ]
    if any(name.startswith("vox-") for name in names):
        synthesisers.append(
            f"VoxCPM2 ({VOXCPM_REPOSITORY}@{VOXCPM_REVISION}, Apache-2.0): voices designed "
            "from descriptions, or cloned from the corpora below"
        )
    return synthesisers


def _measured(bench: dict[str, Any]) -> dict[str, Any]:
    """The figures a manifest states about its model, and the bench's verdict."""
    selected = bench["selected"]
    return {
        "recall_clean": selected["recall clean"]["recall"],
        "recall_10db": selected["recall 10 dB"]["recall"],
        "recall_5db": selected["recall 5 dB"]["recall"],
        "recall_by_form_clean": selected["recall by form, clean"],
        "median_latency_ms": selected["recall clean"]["median_latency_ms"],
        "near_miss_accepts": selected["near-miss accepts clean"],
        "false_accepts_per_hour": {
            group.removeprefix("false accepts "): value["per_hour"]
            for group, value in selected.items()
            if group.startswith("false accepts ")
        },
        # One word the shipped-models guard reads (`go` only when every
        # acceptance check held), and the checks themselves beside it.
        "verdict": "go" if all(bench["verdict"].values()) else "no-go",
        "checks": bench["verdict"],
    }


def _trained_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _export_command(spec: LanguageSpec, work: Path, bench: dict[str, Any], path: Path) -> Path:
    """Write a command's classifier and its entry into the language's manifest."""
    if not path.exists():
        raise SystemExit(f"export the phrase of {spec.code!r} first: {path} does not exist")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    selected = bench["selected"]
    entry = {
        "phrase": spec.phrase,
        "threshold": selected["threshold"],
        "patience": selected["patience"],
        "refractory_chunks": REFRACTORY_CHUNKS,
        "warmup_chunks": WARMUP_CHUNKS,
        "classifier": _addressed(
            work / "classifier.onnx", path.parent, f"{spec.keyword}-classifier"
        ),
        "measured": _measured(bench),
        "trained_at": _trained_at(),
    }
    manifest["commands"] = {**manifest.get("commands", {}), spec.keyword: entry}
    return _write(path, manifest)


def _write(path: Path, manifest: dict[str, Any]) -> Path:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"exported {path}")
    return path


def export(spec: LanguageSpec) -> Path:
    """Copy the files and write the manifest (or a command into it); returns its path."""
    work = language_dir(spec.slug)
    bench = json.loads(bench_path(spec.slug).read_text(encoding="utf-8"))
    root = OUT_DIR / MODEL_VERSION
    language = root / spec.code
    path = language / "manifest.json"
    if spec.keyword != "wake":
        return _export_command(spec, work, bench, path)
    training = json.loads((work / "train_report.json").read_text(encoding="utf-8"))
    selected = bench["selected"]
    shared = root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    lock = read_lock()
    files: dict[str, dict[str, Any]] = {}
    for remote, key in zip(feature_models(), ("melspectrogram", "embedding"), strict=True):
        files[key] = _addressed(fetch(remote, lock), shared, Path(remote.name).stem)
    language.mkdir(parents=True, exist_ok=True)
    # The commands an earlier export wrote stay: retraining the phrase never drops them.
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    files["classifier"] = _addressed(work / "classifier.onnx", language, "classifier")
    manifest = {
        "version": MODEL_VERSION,
        "language": spec.code,
        "phrase": spec.phrase,
        "sample_rate": 16_000,
        "chunk_samples": CHUNK,
        "threshold": selected["threshold"],
        "patience": selected["patience"],
        "refractory_chunks": REFRACTORY_CHUNKS,
        "warmup_chunks": WARMUP_CHUNKS,
        "files": files,
        "measured": _measured(bench),
        **({"commands": previous["commands"]} if "commands" in previous else {}),
        "provenance": {
            "generator": "scripts/wake-word",
            "trained_at": _trained_at(),
            "sources_lock_sha256": hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest(),
            "voices": sorted({f"{voice.key} ({voice.licence})" for voice in spec.train_voices}),
            "synthesisers": _synthesisers(training["clip_banks"]),
            "corpora": [
                f"FLEURS {spec.fleurs} ({fleurs_remotes(spec.fleurs)['train'].licence})",
                *([f"Multilingual LibriSpeech {spec.mls} (CC-BY-4.0)"] if spec.mls else []),
                f"MUSAN ({musan_remote().licence})",
            ],
            "feature_models": "openWakeWord v0.5.1 (Apache-2.0; embedding: Google speech_embedding)",
        },
    }
    return _write(path, manifest)
