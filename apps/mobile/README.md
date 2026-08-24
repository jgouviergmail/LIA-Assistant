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

## Verification

Android is verified end to end on an emulator; iOS compilation runs on a
GitHub-hosted macOS runner (`mobile-webview-probe.yml`), which is the only check
this repository can give Swift — there is no native test harness.

Platform behaviour itself — what a WebView can and cannot do under LIA's real
production headers — is measured separately by
[`scripts/mobile-probe/`](../../scripts/mobile-probe/README.md).
