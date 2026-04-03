# Proactive Notifications

## What are proactive notifications?
Proactive notifications allow LIA to **take the initiative** to contact you with useful information:

**🧠 How it works:**
• LIA continuously analyzes multiple data sources (calendar, weather, emails, interests, memories)
• An LLM **intelligently decides** whether there's something useful to tell you
• The message is rewritten with your **personality** and in your **language**

**📌 Examples:**
• "*Rain expected in 45 minutes, don't forget your umbrella*"
• "*You have a meeting at 2pm and rain is forecast — bring an umbrella*"
• "*A topic you're interested in is trending today*"
• "*Based on my observations, you might find this relevant today...*" (journal-informed)

**💡 Philosophy:**
LIA only sends a notification when it is **genuinely useful** — quality over quantity.

## How do I enable proactive notifications?
Enable the feature in just a few clicks:

**⚙️ Access:**
Settings → "*Proactive Notifications*" section → Enable the toggle

**📝 Available options:**
• **Min/max per day**: set the minimum (default: 1) and maximum (default: 3) notifications per day (range: 1-8)
• **Time window**: configure your own start hour (default: 9 AM) and end hour (default: 10 PM) — independent from interest notification hours
• **Push notifications**: enable/disable push (FCM/Telegram) separately

**💡 Silent mode:**
If you disable push, LIA's messages are archived **silently** in conversation + SSE. You'll see them at your next login without being disturbed.

## What data sources are used?
LIA aggregates **10 data sources** in parallel to decide whether to notify you:

**📅 Calendar:**
• Upcoming events (next few hours)
• Requires an active calendar connector (Google Calendar, Apple Calendar, or Microsoft)

**🌤️ Weather + Changes:**
• Current conditions + transition detection (rain starting/stopping, temperature drops, strong wind)
• Requires an OpenWeatherMap connector + configured location

**✅ Tasks:**
• Pending or overdue tasks
• Requires an active tasks connector (Google Tasks or Microsoft To Do)

**📧 Emails:**
• Today's unread emails (urgent, actionable)
• Requires an active email connector (Gmail, Apple, Microsoft)

**⭐ Interests:**
• Trending topics among your active interests

**🧠 Memories:**
• Relevant information extracted from your memories

**📓 Journals:**
• Relevant entries from the assistant's personal journals (self-reflection, observations, learnings)
• Journals are fetched in a **second pass** — LIA builds a dynamic query from the aggregated context (calendar, weather, emails, etc.) to find the most relevant journal entries
• Requires journals to be enabled (Settings > Features > Personal Journals)

**📊 Indicators:**
The Settings section shows a **green badge** for each connected source and a **gray badge** for unavailable sources.

## How often will I receive notifications?
Frequency is **controlled at multiple levels**:

**📊 Your controls:**
• **Min/max per day**: you choose (1-8 range, default min 1 / max 3)
• **Time window**: only during your configured hours (default 9 AM - 10 PM, independent from interest hours)

**🛡️ Automatic safeguards:**
• **Global cooldown**: minimum 2h between 2 proactive notifications
• **Anti-redundancy**: the LLM sees recent notifications and avoids repeating the same topic
• **Cross-type dedup**: interest notifications are also considered (no thematic spam)
• **Activity cooldown**: if you chatted with LIA in the last 15 minutes, no notification will be sent

**💡 In practice:**
You'll receive between 0 and 3 notifications per day, only when relevant. Some days, LIA may decide not to send anything.

**🛡️ Response filtering protection:**
Proactive suggestions (weather alerts, upcoming event reminders, etc.) are protected from being filtered out. When LIA adds proactive data to a response, those items are preserved even if the response filtering considers them unrelated to the original question.

## How do I give feedback on a notification?
Your feedback helps LIA improve:

**👍👎 Feedback buttons:**
• Each notification displays **thumbs up / thumbs down** buttons
• Your feedback is recorded to improve future decisions

**📜 History:**
• View your recent proactive notifications in the dedicated section
• Each entry shows the sources used and priority level

**⚙️ Adjustment:**
• If you receive too many notifications, reduce the daily maximum
• If notifications aren't relevant, disable unwanted sources (disconnect the corresponding connector)

## Are proactive notifications affected by usage limits?
Yes. If your administrator has set usage limits and you have reached any of your quotas (tokens, messages, or cost), proactive notifications are automatically paused until your limits are reset (next billing period) or adjusted by your administrator. This ensures that background LLM usage doesn't exceed your allocated budget.
