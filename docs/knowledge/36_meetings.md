# Meeting Minutes

## How do I record a meeting?
On a computer the recording button sits in the header, on the right; on a phone, open the LIA logo menu and choose **Record a meeting** — the menu button pulses red for as long as the capture is open. Your phone or your computer becomes the microphone: LIA asks for it once, then a banner at the top of every page shows the recording, its duration and what has already reached your server. You can keep chatting with LIA in the meantime — spoken answers and the wake word are simply paused so the microphone never hears the assistant.

When the meeting ends, press **Stop** in the banner or where you started. LIA transcribes the whole recording, writes the minutes and posts a card in the chat with the title, the summary and an **Open the minutes** button. Every recording also lives on the **Meetings** page of the header, between Relations and Alerts.

**💡 Good to know:** the feature exists only where the administrator has enabled it, the engine that will transcribe — with its price per hour of audio — is shown before you start, and the banner lets you pick the minutes format while the meeting runs.

## What do the minutes contain, and who chooses their structure?
The head of the minutes is fixed: date, start and end time in your time zone, duration, place when it is known, and the participants. The body follows a **format**: an ordered list of sections, each with a heading, an instruction for the assistant and a shape — a paragraph, a bullet list, one entry per topic, action items with owner and deadline, or the full transcript rewritten cleanly.

**Thirty built-in formats** ship with LIA, filed by use: meetings and teams, transcripts, conversation analysis, sales and consulting, technical, personal appointments, courses and training. In **Meetings › Minutes templates** you browse them, preview them and add the ones that serve you to your own templates — one at a time or several at once — then adapt them: rename, reorder the sections, rewrite the instructions, decline a template, delete what no longer serves.

**Choose nothing and LIA chooses**: it reads what was said, keeps the matching format, then states it on the meeting with, in one line, the reason for its choice. You can impose a default in **Settings › Meetings**, or the current meeting's format from the banner. Full-transcript formats are never chosen automatically: they are long and priced like a whole meeting.

The model reports only what the transcript supports: a proposal left open is not a decision, a wish is not an action, and every relative date is resolved to a real one.

## Which engine transcribes, and what does it cost?
Your instance walks a chain: the speech engine chosen by your administrator, then ElevenLabs Scribe or OpenAI when a key exists — both separate the speakers — then the local Whisper engine, which costs nothing and needs no key but does not separate voices and takes longer on a small server. If a provider refuses at processing time (a revoked key, a file it cannot take), the next engine takes over instead of failing your meeting.

You choose in **Settings › Meetings** whether LIA may use a remote engine, must stay local, or decides by itself; the engine and its **price per hour of audio** are shown before recording.

What a meeting cost is stated everywhere it appears: on the chat card (when you display costs), on the meeting page and in the list — the transcription and the minutes as two separate amounts, and their total. The amount is counted in your consumption exactly like any other exchange with the assistant. When a model has no price configured, LIA says *not priced* rather than showing zero.

## What happens if my phone locks, the network drops, or I forget to stop?
LIA keeps the screen awake while it records, because every phone mutes a microphone once the app is in the background — keep LIA in front. Audio leaves in small segments as you speak, so a crash or a reload loses at most the last few seconds: on return, the banner offers to **resume** (the recording continues), **finalize** what exists, or **discard**.

Offline, nothing is lost: the segments wait for the connection and leave in order once it is back; the banner warns when a long stretch of audio is still waiting.

Forgot to stop? After a long silence the banner asks whether you are still recording, and a maximum duration finalizes by itself. If some seconds never reached the server, the minutes say so — a gap is stated, never filled in with a guess.

## Where is the audio, who can hear it, and how long is it kept?
Everything stays on **your** server. The audio is stored in segments while you record, assembled once at the end, and sent to the transcription engine you chose — nothing else hears it. By default the audio is **deleted as soon as the minutes exist**; in Settings › Meetings you may keep it for a while (up to the ceiling your administrator set), and it is purged automatically after that.

The transcript rests encrypted in the database and can be shown on the meeting page or deleted separately, keeping the minutes. Deleting a meeting removes its audio, its transcript, its minutes and the document that had been indexed in your knowledge space — nothing outlives it.

## Can I edit the minutes, send them, and ask LIA about my meetings later?
Yes. On the meeting page you can **edit** every field — title, participant names and roles, each section in its own shape — and **restore** the version the model wrote at any time. **PDF** downloads the minutes as a document; **Email** sends them to your account's address from the application's own address — no connected mailbox needed — and Settings can do that automatically for every meeting.

Every minutes are also indexed in a knowledge space named **Meetings**, created for you the first time. So you can simply ask: “what did we decide about the migration?”, “which actions are due this week?” — the assistant answers from your own meetings, sources cited.

The meetings list accepts multiple selection: tick the ones that no longer serve and delete them at once. A meeting still recording or still being processed is left aside, and LIA tells you which one and why.

## Does LIA know who said what?
When the engine separates the speakers, each voice gets a stable label — **S1, S2…** — throughout the transcript and the minutes. A **name** appears only when the recording itself establishes it: someone introduces themselves, is addressed by name, or the calendar event overlapping the meeting leaves no doubt. LIA never invents a name; an unnamed speaker stays S2, and you can name them yourself when editing the minutes.

The local engine transcribes without separating voices: the minutes then read like a single account, with the participants it could establish.

## Can I change the format of minutes already written?
Yes, as long as the transcript is kept. On the meeting page, **Change the format…** offers two outcomes: **replace** the existing minutes, or get **new minutes** from the same meeting. The new ones keep the link to their origin — the original meeting states how many minutes came out of it — and join the knowledge space as a document of their own, with their own cost.

That is what lets you read one meeting two ways: the working minutes on one side, the full cleaned-up transcript on the other, or an analysis format when you want to look at the exchange rather than its conclusions. **Rebuild** stays next to it: it rewrites the minutes with *the same* format, useful right after you changed your sections.

**💡 Good to know:** rewriting costs a new synthesis, billed like the first one, and the dialog says so before you confirm. If you delete the transcript, the minutes stay readable but can no longer be rewritten.
