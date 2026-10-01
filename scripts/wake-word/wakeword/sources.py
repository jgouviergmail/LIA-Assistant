"""Every byte the toolbox downloads, pinned (ADR-329).

A remote is fetched from an immutable address (a Hugging Face revision, a
release asset) and verified against the SHA-256 recorded in
``sources.lock.json``, committed beside this package. ``python -m wakeword lock``
writes that file: for a Hugging Face file the hash is the one the Hub states
(its LFS object id IS the SHA-256 of the content), for any other host it is
computed from a first download and recorded — trust on first use, written
down, reviewed in the diff. A fetch whose bytes differ from the lock is refused
and deleted; nothing is ever trained on bytes nobody pinned.

Every remote carries the licence it is used under, copied into the shipped
manifest's provenance.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wakeword.languages import PIPER_REVISION, LanguageSpec, Voice
from wakeword.paths import DOWNLOADS

LOCK_PATH = Path(__file__).resolve().parent.parent / "sources.lock.json"

_HF = "https://huggingface.co"
FLEURS_REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
MLS_REVISION = "2e83e61823b4c47dcbcb1980bb88601274127609"
#: The natural-voice synthesiser (Apache-2.0 code and weights), read by the GPU
#: image to generate and by the export to state what a model learnt from.
VOXCPM_REPOSITORY = "openbmb/VoxCPM2"
VOXCPM_REVISION = "32279effe8c19989596f05d353d1447f51d9e915"
#: openWakeWord's feature models (Apache-2.0 code; the embedding is Google's
#: ``speech_embedding``, Apache-2.0): pinned to the release the 0.6.0 package names.
_OWW_RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
_MUSAN = "https://openslr.elda.org/resources/17/musan.tar.gz"
#: How many training shards of a Multilingual LibriSpeech language are used:
#: evenly spaced in name order (speakers spread, reproducible from the revision).
#: Measured 2026-10-01 on French: 20 shards (~49 h) left the dev false accepts
#: RISING through training, to 14/h at the strictest threshold — the classifier
#: memorised too few negatives; 120 (~290 h) is the next measurement.
_MLS_TRAIN_SHARDS = 120
_CHUNK = 1 << 20


@dataclass(frozen=True, slots=True)
class Remote:
    """One downloadable file.

    Attributes:
        name: Its stable key in the lock and its file name under the cache.
        url: An immutable address.
        licence: The licence it is used under.
        hub: ``(repo, revision, path)`` when the Hub states its hash.
    """

    name: str
    url: str
    licence: str
    hub: tuple[str, str, str] | None = None

    @property
    def path(self) -> Path:
        """Where the verified file lives in the cache."""
        return DOWNLOADS / self.name


def feature_models() -> list[Remote]:
    """The two shared ONNX stages every language's classifier sits on."""
    return [
        Remote(f"oww/{name}", f"{_OWW_RELEASE}/{name}", "Apache-2.0")
        for name in ("melspectrogram.onnx", "embedding_model.onnx")
    ]


def voice_remotes(voice: Voice) -> list[Remote]:
    """The model and its configuration for one Piper voice."""
    remotes = []
    for suffix in (".onnx", ".onnx.json"):
        path = f"{voice.path}/{voice.key}{suffix}"
        remotes.append(
            Remote(
                f"voices/{voice.key}{suffix}",
                f"{_HF}/rhasspy/piper-voices/resolve/{PIPER_REVISION}/{path}",
                voice.licence,
                ("models/rhasspy/piper-voices", PIPER_REVISION, path),
            )
        )
    return remotes


def fleurs_remotes(config: str) -> dict[str, Remote]:
    """FLEURS audio of one language, by split (CC-BY 4.0)."""
    remotes = {}
    for split in ("train", "dev", "test"):
        path = f"data/{config}/audio/{split}.tar.gz"
        remotes[split] = Remote(
            f"fleurs/{config}/{split}.tar.gz",
            f"{_HF}/datasets/google/fleurs/resolve/{FLEURS_REVISION}/{path}",
            "CC-BY-4.0",
            ("datasets/google/fleurs", FLEURS_REVISION, path),
        )
    return remotes


def musan_remote() -> Remote:
    """MUSAN — music, noise and speech recordings (OpenSLR 17, CC-BY 4.0)."""
    return Remote("musan/musan.tar.gz", _MUSAN, "CC-BY-4.0")


def _hub_listing(repo: str, revision: str, directory: str) -> list[dict[str, Any]]:
    """Every file of a Hub directory, following the API's pages (1 000 entries each)."""
    url: str | None = f"{_HF}/api/{repo}/tree/{revision}/{directory}"
    files: list[dict[str, Any]] = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as response:
            files.extend(item for item in json.load(response) if item.get("type") == "file")
            url = _next_page(response.headers.get("Link", ""))
    return files


def _next_page(link: str) -> str | None:
    """The ``rel="next"`` target of an HTTP ``Link`` header, if any."""
    for part in link.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def _mls_remote(directory: str, path: str) -> Remote:
    shard = path.rsplit("/", 1)[-1]
    split = path.split("/")[2]
    return Remote(
        f"mls/{directory}/{split}/{shard}",
        f"{_HF}/datasets/facebook/multilingual_librispeech/resolve/{MLS_REVISION}/{path}",
        "CC-BY-4.0",
        ("datasets/facebook/multilingual_librispeech", MLS_REVISION, path),
    )


def mls_remotes_from_hub(directory: str) -> dict[str, list[Remote]]:
    """The MLS shards a language uses, listed at the pinned revision (lock time only).

    Every dev and test shard (the held-out measurement), and a spread subset of
    the training shards: one in every N, in name order, so the speakers vary
    and the choice is reproducible from the revision alone.
    """
    chosen: dict[str, list[Remote]] = {}
    repo = "datasets/facebook/multilingual_librispeech"
    for split in ("train", "dev", "test"):
        files = sorted(
            item["path"]
            for item in _hub_listing(repo, MLS_REVISION, f"data/{directory}/{split}/audio")
        )
        if split == "train":
            stride = max(1, len(files) // _MLS_TRAIN_SHARDS)
            files = files[::stride][:_MLS_TRAIN_SHARDS]
        chosen[split] = [_mls_remote(directory, path) for path in files]
    return chosen


def mls_split(spec: LanguageSpec, lock: dict[str, Any], split: str) -> list[Remote]:
    """The locked MLS shards of one split of the language."""
    if not spec.mls:
        return []
    prefix = f"mls/{spec.mls}/{split}/"
    return [
        Remote(name, entry["url"], entry["licence"])
        for name, entry in sorted(lock.get("remotes", {}).items())
        if name.startswith(prefix)
    ]


# -- the lock ---------------------------------------------------------------------


def read_lock() -> dict[str, Any]:
    """The committed lock, or an empty one."""
    if not LOCK_PATH.exists():
        return {"remotes": {}}
    lock: dict[str, Any] = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    return lock


def write_lock(lock: dict[str, Any]) -> None:
    """Write the lock sorted, LF-terminated, so its diff is the review."""
    lock["remotes"] = dict(sorted(lock["remotes"].items()))
    LOCK_PATH.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _hub_hash(remote: Remote) -> tuple[str, int]:
    assert remote.hub is not None
    repo, revision, path = remote.hub
    request = urllib.request.Request(
        f"{_HF}/api/{repo}/paths-info/{revision}",
        data=json.dumps({"paths": [path], "expand": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        info = json.load(response)[0]
    lfs = info.get("lfs")
    if lfs:
        return str(lfs["oid"]), int(lfs["size"])
    # A small file kept in git (a voice's JSON): the Hub states no SHA-256 for
    # it, so the bytes are hashed — they are fetched at a pinned revision.
    return _download(remote, expected=None)


def lock_remote(remote: Remote, lock: dict[str, Any]) -> None:
    """Record one remote's hash and size in the lock (no-op when already there)."""
    if remote.name in lock["remotes"]:
        return
    sha256, size = _hub_hash(remote) if remote.hub else _download(remote, expected=None)
    lock["remotes"][remote.name] = {
        "url": remote.url,
        "sha256": sha256,
        "bytes": size,
        "licence": remote.licence,
    }


# -- fetching ---------------------------------------------------------------------


def _download(remote: Remote, expected: str | None) -> tuple[str, int]:
    """Download to the cache through a ``.part`` file, hashing as it streams."""
    target = remote.path
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    with (
        urllib.request.urlopen(remote.url, timeout=120) as response,
        partial.open("wb") as out,
    ):
        while chunk := response.read(_CHUNK):
            digest.update(chunk)
            out.write(chunk)
            size += len(chunk)
    sha256 = digest.hexdigest()
    if expected is not None and sha256 != expected:
        partial.unlink()
        raise SystemExit(f"{remote.name}: sha256 {sha256} differs from the lock's {expected}")
    partial.replace(target)
    return sha256, size


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(remote: Remote, lock: dict[str, Any]) -> Path:
    """The verified local copy of a locked remote, downloaded when missing.

    Raises:
        SystemExit: The remote is not in the lock, or its bytes differ from it.
    """
    entry = lock["remotes"].get(remote.name)
    if entry is None:
        raise SystemExit(f"{remote.name} is not in {LOCK_PATH.name}: run `lock` first")
    if entry["url"] != remote.url:
        # The code moved to another revision and the lock did not follow: the
        # hash in the lock is not the hash of what the code now asks for.
        raise SystemExit(f"{remote.name}: the lock pins {entry['url']}, the code asks {remote.url}")
    marker = remote.path.with_name(remote.path.name + ".verified")
    if remote.path.exists() and marker.exists():
        return remote.path
    if remote.path.exists() and _sha256_of(remote.path) == entry["sha256"]:
        marker.touch()
        return remote.path
    _download(remote, expected=entry["sha256"])
    marker.touch()
    return remote.path


def discard(remote: Remote) -> None:
    """Delete a large archive once its contents were extracted (the marker stays)."""
    if remote.path.exists():
        remote.path.unlink()
