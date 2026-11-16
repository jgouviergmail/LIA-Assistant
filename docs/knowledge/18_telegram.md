# Telegram Integration

## How do I link my Telegram account to LIA?

In **Settings › Preferences › Notifications & Communication › Messaging Channels**, click **Link Telegram**. A window gives you two steps:
• **Open the Telegram bot** — its name is shown as a link
• **Send it the command** shown in the window: **/start** followed by your code — the copy button copies the whole command

The bot answers "Account linked successfully!", and the section then shows the channel as **Active**, with your Telegram name.

**🔒 Security:**
• the code works once and expires after a few minutes — a countdown shows it; once it has run out, generate a new one
• after too many wrong codes, the bot stops accepting attempts for a while
• one Telegram account per LIA account, and a Telegram account can be linked to only one LIA account
• linking happens only in the settings: LIA never asks you for a code in the conversation

## What can I do with LIA from Telegram?

Write to the bot as you would in the chat: LIA answers with the same tools — e-mails, calendar, contacts, web search, reminders… — in your language.

**🎙️ Voice notes:**
Send a voice note and LIA transcribes it, then answers as if you had typed it. A note longer than the transcription accepts is refused with a message giving the **maximum duration in seconds** — that limit depends on how your administrator set up transcription. If the note cannot be understood, the bot asks you to try again or to write.

**📝 Good to know:**
• LIA reads **text, voice notes, photos, documents and shared locations**; stickers and videos are not read, and editing a message you already sent changes nothing
• answers arrive as formatted text, headings, tables and quotes included; visual cards (weather, maps, e-mail cards) are shown in the web app, in the same conversation
• **/help** sums up what the bot can do, **/stop** stops the answer in progress

## How do confirmations and notifications work on Telegram?

**✅ Confirmations:**
When LIA needs your go-ahead — an e-mail to send, an event to create, an action to approve — the question arrives with buttons: **Confirm** / **Cancel**, or **Continue** / **Stop** for a series of items. A question that needs words — which contact you meant, a missing detail — is answered by simply replying. You can also answer a confirmation in words, as in the chat, for instance to ask for a change. A button pressed on a question that is no longer pending answers "This question has expired or was already answered."

**🔔 Notifications:**
What LIA sends you — reminders, the results of your routines, proactive notifications, news about your interests — also reaches Telegram, in full, even when the app is closed. Your notification hours and topics apply exactly as elsewhere, and a copy always stays in the conversation.

## Is a Telegram conversation the same as the one in the web app?

Telegram talks in **Main**: your messages and LIA's answers appear there in the web app once archived, with the cards Telegram cannot show. Side discussions keep their own histories; Telegram does not follow whichever one you have open.

**Same preferences:** language, timezone, personality, execution mode, memory and journals follow your account. A capability you switched off stays off here too.

When LIA asks a question in the Telegram conversation, your next message answers it, as in the chat.

## How do I pause or unlink Telegram?

In **Settings › Preferences › Notifications & Communication › Messaging Channels**:
• the **Enable/disable channel** switch pauses Telegram without unlinking it: nothing is sent there any more, and a message you write to the bot gets a reply saying the channel is disabled and where to turn it back on
• **Unlink** removes the link after a confirmation: you will no longer receive messages or notifications on Telegram. You can link it again at any time with a new code

**💬 Or ask LIA:**
• *Is Telegram linked to my account?*
• *Disable my Telegram channel*

LIA reads the current state and, to change it, prepares a confirmation you approve — nothing changes before. Linking itself stays in the settings, because it needs the code.

## Does the administrator need to enable Telegram?

Yes, in two ways:
• the instance needs its own **Telegram bot**: the administrator creates it with Telegram's @BotFather and gives its token to the instance's configuration (in production, together with the webhook address and its secret)
• the **External channels** capability must be on in **Settings › Administration › Platform capabilities**

When external channels are switched off, Telegram can be neither linked nor used on the instance. Existing links are kept and work again once the capability is back on.

If your LIA account is deactivated, the bot only answers that the account is deactivated and that you should contact your administrator.

## What happens if I write while LIA is still answering?

Your message waits its turn, as in the app: the bot marks it with 👀 and sends it as your next message as soon as LIA has finished — its answer comes back on Telegram.

**⏹️ Stopping the answer in progress:**
Send **/stop** (it is also in the bot's menu): LIA stops the answer being written, as with the app's stop button. When nothing is running, or when what runs cannot be stopped from Telegram (another conversation, a routine), the bot tells you.

**📝 Good to know:**
• if the answer was stopped or failed, your waiting message does not leave by itself: the bot shows it to you with two buttons, **Send** and **Withdraw**
• an answer to a question LIA asked you does not wait — it is the answer: send it again once LIA has finished
• a location or a file sent meanwhile does not wait either: send it again once the answer has arrived

## Can I send photos, files or my location?

Yes.

**📎 Photos and files:**
Send a photo or a document, with a caption saying what you want — or without one. LIA reads it like a file attached in the chat: same formats, same size limits, and an album of several photos is read as one message. A file that cannot be received is refused with the reason (too large, a type LIA does not read, too many files at once). The images and documents LIA makes for you are sent to you as files.

**📍 Location:**
Share your location and LIA uses it for the question you ask — *restaurants nearby*, *the weather here*, a route from where you are. It is kept afterwards only if **Location memory** is on. A place you share is read as that place, not as where you are.

**↩️ Replies:**
Reply to one of the messages of the conversation and LIA knows which one you are talking about.

## Can LIA answer my voice notes out loud?

Yes, when **Spoken replies** are on (in the chat's voice menu): the answer to a voice note arrives as text, then as a voice message. The voice reads the beginning of the answer, as in the chat, without the cards or the addresses of links; the text stays complete.

**📝 Good to know:**
• a typed message gets a written answer only
• a question from LIA (with its buttons) stays written
• the voice counts in your costs like the chat's; when your usage limit is reached, only the written answer arrives
