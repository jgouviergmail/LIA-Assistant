# LIA World

<!-- Source: faq.sections.world in apps/web/locales/en/translation.json. -->

## What is LIA World, and how do I enter?

LIA World is a shared isometric house and garden where places lead to LIA’s functions. Open **World** in the menu when your instance offers it. Choose your character, review the displayed LIA account name and accept sharing your name, appearance and coarse presence. Change your name in your LIA profile settings. The operator sets capacity; when full, a queue offers a place for you to confirm. Leaving releases your place and keeps you signed in to LIA.

## How do I move, look around and sit down?

Focus the scene and use arrows, WASD or ZQSD, or click or tap reachable ground. A mobile joystick is available. Drag to explore the camera; use the wheel, pinch or zoom buttons to change scale. The minimap moves the view; recenter follows your character again. Nearby authored seats and resting places offer their available poses. Help explains the controls and lets you adjust graphics quality.

## What can other people see about me?

People in the shared scene see your LIA name, chosen appearance and public movements. Your accepted connections can see a coarse status: in the world, at home, away or offline. Your private home interior, conversation with LIA, memories, documents and personal panels stay outside shared snapshots. Blocking filters visibility and correspondence. Instance operators may have technical access; text sent for translation reaches the configured AI provider under its policies.

## What can I personalise in my home and character?

Choose your character’s skin tone, hair, clothing, colours and accessories at entry or through **My character**. Your saved appearance is visible in shared places. Your home is private: preview its colour palette and save it, or follow your application theme. Saved choices return on your next visit; a concurrent change asks you to reload before saving. This version offers bounded palette choices; home visits and shared furniture editing are unavailable.

## Can I use LIA’s normal functions without leaving the world?

Yes. The places and function directory open the existing LIA panels privately: knowledge spaces, memories, files and kept answers, meetings, workboard, relations, reminders, routines, connectors and extensions, according to your account’s capabilities. Your personal conversation uses the normal workspace, including available attachments and voice controls. Confirmations, permissions, quotas and costs still apply. Administration stays in the ordinary settings. You can return to the usual application at any time.

## How do I talk to LIA, and can I speak to other people?

Call LIA or select the character to open your personal conversation, journals, notifications or psyche. LIA can patrol or follow you; walking the character itself calls no AI model. Dictation, spoken answers and Live sessions use LIA’s existing voice features when available and configured. They connect you to LIA. Communication between human participants in this version uses text; direct human audio is unavailable.

## How do private and public messages work?

Open **Conversations** and choose a person visible in a shared place for a direct message, or the public conversation for a message to its eligible audience present at sending. A public message stays with that audience; later arrivals do not receive its history. Return from home to a shared place before sending. Original and translated text can be viewed, with pending, failed or uncertain delivery shown explicitly. These temporary messages expire after the duration shown in the panel and are not added to LIA’s memory.

## Who pays for message translation?

Sending asks for consent to any translation charge under your LIA quotas. Same-language delivery calls no model; a translation uses the instance’s dedicated translator and shows its available token and cost receipt. A public send groups the required target languages into one translation request. A later translation you explicitly request uses your own quotas. Failure can still consume paid work; an uncertain request offers a status check rather than automatic resending.

## What are the phone, weather and sound controls for?

The compact device panel gives private access to your SMS, reminders, notifications and available calling or radio controls. Proactive notifications can also be offered by LIA without exposing their content to the scene. The weather panel reads your available cached weather; day/night lighting follows your account’s local time, anchored to the server clock. The scene makes no extra weather-provider request. Optional ambience and message sounds have their own controls. Sound and animation do not create a shared microphone or publish your personal data.

## What if the connection drops, another tab takes control or my device struggles?

The server confirms movement and collisions. Losing authority pauses input while the world reconnects; an expired place can require joining again. Another tab must explicitly take control. Changing account closes the old private workspace and asks you to reload with the current account. Help offers graphics quality and performance information; reduced motion limits decorative animation. Keyboard focus can leave the scene normally, and touch controls support phones. Observed performance depends on your device and connection.

## How does an administrator make World available?

The operator enables World in server configuration, then the administrator permits it in **Settings › Administration › Platform capabilities**. The operator also sets capacity and the server limits; the capability switch cannot override a disabled deployment. World reuses native account sessions, Redis-backed presence and saved account preferences. Personal panels keep their own capability gates, while message translation uses its own model slot and the existing usage limits. No administrator panel is exposed inside the shared scene.
