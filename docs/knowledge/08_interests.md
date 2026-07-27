# Interests

## How does LIA learn my interests?
LIA learns your interests **automatically** by analyzing your conversations:

**🧠 Automatic learning:**
• LLM analysis of each conversation
• Detection of topics you're passionate about
• Filtering of practical requests (weather, emails...)

**✨ What is detected — one named ground is required, quoted from your own words:**
• You say you like, follow or are into the subject
• You report practising it yourself
• You show you already know it (vocabulary, an opinion you defend)
• You dig into the same subject several times in one exchange

**🚪 What is never an interest:**
The subject of a request ("*what is photosynthesis*"), a remark about LIA itself,
someone else's taste, something tried once, a daily action (mail, calendar,
weather), or anything LIA brought up on its own initiative.

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
1. **Perplexity**: recent news and research
2. **Brave Search**: up-to-date web results
3. **Wikipedia**: encyclopedic articles
4. **AI Reflection**: generated content if no source fits

**⏰ Triggering:**
• Only within your time window (9am-10pm by default)
• Configurable frequency (1 to 5 per day)
• Never when you're actively using chat
• 1-hour global cooldown between notifications

**📱 Delivery:**
• Push notification (even with app closed)
• Real-time display in chat
• Archived in conversation history
• **Clickable source links** at the end of the message (chat), so you can read the original articles

## How do I manage my interests?
Manage your interests in **Settings**:

**⚙️ Access:**
Settings → "*Interests*" section

**🎚️ Global settings:**
• **Enable/Disable** proactive suggestions
• **Time window**: set notification hours (default: 9 AM - 10 PM)
• **Frequency**: min notifications per day (default: 2) and max per day (default: 5)

**📋 Interest list:**
• View all your interests with their weight
• **Block**: no more notifications on this topic, and the subject can no longer be re-created under another name
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
• Temporal decay (0.5%/day without mention)

**⏳ Temporal decay:**
• If you stop talking about a topic, its weight decreases
• Dormant interests after 15 days without mention
• Automatic deletion after 30 days of dormancy

**🌙 Dormant ≠ lost:**
• Dormant interests stay visible in Settings, in a dedicated section
• You can reactivate, edit or delete them at any time

**🎯 Selection for notification (variety-first):**
• Your interests are grouped into **subjects** (e.g. several AI tools = one subject)
• Recently notified subjects are set aside for a while, and rarely served
  subjects get priority — so one passion never monopolizes your notifications
• Within a subject, the least recently covered interest is favored

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
• The subject stays visible to deduplication, so it cannot come back under a
  neighbouring name, be renamed into place, or be deleted to free the slot
• Reversible in settings

**💡 Where to find the buttons:**
Feedback buttons appear **only in the chat message**, not in settings (because they only make sense in the context of a received notification).

## How is duplicate content avoided?
LIA uses several anti-duplicate mechanisms:

**🔄 Duplicate protection:**

**1. Interest deduplication:**
• Semantic similarity via Gemini gemini-embedding-001
• 90% threshold: two similar topics → consolidation
• "*Python*" and "*Python Programming*" = same interest

**2. Content deduplication:**
• SHA256 hash of content (exact comparison)
• Semantic similarity (90% threshold)
• Checked against the last 7 days

**3. Cooldowns:**
• **Global**: 1h minimum between 2 notifications
• **Per topic**: 12h before discussing the same interest again
• **Per subject**: 36h before revisiting the same theme
• **Daily quota**: max N notifications/day

**📊 Result:**
You will never receive the same content twice, nor topics too similar in a row.

## I blocked a topic and it came back — is that fixed?
Yes, and it was a real defect: blocking marked the topic as rejected, but the
learning loop only ever looked at your **active** interests. A blocked topic was
invisible to it, and the next conversation on the subject re-created it under a
slightly different name — one production case came back **twenty-five minutes**
after being blocked.

**🚫 What blocking means now:**
• The topic is compared against every new subject, blocked ones included
• It can no longer be re-created under a neighbouring name
• It can no longer be renamed back into place, nor deleted to free the slot
• The refusal is counted, so a topic LIA keeps rediscovering is visible

**↩️ Still reversible:**
Unblocking from Settings restores the topic exactly as before — blocking is
definitive, not irreversible.

## Why does LIA create fewer new interests than before?
Because a subject you merely asked about is not a taste. Asking "*what is
photosynthesis*" used to create a lasting interest, and the proactive engine then
came back to you about it for weeks.

**🎯 What it takes now:**
A creation requires one of four grounds, and LIA must quote your own words for it:
• You say you like or follow the subject
• You report practising it yourself
• You show you already know it
• You dig into the same subject several times in one exchange

**🛡️ A safety cap on removals:**
An ordinary sentence used to be enough for LIA to propose deleting nineteen
interests — your entire list. A single exchange can now remove at most a couple
of subjects; beyond that the whole batch is refused and recorded.

**📊 Measured:**
On real conversations, half of the exchanges that should have produced nothing
were creating an interest. None do now, and the genuine ones are still caught.
