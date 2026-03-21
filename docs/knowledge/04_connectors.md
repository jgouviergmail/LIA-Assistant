# Connectors

## What is a connector?
A **connector** is a secure gateway between LIA and your external services:

**🔌 Types of connectors:**

**Google Services (OAuth):**
• 📧 **Gmail**: read, send, reply to emails
• 📅 **Calendar**: manage your events
• 👥 **Contacts**: search and create contacts
• 📁 **Drive**: explore your files
• ✅ **Tasks**: manage your tasks
• 📍 **Places**: search for locations
• 🗺️ **Routes**: directions and routes

**Apple iCloud services (app-specific password):**
• 📮 **Apple Mail**: read, send, reply to emails (IMAP/SMTP)
• 🗓️ **Apple Calendar**: manage your iCloud events (CalDAV)
• 📇 **Apple Contacts**: search and create iCloud contacts (CardDAV)

**Microsoft 365 services (OAuth):**
• 📧 **Outlook**: read, send, reply to emails
• 📅 **Microsoft Calendar**: manage your events
• 👥 **Microsoft Contacts**: search and manage contacts
• ✅ **Microsoft To Do**: manage tasks and lists

**External services (API key):**
• 🌤️ **OpenWeatherMap**: weather and forecasts
• 📚 **Wikipedia**: encyclopedic search
• 🔍 **Perplexity**: AI web search
• 🦁 **Brave Search**: web and news enrichment

**Smart Home (hybrid auth):**
• 💡 **Philips Hue**: control lights, rooms, and scenes

**🔒 Security:**
Each connector has limited permissions. LIA only accesses necessary data.

**⚡ Mutual exclusivity:**
For email, calendar, and contacts, only one provider can be active at a time (Google OR Apple OR Microsoft, not both simultaneously). Tasks are available via Google Tasks or Microsoft To Do (one at a time).

## What Apple iCloud services can I connect?
LIA integrates with **3 Apple iCloud services**:

**📮 Apple Mail (IMAP/SMTP)**
• Search your iCloud emails
• Read message content
• Send, reply, forward
• View attachments
• Navigate by IMAP folders

**🗓️ Apple Calendar (CalDAV)**
• View your iCloud calendar
• Create events
• Modify or delete
• Invite participants

**📇 Apple Contacts (CardDAV)**
• Search by name, email, company
• Create new contacts
• Update information

**❌ Not available:**
• **Apple Reminders**: Apple doesn't provide a standard API for accessing Reminders from a server. Tasks remain available via Google Tasks or Microsoft To Do.

**💡 Same experience:**
Commands are identical whether you use Google or Apple. Just say "*my emails*", "*my calendar*", or "*my contacts*" — LIA automatically uses the active provider.

## What is connector mutual exclusivity?
For email, calendar, contacts, and tasks services, LIA applies a **mutual exclusivity** rule:

**⚡ Principle:**
Only one provider can be active per category:
• **Email**: Gmail OR Apple Mail OR Outlook (not multiple)
• **Calendar**: Google Calendar OR Apple Calendar OR Microsoft Calendar (not multiple)
• **Contacts**: Google Contacts OR Apple Contacts OR Microsoft Contacts (not multiple)
• **Tasks**: Google Tasks OR Microsoft To Do (not both)

**🔄 Switching providers:**
If you activate a new provider while another is active for the same category:
1. The previous service becomes **inactive** (not deleted)
2. The new service becomes **active**
3. Your data remains intact with each provider
4. You can switch back at any time

**✅ Unaffected services:**
Google Drive, Places, Routes, and Philips Hue have no equivalent in other providers and remain always available.

**💡 Tip:**
You don't need to choose the same provider for everything. For example, you can use Outlook for emails, Google Calendar for your calendar, and Microsoft To Do for tasks.

## How do I connect Microsoft 365 services?
Microsoft 365 services use **OAuth 2.0** (secure connection via Microsoft Identity Platform):

**Steps:**
1. Go to **Settings > Connectors**
2. In the **Microsoft 365** section, click **Connect All** or select an individual service
3. A Microsoft login window opens
4. Sign in with your Microsoft account
5. Accept the requested permissions
6. You're redirected back to LIA — the connector is active!

**🔐 Permissions:**
LIA only requests necessary permissions via the Microsoft Graph API. For example, for Outlook: reading and sending emails, but not permanent deletion.

**⚠️ Mutual exclusivity:**
Activating a Microsoft service automatically deactivates its Google or Apple equivalent for the same category (and vice versa).

**💡 Tip:**
You can revoke access at any time from LIA settings or from account.microsoft.com.

## What Microsoft 365 services can I connect?
LIA integrates with **4 Microsoft 365 services**:

**📧 Outlook (Microsoft Graph)**
• Search your emails
• Read message content
• Send, reply, forward
• View attachments

**📅 Microsoft Calendar**
• View your schedule
• Create events
• Modify or delete
• Invite participants

**👥 Microsoft Contacts**
• Search by name, email, company
• Create new contacts
• Update information

**✅ Microsoft To Do**
• List your tasks
• Create new tasks
• Mark as completed
• Manage task lists

**💡 Same experience:**
Commands are identical regardless of provider. Just say "*my emails*", "*my calendar*", "*my contacts*", or "*my tasks*" — LIA automatically uses the active provider.

## How do I connect Google services?
Google services use **OAuth 2.0** (secure connection):

**Steps:**
1. Go to **Settings > Connectors**
2. Find the desired service (Gmail, Calendar, etc.)
3. Click **Connect**
4. A Google window opens
5. Select your Google account
6. Accept the requested permissions
7. You're redirected to LIA - the connector is active!

**🔐 Permissions:**
LIA only requests necessary permissions. For example, for Gmail: reading and sending emails, but not permanent deletion.

**💡 Tip:**
You can revoke access at any time from LIA settings or from your Google account.

## How do I connect external services (API key)?
Some services require a **personal API key**:

**🌤️ OpenWeatherMap (free):**
1. Create an account at openweathermap.org
2. Get your free API key
3. In LIA: **Settings > Connectors > OpenWeatherMap**
4. Paste your key and click **Activate**

**🔍 Perplexity (paid):**
1. Create an account at perplexity.ai
2. Subscribe to an API plan
3. Get your API key
4. Activate in LIA as above

**📚 Wikipedia:**
No key required! Wikipedia is free and directly accessible.

**🔒 Key security:**
Your API keys are stored securely and encrypted.

## How do I connect Philips Hue?
Philips Hue uses a **hybrid authentication** (local press-link or remote OAuth2):

**🏠 Local mode (recommended — same network):**
1. Go to **Settings > Smart Home > Philips Hue**
2. Click **Local connection**
3. Click **Search for bridges** — LIA discovers bridges on your network
4. Select your bridge
5. **Press the physical button** on top of your Hue Bridge
6. Click **Pair** within 30 seconds
7. LIA validates connectivity and activates the connector

**🌐 Remote mode (different network):**
1. Register at developers.meethue.com
2. Configure your Hue Remote API credentials in LIA server settings
3. Go to **Settings > Smart Home > Philips Hue**
4. Click **Remote connection** — redirects to Philips for OAuth2 authorization
5. Authorize LIA — connector activates automatically

**💡 What you can do:**
• "Turn on the living room lights"
• "Dim the bedroom to 30%"
• "Set the kitchen light to blue"
• "Activate the movie scene"
• "What lights are currently on?"
• "Turn off everything"

**⚡ 6 tools available:**
• List lights, control a light (on/off, brightness, color)
• List rooms, control a room
• List scenes, activate a scene

**🔒 Security:**
Your Hue application key (local mode) or OAuth tokens (remote mode) are encrypted and stored securely. Local mode uses `verify=False` for the bridge's self-signed certificate — scoped exclusively to Hue connections.

## How do I disconnect a service?
To revoke LIA's access to a service:

**Disconnection from LIA:**
1. Go to **Settings > Connectors**
2. Find the service to disconnect
3. Click **Disconnect**
4. Confirm disconnection

**⚠️ Consequences:**
• LIA will no longer be able to access this service
• Your data remains intact with the provider (Google, etc.)
• You can reconnect at any time

**🔐 Double security (Google):**
For Google services, you can also revoke access from:
• myaccount.google.com/permissions
• This disconnects LIA immediately

## Why is a connector showing an error?
Several reasons can explain a connector error:

**🔄 Expired token:**
Solution: Click **Reconnect** to refresh the authorization.

**🚫 Permissions revoked:**
If you revoked access from Google, reconnect.

**🔑 Invalid API key:**
For API key services, verify your key is correct and active.

**⏱️ Quota exceeded:**
Some services have usage limits. Wait or upgrade to a higher plan.

**🌐 Network issue:**
Check your internet connection and try again.

**💡 General solution:**
Disconnect then reconnect the service. This solves most problems.

## Can I configure preferences per connector?
Yes! Some connectors have **customizable preferences**:

**📅 Google Calendar:**
• **Default calendar**: where to create new events
• Example: "Work", "Personal", "Family"
• LIA will use this calendar unless specified otherwise

**✅ Google Tasks:**
• **Default task list**: where to create new tasks
• Example: "My main list", "Projects", "Shopping"

**📍 Google Places:**
• **Home address**: your default address for "near me" searches
• **Automatic geolocation**: send your position for accurate results
• Configure both in **Settings > Connectors > Google Places**

**🌐 Browser Geolocation:**
• In Google Places settings, enable the geolocation toggle
• Your browser will ask for permission the first time
• Position used for local weather and "near me" searches

**To configure:**
1. Go to **Settings** (⚙️ icon in the menu)
2. Open the **Connectors** section
3. Find the relevant connector (Calendar, Tasks, or Places)
4. Configure the specific preferences for that connector

**💡 Tip:**
These preferences save you time by not having to specify the calendar, list, or city each time.

## Which Google services can I connect?
LIA integrates with **7 Google services**:

**📧 Gmail**
• Search all your emails
• Read message content
• Send, reply, forward
• View attachments

**📅 Google Calendar**
• View your schedule
• Create events
• Modify or delete
• Invite participants

**👥 Google Contacts**
• Search by name, email, company
• Create new contacts
• Update information

**📁 Google Drive**
• Search your files
• Read document content
• Browse folders

**✅ Google Tasks**
• List your tasks
• Create new tasks
• Mark as completed

**📍 Google Places**
• Search for locations
• Get addresses and hours
• View reviews

**🗺️ Google Routes**
• Calculate routes
• Compare transport modes
• Estimate travel times

## Are connectors secure?
Security is our top priority:

**🔐 Google services — OAuth 2.0:**
• LIA never sees your Google passwords
• You connect directly with Google
• Tokens revocable at any time

**🍎 Apple services — App-specific password:**
• Uses an application-specific password (not your Apple password)
• Encrypted before database storage
• Revocable from appleid.apple.com
• Apple two-factor authentication is required

**🪟 Microsoft 365 — OAuth 2.0:**
• LIA never sees your Microsoft passwords
• You connect directly with Microsoft
• Tokens revocable at any time from your Microsoft account
• Limited permissions (Microsoft Graph API)

**🔒 Minimal permissions:**
• Each connector only requests necessary permissions
• No excessive access to your data

**🗄️ Secure storage:**
• OAuth tokens and app-specific passwords encrypted in database
• API keys stored securely
• No plaintext storage

**🔄 Automatic refresh:**
• Google and Microsoft tokens expire regularly and are renewed automatically
• Apple app-specific passwords don't expire (unless Apple ID password changes)

**📋 Audit and logs:**
• All actions are tracked
• Usage history available

## How do I connect Apple iCloud services?
Apple iCloud services use an **app-specific password**:

**Prerequisites:**
• An Apple account with **two-factor authentication enabled**
• Generate an **app-specific password** from appleid.apple.com

**Steps:**
1. Go to **Settings > Connectors**
2. In the **Apple iCloud** section, click **Connect**
3. Enter your **Apple ID** (email)
4. Enter the **app-specific password** (format xxxx-xxxx-xxxx-xxxx)
5. Select the services to activate (Email, Calendar, Contacts)
6. Click **Test connection** to verify
7. Click **Activate**

**⚠️ Mutual exclusivity:**
Activating an Apple service automatically deactivates its Google equivalent (and vice versa). For example, activating Apple Mail will deactivate Gmail.

**🔐 Security:**
Your app-specific password is encrypted and never exposed. You can revoke it at any time from your Apple account.
