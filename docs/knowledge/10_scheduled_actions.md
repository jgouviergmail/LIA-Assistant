# Scheduled Actions

## What is a scheduled action?
A scheduled action is a **recurring task** executed automatically by LIA:

**📋 Principle:**
• You define a **title**, an **instruction** and a **schedule**
• LIA executes the instruction automatically on chosen days and times
• Results appear in your conversation + push notification

**📌 Examples:**
• "*Search today's weather*" — every day at 8am
• "*Search the latest 5 AI news*" — Mon, Wed, Fri at 7:30pm
• "*Show my tasks and appointments for today*" — Sat, Sun at 9am

**🔁 Recurrence:**
Each execution is automatically rescheduled for the next slot.

## How do I create a scheduled action?
Create an action in 4 steps:

**⚙️ Access:**
Settings → "*Scheduled Actions*" section → **Add** button

**📝 Configuration:**
1. **Title**: descriptive name (e.g., "AI Watch")
2. **Instruction**: the prompt sent to LIA (e.g., "Search the latest 5 AI news")
3. **Days**: select days of the week (Mon-Sun buttons)
4. **Time**: choose the execution time

**💡 Tip:**
Be specific in the instruction, as if you were talking to LIA directly.

## How do I test a scheduled action?
You can test an action **immediately** without waiting for the scheduled time:

**▶️ Test button:**
• Click the **Test** button on the action card
• Execution starts in the background
• Results appear in your conversation + push notification

**💡 Usefulness:**
• Verify the instruction produces the expected result
• Adjust the prompt if needed before the first scheduled execution

## How do I read the week view?
Above the list, the **Week view** draws your routines on a grid: hours down, days across (Monday first), in the time zone named beside it.

**🔢 Numbers:**
• Routines are listed by trigger time and numbered in that order; the same number sits on the card and on the grid
• A paused routine keeps its number; creating or rescheduling one renumbers the later ones

**🎨 Colours of this week:**
• White: not executed (not yet due, or nothing ran)
• Green: executed
• Red: failed
• Amber: proposed, waiting for your approval in the chat
• Grey: the routine is paused
• A ring marks a routine whose condition is checked at that time; a routine running right now pulses

**🔁 Reset:**
• The colours cover the current week only and start over every Monday
• Changing a routine's days or time clears its colours: they belong to the old slots
• Pressing **Test** after today's slot recolours that slot; pressing it before does not

**⌨️ Navigation:**
• Click a number on the grid to jump to the routine's card
• The grid is one tab stop: the arrow keys walk it

## What happens in case of error?
LIA handles errors robustly:

**⚠️ On failure:**
• The action is rescheduled for the next slot
• The error message is displayed on the card
• The consecutive failure counter increments

**🛑 Auto-disable:**
• After **5 consecutive failures**, the action is automatically paused
• Status changes to "Error"
• You can re-enable it via the switch after fixing the issue

**🔄 Re-activation:**
• Re-enabling the action resets the counters
• The next trigger time is recalculated

## How many scheduled actions can I create?
You can create up to **20 scheduled actions**:

**📊 Limits:**
• Maximum 20 actions per user
• Each action can target one or more days of the week
• Time is configured to the minute

**⚙️ Management:**
• **Enable/Disable**: inline switch to pause without deleting
• **Edit**: change the title, instruction, days or time
• **Delete**: permanent deletion (past results remain in conversation)

## Are scheduled actions affected by usage limits?
Yes. When your usage limits are reached, scheduled actions are blocked from executing — the system checks your quota before each execution. The action remains scheduled and will resume automatically once your limits are reset (next billing period) or adjusted by your administrator.

## What does the notification contain?
The push notification and the in-app toast carry the **final text of the execution** — the same one archived in your conversation, not an intermediate draft. Rich formatting (HTML layout, data cards, decorative icons) is flattened to plain text before the body is truncated, so a notification never shows markup.


## Can I create automations directly from the chat?
Yes — in one sentence: "give me an AI press review every weekday at 8am". LIA validates the schedule and shows a **confirmation card** (title, days, time, instruction); nothing is created until you confirm. You can also **list** your automations ("what are my automations?") and **pause/resume** one in natural language.

**💡 Bonus:** when you ask the same kind of thing at the same hour on several distinct days, LIA can spontaneously offer: "Want me to turn this into a recurring automation?" (deterministic detection, one suggestion max per month per pattern, off by default — `RECURRENCE_SUGGESTION_ENABLED`).

Deleting an automation remains a Settings action.
