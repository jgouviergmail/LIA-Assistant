# Scheduled Actions

## What is a scheduled action?
A routine is a task LIA can run again. In the studio you choose **one trigger**:
a schedule, or a condition. A condition routine has no calendar schedule: LIA
checks its source on the system's cadence, day and night, and runs only when a
new matching fact appears. A check with no match creates no run. You can set a
last day for the watch. The editor shows only the fields of the chosen mode.

A scheduled routine uses the recurrence engine:

**📋 Principle:**
• You define a **title**, an **instruction** and a **schedule**
• LIA executes the instruction automatically on chosen days and times
• Results appear in your conversation + push notification

**🗓️ Schedules you can express:**
• Every day, or every N days — "*every three days at 7:30am*"
• Chosen weekdays — "*Monday and Thursday at 8am*", "*every other Tuesday*"
• Days of the month — "*the 15th*", "*the last day of the month*"
• An nth weekday — "*the 2nd Tuesday of each month*"
• A yearly date — "*every 14 July at 11am*"
• A step inside a window — "*every two hours between 9am and 5pm*"
• An end — "*until 30 September*", or "*the next three times*"

The days are enumerated rather than handed to a cron, so a daylight-saving
change never skips one.

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
• A ring marks a routine that waits for a condition: its dots are the checks that found something new and ran; a routine running right now pulses

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

## What does a routine's notification contain?

When a routine produces an answer, LIA sends a notification to your devices and, if LIA is open, shows it as a short message on screen:
• the **title**: **Scheduled action**, followed by the name of your routine
• the **text**: the beginning of the routine's final answer — the very one saved in your conversation, never an intermediate draft

Formatting (HTML layout, data cards, icons) is turned into plain text before it is shortened, so a notification never shows markup. The complete answer, with its cards, waits in your conversation.

A condition check that found nothing new runs nothing, so it sends nothing either. Notifications on a device need to be allowed in **Settings › Preferences › Notifications & Communication › Push Notifications**.

## Can LIA watch for a reply and tell me as soon as it arrives?

Yes — with a **watch**. On the home page, an e-mail of the **Unread mail** card offers **Watch for a reply from …**: LIA creates a routine that waits for that sender and, when a new message from them arrives, tells you and reminds you what the exchange was about. It lasts two weeks; you can pause it, edit it or move its last day in **Settings › Features › Scheduled Actions**.

**⏱️ How fast:** LIA checks a watch on its own, day and night, at the cadence the editor shows. When your instance receives Gmail push notifications, a matching e-mail brings that check forward to within a couple of minutes.

**🛠️ Your own:** in Scheduled Actions, **Add**, then set **Trigger** to **When a condition is met**, choose **An email matches** and give a filter (subject or sender), with an optional **Watch until**. A check that finds nothing new creates no run.

Asking in the chat creates a routine at set times, not a watch: use the card or the editor.

The action sits in the **More actions** menu (⋯) of the mail and is offered only when the mail shows a sender. The watch follows the **sender**, never the subject; if you already watch that person, LIA says so instead of creating a second watch. A watch stops after its last day and is then *closed*, not left "active" forever: it reads as completed, and you can delete it or set it up again.

## Which events can start a routine, and how do I follow its checks?

In the editor, under **When it runs**, choose **When a condition is met**, then what it waits for:
• **A task is overdue**
• **An email matches**
• **An event is coming up**
• **A document was added**
• **Weather change**

A routine that waits for something has **no schedule at all**.

**🔎 Checked by LIA:** no schedule — LIA checks on its own, day and night, at the pace the editor shows along with the maximum number of runs a day. The routine runs only when something **new** appears: the same e-mail, task or event never starts it twice; something new past the daily maximum waits for the next day. The weather is checked less often than your mail, tasks, calendar and documents. **Watch until** (optional) ends the watch after that day.

**🩺 On the card:** the last check, or why it failed — the source is not set up, or did not answer. **Check now** runs a real check: the routine runs only if something new is there.

A fact found at night is announced at night: there are no quiet hours for routines.

## How does a routine watching for a weather change work?

It always reads **Google Weather**, the weather source your instance provides to every account — whatever weather service you set up for yourself.

**🌦️ What triggers it:**
• Rain, drizzle, snow or a thunderstorm forecast within the next few hours — **4 hours** by default
• With a chance of precipitation **above 50%** by default
• Only for the phenomena ticked in the routine

The editor shows your instance's horizon and threshold under the condition.

**🧭 What LIA is told:** the hour, the day, the chance and the source of the change, so the run knows exactly what to check.

**📅 Once a day per phenomenon:** a second shower the same day does not run the routine again. During the run, LIA reads the weather with your own tools: if your service differs from Google Weather, the answer can say which source saw the change.

## Can I manage scheduled actions through chat?

Yes. Request your scheduled actions or prepare their creation, edit, pause, resumption or deletion among the offered operations. Changes requiring agreement use confirmation tied to the precise routine; private choices stay in the interface. The schedule and register let you check its state and outcome. Waiting for confirmation is not execution, and an old reservation must not consume a new occurrence.

If recurrence suggestions are enabled on your instance, a repeated request may lead LIA to propose a routine. A suggestion creates nothing by itself: review the proposal before confirming.
