# External Services Examples

## How do I get the current weather?
**OpenWeatherMap** - Real-time weather:

**🌤️ Current weather:**
• "*What's the weather in Paris?*"
• "*Current temperature in New York*"
• "*Is it raining in London?*"
• "*Weather here*" (uses your configured position)

**📊 Information provided:**
• Temperature (feels like and actual)
• Conditions (sunny, cloudy, rain...)
• Humidity and pressure
• Wind speed and direction
• Visibility
• Sunrise/sunset times

**💡 Tip:**
Add the OpenWeatherMap connector (free) in Settings > Connectors to enable this feature.

## Which services work without configuration?
Some services are **immediately available**, others require configuration:

**✅ Available without configuration:**
• 📚 **Wikipedia**: Free encyclopedic search
• 🌐 **Web Page Reader**: Web page reading (URL → content)
• 💬 **Conversation**: LIA answers your general questions

**🔐 Require Google connection:**
• 📧 Gmail
• 📅 Google Calendar
• 👥 Google Contacts
• 📁 Google Drive
• ✅ Google Tasks
• 📍 Google Places
• 🗺️ Google Routes (Directions)

**🔑 Require an API key:**
• 🌤️ **OpenWeatherMap**: Free, signup at openweathermap.org
• 🔍 **Perplexity**: Paid, signup at perplexity.ai

**💡 Require Philips Hue bridge setup:**
• 💡 **Philips Hue**: Connect your Hue bridge in Settings > Connectors

**💡 Getting started tip:**
Start by connecting your Google services (one authorization for all), then add OpenWeatherMap for free weather.

## How do I get directions?
**Google Routes** - Route calculation:

**🗺️ Simple directions:**
• "*How do I get from Paris to Lyon?*"
• "*Directions to Marseille*"
• "*How do I get to the airport?*"
• "*Travel time between Paris and Bordeaux*"

**📍 From my location:**
• "*How do I get to work?*" (uses your position)
• "*Directions to the restaurant*"

**📊 Information provided:**
• Total distance in kilometers/miles
• Estimated duration (with and without traffic)
• Interactive map with route
• Turn-by-turn directions
• Real-time traffic conditions

**💡 Tip:**
Set your home address in Settings > Connectors > Google Places for "*from home*" searches.

## How do I choose the travel mode?
**Google Routes** - Travel modes:

**🚗 By car (default):**
• "*Driving directions to Lyon*"
• "*How long by car to Marseille?*"
• Includes real-time traffic

**🚶 On foot:**
• "*How do I get there on foot?*"
• "*Walking directions to the station*"
• Suitable for short distances

**🚴 By bike:**
• "*Cycling directions to the park*"
• "*How do I get to the office by bike?*"
• Prefers bike lanes

**🚌 By public transit:**
• "*How do I get there by transit?*"
• "*Subway to the Eiffel Tower*"
• "*Bus to downtown*"
• Shows lines, transfers and schedules

**🏍️ By motorcycle:**
• "*Motorcycle directions*"
• "*By scooter to work*"

## How do I avoid tolls and highways?
**Google Routes** - Avoidance options:

**💰 Avoid tolls:**
• "*Directions to Lyon without tolls*"
• "*Toll-free route to Bordeaux*"
• "*How do I get to Nice avoiding tolls?*"

**🛣️ Avoid highways:**
• "*Directions without highways*"
• "*Local roads to Marseille*"
• "*Avoiding the freeway*"

**⛴️ Avoid ferries:**
• "*Without taking the ferry*"
• "*Avoiding sea crossings*"

**🔄 Possible combinations:**
• "*Directions to Lyon without tolls and without highways*"
• "*Toll-free route by bike*"

**💡 Tip:**
Toll-free trips may take longer but save on road fees.

## How do I plan a trip with multiple stops?
**Google Routes** - Multi-stop trips:

**📍 With waypoints:**
• "*Directions Paris-Lyon via Dijon*"
• "*Route to Nice with a stop in Avignon*"
• "*From home to the airport via the office*"

**🔄 Automatic optimization:**
• "*Best order to visit Paris, Lyon and Marseille*"
• "*Optimize my trip between these 3 addresses*"
• LIA can reorder stops to minimize distance

**📊 Multi-stop information:**
• Total distance and duration
• Duration of each segment
• Map with all waypoints

**⚠️ Limits:**
• Maximum 25 waypoints
• For more, split into multiple routes

**💡 Tip:**
Use references like "*my brother's place*" or "*yesterday's restaurant*" - LIA automatically resolves addresses.

## How do I use directions with my contacts and events?
**Google Routes** - Multi-domain integration:

**👥 To a contact:**
• "*How do I get to my brother's place?*"
• "*Directions to Mary's address*"
• "*Travel time to Dr. Martin's office*"
• LIA finds the address in your contacts

**📅 To an event:**
• "*How do I get to my 2pm meeting?*"
• "*Directions to my next appointment*"
• "*How long to get to tomorrow's event?*"
• LIA uses the calendar event location

**📍 To a recent place:**
• "*Go back to yesterday's restaurant*"
• "*How do I get back to the museum I visited this morning?*"

**🔗 Advanced combinations:**
• "*Send an email to John saying I'll arrive in 30 minutes*" → LIA calculates time and sends the message
• "*Create an event tomorrow in Lyon with directions*"

**💡 Tip:**
The more you enrich your contacts with addresses, the more naturally LIA can guide you.

## How do I read the content of a web page?
**Web Page Reader** - Web page reading:

**🌐 Read an article or page:**
• "*Read this article: https://example.com/article*"
• "*What does this page say? https://korben.info*"
• "*Summarize this web page: https://...*"
• "*What articles are on this page?*"

**📖 What LIA does:**
• Fetches the full page content
• Extracts the main article (smart mode)
• Converts to clean, readable text
• Automatically detects the page language

**📊 Information provided:**
• Page title
• Clean text content (Markdown)
• Word count
• Detected language

**⚠️ Limitations:**
• Public pages only (no login-protected content)
• HTML pages only (no PDF, no images)
• No JavaScript rendering (some dynamic sites may be incomplete)
• Max size: 500 KB

**✅ Free, no configuration required.**

## When should I use Web Page Reader vs web search?
Choose the right tool based on your needs:

**🌐 Use WEB PAGE READER for:**
• Reading the full content of a URL you know
• Summarizing a specific article
• Analyzing the content of a particular page
• Comparing content across multiple pages
• "*Read this article: https://...*"

**🔍 Use WEB SEARCH for:**
• Finding information about a topic
• Getting recent news
• Searching without knowing the exact URL
• "*What's the latest news about X?*"

**🔗 Ideal combination:**
1. Web search → finds relevant URLs
2. Web Page Reader → reads the full content of a result

**💡 Example:**
• "*Search for articles about Rust*" → Web search (Perplexity/Brave)
• "*Read this article: https://blog.rust-lang.org/...*" → Web Page Reader (full content)

## What is Browser Control and when should I use it?
Browser Control lets LIA interact with websites like a real user: navigate, search, click, fill forms, and extract data from JavaScript-rendered pages.

**Use for:** searching products on e-commerce, filling forms, extracting dynamic content.
**Examples:**
- Go to amazon.fr and search for MacBook Pro M4
- Go to nike.com and find white Nike Air for men with prices

## How does the browser agent work?
It uses headless Chromium (Playwright) to: navigate, handle cookies automatically, wait for JS rendering, extract visible content, and interact if needed. The agent decides autonomously which actions to take. Takes 15-60 seconds per task.

## How do I get the weather forecast?
**OpenWeatherMap** - Detailed forecasts:

**📅 Multi-day forecasts:**
• "*What will the weather be like tomorrow in Lyon?*"
• "*5-day forecast for Marseille*"
• "*Will it rain this weekend in Paris?*"

**⏰ Hourly forecasts:**
• "*Hourly forecast for today*"
• "*Temperature this evening at 8pm*"
• "*Will it rain this afternoon?*"

**📊 What you get:**
• Min/max temperature per day
• Precipitation probability
• Expected wind speed
• Condition evolution

**💡 Planning:**
Useful for planning activities: "*What's the best day for a picnic this week?*"

## What is the difference between Browser Control and Web Fetch?
Web Fetch: static HTML, read-only, fast (1-3s), cheap. Browser Control: full JS execution, click/fill/search, slower (15-60s), more expensive but handles dynamic pages and interaction.

## How do I get Wikipedia information?
**Wikipedia** - Get information directly:

**✅ GOOD PHRASING** (direct information):
• "*Who is Elon Musk?*"
• "*Tell me about the Eiffel Tower*"
• "*Information about Marie Curie*"
• "*What is photosynthesis?*"

→ LIA gives you directly the **article content** with a full summary.

**⚠️ AVOID** (returns a list of articles):
• "*Search Wikipedia for...*"
• "*Find articles about...*"

→ These phrasings return a **list of links** instead of content.

**💡 Simple rule:**
Ask your question like you would to a friend: "*Who is X?*", "*What is X?*", "*Tell me about X*" rather than "*Search for X*".

**🌍 Multilingual:**
LIA automatically chooses the Wikipedia version matching your language.

**✅ Free, no configuration required.**

## How do I get the full Wikipedia article?
**Wikipedia** - Full article vs summary:

**📝 Default: Summary**
LIA provides a substantial summary (up to 5000 characters) with essential information.

**📖 For the full article:**
Ask explicitly:
• "*Give me the full article on Napoleon*"
• "*Detailed Wikipedia article on climate change*"
• "*I want the entire article on the French Revolution*"

**🔗 Related topics:**
• "*What are the articles related to space exploration?*"
• "*Topics related to the Renaissance*"

**🔍 When to use search?**
Use "*search Wikipedia*" only if:
• You don't know the exact title
• The topic is ambiguous (multiple homonyms)
• You want to explore different articles

**💡 Example:**
• "*Who is Victor Hugo?*" → Direct summary
• "*Full article on Victor Hugo*" → Detailed article
• "*Search Victor Hugo*" → List of related articles

## How do I use Perplexity (Search vs Ask)?
**Perplexity AI** - Two modes of use:

**🔍 SEARCH MODE** (news, web search):
• "*Latest news on artificial intelligence*"
• "*Latest Apple news*"
• "*Football game results yesterday*"
• "*Flight prices Paris-Tokyo*"

→ Use for: **recent news**, events, trends, real-time prices.

**❓ ASK MODE** (complex questions, synthesis):
• "*Explain how blockchain works*"
• "*What are the pros and cons of electric cars?*"
• "*Compare different machine learning methods*"
• "*Analyze current real estate market trends*"

→ Use for: **in-depth analysis**, syntheses, comparisons, complex explanations.

**💡 How to choose?**
• News/Recent facts → "*Search...*", "*News...*"
• Complex question → "*Explain...*", "*Analyze...*", "*Compare...*"

**📌 Sources and citations:**
Perplexity always provides the web sources used for its answers.

**⚠️ Configuration required:**
Perplexity requires an API key (paid service).

## When should I use Perplexity vs Wikipedia?
Choose the right tool based on your needs:

**📚 Use WIKIPEDIA for:**
• Established historical facts
• Scientific definitions and concepts
• Biographies of notable people
• Geographic information
• Verified encyclopedic content
• ✅ Free, no configuration

**🔍 Use PERPLEXITY for:**
• Current events and recent news
• Product comparisons and reviews
• Real-time information (prices, schedules)
• Current trends and opinions
• Questions requiring multiple sources
• ⚠️ Requires API key

**💡 Concrete example:**
• "*Who invented the light bulb?*" → Wikipedia (historical fact)
• "*What's the best LED bulb this year?*" → Perplexity (recent comparison)

## How do I search for places with Google Places?
**Google Places** - Location search:

**📍 Nearby search:**
• "*Find restaurants near me*"
• "*Pharmacies open now*"
• "*Where is the nearest gas station?*"
• "*Supermarkets within 1 mile*"

**📍 Search by area:**
• "*Italian restaurants in downtown Paris*"
• "*Hotels near the Eiffel Tower*"
• "*Museums in central Lyon*"

**📊 Information displayed:**
• Place name and address
• Rating (stars) and number of reviews
• Opening hours
• Phone number
• Distance from your position

**💡 Configuration:**
For "*near me*" searches, set your default position in settings or specify the city.

## How do I get place details?
**Google Places** - Detailed information:

**📋 Request details:**
• "*Show me details about the Louvre Museum*"
• "*Opening hours for Starbucks on Rivoli Street*"
• "*Phone number for Dr. Martin's office*"
• "*Reviews for the Marriott Hotel in Lyon*"

**📊 Available information:**
• **Place photo**: click to enlarge (2x zoom)
• **Exact address** with GPS coordinates
• **Phone number**
• **Official website**
• **Opening hours** (day by day)
• **Average rating** and number of reviews
• **Price range** (restaurants)
• **Types of services** available

**📷 Clickable photos:**
Place photos are clickable and display larger in a modal window. Click anywhere to close or use the Escape key.

**💡 After a search:**
Say "*more details on the first one*" or "*Italian restaurant hours*" to dig deeper.

## How do I control my Philips Hue lights?
**Philips Hue** - Smart home control:

**💡 Control individual lights:**
• "*Turn on the living room lamp*"
• "*Set bedroom light to 50% brightness*"
• "*Change the kitchen light to warm white*"
• "*Turn off all lights*"

**🏠 Control rooms:**
• "*Turn off the bedroom*"
• "*Dim the living room to 30%*"
• "*List all my rooms*"

**🎨 Activate scenes:**
• "*Activate the 'Relax' scene*"
• "*Set the living room to 'Movie Night'*"
• "*What scenes are available?*"

**📊 Information provided:**
• Light name, status (on/off), brightness level
• Room name and associated lights
• Available scenes per room

**💡 Setup:**
Connect your Philips Hue bridge in **Settings > Connectors > Philips Hue**. LIA supports both local bridge control (API key) and remote cloud access (OAuth).

## Can I combine multiple services?
Yes! LIA can **intelligently combine** multiple services:

**🔗 Combination examples:**

**Weather + Calendar:**
• "*What will the weather be for my meeting tomorrow?*"
• LIA checks your calendar and the weather

**Email + Contacts:**
• "*Send an email to my contact John Smith*"
• LIA finds John's email in your contacts

**Places + Calendar:**
• "*Create an event tomorrow at noon at The Bistro restaurant, 10 Main Street*"
• Combining event creation and address

**Wikipedia + Questions:**
• "*How old was Marie Curie when she got her Nobel Prize?*"
• LIA searches and calculates

**💡 Tip:**
Phrase your requests naturally - LIA will automatically choose the right tools.
