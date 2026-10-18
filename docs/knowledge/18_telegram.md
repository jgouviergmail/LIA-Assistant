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
• LIA reads **text and voice notes** only: photos, files and stickers are not read, and editing a message you already sent changes nothing
• answers arrive as formatted text; visual cards (weather, maps, images, e-mail cards) are shown in the web app, in the same conversation
• while LIA is still working on your previous message, a new one gets "I'm still processing your previous message" — send it again once the answer has arrived

## How do confirmations and notifications work on Telegram?

**✅ Confirmations:**
When LIA needs your go-ahead — an e-mail to send, an event to create, an action to approve — the question arrives with buttons: **Confirm** / **Cancel**, or **Continue** / **Stop** for a series of items. A question that needs words — which contact you meant, a missing detail — is answered by simply replying. You can also answer a confirmation in words, as in the chat, for instance to ask for a change. A button pressed on a question that is no longer pending answers "This question has expired or was already answered."

**🔔 Notifications:**
What LIA sends you — reminders, the results of your routines, proactive notifications, news about your interests — also reaches Telegram, in full, even when the app is closed. Your notification hours and topics apply exactly as elsewhere, and a copy always stays in the conversation.

## Is a Telegram conversation the same as the one in the web app?

Yes. Your account has **one conversation**, whichever way you reach it: a message sent from Telegram and LIA's answer also appear in the web chat — an open chat picks them up without being reloaded — together with the cards Telegram cannot show.

**⚙️ Same preferences, everywhere:**
Telegram is not a reduced mode. Your language, timezone and personality apply, and so do long-term memory, LIA's journals and its emotional state — exactly as you set them. What you switched off stays off on Telegram too.

**💡 One consequence:** when LIA is waiting for your answer to a question, your next Telegram message is read as that answer, just as it would be in the chat.

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
