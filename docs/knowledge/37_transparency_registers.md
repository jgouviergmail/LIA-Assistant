# Registers of Actions and Consultations

## What are the registers, and where do I find them?
LIA keeps **two registers** for you, automatically. The **Registers** tile on your dashboard opens them, and they answer two different questions that are never mixed together.

*Actions* — everything LIA did on your behalf: an email sent, an event created, a file deleted, a document generated. Each line carries the outcome, the confirmation you gave when one was asked, and the moment it happened.

*Consultations* — everything LIA looked at in order to answer you. A line names the **capability** it used, in the words of a domain: "your calendar", "your emails", "your notes". It never records what was searched for.

They are separate on purpose: they count different things and their totals never add up. A single turn can consult five sources and change nothing at all.

**💡 Good to know:** a third tab, **Overview**, draws the same records as charts, so you can read the shape of a week before reading its lines.

## Can LIA say it did something it did not do?
No, and that is the point of the design rather than a promise. An action is written into the register **before** it happens, and marked done **only** when the tool that performed it reports an explicit result. A missing error is never read as a success.

Three consequences you can rely on:

- an action that failed is recorded as failed, with its reason;
- an action you confirmed and that was already performed is **not repeated** — LIA serves what the first attempt recorded instead of doing it twice;
- an action that could not be recorded at all is either refused (when it was one you had to confirm) or performed and **counted as a gap**, never silently forgotten.

## What exactly is kept about a consultation?
The capability and its domain, when it happened, how long it took, and whether it answered. Nothing else. "Consulted your emails" is a record; "searched your emails for Marie" would be a second copy of the very data the register exists to make accountable, so it is not written.

The same restraint applies to the actions register: it keeps what was done and to which service, never the body of a message or the contents of a file.

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

Every export states its period and, when there are more lines than one file may carry, says so and keeps the **most recent** window.

## How long is it kept, and can I delete it?
Both registers live as long as your account and are removed with it. They also leave with your account archive, so exporting your data gives you the registers too.

There is no separate "clear my registers" button: a record you can erase at will is not a record. Deleting your account deletes everything, which is the guarantee that matters.

## Is any of it verifiable?
Optionally, and only if your administrator turns it on. When sealing is enabled, both registers are chained per account with cryptographic fingerprints, and a card above the tabs states how much is sealed and up to when. You can trigger the verification yourself and keep the resulting fingerprint to check a copy later.

Sealing runs shortly after the fact rather than instantly — the delay is published on the same card, because a window nobody mentions is a window nobody can account for.

## Why does this exist?
Because an assistant that acts for you should be able to say what it did, and what it looked at to do it. It is also what the European AI Act's Article 12 expects of a system like this: an automatic record over the system's lifetime, covering the period of each use, the data consulted, the people involved in a confirmation, the parameters of each model call, and the situations that presented a risk.

LIA keeps five records in total. Two of them — actions and consultations — are made for you to read. The other three are technical: the turn itself, the parameters actually sent to each model, and the gaps in the record. Administrators can extract all five into a single file.
