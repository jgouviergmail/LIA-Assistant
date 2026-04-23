# Today Briefing — the dashboard home page

## What is the Today briefing?

The home page of your dashboard is no longer a static stats display — it's a **daily briefing** that opens with a personalized AI greeting and a 2-3 sentence synthesis ("teleprompter") summarizing what matters today, then renders a grid of 6 operational cards: weather, today's agenda, unread mails, upcoming birthdays, active reminders, and health metrics.

**Design principle**: read-only orchestration of data that already lives in your connectors and local domains. No data is created here, nothing is pushed to your providers. The briefing is a *view* that brings together what you'd otherwise have to check across many places.

## What's on the page?

From top to bottom:

1. **Hero with greeting overlay** — The LIA avatar fills the hero card; on top of it, a single AI-generated sentence in your language and tuned to the time of day ("Bonjour Jean", "Good evening", etc.), informed by what the cards contain. While the LLM call is in flight (1-3 s), a static localized tagline is shown so the area is never empty. The exact tokens + EUR cost of the greeting call are displayed discreetly underneath.
2. **Quick Access** — Two compact tiles (Help + Settings).
3. **Mon dashboard** (with a sunrise icon 🌅) — Section title. Above the card grid, a 2-3 sentence **synthesis** from the LLM weaves together what matters across the cards. The synthesis is skipped silently if fewer than 2 cards have data — no LLM call when there's nothing meaningful to say.
4. **Card grid** — 6 cards in a fixed order (Weather, Birthdays, Reminders, Health, Agenda, Mails). Each card has its own status (OK / empty / error / hidden) and its own per-card refresh icon (always visible on mobile, revealed on hover on desktop).
5. **Statistiques d'utilisation** (with a bar chart icon 📊) — Your usage statistics card. Each total counter (messages, tokens, Google API requests, cost) shows the cycle dates AND a small "since DD/MM/YYYY" label below the lifetime total — the reference start of the cumulative figures (your account creation date) is always visible.

## How fresh is the data?

Each card has its own cache TTL adapted to how fast its source actually changes:

| Card | TTL | Notes |
|------|-----|-------|
| Weather | 1 hour | Current conditions + 5-day forecast |
| Agenda | 10 minutes | Today's events from your default calendar |
| Mails | 5 minutes | Today's unread inbox |
| Birthdays | 24 hours | Upcoming birthdays from Google Contacts |
| Reminders | live (no cache) | Local DB lookup is < 10 ms |
| Health | 15 minutes | Today's value + 14-day rolling average |

Beyond the TTL, two refresh options:

- **Per-card refresh** — On desktop, hover any card → click the circular arrow icon top-right. On mobile (where there is no hover), the arrow icon is always visible directly on the card. Only that source is re-fetched and the synthesis is regenerated.
- **Refresh all** — Top-right button above the grid → bypasses every cache and regenerates the whole briefing.

## Why doesn't the page wait for the AI?

The cards arrive **first** (≈ 1 s on warm cache). The greeting and synthesis arrive **second**, in parallel, when the LLM finishes (typically 1-3 s extra). The page is never blocked by the LLM:

- If the LLM call fails for any reason, a static localized greeting is shown instead (`Bonjour Jean.`, `Good morning, Jean.`, etc.) so the page always renders.
- If your dashboard has too few cards with data (fewer than 2), the synthesis is skipped — no LLM cost incurred for a near-empty board.

## What do the tokens / cost numbers next to the timestamp mean?

Each LLM call (greeting + synthesis) shows two things next to the "il y a X min" timestamp:

- **Token count** — total of input + output + cached input tokens used by that specific call.
- **EUR cost** — the actual price computed from the model's pricing × tokens consumed (e.g. `0,000142 €`).

Hover the badge for a tooltip detailing the exact model used (`gpt-4.1-nano` by default) and the `IN / OUT / CACHE` breakdown. These same numbers also feed your usual usage statistics — cached input tokens are correctly subtracted before tracking, so a cached prompt is not charged twice.

## Why is a card not showing up?

There are 4 possible card states:

- **OK** — Data is present, card renders normally.
- **Empty** — The connector is configured and reached successfully, but there's nothing to show today (e.g. inbox is clean, no birthdays this week). The card displays a positive empty state ("Tout est calme côté mails ✨").
- **Error** — The connector failed temporarily (expired token, network blip, rate limit). The card shows a CTA to fix it (e.g. "reconnect Google Calendar").
- **Hidden** — The connector is not configured for your account. The card is removed from the grid entirely so you don't see clutter for features you don't use.

Configuring a connector (Settings → Connectors) makes its card appear at the next refresh.

## Health card layout

For each metric (step count, heart rate), the health card shows two values side-by-side:

- **TODAY** — today's accumulated value (sum for steps, average for heart rate)
- **AVG 14J** — average per day over the last 14 days

The vertical separator between the two values is aligned across both metrics so the columns line up — the layout is a fixed 3-column CSS grid (`today | separator | avg`), independent of label widths.

## Weather forecast — 5 days, localized

Below the current conditions, a strip shows the next 5 days (today + 4) with weather icon and min/max. The day abbreviations (`lun`, `mar`, `mer`…) are computed locally in your browser using `Intl.DateTimeFormat` with your active language, so a French user sees `lun. mar. mer.`, an English user sees `Mon Tue Wed`, a Chinese user sees `周一 周二 周三`, etc.
