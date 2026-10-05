# Security and Privacy

## Are my conversations private?

Your account has controlled access, and conversations are isolated between users.

**Storage:** connector credentials and designated fields, such as saved locations, are encrypted. This does not encrypt every stored field: conversation messages are stored as database text, and the instance operator may have technical access.

**Providers:** LIA sends the context needed for a request to the AI and service providers configured for your instance. Their retention and possible training policies apply. Review those policies, provider settings and your hosting arrangements before sharing sensitive information.

## How is my data protected?

Several controls work together:
• Account authentication, OAuth with PKCE and server-side sessions with HTTP-only cookies
• CSRF protection, revocable sessions and audit records of sensitive actions
• HTTPS when configured by your operator, and encryption of credentials and designated stored fields
• Access controls between accounts and filtering of personal information in operational logs
• Context sent to configured providers only as needed for the selected features, under their own policies

**🌐 Reading the web:**
• Every address a page sends LIA to is checked before connecting, redirects included, one hop at a time
• The connection goes to the address that was checked: neither your internal network nor the server's can be reached this way
• A booby-trapped text (e-mail, page, message) is formatted in time proportional to its length and cannot stall the server

**💾 Backups:**
The deployment provides daily backup and restore-check tools. Your operator must enable and monitor them; recovery depends on the latest successful backup and the chosen retention policy.

**🧬 Software supply chain:**
• Every release ships a locked, cryptographically verified list of components (reproducible builds)
• All dependencies — including indirect ones — are automatically scanned for known vulnerabilities

## What data does LIA collect?

LIA stores the data needed for your account and the features you enable: profile and preferences, conversations, memories, selected documents, connected-service credentials and usage records.

Your home address and, if you opt in, your last known position are stored encrypted. Each position update replaces the previous one; disabling location memory deletes it.

Connected services are read under the permissions and features you authorise. Useful excerpts can appear in conversations or documents you keep. You can export your data and request account deletion; accounting retention and backup policies are explained below.

## Can I delete my account and data?

You can ask your administrator to delete your account.

**Personal content:** deletion purges conversations, memories, connected-service credentials, documents and the other personal records covered by the account-deletion flow, including health data and saved locations. Purged content cannot be recovered through reactivation.

**Accounting and retained records:** billing records remain. Deletion can keep your name and email for billing contact; final erasure deletes the account row. Audit or diagnostic records may still contain identifying details under their retention policies. Backup copies follow the operator’s retention policy.

Disconnecting a service or clearing your conversation is a narrower alternative when you want to keep the account.

## Does LIA have access to all my emails/files?

Access follows the permissions of each connector and the features you enable.

LIA can read useful emails, files and calendar events for a request. Authorised scheduled actions, briefing, proactive features and Radio may also read their selected sources without a new chat message.

Documents you choose to import or synchronise are indexed in your knowledge spaces. Service results may be cached, and excerpts used in an answer can remain in conversation history or a document you keep.

Review your connector permissions and enabled features; you can disconnect a service, pause a knowledge space or delete its imported data.

## Do external services see my data?

Yes, when a feature needs them.

**AI providers** receive your question and useful context, such as selected messages, memories or document excerpts. Speech, image and Live services receive the text, audio or images required by their respective modes. The optional Simli avatar receives LIA's spoken output after your explicit opt-in.

**Connected services** receive the requests needed to use them: searches, requested locations or actions you confirm. Weather services can receive coordinates, not just a city name.

Each provider applies its own privacy, retention and possible training policies. LIA's access controls and local storage do not replace those policies; check the configured providers and share only the information needed.

## What are passkeys and how do I enable them?

A **passkey** lets you sign in with **Face ID, your fingerprint or your device code** — no password typed, nothing to remember.

**🔑 Why it is safer:**
• Phishing-resistant: a passkey only works on the real LIA site
• LIA receives the public key, never the private key; your passkey manager controls any device synchronisation
• A leaked password becomes useless to an attacker

**⚙️ How to enable:**
1. Go to **Settings > Security > Strong authentication**
2. Click **Add a passkey** and follow your browser (Windows Hello, Face ID, Android…)
3. Optionally name it ("iPhone", "Work PC") and add one per device

On the login page, your browser will then offer the passkey directly in the email field (or use the "Sign in with a passkey" button).

## How do I add a second verification step (TOTP)?

The **authenticator app** adds a 6-digit code as a second step to password sign-in.

**⚙️ Setup:**
1. **Settings > Security > Authenticator app (TOTP)** → Enable
2. Scan the QR code with Google Authenticator, 1Password, Aegis…
3. Enter the 6-digit code shown by the app

**🔒 Backup codes:** 10 single-use codes are shown **exactly once** — store them safely; each one replaces the app code if you lose your phone. You can regenerate a fresh set at any time (the old set is invalidated).

Signing in then takes two steps: password, then the current code from your app.

## Why does LIA sometimes ask me to confirm my identity?

Sensitive actions are protected by an **identity confirmation** (a "step-up"):

**🛡️ Protected actions:**
• Managing passkeys and the authenticator app
• Exporting your data
• Signing out all other devices
• Disabling password sign-in

**⏱️ How it behaves:**
• Right after signing in, nothing is asked for 5 minutes
• Afterwards, one quick confirmation (password, code, passkey — or a fresh Google sign-in for Google accounts) re-opens the window

The point: even if someone borrows your open session, they cannot quietly lock you out or walk away with your data.

## How do I see and disconnect the devices connected to my account?

**Settings > Security > My devices** lists every live session of your account.

**💻 What you see:**
• Browser and system families (e.g. "chrome · windows") — never the full technical detail
• A truncated IP (e.g. 192.168.1.x) and coarse last-activity time
• The device name when it is registered for push notifications

**🔌 What you can do:**
• Sign out one device — it loses access immediately, even mid-conversation
• Sign out all other devices (asks for an identity confirmation)

**🔔 New sign-in alerts:** your devices receive a push notification when the account signs in from an unrecognized device — the toggle to turn it off is in the same section.

## How do I export all my data (GDPR)?

You can download a **complete archive of your data** at any time (GDPR right to portability).

**📦 What the archive contains:**
• Your profile and settings
• Conversations, memories, journal — as readable **Markdown** AND structured **JSON**
• Your uploaded files (attachments, knowledge-space documents)

**🚫 What it never contains:** connector credentials, security keys, push tokens — secret material is unexportable by design.

**⚙️ How:** **Settings > Security > Export my data** → Request an export → a push notification tells you when the ZIP is ready (downloadable for 24 h).

## What is left on the device when I sign out?

Nothing that belongs to you. Signing out does not just close the session: it clears what the browser and the device were holding on your behalf.

**🔔 Notifications:**
• This device's push registration is **revoked** before the session closes
• On a shared computer or phone, the next person will not see any of your notifications

**📍 Location:**
• The last known position is erased
• So is the geolocation permission — the next account has to give its own consent, it does not inherit yours

**💬 Content:**
• The message draft in progress is deleted
• No access token was ever stored in the browser (BFF architecture), so there is none to remove

The same cleanup runs if another account signs in through the same tab without a sign-out first — after a session expires, for instance.

## Can an email or a web page give LIA orders?

No. A text LIA reads is never a text LIA runs.

**📨 The problem:**
Every day LIA reads content you did not write: an email body, an invitation description authored by its organiser, a web page, a place listing, an external server's result. Anyone can slip in a sentence like "ignore previous instructions".

**🏷️ The protection:**
Every piece of data carries its **provenance**. The 25 data types LIA handles are classified once and for all: produced by LIA itself, or written by a third party. An unknown type is treated as external for safety, and the application refuses to start if a type has not been classified. What comes from outside reaches the model tagged as **material to analyse, never as an order to follow**.

**🔎 The detection:**
Seven families of trap are recognised across the app's six languages: fake system message, instruction hijack, identity switch, requests to send your data elsewhere, the name of a LIA tool slipped into foreign text, invisible characters, a directive hidden in an HTML comment.

**🧠 And the memory keeps the label:**
When a long conversation is summarised to save room, provenance used to be lost with the detail — a sender's request could resurface later as if it were an established fact. The summary now carries the label with it: what a third party wrote is reported in its own section, attributed to its source, and is never restated as one of your decisions or as something to do.

**✋ What LIA does not do:**
It **never** rewrites your content. An email stays exactly what its author wrote; only a note is added beside it. Cleaning the text would give the illusion of a guarantee that the next bypass would deny — and would alter a message you may have wanted to read as-is.

## Can I get the complete log of what LIA did for me?

Yes, and **complete** means complete. From the **Registers** page — its shortcut is on the Home page — you download what LIA **did**, what it **consulted**, the conversation **turns**, the detail of every **model call**, and any **gaps** in the register itself — as readable Markdown, as CSV, or as pseudonymised JSON Lines.

**Nothing is truncated**, whatever the volume: the header states the **exact count** along with the moment the extraction was taken. The download is compressed on the fly when your browser accepts it, without the file name changing.

**🗣️ Or just ask:** "*what did you do for me this week?*" — LIA reads the same registers and answers with exact totals: what it did, what it consulted, and what it did on its own initiative.

## Does a script written by LIA ever see my API keys or send my data somewhere?

No key, and no data without your word.

**🔑 Keys**
• the script only ever sees a temporary token, valid for that single run
• a dedicated proxy swaps it for your real key, on the host of that connector alone — the key never enters the container the script runs in
• LIA's own account keys and your sign-in credentials are never offered to a script

**📦 Data**
• a script that declares no host runs fully offline, with the data of the turn on its standard input
• a script that wants a host you never allowed is stopped, and you choose: **with** the data, **without** it, or not at all
• « without » means the script receives nothing of what LIA gathered — it can only reach the host

**📖 Traces**
• every network run is claimed in your register before it starts, with the hosts it declared
• the script itself is visible to an administrator in the debug panel, nowhere else

## In a Live session, what does the provider see and what does LIA keep?

**🔑 The provider, on your key:**
your voice and LIA's answers transit directly between your browser and the live provider you connected with your own key — the audio never passes through the LIA server. The provider receives the mandate LIA renders for the session (how to behave, what to hand over) and, in a direct session, the tools' declarations and the results it reads for you. Its own usage and its bill are yours and shown to you once; the platform records none of it.

**🧾 LIA, on your account:**
each request you delegated is an ordinary chat turn — kept, confirmed, counted, filed in the registers like a typed one. The voice-only exchanges of a Live session are archived as visible lines; in a direct session nothing is archived while you speak, and your words are relayed at the end as a message from you. The registers record the session and the capabilities read, never the audio nor a transcript of it. Deleting your account removes all of it.

**🎭 Optional speaking avatar:** after your explicit opt-in, LIA's spoken output is also sent to Simli, on your personal connector, to generate the face. Your microphone audio is not sent to Simli. Disable the avatar to close that connection; its active time, silence included, uses your personal Simli plan.

## Can signing in with Google activate or unblock an account?

No. Signing in with Google proves an email address, nothing more: an account's status never changes on that occasion. A registration awaiting approval stays pending, and an account an administrator blocked stays blocked.

LIA believes the announced address only when Google vouches for it. If someone had created an account with your address without ever verifying it, your Google sign-in proves the address is yours: that person's password and sessions are revoked, and the administrators are notified as after an email verification. A deleted account is never revived.

And even an inactive account can always sign out.

## What do the server's technical logs keep?

**Facts**, not your words. To run and to be repaired, a server writes technical logs; LIA's keep counts, lengths, identifiers and error codes — not your searches, your interests, the names of your contacts or files, nor the pages you visited.

**Measurements too:** the metrics and traces used to monitor the server name the page requested by its pattern — “a relationship’s card” — never by its content: a name or a search sitting in an address does not get into them.

**Even when something fails:** a database that refuses a value usually quotes it in its error message; LIA removes that quotation before writing the line and describes the error by its facts — which constraint, which table. Service access keys are masked in every logged address.

**Checked continuously:** an automated test reads every log line in the code and refuses one that would write a person's text. Two limits remain, stated as they are: an external service's error message in an unknown format can still quote a value, and the debug level — off in production — keeps more detail.

## How does LIA stay protected against flaws in its dependencies?

Through a **watch** and **rules that cannot be forgotten**. Every week, an automated check reads the security advisories each of LIA’s dependencies publishes — including those no public database relays —, the announced end-of-life dates and the state of the browser engine. Every finding is fixed, or accepted in writing with a reason and a review date: never ignored in silence.

**Careful updates:** a new version comes in only after a cooling-off period — from a few days for a fix to two months for a major version — long enough for a possible defect to become known. An update never moves a dependency backwards, and a security fix becomes a floor nothing can go below.

**A verifiable build:** every building block of the server — images, languages, tools — is pinned by its digest, every version publishes the exact inventory of what it contains (a CycloneDX SBOM), and the code goes through the secret detector before every push. Before it is published, every version is installed on blank machines.
