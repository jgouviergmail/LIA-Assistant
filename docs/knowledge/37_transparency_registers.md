# Registers of Actions, Consultations and Initiatives

## What are the registers, and where do I find them?
LIA keeps **three registers** for you, automatically. The **Registers** tile on your dashboard opens them, and they answer questions that are never mixed together.

*Actions* — everything LIA did on your behalf: an email sent, an event created, a file deleted, a document generated. Each line carries the outcome, the confirmation you gave when one was asked, and the moment it happened.

*Consultations* — everything LIA looked at in order to answer you. A line names the **capability** it used, in the words of a domain: "your calendar", "your emails", "your notes". It never records what was searched for.

*Turns* — one line per exchange, the spine the other two hang off: it is what lets an action and a consultation be traced back to the moment they belong to.

They are separate on purpose: they count different things and their totals never add up. A single turn can consult five sources and change nothing at all.

**💡 Good to know:** a fourth tab, **Overview**, draws the same records as charts, so you can read the shape of a week before reading its lines.

## What is the "On LIA's own initiative" tab?
It holds what LIA did and read **without being asked**: her morning sweeps, the subjects she explored for you, the notifications she sent unprompted. Everything you triggered — including the routines you configured yourself, since a routine is your own deferred instruction — stays in the two lists above.

The separation is the point. What you asked for and what she decided do not call for the same reading, and merging them would say nothing at all: a list where everything appears is a list nobody can use to ask "what did she do on her own last week?".

## Can LIA say it did something it did not do?
No, and that is the point of the design rather than a promise. An action is written into the register **before** it happens, and marked done **only** when the tool that performed it reports an explicit result. A missing error is never read as a success.

Three consequences you can rely on:

- an action that failed is recorded as failed, with its reason;
- an action you confirmed and that was already performed is **not repeated** — LIA serves what the first attempt recorded instead of doing it twice;
- an action that could not be recorded at all is either refused (when it was one you had to confirm) or performed and **counted as a gap**, never silently forgotten.

The same rule now covers a proactive notification, which is an action like any other: it is claimed before it leaves and settled from what the delivery actually reported.

## What exactly is kept about a consultation?
The capability and its domain, when it happened, how long it took, and whether it answered. Nothing else. "Consulted your emails" is a record; "searched your emails for Marie" would be a second copy of the very data the register exists to make accountable, so it is not written.

The same restraint applies to the actions register: it keeps what was done and to which service, never the body of a message or the contents of a file.

Two things that are deliberately *not* recorded as consultations: a cache hit, because Redis answered and your mailbox was never opened; and a section you hid, because it was never opened either. A source that refused reads as *failed*, never as a silent success.

## What do the charts show?
Ten of them, all computed on the server from the registers themselves — nothing is counted in your browser:

- how your turns ended, and in which execution mode;
- actions by outcome, consultations by domain;
- calls and tokens per model, average latency per tool;
- activity per day over the period;
- any gap in the record itself — a chart that should stay empty.

Each chart carries the **exact total** of the whole period beside its bars, including what the top twelve folded into "other", so the bars can always be checked. A chart of averages says "average", never "total": a sum of averages is not a quantity.

## Can I export them?
Yes, in three formats. **Readable** for a person, **CSV** for a spreadsheet, and the **technical** format — one JSON object per line — which is the same contract an administrator gets. That last one exists so that a file you hand to someone else is complete and needs no explanation from us.

**Nothing is truncated.** Whatever the volume, an export carries every line your filters name; the header states the **exact count** and the instant the extraction was taken, so a file with no upper bound is still given one. When your browser offers to decompress, the download is compressed along the way — the file name does not change, because that is transport and not a different file.

There is a fifth file, below the tabs rather than inside any of them: the **unified extraction**. The three exports above cover one journal each; this one gathers all five records LIA keeps about you — your turns, the actions, the consultations, the model calls and any gap in the record itself — into a single machine-readable file, one line per record.

It is the same file an administrator can produce, narrowed to your account alone: the route it calls takes no account parameter at all, so it can only ever return yours. And it is the same contract, not a lighter version for readers — no content, every identifier replaced by a handle, including yours. That is deliberate: it means you can attach the file to a portability request, a complaint or a bug report without having to edit anything out of it first.

## How long is it kept, and can I delete it?
The registers live as long as your account and are removed with it. They also leave with your account archive, so exporting your data gives you the registers too.

There is no separate "clear my registers" button: a record you can erase at will is not a record. Deleting your account deletes everything, which is the guarantee that matters.

## Is any of it verifiable?
Optionally, and only if your administrator turns it on. When sealing is enabled, the registers are chained per account with cryptographic fingerprints, and a card above the tabs states how much is sealed and up to when. You can trigger the verification yourself and keep the resulting fingerprint to check a copy later.

Sealing runs shortly after the fact rather than instantly — the delay is published on the same card, because a window nobody mentions is a window nobody can account for.

## Why does this exist?
Because an assistant that acts for you should be able to say what it did, and what it looked at to do it. It is also what the European AI Act's Article 12 expects of a system like this: an automatic record over the system's lifetime, covering the period of each use, the data consulted, the people involved in a confirmation, the parameters of each model call, and the situations that presented a risk.

LIA keeps five records in total. Three of them — actions, consultations and turns — are made for you to read. The other two are technical: the parameters actually sent to each model, and the gaps in the record. All five can be extracted into a single file — by an administrator across accounts, and by you for your own.
