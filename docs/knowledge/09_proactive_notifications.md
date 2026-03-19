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

**💡 Philosophy:**
LIA only sends a notification when it is **genuinely useful** — quality over quantity.

## How do I enable proactive notifications?
Enable the feature in just a few clicks:

**⚙️ Access:**
Settings → "*Proactive Notifications*" section → Enable the toggle

**📝 Available options:**
• **Maximum per day**: choose between 1 and 8 notifications per day (default: 3)
• **Push notifications**: enable/disable push (FCM/Telegram) separately

**💡 Silent mode:**
If you disable push, LIA's messages are archived **silently** in conversation + SSE. You'll see them at your next login without being disturbed.

**⏰ Time windows:**
Time windows are shared with interests (Settings > Interests > Notification hours).

## What data sources are used?
LIA aggregates **9 data sources** in parallel to decide whether to notify you:

**📅 Calendar:**
• Upcoming events (next few hours)
• Requires an active Google Calendar connector

**🌤️ Weather + Changes:**
• Current conditions + transition detection (rain starting/stopping, temperature drops, strong wind)
• Requires an OpenWeatherMap connector + configured location

**✅ Tasks:**
• Pending or overdue tasks (Google Tasks)
• Requires an active Google Tasks connector

**📧 Emails:**
• Today's unread emails (urgent, actionable)
• Requires an active email connector (Gmail, Apple, Microsoft)

**⭐ Interests:**
• Trending topics among your active interests

**🧠 Memories:**
• Relevant information extracted from your memories

**📊 Indicators:**
The Settings section shows a **green badge** for each connected source and a **gray badge** for unavailable sources.

## How often will I receive notifications?
Frequency is **controlled at multiple levels**:

**📊 Your controls:**
• **Maximum per day**: you choose (1-8, default 3)
• **Time windows**: only during your configured hours

**🛡️ Automatic safeguards:**
• **Global cooldown**: minimum 2h between 2 proactive notifications
• **Anti-redundancy**: the LLM sees recent notifications and avoids repeating the same topic
• **Cross-type dedup**: interest notifications are also considered (no thematic spam)
• **Recent activity**: if you just chatted with LIA, no notification will be sent

**💡 In practice:**
You'll receive between 0 and 3 notifications per day, only when relevant. Some days, LIA may decide not to send anything.

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
