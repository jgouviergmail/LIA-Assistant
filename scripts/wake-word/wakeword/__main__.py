"""``python -m wakeword <command> [--lang fr]`` — the toolbox's entry point (ADR-329).

Commands, in the order a language is built:

- ``lock``      pin every remote the language needs in ``sources.lock.json``;
- ``prepare``   download and decode the corpora into banks;
- ``synth``     synthesise the phrase and its near misses with Piper (CPU);
- ``clone``     the same in natural voices with VoxCPM2 (GPU image only);
- ``train``     compute the features and train the classifier;
- ``measure``   measure recall and false accepts on held-out audio (``--threshold``
                certifies another operating point than the dev's);
- ``export``    write the model, the shared stages and the manifest to ``/out``;
- ``golden``    write the web engine's parity fixture (the exported model) to ``/fixtures``;
- ``selfcheck`` hold the feature code to openWakeWord, the reference;
- ``all``       every step above but ``lock``, in order.

``--keyword stop`` builds the language's stop command instead of its phrase (the
same voices and corpora, so ``lock`` and ``prepare`` serve both); ``golden``
covers the phrase alone.
"""

from __future__ import annotations

import argparse

from wakeword import sources
from wakeword.languages import KEYWORDS, Keyword, spec_of

# Every step imports its heavy dependencies itself: the CPU image has no
# VoxCPM, the GPU image no Piper.


def _lock(language: str, _keyword: Keyword) -> None:
    spec = spec_of(language)
    lock = sources.read_lock()
    remotes = [*sources.feature_models(), sources.musan_remote()]
    for voice in {voice.key: voice for voice in (*spec.train_voices, *spec.test_voices)}.values():
        remotes.extend(sources.voice_remotes(voice))
    remotes.extend(sources.fleurs_remotes(spec.fleurs).values())
    if spec.mls:
        selected = [
            shard for shards in sources.mls_remotes_from_hub(spec.mls).values() for shard in shards
        ]
        remotes.extend(selected)
        forgotten = sources.forget_unselected(
            lock, f"mls/{spec.mls}/", {shard.name for shard in selected}
        )
        if forgotten:
            print(f"lock: {len(forgotten)} MLS shards no longer selected, forgotten")
    for remote in remotes:
        sources.lock_remote(remote, lock)
        sources.write_lock(lock)
    print(f"lock: {len(remotes)} remotes for {language}")


def _prepare(language: str, _keyword: Keyword) -> None:
    from wakeword import corpora

    spec = spec_of(language)
    lock = sources.read_lock()
    for remote in sources.feature_models():
        sources.fetch(remote, lock)
    corpora.prepare_musan(lock)
    corpora.prepare_language(spec, lock)


def _synth(language: str, keyword: Keyword) -> None:
    from wakeword import synth
    from wakeword.synth import Kind, Split

    spec = spec_of(language, keyword)
    lock = sources.read_lock()
    kinds: tuple[Kind, ...] = ("positive", "near_miss")
    splits: tuple[Split, ...] = ("train", "test")
    for kind in kinds:
        for split in splits:
            synth.synthesise_bank(spec, kind, split, lock)


def _clone(language: str, keyword: Keyword) -> None:
    from wakeword import clone

    clone.clone_language(spec_of(language, keyword))


def _train(language: str, keyword: Keyword) -> None:
    from wakeword import train

    train.train(spec_of(language, keyword))


def _measure(language: str, keyword: Keyword, threshold: float | None = None) -> None:
    from wakeword import measure

    measure.measure(spec_of(language, keyword), threshold)


def _export(language: str, keyword: Keyword) -> None:
    from wakeword import export

    export.export(spec_of(language, keyword))


def _golden(language: str, keyword: Keyword) -> None:
    from wakeword import golden

    if keyword != "wake":
        raise SystemExit("the golden fixture covers the wake phrase alone")
    golden.golden(spec_of(language))


def _selfcheck(_language: str, _keyword: Keyword) -> None:
    from wakeword import selfcheck

    selfcheck.run()


_COMMANDS = {
    "lock": _lock,
    "prepare": _prepare,
    "synth": _synth,
    "clone": _clone,
    "train": _train,
    "measure": _measure,
    "export": _export,
    "golden": _golden,
    "selfcheck": _selfcheck,
}


def main() -> None:
    """Parse the command line and run one command, or every build step."""
    parser = argparse.ArgumentParser(prog="wakeword", description=__doc__)
    parser.add_argument("command", choices=[*_COMMANDS, "all"])
    parser.add_argument("--lang", default="fr")
    parser.add_argument("--keyword", choices=KEYWORDS, default="wake")
    parser.add_argument(
        "--threshold",
        type=float,
        help="measure: certify this operating point instead of the dev's choice",
    )
    args = parser.parse_args()
    if args.command == "all":
        for step in ("prepare", "synth", "train", "measure", "export"):
            _COMMANDS[step](args.lang, args.keyword)
        return
    if args.command == "measure":
        _measure(args.lang, args.keyword, args.threshold)
        return
    _COMMANDS[args.command](args.lang, args.keyword)


if __name__ == "__main__":
    main()
