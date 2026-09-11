# Habit learning

## What does LIA learn about my habits?
Two things, and only if you enable it (**Settings → Learn my habits**; the deployment ships with the feature off until the administrator switches it on):

**🧭 Your activity rhythm** — the time windows (2-4 hours) when you are usually active, learned separately for weekdays and weekends.

**🔁 Your recurring requests** — the kinds of things you ask regularly ("every Monday morning, the emails"), with their shape: daily, workdays, weekly — or *intermittent* ("several times a week around 9 am") when the days are too few for a calendar promise but the hour is steady.

Nothing leaves your account: the learning runs on your own instance, from your own activity.

## How does LIA learn my habits — is it AI guessing?
No. Habits are learned by **transparent, deterministic statistics** — never an opaque model:

• The statistical unit is the **day**, never the message (bursts of messages in one evening do not fabricate a habit)
• A time window is only claimed when presence, a 99% confidence bound, split-half consistency and recency ALL hold
• Hysteresis prevents a habit from flickering in and out
• Calibration was measured by simulation (`task habits:calibration:measure`, 300 trials per cell): 0-0.3% false positives on patternless usage; a daily rhythm is recognised in about 14 days, a three-times-a-week one in 21-35 days, a weekly ritual kept 90% of the time in about 42 days; unlearning in about 9 days

A displayed habit is proven, or it does not exist: when your activity has no stable pattern, the panel says so honestly instead of inventing one.

## What does the Habits panel show?
Everything the detectors know:

**📊 Rhythm** — a 24-hour heat map with an hour axis, your active-day percentage, and your detected windows per day class (weekday / weekend)

**⏳ Progress** — a progress bar showing observation days acquired versus required before the first claims, and recurring requests **under observation** with their progress ("3/4 distinct days") before they are confirmed

**🔍 Explanations** — every habit has a "Why this habit?" block showing the real days it was observed and the exact thresholds the detector applied

## Can I correct or delete what LIA learned?
Yes — full control, immediately:

• **Pause** a habit (kept, but not used)
• **Block** it permanently (never relearned — a definitive veto)
• **Delete** one habit or **forget everything** at once
• **Recompute now** relaunches learning over your existing history, immediately and retroactively
• The **master toggle** turns the whole feature off: nothing is recorded, suggested or seeded, and the keys you refused are never proposed again. What was already learned stays readable and editable, switch on or off

**A status holds everywhere.** The proactive notifications, their scheduling and the assistant's context all read the same rows you edit here, so a paused or blocked habit is paused or blocked for real — not only on the panel.

**A learned habit has a life.** A nightly job promotes a new recurring request, refreshes one whose hour shifted, keeps one that still holds and demotes one you stopped — never on doubt, and never for a single silent day. A habit you resume comes back the same day; "Recompute now" does the same on demand.

Each recurring request is shown as what and when — "Search · E-mails — every day ~08:30" — because LIA keeps what you usually ask for, not only the time you ask it.

## How does LIA use my habits?
With restraint, and never beyond your own settings:

• **Context**: responses and the daily briefing can take your rhythm into account
• **Missed routines**: if a locked routine is skipped, LIA may offer to run it, naming the request ("shall I run your usual e-mail review?") — at most once a day, and it goes quiet for that habit after two ignored offers until you make the request again; a paused or blocked habit is never offered
• **Notification timing**: LIA can prefer your usual windows for its proactive notifications — but it **never widens the hour bounds you configured**; if your habits and your settings do not overlap, nothing changes

## Does a conversation reset erase what was learned?
No. Activity is aggregated from several durable sources (including run summaries and the reset history itself), so resetting your conversation does not erase your rhythm. Conversely, "Forget everything" in the Habits panel truly forgets: it also clears the durable activity bank so a recompute cannot resurrect the profile.

## Why does it say "no stable time habit detected"?

Because the statistical bar was not met — and that bar is now **shown**, not
hidden. When nothing is detected, the Habits panel displays the exact
presence threshold required for that day class. It is stricter on weekends:
a full observation window holds far fewer weekend days than weekdays, so the
confidence bound demands more presence before claiming anything. An enforced
constraint is a published constraint — you should never face an unexplained
"no habit".

## What are streaks and milestones?
When habit learning is enabled, LIA tracks how many consecutive days each confirmed habit has been honored — its **streak**.

**🔥 Current streak** — the number of consecutive days the habit held, computed from the same activity ledger the habit was learned from (never guessed).

**🏆 Milestones and record** — reaching 7, 30 or 100 days is highlighted, and your best-ever streak is kept as a record even after a break.

**🤝 Honest by design:** a missed day resets the current streak but never erases the record, and days where LIA had no data are not counted against you. Streaks appear in **Settings → Learn my habits** next to each confirmed habit.

## Does reading LIA count towards the rhythm it learns?
Yes — presence is on by default, and the administrator can switch it off. The rhythm LIA learns used to see only what you *typed*, which under-reads anyone who mostly reads.

**What counts as being there:**
- opening the app (once per hour at most)
- a 👍 or a 👎 on a notification — an explicit act

**What never counts:** a notification LIA *sends* you. Its own activity is not yours, and treating it as such is how an assistant ends up learning from itself.

The same presence is what "last seen" reads, so a proactive pass knows you were there this morning even if you wrote nothing. Everything stays visible and reversible in **Settings › Habits**: the heat map of your hours, the days actually observed, and a single click to pause, block or forget everything. And what it has learned now survives a fresh conversation — the reset clears the conversation, not the learning.

