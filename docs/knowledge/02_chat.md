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

**⚠️ What is actually deleted:** Every message, **the attachments you uploaded yourself** — and the context LIA had built from this conversation (`POST /conversations/me/reset` also clears the token summaries, the LangGraph checkpoints and the tool contexts). The action is **irreversible**.

**✅ What is NOT deleted:** **the files LIA produced** — images, documents, browser screenshots — stay in Settings › Preferences › My generated files until their own deadline, or for good if you keep them: a file LIA made for you belongs to you, not to the conversation that happened to produce it. And what LIA learned about you lives outside the conversation and stays — your long-term memory, the rhythm and recurring requests it observed, its mark of which emails it had already read, the thresholds it adjusted for you. Each stored value declares what it is, and a reset only clears what a conversation created (a value whose family is unknown is kept, never guessed). To erase the learning too, use **Forget everything** in the settings, or delete your account.

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

**🧭 How the focus follows you:**
After you search, create, update, or even just mention an item by ordinal ("*the first meeting*"), LIA updates its internal focus to that item. Subsequent references like "*this meeting*" or "*delete it*" target the correct item — no more confusion with something you created earlier in the conversation.

When LIA asks you to validate a modification (meeting, contact, task), the preview is structured in two clear blocks: **Changes** (only the fields that actually change, shown as old → new) and **Full details after update** (the complete post-update snapshot).

**✅ What you approve is what gets executed:**
When you review a draft (email, event…) and ask for changes ("*add a polite closing*", "*sign with my name*"), each revised version appears in its **own chat bubble**, and the content you finally confirm is **exactly the last version displayed** — edits are applied once and never silently re-generated at confirmation time. The same guarantee applies to bulk confirmations: the list of items you approve (optionally refined with a filter like "*keep only this week's*") is exactly the list that gets processed. If your modification request is ambiguous, LIA shows you its clarification question alongside the re-presented draft. And "sign with my name" uses the first name from your profile — no placeholder, no invented name.

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

## What does it mean when LIA says it could not do something?
It means the system **knows** a capability was unavailable and is telling you exactly which one — never a guess.

**What LIA will say:**
• The **specific capability** that could not run (reading your calendar, sending an email…)
• **Why**, at the level that matters to you: not connected, not authorized, a limit reached, a detail missing from the request
• **What would unblock it**, once, calmly — usually a connector to reconnect in Settings

**What LIA will never say:**
• That *nothing* is configured, when only one capability was affected
• That **you** did something wrong — the fault may well be on our side, and from where the answer is written that is indistinguishable
• A made-up result presented as if the step had run

**Partial results are shown as partial.** When one capability fails while another works, LIA presents what it did obtain and names what was missing, instead of announcing a total failure.

**And a refusal is never announced when something did work.** Internally, a plan can be flagged by the validator and still run correctly — the value that bothered the validator is brought back within the allowed range before execution. A failure is reported only when a capability genuinely produced nothing, so a working request is never described as a blocked one.

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
Three ways to attach files:

**📎 Paperclip button:**
Click the **📎** button to the left of the input area to browse your files.

**🖱️ Drag and drop:**
Drag files directly from your file explorer into the input area. A clear landing zone appears over the composer — "Drop your images or PDFs here".

**📋 Paste from the clipboard:**
Press **Ctrl+V** (Cmd+V on Mac) with a screenshot, an image or a PDF in the clipboard: the file is attached through the exact same pipeline as the paperclip (same limits, same preview). Pasting text together with a file keeps both — the text lands in the input while the file uploads.

**📁 Accepted formats:**
• **Photos** (JPEG, PNG, GIF, WebP, HEIC) — automatically compressed
• **PDF documents** — text is automatically extracted

Thumbnails are displayed in the conversation. Click a thumbnail to enlarge it. LIA can analyze the visual content of images and the text of PDFs to answer your questions.

**💡 Limits**: maximum 5 attachments per message, 10 MB per image, 20 MB per document.

**From a knowledge space:** when your knowledge spaces are on, the **+** button becomes a menu: pick **Document from a knowledge space** to attach a copy of a document already indexed — a paused space included (see the next question).

## Can I attach a document from one of my knowledge spaces to a message?

Yes. The **+** button of the composer opens a menu when your knowledge spaces are on: **Attach a file** (the classic picker) and **Document from a knowledge space**.

**What the picker lists:**
- every document already indexed in your spaces — **a paused space included**, named and badged, never hidden
- a search by name, the space beside each document, its size
- a selection bounded by the room left in the message

**What happens when you attach:**
- a **copy** of the document joins the message, exactly like an upload — the space, its index and its file are never touched
- its text is extracted through the knowledge spaces' pipeline (fifteen formats: PDF, Word, Excel, PowerPoint, EPUB…), not only PDF
- a conversation reset removes the copy, never the document of the space

**When to use it:** to ask about one precise document without activating a whole space, or to read a document of a space you keep paused.

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

**📊 Persistent indicator:** A discreet pill in the centre of the chat header (between the hands-free badge and the knowledge-spaces count) continuously shows your *tokens/threshold* usage as a coloured ring — you can see at any moment when the next compaction will fire.

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

**⏱️ Honest time budgets** — a ReAct turn counts thinking time and tool-work time separately, each with its own bound, so a single long delegation (a sub-agent, an iterative MCP task, a browser run) can never consume the whole turn. The deadline is measured on compute time: waiting for your approval never eats into it, and a timeout caused by a slow external tool is attributed to that tool, not reported as the assistant cutting you short.

**🎯 Judged on its result** — in ReAct mode, LIA checks that each result really answers your question — the right day, the right place, a complete list — and treats a result that answers another question as an obstacle, exactly like an error. In front of an obstacle it climbs a short ladder: the same call corrected (an exact date, a wider window, a relaxed search), then another source, which it names as such (« Source: web search (fallback) »). Whatever it still could not obtain is listed at the end of the answer with what it tried, never dropped in silence. When the draft declares such a gap, the loop takes one bounded recovery pass to try the rungs it has not tried yet; a turn with nothing missing takes no pass and costs nothing more. Relative dates — « tomorrow », « next Saturday » — become an exact date before any tool is queried, in every language, and a tool that cannot read a value refuses it instead of silently replacing it.

**🎚️ Your exchange rhythm** — how a ReAct turn prepares its requests is yours to choose, in **Settings › Preferences › Personalization › Usage preferences**. With **frequent exchanges**, LIA keeps every tool at hand, places the turn's context after your question and drops the history by whole blocks of turns, so the provider re-reads the previous turn from its cache at a reduced rate: the first message costs a little more, the next ones much less. With **occasional exchanges**, it picks the tools each question needs, at a cost that does not depend on the gap between two messages. Within one turn, the history the model sees never shifts, however many tools the turn calls.

## How do I copy a message or code, and are math formulas rendered correctly?

The chat has several useful finishing touches:

**📋 Copy button on messages and code**
- Hover over a LIA reply or a code block → a "Copy" button appears
- Text is copied as-is to your clipboard, with visual confirmation

**📤 Share or download an answer**
- Two icons sit next to the Copy button at the bottom of every answer
- **Download** saves it in one click as a dated Markdown file (`lia-YYYY-MM-DD-HH-mm.md`), accents preserved. A formatted answer (rich HTML, cards) keeps its headings, lists, tables, links and code blocks in that file; each card becomes a heading and a few bullets, and what only makes sense on screen — icons, buttons, pictures — stays out. Sending the answer by e-mail and exporting a bookmark write the same Markdown; copying gives plain text
- **Share** hands the raw text to your device's share sheet (Messages, Mail, Notes…) where the browser provides one — dismissing the sheet is not an error. If you have connections, Share opens a menu that lists them as well: picking one fills your message box with a request to relay the answer; you send it, and LIA prepares the message for you to approve, like any message to a connection

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

Yes.

**🔍 Search bar in the chat**
- A search input appears in the chat header (🔍 icon)
- Type a word or phrase → matching messages are filtered instantly
- Search is case-insensitive ("pizza" also finds "Pizza")

**💡 Current limitations**
- Searches through messages currently loaded in the chat — by default the last 50, but you can **load more by scrolling up** (see the next section)
- Accent-sensitive ("reunion" won't find "réunion")
- Click ✕ to clear the search and see all messages again

**🎯 When to use it?**
Find an address, a name, a decision or a detail mentioned earlier in the conversation without scrolling.

## How do I access older messages in a very long conversation?

You can **scroll up in the chat** to reach the beginning of any conversation, even one that has grown to thousands of messages:

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

Nothing is lost. Generation continues **in the background** on the server:

**🔄 Continuity by default**
- Your message and the full answer are saved even if you close the tab, switch apps or lose the connection
- The finished answer is waiting in the conversation when you come back

**📡 Live resume**
- If you return while the answer is still being written, it **resumes live automatically** — the in-progress bubble rebuilds itself and keeps streaming
- This also works with several tabs open
- If your phone suspended the tab and the connection died without saying so, LIA recognises the silence and reconnects on its own: you no longer sit on "Generating the response…" in front of an answer that is already finished and saved

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

If one request produces several drafts, they come one at a time: LIA first lists what it prepared, then shows "Draft 1 of 2" and so on, each with its own buttons. Nothing is sent before you have answered the last one.

## Can I see what LIA did to produce an answer?
Yes. Under each answer, a small **"⚙ N steps · X s"** line summarizes the backstage. One click expands it to show what LIA actually did:

- The **routing** (how your message was understood)
- The **tools** it called
- Its **reasoning**, grouped by category

It is the same transparency as the cost shown on every message, extended to the *flow of actions*. The display stays discreet and collapsed by default, so it never clutters the conversation.

This trace is **stored with the message**: you will find it after a reload and on your other devices (the live reasoning stream itself stays ephemeral).

On a very long turn the panel keeps a bounded number of steps, and it keeps **the first ones as well as the latest**. The count shown is the real total, and the panel says exactly how many intermediate steps are hidden.

Each tool line also says **what the tool did**, in figures only: how many times it was called (×2), how many results it found, how many LIA actually read when it found more than it could read, and how many calls failed. The same figures appear while LIA works and in the stored trace — never the names of the items it read.

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

No. A failed turn carries a **Retry** button, and it replays exactly the
request that failed — not whatever the latest message happens to be when you
press it. That distinction matters: a proactive notification from LIA can land
between your question and your click, and replaying the wrong text would send
something you never asked for.

## The chat is empty. Where do I start?

Under the greeting, LIA offers three ways in. Tapping one **fills the composer** — nothing is sent until you send it yourself, so you can adjust it first.

**☀️ From your day:**
When LIA already knows something about your day — your next event, important e-mails or a commitment it gathered on **Home**, or one of your reminders — the suggestions name it: prepare a meeting, summarise your important e-mails, close a commitment.

**✨ Try one of these:**
Otherwise, or to fill the remaining places, three requests that work on any account, with no connector set up:
• *What can you do?*
• *Remind me to call Jean on Friday at 6pm*
• *Explain quantum computing in simple terms*

Typing **/** in the empty composer opens the command menu, and the examples of the Help page are ready-made requests too.

## Can I use the examples written in the Help page directly?

Yes. In the Help page of the app, every example request written in italics after a bullet is a **button**: a tap or a click opens the chat with that sentence already in the composer, for instance:
• *Show me my reminders for tomorrow*

Nothing is sent by itself: read it, change a name or a date, then send it. The examples work from the keyboard too, and a screen reader announces each one as an example to try.

Only requests addressed to LIA become buttons — ordinary emphasis in an answer stays plain text. On the public help page, before you sign in, the examples are simply text.

## On my phone, how do I get from the chat to the settings?

Tap the **LIA** button at the top left: on a phone, a tablet or a narrow window it carries a small menu icon. The navigation bar does not fit there, so this button opens a menu with every destination — **Home**, **Chat**, **Relations**, **Meetings** (when your instance offers them), **Alerts**, **Settings** and **Help**. The page you are on is highlighted.

Below them come the header's actions that have no room on a small screen: **Record a meeting** and **Start the radio**, when available. While a recording runs, the button pulses red.

On a wider screen the navigation bar is visible, and the LIA logo simply takes you back Home.

## What happens when LIA cannot carry out my request?

LIA drafts a plan before acting, then re-reads it before running it. When that
plan **writes** something — sending an email, creating an appointment, calling
someone — and it cannot repair the plan on its own, it **refuses to run it** and
asks you a question. Writing wrong data costs more than asking.

The question is written in your language and says exactly what is missing: which
recipient, which date, which items to act on. It never contains technical
jargon, a code path or an example address — what LIA shows you is a question,
not its internal diagnosis.

You can answer, rephrase, or drop it: nothing is sent until you decide.

**When a service fails along the way** — a calendar that is unavailable, a page that refuses access —, LIA says so: which tool, what it answered, and what succeeded anyway. It never invents a « service not configured » to fill the gap. A plan that half-succeeded gives you back what worked and names what did not. In ReAct mode LIA first tries another way (a corrected parameter, another source); what it could not obtain is listed at the end of the answer, with what it tried.

## In rich HTML, what does an answer look like?

Like a composed page, not text with tags. As soon as an answer carries data — dates, figures, people, results — LIA lays it out: a **lead sentence** with the key fact in bold, then **one section per facet** in the component that fits it (figures as tiles, statuses as badges, a procedure as steps, a comparison as columns or a table, metadata as a key-value list), and a **closing callout** when there is advice, a caveat or a next step. A greeting or a one-sentence answer stays one line.

The layout follows the answer's own data, never the shape of the conversation's earlier answers. It applies to conversational turns without tools too — unless LIA's voice reads your replies aloud: such a reply stays formatted text, or the voice would read tags; an answer built from tools keeps its layout. Pick **HTML** or **HTML + cards** under **Settings › Preferences › Personalization › Display Mode**.

## What are the little animated eyes on the chat page?

This is LIA’s visual companion. It stays with you on every page of the app, and in the chat it follows real thinking, search, speech and response states. Expressions accompany tone without proving an action completed. Choose its design under **Settings › Features › Identity & Memory › Avatar style**, with previews that animate on hover or focus.

Move the companion, change its size or hide it; controls appear on hover, focus or touch. On a phone it stays where you put it: nothing moves or folds it but you. Style, size and positions are saved in this browser. The landing uses its own BIP presentation, independently of your application choice. The system’s reduced-motion preference retains a quiet pose.

## Do new messages appear by themselves?
Yes. When a message lands in your conversation from elsewhere — another tab or device, Telegram, a voice session, a routine, a reminder — the chat adds it without reloading the page: what is already on screen stays as it is, your selection and open panels included. If you are reading higher up, you are not moved; the round button at the bottom counts what arrived. Nothing changes while an answer is being written: the new messages join once it is done. And if the connection dropped (network, a laptop asleep), the chat catches up when it comes back or when you return to the tab.

## What do the cards in answers show?

Cards show the data received from the source; missing values stay missing. Full detail unfolds with a click or from the keyboard, without another call or cost. Galleries, document previews, slot-by-slot weather and interactive routes keep their own controls and announced charges.

**Reply, forward or delete an e-mail** from its card: LIA prepares a request tied to that exact message and mailbox, then follows the usual confirmation. Changing the active provider cannot target another mailbox.

MCP cards preserve lists and simple values, and show the tool, method and source URL when supplied. Weather icons follow the actual condition and day or night; dates and numbers follow the chosen display format. The model receives the authorised facts, not the card's markup.

Cards at the end of an answer are grouped under one disclosure in Cards and HTML + cards modes. Details remain readable, while confirmations, interactive widgets and messages without text keep their controls.

## How do I know whether an action actually happened?

A prepared request, an awaited confirmation and a recorded change are different states. LIA reports observed results and distinguishes partial results, waiting, conflicts, expiry and failure. If the resource changed after preparation, the command may be refused and need a new request. Delegation to a tool does not by itself prove all its internal effects.

## Why does LIA sometimes read information again?

In ReAct, an exact, complete and still fresh read may be reused within the same request. A change invalidates affected observations; a different request may need a new read. References retain their type and source: a city is not a contact. Dates follow the request context and time zone; weather declares its units rather than guessing a conversion for an unknown value.

Independent reads explicitly eligible for parallel execution can run in checkpointed segments with bounded concurrency. Mutations do not gain that permission merely by appearing nearby in a plan. A stop before checkpoint can still cause a source to be read again; local reuse therefore promises neither one global read nor permanently fresh state.

## Why does LIA say it is already working on this conversation?
A routine, a ticket or the relay of a voice call can make LIA work **on your conversation** while you are elsewhere. The chat shows it: LIA appears busy, and a message you send meanwhile clearly tells you it **was not sent** — nothing is lost silently.

Wait for that work to finish, then send your message again. The stop button never claims to have cancelled work it could not interrupt.

## Can I see all returned places on one map?

When a new answer contains selected Google Places, a **Position** card appears before the place cards, in Cards, HTML cards, HTML and Markdown modes. Each usable location has a marker. The card appears automatically; a click activates the interactive map after its cost is shown. If the administrator has not configured Maps, or the map cannot load, the place list stays available. Old answers are not rewritten.

Each place carries a number, the same in the list and on its pin. Selecting a place, in the list or on the map, shows the details already gathered for the answer — address, rating and number of reviews, phone, website and opening hours — with no new search. The selection also calculates one route to the place: walking for a short distance, otherwise driving. It starts from your current location when your location preference and your browser already allow it (no permission prompt appears), otherwise from your last known location, whose age is shown, otherwise from your home. Each route is a billed Google request, counted in your usage and subject to your quotas; without a starting point, the details stay available. On a phone, the details open in a panel at the bottom of the screen. On a wide enough screen, the list of places sits to the right of the map once the map is switched on.

## Can I bring a kept answer or a generated file back into a discussion?

Yes, as a copy. In the composer, the **+** menu offers **Answer from your bookmarks**
and **File LIA generated**; in **My generated files** — the Bookmarks tab included —
**Use in the discussion** opens the chat with the item already attached. A kept answer
joins as a document (your request, then the answer); a generated image joins as an
image, a document with its text. Nothing is sent until you send your message, and the
original stays where it was — a conversation reset removes the copy only.

