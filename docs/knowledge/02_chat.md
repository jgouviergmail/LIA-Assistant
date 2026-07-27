# Conversations

## Can I have multiple conversations at the same time?
LIA works with **one active conversation**. This design choice allows:

• A **coherent context**: LIA remembers the entire conversation
• **Natural references**: "*the first email*", "*the previous contact*"
• A **smooth experience**: no need to juggle between windows

**To start fresh:**
Click the **🗑️** button in the chat header. It deletes every message **and every attachment** — AI-generated images included — so export anything you want to keep first.

## How do I reset a conversation?
To clear history and start over:

1. In the chat header, find the **🗑️** button
2. Click it
3. Confirm in the dialog

**⚠️ What is actually deleted:** Every message, **all your attachments — AI-generated images included** — and the context LIA had built from this conversation (`POST /conversations/me/reset` also clears the token summaries, the LangGraph checkpoints and the tool contexts). The action is **irreversible**.

**💡 When to reset?**
• When you completely change topics
• If LIA seems confused by previous context
• When you would rather not leave that history behind

## Are conversations saved?
Yes, your conversations are **automatically saved**:

• **Real-time sync**: each message is recorded instantly
• **Multi-device**: access your conversation from any device
• **Persistence**: find your conversation even after logging out

**📱 Multi-device tip:**
You can start a conversation on your computer and continue on mobile (and vice-versa).

**🗑️ Deleting is a deliberate act:** nothing is removed until you use the 🗑️ button and confirm.

## How do I use line breaks in my messages?
Two keyboard shortcuts to know:

• **Enter** = Send the message
• **Shift + Enter** = New line (line break)

**💡 Practical example:**
To send a structured email, type:

Send an email to John:
Subject: Project meeting
Body:
Hello John,

I confirm our meeting tomorrow.

Best regards

Use Shift+Enter between each line, then Enter to send.

## Does LIA remember the conversation context?
Yes! LIA maintains an **intelligent context** throughout the conversation:

**🔗 Contextual references:**
• "*Show my emails from John*" → finds 3 emails
• "*Reply to the second one*" → LIA knows you're talking about the 2nd email
• "*Add Sophie in CC*" → LIA remembers the draft in progress

**📋 What LIA remembers:**
• Previous search results
• Contacts, emails, events mentioned
• Drafts awaiting approval
• The conversation thread
• **The last item you manipulated, searched for, or referenced** — so demonstratives like "*this one*", "*it*", "*delete it*" always target what you most recently talked about, even across several turns.

**💡 Tip:** Use natural references like "*the first one*", "*Mary's one*", "*tomorrow's appointment*".

**🧭 How the focus follows you (v1.16.5):**
After you search, create, update, or even just mention an item by ordinal ("*the first meeting*"), LIA updates its internal focus to that item. Subsequent references like "*this meeting*" or "*delete it*" target the correct item — no more confusion with something you created earlier in the conversation.

When LIA asks you to validate a modification (meeting, contact, task), the preview is structured in two clear blocks: **Changes** (only the fields that actually change, shown as old → new) and **Full details after update** (the complete post-update snapshot).

**✅ What you approve is what gets executed:**
When you review a draft (email, event…) and ask for changes ("*add a polite closing*", "*sign with my name*"), each revised version appears in its **own chat bubble**, and the content you finally confirm is **exactly the last version displayed** — edits are applied once and never silently re-generated at confirmation time. The same guarantee applies to bulk confirmations: the list of items you approve (optionally refined with a filter like "*keep only this week's*") is exactly the list that gets processed. If your modification request is ambiguous, LIA now shows you its clarification question alongside the re-presented draft. And "sign with my name" uses the first name from your profile — no placeholder, no invented name.

**🎯 It quotes what it read, not what it remembers:**
• When a message needs no tool call, LIA re-anchors on the entities it actually retrieved in the previous turns (an appointment time, a contact, a place) instead of paraphrasing its own earlier wording
• Those entities are age-bounded and never override data fetched for the current message
• If a detail was never retrieved, LIA says so rather than producing a plausible value — an honest "I don't have that" beats a convincing mistake

## Why does LIA sometimes take time to respond?
Response time varies based on your request's complexity:

**⚡ Fast responses (1-3 seconds):**
• Simple conversation questions
• Weather information
• Wikipedia searches

**⏱️ Medium responses (3-10 seconds):**
• Searching your emails
• Calendar consultation
• Contact search

**🔄 Longer responses (10-30 seconds):**
• Creating complex emails
• Combined multiple searches
• Actions requiring multiple steps

**💡 Visual indicators:**
During processing, you see each step in real time as it happens. Steps accumulate vertically:
• *🔮 Consultation de la boule de cristal...* (random fun phrase during initial analysis)
• *📋 Planning actions...*
• *✅ Validating plan...*
• *📅 Retrieving events...*
• *🌤️ Fetching weather...*

The first step shows a random witty phrase for a touch of personality, while subsequent steps display descriptive progress labels. Steps accumulate as the pipeline progresses — routing, planning, validation, tool execution — then disappear when the response starts streaming. In ReAct mode, you also see which specific tool is being called and a snippet of LIA's reasoning.

The display itself is alive: past steps dim while the current one gently pulses, a caret blinks at the end of the text while the answer streams, and the "typing" animation changes shape from one response to the next. If you switch to another tab while LIA works, the tab title alternates with "✦ LIA is writing…" so you know when to come back. All of it respects your system's reduced-motion preference.

On an empty conversation, LIA greets you according to the time of day — ☕ in the morning, 👋 during the day, 🌛 in the evening, and 😴 at night while it consolidates its memories. And on the other dashboard pages, a small floating companion keeps LIA present: it rests as the current mood, starts "thinking" when a background run is working, and shows a badge when notifications are waiting — click it to jump back to the chat.

## How do I get better results with LIA?
Here are the **best practices** for communicating with LIA:

**✅ Be specific:**
❌ "*Find an email*"
✅ "*Find emails from Peter about the budget*"

**✅ Give context:**
❌ "*Send an email*"
✅ "*Send an email to mary@example.com to confirm the meeting tomorrow at 2pm*"

**✅ Use specific dates:**
❌ "*The meeting the other day*"
✅ "*The meeting on January 15*"

**✅ Proceed step by step:**
For complex tasks, break down into multiple requests.

**✅ Check previews:**
Before approving an email or modification, carefully review the preview.

## How do I attach photos or documents to my messages?
Two ways to attach files:

**📎 Paperclip button:**
Click the **📎** button to the left of the input area to browse your files.

**🖱️ Drag and drop:**
Drag files directly from your file explorer into the input area. A visual outline appears to confirm the drop zone.

**📁 Accepted formats:**
• **Photos** (JPEG, PNG, GIF, WebP, HEIC) — automatically compressed
• **PDF documents** — text is automatically extracted

Thumbnails are displayed in the conversation. Click a thumbnail to enlarge it. LIA can analyze the visual content of images and the text of PDFs to answer your questions.

**💡 Limits**: maximum 5 attachments per message, 10 MB per image, 20 MB per document.

## What is the /resume command?
The **/resume** command triggers **intelligent context compaction**:

**What it does:**
• Summarizes old conversation history using AI
• Preserves critical identifiers (names, emails, IDs)
• Frees up context window space for longer conversations

**When to use it:**
• When your conversation has been going on for a long time
• When LIA seems to lose track of earlier context
• When you want to "reset" the context without losing important information

**How it works:**
1. Type **/resume** in the chat
2. LIA summarizes old messages into a concise recap
3. Recent messages are preserved intact
4. LIA confirms the compaction with a brief summary

**💡 While compaction runs:**
• A **toast** appears at the top of the screen reading *"Summarizing the conversation…"*
• The input area is **locked** automatically while the summary completes
• When done, the toast morphs into a confirmation *"Conversation summarized — N tokens freed"*
• If the summary cannot complete (LLM outage, timeout), an **explicit fallback** cleanly truncates the older history with a visible notice rather than a silent loss

**📊 Persistent indicator:** A discreet pill in the chat header (next to the search box) continuously shows your *tokens/threshold* usage as a coloured ring — you can see at any moment when the next compaction will fire.

**💡 Note:** Compaction also triggers automatically when the conversation becomes very long. The /resume command lets you force it at any time.

## What is ReAct mode?

LIA offers two execution modes, switchable via the **⚡ toggle** in the chat header:

### Pipeline mode (default)
The classic mode: LIA plans all steps upfront, then executes them in parallel. Fast and efficient for well-defined requests.

### ReAct mode (⚡)
The assistant **reasons step by step**: it calls a tool, analyzes the result, then autonomously decides what to do next. This mode is ideal for:
• **Exploratory questions** — "What's happening this weekend?"
• **Complex research** — multi-step queries where the optimal tool sequence isn't known upfront
• **Cross-domain initiative** — after getting weather, the assistant may proactively check your calendar

**Key differences:**
| Aspect | Pipeline | ReAct |
|--------|----------|-------|
| Planning | Upfront plan | Step-by-step reasoning |
| Adaptability | Follows plan | Pivots on tool results |
| Token cost | Lower | Higher (1 LLM call per step) |
| Best for | Structured requests | Exploration, research |

**Your skills and MCP tools** work in both modes. The toggle preference is saved automatically.

**🎯 Precise values, clean turns** — in ReAct mode, each conversation turn starts from a clean slate (data from a previous request never reappears in the next answer), and the assistant fetches exact values from your data before acting: asking for directions to a contact looks up their precise address in your address book rather than settling for an approximation remembered from earlier conversations.

**🛡️ Sensitive actions are confirmed in both modes** — creating, modifying, replying/forwarding or deleting (events, emails, contacts, tasks, files, labels) always shows a confirmation card and is only carried out **after you approve it** (you can also edit or cancel). This is the same protection in Pipeline and ReAct mode — ReAct never performs a mutation silently. Reminders are created instantly, without a confirmation step, in both modes.

## How do I copy a message or code, and are math formulas rendered correctly?

Since v1.16.9, the chat has several useful finishing touches:

**📋 Copy button on messages and code**
- Hover over a LIA reply or a code block → a "Copy" button appears
- Text is copied as-is to your clipboard, with visual confirmation

**🎨 Syntax highlighting on code**
- Code blocks ```python, ```typescript, ```json, ```bash, ```sql... are auto-colored (25 languages)
- Light or dark theme based on your display preferences

**🧮 Math formulas (LaTeX)**
- Formulas are rendered with proper mathematical notation, whatever notation the assistant uses: inline `$E = mc^2$`, centered block `$$a^2 + b^2 = c^2$$`, LaTeX/math code fences, and `\[…\]` / `\(…\)` all render as formulas.
- Dollar amounts (`9$`, `1.50$`) are never mistaken for math and stay literal, even on a line that also contains a real formula.

**📅 Relative dates**
- Today's messages: time only (14:30)
- Yesterday's: "Yesterday 14:30"
- This week: weekday + time (Monday 14:30)
- Beyond: full date

## Can I search through my conversation history?

Yes, since v1.16.9:

**🔍 Search bar in the chat**
- A search input now appears in the chat header (🔍 icon)
- Type a word or phrase → matching messages are filtered instantly
- Search is case-insensitive ("pizza" also finds "Pizza")

**💡 Current limitations**
- Searches through messages currently loaded in the chat — by default the last 50, but you can **load more by scrolling up** (see the next section)
- Accent-sensitive ("reunion" won't find "réunion")
- Click ✕ to clear the search and see all messages again

**🎯 When to use it?**
Find an address, a name, a decision or a detail mentioned earlier in the conversation without scrolling.

## How do I access older messages in a very long conversation?

Since v1.20.14, you can **scroll up in the chat** to reach the beginning of any conversation, even one that has grown to thousands of messages:

**📜 How it works**
- When you open a conversation, the **50 newest messages** are loaded instantly
- **Scroll up** in the chat — as soon as you reach the top, the previous 50 messages load automatically
- A small "*Loading older messages…*" indicator appears briefly at the top during each fetch
- Repeat as needed — you can scroll all the way back to the very first message

**✨ What stays smooth**
- Your reading position is preserved — the viewport stays exactly where you were, the new content slides in above without jumping
- Duplicates are filtered out, so no message ever appears twice

**📌 Good to know**
- Messages are **always preserved in the database** — nothing is ever lost, even after compaction (which only summarises older messages for the AI's working memory, not the displayed history)
- The in-chat search continues to filter on what's currently loaded, so loading more messages also expands the searchable scope
- Returning to the conversation later, switching tabs, or running a scheduled action all reload the newest page from scratch — so you start fresh at the bottom

## What happens if I leave the page while LIA is answering?

Nothing is lost. Since v1.22.0, generation continues **in the background** on the server:

**🔄 Continuity by default**
- Your message and the full answer are saved even if you close the tab, switch apps or lose the connection
- The finished answer is waiting in the conversation when you come back

**📡 Live resume**
- If you return while the answer is still being written, it **resumes live automatically** — the in-progress bubble rebuilds itself and keeps streaming
- This also works with several tabs open

**⏹️ Stopping an in-progress answer**
- While LIA is writing, the send button becomes a **Stop** button
- The partial text is kept and marked "interrupted" ⏸
- Note: actions already performed (a sent email, a created event…) are **not undone**

**📌 Good to know**
- Only one answer runs at a time per conversation: if you try to send another message during a generation, LIA reattaches you to the answer in progress instead of showing an error

## How do I approve or cancel an action LIA proposes?
When LIA is about to do something sensitive (send an email, delete an event, validate a draft…), an **approval card** appears above the input with **Confirm** and **Cancel** buttons — and **Modify** for drafts, which lets you describe the change to make.

**Two ways to answer, always available:**
- One click on the card, or
- A plain reply **by text or voice** as before ("yes, send it" / "no, cancel")

Both work in parallel — the conversation always wins. Once the action is handled, the card disappears and LIA's reply confirms what was done. This works the same way in both Pipeline and ReAct modes.

## Can I see what LIA did to produce an answer?
Yes. Under each answer, a small **"⚙ N steps · X s"** line summarizes the backstage. One click expands it to show what LIA actually did:

- The **routing** (how your message was understood)
- The **tools** it called
- Its **reasoning**, grouped by category

It is the same transparency as the cost shown on every message, extended to the *flow of actions*. The display stays discreet and collapsed by default, so it never clutters the conversation.

Since v1.25.12 this trace is **stored with the message**: you will find it after a reload and on your other devices (the live reasoning stream itself stays ephemeral).

## How do I search my entire conversation history?
Type in the **search field** of the chat header (or tap the 🔍 icon on mobile). The loaded messages filter instantly — accent-insensitive — with the matches **highlighted** in the bubbles and a result counter.

If older history exists, a **"Search entire history"** button queries the server across everything ever said and lists dated results. Clicking one **jumps to that moment** of the conversation, and a banner offers "Back to present" at any time. Sending a new message automatically returns you to the present first.

## What are the 👍/👎 under the responses for?
Two discreet thumbs appear next to the **Copy** button on ordinary responses. Your verdict is **saved with the message** (you will find it on your other devices) and feeds LIA's understanding: it strengthens or weakens the personal observations that shaped that answer. A 👎 unfolds an optional one-line **"what went wrong?"** field, recorded as a correction.

You can change your mind — the latest verdict wins. And LIA **never regenerates** an answer on its own: you stay in charge.


## Can LIA prepare me before talking to someone?
Yes — ask "prepare my call with Marie" and one pass gathers a **360° view**: her contact card, your recent email exchanges, your upcoming shared meetings, and what LIA remembers about her. If a source is unavailable (no calendar connector, for instance), the overview says so honestly instead of guessing.

It also powers the meeting-prep nudge: when a substantial meeting is close, a proactive notification may end with "want me to prepare this meeting for you?".


## What are the "/" slash commands?
Type **/** at the start of an empty message to open the command menu: **/resume** (compact the conversation), **/briefing** (open the dashboard), **/agenda**, **/search**, plus everyday shortcuts — unread emails, weather, weekend weather, tasks, reminders, news — and your dialogue-enabled skills. Filtering understands your language (typing "mété" finds the weather). A command only **pre-fills** the input: nothing is ever sent without you pressing Enter.

## Does my typed message survive a refresh? Can I recall what I sent?
Yes. Your draft is saved per account as you type and restored after a refresh or navigation (it is cleared when you send, and purged at logout). In an empty input, **↑** walks back through your last 10 sent messages and **↓** walks forward to an empty field — like a terminal. Under every answer, an action row offers **copy**, **feedback** (👍/👎) and the **execution details** ("N steps · X s").

## The thread no longer jumps while I re-read — how does it work?
When you scroll up to re-read, a streaming answer **never drags you back to the bottom**. A floating button appears with a counter of the responses that arrived off-screen; one tap brings you back. Sending a message still jumps to it, as expected. Under the latest answer, up to 3 **follow-up suggestions** may appear as chips: tapping one fills the input (never sends).

## A message failed. Do I have to retype my question?

No. A failed turn now carries a **Retry** button, and it replays exactly the
request that failed — not whatever the latest message happens to be when you
press it. That distinction matters: a proactive notification from LIA can land
between your question and your click, and replaying the wrong text would send
something you never asked for.

## The chat is empty. Where do I start?

A brand-new conversation offers three starting points under the greeting. They
were chosen because they work on **any** account — no connector, no memory, no
history required: ask what LIA can do, set a reminder, or have something
explained. Tapping one **fills the composer**; it never sends on your behalf, so
you can edit first.

## Can I use the examples written in the FAQ directly?

Yes. Every bulleted example in the in-app FAQ is a button: one tap drops the
phrase into the chat composer, ready to adjust before you send it. The FAQ holds
several hundred of them, in all six languages.

## On my phone, how do I get from the chat to the settings?

Tap the **LIA logo** at the top left. On narrow screens the navigation bar is
hidden, so the logo opens a menu with the same four destinations — dashboard,
chat, settings, help — and announces which page you are currently on. On a
desktop the logo stays what it has always been: a link back to the dashboard.
