# Habit learning

## What does LIA learn about my habits?

Two things, from your own activity:

**🧭 Your activity rhythm** — the time windows of a few hours when you are usually active, learned separately for weekdays and weekends.

**🔁 Your recurring needs** — what you keep asking me for, whatever the hour: “Search · Emails — Monday to Friday”, with the number of days you asked and the part of the day you ask most. The hour describes the need, it never conditions it: asking for the weather at 7 am one day and at 1 pm the next is still the same need.

**📥 What counts:** the messages you write — in the app or on Telegram — your app openings and your thumbs on notifications. The routines LIA runs on schedule and the notifications she sends never count: her own activity is not yours.

When your administrator has enabled the feature, it appears in **Settings › Features › Habits**, where the **Learn my habits** switch — on by default — lets you turn it off. Everything is recomputed every night on your instance, by plain statistics: no AI model is called.

## How does LIA learn my habits — is it AI guessing?

No. Habits come from **transparent statistics**, never from an opaque model:

• the unit is the **day**, never the message — a burst of messages one evening does not make a habit
• a time window is claimed only when presence, a cautious confidence bound, consistency between the two halves of the period and recent activity all hold
• a recurring need takes enough distinct days, spread over at least two weeks, and a recent ask — the hour plays no part in the decision
• older days weigh less, so a habit you drop fades, and a safety margin keeps a habit from flickering in and out

**🤝 Honest when nothing is there:** the panel says “still learning” with a progress bar, “occasional usage”, “active throughout the day” or “no stable time habit detected” — and in that last case it shows the exact bar not yet met. Weekends need more presence than weekdays, because a period holds fewer of them.

## Does reading LIA count towards the rhythm it learns?

Yes — presence is on by default, and your administrator can switch it off. The rhythm counts more than what you *type*, which would under-read anyone who mostly reads.

**What counts as being there:**
• opening the app (once per hour at most)
• a 👍 or a 👎 on a notification — an explicit act

**What never counts:** a notification LIA *sends* you. Its own activity is not yours, and treating it as such is how an assistant ends up learning from itself.

The same presence is what "last seen" reads, so a proactive pass knows you were there this morning even if you wrote nothing. Everything stays visible and reversible in **Settings › Features › Habits**: the heat map of your hours, the days actually observed, and the actions to pause, block or forget.

## What does the Habits panel show?

Everything the detectors know, in three blocks:

• **Learned habits** — each habit as what and when (“Weather — Monday to Friday”, then “14 of 22 days of use · mostly in the morning”), its status (Active, Paused, Blocked), how many proposals built on it you accepted or refused, and a **Why this habit?** block listing the real days it was observed and the thresholds applied
• **Activity rhythm** — for weekdays and weekends, your windows or an honest verdict, a 24-hour heat map, when it was last computed and your share of active days
• **Under observation** — needs not confirmed yet, with their progress (“3/4 distinct days”, then “regularity being confirmed”); some are marked “rebuilt from history”

Above them, your streak when one is running; below, **Recalculate** and **Forget everything**. A newly detected habit also appears in your **Activity** timeline.

## How do I control what LIA learned about my habits?

In **Settings › Features › Habits**. Every learned habit is a row that says what and when — “Search · Emails — Monday to Friday” for a recurring need, a time slot for your active hours — with its menu:

• **Pause** — kept, but not used until you choose **Resume**
• **Never relearn** — marked Blocked: never used, proposed or relearned while the row stays
• **Delete** — forgotten; it may be learned again if the need comes back, and deleting a blocked habit lifts its veto

**A status holds everywhere:** the proposals, the timing of proactive notifications and the assistant’s context all read the same rows, so a paused habit is paused for real.

**Life of a habit:** a nightly pass confirms a new need, refreshes one that shifted and drops one you stopped — never on doubt. **Recalculate** does the same on demand.

**Learn my habits**, at the top, closes every door at once: off, nothing is recorded, used or proposed, and the panel folds to the switch. Nothing is erased — switch it back on to find your habits again. LIA can also answer in the chat; a status change, a deletion or a recalculation asks your confirmation first.
• *Show my learned habits*

## How does LIA use my habits?

With restraint, and only active habits — never a paused or blocked one:

• **In her answers and your briefing**, LIA knows your usual hours. At an hour unusual for you she may adapt the format, and after an absence unusual *for you* — measured against your own rhythm — she may greet you and offer a short catch-up
• **Proposals**: from what she learns, LIA proposes — in **Alerts › Proposals**, and at most once a day under one of her chat answers — to automate a need, move a routine, look at a failing routine, adjust your notification hours or connect a source — see “Will LIA suggest automating a request I make regularly?”
• **Notification timing**, where your instance enables it: before a proactive or interest notification, LIA may wait for a later moment of the same day that falls in one of your usual windows — but she **never widens the hours you configured**
• **Your portrait** in the journals can draw on your active windows and your recurring needs

With learning switched off, none of these uses remains.

## Will LIA suggest automating a request I make regularly?

Yes, as a proposal — never by acting on her own. It waits in **Alerts › Proposals**, and LIA may also show it under one of her chat answers, typically when you have just asked for that very thing; the card offers the same three answers. When you ask for the same thing on a good share of your days of use (your weather on 14 of 22 days, say), LIA proposes to have it ready *before* you ask: the routine would be ready at the time you usually start asking — every day, Monday to Friday, or on the day you ask for it each week.

**Three answers:**
• **Create the routine** — LIA creates an ordinary routine, with a title and an instruction in your language, which you edit like any other
• **Later** — the proposal comes back after two weeks if the need is still there
• **Never** — it does not come back; three refusals of the same kind of proposal silence that kind for you

**🤫 Restraint:**
• never for a need one of your routines already reads at a nearby time
• never for a paused or blocked need, nor while learning is off
• never while the source is not connected — LIA then proposes to connect it first
• only for what can be summed up with no parameter to choose: your calendar, your emails, your tasks, the weather, your health data and your text messages
• in the chat, at most one proposal a day under an answer, and the same one at most once a week

If the routine cannot be created — the maximum number of routines reached, for example — nothing is created, the proposal stays open and LIA tells you why.

## Does a conversation reset erase what LIA learned about my habits?

No. A reset clears the conversation, not the learning: your rhythm and your recurring needs are built from durable records that survive it, so nothing has to be relearned.

To truly forget, use **Forget everything** in **Settings › Features › Habits**: it erases every habit — blocked ones included, whose veto goes too — the rhythm profile, the recorded activity and your proposals, refusals included, so a recalculation cannot bring anything back. LIA then starts learning from scratch, unless you switch learning off. Deleting your account erases all of it as well.

## What are streaks and milestones?

When a streak is running, the top of the Habits panel shows how many **days in a row** you have been active with LIA — a message, an app opening or a thumb on a notification — counted from the same activity record your rhythm is learned from.

• **🏆 Milestones**: reaching one shows a badge, and the next one is announced
• **📈 Record**: your longest streak stays as your record after a break
• **🤝 Fair**: today never breaks a streak before the day is over; a whole day without activity ends it, and the banner disappears until a new one starts

A streak is only shown: it never changes what LIA learns. **Forget everything** clears it too.
