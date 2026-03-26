# LIA Tool Catalogue

Complete inventory of agents and tools available for skill generation.
All tool names and parameters are verified against the source code.

> **For plan_template steps**: use `agent_name` and `tool_name` exactly as listed below.
> Parameters marked (required) must be provided. Others are optional with sensible defaults.

---

## Google Calendar — `event_agent`

Requires OAuth. Domain: `event`.

### get_events_tool (unified)
Search, list, or fetch calendar events.
- `query` (string) — Natural language search query
- `event_id` (string) — Fetch a specific event by ID
- `event_ids` (list[string]) — Batch fetch multiple events
- `time_min` (string) — Start of time range (ISO 8601)
- `time_max` (string) — End of time range (ISO 8601)
- `days_ahead` (int) — Shortcut: fetch events for the next N days from now
- `max_results` (int) — Maximum number of results
- `calendar_id` (string) — Target calendar (default: primary)

### create_event_tool
- `summary` (string, required) — Event title
- `start_datetime` (string, required) — Start date/time (ISO 8601)
- `end_datetime` (string, required) — End date/time (ISO 8601)
- `timezone` (string) — Timezone (e.g., "Europe/Paris")
- `description` (string) — Event description
- `location` (string) — Event location
- `attendees` (list[string]) — Email addresses of attendees
- `calendar_id` (string) — Target calendar

### update_event_tool
- `event_id` (string, required) — Event to update
- `summary`, `start_datetime`, `end_datetime`, `timezone`, `description`, `location`, `attendees`, `calendar_id` — Same as create (all optional)

### delete_event_tool
- `event_id` (string, required) — Event to delete
- `send_updates` (string, default: "all") — Notification policy
- `calendar_id` (string) — Target calendar

### list_calendars_tool
- `show_hidden` (bool, default: false) — Include hidden calendars
- `max_results` (int, default: 100)

---

## Gmail — `email_agent`

Requires OAuth. Domain: `email`.

### get_emails_tool (unified)
Search, list, or fetch emails.
- `query` (string) — Gmail search query (e.g., `"in:inbox newer_than:1d"`, `"from:user@example.com"`)
- `message_id` (string) — Fetch a specific email by ID
- `message_ids` (list[string]) — Batch fetch multiple emails
- `max_results` (int) — Maximum number of results
- `use_cache` (bool, default: true) — Use cached results

### send_email_tool
- `to` (string, required) — Recipient email address
- `subject` (string) — Email subject
- `body` (string) — Email body text
- `content_instruction` (string) — Instruction for LLM to compose the body
- `cc` (string) — CC recipients
- `bcc` (string) — BCC recipients
- `is_html` (bool, default: false) — Send as HTML

### reply_email_tool
- `message_id` (string, required) — Email to reply to
- `body` (string, required) — Reply body text
- `reply_all` (bool, default: false) — Reply to all recipients

### forward_email_tool
- `message_id` (string, required) — Email to forward
- `to` (string, required) — Forward recipient
- `body` (string) — Additional message
- `cc` (string) — CC recipients

### delete_email_tool
- `message_id` (string, required) — Email to delete (moves to trash)

---

## Gmail Labels — `email_agent`

Requires OAuth. Same agent as Gmail.

### list_labels_tool
- `name_filter` (string) — Filter labels by name substring
- `include_system` (bool, default: false) — Include system labels

### create_label_tool
- `name` (string, required) — Label name

### update_label_tool
- `label_name` (string, required) — Current label name
- `new_name` (string, required) — New label name

### delete_label_tool
- `label_name` (string, required) — Label to delete
- `children_only` (bool, default: false) — Delete only child labels

### apply_labels_tool
- `label_names` (list[string], required) — Labels to apply
- `message_id` (string) — Single message target
- `message_ids` (list[string]) — Batch target
- `auto_create` (bool, default: true) — Create label if it doesn't exist

### remove_labels_tool
- `label_names` (list[string], required) — Labels to remove
- `message_id` (string) — Single message target
- `message_ids` (list[string]) — Batch target

---

## Google Contacts — `contact_agent`

Requires OAuth. Domain: `contact`.

### get_contacts_tool (unified)
Search, list, or fetch contacts.
- `query` (string) — Search query (name, email, phone)
- `resource_name` (string) — Fetch specific contact by resource name
- `resource_names` (string|list) — Batch fetch
- `max_results` (int) — Maximum number of results
- `fields` (list[string]) — Specific fields to return

### create_contact_tool
- `name` (string, required) — Full name
- `email` (string) — Email address
- `phone` (string) — Phone number
- `organization` (string) — Company/organization
- `notes` (string) — Notes

### update_contact_tool
- `resource_name` (string, required) — Contact to update
- `name`, `email`, `phone`, `organization`, `notes` (all optional) — Fields to update
- `address` (string) — Postal address

### delete_contact_tool
- `resource_name` (string, required) — Contact to delete

---

## Google Drive — `file_agent`

Requires OAuth. Domain: `file`.

### get_files_tool (unified)
Search, list, or fetch files.
- `query` (string) — Search query
- `file_id` (string) — Fetch specific file by ID
- `file_ids` (list[string]) — Batch fetch
- `folder_id` (string) — List files in specific folder
- `max_results` (int) — Maximum number of results
- `include_content` (bool, default: false) — Include file content in response
- `content_type` (string, default: "files_only") — `"files_only"` | `"folders_only"` | `"all"`
- `mime_type` (string) — Filter by MIME type
- `search_mode` (string, default: "name_only") — `"name_only"` | `"full_text"`

---

## Google Tasks — `task_agent`

Requires OAuth. Domain: `task`.

### get_tasks_tool (unified)
Search, list, or fetch tasks.
- `task_id` (string) — Fetch specific task by ID
- `task_ids` (list[string]) — Batch fetch
- `task_list_id` (string) — Target task list
- `max_results` (int) — Maximum number of results
- `show_completed` (bool, default: false) — Include completed tasks
- `only_completed` (bool, default: false) — Show only completed tasks

### create_task_tool
- `title` (string, required) — Task title
- `notes` (string) — Task notes/description
- `due` (string) — Due date (ISO 8601)
- `task_list_id` (string, default: "@default") — Target task list

### update_task_tool
- `task_id` (string, required) — Task to update
- `title` (string) — New title
- `notes` (string) — New notes
- `due` (string) — New due date
- `status` (string) — New status
- `task_list_id` (string, default: "@default")

### complete_task_tool
- `task_id` (string, required) — Task to mark as completed
- `task_list_id` (string, default: "@default")

### delete_task_tool
- `task_id` (string, required) — Task to delete
- `task_list_id` (string, default: "@default")

### list_task_lists_tool
- `max_results` (int, default: 20)

---

## Web Search — `web_search_agent`

No OAuth. Domain: `web_search`. Combines Perplexity + Brave + Wikipedia.

### unified_web_search_tool
- `query` (string, required) — Search query
- `recency` (string) — Filter by recency: `"day"` | `"week"` | `"month"`

---

## Web Fetch — `web_fetch_agent`

No OAuth. Domain: `web_fetch`.

### fetch_web_page_tool
- `url` (string, required) — URL to fetch
- `extract_mode` (string, default: "article") — `"article"` (main content) | `"full"` (entire page)
- `max_length` (int, default: 30000) — Max content length in characters

---

## Wikipedia — `wikipedia_agent`

No OAuth. Domain: `wikipedia`.

### search_wikipedia_tool
- `query` (string, required) — Search query
- `language` (string, default: "fr") — Wikipedia language code
- `max_results` (int, default: 5)

### get_wikipedia_summary_tool
- `title` (string, required) — Article title
- `language` (string, default: "fr")

### get_wikipedia_article_tool
- `title` (string, required) — Article title
- `language` (string, default: "fr")
- `sections` (bool, default: true) — Include section headers
- `max_length` (int, default: 10000)

### get_wikipedia_related_tool
- `title` (string, required) — Article title
- `language` (string, default: "fr")
- `max_results` (int, default: 10)

---

## Perplexity — `perplexity_agent`

No OAuth. Domain: `perplexity`. AI-powered web search.

### perplexity_search_tool
- `query` (string, required) — Search query
- `recency` (string, default: "none") — `"day"` | `"week"` | `"month"` | `"none"`
- `include_citations` (bool, default: true)

### perplexity_ask_tool
- `question` (string, required) — Question to ask
- `context` (string) — Additional context for the question

---

## Brave Search — `brave_agent`

No OAuth. Domain: `brave`. Web and news search.

### brave_search_tool
- `query` (string, required) — Search query
- `count` (int, default: 5) — Number of results (1-10)
- `freshness` (string) — `"pd"` (past day) | `"pw"` (past week) | `"pm"` (past month) | `"py"` (past year)

### brave_news_tool
- `query` (string, required) — News search query
- `count` (int, default: 5) — Number of results (1-10)
- `freshness` (string) — `"pd"` | `"pw"` | `"pm"`

---

## Places — `place_agent`

No OAuth. Domain: `place`. Google Places API.

### get_places_tool (unified)
Search, list, or fetch places.
- `query` (string) — Search query (e.g., "restaurants italiens")
- `location` (string) — Location reference (address or "near me")
- `place_id` (string) — Fetch specific place by ID
- `place_ids` (list[string]) — Batch fetch
- `place_type` (string) — Place type filter (e.g., "restaurant", "hospital")
- `max_results` (int) — Maximum number of results
- `radius_meters` (int) — Search radius in meters
- `open_now` (bool, default: false) — Only places currently open
- `min_rating` (float) — Minimum rating (1.0-5.0)
- `price_levels` (list[string]) — Price level filter

### get_current_location_tool
No parameters. Returns the user's current location.

---

## Routes — `route_agent`

No OAuth. Domain: `route`. Google Routes API.

### get_route_tool
- `destination` (string, required) — Destination address or place
- `origin` (string) — Origin address (default: user's current location)
- `travel_mode` (string) — `"DRIVE"` | `"WALK"` | `"BICYCLE"` | `"TRANSIT"` | `"TWO_WHEELER"`
- `avoid_tolls` (bool, default: false)
- `avoid_highways` (bool, default: false)
- `avoid_ferries` (bool, default: false)
- `departure_time` (string) — Departure time (ISO 8601)
- `arrival_time` (string) — Desired arrival time (ISO 8601)
- `waypoints` (list[string]) — Intermediate stops
- `optimize_waypoints` (bool, default: false) — Optimize waypoint order

### get_route_matrix_tool
- `origins` (list[string], required) — List of origin addresses
- `destinations` (list[string], required) — List of destination addresses
- `travel_mode` (string) — Same options as get_route_tool
- `departure_time` (string) — Departure time (ISO 8601)

---

## Weather — `weather_agent`

No OAuth. Domain: `weather`.

### get_current_weather_tool
- `location` (string) — Location (default: user's location)
- `user_message` (string) — User's original message for context
- `date` (string) — Date for weather query
- `units` (string, default: "metric") — `"metric"` | `"imperial"`
- `language` (string, default: "fr")

### get_weather_forecast_tool
- `location` (string) — Location
- `user_message` (string) — User's original message
- `date` (string) — Start date
- `days` (int) — Number of forecast days (1-5)
- `units` (string, default: "metric")
- `language` (string, default: "fr")

### get_hourly_forecast_tool
- `location` (string) — Location
- `user_message` (string) — User's original message
- `date` (string) — Date
- `hours` (int, default: 24) — Number of hours (1-48)
- `units` (string, default: "metric")
- `language` (string, default: "fr")

---

## Reminders — `reminder_agent`

No OAuth. Domain: `reminder`.

### create_reminder_tool
- `content` (string, required) — Reminder content/message
- `original_message` (string, required) — User's original request (for context)
- `trigger_datetime` (string) — When to trigger (ISO 8601)
- `relative_trigger` (string) — Relative trigger (e.g., "in 30 minutes", "tomorrow at 9am")

### list_reminders_tool
No parameters. Returns all active reminders.

### cancel_reminder_tool
- `reminder_identifier` (string, required) — Reminder ID or description to cancel

---

## Query Engine — `query_agent`

No OAuth. Domain: `query`. Local data query engine.

### local_query_engine_tool
- `query` (object, required) — Structured query with `operation`, `target_type`, `conditions`, `group_by`, `sort_by`
- `source` (string) — Data source (default: "registry")

---

## Context — `context_agent`

No OAuth. Domain: `context`. Internal cross-domain utilities. `is_routable=false`.

### resolve_reference
- `reference` (string, required) — Reference to resolve (e.g., "the first one", "that email")
- `domain` (string) — Domain hint for resolution

### set_current_item
- `reference` (string, required) — Item reference
- `domain` (string, required) — Domain (e.g., "email", "contact")

### get_context_state
- `domain` (string, required) — Domain to inspect

### list_active_domains
No parameters. Returns list of domains with active context.

### get_context_list
- `domain` (string, required) — Domain to list items from

---

## Browser — `browser_agent`

No OAuth. Domain: `browser`. Interactive web browsing via Playwright + accessibility tree.

### browser_task_tool (primary)
Execute a complete browsing task autonomously (navigate, click, fill, search, extract).
- `task` (string, required) — Natural language description of the browsing task

> Internal tools used by the browser agent ReAct loop (not directly callable in plan_template):
> `browser_navigate_tool`, `browser_snapshot_tool`, `browser_click_tool`, `browser_fill_tool`, `browser_press_key_tool`

---

## Philips Hue — `hue_agent`

Requires Hue Bridge connector. Domain: `hue`. Smart lighting control via CLIP v2 API.

### list_hue_lights_tool
No parameters. Lists all lights with their current state (on/off, brightness, color).

### control_hue_light_tool
- `light_name_or_id` (string, required) — Name or ID of the light (e.g., "Bedroom lamp")
- `on` (bool) — Turn light on (true) or off (false)
- `brightness` (int) — Brightness percentage 0-100
- `color` (string) — Color name (red, blue, warm_white, etc.) or CIE "x,y" coordinates

### list_hue_rooms_tool
No parameters. Lists all rooms with their devices.

### control_hue_room_tool
- `room_name_or_id` (string, required) — Name or ID of the room
- `on` (bool) — Turn all lights on (true) or off (false)
- `brightness` (int) — Brightness percentage 0-100 for all lights

### list_hue_scenes_tool
No parameters. Lists all available preset scenes.

### activate_hue_scene_tool
- `scene_name_or_id` (string, required) — Name or ID of the scene to activate (e.g., "Movie", "Relax")

---

## Image Generation — `image_generation_agent`

No OAuth. Domain: `image_generation`. AI image generation and editing.

### generate_image
- `prompt` (string, required) — Detailed text description of the image to generate

### edit_image
- `prompt` (string, required) — Text description of the desired modification
- `source_attachment_id` (string) — UUID of the image to edit (auto-resolves to latest if omitted)

---

## MCP — `mcp_agent`

Virtual agent. Domain: `mcp`. Tools are dynamically registered from external MCP servers.
Tool names and parameters depend on the user's configured MCP servers.
Cannot be used in static plan_template steps.

---

## Tools Available Only via Response Node

These tools are registered via feature flags and are NOT part of domain_taxonomy.
They cannot be used in plan_template steps.

| Tool | Description | Feature Flag |
|------|-------------|:---:|
| `activate_skill_tool` | Load a skill's L2 instructions | `SKILLS_ENABLED` |
| `read_skill_resource` | Read a bundled resource file from a skill | `SKILLS_ENABLED` |
| `run_skill_script` | Execute a Python script from a skill | `SKILLS_ENABLED` + `SKILLS_SCRIPTS_ENABLED` |
| `delegate_to_sub_agent_tool` | Delegate a task to a specialized sub-agent | `SUB_AGENTS_ENABLED` |

---

*Last updated: 2026-03-26. Source: apps/api/src/domains/agents/tools/*
