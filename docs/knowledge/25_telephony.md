# Phone Calls

## What can LIA do on the phone?
LIA can place a **real outbound phone call** for you, pursue the goal you set, and report back in the chat.

**Examples:**
• "Call the bakery and ask if they have a cake for Saturday"
• "Call the garage to check if the car is ready"
• "Call Marie and ask if she's free Tuesday evening"

During the call, LIA introduces itself as an assistant calling on your behalf, holds a natural conversation toward your objective, then hangs up and writes you a summary — with a one-tap follow-up action when relevant (for example, creating the event that was just agreed).

**💡 Good to know:** LIA only places **outgoing** calls — it never answers your incoming calls.

## How does a call work, step by step?
**1. You ask in the chat**
"Call Dr. Martin's office and ask for an appointment this week"

**2. LIA asks for your confirmation**
Before dialing anything, LIA shows you a confirmation card: **who** it will call, **which number**, and **why**. Nothing happens without your explicit approval.

**3. The call takes place**
LIA's voice agent makes the call from your number and works toward the objective. You can keep chatting with LIA — or close the app — in the meantime.

**4. The summary arrives in the chat**
A written summary is delivered asynchronously, with a suggested follow-up action when there is something to do next. Every call also appears in your call history (**Settings > Connectors > Telephony**).

## What do I need before starting?
Phone calls use **your own accounts** with two external services — LIA adds no charge of its own:

**1. 📞 A Twilio account** — provides the **phone number** LIA calls from (number rental + per-minute pricing).

**2. 🎙️ An ElevenLabs account** — provides the **voice agent** that speaks during the call (requires access to the Agents platform; call minutes consume your plan's credits).

**3. ✅ The feature enabled by your administrator** — if you don't see a **Telephony** block in **Settings > Connectors**, ask your administrator to enable it.

The full setup takes about **15 minutes** (plus possible validation delays for a French number) and follows 4 steps:
1. Get a phone number (Twilio)
2. Prepare ElevenLabs (API key + number import)
3. Configure the return webhook
4. Activate the connector in LIA

## Step 1 — How do I get a phone number (Twilio)?
Twilio is the operator that provides the number LIA calls from.

**1. Create the account**
Sign up at **twilio.com** and upgrade to a paid account (the free trial only calls verified numbers).

**2. 🇫🇷 For a French number: submit a Regulatory Bundle**
French regulation requires an identity document and a proof of address: **Phone Numbers > Regulatory Compliance > Bundles**. Human validation takes up to ~3 business days.
• Easiest: a **local number (01–05)** or **national number (09)**
• Avoid mobile numbers (06/07): extra requirements and 1–2 weeks of provisioning

**3. Buy the number**
**Phone Numbers > Buy a Number** — make sure the **Voice** capability is checked.

**4. Note your credentials**
On the Twilio Console dashboard, copy the **Account SID** and the **Auth Token** — you will need them in the next step.

**💡 Just testing?** A US number can be bought instantly, with no regulatory bundle.

## Step 2 — How do I prepare ElevenLabs (API key + number)?
ElevenLabs provides the voice agent that speaks during the call.

**1. Check your plan**
You need a plan with access to the **Agents platform**. Call minutes consume your ElevenLabs credits (on top of Twilio's per-minute cost).

**2. Create an API key**
Profile (bottom left) > **API Keys** > create a key. If you restrict its permissions, it needs at least **read/write access to the Agents platform** (LIA creates its agent, lists your numbers, and triggers outbound calls). A full-access key works fine to start — you can restrict it after your first successful call.

**3. Import your Twilio number**
**Agents Platform > Phone Numbers > Import from Twilio**: enter the number in international format (e.g. +33612345678), the **Account SID**, the **Auth Token**, and a label.

**⚠️ Two important points:**
• Use the **native Twilio import**, not a SIP trunk — LIA triggers calls through ElevenLabs' Twilio integration.
• **Do not create an agent yourself**: LIA automatically provisions its own secured agent when you activate the connector (it will appear in your workspace as "LIA telephony — your name").

## Step 3 — How do I configure the return webhook?
The webhook is the channel through which the call report comes back into your chat. Without it, calls go out but no summary ever returns.

**1. Open the webhooks settings**
In the ElevenLabs **Agents workspace settings**, open the **Webhooks** section (only a workspace admin can do this).

**2. Create a post-call webhook**
• Event type: **post_call_transcription** (transcription only)
• URL: the address LIA shows you at step 3 of its wizard, with a copy button — it looks like `https://your-lia-domain/api/v1/telephony/webhook`
• Authentication: **HMAC**

**3. Copy the signing secret**
ElevenLabs generates a **signing secret** when the webhook is created — copy it immediately, you will paste it into LIA in the next step.

**🔒 Leave "Send audio data" disabled**: LIA never receives nor stores any audio — that is a design guarantee.

## Step 4 — How do I activate the connector in LIA?
Everything now comes together in LIA, in a 3-step wizard.

Go to **Settings > Connectors > Telephony** and click **Connect**. A notice reminds you that calls are billed on your own ElevenLabs/Twilio accounts.

**Step 1 — API key**
Paste your ElevenLabs API key and click **Validate**. LIA checks the key and lists the phone numbers of your workspace. ("No numbers" means the Twilio import from Step 2 is missing.)

**Step 2 — Number**
Pick the number LIA will call from.

**Step 3 — Webhook**
Copy the displayed webhook URL (if you haven't configured it in ElevenLabs yet, do it now), paste the **signing secret**, and click **Activate**.

LIA then creates its secured agent in your ElevenLabs workspace and the connector goes **active**. You're ready to call! 🎉

## How do I place my first call?
**💡 Recommended first test:** have LIA call **your own mobile** — you'll experience a call from the other side.

**1.** In the chat: "Call +336XXXXXXXX and ask whether the package has arrived"

**2.** LIA shows the confirmation card (callee, number, objective) — **confirm**.

**3.** Your phone rings: the agent introduces itself as an assistant calling on your behalf, asks its question, and hangs up.

**4.** The summary appears in the chat a few moments later — asynchronously, so you can chat in the meantime.

You can also target a **contact by name** ("call Marie…"): LIA looks up the number in your contacts and asks you to disambiguate if several match. The call history lives in **Settings > Connectors > Telephony**.

## Is telephony private? Can LIA reveal my calendar or record the call?
Privacy is enforced **by design**, not by instructions:

• **🔒 Read-only, free/busy only** — during a call LIA can check whether you're free or busy at a given time, but **never** reveals your event titles, participants, locations or any content. The call agent simply has no access to that data.
• **🚫 No recording** — the call is not recorded.
• **🗑️ No stored transcript** — the full conversation is never saved; only a short summary is kept, and it expires automatically (30 days by default).
• **📢 Transparent disclosure** — the agent always introduces itself as an assistant calling on your behalf; it never pretends to be you.
• **✅ You stay in control** — every call is confirmed by you before it is placed.

## Can the assistant accept an extra or commit to an expense for me?
No, never. The assistant operates under a **strict mandate**: it can only act within the exact scope of your request. If the person offers an extra, an option, a price change or any unplanned commitment (even a small one, like a 3€ cheese topping on a pizza), it neither accepts nor declines on your behalf: it **notes the exact offer and its price**, explains that it cannot confirm by itself, and announces a call-back to confirm. You then find everything in the call summary — every cost with its amount, every open point — and LIA asks you how to proceed. If you wish, just request a new call with your instructions ("call back and accept the cheese topping").

## How much do phone calls cost?
LIA adds **no charge of its own** — costs go to your two external accounts:

**📞 Twilio**
• Number rental: ~1–15 €/month depending on the type
• Outbound minutes: per-minute rate based on the destination

**🎙️ ElevenLabs**
• Agent call minutes, taken from your plan's credits

**🤖 LIA**
• No surcharge, no markup — only the small LLM synthesis of your summary appears in your LIA usage statistics.

**🛡️ Built-in guardrails against surprises:**
• One active call at a time
• Hourly call cap per user (10/hour by default)
• Hard cap on call duration (10 minutes by default)

## Telephony doesn't work — what should I check?
**"Invalid key" at step 1**
→ The key is mistyped or lacks permissions (Agents platform access required).

**"No numbers" after validating the key**
→ Your number isn't imported into the ElevenLabs **Agents** workspace, or was imported as a SIP trunk instead of the native Twilio integration.

**The call goes out but no summary comes back**
→ The webhook is the issue: URL not publicly reachable, wrong signing secret, or wrong event type (it must be **post_call_transcription**).

**"A call is already in progress"**
→ Only one active call at a time, by design. A stuck call is automatically cleaned up after ~15 minutes.

**Calls refused after several in a row**
→ You've hit the hourly cap (10 calls/hour by default).

**Still stuck?** Ask your administrator: the server logs state precisely which webhook events were received and why any were ignored.
