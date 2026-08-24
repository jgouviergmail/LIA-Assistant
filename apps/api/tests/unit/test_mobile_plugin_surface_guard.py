"""The shell's plugin surface says the same thing in four places.

A Capacitor plugin method has to be declared four times to work: the Java
method, the Swift method, the Swift `pluginMethods` list, and the JavaScript
that calls it. Three of those four fail **silently** when they disagree.

- A Swift method missing from `pluginMethods` compiles, ships, and rejects
  every call at runtime with "not implemented" — the bridge never sees it.
- A method on one platform and not the other builds cleanly on both, and the
  feature simply does not exist on one of them.
- JavaScript calling a name nobody implements is a rejected promise inside a
  `catch`, which is exactly what a genuine failure also looks like.

None of that is caught by a compiler, a linter, or the shells' build workflow.
It is caught here, by reading the four declarations and comparing them.

The one asymmetry allowed is documented below: a plugin method may exist
natively without a web caller, because two of them are called from the shell's
own bundled pages rather than from the app.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
ANDROID_PLUGIN = (
    ROOT
    / "apps"
    / "mobile"
    / "native"
    / "android"
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "lia"
    / "assistant"
    / "LiaShellPlugin.java"
)
IOS_PLUGIN = ROOT / "apps" / "mobile" / "native" / "ios" / "App" / "App" / "LiaShellPlugin.swift"


def _android_methods() -> set[str]:
    """Methods Java exposes to the bridge, by their `@PluginMethod` annotation."""
    source = ANDROID_PLUGIN.read_text(encoding="utf-8")
    return set(re.findall(r"@PluginMethod\s+public void (\w+)\(", source))


def _ios_implemented() -> set[str]:
    """Methods Swift actually implements."""
    source = IOS_PLUGIN.read_text(encoding="utf-8")
    return set(re.findall(r"@objc func (\w+)\(_ call: CAPPluginCall\)", source))


def _ios_declared() -> set[str]:
    """Methods Swift ADVERTISES to the bridge."""
    source = IOS_PLUGIN.read_text(encoding="utf-8")
    return set(re.findall(r'CAPPluginMethod\(name: "(\w+)"', source))


def test_ios_declares_every_method_it_implements() -> None:
    """The silent one: an undeclared method rejects every call at runtime.

    It compiles. It ships. The bridge simply never learns the method exists,
    and the page sees a rejected promise indistinguishable from a real failure.
    """
    implemented = _ios_implemented()
    declared = _ios_declared()

    assert implemented - declared == set(), (
        f"implemented but not in pluginMethods: {sorted(implemented - declared)} — "
        "the bridge will reject every call to them"
    )


def test_ios_implements_every_method_it_declares() -> None:
    """The mirror image: an advertised method nobody wrote."""
    implemented = _ios_implemented()
    declared = _ios_declared()

    assert (
        declared - implemented == set()
    ), f"declared but not implemented: {sorted(declared - implemented)}"


def test_the_two_platforms_offer_the_same_surface() -> None:
    """A method on one platform only is a feature missing from the other.

    Both builds stay green, both shells ship, and the capability is simply
    absent from one of them — discovered by a user, on a device.
    """
    android = _android_methods()
    ios = _ios_implemented()

    assert (
        android == ios
    ), f"Android only: {sorted(android - ios)} | iOS only: {sorted(ios - android)}"


def test_every_method_the_shell_offers_has_a_caller() -> None:
    """Nothing native exists that nothing calls.

    Dead code in a native shell is worse than dead code elsewhere: it cannot be
    exercised by any test in this repository, so it rots invisibly until
    somebody builds on it.

    Callers live in two places, both legitimate — the web app (`src/lib/native`)
    and the shell's own bundled pages, which run before any server is known.
    """
    callers = ""
    for path in (
        ROOT / "apps" / "web" / "src" / "lib" / "native",
        ROOT / "apps" / "mobile" / "www",
    ):
        for file in sorted(path.rglob("*")):
            if file.is_file() and file.suffix in {".ts", ".tsx", ".html"}:
                callers += file.read_text(encoding="utf-8")

    unused = {method for method in _android_methods() if f"{method}(" not in callers}

    assert unused == set(), (
        f"no caller anywhere for: {sorted(unused)} — wire it or remove it "
        "(Systemic Rules: dead code is deleted, not kept for later)"
    )
