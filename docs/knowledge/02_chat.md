# Conversations

## Can I have multiple conversations at the same time?
LIA works with **one active conversation**. This design choice allows:

• A **coherent context**: LIA remembers the entire conversation
• **Natural references**: "*the first email*", "*the previous contact*"
• A **smooth experience**: no need to juggle between windows

**To start fresh:**
Click the **New conversation** button (🗑️ icon). Warning: this deletes the current history.

## How do I reset a conversation?
To clear history and start over:

1. In the chat, find the button with the 🗑️ icon in the header
2. Click it
3. Confirm deletion

**⚠️ Warning:** This action is **irreversible**. All conversation history will be permanently deleted.

**💡 When to reset?**
• When you completely change topics
• If LIA seems confused by previous context
• For privacy reasons

## Are conversations saved?
Yes, your conversations are **automatically saved**:

• **Real-time sync**: each message is recorded instantly
• **Multi-device**: access your conversation from any device
• **Persistence**: find your conversation even after logging out

**📱 Multi-device tip:**
You can start a conversation on your computer and continue on mobile (and vice-versa).

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
