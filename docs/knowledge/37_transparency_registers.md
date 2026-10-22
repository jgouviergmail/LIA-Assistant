# Registers of Actions, Consultations and Initiatives

## What are the transparency registers, and where do I find them?

They record, automatically, what LIA does for you. Open them from the **Registers** shortcut on the Home page (under **My shortcuts**), or from the **Action journal** button of the Alerts and Activity pages. The **Transparency registers** page has four tabs:
• **Actions** — what LIA did on your behalf: an e-mail sent, an event created, a file deleted, a document generated, a notification sent
• **Consultations** — what LIA looked at to answer you: your e-mails, your calendar, the weather…
• **LIA's own initiative** — what it did and read without being asked
• **Overview** — the same records as charts

Actions and consultations are kept apart on purpose: they count different things and their totals never add up — one exchange can consult five sources and change nothing. Behind them, LIA also records each conversation turn, each model call and any gap in the record itself; you see those in the charts and in the complete extraction.

## What does the "LIA's own initiative" tab show?

What LIA did **without being asked**: its proactive passes, the interests it explored for you, the notifications it sent unprompted. The tab holds two lists, **Actions taken on its own** and **Sources consulted on its own**.

Everything you set in motion stays in **Actions** and **Consultations**: what you typed or said, your reminders, the routines you configured — a routine is your own instruction, deferred — and the sub-agents you delegated to. Opening your Home page briefing counts as your request too.

Why a separate tab? A background pass runs on its own schedule and can far outnumber what you asked for: mixed together, the few lines that matter would be lost. Every line also states its origin: **You asked**, **Scheduled**, **Sub-agent** or **LIA's initiative**.

## Can LIA claim it did something it did not do?

No — by construction, not by promise. An action is written into the register **before** it happens, and marked **Done** only when the service that performed it returned an explicit success. The absence of an error never counts as a success.

**🔎 What you can rely on:**
• a failed action is recorded as **Failed**; one that could not be attempted because a confirmation was missing, as **Refused**
• an action you confirmed and that was already performed is **never performed twice**: LIA hands back the result recorded the first time
• if an action you must confirm cannot be recorded, it is **not performed**; any other action goes ahead and the missing line is counted in **Gaps in the record**
• a notification is an action too: recorded before it leaves, marked done only when its delivery reported success

The other states — **In progress**, **Interrupted**, **Interaction requested** — say exactly where an action stopped.

## What exactly is kept about a consultation or an action?

**👁️ A consultation:** the capability and its domain (Emails, Calendar, Weather…), when, how long it took, whether it **Answered** or gave **No answer**, and who set it in motion. **Never what was searched for**: "consulted your e-mails" is a record, "searched your e-mails for Marie" would be a second copy of your data. Identical consultations in a row are shown as one line with a count (×3).

Not counted as consultations: an answer served from cache — your mailbox was never opened — and a Home page section you hid. A source that refused shows **No answer**, never a silent success.

**✋ An action:** a short description in your language (for example: Sent an email to Marie), its outcome, when, who set it in motion and, when you had to confirm, which kind of confirmation you gave — shown in the exports. The description and the service's reply, kept so a confirmed action is never performed twice, are stored encrypted. Neither register copies the words of your request.

## What do the charts of the Overview tab show?

Ten charts over your whole history, computed on the server from the records themselves — nothing is counted in your browser:
• **Activity per day**, in conversation turns
• **How turns ended** and **Execution mode** (Pipeline or ReAct)
• **Actions by outcome** and **Consultations by domain**
• **Average latency per tool**
• **Calls per model** — the model that actually answered, not the one configured today — **Calls per graph step** and **Tokens per model**
• **Gaps in the record**, a chart meant to stay empty

Each chart shows the **exact total** beside its bars, including what was folded into "Other", so you can check that they add up. A chart of averages is labelled "Average", never "Total". Sub-agents and external MCP servers are grouped under one word, because their names are not LIA's to publish.

## How do I export my registers, and what does each file contain?

**📄 One register at a time:** the **Actions** and **Consultations** tabs each offer three downloads of the whole register, LIA's initiative included:
• **Export (readable)** — a document to read, with your own wordings
• **Export (CSV)** — a spreadsheet to count
• **Technical** — JSON Lines: the same events with no content at all and pseudonymised identifiers

**🗂️ Everything in one file:** below the tabs, **Unified extraction** gathers the five records LIA keeps about you — turns, actions, consultations, model calls and gaps in the record — one line per record. It follows the same contract as an administrator's extraction, limited to your account by construction: no content, and every identifier, yours included, replaced by a handle. You can attach it to a portability request, a complaint or a bug report without editing it first.

**✅ Complete:** no export is cut short; its header states the exact count and the moment it was taken.

## How long are the registers kept, and can I delete them?

They are kept as long as your account — there is no automatic purge — and they leave with your account archive (**Settings › Preferences › Security › Data export**), together with a short sealing statement when sealing is on.

**🗑️ No "clear" button:** a record you could erase at will would prove nothing. Deleting or resetting a conversation removes its words, not the register lines: the turn stays as a dated line that no longer points at any text.

**🔚 Deleting your account** removes the registers, their seal and the record of gaps. One technical record remains, kept for billing disputes: the line of each model call — model, provider, settings sent, tokens and cost — with no content and no request.

## Can I check that my registers were not altered?

Yes, when your administrator has switched **sealing** on — it is off unless they do. Each account then has its own chain of cryptographic fingerprints, and a card above the tabs says how far your registers are sealed and how many lines are not sealed yet. **Verify integrity** recomputes the sealed lines and answers **Intact**, or names where a break was found — report a break to your administrator. Note the **final fingerprint** it shows: comparing it later reveals even a rewrite made directly in the database.

**✅ What it proves:** a sealed line has not changed since it was sealed.

**⚠️ What it does not:**
• that a line was true when written — the recording rules answer for that, not cryptography
• anything about lines not sealed yet: sealing runs shortly after the fact, and the card counts them
• what older lines looked like before sealing was switched on: they are vouched for only as they stood at that moment
• a complete rewrite of the chain, unless you compare with a fingerprint you noted earlier

When sealing is off, the card says so: your registers stay complete and readable; only the proof is missing.

## Why does LIA keep these registers?

Because an assistant that acts on your accounts should be able to tell you what it did, and what it looked at to do it — from a record, not from memory.

The recording is **automatic**: every capability that can act or read passes through the register by construction, whatever the route — the chat, Telegram, a routine, a sub-agent, a background pass, a voice session — so nothing depends on someone remembering to log it.

[Article 12 of the European AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) sets record-keeping requirements for high-risk AI systems; it does not by itself make this personal assistant high-risk. LIA's registers are a deliberate transparency measure — not a certification, nor a claim that every obligation of that article applies to every installation.

## Can I ask LIA what it did, and how reliable is the answer?

Yes. LIA reads the same **Actions** and **Consultations** registers and answers with **exact totals**, even when it lists only the most recent lines:
• *What did you do for me this week?*
• *What did you do on your own since Monday?*
• *Did you send the email to Marie yesterday?*
• *Which of your actions failed this month?*

It can narrow by period, by who set the action in motion — you, or LIA on its own, exactly as the tabs separate them — and by outcome. Without a period, it covers the last few days. Each action is worded from the description recorded at the time, in your language, so the answer cannot drift from the screen.

It does not read the turns, the model calls or the Activity page: for those, open the registers or the activity timeline.
