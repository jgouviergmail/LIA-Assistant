# ADR-246: notifying a phone whose app you are not allowed to notify

**Status**: Accepted (2026-08-24)
**Deciders**: LIA core team (arbitration by the project owner, 2026-08-24)
**Technical story**: native shells programme, lot 2c. Companion to the shells themselves ([GUIDE_MOBILE_ANDROID](../guides/GUIDE_MOBILE_ANDROID.md), [GUIDE_MOBILE_IOS](../guides/GUIDE_MOBILE_IOS.md)) and to [ADR-146](ADR_INDEX.md), whose offline page cannot reach one of them.

## Context

LIA is self-hosted, and the native shells are published **once per store** — one
Android app, one iOS app, each pointed at whichever server its user runs. That
decision (taken when `WKAppBoundDomains` turned out not to constrain a remote
`server.url`) is what makes the shells maintainable by one person. It is also what
breaks push notifications, and it breaks them asymmetrically.

**Android is fine, and the reason is worth stating.** Firebase Cloud Messaging
identifies a sender by project, not by publisher. A device can initialise Firebase at
runtime with options fetched from its own server — `applicationId`, `apiKey`,
`projectId`, `gcmSenderId`, the four values every Android build already ships inside
its APK — and receive notifications from the Firebase project *that server owns*.
Nothing passes through the publisher. Baking a `google-services.json` into the binary
would have done the opposite: one project, the publisher's, for every install.

**iOS cannot work that way at all.** FCM reaches an iPhone only through APNs, and APNs
authenticates a provider with a key issued to the Apple Developer team that owns the
bundle identifier. A self-hosted deployment does not own `com.lia.assistant`. Worse,
an APNs `.p8` key is valid for **every app in the team**, so distributing one to
self-hosters would hand each of them push rights over the publisher's entire account.
There is no configuration that fixes this; it is how Apple's trust model works.

The consequence is concrete and was measured against the existing product: the iOS
PWA **does** receive Web Push today (iOS 16.4+, added to the home screen). A native
iOS app with no notifications would therefore be, on this one point, **worse than what
users already have**.

Three options were put to the owner: ship Android push and defer iOS; run a relay; or
close the door and document it. The owner chose the relay.

## Decision

### 1. One acquisition contract, two routes underneath

`GET /notifications/push-config` answers, per platform, with what that platform needs:
Firebase options for Android, a relay URL for iOS, `null` where the deployment offers
nothing. The web layer fetches it and hands it to the shell **whole**; each platform
reads its own half.

The web app never branches on which platform it is running on, and never reads a
platform-specific field. A third platform is a native change, not a web change.

`null` is a real answer and is shown to the user. Registering a token that nothing can
ever send to looks exactly like working, until the first notification does not arrive.

### 2. The relay is a mode of the API, disabled by default

`domains/push_relay/`, behind `PUSH_RELAY_ENABLED`, served by **exactly one**
deployment: the one that publishes the app. Every other deployment *calls* a relay
(`PUSH_RELAY_URL`) without operating one.

`PUSH_RELAY_URL` has **no default**. A default would enrol every self-hosted
deployment into telling a third party when its users are woken — by inheritance rather
than by decision.

Enabling the relay without its credentials **refuses to boot**. A half-configured
relay accepts registrations and fails every push, which reads as "the relay is down"
from one end and "notifications don't work" from the other, with nothing anywhere
naming the missing variable.

### 3. The relay carries no content, and stores nothing

It sends one fixed sentence, from a table with no parameters
(`core/i18n_push_relay.py`), in the six languages LIA speaks. The shell then fetches
the real content from **its own server**, over the user's own session.

It keeps no database. A handle is an authenticated ciphertext carrying the device
token itself, sealed with a Fernet key that is deliberately **not** the application's
`fernet_key` — rotating it invalidates every handle at once, a panic button that must
not also force re-encrypting every connector token. Two seals of one device differ, so
handles held by two servers cannot be correlated. Handles expire; the shell
re-registers on every launch, so expiry is self-healing.

**What the relay unavoidably learns, and what this ADR does not pretend otherwise
about:** that some device was woken, when, and the IP address of the server that asked.
Not who, not from which account, not about what.

### 4. The delivery route travels with the token, not with the configuration

A shell registering through a relay prefixes its token `relay:`. The server branches on
that prefix.

Inferring the route from configuration would have been wrong: a deployment can
legitimately hold both relayed devices and devices reached through its own Apple
account. The shell is the only party that *knows* which route it used, so the shell is
what says it.

### 5. Doubt never deletes

A wake answers with an outcome and an actionable `should_forget_handle`. That flag is
true only for the two outcomes a retry can never fix — a handle we cannot read, and a
device Apple says is gone.

An unreachable relay, a 5xx, a 429, an answer we cannot parse, a topic **we**
mistyped: all keep the handle. Keeping a dead handle costs one HTTP call per
notification. Dropping a live one silences a phone until its owner happens to relaunch
the app — and a single wrong environment variable of ours would do it to everyone at
once.

### 6. iOS talks to Apple directly; the relay owns no Firebase

The relay signs an ES256 JWT and speaks APNs over HTTP/2 (`h2`, `httpx`, `pyjwt`,
`cryptography` — all already present, no new dependency). The iOS shell embeds **no**
Firebase SDK: it registers with APNs natively, in about forty lines of Swift.

Android keeps Firebase, because FCM is the only transport there.

The asymmetry is deliberate. Each side is the simplest correct thing for its platform,
and the relay stays a small testable component rather than an SDK wrapper.

### 7. Registration is native on both platforms, for a reason already learned

The page runs on the user's own server origin, so calling a relay from JavaScript is
cross-origin — and a relay serving every self-hosted server cannot enumerate their
origins in a CORS policy. Every correctly configured deployment would have been
reported unreachable.

This is the same reasoning that had already moved the server health probe into the
shell. It is written down here so it is not rediscovered a third time.

### 8. The offline screen is bundled, not served

Capacitor's `server.errorPath` loads a local page when a main-frame navigation fails.
ADR-146's offline page cannot reach the iOS shell — `navigator.serviceWorker` is absent
from WKWebView (measured) — so without this the user gets WebKit's own "cannot open
page" inside an app.

It offers a retry that **rebuilds the bridge** (reloading would reload the local page)
and, more importantly, a way to forget the stored server. An address mistyped on first
run otherwise produces that screen on every launch forever, with reinstalling the app
as the only remedy.

## Consequences

**Gained.** Notifications on both native platforms. Android with no third party
involved at all. iOS at the cost of one metadata-only hop, stated plainly in the
guides rather than buried.

**Accepted.** The publisher now operates a service other people depend on. It is small
— stateless, two endpoints, no database — but its availability is a commitment, and an
outage silences iOS notifications for every deployment pointed at it. Deployments that
prefer not to depend on it leave `PUSH_RELAY_URL` unset, and can publish their own iOS
build with their own Apple account if they want push without a relay.

**Refused.** Distributing the APNs key (it grants push over the whole team). Defaulting
`PUSH_RELAY_URL` (a privacy decision taken by a constant). Letting a caller influence
the notification text (the relay's entire justification is that it cannot).

**Also fixed on the way.** The per-IP rate-limit factory moved from
`domains/auth/dependencies` to `infrastructure/rate_limiting/ip_limiter`, keeping its
Redis keys byte for byte — four unrelated domains had been importing their limiters
from the auth domain. `_get_client_ip` and its duplicate test went with it: both
restated, less completely and on a since-refuted premise, what
`core/client_ip.py` already documents.
