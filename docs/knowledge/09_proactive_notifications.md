# Proactive Notifications

## What are proactive notifications?
Proactive notifications allow LIA to **take the initiative** to contact you with useful information:

**🧠 How it works:**
• LIA continuously analyzes fourteen data sources (calendar, weather, emails, tasks, interests, memories, journals, health signals, SMS, birthdays, open loops, departure, habits, workboard)
• An LLM **intelligently decides** whether there's something useful to tell you
• The message is rewritten with your **personality** and in your **language**, at your local time
• LIA's inner emotional state subtly shapes the **tone** of notifications (warmth, energy, rhythm) — but is **never projected onto you**

**📌 Examples:**
• "*Rain expected in 45 minutes, don't forget your umbrella*"
• "*You have a meeting at 2pm and rain is forecast — bring an umbrella*"
• "*A topic you're interested in is trending today*"
• "*Based on my observations, you might find this relevant today...*" (journal-informed)

**💡 Philosophy:**
LIA only sends a notification when it is **genuinely useful** — quality over quantity.

## How do I enable proactive notifications?

In **Settings › Features › Proactive notifications**, switch on **Enable proactive notifications**.

**📝 Then, in the same panel:**
• **Notification time window**: your own start and end hours (9 AM to 10 PM by default) — separate from the hours of your interest notifications
• **Notification topics**: switch a source off to keep using it on request without being notified about it
• **Anticipated moments**: the instants LIA may come back to you, such as right after a meeting
• **Recent notifications**: what LIA actually sent you
Weather while you travel is set under **Settings › Preferences › Location**.

**💡 Delivery:** notifications reach your devices once **Push Notifications** are on (Settings › Preferences), and Telegram if you linked it — no separate switch per feature. Every message is also kept in the conversation, so you will find it at your next visit either way.

## What data sources are used?
LIA aggregates **fourteen sources** in parallel to decide whether to notify you. Each has its own switch, and the settings panel says for each one whether it is connected:

**📅 Calendar** — upcoming events (next few hours); needs an active calendar connector (Google, Apple or Microsoft)

**📧 Emails** — today's unread, urgent or actionable emails; needs an active email connector

**✅ Tasks** — pending or overdue tasks; needs Google Tasks or Microsoft To Do

**🌤️ Weather** — current conditions and transitions (rain starting or stopping, a temperature drop or rise for tomorrow compared on daily averages, strong wind); uses your own OpenWeatherMap connector if you set one up, otherwise the Google Weather service your instance provides, and needs a home address
• **Travel-aware location (opt-in)** — with **Remember my last position** on in **Settings › Preferences › Location**, a recent position far enough from home replaces your home address, and the notification names the city (see "How do weather alerts work when I'm travelling?").

**⭐ Interests** — a varied sample of your active interests, one per theme, least recently covered first

**🧠 Memories** — relevant facts from your memories

**📓 Journals** — relevant entries from the assistant's personal journals, when journals are enabled
• Journals are fetched in a **second pass** — LIA builds a dynamic query from the aggregated context (calendar, weather, emails, etc.) to find the most relevant journal entries
• In addition to the dynamic-query entries, the **brief of the compiled user-model portrait** (two or three sentences) is injected so the notification voice is aligned with the same nuanced model of you that drives the conversation

**❤️ Health signals** — when health metrics are enabled for your account

**💬 My SMS** — recent messages your phone relayed that LIA has not mentioned yet; needs the assistant's access to your SMS

**🎂 Birthdays** — from your Google contacts

**🧵 Open loops** — the unfinished threads LIA keeps track of

**🚗 Departure** — when to leave for a meeting, from your calendar

**🧭 Habits** — a learned routine whose usual time passed without your asking, once a habit profile exists

**📋 Workboard** — the tickets LIA holds for you

**📊 Indicators:**
The Settings section shows a **green badge** for each connected source and a **gray badge** with a note for the others; a source that depends on another says which one you switched off.

**🩺 When a source cannot answer:**
• Every source is optional and independently failable — a slow or unavailable one never blocks the notification
• A source that drops out is recorded rather than silently missing, so a degraded notification can be noticed and fixed
• Health indicators in particular are read as per-day aggregates, light enough to always make it into the notification when you have opted in

## How do weather alerts work when I'm travelling?

By default, proactive weather notifications use your **home address**. To let them follow you, go to **Settings › Preferences › Location** and turn on **Remember my last position**, plus **Geolocation** in the same section: your position is captured from the browser when you send a chat message. A home address is needed too — distances are measured from it.

**🎯 When it kicks in:**
A notification uses your last position instead of your home only when it is **recent** and you are **far enough from home** — a freshness window and a distance the administrator sets, so moving around town changes nothing. Otherwise your home is kept. The same remembered position also serves the chat, routines and the briefing when your live position is unavailable.

**🏙️ Transparent:** when the forecast is not for your home, the notification names the city.

**🔒 Privacy by design:**
• your position is **encrypted** and **never historized** — each update overwrites the previous one
• it is **deleted** as soon as you turn the option off or remove your home address
• the **Currently stored** block shows what LIA kept, with a **Clear** button

## How often will I receive notifications?
Frequency is **controlled at multiple levels**:

**📊 Your controls:**
• **Time window**: only during your configured hours (default 9 AM - 10 PM, independent from interest hours)

**🛡️ Automatic safeguards:**
• **Global cooldown**: minimum 1h between 2 proactive notifications by default, a gap your administrator sets
• **Anti-redundancy**: LIA re-reads the **content** of its last notifications (10 over 7 days by default) and never proposes the same topic, activity or product again — even when it comes from a different source
• **Cross-type dedup**: interest notifications count too, in both directions (a theme covered by either flow rests for a while)
• **Activity cooldown**: if you chatted with LIA in the last 15 minutes (by default), no notification will be sent

**💡 In practice:**
There is no daily quota: LIA only writes when a signal warrants it, and no useful notification is held back by a cap. Some days, LIA sends nothing at all.

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
• In **Settings › Features › Proactive notifications**, the **Recent notifications** block
  lists the last ten you received: date, the message itself, the sources used, the priority, and the
  verdict you already gave
• The block is folded by default and loads nothing until you open it
• The interest notifications have their own list, in the same shape

**⚙️ Adjustment:**
• If you receive too many notifications, narrow your notification window
• If a source is not relevant, switch it off in **Notification topics** —
  fourteen switches, one per source. You keep the service connected and the tool
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

## Will a proactive notification interrupt me while I'm chatting or in a meeting?

No. Before writing to you, LIA checks two things:
• **your last message** — in the web app, the mobile app or on Telegram: if you wrote recently, the notification waits (the **activity cooldown** of the safeguards). LIA's own automated messages never count as you being active
• **your calendar**, when one is connected: during a meeting in progress nothing is sent — not even a message prompted by a new e-mail — and the next pass looks again once it is over

When a notification does arrive while the chat is open, it never cuts into an answer being written: the thread waits for that answer to finish, then shows the notification in place.

## Can one account be forgotten by the notification cycle?

No. On each cycle, candidate accounts are selected in a randomized order and
accounts that disabled the feature never take a slot. No account can end up
systematically served last, however many users the instance hosts.

## Where do I find LIA's proposals, and what happens when I accept one?

When a proactive notification offers to run a request you usually make, the offer also waits in **Alerts › Proposals** until you decide — for a few days, a window your administrator sets. The section's counter tells you how many are waiting.

**Two buttons:**
• **I'm on it — open the chat**: the offer is counted as useful and the chat opens with the proposal's text in the composer. **Nothing is sent** until you send it yourself, and any confirmation the request needs is still asked
• **Not now**: the offer is counted as not useful and leaves the list

Both are the same answer as a 👍 or a 👎 on the notification: they teach LIA about the habit itself, and a habit refused often enough stops being offered.

## How can I see what LIA has been doing in the background?

Open the **Activity** page — with the **Activity timeline** button of the **Alerts** page, or **See everything LIA did** on the **For you** card of the Home page. Its **Received / To follow up** button brings you back to the **Alerts** page; it sits under the title, where the Alerts page places **Activity timeline**, next to **Action journal** and **Refresh**. It tells the story of LIA's own work over the last days (the period is shown under the title):
• proactive notifications and interest discoveries
• journal notes LIA wrote from your conversations
• habits it detected
• commitments it started tracking, and those closed
• routines it ran

Each kind carries its **exact total** for the period, and if one source does not respond the page says the view may be incomplete rather than silently showing less. Reminders are not listed: a reminder that fires leaves no record to count.

For the exhaustive record — every action and every source consulted — the **Action journal** button opens the transparency registers. Your administrator can switch the timeline off.

## Can LIA react to an email or an invitation right away?
Yes, when the administrator has switched the capability on. Instead of waiting for its next scheduled pass, LIA can decide within minutes of a message or a calendar change arriving.

**What it looks at — and nothing else:**
- an email carrying the label you treat as important, never promotions, social or mailing lists
- an event starting soon that someone else changed, or one still waiting for your answer

**What does not change:** your notification window, the pauses between two messages, and your choice of sources. A burst of arrivals still produces a single wake-up, and if the moment is not right the message simply waits for the regular pass — nothing is consumed by a wake that was refused.

In the notification history, the ones that answered an email or an invitation are marked as such, next to those that came from the regular pass.

## Can LIA come back to me right after a meeting?

Yes, with **anticipated moments**: shortly after an important meeting ends, LIA asks how it went — without waiting for its next regular pass.

**How it behaves:**
• one open question, grounded in at most two facts — never a judgement, never an evaluation
• the meeting is re-read just before LIA speaks: one cancelled, moved later or declined in the meantime says nothing
• a meeting LIA recorded the minutes of is not asked about — you already have them
• back-to-back meetings earn one question, at the end of the block
• your notification window still applies, and LIA holds back if you were just chatting or it notified you a moment ago

**Where to control it:** **Settings › Features › Proactive notifications** › **Anticipated moments**, shown once proactive notifications are on. Each kind has its own switch (**After a meeting** needs a connected calendar), and your administrator can switch the whole capability off.

## Can LIA offer to run a request I usually make and forgot today?
Yes, once it has learned the habit. When a request you make regularly — say your e-mail review every weekday around 8:30 — has not been made by the time its usual slot passes, the next proactive pass may offer to run it, naming it: "shall I run your usual e-mail review?"

**What it needs:**
• habit learning on for your account, and a recurring request recognised in the habits panel (the row reads what and when, e.g. "Search · E-mails — every day ~08:30")
• a habit that is neither paused nor blocked — a status you set holds everywhere
• the proactive pass itself: your hours and pauses still apply, and a person in a meeting is not interrupted

**How to answer:** a 👍 or a 👎 on the notification is an answer about the habit itself; a habit refused often enough stops being offered.

**What it never does:** run the request on its own — an offer is a question. And an offer is counted against the day only when LIA actually made one, not when a notification merely mentioned your habits.

## What does a proactive pass write in my registers?
Every proactive pass files what it consulted — the sources it aggregated and the calendar check that decides whether you are in a meeting — under its own run in the **Registers** (the **Consultations** list and the **LIA's own initiative** tab), exactly as a conversation turn does. A source answered from cache was not opened and is not filed; a source that failed to answer is filed as failed rather than read as silence. Interest notifications stand aside during a meeting and respect your learned rhythm like the heartbeat does, and a wake triggered by a new mail skips the rhythm but never a meeting.

## What are proactive discussions?
A **proactive discussion** is a personal conversation LIA starts with you of its own accord — taking an interest in a plan, encouraging you, asking an open question — at a good moment. It is separate from notifications: a notification tells you something, a discussion invites a reply.

**Where to turn it on:** **Settings › Features › Proactive discussions**, off until you switch on **Allow LIA to start a discussion**. There you choose:
• your **discussion hours** (the window may cross midnight) and a **maximum per day**, or no limit; **Pause** stops them for as many hours as the button states (24 by default; your administrator sets the length)
• the **allowed data**: each source is its own switch, a new source stays off, and a source LIA cannot reach is never read
• the **sensitive topics** (health, personal relationships, finances, grief, intimacy), which LIA may take into account on top of the source's permission: all of them are allowed by default unless your administrator chose otherwise, and you untick any LIA must never use (an account that had already chosen keeps its choice)
• the **Topics to avoid** you asked for, which you can allow again

**What LIA understood:** two folded panels. **Context data** lists every element LIA keeps, with the period it covers and when it was last read; the filters above it apply as soon as you change them (the search once you stop typing). Switch **Allow** off on one (it becomes **Not usable**, and its known related evidence is excluded too), **Delete** it, or purge everything. **Context** is where the work stands: **Rebuild context** reads every source you allow again and interprets every element it can afford, not just enough to speak; it says it is running and the page updates itself when it ends. Automatic runs also update the context as your sources change: the panel says when the context was **last rebuilt** and **last updated**, then shows the **last run** — an automatic run or a rebuild you asked for —, **why it ended** (for instance nothing new to interpret, or nothing justified a discussion), **what it read and interpreted** — sources read, facts read, admitted and interpreted, calls, usable items, counts only — and **what that run cost**. No spending amount is shown: when a limit stops LIA — your daily limit, your usage quota, the instance's daily budget, or a run limit set too low by your administrator — one plain sentence at the top of the panel says which, and when it renews. When an opening is still waiting for your reply, another sentence says so, with when it was proposed and until when it holds the next one back.

**When LIA writes:** the opening appears in the conversation. Answer it, ignore it, or use one of four reactions: **Thanks, this resonates**, **Not now** (pauses for the hours the button states), **Do not bring up this topic**, **This context is incorrect**. A recent proactive notification or interest alert no longer holds a discussion back (your administrator can restore a gap), and two openings stay at least 30 minutes apart by default. An opening you have not answered holds the next one back for an hour by default (your administrator sets it): an answer or a reaction ends that wait at once — **Not now** then pauses as it says — and a newer opening closes the one left unanswered. **Alerts › Proactive discussions** keeps the history, each opening marked open, answered, set aside or lapsed; in the settings, **Recent discussions** lists them too, each dated in bold, and **Why this opening?** shows the reason and the sources recorded when it began.

**Privacy:** an opening touching a sensitive topic stays private — its push notification is masked and it is never sent to your external channels such as Telegram. An SMS is treated like an email: having read one does not make an opening private.

**Cost:** every model call and every paid read of a discussion or a rebuild is counted on your account like a conversation turn, and your usage quotas apply to it: a run your quota refuses reads nothing and says so. It also stays within the spending limits your administrator sets per run, per account per day and for the whole instance per day. Without those limits nothing starts, and your administrator can switch the feature off.

**In the registers:** each discussion LIA opens is listed under **LIA's own initiative › Actions taken on its own** (« Discussion started »), and the sources its run read under **Sources consulted on its own**; a rebuild you asked for is filed as your request.
