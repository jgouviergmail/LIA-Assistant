# Guide: the Android app — build, configure, ship, operate

> **Audience:** whoever builds and maintains LIA's Android client.
> **Scope:** what the app is, every setting it needs, how it is published and
> updated, what recurs every year, and the platform behaviours that were
> **measured** rather than assumed.
>
> **Status (2026-08-24).** The decision and the measurements are final. Two
> pieces already exist: the measurement harness
> ([scripts/mobile-probe/README.md](../../scripts/mobile-probe/README.md)), which
> asserts the invariants this guide relies on, and the **API-side session
> handoff** that lets a shell complete a provider sign-in. The **app itself is
> planned**, not built; sections marked *(planned)* describe what it still owes.
>
> iOS counterpart: [GUIDE_MOBILE_IOS.md](./GUIDE_MOBILE_IOS.md).

---

## 1. What the app is — and what it is not

It is **a client for a self-hosted LIA server**, in the sense Home Assistant,
Nextcloud and Jellyfin are: **one app published once**, which asks for the
server URL at first launch. It is not a build dedicated to one instance, and it
is not a second frontend.

- **One source of truth.** The UI is `apps/web`, served by the user's own LIA
  server. The app renders it in a native WebView and adds what the web cannot do.
- **The WebView loads the REMOTE origin.** This is not a preference: the API
  accepts nothing but its session cookie
  ([apps/api/src/core/session_dependencies.py](../../apps/api/src/core/session_dependencies.py)),
  so the page must run on the same origin the browser would use. A locally
  bundled build would lose the session entirely.
- **A LIA release ships nothing to the store.** Deploying the server updates all
  surfaces at once. An app submission is needed only when the *native* layer
  changes — see [§8](#8-maintenance-what-actually-recurs).

### The decision, and its price

`WKAppBoundDomains` on iOS would restore Service Workers there, but it is a
static list frozen at build time and therefore incompatible with a server URL
typed by the user. **One published app wins over a Service Worker on iOS** —
otherwise every self-hoster would need their own Apple developer account. Android
is unaffected: Service Workers work here unconditionally (measured).

---

## 2. What is measured on this engine

Android 16 / WebView 133, Capacitor 8.5.0, under LIA's **real production
headers** — the probe imports them from
[apps/web/src/lib/csp.ts](../../apps/web/src/lib/csp.ts) rather than copying them.

| Behaviour | Result |
|---|---|
| Capacitor bridge under the strict CSP (no `unsafe-eval`) | **works** — injected out of band, and its bundled JS contains no `eval` |
| httpOnly session cookie readable from JavaScript | **no** — the BFF contract holds |
| `credentials:'include'` carries the session cookie | **yes** |
| Cross-origin credentialed call to a separate API origin | **yes** |
| Server-Sent Events | **yes** — the chat rail works |
| Service Worker (offline shell, ADR-146) | **yes**, scope `/` |
| Notifications / Push API | **absent** → push must be native |
| `crossOriginIsolated` / `SharedArrayBuffer` | **absent**, even under COEP `require-corp` → **no wake word** |
| `getUserMedia`, `MediaRecorder`, geolocation | **yes** |

Two consequences worth stating plainly:

- **Push is native, and it stays yours** (ADR-246, delivered). The Push API
  does not exist in a WebView on either platform, so the shell asks Firebase
  directly. What matters is *which* Firebase: the app initialises it **at
  runtime** with options your own server publishes, so notifications come from
  the Firebase project **you** own. Nothing passes through the app's publisher
  — unlike iOS, which has no such option (see the iOS guide).
- **The wake word is lost.** `isSherpaKwsSupported()` returns false without
  cross-origin isolation and voice mode degrades to tap-to-speak. This is a
  regression against the PWA, which keeps the wake word in Chrome. It is not a
  header choice — `require-corp` was measured and changes nothing.

Re-measure at any time:

```bash
task mobile:probe:android          # needs a booted emulator or device
```

The engine probe measures what the WebView can do; a second bench holds the
REAL shell to its own guarantees — setup screen, HTTPS refusal, the offline
screen on an unreachable server, deep-link routing and refusal, and the
"forget" escape hatch — by driving the debug build over the WebView devtools
socket, serverless by design (`scripts/mobile-probe/README.md`, shell bench
section, including the two live defects its first runs caught):

```bash
task mobile:verify:android         # builds the debug APK, drives the real app
```

---

## 3. Prerequisites

| Tool | Why | Note |
|---|---|---|
| JDK 21 | Gradle toolchain | Android Studio ships one under `jbr/` |
| Android SDK, platform-tools | build + `adb` | |
| Platform for the target API | compile SDK | API 37 = Android 17 |
| An emulator image or a device | measurement and manual testing | x86_64 on a PC; the ARM images will not boot |
| Google Play Console account | publishing | one-off 25 USD |

The measurement harness needs `ANDROID_HOME` (or `ANDROID_SDK_ROOT`) set; it
writes `local.properties` itself, with forward slashes — a backslash-escaped
Windows path makes Gradle fail with an opaque "syntax of the file name … is
incorrect" during dependency resolution.

---

## 4. Creating the project *(planned)*

The native project is **generated, not vendored**. Committing an Android project
would add thousands of unreviewable files and freeze the very thing that must be
re-measured; worse, `task deploy:prod` rsyncs the working tree — untracked files
included — so a stray build could reach production.

```bash
# planned: the shell lives in apps/mobile/, generated from the config it owns
npx cap add android
npx cap sync android
```

Two Capacitor plugins **must stay disabled**, and their defaults already are
(`pluginConfig.getBoolean("enabled", false)`):

- **`CapacitorHttp`** replaces `window.fetch` and `window.XMLHttpRequest` for the
  whole application. Enabling it would change cookie handling, streaming and
  cancellation semantics on every LIA API call.
- **`CapacitorCookies`** replaces `document.cookie`. It does not leak the
  httpOnly cookie on Android (the getter returns the original descriptor), but it
  moves cookie handling out of the browser for no benefit here.

A test asserts both stay off.

---

## 5. Configuration

### The server URL is chosen at runtime — delivered

`BridgeActivity.load()` calls `bridgeBuilder.setConfig(config).create()` and
`config` is a **protected** field, so `MainActivity` builds one from the stored
value before delegating:

```java
// apps/mobile/native/android/.../MainActivity.java
this.config = new CapConfig.Builder(this)
        .setServerUrl(ServerUrlStore.read(this))
        .create();
super.load();
```

`ServerUrlStore.normalise` refuses anything that is not a usable HTTPS origin,
and the setup screen additionally **probes** the address natively before storing
it (`LiaShell.probe`). Both matter: a typo saved silently produces an app that
never loads.

Two escape hatches exist for when it happens anyway. The offline screen
(below) offers "use a different server", which calls `LiaShell.forget` and sends
the next launch back to setup. Without it, reinstalling is the only remedy.


### Push notifications — your Firebase project, not the publisher's

Delivered in ADR-246. The app carries **no** `google-services.json`: it
initialises Firebase at runtime with options your server publishes, so
notifications originate from the Firebase project **you** own.

Set these three on your server (they are not secrets — every Android build
ships them inside its APK; find them in your project's `google-services.json`):

```bash
FIREBASE_ANDROID_APP_ID=1:123456789:android:abcdef   # mobilesdk_app_id, NOT the package name
FIREBASE_API_KEY=AIza...                             # current_key of the Android client
FIREBASE_SENDER_ID=123456789                         # project_number
FIREBASE_PROJECT_ID=your-project                     # already existed
```

Register `com.lia.assistant` as an Android app in that Firebase project, and
keep `FIREBASE_CREDENTIALS_PATH` pointing at the same project's service account
— the client options and the sending credentials must name **one** project.

**All four, or none.** Firebase refuses to initialise on a partial set, so
`GET /notifications/push-config` publishes `android: null` unless every value is
present, and the shell then tells the user push is unavailable rather than
registering a token nothing will ever send to.

Android 13+ makes notifications a runtime permission. The shell asks
(`POST_NOTIFICATIONS`), and a refusal is reported as a refusal — distinct from
"this server has no push configured", because the two send the user to different
places.

### The offline screen

`server.errorPath` in `capacitor.config.json` points at a bundled
`www/offline.html`, which Capacitor loads when a main-frame navigation fails.
Android *does* run the ADR-146 service worker, so this is belt and braces here —
it is load-bearing on iOS, which has no service worker at all.

It offers a retry that **rebuilds the bridge** (reloading would reload the local
page) and a way to forget the stored server.

### Deployment constraint to document for users

On **iOS**, WebKit's ITP blocks cross-**site** cookies, so an instance whose API
lives on a different registrable domain cannot authenticate. Android permits it
(Capacitor turns on third-party cookies unconditionally), but a self-hoster
should still be told: **keep the API on the same site as the web app** —
`lia.example.com` and `lia-back.example.com`, not `lia-api.other-domain.net`.

### Android 17 (API 37) behaviour changes that reach this app

From the [official behaviour-changes page](https://developer.android.com/about/versions/17/behavior-changes-17):

- **Certificate Transparency is enabled by default and cannot be opted out of.**
  A self-hoster whose certificate is not CT-logged would see connections refused.
  Certificates from public CAs (Let's Encrypt included) are logged; a private or
  internal CA needs verifying before telling users the app supports it.
- **ECH is used for TLS connections**, tunable per domain through the
  `<domainEncryption>` element of the network security configuration.

---

## 6. Building and signing *(planned)*

```bash
./gradlew assembleDebug        # local testing
./gradlew bundleRelease        # the AAB Play Console expects
```

Signing keys belong in the CI secret store, never in the repository. Losing the
upload key means losing the ability to update the listing — enrol in Play App
Signing so Google holds the app signing key and the upload key stays replaceable.

---

## 7. Distribution

**Play Store** is the primary channel: one listing, every self-hoster. Review is
substantially more permissive than Apple's, and a client for a self-hosted server
is a long-established category.

**Direct APK** remains available and costs nothing extra — the same artifact,
downloadable from a release. Useful for users who avoid stores, and for testing.
Android does not expire sideloaded builds, unlike TestFlight on iOS.

---

## 8. Maintenance: what actually recurs

The shell's version is **decoupled from LIA's**. Do not add it to
`scripts/release/version_surfaces.py`: that would tie it to the LIA version and
force a store submission on every release, which is exactly what this
architecture avoids.

| Recurrence | Task |
|---|---|
| Every LIA release | **nothing** — the server serves the new UI |
| 2–4× a year | Submit an update when the native layer changes |
| Yearly | Play Store `targetSdk` deadline |
| Yearly-ish | Capacitor major upgrade → re-run the probe on both engines |
| On any CSP/COEP change | Re-run the probe — it imports the real builders |

---

## 9. Traps measured on this platform

### The cookie flush window

**Android WebView writes its cookie store to disk on a ~30 s timer, and Capacitor
calls `CookieManager.flush()` nowhere in its lifecycle** — the only flush lives
inside the disabled `CapacitorCookies` plugin. Measured: a restart 28 s after the
session cookie was set **loses it**; the same restart at 60 s keeps it.

A user who signs in and leaves the app within that window is signed out — the
most likely moment for someone to background an app. **The shell owes a
`CookieManager.getInstance().flush()` on pause** *(planned)*. Reproduce the
hazard on demand:

```bash
task mobile:probe:android -- --settle 25000
```



### Every OAuth departure leaves for the system browser, not only sign-in

Google refuses OAuth from an embedded webview (`disallowed_useragent`), and that
applies to the ten connectors and to MCP servers exactly as it does to sign-in.
All of them go through `navigateToAuthorizationUrl` in the web app, which is
where the decision is made — once (ADR-246).

The return trip is a `lia://` deep link whose HOST names the flow:

| Host | Where the shell puts the user |
|---|---|
| `auth-callback` | `/native-auth` — spends the sign-in handoff code |
| `connector-callback` | `/dashboard/settings` |
| `mcp-callback` | `/dashboard/settings` |

The paths are fixed in the shell, never carried in the link: a deep link that
named its own destination would let whoever claims the custom scheme choose
where the WebView goes next.

Adding a fourth flow means adding its host in **three** places — the server's
`NativeDeepLinkHost`, both shells' maps, and (on Android) the manifest's
intent-filter. `apps/api/tests/unit/test_mobile_deep_link_hosts_guard.py`
compares all four declarations, because the failure is otherwise silent: the
user comes back from the browser to a screen that never changes.

### The offline screen also catches HTTP errors, not only network failures

Capacitor's `errorPath` redirects on `onReceivedError` **and**
`onReceivedHttpError` for the main frame. A server answering 404 to a
main-frame navigation therefore shows "your LIA is unreachable", which is a
misleading diagnosis.

In practice the shell only navigates to routes that exist — the server root and
`/native-auth`. The one way to reach this is a **shell newer than its server**:
tapping a sign-in deep link against a server that predates that route. It was
observed exactly once, during lot 2b, when production answered 404 to
`/native-auth` because the route lived only in the branch.

Capacitor offers no granularity here, and the alternative is worse: without
`errorPath`, a genuine network failure shows the engine's own error page inside
the app. The trade is deliberate — recorded so the next person does not
rediscover it as a bug.

### OAuth cannot run inside the WebView

Google refuses OAuth from embedded webviews (`disallowed_useragent`, enforced
since 2023-07-24) — `android.webkit.WebView` explicitly. This breaks Google
sign-in **and every connector**.

**The API side is implemented.** `GET /auth/google/login?native_challenge=…`
stores the challenge in the flow's server-side state; the callback returns
`lia://auth-callback?code=…` instead of setting a browser session; and
`POST /auth/native/callback` exchanges that code plus the verifier for the
session cookie — in the WebView's own jar. See
[apps/api/src/domains/auth/native_handoff.py](../../apps/api/src/domains/auth/native_handoff.py).

What the shell still owes *(planned)*: opening the system browser (Custom Tabs),
registering the custom scheme, drawing the verifier and keeping it, and handing
the deep link back to the WebView.

**Connectors need none of this.** Their callbacks are stateless — the user id
travels in the server-side OAuth state — so they already succeed without a
cookie. They only need the return trip.

### Emulator images

The ARM system images will not boot on an x86_64 host ("CPU Architecture 'arm' is
not supported by the QEMU2 emulator"). Install `system-images;android-NN;google_apis;x86_64`.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Page never loads | Server URL wrong, unreachable, or plain HTTP | Validate at entry; require HTTPS |
| Signed out on every launch | Cookie flush window | The native `flush()` on pause |
| Google sign-in shows `disallowed_useragent` | OAuth attempted inside the WebView | System browser + deep link + session handoff |
| TLS refused on API 37 | Certificate not CT-logged | Use a publicly-trusted, CT-logged certificate |
| Voice mode has no wake word | No cross-origin isolation in WebView | Expected; tap-to-speak is the documented fallback |
| No push | Web push does not exist in a WebView | Native FCM, `device_type='android'` |

---

## 11. Related

- [scripts/mobile-probe/README.md](../../scripts/mobile-probe/README.md) — the measurement harness and its evidence
- [GUIDE_MOBILE_IOS.md](./GUIDE_MOBILE_IOS.md) — the iOS counterpart and its different trade-offs
- [GUIDE_FCM_PUSH_NOTIFICATIONS.md](./GUIDE_FCM_PUSH_NOTIFICATIONS.md) — the existing push path this app reuses
- [ADR-146](../architecture/ADR-146-Offline-PWA.md) — the offline shell the Service Worker provides
- [ADR-210](../architecture/ADR-210-Un-Intent-Consomme-Ne-Se-Rejoue-Pas.md) — deep-link intents, which notifications reuse
