# Today Briefing — the dashboard home page

## What does the Home page show?

The Home page opens on **your day**, from top to bottom:
• the **date** as its title, in your time zone — it changes at midnight
• a welcome card with **LIA's living face** (the small portrait switches to the other avatar in one click), a greeting LIA writes for you with its cost, and **Open Chat** and **Services**
• the **radio**, when your instance offers it
• a few hints you can dismiss — the getting-started checklist, installing the app
• **My shortcuts**: Help, Capabilities, Workboard, Registers, Settings
• **My dashboard**: **LIA's briefing**, then the cards of your day
• **What LIA achieved** this billing period: useful results confirmed, successful actions, successful routines, commitments closed
• **Usage Statistics**: your usage limits, if any, and a **Consumption** table — messages, tokens (input, output, cached), Google API calls and cost, for the period and in total

If the briefing cannot load, the radio and your shortcuts stay available.

## Which cards are on My dashboard, and what can I do from them?

Ten cards, in the order you choose: **Weather** (with air quality and pollen where available), **Birthdays**, **Active reminders**, **Health**, **Agenda** (a timeline, day by day), **Unread mail**, **For you** (commitments being tracked and your next routine), **Tasks** (pending and overdue), **Documents** (recent Drive files) and **Workboard** (what waits on you, what LIA or your connections hold, what is late or open — each count opens the board, filtered).

**👆 From an item:**
• a click opens the chat with a matching request ready — you send it yourself
• **More actions** (⋯) runs a named action at once: summarise or reply to a mail, prepare for an event or get directions, complete or postpone a task, write a birthday message… anything that changes your accounts still asks for confirmation in the chat
• some act in place: cancel a reminder (after a confirmation), mark a commitment done or no longer relevant, or edit it

## Can I customize the dashboard cards?

Yes — the shortest path: the **Customize** button next to **Refresh all**, right above the grid, leads straight to the right section. Or go through **Settings › Preferences › Personalization › My dashboard**. Hide any of the ten briefing cards — including the Workboard card, which shows what is waiting on you, what LIA is holding and what is overdue — or reorder them (↑/↓ buttons, or drag-and-drop). A hidden card is **not even fetched**: fewer calls to your services, a faster dashboard.

A starter checklist on the Home page also shows what your instance can do (connectors, voice, channels…) until you dismiss it.

## Why is a card missing, empty or showing an error?

Each card says where it stands:
• **Empty**: the source answered and there is nothing today — "Inbox zero 🎉"
• **Error**: the source failed this time. The card keeps the last data it received, with its age and the time of the last attempt, and offers **Retry**, **Try again later** or **Reconnect** when your access has expired
• **Waiting to be set up**: a card whose source is not configured is not drawn. One discreet line under the grid names those cards, each linking to where you switch it on — your connectors for the agenda, mail, birthdays, tasks, documents and weather (which also needs your location), the **Health data** settings for health
• **Hidden**: a card you hid yourself is never fetched, and never named in that line

The Workboard card is absent when your instance has switched the workboard off.

## How fresh is the dashboard, and how do I refresh it?

Each card shows when its data was read — "5 min ago" — and adds "cache" when it was served from memory rather than fetched again. Each source is kept for a time that suits how fast it changes; reminders are always read live, and birthdays move on at your midnight.

**🔄 One card:** the circular arrow at the top of a card fetches that source again. LIA's greeting and briefing are not rewritten, so no new text is billed.

**🔄 Refresh all:** the button above the grid fetches every visible card again and has LIA write a new greeting and briefing.

A short "updated ✨" confirms a refresh; if something could not be refreshed, a line says so and the last data received stays on screen. Opening the page reads each source only once, even though the cards and LIA's texts arrive separately — the cards first, the texts as soon as they are written.

## What are LIA's greeting and briefing, and what do they cost?

When you open the page, LIA writes two short texts from your cards, in your language and with its personality:
• the **greeting** on the welcome card — one sentence suited to the time of day and to what your cards hold
• **LIA's briefing** above the cards — a few sentences tying together what matters today (the Workboard card is left out of it); the ➖/➕ button folds it

**💶 Cost in view:** each text shows its tokens and its cost in euros — hover it for the model and the input / output / cache breakdown. Both count in your usage, and both are written again when you press **Refresh all**.

The cards never wait for them. If the model is unavailable or a spending limit is reached, a written greeting takes its place and no briefing is written. When too few cards have something to show, no briefing is written either — nothing is billed — and the page says there is not enough data today.

## Can I listen to LIA's briefing?

Yes. The speaker button beside **LIA's briefing** reads it aloud in your language, with LIA's voice — the feminine or masculine one that follows the avatar you picked, as set in the voice mode settings. Press it again to stop, even while the audio is still being prepared.

The reading uses the same speech engine as LIA's spoken replies and is billed like any reading, in your usage. If the speech service returns no audio, a message tells you so instead of leaving you with silence.

## Can I watch for a reply to a mail shown on the dashboard?

Yes. In the **More actions** menu (⋯) of a mail on the **Unread mail** card, **Watch for a reply from …** creates a watch on that sender for the next **two weeks**, without opening the chat. LIA checks your mailbox on its own — there is no schedule to set — and when that person writes back, it tells you and reminds you what the exchange was about.
• The watch follows the **sender**, not the subject, which changes with every "Re:".
• If you already watch that sender, LIA says so instead of creating a second watch.
• It is a routine like the others: you find it under **Settings › Features › Scheduled Actions**, where you can change it or end it early.
• The action is offered only when the mail shows a sender.

## What do the two figures on the Health card mean?

For each metric (steps, heart rate), the Health card shows two values side by side:
• **Today** — today's value so far (the total for steps, the average for heart rate)
• **Avg N d** — the daily average over the last few days; the number of days is set by your administrator

The full charts and statistics live in the **Health data** section of the settings.

## What does the Weather card show?

The current conditions for your location, drawn as an illustrated sky that matches them, with air quality and in-season pollen where the instance offers them, then a strip of the coming days with their minimum and maximum temperatures — how many days is set by your administrator. Day names follow your interface language.
