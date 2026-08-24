# Native WebView capability probe

Measures what LIA's web app can and cannot do when it runs inside a **native
WebView shell** (Capacitor), under the **real production security headers**, on
both engines: Android's Chromium WebView and iOS's WKWebView.

It is a **guard, not a report**. Facts that would silently break the product
fail the run; immovable platform limits are recorded as evidence instead.

```bash
task mobile:probe:android          # needs a booted emulator or device
task mobile:probe:ios              # macOS only (Xcode + simulator)

# options are passed through
task mobile:probe:android -- --settle 25000 --restart kill --out evidence.json
```

## Why it exists

The mobile shell architecture rests on a single bet: **the WebView loads the
remote web origin**, so the httpOnly session cookie, SSE and the whole BFF
contract keep working unchanged. That bet is only worth making if it is
measured — on both engines, under the real headers, and again after every
Capacitor or CSP change.

## No drift by construction

`server.mjs` **imports** `buildAppCsp`, `resolveCoepMode` and `buildHsts` from
[`apps/web/src/lib/csp.ts`](../../apps/web/src/lib/csp.ts) — the same pure module
`next.config.ts` and `csp.test.ts` use. Copying the policy here would recreate
exactly the duplication that module exists to prevent, and a probe measuring a
stale policy is worse than no probe.

The native project is **generated into the OS temp directory**, never vendored:
an Android or Xcode project would add thousands of unreviewable files, would
freeze the very thing being re-measured, and — because `task deploy:prod` rsyncs
the WORKING TREE, untracked files included — could be shipped to production by
accident.

## What it asserts

| Assertion | Why it must hold |
|---|---|
| Native bridge injected under the production CSP | Capacitor injects out-of-band (`addDocumentStartJavaScript` / `WKUserScript`) and its bundled JS contains no `eval`, so `script-src` should not apply. Asserted rather than assumed. |
| httpOnly session cookie invisible to JavaScript | LIA's XSS-proof design ([`api-client.ts`](../../apps/web/src/lib/api-client.ts)) depends on it. |
| `credentials:'include'` carries the session cookie | The BFF contract; the API accepts nothing else ([`session_dependencies.py`](../../apps/api/src/core/session_dependencies.py)). |
| Cross-site credentialed call keeps its cookie | Production splits the app and the API across two origins, so this is the path every authenticated call takes. See below. |
| Session cookie survives a cold restart | See the flush hazard below. |
| SSE streams | The chat rail depends on it. |
| Service Worker registers | Offline shell, [ADR-146](../../docs/architecture/ADR-146-Offline-PWA.md). |
| The production CSP is genuinely enforced | A cross-origin `fetch` must be refused. |
| Voice and geolocation APIs reachable | `useVoiceInput`, `useGeolocation`. |

## Platform limits it records (design inputs, not failures)

Measured on Android 16 / WebView 133, both under `COEP: credentialless` and
`require-corp`:

- **No Push API and no Notifications API.** Web push cannot work in either
  WebView, so push must be native on **both** platforms. `UserFCMToken` already
  carries `device_type ∈ {android, ios, web}`, so no schema change is needed.
- **No cross-origin isolation, therefore no `SharedArrayBuffer`.** Unchanged by
  the COEP value — it is not a header choice. `isSherpaKwsSupported()` returns
  false and voice mode degrades to tap-to-speak, so the **wake word is lost in
  the shell on Android too**, not only on iOS where it is already lost.

## The API origin: what the probe can and cannot reproduce

Production serves `connect-src 'self' https://lia-back.jeyswork.com …` from
`https://lia.jeyswork.com`: **the API is a separate origin**, so every
authenticated call is a cross-origin credentialed request. `buildAppCsp` takes
the API URL as a parameter, so the probe passes one and gets the production
`connect-src` for free.

Production's exact shape — two different **hosts** under one registrable domain
— cannot be reproduced on loopback, and the reason is worth stating so nobody
"fixes" it back:

- `app.localhost` / `api.localhost` *look* right and are not. For an unknown TLD
  the registrable domain is the whole name, so those two are **different sites**.
  Measured: the `SameSite=Lax` cookie was correctly withheld.
- A real registrable domain (`app.`/`api.lia-probe.test`) needs TLS to remain a
  secure context, and without a secure context there are no Service Workers left
  to measure. The two requirements exclude each other on loopback.

So the probe **bounds** production rather than pretending to reproduce it:

| Mode | Relationship | Treatment |
|---|---|---|
| `--api-host localhost` (default) | cross-origin, same host | **asserted** — proves the CORS + credentials plumbing carries cookies |
| `--api-host 127.0.0.1` | genuinely cross-site | **advisory** — records the ITP difference between engines |

Production sits between the two. That it works under WebKit's ITP is evidenced
outside this harness: LIA's web app runs in Safari on iOS today, on the same
engine with the same origin split.

The cross-site mode matters because the engines differ.
`CookieManager.setAcceptThirdPartyCookies` defaults to **false** on Android
WebView; Capacitor enables it unconditionally — `Bridge.create()` →
`MockCordovaWebViewImpl.init()` → `CapacitorCordovaCookieManager` →
`setAcceptThirdPartyCookies(webView, true)` — so Android permits it, while
WKWebView's ITP blocks it. **Deployment constraint: on iOS, an instance whose
API lives on a different registrable domain would not work.**

## What WKWebView gave, and the one architectural trade-off

Measured on iOS: the bridge injects under the strict CSP, the httpOnly cookie
stays invisible to JavaScript, `credentials:'include'` carries it, it survives a
cold restart, SSE streams, and the CSP is enforced. Two results need naming:

- **No Service Worker.** WKWebView hides `navigator.serviceWorker` unless the
  app declares `WKAppBoundDomains` in Info.plist *and* sets
  `limitsNavigationsToAppBoundDomains`. That list is **static, capped at ten
  domains, and cannot be extended at runtime**, so it is incompatible with a
  server URL chosen by the user at first launch — but perfectly compatible with
  a per-deployment build, where the list can be generated from the configured
  URL. Declaring it also **relaxes ITP between the listed domains**, which would
  settle the cross-site question above at the same time. Recorded as an advisory
  on iOS; still asserted on Android, where it works unconditionally.
- **`getUserMedia=false` was the probe's own fault**, not the platform's: the
  generated Info.plist had no `NSMicrophoneUsageDescription`. `scaffold.mjs` now
  adds the usage descriptions, so the answer measures WKWebView rather than a
  missing key.

## Advisory checks

An advisory check is measured and reported (`NOTE`) but never fatal: it records
a platform behaviour the design accounts for, rather than a contract the shell
broke. They stay in the same list on purpose — a limit that quietly disappears
from the report is a limit nobody revisits.

## The cookie flush hazard

Android WebView writes its cookie store to disk on a **~30 s timer**, and
Capacitor never calls `CookieManager.flush()`. Measured: a restart 28 s after
the cookie was set **loses it**; the same restart at 60 s keeps it.

A user who signs in and leaves the app within that window is signed out — the
most likely moment for someone to background the app. The shell owes a
`CookieManager.getInstance().flush()` on pause. Reproduce with
`-- --settle 25000`.

## iOS specifics, established on a generated project

Three assumptions that would each have burned a CI run were checked against a
real `npx cap add ios` output rather than trusted:

- **Capacitor 8 uses Swift Package Manager, not CocoaPods.** It generates
  `ios/App/App.xcodeproj` plus `CapApp-SPM/Package.swift`, and **no
  `.xcworkspace`** — so the build must use `-project`, never `-workspace`.
- **No scheme is shared.** Schemes appear under `xcuserdata` the first time
  Xcode opens the project, which never happens on a runner. `run.mjs` asks
  `xcodebuild -list` and falls back to `-target App`.
- **`server.cleartext` is Android-only.** Capacitor's iOS platform ignores it
  and the generated Info.plist has no `NSAppTransportSecurity` key at all, so
  `scaffold.mjs` adds an exception **scoped to `localhost`** —
  `NSAllowsArbitraryLoads` would disable ATS app-wide and is never a shape to
  copy into a shipping shell. The patch is idempotent and CRLF-tolerant.

## Continuous integration

`.github/workflows/mobile-webview-probe.yml` runs both platforms on manual
dispatch and uploads each evidence JSON. iOS uses a GitHub-hosted `macos-latest`
runner, free for this public repository — the only way to measure WKWebView
without a Mac.

**The engine version is chosen, not inherited.** The first iOS run measured an
iOS 18.7 simulator because the runner defaults to an older Xcode — an answer
about the wrong engine. The workflow now selects the newest Xcode present and
fetches its iOS platform, and `run.mjs` picks an iPhone on the **highest**
available runtime, parsing `…SimRuntime.iOS-26-0` numerically so `iOS-9` cannot
outrank `iOS-18`.

## Pinning

`CAPACITOR_VERSION` in `scaffold.mjs` is pinned **exactly**, not ranged: a guard
whose dependency floats can change its answer without changing its evidence.
Bumping it is deliberate and must be followed by a fresh run of both platforms.
