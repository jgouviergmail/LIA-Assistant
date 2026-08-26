"""The shell's two bundled pages speak the product's six languages.

Both run with no network and no app bundle to ask, so each carries its own
inline translation table. That makes them the only user-facing text in the
repository that the i18n parity gate cannot see: it compares locale FILES, and
these have none. A seventh language would be added everywhere else and silently
skip these two.

They are also the only screens a user can be stuck on. The setup screen is
where a first launch begins, and the offline screen is where a wrong address or
a downed server ends — both before any part of the product can help. Showing
either in English to someone who chose Chinese is worse here than anywhere
else, because there is nothing else on screen.

Guarded here rather than in the web suite because these files belong to
`apps/mobile`, which has no test harness of its own — the same reason the
demonstrator's route surface is checked from this suite.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

#: Frontend locale codes: these pages read `navigator.language`, which yields
#: `zh`, never the backend-canonical `zh-CN`.
EXPECTED_LOCALES = ("en", "fr", "de", "es", "it", "zh")

MOBILE_WWW = repo_root_or_skip() / "apps" / "mobile" / "www"

PAGES = ("index.html", "offline.html")


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("locale", EXPECTED_LOCALES)
def test_every_bundled_page_carries_every_locale(page: str, locale: str) -> None:
    """Each inline table declares all six languages."""
    source = (MOBILE_WWW / page).read_text(encoding="utf-8")

    assert re.search(rf"^\s+{locale}: {{", source, re.M), (
        f"{page} has no `{locale}:` entry — a user who chose {locale} would read "
        f"English on the one screen where nothing else can help them"
    )


@pytest.mark.parametrize("page", PAGES)
def test_every_locale_declares_the_same_keys(page: str) -> None:
    """No language is missing a string the others have.

    A missing key renders as `undefined` in the interface — worse than a
    fallback, because it looks like a bug in the app rather than a gap in a
    translation.
    """
    source = (MOBILE_WWW / page).read_text(encoding="utf-8")

    keys_by_locale: dict[str, set[str]] = {}
    for locale in EXPECTED_LOCALES:
        start = source.index(f"      {locale}: {{")
        end = source.index("}", start)
        keys_by_locale[locale] = set(re.findall(r"^\s+(\w+):", source[start:end], re.M)) - {locale}

    reference = keys_by_locale["en"]
    for locale, keys in keys_by_locale.items():
        assert keys == reference, (
            f"{page}: locale `{locale}` differs from `en` — "
            f"missing {sorted(reference - keys)}, extra {sorted(keys - reference)}"
        )


def test_the_offline_page_can_leave_a_server_that_never_answers() -> None:
    """The offline screen offers a way out, not only a way to retry.

    An address stored wrong on first run produces this screen on every launch,
    forever. Without a control that forgets it, the only remedy is reinstalling
    the app — which is how a typo becomes a support request.
    """
    source = (MOBILE_WWW / "offline.html").read_text(encoding="utf-8")

    assert "forget()" in source
    # And a retry has to rebuild the bridge: reloading would reload this local
    # page, which is not where the user is trying to go. Checked on the CODE,
    # with comments stripped — the page explains that choice in prose, and a
    # naive search finds the explanation and calls it the mistake.
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    assert "restart()" in code
    assert "location.reload()" not in code


class TestTheConfiguredStateKeepsWhatTheJsonDeclares:
    """Android's Builder path starts from NOTHING — it does not read the JSON.

    `MainActivity.load()` swaps in a Builder-built config the moment a server
    URL is stored, and every `server.*` value capacitor.config.json declares
    has to be carried across by hand, or it silently disappears in exactly the
    state where the app is actually used. Found the hard way: `errorPath` was
    dropped, so the offline screen never loaded once a server was configured —
    the only state where it matters. iOS is immune (`instanceDescriptor()`
    starts from the PARSED config and only overrides serverURL), which made the
    defect invisible to every platform-symmetric check.
    """

    ACTIVITY = (
        repo_root_or_skip()
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
        / "MainActivity.java"
    )
    CONFIG = repo_root_or_skip() / "apps" / "mobile" / "capacitor.config.json"

    def test_error_path_is_one_value_in_two_states(self) -> None:
        """The JSON governs the unconfigured state, the constant the other."""
        import json

        declared = json.loads(self.CONFIG.read_text(encoding="utf-8"))["server"]["errorPath"]
        activity = self.ACTIVITY.read_text(encoding="utf-8")

        assert f'OFFLINE_ERROR_PATH = "{declared}"' in activity, (
            f"capacitor.config.json declares errorPath={declared!r} but MainActivity "
            "carries a different value — the two states would show different screens"
        )
        assert ".setErrorPath(OFFLINE_ERROR_PATH)" in activity, (
            "MainActivity builds its config without carrying errorPath — the offline "
            "screen never loads once a server is configured"
        )

    def test_a_new_server_key_forces_a_decision_here(self) -> None:
        """The Builder cannot inherit what the JSON grows; someone must carry it."""
        import json

        declared = set(json.loads(self.CONFIG.read_text(encoding="utf-8"))["server"])

        # Keys the Builder call in MainActivity.load() is known to carry (the
        # URL itself comes from ServerUrlStore, not the JSON). Extending the
        # JSON without extending this set — and the Builder call — means the
        # new value exists only until the user configures a server.
        carried = {"errorPath"}

        assert declared <= carried, (
            f"capacitor.config.json declares server keys {sorted(declared - carried)} "
            "that MainActivity's Builder path does not carry — they vanish the "
            "moment a server URL is stored"
        )
