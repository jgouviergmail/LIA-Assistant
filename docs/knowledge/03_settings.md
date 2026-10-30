# Settings

## Where do I find my MCP servers and plugins?

In **Settings › Features › Extensions & Data**, next to Skills and Knowledge spaces:
• **MCP Servers** — the servers you connect yourself: add, test, edit or pause them
• **Application MCP** — the servers your administrator set up for everyone; it appears only when there are some. You see the tools each one offers and can switch it off for yourself
• **Plugins** — packages that bring skills and MCP servers together; a server a plugin installed also shows in MCP Servers, with a **Via plugin** badge

They sit there rather than with your connectors because they are a different kind of thing: a connector links one of your accounts so LIA can read it, while an MCP server or a plugin gives LIA new tools, like a skill. The **Search a setting** field finds them by name too.

## What does the settings home page tell me before I open anything?

On a computer, Settings opens on an overview: every section you can use, grouped by family, each card with its icon, its name and a short description. Click one to open it beside the list.

**📊 Where each section stands:**
Cards that hold something countable carry one more line, in the same words as the capability map: **Active — 12 items**, **Active** or **To set up**.
• the whole page reads these lines at once, in a single request
• while they load, if they could not be read, or for a section with nothing to count (a theme, an export), the card says nothing — a figure shown is exact, or absent

Once LIA has compiled its portrait of you, a **What LIA understands about you** card at the top opens it. On a phone, the list of sections comes first, without these lines.

## How do I change my timezone?
The timezone affects date display in your conversations:

**To change it:**
1. Go to **Settings** (⚙️ icon in the menu)
2. In the rail, under **Preferences › Personalization**, pick **Timezone**
3. It opens in the panel beside the rail — choose yours

**🌍 Automatic detection:**
On your first login, LIA automatically detects your timezone via your browser.

**💡 Traveler tip:**
If you travel, LIA will offer to update your timezone when it detects a mismatch.

## How do I manage my stored memories?

You control your memories from **Settings › Memory**: read, edit, pin, export or delete them individually or in bulk.

**📌 Pinning:** a pinned memory is protected from automatic edits and cleanup. New **standing instructions** — how LIA should work for you — are pinned as soon as they are stored. You may edit them, unpin them or delete them yourself. Even when unpinned, an instruction is protected from automatic deletion; an automatic correction must preserve a successor.

**🔄 Cleanup:** other unpinned memories are assessed by importance, recency and use. Those at risk of being forgotten are flagged so you can pin what matters. Resetting the conversation does not erase these memories.

## How do I configure my geolocation and home address?
LIA can use your **geographic location** for contextual searches:

**📍 Home address:**
1. Go to **Settings > Preferences > Location**
2. Enter your address in the **Home address** field
3. Validate to save

**🎯 Usage:**
• "*Restaurants near me*" will use your address
• "*Weather here*" will show your home's weather
• "*Pharmacies nearby*" will search around your address

**🌐 Browser geolocation:**
You can also allow real-time geolocation via your browser for even more accurate results.

**✈️ Remember my last position (opt-in):**
In the same **Location** section, **Remember my last position** keeps the position your browser gave with your last chat message. Proactive weather notifications use it instead of your home address when it is recent and far enough from home — a freshness window and a distance the administrator sets — and then name the city; the chat, routines and the briefing use it too when your live position is unavailable. Your position is encrypted, never historized (each update overwrites the previous one), shown under **Currently stored** with a **Clear** button, and deleted as soon as you turn the option off or remove your home address.

**🔒 Privacy:**
Your saved address is encrypted and used by location-based features you enable. Configured services may receive the coordinates needed for those features.

## How does LIA resolve relational references?
LIA understands **references to your loved ones** through its memory:

**👥 Reference examples:**
• "*Send an email to my brother*" → LIA finds the corresponding contact
• "*What did my wife send me?*" → searches your emails
• "*Call my doctor*" → finds Dr. X's contact

**🔗 How it works:**
1. LIA extracts relationships from your conversations ("*My brother's name is John*")
2. These associations are stored in your long-term memory
3. During a query, LIA automatically resolves "*my brother*" to "*John Smith*"

**✏️ Customize relationships:**
You can create or modify these associations in **Settings > Memory**.

**💡 Tip:**
Mention your relationships naturally in conversations: "*My colleague Sophie sent me a file*".

## How do I view my token consumption in chat?
You can display **consumption metrics** in real-time during your conversations:

**💰 To enable/disable display:**
Click the **dollar icon** 💲 in the title bar (available on desktop only).

**📊 Information displayed:**
When enabled, each LIA message shows:
• **Input tokens**: your message + analyzed context
• **Output tokens**: the response generated by LIA
• **Cached tokens**: reused data (savings)
• **Estimated cost**: in euros for this message
• **Conversation total**: cumulative since start

**💡 Why is this useful?**
• Understand what consumes resources
• Optimize your requests if needed
• Track your usage in real-time

**📱 Note:**
This feature is not available on mobile due to display space constraints.

## How do I change the way answers are displayed?

In **Settings › Preferences › Personalization › Display Mode**, pick one of four modes:
• **Cards** (the default) — a standard text answer with data cards for the selected results
• **HTML** — an answer laid out with headings, callouts, lists or key figures
• **HTML + cards** — a visually structured summary followed by detailed data cards
• **Markdown** — text with standard Markdown headings, lists and tables

A **Preview** beside the list draws an illustrative answer in the chosen mode, without your account data. Your choice applies to LIA's new replies.

You can also ask in the chat:
• *Switch my answers to HTML + cards*

**💡 Good to know:** in every mode, copying a message gives you clean readable text — HTML answers are flattened automatically, and paste as rich text where the target supports it.

## Which languages are supported for voice transcription?
LIA transcribes your dictation in **your account's language**, one of the six languages of the interface: French, English, German, Spanish, Italian or Chinese.

**🔤 Choosing the language:**
It comes from your account (Settings › Preferences). To dictate in another of these languages, change it there: LIA does not guess the language you speak.

**🎯 The wake word:**
"Dis LIA" exists in French for now, in beta: its recognition is still improving. The other interface languages do not have their phrase yet — tapping the badge and the long press work everywhere.

**💰 Local by default:**
By default, transcription runs on your server with Whisper, at no API cost. If you choose the remote engine in your voice settings, it is the one your administrator configured, and its cost is counted in your usage.

## Voice mode isn't working, what should I do?
Here are **solutions to common voice mode issues**:

**🎤 Microphone problem:**
1. Check that your browser has permission to use the microphone
2. Click the 🔒 icon to the left of the URL to see permissions
3. Allow the microphone if blocked

**🌐 Unsupported browser:**
Voice mode requires a modern browser:
• ✅ Chrome 92+
• ✅ Firefox 79+
• ✅ Safari 15.2+
• ✅ Edge 92+
• ❌ Internet Explorer (not supported)

**🧩 Wake word unavailable:**
The wake word needs WebAssembly and an audio worklet, which every current browser offers, phones included, and exists in French only for now. In another interface language, or when its model cannot load, the badge offers tap-to-speak instead.

**🔇 Wake word not detected:**
• Say the phrase shown on the badge clearly
• Avoid noisy environments
• Get closer to the microphone
• Use Push-to-Talk (click the overlay) as an alternative

**⏱️ Slow transcription:**
The first transcription may take 2-3 seconds (model loading). Subsequent ones are faster (~500ms).

## How do I change the interface language?
Two methods to change language:

**Quick method:**
Click the **globe icon** 🌐 in the title bar and select your language.

**Via settings:**
1. Go to **Settings** (⚙️ icon in the menu)
2. In the rail, under **Preferences › Personalization**, pick **Language**
3. It opens in the panel beside the rail

**🔄 Sync:**
Both methods sync your preference. The language is saved in your profile.

**📧 Impact on emails:**
Notification emails will also use this language.

## How do I customize appearance (themes)?
Customize LIA's appearance to your taste:

**5 themes available:**
• 💙 **Professional Blue**: elegant and timeless
• 🌊 **Teal**: deep teal, sophisticated and calming
• 🌿 **Sage**: modern sage green, natural and organic
• 🌹 **Rose**: dusty rose, elegant and warm
• 💜 **Lavender**: soft lavender, refined and creative

**Light, dark, absolute black:**
Each theme exists in a light and a dark version, and dark has two depths — ordinary dark, and **absolute black** for OLED screens, where those pixels really switch off. The button in the title bar cycles through the three, and its icon shows where the next press goes. In **Settings › Appearance** you pick the mode directly among four: **Light**, **Dark**, **Absolute black** and **System** (follow your device).

**To change theme:**
Go to **Settings** (⚙️ icon), **Appearance** section.

## How do I update my profile?
Manage your personal information:

**Editable:**
• ✏️ **Full name**: your name displayed in the app
• 🌍 **Timezone**: for date display
• 🌐 **Language**: interface language
• 🎨 **Theme**: color theme and display mode (light, dark, absolute black, or system)
• 🔤 **Font**: choose from 9 font families (System, Noto Sans, Plus Jakarta Sans, IBM Plex Sans, Geist, Source Sans Pro, Merriweather, Libre Baskerville, Fira Code)
• 🔠 **Font size**: make the interface text a little smaller or noticeably larger than the default, with a live preview. Only the text changes size: panels, spacing and icons keep their dimensions

**Not editable:**
• 📧 **Email**: login identifier (fixed after registration)

**To modify:**
Your full name lives in **Settings > Profile**. Timezone, language, theme, font and font size live in **Settings > Preferences**, under the **Personalization** group.

## How do I customize LIA's style?
LIA can adapt its **communication style** to your preferences:

**14 available personalities:**
• **Normal**: neutral and factual, suitable for every situation
• **Enthusiastic**: dynamic and motivated, overflowing with positive energy
• **Teacher**: patient and caring, clear and structured explanations
• **Friend**: warm and close
• **Influencer**: trendy and on the cutting edge
• **Philosopher**: deep reflection and nuanced perspectives
• **Cynical**: dark humor and impactful truths
• **JARVIS**: sophisticated, sarcastic, dedicated digital butler
• **Teenager**: a teenager in the midst of hormonal changes
• And more — administrators can add new ones!

**🌍 6 languages:**
Each personality exists in French, English, Spanish, German, Italian and Chinese. LIA answers in the chosen tone, in your language.

**Two methods to change:**
• **Quick method**: click the **✨** icon in the title bar
• **Via settings**: go to **Settings** (⚙️ icon), **LIA Style** section

**💡 Tip:** Try different styles to find the one that suits you best!

## Are my preferences synchronized?
Yes, all your preferences are **automatically synchronized**:

**🔄 What's synchronized:**
• Interface language
• Timezone
• Theme, color theme, font family, font size, and light/dark mode
• LIA personality style
• Voice preferences
• Active connectors
• Default calendar and task preferences
• Long-term memories
• Feature toggles (journals, heartbeat, interests, sub-agents, debug panel)
• Notification settings (heartbeat min/max/hours, interest min/max/hours)
• Journal settings (sizes, consolidation options)

**📱 Multi-device:**
Your preferences follow you on all devices. Change the theme on mobile, find it on your computer.

**💾 Instant save:**
Each change is recorded immediately.

## How do I enable or disable LIA's voice?
LIA has a **bidirectional voice system**:

**🔊 Voice Synthesis (TTS) - LIA speaks to you:**
Click the **speaker icon** 🔊 in the title bar. When enabled, LIA reads its responses aloud. The administrator picks the active provider, model and voice from a single catalogue:
• **Edge TTS** (default): free, Microsoft neural voices
• **OpenAI TTS**: `tts-1` or `tts-1-hd` — premium, natural voices (alloy, echo, fable, nova, onyx, shimmer)
• **ElevenLabs**: `eleven_multilingual_v2`, `eleven_turbo_v2_5`, or `eleven_flash_v2_5` — premium, ultra-natural voices, custom and library voices supported
• **Google Gemini**: expressive multilingual voices with delivery controls
• **Fish Audio**: `s2.1-pro`, `s2-pro` or `drama-3` — premium voices, the vendor's licensed library and the instance's own cloned or designed voices

**🎙️ Voice Mode (STT) - Speak to LIA:**
Tap the hands-free badge (microphone) in the chat header to turn voice mode on; hold it for 500ms (or hold Space) to turn it off. Greyed, the badge says the mode is off.
• **Wake word** (beta, French interface): say "Dis LIA" to start recording, "Stop" to cut LIA's voice
• **Push-to-talk**: Click the overlay to speak manually
• **Auto-detection**: LIA detects when you stop speaking (1s silence)
• **Local mode (default)**: free, offline transcription via Sherpa-onnx Whisper — your audio never leaves the LIA server
• **Remote mode**: the speech engine your administrator configured — ElevenLabs Scribe, OpenAI or Fish Audio — billed per audio duration; Settings → Voice mode names the engine that receives your audio — opt-in there

**💡 Tip:**
Voice mode is ideal for hands-free use or multitasking.

## How do I change LIA's voice (male/female)?
Choose the **voice gender** that suits you:

**🎙️ Available voices:**
• **Female**: soft and natural neural voice
• **Male**: deep and calm neural voice

**To change:**
1. Go to the **Home** page
2. On the welcome card, click the **small portrait** of the other gender
3. LIA's avatar changes at once
4. The voice automatically switches between female and male

**🌍 Language:**
The voice is the configured one, whatever the language of the answer: a multilingual voice reads every language, a single-language voice reads the others with its accent. The **« Only voices in my language, and multilingual ones »** switch, on by default, narrows every voice list — LIA's, the radio's and the administrator's slots — without ever hiding a voice already chosen.

**🎚️ Your own voices:**
In **Settings › Preferences › Voice & Media › Voice Mode › LIA's voice**, choose the male and the female voice LIA speaks with in the chat, among the voices of the engine your administrator configured — each list opens on the administrator's voice. Your choice is kept when the administrator changes the model of the same provider. The radio, Live sessions and phone calls keep their own voices. Picking a voice plays a short sample of it right away, which you can stop or play again; listening counts in your usage like any reading.

**⚙️ Quality:**
LIA uses high-quality neural voices. Five providers are available, configured by the administrator: Microsoft Edge TTS (free), OpenAI TTS (`tts-1` / `tts-1-hd`), ElevenLabs (`eleven_multilingual_v2` / `eleven_turbo_v2_5` / `eleven_flash_v2_5`), Google Gemini and Fish Audio. Each provider gets its own per-voice tuning (speed, stability, audio format) for a natural and expressive rendering, and on the engines that perform expressive cues LIA's spoken comments can carry a short sigh, a laugh or a whisper, kept for news that calls for one — never to say how one of LIA's actions went.

## How does long-term memory work?
LIA learns about you through its **intelligent memory**:

**🧠 What LIA remembers:**
• **Preferences**: "He prefers concise emails", "She likes black coffee"
• **Personal information**: "His birthday is March 15"
• **Relationships**: "Mary is his sister", "John is his colleague"
• **Significant events**: "He changed jobs recently"
• **Habits**: "She exercises on Tuesday evenings"
• **Sensitive areas**: topics to approach with care

**🔄 Automatic extraction:**
LIA analyzes your conversations and automatically extracts relevant information in the background. When you mention relative dates ("tomorrow", "next Saturday", "next week"), LIA converts them to **absolute dates** before storing — so your memories stay accurate even weeks later.

**✏️ Factual corrections stick:**
When you correct a fact ("actually, I changed jobs, I'm at Meta now" or "my daughter's name is Elsa, not Emma"), LIA updates the existing memory instead of creating a contradictory duplicate. Your history stays coherent over time.

**📌 Pinned memories fully protected:**
Memories you've pinned are never modified or deleted automatically — neither by the extraction pipeline nor by the cleanup jobs. You keep absolute control over what stays frozen.

**🧹 Daily semantic consolidation:**
Every day, LIA merges near-identical memories that accumulate over conversations (e.g., "I love coffee in the morning" and "I drink coffee every morning"). The profile stays crisp without manual cleanup.

**🌱 Memories age gracefully:**
Medium-importance preferences stop cluttering memory after a few weeks, while important information (family, identity, milestones) is preserved long-term. Memories never activated past a grace period are penalized in the retention score.

**🔍 Dual semantic search:**
Each memory is indexed twice — once on its content, once on the keywords that trigger it. Your question is compared to both, and the better match wins, so a memory is found whether you phrase it the way it was recorded or not.

**📊 Usage:**
These memories personalize LIA's responses. For example, LIA will say "Hello Mary" to your sister without you specifying.

**🔎 Also looked up on purpose:**
Beyond what it recalls with each message, LIA can search its memory for a subject it meets along the way — the sender of an e-mail it just read, a place named in a document. On the phone too, it recalls what matches your question, not its latest memories. If you switched memory off, nothing is searched, and a failed search is never passed off as "nothing remembered".

**🛡️ Full control:**
View, edit, pin or delete your memories in **Settings › Features › Identity & Memory › Memory**.

## What are usage limits and where can I see them?
Usage limits are quotas set by your administrator to control resource consumption (tokens, messages, cost). You can see your current usage vs limits on the **Dashboard** via dedicated tiles (Period Limits and Global Limits).

**📊 Dashboard tiles:**
When limits are configured, color-coded gauge bars show your consumption:
- 🟢 Green: under 60%
- 🟡 Yellow: 60-80%
- 🟠 Orange: 80-95%
- 🔴 Red: over 95%

**🔒 When blocked:**
If you reach a limit, the message input and voice are disabled and a red banner explains the situation. Contact your administrator to have limits adjusted.

**⚙️ Admin management:**
Administrators manage limits in **Settings › Administration › Users & Access › Limits admin**. They can set per-user quotas, block/unblock users instantly, and monitor real-time consumption.

## How do I export my consumption data?

You can export your personal LLM and Google API consumption as CSV files from **Settings › Features › Usage export**.

**📥 Three export types:**
- **LLM Token Usage** — Detailed per-call breakdown (model, tokens, cost)
- **Google API Usage** — Detailed per-call breakdown (API, endpoint, cost)
- **My Summary** — Aggregated totals (tokens, calls, costs)

**📅 Date filters:**
Quick presets (current month, last month, last 30 days, all time) or custom date range.

**🔒 Security:**
You can only export your own data — it is not possible to access other users' consumption. Administrators have a separate export tool in Settings > Administration with the ability to filter by user.

## Can LIA run on models hosted on my own machine?

Yes. Any of LIA's roles — routing, planning, answering, an agent — can be given a model served by your own **Ollama** server. In **Settings › Administration › LLM Configuration**, the Ollama row of **Provider API Keys** takes your server's address instead of a key (the root, for example `http://localhost:11434`); then pick a model role by role.

**🔎 What your server declares:**
Tools, vision, thinking and context length are read from the server itself, so the screen offers only what each model accepts. A model the server describes nothing about is not listed, but you can still type its name.

**🧠 Thinking and context:**
A model that thinks follows the depth you choose, including none, and its thinking stays apart from the answer. The context window is set per role, and it is the one LIA asks your server for.

No provider bills those calls: local calls are recorded in your consumption history with their token counts and a zero amount. The trade-off stays yours, role by role, and moving a role between a local and a remote model is a configuration change, not a redeployment.

## How do I set a model's context size and output budget?

In **Settings › Administration › LLM Configuration**, on each slot: the **Context window (k)** field, in thousands of tokens.

**🎯 Why per slot:**
A frugal router and a generous responder can run on the same model and deserve different windows.

**🖥️ On a model your Ollama server runs:**
The field shows what the server declares about the model, the model's maximum is written right below, and the number you set is also the window LIA asks the server for. On a model running on your own machine, the panel warns that a window larger than its memory holds pushes it onto the CPU.

**↩️ Clearing the field:**
The slot goes back to what the model declares for itself.

**Why it matters:**
This is the number LIA counts with — when to summarise a long exchange, how much a turn may hold. When what LIA counts and what the server allocates differ, automatic summarisation fires at the wrong moment and the start of a long exchange can be cut without anyone seeing it.

**📏 The output budget:**
The **Max Tokens** field bounds how long an answer may be. LIA holds it to the output cap the catalogue vouches for the model: a budget chosen for a previous model no longer gets calls refused after a model change. When the field exceeds that cap, the slot's card carries a badge and the field shows a warning; the stored figure stays yours to correct.

## How does an administrator update the LLM model prices in bulk?

In **Settings › Administration › LLM Text Pricing**, **Export workbook** downloads the whole catalogue — every model, its characteristics and its tariffs — as an Excel workbook; **Import workbook** — beside it on a computer, in the **More actions** menu (⋯) on a phone — takes the edited file back.

**📗 Inside:** a notice in your language; one row per model with dropdowns fed by a referentials sheet; a **Time slots** sheet for peak/off-peak billing, each window with its UTC days; a read-only **Status** column (no active tariff, several, or billed under another model's name); and **Reasoning model** / **Accepted depths** beside a read-only **Reasoning shape**.

**🔍 Two steps:** the file is analysed and the changes shown model by model — new, modified, deactivated, reactivated — with nothing written; then you apply exactly the plan you reviewed, or preview again if the catalogue changed meanwhile.

**🛡️ An import never:**
• deletes a model missing from the file — **Active** set to FALSE retires it, TRUE brings it back
• writes anything while a problem remains: all or nothing, each problem naming its sheet and cell (a depth the family lacks lists the accepted ones; a model changed since your export asks for a fresh one)
• rewrites an unchanged tariff, so an untouched file leaves the price history as it was
• reads a workbook of an earlier format

Creating a model from the workbook is possible — including one that does no reasoning at all. Changing a model's provider is reported rather than applied, and teaching LIA a brand-new reasoning family is a code change, not a spreadsheet edit. A window with no days applies every day, and a window that crosses midnight belongs to the day it starts on; in the pricing dialog, each window has the same day selector as the routine editor.

**Every price is the one the provider bills.** The reference tariffs are re-read on the providers' pages, and a correction only replaces a value LIA shipped, never one an administrator entered. A write to a model's prompt cache is billed at its own price, where the provider bills it that way. And an edited price reaches every server process at once: every writer of the pricing tables — a tariff, the workbook import, the exchange rate — publishes the change after it is saved.

## How do I choose how deeply a model thinks?

In **Settings › Administration › LLM Text Pricing**, open a model: under **Accepted depths**, LIA lists the depths that model's family offers — from no thinking up to maximum — and you **untick** the ones this model refuses. Leaving everything ticked means “no restriction”: its family's full ladder applies.

You therefore never type a level, and you cannot write one that does not exist. The list comes from the same source the server validates against: what the screen offers is exactly what the model's API accepts.

If no known family matches the model, LIA says so plainly rather than showing an empty list: no thinking parameter will be sent for it, and teaching LIA one is a code change.

The depth actually used for each role (routing, planning, answering…) is set in **LLM Configuration**, where the same resolved list is offered.

One thing to know about models that think by default: their thinking is billed inside the answer budget. LIA therefore writes its short notifications — a reminder, for instance — without thinking wherever the model can be told to, and a reply that comes back empty or cut is replaced by the plain sentence rather than sent as is.

Some models think even when no level is chosen, at the depth their provider sets: LIA knows it, and warns you if the answer budget is too low for that implicit thinking.

## Who decides a setting: the administration screens or the server configuration?

For most configurable values, what an administrator sets in the administration screens takes precedence over the server's configuration file, which itself takes precedence over the built-in default.

Capability switches and spend ceilings work the other way round: the server configuration is a **ceiling**. An administrator can switch a feature off or lower a ceiling from the screens, but never turn on what the configuration forbids — such a feature shows an **Unavailable** badge.

## What is the "Commitments" section?
LIA automatically detects **commitments** in your conversations ("I must call the plumber back", "waiting for Marc's reply"). **Settings › Features › Identity & Memory › Commitments** lists them by direction (you owe / you are waiting), with three one-tap actions: **Done**, **Follow up** (pre-fills a follow-up message) or **No longer relevant**. Nothing is created manually — the ledger's value is being automatic.

The same actions are available from a relationship's card, and a commitment's wording or deadline can be **corrected**. Correcting is not creating: the ledger stays automatic, it simply stops being wrong. The counterparty and the meaning are not editable — changing those would describe a different commitment rather than correct this one.

The settings search also finds it under its other name, "Open loops".

## Can I bookmark or share a link to one settings section?

Yes. When you open a section, the address in your browser changes to point at it: bookmark it, or send it to someone — the link opens the same section of their own settings. A reload brings you back to the same place.

LIA uses these links itself: the getting-started checklist and the Home cards open the right section directly. A link to a section your account does not show says it is not available here; a link LIA does not recognise lands on the settings overview.

**📌 One tap away, everywhere:** in **Settings › Preferences › Personalization › My favorites**, pin the sections you use most. A floating menu then shows them on every screen of the app — drag it where you like and fold it when you don't need it.

## How do I find a setting quickly?

The settings page lists every section in a rail that never scrolls away, and
opens the one you pick in the panel beside it. On a phone the list comes first
and the section takes the screen, with a way back. Two things get you to the
one you want.

**By its look, before searching at all:**
Each family of settings carries its own colour and each setting its own icon —
on the home cards as in the rail. A section you have already visited is found
by its appearance rather than by reading. The colour groups and decorates: it
never carries an information on its own, and the section you have open is still
marked by its background, its weight and the accent colour.

**By searching.** The **"Search a setting"** field sits at the top of the rail.

**What the search looks at:**
- The **title** and **description** of every section
- Translated **synonyms**: "dark" for Appearance, "2FA" or "TOTP" for Strong
  authentication, "GDPR" for the data export, "cron" for Scheduled actions
- Case, accents and apostrophes are ignored — "theme" finds "Thème"

**When you pick a result:**
LIA opens the section in the panel and brings the cursor to it.
Everything works from the keyboard — arrows to walk the list, Enter to open,
Escape to dismiss and then clear — and the number of matches is announced to
screen readers.

**When a section is not there:**
Some sections only render when the feature is active on your account or once
they have data — recent calls, strong authentication, the data export. Rather
than leaving you in front of a page that did not move, LIA tells you the section
is not showing here.

## Where can I see everything LIA sent me?
The **Alerts** destination in the navigation bar gathers in one screen the
streams your instance offers:

• **Proposals** LIA made that wait for your decision
• **Relayed messages** exchanged with your accepted peers
• **Proactive notifications** LIA sent on its own initiative
• **Interest notifications** about the subjects you follow
• **Pending reminders** — what is still to come
• **Scheduled routines** and their next runs, each marked **Enabled** in green or
  **Disabled** in grey
• **Workboard tickets** that need you — a run waiting for your answer, or something overdue
• **Proactive discussions** LIA opened with you, and whether you answered
• **My SMS** — the messages your phone relayed to LIA

Each section arrives folded, **already showing its exact total**, and
paginates by ten — so you choose what to open rather than opening it to find
out. No list is fetched until something is unfolded: only the counts are,
in a single read, and opening a section costs exactly one more.

Under the title sit three buttons of one height: **Activity timeline** (when
your instance offers it), **Action journal** and **Refresh**, which re-reads the
counts and every open section. The **Activity** page carries the same ones in
the same place, with **Received / To follow up** to come back here.

The settings panels remain the detailed configuration for each of those
streams, and every deep link you had saved keeps working. Reminders are the one
section that can never be a history: a reminder leaves it once it fires,
and a repeating one comes back at its next occurrence.

## Where do I see what LIA can do for me?

On **Home**, under **My shortcuts**, open **Capabilities**: a star chart of your own account, with a line saying how many capabilities are active out of those available.
• **Filled** star: active, genuinely usable now
• **Outlined** star: waiting for you to set it up
• **Size**: what it holds — memories, routines, documents…

A capability your instance switched off is **absent**, not greyed out. There is no score, level or comparison with anyone: the shape is simply your configuration.

Every star is a link to the place where that capability is set up. On a phone the same map arrives as a list — same data, same order, same links — and if you asked your system for less motion, the chart simply stays still.

## Do I have to open a section to know whether it holds anything?
No. Every section of the **Alerts** destination shows its exact count while
still folded, so you choose what to open rather than opening it to find out.
The counts arrive in a single read when the page loads; the lists themselves
still wait for you to unfold a section.

A section your instance has disabled is not counted at all — it is absent from
the page, so counting it would be work for a badge nobody can see.

## Can I give LIA standing rules, and remove one later?

Yes. Say once how you want LIA to work for you, for example:
• *Always answer me in French*
• *Never schedule meetings before 10am*

LIA files such an instruction in its long-term memory under a category of its own, **Rules & directives**, apart from the facts it knows about you.

**📐 How it is applied:** when a rule bears on what you ask, LIA reads it as a working rule, ahead of the facts it remembers. Long-term memory must be switched on.

**🛡️ Protected:** a new rule is pinned as soon as it is stored, so LIA does not rewrite it on its own. Unpinned, a rule can be corrected when you say something new, but it is never simply dropped.

**🗑️ Changing or removing one:** in **Settings › Features › Identity & Memory › Memory**, filter on **Rules & directives**, then edit, unpin or delete it. **Add** lets you write one yourself.

## What happens when a fact I told LIA changes?

Just tell LIA — *my daughter's name is Elsa, not Emma* — and its memory follows. In the background, LIA reviews what you said: the old memory is **retired, with the date** it stopped being true, and the new one takes its place.

**🚫 No stale fact in answers:** a retired memory is never recalled again, and **Settings › Features › Identity & Memory › Memory** lists only what LIA holds as true today.

**🧾 A short trail:** the retired version is kept for a period your administrator sets, then erased for good.

**📌 Two exceptions:**
• a **pinned** memory is never changed automatically — edit it yourself
• an edit you make in Settings replaces the memory directly: your correction is the authority, not a version to archive

## Can I change the look of the expressive eyes?

Yes. **Settings › Features › Identity & Memory › Avatar style** offers several styles for the animated companion that follows you throughout the app — each card renders a **live preview** of the style, so you pick by seeing, not by name.

**🎨 One style, every behavior:** whichever look you choose, the companion keeps the same expressions, reactions and idle life; only the shapes change.

**🎚️ Previews stay calm:** each card keeps the breath and the resting hold and animates on hover or focus, so you compare silhouettes rather than moods. The public home page uses its own presentation, independently of your choice.

**💾 Remembered on this device:** the choice is stored in your browser, alongside the companion's position, size and visibility.

## Frequent or occasional exchanges: which should I pick?
In **Settings › Preferences › Personalization › Usage preferences**, you tell LIA how you use it, and it prepares its requests to the AI model accordingly whenever it works in **ReAct mode** — scheduled actions and Workboard tickets included. The choice applies from your next message.

**🔁 Frequent exchanges** — for regular back-and-forth. LIA keeps every tool at hand and lays out each request so the next one starts with what was already sent, which the provider bills at a reduced rate when the model reads it again. The first message costs a little more, the next ones much less.

**🕰️ Occasional exchanges** — for spaced-out questions. LIA picks the tools each question needs, so every message costs about the same, however long ago the previous one was.

**🎯 Why it is your choice:** the saving exists only while the provider still holds what was sent, and it holds it for a limited time. Messages close together read it back; messages hours apart would pay the heavier first message every time. Nobody knows your rhythm better than you.

**Good to know:**
• if the configured AI model cannot hold every tool, LIA picks them by relevance for that message
• the saving relies on the prompt cache of your instance's AI provider: on a model without one, occasional exchanges remain the cheaper choice
• a new account starts with **Occasional exchanges**; an older account that never chose follows its instance's default
• the Pipeline mode keeps its own planner and is not affected

## How does an administrator send an announcement to some users only?
In **Settings › Administration › Broadcast Message**. Write the message, choose **All users** or **Selected users**, and when it expires.

**🎯 It reaches whom it targets:**
The recipients are stored with it: a targeted announcement is shown to them only, including at their next sign-in. A selection that targets no active account is refused, rather than going to nobody — or to everybody.

**🗂️ Sent broadcasts:**
The history shows, for each announcement, its audience, the exact number of people reached with a preview of their names, its expiry date and the delay chosen.

## Can an administrator enable JEV decisions?

Yes, in **Settings › Administration › JEV integrations**: a general switch, **Enable JEV**, and one switch per usage, each independent — turning the general switch off keeps their individual choices. Everything is off by default, and a usage only works once a TypeSafe API key, an active decision model (in **LLM Configuration**) and its tariff (in **LLM Text Pricing**) are in place.

The model helps classify a value or choose within a declared scope; compatibility rules, permissions and execution stay in code. An uncertain, unavailable or disabled judgement falls back to the existing processing. For example, **Guarded parameter values** — which judges, before a tool call, whether an address, a place or an e-mail value really is one — can refuse a value of another kind only when it is confident, and can never accept a value the existing guard refuses.

A change applies to new operations; work in progress keeps its initial choice. A paid call that fails and its fallback both count. While your debug panel is on, it lists your own account's JEV calls for a short, bounded time. Test-corpus results do not promise the same benefit on all your requests.

## Can I make the interface text bigger or smaller?
Yes. In **Settings › Preferences › Personalization**, the **Font size** section
sets the text from **14 to 20 px** (16 px by default), with a live preview and a
button to return to the default size.

**🔠 Only the text changes:** panels, spacing and icons keep their dimensions —
the chat, the settings and the debug panel stay laid out as before, and only
what you read grows or shrinks.

**🔄 On all your devices:** the choice is saved on your account and applies
wherever you sign in. It combines with the font chosen in the section just
above.

## Can I ask LIA to change its own settings?

Yes. Try “Which response mode is active?”, “Switch my answers to HTML + cards” or “Show my routines”. LIA uses the same settings and labels as the interface, within the features available on your instance and authorised for your account. Reads and some small reversible preferences may be direct. Creating, deleting or making a sensitive change retains its confirmation.

## When do I confirm or continue in the browser?

Confirmation applies to the operation and content shown. OAuth sign-in, file selection, a key or device permission continue in your authenticated browser: do not paste these secrets into chat. LIA may prepare the request and wait for that step. Enabling hands-free listening and sensitive permissions retain their protections; a command cannot bypass them.

## How do I send SMS to LIA and control their use?

In **Settings → SMS**, after Meetings, create and confirm a token for your phone. An iPhone Shortcuts automation then sends each SMS to LIA by HTTPS POST, in the format below. Reuse the same event ID and payload for retries.

**📤 The request:**
• `POST https://your-lia-domain/api/v1/ingest/message`
• headers: `Authorization: Bearer pi_…` (the token created in LIA) and `Content-Type: application/json`
• body: one JSON object per SMS; an array of objects, `{"data": [...]}` or one object per line (NDJSON) sends a batch

**📋 The fields:**
• `sender` (required): who sent it — number, address or name
• `date` (required): ISO 8601 text with a timezone, for example `2026-10-19T09:30:00+02:00`; a date in the future is rejected
• `body` (required): the text of the SMS
• `o` (required): the origin, in letters, digits, `-` or `_` — for example `iphone`
• `event_id` (optional, recommended): a UUID created once per SMS and reused on every retry
• `date_kind` (optional): `received` when the date really is the reception time, `captured` when it is the time the shortcut ran, `unknown` otherwise (the default)
• `schema_version` (optional): `1`
An unknown field gets the SMS rejected.

**💡 Example:**
`{"schema_version": 1, "event_id": "812a2280-6047-4af3-9422-27e2581ec37b", "sender": "Alice", "date": "2026-10-19T09:30:00+02:00", "date_kind": "received", "body": "The meeting moved to 10:30.", "o": "iphone"}`

**✅ The response:**
A single SMS returns **201** when stored, **200** when it was already received or is set aside (a recognized access secret, a blocked sender), **409** when the same `event_id` arrives with different content and **422** when the format needs fixing. In a batch, each SMS gets its own verdict in `items`.

Your SMS remain in LIA until you delete them. **Assistant access** starts disabled, independently of ingestion and immediate reception push. The **Immediate push for each new SMS** switch sits at the top of this page. Proactive notifications also have their own **My SMS** source and hours. Recognized access secrets are excluded before storage; the heuristic cannot recognize all private text.

Personal export includes readable SMS. Erasure invalidates hosted exports but cannot recall downloaded copies, earlier chats or separately retained knowledge. LIA receives only what Shortcuts sends; verify iOS trigger criteria and permissions on the phone. Step-by-step guide: `docs/guides/GUIDE_IPHONE_SHORTCUTS_SMS.md`.
