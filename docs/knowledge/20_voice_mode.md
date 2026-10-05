# Voice Mode

Source: the English application FAQ, Voice Mode section. Question order and answers follow the published help.

## How do I activate voice mode?

A hands-free badge (microphone icon) always sits in the chat header. Greyed, hands-free mode is off: tap it to turn it on — the same switch as Settings > Voice Mode. Once on, tap the badge to start speaking — or, with a French interface, say "Dis LIA" (wake word, in beta); hold it (or hold Space) to turn hands-free mode off.

## How does push-to-talk work?

When voice mode is off and the text field is empty, hold the send button to record your voice. Release to stop — LIA transcribes your speech and places the text in the input field. Works on desktop and mobile.

## Does voice recognition support my language?

Yes! LIA uses Whisper (99+ languages) and automatically transcribes in your preferred language configured in Settings. The wake word itself only exists in French for now ("Dis LIA", in beta: its recognition is still improving); in the other interface languages, tap the badge to speak. The main speech-to-text works in any language.

## Is my voice data sent to external services?

Wake-word detection runs in your browser; the detection model does not upload the audio it listens to. **Local speech-to-text** uses Sherpa-onnx Whisper on the LIA server. Optional **remote STT** sends your recording to ElevenLabs Scribe; it is off by default and requires your choice in Settings → Voice mode.

Other voice paths have their own boundaries: spoken responses can use your configured TTS provider, **Live and Live direct** send the session audio and useful context to the selected voice provider, and an enabled **Simli avatar** receives LIA’s output audio for lip synchronisation. Those services’ processing and retention policies apply. Disabling remote STT does not disable these separate paths.

## Can I use a more accurate (remote) speech-to-text?

Yes. In **Settings -> Voice mode** you can switch from **Local** (default, free, Sherpa-onnx Whisper running on the LIA server, audio never leaves) to **Distant** (ElevenLabs Scribe, $0.22/h, billed by audio duration). The remote mode is more accurate on conversational speech, especially in noisy environments. A discreet 🎤 badge on each user message bubble shows the duration and EUR cost of the transcription. The cost flows into your usual **Cost** dashboard tile and your usage limits - no separate quota. Two safety levers protect against cost spikes: a hard cap of 5 minutes per clip (admin-tunable), and a global kill switch the administrator can flip to force everyone back to local.

## Which voices does LIA use for speech, and what does TTS cost?

LIA's voice synthesis is configured by the administrator from a single catalogue with three providers: **Edge TTS** (Microsoft neural voices, free, default), **OpenAI TTS** (`tts-1` / `tts-1-hd`, premium voices: alloy, echo, nova, ...), and **ElevenLabs** (`eleven_multilingual_v2` / `eleven_turbo_v2_5` / `eleven_flash_v2_5`, including custom and library voices from the configured account). For paid providers, a 🔊 badge on the assistant message shows the character count and the EUR cost; Edge stays free with no badge. Latency-side: a sentence-level streamer starts playing the first sentence in about 1 second, while the assistant is still composing the rest of the answer.

## Does LIA read numbers, prices and addresses correctly?

Yes. A full stop ends a spoken sentence only when a space follows it, so a decimal number, a price, a version number or a web address stays inside a single spoken phrase: "it's 3.5 degrees" is read as one sentence, not as "it's three" followed by "point five degrees" in a separate audio clip.

The rule is the same whether the response is spoken in one go or streamed sentence by sentence, so what you hear does not depend on how fast the answer was generated.

## What is the Live mode, and how do I start a session?

A conversation with LIA **voice to voice, in real time**: you speak, it answers as it listens, you can interrupt it. It runs on a live model you connect with **your own key** — Gemini Live, GPT-Live or an ElevenLabs agent — from **Settings → Connectors** (the « Live » family, additive: you may hold several). Once a connector is active, the voice icon in the chat header becomes a menu: **Live session (brand)** opens one. A band above the thread shows the captions, the time left and an indicative meter; the extension dialog asks before the cap, and after a silence the session goes on standby instead of ending — nothing is billed until it wakes.

**🧠 Two intelligences, one seam:**

the voice holds the conversation; every request for data or action is handed to LIA, which runs it as an ordinary chat turn — the same confirmations, the same registers, the same quotas — drawn in the thread while you speak. A question LIA needs to ask you is what the voice says next.

**📱 On iPhone and iPad:** an ElevenLabs agent goes through its provider's native audio link (WebRTC), which is steadier. If Google refuses the connection because your Gemini Live key is restricted by IP address, LIA tells you: use a key without an IP restriction for this connector.

## « Live session » or « Direct live session » — what is the difference?

**🎧 Live session** — the voice delegates: each thing you ask becomes a chat turn of yours, run by LIA while you speak, with confirmations for anything that acts and every answer drawn in the thread. This is the mode that can DO things.

**🎯 Direct live session** — the voice reads your data itself, without going through the chat: your agenda, mails, contacts, tasks, places, the weather, what LIA remembers — the domains you allow in **Settings → Telephony · My identity**, the same switches as the phone. It acts on nothing: a request is noted, and at the end everything you said is relayed to the conversation as a message from you, which LIA answers. It buys latency, not economy: the tools' declarations are re-billed on every turn by the provider, about nine times the text prompt of a delegated session in our measurement. Offered only where the model's wire carries a tool schema (an ElevenLabs agent does not).

## What does a Live session cost, and who pays?

Two bills, one of which is yours alone.

**🔑 What the provider charges — on your key:**

the live model's audio, in and out, is billed by the provider on your own account. The band shows an **indicative** meter folded from the provider's own usage reports and the tariff your administrator declared, with the context size; a cost that would need an undeclared rate is shown as unavailable, never as a partial figure. On an ElevenLabs agent the platform prices nothing: the clock alone runs, and the provider's own bill is shown once at the end. Nothing of this is recorded anywhere — it is your key. Settings › Live mode lets you set an optional spend ceiling per session.

**💶 What LIA counts:**

what LIA herself spends inside a session — each request you delegated, and in a direct session the lookups and the relayed turn — is counted like any chat message, under your usage limits, and added up on the closing card.

## What does LIA keep of a Live session?

**🎧 In a Live session:**

each request you delegated is a chat turn, kept like any other, and the exchanges that stayed voice-only — small talk, an aside — are archived as two visible lines at the end of each turn, so the conversation reads as it happened; memories and interests learn from them as they would from a typed message. The session closes on one card: how it ended, the duration, the requests, the voice exchanges, LIA's own cost.

**🎯 In a direct session:**

nothing is archived while you speak — the captions live in the band. At the end, what you said is written up and relayed to the conversation as a message from you; the card says « relaying », then is rewritten once LIA answered, with its cost re-read. What the audio was is the provider's and yours: the platform never receives it.

**🧾 In every case:**

the registers record that a session took place and which capability LIA read for you — never a word of what was said.

## What happens when a Live session goes on standby?

After the model's silence timeout, when the page stays hidden, or when you tap the standby button, the session falls asleep instead of ending: the connection to the provider closes, so **nothing is billed** during the standby, but the session stays open — its requests, its meter and its closing card wait for you.

**⏰ Waking it:** tap **Wake up** in the band or, with a French interface, say "Dis LIA" (in beta) while the page is visible. LIA opens a new connection with its own context of the moment — the time, its state, your settings: the memory is the application's, not the provider's. On an iPhone, keep the screen on so that it can hear you.

**🛑 Ending it:** a session only ends on your gesture; an unbroken standby past the length your instance sets (8 hours by default) closes it by itself. The session's cap, its duration and the meter count awake time only, and the closing card says how many times it slept. In a direct session, what you said is relayed into the conversation at each standby.

## How do I cut LIA's voice while it reads an answer?

By voice, with a French interface and hands-free mode on: say **"LIA, stop"** to cut the reading — nothing is recorded or sent to the chat — or **"Dis LIA"** to cut it and speak to LIA at once. Both phrases are detected in your browser, in beta: their recognition is still improving and they do not exist yet in the other languages. A "LIA, stop" said while nothing plays does nothing. In a Live session the provider hears you directly: simply speak to interrupt it.

## Can LIA speak through an avatar, and what does it cost?

Yes, as an **experimental beta**, when your instance enables it. Connect **Simli** in Settings › Connectors using your own account key, stored encrypted, then explicitly enable the speaking avatar and choose a face. Connecting the service alone does not switch it on.

The avatar uses the audio LIA already produces for **voice comments, Live and Live direct**. Its floating window moves by dragging or arrow keys and offers three sizes. Radio keeps its own player. You may need to tap **Enable audio** when your browser asks for a gesture.

**💶 Personal cost:** the active connection consumes your Simli plan even during silence between answers. Live standby closes it; waking starts a new connection. Disable the avatar to close it. This charge belongs to your Simli account, outside the platform's usage limits.

If the avatar is unavailable, the existing text and voice paths remain usable. Speech-driven facial realism and physical Android/iOS behaviour are still being qualified; this beta does not promise identical results on every device.

**Privacy:** enabling it sends LIA's spoken output to Simli to generate the face. It does not send your microphone audio to Simli; the voice provider's own processing still applies.

The “Stop avatar session” button remains available in the window and shows whether closure is confirmed or still pending. If it remains pending, wait and try again; unconfirmed closure is not proof that Simli has stopped billing. The avatar, companion and shortcuts stay within the visible area when the mobile keyboard opens, you rotate the screen or zoom; your preferred position returns afterwards without these adjustments overwriting it.
