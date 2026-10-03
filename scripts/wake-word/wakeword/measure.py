"""Measure one language's model on audio it never heard (ADR-329).

- **Recall**: every TEST clip (voices and speakers absent from training) is
  placed 3 s into a 6 s stream, through a room and a phone half the time, at
  four signal-to-noise ratios against held-out music, noise and speech. A
  detection counts when it falls between the start of the phrase and one
  second after its end; the latency is its distance to the end.
- **Near misses**: the same streams with the TEST near misses — how often a
  phrase that must not wake LIA does, overall and text by text (the phrase
  must ignore its language's stop command, the command a bare « stop »).
- **False accepts per hour**: the policy run over the held-out streams —
  FLEURS and MLS ``test`` in the language, MUSAN's held-out English speech,
  music and noise, each listened to continuously.

The scores are computed in batch on the streaming grid, which the selfcheck
holds equal to the browser's streaming arithmetic. The threshold is the one
the dev split chose, unless the operator certifies another operating point
(``--threshold``): the export ships the measured row, so the manifest's figures
are always those of the threshold it carries. The table around it shows the
trade-off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from wakeword.banks import Bank, open_bank
from wakeword.corpora import language_bank_names
from wakeword.features import Classifier, FeatureExtractor, Policy
from wakeword.languages import Keyword, LanguageSpec
from wakeword.paths import CORPORA, language_dir
from wakeword.train import THRESHOLDS, clip_bank_names, extractor, false_accepts
from wakeword.trials import (
    SNR_CONDITIONS,
    Trial,
    accept_rate,
    form_of,
    hit_latency,
    recall,
    stream,
)

_HISS_DBFS = -70.0
#: Published acceptance thresholds per keyword (spec 2026-10-01, section 4.2). Never
#: lowered to pass. The stop command tolerates more false accepts: it acts only while
#: LIA speaks and a false one only cuts her voice, where a false wake opens the
#: microphone for a request.
ACCEPTANCE: dict[Keyword, dict[str, float]] = {
    "wake": {
        "recall_clean_min": 0.90,
        "recall_10db_min": 0.80,
        # No written form of the phrase (separated, fused, with a pause) left behind:
        # a person says it either way (owner, 2026-10-01: « dis … Lia » woke LIA,
        # « dilia » did not, while the overall recall looked fine).
        "recall_clean_form_min": 0.85,
        "fa_speech_per_hour_max": 0.5,
        "fa_music_per_hour_max": 0.2,
        "latency_ms_max": 300,
    },
    "stop": {
        "recall_clean_min": 0.90,
        "recall_10db_min": 0.80,
        "recall_clean_form_min": 0.85,
        "fa_speech_per_hour_max": 2.0,
        "fa_music_per_hour_max": 1.0,
        "latency_ms_max": 300,
    },
}


def _clip_trials(
    fx: FeatureExtractor,
    bank: Bank,
    snr_db: float | None,
    backgrounds: list[Bank],
    classifier: Classifier,
    seed: int,
) -> list[Trial]:
    """Every clip of a bank as a stream: its scores and its span, in bank order."""
    rng = np.random.default_rng(seed)
    trials = []
    for first in range(0, len(bank), 128):
        streams = [
            stream(bank.segment(index), snr_db, backgrounds, rng)
            for index in range(first, min(first + 128, len(bank)))
        ]
        embeddings = fx.embed(np.stack([stream for stream, _, _ in streams]))
        for (_, start, end), frames in zip(streams, embeddings, strict=True):
            trials.append((classifier.stream_scores(frames), start, end))
    return trials


def _recall_by_voice(trials: list[Trial], bank: Bank, policy: Policy) -> dict[str, float]:
    """Recall per held-out voice (and reading language), to find a weak one."""
    groups: dict[str, list[bool]] = {}
    for trial, meta in zip(trials, bank.meta, strict=True):
        key = meta["voice"] + (f" as {meta['reads_as']}" if "reads_as" in meta else "")
        groups.setdefault(key, []).append(hit_latency(trial, policy)[0] is not None)
    return {key: round(sum(hits) / len(hits), 4) for key, hits in sorted(groups.items())}


def _recall_by_form(trials: list[Trial], bank: Bank, policy: Policy) -> dict[str, float]:
    """Recall per written form of the phrase, to find a pronunciation the model misses."""
    groups: dict[str, list[bool]] = {}
    for trial, meta in zip(trials, bank.meta, strict=True):
        groups.setdefault(form_of(meta["text"]), []).append(
            hit_latency(trial, policy)[0] is not None
        )
    return {key: round(sum(hits) / len(hits), 4) for key, hits in sorted(groups.items())}


def _accepts_by_text(trials: list[Trial], bank: Bank, policy: Policy) -> dict[str, float]:
    """How often each near miss fires, most often first: the ones the model confuses."""
    groups: dict[str, list[Trial]] = {}
    for trial, meta in zip(trials, bank.meta, strict=True):
        groups.setdefault(str(meta["text"]), []).append(trial)
    rates = {text: round(accept_rate(items, policy), 4) for text, items in groups.items()}
    return dict(sorted(rates.items(), key=lambda pair: (-pair[1], pair[0])))


def _merged(banks: list[Bank]) -> Bank:
    """Several clip banks read as one, in order (their metadata keeps each clip's voice)."""
    if len(banks) == 1:
        return banks[0]
    samples = np.concatenate([np.asarray(bank.samples) for bank in banks])
    offsets = [0]
    meta: list[dict[str, Any]] = []
    for bank in banks:
        base = offsets[-1]
        offsets.extend(base + int(end) for end in bank.offsets[1:])
        meta.extend(bank.meta)
    return Bank("+".join(bank.name for bank in banks), samples, np.asarray(offsets), meta)


def measure(spec: LanguageSpec, threshold: float | None = None) -> dict[str, Any]:
    """Measure the trained classifier of a language; writes ``bench.json`` beside it.

    Args:
        spec: The language and keyword.
        threshold: The operating point to certify; the dev's choice when None.

    Raises:
        SystemExit: The threshold is outside (0, 1).
    """
    work = language_dir(spec.slug)
    classifier = Classifier(work / "classifier.onnx")
    selected = json.loads((work / "train_report.json").read_text(encoding="utf-8"))["selected"]
    source = "dev" if threshold is None else "operator"
    threshold = float(selected["threshold"]) if threshold is None else threshold
    if not 0.0 < threshold < 1.0:
        raise SystemExit(f"threshold {threshold} is outside (0, 1)")
    test_backgrounds = [
        open_bank(CORPORA, name)
        for name in ("musan-noise-test", "musan-music-test", "musan-speech-test")
    ] + [open_bank(CORPORA, name) for name in language_bank_names(spec)["test"]]
    positives = _merged([open_bank(CORPORA, n) for n in clip_bank_names(spec, "positive", "test")])
    near = _merged([open_bank(CORPORA, n) for n in clip_bank_names(spec, "near_miss", "test")])

    fx = extractor()
    positive_trials = {
        name: _clip_trials(fx, positives, snr, test_backgrounds, classifier, seed=11 + n)
        for n, (name, snr) in enumerate(SNR_CONDITIONS.items())
    }
    near_trials = {
        name: _clip_trials(fx, near, SNR_CONDITIONS[name], test_backgrounds, classifier, 31 + n)
        for n, name in enumerate(("clean", "10 dB"))
    }
    fa_banks = {
        "speech (language)": language_bank_names(spec)["test"],
        "speech (English)": ["musan-speech-test"],
        "music": ["musan-music-test"],
        "noise": ["musan-noise-test"],
    }
    fa_scores = {
        group: [
            classifier.stream_scores(fx.embed_long(open_bank(CORPORA, n).samples)) for n in names
        ]
        for group, names in fa_banks.items()
    }

    def row(policy: Policy) -> dict[str, Any]:
        result: dict[str, Any] = {"threshold": policy.threshold, "patience": policy.patience}
        for name, trials in positive_trials.items():
            result[f"recall {name}"] = recall(trials, policy)
        for name, trials in near_trials.items():
            result[f"near-miss accepts {name}"] = round(accept_rate(trials, policy), 4)
        for group, streams in fa_scores.items():
            counts = [
                false_accepts(scores, policy.threshold, policy.patience) for scores in streams
            ]
            fired = sum(count for count, _ in counts)
            hours = sum(hours for _, hours in counts)
            result[f"false accepts {group}"] = {
                "count": fired,
                "hours": round(hours, 2),
                "per_hour": round(fired / hours, 3),
            }
        return result

    chosen = row(Policy(threshold))
    chosen["recall by voice, 10 dB"] = _recall_by_voice(
        positive_trials["10 dB"], positives, Policy(threshold)
    )
    for condition in ("clean", "10 dB"):
        chosen[f"recall by form, {condition}"] = _recall_by_form(
            positive_trials[condition], positives, Policy(threshold)
        )
    chosen["near-miss accepts by text, clean"] = _accepts_by_text(
        near_trials["clean"], near, Policy(threshold)
    )
    table = [row(Policy(value)) for value in THRESHOLDS if value >= 0.8]
    table += [row(Policy(value, patience=2)) for value in (0.8, 0.9, threshold)]
    acceptance = ACCEPTANCE[spec.keyword]
    verdict = _verdict(chosen, acceptance)
    bench = {
        "language": spec.code,
        "keyword": spec.keyword,
        "phrase": spec.phrase,
        "threshold_source": source,
        "selected": chosen,
        "verdict": verdict,
        "acceptance": acceptance,
        "table": table,
    }
    (work / "bench.json").write_text(
        json.dumps(bench, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({"selected": chosen, "verdict": verdict}, indent=2, ensure_ascii=False))
    return bench


def _verdict(row: dict[str, Any], acceptance: dict[str, float]) -> dict[str, bool]:
    speech = max(
        row["false accepts speech (language)"]["per_hour"],
        row["false accepts speech (English)"]["per_hour"],
    )
    latency = row["recall clean"]["median_latency_ms"]
    return {
        "recall_clean": row["recall clean"]["recall"] >= acceptance["recall_clean_min"],
        "recall_10db": row["recall 10 dB"]["recall"] >= acceptance["recall_10db_min"],
        "fa_speech": speech <= acceptance["fa_speech_per_hour_max"],
        "fa_music": row["false accepts music"]["per_hour"] <= acceptance["fa_music_per_hour_max"],
        "latency": latency is not None and latency <= acceptance["latency_ms_max"],
        "recall_each_form": min(row["recall by form, clean"].values())
        >= acceptance["recall_clean_form_min"],
    }


def bench_path(language: str) -> Path:
    """Where the bench of a language is written."""
    return language_dir(language) / "bench.json"
