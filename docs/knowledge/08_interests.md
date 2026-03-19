# Interests

## How does LIA learn my interests?
LIA learns your interests **automatically** by analyzing your conversations:

**🧠 Automatic learning:**
• LLM analysis of each conversation
• Detection of topics you're passionate about
• Filtering of practical requests (weather, emails...)

**✨ What is detected:**
• Expressed enthusiasm or curiosity
• Information requests on a topic
• Repeated mentions of a theme
• Personal opinions shared

**📂 10 categories:**
Technology, Science, Culture, Sports, Finance, Travel, Nature, Health, Entertainment, Other

**🎯 Abstraction level:**
LIA extracts **categories**, not products. Example: "*iPhone 18 Pro*" → "*Apple Smartphones, iOS*"

## How do proactive notifications work?
LIA sends you relevant content on your favorite topics:

**📬 Principle:**
• Notifications sent **without you asking**
• Content adapted to your interests
• Personalized with LIA's active personality

**📚 Content sources:**
1. **Wikipedia**: encyclopedic articles
2. **Perplexity**: recent news and research
3. **AI Reflection**: generated content if no source fits

**⏰ Triggering:**
• Only within your time window (9am-10pm by default)
• Configurable frequency (1 to 5 per day)
• Never when you're actively using chat
• 2-hour global cooldown between notifications

**📱 Delivery:**
• Push notification (even with app closed)
• Real-time display in chat
• Archived in conversation history

## How do I manage my interests?
Manage your interests in **Settings**:

**⚙️ Access:**
Settings → "*Interests*" section

**🎚️ Global settings:**
• **Enable/Disable** proactive suggestions
• **Time window**: set notification hours (9am-10pm by default)
• **Frequency**: min/max notifications per day (1-5)

**📋 Interest list:**
• View all your interests with their weight
• **Block**: no more notifications on this topic
• **Delete**: permanently remove
• **Add manually**: create an interest

**🏷️ Filter by category:**
Navigate by type (Technology, Science, Culture...)

## How does the weight system work?
Each interest has a **weight** that evolves:

**📊 Weight calculation:**
• **Bayesian** algorithm (Beta distribution)
• Starts with a slightly positive prior
• Increases with positive signals
• Decreases with negative signals

**📈 Positive signals (+weight):**
• Mentioning the topic in a conversation
• Clicking "*I like this topic*" 👍

**📉 Negative signals (-weight):**
• Clicking "*Less interested*" 👎
• Temporal decay (1%/day without mention)

**⏳ Temporal decay:**
• If you stop talking about a topic, its weight decreases
• Dormant interests after 30 days
• Automatic deletion after 90 days of inactivity

**🎯 Selection for notification:**
Interests with the **highest weight** are more likely to be chosen

## How do I give feedback on a notification?
When you receive a notification, give your opinion:

**👍 "I like this topic":**
• +2 positive signals
• The topic will be suggested more often
• Use when the message was interesting

**👎 "Less interested":**
• +2 negative signals
• The topic will be suggested less
• Use if it wasn't relevant this time

**🚫 "Never suggest again":**
• Permanently blocks this topic
• No more notifications on this theme
• Reversible in settings

**💡 Where to find the buttons:**
Feedback buttons appear **only in the chat message**, not in settings (because they only make sense in the context of a received notification).

## How is duplicate content avoided?
LIA uses several anti-duplicate mechanisms:

**🔄 Duplicate protection:**

**1. Interest deduplication:**
• Semantic similarity via E5 embeddings
• 90% threshold: two similar topics → consolidation
• "*Python*" and "*Python Programming*" = same interest

**2. Content deduplication:**
• SHA256 hash of content (exact comparison)
• Semantic similarity (85% threshold)
• Checked against the last 30 days

**3. Cooldowns:**
• **Global**: 2h minimum between 2 notifications
• **Per topic**: 24h before discussing the same theme again
• **Daily quota**: max N notifications/day

**📊 Result:**
You will never receive the same content twice, nor topics too similar in a row.
