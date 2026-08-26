# `apps/mobile` — the native shells

One published app per store, a **client for a self-hosted LIA server**: it asks
for the server address at first launch and renders that server's web app in a
native WebView. Not a build dedicated to one instance — that would demand an
Apple developer account from every self-hoster.

Full context, measurements and store procedures:
[GUIDE_MOBILE_ANDROID.md](../../docs/guides/GUIDE_MOBILE_ANDROID.md) ·
[GUIDE_MOBILE_IOS.md](../../docs/guides/GUIDE_MOBILE_IOS.md).

```bash
task mobile:prepare:android    # regenerate android/ and lay our sources on top
task mobile:build:android      # → app-debug.apk
task mobile:build:ios          # macOS only; compilation is the Swift's only check
```

## What is versioned, and what is not

`android/` and `ios/` are **generated and gitignored**. `cap add` writes
thousands of files nobody can review, they conflict on every Capacitor upgrade,
and `task deploy:prod` rsyncs the working tree — a generated Xcode project would
ship to the Raspberry Pi.

What *is* versioned is `native/`: the handful of files that are ours.

| File | Why it exists |
|---|---|
| `native/android/.../MainActivity.java` | Points the WebView at the stored server, and flushes cookies on pause |
| `native/android/.../ServerUrlStore.java` | Where the origin lives; refuses anything but HTTPS |
| `native/android/.../ServerUrlPlugin.java` | The setup screen's four calls: get, probe, set, restart |
| `native/ios/.../MainViewController.swift` | Same two jobs, plus registering the plugin |
| `native/ios/.../ServerUrlStore.swift`, `ServerUrlPlugin.swift` | The iOS halves |
| `native/ios/.../Main.storyboard` | Points the scene at our view controller |
| `www/index.html` | The setup screen |

`scripts/prepare.mjs` regenerates, overlays, and — because an overlay hides
whatever it replaces — **reports when upstream changes a file we shadow**.
`native/upstream-baseline.json` holds those hashes; a Capacitor upgrade that
touches `MainActivity.java` or the storyboard says so instead of being silently
overridden for years. Fold the new template into `native/`, then re-run with
`--accept-drift`.

## Why the setup screen is HTML

It could have been an Android layout and a SwiftUI view. It is one bundled page
instead, so its wording, its **six languages**, its dark mode and its
accessibility live where the rest of the product's do — written once, not twice.
The native layer is reduced to four methods.

The i18n is inline, exactly like
[`apps/web/public/offline.html`](../web/public/offline.html): this screen runs
before any server is known, so there is no app bundle to ask.

## Why the address is checked natively

The screen is served from the shell's own local origin, so calling the server
from JavaScript is a cross-origin request — and the API's `CORS_ORIGINS` names
the web app, never a shell. A JS check would have reported **every correctly
configured server** as unreachable. `ServerUrlPlugin.probe` asks from the native
side, where CORS does not exist.


## Why push works differently on each platform

The two platforms do not have the same problem, so they do not get the same
answer (ADR-246).

**Android** initialises Firebase at runtime with options the user's own server
publishes — `PushRegistrar.java`. There is deliberately **no**
`google-services.json` in this repository: shipping one would tie every install
to a single Firebase project, the publisher's, and route every self-hoster's
notifications through it. Capacitor's generated `build.gradle` already applies
the `google-services` plugin only when that file exists, so leaving it out is the
supported path rather than a workaround.

**iOS cannot do the same.** APNs authenticates against the Apple Developer team
that owns the bundle identifier, and a `.p8` key covers every app in that team —
so a self-hosted server can never notify the published app, and the key can never
be distributed. `PushRegistrar.swift` registers with APNs natively and exchanges
the device token for an opaque handle at a **wake relay**. No Firebase SDK is
embedded on iOS at all.

Both registrations happen **natively**, and that is not an implementation
detail: the page runs on the user's own server origin, so calling a relay from
JavaScript is cross-origin, and a relay serving every self-hosted server cannot
enumerate their origins in a CORS policy. Same reasoning as the address check
above.

## Why there are two bundled pages

`www/index.html` is the setup screen, shown before any server is known.
`www/offline.html` is what Capacitor loads when a navigation to the server fails
(`server.errorPath`) — load-bearing on iOS, which has no service worker and would
otherwise show WebKit's own error page inside the app.

Both carry their own inline translations for all six languages, because neither
has an app bundle to ask. `apps/api/tests/unit/test_mobile_shell_pages_guard.py`
holds that parity: they are the only user-facing text in the repository the i18n
gate cannot see, since it compares locale files and these have none.

The offline screen offers a way to **forget** the stored server, not only a
retry. An address mistyped on first launch otherwise produces that screen on
every launch forever, with reinstalling as the only remedy.

## Verification

Android is verified end to end on an emulator; iOS compilation runs on a
GitHub-hosted macOS runner (`mobile-webview-probe.yml`), which is the only check
this repository can give Swift — there is no native test harness.

Platform behaviour itself — what a WebView can and cannot do under LIA's real
production headers — is measured separately by
[`scripts/mobile-probe/`](../../scripts/mobile-probe/README.md).
