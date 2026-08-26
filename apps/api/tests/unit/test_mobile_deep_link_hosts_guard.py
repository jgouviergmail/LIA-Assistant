"""The server and the two shells agree on where a deep link goes.

A deep link is the return leg of a flow that LEFT the app: the user is in a
system browser, has just given a provider their password, and the only thing
bringing them back is a `lia://<host>` URL. If the server emits a host neither
shell maps, nothing happens at all — no error, no screen, no way to tell
whether the connector was created. The user is simply stranded in a browser.

Nothing catches that. The server compiles, both shells compile, every test
passes, and the defect appears only on a real device, after a real sign-in, on
whichever flow was forgotten.

So the three declarations are compared here: the server's enum, Android's map,
and iOS's. The Android manifest is checked too — a host absent from the
intent-filter is never delivered to the app in the first place, however
correctly the activity would have handled it.
"""

from __future__ import annotations

import re

import pytest

from src.core.native_deep_link import NativeDeepLinkHost
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
ANDROID = ROOT / "apps" / "mobile" / "native" / "android" / "app" / "src" / "main"
ACTIVITY = ANDROID / "java" / "com" / "lia" / "assistant" / "MainActivity.java"
MANIFEST = ANDROID / "AndroidManifest.xml"
IOS_CONTROLLER = (
    ROOT / "apps" / "mobile" / "native" / "ios" / "App" / "App" / "MainViewController.swift"
)


def _server_hosts() -> set[str]:
    return {host.value for host in NativeDeepLinkHost}


def _android_hosts() -> set[str]:
    """Hosts the activity knows how to place the user for."""
    source = ACTIVITY.read_text(encoding="utf-8")
    block = source[source.index("DEEP_LINK_PAGES") : source.index("@Override")]
    return set(re.findall(r'"([a-z-]+-callback)"', block))


def _manifest_hosts() -> set[str]:
    """Hosts Android will actually deliver to the app."""
    source = MANIFEST.read_text(encoding="utf-8")
    return set(re.findall(r'android:scheme="lia" android:host="([\w-]+)"', source))


def _ios_hosts() -> set[str]:
    """Hosts the view controller knows how to place the user for."""
    source = IOS_CONTROLLER.read_text(encoding="utf-8")
    block = source[source.index("deepLinkPages") : source.index("/// Bring a provider")]
    return set(re.findall(r'"([a-z-]+-callback)"', block))


def test_android_handles_every_host_the_server_emits() -> None:
    """Otherwise the app receives the link and does nothing with it."""
    missing = _server_hosts() - _android_hosts()

    assert missing == set(), (
        f"MainActivity has no page for: {sorted(missing)} — the user comes back "
        "from the browser to a screen that never changes"
    )


def test_the_manifest_lets_every_handled_host_through() -> None:
    """A host absent here is never delivered, however well it would be handled."""
    missing = _android_hosts() - _manifest_hosts()

    assert missing == set(), (
        f"AndroidManifest declares no intent-filter for: {sorted(missing)} — "
        "the link opens a browser tab instead of the app"
    )


def test_ios_handles_every_host_the_server_emits() -> None:
    """Same failure, other engine.

    iOS registers the SCHEME rather than each host, so there is no Info.plist
    counterpart to check: a scheme registration covers every host on it.
    """
    missing = _server_hosts() - _ios_hosts()

    assert missing == set(), (
        f"MainViewController has no page for: {sorted(missing)} — the user comes "
        "back from the browser to a screen that never changes"
    )


def test_neither_shell_claims_a_host_the_server_never_emits() -> None:
    """Dead native code, which no test in this repository can exercise."""
    extra = (_android_hosts() | _ios_hosts()) - _server_hosts()

    assert extra == set(), (
        f"handled but never emitted: {sorted(extra)} — wire it or remove it "
        "(Systemic Rules: dead code is deleted, not kept for later)"
    )


def test_the_two_shells_agree_with_each_other() -> None:
    """A flow that works on one platform and silently does nothing on the other."""
    assert _android_hosts() == _ios_hosts(), (
        f"Android only: {sorted(_android_hosts() - _ios_hosts())} | "
        f"iOS only: {sorted(_ios_hosts() - _android_hosts())}"
    )
