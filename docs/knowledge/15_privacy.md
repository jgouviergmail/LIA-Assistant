# Security and Privacy

## Are my conversations private?
Yes, your conversations are **strictly private**:

**🔐 Confidentiality:**
• Your conversations are only accessible by **you**
• No sharing with third parties
• Administrators cannot read your messages

**🗄️ Secure storage:**
• Data stored in a secure database
• Complete isolation between users
• Encryption of sensitive data

**🧠 AI usage:**
• Your conversations are processed to respond to you
• They are NOT used to train models
• No analysis for marketing purposes

## How is my data protected?
Multiple security levels protect your data:

**🔐 Authentication:**
• OAuth 2.0 with PKCE (security standard)
• Secure server-side sessions (Redis) with HTTP-only cookies

**🔒 Data protection:**
• Encryption in transit (HTTPS/TLS)
• HTTP-only cookies (XSS protection)
• Built-in CSRF protection
• Strict Content-Security-Policy (CSP) blocking script injection — dynamic content (including AI-generated text) is auto-escaped, so injected markup stays inert

**🛡️ Personal Information Protection (PII):**
• Your sensitive data (emails, contacts) remain confidential
• Never shared with unauthorized third-party services
• Minimal access to external APIs
• No personal data in operational logs — home address, GPS coordinates, contact names/emails, email recipients/subjects and memory content are kept out of the technical logs (only counters and technical identifiers remain), with an automatic safety net enforcing it (GDPR data-minimization)

**📦 Isolated execution:**
• A skill's Python code runs in a throwaway container destroyed right after — no network, no access to your files, no credentials
• If that isolation cannot be set up, the script does not run at all rather than running less protected
• Any administration task on the server is submitted for your approval first, showing in full what will be sent

**📋 Best practices:**
• Automatic logout after inactivity
• Ability to revoke connector access
• Audit logs of sensitive actions
• Sensitive data kept locally is wiped when you sign out, and also when a different account signs in on the same device

**💾 Durability:**
• Automatic daily database backups (7 days / 4 weeks / 6 months of history kept)
• Restore procedure tested for real — the latest dump is restored into a disposable container and compared against the live database, so an incident cannot cost you more than the last day

## What data does LIA collect?
LIA only collects data **necessary for its operation**:

**📋 Data collected:**
• **Profile**: name, email, language, timezone
• **Conversations**: history of your exchanges with LIA
• **Connectors**: OAuth tokens (not your passwords)
• **Preferences**: theme, personality, settings
• **Statistics**: number of messages, tokens consumed
• **Home address**: optional, encrypted in database (for 'at home' queries)

**❌ Data NOT collected:**
• Your Google passwords
• The full content of all your emails
• Your Drive files (only those you request)
• Real-time geolocation data (sent on-the-fly, not stored)

**🗑️ Right to erasure:**
You can request complete deletion of your account and data.

**📥 Right to data portability:**
You can export your personal consumption data as CSV from **Settings > Features > My Consumption Export**. Three export types: LLM token usage, Google API usage, and aggregated summary. You can only export your own data — access to other users' data is blocked server-side.

## Can I delete my account and data?
Yes, you have a **right to complete erasure**:

**🗑️ What will be deleted:**
• Your user account
• All your conversation history
• All your OAuth connectors
• Your preferences and settings
• Your usage statistics
• Your health data (heart rate, steps) and health-ingestion tokens
• Your last known location

After deletion, a device that was sending health data to LIA can no longer do so.

**⚠️ Irreversible action:**
Deletion is **permanent** and cannot be undone.

**📧 How to proceed:**
Contact your administrator to request account deletion.

**💡 Alternatives:**
• Reset conversation (deletes history)
• Disconnect connectors (revokes access)
• These actions are reversible unlike account deletion

## Does LIA have access to all my emails/files?
No, LIA has **limited and controlled** access:

**📧 Gmail:**
• LIA searches ONLY when you ask
• It doesn't automatically scan your mailbox
• Emails are not stored on LIA's side
• Temporary cache for performance (few minutes)

**📁 Google Drive:**
• Access only to files you request
• No automatic scanning of all your files
• Content is not stored permanently

**📅 Calendar:**
• Reading events on your request
• No continuous monitoring of your schedule

**🔐 Principle of least privilege:**
LIA only accesses data strictly necessary to respond to your request, at the moment you make it.

## Do external services see my data?
Understand the **data flow**:

**🔄 Google Services:**
• Your data stays with Google
• LIA queries Google via their official APIs
• Google sees the requests (like in their app)
• Google's privacy policy applies

**🌤️ OpenWeatherMap:**
• Only receives the requested city name
• No personal data transmitted

**📚 Wikipedia:**
• Only receives the search query
• Public service, no tracking

**🔍 Perplexity:**
• Receives your search question
• Perplexity's privacy policy applies

**💡 General principle:**
LIA transmits the minimum information necessary to each service. Your personal data is never shared unnecessarily.

## How does LIA enforce usage limits securely?
Usage limits are enforced via a **5-layer defense-in-depth** architecture:

**🛡️ Enforcement layers:**
1. **Router** — HTTP 429 before SSE stream starts (chat messages)
2. **Service** — SSE error for scheduled actions
3. **LLM Guard** — Centralized check in `invoke_with_instrumentation()` covering all background services
4. **Proactive Runner** — Skip blocked users for notifications
5. **Direct call migration** — Legacy `.ainvoke()` calls migrated to guarded path

**⚡ Fail-open design:**
If Redis or the database is temporarily unavailable, the system allows the request through. Usage limits are a cost control mechanism, not a security boundary — blocking users due to infrastructure issues would be worse than allowing a few extra requests.

**🔒 Admin controls:**
Administrators can manually block any user instantly with a reason, and unblock them with immediate effect.

## What are passkeys and how do I enable them?
A **passkey** lets you sign in with **Face ID, your fingerprint or your device code** — no password typed, nothing to remember.

**🔑 Why it is safer:**
• Phishing-resistant: a passkey only works on the real LIA site
• The secret key never leaves your device
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
