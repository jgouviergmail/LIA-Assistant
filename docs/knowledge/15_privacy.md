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

**🛡️ Personal Information Protection (PII):**
• Your sensitive data (emails, contacts) remain confidential
• Never shared with unauthorized third-party services
• Minimal access to external APIs

**📋 Best practices:**
• Automatic logout after inactivity
• Ability to revoke connector access
• Audit logs of sensitive actions

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

## Can I delete my account and data?
Yes, you have a **right to complete erasure**:

**🗑️ What will be deleted:**
• Your user account
• All your conversation history
• All your OAuth connectors
• Your preferences and settings
• Your usage statistics

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
