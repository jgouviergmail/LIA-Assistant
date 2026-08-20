# Proactive Notifications

## What are proactive notifications?
Proactive notifications allow LIA to **take the initiative** to contact you with useful information:

**🧠 How it works:**
• LIA continuously analyzes multiple data sources (calendar, weather, emails, interests, memories)
• An LLM **intelligently decides** whether there's something useful to tell you
• The message is rewritten with your **personality** and in your **language**
• LIA's inner emotional state subtly shapes the **tone** of notifications (warmth, energy, rhythm) — but is **never projected onto you**

**📌 Examples:**
• "*Rain expected in 45 minutes, don't forget your umbrella*"
• "*You have a meeting at 2pm and rain is forecast — bring an umbrella*"
• "*A topic you're interested in is trending today*"
• "*Based on my observations, you might find this relevant today...*" (journal-informed)

**💡 Philosophy:**
LIA only sends a notification when it is **genuinely useful** — quality over quantity.

## How do I enable proactive notifications?
Enable the feature in just a few clicks:

**⚙️ Access:**
Settings → "*Proactive Notifications*" section → Enable the toggle

**📝 Available options:**
• **Time window**: configure your own start hour (default: 9 AM) and end hour (default: 10 PM) — independent from interest notification hours
• **Min/max per day**: set the minimum (default: 1) and maximum (default: 3) notifications per day (range: 1-8)
• **Travel weather**: a foldable block to opt in to location-aware weather

**💡 Push delivery:**
Push (FCM/Telegram) follows your **global notification opt-in** automatically — there is no separate per-feature switch. Every message is also archived in the conversation, so you will find it at your next login either way.

## What data sources are used?
LIA aggregates **8 data sources** in parallel to decide whether to notify you:

**📅 Calendar:**
• Upcoming events (next few hours)
• Requires an active calendar connector (Google Calendar, Apple Calendar, or Microsoft)

**🌤️ Weather + Changes:**
• Current conditions + transition detection: rain starting/stopping, **temperature drop OR rise for tomorrow** (compared on daily averages — the old detector was removed because it flagged nighttime cooling as a "temperature drop", which was just the normal day/night cycle), strong wind
• Requires an OpenWeatherMap connector + configured home location
• **Travel-aware location (v1.16.7, opt-in)** — If you enable "Use my current location for weather alerts" in Settings > Proactive notifications, LIA uses your browser position instead of your home address when you're more than 50 km away from home and the position is less than 24 h old. The notification always mentions the city it's referring to. Your location is encrypted, never historized (each update overwrites the previous one), and wiped immediately if you disable the option or remove your home address.

**✅ Tasks:**
• Pending or overdue tasks
• Requires an active tasks connector (Google Tasks or Microsoft To Do)

**📧 Emails:**
• Today's unread emails (urgent, actionable)
• Requires an active email connector (Gmail, Apple, Microsoft)

**⭐ Interests:**
• Trending topics among your active interests

**🧠 Memories:**
• Relevant information extracted from your memories

**📓 Journals:**
• Relevant entries from the assistant's personal journals (self-reflection, observations, learnings)
• Journals are fetched in a **second pass** — LIA builds a dynamic query from the aggregated context (calendar, weather, emails, etc.) to find the most relevant journal entries
• In addition to the dynamic-query entries, the **compiled user-model portrait brief** (~60 tokens) is injected so the notification voice is aligned with the same nuanced model of you that drives the conversation
• Requires journals to be enabled (Settings > Features > Personal Journals)

**📊 Indicators:**
The Settings section shows a **green badge** for each connected source and a **gray badge** for unavailable sources.

**🩺 When a source cannot answer:**
• Every source is optional and independently failable — a slow or unavailable one never blocks the notification
• A source that drops out is recorded rather than silently missing, so a degraded notification can be noticed and fixed
• Health indicators in particular are read as per-day aggregates, light enough to always make it into the notification when you have opted in

## How often will I receive notifications?
Frequency is **controlled at multiple levels**:

**📊 Your controls:**
• **Min/max per day**: you choose (1-8 range, default min 1 / max 3)
• **Time window**: only during your configured hours (default 9 AM - 10 PM, independent from interest hours)

**🛡️ Automatic safeguards:**
• **Global cooldown**: minimum 1h between 2 proactive notifications
• **Anti-redundancy**: the LLM sees recent notifications and avoids repeating the same topic
• **Cross-type dedup**: interest notifications are also considered (no thematic spam)
• **Activity cooldown**: if you chatted with LIA in the last 15 minutes, no notification will be sent

**💡 In practice:**
You'll receive between 0 and 3 notifications per day, only when relevant. Some days, LIA may decide not to send anything.

**🛡️ Response filtering protection:**
Proactive suggestions (weather alerts, upcoming event reminders, etc.) are protected from being filtered out. When LIA adds proactive data to a response, those items are preserved even if the response filtering considers them unrelated to the original question.

## How do I give feedback on a notification?
Your feedback helps LIA improve:

**👍👎 Feedback buttons:**
• Each notification in the chat displays **thumbs up / thumbs down** buttons,
  next to the copy button — the same place as on an ordinary answer
• Your feedback is recorded to improve future decisions
• Once you have voted, your choice stays on screen: shown as chosen and
  locked, because that verdict is final. It follows you on every device and
  after a reload — a notification is rated once

**📜 History:**
• Settings → Proactivity → **Recent notifications** lists the last ten you
  received: date, the message itself, the sources used, the priority, and the
  verdict you already gave
• The block is folded by default and loads nothing until you open it
• The interest notifications have their own list, in the same shape

**⚙️ Adjustment:**
• If you receive too many notifications, reduce the daily maximum
• If a source is not relevant, switch it off in **Notification topics** —
  eleven switches, one per source. You keep the service connected and the tool
  you ask with: being connected to a service and being interrupted by it are
  two separate decisions
• Everything is on by default, and a switch that cannot produce anything says
  so (leave-by advice needs the calendar)

## Are proactive notifications affected by usage limits?
Yes. If your administrator has set usage limits and you have reached any of your quotas (tokens, messages, or cost), proactive notifications are automatically paused until your limits are reset (next billing period) or adjusted by your administrator. This ensures that background LLM usage doesn't exceed your allocated budget.


## What are "commitments"?
A commitment is a **promise LIA heard in conversation** and quietly keeps for you — "I must call the plumber back", "Marie owes me the quote". At the right moment (imminent deadline, or a loop left silent too long), a proactive notification gives a gentle, direction-aware memory-jog: "You wanted to call the plumber back — is now a good time?" vs "Still no news from Marie about the quote?".

**Never nagging:** each loop has its own cooldown — once surfaced, it will not come back for several days. A loop closes itself when you say "done", or from the dashboard "For you" card, and quietly expires after weeks of inactivity.

**⚙️ Admin:** off by default (`OPEN_LOOPS_ENABLED`).

## Can LIA tell me when to leave for a meeting?
Yes. When your next calendar event has a **location** and starts within a few hours, LIA checks **real traffic** (Google Routes) from your effective position and can notify you: "Leave by 13:30 — 30 min drive to your 14:00 appointment", combined with weather when it matters ("rain expected at 14:30").

At most one route check per cycle, cached per event — and the same notification is never sent twice for one event.

**⚙️ Admin:** off by default (`HEARTBEAT_DEPARTURE_ENABLED`); requires a configured home location.

## How do I read a notification's urgency at a glance?
Every proactive notification carries its level, and the levels are told apart
by **density** rather than by hue alone:

• **High** renders on a solid ground
• **Medium** renders on a light tint
• **Low** stays neutral

Two neighbouring hues merge on a phone, in bright sunlight, or for a reader who
tells them apart poorly. A solid ground against a light tint stays legible even
in black and white.

The word is always shown next to the colour: colour speeds up reading, it never
replaces it. A level LIA does not know yet renders neutral rather than red —
presenting an unrecognised level as urgent would be a claim nobody made.

## Will a proactive notification interrupt a conversation I'm having?

No. Before any proactive send, LIA checks your latest real message: if you
were active within the last few minutes, the notification waits. The check
reads your actual messages (automated system rows are excluded), so being
mid-conversation genuinely holds proactive pushes back — LIA waits its turn.

## Can one account be forgotten by the notification cycle?

No. On each cycle, candidate accounts are selected in a randomized order and
accounts that disabled the feature never take a slot. No account can end up
systematically served last, however many users the instance hosts.

## What are LIA's proposals (offers)?
Sometimes LIA notices it *could* do something useful but the action is not urgent enough for a notification. These become **proposals**: standing offers listed on your dashboard that wait for your decision.

**💡 Examples:** "you usually review your inbox around now — want a summary?", "a routine you follow was missed yesterday — should I check on it?".

**✅ You decide:** each proposal can be accepted (LIA performs it immediately) or dismissed (it disappears without side effects). Nothing runs until you say so.

**🔕 No pressure:** proposals do not ping you — they wait quietly on the dashboard, with a counter in the hub so you know when something is waiting.

## How can I see what LIA does in the background?
The **activity timeline** on your dashboard shows the assistant's otherwise invisible work as a chronological feed: memories learned, routines checked, briefings prepared, proposals made, habits confirmed.

**🔎 Honest by construction:** every entry comes from a real recorded event — the timeline is a read model over LIA's own activity ledger, with exact counts (never estimates).

**🕰️ In your timezone:** entries are displayed in your configured timezone and language.
