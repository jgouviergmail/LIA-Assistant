# Guide: the iOS app — build, configure, ship, operate

> **Audience:** whoever builds and maintains LIA's iOS client.
> **Scope:** what the app is, every setting it needs, how it is published and
> updated, what recurs every year, and the WKWebView behaviours that were
> **measured** rather than assumed.
>
> **Status (2026-08-24).** The decision and the measurements are final. Two
> pieces already exist: the measurement harness
> ([scripts/mobile-probe/README.md](../../scripts/mobile-probe/README.md)), whose
> iOS leg runs on a GitHub-hosted macOS runner — the only way to reach WKWebView
> without a Mac — and the **API-side session handoff** that lets a shell complete
> a provider sign-in. The **app itself is planned**, not built; sections marked
> *(planned)* describe what it still owes.
>
> Android counterpart: [GUIDE_MOBILE_ANDROID.md](./GUIDE_MOBILE_ANDROID.md).

---

## 1. What the app is — and the one trade-off it accepts

**One app published once**, which asks for the server URL at first launch, the
way Home Assistant, Nextcloud and Jellyfin do. Not a build dedicated to one
instance: that would demand an Apple developer account **from every
self-hoster**.

The WebView loads the **remote origin**, because the API accepts nothing but its
session cookie ([apps/api/src/core/session_dependencies.py](../../apps/api/src/core/session_dependencies.py)).

### The trade-off, stated once

WKWebView hides `navigator.serviceWorker` unless the app declares
**`WKAppBoundDomains`** in `Info.plist` *and* sets
`limitsNavigationsToAppBoundDomains`. That list is **static, capped at ten
domains, and cannot be extended at runtime** — so it is incompatible with a
server URL the user types. Declaring it would also relax ITP between the listed
domains, which is tempting; it is still refused, because it would force the
per-deployment build model this architecture exists to avoid.

**What that costs: the ADR-146 offline page on iOS.** Nothing else — push is
native on both platforms anyway. The shell provides its own **native offline
screen** instead *(planned)*, which is what the comparable apps do and reads
better than a web fallback.

---

## 2. What is measured on this engine

**iOS 26.5, iPhone 17 simulator**, Capacitor 8.5.0, under LIA's real production
headers — imported from [apps/web/src/lib/csp.ts](../../apps/web/src/lib/csp.ts),
never copied.

| Behaviour | Result |
|---|---|
| Capacitor bridge under the strict CSP (no `unsafe-eval`) | **works** — `WKUserScript` injection is out of band |
| httpOnly session cookie readable from JavaScript | **no** — `CapacitorCookieManager` filters `!isHTTPOnly` |
| `credentials:'include'` carries the session cookie | **yes** |
| Session cookie survives a cold restart | **yes** — no flush hazard here, unlike Android |
| Cross-origin credentialed call to a separate API origin | **yes** |
| Server-Sent Events | **yes** |
| Service Worker | **absent** — see the trade-off above |
| Notifications / Push API | **absent** → push must be native, and on iOS that needs a relay (§5) |
| `crossOriginIsolated` / `SharedArrayBuffer` | **absent** → no wake word (already the case in Safari) |
| `getUserMedia`, geolocation | **yes**, once the usage descriptions are declared |

Re-measure on a macOS runner:

```bash
gh workflow run mobile-webview-probe.yml --ref main
```

### Cross-site is blocked, same-site is not

WebKit's ITP blocks cross-**site** credentialed cookies. The probe measures that
deliberately and records it as a **deployment constraint, not a defect**:

> **An instance whose API lives on a different registrable domain will not
> authenticate on iOS.** Keep `lia.example.com` and `lia-back.example.com` under
> one registrable domain.

Production's own split is same-site, and the web app already runs in Safari on
iOS today — the same engine, the same origin split.

---

## 3. Prerequisites

| Tool | Why | Note |
|---|---|---|
| macOS + Xcode | the only way to build for iOS | a GitHub-hosted `macos-latest` runner is free for this public repository |
| Apple Developer Program | signing and publishing | 99 USD per year |
| An iPhone simulator runtime | measurement | see the version trap in [§9](#9-traps-measured-on-this-platform) |

There is **no CocoaPods step**: Capacitor 8 generates `App.xcodeproj` plus
`CapApp-SPM/Package.swift` and uses Swift Package Manager. There is **no
`.xcworkspace`** — build with `-project`.

---

## 4. Creating the project *(planned)*

Generated, never vendored — the same reasoning as on Android, plus the fact that
an Xcode project is unreviewable in a pull request.

```bash
# planned: the shell lives in apps/mobile/, generated from the config it owns
npx cap add ios
npx cap sync ios
```

`CapacitorHttp` and `CapacitorCookies` stay disabled (their default). On iOS,
`CapacitorCookies` does not leak the httpOnly cookie either — `getCookies()`
filters `!$0.isHTTPOnly` — but its observer copies every WebView cookie into the
process-wide `HTTPCookieStorage.shared`, widening where the session lives for no
benefit here.

---

## 5. Configuration

### The server URL is chosen at runtime

`CAPBridgeViewController.instanceDescriptor()` is **`open`**, and
`InstanceDescriptor.serverURL` is a read-write property, so a subclass supplies
the stored value:

```swift
// planned: read the URL the user typed at first launch
override func instanceDescriptor() -> InstanceDescriptor {
    let descriptor = super.instanceDescriptor()
    descriptor.serverURL = UserDefaults.standard.string(forKey: "lia_server_url")
    return descriptor
}
```

Validate before storing: HTTPS only, reachable, answering LIA's health endpoint.

### Info.plist keys the app needs

| Key | Why |
|---|---|
| `NSMicrophoneUsageDescription` | **without it `getUserMedia` is simply absent** — this produced a false negative in the first measurement |
| `NSCameraUsageDescription` | media capture |
| `NSLocationWhenInUseUsageDescription` | geolocation |
| `NSLocationAlwaysAndWhenInUseUsageDescription` | background geolocation *(planned, if that feature ships)* |
| `NSFaceIDUsageDescription` | biometric unlock *(planned)* |

**Do not** set `NSAllowsArbitraryLoads`: it disables App Transport Security for
the whole app. The probe declares an exception scoped to `localhost` only,
because it serves over loopback; a shipping app talks HTTPS and needs none.

### PrivacyInfo.xcprivacy

Apple requires a privacy manifest declaring collected data types and the reasons
for using certain APIs. Fill it from what the app genuinely does — the WebView
carries LIA's own data handling, and the native layer adds push tokens, optional
biometrics and optional location.

---


### Push notifications — the one thing a self-hosted server cannot do alone

This is the platform's hardest constraint, and it has no configuration that
fixes it. Read it before promising a user notifications.

**Why.** FCM reaches an iPhone only through APNs, and APNs authenticates a
provider with a key issued to the Apple Developer team that **owns the bundle
identifier**. One app is published for every self-hosted server, so that team is
the app's publisher — not you. An APNs `.p8` key is moreover valid for *every*
app in a team, so it cannot be handed out. Android has no equivalent problem:
FCM identifies a sender by project, so an Android device talks to whichever
Firebase project its own server owns.

**What LIA does about it** (ADR-246). The shell registers with a **wake relay**
— the deployment that publishes the app — and receives an opaque handle. Your
server sends that handle to the relay when it wants to notify the device; the
relay emits a **fixed, contentless sentence** in the user's language, and the
app fetches the real content from **your** server once opened.

```bash
# On any deployment that wants iOS notifications:
PUSH_RELAY_URL=https://lia.jeyswork.com   # no default, on purpose
```

**What the relay learns, stated plainly:** that some device was woken, when, and
the IP address of the server that asked. Not who, not from which account, not
about what. It stores nothing at all — the handle *is* the record, sealed, and
it expires.

**If that is not acceptable to you**, leave `PUSH_RELAY_URL` unset. Your users
keep the iOS PWA (which does receive Web Push, added to the home screen), or you
publish your own iOS build under your own Apple Developer account and use plain
APNs — the delivery path branches on the token, not on configuration, so both
work side by side.

### Operating a relay (publishers only)

Only the deployment that publishes the app to the App Store turns this on.

```bash
PUSH_RELAY_ENABLED=true
PUSH_RELAY_SEAL_KEY=<Fernet key>       # NOT fernet_key: rotating this invalidates every handle at once
APNS_KEY_PATH=/run/secrets/apns.p8
APNS_KEY_ID=ABCDE12345
APNS_TEAM_ID=TEAM123456
APNS_TOPIC=com.lia.assistant
APNS_USE_SANDBOX=false                 # a token minted for one gateway is invalid on the other
```

Enabling it without any of those **refuses to boot**, naming the missing
variable. That is deliberate: a half-configured relay accepts registrations and
fails every send, which reads as "the relay is down" to a self-hoster and
"notifications don't work" to a user, with nothing anywhere naming the cause.

Two endpoints, no database, no scheduled job:

| Route | Who calls it | What it does |
|---|---|---|
| `POST /api/v1/push-relay/devices` | the iOS shell, natively | seals a device token into a handle |
| `POST /api/v1/push-relay/wake` | a self-hosted LIA server | sends the fixed notification |

Registration is native rather than from the page because the page runs on the
user's own server origin: calling the relay from JavaScript is cross-origin, and
a relay serving every self-hosted server cannot enumerate their origins in a
CORS policy.

**Rotating the seal key** invalidates every handle in circulation. Devices
recover on their next launch, since the shell re-registers each time — so it is
a usable panic button, not a one-way door.

### The offline screen

`server.errorPath` points at a bundled `www/offline.html`. This is **load-bearing
on iOS**: there is no service worker, so ADR-146's offline page can never run
here, and without this the user gets WebKit's own "cannot open page" inside the
app.

It offers a retry that rebuilds the bridge, and a way to forget the stored
server — the escape hatch from an address mistyped on first launch, which
otherwise produces that screen on every launch forever.

---

## 6. Building and signing *(planned)*

```bash
xcodebuild -project apps/mobile/ios/App/App.xcodeproj \
           -scheme App -sdk iphoneos -configuration Release archive
```

The generated project ships **no shared scheme** — schemes appear under
`xcuserdata` the first time Xcode opens it, which never happens on a runner. Ask
`xcodebuild -list` and fall back to `-target App`; the harness already does.

Signing certificates and provisioning profiles live in the CI secret store.
Apple certificates **expire yearly** — that renewal is the single most common
cause of a build that stopped working without anyone changing code.

---

## 7. Distribution

> Le pas-à-pas complet de la publication — comptes, signature, clé APNs,
> formulaires des consoles, risque de review et mises à jour — vit dans
> [GUIDE_MOBILE_PUBLICATION.md](GUIDE_MOBILE_PUBLICATION.md).

**App Store** is the primary channel: one listing serving every self-hoster.

App Review will ask for a working server and a demo account, since a client app
is untestable without one. LIA already has both — point the reviewer at the
public instance and its demo. Guideline 4.2 ("minimum functionality") is the risk
to plan for: a client with native push, biometric unlock, a share extension and
actionable notifications is what makes the app app-like rather than a wrapped
site. **Push is cited as the strongest single signal** — and it is required
anyway, since the Push API does not exist in a WebView.

**TestFlight** suits pre-release testing, with one caveat: **each build expires
after 90 days**, so it is not a distribution channel for a stable product.
**Ad Hoc** distribution lasts as long as the provisioning profile (a year) but is
capped at 100 registered devices.

---

## 8. Maintenance: what actually recurs

The shell's version is **decoupled from LIA's**. Do not add it to
`scripts/release/version_surfaces.py`: tying it to the LIA version would force an
App Store submission on every release, which this architecture exists to avoid.

| Recurrence | Task |
|---|---|
| Every LIA release | **nothing** — the server serves the new UI |
| 2–4× a year | Submit an update when the native layer changes |
| Yearly | Renew Apple certificates and provisioning profiles |
| Yearly | Apple Developer Program renewal (99 USD) |
| Yearly-ish | Capacitor major upgrade → re-run the probe on both engines |
| On any CSP/COEP change | Re-run the probe — it imports the real builders |

---

## 9. Traps measured on this platform

### The simulator runtime is not the one you assume

The first iOS measurement ran on **iOS 18.7** — two majors behind the target —
because the runner defaults to an older Xcode. An answer about the wrong engine
is worse than no answer. The workflow now selects the newest Xcode present, runs
`xcodebuild -downloadPlatform iOS`, and the harness picks an iPhone on the
**highest** runtime, parsing `…SimRuntime.iOS-26-0` numerically so `iOS-9` cannot
outrank `iOS-18`.

### A missing plist key looks exactly like a missing capability

`getUserMedia=false` was reported as a WKWebView limitation. It was
`NSMicrophoneUsageDescription` missing from the generated `Info.plist`. Always
ask whether the harness declared what the platform requires before concluding the
platform refuses it.



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
since 2023-07-24) — `WKWebView` explicitly. This breaks Google sign-in **and
every connector**.

The cookie the system browser receives is **not** the WebView's, which is why the
handoff exchanges a one-time code server-side rather than hoping the session
carries over.

**The API side is implemented**: a challenge on
`GET /auth/google/login`, a `lia://auth-callback?code=…` return, and
`POST /auth/native/callback` to redeem it — see
[apps/api/src/domains/auth/native_handoff.py](../../apps/api/src/domains/auth/native_handoff.py).
The return uses a **custom scheme, not a Universal Link**: Universal Links pin
domains at build time, and one published app serves every self-hosted server.
That is exactly why the code is bound to a verifier the shell keeps — an
intercepted link is inert.

What the shell still owes *(planned)*: `SFSafariViewController`, the scheme
registration, and keeping the verifier.

### Universal Links

`apple-app-site-association` must be served as `application/json`. Serving it as
a static extensionless file from `public/` does not guarantee the content type —
use a route handler *(planned)*. The i18n middleware does not interfere:
`.well-known` contains a dot, so the matcher `.*\..*` excludes it (verified
across locales).

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Page never loads | Server URL wrong, unreachable, or plain HTTP blocked by ATS | Validate at entry; require HTTPS |
| Authenticated calls fail, web works in Safari | API on a different registrable domain → ITP | Move the API under the same site |
| `getUserMedia` undefined | Missing usage description | Declare the Info.plist keys |
| `scheme App not found` on a runner | No shared scheme in the generated project | `-target App`, or share the scheme |
| Google sign-in shows `disallowed_useragent` | OAuth attempted inside the WebView | `SFSafariViewController` + Universal Link + session handoff |
| No offline page | No Service Worker without app-bound domains | Native offline screen — the accepted trade-off |
| Voice mode has no wake word | No cross-origin isolation | Expected; also absent in Safari today |

---

## 11. Related

- [scripts/mobile-probe/README.md](../../scripts/mobile-probe/README.md) — the measurement harness and its evidence
- [GUIDE_MOBILE_ANDROID.md](./GUIDE_MOBILE_ANDROID.md) — the Android counterpart, which keeps the Service Worker
- [GUIDE_FCM_PUSH_NOTIFICATIONS.md](./GUIDE_FCM_PUSH_NOTIFICATIONS.md) — the existing push path this app reuses
- [ADR-146](../architecture/ADR-146-Offline-PWA.md) — the offline shell, replaced natively here
- [ADR-136](../architecture/ADR-136-COEP-Posture-And-Widget-Failure-States.md) — why WebKit gets no cross-origin isolation
