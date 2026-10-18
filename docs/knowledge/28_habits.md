# Habit learning

## What does LIA learn about my habits?

Two things, from your own activity:

**🧭 Your activity rhythm** — the time windows of a few hours when you are usually active, learned separately for weekdays and weekends.

**🔁 Your recurring requests** — what you ask regularly and when, such as "Search · E-mails — every day ~08:30": every day, Mon–Fri, every week on a given day, or *several times a week* when the days vary but the hour holds.

**📥 What counts:** the messages you write — in the app or on Telegram — your app openings and your thumbs on notifications. The routines LIA runs on schedule and the notifications it sends never count: its own activity is not yours.

When your administrator has enabled the feature, it appears in **Settings › Features › Habits**, where the **Learn my habits** switch — on by default — lets you turn it off. The profile is recomputed every night on your instance, by plain statistics: no AI model is called.

## How does LIA learn my habits — is it AI guessing?

No. Habits come from **transparent statistics**, never from an opaque model:

• the unit is the **day**, never the message — a burst of messages one evening does not make a habit
• a time window is claimed only when presence, a cautious confidence bound, consistency between the two halves of the period and recent activity all hold
• a recurring request needs enough distinct days and a steady hour before it is confirmed
• older days weigh less, so a habit you drop fades, and a safety margin keeps a habit from flickering in and out

**🤝 Honest when nothing is there:** the panel says "still learning" with a progress bar, "occasional usage", "active throughout the day" or "no stable time habit detected" — and in that last case it shows the exact bar not yet met. Weekends need more presence than weekdays, because a period holds fewer of them.

## Does reading LIA count towards the rhythm it learns?

Yes — presence is on by default, and your administrator can switch it off. The rhythm counts more than what you *type*, which would under-read anyone who mostly reads.

**What counts as being there:**
• opening the app (once per hour at most)
• a 👍 or a 👎 on a notification — an explicit act

**What never counts:** a notification LIA *sends* you. Its own activity is not yours, and treating it as such is how an assistant ends up learning from itself.

The same presence is what "last seen" reads, so a proactive pass knows you were there this morning even if you wrote nothing. Everything stays visible and reversible in **Settings › Features › Habits**: the heat map of your hours, the days actually observed, and the actions to pause, block or forget.

## What does the Habits panel show?

Everything the detectors know, in three blocks:

• **Learned habits** — each habit as what and when, its status (Active, Paused, Blocked), how many times you confirmed or declined it on a notification, and a **Why this habit?** block listing the real days it was observed and the thresholds applied
• **Activity rhythm** — for weekdays and weekends, your windows or an honest verdict, a 24-hour heat map, when it was last computed and your share of active days
• **Under observation** — recurring requests not confirmed yet, with their progress ("3/4 distinct days", then "regularity being confirmed"); some are marked "rebuilt from history"

Above them, your streak when one is running; below, **Recalculate** and **Forget everything**. A newly detected habit also appears in your **Activity** timeline.

## How do I control what LIA learned about my habits?

In **Settings › Features › Habits**. Every learned habit is a row that says what and when — "Search · E-mails — every day ~08:30" for a recurring request, a time slot for your active hours — with its menu:

• **Pause** — kept, but not used until you choose **Resume**
• **Never relearn** — marked Blocked: never used, suggested or relearned while the row stays
• **Delete** — forgotten; it may be learned again if the pattern comes back, and deleting a blocked habit lifts its veto

**A status holds everywhere:** the proactive notifications, their timing and the assistant's context all read the same rows, so a paused habit is paused for real.

**Life of a habit:** a nightly pass confirms a new recurring request, refreshes one that shifted and drops one you stopped — never on doubt. **Recalculate** does the same on demand.

**Learn my habits**, at the top, closes every door at once: off, nothing is recorded, used or suggested, and the panel folds to the switch. Nothing is erased — switch it back on to find your habits again. LIA can also answer in the chat; a status change, a deletion or a recalculation asks your confirmation first.
• *Show my learned habits*

## How does LIA use my habits?

With restraint, and only active habits — never a paused or blocked one:

• **In its answers and your briefing**, LIA knows your usual hours. At an hour unusual for you it may adapt the format, and after an absence unusual *for you* — measured against your own rhythm — it may greet you and offer a short catch-up
• **Missed routines**: when a usual request has not been made, a proactive notification may offer to run it — see "Can LIA offer to run a request I usually make and forgot today?" in the proactive notifications help
• **Notification timing**, where your instance enables it: before a proactive or interest notification, LIA may wait for a later moment of the same day that falls in one of your usual windows — but it **never widens the hours you configured**
• **Your portrait** in the journals can draw on your active windows

With learning switched off, none of these uses remains.

## Will LIA suggest automating a request I make regularly?

It can, when your instance offers it. Once a recurring request is confirmed, LIA may add to an answer: "I notice you ask me this kind of thing every day — want me to turn it into a recurring automation?" Say yes and LIA prepares the routine with those settings, which you can adjust; ignore it and nothing happens.

**🤫 Restraint:**
• the same kind of request is not suggested again for a long while
• never for a habit you paused or blocked, and never while learning is off
• never from LIA's own routines, so it cannot offer to automate an automation

Depending on your instance's configuration, the suggestion may only appear in Pipeline mode (🔀). When your instance does not offer it, the Habits panel says so — your recurring requests are still learned.

## Does a conversation reset erase what LIA learned about my habits?

No. A conversation reset clears the conversation, not the learning: your rhythm and your recurring requests are built from durable records that survive it, so nothing has to be relearned.

To truly forget, use **Forget everything** in **Settings › Features › Habits**: it erases every habit — blocked ones included, so their veto goes too — the rhythm profile and the stored activity, so that a recalculation cannot bring the profile back. LIA then starts learning again from scratch, unless you switch learning off. Deleting your account erases it all as well.

## What are streaks and milestones?

When a streak is running, the top of the Habits panel shows how many **days in a row** you have been active with LIA — a message, an app opening or a thumb on a notification — counted from the same activity record your rhythm is learned from.

• **🏆 Milestones**: reaching one shows a badge, and the next one is announced
• **📈 Record**: your longest streak stays as your record after a break
• **🤝 Fair**: today never breaks a streak before the day is over; a whole day without activity ends it, and the banner disappears until a new one starts

A streak is only shown: it never changes what LIA learns. **Forget everything** clears it too.
