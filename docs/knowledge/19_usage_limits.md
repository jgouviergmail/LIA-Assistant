# Usage Limits

## What are usage limits?
Usage limits are **quotas set by your administrator** to control resource consumption:

**3 dimensions:**
- **Tokens** (prompt + response + cache) — volume of data processed by AI
- **Messages** — number of messages sent
- **Cost (EUR)** — combined LLM + API + image generation cost

**2 modes:**
- **Per period** — a monthly rolling cycle anchored on your account creation date, not on the first of the month
- **Global** — a cumulative total since registration, which never resets

Each dimension can be given a value or left unlimited, independently of the others.

## How is the billing period calculated?
The period is a **monthly rolling cycle** aligned with your account creation date.

**Example:** If you registered on January 15th, your cycle runs from the 15th of each month to the 15th of the next. This is the same period shown on the dashboard.

## Am I warned before I hit a limit?

Yes. When you cross **80 %** of whichever limit will bind first, a banner
appears in the chat naming that dimension — tokens, messages or cost — and its
percentage. At **95 %** the same banner takes on a more urgent tone.

The dimension named is the *binding* one, meaning the one closest to its ceiling:
any single dimension blocks the account, so warning about a lower one would point
at the wrong deadline. If the limit is a per-cycle one, the banner also gives the
date it resets. An absolute limit has no reset, and the banner does not pretend
otherwise.

Once you are actually blocked, the warning disappears: the blocking banner
explains the situation better, and two messages about the same limit at the worst
possible moment would be noise.

## What happens when I reach a limit?
When a limit is reached:

**Blocking:**
- Message input and voice are **disabled**
- A **red banner** explains the situation
- **Proactive notifications** and **scheduled actions** are also blocked

**To unblock:**
- Wait for the next cycle (period limits)
- Contact your administrator to adjust your quotas

## Can administrators manually block a user?
Yes. Administrators can **block or unblock** any user instantly via **Settings > Administration > Limits Administration**. A reason can be provided and will be shown to the user. The admin table supports **sorting by Email and Blocked status** for quick management.

## What types of limits can be set?
**3 dimensions × 2 modes = 6 possible limits:**

- **Tokens per period** or **global**
- **Messages per period** or **global**
- **Cost EUR per period** or **global**

Each dimension can be set to a specific value or left **unlimited**.

## Are administrators subject to limits?
Yes, all users including administrators are subject to usage limits. However, administrators can **adjust their own limits** through the admin interface.

## What happens if no limits are configured?
If no limit record exists for a user, they have **unlimited access**. Limits are created either automatically at registration (with default values) or manually by an administrator.

## Where can I see my current usage?
Your usage is visible on the **dashboard** via dedicated tiles:

**Tiles:**
- **Period Limits** — current cycle consumption
- **Global Limits** — total consumption since registration

**Color coding:**
- Green: < 60%
- Yellow: 60-80%
- Orange: 80-95%
- Red: > 95%

## How does limit enforcement work?
LIA uses a **5-layer defense-in-depth** architecture:

1. **Router** — HTTP 429 before streaming
2. **Service** — SSE error for scheduled actions
3. **LLM Guard** — Centralized check before each LLM call
4. **Proactive Runner** — Skip blocked users
5. **Direct call migration** — Full coverage

**Fail-open:** If Redis/DB is down, access is allowed (cost control, not security).

## Can I export my consumption data?
Yes. Go to **Settings > Features > My Consumption Export** to download your personal data as CSV:

- **LLM Token Usage** — detailed per-call breakdown (model, tokens, cost)
- **Google API Usage** — detailed per-call breakdown (API, endpoint, cost)
- **My Summary** — aggregated totals (tokens, calls, costs)

Use date presets (current month, last month, last 30 days) or custom ranges. You can only export your own data — other users' data is never accessible.
