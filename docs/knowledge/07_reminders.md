# Reminders & Notifications

## How do I create a reminder?
Create reminders using **natural language**:

**🔔 Creation examples:**
• "*Remind me to call the doctor in 2 hours*"
• "*Remind me tomorrow at 9am to prepare the meeting*"
• "*Remind me tonight at 8pm to buy bread*"
• "*Remind me Friday at 2:30pm to follow up with the client*"

**📅 Supported date/time formats:**
• Relative time: "*in 30 minutes*", "*in 2 hours*"
• Absolute time: "*at 3pm*", "*at 9:30am*"
• Day: "*tomorrow*", "*next Monday*", "*January 15*"
• Combined: "*tomorrow at 10am*", "*Monday at 2pm*"

**🔁 Recurring reminders:**
A reminder can repeat instead of ringing once:
• "*Remind me every day at 8am to take my medication*"
• "*Remind me every Monday and Thursday at 6pm*"
• "*Remind me on the 15th of each month*"
• "*Remind me every two hours between 9am and 5pm*"
• "*Remind me every morning until 30 September*" — or "*the next three times*"

A repeating reminder re-arms itself after each notification. One with no future
left — a single occurrence, or a series that has run out — is deleted, exactly
as a one-shot reminder always was. Settings → Reminders lists them all, with the
sentence describing their rhythm and the next dates.

**✅ Confirmation:**
LIA confirms creation with the exact date and time in your timezone.

**🛠️ From Tools:**
**Remind me** creates a reminder on a message, an event, a contact, a file or a task.

**💡 Tip:**
Be specific about the reminder content so you easily remember what it's about.

## How do I see my pending reminders?
Check your pending reminders easily:

**📋 View reminder list:**
• "*What are my reminders?*"
• "*Show my pending reminders*"
• "*List my reminders*"
• "*Do I have any scheduled reminders?*"

**📊 Information displayed:**
• Content of each reminder
• Scheduled date and time (in your timezone)
• Numbering for easy reference

**💡 Example display:**
🔔 Your pending reminders:
  1. Call the doctor - 12/28 at 2:00 PM
  2. Prepare the meeting - 12/29 at 9:00 AM

**🔗 Using references:**
After listing your reminders, you can reference them by number: "*Cancel the first one*" or "*Cancel reminder number 2*".

## How do I cancel a reminder?
Several ways to cancel a reminder:

**🗑️ By natural reference:**
• "*Cancel my next reminder*"
• "*Cancel the last reminder*"
• "*Cancel the first reminder*"

**🔢 By number (after listing):**
• "*Cancel reminder number 2*"
• "*Delete the 3rd reminder*"

**📝 By content:**
• "*Cancel the doctor reminder*"
• "*Cancel the reminder about the meeting*"

**✅ Confirmation:**
LIA confirms the cancellation by showing the deleted reminder's content.

**🧹 Bulk cancellation:**
You can also cancel several reminders in a single command:
• "*Cancel all my reminders*"
• "*Cancel my reminders for tomorrow*"
• "*Cancel all reminders about the meeting*"

Before deleting, LIA shows a confirmation panel listing every reminder targeted — each row carries the reminder's content, the day of the week and the trigger time, so you can verify there is no false positive before approving. After approval, the summary recaps every deleted reminder by name and time (no more anonymous "Action completed successfully" lines).

**⚠️ Important:**
• For a repeating reminder, **Stop this reminder** removes its future dates after confirmation
• A message already delivered is not withdrawn
• Cancellation is immediate and permanent

## How do push notifications work?
Push notifications alert you even when the app is closed:

**🔔 How it works:**
• At the scheduled time, you receive a notification on your device
• The notification contains your reminder content
• The message is personalized based on your active LIA personality
• If that personalized sentence cannot be written — or comes back empty — you still receive a plain reminder, never an empty notification
• Works even if the app is closed or in the background

**📱 Supported devices:**
• Web browsers (Chrome, Firefox, Edge, Safari)
• Android (browser and PWA)
• iOS (installed PWA only)

**⚙️ Technology used:**
LIA uses **Firebase Cloud Messaging (FCM)** to send notifications reliably and instantly.

**🌍 Language:**
The notification title and the message body are delivered in your interface language, for all six supported languages.

**⏳ If your usage budget is exhausted:**
A reminder that comes due while your usage limit is reached is not lost — it goes back into the queue and is delivered on a later pass, once you are no longer capped.

**💡 Tip:**
For the best experience, enable notifications in settings and add LIA to your home screen on mobile.

## How do I enable notifications on my device?
Enable notifications in a few steps:

**⚙️ Activation:**
1. Go to **Settings**
2. Find the **Push notifications** section
3. Click **Enable**
4. Your browser asks for permission → Accept

**📱 On mobile (iOS):**
iOS notifications require installing LIA as a PWA:
1. Open LIA in Safari
2. Tap **Share** → **Add to Home Screen**
3. Open the app from your home screen
4. Enable notifications in settings

**🔧 If notifications are blocked:**
You need to re-enable them in your browser settings:
• Chrome: Settings > Privacy > Site Settings > Notifications
• Firefox: Settings > Privacy > Permissions > Notifications

**📋 Device management:**
In settings, you can see all your registered devices and remove them individually.

## What's the difference between reminders and Google Tasks?
Reminders and tasks have different uses:

**🔔 LIA Reminders:**
• **One-time or repeating notification** at the chosen time
• Delivered messages stay in the conversation
• Ideal for: "*Remind me to call John at 3pm*"
• Message personalized with your LIA personality
• Push notification on all your devices
• No state tracking (done/not done)

**✅ Google Tasks:**
• **Persistent task list**
• Remains visible until completion
• Ideal for: "*Add 'Go shopping' to my list*"
• Synced with Google Tasks
• State tracking (to do/completed)
• Organization in lists

**💡 In summary:**
• **Reminder** = "*Notify me at a specific time*" (once or on a schedule)
• **Task** = "*I need to do this*" (list of things to accomplish)

**🔗 Possible combination:**
You can use both: create a task for tracking, and a reminder so you don't forget to do it.


## I stopped receiving notifications after reinstalling the app — why?
A notification permit is tied to **one browser or one installation**. Reinstalling the app, clearing site data or switching device issues a **new permit**, and the old one stops working for good.

• **Re-enable notifications** from Settings on the device you want to be reached on. That registers the new permit.
• **The old device is retired automatically.** A permit the notification service reports as permanently invalid is deactivated on its first definitive refusal, instead of being retried for days.
• **Several devices can be registered at once** — each keeps its own permit, and retiring one does not affect the others.

If notifications still do not arrive on a freshly enabled device, check that your browser has not blocked them at the system level.

## How do I postpone a reminder that just rang?
When a reminder rings, you can push it back in one tap, without writing to LIA:

**⏰ In the conversation:**
• Under the reminder's bubble: **In 10 min**, **In 1 h** or **Tomorrow morning** (9 am by default; in the middle of the night, it is the morning to come)
• The message shown when the reminder arrives also offers the short delay

**📱 Elsewhere:**
• On a computer and on Android, the browser notification offers the two delays
• On Telegram, the same buttons come with the reminder
• On iPhone, the notification opens the conversation, where the bubble offers everything

**🔁 A reminder that repeats:**
• **Stop this reminder** removes all its next times, after a confirmation
• Postponing keeps the series' schedule; a delay that reaches its next occurrence is refused

**⏳ Good to know:**
• A reminder can be postponed for 24 h after it rang
• It is postponed only once, even if you tap on two devices
• A postponed copy still rings even if you later stop the series
• The tap itself costs nothing; the postponed reminder is written when it rings, like any reminder

## How can I receive LIA's notifications without Google, with ntfy?

ntfy is a free, open-source app (Android, iPhone, computer) that receives notifications from a server. In **Settings › Push Notifications › ntfy notifications**, add a subscription: on this LIA's own server if your administrator offers one, or on another ntfy server such as ntfy.sh. Then install the ntfy app and subscribe: scan the QR code, tap “Open in the ntfy app” on Android, or copy the server and the topic on iPhone. Every notification LIA sends you also reaches the ntfy app, and “Send a test” checks the whole route.

## What does an ntfy notification show: just a notice, or the text?

By default, only a notice that LIA has something for you: the server that relays it never sees your words, and you read the message in LIA. You can choose “Full text” for each subscription to read the notification itself on your phone; the server that relays it can then read it, which is why the notice is the default. A notification you keep private in LIA always leaves as a notice, whatever you chose.

## Why do ntfy notifications arrive late on my iPhone?

Apple only lets an app wake instantly through its own push service, and the ntfy app on iPhone receives it through ntfy.sh. A self-hosted ntfy server therefore delivers instantly only if its administrator lets it ask ntfy.sh to wake your phone — a short signal that carries no text. Otherwise the iPhone app checks for new notifications from time to time. Android and computers are not affected.

## Can someone else read my ntfy notifications?

The topic is the key: whoever knows it can read what LIA publishes there. LIA draws topics nobody can guess, shows them to you alone and keeps them encrypted. Do not share yours; if you think it leaked, remove the subscription and add a new one. With “Notice only”, even someone who knew the topic would read nothing but the fact that LIA has something for you.
