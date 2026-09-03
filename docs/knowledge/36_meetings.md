# Meeting Minutes

## How do I record a meeting?
In the chat, open the **+** button next to the message field and choose **Record a meeting**. Your phone or your computer becomes the microphone: LIA asks for it once, then a banner at the top of every page shows the recording, its duration and what has already reached your server. You can keep chatting with LIA in the meantime — spoken answers and the wake word are simply paused so the microphone never hears the assistant.

When the meeting ends, press **Stop** in the banner or in the same menu. LIA transcribes the whole recording, writes the minutes and posts a card in the chat with the title, the summary and an **Open the minutes** button. Every recording also lives on the **Meetings** page of the header, between Relations and Alerts.

**💡 Good to know:** the feature exists only where the administrator has enabled it, and the engine that will transcribe — with its price per hour of audio — is shown before you start.

## What do the minutes contain, and can I change their structure?
The head of the minutes is fixed: date, start and end time in your time zone, duration, place when it is known, and the participants. The body follows **your template**: an ordered list of sections, each with a heading, an instruction for the assistant and a format — a paragraph, a bullet list, one entry per topic, or action items with owner and deadline.

The built-in template gives a summary, the topics discussed, the decisions, the actions, the risks and the open questions. Change it in **Settings › Meetings**: rename, reorder, add or remove sections, and reset to the default in one click. The minutes already written keep the structure they were produced with; **Rebuild** applies your current template to a past meeting from its stored transcript.

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
Yes. On the meeting page you can **edit** every field — title, participant names and roles, each section in its own shape — and **restore** the version the model wrote at any time. **PDF** downloads the minutes as a document; **Email** sends them to your own address through your connected mailbox, and Settings can do that automatically for every meeting.

Every minutes are also indexed in a knowledge space named **Meetings**, created for you the first time. So you can simply ask: “what did we decide about the migration?”, “which actions are due this week?” — the assistant answers from your own meetings, sources cited.

## Does LIA know who said what?
When the engine separates the speakers, each voice gets a stable label — **S1, S2…** — throughout the transcript and the minutes. A **name** appears only when the recording itself establishes it: someone introduces themselves, is addressed by name, or the calendar event overlapping the meeting leaves no doubt. LIA never invents a name; an unnamed speaker stays S2, and you can name them yourself when editing the minutes.

The local engine transcribes without separating voices: the minutes then read like a single account, with the participants it could establish.
